import unittest

from XBrainLab.ui.dialogs.preprocess import NormalizeDialog


class TestNormalizeDialog(unittest.TestCase):
    def test_dialog_params(self):
        dialog = NormalizeDialog(None)
        dialog.zscore_radio.setChecked(True)
        dialog.accept()
        self.assertEqual(dialog.get_params(), "z score")
        dialog.minmax_radio.setChecked(True)
        dialog.accept()
        self.assertEqual(dialog.get_params(), "minmax")
