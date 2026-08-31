from __future__ import annotations

import ast
import inspect
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.application.saliency_render import (
    SaliencyPlanIdentity,
    SaliencyRenderData,
    SaliencyRenderPublication,
    SaliencyRenderRequest,
    SaliencyRunIdentity,
)
from XBrainLab.ui.panels.visualization.saliency_views import plot_3d_view
from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view import (
    Saliency3DPlotWidget,
)


class _Signal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in tuple(self._callbacks):
            callback(*args)

    def disconnect(self, callback=None) -> None:
        if callback is None:
            self._callbacks.clear()
            return
        self._callbacks.remove(callback)


def test_interactive_probe_disables_core_dumps_before_native_imports():
    tree = ast.parse(plot_3d_view._INTERACTIVE_3D_PROBE_CODE)
    disable_call = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "_disable_probe_core_dumps"
        ),
        None,
    )
    assert disable_call is not None

    native_import_lines = [
        node.lineno
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and (
            (
                isinstance(node, ast.Import)
                and any(
                    alias.name.split(".", 1)[0] in {"PyQt6", "pyvista", "pyvistaqt"}
                    for alias in node.names
                )
            )
            or (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.split(".", 1)[0] in {"PyQt6", "pyvista", "pyvistaqt"}
            )
        )
    ]
    assert native_import_lines
    assert disable_call.lineno < min(native_import_lines)

    disable_function = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_disable_probe_core_dumps"
        ),
        None,
    )
    assert disable_function is not None
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "setrlimit"
        for node in ast.walk(disable_function)
    )
    fail_closed_guard = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.If)
            and disable_call.lineno < node.lineno < min(native_import_lines)
            and any(
                isinstance(candidate, ast.Name)
                and candidate.id == "_CORE_DUMPS_DISABLED"
                for candidate in ast.walk(node.test)
            )
        ),
        None,
    )
    assert fail_closed_guard is not None
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "exit"
        for node in ast.walk(fail_closed_guard)
    )


class _ManualWorker:
    def __init__(self, *_args, **_kwargs) -> None:
        self.signals = SimpleNamespace(
            result=_Signal(),
            error=_Signal(),
            finished=_Signal(),
        )


class _CollectingPool:
    def __init__(self) -> None:
        self.workers = []

    def start(self, worker) -> None:
        self.workers.append(worker)

    def clear(self) -> None:
        pass


def _render_publication(
    *,
    method: str = "Gradient",
    class_names: tuple[str, ...] = ("left",),
    generation: int = 2,
) -> SaliencyRenderPublication:
    request = SaliencyRenderRequest(
        publication_generation=generation,
        run=SaliencyRunIdentity(
            plan=SaliencyPlanIdentity(plan_index=0),
            run_index=0,
        ),
        method=method,
    )
    data = SaliencyRenderData(
        method=method,
        saliency_by_class={
            index: np.ones((1, 1, 3)) for index, _name in enumerate(class_names)
        },
        class_map=tuple(enumerate(class_names)),
        event_ids={name: index for index, name in enumerate(class_names)},
        channel_names=("C3",),
        channel_positions=((0.0, 0.0, 0.1),),
        sfreq=128.0,
        tmin=0.0,
    )
    return SaliencyRenderPublication(
        request=request,
        generation=generation,
        training_generation=4,
        data=data,
    )


def _install_manual_workers(widget, monkeypatch):
    workers: list[_ManualWorker] = []
    worker_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    pool = _CollectingPool()

    def make_worker(*args, **kwargs):
        worker = _ManualWorker()
        workers.append(worker)
        worker_calls.append((args, kwargs))
        return worker

    monkeypatch.setattr(plot_3d_view, "Worker", make_worker)
    monkeypatch.setattr(widget._worker_pool_owner, "_thread_pool", pool)
    return workers, pool, worker_calls


def _start_engine_for_publication(
    widget: Saliency3DPlotWidget,
    publication: SaliencyRenderPublication,
    selected_event: str = "left",
    *,
    absolute: bool = False,
) -> int:
    request_id = widget._invalidate_async_requests()
    widget._current_publication_generation = publication.generation
    widget._start_3d_engine_worker(
        publication.data,
        selected_event,
        method=publication.data.method,
        absolute=absolute,
        request_id=request_id,
        publication_generation=publication.generation,
    )
    return request_id


def test_3d_background_paths_do_not_depend_on_the_global_qthreadpool():
    for start_method in (
        Saliency3DPlotWidget._start_3d_engine_worker,
        Saliency3DPlotWidget._start_interactive_3d_runtime_probe,
    ):
        assert "QThreadPool.globalInstance" not in inspect.getsource(start_method)


def _visible_messages(widget: Saliency3DPlotWidget) -> list[str]:
    return [
        label.text()
        for label in widget.findChildren(plot_3d_view.QLabel)
        if not label.isHidden() and label.text()
    ]


def _flush_deferred_deletes() -> None:
    for _ in range(3):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        QCoreApplication.processEvents()


@pytest.fixture
def widget(qtbot, monkeypatch):
    monkeypatch.setattr(plot_3d_view, "pyvistaqt", MagicMock())
    instance = Saliency3DPlotWidget(parent=None)
    qtbot.addWidget(instance)
    return instance


@pytest.mark.parametrize("failure_stage", ["constructor", "pool_start"])
def test_3d_engine_start_failure_releases_worker_and_allows_retry(
    widget,
    monkeypatch,
    failure_stage,
):
    publication = _render_publication(method="SmoothGrad", generation=7)
    failed_worker = None
    if failure_stage == "constructor":

        def fail_worker(*_args, **_kwargs):
            raise RuntimeError("engine worker construction failed")

        monkeypatch.setattr(plot_3d_view, "Worker", fail_worker)
    else:
        failed_worker = _ManualWorker()
        monkeypatch.setattr(
            plot_3d_view,
            "Worker",
            lambda *_args, **_kwargs: failed_worker,
        )

        class FailingPool:
            def start(self, _worker) -> None:
                raise RuntimeError("engine thread pool start failed")

            def clear(self) -> None:
                pass

        monkeypatch.setattr(
            widget._worker_pool_owner,
            "_thread_pool",
            FailingPool(),
        )

    failed_request_id = _start_engine_for_publication(widget, publication)

    assert widget._engine_worker is None
    assert widget._pending_3d_request is None
    assert widget._current_publication_generation is None
    assert widget._engine_request_id > failed_request_id
    messages = _visible_messages(widget)
    assert all("Preparing 3D view..." not in message for message in messages)
    assert any("3D engine renderer failed to start" in message for message in messages)
    assert all("RuntimeError" not in message for message in messages)
    assert any("Try again" in message for message in messages)

    if failed_worker is not None:
        with patch.object(
            plot_3d_view.pyvistaqt,
            "QtInteractor",
            side_effect=AssertionError("failed starts must not retain callbacks"),
        ):
            failed_worker.signals.result.emit((MagicMock(), 1))
        assert widget._engine_worker is None

    workers, pool, worker_calls = _install_manual_workers(widget, monkeypatch)
    retry_request_id = _start_engine_for_publication(
        widget,
        publication,
        absolute=True,
    )

    assert pool.workers == workers
    assert widget._engine_worker is workers[0]
    assert widget._engine_request_id == retry_request_id
    assert widget._current_publication_generation == publication.generation
    worker_args, worker_kwargs = worker_calls[0]
    assert worker_args == (
        plot_3d_view.Saliency3D.prepare_engine,
        publication.data,
        "left",
    )
    assert worker_kwargs == {"method": "SmoothGrad", "absolute": True}
    with patch.object(widget, "show_error", wraps=widget.show_error) as show_error:
        workers[0].signals.error.emit((RuntimeError, RuntimeError("engine failed"), ""))
        workers[0].signals.error.emit((RuntimeError, RuntimeError("engine failed"), ""))

    assert widget._engine_worker is workers[0]
    workers[0].signals.finished.emit()
    assert widget._engine_worker is None
    assert widget._current_publication_generation is None
    show_error.assert_called_once()


def test_failed_3d_engine_preparation_allows_retry_of_the_same_scene(
    widget,
    monkeypatch,
):
    """A failed preparation must not reserve its scene key indefinitely."""
    publication = _render_publication(generation=13)
    widget.set_saliency_coverage(
        plot_3d_view.SaliencyMethodCoverageSnapshot(
            method="Gradient",
            available=True,
            complete=True,
            classes=[
                plot_3d_view.SaliencyClassCoverageSnapshot(
                    class_index=0,
                    display_name="left",
                    available=True,
                ),
            ],
        )
    )

    monkeypatch.setattr(
        Saliency3DPlotWidget,
        "_interactive_3d_runtime_available",
        staticmethod(lambda: (True, "")),
    )
    workers, pool, _ = _install_manual_workers(widget, monkeypatch)
    widget.update_plot(publication, False)
    workers[0].signals.error.emit((RuntimeError, RuntimeError("engine failed"), ""))
    workers[0].signals.finished.emit()

    assert widget._active_scene_key is None

    widget.update_plot(publication, False)

    assert pool.workers == workers
    assert widget._engine_worker is workers[1]


def test_failed_final_3d_render_allows_retry_of_the_same_scene(
    widget,
    monkeypatch,
):
    """A head-plot failure releases the current scene key for an exact retry."""
    publication = _render_publication(generation=14)
    plotter = QWidget(widget.plot_container)
    widget.plot_layout.addWidget(plotter)
    widget.plotter_widget = plotter
    request_id = widget._invalidate_async_requests()
    widget._current_publication_generation = publication.generation
    widget._active_scene_key = widget._prepared_engine_cache_key(
        publication,
        "left",
        absolute=False,
    )
    time_axis = np.array([-0.2, 0.0])
    engine_contract = {
        "time_axis_seconds": time_axis,
        "time_range_seconds": (-0.2, 0.0),
        "initial_time_seconds": -0.2,
        "sample_index_for_time": lambda _time: 0,
    }
    failed_scene = SimpleNamespace(
        init_error="",
        engine=SimpleNamespace(**engine_contract),
        get_3d_head_plot=MagicMock(side_effect=RuntimeError("head plot failed")),
    )
    rendered_scene = SimpleNamespace(
        init_error="",
        engine=SimpleNamespace(**engine_contract),
        get_3d_head_plot=MagicMock(),
    )
    monkeypatch.setattr(
        plot_3d_view,
        "Saliency3D",
        MagicMock(side_effect=(failed_scene, rendered_scene)),
    )

    widget._do_3d_plot_if_alive(
        request_id,
        plotter,
        publication.data,
        "left",
        publication_generation=publication.generation,
    )

    assert widget._active_scene_key is None

    retry_request_id = widget._invalidate_async_requests()
    widget._current_publication_generation = publication.generation
    retry_plotter = QWidget(widget.plot_container)
    widget.plot_layout.addWidget(retry_plotter)
    widget.plotter_widget = retry_plotter
    widget._do_3d_plot_if_alive(
        retry_request_id,
        retry_plotter,
        publication.data,
        "left",
        publication_generation=publication.generation,
    )

    assert plot_3d_view.Saliency3D.call_count == 2
    assert widget._saliency_scene is rendered_scene


def test_stale_final_3d_render_failure_keeps_newer_scene_key(
    widget,
    monkeypatch,
):
    publication = _render_publication(generation=15)
    plotter = QWidget(widget.plot_container)
    widget.plot_layout.addWidget(plotter)
    widget.plotter_widget = plotter
    stale_request_id = widget._invalidate_async_requests()
    widget._current_publication_generation = publication.generation
    widget._invalidate_async_requests()
    widget._current_publication_generation = publication.generation + 1
    newer_scene_key = ("newer-scene",)
    widget._active_scene_key = newer_scene_key
    saliency_constructor = MagicMock(
        side_effect=AssertionError("stale render must not construct a scene"),
    )
    monkeypatch.setattr(plot_3d_view, "Saliency3D", saliency_constructor)

    widget._do_3d_plot_if_alive(
        stale_request_id,
        plotter,
        publication.data,
        "left",
        publication_generation=publication.generation,
    )

    saliency_constructor.assert_not_called()
    assert widget._active_scene_key == newer_scene_key


@pytest.mark.parametrize("failure_stage", ["constructor", "pool_start"])
def test_3d_runtime_probe_start_failure_releases_worker_and_allows_retry(
    widget,
    monkeypatch,
    failure_stage,
):
    publication = _render_publication(generation=11)
    failed_worker = None
    if failure_stage == "constructor":

        def fail_worker(*_args, **_kwargs):
            raise RuntimeError("probe worker construction failed")

        monkeypatch.setattr(plot_3d_view, "Worker", fail_worker)
    else:
        failed_worker = _ManualWorker()
        monkeypatch.setattr(
            plot_3d_view,
            "Worker",
            lambda *_args, **_kwargs: failed_worker,
        )

        class FailingPool:
            def start(self, _worker) -> None:
                raise RuntimeError("probe thread pool start failed")

            def clear(self) -> None:
                pass

        monkeypatch.setattr(
            widget._worker_pool_owner,
            "_thread_pool",
            FailingPool(),
        )

    widget._start_interactive_3d_runtime_probe(
        publication,
        False,
    )

    assert widget._runtime_probe_worker is None
    assert widget._pending_3d_request is None
    assert widget._current_publication_generation is None
    messages = _visible_messages(widget)
    assert any("3D runtime probe failed to start" in message for message in messages)
    assert all("RuntimeError" not in message for message in messages)
    assert any("Try again" in message for message in messages)

    if failed_worker is not None:
        with patch.object(widget, "update_plot") as update_plot:
            failed_worker.signals.result.emit((True, ""))
        update_plot.assert_not_called()
        assert widget._pending_3d_request is None

    workers, pool, worker_calls = _install_manual_workers(widget, monkeypatch)
    widget._start_interactive_3d_runtime_probe(
        publication,
        True,
    )

    assert pool.workers == workers
    assert widget._runtime_probe_worker is workers[0]
    request_id = widget._engine_request_id
    assert widget._pending_3d_request == (request_id, (publication, True))
    assert widget._current_publication_generation == publication.generation
    assert worker_calls == [
        ((widget._probe_interactive_3d_runtime,), {}),
    ]
    workers[0].signals.result.emit((False, "3D runtime unavailable"))
    assert widget._runtime_probe_worker is workers[0]
    workers[0].signals.finished.emit()
    assert widget._runtime_probe_worker is None
    assert widget._pending_3d_request is None
    assert widget._current_publication_generation is None


def test_3d_geometry_handoff_failure_is_typed_and_cleaned_once(
    widget,
    monkeypatch,
):
    publication = _render_publication(
        method="VarGrad",
        generation=17,
    )
    workers, pool, worker_calls = _install_manual_workers(widget, monkeypatch)
    request_id = _start_engine_for_publication(
        widget,
        publication,
        absolute=True,
    )

    assert pool.workers == workers
    worker_args, worker_kwargs = worker_calls[0]
    assert isinstance(worker_args[1], SaliencyRenderData)
    assert worker_args[1] is publication.data
    assert worker_args[2] == "left"
    assert worker_kwargs == {"method": "VarGrad", "absolute": True}

    with (
        patch.object(widget, "show_error", wraps=widget.show_error) as show_error,
        patch.object(
            plot_3d_view.pyvistaqt,
            "QtInteractor",
            side_effect=RuntimeError("OpenGL context initialization failed"),
        ),
    ):
        workers[0].signals.result.emit((MagicMock(), 1))
        workers[0].signals.result.emit((MagicMock(), 1))

    assert widget._engine_worker is workers[0]
    workers[0].signals.finished.emit()
    assert widget._engine_worker is None
    assert widget._engine_request_id > request_id
    assert widget._current_publication_generation is None
    show_error.assert_called_once()
    messages = _visible_messages(widget)
    assert any(
        "3D geometry renderer failed to start" in message for message in messages
    )
    assert all("RuntimeError" not in message for message in messages)
    assert any("Try again" in message for message in messages)


def test_3d_engine_terminal_error_is_sanitized_and_logged(
    widget,
    monkeypatch,
    caplog,
    capture_product_logs,
) -> None:
    publication = _render_publication(generation=19)
    workers, _pool, _worker_calls = _install_manual_workers(widget, monkeypatch)
    _start_engine_for_publication(widget, publication)

    with capture_product_logs(logging.ERROR):
        workers[0].signals.error.emit(
            (
                RuntimeError,
                RuntimeError("OpenGL private tuple ('context', 0)"),
                "Traceback: OpenGL private tuple",
            ),
        )

    messages = _visible_messages(widget)
    assert any("Saliency could not be rendered" in message for message in messages)
    assert all("OpenGL private tuple" not in message for message in messages)
    assert "OpenGL private tuple ('context', 0)" in caplog.text


def test_stale_3d_worker_callbacks_do_not_clear_newer_worker_or_mutate_ui(
    widget,
    monkeypatch,
):
    first_publication = _render_publication(generation=21)
    current_publication = _render_publication(
        method="SmoothGrad",
        class_names=("left", "right"),
        generation=22,
    )
    workers, pool, _worker_calls = _install_manual_workers(widget, monkeypatch)

    first_request_id = _start_engine_for_publication(widget, first_publication)
    current_request_id = _start_engine_for_publication(
        widget,
        current_publication,
        "right",
        absolute=True,
    )

    first = workers[0]
    assert pool.workers == [first]
    assert current_request_id > first_request_id
    assert widget._engine_request_id == current_request_id
    assert widget._current_publication_generation == current_publication.generation
    with patch.object(
        plot_3d_view.pyvistaqt,
        "QtInteractor",
        side_effect=AssertionError("stale engine result must not build geometry"),
    ):
        first.signals.result.emit((MagicMock(), 1))

    assert widget._engine_worker is first
    assert widget._engine_request_id == current_request_id
    assert widget._current_publication_generation == current_publication.generation
    first.signals.finished.emit()
    current = workers[1]
    assert pool.workers == [first, current]
    assert widget._engine_worker is current

    # Finish the current engine before exercising the probe serialization path.
    current.signals.finished.emit()
    assert widget._engine_worker is None

    failed_probe_publication = _render_publication(generation=23)
    widget._start_interactive_3d_runtime_probe(
        failed_probe_publication,
        False,
    )
    first_probe = workers[2]
    first_probe_request_id = widget._engine_request_id
    assert widget._pending_3d_request == (
        first_probe_request_id,
        (failed_probe_publication, False),
    )
    first_probe.signals.error.emit((RuntimeError, RuntimeError("probe failed"), ""))
    assert widget._runtime_probe_worker is first_probe
    assert widget._pending_3d_request is None
    assert widget._current_publication_generation is None
    first_probe.signals.finished.emit()
    assert widget._runtime_probe_worker is None

    current_probe_publication = _render_publication(generation=24)
    widget._start_interactive_3d_runtime_probe(
        current_probe_publication,
        True,
    )
    current_probe = workers[3]
    current_probe_request_id = widget._engine_request_id

    with patch.object(widget, "update_plot") as update_plot:
        first_probe.signals.result.emit((True, ""))

    assert widget._runtime_probe_worker is current_probe
    assert widget._engine_request_id == current_probe_request_id
    assert widget._current_publication_generation == (
        current_probe_publication.generation
    )
    assert widget._pending_3d_request == (
        current_probe_request_id,
        (current_probe_publication, True),
    )
    update_plot.assert_not_called()


@pytest.mark.parametrize("worker_kind", ["engine", "probe"])
def test_3d_worker_is_owned_until_finished_and_serializes_replacement(
    widget,
    monkeypatch,
    worker_kind,
):
    first_publication = _render_publication(generation=61)
    second_publication = _render_publication(generation=62)
    workers, pool, _worker_calls = _install_manual_workers(widget, monkeypatch)

    if worker_kind == "engine":
        _start_engine_for_publication(widget, first_publication)
        first_worker = workers[0]
        first_worker.signals.result.emit((MagicMock(), 1))
        _start_engine_for_publication(widget, second_publication)
        retained_worker = widget._engine_worker
    else:
        widget._start_interactive_3d_runtime_probe(first_publication, False)
        first_worker = workers[0]
        with patch.object(widget, "update_plot"):
            first_worker.signals.result.emit((False, "unavailable"))
        widget._start_interactive_3d_runtime_probe(second_publication, True)
        retained_worker = widget._runtime_probe_worker

    assert retained_worker is first_worker
    assert pool.workers == [first_worker]

    first_worker.signals.finished.emit()

    assert len(pool.workers) == 2
    assert pool.workers[1] is workers[1]
    if worker_kind == "engine":
        assert widget._engine_worker is workers[1]
    else:
        assert widget._runtime_probe_worker is workers[1]


@pytest.mark.parametrize(
    ("replacement", "expected_message"),
    [
        ("message", "new status"),
        ("clear", None),
        ("error", "Error: new failure"),
    ],
)
def test_new_plot_state_invalidates_old_engine_completion(
    widget,
    monkeypatch,
    replacement,
    expected_message,
):
    publication = _render_publication(generation=31)
    workers, _pool, _worker_calls = _install_manual_workers(widget, monkeypatch)
    old_request_id = _start_engine_for_publication(widget, publication)
    old_worker = workers[0]

    if replacement == "message":
        widget.show_message("new status")
    elif replacement == "error":
        widget.show_error("new failure")
    else:
        widget.clear_plot()

    invalidated_request_id = widget._engine_request_id
    assert invalidated_request_id > old_request_id
    assert widget._engine_worker is old_worker
    assert widget._pending_3d_request is None
    assert widget._current_publication_generation is None

    with (
        patch.object(plot_3d_view.pyvistaqt, "QtInteractor") as interactor,
        patch.object(widget, "show_error") as stale_error,
    ):
        old_worker.signals.result.emit((MagicMock(), 1))
        old_worker.signals.error.emit(
            (RuntimeError, RuntimeError("stale engine failure"), ""),
        )

    interactor.assert_not_called()
    stale_error.assert_not_called()
    assert widget._engine_worker is old_worker
    old_worker.signals.finished.emit()
    assert widget._engine_worker is None
    assert widget._engine_request_id == invalidated_request_id
    if expected_message is not None:
        assert expected_message in _visible_messages(widget)


def test_runtime_probe_completion_is_isolated_to_its_request_generation(
    widget,
    monkeypatch,
):
    workers, pool, worker_calls = _install_manual_workers(widget, monkeypatch)
    first_publication = _render_publication(
        method="Gradient",
        generation=41,
    )
    second_publication = _render_publication(
        method="SmoothGrad",
        generation=42,
    )

    widget._start_interactive_3d_runtime_probe(first_publication, False)
    first_probe = workers[0]
    first_request_id = widget._engine_request_id
    assert widget._current_publication_generation == first_publication.generation
    assert widget._pending_3d_request == (
        first_request_id,
        (first_publication, False),
    )

    widget._start_interactive_3d_runtime_probe(second_publication, True)
    second_request_id = widget._engine_request_id
    assert pool.workers == [first_probe]
    assert len(worker_calls) == 1
    assert second_request_id > first_request_id
    assert widget._current_publication_generation == second_publication.generation
    assert widget._pending_3d_request == (
        second_request_id,
        (second_publication, True),
    )

    with patch.object(widget, "update_plot") as update_plot:
        first_probe.signals.result.emit((True, ""))
        update_plot.assert_not_called()
        assert widget._runtime_probe_worker is first_probe
        assert widget._engine_request_id == second_request_id
        assert widget._current_publication_generation == (second_publication.generation)
        assert widget._pending_3d_request == (
            second_request_id,
            (second_publication, True),
        )

        first_probe.signals.finished.emit()
        second_probe = workers[1]
        assert pool.workers == [first_probe, second_probe]
        assert len(worker_calls) == 2
        assert widget._runtime_probe_worker is second_probe
        second_probe.signals.result.emit((True, ""))

    update_plot.assert_called_once_with(second_publication, True)
    assert widget._runtime_probe_worker is second_probe
    assert widget._pending_3d_request is None
    assert widget._current_publication_generation == second_publication.generation
    second_probe.signals.finished.emit()
    assert widget._runtime_probe_worker is None


def test_close_invalidates_engine_completion_before_geometry_initialization(
    widget,
    monkeypatch,
):
    publication = _render_publication(generation=51)
    workers, _pool, _worker_calls = _install_manual_workers(widget, monkeypatch)
    request_id = _start_engine_for_publication(widget, publication)
    old_worker = workers[0]
    widget._current_plot_request = (publication, False)

    assert widget._current_publication_generation == publication.generation
    assert widget._current_plot_request == (publication, False)

    widget.closeEvent(QCloseEvent())
    closed_request_id = widget._engine_request_id

    with (
        patch.object(plot_3d_view.pyvistaqt, "QtInteractor") as interactor,
        patch.object(widget, "_do_3d_plot") as render,
        patch.object(widget, "show_error") as show_error,
    ):
        old_worker.signals.result.emit((MagicMock(), 1))
        old_worker.signals.error.emit(
            (RuntimeError, RuntimeError("late close failure"), ""),
        )

    interactor.assert_not_called()
    render.assert_not_called()
    show_error.assert_not_called()
    assert widget._closed is True
    assert closed_request_id > request_id
    assert widget._engine_worker is old_worker
    assert widget._runtime_probe_worker is None
    assert widget._pending_3d_request is None
    assert widget._current_publication_generation is None
    assert widget._current_plot_request is None
    old_worker.signals.finished.emit()
    assert widget._engine_worker is None

    widget._start_3d_engine_worker(
        publication.data,
        "left",
        method=publication.data.method,
        absolute=False,
    )
    widget._start_interactive_3d_runtime_probe(publication, False)

    assert workers == [old_worker]
    assert widget._engine_request_id == closed_request_id


def test_close_invalidates_runtime_probe_completion_before_render_restart(
    widget,
    monkeypatch,
):
    publication = _render_publication(generation=52)
    workers, _pool, _worker_calls = _install_manual_workers(widget, monkeypatch)

    widget._start_interactive_3d_runtime_probe(publication, True)
    probe_worker = workers[0]
    request_id = widget._engine_request_id
    assert widget._runtime_probe_worker is probe_worker
    assert widget._pending_3d_request == (request_id, (publication, True))
    assert widget._current_publication_generation == publication.generation

    widget.closeEvent(QCloseEvent())

    with (
        patch.object(widget, "update_plot") as update_plot,
        patch.object(widget, "show_message") as show_message,
    ):
        probe_worker.signals.result.emit((True, ""))
        probe_worker.signals.error.emit(
            (RuntimeError, RuntimeError("late probe failure"), ""),
        )

    update_plot.assert_not_called()
    show_message.assert_not_called()
    assert widget._closed is True
    assert widget._engine_request_id > request_id
    assert widget._engine_worker is None
    assert widget._runtime_probe_worker is probe_worker
    assert widget._pending_3d_request is None
    assert widget._current_publication_generation is None
    probe_worker.signals.finished.emit()
    assert widget._runtime_probe_worker is None


@pytest.mark.parametrize("worker_kind", ["engine", "probe"])
def test_deleted_3d_widget_does_not_receive_worker_callbacks(
    qtbot,
    monkeypatch,
    worker_kind,
):
    monkeypatch.setattr(plot_3d_view, "pyvistaqt", MagicMock())
    instance = Saliency3DPlotWidget(parent=None)
    publication = _render_publication(generation=71)
    workers, _pool, _worker_calls = _install_manual_workers(instance, monkeypatch)
    callback_entries: list[tuple[str, bool]] = []

    if worker_kind == "engine":
        instance._on_3d_engine_ready = lambda *_args, **_kwargs: (
            callback_entries.append(("result", sip.isdeleted(instance)))
        )
        instance._on_3d_engine_error = lambda *_args, **_kwargs: (
            callback_entries.append(("error", sip.isdeleted(instance)))
        )
        instance._on_engine_worker_finished = lambda *_args, **_kwargs: (
            callback_entries.append(("finished", sip.isdeleted(instance)))
        )
        _start_engine_for_publication(instance, publication)
        worker = workers[0]
        result = (MagicMock(), 1)
    else:
        instance._on_interactive_3d_runtime_probe_result = (
            lambda *_args, **_kwargs: callback_entries.append(
                ("result", sip.isdeleted(instance)),
            )
        )
        instance._on_interactive_3d_runtime_probe_error = (
            lambda *_args, **_kwargs: callback_entries.append(
                ("error", sip.isdeleted(instance)),
            )
        )
        instance._on_runtime_probe_worker_finished = lambda *_args, **_kwargs: (
            callback_entries.append(("finished", sip.isdeleted(instance)))
        )
        instance._start_interactive_3d_runtime_probe(publication, False)
        worker = workers[0]
        result = (False, "unavailable")

    owner = instance._worker_pool_owner
    instance.deleteLater()
    _flush_deferred_deletes()
    assert sip.isdeleted(instance)
    assert owner.active_worker_count == 1

    worker.signals.result.emit(result)
    worker.signals.error.emit((RuntimeError, RuntimeError("late failure"), ""))
    worker.signals.finished.emit()

    assert callback_entries == []
    assert owner.active_worker_count == 0
    qtbot.waitUntil(lambda: sip.isdeleted(owner), timeout=1000)


def test_deferred_delete_is_consumed_when_native_interactor_close_fails(
    monkeypatch,
):
    monkeypatch.setattr(plot_3d_view, "pyvistaqt", MagicMock())
    instance = Saliency3DPlotWidget(parent=None)

    class _FailingInteractor(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.should_fail = True
            self.close_calls = 0
            self._closed = False
            self._RenderWindow = object()
            self.iren = object()

        def close(self) -> bool:
            self.close_calls += 1
            if self.should_fail:
                raise RuntimeError("native close failed")
            self._closed = True
            self._RenderWindow = None
            self.iren = None
            return True

    plotter = _FailingInteractor(instance.plot_container)
    instance.plot_layout.addWidget(plotter)
    instance.plotter_widget = plotter
    cleanup_state = instance._native_interactor_cleanup_state

    instance.deleteLater()
    _flush_deferred_deletes()

    assert not sip.isdeleted(instance)
    assert not sip.isdeleted(plotter)
    assert cleanup_state.finalized is False
    assert cleanup_state.finalize_count == 0
    assert cleanup_state.close_attempts == 1
    assert cleanup_state.close_successes == 0
    assert instance.plotter_widget is plotter

    plotter.should_fail = False
    assert instance.finalize_native_render_resources() is True
    _flush_deferred_deletes()
    assert sip.isdeleted(instance)
    assert cleanup_state.finalized is True
    assert cleanup_state.finalize_count == 1
    assert cleanup_state.close_attempts == 2
    assert cleanup_state.close_successes == 1


def test_3d_native_resource_finalizer_closes_interactor_once_across_child_paths(
    qtbot,
):
    widget = Saliency3DPlotWidget(parent=None)

    class _TrackedInteractor(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.close_calls = 0
            self.delete_later_calls = 0
            self._closed = False
            self._RenderWindow = object()
            self.iren = object()
            self.renderer = object()

        def close(self) -> bool:
            self.close_calls += 1
            self._closed = True
            self._RenderWindow = None
            self.iren = None
            self.renderer = None
            return True

        def deleteLater(self) -> None:
            self.delete_later_calls += 1
            super().deleteLater()

    plotter = _TrackedInteractor(widget.plot_container)
    widget.plot_layout.addWidget(plotter)
    widget.plotter_widget = plotter
    assert widget.native_render_resources_finalized() is False

    with patch.object(
        widget,
        "finalize_native_render_resources",
        wraps=widget.finalize_native_render_resources,
    ) as finalize:
        assert finalize() is True
        cleanup_state = widget._native_interactor_cleanup_state
        qtbot.waitUntil(lambda: plot_3d_view.sip.isdeleted(plotter), timeout=1000)
        widget.closeEvent(QCloseEvent())
        widget.deleteLater()
        qtbot.waitUntil(lambda: plot_3d_view.sip.isdeleted(widget), timeout=1000)

    assert finalize.call_count == 3
    assert plotter.close_calls == 1
    assert plotter.delete_later_calls == 1
    assert cleanup_state.finalized is True
    assert cleanup_state.finalize_count == 1
    assert cleanup_state.close_attempts == 1
    assert cleanup_state.close_successes == 1
    assert widget.plotter_widget is None
    assert widget.native_render_resources_finalized() is True


def test_3d_finalizer_retains_native_ownership_and_reports_close_failure(widget):
    class _FailingInteractor(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.close_calls = 0
            self.delete_later_calls = 0
            self.should_fail = True
            self._closed = False
            self._RenderWindow = object()
            self.iren = object()
            self.renderer = object()

        def close(self) -> bool:
            self.close_calls += 1
            if self.should_fail:
                raise RuntimeError("native close failed")
            self._closed = True
            self._RenderWindow = None
            self.iren = None
            self.renderer = None
            return True

        def deleteLater(self) -> None:
            self.delete_later_calls += 1

    plotter = _FailingInteractor(widget.plot_container)
    widget.plot_layout.addWidget(plotter)
    widget.plotter_widget = plotter

    assert widget.finalize_native_render_resources() is False

    cleanup_state = widget._native_interactor_cleanup_state
    assert cleanup_state.finalized is False
    assert cleanup_state.finalize_count == 0
    assert cleanup_state.close_attempts == 1
    assert cleanup_state.close_successes == 0
    assert "native close failed" in cleanup_state.failure
    assert widget.plotter_widget is plotter
    assert plotter.parent() is widget.plot_container
    assert widget.plot_layout.indexOf(plotter) >= 0
    assert plotter.delete_later_calls == 0
    assert widget.native_render_resources_finalized() is False

    plotter.should_fail = False
    assert widget.finalize_native_render_resources() is True
    assert cleanup_state.finalized is True
    assert cleanup_state.finalize_count == 1
    assert cleanup_state.close_attempts == 2
    assert cleanup_state.close_successes == 1
    assert cleanup_state.failure == ""
    assert widget.plotter_widget is None
    assert plotter.delete_later_calls == 1


def test_3d_finalizer_rejects_unverified_native_close(widget):
    class _UnverifiedInteractor(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.close_calls = 0
            self.delete_later_calls = 0
            self._closed = False
            self._RenderWindow = object()
            self.iren = object()
            self.renderer = object()

        def close(self) -> bool:
            self.close_calls += 1
            return True

        def deleteLater(self) -> None:
            self.delete_later_calls += 1

    plotter = _UnverifiedInteractor(widget.plot_container)
    widget.plot_layout.addWidget(plotter)
    widget.plotter_widget = plotter

    assert widget.finalize_native_render_resources() is False

    cleanup_state = widget._native_interactor_cleanup_state
    assert cleanup_state.finalized is False
    assert cleanup_state.close_attempts == 1
    assert cleanup_state.close_successes == 0
    assert cleanup_state.failure
    assert widget.plotter_widget is plotter
    assert plotter.delete_later_calls == 0
    assert widget.native_render_resources_finalized() is False

    plotter._closed = True
    plotter._RenderWindow = None
    plotter.iren = None
    plotter.renderer = None
    assert widget.finalize_native_render_resources() is True


def test_3d_finalizer_retries_wrapper_release_without_double_closing(widget):
    class _ReleaseFailingInteractor(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.close_calls = 0
            self.delete_later_calls = 0
            self.fail_release = True
            self._closed = False
            self._RenderWindow = object()
            self.iren = object()
            self.renderer = object()

        def close(self) -> bool:
            self.close_calls += 1
            self._closed = True
            self._RenderWindow = None
            self.iren = None
            self.renderer = None
            return True

        def deleteLater(self) -> None:
            self.delete_later_calls += 1
            if self.fail_release:
                raise RuntimeError("wrapper release failed")

    plotter = _ReleaseFailingInteractor(widget.plot_container)
    widget.plot_layout.addWidget(plotter)
    widget.plotter_widget = plotter

    assert widget.finalize_native_render_resources() is False
    cleanup_state = widget._native_interactor_cleanup_state
    assert cleanup_state.finalized is False
    assert cleanup_state.close_attempts == 1
    assert cleanup_state.close_successes == 1
    assert "wrapper release failed" in cleanup_state.failure
    assert widget.plotter_widget is plotter

    plotter.fail_release = False
    assert widget.finalize_native_render_resources() is True
    assert plotter.close_calls == 1
    assert plotter.delete_later_calls == 2
    assert cleanup_state.finalized is True
    assert cleanup_state.finalize_count == 1
    assert cleanup_state.close_attempts == 1
    assert cleanup_state.close_successes == 1
    assert cleanup_state.failure == ""
    assert widget.plotter_widget is None
