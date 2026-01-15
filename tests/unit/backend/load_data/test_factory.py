import pytest
import os
from unittest.mock import MagicMock, patch
from XBrainLab.backend.load_data.factory import RawDataLoaderFactory
from XBrainLab.backend.exceptions import UnsupportedFormatError, FileCorruptedError

def test_factory_registration():
    # Test registering a dummy loader
    mock_loader = MagicMock()
    RawDataLoaderFactory.register_loader('.dummy', mock_loader)
    
    loader = RawDataLoaderFactory.get_loader('test.dummy')
    assert loader == mock_loader

def test_factory_unsupported_format():
    with pytest.raises(UnsupportedFormatError):
        RawDataLoaderFactory.get_loader('test.unknown')

def test_factory_load_success():
    mock_loader = MagicMock(return_value="RawData")
    RawDataLoaderFactory.register_loader('.dummy', mock_loader)
    
    with patch('os.path.exists', return_value=True):
        data = RawDataLoaderFactory.load('test.dummy')
        assert data == "RawData"
        mock_loader.assert_called_once_with('test.dummy')

def test_factory_load_file_not_found():
    with patch('os.path.exists', return_value=False):
        with pytest.raises(FileNotFoundError):
            RawDataLoaderFactory.load('test.dummy')

def test_factory_load_corruption():
    mock_loader = MagicMock(side_effect=Exception("Corrupted"))
    RawDataLoaderFactory.register_loader('.dummy', mock_loader)
    
    with patch('os.path.exists', return_value=True):
        with pytest.raises(FileCorruptedError):
            RawDataLoaderFactory.load('test.dummy')
