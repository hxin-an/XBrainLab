import pytest
from XBrainLab.backend.study import Study
from XBrainLab.ui.evaluation.panel import EvaluationPanel
from PyQt6.QtWidgets import QMainWindow, QWidget
from unittest.mock import MagicMock, patch

class MockMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.study = Study()

@pytest.fixture
def mock_main_window(qapp):
    return MockMainWindow()

def test_evaluation_panel_tabs_attribute(mock_main_window, qtbot):
    """Test if tabs attribute exists after init."""
    panel = EvaluationPanel(mock_main_window)
    qtbot.addWidget(panel)
    assert hasattr(panel, 'tabs')
    assert panel.tabs is not None

def test_evaluation_panel_refresh_no_data(mock_main_window, qtbot):
    """Test refresh_data when no trainers are present."""
    panel = EvaluationPanel(mock_main_window)
    qtbot.addWidget(panel)
    # Should show warning but not crash
    # Should show warning but not crash
    with patch('XBrainLab.ui.evaluation.panel.QMessageBox.warning') as mock_warn:
        panel.refresh_data()
        mock_warn.assert_called_once()

class DummyWidget(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

def test_evaluation_panel_refresh_with_data(mock_main_window, qtbot):
    """
    Test refresh_data when trainers are present.
    """
    # Mock Trainer and Plans
    mock_trainer = MagicMock()
    mock_plan = MagicMock()
    mock_plan.get_name.return_value = "TestPlan" # Return string
    mock_trainer.get_training_plan_holders.return_value = [mock_plan]
    mock_main_window.study.trainer = mock_trainer
    
    # Mock Widgets to avoid actual instantiation issues
    # Use DummyWidget so QTabWidget accepts them
    with patch('XBrainLab.ui.evaluation.panel.EvaluationTableWidget', side_effect=DummyWidget) as MockTable, \
         patch('XBrainLab.ui.evaluation.panel.ConfusionMatrixWidget', side_effect=DummyWidget) as MockMatrix, \
         patch('XBrainLab.ui.evaluation.panel.QMessageBox.information') as mock_info:
        
        panel = EvaluationPanel(mock_main_window)
        qtbot.addWidget(panel)
        
        panel.refresh_data()
        
        # Verify widgets were re-created
        assert MockTable.call_count == 2 # Init + Refresh
        assert MockMatrix.call_count == 2 # Init + Refresh
        
        # Verify success message
        mock_info.assert_called_once()

def test_evaluation_panel_export_placeholders(mock_main_window, qtbot):
    """
    Test that export/report buttons show placeholder messages.
    """
    panel = EvaluationPanel(mock_main_window)
    qtbot.addWidget(panel)
    
    with patch('XBrainLab.ui.evaluation.panel.QMessageBox.information') as mock_info:
        panel.export_results()
        mock_info.assert_called_with(panel, "Info", "Export Results feature coming soon.")
        
        panel.save_report()
        mock_info.assert_called_with(panel, "Info", "Save Report feature coming soon.")
