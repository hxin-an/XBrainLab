"""Contract coverage for publication-backed VisualizationPanel behavior."""

from __future__ import annotations

import threading
from dataclasses import replace
from time import sleep
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from matplotlib.figure import Figure
from PyQt6.QtCore import QRunnable, QThreadPool
from PyQt6.QtWidgets import QLabel, QWidget

from XBrainLab.backend.application import (
    ApplicationViewPublication,
    SaliencyCrossFoldIdentity,
    SaliencyPlanIdentity,
    SaliencyRenderData,
    SaliencyRenderPublication,
    SaliencyRenderRequest,
    SaliencyRunIdentity,
)
from XBrainLab.backend.application.results import ChangedState, CommandResult
from XBrainLab.backend.application.saliency_render import (
    normalized_saliency_render_publication,
)
from XBrainLab.backend.application.state import (
    ApplicationStateSnapshot,
    SaliencyClassCoverageSnapshot,
    SaliencyMethodCoverageSnapshot,
    SaliencyRunCoverageSnapshot,
    VisualizationStateSnapshot,
)
from XBrainLab.backend.application.view_publication import ApplicationViewStore
from XBrainLab.backend.training_state_contract import TrainingReadBoundary
from XBrainLab.backend.utils.observer import Observable


def _complete_coverage(method: str = "Gradient") -> SaliencyMethodCoverageSnapshot:
    return SaliencyMethodCoverageSnapshot(
        method=method,
        available=True,
        complete=True,
        classes=[
            SaliencyClassCoverageSnapshot(
                class_index=0,
                display_name="left",
                event_code=0,
                available=True,
            ),
        ],
    )


def _visualization_result(
    *run_coverages: SaliencyRunCoverageSnapshot,
    cross_fold_choices: tuple[dict[str, object], ...] = (),
) -> CommandResult:
    state = replace(
        ApplicationStateSnapshot.empty(),
        visualization=VisualizationStateSnapshot(
            saliency_available=any(
                method.available for run in run_coverages for method in run.methods
            ),
            saliency_coverage=list(run_coverages),
        ),
    )
    return CommandResult.success_result(
        command_name="visualize",
        message="Visualization ready.",
        state=state,
        changed_state=ChangedState(),
        diagnostics={
            "payload_type": "visualization_summary",
            "available": True,
            "plot_views_available": True,
            "saliency_cross_fold_choices": list(cross_fold_choices),
        },
    )


def _run_coverage(
    *,
    plan_index: int,
    run_index: int,
    model_name: str,
    run_name: str = "",
    methods: tuple[SaliencyMethodCoverageSnapshot, ...] | None = None,
) -> SaliencyRunCoverageSnapshot:
    return SaliencyRunCoverageSnapshot(
        plan_index=plan_index,
        run_index=run_index,
        model_name=model_name,
        run_name=run_name,
        methods=list(methods or (_complete_coverage(),)),
    )


def _publish_panel_state(
    panel,
    result: CommandResult,
    *,
    publication: ApplicationViewPublication | None = None,
) -> ApplicationViewPublication:
    """Install one exact application publication and populate its selectors."""
    assert isinstance(result.state, ApplicationStateSnapshot)
    publication = (
        publication
        or ApplicationViewStore(
            result.state,
            TrainingReadBoundary.no_trainer(),
        ).read()
    )
    assert panel._accept_application_publication(publication) is True
    panel.last_application_query = result
    panel._application_summary_dirty = False
    with patch.object(panel, "on_update"):
        panel.refresh_combos()
    return publication


def _select_run(panel, run_identity: SaliencyRunIdentity) -> None:
    plan_index = next(
        (
            index
            for index in range(1, panel.plan_combo.count())
            if panel.plan_combo.itemData(index) == run_identity.plan
        ),
        -1,
    )
    assert plan_index >= 1
    panel.plan_combo.blockSignals(True)
    panel.plan_combo.setCurrentIndex(plan_index)
    panel.plan_combo.blockSignals(False)
    with patch.object(panel, "on_update"):
        panel.on_plan_changed(
            panel.plan_combo.currentText(),
            preferred_run=run_identity,
        )
    assert panel.run_combo.currentData() == run_identity


def _render_data(method: str = "Gradient") -> SaliencyRenderData:
    return SaliencyRenderData(
        method=method,
        saliency_by_class={0: np.ones((1, 2, 3))},
        class_map=((0, "left"),),
        event_ids={"left": 0},
        channel_names=("C3", "C4"),
        channel_positions=((-0.04, 0.0, 0.08), (0.04, 0.0, 0.08)),
        sfreq=128.0,
        tmin=0.0,
    )


def _install_owned_render_runtime(runtime):
    """Give a focused UI runtime the current backend-owned render contract."""
    operation_phases: dict[str, str] = {}
    next_operation = 0

    def begin(_request):
        nonlocal next_operation
        next_operation += 1
        operation_id = f"coverage-render-{next_operation}"
        operation_phases[operation_id] = "running"
        return SimpleNamespace(operation_id=operation_id)

    def prepare_variants(operation_id, request, *, include_normalized):
        raw = runtime.get_saliency_render(replace(request, normalize=False))
        if not isinstance(raw, SaliencyRenderPublication):
            return raw, None
        raw = replace(raw, operation_id=operation_id)
        normalized = (
            normalized_saliency_render_publication(raw) if include_normalized else None
        )
        return raw, normalized

    def snapshot(operation_id):
        phase = operation_phases.get(operation_id, "running")
        return SimpleNamespace(
            phase=phase,
            completed=None,
            total=None,
            indeterminate=True,
            cancel_requested=False,
            cancellable=phase not in {"completed", "cancelled", "failed"},
            stage="Rendering saliency canvas",
        )

    def finish(operation_id, phase, *, message=""):
        del message
        operation_phases[operation_id] = phase

    def cancel(operation_id):
        operation_phases[operation_id] = "cancelled"
        return True

    runtime.begin_saliency_render = MagicMock(side_effect=begin)
    runtime.prepare_saliency_render_variants = MagicMock(side_effect=prepare_variants)
    runtime.enter_saliency_render_commit = MagicMock(return_value=True)
    runtime.finish_saliency_render = MagicMock(side_effect=finish)
    runtime.get_owned_operation = MagicMock(side_effect=snapshot)
    runtime.cancel_owned_operation = MagicMock(side_effect=cancel)
    return runtime


def _prepare_variants_from(renderer):
    """Adapt an existing detached-render fixture to current owned preparation."""

    def prepare(
        panel,
        operation_id,
        request,
        *,
        include_normalized,
        **kwargs,
    ):
        raw = renderer(panel, replace(request, normalize=False), **kwargs)
        if not isinstance(raw, SaliencyRenderPublication):
            return raw, None
        raw = replace(raw, operation_id=operation_id)
        normalized = (
            normalized_saliency_render_publication(raw) if include_normalized else None
        )
        return raw, normalized

    return prepare


def _make_panel(
    qtbot,
    *,
    training_controller=None,
    preprocess_controller=None,
    parent=None,
):
    """Create a panel whose controller exposes no live training objects."""
    del training_controller, preprocess_controller
    controller = Observable()
    application_port = Observable()
    runtime_port = cast(Any, application_port)
    runtime_port.get_view_publication = MagicMock(return_value=None)
    runtime_port.execute = MagicMock(return_value=None)
    runtime_port.get_saliency_render = MagicMock(return_value=None)
    _install_owned_render_runtime(runtime_port)

    def _widget_factory(parent=None):
        widget = cast(Any, QWidget(parent))
        widget.class_selected = MagicMock()
        widget.select_class_key = MagicMock()
        widget.show_error = MagicMock()
        widget.show_message = MagicMock()
        widget.set_saliency_coverage = MagicMock()
        widget.set_post_training_saliency_status = MagicMock()
        widget.update_plot = MagicMock()
        widget.invalidate_render_publication = MagicMock()
        widget.begin_render_shutdown = MagicMock()
        widget.cancel_render_shutdown = MagicMock()
        widget.native_render_work_idle = MagicMock(return_value=True)
        widget.finalize_native_render_resources = MagicMock(return_value=True)
        widget.native_render_resources_finalized = MagicMock(return_value=True)
        widget.repaint = MagicMock()
        return widget

    class _SidebarStub(QWidget):
        def __init__(self, *args, **kwargs):
            super().__init__()
            self.update_info = MagicMock()

    with (
        patch(
            "XBrainLab.ui.panels.visualization.panel.ControlSidebar",
            _SidebarStub,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.panel.SaliencyMapWidget",
            side_effect=_widget_factory,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.panel.SaliencySpectrogramWidget",
            side_effect=_widget_factory,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.panel.SaliencyTopographicMapWidget",
            side_effect=_widget_factory,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.panel.Saliency3DPlotWidget",
            side_effect=_widget_factory,
        ),
    ):
        from XBrainLab.ui.panels.visualization.panel import VisualizationPanel

        panel = VisualizationPanel(
            parent=parent,
            query_port=runtime_port,
            publication_port=runtime_port,
            action_port=runtime_port,
        )
        qtbot.addWidget(panel)
    return panel, controller


def _make_real_saliency_panel(qtbot, *, application_runtime=None, parent=None):
    class _SidebarStub(QWidget):
        def __init__(self, *args, **kwargs):
            super().__init__()
            self.update_info = MagicMock()

    with patch(
        "XBrainLab.ui.panels.visualization.panel.ControlSidebar",
        _SidebarStub,
    ):
        from XBrainLab.ui.panels.visualization.panel import VisualizationPanel

        runtime = application_runtime
        if runtime is None:
            runtime = cast(Any, Observable())
            runtime.get_view_publication = MagicMock(return_value=None)
            runtime.execute = MagicMock(return_value=None)
            runtime.get_saliency_render = MagicMock(return_value=None)
        _install_owned_render_runtime(runtime)
        publication_port = runtime if isinstance(runtime, Observable) else Observable()
        panel = VisualizationPanel(
            parent=parent,
            query_port=runtime,
            publication_port=publication_port,
            action_port=runtime,
        )
        qtbot.addWidget(panel)
    return panel


@pytest.fixture
def panel_and_controller(qtbot):
    return _make_panel(qtbot)


def _current_widget(panel) -> Any:
    widget = panel.tabs.currentWidget()
    assert widget is not None
    return cast(Any, widget)


def test_overview_class_activation_invalidates_existing_native_binding(qtbot):
    """Changing display mode/class must rerender an already bound canvas."""
    coverage = SaliencyMethodCoverageSnapshot(
        method="Gradient",
        available=True,
        complete=True,
        classes=[
            SaliencyClassCoverageSnapshot(
                class_index=0,
                display_name="motor",
                event_code=10,
                store_key="left-key",
                available=True,
            ),
            SaliencyClassCoverageSnapshot(
                class_index=1,
                display_name="motor",
                event_code=20,
                store_key="right-key",
                available=True,
            ),
        ],
    )
    result = _visualization_result(
        _run_coverage(
            plan_index=0,
            run_index=0,
            model_name="EEGNet",
            methods=(coverage,),
        )
    )
    panel = _make_real_saliency_panel(qtbot)
    publication = _publish_panel_state(panel, result)
    run_identity = SaliencyRunIdentity(
        plan=SaliencyPlanIdentity(plan_index=0),
        run_index=0,
    )
    _select_run(panel, run_identity)
    render_data = SaliencyRenderData(
        method="Gradient",
        saliency_by_class={
            "left-key": np.ones((1, 2, 3)),
            "right-key": np.ones((1, 2, 3)) * 2,
        },
        class_map=(("left-key", "motor"), ("right-key", "motor")),
        event_ids={"motor": 10},
        channel_names=("C3", "C4"),
        channel_positions=((-0.04, 0.0, 0.08), (0.04, 0.0, 0.08)),
        sfreq=128.0,
        tmin=-0.2,
    )
    base_render = SaliencyRenderPublication(
        request=SaliencyRenderRequest(
            publication_generation=publication.generation,
            run=run_identity,
            method="Gradient",
            view="channel_time",
        ),
        generation=publication.generation,
        training_generation=1,
        data=render_data,
    )
    panel.tab_map.update_plot = MagicMock()

    def render_for(request):
        return replace(base_render, request=request)

    def cancel_binding(widget):
        panel._native_render_bindings.pop(widget, None)
        return True

    with (
        patch.object(panel, "_saliency_render_is_cached", return_value=True),
        patch.object(
            panel,
            "_saliency_render_publication",
            side_effect=render_for,
        ),
        patch.object(panel, "_bind_native_render_terminal"),
        patch.object(
            panel,
            "_cancel_native_render_binding",
            side_effect=cancel_binding,
        ) as cancel,
    ):
        panel.on_update()
        first_publication = panel.tab_map.update_plot.call_args.args[0]
        panel._native_render_bindings[panel.tab_map] = (
            1,
            publication.generation,
            "render-overview",
            first_publication,
            (False, False, "all", "left-key"),
        )

        panel._open_saliency_class_detail("right-key")

    assert cancel.call_count == 1
    assert panel.tab_map.update_plot.call_count == 2
    assert panel.tab_map.update_plot.call_args.kwargs == {
        "selected_label_key": "right-key",
        "display_mode": "single",
    }
    assert panel.saliency_view_mode.currentData() == "single"
    assert panel.saliency_class_combo.currentData() == "right-key"


@pytest.mark.parametrize(
    "view",
    ("channel_time", "topographic_map", "three_dimensional"),
)
def test_normalized_render_worker_claims_the_raw_operation_identity(view) -> None:
    from XBrainLab.backend.application.owned_work import (
        OwnedWorkPhase,
        OwnedWorkRegistry,
    )
    from XBrainLab.backend.application.saliency_render_work import (
        SaliencyRenderWorkController,
    )
    from XBrainLab.ui.panels.visualization.panel import (
        VisualizationPanel,
        _SaliencyRenderTask,
    )

    registry = OwnedWorkRegistry()

    def publish(request: SaliencyRenderRequest) -> SaliencyRenderPublication:
        return SaliencyRenderPublication(
            request=request,
            generation=request.publication_generation,
            training_generation=8,
            data=_render_data(request.method),
        )

    controller = SaliencyRenderWorkController(
        registry=registry,
        publish=publish,
    )

    class _OwnedRuntime:
        begin_saliency_render = controller.begin
        prepare_saliency_render_variants = controller.prepare_variants

    normalized_request = SaliencyRenderRequest(
        publication_generation=7,
        run=SaliencyRunIdentity(
            plan=SaliencyPlanIdentity(plan_index=0),
            run_index=1,
        ),
        method="Gradient",
        normalize=True,
        view=cast(Any, view),
    )
    raw_request = replace(normalized_request, normalize=False)
    operation = controller.begin(raw_request)
    task = _SaliencyRenderTask(
        request=normalized_request,
        needs_normalized_variant=True,
        operation_id=operation.operation_id,
    )

    returned_task, raw_publication, normalized_publication = (
        VisualizationPanel._load_saliency_render(_OwnedRuntime(), task)
    )

    assert returned_task == task
    assert raw_publication.request == raw_request
    assert raw_publication.operation_id == operation.operation_id
    assert normalized_publication is not None
    assert normalized_publication.request == normalized_request
    assert normalized_publication.operation_id == operation.operation_id
    assert registry.snapshot(operation.operation_id).phase is OwnedWorkPhase.RUNNING


def test_publication_runtime_composes_through_active_real_map_view(qtbot):
    result = _visualization_result(
        _run_coverage(plan_index=0, run_index=0, model_name="EEGNet"),
    )
    assert isinstance(result.state, ApplicationStateSnapshot)
    publication = ApplicationViewStore(
        result.state,
        TrainingReadBoundary.no_trainer(),
    ).read()
    render_requests: list[SaliencyRenderRequest] = []

    class _PublicationRuntime:
        def execute(self, command, *, expected_publication_generation=None):
            assert expected_publication_generation in {None, publication.generation}
            return CommandResult.success_result(
                command_name=command.name.value,
                message="Native saliency stress fixture ready.",
                state=result.state,
                changed_state=ChangedState(),
            )

        def get_view_publication(self):
            return publication

        def get_saliency_render(self, request):
            render_requests.append(request)
            return SaliencyRenderPublication(
                request=request,
                generation=publication.generation,
                training_generation=1,
                data=_render_data(),
            )

    runtime = _PublicationRuntime()
    panel = _make_real_saliency_panel(qtbot, application_runtime=runtime)

    panel.on_update()
    panel.refresh_combos()
    previous_figure = panel.tab_map.fig
    previous_canvas = panel.tab_map.canvas
    panel.on_update()

    qtbot.waitUntil(
        lambda: (
            panel.tab_map.native_render_work_idle()
            and panel.tab_map.fig is not None
            and panel.tab_map.canvas is not None
            and panel.tab_map.fig is not previous_figure
            and panel.tab_map.canvas is not previous_canvas
            and bool(panel.tab_map.fig.axes)
            and panel.tab_map.error_label.isHidden()
        ),
        timeout=5000,
    )

    assert render_requests
    assert render_requests[-1].publication_generation == publication.generation
    assert render_requests[-1].run == panel.run_combo.currentData()
    assert panel.tabs.currentWidget() is panel.tab_map


def test_real_panel_close_ignores_global_pool_saturation_before_submission(
    qtbot,
    monkeypatch,
):
    from XBrainLab.ui.main_window import MainWindow
    from XBrainLab.ui.panels.visualization.saliency_views.map_view import (
        SaliencyMapWidget,
    )

    result = _visualization_result(
        _run_coverage(plan_index=0, run_index=0, model_name="EEGNet"),
    )
    assert isinstance(result.state, ApplicationStateSnapshot)
    publication = ApplicationViewStore(
        result.state,
        TrainingReadBoundary.no_trainer(),
    ).read()
    render_publication = SaliencyRenderPublication(
        request=SaliencyRenderRequest(
            publication_generation=publication.generation,
            run=SaliencyRunIdentity(
                plan=SaliencyPlanIdentity(plan_index=0),
                run_index=0,
            ),
            method="Gradient",
        ),
        generation=publication.generation,
        training_generation=1,
        data=_render_data(),
    )
    render_requests: list[SaliencyRenderRequest] = []

    class _PublicationRuntime:
        def execute(self, command, *, expected_publication_generation=None):
            assert expected_publication_generation in {None, publication.generation}
            return CommandResult.success_result(
                command_name=command.name.value,
                message="Native saliency saturation fixture ready.",
                state=result.state,
                changed_state=ChangedState(),
            )

        def get_view_publication(self):
            return publication

        def get_saliency_render(self, request):
            render_requests.append(request)
            return replace(render_publication, request=request)

    global_started = threading.Event()
    global_release = threading.Event()
    global_finished = threading.Event()
    render_started = threading.Event()
    render_release = threading.Event()

    class _GlobalBlocker(QRunnable):
        def run(self) -> None:
            global_started.set()
            global_release.wait(timeout=5.0)
            global_finished.set()

    def render(_data, _absolute, *_display_options) -> Figure:
        render_started.set()
        assert render_release.wait(timeout=5.0)
        figure = Figure()
        figure.set_label("owned-pool-render")
        figure.add_subplot(111).plot([0, 1], [1, 0])
        return figure

    monkeypatch.setattr(SaliencyMapWidget, "_render_plot", staticmethod(render))
    pool = QThreadPool.globalInstance()
    assert pool is not None
    qtbot.waitUntil(lambda: pool.activeThreadCount() == 0, timeout=2000)
    previous_max_threads = pool.maxThreadCount()
    pool.setMaxThreadCount(1)

    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
    ):
        window = MainWindow(MagicMock())
    qtbot.addWidget(window)
    panel = _make_real_saliency_panel(
        qtbot,
        application_runtime=_PublicationRuntime(),
        parent=window,
    )
    cast(Any, window).visualization_panel = panel
    _publish_panel_state(panel, result, publication=publication)
    window.show()
    blocker = _GlobalBlocker()
    pool.start(blocker)

    try:
        qtbot.waitUntil(global_started.is_set, timeout=1000)
        panel.on_update()
        qtbot.waitUntil(render_started.is_set, timeout=1000)
        assert render_requests
        assert pool.activeThreadCount() == 1

        with (
            patch.object(
                window,
                "_ensure_shutdown_fence_for_close",
                return_value=True,
            ),
            patch.object(window, "_stop_training_for_close", return_value=True),
            patch.object(
                window.window_geometry,
                "persist_before_close",
                return_value=True,
            ),
        ):
            window.close()
            assert window.isVisible()
            assert window._closing_in_progress is True
            assert global_finished.is_set() is False

            render_release.set()
            qtbot.waitUntil(lambda: not window.isVisible(), timeout=5000)

        assert global_finished.is_set() is False
        assert pool.activeThreadCount() == 1
        assert panel.native_render_work_idle() is True
        assert panel.native_render_resources_finalized() is True
    finally:
        render_release.set()
        global_release.set()
        qtbot.waitUntil(global_finished.is_set, timeout=3000)
        qtbot.waitUntil(panel.native_render_work_idle, timeout=3000)
        if not panel.native_render_resources_finalized():
            panel.begin_native_render_shutdown()
            assert panel.finalize_native_render_resources() is True
        pool.setMaxThreadCount(previous_max_threads)
        window.hide()


def test_tab_switch_invalidates_previous_saliency_view(panel_and_controller):
    panel, _controller = panel_and_controller
    previous = cast(Any, panel.tab_map)

    with patch.object(panel, "on_update"):
        panel.tabs.setCurrentIndex(1)

    previous.invalidate_render_publication.assert_called_once_with()
    assert panel._last_active_saliency_view is panel.tab_spectro


def test_panel_shutdown_fences_all_saliency_views(panel_and_controller):
    panel, _controller = panel_and_controller
    views = (panel.tab_map, panel.tab_spectro, panel.tab_topo, panel.tab_3d)

    panel.begin_native_render_shutdown()

    for view in views:
        cast(Any, view).begin_render_shutdown.assert_called_once_with()
    cast(Any, panel.tab_topo).native_render_work_idle.return_value = False
    assert panel.native_render_work_idle() is False
    cast(Any, panel.tab_topo).native_render_work_idle.return_value = True
    assert panel.native_render_work_idle() is True
    panel.cancel_native_render_shutdown()
    for view in views:
        cast(Any, view).cancel_render_shutdown.assert_called_once_with()


def test_panel_cleanup_fences_late_saliency_worker_callbacks(panel_and_controller):
    panel, _controller = panel_and_controller
    views = (panel.tab_map, panel.tab_spectro, panel.tab_topo, panel.tab_3d)

    panel.cleanup()

    assert panel._native_render_shutdown_requested is True
    assert panel._saliency_render_pending_task is None
    for view in views:
        cast(Any, view).begin_render_shutdown.assert_called_once_with()


def test_saliency_worker_ownership_lasts_until_finished_callback(
    panel_and_controller,
):
    from XBrainLab.ui.panels.visualization.panel import _SaliencyRenderTask

    panel, _controller = panel_and_controller
    run = SaliencyRunIdentity(
        plan=SaliencyPlanIdentity(plan_index=0),
        run_index=0,
    )
    active = _SaliencyRenderTask(
        request=SaliencyRenderRequest(
            publication_generation=1,
            run=run,
            method="Gradient",
        ),
        needs_normalized_variant=False,
    )
    stale_pending = replace(
        active,
        request=replace(active.request, method="SmoothGrad"),
    )
    worker = MagicMock()
    worker.is_alive.return_value = False
    panel._saliency_render_worker = worker
    panel._saliency_render_active_task = active
    panel._saliency_render_pending_task = stale_pending

    assert panel.native_render_work_idle() is False

    # Returning A while A's Qt callbacks are queued must clear stale B rather
    # than replace the still-owned worker or launch B after A finishes.
    panel._request_saliency_render(active)

    assert panel._saliency_render_worker is worker
    assert panel._saliency_render_pending_task is None
    worker.start.assert_not_called()

    panel._on_saliency_render_finished(worker)

    assert panel._saliency_render_worker is None
    assert panel.native_render_work_idle() is True


def test_saliency_worker_requeues_active_task_after_its_result_was_discarded(
    panel_and_controller,
):
    from XBrainLab.ui.panels.visualization.panel import _SaliencyRenderTask

    panel, _controller = panel_and_controller
    run = SaliencyRunIdentity(
        plan=SaliencyPlanIdentity(plan_index=0),
        run_index=0,
    )
    active = _SaliencyRenderTask(
        request=SaliencyRenderRequest(
            publication_generation=1,
            run=run,
            method="Gradient",
        ),
        needs_normalized_variant=False,
    )
    worker = MagicMock()
    panel._saliency_render_worker = worker
    panel._saliency_render_active_task = active
    different_selection = replace(
        active,
        request=replace(active.request, method="SmoothGrad"),
    )
    publication = SaliencyRenderPublication(
        request=active.request,
        generation=active.request.publication_generation,
        training_generation=1,
        data=_render_data(),
    )

    with patch.object(
        panel,
        "_current_saliency_render_task",
        return_value=different_selection,
    ):
        panel._on_saliency_render_ready(worker, (active, publication, None))

    assert panel._saliency_render_result_seen is True
    assert not panel._saliency_render_cache

    # A completed while B was selected, so A's result was intentionally
    # discarded. Returning to A before its finished signal must queue a fresh
    # A request instead of leaving the view on a permanent loading message.
    panel._request_saliency_render(active)

    assert panel._saliency_render_pending_task == active

    with patch.object(panel, "_request_saliency_render") as request_render:
        panel._on_saliency_render_finished(worker)

    request_render.assert_called_once_with(active)


def test_saliency_worker_terminal_for_current_result_avoids_duplicate_render(
    panel_and_controller,
):
    from XBrainLab.ui.panels.visualization.panel import _SaliencyRenderTask

    panel, _controller = panel_and_controller
    active = _SaliencyRenderTask(
        request=SaliencyRenderRequest(
            publication_generation=1,
            run=SaliencyRunIdentity(
                plan=SaliencyPlanIdentity(plan_index=0),
                run_index=0,
            ),
            method="Gradient",
        ),
        needs_normalized_variant=False,
    )
    publication = SaliencyRenderPublication(
        request=active.request,
        generation=active.request.publication_generation,
        training_generation=1,
        data=_render_data(),
    )
    worker = MagicMock()
    panel._saliency_render_worker = worker
    panel._saliency_render_active_task = active

    with (
        patch.object(
            panel,
            "_current_saliency_render_task",
            return_value=active,
        ),
        patch.object(panel, "on_update"),
    ):
        panel._on_saliency_render_ready(worker, (active, publication, None))

    assert panel._saliency_render_cache[False] == publication
    assert panel._saliency_render_result_seen is False

    panel._request_saliency_render(active)

    assert panel._saliency_render_pending_task is None


def test_saliency_cache_miss_never_queries_backend_on_gui_thread(
    panel_and_controller,
):
    panel, _controller = panel_and_controller
    request = SaliencyRenderRequest(
        publication_generation=1,
        run=SaliencyRunIdentity(
            plan=SaliencyPlanIdentity(plan_index=0),
            run_index=0,
        ),
        method="Gradient",
    )

    prepare_variants = panel._query_port.prepare_saliency_render_variants
    prepare_variants.reset_mock()

    publication = panel._saliency_render_publication(request)

    assert publication is None
    prepare_variants.assert_not_called()


def test_panel_native_resource_finalizer_is_idempotent(panel_and_controller):
    panel, _controller = panel_and_controller
    views = (panel.tab_map, panel.tab_spectro, panel.tab_topo, panel.tab_3d)

    assert panel.native_render_resources_finalized() is False
    assert panel.finalize_native_render_resources() is True
    assert panel.finalize_native_render_resources() is True
    assert panel.native_render_resources_finalized() is True

    for view in views:
        cast(Any, view).finalize_native_render_resources.assert_called_once_with()


def test_real_panel_propagates_3d_native_close_failure_until_verified(qtbot):
    panel = _make_real_saliency_panel(qtbot)

    class _RecoverableInteractor(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.fail_close = True
            self.close_calls = 0
            self.delete_later_calls = 0
            self._closed = False
            self._RenderWindow = object()
            self.iren = object()
            self.renderer = object()

        def close(self) -> bool:
            self.close_calls += 1
            if self.fail_close:
                raise RuntimeError("recoverable native close failure")
            self._closed = True
            self._RenderWindow = None
            self.iren = None
            self.renderer = None
            return True

        def deleteLater(self) -> None:
            self.delete_later_calls += 1

    plotter = _RecoverableInteractor(panel.tab_3d.plot_container)
    panel.tab_3d.plot_layout.addWidget(plotter)
    panel.tab_3d.plotter_widget = plotter
    panel.begin_native_render_shutdown()

    assert panel.native_render_work_idle() is True
    assert panel.finalize_native_render_resources() is False
    assert panel.native_render_resources_finalized() is False
    assert panel.tab_3d.plotter_widget is plotter
    assert plotter.delete_later_calls == 0

    plotter.fail_close = False
    assert panel.finalize_native_render_resources() is True
    assert panel.native_render_resources_finalized() is True
    assert panel.tab_3d.plotter_widget is None
    assert plotter.close_calls == 2
    assert plotter.delete_later_calls == 1
    cleanup_state = panel.tab_3d._native_interactor_cleanup_state
    assert cleanup_state.finalized is True
    assert cleanup_state.finalize_count == 1
    assert cleanup_state.close_attempts == 2
    assert cleanup_state.close_successes == 1
    QWidget.deleteLater(plotter)


def test_cancelled_shutdown_resubmits_active_tab_with_current_publication(
    panel_and_controller,
):
    panel, _controller = panel_and_controller
    publication = MagicMock(usable=True)
    panel._application_view_publication = publication
    views = (panel.tab_map, panel.tab_spectro, panel.tab_topo, panel.tab_3d)

    with patch.object(panel, "on_update") as on_update:
        panel.begin_native_render_shutdown()
        panel.cancel_native_render_shutdown()

    assert panel._application_view_publication is publication
    assert panel.tabs.currentWidget() is panel.tab_map
    for view in views:
        cast(Any, view).cancel_render_shutdown.assert_called_once_with()
    on_update.assert_called_once_with()


def test_cancelled_shutdown_resubmits_2d_publication_to_true_worker(
    qtbot,
    monkeypatch,
):
    from XBrainLab.ui.panels.visualization.saliency_views.map_view import (
        SaliencyMapWidget,
    )

    panel = _make_real_saliency_panel(qtbot)
    result = _visualization_result(
        _run_coverage(plan_index=0, run_index=0, model_name="EEGNet"),
    )
    publication = _publish_panel_state(panel, result)
    run_identity = cast(SaliencyRunIdentity, panel.run_combo.currentData())
    render_publication = SaliencyRenderPublication(
        request=SaliencyRenderRequest(
            publication_generation=publication.generation,
            run=run_identity,
            method="Gradient",
            view="channel_time",
        ),
        generation=publication.generation,
        training_generation=1,
        data=_render_data(),
    )
    first_started = threading.Event()
    release_first = threading.Event()
    worker_threads: list[int] = []
    render_count = 0

    def render(_data, _absolute, *_display_options) -> Figure:
        nonlocal render_count
        render_count += 1
        worker_threads.append(threading.get_ident())
        figure = Figure()
        figure.set_label(f"resumed-2d-{render_count}")
        figure.add_subplot(111).plot([0, 1], [render_count, 0])
        if render_count == 1:
            first_started.set()
            assert release_first.wait(timeout=3.0)
        return figure

    monkeypatch.setattr(SaliencyMapWidget, "_render_plot", staticmethod(render))
    with patch(
        "XBrainLab.ui.panels.visualization.panel.prepare_saliency_render_variants_operation",
        side_effect=_prepare_variants_from(
            lambda _panel, _request, **_kwargs: render_publication
        ),
    ):
        panel.on_update()
        qtbot.waitUntil(first_started.is_set, timeout=2000)
        panel.begin_native_render_shutdown()
        release_first.set()
        qtbot.waitUntil(panel.native_render_work_idle, timeout=3000)

        panel.cancel_native_render_shutdown()
        qtbot.waitUntil(
            lambda: (
                panel.tab_map.fig is not None
                and panel.tab_map.fig.get_label() == "resumed-2d-2"
                and panel.native_render_work_idle()
            ),
            timeout=3000,
        )

    assert render_count == 2
    assert panel.tab_map.error_label.isHidden()
    assert all(thread_id != threading.get_ident() for thread_id in worker_threads)


def test_cancelled_shutdown_resubmits_3d_publication_to_true_worker(
    qtbot,
    monkeypatch,
):
    from XBrainLab.ui.panels.visualization.saliency_views import plot_3d_view

    panel = _make_real_saliency_panel(qtbot)
    result = _visualization_result(
        _run_coverage(plan_index=0, run_index=0, model_name="EEGNet"),
    )
    publication = _publish_panel_state(panel, result)
    run_identity = cast(SaliencyRunIdentity, panel.run_combo.currentData())
    render_publication = SaliencyRenderPublication(
        request=SaliencyRenderRequest(
            publication_generation=publication.generation,
            run=run_identity,
            method="Gradient",
            view="three_dimensional",
        ),
        generation=publication.generation,
        training_generation=1,
        data=_render_data(),
    )
    first_started = threading.Event()
    release_first = threading.Event()
    worker_threads: list[int] = []
    prepare_count = 0

    class _FakeInteractor(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.interactor = self

        def Initialize(self) -> None:
            return

    def prepare_engine(*_args, **_kwargs):
        nonlocal prepare_count
        prepare_count += 1
        worker_threads.append(threading.get_ident())
        if prepare_count == 1:
            first_started.set()
            assert release_first.wait(timeout=3.0)
        return object(), 2

    monkeypatch.setattr(
        plot_3d_view.Saliency3D,
        "prepare_engine",
        staticmethod(prepare_engine),
    )
    monkeypatch.setattr(
        plot_3d_view.Saliency3DPlotWidget,
        "_interactive_3d_runtime_available",
        staticmethod(lambda: (True, "")),
    )
    monkeypatch.setattr(plot_3d_view.pyvistaqt, "QtInteractor", _FakeInteractor)
    monkeypatch.setattr(panel.tab_3d, "_do_3d_plot", MagicMock())
    with patch.object(panel, "on_update"):
        panel.tabs.setCurrentIndex(3)

    with patch(
        "XBrainLab.ui.panels.visualization.panel.prepare_saliency_render_variants_operation",
        side_effect=_prepare_variants_from(
            lambda _panel, _request, **_kwargs: render_publication
        ),
    ):
        panel.on_update()
        qtbot.waitUntil(first_started.is_set, timeout=2000)
        panel.begin_native_render_shutdown()
        release_first.set()
        qtbot.waitUntil(panel.native_render_work_idle, timeout=3000)

        panel.cancel_native_render_shutdown()
        qtbot.waitUntil(
            lambda: (
                isinstance(panel.tab_3d.plotter_widget, _FakeInteractor)
                and panel.native_render_work_idle()
            ),
            timeout=3000,
        )

    plot_widgets = []
    for index in range(panel.tab_3d.plot_layout.count()):
        item = panel.tab_3d.plot_layout.itemAt(index)
        if item is not None:
            plot_widgets.append(item.widget())
    assert prepare_count == 2
    assert panel.tab_3d.plotter_widget in plot_widgets
    assert not any(
        isinstance(widget, QLabel) and widget.text() == "Preparing 3D view..."
        for widget in plot_widgets
    )
    assert all(thread_id != threading.get_ident() for thread_id in worker_threads)


class TestRefreshCombos:
    def test_empty_publication_keeps_only_placeholder(self, panel_and_controller):
        panel, _controller = panel_and_controller

        publication = _publish_panel_state(panel, _visualization_result())

        assert publication.usable is True
        assert panel.plan_combo.count() == 1
        assert panel.plan_combo.itemText(0) == "Select a fold"
        assert panel.plan_combo.itemData(0) is None
        assert panel.run_combo.count() == 0
        assert panel._runs_by_plan == {}

    def test_populates_sorted_typed_plan_and_run_identities(
        self,
        panel_and_controller,
    ):
        panel, _controller = panel_and_controller
        result = _visualization_result(
            _run_coverage(
                plan_index=1,
                run_index=1,
                model_name="SCCNet",
                run_name="Repeat B",
            ),
            _run_coverage(
                plan_index=0,
                run_index=1,
                model_name="EEGNet",
                run_name="Repeat B",
            ),
            _run_coverage(
                plan_index=1,
                run_index=0,
                model_name="SCCNet",
                run_name="Repeat A",
            ),
            _run_coverage(
                plan_index=0,
                run_index=0,
                model_name="EEGNet",
                run_name="Repeat A",
            ),
        )

        _publish_panel_state(panel, result)

        plan_zero = SaliencyPlanIdentity(plan_index=0)
        plan_one = SaliencyPlanIdentity(plan_index=1)
        assert [
            panel.plan_combo.itemText(index)
            for index in range(panel.plan_combo.count())
        ] == ["Select a fold", "Fold 1 (EEGNet)", "Fold 2 (SCCNet)"]
        assert panel.plan_combo.itemData(1) == plan_zero
        assert panel.plan_combo.itemData(2) == plan_one
        assert isinstance(panel.plan_combo.itemData(1), SaliencyPlanIdentity)
        assert [
            panel.run_combo.itemData(index) for index in range(panel.run_combo.count())
        ] == [
            SaliencyRunIdentity(plan=plan_zero, run_index=0),
            SaliencyRunIdentity(plan=plan_zero, run_index=1),
        ]
        assert [
            panel.run_combo.itemText(index) for index in range(panel.run_combo.count())
        ] == ["Run 1", "Run 2"]

        _select_run(
            panel,
            SaliencyRunIdentity(plan=plan_one, run_index=1),
        )

        assert [
            panel.run_combo.itemData(index) for index in range(panel.run_combo.count())
        ] == [
            SaliencyRunIdentity(plan=plan_one, run_index=0),
            SaliencyRunIdentity(plan=plan_one, run_index=1),
        ]
        assert panel.run_combo.findText("Average") == -1

    def test_backend_admitted_cross_fold_summary_preserves_exact_identity(
        self,
        panel_and_controller,
        qtbot,
    ):
        panel, _controller = panel_and_controller
        cross_choice = {
            "identity": {
                "members": [
                    {"plan_index": 0, "run_index": 0},
                    {"plan_index": 1, "run_index": 0},
                ]
            },
            "display_name": "All Folds",
            "run_label": "Run 1 (Summary)",
            "methods": ["Gradient"],
            "source_split": "test",
            "fold_count": 2,
            "classes": [
                {
                    "class_index": 0,
                    "display_name": "left",
                    "event_code": 769,
                    "store_key": 0,
                }
            ],
        }
        result = _visualization_result(
            _run_coverage(plan_index=0, run_index=0, model_name="EEGNet"),
            _run_coverage(plan_index=1, run_index=0, model_name="EEGNet"),
            cross_fold_choices=(cross_choice,),
        )
        publication = _publish_panel_state(panel, result)

        all_folds_index = panel.plan_combo.findText("All Folds")
        assert all_folds_index > 0
        panel.plan_combo.blockSignals(True)
        panel.plan_combo.setCurrentIndex(all_folds_index)
        panel.plan_combo.blockSignals(False)
        with patch.object(panel, "on_update"):
            panel.on_plan_changed(panel.plan_combo.currentText())

        identity = panel.run_combo.currentData()
        assert isinstance(identity, SaliencyCrossFoldIdentity)
        assert panel.run_combo.currentText() == "Run 1 (Summary)"
        assert [member.plan.plan_index for member in identity.members] == [0, 1]
        coverage = panel._published_coverage_for_selection()
        assert coverage is not None
        assert coverage["Gradient"].complete is True

        panel.normalize_check.blockSignals(True)
        panel.normalize_check.setChecked(True)
        panel.normalize_check.blockSignals(False)
        requests: list[SaliencyRenderRequest] = []
        render_thread_ids: list[int] = []
        gui_thread_id = threading.get_ident()

        def get_render(_panel, request, **_kwargs):
            requests.append(request)
            render_thread_ids.append(threading.get_ident())
            return SaliencyRenderPublication(
                request=request,
                generation=request.publication_generation,
                training_generation=8,
                data=replace(_render_data(), fold_count=2),
            )

        current_widget = _current_widget(panel)
        current_widget.update_plot.reset_mock()
        with patch(
            "XBrainLab.ui.panels.visualization.panel.prepare_saliency_render_variants_operation",
            side_effect=_prepare_variants_from(get_render),
        ):
            panel.on_update()
            qtbot.waitUntil(
                lambda: current_widget.update_plot.call_count == 1,
                timeout=2000,
            )

        assert requests == [
            SaliencyRenderRequest(
                publication_generation=publication.generation,
                run=identity,
                method="Gradient",
            )
        ]
        assert render_thread_ids and render_thread_ids[0] != gui_thread_id
        assert [
            panel.method_combo.itemText(index)
            for index in range(panel.method_combo.count())
        ] == ["Gradient"]
        rendered = current_widget.update_plot.call_args.args[0]
        assert rendered.request.normalize is True
        assert rendered.data.normalized is True
        assert rendered.data.fold_count == 2

    def test_cross_fold_normalize_during_first_load_reschedules_owned_variant(
        self,
        panel_and_controller,
        qtbot,
    ):
        panel, _controller = panel_and_controller
        cross_choice = {
            "identity": {
                "members": [
                    {"plan_index": 0, "run_index": 0},
                    {"plan_index": 1, "run_index": 0},
                ]
            },
            "display_name": "All Folds",
            "run_label": "Run 1 (Summary)",
            "methods": ["Gradient"],
            "source_split": "test",
            "fold_count": 2,
            "classes": [
                {
                    "class_index": 0,
                    "display_name": "left",
                    "event_code": 769,
                    "store_key": 0,
                }
            ],
        }
        result = _visualization_result(
            _run_coverage(plan_index=0, run_index=0, model_name="EEGNet"),
            _run_coverage(plan_index=1, run_index=0, model_name="EEGNet"),
            cross_fold_choices=(cross_choice,),
        )
        publication = _publish_panel_state(panel, result)
        panel.plan_combo.blockSignals(True)
        panel.plan_combo.setCurrentIndex(panel.plan_combo.findText("All Folds"))
        panel.plan_combo.blockSignals(False)
        with patch.object(panel, "on_update"):
            panel.on_plan_changed(panel.plan_combo.currentText())

        identity = panel.run_combo.currentData()
        assert isinstance(identity, SaliencyCrossFoldIdentity)
        render_started = threading.Event()
        release_render = threading.Event()
        requests: list[SaliencyRenderRequest] = []

        def get_render(_panel, request, **_kwargs):
            requests.append(request)
            render_started.set()
            assert release_render.wait(timeout=2.0)
            return SaliencyRenderPublication(
                request=request,
                generation=request.publication_generation,
                training_generation=8,
                data=replace(_render_data(), fold_count=2),
            )

        current_widget = _current_widget(panel)
        current_widget.update_plot.reset_mock()
        try:
            with patch(
                "XBrainLab.ui.panels.visualization.panel.prepare_saliency_render_variants_operation",
                side_effect=_prepare_variants_from(get_render),
            ):
                panel.on_update()
                assert render_started.wait(timeout=2.0)
                panel.normalize_check.setChecked(True)
                release_render.set()
                qtbot.waitUntil(
                    lambda: current_widget.update_plot.call_count == 1
                    and panel.native_render_work_idle(),
                    timeout=3000,
                )
        finally:
            release_render.set()

        expected_request = SaliencyRenderRequest(
            publication_generation=publication.generation,
            run=identity,
            method="Gradient",
        )
        assert requests == [expected_request, expected_request]
        assert panel._query_port.begin_saliency_render.call_count == 2
        rendered = current_widget.update_plot.call_args.args[0]
        assert rendered.request.normalize is True
        assert rendered.data.normalized is True

    def test_preserves_selection_by_identity_across_publication_generation(
        self,
        panel_and_controller,
    ):
        panel, _controller = panel_and_controller
        initial_result = _visualization_result(
            _run_coverage(
                plan_index=0,
                run_index=0,
                model_name="EEGNet",
                run_name="Initial 1",
            ),
            _run_coverage(
                plan_index=1,
                run_index=0,
                model_name="SCCNet",
                run_name="Initial 1",
            ),
            _run_coverage(
                plan_index=1,
                run_index=1,
                model_name="SCCNet",
                run_name="Initial 2",
            ),
        )
        assert isinstance(initial_result.state, ApplicationStateSnapshot)
        store = ApplicationViewStore(
            initial_result.state,
            TrainingReadBoundary.no_trainer(),
        )
        first_publication = store.read()
        _publish_panel_state(
            panel,
            initial_result,
            publication=first_publication,
        )
        selected_run = SaliencyRunIdentity(
            plan=SaliencyPlanIdentity(plan_index=1),
            run_index=1,
        )
        _select_run(panel, selected_run)

        updated_result = _visualization_result(
            _run_coverage(
                plan_index=1,
                run_index=1,
                model_name="SCCNet v2",
                run_name="Updated 2",
            ),
            _run_coverage(
                plan_index=0,
                run_index=0,
                model_name="EEGNet",
                run_name="Updated 1",
            ),
            _run_coverage(
                plan_index=1,
                run_index=0,
                model_name="SCCNet v2",
                run_name="Updated 1",
            ),
        )
        assert isinstance(updated_result.state, ApplicationStateSnapshot)
        second_publication = store.publish(
            updated_result.state,
            TrainingReadBoundary.no_trainer(),
        )
        assert second_publication.generation == first_publication.generation + 1

        _publish_panel_state(
            panel,
            updated_result,
            publication=second_publication,
        )

        assert panel.plan_combo.currentData() == selected_run.plan
        assert panel.plan_combo.currentText() == "Fold 2 (SCCNet v2)"
        assert panel.run_combo.currentData() == selected_run
        assert panel.run_combo.currentText() == "Run 2"

    @pytest.mark.parametrize(
        ("verified", "stale"),
        [(False, False), (True, True)],
        ids=("unverified", "stale"),
    )
    def test_rejects_unusable_publication_and_clears_controls(
        self,
        panel_and_controller,
        verified,
        stale,
    ):
        panel, _controller = panel_and_controller
        result = _visualization_result(
            _run_coverage(
                plan_index=0,
                run_index=0,
                model_name="EEGNet",
            ),
        )
        accepted = _publish_panel_state(panel, result)
        rejected = replace(accepted, verified=verified, stale=stale)
        assert rejected.usable is False

        assert panel._accept_application_publication(rejected) is False
        with patch.object(panel, "on_update"):
            panel.refresh_combos()

        assert panel._application_view_publication is None
        assert panel.plan_combo.count() == 1
        assert panel.plan_combo.itemText(0) == "Select a fold"
        assert panel.run_combo.count() == 0
        assert panel._runs_by_plan == {}
        for view in (panel.tab_map, panel.tab_spectro, panel.tab_topo, panel.tab_3d):
            cast(Any, view).invalidate_render_publication.assert_called_once_with()

    def test_rejects_publication_with_unreliable_state(
        self,
        panel_and_controller,
    ):
        panel, _controller = panel_and_controller
        result = _visualization_result(
            _run_coverage(
                plan_index=0,
                run_index=0,
                model_name="EEGNet",
            ),
        )
        accepted = _publish_panel_state(panel, result)
        unreliable = replace(
            accepted,
            state=replace(accepted.state, state_reliable=False),
        )
        assert unreliable.usable is True
        assert unreliable.state.state_reliable is False

        assert panel._accept_application_publication(unreliable) is False
        assert panel._application_view_publication is None


class TestOnPlanChanged:
    def test_populates_runs_only_for_typed_plan_identity(
        self,
        panel_and_controller,
    ):
        panel, _controller = panel_and_controller
        plan = SaliencyPlanIdentity(plan_index=0)
        result = _visualization_result(
            _run_coverage(
                plan_index=0,
                run_index=1,
                model_name="EEGNet",
            ),
            _run_coverage(
                plan_index=0,
                run_index=0,
                model_name="EEGNet",
            ),
        )
        _publish_panel_state(panel, result)

        panel.run_combo.clear()
        with patch.object(panel, "on_update"):
            panel.on_plan_changed("display text is not the identity")

        assert panel.plan_combo.currentData() == plan
        assert [
            panel.run_combo.itemData(index) for index in range(panel.run_combo.count())
        ] == [
            SaliencyRunIdentity(plan=plan, run_index=0),
            SaliencyRunIdentity(plan=plan, run_index=1),
        ]

    def test_placeholder_identity_clears_run_selection(
        self,
        panel_and_controller,
    ):
        panel, _controller = panel_and_controller
        _publish_panel_state(
            panel,
            _visualization_result(
                _run_coverage(
                    plan_index=0,
                    run_index=0,
                    model_name="EEGNet",
                ),
            ),
        )
        panel.plan_combo.blockSignals(True)
        panel.plan_combo.setCurrentIndex(0)
        panel.plan_combo.blockSignals(False)

        with patch.object(panel, "on_update"):
            panel.on_plan_changed("Fold 1 (EEGNet)")

        assert panel.plan_combo.currentData() is None
        assert panel.run_combo.count() == 0


class TestOnUpdate:
    def test_without_valid_selection_shows_placeholder(
        self,
        panel_and_controller,
    ):
        panel, _controller = panel_and_controller
        _publish_panel_state(panel, _visualization_result())
        current_widget = _current_widget(panel)
        current_widget.show_message.reset_mock()
        current_widget.show_error.reset_mock()
        current_widget.update_plot.reset_mock()

        panel.on_update()

        current_widget.update_plot.assert_not_called()
        current_widget.show_error.assert_not_called()
        current_widget.show_message.assert_called_once_with(
            "Select a fold and run to continue."
        )

    def test_without_run_identity_shows_placeholder(
        self,
        panel_and_controller,
    ):
        panel, _controller = panel_and_controller
        _publish_panel_state(
            panel,
            _visualization_result(
                _run_coverage(
                    plan_index=0,
                    run_index=0,
                    model_name="EEGNet",
                ),
            ),
        )
        panel.run_combo.blockSignals(True)
        panel.run_combo.clear()
        panel.run_combo.blockSignals(False)
        current_widget = _current_widget(panel)
        current_widget.show_message.reset_mock()
        current_widget.update_plot.reset_mock()

        panel.on_update()

        assert isinstance(panel.plan_combo.currentData(), SaliencyPlanIdentity)
        assert panel.run_combo.currentData() is None
        current_widget.update_plot.assert_not_called()
        current_widget.show_message.assert_called_once_with(
            "Select a fold and run to continue."
        )

    def test_missing_publication_with_typed_selection_fails_closed(
        self,
        panel_and_controller,
    ):
        panel, _controller = panel_and_controller
        _publish_panel_state(
            panel,
            _visualization_result(
                _run_coverage(
                    plan_index=0,
                    run_index=0,
                    model_name="EEGNet",
                ),
            ),
        )
        assert isinstance(panel.plan_combo.currentData(), SaliencyPlanIdentity)
        assert isinstance(panel.run_combo.currentData(), SaliencyRunIdentity)
        panel._application_view_publication = None
        current_widget = _current_widget(panel)
        current_widget.show_message.reset_mock()
        current_widget.update_plot.reset_mock()

        with patch(
            "XBrainLab.ui.panels.visualization.panel.begin_saliency_render_operation",
        ) as begin_render:
            panel.on_update()

        begin_render.assert_not_called()
        current_widget.set_saliency_coverage.assert_called_with(None)
        current_widget.update_plot.assert_not_called()
        current_widget.show_message.assert_called_once_with(
            "Saliency coverage is unavailable because application state could "
            "not be verified."
        )

    def test_unknown_typed_run_identity_fails_closed(
        self,
        panel_and_controller,
    ):
        panel, _controller = panel_and_controller
        _publish_panel_state(
            panel,
            _visualization_result(
                _run_coverage(
                    plan_index=0,
                    run_index=0,
                    model_name="EEGNet",
                ),
            ),
        )
        plan_identity = cast(
            SaliencyPlanIdentity,
            panel.plan_combo.currentData(),
        )
        stale_run = SaliencyRunIdentity(plan=plan_identity, run_index=99)
        panel.run_combo.blockSignals(True)
        panel.run_combo.clear()
        panel.run_combo.addItem("Stale run", stale_run)
        panel.run_combo.blockSignals(False)
        current_widget = _current_widget(panel)
        current_widget.show_message.reset_mock()
        current_widget.update_plot.reset_mock()

        with patch(
            "XBrainLab.ui.panels.visualization.panel.begin_saliency_render_operation",
        ) as begin_render:
            panel.on_update()

        begin_render.assert_not_called()
        current_widget.set_saliency_coverage.assert_called_with(None)
        current_widget.update_plot.assert_not_called()
        current_widget.show_message.assert_called_once_with(
            "Saliency coverage is unavailable for the selected result."
        )

    def test_unavailable_published_method_never_requests_render(
        self,
        panel_and_controller,
    ):
        panel, _controller = panel_and_controller
        unavailable = SaliencyMethodCoverageSnapshot(
            method="Gradient",
            available=False,
            complete=False,
            classes=[
                SaliencyClassCoverageSnapshot(
                    class_index=0,
                    display_name="left",
                    available=False,
                ),
            ],
        )
        _publish_panel_state(
            panel,
            _visualization_result(
                _run_coverage(
                    plan_index=0,
                    run_index=0,
                    model_name="EEGNet",
                    methods=(unavailable,),
                ),
            ),
        )
        current_widget = _current_widget(panel)
        current_widget.show_message.reset_mock()
        current_widget.update_plot.reset_mock()

        with patch(
            "XBrainLab.ui.panels.visualization.panel.begin_saliency_render_operation",
        ) as begin_render:
            panel.on_update()

        begin_render.assert_not_called()
        current_widget.set_saliency_coverage.assert_called_with(unavailable)
        current_widget.update_plot.assert_not_called()
        current_widget.show_message.assert_called_once_with(
            "Gradient saliency has not been computed for this run. "
            "Use Compute Saliency to continue."
        )

    def test_render_request_uses_exact_publication_and_run_identity(
        self,
        panel_and_controller,
        qtbot,
    ):
        panel, _controller = panel_and_controller
        coverage = _complete_coverage()
        publication = _publish_panel_state(
            panel,
            _visualization_result(
                _run_coverage(
                    plan_index=2,
                    run_index=4,
                    model_name="EEGNet",
                    run_name="Held-out repeat",
                    methods=(coverage,),
                ),
            ),
        )
        plan_identity = SaliencyPlanIdentity(plan_index=2)
        run_identity = SaliencyRunIdentity(
            plan=plan_identity,
            run_index=4,
        )
        assert panel.plan_combo.currentData() == plan_identity
        assert panel.run_combo.currentData() == run_identity
        expected_request = SaliencyRenderRequest(
            publication_generation=publication.generation,
            run=run_identity,
            method="Gradient",
        )
        requests: list[SaliencyRenderRequest] = []
        render_thread_ids: list[int] = []
        gui_thread_id = threading.get_ident()

        def get_render(_panel, request, **_kwargs):
            requests.append(request)
            render_thread_ids.append(threading.get_ident())
            return SaliencyRenderPublication(
                request=request,
                generation=request.publication_generation,
                training_generation=8,
                data=_render_data(request.method),
            )

        current_widget = _current_widget(panel)
        current_widget.update_plot.reset_mock()
        with patch(
            "XBrainLab.ui.panels.visualization.panel.prepare_saliency_render_variants_operation",
            side_effect=_prepare_variants_from(get_render),
        ):
            panel.on_update()
            qtbot.waitUntil(
                lambda: current_widget.update_plot.call_count == 1
                and panel.native_render_work_idle(),
                timeout=3000,
            )

        assert requests == [expected_request]
        assert render_thread_ids and render_thread_ids[0] != gui_thread_id
        current_widget.set_saliency_coverage.assert_called_with(coverage)
        current_widget.update_plot.assert_called_once()
        rendered, absolute = current_widget.update_plot.call_args.args
        assert isinstance(rendered, SaliencyRenderPublication)
        assert rendered.request == expected_request
        assert rendered.generation == publication.generation
        assert absolute is False

    def test_display_transform_toggles_use_fresh_owned_render_operations(
        self,
        panel_and_controller,
        qtbot,
    ):
        panel, _controller = panel_and_controller
        publication = _publish_panel_state(
            panel,
            _visualization_result(
                _run_coverage(
                    plan_index=0,
                    run_index=0,
                    model_name="EEGNet",
                ),
            ),
        )
        source_values = np.array([[[-2.0, 1.0, 0.0]]], dtype=np.float32)
        source_data = SaliencyRenderData(
            method="Gradient",
            saliency_by_class={0: source_values},
            class_map=((0, "left"),),
            event_ids={"left": 0},
            channel_names=("C3",),
            channel_positions=((-0.04, 0.0, 0.08),),
            sfreq=128.0,
            tmin=0.0,
        )
        backend_requests: list[SaliencyRenderRequest] = []

        def get_render(_panel, request, **_kwargs):
            sleep(0.05)
            backend_requests.append(request)
            return SaliencyRenderPublication(
                request=request,
                generation=request.publication_generation,
                training_generation=8,
                data=source_data,
            )

        current_widget = _current_widget(panel)
        current_widget.update_plot.reset_mock()
        with patch(
            "XBrainLab.ui.panels.visualization.panel.prepare_saliency_render_variants_operation",
            side_effect=_prepare_variants_from(get_render),
        ):
            panel.on_update()
            qtbot.waitUntil(
                lambda: current_widget.update_plot.call_count == 1
                and panel.native_render_work_idle(),
                timeout=3000,
            )

            for checkbox, checked in (
                (panel.abs_check, True),
                (panel.normalize_check, True),
                (panel.abs_check, False),
                (panel.normalize_check, False),
            ):
                checkbox.blockSignals(True)
                checkbox.setChecked(checked)
                checkbox.blockSignals(False)
                panel.on_update()
                qtbot.waitUntil(
                    lambda: panel.native_render_work_idle(),
                    timeout=3000,
                )

        expected_request = SaliencyRenderRequest(
            publication_generation=publication.generation,
            run=panel.run_combo.currentData(),
            method="Gradient",
        )
        assert backend_requests == [expected_request] * 5
        assert panel._query_port.begin_saliency_render.call_count == 5
        assert [call.args[1] for call in current_widget.update_plot.call_args_list] == [
            False,
            True,
            True,
            False,
            False,
        ]
        normalized_publication = next(
            call.args[0]
            for call in current_widget.update_plot.call_args_list
            if call.args[0].request.normalize
        )
        assert normalized_publication.request.normalize is True
        assert normalized_publication.data.normalized is True
        np.testing.assert_allclose(
            normalized_publication.data.saliency_by_class[0],
            [[[-1.0, 0.5, 0.0]]],
        )
        np.testing.assert_array_equal(source_values, [[[-2.0, 1.0, 0.0]]])

    def test_render_publication_cache_is_invalidated_by_application_generation(
        self,
        panel_and_controller,
        qtbot,
    ):
        panel, _controller = panel_and_controller
        publication = _publish_panel_state(
            panel,
            _visualization_result(
                _run_coverage(
                    plan_index=0,
                    run_index=0,
                    model_name="EEGNet",
                ),
            ),
        )
        backend_requests: list[SaliencyRenderRequest] = []

        def get_render(_panel, request, **_kwargs):
            backend_requests.append(request)
            return SaliencyRenderPublication(
                request=request,
                generation=request.publication_generation,
                training_generation=8,
                data=_render_data(),
            )

        with patch(
            "XBrainLab.ui.panels.visualization.panel.prepare_saliency_render_variants_operation",
            side_effect=_prepare_variants_from(get_render),
        ):
            panel.on_update()
            qtbot.waitUntil(
                lambda: len(backend_requests) == 1 and panel.native_render_work_idle(),
                timeout=3000,
            )
            next_publication = replace(
                publication,
                generation=publication.generation + 1,
                revision=publication.revision + 1,
            )
            assert panel._accept_application_publication(next_publication) is True
            panel.on_update()
            qtbot.waitUntil(
                lambda: len(backend_requests) == 2 and panel.native_render_work_idle(),
                timeout=3000,
            )

        assert [request.publication_generation for request in backend_requests] == [
            publication.generation,
            publication.generation + 1,
        ]

    def test_stale_render_publication_is_rejected(
        self,
        panel_and_controller,
        qtbot,
    ):
        panel, _controller = panel_and_controller
        publication = _publish_panel_state(
            panel,
            _visualization_result(
                _run_coverage(
                    plan_index=0,
                    run_index=0,
                    model_name="EEGNet",
                ),
            ),
        )
        run_identity = cast(
            SaliencyRunIdentity,
            panel.run_combo.currentData(),
        )
        stale_request = SaliencyRenderRequest(
            publication_generation=publication.generation + 1,
            run=run_identity,
            method="Gradient",
        )
        stale_render = SaliencyRenderPublication(
            request=stale_request,
            generation=stale_request.publication_generation,
            training_generation=8,
            data=_render_data(),
        )
        current_widget = _current_widget(panel)
        current_widget.show_message.reset_mock()
        current_widget.update_plot.reset_mock()

        with patch(
            "XBrainLab.ui.panels.visualization.panel.prepare_saliency_render_variants_operation",
            side_effect=_prepare_variants_from(
                lambda _panel, _request, **_kwargs: stale_render
            ),
        ):
            panel.on_update()
            qtbot.waitUntil(
                lambda: panel._application_view_publication is None
                and panel.native_render_work_idle(),
                timeout=3000,
            )

        current_widget.update_plot.assert_not_called()
        current_widget.show_message.assert_called_with(
            "Visualization results changed. Refresh Visualization and try again."
        )
        assert panel._application_view_publication is None
        assert panel._application_summary_dirty is True


class TestUpdatePanel:
    def test_update_panel_refreshes_info_then_plot(self, panel_and_controller):
        panel, _controller = panel_and_controller
        with (
            patch.object(panel, "update_info") as update_info,
            patch.object(panel, "on_update") as on_update,
        ):
            panel.update_panel()

        update_info.assert_called_once_with()
        on_update.assert_called_once_with()

    def test_update_info_refreshes_sidebar_and_combos(self, panel_and_controller):
        panel, _controller = panel_and_controller
        panel.last_saliency_query = MagicMock()
        panel._saliency_summary_dirty = False
        with patch.object(panel, "refresh_combos") as refresh_combos:
            panel.update_info()

        panel.sidebar.update_info.assert_called_once_with()
        refresh_combos.assert_called_once_with()
