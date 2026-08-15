from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PyQt6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from XBrainLab.backend.application import (
    SaliencyCommand,
    SaliencyPlanIdentity,
    SaliencyRenderData,
    SaliencyRenderPublication,
    SaliencyRunIdentity,
    VisualizeCommand,
)
from XBrainLab.backend.application.results import ChangedState, CommandResult, ErrorType
from XBrainLab.backend.application.state import (
    ApplicationStateSnapshot,
    SaliencyClassCoverageSnapshot,
    SaliencyMethodCoverageSnapshot,
    SaliencyRunCoverageSnapshot,
    VisualizationStateSnapshot,
)
from XBrainLab.backend.application.view_publication import ApplicationViewStore
from XBrainLab.backend.study import Study
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyStatus,
    TrainingReadBoundary,
    TrainingRunIdentity,
)
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.interaction_outcome import InteractionStatus


def _widget_factory(parent=None):
    widget = QWidget(parent)
    mock_widget = cast(Any, widget)
    mock_widget.show_error = MagicMock()
    mock_widget.show_message = MagicMock()
    mock_widget.set_saliency_coverage = MagicMock()
    mock_widget.update_plot = MagicMock()
    mock_widget.repaint = MagicMock()
    return widget


def _info_panel_factory(*args, **kwargs):
    return QWidget()


def _make_panel(qtbot, training_controller=None, parent=None, controller=None):
    del training_controller
    mock_ctrl = controller if controller is not None else MagicMock()
    if controller is None:
        mock_ctrl.get_trainers.return_value = []
        mock_ctrl.get_averaged_record.return_value = MagicMock()
    fallback_port = Observable()
    fallback_runtime = cast(Any, fallback_port)
    fallback_runtime.get_view_publication = MagicMock(return_value=None)
    fallback_runtime.execute = MagicMock(return_value=None)
    fallback_runtime.get_saliency_render = MagicMock(return_value=None)
    fallback_runtime.begin_saliency_render = MagicMock(
        side_effect=lambda _request: SimpleNamespace(operation_id="render-operation")
    )
    fallback_runtime.prepare_saliency_render = MagicMock(
        side_effect=lambda operation_id, request: replace(
            _render_publication_for_request(None, request),
            operation_id=operation_id,
        )
    )
    fallback_runtime.prepare_saliency_render_variants = MagicMock(
        side_effect=lambda operation_id, request, *, include_normalized: (
            replace(
                _render_publication_for_request(
                    None,
                    replace(request, normalize=False),
                ),
                operation_id=operation_id,
            ),
            (
                replace(
                    _render_publication_for_request(
                        None,
                        replace(request, normalize=True),
                    ),
                    operation_id=operation_id,
                )
                if include_normalized
                else None
            ),
        )
    )
    fallback_runtime.enter_saliency_render_commit = MagicMock(return_value=True)
    fallback_runtime.finish_saliency_render = MagicMock()
    fallback_runtime.get_owned_operation = MagicMock(
        return_value=SimpleNamespace(
            phase="running",
            completed=None,
            total=None,
            indeterminate=True,
            cancel_requested=False,
            cancellable=True,
            stage="Rendering saliency canvas",
        )
    )
    fallback_runtime.cancel_owned_operation = MagicMock(return_value=True)

    with (
        patch(
            "XBrainLab.ui.panels.visualization.control_sidebar.AggregateInfoPanel",
            side_effect=_info_panel_factory,
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
        from XBrainLab.ui.panels.visualization.panel import (
            VisualizationPanel,
            application_ui_runtime,
        )

        runtime_port = cast(Any, application_ui_runtime(parent) or fallback_runtime)
        publication_port = cast(
            Any,
            runtime_port if isinstance(runtime_port, Observable) else fallback_runtime,
        )
        panel = VisualizationPanel(
            parent=parent,
            query_port=cast(Any, runtime_port),
            publication_port=publication_port,
            action_port=cast(Any, runtime_port),
        )
        qtbot.addWidget(panel)

    return panel, mock_ctrl


def _make_trainer(name="EEGNet", repeats=2):
    trainer = MagicMock()
    trainer.model_holder.target_model.__name__ = name
    trainer.option.repeat_num = repeats
    trainer.get_plans.return_value = [MagicMock() for _ in range(repeats)]
    return trainer


def _make_eval_record_with_saliency():
    record = MagicMock()
    record.gradient = {0: np.ones((1, 2, 3))}
    record.gradient_input = {}
    record.smoothgrad = {}
    record.smoothgrad_sq = {}
    record.vargrad = {}
    return record


def test_visualization_selectors_have_visible_dropdown_affordance(qtbot):
    panel, _ = _make_panel(qtbot)

    for combo in (panel.plan_combo, panel.run_combo, panel.method_combo):
        style = combo.styleSheet()
        assert "QComboBox::down-arrow" in style
        assert "chevron-down.svg" in style


def test_visualization_shutdown_cancels_active_explicit_saliency(qtbot, monkeypatch):
    panel, _ = _make_panel(qtbot)
    panel._active_saliency_operation_id = "saliency-operation-1"
    cancelled: list[tuple[object, str, object]] = []
    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.cancel_application_operation",
        lambda context, operation_id, *, runtime=None: cancelled.append(
            (context, operation_id, runtime)
        )
        or True,
    )

    panel.begin_native_render_shutdown()

    assert cancelled == [
        (panel, "saliency-operation-1", panel._action_port),
    ]


def test_saliency_render_worker_start_failure_terminalizes_and_allows_retry(
    qtbot,
    monkeypatch,
) -> None:
    panel, _ = _make_panel(qtbot)
    _publish_panel_state(
        panel,
        _application_query_with_saliency_state(
            PostTrainingSaliencyStatus.idle(),
            _complete_coverage(),
        ),
    )
    task = panel._current_saliency_render_task()
    assert task is not None
    runtime = cast(Any, panel._query_port)
    phases: dict[str, str] = {}
    operation_ids = iter(("render-start-failed", "render-retry"))

    def begin_operation(_request):
        operation_id = next(operation_ids)
        phases[operation_id] = "pending"
        return SimpleNamespace(operation_id=operation_id)

    def finish_operation(operation_id, phase, *, message=""):
        del message
        phases[operation_id] = phase

    def operation_snapshot(operation_id):
        return SimpleNamespace(
            phase=phases[operation_id],
            completed=None,
            total=None,
            indeterminate=True,
            cancel_requested=False,
            cancellable=phases[operation_id] not in {"failed", "cancelled"},
            stage="Rendering saliency canvas",
        )

    runtime.begin_saliency_render.side_effect = begin_operation
    runtime.finish_saliency_render.side_effect = finish_operation
    runtime.get_owned_operation.side_effect = operation_snapshot
    first_worker = MagicMock()
    first_worker.signals = SimpleNamespace(
        result=MagicMock(),
        error=MagicMock(),
        finished=MagicMock(),
    )
    first_worker.start.side_effect = RuntimeError("thread start failed")
    retry_worker = MagicMock()
    retry_worker.signals = SimpleNamespace(
        result=MagicMock(),
        error=MagicMock(),
        finished=MagicMock(),
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.PythonThreadWorker",
        MagicMock(side_effect=(first_worker, retry_worker)),
    )
    current_widget = _current_mock_widget(panel)
    current_widget.show_error.reset_mock()

    panel._request_saliency_render(task)

    assert phases["render-start-failed"] == "failed"
    assert panel._saliency_render_worker is None
    assert panel._saliency_render_active_task is None
    assert panel.native_render_work_idle()
    assert panel._saliency_operation_presenter.active_operation_id is None
    current_widget.show_error.assert_called_once_with(
        "Visualization could not be loaded. Refresh Visualization and try again."
    )

    panel._request_saliency_render(task)

    retry_worker.start.assert_called_once_with()
    assert panel._saliency_render_worker is retry_worker
    assert panel._saliency_render_active_task is not None
    assert panel._saliency_render_active_task.operation_id == "render-retry"
    panel._on_saliency_render_finished(retry_worker)
    assert phases["render-retry"] == "cancelled"
    assert panel.native_render_work_idle()


def _make_eval_record_without_saliency():
    record = MagicMock()
    record.gradient = {}
    record.gradient_input = {}
    record.smoothgrad = {}
    record.smoothgrad_sq = {}
    record.vargrad = {}
    return record


def _complete_coverage(
    method: str = "Gradient",
    *class_names: str,
) -> SaliencyMethodCoverageSnapshot:
    names = class_names or ("left",)
    return SaliencyMethodCoverageSnapshot(
        method=method,
        available=True,
        complete=True,
        classes=[
            SaliencyClassCoverageSnapshot(
                class_index=index,
                display_name=name,
                available=True,
            )
            for index, name in enumerate(names)
        ],
    )


def _post_training_saliency_status(
    phase: PostTrainingSaliencyPhase,
    *,
    generation: int = 3,
) -> PostTrainingSaliencyStatus:
    pending = PostTrainingSaliencyStatus.pending(
        generation=generation,
        run=TrainingRunIdentity(trainer_id="trainer-ui", run_id=1),
        training_generation=7,
        methods=("Gradient", "Gradient * Input"),
    )
    if phase is PostTrainingSaliencyPhase.PENDING:
        return pending
    source = pending
    if phase is PostTrainingSaliencyPhase.SUCCEEDED:
        source = pending.transition(
            generation=generation,
            phase=PostTrainingSaliencyPhase.RUNNING,
            message="Automatic saliency is being computed.",
        )
    return source.transition(
        generation=generation,
        phase=phase,
        error_code="computation_failed"
        if phase is PostTrainingSaliencyPhase.FAILED
        else None,
        message={
            PostTrainingSaliencyPhase.RUNNING: (
                "Automatic saliency is being computed."
            ),
            PostTrainingSaliencyPhase.SUCCEEDED: "Automatic saliency is available.",
            PostTrainingSaliencyPhase.FAILED: (
                "Automatic saliency computation failed."
            ),
            PostTrainingSaliencyPhase.CANCELLED: (
                "Automatic saliency computation was cancelled."
            ),
        }[phase],
        diagnostic_type="RuntimeError"
        if phase is PostTrainingSaliencyPhase.FAILED
        else None,
    )


def _application_query_with_saliency_state(
    status: PostTrainingSaliencyStatus,
    coverage: SaliencyMethodCoverageSnapshot,
    *,
    plan_index: int = 0,
    run_index: int = 0,
    additional_coverages: tuple[SaliencyMethodCoverageSnapshot, ...] = (),
    training_is_running: bool = False,
) -> CommandResult:
    empty_state = ApplicationStateSnapshot.empty()
    state = replace(
        empty_state,
        training=replace(
            empty_state.training,
            is_running=training_is_running,
        ),
        active_training=replace(
            empty_state.active_training,
            is_running=training_is_running,
        ),
        visualization=VisualizationStateSnapshot(
            saliency_available=coverage.available,
            saliency_coverage=[
                SaliencyRunCoverageSnapshot(
                    plan_index=plan_index,
                    run_index=run_index,
                    methods=[coverage, *additional_coverages],
                ),
            ],
            post_training_saliency=status,
        ),
    )
    return CommandResult.success_result(
        "visualize",
        "Visualization ready",
        state,
        ChangedState(),
    )


def _publish_panel_state(panel, result: CommandResult) -> None:
    """Exact test helper for the immutable Application publication boundary."""
    assert isinstance(result.state, ApplicationStateSnapshot)
    publication = ApplicationViewStore(
        result.state,
        TrainingReadBoundary.no_trainer(),
    ).read()
    assert panel._accept_application_publication(publication) is True
    panel.last_application_query = result
    panel._application_summary_dirty = False
    with patch.object(panel, "on_update"):
        panel.refresh_combos()


def _render_publication_for_request(_panel, request, **_kwargs):
    data = SaliencyRenderData(
        method=request.method,
        saliency_by_class={0: np.ones((1, 2, 3))},
        class_map=((0, "left"),),
        event_ids={"left": 0},
        channel_names=("C3", "C4"),
        channel_positions=((-0.04, 0.0, 0.08), (0.04, 0.0, 0.08)),
        sfreq=128.0,
        tmin=0.0,
    )
    return SaliencyRenderPublication(
        request=request,
        generation=request.publication_generation,
        training_generation=4,
        data=data,
    )


def _prepare_render_operation(_panel, operation_id, request, **_kwargs):
    return replace(
        _render_publication_for_request(_panel, request),
        operation_id=operation_id,
    )


def _prepare_render_variants(
    _panel,
    operation_id,
    request,
    *,
    include_normalized,
    **_kwargs,
):
    raw = replace(
        _render_publication_for_request(_panel, replace(request, normalize=False)),
        operation_id=operation_id,
    )
    normalized = (
        replace(
            _render_publication_for_request(_panel, replace(request, normalize=True)),
            operation_id=operation_id,
        )
        if include_normalized
        else None
    )
    return raw, normalized


def _result_with_run_coverages(
    *coverages: SaliencyRunCoverageSnapshot,
    raw_files: tuple[str, ...] = (),
) -> CommandResult:
    empty_state = ApplicationStateSnapshot.empty()
    state = replace(
        empty_state,
        raw=replace(
            empty_state.raw,
            loaded=bool(raw_files),
            count=len(raw_files),
            files=list(raw_files),
        ),
        visualization=VisualizationStateSnapshot(
            saliency_available=True,
            saliency_coverage=list(coverages),
        ),
    )
    return CommandResult.success_result(
        "visualize",
        "Visualization ready",
        state,
        ChangedState(),
    )


def _saliency_resource_failure(
    risk_level: str,
    *,
    receipt_id: str | None = None,
    challenge_command: str = "saliency",
    message: str | None = None,
) -> CommandResult:
    resource_message = message or f"Saliency resource risk: {risk_level}."
    requires_confirmation = risk_level in {"warning", "unknown"}
    resource_preflight: dict[str, Any] = {
        "schema_version": 1,
        "payload_type": "saliency_resource_preflight",
        "risk_level": risk_level,
        "requires_confirmation": requires_confirmation,
        "issues": [resource_message] if risk_level == "blocking" else [],
        "warnings": [resource_message] if risk_level == "warning" else [],
        "unknowns": [resource_message] if risk_level == "unknown" else [],
        "message": resource_message,
    }
    if receipt_id is not None:
        resource_preflight["confirmation_challenge"] = {
            "schema_version": 1,
            "challenge_id": receipt_id,
            "command_name": challenge_command,
            "scope_fingerprint": f"scope-{receipt_id}",
            "configuration_fingerprint": f"configuration-{receipt_id}",
            "preflight_fingerprint": f"preflight-{receipt_id}",
            "ttl_seconds": 120.0,
        }
    return CommandResult.failure_result(
        command_name="saliency",
        message=resource_message,
        state=ApplicationStateSnapshot.empty(),
        changed_state=ChangedState(),
        error_type=(
            ErrorType.CONFIRMATION_REQUIRED
            if requires_confirmation
            else ErrorType.PRECONDITION
        ),
        recoverable=requires_confirmation,
        diagnostics={"resource_preflight": resource_preflight},
    )


def _install_panel_publication_runtime(monkeypatch, result: CommandResult) -> None:
    """Keep real Study tests fail-closed while supplying an exact UI publication."""
    assert isinstance(result.state, ApplicationStateSnapshot)
    publication = ApplicationViewStore(
        result.state,
        TrainingReadBoundary.no_trainer(),
    ).read()
    runtime = MagicMock()
    runtime.get_view_publication.return_value = publication
    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.application_ui_runtime",
        lambda _context: runtime,
    )


def _current_mock_widget(panel) -> Any:
    widget = panel.tabs.currentWidget()
    assert widget is not None
    return cast(Any, widget)


def test_visualization_panel_layout_and_sidebar(qtbot):
    panel, _ctrl = _make_panel(qtbot)

    assert panel.tabs.count() == 4
    assert not any(
        group.title() == "EXPLANATION PLOTS" for group in panel.findChildren(QGroupBox)
    )
    assert panel.plan_combo.itemText(0) == "Select a fold"
    assert panel.method_combo.count() == 1
    assert panel.method_combo.currentText() == "No computed methods"
    assert panel.method_combo.isEnabled() is False
    assert panel.saliency_action_bar.isHidden()
    assert panel.compute_saliency_btn.text() == "Compute Saliency"
    assert panel.sidebar.btn_montage.text() == "Set Montage"
    assert panel.sidebar.btn_saliency.text() == "Saliency Settings"


def test_visualization_panel_keeps_aggregation_in_tooltip_without_extra_chrome(qtbot):
    panel, _ctrl = _make_panel(qtbot)

    assert not hasattr(panel, "explanation_context")
    assert not hasattr(panel, "explanation_info_button")
    assert not hasattr(panel, "explanation_provenance_label")
    assert panel.tabs.toolTip() == "True class · Mean over EEG epochs"

    panel.tabs.setCurrentIndex(1)
    assert panel.tabs.toolTip() == (
        "True class · Mean magnitude over EEG epochs and channels"
    )

    panel.tabs.setCurrentIndex(2)
    assert panel.tabs.toolTip() == "True class · Mean over EEG epochs and time"

    _publish_panel_state(
        panel,
        _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                plan_name="motor-imagery",
                model_name="EEGNet",
                run_name="Run 1",
                methods=[_complete_coverage()],
            ),
            raw_files=("A01T.gdf", "A02T.gdf", "A03T.gdf"),
        ),
    )
    with patch.object(panel, "on_update"):
        panel.tabs.setCurrentIndex(0)

    assert panel.tabs.toolTip() == (
        "motor-imagery · Fold 1 (EEGNet) · Run 1 · True class · Mean over EEG epochs"
    )

    _publish_panel_state(
        panel,
        _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                plan_name="motor-imagery",
                model_name="EEGNet",
                run_name="Run 1",
                methods=[_complete_coverage()],
            ),
            raw_files=("new-current-file.edf",),
        ),
    )

    assert panel.tabs.toolTip().startswith("motor-imagery · Fold 1 (EEGNet) · Run 1")
    assert "new-current-file.edf" not in panel.tabs.toolTip()


def test_visualization_panel_clears_result_identity_after_publication_rejection(qtbot):
    panel, _ctrl = _make_panel(qtbot)
    _publish_panel_state(
        panel,
        _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                plan_name="motor-imagery",
                model_name="EEGNet",
                run_name="Run 1",
                methods=[_complete_coverage()],
            ),
        ),
    )
    panel._refresh_explanation_context()
    publication = panel._application_view_publication
    assert publication is not None
    assert "motor-imagery" in panel.tabs.toolTip()
    with patch.object(panel, "_request_saliency_render"):
        panel.on_update()
    assert panel.method_combo.currentText() == "Gradient"

    assert (
        panel._accept_application_publication(replace(publication, stale=True)) is False
    )

    assert panel.tabs.toolTip() == "True class · Mean over EEG epochs"
    assert "motor-imagery" not in panel.tabs.toolTip()
    assert panel.method_combo.currentText() == "No computed methods"
    assert panel.method_combo.isEnabled() is False


def test_visualization_panel_invalidates_rendered_views_when_runtime_disappears(
    qtbot,
):
    panel, _ctrl = _make_panel(qtbot)
    _publish_panel_state(
        panel,
        _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                plan_name="motor-imagery",
                model_name="EEGNet",
                run_name="Run 1",
                methods=[_complete_coverage()],
            ),
        ),
    )
    invalidations: list[MagicMock] = []
    for attribute in ("tab_map", "tab_spectro", "tab_topo", "tab_3d"):
        invalidate = MagicMock()
        view = cast(Any, getattr(panel, attribute))
        view.invalidate_render_publication = invalidate
        invalidations.append(invalidate)
    panel._query_port = None

    with patch(
        "XBrainLab.ui.panels.visualization.panel.application_ui_runtime",
        return_value=None,
    ):
        assert panel._refresh_application_publication() is False

    assert panel._application_view_publication is None
    for invalidate in invalidations:
        invalidate.assert_called_once_with()


def test_visualization_panel_invalidates_rendered_views_when_publication_read_fails(
    qtbot,
):
    panel, _ctrl = _make_panel(qtbot)
    _publish_panel_state(
        panel,
        _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                methods=[_complete_coverage()],
            ),
        ),
    )
    invalidations: list[MagicMock] = []
    for attribute in ("tab_map", "tab_spectro", "tab_topo", "tab_3d"):
        invalidate = MagicMock()
        view = cast(Any, getattr(panel, attribute))
        view.invalidate_render_publication = invalidate
        invalidations.append(invalidate)
    runtime = MagicMock()
    runtime.get_view_publication.side_effect = RuntimeError("publication failed")
    panel._query_port = runtime

    assert panel._refresh_application_publication() is False

    assert panel._application_view_publication is None
    for invalidate in invalidations:
        invalidate.assert_called_once_with()


def test_visualization_panel_hides_absolute_only_for_spectrogram_and_restores_choice(
    qtbot,
):
    panel, _ctrl = _make_panel(qtbot)

    panel.method_combo.setCurrentText("Gradient")
    panel.abs_check.setChecked(True)

    for tab_index in (0, 2, 3):
        panel.tabs.setCurrentIndex(tab_index)
        assert not panel.abs_check.isHidden()
        assert panel.abs_check.isEnabled()
        assert panel.abs_check.isChecked()

        panel.tabs.setCurrentIndex(1)
        assert panel.abs_check.isHidden()
        assert panel.abs_check.isChecked()
        assert not panel.normalize_check.isHidden()
        assert panel.normalize_check.isEnabled()


def test_visualization_panel_keeps_nonnegative_method_absolute_visible_but_disabled(
    qtbot,
):
    panel, _ctrl = _make_panel(qtbot)
    _publish_panel_state(
        panel,
        _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                methods=[_complete_coverage("SmoothGrad_Squared")],
            ),
        ),
    )
    with patch.object(panel, "_request_saliency_render"):
        panel.on_update()

    for tab_index in (0, 2, 3):
        panel.tabs.setCurrentIndex(tab_index)
        assert not panel.abs_check.isHidden()
        assert not panel.abs_check.isEnabled()
        assert "non-negative" in panel.abs_check.toolTip()

    panel.tabs.setCurrentIndex(1)
    assert panel.abs_check.isHidden()
    assert "magnitude" in panel.abs_check.toolTip()


def test_spectrogram_normalize_uses_raw_publication_and_display_transform(
    qtbot,
    monkeypatch,
):
    panel, _ctrl = _make_panel(qtbot)
    _publish_panel_state(
        panel,
        _application_query_with_saliency_state(
            PostTrainingSaliencyStatus.idle(),
            _complete_coverage(),
        ),
    )
    requests = []

    def publish(
        _panel,
        operation_id,
        request,
        *,
        include_normalized,
        **_kwargs,
    ):
        requests.append(request)
        raw = replace(
            _render_publication_for_request(
                _panel,
                replace(request, normalize=False),
            ),
            operation_id=operation_id,
        )
        normalized = (
            replace(
                _render_publication_for_request(
                    _panel,
                    replace(request, normalize=True),
                ),
                operation_id=operation_id,
            )
            if include_normalized
            else None
        )
        return raw, normalized

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.prepare_saliency_render_variants_operation",
        publish,
    )
    panel.abs_check.setChecked(True)
    panel.tabs.setCurrentIndex(1)
    qtbot.waitUntil(panel.native_render_work_idle, timeout=3000)
    spectrogram = cast(Any, panel.tab_spectro)
    spectrogram.update_plot.reset_mock()
    raw_request_count = len(requests)

    panel.normalize_check.setChecked(True)
    qtbot.waitUntil(
        lambda: spectrogram.update_plot.call_count == 1
        and panel.native_render_work_idle(),
        timeout=3000,
    )

    assert requests
    assert len(requests) == raw_request_count + 1
    assert requests[-1].normalize is False
    publication, absolute = spectrogram.update_plot.call_args.args
    assert publication.data.normalized is False
    assert absolute is False
    assert spectrogram.update_plot.call_args.kwargs == {"display_normalized": True}


def test_visualization_controls_stay_in_a_compact_two_row_grid(qtbot):
    panel, _ctrl = _make_panel(qtbot)
    panel.abs_check.setChecked(True)
    panel.resize(760, 720)
    panel.show()
    qtbot.wait(50)

    control_group = next(
        group
        for group in panel.findChildren(QGroupBox)
        if group.title() == "VISUALIZATION CONTROLS"
    )
    layout = control_group.layout()

    assert isinstance(layout, QGridLayout)
    plan_item = layout.itemAtPosition(0, 1)
    run_item = layout.itemAtPosition(0, 3)
    method_item = layout.itemAtPosition(1, 1)
    absolute_item = layout.itemAtPosition(1, 3)
    normalize_item = layout.itemAtPosition(1, 4)
    assert plan_item is not None
    assert run_item is not None
    assert method_item is not None
    assert absolute_item is not None
    assert normalize_item is not None
    assert plan_item.widget() is panel.plan_combo
    assert run_item.widget() is panel.run_combo
    assert method_item.widget() is panel.method_combo
    assert absolute_item.widget() is panel.abs_check
    assert normalize_item.widget() is panel.normalize_check
    assert abs(panel.plan_combo.y() - panel.run_combo.y()) <= 8
    assert abs(panel.method_combo.y() - panel.abs_check.y()) <= 8
    assert abs(panel.method_combo.y() - panel.normalize_check.y()) <= 8
    assert panel.plan_combo.y() < panel.method_combo.y()

    widgets = [
        panel.plan_combo,
        panel.run_combo,
        panel.method_combo,
        panel.abs_check,
        panel.normalize_check,
    ]
    rects = [widget.geometry() for widget in widgets]
    for left_index, left_rect in enumerate(rects):
        for right_rect in rects[left_index + 1 :]:
            assert not left_rect.intersects(right_rect)

    control_height = control_group.height()
    transform_row_y = panel.normalize_check.y()
    selector_geometry = {
        "plan": panel.plan_combo.geometry(),
        "run": panel.run_combo.geometry(),
        "method": panel.method_combo.geometry(),
        "normalize": panel.normalize_check.geometry(),
    }
    panel.tabs.setCurrentIndex(1)
    qtbot.wait(20)

    assert panel.abs_check.isHidden()
    assert panel.abs_check.isChecked()
    assert not panel.normalize_check.isHidden()
    assert layout.getItemPosition(layout.indexOf(panel.abs_check))[:2] == (1, 3)
    assert layout.getItemPosition(layout.indexOf(panel.normalize_check))[:2] == (1, 4)
    assert panel.normalize_check.y() == transform_row_y
    assert control_group.height() == control_height
    assert panel.plan_combo.geometry() == selector_geometry["plan"]
    assert panel.run_combo.geometry() == selector_geometry["run"]
    assert panel.method_combo.geometry() == selector_geometry["method"]
    assert panel.normalize_check.geometry() == selector_geometry["normalize"]

    panel.tabs.setCurrentIndex(2)
    qtbot.wait(20)

    assert not panel.abs_check.isHidden()
    assert panel.abs_check.isChecked()
    assert layout.getItemPosition(layout.indexOf(panel.abs_check))[:2] == (1, 3)
    assert layout.getItemPosition(layout.indexOf(panel.normalize_check))[:2] == (1, 4)
    assert control_group.height() == control_height
    assert panel.plan_combo.geometry() == selector_geometry["plan"]
    assert panel.run_combo.geometry() == selector_geometry["run"]
    assert panel.method_combo.geometry() == selector_geometry["method"]
    assert panel.normalize_check.geometry() == selector_geometry["normalize"]


def test_visualization_controls_use_one_row_when_panel_is_wide(qtbot):
    panel, _ctrl = _make_panel(qtbot)
    panel.abs_check.setChecked(True)
    panel.resize(1180, 720)
    panel.show()
    qtbot.wait(50)

    control_group = next(
        group
        for group in panel.findChildren(QGroupBox)
        if group.title() == "VISUALIZATION CONTROLS"
    )
    layout = control_group.layout()
    assert isinstance(layout, QGridLayout)

    assert panel.plan_combo.y() == panel.run_combo.y()
    assert panel.plan_combo.y() == panel.method_combo.y()
    assert abs(panel.plan_combo.y() - panel.abs_check.y()) <= 8
    assert abs(panel.plan_combo.y() - panel.normalize_check.y()) <= 8

    widgets = [
        panel.plan_combo,
        panel.run_combo,
        panel.method_combo,
        panel.abs_check,
        panel.normalize_check,
    ]
    rects = [widget.geometry() for widget in widgets]
    for left_index, left_rect in enumerate(rects):
        for right_rect in rects[left_index + 1 :]:
            assert not left_rect.intersects(right_rect)

    control_height = control_group.height()
    transform_row_y = panel.normalize_check.y()
    selector_geometry = {
        "plan": panel.plan_combo.geometry(),
        "run": panel.run_combo.geometry(),
        "method": panel.method_combo.geometry(),
        "normalize": panel.normalize_check.geometry(),
    }
    panel.tabs.setCurrentIndex(1)
    qtbot.wait(20)

    assert panel.abs_check.isHidden()
    assert panel.abs_check.isChecked()
    assert not panel.normalize_check.isHidden()
    assert layout.getItemPosition(layout.indexOf(panel.abs_check))[:2] == (0, 6)
    assert layout.getItemPosition(layout.indexOf(panel.normalize_check))[:2] == (0, 7)
    assert panel.normalize_check.y() == transform_row_y
    assert control_group.height() == control_height
    assert panel.plan_combo.geometry() == selector_geometry["plan"]
    assert panel.run_combo.geometry() == selector_geometry["run"]
    assert panel.method_combo.geometry() == selector_geometry["method"]
    assert panel.normalize_check.geometry() == selector_geometry["normalize"]

    panel.tabs.setCurrentIndex(3)
    qtbot.wait(20)

    assert not panel.abs_check.isHidden()
    assert panel.abs_check.isChecked()
    assert layout.getItemPosition(layout.indexOf(panel.abs_check))[:2] == (0, 6)
    assert layout.getItemPosition(layout.indexOf(panel.normalize_check))[:2] == (0, 7)
    assert control_group.height() == control_height
    assert panel.plan_combo.geometry() == selector_geometry["plan"]
    assert panel.run_combo.geometry() == selector_geometry["run"]
    assert panel.method_combo.geometry() == selector_geometry["method"]
    assert panel.normalize_check.geometry() == selector_geometry["normalize"]


def test_visualization_panel_defers_service_queries_until_opened(
    qtbot,
    monkeypatch,
):
    from XBrainLab.backend.application import SaliencyCommand, VisualizeCommand

    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    calls = []

    def fake_execute(_panel, command, **_kwargs):
        calls.append(command)
        if isinstance(command, SaliencyCommand):
            return CommandResult.success_result(
                command_name="saliency",
                message="Saliency parameters are not configured yet.",
                state={},
                changed_state=ChangedState(),
                diagnostics={
                    "payload_type": "saliency_summary",
                    "saliency_available": False,
                },
            )
        if isinstance(command, VisualizeCommand):
            return CommandResult.success_result(
                command_name="visualize",
                message="No visualization views are ready yet.",
                state={},
                changed_state=ChangedState(),
                diagnostics={
                    "payload_type": "visualization_summary",
                    "available": False,
                },
            )
        raise AssertionError(f"unexpected command: {command!r}")

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command",
        fake_execute,
    )

    panel, _ctrl = _make_panel(qtbot, parent=RealMainWindow())

    assert calls == []

    panel.update_panel()
    panel.update_panel()

    assert [type(command) for command in calls] == [
        SaliencyCommand,
        VisualizeCommand,
    ]
    assert all(
        set(vars(command)) == {"view"}
        for command in calls
        if isinstance(command, VisualizeCommand)
    )

    panel.mark_refresh_dirty()
    panel.update_panel()

    assert [type(command) for command in calls] == [
        SaliencyCommand,
        VisualizeCommand,
        SaliencyCommand,
        VisualizeCommand,
    ]
    assert all(
        set(vars(command)) == {"view"}
        for command in calls
        if isinstance(command, VisualizeCommand)
    )


def test_visualization_panel_populates_controls_for_published_runs(qtbot):
    panel, ctrl = _make_panel(qtbot)
    complete = _complete_coverage()
    _publish_panel_state(
        panel,
        _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                model_name="EEGNet",
                run_name="Run 1",
                methods=[complete],
            ),
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=1,
                model_name="EEGNet",
                run_name="Run 2",
                methods=[complete],
            ),
            SaliencyRunCoverageSnapshot(
                plan_index=1,
                run_index=0,
                model_name="SCCNet",
                run_name="Run 1",
                methods=[complete],
            ),
        ),
    )

    assert panel.plan_combo.count() == 3
    assert panel.plan_combo.currentText() == "Fold 1 (EEGNet)"
    assert panel.run_combo.count() == 2

    panel.plan_combo.setCurrentIndex(2)

    assert panel.plan_combo.currentText() == "Fold 2 (SCCNet)"
    assert panel.run_combo.count() == 1
    assert panel.run_combo.findText("Average") == -1
    ctrl.get_trainers.assert_not_called()


def test_visualization_panel_dispatches_default_run_when_fold_changes(qtbot):
    panel, ctrl = _make_panel(qtbot)
    complete = _complete_coverage()
    _publish_panel_state(
        panel,
        _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                model_name="EEGNet",
                methods=[complete],
            ),
            SaliencyRunCoverageSnapshot(
                plan_index=1,
                run_index=0,
                model_name="SCCNet",
                methods=[complete],
            ),
        ),
    )
    panel.tabs.setCurrentIndex(0)
    current_widget = _current_mock_widget(panel)
    current_widget.update_plot.reset_mock()

    with patch(
        "XBrainLab.ui.panels.visualization.panel.prepare_saliency_render_variants_operation",
        side_effect=_prepare_render_variants,
    ):
        panel.plan_combo.setCurrentIndex(2)
        qtbot.waitUntil(
            lambda: current_widget.update_plot.call_count >= 1
            and panel.native_render_work_idle(),
            timeout=3000,
        )

    current_widget.update_plot.assert_called()
    args, _kwargs = current_widget.update_plot.call_args
    assert args[0].request.run == SaliencyRunIdentity(
        plan=SaliencyPlanIdentity(plan_index=1),
        run_index=0,
    )
    assert args[1] is False
    ctrl.get_trainers.assert_not_called()


def test_visualization_panel_dispatches_plot_update_to_active_tab(qtbot):
    panel, ctrl = _make_panel(qtbot)
    complete = _complete_coverage()
    _publish_panel_state(
        panel,
        _application_query_with_saliency_state(
            PostTrainingSaliencyStatus.idle(),
            complete,
        ),
    )
    panel._application_summary_dirty = False
    panel.tabs.setCurrentIndex(0)
    panel.plan_combo.setCurrentIndex(1)
    panel.run_combo.setCurrentIndex(0)
    current_widget = _current_mock_widget(panel)
    current_widget.update_plot.reset_mock()

    with patch(
        "XBrainLab.ui.panels.visualization.panel.prepare_saliency_render_variants_operation",
        side_effect=_prepare_render_variants,
    ):
        panel.on_update()
        qtbot.waitUntil(
            lambda: current_widget.update_plot.call_count == 1
            and panel.native_render_work_idle(),
            timeout=3000,
        )

    current_widget.set_saliency_coverage.assert_called_with(complete)
    current_widget.update_plot.assert_called_once()
    args, _kwargs = current_widget.update_plot.call_args
    assert isinstance(args[0], SaliencyRenderPublication)
    assert args[0].request.run.run_index == 0
    assert args[1] is False
    ctrl.get_trainers.assert_not_called()


def test_visualization_panel_filters_methods_by_selected_run_coverage(qtbot):
    panel, ctrl = _make_panel(qtbot)
    trainer = _make_trainer("EEGNet", repeats=1)
    eval_record = MagicMock()
    eval_record.saliency_context = cast(
        Any,
        type(
            "Context",
            (),
            {"class_map": ((0, "left"), (1, "right"))},
        )(),
    )
    eval_record.gradient = {0: np.ones((1, 2, 3)), 1: []}
    eval_record.gradient_input = {
        0: np.ones((1, 2, 3)),
        1: np.ones((1, 2, 3)),
    }
    eval_record.smoothgrad = {}
    eval_record.smoothgrad_sq = {}
    eval_record.vargrad = {}
    trainer.get_plans.return_value[0].get_eval_record.return_value = eval_record
    epoch = MagicMock()
    epoch.event_id = {"left": 0, "right": 1}
    trainer.get_dataset.return_value.get_epoch_data.return_value = epoch
    ctrl.get_trainers.return_value = [trainer]

    panel.refresh_combos()
    gradient = SaliencyMethodCoverageSnapshot(
        method="Gradient",
        available=True,
        complete=False,
        classes=[
            SaliencyClassCoverageSnapshot(
                class_index=0,
                display_name="left",
                available=True,
            ),
            SaliencyClassCoverageSnapshot(
                class_index=1,
                display_name="right",
                available=False,
            ),
        ],
    )
    gradient_input = _complete_coverage("Gradient * Input", "left", "right")
    _publish_panel_state(
        panel,
        _application_query_with_saliency_state(
            PostTrainingSaliencyStatus.idle(),
            gradient,
            additional_coverages=(gradient_input,),
        ),
    )
    panel._application_summary_dirty = False
    with patch(
        "XBrainLab.ui.panels.visualization.panel.prepare_saliency_render_variants_operation",
        side_effect=_prepare_render_variants,
    ):
        panel.on_update()
        qtbot.waitUntil(panel.native_render_work_idle, timeout=3000)

    assert [
        panel.method_combo.itemText(index)
        for index in range(panel.method_combo.count())
    ] == ["Gradient * Input"]
    assert panel.method_combo.isEnabled() is True
    assert panel.method_combo.currentText() == "Gradient * Input"

    with patch(
        "XBrainLab.ui.panels.visualization.panel.prepare_saliency_render_variants_operation",
        side_effect=_prepare_render_variants,
    ):
        panel.tabs.setCurrentIndex(3)
        assert [
            panel.method_combo.itemText(index)
            for index in range(panel.method_combo.count())
        ] == ["Gradient", "Gradient * Input"]
        panel.method_combo.setCurrentText("Gradient")
        current_widget = _current_mock_widget(panel)
        current_widget.update_plot.reset_mock()
        panel.on_update()
        qtbot.waitUntil(
            lambda: current_widget.update_plot.call_count == 1
            and panel.native_render_work_idle(),
            timeout=3000,
        )

    current_widget.update_plot.assert_called_once()


def test_visualization_panel_replaces_computed_methods_in_canonical_order(qtbot):
    panel, _ctrl = _make_panel(qtbot)
    _publish_panel_state(
        panel,
        _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                methods=[
                    _complete_coverage("VarGrad"),
                    _complete_coverage("Gradient * Input"),
                    _complete_coverage("Gradient"),
                ],
            ),
        ),
    )

    with patch.object(panel, "_request_saliency_render"):
        panel.on_update()

    assert [
        panel.method_combo.itemText(index)
        for index in range(panel.method_combo.count())
    ] == ["Gradient", "Gradient * Input", "VarGrad"]

    _publish_panel_state(
        panel,
        _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                methods=[_complete_coverage("SmoothGrad")],
            ),
        ),
    )
    with patch.object(panel, "_request_saliency_render"):
        panel.on_update()

    assert [
        panel.method_combo.itemText(index)
        for index in range(panel.method_combo.count())
    ] == ["SmoothGrad"]


def test_visualization_panel_prefers_published_run_coverage(qtbot):
    panel, ctrl = _make_panel(qtbot)
    trainer = _make_trainer("EEGNet", repeats=1)
    eval_record = _make_eval_record_with_saliency()
    trainer.get_plans.return_value[0].get_eval_record.return_value = eval_record
    ctrl.get_trainers.return_value = [trainer]

    panel.refresh_combos()
    published_coverage = SaliencyMethodCoverageSnapshot(
        method="Gradient",
        available=False,
        complete=False,
        classes=[
            SaliencyClassCoverageSnapshot(
                class_index=0,
                display_name="left",
                event_code=0,
                available=False,
                reason="No Gradient saliency is available for left.",
            ),
        ],
    )
    state = ApplicationStateSnapshot.empty()
    state = replace(
        state,
        visualization=VisualizationStateSnapshot(
            saliency_coverage=[
                SaliencyRunCoverageSnapshot(
                    plan_index=0,
                    run_index=0,
                    methods=[published_coverage],
                ),
            ],
        ),
    )
    _publish_panel_state(
        panel,
        CommandResult.success_result(
            "visualize",
            "Visualization ready",
            state,
            ChangedState(),
        ),
    )

    coverage = panel._published_coverage_for_selection()

    assert coverage == {"Gradient": published_coverage}


@pytest.mark.parametrize(
    "phase",
    [PostTrainingSaliencyPhase.PENDING, PostTrainingSaliencyPhase.RUNNING],
)
def test_visualization_panel_reports_active_background_saliency_without_recompute(
    qtbot,
    phase,
):
    panel, ctrl = _make_panel(qtbot)
    trainer = _make_trainer("EEGNet", repeats=1)
    eval_record = _make_eval_record_without_saliency()
    trainer.get_plans.return_value[0].get_eval_record.return_value = eval_record
    ctrl.get_trainers.return_value = [trainer]
    panel.refresh_combos()
    missing = SaliencyMethodCoverageSnapshot(
        method="Gradient",
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
        _application_query_with_saliency_state(
            _post_training_saliency_status(phase),
            missing,
        ),
    )
    panel._application_summary_dirty = False
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()

    with patch.object(panel, "_start_saliency_compute") as start_compute:
        panel.on_update()

    start_compute.assert_not_called()
    current_widget.update_plot.assert_not_called()
    message = current_widget.show_message.call_args.args[0]
    assert "background" in message
    assert "has not been computed" not in message
    assert panel.compute_saliency_btn.text() == "Computing..."
    assert panel.compute_saliency_btn.isEnabled() is False


def test_visualization_panel_hides_compute_saliency_while_training(qtbot):
    panel, ctrl = _make_panel(qtbot)
    trainer = _make_trainer("EEGNet", repeats=1)
    trainer.get_plans.return_value[
        0
    ].get_eval_record.return_value = _make_eval_record_without_saliency()
    ctrl.get_trainers.return_value = [trainer]
    panel.refresh_combos()
    missing = SaliencyMethodCoverageSnapshot(
        method="Gradient",
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
        _application_query_with_saliency_state(
            PostTrainingSaliencyStatus.idle(),
            missing,
            training_is_running=True,
        ),
    )
    panel._application_summary_dirty = False

    with patch.object(panel, "_start_saliency_compute") as start_compute:
        panel.on_update()
        panel._compute_saliency_from_action_bar()

    start_compute.assert_not_called()
    assert panel.compute_saliency_btn.isHidden()
    assert panel.saliency_action_title.text() == "Training in progress"


@pytest.mark.parametrize(
    "phase",
    [PostTrainingSaliencyPhase.FAILED, PostTrainingSaliencyPhase.CANCELLED],
)
def test_visualization_panel_reports_terminal_background_saliency_action(
    qtbot,
    phase,
):
    panel, ctrl = _make_panel(qtbot)
    trainer = _make_trainer("EEGNet", repeats=1)
    trainer.get_plans.return_value[
        0
    ].get_eval_record.return_value = _make_eval_record_without_saliency()
    ctrl.get_trainers.return_value = [trainer]
    panel.refresh_combos()
    missing = SaliencyMethodCoverageSnapshot(
        method="Gradient",
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
        _application_query_with_saliency_state(
            _post_training_saliency_status(phase),
            missing,
        ),
    )
    panel._application_summary_dirty = False
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()

    with patch.object(panel, "_start_saliency_compute") as start_compute:
        panel.on_update()

    start_compute.assert_not_called()
    message = current_widget.show_message.call_args.args[0]
    assert phase.value in message
    assert "Use Recompute Saliency" in message
    assert panel.compute_saliency_btn.text() == "Recompute Saliency"
    assert panel.compute_saliency_btn.isEnabled() is True


def test_visualization_panel_partial_coverage_reports_running_not_no_data(qtbot):
    panel, ctrl = _make_panel(qtbot)
    trainer = _make_trainer("EEGNet", repeats=1)
    eval_record = MagicMock()
    eval_record.gradient = {0: np.ones((1, 2, 3)), 1: []}
    trainer.get_plans.return_value[0].get_eval_record.return_value = eval_record
    ctrl.get_trainers.return_value = [trainer]
    panel.refresh_combos()
    partial = SaliencyMethodCoverageSnapshot(
        method="Gradient",
        available=True,
        complete=False,
        classes=[
            SaliencyClassCoverageSnapshot(
                class_index=0,
                display_name="left",
                available=True,
            ),
            SaliencyClassCoverageSnapshot(
                class_index=1,
                display_name="right",
                available=False,
            ),
        ],
    )
    _publish_panel_state(
        panel,
        _application_query_with_saliency_state(
            _post_training_saliency_status(PostTrainingSaliencyPhase.RUNNING),
            partial,
        ),
    )
    panel._application_summary_dirty = False
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()

    with patch(
        "XBrainLab.ui.panels.visualization.panel.prepare_saliency_render_variants_operation",
        side_effect=_prepare_render_variants,
    ):
        panel.on_update()

    current_widget.update_plot.assert_not_called()
    message = current_widget.show_message.call_args.args[0]
    assert message == "Gradient saliency is being computed in the background."
    assert "missing" not in message.lower()


def test_visualization_panel_renders_complete_coverage_after_background_failure(qtbot):
    panel, ctrl = _make_panel(qtbot)
    trainer = _make_trainer("EEGNet", repeats=1)
    eval_record = _make_eval_record_with_saliency()
    trainer.get_plans.return_value[0].get_eval_record.return_value = eval_record
    ctrl.get_trainers.return_value = [trainer]
    panel.refresh_combos()
    complete = SaliencyMethodCoverageSnapshot(
        method="Gradient",
        available=True,
        complete=True,
        classes=[
            SaliencyClassCoverageSnapshot(
                class_index=0,
                display_name="left",
                available=True,
            ),
        ],
    )
    _publish_panel_state(
        panel,
        _application_query_with_saliency_state(
            _post_training_saliency_status(PostTrainingSaliencyPhase.FAILED),
            complete,
        ),
    )
    panel._application_summary_dirty = False
    current_widget = _current_mock_widget(panel)
    current_widget.update_plot.reset_mock()

    with patch(
        "XBrainLab.ui.panels.visualization.panel.prepare_saliency_render_variants_operation",
        side_effect=_prepare_render_variants,
    ):
        panel.on_update()
        qtbot.waitUntil(
            lambda: current_widget.update_plot.call_count == 1
            and panel.native_render_work_idle(),
            timeout=3000,
        )

    current_widget.update_plot.assert_called_once()


def test_visualization_panel_partial_multiclass_method_requires_recompute(qtbot):
    panel, ctrl = _make_panel(qtbot)
    trainer = _make_trainer("EEGNet", repeats=1)
    eval_record = MagicMock()
    eval_record.saliency_context = cast(
        Any,
        type(
            "Context",
            (),
            {"class_map": ((0, "left"), (1, "right"))},
        )(),
    )
    eval_record.gradient = {0: np.ones((1, 2, 3)), 1: []}
    eval_record.gradient_input = {}
    eval_record.smoothgrad = {}
    eval_record.smoothgrad_sq = {}
    eval_record.vargrad = {}
    trainer.get_plans.return_value[0].get_eval_record.return_value = eval_record
    epoch = MagicMock()
    epoch.event_id = {"left": 0, "right": 1}
    trainer.get_dataset.return_value.get_epoch_data.return_value = epoch
    ctrl.get_trainers.return_value = [trainer]

    panel.refresh_combos()
    partial = SaliencyMethodCoverageSnapshot(
        method="Gradient",
        available=True,
        complete=False,
        classes=[
            SaliencyClassCoverageSnapshot(
                class_index=0,
                display_name="left",
                available=True,
            ),
            SaliencyClassCoverageSnapshot(
                class_index=1,
                display_name="right",
                available=False,
            ),
        ],
    )
    _publish_panel_state(
        panel,
        _application_query_with_saliency_state(
            PostTrainingSaliencyStatus.idle(),
            partial,
        ),
    )
    panel._application_summary_dirty = False
    current_widget = _current_mock_widget(panel)
    current_widget.update_plot.reset_mock()
    current_widget.show_message.reset_mock()
    panel.method_combo.setCurrentText("Gradient")

    panel.on_update()

    current_widget.update_plot.assert_not_called()
    current_widget.show_message.assert_called_with(
        "Gradient saliency is missing for: right. Recompute saliency for this "
        "run before opening a multi-class view."
    )
    assert panel.compute_saliency_btn.text() == "Recompute Saliency"


def test_visualization_panel_missing_publication_does_not_rebuild_eval_policy(qtbot):
    panel, _ctrl = _make_panel(qtbot)

    coverage = panel._published_coverage_for_selection()

    assert coverage is None


def test_visualization_panel_empty_publication_clears_run_selection(qtbot):
    panel, ctrl = _make_panel(qtbot)
    publication = ApplicationViewStore(
        ApplicationStateSnapshot.empty(),
        TrainingReadBoundary.no_trainer(),
    ).read()
    assert panel._accept_application_publication(publication) is True
    panel._application_summary_dirty = False
    panel.last_application_query = CommandResult.success_result(
        "visualize",
        "Visualization ready",
        publication.state,
        ChangedState(),
    )
    panel.refresh_combos()
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()
    current_widget.update_plot.reset_mock()

    panel.on_update()

    current_widget.update_plot.assert_not_called()
    current_widget.show_message.assert_called_with("Select a fold and run to continue.")
    assert panel.run_combo.count() == 0
    ctrl.get_trainers.assert_not_called()
    assert panel.saliency_action_bar.isHidden()


def test_visualization_panel_configured_saliency_requires_explicit_action(
    qtbot,
    monkeypatch,
):
    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    service_trainer = _make_trainer("EEGNet", repeats=1)
    service_trainer.get_plans.return_value[
        0
    ].get_eval_record.return_value = _make_eval_record_without_saliency()
    async_commands = []
    configured_params = {
        "SmoothGrad": {"nt_samples": 3},
        "SmoothGrad_Squared": {"nt_samples": 3},
        "VarGrad": {"nt_samples": 3},
    }

    def fake_execute(_panel, command, **_kwargs):
        if isinstance(command, SaliencyCommand):
            return CommandResult.success_result(
                command_name="saliency",
                message="Saliency summary ready.",
                state={},
                changed_state=ChangedState(),
                diagnostics={
                    "payload_type": "saliency_summary",
                    "params": configured_params,
                    "saliency_configured": True,
                    "saliency_available": False,
                    "configure_available": True,
                },
            )
        if isinstance(command, VisualizeCommand):
            return CommandResult.success_result(
                command_name="visualize",
                message="Visualization summary ready.",
                state={},
                changed_state=ChangedState(),
                diagnostics={
                    "payload_type": "visualization_summary",
                    "available": True,
                },
            )
        raise AssertionError(f"unexpected command: {command!r}")

    def fake_execute_async(_panel, command, *, on_result, **_kwargs):
        del on_result
        async_commands.append(command)
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command",
        fake_execute,
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        fake_execute_async,
    )
    _install_panel_publication_runtime(
        monkeypatch,
        _application_query_with_saliency_state(
            PostTrainingSaliencyStatus.idle(),
            SaliencyMethodCoverageSnapshot(method="SmoothGrad"),
        ),
    )

    panel, ctrl = _make_panel(qtbot, parent=RealMainWindow())
    ctrl.get_trainers.return_value = [service_trainer]
    panel.method_combo.setCurrentText("SmoothGrad")
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()
    current_widget.update_plot.reset_mock()

    panel.update_panel()

    assert async_commands == []
    current_widget.update_plot.assert_not_called()
    current_widget.show_message.assert_called_with(
        "SmoothGrad saliency has not been computed for this run. "
        "Use Compute Saliency to continue."
    )

    panel.tabs.setCurrentIndex(1)
    assert async_commands == []

    panel.compute_saliency_btn.click()

    assert len(async_commands) == 1
    command = async_commands[0]
    assert isinstance(command, SaliencyCommand)
    assert command.method == "SmoothGrad"
    assert command.params == configured_params


def test_explicit_saliency_busy_state_keeps_visible_cancel_operable(
    qtbot,
    monkeypatch,
) -> None:
    class BusyMainWindow(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.study = Study()

        def set_busy(self, busy: bool) -> None:
            self.setEnabled(not busy)

    window = BusyMainWindow()
    qtbot.addWidget(window)
    panel, _ctrl = _make_panel(qtbot, parent=window)
    _publish_panel_state(
        panel,
        _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                model_name="EEGNet",
                methods=[SaliencyMethodCoverageSnapshot(method="Gradient")],
            ),
        ),
    )
    panel._show_saliency_action_bar("Gradient")
    commands: list[object] = []

    def fake_execute_async(_panel, command, **kwargs) -> bool:
        commands.append(command)
        busy_target = kwargs["busy_target"]
        busy_target.set_busy(True)
        kwargs["on_operation_started"]("saliency-operation-1")
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        fake_execute_async,
    )
    cancelled: list[str] = []
    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.cancel_application_operation",
        lambda _context, operation_id, *, runtime=None: cancelled.append(operation_id)
        or True,
    )

    panel.compute_saliency_btn.click()

    assert len(commands) == 1
    assert isinstance(commands[0], SaliencyCommand)
    assert window.isEnabled()
    assert not panel.cancel_saliency_btn.isHidden()
    assert panel.cancel_saliency_btn.isEnabled()
    assert not panel.plan_combo.isEnabled()
    assert not panel.run_combo.isEnabled()
    assert not panel.method_combo.isEnabled()
    assert not panel.sidebar.btn_montage.isEnabled()
    assert not panel.sidebar.btn_saliency.isEnabled()

    panel.cancel_saliency_btn.click()

    assert cancelled == ["saliency-operation-1"]
    panel.set_busy(False)
    assert not panel.plan_combo.isEnabled()

    panel._finish_saliency_compute_cancelled(
        attempt_key=None,
        current_widget=panel.tab_map,
    )

    assert panel.plan_combo.isEnabled()
    assert panel.run_combo.isEnabled()
    assert not panel.method_combo.isEnabled()
    assert panel.sidebar.btn_montage.isEnabled()
    assert panel.sidebar.btn_saliency.isEnabled()


def test_saliency_busy_state_tolerates_minimal_sidebar(qtbot) -> None:
    panel, _ctrl = _make_panel(qtbot)
    full_sidebar = panel.sidebar
    panel.sidebar = SimpleNamespace()
    try:
        panel.set_busy(True)

        assert not panel.plan_combo.isEnabled()
        assert panel.cancel_saliency_btn.isEnabled() is False

        panel.set_busy(False)

        assert panel.plan_combo.isEnabled()
    finally:
        panel.sidebar = full_sidebar


def test_unowned_saliency_render_terminalization_is_a_noop(
    qtbot,
    monkeypatch,
) -> None:
    panel, _ctrl = _make_panel(qtbot)
    finish = MagicMock(return_value=True)
    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.finish_saliency_render_operation",
        finish,
    )

    assert panel._finish_render_operation("", "cancelled") is False
    finish.assert_not_called()


def test_visualization_panel_converts_stored_saliency_params_before_compute(
    qtbot,
    monkeypatch,
):
    panel, _ctrl = _make_panel(qtbot)
    _publish_panel_state(
        panel,
        _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                model_name="EEGNet",
                methods=[SaliencyMethodCoverageSnapshot(method="SmoothGrad")],
            ),
        ),
    )
    configured_params = {
        "_profile": "advanced",
        "_methods": ["SmoothGrad"],
        "SmoothGrad": {
            "nt_samples": 7,
            "nt_samples_batch_size": None,
            "stdevs": 0.25,
        },
        "SmoothGrad_Squared": {
            "nt_samples": 5,
            "nt_samples_batch_size": None,
            "stdevs": 1.0,
        },
        "VarGrad": {
            "nt_samples": 5,
            "nt_samples_batch_size": None,
            "stdevs": 1.0,
        },
    }
    panel.last_saliency_query = CommandResult.success_result(
        command_name="saliency",
        message="Saliency summary ready.",
        state={},
        changed_state=ChangedState(),
        diagnostics={
            "payload_type": "saliency_summary",
            "params": configured_params,
        },
    )
    panel.method_combo.setCurrentText("SmoothGrad")
    starts = []
    monkeypatch.setattr(
        panel,
        "_start_saliency_compute",
        lambda **kwargs: starts.append(kwargs) or True,
    )

    panel._compute_saliency_from_action_bar()

    assert len(starts) == 1
    assert starts[0]["params"] == {
        "profile": "advanced",
        "methods": ["SmoothGrad"],
        "SmoothGrad": {
            "nt_samples": 7,
            "nt_samples_batch_size": None,
            "stdevs": 0.25,
        },
    }


def test_staged_saliency_settings_run_only_from_explicit_compute(
    qtbot,
    monkeypatch,
):
    panel, _ctrl = _make_panel(qtbot)
    committed = _complete_coverage("Gradient")
    _publish_panel_state(
        panel,
        _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                model_name="EEGNet",
                methods=[committed],
            ),
        ),
    )
    panel.on_update()
    publication = panel._application_view_publication
    assert publication is not None
    run_identity = panel.run_combo.currentData()
    assert isinstance(run_identity, SaliencyRunIdentity)
    starts = []
    monkeypatch.setattr(
        panel,
        "_start_saliency_compute",
        lambda **kwargs: starts.append(kwargs) or True,
    )
    params = {
        "profile": "advanced",
        "methods": ["VarGrad"],
        "VarGrad": {"nt_samples": 7},
    }

    panel.stage_saliency_params(
        params,
        publication_generation=publication.generation,
        run_identity=run_identity,
        model_name="EEGNet",
    )

    assert starts == []
    assert [
        panel.method_combo.itemText(index)
        for index in range(panel.method_combo.count())
    ] == ["Gradient"]
    assert panel.method_combo.currentText() == "Gradient"
    assert panel.compute_saliency_btn.text() == "Recompute Saliency"

    panel._compute_saliency_from_action_bar()

    assert len(starts) == 1
    assert starts[0]["method_name"] == "VarGrad"
    assert starts[0]["params"] == params

    panel._finish_saliency_compute_failure(
        message="compute failed",
        attempt_key=None,
        current_widget=None,
    )
    assert [
        panel.method_combo.itemText(index)
        for index in range(panel.method_combo.count())
    ] == ["Gradient"]

    panel._finish_saliency_compute_cancelled(
        attempt_key=None,
        current_widget=None,
    )
    assert [
        panel.method_combo.itemText(index)
        for index in range(panel.method_combo.count())
    ] == ["Gradient"]


def test_staged_uncomputed_method_stays_out_of_render_combo_through_real_lifecycle(
    qtbot,
    monkeypatch,
):
    panel, _ctrl = _make_panel(qtbot)

    def publish(*methods: SaliencyMethodCoverageSnapshot) -> None:
        result = _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                model_name="EEGNet",
                methods=list(methods),
            ),
        )
        assert isinstance(result.state, ApplicationStateSnapshot)
        publication = ApplicationViewStore(
            result.state,
            TrainingReadBoundary.no_trainer(),
        ).read()
        assert panel._accept_application_publication(publication) is True
        panel.last_application_query = result
        panel._application_summary_dirty = False
        panel.refresh_combos()
        qtbot.waitUntil(panel.native_render_work_idle, timeout=3000)

    def rendered_methods() -> list[str]:
        return [
            panel.method_combo.itemText(index)
            for index in range(panel.method_combo.count())
        ]

    publish(_complete_coverage("Gradient"))
    publication = panel._application_view_publication
    assert publication is not None
    run_identity = panel.run_combo.currentData()
    assert isinstance(run_identity, SaliencyRunIdentity)

    params = {
        "profile": "advanced",
        "methods": ["VarGrad"],
        "VarGrad": {"nt_samples": 7},
    }
    assert panel.stage_saliency_params(
        params,
        publication_generation=publication.generation,
        run_identity=run_identity,
        model_name="EEGNet",
    )
    assert rendered_methods() == ["Gradient"]

    async_calls: list[tuple[SaliencyCommand, Any, Any]] = []

    def execute_async(
        _panel,
        command,
        *,
        on_result,
        on_error,
        on_operation_started,
        **_kwargs,
    ) -> bool:
        assert isinstance(command, SaliencyCommand)
        async_calls.append((command, on_result, on_error))
        on_operation_started(f"saliency-operation-{len(async_calls)}")
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        execute_async,
    )

    panel.compute_saliency_btn.click()

    assert len(async_calls) == 1
    command, on_result, on_error = async_calls[0]
    assert command.method == "VarGrad"
    assert command.params == params
    assert panel.compute_saliency_btn.property("operationPhase") == "pending"
    assert rendered_methods() == ["Gradient"]

    minimum_generation = panel._active_saliency_minimum_generation
    assert minimum_generation is not None
    outcome = on_result(
        CommandResult.success_result(
            command_name="saliency",
            message="Saliency computation scheduled.",
            state={},
            changed_state=ChangedState(),
            diagnostics={
                "action": "schedule",
                "post_training_saliency_schedule": {
                    "status": {"generation": minimum_generation},
                },
            },
        )
    )

    assert outcome.status is InteractionStatus.ACCEPTED
    assert panel.compute_saliency_btn.property("operationPhase") == "running"
    assert rendered_methods() == ["Gradient"]

    on_error((RuntimeError, RuntimeError("compute failed"), "traceback"))

    assert panel.compute_saliency_btn.property("operationPhase") == "failed"
    assert rendered_methods() == ["Gradient"]

    panel.compute_saliency_btn.click()

    assert len(async_calls) == 2
    assert async_calls[1][0].method == "VarGrad"
    assert panel.compute_saliency_btn.property("operationPhase") == "pending"
    assert rendered_methods() == ["Gradient"]

    panel._finish_saliency_compute_cancelled(
        attempt_key=None,
        current_widget=panel.tabs.currentWidget(),
    )

    assert panel.compute_saliency_btn.property("operationPhase") == "cancelled"
    assert rendered_methods() == ["Gradient"]

    publish(
        _complete_coverage("VarGrad"),
        _complete_coverage("Gradient"),
    )

    assert rendered_methods() == ["Gradient", "VarGrad"]


def test_staged_saliency_settings_dispatch_with_reviewed_generation(
    qtbot,
    monkeypatch,
):
    panel, _ctrl = _make_panel(qtbot)
    _publish_panel_state(
        panel,
        _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                model_name="EEGNet",
                methods=[SaliencyMethodCoverageSnapshot(method="VarGrad")],
            ),
        ),
    )
    publication = panel._application_view_publication
    assert publication is not None
    run_identity = panel.run_combo.currentData()
    assert isinstance(run_identity, SaliencyRunIdentity)
    starts = []
    monkeypatch.setattr(
        panel,
        "_start_saliency_compute",
        lambda **kwargs: starts.append(kwargs) or True,
    )
    params = {
        "profile": "advanced",
        "methods": ["VarGrad"],
        "VarGrad": {"nt_samples": 7},
    }

    staged = panel.stage_saliency_params(
        params,
        publication_generation=publication.generation,
        run_identity=run_identity,
        model_name="EEGNet",
    )
    panel._compute_saliency_from_action_bar()

    assert staged is True
    assert len(starts) == 1
    assert starts[0]["expected_publication_generation"] == publication.generation
    assert starts[0]["run_identity"] == run_identity
    assert starts[0]["model_name"] == "EEGNet"


def test_staged_saliency_settings_reject_changed_run_selection(
    qtbot,
    monkeypatch,
):
    panel, _ctrl = _make_panel(qtbot)
    _publish_panel_state(
        panel,
        _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                model_name="EEGNet",
                methods=[SaliencyMethodCoverageSnapshot(method="VarGrad")],
            ),
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=1,
                model_name="EEGNet",
                methods=[SaliencyMethodCoverageSnapshot(method="VarGrad")],
            ),
        ),
    )
    publication = panel._application_view_publication
    assert publication is not None
    reviewed_run = panel.run_combo.currentData()
    assert isinstance(reviewed_run, SaliencyRunIdentity)
    panel.stage_saliency_params(
        {
            "profile": "advanced",
            "methods": ["VarGrad"],
            "VarGrad": {"nt_samples": 7},
        },
        publication_generation=publication.generation,
        run_identity=reviewed_run,
        model_name="EEGNet",
    )
    panel.run_combo.setCurrentIndex(1)
    starts = []
    monkeypatch.setattr(
        panel,
        "_start_saliency_compute",
        lambda **kwargs: starts.append(kwargs) or True,
    )

    panel._compute_saliency_from_action_bar()

    assert starts == []
    assert panel.saliency_action_title.text() == "Review Saliency Settings Again"
    assert "selected run changed" in panel.saliency_action_detail.text().lower()


def test_staged_saliency_settings_reject_changed_publication(
    qtbot,
    monkeypatch,
):
    panel, _ctrl = _make_panel(qtbot)
    _publish_panel_state(
        panel,
        _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                model_name="EEGNet",
                methods=[SaliencyMethodCoverageSnapshot(method="VarGrad")],
            ),
        ),
    )
    publication = panel._application_view_publication
    assert publication is not None
    run_identity = panel.run_combo.currentData()
    assert isinstance(run_identity, SaliencyRunIdentity)
    panel.stage_saliency_params(
        {
            "profile": "advanced",
            "methods": ["VarGrad"],
            "VarGrad": {"nt_samples": 7},
        },
        publication_generation=publication.generation,
        run_identity=run_identity,
        model_name="EEGNet",
    )
    assert panel._accept_application_publication(
        replace(publication, generation=publication.generation + 1)
    )
    starts = []
    monkeypatch.setattr(
        panel,
        "_start_saliency_compute",
        lambda **kwargs: starts.append(kwargs) or True,
    )

    panel._compute_saliency_from_action_bar()

    assert starts == []
    assert panel.saliency_action_title.text() == "Review Saliency Settings Again"
    assert "results changed" in panel.saliency_action_detail.text().lower()


def test_staged_saliency_settings_survive_refresh_of_same_publication(
    qtbot,
    monkeypatch,
):
    panel, _ctrl = _make_panel(qtbot)
    _publish_panel_state(
        panel,
        _result_with_run_coverages(
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                model_name="EEGNet",
                methods=[SaliencyMethodCoverageSnapshot(method="VarGrad")],
            ),
        ),
    )
    publication = panel._application_view_publication
    assert publication is not None
    run_identity = panel.run_combo.currentData()
    assert isinstance(run_identity, SaliencyRunIdentity)
    params = {
        "profile": "advanced",
        "methods": ["VarGrad"],
        "VarGrad": {"nt_samples": 7},
    }
    panel.stage_saliency_params(
        params,
        publication_generation=publication.generation,
        run_identity=run_identity,
        model_name="EEGNet",
    )
    panel.mark_refresh_dirty()
    assert panel._accept_application_publication(publication)
    starts = []
    monkeypatch.setattr(
        panel,
        "_start_saliency_compute",
        lambda **kwargs: starts.append(kwargs) or True,
    )

    panel._compute_saliency_from_action_bar()

    assert len(starts) == 1
    assert starts[0]["expected_publication_generation"] == publication.generation


def test_stale_saliency_compute_requests_settings_review(qtbot):
    panel, _ctrl = _make_panel(qtbot)
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()
    current_widget.show_error.reset_mock()
    panel._saliency_compute_in_progress = True
    stale_result = CommandResult.failure_result(
        command_name="saliency",
        message="The reviewed application state changed.",
        state=ApplicationStateSnapshot.empty(),
        changed_state=ChangedState(),
        error_type=ErrorType.PRECONDITION,
        recoverable=True,
        diagnostics={"stale_publication": True},
    )

    outcome = panel._on_lazy_saliency_configured(
        stale_result,
        attempt_key=("manual",),
        current_widget=current_widget,
    )

    assert outcome.status is InteractionStatus.BLOCKED
    assert outcome.message == "Review Saliency Settings Again"
    assert panel.saliency_action_title.text() == "Review Saliency Settings Again"
    current_widget.show_message.assert_called_with("Review Saliency Settings Again")
    current_widget.show_error.assert_not_called()


def test_scheduled_saliency_result_keeps_visible_compute_state_busy(qtbot):
    panel, _ctrl = _make_panel(qtbot)
    panel._saliency_compute_in_progress = True
    panel._active_saliency_operation_id = "saliency-operation-1"
    result = CommandResult.success_result(
        command_name="saliency",
        message="Saliency computation scheduled.",
        state=ApplicationStateSnapshot.empty(),
        changed_state=ChangedState(),
        diagnostics={
            "action": "schedule",
            "post_training_saliency_schedule": {
                "status": {"generation": 4},
            },
        },
    )
    panel._active_saliency_minimum_generation = 4

    outcome = panel._on_lazy_saliency_configured(result)

    assert outcome.status is InteractionStatus.ACCEPTED
    assert panel._saliency_compute_in_progress is True
    assert panel._active_saliency_operation_id == "saliency-operation-1"
    assert panel._active_saliency_generation == 4
    assert panel.compute_saliency_btn.text() == "Computing..."


def test_terminal_saliency_publication_releases_visible_compute_state(qtbot):
    panel, _ctrl = _make_panel(qtbot)
    panel._saliency_compute_in_progress = True
    panel._active_saliency_operation_id = "saliency-operation-1"
    panel._active_saliency_generation = 3
    result = _application_query_with_saliency_state(
        _post_training_saliency_status(PostTrainingSaliencyPhase.SUCCEEDED),
        _complete_coverage(),
    )
    assert isinstance(result.state, ApplicationStateSnapshot)
    publication = ApplicationViewStore(
        result.state,
        TrainingReadBoundary.no_trainer(),
    ).read()

    assert panel._accept_application_publication(publication)

    assert panel._saliency_compute_in_progress is False
    assert panel._active_saliency_operation_id is None
    assert panel.compute_saliency_btn.text() == "Compute Saliency"


def test_old_terminal_does_not_release_new_saliency_operation(qtbot):
    panel, _ctrl = _make_panel(qtbot)
    panel._saliency_compute_in_progress = True
    panel._active_saliency_minimum_generation = 4
    panel._bind_saliency_operation("saliency-operation-new")
    assert panel.compute_saliency_btn.property("operationId") == (
        "saliency-operation-new"
    )
    assert panel.compute_saliency_btn.property("operationPhase") == "pending"
    old_result = _application_query_with_saliency_state(
        _post_training_saliency_status(
            PostTrainingSaliencyPhase.SUCCEEDED,
            generation=3,
        ),
        _complete_coverage(),
    )
    assert isinstance(old_result.state, ApplicationStateSnapshot)
    old_publication = ApplicationViewStore(
        old_result.state,
        TrainingReadBoundary.no_trainer(),
    ).read()

    assert panel._accept_application_publication(old_publication)

    assert panel._saliency_compute_in_progress is True
    assert panel._active_saliency_operation_id == "saliency-operation-new"
    assert panel.compute_saliency_btn.property("operationPhase") == "pending"
    assert panel._saliency_operation_presenter.active_operation_id == (
        "saliency-operation-new"
    )
    assert panel.cancel_saliency_btn.isEnabled()

    new_result = _application_query_with_saliency_state(
        _post_training_saliency_status(
            PostTrainingSaliencyPhase.SUCCEEDED,
            generation=4,
        ),
        _complete_coverage(),
    )
    assert isinstance(new_result.state, ApplicationStateSnapshot)
    new_publication = ApplicationViewStore(
        new_result.state,
        TrainingReadBoundary.no_trainer(),
    ).read()

    assert panel._accept_application_publication(new_publication)
    assert panel._saliency_compute_in_progress is False
    assert panel._active_saliency_operation_id is None
    assert panel.compute_saliency_btn.property("operationPhase") == "completed"


def test_terminal_saliency_publication_wins_over_late_schedule_receipt(qtbot):
    panel, _ctrl = _make_panel(qtbot)
    panel._saliency_compute_in_progress = True
    panel._active_saliency_operation_id = "saliency-operation-1"
    panel._active_saliency_minimum_generation = 3
    terminal = _application_query_with_saliency_state(
        _post_training_saliency_status(PostTrainingSaliencyPhase.SUCCEEDED),
        _complete_coverage(),
    )
    assert isinstance(terminal.state, ApplicationStateSnapshot)
    publication = ApplicationViewStore(
        terminal.state,
        TrainingReadBoundary.no_trainer(),
    ).read()
    scheduled = CommandResult.success_result(
        command_name="saliency",
        message="Saliency computation scheduled.",
        state=terminal.state,
        changed_state=ChangedState(),
        diagnostics={"action": "schedule"},
    )

    assert panel._accept_application_publication(publication)
    outcome = panel._on_lazy_saliency_configured(scheduled)

    assert outcome.status is InteractionStatus.COMPLETED
    assert panel._saliency_compute_in_progress is False
    assert panel._active_saliency_operation_id is None
    assert panel.compute_saliency_btn.text() == "Compute Saliency"


def test_visualization_panel_unconfigured_saliency_requires_explicit_action(
    qtbot,
    monkeypatch,
):
    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    service_trainer = _make_trainer("EEGNet", repeats=1)
    service_trainer.get_plans.return_value[
        0
    ].get_eval_record.return_value = _make_eval_record_without_saliency()

    def fake_execute(_panel, command, **_kwargs):
        if isinstance(command, SaliencyCommand):
            return CommandResult.success_result(
                command_name="saliency",
                message="Saliency parameters are not configured yet.",
                state={},
                changed_state=ChangedState(),
                diagnostics={
                    "payload_type": "saliency_summary",
                    "params": {},
                    "saliency_available": False,
                    "configure_available": True,
                    "finished_run_count": 1,
                },
            )
        if isinstance(command, VisualizeCommand):
            return CommandResult.success_result(
                command_name="visualize",
                message="Visualization summary ready.",
                state={},
                changed_state=ChangedState(),
                diagnostics={
                    "payload_type": "visualization_summary",
                    "available": True,
                },
            )
        raise AssertionError(f"unexpected command: {command!r}")

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command",
        fake_execute,
    )
    async_commands = []
    async_results = []

    def fake_execute_async(_panel, command, *, on_result, **_kwargs):
        async_commands.append(command)
        async_results.append(on_result)
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        fake_execute_async,
    )
    _install_panel_publication_runtime(
        monkeypatch,
        _application_query_with_saliency_state(
            PostTrainingSaliencyStatus.idle(),
            SaliencyMethodCoverageSnapshot(method="Gradient"),
        ),
    )

    panel, ctrl = _make_panel(qtbot, parent=RealMainWindow())
    ctrl.get_trainers.return_value = [service_trainer]
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()
    current_widget.update_plot.reset_mock()

    panel.update_panel()

    current_widget.update_plot.assert_not_called()
    current_widget.show_message.assert_called_with(
        "Gradient saliency has not been computed for this run. "
        "Use Compute Saliency to continue."
    )
    assert async_commands == []
    assert panel.saliency_action_bar.isVisibleTo(panel)
    assert panel.saliency_action_title.text() == "Saliency not computed yet"
    assert panel.saliency_action_detail.text() == (
        "Use Compute Saliency to prepare Gradient + Gradient * Input."
    )
    assert panel.compute_saliency_btn.text() == "Compute Saliency"

    panel.compute_saliency_btn.click()

    assert len(async_commands) == 1
    command = async_commands[0]
    assert isinstance(command, SaliencyCommand)
    assert command.method == "Gradient"
    assert command.params == {
        "profile": "recommended",
        "methods": ["Gradient", "Gradient * Input"],
    }
    assert panel.compute_saliency_btn.text() == "Computing..."

    async_results[0](
        CommandResult.success_result(
            command_name="saliency",
            message="Saliency computation completed without class output.",
            state={},
            changed_state=ChangedState(),
        )
    )

    assert len(async_commands) == 1
    assert panel.compute_saliency_btn.text() == "Compute Saliency"
    current_widget.show_message.assert_called_with("Computing saliency...")


def test_visualization_panel_compute_button_uses_recommended_profile(
    qtbot,
    monkeypatch,
):
    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    service_trainer = _make_trainer("EEGNet", repeats=1)
    service_trainer.get_plans.return_value[
        0
    ].get_eval_record.return_value = _make_eval_record_without_saliency()
    async_commands = []
    async_kwargs = []

    def fake_execute(_panel, command, **_kwargs):
        if isinstance(command, SaliencyCommand):
            return CommandResult.success_result(
                command_name="saliency",
                message="Saliency parameters are not configured yet.",
                state={},
                changed_state=ChangedState(),
                diagnostics={
                    "payload_type": "saliency_summary",
                    "saliency_available": False,
                    "configure_available": True,
                },
            )
        if isinstance(command, VisualizeCommand):
            return CommandResult.success_result(
                command_name="visualize",
                message="Visualization summary ready.",
                state={},
                changed_state=ChangedState(),
                diagnostics={
                    "payload_type": "visualization_summary",
                    "available": True,
                },
            )
        raise AssertionError(f"unexpected command: {command!r}")

    def fake_execute_async(_panel, command, *, on_result, **_kwargs):
        del on_result
        async_commands.append(command)
        async_kwargs.append(_kwargs)
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command",
        fake_execute,
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        fake_execute_async,
    )
    _install_panel_publication_runtime(
        monkeypatch,
        _application_query_with_saliency_state(
            PostTrainingSaliencyStatus.idle(),
            SaliencyMethodCoverageSnapshot(method="Gradient"),
        ),
    )

    panel, ctrl = _make_panel(qtbot, parent=RealMainWindow())
    ctrl.get_trainers.return_value = [service_trainer]
    panel.update_panel()

    panel.compute_saliency_btn.click()

    assert len(async_commands) == 1
    command = async_commands[0]
    assert isinstance(command, SaliencyCommand)
    assert command.method == "Gradient"
    assert command.params == {
        "profile": "recommended",
        "methods": ["Gradient", "Gradient * Input"],
    }
    publication = panel._application_view_publication
    assert publication is not None
    assert async_kwargs[0]["expected_publication_generation"] == (
        publication.generation
    )
    assert panel.compute_saliency_btn.text() == "Computing..."


def test_saliency_resource_preflight_safe_dispatches_once_without_confirmation(
    qtbot,
    monkeypatch,
):
    panel, _ctrl = _make_panel(qtbot)
    current_widget = _current_mock_widget(panel)
    commands: list[SaliencyCommand] = []
    callbacks = []

    def fake_execute_async(_panel, command, *, on_result, **_kwargs):
        commands.append(command)
        callbacks.append(on_result)
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        fake_execute_async,
    )
    question = MagicMock(side_effect=AssertionError("safe preflight must not prompt"))
    monkeypatch.setattr(QMessageBox, "question", question)
    params = {"profile": "recommended", "methods": ["Gradient"]}

    assert panel._start_saliency_compute(
        params=params,
        method_name="Gradient",
        current_widget=current_widget,
        attempt_key=("safe-resource-preflight",),
    )
    assert len(commands) == 1
    assert commands[0].resource_preflight_confirmed is False
    assert commands[0].resource_preflight_token is None

    outcome = callbacks[0](
        CommandResult.success_result(
            command_name="saliency",
            message="Saliency parameters configured.",
            state={},
            changed_state=ChangedState(),
            diagnostics={
                "resource_preflight": {
                    "schema_version": 1,
                    "risk_level": "safe",
                    "requires_confirmation": False,
                    "message": "Saliency resource check passed.",
                }
            },
        )
    )

    assert outcome.status is InteractionStatus.COMPLETED
    assert len(commands) == 1
    question.assert_not_called()


@pytest.mark.parametrize("risk_level", ["warning", "unknown"])
def test_saliency_resource_preflight_approval_uses_host_receipt_not_param_token(
    qtbot,
    monkeypatch,
    risk_level,
):
    panel, _ctrl = _make_panel(qtbot)
    current_widget = _current_mock_widget(panel)
    commands: list[SaliencyCommand] = []
    callbacks = []

    def fake_execute_async(_panel, command, *, on_result, **_kwargs):
        commands.append(command)
        callbacks.append(on_result)
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        fake_execute_async,
    )
    question = MagicMock(return_value=QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "question", question)
    params = {
        "profile": "recommended",
        "methods": ["Gradient"],
        "resource_preflight_confirmed": True,
        "resource_preflight_token": "untrusted-model-token",
    }
    host_token = f"host-{risk_level}-receipt"
    resource_message = f"Host resource message for {risk_level}."

    assert panel._start_saliency_compute(
        params=params,
        method_name="Gradient",
        current_widget=current_widget,
        attempt_key=("confirmed-resource-preflight", risk_level),
    )
    first_outcome = callbacks[0](
        _saliency_resource_failure(
            risk_level,
            receipt_id=host_token,
            message=resource_message,
        )
    )

    assert first_outcome.status is InteractionStatus.ACCEPTED
    assert len(commands) == 2
    initial, confirmed = commands
    assert initial.resource_preflight_confirmed is False
    assert initial.resource_preflight_token is None
    assert confirmed.resource_preflight_confirmed is True
    assert confirmed.resource_preflight_token == host_token
    assert confirmed.resource_preflight_token != params["resource_preflight_token"]
    assert confirmed.method == initial.method == "Gradient"
    assert confirmed.params == initial.params == params
    question.assert_called_once()
    assert resource_message in question.call_args.args[2]

    second_outcome = callbacks[1](
        CommandResult.success_result(
            command_name="saliency",
            message="Saliency parameters configured.",
            state={},
            changed_state=ChangedState(),
        )
    )

    assert second_outcome.status is InteractionStatus.COMPLETED
    assert len(commands) == 2


def test_saliency_resource_preflight_cancel_does_not_mutate_evaluator(
    qtbot,
    monkeypatch,
):
    panel, _ctrl = _make_panel(qtbot)
    current_widget = _current_mock_widget(panel)
    evaluator_state: dict[str, object] = {"params": None}
    commands: list[SaliencyCommand] = []
    callbacks = []

    def fake_execute_async(_panel, command, *, on_result, **_kwargs):
        commands.append(command)
        callbacks.append(on_result)
        if command.resource_preflight_confirmed:
            evaluator_state["params"] = command.params
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        fake_execute_async,
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        MagicMock(return_value=QMessageBox.StandardButton.No),
    )

    assert panel._start_saliency_compute(
        params={"profile": "recommended", "methods": ["Gradient"]},
        method_name="Gradient",
        current_widget=current_widget,
        attempt_key=("cancelled-resource-preflight",),
    )
    outcome = callbacks[0](
        _saliency_resource_failure("warning", receipt_id="cancel-receipt")
    )

    assert outcome.status is InteractionStatus.CANCELLED
    assert len(commands) == 1
    assert evaluator_state["params"] is None
    assert panel._saliency_compute_in_progress is False
    current_widget.show_error.assert_not_called()


def test_saliency_resource_preflight_blocking_does_not_dispatch_confirmation(
    qtbot,
    monkeypatch,
):
    panel, _ctrl = _make_panel(qtbot)
    current_widget = _current_mock_widget(panel)
    commands: list[SaliencyCommand] = []
    callbacks = []

    def fake_execute_async(_panel, command, *, on_result, **_kwargs):
        commands.append(command)
        callbacks.append(on_result)
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        fake_execute_async,
    )
    question = MagicMock(side_effect=AssertionError("blocking must not prompt"))
    critical = MagicMock()
    monkeypatch.setattr(QMessageBox, "question", question)
    monkeypatch.setattr(QMessageBox, "critical", critical)
    resource_message = "Saliency exceeds the available memory limit."

    assert panel._start_saliency_compute(
        params={"profile": "recommended", "methods": ["Gradient"]},
        method_name="Gradient",
        current_widget=current_widget,
        attempt_key=("blocking-resource-preflight",),
    )
    outcome = callbacks[0](
        _saliency_resource_failure("blocking", message=resource_message)
    )

    assert outcome.status is InteractionStatus.BLOCKED
    assert len(commands) == 1
    question.assert_not_called()
    critical.assert_called_once_with(panel, "Saliency Resource Check", resource_message)


def test_saliency_resource_preflight_rejects_mismatched_host_challenge(
    qtbot,
    monkeypatch,
):
    panel, _ctrl = _make_panel(qtbot)
    current_widget = _current_mock_widget(panel)
    commands: list[SaliencyCommand] = []
    callbacks = []

    def fake_execute_async(_panel, command, *, on_result, **_kwargs):
        commands.append(command)
        callbacks.append(on_result)
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        fake_execute_async,
    )
    question = MagicMock(side_effect=AssertionError("mismatched receipt must fail"))
    monkeypatch.setattr(QMessageBox, "question", question)

    assert panel._start_saliency_compute(
        params={"profile": "recommended", "methods": ["Gradient"]},
        method_name="Gradient",
        current_widget=current_widget,
        attempt_key=("mismatched-resource-preflight",),
    )
    outcome = callbacks[0](
        _saliency_resource_failure(
            "warning",
            receipt_id="training-receipt",
            challenge_command="start_training",
        )
    )

    assert outcome.status is InteractionStatus.FAILED
    assert "could not be confirmed safely" in outcome.message.lower()
    assert len(commands) == 1
    question.assert_not_called()


def test_saliency_resource_preflight_rejected_receipt_never_retries_twice(
    qtbot,
    monkeypatch,
):
    panel, _ctrl = _make_panel(qtbot)
    current_widget = _current_mock_widget(panel)
    commands: list[SaliencyCommand] = []
    callbacks = []

    def fake_execute_async(_panel, command, *, on_result, **_kwargs):
        commands.append(command)
        callbacks.append(on_result)
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        fake_execute_async,
    )
    question = MagicMock(return_value=QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "question", question)

    assert panel._start_saliency_compute(
        params={"profile": "recommended", "methods": ["Gradient"]},
        method_name="Gradient",
        current_widget=current_widget,
        attempt_key=("one-shot-resource-preflight",),
    )
    first_outcome = callbacks[0](
        _saliency_resource_failure("warning", receipt_id="first-receipt")
    )
    assert first_outcome.status is InteractionStatus.ACCEPTED
    assert len(commands) == 2

    rejected_outcome = callbacks[1](
        _saliency_resource_failure("warning", receipt_id="replacement-receipt")
    )

    assert rejected_outcome.status is InteractionStatus.FAILED
    assert "no longer valid" in rejected_outcome.message.lower()
    assert len(commands) == 2
    question.assert_called_once()
    assert panel._saliency_compute_in_progress is False


@pytest.mark.parametrize("startup_failure", ["returned_false", "raised"])
def test_visualization_panel_saliency_startup_failure_restores_retryable_action(
    qtbot,
    monkeypatch,
    startup_failure,
):
    class RealMainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.study = Study()

    dispatch_count = 0

    def fake_execute_async(*_args, **_kwargs):
        nonlocal dispatch_count
        dispatch_count += 1
        if dispatch_count > 1:
            return True
        if startup_failure == "raised":
            raise RuntimeError("worker setup failed")
        return False

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        fake_execute_async,
    )
    main_window = RealMainWindow()
    panel, _ctrl = _make_panel(qtbot, parent=main_window)
    current_widget = _current_mock_widget(panel)
    attempt_key = ("manual", "Fold 1", "Run 1", "Gradient", ())

    started = panel._start_saliency_compute(
        params={"methods": ["Gradient"]},
        method_name="Gradient",
        current_widget=current_widget,
        attempt_key=attempt_key,
    )

    assert started is False
    assert attempt_key not in panel._saliency_compute_attempted
    assert panel._saliency_compute_in_progress is False
    current_widget.show_error.assert_called_once_with(
        "Saliency compute could not start. Try again."
    )
    assert panel.saliency_action_title.text() == "Saliency compute failed"
    assert panel.saliency_action_detail.text() == (
        "Saliency compute could not start. Try again."
    )
    assert panel.compute_saliency_btn.isEnabled() is True
    assert panel.compute_saliency_btn.text() == "Compute Saliency"
    status_bar = main_window.statusBar()
    assert status_bar is not None
    assert status_bar.currentMessage() == (
        "Saliency compute could not start. Try again."
    )

    retried = panel._start_saliency_compute(
        params={"methods": ["Gradient"]},
        method_name="Gradient",
        current_widget=current_widget,
        attempt_key=attempt_key,
    )

    assert retried is True
    assert dispatch_count == 2
    assert attempt_key in panel._saliency_compute_attempted
    assert panel._saliency_compute_in_progress is True
    assert panel.compute_saliency_btn.text() == "Computing..."


def test_visualization_panel_malformed_saliency_terminal_restores_retryable_action(
    qtbot,
    monkeypatch,
):
    class RealMainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.study = Study()

    result_callbacks = []

    def fake_execute_async(_panel, _command, *, on_result, **_kwargs):
        result_callbacks.append(on_result)
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        fake_execute_async,
    )
    main_window = RealMainWindow()
    panel, _ctrl = _make_panel(qtbot, parent=main_window)
    current_widget = _current_mock_widget(panel)
    attempt_key = ("manual", "Fold 1", "Run 1", "Gradient", ())

    assert panel._start_saliency_compute(
        params={"methods": ["Gradient"]},
        method_name="Gradient",
        current_widget=current_widget,
        attempt_key=attempt_key,
    )

    outcome = result_callbacks[0](object())

    assert outcome.status is InteractionStatus.FAILED
    assert attempt_key not in panel._saliency_compute_attempted
    assert panel._saliency_compute_in_progress is False
    current_widget.show_error.assert_called_once_with(
        "Saliency compute returned an invalid result. Try again."
    )
    assert panel.saliency_action_title.text() == "Saliency compute failed"
    assert panel.compute_saliency_btn.isEnabled() is True
    assert panel.compute_saliency_btn.text() == "Compute Saliency"
    status_bar = main_window.statusBar()
    assert status_bar is not None
    assert status_bar.currentMessage() == (
        "Saliency compute returned an invalid result. Try again."
    )

    assert panel._start_saliency_compute(
        params={"methods": ["Gradient"]},
        method_name="Gradient",
        current_widget=current_widget,
        attempt_key=attempt_key,
    )
    assert len(result_callbacks) == 2


def test_visualization_panel_missing_saliency_worker_shows_actionable_message(
    qtbot,
    monkeypatch,
):
    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    service_trainer = _make_trainer("EEGNet", repeats=1)
    service_trainer.get_plans.return_value[
        0
    ].get_eval_record.return_value = _make_eval_record_without_saliency()

    def fake_execute(_panel, command, **_kwargs):
        if isinstance(command, SaliencyCommand):
            return CommandResult.success_result(
                command_name="saliency",
                message="Saliency summary ready.",
                state={},
                changed_state=ChangedState(),
                diagnostics={
                    "payload_type": "saliency_summary",
                    "params": {
                        "SmoothGrad": {"nt_samples": 1},
                        "SmoothGrad_Squared": {"nt_samples": 1},
                        "VarGrad": {"nt_samples": 1},
                    },
                    "saliency_configured": True,
                    "saliency_available": False,
                    "configure_available": True,
                },
            )
        if isinstance(command, VisualizeCommand):
            return CommandResult.success_result(
                command_name="visualize",
                message="Visualization summary ready.",
                state={},
                changed_state=ChangedState(),
                diagnostics={
                    "payload_type": "visualization_summary",
                    "available": True,
                },
            )
        raise AssertionError(f"unexpected command: {command!r}")

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command",
        fake_execute,
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        lambda *_args, **_kwargs: False,
    )
    _install_panel_publication_runtime(
        monkeypatch,
        _application_query_with_saliency_state(
            PostTrainingSaliencyStatus.idle(),
            SaliencyMethodCoverageSnapshot(method="Gradient"),
        ),
    )

    panel, ctrl = _make_panel(qtbot, parent=RealMainWindow())
    ctrl.get_trainers.return_value = [service_trainer]
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()
    current_widget.update_plot.reset_mock()

    panel.update_panel()

    current_widget.update_plot.assert_not_called()
    current_widget.show_message.assert_called_with(
        "SmoothGrad saliency has not been computed for this run. "
        "Use Compute Saliency to continue."
    )
    assert panel.saliency_action_bar.isVisibleTo(panel)


def test_visualization_panel_preserves_selection_across_publication_refresh(qtbot):
    panel, ctrl = _make_panel(qtbot)
    complete = _complete_coverage()
    result = _result_with_run_coverages(
        SaliencyRunCoverageSnapshot(
            plan_index=0,
            run_index=0,
            model_name="EEGNet",
            methods=[complete],
        ),
        SaliencyRunCoverageSnapshot(
            plan_index=1,
            run_index=0,
            model_name="SCCNet",
            methods=[complete],
        ),
        SaliencyRunCoverageSnapshot(
            plan_index=1,
            run_index=1,
            model_name="SCCNet",
            methods=[complete],
        ),
    )
    _publish_panel_state(panel, result)
    panel.plan_combo.setCurrentIndex(2)
    panel.run_combo.setCurrentIndex(1)

    assert panel.plan_combo.currentText() == "Fold 2 (SCCNet)"
    assert panel.run_combo.currentText() == "Run 2"

    panel.mark_refresh_dirty()
    _publish_panel_state(panel, result)

    assert panel.plan_combo.currentText() == "Fold 2 (SCCNet)"
    assert panel.run_combo.currentText() == "Run 2"
    ctrl.get_trainers.assert_not_called()


def test_visualization_panel_shows_placeholder_without_valid_selection(qtbot):
    panel, _ctrl = _make_panel(qtbot)
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()
    current_widget.show_error.reset_mock()

    panel.on_update()

    current_widget.show_message.assert_called_once_with(
        "Select a fold and run to continue."
    )
    current_widget.show_error.assert_not_called()


def test_visualization_panel_shows_pending_montage_on_position_dependent_view(
    qtbot,
):
    panel, _ctrl = _make_panel(qtbot)
    panel.tabs.setCurrentWidget(panel.tab_topo)
    panel.last_application_query = CommandResult.success_result(
        command_name="visualize",
        message="Results available",
        state={},
        changed_state=ChangedState(),
        diagnostics={
            "payload_type": "visualization_summary",
            "available": True,
            "blocked_views": {"topographic map": ["Preparing electrode positions..."]},
        },
    )
    panel._application_summary_dirty = False
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()

    panel.refresh_combos()
    panel.on_update()

    assert current_widget.show_message.call_args_list
    assert all(
        call.args == ("Preparing electrode positions...",)
        for call in current_widget.show_message.call_args_list
    )


def test_visualization_panel_normalizes_3d_blocked_key_without_duplicate_status(
    qtbot,
    monkeypatch,
):
    panel, _ctrl = _make_panel(qtbot)
    panel.tabs.setCurrentWidget(panel.tab_3d)
    panel.last_application_query = CommandResult.success_result(
        command_name="visualize",
        message="Results available",
        state={},
        changed_state=ChangedState(),
        diagnostics={
            "payload_type": "visualization_summary",
            "available": True,
            "blocked_views": {
                "3D plot": ["Set a 3D montage before opening the 3D plot."]
            },
        },
    )
    panel._application_summary_dirty = False
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()
    statuses: list[str] = []
    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.show_status_message",
        lambda _context, message: statuses.append(message),
    )

    panel.on_update()

    expected = "Set a 3D montage before opening the 3D plot."
    current_widget.show_message.assert_called_once_with(expected)
    assert statuses == []


def test_visualization_panel_shows_setup_message_without_training_results(
    qtbot,
    monkeypatch,
):
    from XBrainLab.backend.application import SaliencyCommand, VisualizeCommand

    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    def fake_execute(_panel, command, **_kwargs):
        if isinstance(command, SaliencyCommand):
            return CommandResult.success_result(
                command_name="saliency",
                message="Saliency parameters are not configured yet.",
                state={},
                changed_state=ChangedState(),
                diagnostics={
                    "payload_type": "saliency_summary",
                    "saliency_available": False,
                    "configure_available": True,
                },
            )
        if isinstance(command, VisualizeCommand):
            return CommandResult.success_result(
                command_name="visualize",
                message="Visualization summary ready.",
                state={},
                changed_state=ChangedState(),
                diagnostics={
                    "payload_type": "visualization_summary",
                    "available": True,
                    "available_views": ["montage setup"],
                    "plot_views_available": False,
                },
            )
        raise AssertionError(f"unexpected command: {command!r}")

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command",
        fake_execute,
    )
    panel, _ctrl = _make_panel(qtbot, parent=RealMainWindow())
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()
    current_widget.show_error.reset_mock()

    panel.update_panel()

    current_widget.show_message.assert_called_with(
        "Complete training to view saliency plots. Set Montage remains available."
    )
    current_widget.show_error.assert_not_called()


def test_visualization_panel_update_panel_refreshes_combos_and_tab(qtbot):
    panel, _ctrl = _make_panel(qtbot)

    with (
        patch.object(panel, "update_info") as mock_info,
        patch.object(panel, "on_update") as mock_update,
    ):
        panel.update_panel()

    mock_info.assert_called_once()
    mock_update.assert_called_once()


def test_base_saliency_view_uses_only_injected_application_coverage(qtbot):
    from XBrainLab.ui.panels.visualization.saliency_views.base_saliency_view import (
        BaseSaliencyView,
    )

    view = BaseSaliencyView()
    qtbot.addWidget(view)
    complete = SaliencyMethodCoverageSnapshot(
        method="Gradient",
        available=True,
        complete=True,
        classes=[
            SaliencyClassCoverageSnapshot(
                class_index=0,
                display_name="left",
                available=True,
            )
        ],
    )

    with pytest.raises(ValueError, match="has not been published"):
        view.require_complete_saliency_coverage("Gradient")

    view.set_saliency_coverage(complete)
    view.require_complete_saliency_coverage("Gradient")


def test_visualization_placeholder_wraps_inside_narrow_view(qtbot):
    from XBrainLab.ui.panels.visualization.saliency_views.base_saliency_view import (
        BaseSaliencyView,
    )

    view = BaseSaliencyView()
    qtbot.addWidget(view)
    message = (
        "Create EEG epochs, complete training, or configure saliency before "
        "opening visualization views."
    )

    view.resize(360, 240)
    view.show_message(message)
    view.show()
    qtbot.wait(0)

    assert view.error_label.wordWrap()
    assert view.error_label.text() == message
    assert view.error_label.geometry().left() >= 0
    assert view.error_label.geometry().right() <= view.contentsRect().right()


def test_visualization_panel_uses_application_query_before_stale_controller_trainers(
    qtbot,
):
    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    main_window = RealMainWindow()
    panel, ctrl = _make_panel(qtbot, parent=main_window)
    ctrl.get_trainers.return_value = [_make_trainer("StaleNet", repeats=1)]
    ctrl.get_trainers.reset_mock()
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()
    current_widget.show_error.reset_mock()

    panel.update_panel()

    assert panel.last_application_query is not None
    assert panel.last_application_query.failed
    assert "Create EEG epochs, complete training, or configure saliency" in (
        panel.last_application_query.message
    )
    ctrl.get_trainers.assert_not_called()
    assert panel.plan_combo.count() == 1
    assert panel.plan_combo.itemText(0) == "Select a fold"
    assert panel.run_combo.count() == 0
    current_widget.show_message.assert_called_once_with(
        "Create EEG epochs, complete training, or configure saliency before "
        "opening visualization views."
    )
    current_widget.show_error.assert_not_called()


def test_visualization_failed_query_does_not_read_live_trainers(qtbot):
    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    panel, ctrl = _make_panel(qtbot, parent=RealMainWindow())
    stale_trainer = _make_trainer("StaleNet", repeats=1)
    ctrl.get_trainers.return_value = [stale_trainer]
    ctrl.get_trainers.reset_mock()
    panel.last_application_query = CommandResult.failure_result(
        command_name="visualize",
        message="Visualization is not ready.",
        state={},
        changed_state=ChangedState(),
        error_type=ErrorType.PRECONDITION,
        recoverable=True,
    )

    panel.refresh_combos()
    ctrl.get_trainers.assert_not_called()
    assert panel.run_combo.count() == 0


def test_visualization_panel_refuses_real_study_query_none_controller_fallback(
    qtbot,
    monkeypatch,
):
    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command",
        lambda *_args, **_kwargs: None,
    )
    panel, ctrl = _make_panel(qtbot, parent=RealMainWindow())
    ctrl.get_trainers.side_effect = AssertionError(
        "stale visualization trainers should not be read",
    )
    ctrl.get_averaged_record.side_effect = AssertionError(
        "stale averaged records should not be read",
    )
    ctrl.get_trainers.reset_mock()
    ctrl.get_averaged_record.reset_mock()

    panel.refresh_combos()

    ctrl.get_trainers.assert_not_called()
    ctrl.get_averaged_record.assert_not_called()
    assert panel.plan_combo.count() == 1
    assert panel.plan_combo.itemText(0) == "Select a fold"
    assert panel.run_combo.count() == 0


def test_visualization_panel_uses_typed_render_boundary(
    qtbot,
    monkeypatch,
):
    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    panel, ctrl = _make_panel(qtbot, parent=RealMainWindow())
    _publish_panel_state(
        panel,
        _application_query_with_saliency_state(
            PostTrainingSaliencyStatus.idle(),
            _complete_coverage(),
        ),
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.prepare_saliency_render_variants_operation",
        _prepare_render_variants,
    )

    assert panel.plan_combo.count() == 2
    assert panel.run_combo.findText("Average") == -1
    current_widget = _current_mock_widget(panel)
    current_widget.update_plot.reset_mock()
    panel.on_update()
    qtbot.waitUntil(
        lambda: current_widget.update_plot.call_count == 1
        and panel.native_render_work_idle(),
        timeout=3000,
    )

    ctrl.get_trainers.assert_not_called()
    ctrl.get_averaged_record.assert_not_called()
    current_widget.update_plot.assert_called_once()
    assert isinstance(
        current_widget.update_plot.call_args.args[0], SaliencyRenderPublication
    )


def test_visualization_panel_has_no_average_option_without_publication(
    qtbot,
    monkeypatch,
):
    from XBrainLab.backend.application import VisualizeCommand

    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    commands = []

    def fake_execute(_panel, command, **_kwargs):
        commands.append(command)
        if not isinstance(command, VisualizeCommand):
            raise AssertionError(f"unexpected command: {command!r}")
        diagnostics = {
            "payload_type": "visualization_summary",
            "available": True,
        }
        return CommandResult.success_result(
            command_name="visualize",
            message="Visualization summary ready.",
            state={},
            changed_state=ChangedState(),
            diagnostics=diagnostics,
        )

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command",
        fake_execute,
    )

    def fake_execute_async(_panel, command, *, on_result, **_kwargs):
        on_result(fake_execute(_panel, command))
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        fake_execute_async,
    )
    panel, ctrl = _make_panel(qtbot, parent=RealMainWindow())
    ctrl.get_averaged_record.side_effect = AssertionError(
        "stale averaged records should not be read",
    )

    panel.refresh_combos()

    assert commands
    assert all(set(vars(command)) == {"view"} for command in commands)

    assert all(set(vars(command)) == {"view"} for command in commands)
    assert panel.run_combo.findText("Average") == -1
    ctrl.get_trainers.assert_not_called()
    ctrl.get_averaged_record.assert_not_called()


def test_visualization_panel_unpublished_state_uses_detached_summary_query(
    qtbot,
    monkeypatch,
):
    from XBrainLab.backend.application import VisualizeCommand

    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    commands = []

    def fake_execute(_panel, command, **_kwargs):
        commands.append(command)
        if not isinstance(command, VisualizeCommand):
            raise AssertionError(f"unexpected command: {command!r}")
        return CommandResult.success_result(
            command_name="visualize",
            message="Visualization summary ready.",
            state={},
            changed_state=ChangedState(),
            diagnostics={
                "payload_type": "visualization_summary",
                "available": True,
            },
        )

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command",
        fake_execute,
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        lambda *_args, **_kwargs: False,
    )
    panel, ctrl = _make_panel(qtbot, parent=RealMainWindow())
    ctrl.get_averaged_record.side_effect = AssertionError(
        "stale averaged records should not be read",
    )

    panel.refresh_combos()
    assert commands
    assert all(set(vars(command)) == {"view"} for command in commands)
    ctrl.get_trainers.assert_not_called()
    ctrl.get_averaged_record.assert_not_called()
    assert panel.run_combo.findText("Average") == -1


def test_visualization_panel_refuses_real_study_query_none_domain_fallback(
    qtbot,
    monkeypatch,
):
    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command",
        lambda *_args, **_kwargs: None,
    )
    panel, ctrl = _make_panel(qtbot, parent=RealMainWindow())
    ctrl.get_trainers.side_effect = AssertionError(
        "stale visualization trainers should not be read",
    )
    ctrl.get_averaged_record.side_effect = AssertionError(
        "stale averaged records should not be read",
    )
    ctrl.get_averaged_record.reset_mock()
    current_widget = _current_mock_widget(panel)
    current_widget.show_error.reset_mock()
    current_widget.show_message.reset_mock()
    current_widget.update_plot.reset_mock()

    panel.on_update()

    ctrl.get_trainers.assert_not_called()
    ctrl.get_averaged_record.assert_not_called()
    current_widget.update_plot.assert_not_called()
    current_widget.show_error.assert_not_called()
    current_widget.show_message.assert_called_once_with(
        "Select a fold and run to continue."
    )


def test_visualization_panel_uses_typed_render_publication_without_live_getters(
    qtbot,
    monkeypatch,
) -> None:
    panel, controller = _make_panel(qtbot)
    controller.get_trainers.side_effect = AssertionError(
        "visualization must not read live trainers"
    )
    controller.get_averaged_record.side_effect = AssertionError(
        "visualization must not read live evaluation records"
    )
    coverage = _complete_coverage()
    result = _application_query_with_saliency_state(
        PostTrainingSaliencyStatus.idle(),
        coverage,
    )
    run_coverage = result.state.visualization.saliency_coverage[0]
    run_coverage = replace(
        run_coverage,
        plan_name="motor-imagery",
        model_name="EEGNet",
        run_name="Run 1",
    )
    result = replace(
        result,
        state=replace(
            result.state,
            visualization=replace(
                result.state.visualization,
                saliency_coverage=[run_coverage],
            ),
        ),
    )
    _publish_panel_state(panel, result)
    panel._application_summary_dirty = False
    source_publication = panel._application_view_publication
    assert source_publication is not None
    render_data = SaliencyRenderData(
        method="Gradient",
        saliency_by_class={0: np.ones((1, 2, 3))},
        class_map=((0, "left"),),
        event_ids={"left": 0},
        channel_names=("C3", "C4"),
        channel_positions=((-0.04, 0.0, 0.08), (0.04, 0.0, 0.08)),
        sfreq=128.0,
        tmin=0.0,
    )
    render_requests = []

    def get_render(
        _panel,
        operation_id,
        request,
        *,
        include_normalized,
        **_kwargs,
    ):
        render_requests.append(request)
        raw = SaliencyRenderPublication(
            request=replace(request, normalize=False),
            generation=request.publication_generation,
            training_generation=4,
            data=render_data,
            operation_id=operation_id,
        )
        return raw, None

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.prepare_saliency_render_variants_operation",
        get_render,
        raising=False,
    )
    current_widget = _current_mock_widget(panel)
    current_widget.update_plot.reset_mock()

    panel.refresh_combos()
    qtbot.waitUntil(
        lambda: current_widget.update_plot.call_count >= 1
        and panel.native_render_work_idle(),
        timeout=3000,
    )

    plan_identity = panel.plan_combo.currentData()
    run_identity = panel.run_combo.currentData()
    assert plan_identity == SaliencyPlanIdentity(plan_index=0)
    assert run_identity == SaliencyRunIdentity(
        plan=plan_identity,
        run_index=0,
    )
    assert panel.plan_combo.currentText() == "Fold 1 (EEGNet)"
    assert panel.run_combo.count() == 1
    assert panel.run_combo.findText("Average") == -1
    assert render_requests
    assert render_requests[-1].publication_generation == source_publication.generation
    assert render_requests[-1].run == run_identity
    controller.get_trainers.assert_not_called()
    controller.get_averaged_record.assert_not_called()
    current_widget.update_plot.assert_called_with(
        SaliencyRenderPublication(
            request=render_requests[-1],
            generation=source_publication.generation,
            training_generation=4,
            data=render_data,
            operation_id="render-operation",
        ),
        False,
    )
