
import sys
import pytest
from PyQt6.QtWidgets import QApplication, QMainWindow, QTableWidgetItem
from PyQt6.QtCore import Qt
from unittest.mock import MagicMock, patch
from XBrainLab.ui_pyqt.dashboard_panel.dataset import DatasetPanel

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)

class MockMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.study = MagicMock()
        self.study.loaded_data_list = []
        self.study.is_locked.return_value = False
    
    def update_info_panel(self):
        pass

@pytest.fixture
def mock_main_window(qapp):
    return MockMainWindow()

def test_dataset_panel_init(mock_main_window, qtbot):
    """Test initialization of DatasetPanel."""
    panel = DatasetPanel(mock_main_window)
    qtbot.addWidget(panel)
    
    assert panel.table.columnCount() == 7
    assert panel.import_btn.isEnabled()
    assert panel.clear_btn.isEnabled()

def test_dataset_panel_import_data_success(mock_main_window, qtbot):
    """Test successful data import."""
    panel = DatasetPanel(mock_main_window)
    qtbot.addWidget(panel)
    
    # Mock QFileDialog
    with patch('PyQt6.QtWidgets.QFileDialog.getOpenFileNames', return_value=(['/path/to/file.set'], 'Filter')):
        # Mock Loader
        with patch('XBrainLab.ui_pyqt.dashboard_panel.dataset.RawDataLoader') as MockLoader:
            loader_instance = MockLoader.return_value
            loader_instance.__len__.return_value = 1
            
            # Mock load_set_file
            with patch('XBrainLab.ui_pyqt.dashboard_panel.dataset.load_set_file') as mock_load:
                mock_raw = MagicMock()
                mock_raw.get_filepath.return_value = '/path/to/file.set'
                mock_load.return_value = mock_raw
                
                # Mock QMessageBox
                with patch('PyQt6.QtWidgets.QMessageBox.information') as mock_info:
                    panel.import_data()
                    
                    # Verify loader was applied
                    loader_instance.apply.assert_called_once()
                    mock_info.assert_called_once()

def test_dataset_panel_clear_dataset(mock_main_window, qtbot):
    """Test clearing the dataset."""
    panel = DatasetPanel(mock_main_window)
    qtbot.addWidget(panel)
    
    with patch('PyQt6.QtWidgets.QMessageBox.question', return_value=True): # Yes
         with patch('PyQt6.QtWidgets.QMessageBox.information') as mock_info:
            panel.clear_dataset()
            
            mock_main_window.study.clean_raw_data.assert_called_once()
            mock_info.assert_called_once()

def test_dataset_panel_update_tree_view(mock_main_window, qtbot):
    """Test table update from study data."""
    # Setup mock data
    mock_data = MagicMock()
    mock_data.get_filename.return_value = "test.set"
    mock_data.get_subject_name.return_value = "Sub01"
    mock_data.get_session_name.return_value = "Sess01"
    mock_data.get_nchan.return_value = 32
    mock_data.get_sfreq.return_value = 250
    mock_data.get_epochs_length.return_value = 100
    mock_data.has_event.return_value = True
    mock_data.is_raw.return_value = True
    mock_data.get_event_list.return_value = ([1,2,3], {})
    mock_data.is_labels_imported.return_value = False
    
    mock_main_window.study.loaded_data_list = [mock_data]
    
    panel = DatasetPanel(mock_main_window)
    qtbot.addWidget(panel)
    
    panel.update_panel()
    
    assert panel.table.rowCount() == 1
    assert panel.table.item(0, 0).text() == "test.set"
    assert panel.table.item(0, 1).text() == "Sub01"

def test_dataset_panel_on_item_changed(mock_main_window, qtbot):
    """Test editing subject/session in table."""
    # Setup mock data
    mock_data = MagicMock()
    mock_data.get_filename.return_value = "test.set"
    mock_data.get_subject_name.return_value = "Sub01"
    mock_data.get_session_name.return_value = "Sess01"
    
    mock_main_window.study.loaded_data_list = [mock_data]
    
    panel = DatasetPanel(mock_main_window)
    qtbot.addWidget(panel)
    panel.update_panel()
    
    # Simulate edit
    item = panel.table.item(0, 1) # Subject column
    item.setText("NewSub")
    
    # Manually trigger since we might have blocked signals or need to ensure it fires
    # But setText triggers itemChanged if signals are not blocked.
    # update_panel blocks signals, but unblocks at end.
    
    # Verify data object was updated
    mock_data.set_subject_name.assert_called_with("NewSub")

def test_dataset_panel_smart_parse(mock_main_window, qtbot):
    """Test smart parser integration."""
    mock_data = MagicMock()
    mock_data.get_filepath.return_value = "/path/to/sub-01_ses-01_eeg.set"
    mock_main_window.study.loaded_data_list = [mock_data]
    
    panel = DatasetPanel(mock_main_window)
    qtbot.addWidget(panel)
    
    with patch('XBrainLab.ui_pyqt.dashboard_panel.dataset.SmartParserDialog') as MockDialog:
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_results.return_value = {
            "/path/to/sub-01_ses-01_eeg.set": ("sub-01", "ses-01")
        }
        
        with patch('PyQt6.QtWidgets.QMessageBox.information'):
            panel.open_smart_parser()
            
            mock_data.set_subject_name.assert_called_with("sub-01")
            mock_data.set_session_name.assert_called_with("ses-01")

if __name__ == "__main__":
    pytest.main([__file__])
