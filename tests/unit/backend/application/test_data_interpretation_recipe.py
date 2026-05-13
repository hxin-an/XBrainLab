from types import SimpleNamespace

from XBrainLab.backend.application.data_interpretation_metadata import (
    FileMetadataResolution,
    MetadataFieldResolution,
)
from XBrainLab.backend.application.data_interpretation_recipe import (
    ImportRecipe,
    build_import_recipe,
    choices_from_import_recipe,
    import_recipe_from_dict,
    load_import_recipe,
)


def test_import_recipe_from_dict_rehydrates_metadata_and_mappings():
    recipe = import_recipe_from_dict(
        {
            "recipe_id": "recipe-1",
            "interpretation_id": "interp-1",
            "source_path": "/data",
            "source_kind": "bids",
            "selected_eeg_files": ["/data/sub-01.fif"],
            "skip_labels": True,
            "label_carrier": "external_files",
            "excluded_label_carriers": ["/data/rejected_events.tsv"],
            "metadata": [
                {
                    "file": "/data/sub-01.fif",
                    "subject": {
                        "field": "subject",
                        "value": "01",
                        "source": "bids_entity",
                        "decision": "safe",
                    },
                }
            ],
            "event_roles": {"trial_type": "class cue"},
            "class_map": {"left": "0"},
            "run_event_mappings": {
                "S001R04.edf": {"T1": "left_fist", "T2": "right_fist"}
            },
        }
    )

    assert isinstance(recipe, ImportRecipe)
    assert recipe.metadata[0].subject.value == "01"
    assert recipe.skip_labels is True
    assert recipe.label_carrier == "external_files"
    assert recipe.excluded_label_carriers == ["/data/rejected_events.tsv"]
    assert recipe.event_roles == {"trial_type": "class cue"}
    assert recipe.class_map == {"left": "0"}
    assert recipe.run_event_mappings == {
        "S001R04.edf": {"T1": "left_fist", "T2": "right_fist"}
    }


def test_build_import_recipe_preserves_applied_trace_and_writes_json(tmp_path):
    applied = SimpleNamespace(
        interpretation_id="interp-1",
        source_path="/data",
        source_kind="folder",
        loaded_files=["/data/sample.fif"],
        label_sources=["/external-labels"],
        label_carriers=["/data/events.tsv"],
        label_carrier_plan=[{"path": "/data/events.tsv"}],
        metadata=[],
        format_capabilities=[{"format": "MNE FIF"}],
        skip_labels=True,
        label_carrier="external_files",
        excluded_label_carriers=["/data/rejected_events.tsv"],
        validation_decision="needs_confirmation",
        confirmations=["Confirm metadata."],
        event_roles={"trial_type": "class cue"},
        class_map={"left": "0"},
        run_event_mappings={"S001R04.edf": {"T1": "left_fist", "T2": "right_fist"}},
        label_imports=[{"status": "applied"}],
        recipe_trace=["scan", "apply"],
    )

    recipe = build_import_recipe(
        recipe_id="recipe-1",
        applied=applied,
        warnings=["Review labels."],
    )
    target = tmp_path / "recipe.json"
    recipe.write_json(str(target))
    loaded = load_import_recipe(str(target))

    assert target.read_bytes().endswith(b"\n")
    assert loaded.label_sources == ["/external-labels"]
    assert loaded.skip_labels is True
    assert loaded.label_carrier == "external_files"
    assert loaded.excluded_label_carriers == ["/data/rejected_events.tsv"]
    assert loaded.recipe_trace == ["scan", "apply", "recipe:recipe-1"]
    assert loaded.warnings == ["Review labels."]
    assert loaded.label_imports == [{"status": "applied"}]
    assert loaded.run_event_mappings == {
        "S001R04.edf": {"T1": "left_fist", "T2": "right_fist"}
    }


def test_choices_from_import_recipe_recreates_review_choices():
    recipe = ImportRecipe(
        recipe_id="recipe-1",
        interpretation_id="interp-1",
        source_path="/data",
        source_kind="bids",
        selected_eeg_files=["/data/sub-01.fif"],
        label_sources=["/external-labels"],
        label_carriers=["/data/events.tsv"],
        label_carrier_plan=[
            {
                "path": "/data/events.tsv",
                "selected_target_file": "sub-01.fif",
                "selected_label_field": "trial_type",
                "selected_anchor": "onset",
                "selected_duration_field": "duration",
                "time_model": "seconds",
                "placement_method": "interval",
                "granularity": "trial",
                "role": "class cue labels",
            }
        ],
        metadata=[
            FileMetadataResolution(
                file="/data/sub-01.fif",
                subject=MetadataFieldResolution(
                    field="subject",
                    value="S01",
                    source="user_override",
                    decision="safe",
                    reason="confirmed",
                    override="S01",
                ),
                session=MetadataFieldResolution(
                    field="session",
                    value=None,
                    source="missing",
                    decision="needs_confirmation",
                    reason="missing",
                ),
                task=MetadataFieldResolution(
                    field="task",
                    value="motor-imagery",
                    source="user_override",
                    decision="safe",
                    reason="confirmed",
                    override="motor-imagery",
                ),
                run=MetadataFieldResolution(
                    field="run",
                    value=None,
                    source="missing",
                    decision="needs_confirmation",
                    reason="missing",
                ),
            )
        ],
        event_roles={"trial_type": "class cue"},
        class_map={"1": "left", "2": "right"},
        run_event_mappings={"S001R04.edf": {"T1": "left_fist", "T2": "right_fist"}},
        skip_labels=True,
        label_carrier="external_files",
        excluded_label_carriers=["/data/rejected_events.tsv"],
    )

    choices = choices_from_import_recipe(recipe)

    assert choices["recipe_id"] == "recipe-1"
    assert choices["selected_eeg_files"] == ["/data/sub-01.fif"]
    assert choices["label_sources"] == ["/external-labels"]
    assert choices["skip_labels"] is True
    assert choices["label_carrier"] == "external_files"
    assert choices["excluded_label_carriers"] == ["/data/rejected_events.tsv"]
    assert choices["required_label_carriers"] == ["/data/events.tsv"]
    assert choices["metadata_overrides"] == {
        "sub-01.fif": {"subject": "S01", "task": "motor-imagery"}
    }
    assert choices["label_carrier_choices"]["/data/events.tsv"] == {
        "target_file": "sub-01.fif",
        "label_field": "trial_type",
        "anchor": "onset",
        "duration_field": "duration",
        "time_model": "seconds",
        "placement_method": "interval",
        "granularity": "trial",
        "role": "class cue labels",
    }
    assert choices["event_roles"] == {"trial_type": "class cue"}
    assert choices["class_map"] == {"1": "left", "2": "right"}
    assert choices["run_event_mappings"] == {
        "S001R04.edf": {"T1": "left_fist", "T2": "right_fist"}
    }


def test_import_recipe_to_dict_is_json_ready():
    recipe = ImportRecipe(
        recipe_id="recipe-1",
        interpretation_id="interp-1",
        source_path="/data",
        source_kind="file",
        metadata=[
            FileMetadataResolution(
                file="/data/sample.fif",
                subject=MetadataFieldResolution(
                    field="subject",
                    value="S01",
                    source="user_override",
                    decision="safe",
                    reason="confirmed",
                ),
                session=MetadataFieldResolution(
                    field="session",
                    value=None,
                    source="missing",
                    decision="needs_confirmation",
                    reason="missing",
                ),
                task=MetadataFieldResolution(
                    field="task",
                    value=None,
                    source="missing",
                    decision="needs_confirmation",
                    reason="missing",
                ),
                run=MetadataFieldResolution(
                    field="run",
                    value=None,
                    source="missing",
                    decision="needs_confirmation",
                    reason="missing",
                ),
            )
        ],
    )

    payload = recipe.to_dict()

    assert payload["metadata"][0]["subject"]["value"] == "S01"
