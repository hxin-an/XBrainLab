from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.exceptions import FileCorruptedError
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.load_data.raw_data_loader import load_gdf_file, load_set_file


class TestRawDataLoaderUnit:
    """
    Unit tests for raw_data_loader.py
    Uses mocking to avoid actual file I/O.
    """

    @patch("XBrainLab.backend.load_data.raw.validate_type")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_gdf")
    def test_load_gdf_success(self, mock_read_gdf, mock_validate):
        """Test successful GDF loading with mocked MNE."""
        # Setup mock return value
        mock_raw = MagicMock()
        mock_read_gdf.return_value = mock_raw

        # Execute
        result = load_gdf_file("dummy.gdf")

        # Verify
        mock_read_gdf.assert_called_once_with("dummy.gdf", preload=False)
        assert isinstance(result, Raw)
        assert result.get_mne() == mock_raw

    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_gdf")
    def test_load_gdf_failure(self, mock_read_gdf):
        """Test GDF loading failure handling."""
        # Setup mock to raise exception
        mock_read_gdf.side_effect = Exception("File corrupted")

        # Execute & Verify
        # Execute & Verify

        with pytest.raises(FileCorruptedError):
            load_gdf_file("corrupted.gdf")

    @patch("XBrainLab.backend.load_data.raw.validate_type")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_eeglab")
    def test_load_set_raw_success(self, mock_read_eeglab, mock_validate):
        """Test successful SET loading as Raw."""
        mock_raw = MagicMock()
        mock_read_eeglab.return_value = mock_raw

        result = load_set_file("dummy.set")

        mock_read_eeglab.assert_called_once()
        assert isinstance(result, Raw)
        assert result.get_mne() == mock_raw

    @patch("XBrainLab.backend.load_data.raw.validate_type")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_epochs_eeglab")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_eeglab")
    def test_load_set_fallback_to_epochs(
        self, mock_read_raw, mock_read_epochs, mock_validate
    ):
        """Test fallback to Epochs when Raw loading fails with TypeError."""
        # Raw loading fails
        mock_read_raw.side_effect = TypeError("Not a raw file")
        # Epochs loading succeeds
        mock_epochs = MagicMock()
        mock_read_epochs.return_value = mock_epochs

        result = load_set_file("epochs.set")

        mock_read_raw.assert_called_once()
        mock_read_epochs.assert_called_once()
        assert isinstance(result, Raw)
        assert result.get_mne() == mock_epochs
