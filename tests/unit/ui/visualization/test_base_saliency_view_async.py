from __future__ import annotations

import ast
import gc
import inspect
import threading
import time
import weakref
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from matplotlib.figure import Figure
from PyQt6 import sip
from PyQt6.QtCore import QThread, QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QWidget

from XBrainLab.ui.panels.visualization.saliency_views import base_saliency_view
from XBrainLab.ui.panels.visualization.saliency_views.base_saliency_view import (
    BaseSaliencyView,
)
from XBrainLab.ui.panels.visualization.saliency_views.map_view import SaliencyMapWidget


def test_saliency_render_returns_before_background_work_finishes(qtbot):
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    started = threading.Event()
    release = threading.Event()
    rendered = Figure()

    def render() -> Figure:
        started.set()
        assert release.wait(timeout=3.0)
        return rendered

    started_at = time.perf_counter()
    view._render_figure_async(render, error_context="test")
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.2
    assert view.error_label.text() == "Rendering saliency..."
    assert started.wait(timeout=1.0)

    release.set()
    qtbot.waitUntil(lambda: view.fig is rendered, timeout=3000)
    assert view.canvas is not None
    assert view.error_label.isHidden()


def test_saliency_render_result_is_published_on_widget_thread(qtbot):
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    rendered = Figure()
    publish_threads: list[QThread] = []
    original = view._replace_figure

    def record_publish(figure: Figure) -> None:
        current_thread = QThread.currentThread()
        assert current_thread is not None
        publish_threads.append(current_thread)
        original(figure)

    with patch.object(view, "_replace_figure", side_effect=record_publish):
        view._render_figure_async(lambda: rendered, error_context="test")
        qtbot.waitUntil(lambda: bool(publish_threads), timeout=3000)

    assert publish_threads == [view.thread()]


def test_detail_canvas_zoom_pan_and_reset_follow_replacement_canvas(qtbot):
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    first = Figure()
    first_axis = first.add_subplot(111)
    first_axis.imshow([[0.0, 1.0], [2.0, 3.0]])
    assert view._replace_figure(first) is True
    initial_xlim = first_axis.get_xlim()
    initial_ylim = first_axis.get_ylim()

    view._on_canvas_scroll(
        SimpleNamespace(
            inaxes=first_axis,
            xdata=0.5,
            ydata=0.5,
            step=1,
        )
    )
    assert first_axis.get_xlim() != initial_xlim
    view._on_canvas_press(
        SimpleNamespace(
            button=1,
            inaxes=first_axis,
            xdata=0.5,
            ydata=0.5,
        )
    )
    view._on_canvas_motion(
        SimpleNamespace(
            inaxes=first_axis,
            xdata=0.7,
            ydata=0.8,
        )
    )
    view._on_canvas_release(SimpleNamespace())
    view.reset_view()
    assert first_axis.get_xlim() == pytest.approx(initial_xlim)
    assert first_axis.get_ylim() == pytest.approx(initial_ylim)

    second = Figure()
    second_axis = second.add_subplot(111)
    second_axis.imshow([[5.0, 6.0], [7.0, 8.0]])
    assert view._replace_figure(second) is True

    assert id(first_axis) not in view._initial_axis_limits
    assert id(second_axis) in view._initial_axis_limits
    assert view._pan_state is None


def test_cross_view_worker_waits_until_gui_install_is_terminal(qtbot):
    """A second view must not render while the first result is installed."""
    first_view = BaseSaliencyView()
    second_view = BaseSaliencyView()
    qtbot.addWidget(first_view)
    qtbot.addWidget(second_view)
    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    release_second = threading.Event()
    install_observations: list[bool] = []
    first_figure = Figure()
    second_figure = Figure()

    def render_first() -> Figure:
        first_started.set()
        assert release_first.wait(timeout=3.0)
        return first_figure

    def render_second() -> Figure:
        second_started.set()
        assert release_second.wait(timeout=3.0)
        return second_figure

    original_install = first_view._replace_figure

    def observe_install(figure: Figure) -> bool:
        # Give an incorrectly released worker lock enough time to expose the
        # overlap. The production GUI never performs this wait.
        install_observations.append(second_started.wait(timeout=0.15))
        return original_install(figure)

    with patch.object(first_view, "_replace_figure", side_effect=observe_install):
        first_view._render_figure_async(render_first, error_context="first")
        assert first_started.wait(timeout=1.0)
        second_view._render_figure_async(render_second, error_context="second")
        release_first.set()
        qtbot.waitUntil(lambda: bool(install_observations), timeout=3000)

    assert install_observations == [False]
    qtbot.waitUntil(second_started.is_set, timeout=3000)
    release_second.set()
    qtbot.waitUntil(lambda: second_view.fig is second_figure, timeout=3000)


def test_gui_clear_is_queued_behind_another_views_worker(qtbot):
    first_view = BaseSaliencyView()
    second_view = BaseSaliencyView()
    qtbot.addWidget(first_view)
    qtbot.addWidget(second_view)
    render_started = threading.Event()
    release_render = threading.Event()

    def render() -> Figure:
        render_started.set()
        assert release_render.wait(timeout=3.0)
        return Figure()

    first_view._render_figure_async(render, error_context="first")
    assert render_started.wait(timeout=1.0)

    with patch.object(
        second_view,
        "_clear_plot_now",
        wraps=second_view._clear_plot_now,
    ) as clear_now:
        second_view.clear_plot()
        clear_now.assert_not_called()
        release_render.set()
        qtbot.waitUntil(lambda: clear_now.call_count == 1, timeout=3000)


def test_stale_saliency_render_is_closed_instead_of_installed(qtbot):
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    first_started = threading.Event()
    release_first = threading.Event()
    first: Figure | None = Figure()
    second = Figure()

    def render_first() -> Figure:
        first_started.set()
        assert release_first.wait(timeout=3.0)
        assert first is not None
        return first

    assert first is not None
    first.add_subplot(111)
    first_ref = weakref.ref(first)
    view._render_figure_async(render_first, error_context="first")
    assert first_started.wait(timeout=1.0)
    view._render_figure_async(lambda: second, error_context="second")
    release_first.set()
    qtbot.waitUntil(lambda: view.fig is second, timeout=3000)

    assert first.canvas is None
    assert first.axes == []
    first = None
    gc.collect()
    assert first_ref() is None
    assert view._render_workers == {}


def test_saliency_render_coalesces_queued_requests_to_latest(qtbot):
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    first_started = threading.Event()
    release_first = threading.Event()
    started: list[str] = []
    first = Figure()
    second = Figure()
    latest = Figure()

    def render_first() -> Figure:
        started.append("first")
        first_started.set()
        assert release_first.wait(timeout=3.0)
        return first

    def render_second() -> Figure:
        started.append("second")
        return second

    def render_latest() -> Figure:
        started.append("latest")
        return latest

    view._render_figure_async(render_first, error_context="first")
    assert first_started.wait(timeout=1.0)

    view._render_figure_async(render_second, error_context="second")
    view._render_figure_async(render_latest, error_context="latest")

    assert started == ["first"]

    release_first.set()
    qtbot.waitUntil(lambda: view.fig is latest, timeout=3000)

    assert started == ["first", "latest"]
    assert view._render_workers == {}


def test_close_does_not_wait_for_render_and_late_figure_is_closed(qtbot):
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    figure_created = threading.Event()
    release_render = threading.Event()
    pending_started = threading.Event()
    rendered_figure_ref: list[weakref.ReferenceType[Figure]] = []
    published: list[Figure] = []

    def render() -> Figure:
        figure = Figure()
        figure.add_subplot(111)
        rendered_figure_ref.append(weakref.ref(figure))
        figure_created.set()
        assert release_render.wait(timeout=3.0)
        return figure

    with patch.object(view, "_replace_figure", side_effect=published.append):
        view._render_figure_async(render, error_context="close")
        assert figure_created.wait(timeout=1.0)
        view._render_figure_async(
            lambda: pending_started.set() or Figure(),
            error_context="pending",
        )

        started_at = time.perf_counter()
        view.close()
        elapsed = time.perf_counter() - started_at

        assert elapsed < 0.2
        assert view.fig is None
        assert view.canvas is None
        retained_worker_count = len(view._render_workers)
        cleanup_owner = getattr(view, "_render_cleanup_owner", None)
        retained_owner_count = (
            cleanup_owner.active_worker_count if cleanup_owner is not None else 0
        )

        release_render.set()
        qtbot.waitUntil(lambda: view._render_workers == {}, timeout=3000)
        gc.collect()
        qtbot.wait(50)
        late_figure_released = rendered_figure_ref[0]() is None

    assert retained_worker_count == 1
    assert retained_owner_count == 1
    assert late_figure_released
    assert published == []
    assert not pending_started.is_set()


def test_qt_teardown_drops_late_result_and_releases_figure(qtbot):
    view = BaseSaliencyView()
    figure_created = threading.Event()
    release_render = threading.Event()
    rendered_figure_ref: list[weakref.ReferenceType[Figure]] = []
    published: list[Figure] = []

    def render() -> Figure:
        figure = Figure()
        figure.add_subplot(111)
        rendered_figure_ref.append(weakref.ref(figure))
        figure_created.set()
        assert release_render.wait(timeout=3.0)
        return figure

    with patch.object(
        BaseSaliencyView,
        "_replace_figure",
        side_effect=published.append,
    ):
        view._render_figure_async(render, error_context="delete")
        assert figure_created.wait(timeout=1.0)
        owner = getattr(view, "_render_cleanup_owner", None)
        owner_thread = owner.thread() if owner is not None else None
        owner_thread_id = int(QThread.currentThreadId())
        worker = next(iter(view._render_workers.values()))
        worker_ref = weakref.ref(worker)
        signals_ref = weakref.ref(worker.signals)
        cleanup_thread_ids: list[int] = []
        worker_probe = weakref.ref(
            worker,
            lambda _reference: cleanup_thread_ids.append(
                int(QThread.currentThreadId())
            ),
        )
        signals_probe = weakref.ref(
            worker.signals,
            lambda _reference: cleanup_thread_ids.append(
                int(QThread.currentThreadId())
            ),
        )
        del worker

        view.deleteLater()
        qtbot.waitUntil(lambda: sip.isdeleted(view), timeout=1000)
        retained_owner_count = owner.active_worker_count if owner is not None else 0
        retained_worker = worker_ref() is not None
        retained_signals = signals_ref() is not None
        release_render.set()
        if owner is not None:
            qtbot.waitUntil(lambda: owner.active_worker_count == 0, timeout=3000)
            qtbot.waitUntil(lambda: sip.isdeleted(owner), timeout=3000)
            owner_deleted = True
        else:
            qtbot.wait(100)
            owner_deleted = False
        gc.collect()
        worker_released = worker_ref() is None
        signals_released = signals_ref() is None
        late_figure_released = rendered_figure_ref[0]() is None

    assert owner is not None
    assert owner_deleted
    assert retained_owner_count == 1
    assert retained_worker
    assert retained_signals
    assert worker_released
    assert signals_released
    assert late_figure_released
    assert published == []
    assert view._render_workers == {}
    assert owner_thread is not None
    assert cleanup_thread_ids
    assert all(thread_id == owner_thread_id for thread_id in cleanup_thread_ids)
    assert worker_probe() is None
    assert signals_probe() is None


def test_long_worker_render_keeps_gui_heartbeat_responsive(qtbot):
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    started = threading.Event()
    release = threading.Event()
    heartbeat_count = 0

    def render() -> Figure:
        started.set()
        assert release.wait(timeout=3.0)
        return Figure()

    timer = QTimer(view)

    def heartbeat() -> None:
        nonlocal heartbeat_count
        heartbeat_count += 1

    timer.timeout.connect(heartbeat)
    timer.start(5)

    view._render_figure_async(render, error_context="heartbeat")
    assert started.wait(timeout=1.0)
    assert view.fig is None
    assert view.canvas is None
    qtbot.waitUntil(lambda: heartbeat_count >= 5, timeout=500)

    release.set()
    qtbot.waitUntil(lambda: view._render_workers == {}, timeout=3000)


def test_replacing_qtagg_canvas_deletes_widget_and_breaks_figure_cycle(qtbot):
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    old_canvas = view.canvas
    old_figure = view.fig
    assert old_canvas is not None
    assert old_figure is not None
    old_canvas_ref = weakref.ref(old_canvas)
    old_figure_ref = weakref.ref(old_figure)

    replacement = Figure()
    view._replace_figure(replacement)

    assert view.fig is replacement
    assert old_figure.canvas is None
    assert old_canvas.figure is None
    qtbot.waitUntil(lambda: sip.isdeleted(old_canvas), timeout=1000)
    old_canvas = None
    old_figure = None
    gc.collect()
    assert old_canvas_ref() is None
    assert old_figure_ref() is None


def test_view_delete_deletes_current_canvas_and_releases_current_figure(qtbot):
    view = BaseSaliencyView()
    canvas = view.canvas
    figure = view.fig
    assert canvas is not None
    assert figure is not None
    canvas_ref = weakref.ref(canvas)
    figure_ref = weakref.ref(figure)

    view.deleteLater()
    qtbot.waitUntil(lambda: sip.isdeleted(view), timeout=1000)
    qtbot.waitUntil(lambda: sip.isdeleted(canvas), timeout=1000)
    assert figure.canvas is None
    assert canvas.figure is None

    canvas = None
    figure = None
    gc.collect()
    assert canvas_ref() is None
    assert figure_ref() is None


def test_native_resource_finalizer_is_idempotent_across_child_close_paths(qtbot):
    view = BaseSaliencyView()
    canvas = view.canvas
    figure = view.fig
    assert canvas is not None
    assert figure is not None
    assert view.native_render_resources_finalized() is False

    with patch.object(
        view,
        "finalize_native_render_resources",
        wraps=view.finalize_native_render_resources,
    ) as finalize:
        assert finalize() is True
        cleanup_state = view._native_plot_cleanup_state
        assert cleanup_state is not None
        view.closeEvent(QCloseEvent())
        assert view.canvas is None
        assert view.fig is None
        assert figure.canvas is None
        assert canvas.figure is None

        view.deleteLater()
        qtbot.waitUntil(lambda: sip.isdeleted(view), timeout=1000)

        assert finalize.call_count == 3
        assert cleanup_state.release_count == 1
        assert view.native_render_resources_finalized() is True


def test_deferred_delete_queues_live_canvas_cleanup_independent_of_deleted_view(
    qtbot,
    monkeypatch,
):
    active_view = BaseSaliencyView()
    qtbot.addWidget(active_view)
    deleted_view = BaseSaliencyView()
    canvas = deleted_view.canvas
    figure = deleted_view.fig
    assert canvas is not None
    assert figure is not None

    active_started = threading.Event()
    release_active = threading.Event()
    cleanup_threads: list[QThread] = []
    original_dispose = base_saliency_view._dispose_figure

    def hold_coordinator() -> Figure:
        active_started.set()
        assert release_active.wait(timeout=3.0)
        return Figure()

    def track_deleted_figure_cleanup(candidate: Figure | None) -> None:
        if candidate is figure:
            cleanup_thread = QThread.currentThread()
            assert cleanup_thread is not None
            cleanup_threads.append(cleanup_thread)
        original_dispose(candidate)

    monkeypatch.setattr(
        base_saliency_view,
        "_dispose_figure",
        track_deleted_figure_cleanup,
    )
    active_view._render_figure_async(
        hold_coordinator,
        error_context="hold coordinator",
    )
    qtbot.waitUntil(active_started.is_set, timeout=1000)

    deleted_view.deleteLater()
    qtbot.waitUntil(lambda: sip.isdeleted(deleted_view), timeout=1000)

    assert cleanup_threads == []
    assert sip.isdeleted(canvas) is False
    assert figure.canvas is canvas
    assert canvas.figure is figure

    release_active.set()
    qtbot.waitUntil(lambda: len(cleanup_threads) == 1, timeout=3000)
    qtbot.waitUntil(active_view.native_render_work_idle, timeout=3000)
    qtbot.wait(50)

    assert cleanup_threads == [active_view.thread()]
    assert deleted_view._native_resources_finalized is True
    assert deleted_view._native_plot_cleanup_state is not None
    assert deleted_view._native_plot_cleanup_state.release_count == 1
    assert deleted_view._native_plot_cleanup_owner is None
    assert figure.canvas is None
    assert canvas.figure is None
    qtbot.waitUntil(lambda: sip.isdeleted(canvas), timeout=1000)


def test_replace_figure_failure_releases_candidate_and_shows_recovery(
    qtbot,
    monkeypatch,
):
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    original_figure = view.fig
    original_canvas = view.canvas
    candidate = Figure()
    candidate.add_subplot(111)

    def fail_canvas(_figure):
        raise RuntimeError("native canvas construction failed")

    monkeypatch.setattr(base_saliency_view, "FigureCanvas", fail_canvas)
    replaced = view._replace_figure(candidate)

    assert replaced is False
    assert view.fig is original_figure
    assert view.canvas is original_canvas
    assert candidate.canvas is None
    assert candidate.axes == []
    assert "Saliency could not be rendered" in view.error_label.text()
    assert "Try again" in view.error_label.text()


def test_replace_figure_install_failure_deletes_candidate_canvas_and_figure(
    qtbot,
    monkeypatch,
):
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    original_figure = view.fig
    original_canvas = view.canvas
    candidate = Figure()
    candidate.add_subplot(111)
    created_canvases = []
    original_canvas_factory = base_saliency_view.FigureCanvas

    def create_canvas(figure):
        canvas = original_canvas_factory(figure)
        created_canvases.append(canvas)
        return canvas

    def fail_fit() -> None:
        raise RuntimeError("native canvas draw failed")

    monkeypatch.setattr(base_saliency_view, "FigureCanvas", create_canvas)
    monkeypatch.setattr(view, "_fit_current_figure", fail_fit)

    replaced = view._replace_figure(candidate)

    assert replaced is False
    assert view.fig is original_figure
    assert view.canvas is original_canvas
    assert len(created_canvases) == 1
    candidate_canvas = created_canvases.pop()
    assert candidate.canvas is None
    assert candidate_canvas.figure is None
    assert candidate.axes == []
    assert "Saliency could not be rendered" in view.error_label.text()
    qtbot.waitUntil(lambda: sip.isdeleted(candidate_canvas), timeout=1000)


@pytest.mark.parametrize("failure_stage", ["constructor", "pool_start"])
def test_saliency_render_start_failure_is_actionable_released_and_retryable(
    qtbot,
    monkeypatch,
    failure_stage,
):
    """A setup failure must not strand the 2D view in its loading state."""
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    original_worker = base_saliency_view.Worker

    if failure_stage == "constructor":

        def fail_worker(*_args, **_kwargs):
            raise RuntimeError("worker construction failed")

        monkeypatch.setattr(base_saliency_view, "Worker", fail_worker)
    else:

        class FailingPool:
            def start(self, _worker):
                raise RuntimeError("thread pool start failed")

            def clear(self) -> None:
                pass

        monkeypatch.setattr(
            view._render_cleanup_owner,
            "_thread_pool",
            FailingPool(),
        )

    view._render_figure_async(lambda: Figure(), error_context="test")

    assert view._render_workers == {}
    assert "Rendering saliency..." not in view.error_label.text()
    assert "Saliency renderer failed to start" in view.error_label.text()
    assert "RuntimeError" not in view.error_label.text()
    assert "Try again" in view.error_label.text()

    class RunningPool:
        def start(self, worker):
            worker.run()

        def clear(self) -> None:
            pass

    rendered = Figure()
    monkeypatch.setattr(base_saliency_view, "Worker", original_worker)
    monkeypatch.setattr(
        view._render_cleanup_owner,
        "_thread_pool",
        RunningPool(),
    )

    view._render_figure_async(lambda: rendered, error_context="retry")

    qtbot.waitUntil(lambda: view.fig is rendered, timeout=1_000)
    assert view._render_workers == {}
    assert view.error_label.isHidden()


def test_saliency_render_path_does_not_pump_nested_qt_events():
    source = inspect.getsource(BaseSaliencyView)

    assert "processEvents" not in source


def test_saliency_render_worker_does_not_depend_on_the_global_qthreadpool():
    source = inspect.getsource(BaseSaliencyView._start_render_request)

    assert "QThreadPool.globalInstance" not in source


def test_saliency_layout_path_does_not_defer_geometry_with_qtimer():
    source = inspect.getsource(base_saliency_view)

    assert "QTimer.singleShot" not in source


def test_all_saliency_views_avoid_timing_based_render_workarounds():
    view_dir = Path(base_saliency_view.__file__).parent

    for source_path in view_dir.glob("*.py"):
        source = source_path.read_text(encoding="utf-8")
        assert "QTimer.singleShot" not in source, source_path.name
        assert ".processEvents(" not in source, source_path.name


def test_2d_saliency_render_jobs_do_not_capture_widget_instance():
    view_dir = Path(base_saliency_view.__file__).parent

    for filename in ("map_view.py", "spectrogram_view.py", "topomap_view.py"):
        source = (view_dir / filename).read_text(encoding="utf-8")
        tree = ast.parse(source)
        render_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_render_figure_async"
        ]
        assert render_calls, filename
        for call in render_calls:
            assert call.args, filename
            captured_names = {
                node.id for node in ast.walk(call.args[0]) if isinstance(node, ast.Name)
            }
            assert "self" not in captured_names, filename

        render_functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_render_plot"
        ]
        assert render_functions, filename
        for function in render_functions:
            forbidden_names = {
                node.id for node in ast.walk(function) if isinstance(node, ast.Name)
            }
            assert "FigureCanvas" not in forbidden_names, filename
            assert "QWidget" not in forbidden_names, filename


def test_runtime_guard_rejects_render_callable_that_captures_qwidget(qtbot):
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    captured_widget = QWidget()
    qtbot.addWidget(captured_widget)
    called = threading.Event()

    def render() -> Figure:
        captured_widget.objectName()
        called.set()
        return Figure()

    view._render_figure_async(render, error_context="captured QWidget")

    assert not called.is_set()
    assert view._render_workers == {}
    assert "Saliency could not be rendered" in view.error_label.text()


def test_runtime_guard_rejects_callable_object_with_qwidget_attribute(qtbot):
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    captured_widget = QWidget()
    qtbot.addWidget(captured_widget)
    called = threading.Event()

    class WidgetCapturingRenderer:
        def __init__(self, widget: QWidget) -> None:
            self.widget = widget

        def __call__(self) -> Figure:
            self.widget.objectName()
            called.set()
            return Figure()

    view._render_figure_async(
        WidgetCapturingRenderer(captured_widget),
        error_context="callable object QWidget",
    )

    assert not called.is_set()
    assert view._render_workers == {}
    assert "Saliency could not be rendered" in view.error_label.text()


def test_runtime_guard_rejects_slotted_callable_with_qwidget_attribute(qtbot):
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    captured_widget = QWidget()
    qtbot.addWidget(captured_widget)
    called = threading.Event()

    class SlottedWidgetCapturingRenderer:
        __slots__ = ("widget",)

        def __init__(self, widget: QWidget) -> None:
            self.widget = widget

        def __call__(self) -> Figure:
            self.widget.objectName()
            called.set()
            return Figure()

    view._render_figure_async(
        SlottedWidgetCapturingRenderer(captured_widget),
        error_context="slotted callable QWidget",
    )

    assert not called.is_set()
    assert view._render_workers == {}
    assert "Saliency could not be rendered" in view.error_label.text()


def test_replaced_figure_is_fitted_to_current_qt_layout_synchronously(qtbot):
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    view.resize(220, 220)
    figure = Figure(figsize=(2, 2), dpi=100)
    axis = figure.add_subplot(111)
    axis.set_ylabel("frequency")
    figure.subplots_adjust(left=0.01)

    view._replace_figure(figure)

    assert view.canvas is not None
    view.canvas.draw()
    bounds = axis.get_tightbbox(view.canvas.get_renderer())
    assert bounds is not None
    assert bounds.x0 >= 3.0


def test_replaced_figure_becomes_visible_after_loading_state(qtbot):
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    view.show()
    view._display_message("Rendering saliency...")

    assert view.canvas is not None
    assert view.canvas.isHidden()

    replaced = view._replace_figure(Figure(figsize=(2, 2), dpi=100))
    qtbot.wait(0)

    assert replaced is True
    assert view.canvas is not None
    assert view.canvas.isVisibleTo(view)
    assert view.error_label.isHidden()


def test_scrollable_map_placeholder_hides_plot_surface_and_centers_message(qtbot):
    """An empty Saliency Map must not reserve its hidden scroll canvas height."""
    view = SaliencyMapWidget()
    qtbot.addWidget(view)
    view.resize(640, 360)
    view.show()
    qtbot.waitExposed(view)

    view.show_message("Gradient saliency has not been computed for this fold.")
    qtbot.wait(0)

    assert view._canvas_scroll_area is not None
    assert view._canvas_scroll_area.isHidden()
    assert view.error_label.isVisible()
    assert (
        abs(view.error_label.geometry().center().y() - view.contentsRect().center().y())
        <= 3
    )
