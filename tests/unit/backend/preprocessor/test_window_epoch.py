"""Unit tests for preprocessor/window_epoch — WindowEpoch."""

import mne
import numpy as np
import pytest

from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.preprocessor.window_epoch import WindowEpoch


def _make_raw_with_single_event(duration=10.0):
    """Create raw data with exactly one event label (required by WindowEpoch)."""
    sfreq = 256
    info = mne.create_info(["Cz", "Fz"], sfreq=sfreq, ch_types="eeg")
    n_samples = int(duration * sfreq)
    data = np.random.randn(2, n_samples)
    raw_mne = mne.io.RawArray(data, info)

    # Add a single annotation spanning the full signal
    raw_mne.set_annotations(
        mne.Annotations(onset=[0.0], duration=[duration], description=["rest"])
    )
    raw = Raw("test.gdf", raw_mne)
    # Manually set event list for single-event raw
    events = np.array([[0, 0, 1]])
    event_id = {"rest": 1}
    raw.set_event(events, event_id)
    return raw


def _make_epoch_raw():
    """Create already-epoched data."""
    info = mne.create_info(["Cz"], sfreq=256, ch_types="eeg")
    data = np.random.randn(3, 1, 256)
    epochs = mne.EpochsArray(data, info)
    return Raw("test.gdf", epochs)


def _make_raw_no_events():
    """Create raw data with no events."""
    info = mne.create_info(["Cz"], sfreq=256, ch_types="eeg")
    raw_mne = mne.io.RawArray(np.random.randn(1, 2560), info)
    raw = Raw("test.gdf", raw_mne)
    return raw


def _make_raw_multi_events():
    """Create raw data with multiple event labels."""
    info = mne.create_info(["Cz"], sfreq=256, ch_types="eeg")
    raw_mne = mne.io.RawArray(np.random.randn(1, 2560), info)
    raw = Raw("test.gdf", raw_mne)
    events = np.array([[0, 0, 1], [256, 0, 2]])
    event_id = {"left": 1, "right": 2}
    raw.set_event(events, event_id)
    return raw


class TestWindowEpochCheckData:
    def test_rejects_already_epoched(self):
        raw = _make_epoch_raw()
        with pytest.raises(ValueError):
            WindowEpoch([raw])  # check_data called in __init__

    def test_rejects_no_events(self):
        raw = _make_raw_no_events()
        with pytest.raises(ValueError):
            WindowEpoch([raw])  # check_data called in __init__

    def test_rejects_multiple_events(self):
        raw = _make_raw_multi_events()
        with pytest.raises(ValueError):
            WindowEpoch([raw])  # check_data called in __init__

    def test_accepts_single_event_raw(self):
        raw = _make_raw_with_single_event()
        pp = WindowEpoch([raw])  # should not raise


class TestWindowEpochDesc:
    def test_description(self):
        raw = _make_raw_with_single_event()
        pp = WindowEpoch([raw])
        desc = pp.get_preprocess_desc(duration=2.0, overlap=0.5)
        assert "2.0s" in desc
        assert "0.5s" in desc
        assert "sliding window" in desc.lower()


class TestWindowEpochDataPreprocess:
    """Tests for the core _data_preprocess sliding-window logic."""

    def test_basic_epoching(self):
        """Non-overlapping 2s windows on 10s raw → 5 epochs."""
        raw = _make_raw_with_single_event(duration=10.0)
        pp = WindowEpoch([raw])
        pp._data_preprocess(raw, duration=2.0, overlap=0.0)
        mne_data = raw.get_mne()
        assert isinstance(mne_data, mne.BaseEpochs)
        assert len(mne_data) == 5

    def test_overlap_produces_more_epochs(self):
        """Overlapping windows should produce more epochs than non-overlapping."""
        raw_no_overlap = _make_raw_with_single_event(duration=10.0)
        pp1 = WindowEpoch([raw_no_overlap])
        pp1._data_preprocess(raw_no_overlap, duration=2.0, overlap=0.0)

        raw_overlap = _make_raw_with_single_event(duration=10.0)
        pp2 = WindowEpoch([raw_overlap])
        pp2._data_preprocess(raw_overlap, duration=2.0, overlap=1.0)

        assert len(raw_overlap.get_mne()) > len(raw_no_overlap.get_mne())

    def test_empty_string_overlap_treated_as_zero(self):
        """overlap='' (from UI) should be treated as 0.0."""
        raw = _make_raw_with_single_event(duration=10.0)
        pp = WindowEpoch([raw])
        pp._data_preprocess(raw, duration=2.0, overlap="")
        mne_data = raw.get_mne()
        # Same result as overlap=0.0 → 5 epochs for 10s / 2s
        assert len(mne_data) == 5

    def test_event_id_preserved(self):
        """Original event label key should be preserved after epoching."""
        raw = _make_raw_with_single_event(duration=10.0)
        pp = WindowEpoch([raw])
        pp._data_preprocess(raw, duration=2.0, overlap=0.0)
        mne_data = raw.get_mne()
        assert "rest" in mne_data.event_id
