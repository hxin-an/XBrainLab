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

    new_events, _ = loader.create_event(mapping)

    assert new_events is not None
    assert len(new_events) == 2
    assert new_events[0, -1] == 1
    assert new_events[1, -1] == 2


def test_event_loader_empty_labels_raises():
    """Empty labels should fail clearly instead of producing empty events."""
    raw_mne = _generate_mne_raw()
    raw = Raw("test.fif", raw_mne)
    raw.set_event(np.array([[10, 0, 1]]), {"A": 1})

    loader = EventLoader(raw)
    loader.label_list = []

    with pytest.raises(ValueError, match="Loaded labels are empty"):
        loader.create_event({1: "A"})


def test_event_loader_filtered_events_empty_raises():
    """A selected event filter with no matches should fail clearly."""
    raw_mne = _generate_mne_raw()
    raw = Raw("test.fif", raw_mne)
    raw.set_event(np.array([[10, 0, 1], [20, 0, 1]]), {"A": 1})

    loader = EventLoader(raw)
    loader.label_list = [1, 2]

    with pytest.raises(
        ValueError,
        match="No EEG events matched the selected event filter",
    ):
        loader.create_event({1: "A", 2: "B"}, selected_event_ids=[999])


def test_event_loader_string_labels_assign_sequential_event_ids():
    """Categorical string labels should map to stable integer event IDs."""
    raw_mne = _generate_mne_raw()
    raw = Raw("test.fif", raw_mne)
    raw.set_event(np.array([[10, 0, 1], [20, 0, 1], [30, 0, 1]]), {"A": 1})

    loader = EventLoader(raw)
    loader.label_list = ["left", "right", "left"]

    events, event_id = loader.create_event({"left": "Left", "right": "Right"})

    assert events is not None
    assert events[:, -1].tolist() == [1, 2, 1]
    assert event_id == {"Left": 1, "Right": 2}


def test_event_loader_numeric_string_labels_preserve_numeric_codes():
    """Quoted numeric labels should still preserve their original codes."""
    raw_mne = _generate_mne_raw()
    raw = Raw("test.fif", raw_mne)
    raw.set_event(np.array([[10, 0, 1], [20, 0, 1]]), {"A": 1})

    loader = EventLoader(raw)
    loader.label_list = ["769", "770"]

    events, event_id = loader.create_event({"769": "Left", "770": "Right"})

    assert events is not None
    assert events[:, -1].tolist() == [769, 770]
    assert event_id == {"Left": 769, "Right": 770}


def test_event_loader_timestamp_labels_use_class_map_names():
    """Timestamp labels should expose reviewed class names to Epoch setup."""
    raw_mne = _generate_mne_raw(duration=5)
    raw = Raw("test.fif", raw_mne)

    loader = EventLoader(raw)
    loader.label_list = [
        {"onset": 0.1, "duration": 0.5, "label": "left"},
        {"onset": 1.1, "duration": 0.5, "label": "right"},
    ]

    events, event_id = loader.create_event({"left": "Left hand", "right": "Right hand"})

    assert events is not None
    assert event_id is not None
    assert sorted(event_id) == ["Left hand", "Right hand"]


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

    events, _ = loader.create_event(mapping)

    assert events is not None
    assert len(events) == 2
    # Since we provided matching count (2 labels, 2 events), it syncs with
    # existing events [10, 20]
    assert events[0, 0] == 10
    assert events[1, 0] == 20
