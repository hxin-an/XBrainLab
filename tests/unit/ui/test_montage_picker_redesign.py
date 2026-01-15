import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QWidget

# Import the module under test
from XBrainLab.ui.visualization.montage_picker import PickMontageWindow

@pytest.fixture
def montage_picker_mocks():
    """Setup all necessary mocks for montage picker tests."""
    channel_names = ["EEG Fp1-Ref", "EEG Fp2-Ref", "Cz", "Trash", "O1"]
    mock_parent = QWidget()
    
    # Patch backend functions
    patcher_builtin = patch('XBrainLab.ui.visualization.montage_picker.get_builtin_montages')
    patcher_pos = patch('XBrainLab.ui.visualization.montage_picker.get_montage_positions')
    patcher_ch_pos = patch('XBrainLab.ui.visualization.montage_picker.get_montage_channel_positions')
    patcher_settings = patch('XBrainLab.ui.visualization.montage_picker.QSettings')
    
    mock_get_builtin = patcher_builtin.start()
    mock_get_pos = patcher_pos.start()
    mock_get_ch_pos = patcher_ch_pos.start()
    mock_settings_cls = patcher_settings.start()
    
    # Mock Settings
    mock_settings = MagicMock()
    mock_settings_cls.return_value = mock_settings
    mock_settings.value.return_value = {} # Default empty
    
    # Setup mock returns
    mock_get_builtin.return_value = ["standard_1020"]
    mock_get_pos.return_value = {
        'ch_pos': {
            'Fp1': [1, 2, 3],
            'Fp2': [4, 5, 6],
            'F3': [7, 8, 9],
            'F4': [10, 11, 12],
            'Cz': [13, 14, 15],
            'O1': [16, 17, 18],
            'O2': [19, 20, 21]
        }
    }
    
    yield {
        'parent': mock_parent,
        'channels': channel_names,
        'mock_settings': mock_settings,
        'mock_get_ch_pos': mock_get_ch_pos
    }

    # Cleanup
    patcher_builtin.stop()
    patcher_pos.stop()
    patcher_ch_pos.stop()
    patcher_settings.stop()

def test_smart_match(qtbot, montage_picker_mocks):
    """Test automatic smart matching logic."""
    dialog = PickMontageWindow(montage_picker_mocks['parent'], montage_picker_mocks['channels'])
    qtbot.addWidget(dialog)
    
    # Row 0: "EEG Fp1-Ref" -> Fp1
    combo0 = dialog.table.cellWidget(0, 1)
    assert combo0.currentText() == "Fp1"
    assert 0 in dialog.anchors
    
    # Row 2: "Cz" -> Cz
    combo2 = dialog.table.cellWidget(2, 1)
    assert combo2.currentText() == "Cz"
    assert 2 in dialog.anchors

def test_true_anchor_logic(qtbot, montage_picker_mocks):
    """Test True Anchor logic: Overwrite auto-filled, stop at anchors."""
    dialog = PickMontageWindow(montage_picker_mocks['parent'], montage_picker_mocks['channels'])
    qtbot.addWidget(dialog)
    
    # Scenario details in comments preserved from original...
    
    # Check initial auto-fill for Row 3 (Trash)
    # Between Cz (Row 2, idx 4) and O1 (Row 4, idx 5).
    # Logic should fill Row 3.
    
    combo3 = dialog.table.cellWidget(3, 1)
    # Based on original test logic
    assert combo3.currentText() == "O1"
    assert 3 not in dialog.anchors
    
    # Change Row 2 (Cz) to F3 (index 2) -> Anchor change
    combo2 = dialog.table.cellWidget(2, 1)
    idx_f3 = combo2.findText("F3")
    combo2.setCurrentIndex(idx_f3)
    
    # Verify Row 3
    # F3 is index 2. Next is F4 (index 3).
    assert combo3.currentText() == "F4"
    
    # Verify Row 4 (Anchor) should remain O1
    combo4 = dialog.table.cellWidget(4, 1)
    assert combo4.currentText() == "O1"

def test_persistence(qtbot, montage_picker_mocks):
    """Test saving and loading settings."""
    # Mock confirm to trigger save
    montage_picker_mocks['mock_get_ch_pos'].return_value = {}
    
    dialog = PickMontageWindow(montage_picker_mocks['parent'], montage_picker_mocks['channels'])
    qtbot.addWidget(dialog)
    
    # Set some values
    combo = dialog.table.cellWidget(3, 1)
    combo.setCurrentText("O2") # Manually set Trash to O2
    
    dialog.confirm()
    
    # Verify save
    mock_settings = montage_picker_mocks['mock_settings']
    mock_settings.setValue.assert_any_call("last_montage", "standard_1020")
    
    # Check mapping save
    args_list = mock_settings.setValue.call_args_list
    found = False
    for args, _ in args_list:
        if args[0] == "mapping/standard_1020":
            saved_map = args[1]
            assert saved_map["Trash"] == "O2"
            found = True
            break
    assert found
