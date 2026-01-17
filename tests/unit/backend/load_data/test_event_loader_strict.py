import mne
import numpy as np
import pytest

from XBrainLab.backend.load_data import EventLoader, Raw


def _generate_mne_raw(fs=100, duration=1):
    info = mne.create_info(ch_names=["O1", "O2"], sfreq=fs, ch_types="eeg")
    data = np.random.randn(2, fs * duration)
    return mne.io.RawArray(data, info)


def test_event_loader_raw_no_events_raises_error():
    """Test that loading labels for Raw data without events raises ValueError."""
    raw_mne = _generate_mne_raw()
    raw = Raw("test.fif", raw_mne)

    # Ensure no events
    assert not raw.has_event()

    loader = EventLoader(raw)
    loader.label_list = [1, 2, 3]
    mapping = {1: "A", 2: "B", 3: "C"}

    # Expect ValueError because we cannot sync timestamps
    # Expect ValueError because raw has no events
    with pytest.raises(
        ValueError, match=r"Raw data has no events for sequence alignment"
    ):
        loader.create_event(mapping)


def test_event_loader_raw_mismatch_truncates():
    """Test that loading labels with count mismatch truncates to minimum."""
    raw_mne = _generate_mne_raw()
    raw = Raw("test.fif", raw_mne)

    # Set 2 events
    events = np.array([[10, 0, 1], [20, 0, 1]])
    event_id = {"A": 1}
    raw.set_event(events, event_id)

    loader = EventLoader(raw)
    loader.label_list = [1, 2, 3]  # 3 labels vs 2 events
    mapping = {1: "A", 2: "B", 3: "C"}

    # Should NOT raise error, but truncate
    new_events, _ = loader.create_event(mapping)

    assert len(new_events) == 2
    assert new_events[0, -1] == 1
    assert new_events[1, -1] == 2


def test_event_loader_epochs_fallback_ok():
    """Test that Epochs data still allows artificial timestamps (indices)."""
    raw_mne = _generate_mne_raw()
    events = np.array([[10, 0, 1], [20, 0, 1]])
    event_id = {"A": 1}
    epochs_mne = mne.Epochs(raw_mne, events, event_id, tmin=0, tmax=0.1, baseline=None)

    raw_epochs = Raw("test.fif", epochs_mne)

    loader = EventLoader(raw_epochs)
    loader.label_list = [1, 2]
    mapping = {1: "A", 2: "B"}

    # Should NOT raise error, but create events with index timestamps
    events, _ = loader.create_event(mapping)

    assert len(events) == 2
    # Since we provided matching count (2 labels, 2 events), it syncs with
    # existing events [10, 20]
    assert events[0, 0] == 10
    assert events[1, 0] == 20
