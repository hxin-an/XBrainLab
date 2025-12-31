
import sys
import pytest
from PyQt6.QtWidgets import QApplication
from unittest.mock import MagicMock, patch
from XBrainLab.ui_pyqt.dashboard_panel.dataset import ChannelSelectionDialog, SmartParserDialog
from XBrainLab.ui_pyqt.dashboard_panel.preprocess import EpochingDialog
from XBrainLab.load_data import Raw

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)

def test_channel_selection_dialog(qtbot):
    """Test ChannelSelectionDialog initialization and selection."""
    # Mock data list
    mock_data = MagicMock()
    mock_data.get_mne.return_value.ch_names = ['C3', 'C4', 'Cz']
    data_list = [mock_data]
    
    # Mock Preprocessor
    with patch('XBrainLab.preprocessor.ChannelSelection') as MockCS:
        dialog = ChannelSelectionDialog(None, data_list)
        qtbot.addWidget(dialog)
        
        # Check list items
        assert dialog.list_widget.count() == 3
        items = [dialog.list_widget.item(i).text() for i in range(3)]
        assert items == ['C3', 'C4', 'Cz']
        
        # Test Accept
        dialog.accept()
        # Should call preprocessor.data_preprocess
        MockCS.return_value.data_preprocess.assert_called_once()

def test_smart_parser_dialog(qtbot):
    """Test SmartParserDialog regex logic."""
    filepaths = ['/data/sub-01_ses-01_eeg.set', '/data/sub-02_ses-01_eeg.set']
    dialog = SmartParserDialog(filepaths, None)
    qtbot.addWidget(dialog)
    
    # Set regex pattern manually to ensure test stability
    dialog.radio_regex.setChecked(True)
    dialog.regex_preset_combo.setCurrentIndex(0)
    # Pattern: sub-(\d+)_ses-(\d+)
    dialog.regex_input.setText(r"sub-(\d+)_ses-(\d+)")
    dialog.regex_sub_idx.setValue(1)
    dialog.regex_sess_idx.setValue(2)
    
    # Trigger preview (usually connected to textChanged)
    dialog.update_preview()
    
    assert dialog.table.rowCount() == 2
    
    # Row 0
    item_sub = dialog.table.item(0, 1) # Subject
    item_ses = dialog.table.item(0, 2) # Session
    assert item_sub.text() == "01"
    assert item_ses.text() == "01"

def test_epoching_dialog_init(qtbot):
    """
    Test EpochingDialog initialization and basic flow.
    """
    # Mock Raw object with spec to pass validation
    mock_data = MagicMock(spec=Raw)
    mock_data.get_raw_event_list.return_value = (MagicMock(), {'Event1': 1})
    mock_data.get_event_list.return_value = (MagicMock(), {'Event1': 1})
    mock_data.is_raw.return_value = True
    
    # Patch validate_list_type to bypass strict type checking if spec doesn't work perfectly
    with patch('XBrainLab.preprocessor.base.validate_list_type'):
        dialog = EpochingDialog(None, [mock_data])
        qtbot.addWidget(dialog)
        
        # Check if event list is populated
        assert dialog.event_list.count() > 0
        assert dialog.event_list.item(0).text() == 'Event1'
        
        # Select event
        dialog.event_list.item(0).setSelected(True)
        
        # Mock preprocessor internal data_preprocess to avoid running real logic
        dialog.preprocessor = MagicMock()
        
        # Accept
        dialog.accept()
        
        # Verify preprocess call
        dialog.preprocessor.data_preprocess.assert_called()

if __name__ == "__main__":
    pytest.main([__file__])
