
import sys
import pytest
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget
from unittest.mock import MagicMock, patch
from XBrainLab.ui_pyqt.dashboard_panel.preprocess import PreprocessPanel

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)

class MockMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.study = MagicMock()
        self.study.preprocessed_data_list = []
        self.study.loaded_data_list = []
        
    def update_info_panel(self):
        pass

@pytest.fixture
def mock_main_window(qapp):
    return MockMainWindow()

class DummyWidget(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.return_data = None
    def exec(self):
        return True
    def get_result(self):
        return self.return_data

def test_preprocess_panel_init(mock_main_window, qtbot):
    """Test initialization of PreprocessPanel."""
    panel = PreprocessPanel(mock_main_window)
    qtbot.addWidget(panel)
    
    assert panel.btn_filter.isEnabled()
    assert panel.btn_resample.isEnabled()
    assert panel.btn_epoch.isEnabled()

def test_preprocess_panel_filtering(mock_main_window, qtbot):
    """Test filtering operation."""
    mock_main_window.study.preprocessed_data_list = [MagicMock()]
    
    panel = PreprocessPanel(mock_main_window)
    qtbot.addWidget(panel)
    
    with patch('XBrainLab.ui_pyqt.dashboard_panel.preprocess.FilteringDialog') as MockDialog:
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_result.return_value = ["filtered_data"]
        
        with patch('PyQt6.QtWidgets.QMessageBox.information') as mock_info:
            panel.open_filtering()
            
            mock_main_window.study.set_preprocessed_data_list.assert_called_with(["filtered_data"])
            mock_main_window.study.lock_dataset.assert_called_once()
            mock_info.assert_called_once()

def test_preprocess_panel_resample(mock_main_window, qtbot):
    """Test resampling operation."""
    mock_main_window.study.preprocessed_data_list = [MagicMock()]
    
    panel = PreprocessPanel(mock_main_window)
    qtbot.addWidget(panel)
    
    with patch('XBrainLab.ui_pyqt.dashboard_panel.preprocess.ResampleDialog') as MockDialog:
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_result.return_value = ["resampled_data"]
        
        with patch('PyQt6.QtWidgets.QMessageBox.information') as mock_info:
            panel.open_resample()
            
            mock_main_window.study.set_preprocessed_data_list.assert_called_with(["resampled_data"])
            mock_info.assert_called_once()

def test_preprocess_panel_epoching(mock_main_window, qtbot):
    """Test epoching operation."""
    mock_main_window.study.preprocessed_data_list = [MagicMock()]
    
    panel = PreprocessPanel(mock_main_window)
    qtbot.addWidget(panel)
    
    with patch('XBrainLab.ui_pyqt.dashboard_panel.preprocess.EpochingDialog') as MockDialog:
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_result.return_value = ["epoched_data"]
        
        with patch('PyQt6.QtWidgets.QMessageBox.information') as mock_info:
            panel.open_epoching()
            
            mock_main_window.study.set_preprocessed_data_list.assert_called_with(["epoched_data"])
            mock_info.assert_called_once()


def test_preprocess_panel_reset(mock_main_window, qtbot):
    """Test reset operation."""
    mock_main_window.study.preprocessed_data_list = [MagicMock()]
    
    panel = PreprocessPanel(mock_main_window)
    qtbot.addWidget(panel)
    
    from PyQt6.QtWidgets import QMessageBox
    with patch('PyQt6.QtWidgets.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
        with patch('PyQt6.QtWidgets.QMessageBox.information') as mock_info:
            panel.reset_preprocess()
            
            mock_main_window.study.reset_preprocess.assert_called_once()
            mock_info.assert_called_once()

def test_preprocess_panel_update_history(mock_main_window, qtbot):
    """Test history list update."""
    mock_data = MagicMock()
    mock_data.get_preprocess_history.return_value = ["Step 1", "Step 2"]
    mock_data.get_nchan.return_value = 10
    mock_data.get_epochs_length.return_value = 100
    mock_data.is_raw.return_value = False
    
    mock_main_window.study.preprocessed_data_list = [mock_data]
    
    panel = PreprocessPanel(mock_main_window)
    qtbot.addWidget(panel)
    
    # Mock plotting to avoid matplotlib issues
    with patch.object(panel, 'plot_sample_data'):
        panel.update_panel()
        
        assert panel.history_list.count() == 2
        assert panel.history_list.item(0).text() == "Step 1"

def test_preprocess_panel_plot_update(mock_main_window, qtbot):
    """Test plot update logic (mocking matplotlib)."""
    import numpy as np
    mock_data = MagicMock()
    mock_data.get_nchan.return_value = 2
    mock_data.get_sfreq.return_value = 100
    mock_data.is_raw.return_value = True
    
    # Mock MNE data as numpy array
    mock_mne = MagicMock()
    mock_mne.get_data.return_value = np.array([[1, 2, 3], [4, 5, 6]]) # (n_chan, n_times)
    mock_data.get_mne.return_value = mock_mne
    
    mock_main_window.study.preprocessed_data_list = [mock_data]
    mock_main_window.study.loaded_data_list = [mock_data]
    
    panel = PreprocessPanel(mock_main_window)
    qtbot.addWidget(panel)
    
    # We need to mock the canvas draw methods
    panel.canvas_time.draw = MagicMock()
    panel.canvas_freq.draw = MagicMock()
    
    panel.update_panel()
    
    # Verify draw was called
    panel.canvas_time.draw.assert_called()
    panel.canvas_freq.draw.assert_called()

if __name__ == "__main__":
    pytest.main([__file__])
