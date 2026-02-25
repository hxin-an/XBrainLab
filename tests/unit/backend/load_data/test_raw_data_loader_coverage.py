"""Extended tests for raw_data_loader covering all format loaders and edge cases.

Covers: load_edf_file, load_bdf_file, load_cnt_file, load_brainvision_file,
load_set_file fallbacks, load_raw_data, and factory registration.
"""

from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.exceptions import FileCorruptedError
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.load_data.raw_data_loader import (
    load_bdf_file,
    load_brainvision_file,
    load_cnt_file,
    load_edf_file,
    load_fif_file,
    load_raw_data,
    load_set_file,
)

# ---------------------------------------------------------------------------
# EDF loader
# ---------------------------------------------------------------------------


class TestLoadEdf:
    @patch("XBrainLab.backend.load_data.raw.validate_type")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_edf")
    def test_success(self, mock_read, mock_validate):
        mock_raw = MagicMock()
        mock_read.return_value = mock_raw
        result = load_edf_file("test.edf")
        assert isinstance(result, Raw)
        mock_read.assert_called_once_with("test.edf", preload=False)

    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_edf")
    def test_failure(self, mock_read):
        mock_read.side_effect = Exception("corrupted")
        with pytest.raises(FileCorruptedError):
            load_edf_file("bad.edf")

    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_edf")
    def test_returns_none(self, mock_read):
        mock_read.return_value = None
        result = load_edf_file("empty.edf")
        assert result is None


# ---------------------------------------------------------------------------
# BDF loader
# ---------------------------------------------------------------------------


class TestLoadBdf:
    @patch("XBrainLab.backend.load_data.raw.validate_type")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_bdf")
    def test_success(self, mock_read, mock_validate):
        mock_raw = MagicMock()
        mock_read.return_value = mock_raw
        result = load_bdf_file("test.bdf")
        assert isinstance(result, Raw)

    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_bdf")
    def test_failure(self, mock_read):
        mock_read.side_effect = Exception("corrupted")
        with pytest.raises(FileCorruptedError):
            load_bdf_file("bad.bdf")


# ---------------------------------------------------------------------------
# CNT loader
# ---------------------------------------------------------------------------


class TestLoadCnt:
    @patch("XBrainLab.backend.load_data.raw.validate_type")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_cnt")
    def test_success(self, mock_read, mock_validate):
        mock_raw = MagicMock()
        mock_read.return_value = mock_raw
        result = load_cnt_file("test.cnt")
        assert isinstance(result, Raw)

    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_cnt")
    def test_failure(self, mock_read):
        mock_read.side_effect = Exception("corrupted")
        with pytest.raises(FileCorruptedError):
            load_cnt_file("bad.cnt")


# ---------------------------------------------------------------------------
# BrainVision loader
# ---------------------------------------------------------------------------


class TestLoadBrainVision:
    @patch("XBrainLab.backend.load_data.raw.validate_type")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_brainvision")
    def test_success(self, mock_read, mock_validate):
        mock_raw = MagicMock()
        mock_read.return_value = mock_raw
        result = load_brainvision_file("test.vhdr")
        assert isinstance(result, Raw)

    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_brainvision")
    def test_failure(self, mock_read):
        mock_read.side_effect = Exception("corrupted")
        with pytest.raises(FileCorruptedError):
            load_brainvision_file("bad.vhdr")


# ---------------------------------------------------------------------------
# FIF loader
# ---------------------------------------------------------------------------


class TestLoadFif:
    @patch("XBrainLab.backend.load_data.raw.validate_type")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_fif")
    def test_success(self, mock_read, mock_validate):
        mock_raw = MagicMock()
        mock_read.return_value = mock_raw
        result = load_fif_file("test.fif")
        assert isinstance(result, Raw)

    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_fif")
    def test_returns_none(self, mock_read):
        mock_read.return_value = None
        result = load_fif_file("empty.fif")
        assert result is None


# ---------------------------------------------------------------------------
# SET loader edge cases
# ---------------------------------------------------------------------------


class TestLoadSetEdgeCases:
    @patch("XBrainLab.backend.load_data.raw.validate_type")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_epochs_eeglab")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_eeglab")
    def test_raw_fails_non_type_error_fallback_epochs(
        self, mock_read_raw, mock_read_epochs, mock_validate
    ):
        """When raw fails with ValueError, fallback to epochs."""
        mock_read_raw.side_effect = ValueError("not raw")
        mock_epochs = MagicMock()
        mock_read_epochs.return_value = mock_epochs
        result = load_set_file("data.set")
        assert isinstance(result, Raw)

    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_epochs_eeglab")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_eeglab")
    def test_both_fail_raises(self, mock_read_raw, mock_read_epochs):
        """When both raw and epochs fail, raise FileCorruptedError."""
        mock_read_raw.side_effect = ValueError("not raw")
        mock_read_epochs.side_effect = Exception("also fails")
        with pytest.raises(FileCorruptedError):
            load_set_file("bad.set")

    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_epochs_eeglab")
    @patch("XBrainLab.backend.load_data.raw_data_loader.mne.io.read_raw_eeglab")
    def test_type_error_then_epochs_fail(self, mock_read_raw, mock_read_epochs):
        """TypeError then epochs also fail -> FileCorruptedError."""
        mock_read_raw.side_effect = TypeError("type err")
        mock_read_epochs.side_effect = Exception("epochs fail")
        with pytest.raises(FileCorruptedError):
            load_set_file("bad.set")


# ---------------------------------------------------------------------------
# load_raw_data (factory entry point)
# ---------------------------------------------------------------------------


class TestLoadRawData:
    @patch("XBrainLab.backend.load_data.raw_data_loader.RawDataLoaderFactory.load")
    def test_success(self, mock_factory_load):
        mock_raw = MagicMock(spec=Raw)
        mock_factory_load.return_value = mock_raw
        result = load_raw_data("test.edf")
        assert result == mock_raw

    @patch("XBrainLab.backend.load_data.raw_data_loader.RawDataLoaderFactory.load")
    def test_returns_none_raises(self, mock_factory_load):
        mock_factory_load.return_value = None
        with pytest.raises(ValueError, match="Failed to load"):
            load_raw_data("test.edf")
