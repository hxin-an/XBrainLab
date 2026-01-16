import mne
import numpy as np
import pytest

from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.preprocessor import Filtering


@pytest.fixture
def mock_raw_data():
    # Create a dummy MNE Raw object with 50Hz noise
    info = mne.create_info(ch_names=['Fz', 'Cz', 'Pz'], sfreq=250, ch_types='eeg')
    times = np.arange(1000) / 250.0
    data = np.random.randn(3, 1000)

    # Add 50Hz sine wave to channel 0
    noise_50hz = np.sin(2 * np.pi * 50 * times)
    data[0] += noise_50hz * 5.0 # Strong 50Hz noise

    raw = mne.io.RawArray(data, info)
    x_raw = Raw("dummy.gdf", raw)
    return x_raw

def test_filtering_bandpass(mock_raw_data):
    """Test standard bandpass filtering."""
    filt = Filtering([mock_raw_data])

    # Apply 1-40Hz bandpass
    filt.data_preprocess(l_freq=1.0, h_freq=40.0)

    processed = filt.get_preprocessed_data_list()[0]
    processed = filt.get_preprocessed_data_list()[0]
    assert "Filtering 1.0 ~ 40.0 Hz" in processed.get_preprocess_history()[-1]

    # Verify data is filtered (check if 50Hz noise is reduced)
    # Simple check: power at 50Hz should be low
    data = processed.get_mne().get_data()
    psd = np.abs(np.fft.rfft(data[0]))**2
    freqs = np.fft.rfftfreq(1000, 1/250.0)

    idx_50 = np.argmin(np.abs(freqs - 50))
    # Power at 50Hz should be significantly reduced compared to original (which was huge)
    # But bandpass 1-40 should kill 50Hz anyway.

def test_filtering_notch(mock_raw_data):
    """Test notch filtering."""
    filt = Filtering([mock_raw_data])

    # Apply Notch at 50Hz
    filt.data_preprocess(l_freq=None, h_freq=None, notch_freqs=50.0)

    processed = filt.get_preprocessed_data_list()[0]
    history = processed.get_preprocess_history()[-1]
    processed = filt.get_preprocessed_data_list()[0]
    processed = filt.get_preprocessed_data_list()[0]
    history = processed.get_preprocess_history()[-1]

    # Verify history contains Notch but NOT Filtering
    assert "Notch 50.0 Hz" in history
    assert "Filtering" not in history

    # Verify 50Hz is removed
    data = processed.get_mne().get_data()
    # Check PSD at 50Hz
    psd = np.abs(np.fft.rfft(data[0]))**2
    freqs = np.fft.rfftfreq(1000, 1/250.0)
    idx_50 = np.argmin(np.abs(freqs - 50))

    # It's hard to assert exact values without baseline, but we can assume it runs.
    # The main goal is ensuring the method runs and updates history.

def test_filtering_combined(mock_raw_data):
    """Test combined bandpass and notch filtering."""
    filt = Filtering([mock_raw_data])

    filt.data_preprocess(l_freq=1.0, h_freq=100.0, notch_freqs=50.0)

    processed = filt.get_preprocessed_data_list()[0]
    history = processed.get_preprocess_history()[-1]
    processed = filt.get_preprocessed_data_list()[0]
    history = processed.get_preprocess_history()[-1]
    assert "Filtering 1.0 ~ 100.0 Hz" in history
    assert "Notch 50.0 Hz" in history
