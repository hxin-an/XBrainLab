import os
import pytest
import numpy as np
from XBrainLab.load_data.raw_data_loader import load_gdf_file
from XBrainLab.load_data import Raw

# Path to the small test data provided in the repo
TEST_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'test_data_small'))
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
        
        # 2. Verify metadata (Based on known properties of A01T.gdf if possible, 
        #    or just sanity checks)
        assert raw.get_nchan() > 0
        assert raw.get_sfreq() > 0
        assert raw.get_filepath() == GDF_FILE
        
        # 3. Verify data is loaded (preload=True)
        assert raw.get_mne()._data is not None
        
        # 4. Check shape
        n_channels = raw.get_nchan()
        n_times = raw.get_mne().n_times
        assert raw.get_mne()._data.shape == (n_channels, n_times)

    def test_load_non_existent_file(self):
        """Test loading a file that does not exist."""
        fake_path = os.path.join(TEST_DATA_DIR, 'non_existent.gdf')
        raw = load_gdf_file(fake_path)
        assert raw is None

    def test_load_invalid_extension(self):
        """Test loading a file with wrong extension (though loader might just try to read it)."""
        # Create a dummy text file
        dummy_path = os.path.join(TEST_DATA_DIR, 'dummy.txt')
        with open(dummy_path, 'w') as f:
            f.write("This is not a GDF file.")
            
        try:
            raw = load_gdf_file(dummy_path)
            assert raw is None
        finally:
            if os.path.exists(dummy_path):
                os.remove(dummy_path)
