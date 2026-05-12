import numpy as np
import pytest

from XBrainLab.backend.load_data import EventLoader

from .test_raw import (
    _set_event,
    epoch,  # noqa: F401
    mne_epoch,  # noqa: F401
    mne_raw,  # noqa: F401
    raw,  # noqa: F401
)


def test_event_loader_init(raw):  # noqa: F811
    _set_event(raw)
    event_loader = EventLoader(raw)

    with pytest.raises(ValueError, match=r"No label has been loaded."):
        event_loader.create_event({})

    with pytest.raises(ValueError, match=r"No label/events generated to apply."):
        event_loader.apply()


def test_create_event_from_1d_list(raw):  # noqa: F811
    event_loader = EventLoader(raw)
    # Simulate labels loaded from label_loader (1D list/array)
    event_loader.label_list = [1, 2, 3, 4]

    # Mock existing events to allow sync (needed for create_event to proceed
    # to name check)
    raw.set_event(np.zeros((4, 3), dtype=int), {str(i): i for i in range(4)})

    with pytest.raises(ValueError, match=r"Event name cannot be empty."):
        event_loader.create_event({1: ""})

    # Map 1->new 1, 2->new 2, etc.
    mapping = {1: "new 1", 2: "new 2", 3: "new 3", 4: "new 4"}

    # Mock existing events to allow sync
    raw.set_event(np.zeros((4, 3), dtype=int), {str(i): i for i in range(4)})

    event_loader.create_event(mapping)
    event_loader.apply()

    events, event_id = raw.get_event_list()
    assert len(events) == 4
    assert len(event_id) == 4
    for i in range(4):
        assert event_id["new " + str(i + 1)] == i + 1
        assert events[i, -1] == i + 1
        # Timestamps might be 0, 1, 2, 3 if raw has no previous events or sync fails
        # In this mock raw, it might differ, but we check existence.


def test_create_event_from_nx3_array(raw):  # noqa: F811
    event_loader = EventLoader(raw)
    # Simulate labels loaded from label_loader (Nx3 array, e.g. from GDF events)
    # Timestamps: 10, 20, 30, 40
    # Values: 0, 0, 0, 0
    # IDs: 1, 2, 3, 4
    event_loader.label_list = np.array([[10, 0, 1], [20, 0, 2], [30, 0, 3], [40, 0, 4]])

    mapping = {1: "new 1", 2: "new 2", 3: "new 3", 4: "new 4"}
    event_loader.create_event(mapping)
    event_loader.apply()

    events, _event_id = raw.get_event_list()
    assert len(events) == 4
    assert events[0, 0] == 10  # Should preserve timestamps
    assert events[0, -1] == 1


def test_create_event_inconsistent(epoch):  # noqa: F811
    event_loader = EventLoader(epoch)
    event_loader.label_list = [1]

    events, event_id = event_loader.create_event({1: "new 1"})

    assert events is not None
    assert event_id == {"new 1": 1}
    assert len(events) == 1
