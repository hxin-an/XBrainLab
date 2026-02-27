"""Coverage tests for VisualizationPanel methods: refresh_combos, on_plan_changed, on_update."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QWidget


def _make_panel(qtbot):
    """Create a VisualizationPanel with mocked dependencies."""
    mock_ctrl = MagicMock()
    mock_ctrl.get_trainers.return_value = []

    # Use real QWidget instances so QTabWidget.addTab accepts them
    def _widget_factory(parent=None):
        w = QWidget(parent)
        w.show_error = MagicMock()
        w.update_plot = MagicMock()
        w.repaint = MagicMock()
        return w

    with (
        patch(
            "XBrainLab.ui.panels.visualization.panel.ControlSidebar",
            side_effect=lambda *a, **kw: QWidget(),
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

        panel = VisualizationPanel(controller=mock_ctrl, parent=None)
        qtbot.addWidget(panel)
    return panel, mock_ctrl


@pytest.fixture
def panel_and_ctrl(qtbot):
    return _make_panel(qtbot)


class TestRefreshCombos:
    def test_no_trainers(self, panel_and_ctrl):
        panel, ctrl = panel_and_ctrl
        ctrl.get_trainers.return_value = []
        panel.refresh_combos()
        # Plan combo should only have placeholder
        assert panel.plan_combo.count() == 1

    def test_with_trainers(self, panel_and_ctrl):
        panel, ctrl = panel_and_ctrl
        trainer = MagicMock()
        trainer.model_holder.target_model.__name__ = "EEGNet"
        trainer.option.repeat_num = 3
        trainer.get_plans.return_value = [MagicMock() for _ in range(3)]
        ctrl.get_trainers.return_value = [trainer]

        panel.refresh_combos()
        # Should have "Select a plan" + "Fold 1 (EEGNet)"
        assert panel.plan_combo.count() == 2
        assert "EEGNet" in panel.plan_combo.itemText(1)

    def test_multiple_trainers(self, panel_and_ctrl):
        panel, ctrl = panel_and_ctrl
        t1 = MagicMock()
        t1.model_holder.target_model.__name__ = "EEGNet"
        t1.option.repeat_num = 1
        t1.get_plans.return_value = [MagicMock()]

        t2 = MagicMock()
        t2.model_holder.target_model.__name__ = "SCCNet"
        t2.option.repeat_num = 2
        t2.get_plans.return_value = [MagicMock(), MagicMock()]

        ctrl.get_trainers.return_value = [t1, t2]
        panel.refresh_combos()
        assert panel.plan_combo.count() == 3


class TestOnPlanChanged:
    def test_valid_plan(self, panel_and_ctrl):
        panel, _ctrl = panel_and_ctrl
        trainer = MagicMock()
        trainer.option.repeat_num = 2
        panel.friendly_map["Fold 1 (EEGNet)"] = trainer

        panel.on_plan_changed("Fold 1 (EEGNet)")
        # Run combo should have "Run 1", "Run 2", "Average"
        assert panel.run_combo.count() == 3
        assert panel.run_combo.itemText(2) == "Average"

    def test_unknown_plan(self, panel_and_ctrl):
        panel, _ = panel_and_ctrl
        panel.on_plan_changed("does not exist")
        assert panel.run_combo.count() == 0


class TestOnUpdate:
    def _setup_plan(self, panel, trainer, plan_text="Fold 1 (EEGNet)"):
        """Helper to set up a plan selection."""
        panel.friendly_map[plan_text] = trainer
        panel.plan_combo.addItem(plan_text)
        panel.plan_combo.setCurrentText(plan_text)

    def test_no_plan_selected(self, panel_and_ctrl):
        panel, _ = panel_and_ctrl
        # Default: plan_combo is "Select a plan"
        current_widget = panel.tabs.currentWidget()
        current_widget.show_error = MagicMock()
        panel.on_update()
        current_widget.show_error.assert_called_once()

    def test_run_not_selected(self, panel_and_ctrl):
        panel, _ = panel_and_ctrl
        trainer = MagicMock()
        self._setup_plan(panel, trainer)
        # run_combo is empty

        current_widget = panel.tabs.currentWidget()
        current_widget.show_error = MagicMock()
        panel.on_update()
        current_widget.show_error.assert_called_once()

    def test_average_run(self, panel_and_ctrl):
        panel, ctrl = panel_and_ctrl
        trainer = MagicMock()
        trainer.option.repeat_num = 1
        trainer.get_plans.return_value = [MagicMock()]
        self._setup_plan(panel, trainer)
        panel.run_combo.addItem("Average")
        panel.run_combo.setCurrentText("Average")

        avg_record = MagicMock()
        ctrl.get_averaged_record.return_value = avg_record

        current_widget = panel.tabs.currentWidget()
        current_widget.update_plot = MagicMock()
        current_widget.repaint = MagicMock()

        panel.on_update()
        current_widget.update_plot.assert_called_once()

    def test_average_no_record(self, panel_and_ctrl):
        panel, ctrl = panel_and_ctrl
        trainer = MagicMock()
        self._setup_plan(panel, trainer)
        panel.run_combo.addItem("Average")
        panel.run_combo.setCurrentText("Average")
        ctrl.get_averaged_record.return_value = None

        current_widget = panel.tabs.currentWidget()
        current_widget.show_error = MagicMock()

        panel.on_update()
        current_widget.show_error.assert_called_once()

    def test_specific_run(self, panel_and_ctrl):
        panel, _ctrl = panel_and_ctrl
        trainer = MagicMock()
        trainer.option.repeat_num = 2
        plan = MagicMock()
        plan.get_eval_record.return_value = MagicMock()
        trainer.get_plans.return_value = [plan, MagicMock()]
        self._setup_plan(panel, trainer)
        panel.run_combo.addItem("Run 1")
        panel.run_combo.setCurrentText("Run 1")

        current_widget = panel.tabs.currentWidget()
        current_widget.update_plot = MagicMock()
        current_widget.repaint = MagicMock()

        panel.on_update()
        current_widget.update_plot.assert_called_once()

    def test_run_no_eval_record(self, panel_and_ctrl):
        panel, _ctrl = panel_and_ctrl
        trainer = MagicMock()
        trainer.option.repeat_num = 1
        plan = MagicMock()
        plan.get_eval_record.return_value = None
        trainer.get_plans.return_value = [plan]
        self._setup_plan(panel, trainer)
        panel.run_combo.addItem("Run 1")
        panel.run_combo.setCurrentText("Run 1")

        current_widget = panel.tabs.currentWidget()
        current_widget.show_error = MagicMock()

        panel.on_update()
        current_widget.show_error.assert_called_once()

    def test_run_index_out_of_range(self, panel_and_ctrl):
        panel, _ctrl = panel_and_ctrl
        trainer = MagicMock()
        trainer.option.repeat_num = 1
        trainer.get_plans.return_value = []  # empty
        self._setup_plan(panel, trainer)
        panel.run_combo.addItem("Run 99")
        panel.run_combo.setCurrentText("Run 99")

        current_widget = panel.tabs.currentWidget()
        current_widget.show_error = MagicMock()

        panel.on_update()
        current_widget.show_error.assert_called_once()

    def test_unparseable_run_name(self, panel_and_ctrl):
        panel, _ctrl = panel_and_ctrl
        trainer = MagicMock()
        self._setup_plan(panel, trainer)
        panel.run_combo.addItem("CustomName")
        panel.run_combo.setCurrentText("CustomName")

        current_widget = panel.tabs.currentWidget()
        current_widget.show_error = MagicMock()

        panel.on_update()
        current_widget.show_error.assert_called_once()


class TestUpdatePanel:
    def test_update_panel(self, panel_and_ctrl):
        panel, _ctrl = panel_and_ctrl
        with (
            patch.object(panel, "update_info") as mock_info,
            patch.object(panel, "on_update") as mock_update,
        ):
            panel.update_panel()
            mock_info.assert_called_once()
            mock_update.assert_called_once()

    def test_update_info(self, panel_and_ctrl):
        panel, _ctrl = panel_and_ctrl
        panel.sidebar = MagicMock()
        with patch.object(panel, "refresh_combos"):
            panel.update_info()
            panel.sidebar.update_info.assert_called_once()
