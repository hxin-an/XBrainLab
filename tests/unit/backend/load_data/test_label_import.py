from unittest.mock import MagicMock

import mne
import numpy as np
import pytest

from XBrainLab.backend.load_data.event_loader import EventLoader
from XBrainLab.backend.load_data.raw import Raw


@pytest.fixture
def mock_raw():
    raw = MagicMock(spec=Raw)
    raw.is_raw.return_value = True
    raw.get_mne.return_value = MagicMock()
    return raw


def test_timestamp_import():
    info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
    mne_raw = mne.io.RawArray(np.zeros((1, 300)), info, verbose=False)
    raw = Raw("timestamp.fif", mne_raw)
    loader = EventLoader(raw)
    # Simulate list of dicts from CSV
    loader.label_list = [
        {"onset": 1.0, "duration": 0.5, "label": "Event A"},
        {"onset": 2.0, "duration": 0.5, "label": "Event B"},
    ]

    events, event_id = loader.create_event({})
    loader.apply()

    assert loader.annotations is not None
    assert len(loader.annotations) == 2
    assert loader.annotations.onset[0] == 1.0
    assert loader.annotations.description[0] == "Event A"
    assert events is not None
    assert events[:, 0].tolist() == [100, 200]
    assert event_id == {"Event A": 1, "Event B": 2}


def test_smart_filter(mock_raw):
    loader = EventLoader(mock_raw)
    # Mock raw events: ID 1 (100 times), ID 2 (5 times)
    events = np.zeros((105, 3), dtype=int)
    events[:100, 2] = 1
    events[100:, 2] = 2

    mock_raw.has_event.return_value = True
    mock_raw.get_event_list.return_value = (events, {"A": 1, "B": 2})

    # Target count 100 -> Should suggest ID 1
    suggestions = loader.smart_filter(100)
    assert suggestions == [1]

    # Target count 5 -> Should suggest ID 2
    suggestions = loader.smart_filter(5)
    assert suggestions == [2]


def test_sequence_alignment_perfect(mock_raw):
    loader = EventLoader(mock_raw)
    loader.label_list = np.array([1, 2, 3])

    # Mock raw events: 3 events
    events = np.zeros((3, 3), dtype=int)
    events[:, 0] = [10, 20, 30]
    events[:, 2] = [100, 100, 100]  # Dummy trigger ID

    mock_raw.has_event.return_value = True
    mock_raw.get_event_list.return_value = (events, {"Trigger": 100})

    mapping = {1: "A", 2: "B", 3: "C"}
    events_out, _event_id_out = loader.create_event(mapping)

    assert events_out is not None
    assert len(events_out) == 3
    assert np.array_equal(events_out[:, 2], [1, 2, 3])
    assert events_out[0, 0] == 10


def test_sequence_alignment_mismatch(mock_raw):
    loader = EventLoader(mock_raw)
    loader.label_list = np.array([1, 2])  # 2 labels

    # Mock raw events: 3 events (1 extra)
    events = np.zeros((3, 3), dtype=int)
    events[:, 0] = [10, 20, 30]
    events[:, 2] = [100, 100, 100]

    mock_raw.has_event.return_value = True
    mock_raw.get_event_list.return_value = (events, {"Trigger": 100})

    mapping = {1: "A", 2: "B"}

    with pytest.raises(ValueError, match="Label count does not match"):
        loader.create_event(mapping)
