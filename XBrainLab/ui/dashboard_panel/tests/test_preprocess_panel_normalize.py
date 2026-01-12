import unittest
from unittest.mock import MagicMock, patch
import sys
from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QRadioButton
from PyQt6.QtCore import Qt

# Import the module under test
from XBrainLab.ui.dashboard_panel.preprocess import NormalizeDialog, PreprocessPanel

app = QApplication(sys.argv)

class TestNormalizeDialog(unittest.TestCase):
    def setUp(self):
        self.mock_parent = MagicMock()
        self.mock_data = MagicMock()
        self.mock_data_list = [self.mock_data]
        
        # Patch Preprocessor
        self.patcher = patch('XBrainLab.ui.dashboard_panel.preprocess.Preprocessor')
        self.mock_preprocessor_cls = self.patcher.start()
        self.mock_normalize_instance = self.mock_preprocessor_cls.Normalize.return_value
        
        self.dialog = NormalizeDialog(None, self.mock_data_list)

    def tearDown(self):
        self.dialog.close()
        self.patcher.stop()

    def test_init(self):
        """Test dialog initialization."""
        self.assertEqual(self.dialog.windowTitle(), "Normalize")
        self.assertTrue(self.dialog.zscore_radio.isChecked())
        self.assertFalse(self.dialog.minmax_radio.isChecked())

    def test_accept_zscore(self):
        """Test accepting Z-Score normalization."""
        self.dialog.zscore_radio.setChecked(True)
        
        # Mock backend return
        expected_data = [MagicMock()]
        self.mock_normalize_instance.data_preprocess.return_value = expected_data
        
        self.dialog.accept()
        
        self.mock_normalize_instance.data_preprocess.assert_called_with(norm="z score")
        self.assertEqual(self.dialog.get_result(), expected_data)

    def test_accept_minmax(self):
        """Test accepting Min-Max normalization."""
        self.dialog.minmax_radio.setChecked(True)
        
        # Mock backend return
        expected_data = [MagicMock()]
        self.mock_normalize_instance.data_preprocess.return_value = expected_data
        
        self.dialog.accept()
        
        self.mock_normalize_instance.data_preprocess.assert_called_with(norm="minmax")
        self.assertEqual(self.dialog.get_result(), expected_data)

class TestPreprocessPanelNormalize(unittest.TestCase):
    def setUp(self):
        self.panel = PreprocessPanel()
        self.panel.main_window = MagicMock()
        self.panel.main_window.study = MagicMock()
        self.panel.main_window.study.preprocessed_data_list = [MagicMock()]
        
        # Mock check methods
        self.panel.check_data_loaded = MagicMock(return_value=True)
        self.panel.check_is_epoched = MagicMock(return_value=False)
        self.panel.check_lock = MagicMock(return_value=False)
        self.panel.update_panel = MagicMock()

    @patch('XBrainLab.ui.dashboard_panel.preprocess.NormalizeDialog')
    def test_open_normalize(self, mock_dialog_cls):
        """Test opening normalize dialog."""
        mock_dialog = mock_dialog_cls.return_value
        mock_dialog.exec.return_value = True
        mock_dialog.get_result.return_value = ["new_data"]
        
        self.panel.open_normalize()
        
        # Verify dialog created
        mock_dialog_cls.assert_called_once()
        # Verify result applied via setter
        self.panel.main_window.study.set_preprocessed_data_list.assert_called_once_with(["new_data"])
        self.panel.update_panel.assert_called_once()

if __name__ == '__main__':
    unittest.main()
