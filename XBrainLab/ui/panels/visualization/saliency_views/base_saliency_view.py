from __future__ import annotations

import logging
import threading
import traceback
import weakref
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from types import ModuleType
from typing import Any, cast

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.backend_bases import Event, MouseEvent
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, Qt, QThread, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application.state import SaliencyMethodCoverageSnapshot
from XBrainLab.ui.core.worker import Worker
from XBrainLab.ui.styles.theme import Theme

logger = logging.getLogger(__name__)
_ACTIVE_RENDER_CLEANUP_OWNERS: set[_RenderCleanupOwner] = set()
_ACTIVE_NATIVE_PLOT_CLEANUP_OWNERS: set[_NativePlotCleanupOwner] = set()
SALIENCY_RENDER_FAILED_TEXT = (
    "Saliency could not be rendered. Try again or choose another saliency view."
)
SALIENCY_PREPARATION_FAILED_TEXT = (
    "This saliency view could not be prepared. "
    "Recompute saliency or choose another view."
)
_SAFE_SALIENCY_DETAIL_PREFIXES = (
    "Cannot map EEG event ",
    "Could not map EEG event ",
    "No saliency samples are available for EEG event ",
    "No montage positions found.",
    "3D head model assets are not installed:",
    "Failed to map any channels to 3D positions.",
    "3D saliency requires at least one time sample.",
)


class SaliencyViewUnavailableError(ValueError):
    """Controlled, user-facing saliency readiness message."""


def _dispose_figure(figure: Figure | None) -> None:
    """Release a Matplotlib figure and break its canvas reference cycle."""
    if figure is None:
        return
    canvas = getattr(figure, "canvas", None)
    if isinstance(canvas, QWidget):
        widget_canvas = cast(QWidget, canvas)
        if hasattr(widget_canvas, "_draw_pending"):
            cast(Any, widget_canvas)._draw_pending = False
        with suppress(RuntimeError):
            widget_canvas.hide()
            widget_canvas.close()
            widget_canvas.setParent(None)
            widget_canvas.deleteLater()
    with suppress(Exception):
        plt.close(figure)
    with suppress(Exception):
        figure.clear()
    _disconnect_figure_canvas(figure, canvas)


def _disconnect_figure_canvas(figure: Figure | None, canvas: object) -> None:
    if figure is not None and getattr(figure, "canvas", None) is canvas:
        with suppress(Exception):
            cast(Any, figure).canvas = None
    if canvas is not None and getattr(canvas, "figure", None) is figure:
        with suppress(Exception):
            cast(Any, canvas).figure = None


def _render_callable_captures_qwidget(render_fn: Callable[[], object]) -> bool:
    """Return whether a bounded callable graph captures a QWidget."""
    seen: set[int] = set()
    max_nodes = 512
    max_depth = 10
    max_attributes = 128

    def captures(value: object, *, depth: int = 0) -> bool:
        if depth > max_depth or len(seen) >= max_nodes:
            return False
        value_id = id(value)
        if value_id in seen:
            return False
        seen.add(value_id)
        if isinstance(value, QWidget):
            return True
        if isinstance(value, (ModuleType, type)):
            return False
        if isinstance(value, partial):
            return (
                captures(value.func, depth=depth + 1)
                or any(captures(item, depth=depth + 1) for item in value.args)
                or any(
                    captures(item, depth=depth + 1)
                    for item in (value.keywords or {}).values()
                )
            )
        if isinstance(value, dict):
            items = list(value.items())[:max_attributes]
            return any(
                captures(item, depth=depth + 1) for pair in items for item in pair
            )
        if isinstance(value, (list, tuple, set, frozenset)):
            return any(
                captures(item, depth=depth + 1) for item in list(value)[:max_attributes]
            )
        bound_self = getattr(value, "__self__", None)
        if bound_self is not None and captures(bound_self, depth=depth + 1):
            return True
        closure = getattr(value, "__closure__", None)
        if closure is not None:
            for cell in closure:
                with suppress(ValueError):
                    if captures(cell.cell_contents, depth=depth + 1):
                        return True
        defaults = getattr(value, "__defaults__", None)
        if defaults is not None and captures(defaults, depth=depth + 1):
            return True
        keyword_defaults = getattr(value, "__kwdefaults__", None)
        if keyword_defaults is not None and captures(
            keyword_defaults,
            depth=depth + 1,
        ):
            return True
        attributes = getattr(value, "__dict__", None)
        if not callable(value):
            return False
        if isinstance(attributes, dict) and any(
            captures(attribute, depth=depth + 1)
            for attribute in list(attributes.values())[:max_attributes]
        ):
            return True
        slot_names: list[str] = []
        for cls in getattr(type(value), "__mro__", ())[:8]:
            declared_slots = getattr(cls, "__slots__", ())
            if isinstance(declared_slots, str):
                declared_slots = (declared_slots,)
            slot_names.extend(
                str(slot)
                for slot in declared_slots
                if slot not in {"__dict__", "__weakref__"}
            )
            if len(slot_names) >= max_attributes:
                break
        for slot_name in slot_names[:max_attributes]:
            with suppress(AttributeError, RuntimeError):
                if captures(
                    getattr(value, slot_name),
                    depth=depth + 1,
                ):
                    return True
        return False

    return captures(render_fn)


def safe_saliency_detail(
    detail: object,
    *,
    fallback: str = SALIENCY_RENDER_FAILED_TEXT,
) -> str:
    """Allow only reviewed product details to cross the UI boundary."""
    message = str(detail).strip()
    if message.startswith(_SAFE_SALIENCY_DETAIL_PREFIXES):
        return message
    return fallback


def _start_worker_atomically(
    *,
    worker_factory: Callable[[], Worker],
    configure_worker: Callable[[Worker], object],
    thread_pool_factory: Callable[[], QThreadPool | None],
    retain_worker: Callable[[Worker], None],
    release_worker: Callable[[Worker], object],
) -> Exception | None:
    """Start a worker only after all setup succeeds, rolling ownership back on error."""
    worker: Worker | None = None
    try:
        worker = worker_factory()
        configure_worker(worker)
        thread_pool = thread_pool_factory()
        if thread_pool is None:
            error = RuntimeError("Qt thread pool is unavailable.")
            release_worker(worker)
            logger.error("Could not start saliency background worker: %s", error)
            return error
        retain_worker(worker)
        thread_pool.start(worker)
    except Exception as exc:
        if worker is not None:
            with suppress(Exception):
                release_worker(worker)
        logger.exception("Could not start saliency background worker.")
        return exc
    return None


def _worker_start_failure_message(
    worker_name: str,
    error: Exception,
    recovery: str,
) -> str:
    """Return product copy while the caller keeps technical detail in the log."""
    del error
    return f"{worker_name} failed to start. {recovery}"


@dataclass(frozen=True)
class _RenderRequest:
    """The latest render request retained by one saliency view."""

    generation: int
    context: str
    publication_generation: int | None
    render_fn: Callable[[], Figure | None]


@dataclass(frozen=True)
class _QueuedRenderStart:
    view_ref: weakref.ReferenceType[BaseSaliencyView]
    view_identity: int
    request: _RenderRequest


@dataclass(frozen=True)
class _QueuedGuiOperation:
    view_ref: weakref.ReferenceType[BaseSaliencyView]
    view_identity: int
    key: str
    operation: Callable[[], object]


@dataclass(frozen=True)
class _QueuedOwnedGuiOperation:
    owner: _NativePlotCleanupOwner
    owner_identity: int
    key: str
    operation: Callable[[], object]


@dataclass
class _ActiveRenderLease:
    view_identity: int
    generation: int
    phase: str = "preparing"


@dataclass
class _NativePlotCleanupState:
    finalized: bool = False
    release_count: int = 0
    cleanup_thread: QThread | None = None


class _NativePlotCleanupOwner(QObject):
    """Own detached QTAgg resources until serialized GUI cleanup runs."""

    def __init__(
        self,
        canvas: FigureCanvas | None,
        figure: Figure | None,
        state: _NativePlotCleanupState,
        *,
        on_finalized: Callable[[_NativePlotCleanupOwner], None],
    ) -> None:
        super().__init__(QApplication.instance())
        self._canvas = canvas
        self._figure = figure
        self._state = state
        self._on_finalized = on_finalized
        _ACTIVE_NATIVE_PLOT_CLEANUP_OWNERS.add(self)

    @pyqtSlot()
    def finalize(self) -> None:
        if self._state.finalized:
            return
        if QThread.currentThread() is not self.thread():
            raise RuntimeError(
                "Detached saliency resources must be finalized on the GUI thread."
            )
        canvas = self._canvas
        figure = self._figure
        self._canvas = None
        self._figure = None
        self._state.release_count += 1
        self._state.cleanup_thread = QThread.currentThread()
        if figure is not None:
            _dispose_figure(figure)
        elif canvas is not None:
            if hasattr(canvas, "_draw_pending"):
                cast(Any, canvas)._draw_pending = False
            with suppress(RuntimeError):
                canvas.hide()
                canvas.close()
                canvas.setParent(None)
                canvas.deleteLater()
        self._state.finalized = True
        self._on_finalized(self)
        _ACTIVE_NATIVE_PLOT_CLEANUP_OWNERS.discard(self)
        self.deleteLater()


class _MatplotlibRenderCoordinator:
    """Serialize worker rendering and GUI-native Matplotlib operations.

    The GUI thread never waits for a worker lock. Render requests and GUI
    operations are queued; one worker lease remains active until its queued
    result/error and ``finished`` signals have both reached the GUI thread.
    """

    def __init__(self) -> None:
        self._queue: deque[
            _QueuedRenderStart | _QueuedGuiOperation | _QueuedOwnedGuiOperation
        ] = deque()
        self._active: _ActiveRenderLease | None = None
        self._draining = False
        self._drain_requested = False

    def submit_render(
        self,
        view: BaseSaliencyView,
        request: _RenderRequest,
    ) -> None:
        identity = id(view)
        self._queue = deque(
            item
            for item in self._queue
            if not (
                isinstance(item, _QueuedRenderStart) and item.view_identity == identity
            )
        )
        self._queue.append(
            _QueuedRenderStart(
                view_ref=weakref.ref(view),
                view_identity=identity,
                request=request,
            )
        )
        self._drain()

    def run_gui_operation(
        self,
        view: BaseSaliencyView,
        operation: Callable[[], object],
        *,
        key: str,
    ) -> bool:
        identity = id(view)
        active = self._active
        if active is None or (
            active.view_identity == identity and active.phase == "gui"
        ):
            operation()
            return True
        self._queue = deque(
            item
            for item in self._queue
            if not (
                isinstance(item, _QueuedGuiOperation)
                and item.view_identity == identity
                and item.key == key
            )
        )
        self._queue.append(
            _QueuedGuiOperation(
                view_ref=weakref.ref(view),
                view_identity=identity,
                key=key,
                operation=operation,
            )
        )
        return False

    def run_owned_gui_operation(
        self,
        owner: _NativePlotCleanupOwner,
        operation: Callable[[], object],
        *,
        key: str,
    ) -> bool:
        """Queue cleanup by its independent owner, not a disposable view."""
        identity = id(owner)
        if self._active is None:
            operation()
            return True
        self._queue = deque(
            item
            for item in self._queue
            if not (
                isinstance(item, _QueuedOwnedGuiOperation)
                and item.owner_identity == identity
                and item.key == key
            )
        )
        self._queue.append(
            _QueuedOwnedGuiOperation(
                owner=owner,
                owner_identity=identity,
                key=key,
                operation=operation,
            )
        )
        return False

    def cancel_render_requests(self, view: BaseSaliencyView) -> None:
        identity = id(view)
        self._queue = deque(
            item
            for item in self._queue
            if not (
                isinstance(item, _QueuedRenderStart) and item.view_identity == identity
            )
        )

    def enter_gui_phase(self, view_identity: int, generation: int) -> bool:
        active = self._active
        if (
            active is None
            or active.view_identity != view_identity
            or active.generation != generation
        ):
            return False
        active.phase = "gui"
        return True

    def complete(self, view_identity: int, generation: int) -> None:
        active = self._active
        if (
            active is None
            or active.view_identity != view_identity
            or active.generation != generation
        ):
            return
        self._active = None
        self._drain()

    def has_work_for(self, view: BaseSaliencyView) -> bool:
        identity = id(view)
        active = self._active
        if active is not None and active.view_identity == identity:
            return True
        return any(
            isinstance(item, (_QueuedRenderStart, _QueuedGuiOperation))
            and item.view_identity == identity
            for item in self._queue
        )

    def _drain(self) -> None:
        if self._draining:
            self._drain_requested = True
            return
        if self._active is not None:
            return
        self._draining = True
        try:
            while self._active is None and self._queue:
                item = self._queue.popleft()
                if isinstance(item, _QueuedOwnedGuiOperation):
                    try:
                        item.operation()
                    except Exception:
                        logger.exception(
                            "Queued owned Matplotlib GUI cleanup failed: %s",
                            item.key,
                        )
                    continue
                view = item.view_ref()
                if view is None or sip.isdeleted(view):
                    continue
                if isinstance(item, _QueuedGuiOperation):
                    try:
                        item.operation()
                    except Exception:
                        logger.exception(
                            "Queued Matplotlib GUI cleanup failed: %s",
                            item.key,
                        )
                    continue
                if not view._is_current_render_request(item.request):
                    continue
                lease = _ActiveRenderLease(
                    view_identity=item.view_identity,
                    generation=item.request.generation,
                )
                self._active = lease
                try:
                    view._prepare_for_render_request(item.request)
                    lease.phase = "worker"
                    started = view._start_render_request(item.request)
                except Exception:
                    logger.exception("Could not dispatch saliency render request.")
                    started = False
                if self._active is lease and not started:
                    self._active = None
                if self._active is lease:
                    return
        finally:
            self._draining = False
        if self._drain_requested:
            self._drain_requested = False
            self._drain()


_MATPLOTLIB_RENDER_COORDINATOR = _MatplotlibRenderCoordinator()


@dataclass
class _RenderOutcome:
    """One worker result tagged with the UI request generation that owns it."""

    generation: int
    context: str
    publication_generation: int | None = None
    figure: Figure | None = None
    error: tuple[type[BaseException], BaseException, str] | None = None
    cancelled: bool = False

    def take_figure(self) -> Figure | None:
        """Transfer figure ownership to the GUI consumer."""
        figure = self.figure
        self.figure = None
        return figure

    def close_figure(self) -> None:
        """Release an unconsumed figure on the GUI cleanup owner."""
        figure = self.take_figure()
        _dispose_figure(figure)


def _cancelled_render_outcome(
    request: _RenderRequest,
    figure: Figure | None = None,
) -> _RenderOutcome:
    return _RenderOutcome(
        generation=request.generation,
        context=request.context,
        publication_generation=request.publication_generation,
        figure=figure,
        cancelled=True,
    )


def _execute_render_request(
    request: _RenderRequest,
    cancellation: threading.Event,
) -> _RenderOutcome:
    """Execute one request without constructing a QWidget or QTAgg canvas."""
    if cancellation.is_set():
        return _cancelled_render_outcome(request)
    try:
        figure = request.render_fn()
    except Exception as exc:
        if cancellation.is_set():
            return _cancelled_render_outcome(request)
        return _RenderOutcome(
            generation=request.generation,
            context=request.context,
            publication_generation=request.publication_generation,
            error=(type(exc), exc, traceback.format_exc()),
        )
    if cancellation.is_set():
        return _cancelled_render_outcome(request, figure)
    canvas = getattr(figure, "canvas", None) if figure is not None else None
    if isinstance(canvas, QWidget):
        error = RuntimeError("Saliency worker returned a Qt-backed Matplotlib figure.")
        return _RenderOutcome(
            generation=request.generation,
            context=request.context,
            publication_generation=request.publication_generation,
            figure=figure,
            error=(type(error), error, ""),
        )
    return _RenderOutcome(
        generation=request.generation,
        context=request.context,
        publication_generation=request.publication_generation,
        figure=figure,
    )


@dataclass(frozen=True)
class _OwnedRenderJob:
    request: _RenderRequest
    worker: Worker
    cancellation: threading.Event


class _RenderCleanupOwner(QObject):
    """GUI-thread owner for active worker, signals, and terminal cleanup."""

    def __init__(self, view: BaseSaliencyView) -> None:
        app = QApplication.instance()
        super().__init__(app)
        self._view_ref: Callable[[], BaseSaliencyView | None] = weakref.ref(view)
        self._view_identity = id(view)
        self._jobs: dict[int, _OwnedRenderJob] = {}
        self.workers: dict[int, Worker] = {}
        self._signal_generations: dict[int, int] = {}
        self._view_detached = False
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)
        self._thread_pool.setExpiryTimeout(1_000)

    @property
    def active_worker_count(self) -> int:
        return len(self._jobs)

    @property
    def thread_pool(self) -> QThreadPool:
        return self._thread_pool

    def connect_worker(self, worker: Worker) -> None:
        worker.signals.result.connect(self._on_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)

    def retain(
        self,
        request: _RenderRequest,
        worker: Worker,
        cancellation: threading.Event,
    ) -> None:
        job = _OwnedRenderJob(
            request=request,
            worker=worker,
            cancellation=cancellation,
        )
        self._jobs[request.generation] = job
        self.workers[request.generation] = worker
        self._signal_generations[id(worker.signals)] = request.generation
        _ACTIVE_RENDER_CLEANUP_OWNERS.add(self)

    def release_start_failure(
        self,
        generation: int,
        worker: Worker,
    ) -> bool:
        job = self._jobs.get(generation)
        if job is not None and job.worker is not worker:
            return False
        self._jobs.pop(generation, None)
        self.workers.pop(generation, None)
        self._signal_generations.pop(id(worker.signals), None)
        self._disconnect_worker(worker)
        self._release_owner_if_idle()
        return job is not None

    def detach_view(self) -> None:
        self._view_detached = True
        self._view_ref = lambda: None
        for job in self._jobs.values():
            job.cancellation.set()
        self._release_owner_if_idle()

    def _live_view(self) -> BaseSaliencyView | None:
        view = self._view_ref()
        if view is None or sip.isdeleted(view):
            return None
        return view

    def _generation_for_sender(self) -> int | None:
        sender = self.sender()
        if sender is None:
            return None
        return self._signal_generations.get(id(sender))

    @pyqtSlot(object)
    def _on_result(self, outcome: object) -> None:
        if not isinstance(outcome, _RenderOutcome):
            logger.error("Saliency renderer returned an invalid result.")
            return
        if outcome.generation not in self._jobs:
            outcome.close_figure()
            return
        _MATPLOTLIB_RENDER_COORDINATOR.enter_gui_phase(
            self._view_identity,
            outcome.generation,
        )
        view = self._live_view()
        if view is None:
            outcome.close_figure()
            return
        view._consume_render_outcome(outcome)

    @pyqtSlot(tuple)
    def _on_error(self, error: tuple[Any, Any, str]) -> None:
        generation = self._generation_for_sender()
        if generation is None:
            return
        job = self._jobs.get(generation)
        if job is None:
            return
        _MATPLOTLIB_RENDER_COORDINATOR.enter_gui_phase(
            self._view_identity,
            generation,
        )
        outcome = _RenderOutcome(
            generation=generation,
            context=job.request.context,
            publication_generation=job.request.publication_generation,
            error=error,
        )
        view = self._live_view()
        if view is not None:
            view._consume_render_outcome(outcome)

    @pyqtSlot()
    def _on_finished(self) -> None:
        generation = self._generation_for_sender()
        if generation is None:
            return
        job = self._jobs.pop(generation, None)
        if job is None:
            return
        self.workers.pop(generation, None)
        self._signal_generations.pop(id(job.worker.signals), None)
        self._disconnect_worker(job.worker)
        view = self._live_view()
        if view is not None:
            view._render_worker_finished(generation, job.worker)
        _MATPLOTLIB_RENDER_COORDINATOR.complete(
            self._view_identity,
            generation,
        )
        del job
        self._release_owner_if_idle()

    def _disconnect_worker(self, worker: Worker) -> None:
        for signal, slot in (
            (worker.signals.result, self._on_result),
            (worker.signals.error, self._on_error),
            (worker.signals.finished, self._on_finished),
        ):
            with suppress(TypeError, RuntimeError):
                signal.disconnect(slot)

    def _release_owner_if_idle(self) -> None:
        if self._jobs:
            return
        _ACTIVE_RENDER_CLEANUP_OWNERS.discard(self)
        if self._view_detached:
            self._thread_pool.clear()
            self.deleteLater()


def fit_figure_subplots_to_canvas(
    figure: Figure,
    canvas,
    *,
    padding_px: float = 6.0,
    max_iterations: int = 2,
) -> bool:
    """Move subplot contents inside the canvas after a Qt resize.

    Matplotlib layout is initially calculated for the visualizer's default
    figure size. The embedded Qt canvas can be narrower, which otherwise clips
    axis labels or colorbar ticks even though the plot itself still renders.
    """
    changed = False
    for _ in range(max_iterations):
        canvas.draw()
        renderer = canvas.get_renderer()
        width, height = canvas.get_width_height()
        bounds = [
            bbox
            for axis in list(figure.axes)
            if (bbox := axis.get_tightbbox(renderer)) is not None
        ]
        if not bounds or width <= 0 or height <= 0:
            break
        left_overflow = max(0.0, padding_px - min(box.x0 for box in bounds))
        right_overflow = max(
            0.0,
            max(box.x1 for box in bounds) - (float(width) - padding_px),
        )
        bottom_overflow = max(0.0, padding_px - min(box.y0 for box in bounds))
        top_overflow = max(
            0.0,
            max(box.y1 for box in bounds) - (float(height) - padding_px),
        )
        if not any((left_overflow, right_overflow, bottom_overflow, top_overflow)):
            break

        params = figure.subplotpars
        left = params.left + left_overflow / float(width)
        right = params.right - right_overflow / float(width)
        bottom = params.bottom + bottom_overflow / float(height)
        top = params.top - top_overflow / float(height)
        if right - left < 0.3 or top - bottom < 0.3:
            break
        figure.subplots_adjust(
            left=left,
            right=right,
            bottom=bottom,
            top=top,
        )
        changed = True
    if changed:
        canvas.draw()
    return changed


class BaseSaliencyView(QWidget):
    """Abstract base class for all Saliency views (Map, Spectrogram, Topo, 3D).
    Standardizes layout, error handling, and placeholder display.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = (
            parent.main_window if parent and hasattr(parent, "main_window") else None
        )
        self._plot_generation = 0
        self._render_publication_generation: int | None = None
        self._render_cleanup_owner = _RenderCleanupOwner(self)
        self._render_workers = self._render_cleanup_owner.workers
        self._active_render_cancellation: threading.Event | None = None
        self._render_shutdown_requested = False
        self._closed = False
        self._native_resources_finalized = False
        self._native_plot_cleanup_owner: _NativePlotCleanupOwner | None = None
        self._native_plot_cleanup_state: _NativePlotCleanupState | None = None
        self._saliency_coverage: SaliencyMethodCoverageSnapshot | None = None
        self._render_commit_guard: Callable[[int, int], bool] | None = None
        self._pan_state: (
            tuple[Axes, float, float, tuple[float, float], tuple[float, float]] | None
        ) = None
        self._initial_axis_limits: dict[
            int,
            tuple[tuple[float, float], tuple[float, float]],
        ] = {}
        self._canvas_scroll_area: QScrollArea | None = None

        self.init_ui()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # 1. Matplotlib Canvas (Default, subclasses can override)
        self.fig: Figure | None = Figure(figsize=(5, 4), dpi=100)
        self.canvas: FigureCanvas | None = FigureCanvas(self.fig)

        # Apply Theme
        Theme.apply_matplotlib_dark_theme(self.fig)

        if getattr(self, "_scrollable_canvas", False):
            scroll_area = QScrollArea(self)
            scroll_area.setWidgetResizable(True)
            scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll_area.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )
            scroll_area.setWidget(self.canvas)
            self._canvas_scroll_area = scroll_area
            self.main_layout.addWidget(scroll_area)
        else:
            self.main_layout.addWidget(self.canvas)

        # 2. Error Message (Hidden by default)
        self.error_label = QLabel()
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.setContentsMargins(16, 8, 16, 8)
        self.error_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.error_label.setStyleSheet(
            f"color: {Theme.ACCENT_ERROR}; font-size: 14px; font-weight: bold;",
        )
        self.error_label.hide()
        self.main_layout.addWidget(self.error_label)

    def show_error(self, message):
        """Display an error message overlaid on the view."""
        self._cancel_pending_render()
        self._display_error(message)

    def _display_error(self, message):
        if self.canvas is not None:
            self.canvas.hide()
        self.error_label.setStyleSheet(
            f"color: {Theme.ACCENT_ERROR}; font-size: 14px; font-weight: bold;",
        )
        self.error_label.setText(f"Error: {message}")
        self.error_label.show()

    def show_message(self, message):
        """Display a neutral placeholder message over the view."""
        self._cancel_pending_render()
        self._display_message(message)

    def _display_message(self, message):
        if self.canvas is not None:
            self.canvas.hide()
        self.error_label.setStyleSheet(
            f"color: {Theme.TEXT_SECONDARY}; font-size: 14px; font-weight: bold;",
        )
        self.error_label.setText(message)
        self.error_label.show()

    def clear_plot(self):
        """Clear the plot and reset error state."""
        self._cancel_pending_render()
        _MATPLOTLIB_RENDER_COORDINATOR.run_gui_operation(
            self,
            self._clear_plot_now,
            key="clear-plot",
        )

    def _clear_plot_now(self) -> None:
        """Clear native Matplotlib state while holding the GUI render phase."""
        self.error_label.hide()
        self.error_label.setStyleSheet(
            f"color: {Theme.ACCENT_ERROR}; font-size: 14px; font-weight: bold;",
        )
        if self.canvas is not None:
            self.canvas.show()
        if self.fig is None or self.canvas is None:
            return
        self.fig.clear()
        self._draw_canvas_now()

    def _draw_canvas_now(self) -> None:
        if self.canvas is None:
            return
        # Qt can destroy the backing widget while saliency tabs are being
        # replaced. Treat late canvas draws as stale rather than crashing.
        with suppress(RuntimeError):
            self.canvas.draw()

    def update_view(self, result, params):
        """Update the view with calculation results.
        Must be implemented by subclasses.
        """
        raise NotImplementedError

    def set_saliency_coverage(
        self,
        coverage: SaliencyMethodCoverageSnapshot | None,
    ) -> None:
        """Receive coverage from the parent Application publication."""
        if coverage is not None and not isinstance(
            coverage,
            SaliencyMethodCoverageSnapshot,
        ):
            raise TypeError("saliency coverage publication is invalid")
        self._saliency_coverage = coverage

    def require_complete_saliency_coverage(
        self,
        method: str,
    ) -> None:
        """Fail closed unless Application published complete method coverage."""
        coverage = self._saliency_coverage
        if coverage is None or coverage.method != method:
            raise SaliencyViewUnavailableError(
                f"{method} saliency coverage has not been published for this run. "
                "Compute saliency to continue."
            )
        if not coverage.available:
            raise SaliencyViewUnavailableError(
                f"{method} saliency has not been computed for this run. "
                "Compute saliency to continue."
            )
        if coverage.complete:
            return
        missing = ", ".join(
            item.display_name for item in coverage.classes if not item.available
        )
        raise SaliencyViewUnavailableError(
            f"{method} saliency is missing for: {missing or 'one or more classes'}. "
            "Recompute saliency before opening a multi-class view."
        )

    def _close_current_figure(self) -> None:
        figure = self.fig
        self.fig = None
        _dispose_figure(figure)

    def _release_canvas(self) -> None:
        if self.canvas is None:
            return
        canvas = self.canvas
        figure = self.fig
        self.canvas = None
        if hasattr(canvas, "_draw_pending"):
            canvas._draw_pending = False
        with suppress(RuntimeError):
            if self._canvas_scroll_area is not None:
                self._canvas_scroll_area.takeWidget()
            else:
                self.main_layout.removeWidget(canvas)
        with suppress(RuntimeError):
            canvas.hide()
            canvas.close()
            canvas.setParent(None)
        _disconnect_figure_canvas(figure, canvas)
        with suppress(RuntimeError):
            canvas.deleteLater()

    def _replace_figure(self, figure: Figure) -> bool:
        """Install one worker Figure transactionally on the GUI thread."""
        if self._closed:
            _dispose_figure(figure)
            return False

        candidate_canvas: FigureCanvas | None = None
        try:
            Theme.apply_matplotlib_dark_theme(figure)
            candidate_canvas = FigureCanvas(figure)
        except Exception as exc:
            logger.error("Could not create the saliency Qt canvas: %s", exc)
            if candidate_canvas is not None:
                self._dispose_candidate_canvas(candidate_canvas, figure)
            else:
                _dispose_figure(figure)
            self._display_error(SALIENCY_RENDER_FAILED_TEXT)
            return False

        old_figure = self.fig
        old_canvas = self.canvas
        installed_canvas = cast(FigureCanvas, candidate_canvas)
        self.fig = figure
        self.canvas = installed_canvas
        try:
            min_height = int(getattr(figure, "_xbrainlab_min_canvas_height", 0))
            if min_height > 0:
                installed_canvas.setMinimumHeight(min_height)
            if self._canvas_scroll_area is not None:
                old_canvas = self._canvas_scroll_area.takeWidget()
                self._canvas_scroll_area.setWidget(installed_canvas)
            else:
                self.main_layout.insertWidget(0, installed_canvas)
            installed_canvas.show()
            self.main_layout.activate()
            self._fit_current_figure()
        except Exception as exc:
            logger.error("Could not install the saliency Qt canvas: %s", exc)
            self.fig = old_figure
            self.canvas = old_canvas
            self._dispose_candidate_canvas(installed_canvas, figure)
            if self._canvas_scroll_area is not None and old_canvas is not None:
                self._canvas_scroll_area.setWidget(old_canvas)
            self._display_error(SALIENCY_RENDER_FAILED_TEXT)
            return False

        self._release_previous_plot(old_canvas, old_figure)
        self._install_canvas_interactions(installed_canvas)
        self.error_label.hide()
        return True

    def reset_view(self) -> None:
        """Restore the rendered axes to their data extents."""
        if self.fig is None:
            return
        for axis in self.fig.axes:
            limits = self._initial_axis_limits.get(id(axis))
            if axis.images and limits is not None:
                axis.set_xlim(limits[0])
                axis.set_ylim(limits[1])
        self._draw_canvas_now()

    def _install_canvas_interactions(self, canvas: FigureCanvas) -> None:
        """Enable pointer-local zoom and drag pan for detailed saliency plots."""
        figure = canvas.figure
        self._initial_axis_limits = {
            id(axis): (axis.get_xlim(), axis.get_ylim())
            for axis in figure.axes
            if axis.images
        }
        canvas.mpl_connect("scroll_event", self._on_canvas_scroll)
        canvas.mpl_connect("button_press_event", self._on_canvas_press)
        canvas.mpl_connect("motion_notify_event", self._on_canvas_motion)
        canvas.mpl_connect("button_release_event", self._on_canvas_release)

    def _on_canvas_scroll(self, event: Event) -> None:
        mouse_event = cast(MouseEvent, event)
        axis = getattr(mouse_event, "inaxes", None)
        if axis is None or not getattr(axis, "images", None):
            return
        xdata = getattr(mouse_event, "xdata", None)
        ydata = getattr(mouse_event, "ydata", None)
        if xdata is None or ydata is None:
            return
        factor = 0.8 if getattr(mouse_event, "step", 0) > 0 else 1.25
        x0, x1 = axis.get_xlim()
        y0, y1 = axis.get_ylim()
        axis.set_xlim(xdata - (xdata - x0) * factor, xdata + (x1 - xdata) * factor)
        axis.set_ylim(ydata - (ydata - y0) * factor, ydata + (y1 - ydata) * factor)
        self._draw_canvas_now()

    def _on_canvas_press(self, event: Event) -> None:
        mouse_event = cast(MouseEvent, event)
        axis = getattr(mouse_event, "inaxes", None)
        if (
            getattr(mouse_event, "button", None) != 1
            or axis is None
            or not getattr(axis, "images", None)
            or getattr(mouse_event, "xdata", None) is None
            or getattr(mouse_event, "ydata", None) is None
        ):
            return
        x_limits = axis.get_xlim()
        y_limits = axis.get_ylim()
        self._pan_state = (
            axis,
            float(mouse_event.xdata),
            float(mouse_event.ydata),
            (float(x_limits[0]), float(x_limits[1])),
            (float(y_limits[0]), float(y_limits[1])),
        )

    def _on_canvas_motion(self, event: Event) -> None:
        mouse_event = cast(MouseEvent, event)
        state = self._pan_state
        if state is None or getattr(mouse_event, "inaxes", None) is not state[0]:
            return
        if (
            getattr(mouse_event, "xdata", None) is None
            or getattr(mouse_event, "ydata", None) is None
        ):
            return
        axis, start_x, start_y, xlim, ylim = state
        dx = start_x - float(mouse_event.xdata)
        dy = start_y - float(mouse_event.ydata)
        axis.set_xlim(xlim[0] + dx, xlim[1] + dx)
        axis.set_ylim(ylim[0] + dy, ylim[1] + dy)
        self._draw_canvas_now()

    def _on_canvas_release(self, _event: Event) -> None:
        self._pan_state = None

    def _dispose_candidate_canvas(
        self,
        canvas: FigureCanvas,
        figure: Figure,
    ) -> None:
        with suppress(RuntimeError):
            if self._canvas_scroll_area is not None:
                self._canvas_scroll_area.takeWidget()
            else:
                self.main_layout.removeWidget(canvas)
            canvas.hide()
            canvas.close()
            canvas.setParent(None)
        _disconnect_figure_canvas(figure, canvas)
        with suppress(RuntimeError):
            canvas.deleteLater()
        _dispose_figure(figure)

    def _release_previous_plot(
        self,
        canvas: FigureCanvas | None,
        figure: Figure | None,
    ) -> None:
        if canvas is not None:
            if hasattr(canvas, "_draw_pending"):
                canvas._draw_pending = False
            if self._canvas_scroll_area is None:
                self.main_layout.removeWidget(canvas)
            with suppress(RuntimeError):
                canvas.hide()
                canvas.close()
                canvas.setParent(None)
            _disconnect_figure_canvas(figure, canvas)
            with suppress(RuntimeError):
                canvas.deleteLater()
        _dispose_figure(figure)

    def _fit_current_figure(self) -> None:
        if self.fig is None or self.canvas is None:
            return
        with suppress(RuntimeError, ValueError):
            fit_figure_subplots_to_canvas(self.fig, self.canvas)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self.main_layout.activate()
        _MATPLOTLIB_RENDER_COORDINATOR.run_gui_operation(
            self,
            self._fit_current_figure,
            key="fit-current-figure",
        )

    def _render_figure_async(
        self,
        render_fn: Callable[[], Figure | None],
        *,
        error_context: str,
        publication_generation: int | None = None,
    ) -> None:
        """Render away from the GUI thread and publish only the latest result."""
        if self._closed or self._render_shutdown_requested:
            return
        if _render_callable_captures_qwidget(render_fn):
            logger.error(
                "Rejected saliency render callable because it captures a QWidget."
            )
            self._cancel_pending_render()
            self._display_error(SALIENCY_RENDER_FAILED_TEXT)
            return
        self._plot_generation += 1
        generation = self._plot_generation
        self._render_publication_generation = publication_generation
        if publication_generation is None or self.canvas is None:
            self._display_message("Rendering saliency...")

        request = _RenderRequest(
            generation=generation,
            context=error_context,
            publication_generation=publication_generation,
            render_fn=render_fn,
        )
        if self._render_workers:
            self._cancel_active_render()
        _MATPLOTLIB_RENDER_COORDINATOR.submit_render(self, request)

    def _prepare_for_render_request(self, request: _RenderRequest) -> None:
        """Keep the committed canvas visible while a replacement is prepared."""
        if not self._is_current_render_request(request):
            return
        if request.publication_generation is None:
            self._release_canvas()
            self._close_current_figure()
        if self.canvas is None:
            self._display_message("Rendering saliency...")

    def _start_render_request(self, request: _RenderRequest) -> bool:
        cancellation = threading.Event()

        start_error = _start_worker_atomically(
            worker_factory=lambda: Worker(
                _execute_render_request,
                request,
                cancellation,
            ),
            configure_worker=self._render_cleanup_owner.connect_worker,
            thread_pool_factory=lambda: self._render_cleanup_owner.thread_pool,
            retain_worker=lambda worker: self._retain_render_worker(
                request,
                worker,
                cancellation,
            ),
            release_worker=lambda worker: (
                self._render_cleanup_owner.release_start_failure(
                    request.generation,
                    worker,
                )
            ),
        )
        if start_error is not None:
            self._active_render_cancellation = None
            if self._is_current_render_request(request):
                self._display_error(
                    _worker_start_failure_message(
                        "Saliency renderer",
                        start_error,
                        "Try again or switch to another saliency view.",
                    ),
                )
                self._emit_render_terminal(request.generation, "failed")
            return False
        return True

    def _is_current_render_request(self, request: _RenderRequest) -> bool:
        return (
            not self._closed
            and not self._render_shutdown_requested
            and request.generation == self._plot_generation
            and request.publication_generation == self._render_publication_generation
        )

    def _cancel_active_render(self) -> None:
        if self._active_render_cancellation is not None:
            self._active_render_cancellation.set()

    def _retain_render_worker(
        self,
        request: _RenderRequest,
        worker: Worker,
        cancellation: threading.Event,
    ) -> None:
        self._render_cleanup_owner.retain(
            request,
            worker,
            cancellation,
        )
        self._active_render_cancellation = cancellation

    def _render_worker_finished(
        self,
        generation: int,
        worker: Worker,
    ) -> None:
        del generation, worker
        self._active_render_cancellation = None

    @pyqtSlot(object)
    def _consume_render_outcome(self, outcome: object) -> None:
        """Install one worker result on the owning QWidget's GUI thread."""
        if not isinstance(outcome, _RenderOutcome):
            logger.error("Saliency renderer returned an invalid result.")
            return
        if (
            self._closed
            or outcome.cancelled
            or outcome.generation != self._plot_generation
            or outcome.publication_generation != self._render_publication_generation
        ):
            outcome.close_figure()
            return
        if outcome.error is not None:
            outcome.close_figure()
            self._handle_plot_error(
                outcome.generation,
                outcome.context,
                outcome.error,
            )
        else:
            self._handle_plot_result(
                outcome.generation,
                outcome.take_figure(),
            )

    def _handle_plot_result(self, generation: int, figure: Figure | None) -> None:
        if generation != self._plot_generation:
            _dispose_figure(figure)
            return
        if figure is None:
            self._display_error("No Data Available")
            self._emit_render_terminal(generation, "failed")
            return
        publication_generation = self._render_publication_generation
        guard = self._render_commit_guard
        if publication_generation is None and guard is not None:
            _dispose_figure(figure)
            return
        if guard is not None and publication_generation is not None:
            try:
                admitted = bool(guard(generation, publication_generation))
            except Exception:
                logger.exception("Saliency native commit admission failed")
                admitted = False
            if not admitted:
                _dispose_figure(figure)
                self._emit_render_terminal(generation, "cancelled")
                return
        phase = "completed" if self._replace_figure(figure) else "failed"
        self._emit_render_terminal(generation, phase)

    def _handle_plot_error(self, generation: int, context: str, error: tuple) -> None:
        if generation != self._plot_generation:
            return
        _, value, formatted_traceback = error
        logger.error("Error rendering %s: %s\n%s", context, value, formatted_traceback)
        self._display_error(SALIENCY_RENDER_FAILED_TEXT)
        self._emit_render_terminal(generation, "failed")

    def _emit_render_terminal(self, generation: int, phase: str) -> None:
        publication_generation = self._render_publication_generation
        if publication_generation is None:
            return
        self.render_terminal.emit(generation, publication_generation, phase)

    @property
    def active_render_generation(self) -> int:
        """Return the current native generation for exact parent binding."""
        return self._plot_generation

    @property
    def active_render_publication_generation(self) -> int | None:
        """Return the publication generation owned by the native request."""
        return self._render_publication_generation

    def set_render_commit_guard(
        self,
        guard: Callable[[int, int], bool] | None,
    ) -> None:
        """Install the parent-owned atomic commit admission callback."""
        if guard is not None and not callable(guard):
            raise TypeError("render commit guard must be callable")
        self._render_commit_guard = guard

    def _cancel_pending_render(self) -> None:
        self._plot_generation += 1
        self._render_publication_generation = None
        _MATPLOTLIB_RENDER_COORDINATOR.cancel_render_requests(self)
        self._cancel_active_render()

    def invalidate_render_publication(self) -> None:
        """Reject every callback owned by an older application publication."""
        self._cancel_pending_render()

    def begin_render_shutdown(self) -> None:
        """Cancel render publication and reject new work without blocking Qt."""
        if self._render_shutdown_requested:
            return
        self._render_shutdown_requested = True
        self._cancel_pending_render()

    def cancel_render_shutdown(self) -> None:
        """Allow new render requests after an application close is cancelled."""
        if not self._closed:
            self._render_shutdown_requested = False

    def native_render_work_idle(self) -> bool:
        """Return whether this view owns no queued or running native work."""
        cleanup_state = self._native_plot_cleanup_state
        return (
            self._render_cleanup_owner.active_worker_count == 0
            and not _MATPLOTLIB_RENDER_COORDINATOR.has_work_for(self)
            and (cleanup_state is None or cleanup_state.finalized)
        )

    def native_render_resources_finalized(self) -> bool:
        """Return whether detached QTAgg resources reached terminal cleanup."""
        state = self._native_plot_cleanup_state
        return bool(
            self._native_resources_finalized and state is not None and state.finalized
        )

    def _detach_native_plot_resources(self) -> _NativePlotCleanupOwner:
        owner = self._native_plot_cleanup_owner
        if owner is not None:
            return owner

        canvas = self.canvas
        figure = self.fig
        self.canvas = None
        self.fig = None
        if canvas is not None:
            if hasattr(canvas, "_draw_pending"):
                canvas._draw_pending = False
            with suppress(RuntimeError):
                self.main_layout.removeWidget(canvas)
                canvas.hide()
                canvas.setParent(None)

        state = _NativePlotCleanupState()
        view_ref = weakref.ref(self)

        def mark_view_finalized(finalized_owner: _NativePlotCleanupOwner) -> None:
            view = view_ref()
            if view is not None:
                view._native_resources_finalized = True
                if view._native_plot_cleanup_owner is finalized_owner:
                    view._native_plot_cleanup_owner = None

        owner = _NativePlotCleanupOwner(
            canvas,
            figure,
            state,
            on_finalized=mark_view_finalized,
        )
        self._native_plot_cleanup_owner = owner
        self._native_plot_cleanup_state = state
        return owner

    def finalize_native_render_resources(self) -> bool:
        """Release QTAgg resources once on the owning GUI thread."""
        state = self._native_plot_cleanup_state
        if self._native_resources_finalized or (state is not None and state.finalized):
            self._native_resources_finalized = True
            self._native_plot_cleanup_owner = None
            return True
        if QThread.currentThread() is not self.thread():
            logger.error(
                "Saliency native resources must be finalized on the GUI thread."
            )
            return False
        if not self._closed:
            self._closed = True
            self._render_shutdown_requested = True
            self._cancel_pending_render()
            self._render_cleanup_owner.detach_view()
            self._active_render_cancellation = None
        owner = self._detach_native_plot_resources()
        _MATPLOTLIB_RENDER_COORDINATOR.run_owned_gui_operation(
            owner,
            owner.finalize,
            key="teardown",
        )
        state = self._native_plot_cleanup_state
        finalized = bool(state is not None and state.finalized)
        self._native_resources_finalized = finalized
        if finalized:
            self._native_plot_cleanup_owner = None
        return finalized

    def event(self, event):
        """Release render ownership before Qt destroys this widget."""
        if event.type() is QEvent.Type.DeferredDelete:
            self.finalize_native_render_resources()
        return super().event(event)

    def closeEvent(self, event):  # noqa: N802
        """Release matplotlib figure and canvas widgets to prevent leaks."""
        self.finalize_native_render_resources()
        super().closeEvent(event)

    render_terminal = pyqtSignal(int, int, str)
