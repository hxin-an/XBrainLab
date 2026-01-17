import mne
import numpy as np
import pytest

from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.preprocessor import Rereference


@pytest.fixture
def mock_raw_data():
    info = mne.create_info(ch_names=["Fz", "Cz", "Pz"], sfreq=100, ch_types="eeg")
    data = np.random.randn(3, 1000)
    raw = mne.io.RawArray(data, info)
    x_raw = Raw("dummy.gdf", raw)
    return x_raw


def test_rereference_average(mock_raw_data):
    proc = Rereference([mock_raw_data])

    # Apply average reference
    proc.data_preprocess(ref_channels="average")

    processed = proc.get_preprocessed_data_list()[0]
    data = processed.get_mne().get_data()

    # Check if sum of channels is close to 0 (property of average reference)
    # Sum across channels for each time point should be 0
    assert np.allclose(data.sum(axis=0), 0, atol=1e-10)

    assert "Average" in processed.get_preprocess_history()[-1]


def test_rereference_specific_channel(mock_raw_data):
    proc = Rereference([mock_raw_data])

    # Use Cz (index 1) as reference
    proc.data_preprocess(ref_channels=["Cz"])

    processed = proc.get_preprocessed_data_list()[0]
    data = processed.get_mne().get_data()

    # Cz should be flat (0)
    assert np.allclose(data[1, :], 0, atol=1e-10)

    assert "Channels: ['Cz']" in processed.get_preprocess_history()[-1]
