import os
import pytest
import numpy as np
from XBrainLab.backend.load_data.raw_data_loader import load_gdf_file
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.exceptions import FileCorruptedError

# Path to the small test data provided in the repo
TEST_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'test_data_small'))
GDF_FILE = os.path.join(TEST_DATA_DIR, 'A01T.gdf')

class TestIOIntegration:
    """
    Integration tests for data loading module.
    Verifies that we can actually load real files from disk.
    """

    def test_load_gdf_file_success(self):
        """Test loading a valid GDF file."""
        # Ensure the test file exists before trying to load
        if not os.path.exists(GDF_FILE):
            pytest.skip(f"Test data not found at {GDF_FILE}")

        raw = load_gdf_file(GDF_FILE)
        
        # 1. Verify return type
        assert raw is not None
        assert isinstance(raw, Raw)
        
        # 2. Verify metadata
        assert raw.get_nchan() > 0
        assert raw.get_sfreq() > 0
        assert raw.get_filepath() == GDF_FILE
        
        # 3. Verify data access (preload=False by default now)
        # Use get_data() instead of private _data
        data = raw.get_mne().get_data()
        assert data is not None
        
        # 4. Check shape
        n_channels = raw.get_nchan()
        # n_times might vary if not preloaded vs preloaded, but get_data() returns full array
        assert data.shape[0] == n_channels
        assert data.shape[1] > 0

    def test_load_non_existent_file(self):
        """Test loading a file that does not exist."""
        fake_path = os.path.join(TEST_DATA_DIR, 'non_existent.gdf')
        with pytest.raises((FileCorruptedError, FileNotFoundError)):
            load_gdf_file(fake_path)

    def test_load_invalid_extension(self):
        """Test loading a file with wrong extension."""
        # Create a dummy text file
        dummy_path = os.path.join(TEST_DATA_DIR, 'dummy.txt')
        with open(dummy_path, 'w') as f:
            f.write("This is not a GDF file.")
            
        try:
            with pytest.raises((FileCorruptedError, FileNotFoundError, ValueError)):
                load_gdf_file(dummy_path)
        finally:
            if os.path.exists(dummy_path):
                os.remove(dummy_path)
