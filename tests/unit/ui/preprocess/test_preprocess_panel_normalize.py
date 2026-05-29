import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QWidget

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
        """Opening normalize blocks instead of mutating the legacy controller."""
        mock_instance = MockDialog.return_value
        mock_instance.exec.return_value = True
        mock_instance.get_params.return_value = "z score"

        with patch.object(self.panel, "update_panel") as mock_update:
            self.panel.sidebar.open_normalize()

            self.panel.controller.apply_normalization.assert_not_called()

            mock_update.assert_not_called()
            MockBox.warning.assert_called_once()
            self.assertEqual(MockBox.warning.call_args.args[1], "Normalization Blocked")
            MockBox.information.assert_not_called()
