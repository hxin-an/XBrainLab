from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.application.results import ChangedState, CommandResult, ErrorType
from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.observer import Observable


def _widget_factory(parent=None):
    widget = QWidget(parent)
    mock_widget = cast(Any, widget)
    mock_widget.show_error = MagicMock()
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
    assert panel.sidebar.btn_export.text() == "Export Saliency"


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


def test_visualization_panel_dispatches_plot_update_to_active_tab(qtbot):
    panel, ctrl = _make_panel(qtbot)
    trainer = _make_trainer("EEGNet", repeats=2)
    eval_record = MagicMock()
    trainer.get_plans.return_value[0].get_eval_record.return_value = eval_record
    ctrl.get_trainers.return_value = [trainer]

    panel.refresh_combos()
    panel.tabs.setCurrentIndex(0)
    panel.plan_combo.setCurrentIndex(1)
    panel.run_combo.setCurrentIndex(0)
    current_widget = _current_mock_widget(panel)

    panel.on_update()

    current_widget.update_plot.assert_called_once()
    args, _kwargs = current_widget.update_plot.call_args
    assert args[0] is trainer.get_plans.return_value[0]
    assert args[1] is trainer
    assert args[4] is eval_record


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


def test_visualization_panel_shows_placeholder_without_valid_selection(qtbot):
    panel, _ctrl = _make_panel(qtbot)
    current_widget = _current_mock_widget(panel)
    current_widget.show_error.reset_mock()

    panel.on_update()

    current_widget.show_error.assert_called_once_with("Please select a Plan and Run.")


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
