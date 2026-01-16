
import unittest
from unittest.mock import MagicMock, patch

from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.load_data.raw_data_loader import (
    load_bdf_file,
    load_brainvision_file,
    load_cnt_file,
    load_edf_file,
    load_fif_file,
)


class TestLoaders(unittest.TestCase):

    def setUp(self):
        # Patch validate_type to bypass strict type checking for mocks
        self.patcher = patch('XBrainLab.backend.load_data.raw.validate_type')
        self.mock_validate = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    @patch('mne.io.read_raw_fif')
    def test_load_fif_file(self, mock_read):
        mock_read.return_value = MagicMock()
        result = load_fif_file('test.fif')
        self.assertIsInstance(result, Raw)
        mock_read.assert_called_with('test.fif', preload=False)

    @patch('mne.io.read_raw_edf')
    def test_load_edf_file(self, mock_read):
        mock_read.return_value = MagicMock()
        result = load_edf_file('test.edf')
        self.assertIsInstance(result, Raw)
        mock_read.assert_called_with('test.edf', preload=False)

    @patch('mne.io.read_raw_bdf')
    def test_load_bdf_file(self, mock_read):
        mock_read.return_value = MagicMock()
        result = load_bdf_file('test.bdf')
        self.assertIsInstance(result, Raw)
        mock_read.assert_called_with('test.bdf', preload=False)

    @patch('mne.io.read_raw_cnt')
    def test_load_cnt_file(self, mock_read):
        mock_read.return_value = MagicMock()
        result = load_cnt_file('test.cnt')
        self.assertIsInstance(result, Raw)
        mock_read.assert_called_with('test.cnt', preload=False)

    @patch('mne.io.read_raw_brainvision')
    def test_load_brainvision_file(self, mock_read):
        mock_read.return_value = MagicMock()
        result = load_brainvision_file('test.vhdr')
        self.assertIsInstance(result, Raw)
        mock_read.assert_called_with('test.vhdr', preload=False)

    @patch('mne.io.read_raw_fif')
    def test_load_fif_failure(self, mock_read):
        mock_read.side_effect = Exception("Load failed")
        from XBrainLab.backend.exceptions import FileCorruptedError
        with self.assertRaises(FileCorruptedError):
            load_fif_file('test.fif')
