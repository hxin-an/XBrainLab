from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
from PyQt6.QtWidgets import QGridLayout, QGroupBox, QWidget

from XBrainLab.backend.application import SaliencyCommand, VisualizeCommand
from XBrainLab.backend.application.results import ChangedState, CommandResult, ErrorType
from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.observer import Observable


def _widget_factory(parent=None):
    widget = QWidget(parent)
    mock_widget = cast(Any, widget)
    mock_widget.show_error = MagicMock()
    mock_widget.show_message = MagicMock()
    mock_widget.update_plot = MagicMock()
    mock_widget.repaint = MagicMock()
    return widget


def _info_panel_factory(*args, **kwargs):
    return QWidget()


def _make_panel(qtbot, training_controller=None, parent=None):
    mock_ctrl = MagicMock()
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


def _make_eval_record_without_saliency():
    record = MagicMock()
    record.gradient = {}
    record.gradient_input = {}
    record.smoothgrad = {}
    record.smoothgrad_sq = {}
    record.vargrad = {}
    return record


def _current_mock_widget(panel) -> Any:
    widget = panel.tabs.currentWidget()
    assert widget is not None
    return cast(Any, widget)


def test_visualization_panel_layout_and_sidebar(qtbot):
    panel, _ctrl = _make_panel(qtbot)

    assert panel.tabs.count() == 4
    assert panel.plan_combo.itemText(0) == "Select a plan"
    assert panel.method_combo.count() >= 3
    assert panel.sidebar.btn_montage.text() == "Set Montage"
    assert panel.sidebar.btn_saliency.text() == "Saliency Settings"
    assert panel.sidebar.btn_export.isHidden()


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
                    "trainer_objects": [],
                    "averaged_records": [],
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

    panel.mark_refresh_dirty()
    panel.update_panel()

    assert [type(command) for command in calls] == [
        SaliencyCommand,
        VisualizeCommand,
        SaliencyCommand,
        VisualizeCommand,
    ]


def test_visualization_panel_populates_controls_for_multiple_trainers(qtbot):
    panel, ctrl = _make_panel(qtbot)
    ctrl.get_trainers.return_value = [
        _make_trainer("EEGNet", repeats=2),
        _make_trainer("SCCNet", repeats=2),
    ]

    panel.refresh_combos()

    assert panel.plan_combo.count() == 3
    assert panel.plan_combo.currentText() == "Fold 1 (EEGNet)"
    assert panel.run_combo.count() == 3

    panel.plan_combo.setCurrentIndex(2)

    assert panel.plan_combo.currentText() == "Fold 2 (SCCNet)"
    assert panel.run_combo.count() == 3
    assert panel.run_combo.itemText(2) == "Average"


def test_visualization_panel_dispatches_default_run_when_fold_changes(qtbot):
    panel, ctrl = _make_panel(qtbot)
    first_trainer = _make_trainer("EEGNet", repeats=2)
    second_trainer = _make_trainer("SCCNet", repeats=2)
    second_plan = second_trainer.get_plans.return_value[0]
    second_eval_record = _make_eval_record_with_saliency()
    second_plan.get_eval_record.return_value = second_eval_record
    ctrl.get_trainers.return_value = [first_trainer, second_trainer]

    panel.refresh_combos()
    panel.tabs.setCurrentIndex(0)
    current_widget = _current_mock_widget(panel)
    current_widget.update_plot.reset_mock()

    panel.plan_combo.setCurrentIndex(2)

    current_widget.update_plot.assert_called()
    args, _kwargs = current_widget.update_plot.call_args
    assert args[0] is second_plan
    assert args[1] is second_trainer
    assert args[4] is second_eval_record


def test_visualization_panel_dispatches_plot_update_to_active_tab(qtbot):
    panel, ctrl = _make_panel(qtbot)
    trainer = _make_trainer("EEGNet", repeats=2)
    eval_record = _make_eval_record_with_saliency()
    trainer.get_plans.return_value[0].get_eval_record.return_value = eval_record
    ctrl.get_trainers.return_value = [trainer]

    panel.refresh_combos()
    panel.tabs.setCurrentIndex(0)
    panel.plan_combo.setCurrentIndex(1)
    panel.run_combo.setCurrentIndex(0)
    current_widget = _current_mock_widget(panel)
    current_widget.update_plot.reset_mock()

    panel.on_update()

    current_widget.update_plot.assert_called_once()
    args, _kwargs = current_widget.update_plot.call_args
    assert args[0] is trainer.get_plans.return_value[0]
    assert args[1] is trainer
    assert args[4] is eval_record


def test_visualization_panel_computes_configured_saliency_on_demand(
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
                    "trainer_objects": [service_trainer],
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

    panel, _ctrl = _make_panel(qtbot, parent=RealMainWindow())
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()
    current_widget.update_plot.reset_mock()

    panel.update_panel()

    assert len(async_commands) == 1
    command = async_commands[0]
    assert isinstance(command, SaliencyCommand)
    assert command.method == "Gradient"
    assert command.params == configured_params
    current_widget.update_plot.assert_not_called()
    current_widget.show_message.assert_called_with("Computing saliency...")


def test_visualization_panel_unconfigured_saliency_shows_actionable_message(
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
                    "trainer_objects": [service_trainer],
                },
            )
        raise AssertionError(f"unexpected command: {command!r}")

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command",
        fake_execute,
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unconfigured saliency should not auto-compute")
        ),
    )

    panel, _ctrl = _make_panel(qtbot, parent=RealMainWindow())
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()
    current_widget.update_plot.reset_mock()

    panel.update_panel()

    current_widget.update_plot.assert_not_called()
    current_widget.show_message.assert_called_with(
        "Saliency has not been computed for this run. "
        "Use Saliency Settings to compute it."
    )


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
                    "trainer_objects": [service_trainer],
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

    panel, _ctrl = _make_panel(qtbot, parent=RealMainWindow())
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()
    current_widget.update_plot.reset_mock()

    panel.update_panel()

    current_widget.update_plot.assert_not_called()
    current_widget.show_message.assert_called_with(
        "Saliency has not been computed for this run. "
        "Use Saliency Settings to compute it."
    )


def test_visualization_panel_preserves_selection_on_training_stopped(qtbot):
    training_controller = Observable()
    panel, ctrl = _make_panel(qtbot, training_controller=training_controller)
    ctrl.get_trainers.return_value = [
        _make_trainer("EEGNet", repeats=2),
        _make_trainer("SCCNet", repeats=2),
    ]

    panel.refresh_combos()
    panel.plan_combo.setCurrentIndex(2)
    panel.run_combo.setCurrentIndex(2)

    assert panel.plan_combo.currentText() == "Fold 2 (SCCNet)"
    assert panel.run_combo.currentText() == "Average"

    training_controller.notify("training_stopped")
    qtbot.wait(50)

    assert panel.plan_combo.currentText() == "Fold 2 (SCCNet)"
    assert panel.run_combo.currentText() == "Average"


def test_visualization_panel_starts_configured_saliency_after_training_stopped(
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
                    "trainer_objects": [],
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

    assert len(async_commands) == 1
    assert isinstance(async_commands[0], SaliencyCommand)
    assert async_commands[0].params == configured_params


def test_visualization_panel_shows_placeholder_without_valid_selection(qtbot):
    panel, _ctrl = _make_panel(qtbot)
    current_widget = _current_mock_widget(panel)
    current_widget.show_error.reset_mock()

    panel.on_update()

    current_widget.show_error.assert_called_once_with("Please select a Plan and Run.")


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
                    "trainer_objects": [],
                    "averaged_records": [],
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
    current_widget.show_error.assert_called()


def test_visualization_get_trainers_does_not_fallback_after_failed_query(qtbot):
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

    assert panel.get_trainers() == []
    ctrl.get_trainers.assert_not_called()


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


def test_visualization_panel_uses_application_payload_before_stale_controller(
    qtbot,
    monkeypatch,
):
    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    service_trainer = _make_trainer("ServiceNet", repeats=1)
    average_record = MagicMock()
    query_result = CommandResult.success_result(
        command_name="visualize",
        message="Visualization summary ready.",
        state={},
        changed_state=ChangedState(),
        diagnostics={
            "payload_type": "visualization_summary",
            "available": True,
            "trainer_objects": [service_trainer],
            "averaged_records": [average_record],
        },
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command",
        lambda *_args, **_kwargs: query_result,
    )
    panel, ctrl = _make_panel(qtbot, parent=RealMainWindow())
    ctrl.get_trainers.return_value = [_make_trainer("StaleNet", repeats=1)]
    ctrl.get_averaged_record.return_value = MagicMock()
    ctrl.get_trainers.reset_mock()
    ctrl.get_averaged_record.reset_mock()

    panel.refresh_combos()

    ctrl.get_trainers.assert_not_called()
    assert panel.plan_combo.count() == 2
    assert panel.plan_combo.itemText(1) == "Fold 1 (ServiceNet)"

    panel.run_combo.setCurrentText("Average")
    current_widget = _current_mock_widget(panel)
    current_widget.update_plot.reset_mock()
    panel.on_update()

    ctrl.get_averaged_record.assert_not_called()
    current_widget.update_plot.assert_called()
    args, _kwargs = current_widget.update_plot.call_args
    assert args[1] is service_trainer
    assert args[4] is average_record


def test_visualization_panel_loads_average_record_only_on_average_selection(
    qtbot,
    monkeypatch,
):
    from XBrainLab.backend.application import VisualizeCommand

    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    service_trainer = _make_trainer("ServiceNet", repeats=1)
    average_record = MagicMock()
    commands = []

    def fake_execute(_panel, command, **_kwargs):
        commands.append(command)
        if not isinstance(command, VisualizeCommand):
            raise AssertionError(f"unexpected command: {command!r}")
        diagnostics = {
            "payload_type": "visualization_summary",
            "available": True,
            "trainer_objects": [service_trainer],
        }
        if command.include_averaged_records:
            diagnostics["averaged_records"] = [average_record]
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
    assert all(not command.include_averaged_records for command in commands)

    current_widget = _current_mock_widget(panel)
    current_widget.update_plot.reset_mock()
    panel.run_combo.setCurrentText("Average")

    assert any(command.include_averaged_records for command in commands)
    current_widget.update_plot.assert_called()
    args, _kwargs = current_widget.update_plot.call_args
    assert args[4] is average_record
    ctrl.get_averaged_record.assert_not_called()


def test_visualization_panel_does_not_sync_load_average_when_worker_unavailable(
    qtbot,
    monkeypatch,
):
    from XBrainLab.backend.application import VisualizeCommand

    class RealMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.study = Study()

    service_trainer = _make_trainer("ServiceNet", repeats=1)
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
                "trainer_objects": [service_trainer],
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
    current_widget = _current_mock_widget(panel)
    current_widget.show_message.reset_mock()
    current_widget.update_plot.reset_mock()

    panel.run_combo.setCurrentText("Average")

    assert commands
    assert all(not command.include_averaged_records for command in commands)
    ctrl.get_averaged_record.assert_not_called()
    current_widget.update_plot.assert_not_called()
    current_widget.show_message.assert_called_with(
        "Average saliency could not start in the background. "
        "Try again after the current operation finishes."
    )


def test_visualization_panel_refuses_real_study_query_none_average_fallback(
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
    trainer = _make_trainer("StaleNet", repeats=1)
    ctrl.get_averaged_record.side_effect = AssertionError(
        "stale averaged records should not be read",
    )
    ctrl.get_averaged_record.reset_mock()
    panel.friendly_map = {"Fold 1 (StaleNet)": trainer}
    panel.plan_combo.clear()
    panel.plan_combo.addItem("Fold 1 (StaleNet)", trainer)
    panel.run_combo.clear()
    panel.run_combo.addItem("Average", "average")
    current_widget = _current_mock_widget(panel)
    current_widget.show_error.reset_mock()
    current_widget.update_plot.reset_mock()

    panel.on_update()

    ctrl.get_averaged_record.assert_not_called()
    current_widget.update_plot.assert_not_called()
    current_widget.show_error.assert_called_once_with("No finished runs to average.")
