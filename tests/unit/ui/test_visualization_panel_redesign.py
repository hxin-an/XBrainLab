from __future__ import annotations

from dataclasses import replace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PyQt6.QtWidgets import QGridLayout, QGroupBox, QMainWindow, QWidget

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
from XBrainLab.backend.visualization import all_saliency_methods
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
    mock_ctrl = controller if controller is not None else MagicMock()
    if controller is None:
        mock_ctrl.get_trainers.return_value = []
        mock_ctrl.get_averaged_record.return_value = MagicMock()

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
        from XBrainLab.ui.panels.visualization.panel import VisualizationPanel

        panel = VisualizationPanel(
            controller=mock_ctrl,
            training_controller=training_controller,
            parent=parent,
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
) -> PostTrainingSaliencyStatus:
    pending = PostTrainingSaliencyStatus.pending(
        generation=3,
        run=TrainingRunIdentity(trainer_id="trainer-ui", run_id=1),
        training_generation=7,
        methods=("Gradient", "Gradient * Input"),
    )
    if phase is PostTrainingSaliencyPhase.PENDING:
        return pending
    source = pending
    if phase is PostTrainingSaliencyPhase.SUCCEEDED:
        source = pending.transition(
            generation=3,
            phase=PostTrainingSaliencyPhase.RUNNING,
            message="Automatic saliency is being computed.",
        )
    return source.transition(
        generation=3,
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
) -> CommandResult:
    state = replace(
        ApplicationStateSnapshot.empty(),
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


def _result_with_run_coverages(
    *coverages: SaliencyRunCoverageSnapshot,
) -> CommandResult:
    state = replace(
        ApplicationStateSnapshot.empty(),
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
    assert panel.plan_combo.itemText(0) == "Select a plan"
    assert [
        panel.method_combo.itemText(i) for i in range(panel.method_combo.count())
    ] == (all_saliency_methods)
    assert panel.saliency_action_bar.isHidden()
    assert panel.compute_saliency_btn.text() == "Compute Saliency"
    assert panel.sidebar.btn_montage.text() == "Set Montage"
    assert panel.sidebar.btn_saliency.text() == "Saliency Settings"


def test_visualization_panel_explains_attribution_target_and_aggregation(qtbot):
    panel, _ctrl = _make_panel(qtbot)

    assert panel.explanation_context.text() == (
        "Grouped by true class label · Mean across evaluated epochs"
    )

    panel.tabs.setCurrentIndex(1)
    assert panel.explanation_context.text() == (
        "Grouped by true class label · Mean magnitude across evaluated epochs "
        "and channels"
    )

    panel.tabs.setCurrentIndex(2)
    assert panel.explanation_context.text() == (
        "Grouped by true class label · Mean across evaluated epochs and time"
    )


def test_visualization_panel_disables_absolute_when_view_is_already_nonnegative(
    qtbot,
):
    panel, _ctrl = _make_panel(qtbot)

    panel.method_combo.setCurrentText("Gradient")
    panel.tabs.setCurrentIndex(0)
    assert panel.abs_check.isEnabled()

    panel.method_combo.setCurrentText("SmoothGrad_Squared")
    assert not panel.abs_check.isEnabled()
    assert "non-negative" in panel.abs_check.toolTip()

    panel.method_combo.setCurrentText("Gradient")
    panel.tabs.setCurrentIndex(1)
    assert not panel.abs_check.isEnabled()
    assert "magnitude" in panel.abs_check.toolTip()


def test_visualization_controls_stay_in_a_compact_two_row_grid(qtbot):
    panel, _ctrl = _make_panel(qtbot)
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
    assert plan_item is not None
    assert run_item is not None
    assert method_item is not None
    assert absolute_item is not None
    assert plan_item.widget() is panel.plan_combo
    assert run_item.widget() is panel.run_combo
    assert method_item.widget() is panel.method_combo
    assert absolute_item.widget() is panel.abs_check
    assert abs(panel.plan_combo.y() - panel.run_combo.y()) <= 8
    assert abs(panel.method_combo.y() - panel.abs_check.y()) <= 8
    assert panel.plan_combo.y() < panel.method_combo.y()

    widgets = [panel.plan_combo, panel.run_combo, panel.method_combo, panel.abs_check]
    rects = [widget.geometry() for widget in widgets]
    for left_index, left_rect in enumerate(rects):
        for right_rect in rects[left_index + 1 :]:
            assert not left_rect.intersects(right_rect)


def test_visualization_controls_use_one_row_when_panel_is_wide(qtbot):
    panel, _ctrl = _make_panel(qtbot)
    panel.resize(1180, 720)
    panel.show()
    qtbot.wait(50)

    assert panel.plan_combo.y() == panel.run_combo.y()
    assert panel.plan_combo.y() == panel.method_combo.y()
    assert abs(panel.plan_combo.y() - panel.abs_check.y()) <= 8

    widgets = [panel.plan_combo, panel.run_combo, panel.method_combo, panel.abs_check]
    rects = [widget.geometry() for widget in widgets]
    for left_index, left_rect in enumerate(rects):
        for right_rect in rects[left_index + 1 :]:
            assert not left_rect.intersects(right_rect)


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
        not command.include_objects and not command.include_averaged_records
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
        not command.include_objects and not command.include_averaged_records
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
        "XBrainLab.ui.panels.visualization.panel.get_saliency_render_publication",
        side_effect=_render_publication_for_request,
    ):
        panel.plan_combo.setCurrentIndex(2)

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
        "XBrainLab.ui.panels.visualization.panel.get_saliency_render_publication",
        side_effect=_render_publication_for_request,
    ):
        panel.on_update()

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
        "XBrainLab.ui.panels.visualization.panel.get_saliency_render_publication",
        side_effect=_render_publication_for_request,
    ):
        panel.on_update()

    model = cast(Any, panel.method_combo.model())
    gradient_item = model.item(panel.method_combo.findText("Gradient"))
    gradient_input_item = model.item(
        panel.method_combo.findText("Gradient * Input"),
    )
    assert gradient_item.isEnabled() is False
    assert "missing for: right" in gradient_item.toolTip()
    assert gradient_input_item.isEnabled() is True
    assert panel.method_combo.currentText() == "Gradient * Input"

    with patch(
        "XBrainLab.ui.panels.visualization.panel.get_saliency_render_publication",
        side_effect=_render_publication_for_request,
    ):
        panel.tabs.setCurrentIndex(3)
        gradient_item = model.item(panel.method_combo.findText("Gradient"))
        assert gradient_item.isEnabled() is True
        panel.method_combo.setCurrentText("Gradient")
        current_widget = _current_mock_widget(panel)
        current_widget.update_plot.reset_mock()
        panel.on_update()

    current_widget.update_plot.assert_called_once()


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


def test_visualization_panel_terminal_observer_refreshes_once_without_polling(
    qtbot,
    monkeypatch,
):
    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    controller = cast(Any, Observable())
    controller.get_trainers = MagicMock(return_value=[])
    controller.get_averaged_record = MagicMock()
    parent = RealMainWindow()
    panel, _ctrl = _make_panel(
        qtbot,
        parent=parent,
        controller=controller,
    )
    cast(Any, parent).visualization_panel = panel
    mark_refresh_dirty = MagicMock()
    update_panel = MagicMock()
    panel.mark_refresh_dirty = mark_refresh_dirty
    panel.update_panel = update_panel
    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        MagicMock(side_effect=AssertionError("terminal refresh must not poll")),
    )

    controller.notify("saliency_changed")
    qtbot.waitUntil(lambda: update_panel.call_count == 1, timeout=1000)

    mark_refresh_dirty.assert_called_once_with()
    update_panel.assert_called_once_with()
    assert not hasattr(panel, "_saliency_status_timer")
    assert not hasattr(panel, "_poll_saliency_status")


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
        "XBrainLab.ui.panels.visualization.panel.get_saliency_render_publication",
        side_effect=_render_publication_for_request,
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
        "XBrainLab.ui.panels.visualization.panel.get_saliency_render_publication",
        side_effect=_render_publication_for_request,
    ):
        panel.on_update()

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
    current_widget.show_message.assert_called_with("Select a plan and run to continue.")
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


def test_staged_saliency_settings_run_only_from_explicit_compute(
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

    panel.stage_saliency_params(
        params,
        publication_generation=publication.generation,
        run_identity=run_identity,
        model_name="EEGNet",
    )

    assert starts == []
    assert panel.method_combo.currentText() == "VarGrad"
    assert panel.compute_saliency_btn.text() == "Recompute Saliency"

    panel._compute_saliency_from_action_bar()

    assert len(starts) == 1
    assert starts[0]["method_name"] == "VarGrad"
    assert starts[0]["params"] == params


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
    current_widget.show_message.assert_called_with(
        "Gradient saliency has not been computed for this run. "
        "Use Compute Saliency to continue."
    )


def test_visualization_panel_does_not_duplicate_application_saliency_after_training(
    qtbot,
    monkeypatch,
):
    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    training_controller = Observable()
    async_commands = []

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
                    "saliency_configured": False,
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
    panel, _ctrl = _make_panel(
        qtbot,
        training_controller=training_controller,
        parent=RealMainWindow(),
    )

    with patch.object(panel, "update_panel"):
        training_controller.notify("training_stopped")
        qtbot.wait(50)

    assert async_commands == []


def test_visualization_panel_invalidates_previous_saliency_status_on_training_start(
    qtbot,
):
    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    training_controller = Observable()
    panel, _ctrl = _make_panel(
        qtbot,
        training_controller=training_controller,
        parent=RealMainWindow(),
    )
    complete = SaliencyMethodCoverageSnapshot(
        method="Gradient",
        available=True,
        complete=True,
    )
    _publish_panel_state(
        panel,
        _application_query_with_saliency_state(
            _post_training_saliency_status(PostTrainingSaliencyPhase.SUCCEEDED),
            complete,
        ),
    )
    panel._application_summary_dirty = False

    with patch.object(panel, "update_panel"):
        training_controller.notify("training_started")
        qtbot.wait(50)

    assert panel._application_summary_dirty is True
    assert panel._saliency_summary_dirty is True


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
        "Gradient saliency has not been computed for this run. "
        "Use Compute Saliency to continue."
    )
    assert panel.saliency_action_bar.isVisibleTo(panel)


def test_visualization_panel_preserves_selection_on_training_stopped(qtbot):
    training_controller = Observable()
    panel, ctrl = _make_panel(qtbot, training_controller=training_controller)
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


def test_visualization_panel_training_stopped_never_replays_advanced_settings(
    qtbot,
    monkeypatch,
):
    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    training_controller = Observable()
    configured_params = {
        "SmoothGrad": {"nt_samples": 2},
        "SmoothGrad_Squared": {"nt_samples": 2},
        "VarGrad": {"nt_samples": 2},
    }
    async_commands = []

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
    panel, _ctrl = _make_panel(
        qtbot,
        training_controller=training_controller,
        parent=RealMainWindow(),
    )

    with patch.object(panel, "update_panel"):
        training_controller.notify("training_stopped")
        qtbot.wait(50)

    assert async_commands == []


def test_visualization_panel_shows_placeholder_without_valid_selection(qtbot):
    panel, _ctrl = _make_panel(qtbot)
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()
    current_widget.show_error.reset_mock()

    panel.on_update()

    current_widget.show_message.assert_called_once_with(
        "Select a plan and run to continue."
    )
    current_widget.show_error.assert_not_called()


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
        "Create epochs, complete training, or configure saliency before "
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
    assert "Create epochs, complete training, or configure saliency" in (
        panel.last_application_query.message
    )
    ctrl.get_trainers.assert_not_called()
    assert panel.plan_combo.count() == 1
    assert panel.plan_combo.itemText(0) == "Select a plan"
    assert panel.run_combo.count() == 0
    current_widget.show_message.assert_called_once_with(
        "Create epochs, complete training, or configure saliency before "
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
    assert panel.plan_combo.itemText(0) == "Select a plan"
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
        "XBrainLab.ui.panels.visualization.panel.get_saliency_render_publication",
        _render_publication_for_request,
    )

    assert panel.plan_combo.count() == 2
    assert panel.run_combo.findText("Average") == -1
    current_widget = _current_mock_widget(panel)
    current_widget.update_plot.reset_mock()
    panel.on_update()

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
    assert all(
        not command.include_objects and not command.include_averaged_records
        for command in commands
    )

    assert all(
        not command.include_objects and not command.include_averaged_records
        for command in commands
    )
    assert panel.run_combo.findText("Average") == -1
    ctrl.get_trainers.assert_not_called()
    ctrl.get_averaged_record.assert_not_called()


def test_visualization_panel_unpublished_state_never_starts_object_query(
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
    assert all(
        not command.include_objects and not command.include_averaged_records
        for command in commands
    )
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
        "Select a plan and run to continue."
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

    def get_render(_panel, request, **_kwargs):
        render_requests.append(request)
        return SaliencyRenderPublication(
            request=request,
            generation=request.publication_generation,
            training_generation=4,
            data=render_data,
        )

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.get_saliency_render_publication",
        get_render,
        raising=False,
    )
    current_widget = _current_mock_widget(panel)
    current_widget.update_plot.reset_mock()

    panel.refresh_combos()

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
        ),
        False,
    )
