
import sys
import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication

# Import the module under test
from XBrainLab.ui.dashboard_panel.preprocess import NormalizeDialog, PreprocessPanel


class TestNormalizeDialog(unittest.TestCase):
    def setUp(self):
        # We need a qapp instance for widgets
        if not QApplication.instance():
            self.app = QApplication(sys.argv)

    def test_dialog_params(self):
        dialog = NormalizeDialog(None)

        # Default Z-Score
        dialog.zscore_radio.setChecked(True)
        dialog.accept()
        self.assertEqual(dialog.get_params(), "z score")

        # Min-Max
        dialog.minmax_radio.setChecked(True)
        dialog.accept()
        self.assertEqual(dialog.get_params(), "minmax")

class TestPreprocessPanelNormalize(unittest.TestCase):
    # Patch module where PreprocessController is imported in PreprocessPanel
    # It seems to be 'XBrainLab.ui.dashboard_panel.preprocess.PreprocessController'
    @patch('XBrainLab.ui.dashboard_panel.preprocess.PreprocessController')
    def setUp(self, MockController):
        if not QApplication.instance():
            self.app = QApplication(sys.argv)

        self.mock_controller = MockController.return_value
        self.mock_controller.has_data.return_value = True
        self.mock_controller.is_locked.return_value = False
        self.mock_controller.is_epoched.return_value = False # Crucial for check_lock

        # Create panel
        self.panel = PreprocessPanel()
        # Inject controller
        self.panel.controller = self.mock_controller
        self.panel.main_window = MagicMock()

    @patch('XBrainLab.ui.dashboard_panel.preprocess.NormalizeDialog')
    @patch('XBrainLab.ui.dashboard_panel.preprocess.QMessageBox')
    def test_open_normalize(self, MockBox, MockDialog):
        """Test opening normalize dialog."""
        mock_instance = MockDialog.return_value
        mock_instance.exec.return_value = True
        mock_instance.get_params.return_value = "z score"

        with patch.object(self.panel, 'update_panel') as mock_update:
            self.panel.open_normalize()

            # Verify controller call
            self.panel.controller.apply_normalization.assert_called_once_with("z score")

            # Verify update
            mock_update.assert_called_once()
            MockBox.information.assert_called_once() # Success message

if __name__ == '__main__':
    unittest.main()
