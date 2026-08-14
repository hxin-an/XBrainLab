"""Independent semantic gate for external timestamp/event application."""

from __future__ import annotations

from datetime import UTC, datetime

import mne
import numpy as np
import pytest

from XBrainLab.backend.event_semantics import mark_gdf_rejected_trials
from XBrainLab.backend.load_data import EventLoader, Raw


def _raw(
    *,
    duration: float = 5.0,
    first_samp: int = 0,
    meas_date: bool = False,
) -> mne.io.RawArray:
    info = mne.create_info(["Cz", "Pz"], 100.0, ch_types="eeg")
    if meas_date:
        info.set_meas_date(datetime(2024, 1, 2, tzinfo=UTC))
    return mne.io.RawArray(
        np.zeros((2, round(duration * 100))),
        info,
        first_samp=first_samp,
        verbose=False,
    )


def _annotation_rows(
    annotations: mne.Annotations,
) -> list[tuple[float, float, str, tuple[str, ...]]]:
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


def _row_for(
    annotations: mne.Annotations,
    description: str,
) -> tuple[float, float, str, tuple[str, ...]]:
    return next(row for row in _annotation_rows(annotations) if row[2] == description)


def test_timestamp_semantics_preserve_time_origin_duration_channels_and_roles() -> None:
    raw_mne = _raw(first_samp=500, meas_date=True)
    raw_mne.set_annotations(
        mne.Annotations(
            [0.2],
            [0.1],
            ["acquisition/start"],
            ch_names=[("Pz",)],
        )
    )
    acquisition_rows = _annotation_rows(raw_mne.annotations)
    acquisition_orig_time = raw_mne.annotations.orig_time
    wrapped = Raw("semantic.fif", raw_mne)
    loader = EventLoader(wrapped)
    loader.label_list = [
        {
            "onset": 0.5,
            "duration": 0.2,
            "label": "left",
            "role": "stimulus",
            "use_as_class": True,
            "ch_names": ["Cz"],
        },
        {
            "onset": 0.5,
            "duration": 0.2,
            "label": "left",
            "role": "stimulus",
            "use_as_class": True,
            "ch_names": ["Cz"],
        },
        {
            "onset": 1.0,
            "duration": 0.25,
            "label": "ocular",
            "role": "artifact",
            "use_as_class": False,
            "ch_names": ["Cz"],
        },
        {
            "onset": 2.0,
            "duration": 0.1,
            "label": "run-break",
            "role": "boundary",
            "use_as_class": False,
        },
        {
            "onset": 2.5,
            "duration": 0.0,
            "label": "amplifier-ready",
            "role": "system",
            "use_as_class": False,
        },
        {
            "onset": 3.0,
            "duration": 0.0,
            "label": "button-1",
            "role": "response",
            "use_as_class": False,
        },
    ]

    events, event_id = loader.create_event({"left": "Left hand"})
    assert _annotation_rows(raw_mne.annotations) == acquisition_rows
    loader.apply()

    assert events is not None
    assert events.tolist() == [[550, 0, 1]]
    assert event_id == {"Left hand": 1}
    assert wrapped.raw_events is not None
    np.testing.assert_array_equal(wrapped.raw_events, events)
    assert wrapped.raw_event_id == event_id
    assert raw_mne.annotations.orig_time == acquisition_orig_time
    merged_rows = _annotation_rows(raw_mne.annotations)
    assert all(row in merged_rows for row in acquisition_rows)
    assert [row[2] for row in merged_rows].count("Left hand") == 1
    artifact = _row_for(raw_mne.annotations, "BAD_artifact/ocular")
    assert artifact[0] == pytest.approx(raw_mne.first_time + 1.0)
    assert artifact[1] == pytest.approx(0.25)
    assert artifact[3] == ("Cz",)
    assert _row_for(raw_mne.annotations, "BAD_boundary/run-break")[1] == 0.1
    assert _row_for(raw_mne.annotations, "system/amplifier-ready")[1] == 0.0
    assert _row_for(raw_mne.annotations, "response/button-1")[1] == 0.0


def test_same_sample_class_ambiguity_is_rejected_without_state_mutation() -> None:
    raw_mne = _raw(first_samp=500)
    raw_mne.set_annotations(mne.Annotations([0.2], [0.0], ["acquisition"]))
    before = _annotation_rows(raw_mne.annotations)
    wrapped = Raw("ambiguous.fif", raw_mne)
    wrapped.set_event(np.array([[520, 0, 7]]), {"original": 7})
    loader = EventLoader(wrapped)
    loader.label_list = [
        {"onset": 0.1001, "duration": 0.0, "label": "left"},
        {"onset": 0.1002, "duration": 0.0, "label": "right"},
    ]

    with pytest.raises(ValueError, match="Ambiguous class placement"):
        loader.create_event({"left": "Left", "right": "Right"})

    assert _annotation_rows(raw_mne.annotations) == before
    events, event_id = wrapped.get_event_list()
    np.testing.assert_array_equal(events, np.array([[520, 0, 7]]))
    assert event_id == {"original": 7}


def test_timestamp_sample_conversion_is_batched_without_changing_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_mne = _raw(first_samp=500)
    wrapped = Raw("batched-timestamps.fif", raw_mne)
    loader = EventLoader(wrapped)
    loader.label_list = [
        {
            "onset": 0.1001,
            "duration": 0.2,
            "label": "left",
            "ch_names": ["Cz"],
        },
        {
            "onset": 0.2049,
            "duration": 0.0,
            "label": "right",
        },
        {
            "onset": 0.2049,
            "duration": 0.0,
            "label": "right",
        },
        {
            "onset": 0.3,
            "duration": 0.1,
            "label": "ocular",
            "role": "artifact",
            "use_as_class": False,
        },
    ]
    original_time_as_index = raw_mne.time_as_index
    converted_onsets: list[tuple[float, ...]] = []

    def tracked_time_as_index(
        times: list[float] | np.ndarray,
        *,
        use_rounding: bool = False,
        origin: datetime | None = None,
    ) -> np.ndarray:
        converted_onsets.append(tuple(float(value) for value in times))
        return original_time_as_index(
            times,
            use_rounding=use_rounding,
            origin=origin,
        )

    monkeypatch.setattr(raw_mne, "time_as_index", tracked_time_as_index)

    events, event_id = loader.create_event({"left": "Left", "right": "Right"})
    loader.apply()

    assert converted_onsets == [(0.1001, 0.2049), (0.1001, 0.2049)]
    assert events is not None
    assert events.tolist() == [[510, 0, 1], [520, 0, 2]]
    assert event_id == {"Left": 1, "Right": 2}
    left_row = _row_for(raw_mne.annotations, "Left")
    assert left_row[0] == pytest.approx(raw_mne.first_time + 0.1001, abs=1e-6)
    assert left_row[1:] == (0.2, "Left", ("Cz",))
    assert raw_mne.annotations.description.tolist().count("Right") == 1
    assert "BAD_artifact/ocular" in raw_mne.annotations.description


def test_distinct_reviewed_rows_normalized_to_same_annotation_are_not_deleted() -> None:
    raw_mne = _raw()
    wrapped = Raw("distinct-system-rows.fif", raw_mne)
    loader = EventLoader(wrapped)
    loader.label_list = [
        {
            "onset": 1.0,
            "duration": 0.0,
            "label": "system-code-11",
            "description": "sync",
            "role": "system",
            "use_as_class": False,
        },
        {
            "onset": 1.0,
            "duration": 0.0,
            "label": "system-code-12",
            "description": "sync",
            "role": "system",
            "use_as_class": False,
        },
    ]

    try:
        events, event_id = loader.create_event({})
    except ValueError:
        # An explicit collision rejection is also scientifically safe.
        assert len(raw_mne.annotations) == 0
        return
    loader.apply()

    assert events is not None
    assert events.shape == (0, 3)
    assert event_id == {}
    assert raw_mne.annotations.description.tolist().count("system/sync") == 2


def test_apply_merges_annotations_added_after_create_event() -> None:
    raw_mne = _raw(first_samp=200)
    raw_mne.set_annotations(
        mne.Annotations([0.25], [0.1], ["acquisition"], ch_names=[("Cz",)])
    )
    wrapped = Raw("concurrent.fif", raw_mne)
    loader = EventLoader(wrapped)
    loader.label_list = [
        {"onset": 1.0, "duration": 0.2, "label": "left"},
    ]
    events, event_id = loader.create_event({"left": "Left"})

    raw_mne.set_annotations(
        mne.Annotations(
            [0.25, 1.5],
            [0.1, 0.0],
            ["acquisition", "system/late-mutation"],
            ch_names=[("Cz",), ()],
        )
    )
    loader.apply()

    assert events is not None
    assert events.tolist() == [[300, 0, 1]]
    assert event_id == {"Left": 1}
    descriptions = raw_mne.annotations.description.tolist()
    assert descriptions == ["acquisition", "Left", "system/late-mutation"]


def test_apply_rolls_back_annotations_and_event_state_after_partial_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_mne = _raw(meas_date=True)
    raw_mne.set_annotations(mne.Annotations([0.2], [0.1], ["acquisition"]))
    wrapped = Raw("rollback.fif", raw_mne)
    previous_events = np.array([[25, 0, 7]])
    previous_event_id = {"original": 7}
    wrapped.set_event(previous_events.copy(), previous_event_id.copy())
    loader = EventLoader(wrapped)
    loader.label_list = [{"onset": 1.0, "duration": 0.2, "label": "left"}]
    loader.create_event({"left": "Left"})
    raw_mne.set_annotations(
        mne.Annotations(
            [0.2, 1.5],
            [0.1, 0.0],
            ["acquisition", "system/concurrent"],
        )
    )
    annotations_before_apply = _annotation_rows(raw_mne.annotations)
    orig_time_before_apply = raw_mne.annotations.orig_time

    def _partially_mutate_then_fail(
        events: np.ndarray,
        event_id: dict[str, int],
    ) -> None:
        wrapped.raw_events = events.copy()
        wrapped.raw_event_id = event_id.copy()
        raise RuntimeError("injected event commit failure")

    monkeypatch.setattr(wrapped, "set_event", _partially_mutate_then_fail)

    with pytest.raises(RuntimeError, match="injected event commit failure"):
        loader.apply()

    assert _annotation_rows(raw_mne.annotations) == annotations_before_apply
    assert raw_mne.annotations.orig_time == orig_time_before_apply
    assert wrapped.raw_events is not None
    np.testing.assert_array_equal(wrapped.raw_events, previous_events)
    assert wrapped.raw_event_id == previous_event_id


def test_gdf_rejected_normalization_preserves_nonzero_first_sample_onset() -> None:
    raw_mne = _raw(first_samp=500)
    raw_mne.set_annotations(
        mne.Annotations(
            [1.0],
            [0.2],
            ["Stimulus/S 1023"],
            ch_names=[("Cz",)],
        )
    )
    before = _annotation_rows(raw_mne.annotations)
    wrapped = Raw("nonzero-first-sample.gdf", raw_mne)

    changed = mark_gdf_rejected_trials(wrapped)

    assert changed is True
    assert len(raw_mne.annotations) == 1
    assert _annotation_rows(raw_mne.annotations) == [
        (before[0][0], before[0][1], "BAD_rejected_trial", before[0][3])
    ]
