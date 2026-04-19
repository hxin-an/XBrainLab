from __future__ import annotations

from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.utils.observer import Observable


def _widget_factory(parent=None):
    widget = QWidget(parent)
    widget.show_error = MagicMock()
    widget.update_plot = MagicMock()
    widget.repaint = MagicMock()
    return widget


def _info_panel_factory(*args, **kwargs):
    return QWidget()


def _make_panel(qtbot, training_controller=None):
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
        )
        qtbot.addWidget(panel)

    return panel, mock_ctrl


def _make_trainer(name="EEGNet", repeats=2):
    trainer = MagicMock()
    trainer.model_holder.target_model.__name__ = name
    trainer.option.repeat_num = repeats
    trainer.get_plans.return_value = [MagicMock() for _ in range(repeats)]
    return trainer


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
    current_widget = panel.tabs.currentWidget()

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
    current_widget = panel.tabs.currentWidget()
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
