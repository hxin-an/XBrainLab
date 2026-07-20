from types import SimpleNamespace

import pytest

from XBrainLab.backend.application import data_interpretation_recipe as recipe_module
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
            "bids": {
                "root": "/data",
                "selected_scope": {"events_files": ["/data/events.tsv"]},
            },
            "skip_labels": True,
            "label_sources": ["/external-labels"],
            "label_carriers": ["/data/events.tsv"],
            "label_carrier_plan": [{"path": "/data/events.tsv"}],
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
                "S001R04.edf": {"T1": "left fist", "T2": "right fist"},
            },
        }
    )

    assert isinstance(recipe, ImportRecipe)
    assert recipe.metadata[0].subject.value == "01"
    assert recipe.skip_labels is True
    assert recipe.bids == {
        "root": "/data",
        "selected_scope": {"events_files": ["/data/events.tsv"]},
    }
    assert recipe.label_sources == []
    assert recipe.label_carriers == []
    assert recipe.label_carrier_plan == []
    assert recipe.label_carrier == ""
    assert recipe.excluded_label_carriers == []
    assert recipe.event_roles == {}
    assert recipe.class_map == {}
    assert recipe.run_event_mappings == {}


def test_build_import_recipe_preserves_applied_trace_and_writes_json(tmp_path):
    applied = SimpleNamespace(
        interpretation_id="interp-1",
        source_path="/data",
        source_kind="folder",
        loaded_files=["/data/sample.fif"],
        label_sources=["/external-labels"],
        label_carriers=["/data/events.tsv"],
        bids={
            "root": "/data",
            "selected_scope": {"events_files": ["/data/events.tsv"]},
        },
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
        run_event_mappings={
            "S001R04.edf": {"T1": "left fist", "T2": "right fist"},
        },
        label_imports=[{"status": "applied"}],
        recipe_trace=["scan", "apply"],
        epoch_settings={"t_min": -0.2, "t_max": 1.0},
        epoch_window=(-0.2, 1.0),
        baseline=(None, 0.0),
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
    assert loaded.label_sources == []
    assert loaded.bids == {
        "root": "/data",
        "selected_scope": {"events_files": ["/data/events.tsv"]},
    }
    assert loaded.skip_labels is True
    assert loaded.label_carriers == []
    assert loaded.label_carrier_plan == []
    assert loaded.label_carrier == ""
    assert loaded.excluded_label_carriers == []
    assert loaded.event_roles == {}
    assert loaded.class_map == {}
    assert loaded.recipe_trace == ["scan", "apply", "recipe:recipe-1"]
    assert loaded.warnings == ["Review labels."]
    assert loaded.label_imports == []
    assert loaded.run_event_mappings == {}
    assert {
        "epoch",
        "epoch_settings",
        "epoch_window",
        "t_min",
        "t_max",
        "baseline",
    }.isdisjoint(recipe.to_dict())


def test_recipe_preserves_reviewed_label_content_identity(tmp_path):
    content_identity = {
        "version": 1,
        "algorithm": "sha256",
        "scope": "label_carriers_and_bids_event_sidecars",
        "scope_sha256": "scope-digest",
        "content_sha256": "content-digest",
        "review_contract_sha256": "contract-digest",
        "files": [
            {
                "path": "/data/events.tsv",
                "role": "label_carrier",
                "file_bytes": 42,
                "sha256": "file-digest",
            }
        ],
        "bindings": [{"path": "/data/events.tsv"}],
    }
    applied = SimpleNamespace(
        interpretation_id="interp-identity",
        source_path="/data",
        source_kind="folder",
        loaded_files=["/data/sample.fif"],
        label_sources=["/data"],
        label_carriers=["/data/events.tsv"],
        bids={},
        label_carrier_plan=[{"path": "/data/events.tsv"}],
        metadata=[],
        format_capabilities=[],
        skip_labels=False,
        label_carrier="external_files",
        excluded_label_carriers=[],
        validation_decision="needs_confirmation",
        confirmations=["Confirm labels."],
        event_roles={"trial_type": "class label"},
        class_map={"left": "Left"},
        internal_event_selection={},
        run_event_mappings={},
        label_imports=[{"status": "applied"}],
        recipe_trace=["content:scope-digest", "applied:interp-identity"],
    )

    recipe = build_import_recipe(
        recipe_id="recipe-identity",
        applied=applied,
        warnings=[],
        content_identity=content_identity,
    )
    target = tmp_path / "identity-recipe.json"
    recipe.write_json(str(target))
    loaded = load_import_recipe(str(target))

    assert loaded.content_identity == content_identity
    assert loaded.recipe_trace == [
        "content:scope-digest",
        "applied:interp-identity",
        "recipe:recipe-identity",
    ]


def test_recipe_loader_uses_one_bounded_binary_read(tmp_path, monkeypatch) -> None:
    target = tmp_path / "oversized-recipe.json"
    target.write_bytes(b"{}")
    with target.open("ab") as handle:
        handle.truncate(recipe_module.IMPORT_RECIPE_MAX_BYTES + 100)
    original_open = type(target).open
    original_read_text = type(target).read_text
    read_sizes = []

    class _ObservedReader:
        def __init__(self, handle):
            self._handle = handle

        def __enter__(self):
            self._handle.__enter__()
            return self

        def __exit__(self, *args):
            return self._handle.__exit__(*args)

        def read(self, size=-1):
            read_sizes.append(size)
            return self._handle.read(size)

        def __getattr__(self, name):
            return getattr(self._handle, name)

    def _observed_open(path, *args, **kwargs):
        handle = original_open(path, *args, **kwargs)
        mode = str(args[0] if args else kwargs.get("mode", "r"))
        if path == target and mode == "rb":
            return _ObservedReader(handle)
        return handle

    def _guarded_read_text(path, *args, **kwargs):
        if path == target:
            pytest.fail("recipe loader used unbounded Path.read_text")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(type(target), "open", _observed_open)
    monkeypatch.setattr(type(target), "read_text", _guarded_read_text)

    with pytest.raises(ValueError, match=r"recipe.*limit"):
        recipe_module.load_import_recipe(str(target))

    assert read_sizes == [recipe_module.IMPORT_RECIPE_MAX_BYTES + 1]


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
        run_event_mappings={
            "S001R04.edf": {"T1": "left fist", "T2": "right fist"},
        },
        skip_labels=False,
        label_carrier="external_files",
        excluded_label_carriers=["/data/rejected_events.tsv"],
    )

    choices = choices_from_import_recipe(recipe)

    assert choices["recipe_id"] == "recipe-1"
    assert choices["selected_eeg_files"] == ["/data/sub-01.fif"]
    assert choices["label_sources"] == ["/external-labels"]
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
        "value_decisions": {
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
        },
    }
    assert choices["event_roles"] == {"trial_type": "class cue"}
    assert "class_map" not in choices
    assert choices["run_event_mappings"] == {
        "S001R04.edf": {"T1": "left fist", "T2": "right fist"},
    }


def test_choices_from_import_recipe_skip_labels_suppresses_label_choices():
    recipe = ImportRecipe(
        recipe_id="recipe-1",
        interpretation_id="interp-1",
        source_path="/data",
        source_kind="folder",
        selected_eeg_files=["/data/sub-01.fif"],
        label_sources=["/external-labels"],
        label_carriers=["/data/events.tsv"],
        label_carrier_plan=[{"path": "/data/events.tsv"}],
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
        event_roles={"trial_type": "class cue"},
        class_map={"1": "left", "2": "right"},
        run_event_mappings={
            "S001R04.edf": {"T1": "left fist", "T2": "right fist"},
        },
        skip_labels=True,
        label_carrier="external_files",
        excluded_label_carriers=["/data/rejected_events.tsv"],
    )

    choices = choices_from_import_recipe(recipe)

    assert choices["recipe_id"] == "recipe-1"
    assert choices["selected_eeg_files"] == ["/data/sub-01.fif"]
    assert choices["metadata_overrides"] == {"sub-01.fif": {"subject": "S01"}}
    assert choices["skip_labels"] is True
    for key in (
        "label_sources",
        "label_carrier",
        "excluded_label_carriers",
        "required_label_carriers",
        "label_carrier_choices",
        "event_roles",
        "class_map",
        "internal_event_selection",
        "run_event_mappings",
    ):
        assert key not in choices


def test_choices_from_import_recipe_preserves_event_order_targets():
    recipe = ImportRecipe(
        recipe_id="recipe-1",
        interpretation_id="interp-1",
        source_path="/data",
        source_kind="folder",
        label_carriers=["/data/A01T.mat"],
        label_carrier_plan=[
            {
                "path": "/data/A01T.mat",
                "selected_label_field": "classlabel",
                "selected_anchor": "769",
                "selected_target_event_codes": ["769", "770"],
                "time_model": "trial_order",
                "placement_method": "eeg_event",
                "granularity": "trial",
                "role": "external labels",
            }
        ],
    )

    choices = choices_from_import_recipe(recipe)

    assert choices["label_carrier_choices"]["/data/A01T.mat"]["target_event_codes"] == [
        "769",
        "770",
    ]


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
