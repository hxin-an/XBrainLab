from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.exceptions import FileCorruptedError, UnsupportedFormatError
from XBrainLab.backend.load_data.factory import RawDataLoaderFactory
from XBrainLab.backend.load_data.raw_data_loader import load_fif_file


def test_factory_registration():
    # Test registering a dummy loader
    mock_loader = MagicMock()
    RawDataLoaderFactory.register_loader(".dummy", mock_loader)

    loader = RawDataLoaderFactory.get_loader("test.dummy")
    assert loader == mock_loader


def test_factory_unsupported_format():
    with pytest.raises(UnsupportedFormatError):
        RawDataLoaderFactory.get_loader("test.unknown")


def test_factory_load_success():
    mock_loader = MagicMock(return_value="RawData")
    RawDataLoaderFactory.register_loader(".dummy", mock_loader)

    with patch("os.path.exists", return_value=True):
        data = RawDataLoaderFactory.load("test.dummy")
        assert data == "RawData"
        mock_loader.assert_called_once_with("test.dummy")


def test_factory_load_file_not_found():
    with (
        patch("os.path.exists", return_value=False),
        pytest.raises(FileNotFoundError),
    ):
        RawDataLoaderFactory.load("test.dummy")


def test_factory_load_corruption():
    mock_loader = MagicMock(side_effect=Exception("Corrupted"))
    RawDataLoaderFactory.register_loader(".dummy", mock_loader)

    with (
        patch("os.path.exists", return_value=True),
        pytest.raises(FileCorruptedError),
    ):
        RawDataLoaderFactory.load("test.dummy")


def test_factory_supports_double_extension_fif_gz():
    loader = RawDataLoaderFactory.get_loader("subject01-epo.fif.gz")
    assert loader == load_fif_file
