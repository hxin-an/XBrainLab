from datetime import UTC, datetime

import mne
import numpy as np
import pytest

from XBrainLab.backend.event_semantics import mark_gdf_rejected_trials
from XBrainLab.backend.load_data import EventLoader, Raw


def _generate_mne_raw(fs=100, duration=1, *, first_samp=0):
    info = mne.create_info(ch_names=["O1", "O2"], sfreq=fs, ch_types="eeg")
    data = np.random.randn(2, fs * duration)
    return mne.io.RawArray(data, info, first_samp=first_samp)


def _annotation_rows(annotations):
    return [
        (
            float(onset),
            float(duration),
            str(description),
            tuple(str(name) for name in annotations.ch_names[index]),
        )
        for index, (onset, duration, description) in enumerate(
            zip(
                annotations.onset,
                annotations.duration,
                annotations.description,
                strict=True,
            )
        )
    ]


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


def test_event_loader_raw_mismatch_raises():
    """Label rows must not be silently truncated against EEG events."""
    raw_mne = _generate_mne_raw()
    raw = Raw("test.fif", raw_mne)

    # Set 2 events
    events = np.array([[10, 0, 1], [20, 0, 1]])
    event_id = {"A": 1}
    raw.set_event(events, event_id)

    loader = EventLoader(raw)
    loader.label_list = [1, 2, 3]  # 3 labels vs 2 events
    mapping = {1: "A", 2: "B", 3: "C"}

    with pytest.raises(ValueError, match="Label count does not match"):
        loader.create_event(mapping)


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


def test_timestamp_labels_accept_mne_microsecond_quantization():
    """Fractional-sample BIDS onsets survive MNE annotation quantization."""
    raw_mne = _generate_mne_raw(fs=256, duration=6)
    raw = Raw("p300.set", raw_mne)
    loader = EventLoader(raw)
    loader.label_list = [
        {"onset": 4.44921875, "duration": 0.0, "label": "standard"},
        {"onset": 5.2578125, "duration": 0.0, "label": "oddball"},
    ]

    events, event_id = loader.create_event(
        {"standard": "Standard", "oddball": "Oddball"}
    )
    loader.apply()

    assert events is not None
    assert events[:, 0].tolist() == [1139, 1346]
    assert event_id == {"Oddball": 1, "Standard": 2}
    assert raw_mne.annotations.description.tolist() == ["Standard", "Oddball"]
    np.testing.assert_allclose(
        raw_mne.annotations.onset,
        [4.44921875, 5.2578125],
        atol=1e-6,
        rtol=0.0,
    )


def test_timestamp_labels_preserve_existing_annotations_without_event_pollution():
    """External label events stay authoritative without erasing EEG context."""
    raw_mne = _generate_mne_raw(duration=5)
    raw_mne.set_annotations(
        mne.Annotations(
            onset=[0.05, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
            duration=[0.0, 0.1, 0.0, 0.0, 0.0, 0.2, 0.0],
            description=[
                "old_class",
                "BAD_rejected_trial",
                "boundary",
                "system/recording_start",
                "New Segment/",
                "artifact",
                "Stimulus/S 32766",
            ],
        )
    )
    raw = Raw("test.gdf", raw_mne)
    loader = EventLoader(raw)
    loader.label_list = [
        {"onset": 0.1, "duration": 0.2, "label": "left"},
        {"onset": 1.1, "duration": 0.2, "label": "right"},
    ]

    events, event_id = loader.create_event({"left": "Left hand", "right": "Right hand"})
    loader.apply()

    assert events is not None
    assert len(events) == 2
    assert event_id == {"Left hand": 1, "Right hand": 2}
    assert list(raw_mne.annotations.description) == [
        "old_class",
        "Left hand",
        "BAD_rejected_trial",
        "boundary",
        "Right hand",
        "system/recording_start",
        "New Segment/",
        "artifact",
        "Stimulus/S 32766",
    ]
    np.testing.assert_allclose(
        raw_mne.annotations.onset,
        [0.05, 0.1, 0.5, 1.0, 1.1, 1.5, 2.0, 2.5, 3.0],
    )
    np.testing.assert_allclose(
        raw_mne.annotations.duration,
        [0.0, 0.2, 0.1, 0.0, 0.2, 0.0, 0.0, 0.2, 0.0],
    )


def test_timestamp_annotation_merge_deduplicates_and_orders_exact_rows():
    """Exact duplicates collapse and equal-onset rows have canonical order."""
    raw_mne = _generate_mne_raw(duration=5)
    raw_mne.set_annotations(
        mne.Annotations(
            onset=[1.0, 1.0, 1.0],
            duration=[0.0, 0.0, 0.2],
            description=["boundary", "boundary", "artifact"],
        )
    )
    raw = Raw("test.fif", raw_mne)
    loader = EventLoader(raw)
    loader.label_list = [
        {"onset": 1.0, "duration": 0.0, "label": "right"},
        {"onset": 1.0, "duration": 0.0, "label": "right"},
    ]

    events, event_id = loader.create_event({"right": "Right hand"})
    loader.apply()

    assert events is not None
    assert len(events) == 1
    assert event_id == {"Right hand": 1}
    assert list(raw_mne.annotations.description) == [
        "Right hand",
        "boundary",
        "artifact",
    ]
    np.testing.assert_allclose(raw_mne.annotations.onset, [1.0, 1.0, 1.0])
    np.testing.assert_allclose(raw_mne.annotations.duration, [0.0, 0.0, 0.2])


def test_timestamp_apply_keeps_annotation_changes_made_after_create_event():
    """GDF safety normalization between create/apply must not be overwritten."""
    raw_mne = _generate_mne_raw(duration=5)
    raw_mne.set_annotations(
        mne.Annotations(
            onset=[0.5],
            duration=[0.0],
            description=["Stimulus/S 1023"],
        )
    )
    raw = Raw("test.gdf", raw_mne)
    loader = EventLoader(raw)
    loader.label_list = [
        {"onset": 1.0, "duration": 0.25, "label": "left"},
    ]

    events, event_id = loader.create_event({"left": "Left hand"})
    assert mark_gdf_rejected_trials(raw) is True
    loader.apply()

    assert events is not None
    assert event_id == {"Left hand": 1}
    assert list(raw_mne.annotations.description) == [
        "BAD_rejected_trial",
        "Left hand",
    ]
    assert "Stimulus/S 1023" not in raw_mne.annotations.description


def test_timestamp_semantic_rows_create_safety_annotations_and_class_only_events():
    """Artifact/boundary rows reject epochs without entering the class map."""
    raw_mne = _generate_mne_raw(duration=5)
    raw_mne.set_meas_date(datetime(2024, 1, 2, tzinfo=UTC))
    acquisition = mne.Annotations(
        onset=[0.2, 3.0],
        duration=[0.1, 0.0],
        description=["BAD_existing", "system/start"],
        orig_time=raw_mne.info["meas_date"],
        ch_names=[("O1",), ()],
    )
    raw_mne.set_annotations(acquisition)
    acquisition_rows = _annotation_rows(raw_mne.annotations)
    acquisition_orig_time = raw_mne.annotations.orig_time
    raw = Raw("semantic.fif", raw_mne)
    loader = EventLoader(raw)
    loader.label_list = [
        {
            "onset": 1.0,
            "duration": 0.0,
            "label": "left",
            "role": "stimulus",
            "use_as_class": True,
        },
        {
            "onset": 1.1,
            "duration": 0.2,
            "label": "ocular",
            "role": "artifact",
            "use_as_class": False,
        },
        {
            "onset": 2.0,
            "duration": 0.1,
            "label": "run_break",
            "role": "boundary",
            "use_as_class": False,
        },
        {
            "onset": 2.5,
            "duration": 0.0,
            "label": "button",
            "role": "response",
            "use_as_class": False,
        },
    ]

    events, event_id = loader.create_event({"left": "Left hand"})
    loader.apply()

    assert events is not None
    assert events[:, 0].tolist() == [100]
    assert event_id == {"Left hand": 1}
    descriptions = list(raw_mne.annotations.description)
    assert "BAD_artifact/ocular" in descriptions
    assert "BAD_boundary/run_break" in descriptions
    assert "response/button" in descriptions
    assert raw_mne.annotations.orig_time == acquisition_orig_time
    merged_rows = _annotation_rows(raw_mne.annotations)
    assert all(row in merged_rows for row in acquisition_rows)

    epochs = mne.Epochs(
        raw_mne,
        events,
        event_id=event_id,
        tmin=0.0,
        tmax=0.4,
        baseline=None,
        preload=True,
        verbose=False,
    )

    assert len(epochs) == 0
    assert "BAD_artifact/ocular" in epochs.drop_log[0]


@pytest.mark.parametrize("class_name", ["Bad trial", "BAD_left", "Edge boundary"])
def test_timestamp_class_names_excluded_by_mne_are_rejected_without_mutation(
    class_name,
):
    raw_mne = _generate_mne_raw(duration=3)
    raw_mne.set_annotations(mne.Annotations([0.25], [0.1], ["acquisition"]))
    before = _annotation_rows(raw_mne.annotations)
    raw = Raw("excluded-class.fif", raw_mne)
    raw.set_event(np.array([[50, 0, 7]]), {"original": 7})
    loader = EventLoader(raw)
    loader.label_list = [
        {
            "onset": 1.0,
            "duration": 0.1,
            "label": "left",
            "role": "stimulus",
            "use_as_class": True,
        }
    ]

    with pytest.raises(ValueError, match="MNE excludes class description"):
        loader.create_event({"left": class_name})

    assert _annotation_rows(raw_mne.annotations) == before
    events, event_id = raw.get_event_list()
    np.testing.assert_array_equal(events, np.array([[50, 0, 7]]))
    assert event_id == {"original": 7}


@pytest.mark.parametrize(
    "row",
    [
        {"onset": -0.01, "duration": 0.0, "label": "left"},
        {"onset": 3.0, "duration": 0.0, "label": "left"},
        {"onset": 2.9, "duration": 0.2, "label": "left"},
    ],
)
def test_timestamp_out_of_range_rows_are_rejected_without_partial_clipping(row):
    raw_mne = _generate_mne_raw(duration=3)
    raw_mne.set_annotations(mne.Annotations([0.25], [0.1], ["acquisition"]))
    before = _annotation_rows(raw_mne.annotations)
    raw = Raw("bounds.fif", raw_mne)
    loader = EventLoader(raw)
    loader.label_list = [
        {"onset": 1.0, "duration": 0.0, "label": "left"},
        row,
    ]

    with pytest.raises(ValueError, match="outside the stored EEG range"):
        loader.create_event({"left": "Left hand"})

    assert _annotation_rows(raw_mne.annotations) == before
    assert raw.raw_events is None
    assert raw.raw_event_id is None


def test_timestamp_exact_duplicates_dedupe_but_conflicting_class_placement_blocks():
    raw_mne = _generate_mne_raw(duration=3, first_samp=500)
    raw = Raw("dedupe.fif", raw_mne)
    loader = EventLoader(raw)
    loader.label_list = [
        {"onset": 1.0, "duration": 0.0, "label": "left"},
        {"onset": 1.0, "duration": 0.0, "label": "left"},
    ]

    events, event_id = loader.create_event({"left": "Left hand"})
    loader.apply()

    assert events is not None
    assert events[:, 0].tolist() == [600]
    assert event_id == {"Left hand": 1}
    assert list(raw_mne.annotations.description) == ["Left hand"]

    conflicting = EventLoader(raw)
    conflicting.label_list = [
        {"onset": 2.0, "duration": 0.0, "label": "left"},
        {"onset": 2.0, "duration": 0.0, "label": "right"},
    ]
    with pytest.raises(ValueError, match="Ambiguous class placement"):
        conflicting.create_event({"left": "Left hand", "right": "Right hand"})


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
