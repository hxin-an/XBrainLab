"""Focused contract tests for external event/label value semantics."""

from __future__ import annotations

from XBrainLab.backend.application.data_interpretation_event_values import (
    build_event_catalog,
    class_map_from_value_decisions,
    class_targets_from_event_catalog,
    derive_class_views,
    filter_kept_label_values,
    review_event_values,
)


def test_bids_levels_are_suggestions_not_automatic_classes() -> None:
    review = review_event_values(
        value_counts={"left": 2, "button_press": 1},
        selected_field="trial_type",
        carrier_format="BIDS events",
        carrier_role="external labels",
        suggested_names={"left": "Left hand", "button_press": "Button press"},
        choices={},
    )

    assert review.unresolved_values == ["button_press", "left"]
    assert review.decisions["left"] == {
        "role": "unknown",
        "keep_event": None,
        "use_as_class": None,
        "suggested_name": "Left hand",
        "decision": "unresolved",
        "decision_source": "unresolved",
        "provenance": "observed:BIDS events:trial_type",
        "count": 2,
    }
    assert class_map_from_value_decisions(review.decisions) == {}


def test_generic_simple_class_label_series_is_resolved_by_domain_rule() -> None:
    review = review_event_values(
        value_counts={"left": 3, "right": 2},
        selected_field="classlabel",
        carrier_format="CSV",
        carrier_role="class labels",
        suggested_names={},
        choices={},
    )

    assert review.unresolved_values == []
    assert review.decisions["left"] == {
        "role": "unknown",
        "keep_event": True,
        "use_as_class": True,
        "class_name": "left",
        "suggested_name": "left",
        "decision": "resolved",
        "decision_source": "format_domain_rule",
        "provenance": "generic_simple_class_label_series:classlabel",
        "count": 3,
    }
    assert class_map_from_value_decisions(review.decisions) == {
        "left": "left",
        "right": "right",
    }


def test_ambiguous_generic_label_field_requires_explicit_class_carrier_role() -> None:
    ambiguous = review_event_values(
        value_counts={"left": 1, "button_press": 1},
        selected_field="label",
        carrier_format="CSV",
        carrier_role="external labels",
        suggested_names={},
        choices={},
    )
    explicit_class_series = review_event_values(
        value_counts={"left": 1, "right": 1},
        selected_field="label",
        carrier_format="CSV",
        carrier_role="class labels",
        suggested_names={},
        choices={},
    )

    assert ambiguous.unresolved_values == ["button_press", "left"]
    assert class_map_from_value_decisions(ambiguous.decisions) == {}
    assert explicit_class_series.unresolved_values == []
    assert class_map_from_value_decisions(explicit_class_series.decisions) == {
        "left": "left",
        "right": "right",
    }


def test_role_and_use_as_class_are_orthogonal() -> None:
    review = review_event_values(
        value_counts={"button_press": 4, "bad_segment": 1},
        selected_field="trial_type",
        carrier_format="BIDS events",
        carrier_role="external labels",
        suggested_names={},
        choices={
            "button_press": {
                "role": "response",
                "keep_event": True,
                "use_as_class": True,
                "class_name": "Responded",
            },
            "bad_segment": {
                "role": "artifact",
                "keep_event": True,
                "use_as_class": False,
            },
        },
    )

    assert review.unresolved_values == []
    assert review.decisions["button_press"]["role"] == "response"
    assert review.decisions["button_press"]["use_as_class"] is True
    assert "class_name" not in review.decisions["bad_segment"]
    assert class_map_from_value_decisions(review.decisions) == {
        "button_press": "Responded"
    }


def test_incomplete_explicit_decision_remains_unresolved() -> None:
    review = review_event_values(
        value_counts={"left": 1},
        selected_field="trial_type",
        carrier_format="BIDS events",
        carrier_role="external labels",
        suggested_names={},
        choices={
            "left": {
                "role": "stimulus",
                "keep_event": True,
                "use_as_class": True,
            }
        },
    )

    assert review.unresolved_values == ["left"]
    assert review.decisions["left"]["decision"] == "unresolved"
    assert review.decisions["left"]["decision_source"] == "user_choice_incomplete"


def test_disappeared_recipe_values_warn_and_new_values_are_unresolved() -> None:
    review = review_event_values(
        value_counts={"left": 2, "new_value": 1},
        selected_field="trial_type",
        carrier_format="BIDS events",
        carrier_role="external labels",
        suggested_names={},
        choices={
            "left": {
                "role": "stimulus",
                "keep_event": True,
                "use_as_class": True,
                "class_name": "Left hand",
                "decision_source": "user_choice",
                "provenance": "label_carrier_choice",
            },
            "right": {
                "role": "stimulus",
                "keep_event": True,
                "use_as_class": True,
                "class_name": "Right hand",
                "decision_source": "user_choice",
                "provenance": "label_carrier_choice",
            },
        },
    )

    assert review.unresolved_values == ["new_value"]
    assert review.missing_values == ["right"]
    assert review.decisions["left"]["count"] == 2
    assert any("right" in warning for warning in review.warnings)


def test_per_carrier_class_views_do_not_merge_conflicting_raw_values() -> None:
    plans = [
        {
            "path": "/data/run-1_events.tsv",
            "selected_target_file": "/data/run-1_eeg.fif",
            "selected_label_field": "trial_type",
            "value_decisions": {
                "T1": _class_decision("left hand"),
                "button": _non_class_decision("response"),
            },
        },
        {
            "path": "/data/run-2_events.tsv",
            "selected_target_file": "/data/run-2_eeg.fif",
            "selected_label_field": "trial_type",
            "value_decisions": {"T1": _class_decision("right hand")},
        },
    ]

    global_map, run_maps = derive_class_views(plans)

    assert global_map == {}
    assert run_maps == {
        "/data/run-1_eeg.fif": {"T1": "left hand"},
        "/data/run-2_eeg.fif": {"T1": "right hand"},
    }


def test_filtering_keeps_non_class_events_but_class_targets_only_include_classes() -> (
    None
):
    decisions = {
        "left": _class_decision("Left hand", count=2),
        "button_press": _non_class_decision("response", count=1),
        "bad_segment": {
            **_non_class_decision("artifact", count=1),
            "keep_event": False,
        },
    }
    values = ["left", "button_press", "bad_segment", "left"]

    assert filter_kept_label_values(values, decisions) == [
        "left",
        "button_press",
        "left",
    ]

    catalog = build_event_catalog(
        [
            {
                "path": "/data/events.tsv",
                "selected_target_file": "/data/eeg.fif",
                "selected_label_field": "trial_type",
                "value_decisions": decisions,
            }
        ]
    )
    targets = class_targets_from_event_catalog(catalog)

    assert {row["raw_value"] for row in catalog} == {
        "left",
        "button_press",
        "bad_segment",
    }
    assert targets == [
        {
            "event": "Left hand",
            "class_name": "Left hand",
            "raw_value": "left",
            "role": "unknown",
            "carrier": "/data/events.tsv",
            "target_file": "/data/eeg.fif",
            "field": "trial_type",
            "count": 2,
            "decision_source": "user_choice",
            "provenance": "label_carrier_choice",
        }
    ]


def test_filtering_excludes_canonical_missing_values_absent_from_review() -> None:
    decisions = {
        "None": _class_decision("None category", count=1),
        "#N/A": _class_decision("Hash N/A category", count=1),
    }

    assert filter_kept_label_values(
        ["None", "n/a", "#N/A", "null", "nan", "na"],
        decisions,
    ) == ["None", "#N/A"]


def _class_decision(name: str, *, count: int = 1) -> dict[str, object]:
    return {
        "role": "unknown",
        "keep_event": True,
        "use_as_class": True,
        "class_name": name,
        "suggested_name": name,
        "decision": "resolved",
        "decision_source": "user_choice",
        "provenance": "label_carrier_choice",
        "count": count,
    }


def _non_class_decision(role: str, *, count: int = 1) -> dict[str, object]:
    return {
        "role": role,
        "keep_event": True,
        "use_as_class": False,
        "suggested_name": role,
        "decision": "resolved",
        "decision_source": "user_choice",
        "provenance": "label_carrier_choice",
        "count": count,
    }
