import unittest
from unittest.mock import MagicMock, patch
import sys
from PyQt6.QtWidgets import QApplication, QComboBox, QTableWidget, QWidget
from PyQt6.QtCore import Qt

# Import the module under test
from XBrainLab.ui.visualization.montage_picker import PickMontageWindow

app = QApplication(sys.argv)

class TestMontagePickerRedesign(unittest.TestCase):
    def setUp(self):
        self.channel_names = ["EEG Fp1-Ref", "EEG Fp2-Ref", "Cz", "Trash", "O1"]
        self.mock_parent = QWidget()
        
        # Patch backend functions
        self.patcher_builtin = patch('XBrainLab.ui.visualization.montage_picker.get_builtin_montages')
        self.patcher_pos = patch('XBrainLab.ui.visualization.montage_picker.get_montage_positions')
        self.patcher_ch_pos = patch('XBrainLab.ui.visualization.montage_picker.get_montage_channel_positions')
        self.patcher_settings = patch('XBrainLab.ui.visualization.montage_picker.QSettings')
        
        self.mock_get_builtin = self.patcher_builtin.start()
        self.mock_get_pos = self.patcher_pos.start()
        self.mock_get_ch_pos = self.patcher_ch_pos.start()
        self.mock_settings_cls = self.patcher_settings.start()
        
        # Mock Settings
        self.mock_settings = MagicMock()
        self.mock_settings_cls.return_value = self.mock_settings
        self.mock_settings.value.return_value = {} # Default empty
        
        # Setup mock returns
        self.mock_get_builtin.return_value = ["standard_1020"]
        self.mock_get_pos.return_value = {
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
        
        self.dialog = PickMontageWindow(self.mock_parent, self.channel_names)

    def tearDown(self):
        self.dialog.close()
        self.patcher_builtin.stop()
        self.patcher_pos.stop()
        self.patcher_ch_pos.stop()
        self.patcher_settings.stop()

    def test_smart_match(self):
        """Test automatic smart matching logic."""
        # Row 0: "EEG Fp1-Ref" -> Fp1
        combo0 = self.dialog.table.cellWidget(0, 1)
        self.assertEqual(combo0.currentText(), "Fp1")
        self.assertIn(0, self.dialog.anchors)
        
        # Row 2: "Cz" -> Cz
        combo2 = self.dialog.table.cellWidget(2, 1)
        self.assertEqual(combo2.currentText(), "Cz")
        self.assertIn(2, self.dialog.anchors)

    def test_true_anchor_logic(self):
        """Test True Anchor logic: Overwrite auto-filled, stop at anchors."""
        # Scenario:
        # Row 0: Fp1 (Anchor)
        # Row 1: Fp2 (Anchor)
        # Row 2: Cz (Anchor, index 4)
        # Row 3: Trash (Unmatched, Auto-filled by initial fill?)
        # Row 4: O1 (Anchor, index 5)
        
        # Initial fill logic:
        # Between Cz (Row 2) and O1 (Row 4).
        # Cz is index 4. O1 is index 5.
        # Gap is Row 3.
        # Fill Row 3 with index 4+1 = 5 (O1).
        # Wait, O1 is already at Row 4.
        # So Row 3 becomes O1.
        
        combo3 = self.dialog.table.cellWidget(3, 1)
        self.assertEqual(combo3.currentText(), "O1")
        self.assertNotIn(3, self.dialog.anchors) # Should NOT be an anchor
        
        # Now, user changes Row 2 (Cz) to F3 (index 2).
        # This is an Anchor change.
        # Should cascade to Row 3.
        # Row 3 is NOT an anchor, so it should be overwritten.
        # Row 4 (O1) IS an anchor, so cascade stops there.
        
        combo2 = self.dialog.table.cellWidget(2, 1)
        idx_f3 = combo2.findText("F3")
        combo2.setCurrentIndex(idx_f3)
        
        # Verify Row 3
        # F3 is index 2. Next is F4 (index 3).
        self.assertEqual(combo3.currentText(), "F4")
        
        # Verify Row 4
        combo4 = self.dialog.table.cellWidget(4, 1)
        self.assertEqual(combo4.currentText(), "O1") # Should remain O1
        
    def test_persistence(self):
        """Test saving and loading settings."""
        # Mock confirm to trigger save
        self.mock_get_ch_pos.return_value = {}
        
        # Set some values
        combo = self.dialog.table.cellWidget(3, 1)
        combo.setCurrentText("O2") # Manually set Trash to O2
        
        self.dialog.confirm()
        
        # Verify save
        self.mock_settings.setValue.assert_any_call("last_montage", "standard_1020")
        # Check mapping save
        args_list = self.mock_settings.setValue.call_args_list
        found = False
        for args, _ in args_list:
            if args[0] == "mapping/standard_1020":
                saved_map = args[1]
                self.assertEqual(saved_map["Trash"], "O2")
                found = True
                break
        self.assertTrue(found)

if __name__ == '__main__':
    unittest.main()
