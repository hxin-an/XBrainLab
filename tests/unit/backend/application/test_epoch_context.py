from types import SimpleNamespace

import numpy as np

from XBrainLab.backend.application.epoch_context import build_epoching_context


class _Data:
    def __init__(self, events, event_id, hint=None):
        self._events = events
        self._event_id = event_id
        self._hint = hint

    def get_event_list(self):
        return self._events, self._event_id

    def get_runtime_detail(self, name):
        if name == "data_interpretation_epoch_hint":
            return self._hint
        return None

    def get_filename(self):
        return "A01T.gdf"


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
    assert context["window_evidence"] == "duration max 1.25s from duration"


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

    assert context["source"] == "Manual epoch setup"
    assert context["available_events"] == [{"name": "left", "count": None}]
