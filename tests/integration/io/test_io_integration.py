import os

import pytest

from XBrainLab.backend.facade import BackendFacade
from XBrainLab.backend.exceptions import FileCorruptedError
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.load_data.raw_data_loader import load_gdf_file, load_raw_data

# Path to the small real-data fixtures stored under tests/data
TEST_DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data"),
)
GDF_FILE = os.path.join(TEST_DATA_DIR, "A01T.gdf")
MULTIFORMAT_DIR = os.path.join(TEST_DATA_DIR, "multiformat")
PUBLIC_DATA_DIR = os.path.join(TEST_DATA_DIR, "public")
REAL_DATA_FIXTURES = [
    GDF_FILE,
    os.path.join(MULTIFORMAT_DIR, "A01T-mini-real_raw.fif"),
    os.path.join(MULTIFORMAT_DIR, "A01T-mini-real_raw.fif.gz"),
    os.path.join(MULTIFORMAT_DIR, "A01T-mini-real.edf"),
    os.path.join(MULTIFORMAT_DIR, "A01T-mini-real.bdf"),
    os.path.join(MULTIFORMAT_DIR, "A01T-mini-real.vhdr"),
    os.path.join(MULTIFORMAT_DIR, "A01T-mini-real.set"),
    os.path.join(MULTIFORMAT_DIR, "A01T-mini-real-epo.fif"),
]
PUBLIC_REAL_DATA_FIXTURES = [
    os.path.join(PUBLIC_DATA_DIR, "physionet-eegmmidb-S008R01.edf"),
    os.path.join(PUBLIC_DATA_DIR, "bbci-competition-iii-O3VR.gdf"),
    os.path.join(PUBLIC_DATA_DIR, "sccn-eeglab_data.set"),
]


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
        # n_times might vary if not preloaded vs preloaded,
        # but get_data() returns full array
        assert data.shape[0] == n_channels
        assert data.shape[1] > 0

    @pytest.mark.parametrize("filepath", REAL_DATA_FIXTURES)
    def test_load_supported_real_formats(self, filepath):
        """Load compact real-data fixtures across several supported extensions."""
        if not os.path.exists(filepath):
            pytest.skip(f"Test data not found at {filepath}")

        raw = load_raw_data(filepath)

        assert raw is not None
        assert isinstance(raw, Raw)
        assert raw.get_filepath() == filepath
        assert raw.get_nchan() > 0
        assert raw.get_sfreq() > 0

        data = raw.get_mne().get_data()
        assert data is not None
        assert data.ndim in (2, 3)
        if data.ndim == 2:
            assert data.shape[0] == raw.get_nchan()
            assert data.shape[1] > 0
        else:
            assert data.shape[1] == raw.get_nchan()
            assert data.shape[0] > 0
            assert data.shape[2] > 0

    @pytest.mark.parametrize("filepath", REAL_DATA_FIXTURES)
    def test_facade_import_supported_real_formats(self, filepath):
        """Exercise the real dataset import entrypoint across multiple formats."""
        if not os.path.exists(filepath):
            pytest.skip(f"Test data not found at {filepath}")

        facade = BackendFacade()
        success_count, errors = facade.load_data([filepath])

        assert success_count == 1
        assert errors == []

        summary = facade.get_data_summary()
        assert summary["count"] == 1
        assert summary["files"] == [os.path.basename(filepath)]

    @pytest.mark.parametrize("filepath", PUBLIC_REAL_DATA_FIXTURES)
    def test_load_public_real_formats(self, filepath):
        """Load small public EEG fixtures from different sources and formats."""
        if not os.path.exists(filepath):
            pytest.skip(f"Public test data not found at {filepath}")

        raw = load_raw_data(filepath)

        assert raw is not None
        assert isinstance(raw, Raw)
        assert raw.get_filepath() == filepath
        assert raw.get_nchan() > 0
        assert raw.get_sfreq() > 0

        data = raw.get_mne().get_data()
        assert data is not None
        assert data.ndim in (2, 3)

    @pytest.mark.parametrize("filepath", PUBLIC_REAL_DATA_FIXTURES)
    def test_facade_import_public_real_formats(self, filepath):
        """Exercise the facade import entrypoint across downloaded public EEG fixtures."""
        if not os.path.exists(filepath):
            pytest.skip(f"Public test data not found at {filepath}")

        facade = BackendFacade()
        success_count, errors = facade.load_data([filepath])

        assert success_count == 1
        assert errors == []

        summary = facade.get_data_summary()
        assert summary["count"] == 1
        assert summary["files"] == [os.path.basename(filepath)]

    def test_load_non_existent_file(self):
        """Test loading a file that does not exist."""
        fake_path = os.path.join(TEST_DATA_DIR, "non_existent.gdf")
        with pytest.raises((FileCorruptedError, FileNotFoundError)):
            load_gdf_file(fake_path)

    def test_load_invalid_extension(self, tmp_path):
        """Test loading a file with wrong extension."""
        dummy_path = str(tmp_path / "dummy.txt")
        with open(dummy_path, "w") as f:
            f.write("This is not a GDF file.")

        with pytest.raises((FileCorruptedError, FileNotFoundError, ValueError)):
            load_gdf_file(dummy_path)
