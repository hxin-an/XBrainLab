from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import weakref
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar, cast

import pyvistaqt
from PyQt6 import sip
from PyQt6.QtCore import (
    QEvent,
    QObject,
    QSignalBlocker,
    Qt,
    QThread,
    QThreadPool,
    QTimer,
)
from PyQt6.QtGui import QResizeEvent, QStandardItemModel
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application.saliency_render import (
    SaliencyRenderData,
    SaliencyRenderPublication,
)
from XBrainLab.backend.application.state import (
    SaliencyClassCoverageSnapshot,
    SaliencyMethodCoverageSnapshot,
)
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyStatus,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.core.worker import Worker
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme

from .base_saliency_view import (
    SALIENCY_PREPARATION_FAILED_TEXT,
    SALIENCY_RENDER_FAILED_TEXT,
    _start_worker_atomically,
    _worker_start_failure_message,
    safe_saliency_detail,
)
from .plot_3d_head import Saliency3D

_INTERACTIVE_3D_PROBE_TIMEOUT_SECONDS = 10
_RUNTIME_PROBE_FAILED_TEXT = (
    "3D rendering support could not be checked. Try again or use a 2D saliency view."
)
_INTERACTIVE_3D_PROBE_CODE = r"""
import os
import sys


def _disable_probe_core_dumps():
    try:
        import resource
    except ImportError:
        return False
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        core_limit = resource.getrlimit(resource.RLIMIT_CORE)
    except (AttributeError, OSError, ValueError):
        return False
    return core_limit == (0, 0)


_CORE_DUMPS_DISABLED = _disable_probe_core_dumps()
if os.name == "posix" and not _CORE_DUMPS_DISABLED:
    print("Interactive 3D probe blocked because RLIMIT_CORE=0 failed.", file=sys.stderr)
    sys.exit(3)

from PyQt6.QtWidgets import QApplication
import pyvista as pv
import pyvistaqt

app = QApplication([])
plotter = pyvistaqt.QtInteractor()
plotter.add_mesh(pv.Sphere(radius=0.25), color="white")
plotter.show()
# This isolated probe covers synchronous VTK render-window initialization only.
plotter.interactor.Initialize()
plotter.render()
print(f"plotter_created={plotter is not None}")
plotter.close()
app.quit()
sys.exit(0)
"""

_INTERACTIVE_3D_PROBE_CACHE: dict[tuple[str, str, str, str], tuple[bool, str]] = {}
_ACTIVE_3D_WORKER_POOL_OWNERS: set[_Saliency3DWorkerPoolOwner] = set()
_QObjectT = TypeVar("_QObjectT", bound=QObject)


def _live_qobject(
    receiver_ref: weakref.ReferenceType[_QObjectT],
) -> _QObjectT | None:
    """Resolve a weak Qt receiver only while its C++ wrapper is alive."""
    receiver = receiver_ref()
    if receiver is None:
        return None
    try:
        if sip.isdeleted(receiver):
            return None
    except (AttributeError, TypeError, RuntimeError):
        return None
    return receiver


@dataclass
class _NativeInteractorCleanupState:
    finalized: bool = False
    finalize_count: int = 0
    close_attempts: int = 0
    close_successes: int = 0
    cleanup_thread: QThread | None = None
    failure: str = ""


@dataclass(frozen=True)
class _PreparedEngineCacheEntry:
    publication_ref: weakref.ReferenceType[SaliencyRenderPublication]
    engine: object
    channel_count: int


class _Saliency3DWorkerPoolOwner(QObject):
    """Retain one view's engine/probe workers independently of its QWidget."""

    def __init__(self) -> None:
        super().__init__(QApplication.instance())
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)
        self._thread_pool.setExpiryTimeout(1_000)
        self._workers: set[Worker] = set()
        self._finished_callbacks: dict[int, Callable[[], None]] = {}
        self._shutdown_requested = False
        self._released = False

    @property
    def thread_pool(self) -> QThreadPool:
        return self._thread_pool

    @property
    def active_worker_count(self) -> int:
        return len(self._workers)

    def retain(self, worker: Worker) -> None:
        if self._shutdown_requested or self._released:
            raise RuntimeError("The 3D worker pool is shutting down.")
        if worker in self._workers:
            return

        def callback(owned_worker: Worker = worker) -> None:
            self.release(owned_worker)

        worker.signals.finished.connect(callback)
        self._workers.add(worker)
        self._finished_callbacks[id(worker)] = callback
        _ACTIVE_3D_WORKER_POOL_OWNERS.add(self)

    def release(self, worker: Worker) -> bool:
        callback = self._finished_callbacks.pop(id(worker), None)
        if callback is not None:
            with contextlib.suppress(TypeError, RuntimeError, ValueError):
                worker.signals.finished.disconnect(callback)
        retained = worker in self._workers
        self._workers.discard(worker)
        self._release_if_idle()
        return retained

    def request_shutdown(self) -> None:
        self._shutdown_requested = True
        self._release_if_idle()

    def _release_if_idle(self) -> None:
        if not self._shutdown_requested or self._workers or self._released:
            return
        self._released = True
        self._thread_pool.clear()
        _ACTIVE_3D_WORKER_POOL_OWNERS.discard(self)
        self.deleteLater()


class Saliency3DPlotWidget(QWidget):
    """Widget for visualizing 3D Brain Saliency Maps using PyVista.
    Embeds a QtInteractor for interactive 3D rendering.
    """

    _MAX_PREPARED_ENGINE_CACHE_ENTRIES = 8

    def __init__(self, parent):
        super().__init__(parent)
        self._closed = False
        self._shutdown_requested = False
        self._deferred_delete_blocked = False
        self._handling_deferred_delete = False
        self._native_resources_finalized = False
        self._native_interactor_cleanup_state = _NativeInteractorCleanupState()
        self._worker_pool_owner = _Saliency3DWorkerPoolOwner()
        self._runtime_probe_worker: Worker | None = None
        self._pending_3d_request: (
            tuple[int, tuple[SaliencyRenderPublication, bool]] | None
        ) = None
        self._engine_worker: Worker | None = None
        self._pending_worker_start: Callable[[], None] | None = None
        self._consumed_worker_callbacks: set[int] = set()
        self._engine_request_id = 0
        self._current_publication_generation: int | None = None
        self._current_plot_request: tuple[SaliencyRenderPublication, bool] | None = None
        self._prepared_engine_cache: OrderedDict[
            tuple[object, ...],
            _PreparedEngineCacheEntry,
        ] = OrderedDict()
        self._class_coverage: dict[str, SaliencyClassCoverageSnapshot] = {}
        self._requested_class_key: object | None = None
        self._saliency_coverage: SaliencyMethodCoverageSnapshot | None = None
        self._post_training_saliency_status = PostTrainingSaliencyStatus.idle()
        self._selector_syncing = False
        self._saliency_scene: Saliency3D | None = None
        self._active_scene_key: tuple[object, ...] | None = None
        self.init_ui()

    def set_post_training_saliency_status(
        self,
        status: PostTrainingSaliencyStatus,
    ) -> None:
        """Receive the lifecycle published by the parent Application state."""
        self._post_training_saliency_status = (
            status
            if isinstance(status, PostTrainingSaliencyStatus)
            else PostTrainingSaliencyStatus.idle()
        )

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

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.class_controls = QWidget(self)
        self.class_controls.setStyleSheet("background: transparent;")
        class_layout = QHBoxLayout(self.class_controls)
        class_layout.setContentsMargins(8, 6, 8, 0)
        class_layout.setSpacing(8)
        class_label = QLabel("True class:", self.class_controls)
        class_label.setStyleSheet(
            f"color: {Theme.TEXT_SECONDARY}; background: transparent;"
        )
        self.class_combo = QComboBox(self.class_controls)
        self.class_combo.setMinimumWidth(140)
        self.class_combo.setMaximumWidth(240)
        self.class_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.class_combo.currentIndexChanged.connect(self._on_class_changed)
        class_layout.addWidget(class_label)
        class_layout.addWidget(self.class_combo)
        self.class_semantics = QLabel(self.class_controls)
        self.class_semantics.setWordWrap(True)
        self.class_semantics.setStyleSheet(
            f"color: {Theme.TEXT_MUTED}; background: transparent;"
        )
        self.class_semantics.setToolTip(
            "Colour shows mean attribution for the selected true class at the "
            "chosen epoch-relative time. It is not source localisation."
        )
        class_layout.addWidget(self.class_semantics, stretch=1)
        class_layout.addStretch(1)
        self.class_controls.hide()

        self.scene_controls = QWidget(self)
        self.scene_controls.setObjectName("Saliency3DEpochTimeControls")
        scene_layout = QHBoxLayout(self.scene_controls)
        scene_layout.setContentsMargins(8, 0, 8, 0)
        scene_layout.addWidget(QLabel("Epoch time (s):", self.scene_controls))
        self.time_slider = QSlider(Qt.Orientation.Horizontal, self.scene_controls)
        self.time_slider.setObjectName("Saliency3DEpochTimeSlider")
        self.time_slider.setRange(0, 1000)
        self.time_slider.valueChanged.connect(self._set_epoch_time)
        scene_layout.addWidget(self.time_slider, stretch=1)
        self.scene_controls.hide()

        # Plot Area
        self.plot_container = QWidget()
        self.plot_layout = QVBoxLayout(self.plot_container)
        self.plot_layout.setContentsMargins(0, 0, 0, 0)

        self.scene_overlay = QWidget(self.plot_container)
        self.scene_overlay.setObjectName("Saliency3DSceneOverlay")
        self.scene_overlay.setStyleSheet("background: transparent;")
        overlay_layout = QHBoxLayout(self.scene_overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setSpacing(6)
        self.electrodes_button = QPushButton("Electrodes", self.scene_overlay)
        self.electrodes_button.setObjectName("Saliency3DElectrodesToggle")
        self.electrodes_button.setCheckable(True)
        self.electrodes_button.setChecked(True)
        self.electrodes_button.toggled.connect(self._toggle_electrodes)
        overlay_layout.addWidget(self.electrodes_button)
        self.head_button = QPushButton("Head surface", self.scene_overlay)
        self.head_button.setObjectName("Saliency3DHeadSurfaceToggle")
        self.head_button.setCheckable(True)
        self.head_button.setChecked(True)
        self.head_button.toggled.connect(self._toggle_head)
        overlay_layout.addWidget(self.head_button)
        self.reset_camera_button = QPushButton("Reset view", self.scene_overlay)
        self.reset_camera_button.setObjectName("Saliency3DResetView")
        self.reset_camera_button.clicked.connect(self._reset_camera)
        overlay_layout.addWidget(self.reset_camera_button)
        self.scene_overlay.hide()

        # Initial Placeholder
        lbl = QLabel("Select a fold and method to visualize")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 14px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_layout.addWidget(lbl)

        layout.addWidget(self.plot_container, stretch=1)
        layout.addWidget(self.scene_controls)

        self.plotter_widget: Any = None

    def show_error(self, msg):
        self._invalidate_async_requests()
        self._display_error(msg)

    def _display_error(self, msg) -> None:
        if not self._clear_plot_widgets():
            return
        lbl = self._message_label(f"Error: {msg}")
        lbl.setStyleSheet(
            f"color: {Theme.ACCENT_ERROR}; font-size: 14px; font-weight: bold;",
        )
        self.plot_layout.addWidget(lbl, stretch=1)

    def show_message(self, msg):
        self._invalidate_async_requests()
        self._display_message(msg)

    def _display_message(self, msg) -> None:
        if not self._clear_plot_widgets():
            return
        lbl = self._message_label(msg)
        lbl.setStyleSheet(
            f"color: {Theme.WARNING}; font-size: 16px; font-weight: bold;",
        )
        self.plot_layout.addWidget(lbl, stretch=1)

    @staticmethod
    def _message_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setContentsMargins(16, 16, 16, 16)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        lbl.setMinimumWidth(0)
        lbl.setMinimumHeight(80)
        return lbl

    def clear_plot(self):
        self._invalidate_async_requests()
        self._clear_prepared_engine_cache()
        self._clear_plot_widgets()

    @staticmethod
    def _native_plotter_close_verified(plotter: object) -> bool:
        if isinstance(plotter, QObject) and sip.isdeleted(plotter):
            return True
        native_markers = ("_RenderWindow", "iren", "interactor")
        if isinstance(plotter, QWidget) and not any(
            hasattr(plotter, marker) for marker in native_markers
        ):
            return True
        if getattr(plotter, "_closed", None) is not True:
            return False
        if (
            not hasattr(plotter, "_RenderWindow")
            or getattr(plotter, "_RenderWindow", object()) is not None
        ):
            return False
        return bool(
            hasattr(plotter, "iren") and getattr(plotter, "iren", object()) is None
        )

    def _close_owned_plotter(self, plotter: object) -> bool:
        state = self._native_interactor_cleanup_state
        close_plotter = getattr(plotter, "close", None)
        if not callable(close_plotter):
            state.failure = "The 3D interactor has no callable close operation."
            logger.error(state.failure)
            return False
        state.close_attempts += 1
        try:
            close_plotter()
        except Exception as exc:
            state.failure = f"3D interactor close failed: {exc}"
            logger.exception(state.failure)
            return False
        if not self._native_plotter_close_verified(plotter):
            state.failure = (
                "3D interactor close returned without verified native teardown."
            )
            logger.error(state.failure)
            return False
        state.close_successes += 1
        state.failure = ""
        return True

    def _clear_plot_widgets(self) -> bool:
        self._saliency_scene = None
        self._active_scene_key = None
        self.scene_controls.hide()
        self.scene_overlay.hide()
        plotter = self.plotter_widget
        delete_later: Callable[[], object] | None = None
        if plotter is not None:
            if self._native_plotter_close_verified(plotter):
                state = self._native_interactor_cleanup_state
                if state.close_successes == 0:
                    state.close_successes = 1
                state.failure = ""
            elif not self._close_owned_plotter(plotter):
                return False
            deferred_delete = getattr(plotter, "deleteLater", None)
            if not callable(deferred_delete):
                state = self._native_interactor_cleanup_state
                state.failure = "The 3D interactor has no DeferredDelete operation."
                logger.error(state.failure)
                return False
            delete_later = deferred_delete

        try:
            for i in reversed(range(self.plot_layout.count())):
                item = self.plot_layout.itemAt(i)
                if item:
                    w = item.widget()
                    if w:
                        w.setParent(None)
                        if w is not plotter:
                            w.deleteLater()

            if plotter is not None:
                if delete_later is None:
                    state = self._native_interactor_cleanup_state
                    state.failure = (
                        "The 3D interactor DeferredDelete operation was lost."
                    )
                    logger.error(state.failure)
                    return False
                delete_later()
                self.plotter_widget = None
        except Exception as exc:
            state = self._native_interactor_cleanup_state
            state.failure = f"3D interactor wrapper release failed: {exc}"
            logger.exception(state.failure)
            return False
        return True

    def _invalidate_async_requests(self) -> int:
        """Invalidate callbacks while retaining workers through ``finished``."""
        self._engine_request_id += 1
        self._pending_worker_start = None
        self._pending_3d_request = None
        self._current_publication_generation = None
        return self._engine_request_id

    def invalidate_render_publication(self) -> None:
        """Reject every callback owned by an older application publication."""
        self._active_scene_key = None
        self._invalidate_async_requests()
        self._clear_prepared_engine_cache()

    def _prepared_engine_cache_key(
        self,
        publication: SaliencyRenderPublication,
        selected_event: object,
        *,
        absolute: bool,
    ) -> tuple[object, ...]:
        return (
            id(publication),
            publication.request,
            publication.generation,
            publication.training_generation,
            str(selected_event),
            bool(absolute),
        )

    def _cached_prepared_engine(
        self,
        cache_key: tuple[object, ...],
        publication: SaliencyRenderPublication,
    ) -> tuple[object, int] | None:
        self._prune_dead_prepared_engine_cache_entries()
        entry = self._prepared_engine_cache.get(cache_key)
        if entry is None or entry.publication_ref() is not publication:
            return None
        self._prepared_engine_cache.move_to_end(cache_key)
        return entry.engine, entry.channel_count

    def _cache_prepared_engine(
        self,
        cache_key: tuple[object, ...],
        publication: SaliencyRenderPublication,
        result: tuple[object, int],
    ) -> None:
        self._prune_dead_prepared_engine_cache_entries()
        engine, channel_count = result
        self._prepared_engine_cache[cache_key] = _PreparedEngineCacheEntry(
            publication_ref=weakref.ref(publication),
            engine=engine,
            channel_count=int(channel_count),
        )
        self._prepared_engine_cache.move_to_end(cache_key)
        while (
            len(self._prepared_engine_cache) > self._MAX_PREPARED_ENGINE_CACHE_ENTRIES
        ):
            self._prepared_engine_cache.popitem(last=False)

    def _prune_dead_prepared_engine_cache_entries(self) -> None:
        dead_keys = [
            key
            for key, entry in self._prepared_engine_cache.items()
            if entry.publication_ref() is None
        ]
        for key in dead_keys:
            self._prepared_engine_cache.pop(key, None)

    def _clear_prepared_engine_cache(self) -> None:
        self._prepared_engine_cache.clear()

    @staticmethod
    def _disconnect_worker_callbacks(worker: Worker | None) -> None:
        if worker is None:
            return
        signals = getattr(worker, "signals", None)
        for signal_name in ("result", "error", "finished"):
            signal = getattr(signals, signal_name, None)
            disconnect = getattr(signal, "disconnect", None)
            if callable(disconnect):
                with contextlib.suppress(TypeError, RuntimeError):
                    disconnect()

    def _is_current_request(
        self,
        request_id: int,
        publication_generation: int | None = None,
    ) -> bool:
        return (
            not self._closed
            and not self._shutdown_requested
            and request_id == self._engine_request_id
            and (
                publication_generation is None
                or publication_generation == self._current_publication_generation
            )
            and not self._qt_object_deleted(self)
        )

    def update_plot(
        self,
        publication: SaliencyRenderPublication,
        absolute: bool,
    ) -> None:
        if self._closed:
            return
        if not isinstance(publication, SaliencyRenderPublication):
            message = "saliency render publication is invalid"
            logger.error("Error initializing 3D plot: %s", message)
            if not self._qt_object_deleted(self):
                self.show_error(message)
            return
        reserved_scene_key = None
        try:
            data = publication.data
            method = data.method
            method_coverage = self._saliency_coverage
            if method_coverage is None or method_coverage.method != method:
                self._sync_class_selector([], method=method)
                self.show_message(
                    f"{method} saliency coverage has not been published for this run. "
                    "Compute saliency to continue."
                )
                return
            self._sync_class_selector(method_coverage.classes, method=method)
            if not method_coverage.available:
                self.show_message(
                    self._unavailable_class_message(method),
                )
                return
            selected_event = self.class_combo.currentData()
            if selected_event is None:
                self.show_message(
                    f"No renderable class has {method} saliency. "
                    "Recompute saliency to continue.",
                )
                return
            selected_coverage = self._class_coverage.get(repr(selected_event))
            if selected_coverage is None or not selected_coverage.available:
                self.show_message(
                    self._unavailable_class_message(method, selected_coverage),
                )
                return

            scene_key = self._prepared_engine_cache_key(
                publication,
                selected_event,
                absolute=absolute,
            )
            if scene_key == getattr(self, "_active_scene_key", None):
                return

            request_id = self._invalidate_async_requests()
            self._current_publication_generation = publication.generation
            self._current_plot_request = (publication, absolute)

            # Montage Check
            positions = data.channel_positions
            if positions is None or len(positions) == 0:
                self.show_message(
                    "Please Set Montage First\n(Go to Configuration -> Set Montage)",
                )
                return

            events = list(data.event_ids)
            if not events:
                self._sync_class_selector([], method=method)
                self.show_error("No events found in dataset.")
                return

            available, reason = self._interactive_3d_runtime_available()
            if available is None:
                self._display_message(reason)
                self._start_interactive_3d_runtime_probe(
                    publication,
                    absolute,
                    request_id=request_id,
                )
                return
            if not available:
                self.show_message(reason)
                return

            cache_key = scene_key
            self._active_scene_key = scene_key
            reserved_scene_key = scene_key
            prepared = self._cached_prepared_engine(cache_key, publication)
            if prepared is not None:
                self._show_prepared_engine(
                    request_id,
                    prepared,
                    data,
                    selected_event,
                    method=method,
                    absolute=absolute,
                    publication_generation=publication.generation,
                )
                return

            self._start_3d_engine_worker(
                data,
                selected_event,
                method=method,
                absolute=absolute,
                request_id=request_id,
                publication_generation=publication.generation,
                publication=publication,
                prepared_cache_key=cache_key,
            )

        except Exception as e:
            if self._active_scene_key == reserved_scene_key:
                self._active_scene_key = None
            logger.error("Error initializing 3D plot: %s", e, exc_info=True)
            if not self._qt_object_deleted(self):
                self.show_error(SALIENCY_PREPARATION_FAILED_TEXT)

    def _sync_class_selector(
        self,
        classes: list[SaliencyClassCoverageSnapshot],
        *,
        method: str,
    ) -> None:
        class_keys = [
            item.store_key if item.store_key is not None else item.class_index
            for item in classes
        ]
        self._class_coverage = {
            repr(key): item for key, item in zip(class_keys, classes, strict=True)
        }
        if not class_keys:
            self.class_controls.hide()
            self.class_combo.clear()
            return

        existing = [
            str(self.class_combo.itemData(index))
            for index in range(self.class_combo.count())
        ]
        previous = (
            self._requested_class_key
            if self._requested_class_key is not None
            else self.class_combo.currentData()
        )
        self._selector_syncing = True
        self.class_combo.blockSignals(True)
        if existing != [str(key) for key in class_keys]:
            self.class_combo.clear()
            for coverage, class_key in zip(classes, class_keys, strict=True):
                self.class_combo.addItem(coverage.display_name, class_key)
        model = cast(QStandardItemModel, self.class_combo.model())
        for index, coverage in enumerate(classes):
            item = model.item(index)
            if item is not None:
                item.setEnabled(coverage.available)
                item.setToolTip(
                    "Saliency is ready for this class."
                    if coverage.available
                    else self._unavailable_class_message(method, coverage)
                )
        selected_index = self.class_combo.findData(previous)
        if selected_index < 0 or not classes[selected_index].available:
            selected_index = next(
                (index for index, coverage in enumerate(classes) if coverage.available),
                -1,
            )
        self.class_combo.setCurrentIndex(selected_index)
        self.class_combo.blockSignals(False)
        self._selector_syncing = False
        selected_coverage = classes[selected_index] if selected_index >= 0 else None
        if selected_coverage is None:
            self._requested_class_key = None
            self.class_semantics.clear()
        else:
            self._requested_class_key = self.class_combo.itemData(selected_index)
            event = selected_coverage.event_code
            self.class_semantics.setText(
                f"Event code: {event}" if event is not None else ""
            )
        self.class_controls.hide()

    def select_class_key(self, class_key: object) -> None:
        """Select a backend-admitted class key from the shared 2D controls."""
        self._requested_class_key = class_key
        coverage = next(
            (
                item
                for item in self._class_coverage.values()
                if (item.store_key if item.store_key is not None else item.class_index)
                == class_key
            ),
            None,
        )
        if coverage is not None:
            key = (
                coverage.store_key
                if coverage.store_key is not None
                else coverage.class_index
            )
            index = self.class_combo.findData(key)
            if index >= 0:
                with QSignalBlocker(self.class_combo):
                    self.class_combo.setCurrentIndex(index)

    def _on_class_changed(self, index: int) -> None:
        if self._selector_syncing or index < 0 or self._current_plot_request is None:
            return
        selected = self.class_combo.itemData(index)
        self._requested_class_key = selected
        coverage = self._class_coverage.get(repr(selected))
        if coverage is None or not coverage.available:
            self.show_message(
                self._unavailable_class_message(
                    self._current_plot_request[0].data.method,
                    coverage,
                ),
            )
            return
        publication = self._current_plot_request[0]
        self.update_plot(publication, self._current_plot_request[1])

    def _unavailable_class_message(
        self,
        method: str,
        coverage: SaliencyClassCoverageSnapshot | None = None,
    ) -> str:
        status = self._post_training_saliency_status
        if method in status.methods:
            if status.phase is PostTrainingSaliencyPhase.PENDING:
                return f"{method} saliency is waiting to start in the background."
            if status.phase is PostTrainingSaliencyPhase.RUNNING:
                return f"{method} saliency is being computed in the background."
            if status.phase is PostTrainingSaliencyPhase.FAILED:
                if status.message:
                    logger.error("Saliency computation failed: %s", status.message)
                return (
                    "Saliency computation could not be completed. "
                    "Recompute saliency to try again."
                )
            if status.phase is PostTrainingSaliencyPhase.CANCELLED:
                return (
                    "Saliency computation was cancelled. "
                    "Recompute saliency to try again."
                )
            if status.phase is PostTrainingSaliencyPhase.SUCCEEDED:
                return (
                    f"Saliency computation finished without renderable {method} output "
                    "for this class. Recompute saliency to try again."
                )
        if coverage is not None and coverage.reason:
            return coverage.reason
        return (
            f"No {method} saliency is available for the selected class. "
            "Recompute saliency to continue."
        )

    def _start_3d_engine_worker(
        self,
        render_data: SaliencyRenderData,
        selected_event,
        *,
        method="Gradient",
        absolute=False,
        request_id=None,
        publication_generation: int | None = None,
        publication: SaliencyRenderPublication | None = None,
        prepared_cache_key: tuple[object, ...] | None = None,
    ) -> None:
        if self._closed or self._shutdown_requested:
            return
        if request_id is None:
            request_id = self._invalidate_async_requests()
        elif not self._is_current_request(request_id, publication_generation):
            return
        if self.plotter_widget is None or self._qt_object_deleted(self.plotter_widget):
            self._display_message("Preparing 3D view...")
        if self._has_active_background_worker():
            self._pending_worker_start = lambda: self._start_3d_engine_worker(
                render_data,
                selected_event,
                method=method,
                absolute=absolute,
                request_id=request_id,
                publication_generation=publication_generation,
                publication=publication,
                prepared_cache_key=prepared_cache_key,
            )
            return
        start_error = _start_worker_atomically(
            worker_factory=lambda: Worker(
                Saliency3D.prepare_engine,
                render_data,
                selected_event,
                method=method,
                absolute=absolute,
            ),
            configure_worker=lambda worker: self._configure_3d_engine_worker(
                worker,
                request_id,
                render_data,
                selected_event,
                method=method,
                absolute=absolute,
                publication_generation=publication_generation,
                publication=publication,
                prepared_cache_key=prepared_cache_key,
            ),
            thread_pool_factory=lambda: self._worker_pool_owner.thread_pool,
            retain_worker=self._retain_engine_worker,
            release_worker=self._release_engine_worker,
        )
        if start_error is not None and self._is_current_request(
            request_id,
            publication_generation,
        ):
            self._active_scene_key = None
            self.show_error(
                _worker_start_failure_message(
                    "3D engine renderer",
                    start_error,
                    "Try again or switch to a 2D saliency view.",
                ),
            )

    def _configure_3d_engine_worker(
        self,
        worker: Worker,
        request_id: int,
        render_data: SaliencyRenderData,
        selected_event,
        *,
        method: str,
        absolute: bool,
        publication_generation: int | None,
        publication: SaliencyRenderPublication | None,
        prepared_cache_key: tuple[object, ...] | None,
    ) -> None:
        self._worker_pool_owner.retain(worker)
        receiver_ref = weakref.ref(self)

        def on_result(result, owned_worker=worker, rid=request_id) -> None:
            receiver = _live_qobject(receiver_ref)
            if receiver is None:
                return
            cast(Saliency3DPlotWidget, receiver)._on_3d_engine_ready(
                owned_worker,
                rid,
                result,
                render_data,
                selected_event,
                method=method,
                absolute=absolute,
                publication_generation=publication_generation,
                publication=publication,
                prepared_cache_key=prepared_cache_key,
            )

        def on_error(error, owned_worker=worker, rid=request_id) -> None:
            receiver = _live_qobject(receiver_ref)
            if receiver is None:
                return
            cast(Saliency3DPlotWidget, receiver)._on_3d_engine_error(
                owned_worker,
                rid,
                error,
                publication_generation=publication_generation,
            )

        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error)

        def on_finished(owned_worker=worker) -> None:
            receiver = _live_qobject(receiver_ref)
            if receiver is None:
                return
            cast(Saliency3DPlotWidget, receiver)._on_engine_worker_finished(
                owned_worker,
            )

        worker.signals.finished.connect(on_finished)

    def _retain_engine_worker(self, worker: Worker) -> None:
        self._engine_worker = worker

    def _release_engine_worker(self, worker: Worker) -> bool:
        retained_by_view = self._engine_worker is worker
        self._worker_pool_owner.release(worker)
        if retained_by_view:
            self._engine_worker = None
            self._consumed_worker_callbacks.discard(id(worker))
            self._disconnect_worker_callbacks(worker)
        return retained_by_view

    def _on_3d_engine_ready(
        self,
        worker: Worker,
        request_id,
        result,
        render_data: SaliencyRenderData,
        selected_event,
        *,
        method="Gradient",
        absolute=False,
        publication_generation: int | None = None,
        publication: SaliencyRenderPublication | None = None,
        prepared_cache_key: tuple[object, ...] | None = None,
    ) -> None:
        if not self._claim_worker_callback(worker, kind="engine"):
            return
        if not self._is_current_request(request_id, publication_generation):
            return
        self._show_prepared_engine(
            request_id,
            result,
            render_data,
            selected_event,
            method=method,
            absolute=absolute,
            publication_generation=publication_generation,
            publication=publication,
            prepared_cache_key=prepared_cache_key,
        )

    def _show_prepared_engine(
        self,
        request_id: int,
        result: tuple[object, int],
        render_data: SaliencyRenderData,
        selected_event: object,
        *,
        method: str,
        absolute: bool,
        publication_generation: int | None,
        publication: SaliencyRenderPublication | None = None,
        prepared_cache_key: tuple[object, ...] | None = None,
    ) -> None:
        if not self._is_current_request(request_id, publication_generation):
            return
        try:
            prepared_engine, prepared_channel_count = result
            if publication is not None and prepared_cache_key is not None:
                self._cache_prepared_engine(
                    prepared_cache_key,
                    publication,
                    (prepared_engine, prepared_channel_count),
                )
            if self.plotter_widget is None or self._qt_object_deleted(
                self.plotter_widget
            ):
                if not self._clear_plot_widgets():
                    return
                self.plotter_widget = cast(
                    QWidget,
                    pyvistaqt.QtInteractor(self.plot_container),
                )
                self.plot_layout.addWidget(self.plotter_widget)
                self.plot_layout.activate()
                self.plot_container.updateGeometry()
                interactor = getattr(self.plotter_widget, "interactor", None)
                if interactor is not None:
                    interactor.Initialize()
            plotter_widget = self.plotter_widget
            self._do_3d_plot_if_alive(
                request_id,
                plotter_widget,
                render_data,
                selected_event,
                method=method,
                absolute=absolute,
                prepared_engine=prepared_engine,
                prepared_channel_count=prepared_channel_count,
                publication_generation=publication_generation,
            )
        except Exception as exc:
            logger.exception("Could not initialize the 3D saliency geometry.")
            if self._is_current_request(request_id, publication_generation):
                self._active_scene_key = None
            if not self._qt_object_deleted(self):
                self.show_error(
                    _worker_start_failure_message(
                        "3D geometry renderer",
                        exc,
                        "Try again or switch to a 2D saliency view.",
                    ),
                )

    def _on_3d_engine_error(
        self,
        worker: Worker,
        request_id,
        error: tuple,
        *,
        publication_generation: int | None = None,
    ) -> None:
        if not self._claim_worker_callback(worker, kind="engine"):
            return
        if not self._is_current_request(request_id, publication_generation):
            return
        diagnostic = error[1] if len(error) > 1 else error
        formatted_traceback = error[2] if len(error) > 2 else ""
        logger.error(
            "3D saliency engine worker failed: %s\n%s",
            diagnostic,
            formatted_traceback,
        )
        self._active_scene_key = None
        self.show_error(SALIENCY_RENDER_FAILED_TEXT)

    def _on_engine_worker_finished(self, worker: Worker) -> None:
        if not self._release_engine_worker(worker):
            return
        self._start_pending_worker()

    def _do_3d_plot_if_alive(
        self,
        request_id,
        plotter_widget,
        render_data: SaliencyRenderData,
        selected_event,
        *,
        method="Gradient",
        absolute=False,
        prepared_engine=None,
        prepared_channel_count=None,
        publication_generation: int | None = None,
    ) -> None:
        """Render only for the exact current request and plotter identity."""
        if (
            not self._is_current_request(request_id, publication_generation)
            or self.plotter_widget is not plotter_widget
            or self._qt_object_deleted(plotter_widget)
        ):
            return
        self._do_3d_plot(
            render_data,
            selected_event,
            method=method,
            absolute=absolute,
            prepared_engine=prepared_engine,
            prepared_channel_count=prepared_channel_count,
            request_id=request_id,
            publication_generation=publication_generation,
        )

    def _do_3d_plot(
        self,
        render_data: SaliencyRenderData,
        selected_event,
        *,
        method="Gradient",
        absolute=False,
        prepared_engine=None,
        prepared_channel_count=None,
        request_id: int | None = None,
        publication_generation: int | None = None,
    ):
        try:
            if self._qt_object_deleted(self) or self._qt_object_deleted(
                self.plotter_widget,
            ):
                return
            if not self.plotter_widget:
                return

            saliency = Saliency3D(
                render_data,
                selected_event,
                method=method,
                absolute=absolute,
                plotter=self.plotter_widget,
                prepared_engine=prepared_engine,
                prepared_channel_count=prepared_channel_count,
            )
            init_error = getattr(saliency, "init_error", "")
            if init_error:
                logger.error("3D saliency engine initialization failed: %s", init_error)
                self._clear_active_scene_key_for_current_render(
                    request_id,
                    publication_generation,
                )
                self.show_error(safe_saliency_detail(init_error))
                return
            if getattr(saliency, "engine", None) is None:
                self._clear_active_scene_key_for_current_render(
                    request_id,
                    publication_generation,
                )
                self.show_error("3D saliency engine could not initialize.")
                return
            saliency.get_3d_head_plot()
            self._saliency_scene = saliency
            self.scene_controls.show()
            self.scene_overlay.show()
            self._position_scene_overlay()
        except Exception as e:
            logger.error("Error executing 3D plot: %s", e, exc_info=True)
            self._clear_active_scene_key_for_current_render(
                request_id,
                publication_generation,
            )
            if not self._qt_object_deleted(self):
                self.show_error(SALIENCY_RENDER_FAILED_TEXT)

    def _clear_active_scene_key_for_current_render(
        self,
        request_id: int | None,
        publication_generation: int | None,
    ) -> None:
        """Release only the scene owned by this still-current render callback."""
        if request_id is not None and self._is_current_request(
            request_id,
            publication_generation,
        ):
            self._active_scene_key = None

    def _set_epoch_time(self, value: int) -> None:
        scene = self._saliency_scene
        if scene is None or scene.engine is None:
            return
        low, high = scene.engine.time_range_seconds
        scene._set_time_seconds(low + (high - low) * value / 1000)

    def _toggle_electrodes(self, checked: bool) -> None:
        scene = self._saliency_scene
        if scene is not None:
            scene.channelBox.ctrl = checked
            scene.update()

    def _toggle_head(self, checked: bool) -> None:
        scene = self._saliency_scene
        if scene is not None:
            scene.headBox.ctrl = checked
            scene.update()

    def _reset_camera(self) -> None:
        if self.plotter_widget is not None:
            reset = getattr(self.plotter_widget, "reset_camera", None)
            if callable(reset):
                reset()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_scene_overlay()

    def _position_scene_overlay(self) -> None:
        """Keep scene actions inside the canvas at its lower-left edge."""
        if self.scene_overlay.isHidden():
            return
        size = self.scene_overlay.sizeHint()
        self.scene_overlay.setGeometry(
            12,
            max(12, self.plot_container.height() - size.height() - 12),
            size.width(),
            size.height(),
        )
        self.scene_overlay.raise_()

    @staticmethod
    def _qt_object_deleted(obj) -> bool:
        if obj is None:
            return False
        try:
            return bool(sip.isdeleted(obj))
        except (AttributeError, TypeError, RuntimeError):
            return False

    @staticmethod
    def _interactive_3d_runtime_available() -> tuple[bool | None, str]:
        """Return whether an interactive OpenGL Qt runtime is available."""
        qt_platform = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
        active_qt_platform = Saliency3DPlotWidget._active_qt_platform_name()
        pyvista_offscreen = os.environ.get("PYVISTA_OFF_SCREEN", "").strip().lower()
        if (
            qt_platform in {"offscreen", "minimal"}
            or active_qt_platform in {"offscreen", "minimal"}
            or pyvista_offscreen in {"1", "true", "yes"}
        ):
            return (
                False,
                "3D rendering requires an interactive OpenGL desktop session. "
                "Use the desktop launcher, or switch to Saliency Map, Spectrogram, "
                "or Topographic Map in this headless environment.",
            )
        if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
            return (
                False,
                "3D rendering requires an interactive Linux display with OpenGL. "
                "Use WSLg or a desktop session, or switch to a 2D saliency view.",
            )
        if sys.platform.startswith("linux"):
            cache_key = Saliency3DPlotWidget._runtime_probe_cache_key()
            cached = _INTERACTIVE_3D_PROBE_CACHE.get(cache_key)
            if cached is not None:
                return cached
            return (
                None,
                "Checking 3D runtime... If this takes more than a few seconds, "
                "use a 2D saliency view.",
            )
        return True, ""

    def _start_interactive_3d_runtime_probe(
        self,
        publication: SaliencyRenderPublication,
        absolute: bool,
        *,
        request_id: int | None = None,
    ) -> None:
        if self._closed or self._shutdown_requested:
            return
        publication_generation = publication.generation
        if request_id is None:
            request_id = self._invalidate_async_requests()
            self._current_publication_generation = publication_generation
        elif not self._is_current_request(request_id, publication_generation):
            return
        self._pending_3d_request = (
            request_id,
            (publication, absolute),
        )
        if self._has_active_background_worker():
            self._pending_worker_start = (
                lambda: self._start_interactive_3d_runtime_probe(
                    publication,
                    absolute,
                    request_id=request_id,
                )
            )
            return
        start_error = _start_worker_atomically(
            worker_factory=lambda: Worker(self._probe_interactive_3d_runtime),
            configure_worker=lambda worker: self._configure_runtime_probe_worker(
                worker,
                request_id,
                publication_generation,
            ),
            thread_pool_factory=lambda: self._worker_pool_owner.thread_pool,
            retain_worker=self._retain_runtime_probe_worker,
            release_worker=self._release_runtime_probe_worker,
        )
        if start_error is not None and self._is_current_request(
            request_id,
            publication_generation,
        ):
            self.show_error(
                _worker_start_failure_message(
                    "3D runtime probe",
                    start_error,
                    "Try again or switch to a 2D saliency view.",
                ),
            )

    def _configure_runtime_probe_worker(
        self,
        worker: Worker,
        request_id: int,
        publication_generation: int,
    ) -> None:
        self._worker_pool_owner.retain(worker)
        receiver_ref = weakref.ref(self)

        def on_result(result, owned_worker=worker, rid=request_id) -> None:
            receiver = _live_qobject(receiver_ref)
            if receiver is None:
                return
            cast(
                Saliency3DPlotWidget,
                receiver,
            )._on_interactive_3d_runtime_probe_result(
                owned_worker,
                rid,
                result,
                publication_generation=publication_generation,
            )

        def on_error(error, owned_worker=worker, rid=request_id) -> None:
            receiver = _live_qobject(receiver_ref)
            if receiver is None:
                return
            cast(
                Saliency3DPlotWidget,
                receiver,
            )._on_interactive_3d_runtime_probe_error(
                owned_worker,
                rid,
                error,
                publication_generation=publication_generation,
            )

        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error)

        def on_finished(owned_worker=worker) -> None:
            receiver = _live_qobject(receiver_ref)
            if receiver is None:
                return
            cast(
                Saliency3DPlotWidget,
                receiver,
            )._on_runtime_probe_worker_finished(owned_worker)

        worker.signals.finished.connect(on_finished)

    def _retain_runtime_probe_worker(self, worker: Worker) -> None:
        self._runtime_probe_worker = worker

    def _release_runtime_probe_worker(self, worker: Worker) -> bool:
        retained_by_view = self._runtime_probe_worker is worker
        self._worker_pool_owner.release(worker)
        if retained_by_view:
            self._runtime_probe_worker = None
            self._consumed_worker_callbacks.discard(id(worker))
            self._disconnect_worker_callbacks(worker)
        return retained_by_view

    def _on_interactive_3d_runtime_probe_result(
        self,
        worker: Worker,
        request_id: int,
        result,
        *,
        publication_generation: int | None = None,
    ) -> None:
        if not self._claim_worker_callback(worker, kind="probe"):
            return
        if not self._is_current_request(request_id, publication_generation):
            return
        available, reason = result
        pending = self._pending_3d_request
        self._pending_3d_request = None
        if pending is None or pending[0] != request_id:
            return
        if not available:
            self.show_message(str(reason))
            return
        self.update_plot(*pending[1])

    def _on_interactive_3d_runtime_probe_error(
        self,
        worker: Worker,
        request_id: int,
        error: tuple,
        *,
        publication_generation: int | None = None,
    ) -> None:
        if not self._claim_worker_callback(worker, kind="probe"):
            return
        if not self._is_current_request(request_id, publication_generation):
            return
        self._pending_3d_request = None
        diagnostic = error[1] if len(error) > 1 else error
        formatted_traceback = error[2] if len(error) > 2 else ""
        logger.error(
            "3D runtime probe failed: %s\n%s",
            diagnostic,
            formatted_traceback,
        )
        self.show_message(_RUNTIME_PROBE_FAILED_TEXT)

    def _on_runtime_probe_worker_finished(self, worker: Worker) -> None:
        if not self._release_runtime_probe_worker(worker):
            return
        self._start_pending_worker()

    def _has_active_background_worker(self) -> bool:
        return self._engine_worker is not None or self._runtime_probe_worker is not None

    def _claim_worker_callback(self, worker: Worker, *, kind: str) -> bool:
        expected = (
            self._engine_worker if kind == "engine" else self._runtime_probe_worker
        )
        identity = id(worker)
        if expected is not worker or identity in self._consumed_worker_callbacks:
            return False
        self._consumed_worker_callbacks.add(identity)
        return True

    def _start_pending_worker(self) -> None:
        if self._has_active_background_worker():
            return
        pending = self._pending_worker_start
        self._pending_worker_start = None
        if pending is not None and not self._closed and not self._shutdown_requested:
            pending()

    def begin_render_shutdown(self) -> None:
        """Detach callbacks and reject new 3D work without blocking Qt."""
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        self._active_scene_key = None
        self._invalidate_async_requests()
        self._clear_prepared_engine_cache()

    def cancel_render_shutdown(self) -> None:
        """Allow new 3D requests after an application close is cancelled."""
        if not self._closed:
            self._shutdown_requested = False

    def native_render_work_idle(self) -> bool:
        """Return whether engine/probe ownership reached queued ``finished``."""
        return (
            not self._has_active_background_worker()
            and self._worker_pool_owner.active_worker_count == 0
        )

    def native_render_resources_finalized(self) -> bool:
        """Return whether the owned QtInteractor reached terminal cleanup."""
        state = self._native_interactor_cleanup_state
        return bool(
            self._native_resources_finalized
            and state.finalized
            and state.finalize_count == 1
            and self.plotter_widget is None
        )

    def finalize_native_render_resources(self) -> bool:
        """Release the QtInteractor once on the owning GUI thread."""
        state = self._native_interactor_cleanup_state
        if state.finalized:
            self._native_resources_finalized = True
            self._resume_blocked_deferred_delete()
            return True
        if QThread.currentThread() is not self.thread():
            logger.error("3D native resources must be finalized on the GUI thread.")
            return False
        self._closed = True
        self._shutdown_requested = True
        self._invalidate_async_requests()
        self._current_plot_request = None
        self._clear_prepared_engine_cache()
        self._worker_pool_owner.request_shutdown()
        if not self._clear_plot_widgets():
            self._native_resources_finalized = False
            return False
        state.finalized = True
        state.finalize_count += 1
        state.cleanup_thread = QThread.currentThread()
        state.failure = ""
        self._native_resources_finalized = True
        self._resume_blocked_deferred_delete()
        return True

    def _resume_blocked_deferred_delete(self) -> None:
        if (
            not self._deferred_delete_blocked
            or self._handling_deferred_delete
            or self._qt_object_deleted(self)
        ):
            return
        self._deferred_delete_blocked = False
        receiver_ref = weakref.ref(self)
        delete_timer = QTimer(QApplication.instance())
        delete_timer.setSingleShot(True)

        def delete_finalized_receiver() -> None:
            try:
                receiver = _live_qobject(receiver_ref)
                if receiver is None or not receiver.native_render_resources_finalized():
                    return
                sip.delete(receiver)
            finally:
                delete_timer.deleteLater()

        delete_timer.timeout.connect(delete_finalized_receiver)
        delete_timer.start(0)

    def event(self, event):
        """Use the same finalizer for deferred Qt destruction."""
        if event.type() is QEvent.Type.DeferredDelete:
            self._handling_deferred_delete = True
            try:
                finalized = self.finalize_native_render_resources()
            finally:
                self._handling_deferred_delete = False
            if not finalized:
                self._deferred_delete_blocked = True
                return True
            self._deferred_delete_blocked = False
        return super().event(event)

    def closeEvent(self, event):  # noqa: N802
        """Invalidate late callbacks and release native 3D widgets on close."""
        if not self.finalize_native_render_resources():
            event.ignore()
            return
        super().closeEvent(event)

    @staticmethod
    def _active_qt_platform_name() -> str:
        """Return the actual QApplication platform if a Qt app exists."""
        app = QApplication.instance()
        if app is None:
            return ""
        platform_name = getattr(app, "platformName", None)
        if not callable(platform_name):
            return ""
        return str(platform_name()).strip().lower()

    @staticmethod
    def _probe_interactive_3d_runtime() -> tuple[bool, str]:
        """Probe PyVistaQt in a child process before touching the live UI."""
        env = dict(os.environ)
        cache_key = Saliency3DPlotWidget._runtime_probe_cache_key(env)
        cached = _INTERACTIVE_3D_PROBE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        try:
            completed = subprocess.run(  # noqa: S603
                [sys.executable, "-c", _INTERACTIVE_3D_PROBE_CODE],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_INTERACTIVE_3D_PROBE_TIMEOUT_SECONDS,
                env=env,
            )
        except subprocess.TimeoutExpired:
            result = (
                False,
                "3D rendering did not start within the runtime probe timeout. "
                "Use a native desktop/OpenGL session or a 2D saliency view.",
            )
            _INTERACTIVE_3D_PROBE_CACHE[cache_key] = result
            return result

        if completed.returncode == 0 and "plotter_created=True" in completed.stdout:
            result = (True, "")
        else:
            detail = (
                completed.stderr.strip()
                or completed.stdout.strip()
                or f"probe exited with code {completed.returncode}"
            )
            first_line = detail.splitlines()[0]
            result = (
                False,
                "3D rendering is blocked by the current desktop OpenGL runtime "
                f"({first_line}). Use a native desktop/X11 session or a 2D "
                "saliency view.",
            )
        _INTERACTIVE_3D_PROBE_CACHE[cache_key] = result
        return result

    @staticmethod
    def _runtime_probe_cache_key(
        env: dict[str, str] | None = None,
    ) -> tuple[str, str, str, str]:
        source = env if env is not None else os.environ
        return (
            source.get("QT_QPA_PLATFORM", ""),
            source.get("DISPLAY", ""),
            source.get("WAYLAND_DISPLAY", ""),
            source.get("XDG_SESSION_TYPE", ""),
        )
