import warnings
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

    @patch("XBrainLab.backend.load_data.raw.validate_type")
    @patch("XBrainLab.backend.load_data.raw_data_loader.logger.warning")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_gdf")
    def test_load_gdf_logs_duplicate_channel_signal(
        self,
        mock_read_gdf,
        mock_logger_warning,
        mock_validate,
    ):
        """Surface a repo-specific warning when MNE auto-renames duplicate names."""
        mock_raw = MagicMock()
        mock_raw.info = {"ch_names": ["EEG-Fz", "EEG-0", "EEG-1", "EEG-Cz"]}

        def fake_read(*args, **kwargs):
            warnings.warn(
                "Channel names are not unique, found duplicates for: {'EEG'}. "
                "Applying running numbers for duplicates.",
                RuntimeWarning,
                stacklevel=1,
            )
            return mock_raw

        mock_read_gdf.side_effect = fake_read

        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            result = load_gdf_file("dummy.gdf")

        assert isinstance(result, Raw)
        assert result.get_mne() == mock_raw
        mock_logger_warning.assert_called_once()
        assert (
            "auto-renaming duplicate channel names"
            in mock_logger_warning.call_args[0][1]
        )
        assert "dummy.gdf" in mock_logger_warning.call_args[0][1]
        assert result.has_runtime_signals()
        assert (
            "auto-renaming duplicate channel names" in result.get_runtime_signals()[0]
        )
        assert result.has_runtime_detail("gdf_duplicate_channel_names")
        assert result.has_gdf_duplicate_channel_detail()
        assert result.get_gdf_duplicate_channel_detail() == {
            "kind": "gdf_duplicate_channel_names",
            "filepath": "dummy.gdf",
            "generated_bases": ["EEG"],
            "generated_channels": ["EEG-0", "EEG-1"],
            "message": result.get_runtime_signals()[0],
        }
        assert any(
            "Channel names are not unique" in str(caught_warning.message)
            for caught_warning in caught_warnings
        )

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
