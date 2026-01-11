
import sys
import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication, QComboBox, QCheckBox, QSplitter, QWidget, QGroupBox
from PyQt6.QtCore import Qt
from XBrainLab.ui.evaluation.panel import EvaluationPanel
from XBrainLab.ui.evaluation.confusion_matrix import ConfusionMatrixWidget
from XBrainLab.ui.evaluation.metrics_table import MetricsTableWidget
from XBrainLab.ui.evaluation.metrics_bar_chart import MetricsBarChartWidget

from XBrainLab.ui.evaluation.metrics_bar_chart import MetricsBarChartWidget

# Mock classes
class MockEvalRecord:
    def __init__(self):
        self.output = MagicMock()
        self.label = MagicMock()
        
    def get_per_class_metrics(self):
        return {
            0: {'precision': 0.8, 'recall': 0.9, 'f1-score': 0.85, 'support': 10},
            1: {'precision': 0.7, 'recall': 0.6, 'f1-score': 0.65, 'support': 10},
            'macro_avg': {'precision': 0.75, 'recall': 0.75, 'f1-score': 0.75, 'support': 20}
        }

class MockTrainRecord:
    def __init__(self, finished=True):
        self.finished = finished
        self.eval_record = MockEvalRecord() if finished else None
        
    def is_finished(self):
        return self.finished
        
    def get_confusion_figure(self, show_percentage=False):
        # Return a dummy figure
        from matplotlib.figure import Figure
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
        self.training_plan_holders = [MockPlanHolder("Plan A"), MockPlanHolder("Plan B")]

class MockStudy:
    def __init__(self):
        self.trainer = MockTrainer()
        self.loaded_data_list = []
        self.preprocessed_data_list = []

class MockMainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.study = MockStudy()

def test_evaluation_panel_layout(qtbot):
    """Test the layout of the redesigned EvaluationPanel."""
    app = QApplication.instance() or QApplication(sys.argv)
    
    main_window = MockMainWindow()
    panel = EvaluationPanel(main_window)
    qtbot.addWidget(panel)
    
    # Check Splitter (Should be None now)
    splitter = panel.findChild(QSplitter)
    assert splitter is None
    
    # Check Groups existence
    groups = panel.findChildren(QGroupBox)
    assert len(groups) >= 2 # Matrix + Metrics (and possibly others inside sidebar)
    
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
    app = QApplication.instance() or QApplication(sys.argv)
    
    main_window = MockMainWindow()
    panel = EvaluationPanel(main_window)
    qtbot.addWidget(panel)
    
    # Trigger update via refresh_data (alias)
    panel.refresh_data()
    
    # Trigger update_info
    panel.update_info()
    
    # Check Model Combo population
    assert panel.model_combo.count() == 2
    assert panel.model_combo.itemText(0) == "Group 1: Plan A"
    
    # Check Run Combo population (defaults to first model)
    assert panel.run_combo.count() == 2
    assert "Repeat 1 (Finished)" in panel.run_combo.itemText(0)
    assert "Repeat 2" in panel.run_combo.itemText(1) # Not finished
    
    # Check Metrics Table population (Repeat 1 is finished)
    assert panel.metrics_table.rowCount() == 3 # 2 classes + macro avg
    
    # Mock update_plot for bar chart to verify call
    panel.bar_chart.update_plot = MagicMock()
    
    # Change Run to Repeat 2 (Not finished)
    panel.run_combo.setCurrentIndex(1)
    assert panel.metrics_table.rowCount() == 0 # Should be empty
    panel.bar_chart.update_plot.assert_called_with({}) # Should be cleared
    
    # Change Model to Plan B
    panel.model_combo.setCurrentIndex(1)
    assert panel.model_combo.currentText() == "Group 2: Plan B"
    # Plan B also has 2 records mock
    assert panel.run_combo.count() == 2
    
    # Test Show Percentage Toggle
    panel.chk_percentage.setChecked(True)
    panel.chk_percentage.setChecked(False)

if __name__ == "__main__":
    pytest.main([__file__])
