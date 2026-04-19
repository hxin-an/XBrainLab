from unittest.mock import MagicMock

from matplotlib.figure import Figure
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QSplitter,
    QWidget,
)

from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.panels.evaluation.confusion_matrix import ConfusionMatrixWidget
from XBrainLab.ui.panels.evaluation.metrics_bar_chart import MetricsBarChartWidget
from XBrainLab.ui.panels.evaluation.metrics_table import MetricsTableWidget
from XBrainLab.ui.panels.evaluation.panel import EvaluationPanel


# Mock classes
class MockEvalRecord:
    def __init__(self):
        self.output = MagicMock()
        self.label = MagicMock()

    def get_per_class_metrics(self):
        return {
            0: {
                "precision": 0.8,
                "recall": 0.9,
                "f1-score": 0.85,
                "support": 10,
            },
            1: {
                "precision": 0.7,
                "recall": 0.6,
                "f1-score": 0.65,
                "support": 10,
            },
            "macro_avg": {
                "precision": 0.75,
                "recall": 0.75,
                "f1-score": 0.75,
                "support": 20,
            },
        }


class MockTrainRecord:
    def __init__(self, finished=True):
        self.finished = finished
        self.eval_record = MockEvalRecord() if finished else None
        self.dataset = MagicMock()

    def is_finished(self):
        return self.finished

    def get_confusion_figure(self, show_percentage=False):
        # Return a dummy figure

        return Figure()


class MockPlanHolder:
    def __init__(self, name="Test Plan"):
        self.name = name
        self.records = [MockTrainRecord(True), MockTrainRecord(False)]

    def get_name(self):
        return self.name

    def get_plans(self):
        return self.records


class MockTrainer:
    def __init__(self):
        self.training_plan_holders = [
            MockPlanHolder("Plan A"),
            MockPlanHolder("Plan B"),
        ]

    def get_training_plan_holders(self):
        return self.training_plan_holders


class MockStudy:
    def __init__(self):
        self.trainer = MockTrainer()
        self.loaded_data_list = []
        self.preprocessed_data_list = []

    def get_controller(self, name):
        if name == "evaluation":
            controller = MagicMock()
            controller.get_plans.return_value = self.trainer.get_training_plan_holders()
            controller.get_model_summary_str.return_value = "Mock Summary"
            controller.get_loaded_data_list.return_value = self.loaded_data_list
            controller.get_preprocessed_data_list.return_value = (
                self.preprocessed_data_list
            )
            return controller
        return MagicMock()


class MockMainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.study = MockStudy()


def test_evaluation_panel_layout(qtbot):
    """Test the layout of the redesigned EvaluationPanel."""
    main_window = MockMainWindow()
    controller = main_window.study.get_controller("evaluation")
    panel = EvaluationPanel(controller=controller, parent=main_window)
    qtbot.addWidget(panel)

    # Check Splitter (Should be None now)
    splitter = panel.findChild(QSplitter)
    assert splitter is None

    # Check Groups existence
    groups = panel.findChildren(QGroupBox)
    assert len(groups) >= 2  # Matrix + Metrics (and possibly others inside sidebar)

    # Check Matrix Widget
    matrix_widget = panel.findChild(ConfusionMatrixWidget)
    assert matrix_widget is not None

    # Check Bar Chart Widget
    bar_chart = panel.findChild(MetricsBarChartWidget)
    assert bar_chart is not None

    # Check Metrics Table
    metrics_table = panel.findChild(MetricsTableWidget)
    assert metrics_table is not None

    # Check Actions Group (Should be Removed)
    action_group = next((g for g in groups if g.title() == "ACTIONS"), None)
    assert action_group is None

    # Check Toolbar Controls
    model_combo = panel.model_combo
    run_combo = panel.run_combo
    chk_percentage = panel.chk_percentage

    assert isinstance(model_combo, QComboBox)
    assert isinstance(run_combo, QComboBox)
    assert isinstance(chk_percentage, QCheckBox)


def test_evaluation_panel_logic(qtbot):
    """Test the logic of the EvaluationPanel."""
    main_window = MockMainWindow()
    controller = main_window.study.get_controller("evaluation")
    panel = EvaluationPanel(controller=controller, parent=main_window)
    qtbot.addWidget(panel)

    # Trigger update via update_panel (standardized interface)
    panel.update_panel()

    # Trigger update_info
    panel.update_info()

    # Check Model Combo population
    assert panel.model_combo.count() == 2
    assert panel.model_combo.itemText(0) == "Fold 1: Plan A"

    # Check Run Combo population (defaults to first model)
    # 2 Repeats + 1 Average option = 3
    assert panel.run_combo.count() == 3
    assert "Repeat 1 (Finished)" in panel.run_combo.itemText(0)
    assert "Repeat 2" in panel.run_combo.itemText(1)  # Not finished

    rc = panel.metrics_table.rowCount()
    assert rc == 3, f"Row count mismatch. Expected 3, got {rc}"

    # Mock update_plot for bar chart to verify call
    panel.bar_chart.update_plot = MagicMock()

    # Change Run to Repeat 2 (Not finished)
    panel.run_combo.setCurrentIndex(1)
    assert panel.metrics_table.rowCount() == 0  # Should be empty
    panel.bar_chart.update_plot.assert_called_with({})  # Should be cleared

    # Change Model to Plan B
    panel.model_combo.setCurrentIndex(1)
    assert panel.model_combo.currentText() == "Fold 2: Plan B"
    # Plan B also has 2 records mock (1 finished), so 3 items (Repeats + Average)
    assert panel.run_combo.count() == 3

    # Test Show Percentage Toggle
    panel.chk_percentage.setChecked(True)
    panel.chk_percentage.setChecked(False)


def test_evaluation_panel_clears_stale_plans_on_preprocess_change(qtbot):
    """Preprocess invalidation should clear stale evaluation plan selections."""
    main_window = MockMainWindow()
    controller = main_window.study.get_controller("evaluation")
    preprocess_controller = Observable()
    panel = EvaluationPanel(
        controller=controller,
        preprocess_controller=preprocess_controller,
        parent=main_window,
    )
    qtbot.addWidget(panel)

    panel.update_panel()
    assert panel.model_combo.count() == 2
    assert panel.model_combo.itemText(0) == "Fold 1: Plan A"

    controller.get_plans.return_value = []
    preprocess_controller.notify("preprocess_changed")
    qtbot.wait(50)

    assert panel.model_combo.count() == 1
    assert panel.model_combo.itemText(0) == "No Data Available"
    assert panel.run_combo.count() == 0


def test_evaluation_panel_clears_stale_plans_on_history_cleared(qtbot):
    """Training-history clears should remove stale evaluation selections."""
    main_window = MockMainWindow()
    controller = main_window.study.get_controller("evaluation")
    controller.get_pooled_eval_result.return_value = (
        [0, 1],
        [0, 1],
        {
            0: {"precision": 0.8, "recall": 0.9, "f1-score": 0.85, "support": 10},
        },
    )
    training_controller = Observable()
    panel = EvaluationPanel(
        controller=controller,
        training_controller=training_controller,
        parent=main_window,
    )
    qtbot.addWidget(panel)

    panel.update_panel()
    assert panel.model_combo.count() == 2
    assert panel.model_combo.itemText(0) == "Fold 1: Plan A"

    controller.get_plans.return_value = []
    training_controller.notify("history_cleared")
    qtbot.wait(50)

    assert panel.model_combo.count() == 1
    assert panel.model_combo.itemText(0) == "No Data Available"
    assert panel.run_combo.count() == 0


def test_evaluation_panel_clears_stale_plans_on_config_changed(qtbot):
    """Training config changes should remove stale evaluation selections."""
    main_window = MockMainWindow()
    controller = main_window.study.get_controller("evaluation")
    training_controller = Observable()
    panel = EvaluationPanel(
        controller=controller,
        training_controller=training_controller,
        parent=main_window,
    )
    qtbot.addWidget(panel)

    panel.update_panel()
    assert panel.model_combo.count() == 2
    assert panel.model_combo.itemText(0) == "Fold 1: Plan A"

    controller.get_plans.return_value = []
    training_controller.notify("config_changed")
    qtbot.wait(50)

    assert panel.model_combo.count() == 1
    assert panel.model_combo.itemText(0) == "No Data Available"
    assert panel.run_combo.count() == 0


def test_evaluation_panel_preserves_selected_plan_and_average_on_training_stopped(
    qtbot,
):
    """training_stopped should keep the current plan/run selection when still valid."""
    main_window = MockMainWindow()
    controller = main_window.study.get_controller("evaluation")
    controller.get_pooled_eval_result.return_value = (
        [0, 1],
        [0, 1],
        {
            0: {"precision": 0.8, "recall": 0.9, "f1-score": 0.85, "support": 10},
        },
    )
    training_controller = Observable()
    panel = EvaluationPanel(
        controller=controller,
        training_controller=training_controller,
        parent=main_window,
    )
    qtbot.addWidget(panel)

    panel.update_panel()
    panel.model_combo.setCurrentIndex(1)
    panel.run_combo.setCurrentIndex(2)

    assert panel.model_combo.currentText() == "Fold 2: Plan B"
    assert panel.run_combo.currentText() == "Average (Finished Runs)"

    training_controller.notify("training_stopped")
    qtbot.wait(50)

    assert panel.model_combo.currentText() == "Fold 2: Plan B"
    assert panel.run_combo.currentText() == "Average (Finished Runs)"


def test_evaluation_panel_preserves_selected_repeat_when_status_label_changes(
    qtbot,
):
    """training_stopped should keep the selected record even if its label changes."""
    main_window = MockMainWindow()
    controller = main_window.study.get_controller("evaluation")
    training_controller = Observable()
    panel = EvaluationPanel(
        controller=controller,
        training_controller=training_controller,
        parent=main_window,
    )
    qtbot.addWidget(panel)

    plan_a = controller.get_plans.return_value[0]
    target_record = plan_a.get_plans()[1]
    assert target_record.is_finished() is False

    panel.update_panel()
    panel.run_combo.setCurrentIndex(1)

    assert panel.run_combo.currentText() == "Repeat 2"
    assert panel.run_combo.currentData() is target_record

    target_record.finished = True
    training_controller.notify("training_stopped")
    qtbot.wait(50)

    assert panel.run_combo.currentData() is target_record
    assert panel.run_combo.currentText() == "Repeat 2 (Finished)"
