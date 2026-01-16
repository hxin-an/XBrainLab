
import sys
import pytest
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget
from unittest.mock import MagicMock, patch
from XBrainLab.ui.dashboard_panel.preprocess import PreprocessPanel

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)

@pytest.fixture
def mock_main_window(qapp):
    window = MagicMock(spec=QMainWindow)
    window.study = MagicMock()
    # Add custom methods not in QMainWindow spec
    window.refresh_panels = MagicMock()
    return window

@pytest.fixture
def mock_controller():
    with patch('XBrainLab.ui.dashboard_panel.preprocess.PreprocessController') as MockController:
        instance = MockController.return_value
        instance.is_epoched.return_value = False
        instance.has_data.return_value = True
        instance.get_preprocessed_data_list.return_value = []
        yield instance

def test_preprocess_panel_init_controller(mock_main_window, mock_controller, qtbot):
    """Test initialization creates controller."""
    # Use real objects for inheritance check
    real_window = QMainWindow()
    real_window.study = MagicMock()
    
    panel = PreprocessPanel(real_window)
    qtbot.addWidget(panel)
    assert hasattr(panel, 'controller')
    
    panel.close()
    real_window.close()

def test_preprocess_panel_filtering(mock_main_window, mock_controller, qtbot):
    """Test filtering delegates to controller."""
    mock_controller.has_data.return_value = True
    panel = PreprocessPanel(None)
    panel.main_window = mock_main_window
    panel.controller = mock_controller
    qtbot.addWidget(panel)
    
    with patch.object(panel, 'plot_sample_data'): # Mock plotting
        with patch('XBrainLab.ui.dashboard_panel.preprocess.FilteringDialog') as MockDialog:
            instance = MockDialog.return_value
            instance.exec.return_value = True
            instance.get_params.return_value = (1.0, 40.0, 50.0) # l_freq, h_freq, notch
            
            with patch('XBrainLab.ui.dashboard_panel.preprocess.QMessageBox.information') as mock_info:
                panel.open_filtering()
                
                mock_controller.apply_filter.assert_called_with(1.0, 40.0, 50.0)
                mock_info.assert_called_once()

def test_preprocess_panel_resample(mock_main_window, mock_controller, qtbot):
    """Test resampling delegates to controller."""
    mock_controller.has_data.return_value = True
    panel = PreprocessPanel(None)
    panel.main_window = mock_main_window
    panel.controller = mock_controller
    qtbot.addWidget(panel)
    
    with patch.object(panel, 'plot_sample_data'):
        with patch('XBrainLab.ui.dashboard_panel.preprocess.ResampleDialog') as MockDialog:
            instance = MockDialog.return_value
            instance.exec.return_value = True
            instance.get_params.return_value = 256.0
            
            with patch('XBrainLab.ui.dashboard_panel.preprocess.QMessageBox.information') as mock_info:
                panel.open_resample()
                
                mock_controller.apply_resample.assert_called_with(256.0)
                mock_info.assert_called_once()

def test_preprocess_panel_epoching(mock_main_window, mock_controller, qtbot):
    """Test epoching delegates to controller."""
    mock_controller.has_data.return_value = True
    panel = PreprocessPanel(None)
    panel.main_window = mock_main_window
    panel.controller = mock_controller
    qtbot.addWidget(panel)
    
    with patch.object(panel, 'plot_sample_data'):
        with patch('XBrainLab.ui.dashboard_panel.preprocess.EpochingDialog') as MockDialog:
            instance = MockDialog.return_value
            instance.exec.return_value = True
            instance.get_params.return_value = ((0.0, 0.1), ['Event1'], -0.2, 0.5)
            
            mock_controller.apply_epoching.return_value = True
            
            with patch('XBrainLab.ui.dashboard_panel.preprocess.QMessageBox.information') as mock_info:
                panel.open_epoching()
                
                mock_controller.apply_epoching.assert_called_with((0.0, 0.1), ['Event1'], -0.2, 0.5)
                # Should show success message
                mock_info.assert_called_once()

def test_preprocess_panel_reset(mock_main_window, mock_controller, qtbot):
    """Test reset delegates to controller."""
    mock_controller.has_data.return_value = True
    panel = PreprocessPanel(None)
    panel.main_window = mock_main_window
    panel.controller = mock_controller
    qtbot.addWidget(panel)
    
    from PyQt6.QtWidgets import QMessageBox
    with patch.object(panel, 'plot_sample_data'):
        # Patch the imported name in preprocess module
        with patch('XBrainLab.ui.dashboard_panel.preprocess.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
            with patch('XBrainLab.ui.dashboard_panel.preprocess.QMessageBox.information') as mock_info:
                panel.reset_preprocess()
                mock_controller.reset_preprocess.assert_called_once()
                mock_info.assert_called_once()

if __name__ == "__main__":
    pytest.main([__file__])
