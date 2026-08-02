from types import SimpleNamespace

import numpy as np
import pytest

from XBrainLab.backend.application.epoch_context import build_epoching_context


class _Data:
    def __init__(self, events, event_id, hint=None, *, sfreq=None):
        self._events = events
        self._event_id = event_id
        self._hint = hint
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

    context = build_epoching_context([data])

    assert context["suggested_t_max"] == pytest.approx(expected_tmax)


@pytest.mark.parametrize(
    "duration_stats",
    [
        {"numeric_count": 1, "min": 0.0, "max": 0.0},
        {"numeric_count": 0, "min": None, "max": None},
        {},
    ],
)
def test_bids_zero_or_missing_duration_keeps_event_locked_default(duration_stats):
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

    context = build_epoching_context([data])

    assert context["suggested_t_min"] == -0.2
    assert context["suggested_t_max"] == 1.0
    assert context["window_mode"] == "event_locked"


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

    context = build_epoching_context([data])

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

    context = build_epoching_context([data])

    assert context["source"] == "BIDS events.tsv"
    assert context["placement_label"] == "Label interval"
    assert context["recommended_events"] == ["Left hand", "Right hand"]
    assert context["suggested_t_min"] == 0.0
    assert context["suggested_t_max"] == 1.25
    assert context["suggested_baseline"] is None
    assert context["window_evidence"] == "Suggested from imported duration field."
    assert context["window_mode"] == "duration"


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
            "class_map": {"left": "left", "right": "right"},
        },
    )

    context = build_epoching_context([data])

    assert context["suggested_t_min"] == -0.2
    assert context["suggested_t_max"] == 1.0
    assert context["suggested_baseline"] == (-0.2, 0.0)
    assert context["window_mode"] == "event_locked"
    assert "duration field has no positive values" in context["window_evidence"]


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

    context = build_epoching_context([data])

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

    context = build_epoching_context([data])

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

    context = build_epoching_context([data])

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

    forward = build_epoching_context([run_one, run_two])
    reversed_order = build_epoching_context([run_two, run_one])

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

    context = build_epoching_context([run_one, run_two])

    assert context["suggested_t_max"] == 0.5
    assert context["suggested_t_max_decimals"] == 2
    assert context["requires_common_sampling_frequency"] is True
    assert "Resample them to one shared rate" in context["window_warning"]


@pytest.mark.parametrize(
    "duration_stats",
    [
        {"numeric_count": 1, "min": 0.0, "max": 0.0},
        {"numeric_count": 0, "min": None, "max": None},
        {},
    ],
)
def test_bids_mixed_sampling_rates_warn_when_duration_is_not_positive(
    duration_stats,
):
    hint = {
        "source": "BIDS events.tsv",
        "placement_method": "interval",
        "duration_field": "duration",
        "duration_stats": duration_stats,
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

    context = build_epoching_context([run_one, run_two])

    assert context["window_mode"] == "event_locked"
    assert context["requires_common_sampling_frequency"] is True
    assert "Resample them to one shared rate" in context["window_warning"]


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

    context = build_epoching_context([data])

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
