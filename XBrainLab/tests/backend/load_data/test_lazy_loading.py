import pytest
from unittest.mock import MagicMock, patch
from XBrainLab.backend.load_data.raw_data_loader import load_gdf_file, load_set_file

@patch('XBrainLab.backend.load_data.raw.validate_type')
@patch('mne.io.read_raw_gdf')
def test_load_gdf_lazy(mock_read_gdf, mock_validate):
    mock_read_gdf.return_value = MagicMock()
    load_gdf_file('test.gdf')
    # Verify preload=False is passed
    mock_read_gdf.assert_called_with('test.gdf', preload=False)

@patch('XBrainLab.backend.load_data.raw.validate_type')
@patch('mne.io.read_raw_eeglab')
def test_load_set_lazy(mock_read_set, mock_validate):
    mock_read_set.return_value = MagicMock()
    load_set_file('test.set')
    # Verify preload=False is passed
    mock_read_set.assert_called_with('test.set', uint16_codec='latin1', preload=False)
