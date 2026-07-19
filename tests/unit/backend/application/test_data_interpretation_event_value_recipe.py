"""Recipe migration and exact event-value replay tests."""

from __future__ import annotations

from XBrainLab.backend.application.data_interpretation_recipe import (
    choices_from_import_recipe,
    import_recipe_from_dict,
)


def test_recipe_replays_exact_per_carrier_value_decisions() -> None:
    decisions = {
        "left": {
            "role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": "Left hand",
            "suggested_name": "Left hand",
            "decision": "resolved",
            "decision_source": "user_choice",
            "provenance": "label_carrier_choice",
            "count": 2,
        },
        "button": {
            "role": "response",
            "keep_event": True,
            "use_as_class": False,
            "suggested_name": "Button",
            "decision": "resolved",
            "decision_source": "user_choice",
            "provenance": "label_carrier_choice",
            "count": 1,
        },
    }
    recipe = import_recipe_from_dict(
        {
            "recipe_id": "recipe-1",
            "interpretation_id": "interpretation-1",
            "source_path": "/data",
            "source_kind": "bids",
            "selected_eeg_files": ["/data/sub-01_task-mi_eeg.fif"],
            "label_carriers": ["/data/sub-01_task-mi_events.tsv"],
            "label_carrier_plan": [
                {
                    "path": "/data/sub-01_task-mi_events.tsv",
                    "selected_target_file": "/data/sub-01_task-mi_eeg.fif",
                    "selected_label_field": "trial_type",
                    "value_decisions": decisions,
                }
            ],
            "class_map": {"left": "Left hand"},
        }
    )

    choices = choices_from_import_recipe(recipe)

    assert (
        choices["label_carrier_choices"]["/data/sub-01_task-mi_events.tsv"][
            "value_decisions"
        ]
        == decisions
    )
    assert "class_map" not in choices


def test_legacy_recipe_class_map_becomes_unconfirmed_migration_suggestion() -> None:
    recipe = import_recipe_from_dict(
        {
            "recipe_id": "recipe-legacy",
            "interpretation_id": "interpretation-legacy",
            "source_path": "/data",
            "source_kind": "folder",
            "label_carriers": ["/data/labels.csv"],
            "label_carrier_plan": [
                {
                    "path": "/data/labels.csv",
                    "selected_label_field": "condition",
                    "time_model": "trial_order",
                    "granularity": "trial",
                }
            ],
            "class_map": {"1": "left", "2": "right"},
        }
    )

    choices = choices_from_import_recipe(recipe)
    migrated = choices["label_carrier_choices"]["/data/labels.csv"]["value_decisions"]

    assert "class_map" not in choices
    assert migrated == {
        "1": {
            "suggested_name": "left",
            "decision_source": "legacy_recipe_class_map_suggestion",
            "provenance": "legacy_recipe:class_map",
        },
        "2": {
            "suggested_name": "right",
            "decision_source": "legacy_recipe_class_map_suggestion",
            "provenance": "legacy_recipe:class_map",
        },
    }
