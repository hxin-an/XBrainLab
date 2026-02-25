"""Unit tests for preprocessor/edit_event — EditEventName and EditEventId."""

import logging

import mne
import numpy as np
import pytest

from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.preprocessor.edit_event import EditEventId, EditEventName


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_epoch_raw(event_id=None):
    """Create an epoched Raw with specified event_id mapping."""
    if event_id is None:
        event_id = {"left": 1, "right": 2}
    info = mne.create_info(["Cz"], sfreq=256, ch_types="eeg")
    n_events = 6
    data = np.random.randn(n_events, 1, 256)
    events = np.column_stack(
        [
            np.arange(n_events) * 256,
            np.zeros(n_events, dtype=int),
            np.tile(list(event_id.values()), n_events // len(event_id)),
        ]
    )
    epochs = mne.EpochsArray(data, info, events=events, event_id=event_id)
    return Raw("test.gdf", epochs)


def _make_raw_raw():
    """Create a raw (non-epoched) Raw."""
    info = mne.create_info(["Cz"], sfreq=256, ch_types="eeg")
    raw_mne = mne.io.RawArray(np.random.randn(1, 256), info)
    return Raw("test.gdf", raw_mne)


# ---------------------------------------------------------------------------
# EditEventName
# ---------------------------------------------------------------------------
class TestEditEventName:
    def test_check_data_rejects_raw(self):
        raw = _make_raw_raw()
        with pytest.raises(ValueError, match="epoched"):
            EditEventName([raw])  # check_data called in __init__

    def test_check_data_accepts_epochs(self):
        epoch_raw = _make_epoch_raw()
        pp = EditEventName([epoch_raw])
        pp.check_data()  # should not raise

    def test_get_preprocess_desc(self):
        epoch_raw = _make_epoch_raw()
        pp = EditEventName([epoch_raw])
        desc = pp.get_preprocess_desc({"left": "LEFT", "right": "right"})
        assert "1" in desc  # 1 name changed

    def test_rename_events(self):
        epoch_raw = _make_epoch_raw()
        pp = EditEventName([epoch_raw])
        pp.data_preprocess(new_event_name={"left": "LEFT", "right": "RIGHT"})
        _, event_id = pp.get_preprocessed_data_list()[0].get_event_list()
        assert "LEFT" in event_id
        assert "RIGHT" in event_id
        assert "left" not in event_id

    def test_no_change_raises(self):
        epoch_raw = _make_epoch_raw()
        pp = EditEventName([epoch_raw])
        with pytest.raises(ValueError, match="No Event name updated"):
            pp.data_preprocess(new_event_name={"left": "left", "right": "right"})

    def test_unknown_event_raises(self):
        epoch_raw = _make_epoch_raw()
        pp = EditEventName([epoch_raw])
        with pytest.raises(ValueError, match="not found"):
            pp.data_preprocess(new_event_name={"nonexistent": "foo"})

    def test_duplicate_new_name_raises(self):
        epoch_raw = _make_epoch_raw()
        pp = EditEventName([epoch_raw])
        with pytest.raises(ValueError, match="Duplicate"):
            pp.data_preprocess(new_event_name={"left": "same", "right": "same"})


# ---------------------------------------------------------------------------
# EditEventId
# ---------------------------------------------------------------------------
class TestEditEventId:
    def test_check_data_rejects_raw(self):
        raw = _make_raw_raw()
        with pytest.raises(ValueError, match="epoched"):
            EditEventId([raw])  # check_data called in __init__

    def test_check_data_accepts_epochs(self):
        epoch_raw = _make_epoch_raw()
        pp = EditEventId([epoch_raw])
        pp.check_data()  # should not raise

    def test_get_preprocess_desc(self):
        epoch_raw = _make_epoch_raw()
        pp = EditEventId([epoch_raw])
        desc = pp.get_preprocess_desc({"left": 10, "right": 20})
        assert "event" in desc.lower()

    def test_change_event_ids(self):
        epoch_raw = _make_epoch_raw()
        pp = EditEventId([epoch_raw])
        pp.data_preprocess(new_event_ids={"left": 10, "right": 20})
        _, event_id = pp.get_preprocessed_data_list()[0].get_event_list()
        assert 10 in event_id.values()
        assert 20 in event_id.values()

    def test_no_change_raises(self):
        epoch_raw = _make_epoch_raw()
        pp = EditEventId([epoch_raw])
        with pytest.raises(ValueError, match="No Event Id updated"):
            pp.data_preprocess(new_event_ids={"left": 1, "right": 2})

    def test_duplicate_ids_merges(self, caplog):
        epoch_raw = _make_epoch_raw()
        pp = EditEventId([epoch_raw])
        with caplog.at_level(logging.WARNING):
            pp.data_preprocess(new_event_ids={"left": 99, "right": 99})
        _, event_id = pp.get_preprocessed_data_list()[0].get_event_list()
        # Should merge names
        assert 99 in event_id.values()
        log_text = caplog.text.lower()
        assert "duplicate" in log_text or "merged" in log_text
