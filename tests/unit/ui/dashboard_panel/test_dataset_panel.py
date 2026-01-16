
import sys
import pytest
from PyQt6.QtWidgets import QApplication, QMainWindow, QTableWidgetItem
from PyQt6.QtCore import Qt
from unittest.mock import MagicMock, patch
from XBrainLab.ui.dashboard_panel.dataset import DatasetPanel

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)

@pytest.fixture
def mock_main_window(qapp):
    window = MagicMock(spec=QMainWindow)
    window.study = MagicMock() # Still needed for init, but controller will be mocked
    window.study.loaded_data_list = []
    # Add custom methods not in QMainWindow spec
    window.refresh_panels = MagicMock()
    return window

@pytest.fixture
def mock_controller():
    with patch('XBrainLab.ui.dashboard_panel.dataset.DatasetController') as MockController:
        instance = MockController.return_value
        instance.is_locked.return_value = False
        instance.has_data.return_value = False
        instance.get_loaded_data_list.return_value = []
        yield instance

def test_dataset_panel_init_controller(mock_main_window, mock_controller, qtbot):
    """Test initialization creates controller."""
    # Alternative: Create a real QMainWindow for parent
    real_window = QMainWindow()
    real_window.study = MagicMock()
    
    panel = DatasetPanel(real_window)
    qtbot.addWidget(panel)
    
    # Check if controller was instantiated
    assert hasattr(panel, 'controller')
    
    # Clean up
    panel.close()
    real_window.close()

def test_dataset_panel_import_data_success(mock_main_window, mock_controller, qtbot):
    """Test successful data import delegates to controller."""
    from PyQt6.QtWidgets import QMessageBox, QFileDialog
    panel = DatasetPanel(None)
    panel.main_window = mock_main_window
    panel.controller = mock_controller
    qtbot.addWidget(panel)
    
    # Patch the name imported in the module
    with patch('XBrainLab.ui.dashboard_panel.dataset.QFileDialog.getOpenFileNames', return_value=(['/path/to/file.set'], 'Filter')):
        # Controller returns success
        mock_controller.import_files.return_value = (1, [])
        
        with patch('XBrainLab.ui.dashboard_panel.dataset.QMessageBox.information') as mock_info:
            panel.import_data()
            mock_controller.import_files.assert_called_once_with(['/path/to/file.set'])
            # No success message provided for clean import
            mock_info.assert_not_called()

def test_dataset_panel_clear_dataset(mock_main_window, mock_controller, qtbot):
    """Test clearing the dataset."""
    from PyQt6.QtWidgets import QMessageBox
    panel = DatasetPanel(None)
    panel.main_window = mock_main_window
    panel.controller = mock_controller
    qtbot.addWidget(panel)
    
    with patch('XBrainLab.ui.dashboard_panel.dataset.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
         with patch('XBrainLab.ui.dashboard_panel.dataset.QMessageBox.information') as mock_info:
            panel.clear_dataset()
            mock_controller.clean_dataset.assert_called_once()
            mock_info.assert_called_once()

def test_dataset_panel_update_tree_view(mock_main_window, mock_controller, qtbot):
    """Test table update from controller data."""
    mock_data = MagicMock()
    mock_data.configure_mock(**{
        'get_filepath.return_value': "/path/test.set",
        'get_filename.return_value': "test.set",
        'get_subject_name.return_value': "Sub01",
        'get_session_name.return_value': "Sess01",
        'get_nchan.return_value': 32,
        'get_sfreq.return_value': 250,
        'get_epochs_length.return_value': 100,
        'has_event.return_value': False,
        'is_raw.return_value': False,
        'is_labels_imported.return_value': False,
        'get_event_list.return_value': ([], {}),
        'get_filter_range.return_value': (0.1, 40.0),
        'get_tmin.return_value': 0.0,
        'get_epoch_duration.return_value': 1.0
    })
    
    mock_controller.get_loaded_data_list.return_value = [mock_data]
    
    panel = DatasetPanel(None)
    panel.main_window = mock_main_window
    panel.controller = mock_controller
    qtbot.addWidget(panel)
    
    panel.update_panel()
    
    assert panel.table.rowCount() == 1
    assert panel.table.item(0, 0).text() == "test.set"

def test_dataset_panel_on_item_changed(mock_main_window, mock_controller, qtbot):
    """Test editing subject/session in table updates metadata via controller."""
    mock_data = MagicMock()
    mock_data.configure_mock(**{
        'get_filepath.return_value': "/path/test.set",
        'get_filename.return_value': "test.set",
        'get_subject_name.return_value': "Sub01",
        'get_session_name.return_value': "Sess01"
    })
    # Needed for _populate_table in update_panel
    mock_data.get_subject_name.return_value = "Sub01"
    
    mock_controller.get_loaded_data_list.return_value = [mock_data]
    
    panel = DatasetPanel(None)
    panel.main_window = mock_main_window
    panel.controller = mock_controller
    qtbot.addWidget(panel)
    panel.update_panel()
    
    # Mock update_panel to avoid clearing the table (which deletes the item triggering the signal)
    with patch.object(panel, 'update_panel'):
        # Simulate editing Subject (Column 1)
        item = panel.table.item(0, 1) # Subject
        item.setText("NewSub")
        
        # Verify controller called
        mock_controller.update_metadata.assert_called()

def test_dataset_panel_smart_parse(mock_main_window, mock_controller, qtbot):
    """Test smart parser delegates to controller."""
    mock_controller.has_data.return_value = True
    mock_controller.get_filenames.return_value = ["/path/file.set"]
    
    panel = DatasetPanel(None)
    panel.main_window = mock_main_window
    panel.controller = mock_controller
    qtbot.addWidget(panel)
    
    with patch('XBrainLab.ui.dashboard_panel.dataset.SmartParserDialog') as MockDialog:
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_results.return_value = {"/path/file.set": ("sub", "ses")}
        
        mock_controller.apply_smart_parse.return_value = 1
        
        with patch('XBrainLab.ui.dashboard_panel.dataset.QMessageBox.information'):
            panel.open_smart_parser()
            mock_controller.apply_smart_parse.assert_called_with({"/path/file.set": ("sub", "ses")})

if __name__ == "__main__":
    pytest.main([__file__])
