import mne
import numpy as np
import pytest

from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.preprocessor import Filtering


@pytest.fixture
def mock_raw_data():
    # Create a dummy MNE Raw object with 50Hz noise
    info = mne.create_info(ch_names=["Fz", "Cz", "Pz"], sfreq=250, ch_types="eeg")
    times = np.arange(1000) / 250.0
    data = np.random.randn(3, 1000)

    # Add 50Hz sine wave to channel 0
    noise_50hz = np.sin(2 * np.pi * 50 * times)
    data[0] += noise_50hz * 5.0  # Strong 50Hz noise

    raw = mne.io.RawArray(data, info)
    x_raw = Raw("dummy.gdf", raw)
    return x_raw


def test_filtering_bandpass(mock_raw_data):
    """Test standard bandpass filtering."""
    # Capture original 50Hz power
    orig_data = mock_raw_data.get_mne().get_data()
    orig_psd = np.abs(np.fft.rfft(orig_data[0])) ** 2
    freqs = np.fft.rfftfreq(1000, 1 / 250.0)
    idx_50 = np.argmin(np.abs(freqs - 50))
    orig_power_50 = orig_psd[idx_50]

    filt = Filtering([mock_raw_data])

    # Apply 1-40Hz bandpass
    filt.data_preprocess(l_freq=1.0, h_freq=40.0)

    processed = filt.get_preprocessed_data_list()[0]
    assert "Filtering 1.0 ~ 40.0 Hz" in processed.get_preprocess_history()[-1]

    # Verify 50Hz power is significantly reduced
    data = processed.get_mne().get_data()
    psd = np.abs(np.fft.rfft(data[0])) ** 2
    assert psd[idx_50] < orig_power_50 * 0.1, "50Hz power not sufficiently reduced"


def test_filtering_notch(mock_raw_data):
    """Test notch filtering."""
    # Capture original 50Hz power
    orig_data = mock_raw_data.get_mne().get_data()
    orig_psd = np.abs(np.fft.rfft(orig_data[0])) ** 2
    freqs = np.fft.rfftfreq(1000, 1 / 250.0)
    idx_50 = np.argmin(np.abs(freqs - 50))
    orig_power_50 = orig_psd[idx_50]

    filt = Filtering([mock_raw_data])

    # Apply Notch at 50Hz
    filt.data_preprocess(l_freq=None, h_freq=None, notch_freqs=50.0)

    processed = filt.get_preprocessed_data_list()[0]
    history = processed.get_preprocess_history()[-1]

    # Verify history contains Notch but NOT Filtering
    assert "Notch 50.0 Hz" in history
    assert "Filtering" not in history

    # Verify 50Hz power is reduced
    data = processed.get_mne().get_data()
    psd = np.abs(np.fft.rfft(data[0])) ** 2
    assert psd[idx_50] < orig_power_50 * 0.5, "Notch did not reduce 50Hz power"


def test_filtering_combined(mock_raw_data):
    """Test combined bandpass and notch filtering."""
    filt = Filtering([mock_raw_data])

    filt.data_preprocess(l_freq=1.0, h_freq=100.0, notch_freqs=50.0)

    processed = filt.get_preprocessed_data_list()[0]
    history = processed.get_preprocess_history()[-1]
    assert "Filtering 1.0 ~ 100.0 Hz" in history
    assert "Notch 50.0 Hz" in history
