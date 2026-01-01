
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication
from XBrainLab.ui_pyqt.main_window import MainWindow

@pytest.fixture
def mock_study():
    study = MagicMock()
    study.trainer = MagicMock()
    return study

def test_ui_refresh_on_tab_switch(qtbot, mock_study):
    """Test that switching tabs triggers refresh_data on panels."""
    # Setup
    window = MainWindow(mock_study)
    qtbot.addWidget(window)
    
    # Mock the panels and their refresh_data methods
    window.evaluation_panel = MagicMock()
    window.visualization_panel = MagicMock()
    
    # Test switching to Evaluation (Index 3)
    window.switch_page(3)
    window.evaluation_panel.refresh_data.assert_called_once()
    
    # Test switching to Visualization (Index 4)
    window.switch_page(4)
    window.visualization_panel.refresh_data.assert_called_once()
    
    # Test switching to other tabs (should not call refresh)
    window.evaluation_panel.refresh_data.reset_mock()
    window.visualization_panel.refresh_data.reset_mock()
    
    window.switch_page(0) # Dataset
    window.evaluation_panel.refresh_data.assert_not_called()
    window.visualization_panel.refresh_data.assert_not_called()

if __name__ == "__main__":
    pytest.main([__file__])
