"""Epoch handoff tests for event catalog and supervised class targets."""

from __future__ import annotations

from dataclasses import replace

from XBrainLab.backend.application.data_interpretation import AppliedInterpretation
from XBrainLab.backend.application.data_interpretation_state import (
    DataInterpretationSessionState,
)


def test_epoch_handoff_uses_only_class_targets_for_defaults() -> None:
    applied = _applied(
        [
            {
                "path": "/data/run-1_events.tsv",
                "selected_target_file": "/data/run-1_eeg.fif",
                "selected_label_field": "trial_type",
                "placement_method": "time_field",
                "value_decisions": {
                    "left": _decision("stimulus", True, "Left hand", count=2),
                    "right": _decision("stimulus", True, "Right hand", count=2),
                    "button": _decision("response", False, count=1),
                    "bad": _decision("artifact", False, keep_event=False, count=1),
                    "boundary": _decision("boundary", False, count=1),
                },
                "run_class_map": {
                    "left": "Left hand",
                    "right": "Right hand",
                },
            }
        ]
    )

    handoff = DataInterpretationSessionState._epoch_handoff(None, applied)

    assert handoff["supervised_ready"] is True
    assert handoff["default_epoch_events"] == ["Left hand", "Right hand"]
    assert len(handoff["event_catalog"]) == 5
    assert [row["raw_value"] for row in handoff["class_targets"]] == [
        "left",
        "right",
    ]
    assert handoff["class_map"] == {
        "left": "Left hand",
        "right": "Right hand",
    }
    boundary = next(
        row for row in handoff["event_catalog"] if row["raw_value"] == "boundary"
    )
    assert boundary["role"] == "boundary"
    assert boundary["use_as_class"] is False


def test_epoch_handoff_preserves_per_run_same_raw_value_semantics() -> None:
    applied = _applied(
        [
            {
                "path": "/data/run-1_events.tsv",
                "selected_target_file": "/data/run-1_eeg.fif",
                "selected_label_field": "trial_type",
                "value_decisions": {"T1": _decision("stimulus", True, "left")},
                "run_class_map": {"T1": "left"},
            },
            {
                "path": "/data/run-2_events.tsv",
                "selected_target_file": "/data/run-2_eeg.fif",
                "selected_label_field": "trial_type",
                "value_decisions": {"T1": _decision("stimulus", True, "right")},
                "run_class_map": {"T1": "right"},
            },
        ]
    )

    handoff = DataInterpretationSessionState._epoch_handoff(None, applied)

    assert handoff["class_map"] == {}
    assert handoff["run_class_maps"] == {
        "/data/run-1_eeg.fif": {"T1": "left"},
        "/data/run-2_eeg.fif": {"T1": "right"},
    }
    assert handoff["default_epoch_events"] == ["left", "right"]
    assert {row["class_name"] for row in handoff["class_targets"]} == {
        "left",
        "right",
    }


def test_zero_class_or_unresolved_values_are_not_supervised_ready() -> None:
    no_class = _applied(
        [
            {
                "path": "/data/events.tsv",
                "selected_label_field": "trial_type",
                "value_decisions": {"button": _decision("response", False)},
            }
        ]
    )
    unresolved = replace(
        no_class,
        label_carrier_plan=[
            {
                "path": "/data/events.tsv",
                "selected_label_field": "trial_type",
                "value_decisions": {
                    "new": {
                        "role": "unknown",
                        "keep_event": None,
                        "use_as_class": None,
                        "suggested_name": "new",
                        "decision": "unresolved",
                        "decision_source": "unresolved",
                        "provenance": "observed",
                        "count": 1,
                    }
                },
            }
        ],
    )

    no_class_handoff = DataInterpretationSessionState._epoch_handoff(None, no_class)
    unresolved_handoff = DataInterpretationSessionState._epoch_handoff(None, unresolved)

    assert no_class_handoff["supervised_ready"] is False
    assert no_class_handoff["default_epoch_events"] == []
    assert no_class_handoff["supervised_blocker_codes"] == ["missing_reviewed_target"]
    assert any(
        "class target" in item for item in no_class_handoff["supervised_blockers"]
    )
    assert unresolved_handoff["supervised_ready"] is False
    assert unresolved_handoff["supervised_blocker_codes"] == [
        "unresolved_external_values"
    ]
    assert any(
        "unresolved" in item for item in unresolved_handoff["supervised_blockers"]
    )


def test_one_usable_class_is_not_supervised_ready() -> None:
    applied = _applied(
        [
            {
                "path": "/data/events.tsv",
                "selected_target_file": "/data/run-1_eeg.fif",
                "selected_label_field": "trial_type",
                "value_decisions": {
                    "left": _decision("stimulus", True, "Left hand", count=3),
                    "right": _decision("stimulus", True, "Right hand", count=0),
                },
                "run_class_map": {
                    "left": "Left hand",
                    "right": "Right hand",
                },
            }
        ]
    )

    handoff = DataInterpretationSessionState._epoch_handoff(None, applied)

    assert handoff["supervised_ready"] is False
    assert handoff["supervised_blocker_codes"] == ["insufficient_usable_classes"]
    assert any(
        "at least 2" in blocker and "usable trials" in blocker
        for blocker in handoff["supervised_blockers"]
    )


def _applied(plans: list[dict[str, object]]) -> AppliedInterpretation:
    return AppliedInterpretation(
        interpretation_id="interpretation-1",
        candidate_id="candidate-1",
        source_path="/data",
        source_kind="bids",
        loaded_files=["/data/run-1_eeg.fif"],
        label_carriers=[str(plan["path"]) for plan in plans],
        label_carrier_plan=plans,
        class_map={},
        label_imports=[
            {
                "mode": "timestamp",
                "selected_event_names": [],
                "success_count": len(plans),
            }
        ],
    )


def _decision(
    role: str,
    use_as_class: bool,
    class_name: str = "",
    *,
    keep_event: bool = True,
    count: int = 1,
) -> dict[str, object]:
    value: dict[str, object] = {
        "role": role,
        "keep_event": keep_event,
        "use_as_class": use_as_class,
        "suggested_name": class_name or role,
        "decision": "resolved",
        "decision_source": "user_choice",
        "provenance": "label_carrier_choice",
        "count": count,
    }
    if use_as_class:
        value["class_name"] = class_name
    return value
