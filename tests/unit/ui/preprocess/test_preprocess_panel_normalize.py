import sys
import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication, QWidget

# Import the module under test
from XBrainLab.ui.dialogs.preprocess import NormalizeDialog
from XBrainLab.ui.panels.preprocess.panel import PreprocessPanel


class TestNormalizeDialog(unittest.TestCase):
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

    def setUp(self):
        if not QApplication.instance():
            self.app = QApplication(sys.argv)

        self.mock_controller = MagicMock()
        self.mock_controller.has_data.return_value = True
        self.mock_controller.is_locked.return_value = False
        self.mock_controller.is_epoched.return_value = False  # Crucial for check_lock
        self.mock_controller.get_preprocessed_data_list.return_value = []

        self.mock_window = QWidget()
        self.mock_window.study = MagicMock()
        self.mock_window.refresh_panels = MagicMock()
        self.mock_window.study.get_controller.return_value = self.mock_controller

        # Create panel
        self.panel = PreprocessPanel(parent=self.mock_window)

    @patch("XBrainLab.ui.panels.preprocess.sidebar.NormalizeDialog")
    @patch("XBrainLab.ui.panels.preprocess.sidebar.QMessageBox")
    def test_open_normalize(self, MockBox, MockDialog):
        """Test opening normalize dialog."""
        mock_instance = MockDialog.return_value
        mock_instance.exec.return_value = True
        mock_instance.get_params.return_value = "z score"

        with patch.object(self.panel, "update_panel") as mock_update:
            self.panel.sidebar.open_normalize()

            # Verify controller call
            self.panel.controller.apply_normalization.assert_called_once_with("z score")

            # Verify update
            # update_panel on main panel is called via notify_update from sidebar
            mock_update.assert_called_once()
            MockBox.information.assert_called_once()  # Success message


if __name__ == "__main__":
    unittest.main()
