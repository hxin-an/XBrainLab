from types import SimpleNamespace

import numpy as np
import pytest

from XBrainLab.backend.application.epoch_context import (
    EpochContextAvailabilityCode,
    EpochWindowMode,
    build_epoching_context,
    validated_epoch_context_availability,
    validated_epoch_window_mode,
)


class _Data:
    def __init__(self, events, event_id, hint=None, *, sfreq=None):
        self._events = events
        self._event_id = event_id
        self._hint = dict(hint) if isinstance(hint, dict) else hint
        if (
            isinstance(self._hint, dict)
            and "bids" in str(self._hint.get("source") or "").casefold()
        ):
            self._hint.setdefault("time_field", "onset")
            if "duration_stats" in self._hint:
                self._hint.setdefault("duration_field", "duration")
                stats = self._hint.get("duration_stats")
                if isinstance(stats, dict):
                    numeric_count = stats.get("numeric_count")
                    if isinstance(numeric_count, int) and numeric_count > 0:
                        self._hint.setdefault("placement_event_count", numeric_count)
                        self._hint.setdefault("unknown_duration_count", 0)
        self._sfreq = sfreq

    def get_event_list(self):
        return self._events, self._event_id

    def get_runtime_detail(self, name):
        if name == "data_interpretation_epoch_hint":
            return self._hint
        return None

    def get_filename(self):
        return "A01T.gdf"

    def get_sfreq(self):
        if self._sfreq is None:
            raise RuntimeError("sampling frequency unavailable")
        return self._sfreq


def _ready_handoff(
    *,
    label_source: str,
    placement_modes: list[str],
) -> dict[str, object]:
    return {
        "ready": True,
        "supervised_ready": True,
        "label_source": label_source,
        "placement_modes": placement_modes,
        "default_epoch_events": ["left"],
        "selected_event_names": ["left"],
    }


def _build_ready_context(data_list: list[_Data]) -> dict[str, object]:
    """Build the same admitted context the product receives after import."""
    hint = data_list[0]._hint or {}
    placement = str(hint.get("placement_method") or "internal_events")
    source = str(hint.get("source") or "").casefold()
    if "bids" in source:
        label_source = "bids_events"
    elif placement == "internal_events":
        label_source = "internal_events"
    else:
        label_source = "loaded_label_files"
    return build_epoching_context(
        data_list,
        epoch_handoff=_ready_handoff(
            label_source=label_source,
            placement_modes=[placement],
        ),
    )


@pytest.mark.parametrize(
    ("raw_mode", "expected"),
    [
        ("event_locked", EpochWindowMode.EVENT_LOCKED),
        ("duration", EpochWindowMode.DURATION),
    ],
)
def test_validated_epoch_window_mode_returns_typed_contract_value(
    raw_mode,
    expected,
):
    assert validated_epoch_window_mode(raw_mode) is expected


@pytest.mark.parametrize(
    "raw_mode",
    [None, "", " event_locked ", "fixed_duration", "EVENT_LOCKED", 1],
)
def test_validated_epoch_window_mode_rejects_unknown_or_coerced_values(raw_mode):
    with pytest.raises(ValueError, match="window_mode"):
        validated_epoch_window_mode(raw_mode)


@pytest.mark.parametrize(
    ("data", "expected_code"),
    [
        (
            _Data(np.array([[0, 0, 1]]), {"left": 1}, None),
            EpochContextAvailabilityCode.HINT_MISSING,
        ),
        (
            SimpleNamespace(
                get_event_list=lambda: (np.array([[0, 0, 1]]), {"left": 1}),
                get_runtime_detail=lambda _name: (_ for _ in ()).throw(
                    RuntimeError("runtime hint read failed")
                ),
                get_sfreq=lambda: 250.0,
            ),
            EpochContextAvailabilityCode.HINT_READ_FAILED,
        ),
    ],
    ids=["missing", "read-failed"],
)
def test_epoch_context_fails_closed_when_runtime_hint_is_unavailable(
    data,
    expected_code,
):
    context = build_epoching_context(
        [data],
        epoch_handoff=_ready_handoff(
            label_source="internal_events",
            placement_modes=["internal_events"],
        ),
    )

    availability = validated_epoch_context_availability(context)

    assert availability.available is False
    assert availability.code is expected_code
    assert availability.window_mode is None
    assert "needs review" in availability.reason


@pytest.mark.parametrize(
    ("handoff", "expected_code"),
    [
        (
            _ready_handoff(
                label_source="loaded_label_files",
                placement_modes=["interval"],
            ),
            EpochContextAvailabilityCode.HANDOFF_SOURCE_MISMATCH,
        ),
        (
            _ready_handoff(
                label_source="bids_events",
                placement_modes=["time_field"],
            ),
            EpochContextAvailabilityCode.HANDOFF_PLACEMENT_MISMATCH,
        ),
    ],
)
def test_epoch_context_rejects_handoff_hint_semantic_mismatch(
    handoff,
    expected_code,
):
    data = _Data(
        np.array([[0, 0, 1]]),
        {"left": 1},
        {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "duration_field": "duration",
            "duration_stats": {"numeric_count": 1, "min": 0.5, "max": 0.5},
            "class_map": {"left": "left"},
        },
        sfreq=250.0,
    )

    availability = validated_epoch_context_availability(
        build_epoching_context([data], epoch_handoff=handoff)
    )

    assert availability.available is False
    assert availability.code is expected_code
    assert availability.window_mode is None


def test_epoch_context_rejects_ready_handoff_with_blockers():
    data = _Data(
        np.array([[0, 0, 1]]),
        {"left": 1},
        {
            "source": "Labels inside EEG files",
            "placement_method": "internal_events",
            "class_map": {"left": "left"},
        },
        sfreq=250.0,
    )
    handoff = _ready_handoff(
        label_source="internal_events",
        placement_modes=["internal_events"],
    )
    handoff["supervised_blockers"] = ["Event role mapping is incomplete."]

    availability = validated_epoch_context_availability(
        build_epoching_context([data], epoch_handoff=handoff)
    )

    assert availability.available is False
    assert availability.code is EpochContextAvailabilityCode.HANDOFF_UNAVAILABLE
    assert availability.reason == "Event role mapping is incomplete."


def test_epoch_context_rejects_multi_run_with_partial_bids_semantics():
    complete = _Data(
        np.array([[0, 0, 1]]),
        {"left": 1},
        {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "time_field": "onset",
            "duration_field": "duration",
            "duration_stats": {
                "row_count": 1,
                "numeric_count": 1,
                "min": 0.5,
                "max": 0.5,
            },
            "placement_event_count": 1,
            "unknown_duration_count": 0,
        },
        sfreq=250.0,
    )
    missing_duration_semantics = _Data(
        np.array([[250, 0, 1]]),
        {"left": 1},
        {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "time_field": "onset",
        },
        sfreq=250.0,
    )

    availability = validated_epoch_context_availability(
        build_epoching_context(
            [complete, missing_duration_semantics],
            epoch_handoff=_ready_handoff(
                label_source="bids_events",
                placement_modes=["interval"],
            ),
        )
    )

    assert availability.available is False
    assert availability.code is EpochContextAvailabilityCode.HINT_SEMANTICS_INVALID


@pytest.mark.parametrize(
    "duration_stats",
    [
        {"numeric_count": 0, "min": None, "max": 0.5},
        {"numeric_count": 1, "min": 1.0, "max": 0.5},
        {"numeric_count": 1, "min": None, "max": 0.5},
    ],
)
def test_epoch_context_rejects_inconsistent_bids_duration_evidence(duration_stats):
    data = _Data(
        np.array([[0, 0, 1]]),
        {"left": 1},
        {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "time_field": "onset",
            "duration_field": "duration",
            "duration_stats": duration_stats,
            "placement_event_count": 1,
            "unknown_duration_count": 0,
        },
        sfreq=250.0,
    )

    availability = validated_epoch_context_availability(
        build_epoching_context(
            [data],
            epoch_handoff=_ready_handoff(
                label_source="bids_events",
                placement_modes=["interval"],
            ),
        )
    )

    assert availability.available is False
    assert availability.code is EpochContextAvailabilityCode.DURATION_UNAVAILABLE


def test_non_bids_interval_without_positive_duration_is_unavailable():
    data = _Data(
        np.array([[0, 0, 1]]),
        {"left": 1},
        {
            "source": "Loaded label file",
            "placement_method": "interval",
            "duration_field": "duration",
            "duration_stats": {"numeric_count": 0, "min": None, "max": None},
            "class_map": {"left": "left"},
        },
        sfreq=250.0,
    )

    context = build_epoching_context(
        [data],
        epoch_handoff=_ready_handoff(
            label_source="loaded_label_files",
            placement_modes=["interval"],
        ),
    )
    availability = validated_epoch_context_availability(context)

    assert availability.available is False
    assert availability.code is EpochContextAvailabilityCode.DURATION_UNAVAILABLE
    assert availability.window_mode is None


def test_bids_event_locked_explanation_uses_reviewed_anchor_not_fixed_cause():
    data = _Data(
        np.array([[0, 0, 1]]),
        {"left": 1},
        {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "duration_field": "duration",
            "duration_stats": {"numeric_count": 0, "min": None, "max": None},
            "placement_event_count": 1,
            "unknown_duration_count": 1,
            "class_map": {"left": "left"},
        },
        sfreq=250.0,
    )

    availability = validated_epoch_context_availability(
        build_epoching_context(
            [data],
            epoch_handoff=_ready_handoff(
                label_source="bids_events",
                placement_modes=["interval"],
            ),
        )
    )

    assert availability.available is True
    assert availability.window_mode is EpochWindowMode.EVENT_LOCKED
    assert "reviewed BIDS event onset" in availability.window_explanation
    assert "missing" not in availability.window_explanation.casefold()
    assert "not usable" not in availability.window_explanation.casefold()


@pytest.mark.parametrize(
    ("sfreq", "duration", "expected_tmax"),
    [
        (100.0, 0.5, 0.49),
        (128.0, 0.5, 63 / 128),
        (250.0, 0.5, 124 / 250),
        (256.0, 1.25, 319 / 256),
        (100.0, 0.494, 0.49),
        (100.0, 0.501, 0.5),
    ],
)
def test_bids_interval_window_ends_at_last_sample_inside_half_open_duration(
    sfreq,
    duration,
    expected_tmax,
):
    data = _Data(
        np.array([[0, 0, 1]], dtype=np.int32),
        {"left": 1},
        {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "duration_field": "duration",
            "duration_stats": {
                "numeric_count": 1,
                "min": duration,
                "max": duration,
            },
        },
        sfreq=sfreq,
    )

    context = _build_ready_context([data])

    assert context["suggested_t_max"] == pytest.approx(expected_tmax)


def test_bids_explicit_zero_duration_keeps_event_locked_default():
    duration_stats = {"numeric_count": 1, "min": 0.0, "max": 0.0}
    data = _Data(
        np.array([[0, 0, 1]], dtype=np.int32),
        {"left": 1},
        {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "duration_field": "duration",
            "duration_stats": duration_stats,
        },
        sfreq=250.0,
    )

    context = _build_ready_context([data])

    assert context["suggested_t_min"] == -0.2
    assert context["suggested_t_max"] == 1.0
    assert context["window_mode"] is EpochWindowMode.EVENT_LOCKED


def test_bids_reviewed_unknown_duration_uses_event_locked_policy():
    data = _Data(
        np.array([[0, 0, 1]], dtype=np.int32),
        {"left": 1},
        {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "time_field": "onset",
            "duration_field": "duration",
            "duration_stats": {},
            "placement_event_count": 1,
            "unknown_duration_count": 1,
        },
        sfreq=250.0,
    )

    context = _build_ready_context([data])

    assert context["window_mode"] is EpochWindowMode.EVENT_LOCKED
    assert "unknown" in context["window_evidence"].casefold()


def test_bids_missing_duration_evidence_is_unavailable():
    data = _Data(
        np.array([[0, 0, 1]], dtype=np.int32),
        {"left": 1},
        {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "time_field": "onset",
            "duration_field": "duration",
            "duration_stats": {},
        },
        sfreq=250.0,
    )

    availability = validated_epoch_context_availability(_build_ready_context([data]))

    assert availability.available is False
    assert availability.code is EpochContextAvailabilityCode.DURATION_UNAVAILABLE


def test_non_bids_interval_keeps_existing_duration_window_semantics():
    data = _Data(
        np.array([[0, 0, 1]], dtype=np.int32),
        {"left": 1},
        {
            "source": "Loaded label file",
            "placement_method": "interval",
            "duration_field": "duration",
            "duration_stats": {"numeric_count": 1, "min": 0.5, "max": 0.5},
        },
        sfreq=250.0,
    )

    context = _build_ready_context([data])

    assert context["suggested_t_max"] == 0.5


def test_epoching_context_uses_interval_duration_for_default_window():
    data = _Data(
        np.array([[0, 0, 1], [250, 0, 2], [500, 0, 1]], dtype=np.int32),
        {"Left hand": 1, "Right hand": 2},
        {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "label_field": "trial_type",
            "time_field": "onset",
            "duration_field": "duration",
            "duration_stats": {"numeric_count": 3, "min": 0.5, "max": 1.25},
            "class_map": {"left": "Left hand", "right": "Right hand"},
        },
    )

    context = _build_ready_context([data])

    assert context["source"] == "BIDS events.tsv"
    assert context["placement_label"] == "Label interval"
    assert context["recommended_events"] == ["Left hand", "Right hand"]
    assert context["suggested_t_min"] == 0.0
    assert context["suggested_t_max"] == 1.25
    assert context["suggested_baseline"] is None
    assert context["window_evidence"] == "Suggested from imported duration field."
    assert context["window_mode"] is EpochWindowMode.DURATION


def test_bids_epoching_context_missing_duration_uses_event_locked_default():
    data = _Data(
        np.array([[0, 0, 1], [250, 0, 2]], dtype=np.int32),
        {"left": 1, "right": 2},
        {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "label_field": "trial_type",
            "time_field": "onset",
            "duration_field": "duration",
            "duration_stats": {"numeric_count": 0, "min": None, "max": None},
            "placement_event_count": 2,
            "unknown_duration_count": 2,
            "class_map": {"left": "left", "right": "right"},
        },
    )

    context = _build_ready_context([data])

    assert context["suggested_t_min"] == -0.2
    assert context["suggested_t_max"] == 1.0
    assert context["suggested_baseline"] == (-0.2, 0.0)
    assert context["window_mode"] == "event_locked"
    assert "durations are unknown" in context["window_evidence"]


def test_bids_epoching_context_flags_long_or_uneven_durations():
    data = _Data(
        np.array([[0, 0, 1], [250, 0, 2]], dtype=np.int32),
        {"left": 1, "right": 2},
        {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "label_field": "trial_type",
            "time_field": "onset",
            "duration_field": "duration",
            "duration_stats": {"numeric_count": 3, "min": 0.25, "max": 12.0},
            "class_map": {"left": "left", "right": "right"},
        },
    )

    context = _build_ready_context([data])

    assert context["suggested_t_min"] == 0.0
    assert context["suggested_t_max"] == 12.0
    assert context["window_mode"] == "duration"
    assert "review the EEG epoch window" in context["window_warning"]
    requirement = context["confirmation_requirement"]
    assert requirement["code"] == "bids_duration_review"
    assert requirement["message"] in context["window_warning"]
    assert requirement["scope"] == {
        "t_min": 0.0,
        "t_max": 12.0,
        "selected_events": ["left", "right"],
    }
    assert requirement["receipt"]


@pytest.mark.parametrize(
    "duration_stats",
    [
        {"numeric_count": 2, "min": 11.0, "max": 12.0},
        {"numeric_count": 2, "min": 0.25, "max": 1.0},
    ],
)
def test_bids_long_and_uneven_duration_policies_each_require_confirmation(
    duration_stats,
):
    data = _Data(
        np.array([[0, 0, 1], [250, 0, 2]], dtype=np.int32),
        {"left": 1, "right": 2},
        {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "duration_field": "duration",
            "duration_stats": duration_stats,
            "class_map": {"left": "left", "right": "right"},
        },
        sfreq=100.0,
    )

    context = _build_ready_context([data])

    assert context["confirmation_requirement"] is not None


def test_ordinary_epoch_context_does_not_issue_confirmation_requirement():
    data = _Data(
        np.array([[0, 0, 1]], dtype=np.int32),
        {"left": 1},
        {
            "source": "Loaded label file",
            "placement_method": "interval",
            "duration_field": "duration",
            "duration_stats": {"numeric_count": 1, "min": 12.0, "max": 12.0},
        },
        sfreq=100.0,
    )

    context = _build_ready_context([data])

    assert context["confirmation_requirement"] is None


def test_bids_multi_run_epoch_hint_uses_all_runs_independent_of_file_order():
    run_one = _Data(
        np.array([[0, 0, 1]], dtype=np.int32),
        {"Left hand": 1},
        {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "label_field": "trial_type",
            "time_field": "onset",
            "duration_field": "duration",
            "duration_stats": {"numeric_count": 1, "min": 0.5, "max": 0.5},
            "class_map": {"left": "Left hand"},
        },
    )
    run_two = _Data(
        np.array([[0, 0, 2]], dtype=np.int32),
        {"Right hand": 2},
        {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "label_field": "trial_type",
            "time_field": "onset",
            "duration_field": "duration",
            "duration_stats": {"numeric_count": 1, "min": 3.0, "max": 3.0},
            "class_map": {"right": "Right hand"},
        },
    )

    forward = _build_ready_context([run_one, run_two])
    reversed_order = _build_ready_context([run_two, run_one])

    assert forward == reversed_order
    assert forward["recommended_events"] == ["Left hand", "Right hand"]
    assert forward["suggested_t_min"] == 0.0
    assert forward["suggested_t_max"] == 3.0
    assert "all 2 selected runs" in forward["window_evidence"]
    assert "longest observed duration" in forward["window_warning"]


def test_bids_mixed_sampling_rates_require_resampling_before_epoching():
    hint = {
        "source": "BIDS events.tsv",
        "placement_method": "interval",
        "duration_field": "duration",
        "duration_stats": {"numeric_count": 1, "min": 0.5, "max": 0.5},
    }
    run_one = _Data(
        np.array([[0, 0, 1]], dtype=np.int32),
        {"left": 1},
        hint,
        sfreq=100.0,
    )
    run_two = _Data(
        np.array([[0, 0, 1]], dtype=np.int32),
        {"left": 1},
        hint,
        sfreq=256.0,
    )

    context = _build_ready_context([run_one, run_two])

    assert context["suggested_t_max"] == 0.5
    assert context["suggested_t_max_decimals"] == 2
    assert context["requires_common_sampling_frequency"] is True
    assert "Resample them to one shared rate" in context["window_warning"]
    availability = context["context_availability"]
    assert availability["available"] is False
    assert availability["code"] == "sampling_frequency_mismatch"
    assert "different sampling frequencies (100 Hz, 256 Hz)" in availability["reason"]
    assert context["recommended_events"] == []


@pytest.mark.parametrize(
    ("duration_stats", "placement_count", "unknown_count"),
    [
        ({"numeric_count": 1, "min": 0.0, "max": 0.0}, 1, 0),
        ({"numeric_count": 0, "min": None, "max": None}, 1, 1),
        ({}, 1, 1),
    ],
)
def test_bids_mixed_sampling_rates_warn_when_duration_is_not_positive(
    duration_stats,
    placement_count,
    unknown_count,
):
    hint = {
        "source": "BIDS events.tsv",
        "placement_method": "interval",
        "duration_field": "duration",
        "duration_stats": duration_stats,
        "placement_event_count": placement_count,
        "unknown_duration_count": unknown_count,
    }
    run_one = _Data(
        np.array([[0, 0, 1]], dtype=np.int32),
        {"left": 1},
        hint,
        sfreq=100.0,
    )
    run_two = _Data(
        np.array([[0, 0, 1]], dtype=np.int32),
        {"left": 1},
        hint,
        sfreq=256.0,
    )

    context = _build_ready_context([run_one, run_two])

    assert context["window_mode"] == "event_locked"
    assert context["requires_common_sampling_frequency"] is True
    assert "Resample them to one shared rate" in context["window_warning"]
    assert context["context_availability"]["available"] is False
    assert context["context_availability"]["code"] == ("sampling_frequency_mismatch")


def test_epoching_context_maps_internal_class_codes_to_event_names():
    data = _Data(
        np.array([[0, 0, 769], [250, 0, 770], [500, 0, 768]], dtype=np.int32),
        {"769": 769, "770": 770, "768": 768},
        {
            "source": "Labels inside EEG files",
            "placement_method": "internal_events",
            "class_map": {"769": "Left hand", "770": "Right hand"},
        },
    )

    context = _build_ready_context([data])

    assert context["placement_label"] == "Events inside EEG files"
    assert context["recommended_events"] == ["769", "770"]
    assert context["suggested_t_min"] == -0.2
    assert context["suggested_t_max"] == 1.0
    assert context["suggested_baseline"] == (-0.2, 0.0)


def test_epoching_context_tolerates_mock_like_event_objects():
    data = SimpleNamespace(
        get_event_list=lambda: (None, {"left": 1}),
        get_runtime_detail=lambda _name: None,
        get_filename=lambda: "mock.fif",
    )

    context = build_epoching_context([data])

    assert context["source"] == "Manual EEG epoch setup"
    assert context["available_events"] == [{"name": "left", "count": None}]
