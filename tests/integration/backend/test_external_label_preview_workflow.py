"""Low-mock external-label preview and one-shot commit integration coverage."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import numpy as np
from scipy.io import savemat

from tests.unit.backend.path_assertions import filesystem_path_key
from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    AttachLabelsCommand,
    ImportLabelsCommand,
    LabelImportPlan,
    LoadDataCommand,
    PreviewInterpretationCommand,
    PreviewLabelImportCommand,
    ReloadInterpretationRecipeCommand,
    ResetSessionCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.application.results import ErrorType

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "data"
GDF_PATH = (FIXTURE_DIR / "A01T.gdf").resolve()
MAT_PATH = (FIXTURE_DIR / "label" / "A01T.mat").resolve()
A02_MAT_PATH = (FIXTURE_DIR / "label" / "A02T.mat").resolve()
CLASS_MAP = {1: "left", 2: "right", 3: "feet", 4: "tongue"}
EVENT_ID = {name: event_code for event_code, name in CLASS_MAP.items()}
GRAZ_TARGET_EVENTS = ["769", "770", "771", "772"]


def _real_interpreted_service() -> ApplicationService:
    service = ApplicationService()
    commands = (
        ScanSourceCommand(source_path=str(GDF_PATH), source_hint="file"),
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(GDF_PATH)],
                "skip_labels": True,
                "excluded_label_carriers": [str(MAT_PATH)],
            }
        ),
        ValidateInterpretationCommand(),
        ApplyInterpretationCommand(confirmed=True),
    )
    for command in commands:
        result = service.execute(command)
        assert result.ok is True, result.message
    return service


def _preview(service: ApplicationService, label_path: Path = MAT_PATH):
    return service.execute(
        PreviewLabelImportCommand(
            label_paths=[str(label_path)],
            label_configs={str(label_path): {"label_field": "classlabel"}},
        )
    )


def _plan(preview_id: str, label_path: Path = MAT_PATH) -> LabelImportPlan:
    return LabelImportPlan(
        preview_id=preview_id,
        target_indices=[0],
        label_paths=[str(label_path)],
        label_configs={str(label_path): {"label_field": "classlabel"}},
        file_mapping={str(GDF_PATH): str(label_path)},
        mapping=CLASS_MAP,
        selected_event_names=GRAZ_TARGET_EVENTS,
        mode="sequence",
    )


def _link_or_copy(source: Path, target: Path) -> None:
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


def _loaded_target(service: ApplicationService, index: int = 0):
    """Read application-owned domain state for deep rollback verification only."""
    return service.dataset.get_loaded_data_list()[index]


def _event_signature(target) -> tuple[np.ndarray, dict[str, int], bool]:
    events, event_id = target.get_event_list()
    return events.copy(), dict(event_id), bool(target.is_labels_imported())


def test_real_a01t_preview_commit_updates_exact_state_recipe_and_consumes_once(
    tmp_path: Path,
) -> None:
    service = _real_interpreted_service()
    high_cardinality = tmp_path / "high-cardinality.npy"
    np.save(high_cardinality, np.arange(20_000, dtype=np.int32))

    blocked = service.execute(
        PreviewLabelImportCommand(label_paths=[str(high_cardinality)])
    )
    assert blocked.failed is True
    assert blocked.error_type is ErrorType.PRECONDITION
    assert blocked.diagnostics["code"] == "label_preview_cardinality_exceeded"
    assert blocked.diagnostics["observed_count"] == 257
    assert blocked.diagnostics["observed_count_is_lower_bound"] is True
    assert blocked.diagnostics["limit"] == 256
    assert "label_preview" not in blocked.diagnostics
    assert blocked.state.interpretation.label_import_count == 0

    preview = _preview(service)
    assert preview.ok is True
    summary = preview.diagnostics["label_preview"]
    assert summary["unique_labels"] == [1, 2, 3, 4]
    assert summary["total_label_count"] == 288
    plan = _plan(summary["preview_id"])

    imported = service.execute(ImportLabelsCommand(plan=plan))

    assert imported.ok is True
    assert imported.diagnostics["success_count"] == 1
    target = _loaded_target(service)
    events, event_id = target.get_event_list()
    assert event_id == EVENT_ID
    assert events.shape == (288, 3)
    assert {
        name: int((events[:, -1] == event_code).sum())
        for event_code, name in CLASS_MAP.items()
    } == {"left": 72, "right": 72, "feet": 72, "tongue": 72}
    assert imported.state.interpretation.label_import_count == 1
    assert imported.state.interpretation.label_imports == [
        {
            "mode": "sequence",
            "label_carriers": [str(MAT_PATH)],
            "label_configs": {str(MAT_PATH): {"label_field": "classlabel"}},
            "target_files": [str(GDF_PATH)],
            "file_mapping": {str(GDF_PATH): str(MAT_PATH)},
            "selected_event_names": GRAZ_TARGET_EVENTS,
            "class_map": {
                "1": "left",
                "2": "right",
                "3": "feet",
                "4": "tongue",
            },
            "success_count": 1,
        }
    ]
    live_review = service.get_interpretation_review()
    live_candidate = live_review["candidate"]
    live_preview = live_review["preview"]
    assert live_candidate["choices"]["skip_labels"] is False
    assert "class_map" not in live_candidate["choices"]
    assert live_candidate["label_sources"] == [str(MAT_PATH)]
    assert live_candidate["label_carriers"] == [str(MAT_PATH)]
    assert live_candidate["class_map"] == {
        "1": "left",
        "2": "right",
        "3": "feet",
        "4": "tongue",
    }
    [live_carrier] = live_candidate["label_carrier_plan"]
    assert live_carrier["path"] == str(MAT_PATH)
    assert live_carrier["selected_target_file"] == str(GDF_PATH)
    assert live_carrier["placement_review"]["status"] == "ready"
    assert live_preview["label_carrier_preview"] == live_candidate["label_carrier_plan"]
    assert live_preview["class_map"] == live_candidate["class_map"]
    assert live_preview["content_identity"] == live_candidate["content_identity"]
    assert live_review["validation_decision"]["decision"] == "safe"

    validated_live = service.execute(
        ValidateInterpretationCommand(candidate_id=live_candidate["candidate_id"])
    )
    assert validated_live.ok is True, validated_live.message
    assert validated_live.diagnostics["validation_decision"]["decision"] == "safe"

    saved = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(tmp_path / "a01t-recipe.json"))
    )
    assert saved.ok is True
    assert saved.diagnostics["recipe"]["label_imports"] == (
        imported.state.interpretation.label_imports
    )
    assert "label_import:sequence:1" in saved.diagnostics["recipe"]["recipe_trace"]
    saved_recipe = saved.diagnostics["recipe"]
    assert saved_recipe["content_identity"] == live_candidate["content_identity"]
    assert saved_recipe["label_carrier_plan"] == live_candidate["label_carrier_plan"]
    assert saved_recipe["label_sources"] == [str(MAT_PATH)]
    assert saved_recipe["label_carriers"] == [str(MAT_PATH)]
    assert saved_recipe["class_map"] == {
        "1": "left",
        "2": "right",
        "3": "feet",
        "4": "tongue",
    }
    assert saved_recipe["label_imports"][0]["label_configs"] == {
        str(MAT_PATH): {"label_field": "classlabel"}
    }
    [saved_carrier] = saved_recipe["label_carrier_plan"]
    assert saved_carrier["path"] == str(MAT_PATH)
    assert saved_carrier["selected_label_field"] == "classlabel"
    assert saved_carrier["selected_target_file"] == str(GDF_PATH)

    replay = ApplicationService().execute(
        ReloadInterpretationRecipeCommand(
            recipe_path=str(tmp_path / "a01t-recipe.json")
        )
    )
    assert replay.ok is True, replay.message
    replay_candidate = replay.diagnostics["candidate"]
    assert replay_candidate["label_sources"] == [str(MAT_PATH)]
    assert replay_candidate["label_carriers"] == [str(MAT_PATH)]
    assert replay_candidate["class_map"] == saved_recipe["class_map"]
    [replayed_carrier] = replay_candidate["label_carrier_plan"]
    assert replayed_carrier["selected_label_field"] == "classlabel"
    assert replayed_carrier["selected_target_file"] == str(GDF_PATH)
    replay_choices = replay_candidate["choices"]
    assert replay_choices["label_sources"] == [str(MAT_PATH)]
    assert replay_choices["required_label_carriers"] == [str(MAT_PATH)]
    replay_carrier_choices = replay_choices["label_carrier_choices"][str(MAT_PATH)]
    assert replay_carrier_choices["label_field"] == "classlabel"
    assert {
        raw_value: decision["class_name"]
        for raw_value, decision in replay_carrier_choices["value_decisions"].items()
    } == saved_recipe["class_map"]

    consumed = service.execute(ImportLabelsCommand(plan=plan))
    assert consumed.failed is True
    assert consumed.error_type is ErrorType.PRECONDITION
    assert consumed.diagnostics["code"] == "label_preview_unavailable"
    assert consumed.state.interpretation.label_import_count == 1


def test_reviewed_preview_and_import_share_one_publication_generation() -> None:
    service = _real_interpreted_service()
    reviewed_generation = service.get_view_publication().generation

    preview = service.execute(
        PreviewLabelImportCommand(
            label_paths=[str(MAT_PATH)],
            label_configs={str(MAT_PATH): {"label_field": "classlabel"}},
        ),
        expected_publication_generation=reviewed_generation,
    )

    assert preview.ok is True, preview.message
    assert service.get_view_publication().generation == reviewed_generation
    preview_id = preview.diagnostics["label_preview"]["preview_id"]

    imported = service.execute(
        ImportLabelsCommand(plan=_plan(preview_id)),
        expected_publication_generation=reviewed_generation,
    )

    assert imported.ok is True, imported.message
    assert imported.diagnostics["success_count"] == 1
    assert imported.state.interpretation.label_import_count == 1


def test_preview_is_unavailable_after_session_reset_and_same_path_reload() -> None:
    service = _real_interpreted_service()
    preview = _preview(service)
    assert preview.ok is True, preview.message
    preview_id = preview.diagnostics["label_preview"]["preview_id"]
    original_target = _loaded_target(service)

    reset = service.execute(ResetSessionCommand(confirmed=True))
    assert reset.ok is True, reset.message
    reloaded = service.execute(
        LoadDataCommand(paths=[str(GDF_PATH)], allow_append=False)
    )
    assert reloaded.ok is True, reloaded.message
    assert service.wait_for_background_tasks(timeout=10.0)
    replacement_target = _loaded_target(service)
    assert replacement_target is not original_target
    before_events, before_event_id, before_labels_imported = _event_signature(
        replacement_target
    )
    before_publication = service.get_view_publication()
    assert before_publication.state.interpretation.label_import_count == 0
    assert before_publication.state.interpretation.label_imports == []

    stale = service.execute(ImportLabelsCommand(plan=_plan(preview_id)))

    assert stale.failed is True
    assert stale.error_type is ErrorType.PRECONDITION
    assert stale.diagnostics["code"] == "label_preview_unavailable"
    assert _loaded_target(service) is replacement_target
    after_events, after_event_id, after_labels_imported = _event_signature(
        replacement_target
    )
    np.testing.assert_array_equal(after_events, before_events)
    assert after_event_id == before_event_id
    assert after_labels_imported is before_labels_imported
    assert stale.state.interpretation == before_publication.state.interpretation
    assert stale.state.raw == before_publication.state.raw
    assert stale.changed_state.raw_changed is False
    assert stale.changed_state.interpretation_changed is False
    assert stale.changed_state.error_changed is True
    after_publication = service.get_view_publication()
    assert after_publication.generation > before_publication.generation
    assert after_publication.state == stale.state
    assert after_publication.state.raw == before_publication.state.raw
    assert (
        after_publication.state.interpretation
        == before_publication.state.interpretation
    )


def test_real_shared_label_recipe_keeps_full_path_identity_for_duplicate_basenames(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "multi-target-source"
    source_dir.mkdir()
    target_dirs = [source_dir / "subject-a", source_dir / "subject-b"]
    for target_dir in target_dirs:
        target_dir.mkdir()
    target_paths = [
        (target_dir / "session.gdf").resolve() for target_dir in target_dirs
    ]
    for target in target_paths:
        _link_or_copy(GDF_PATH, target)
    shared_labels = (source_dir / "shared.mat").resolve()
    shutil.copyfile(MAT_PATH, shared_labels)

    service = ApplicationService()
    commands = (
        ScanSourceCommand(source_path=str(source_dir), source_hint="folder"),
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(path) for path in target_paths],
                "skip_labels": True,
            }
        ),
        ValidateInterpretationCommand(),
        ApplyInterpretationCommand(confirmed=True),
    )
    for command in commands:
        result = service.execute(command)
        assert result.ok is True, result.message

    preview = _preview(service, shared_labels)
    assert preview.ok is True, preview.message
    preview_id = preview.diagnostics["label_preview"]["preview_id"]
    file_mapping = {str(target): str(shared_labels) for target in target_paths}
    selected_events = ["769", "770", "771", "772"]
    imported = service.execute(
        ImportLabelsCommand(
            plan=LabelImportPlan(
                preview_id=preview_id,
                target_indices=[0, 1],
                label_paths=[str(shared_labels)],
                label_configs={str(shared_labels): {"label_field": "classlabel"}},
                file_mapping=file_mapping,
                mapping=CLASS_MAP,
                selected_event_names=selected_events,
                mode="sequence",
            )
        )
    )
    assert imported.ok is True, imported.message
    assert imported.diagnostics["success_count"] == 2

    targets = service.dataset.get_loaded_data_list()
    assert len(targets) == 2
    for target in targets:
        events, event_id = target.get_event_list()
        assert event_id == EVENT_ID
        assert events.shape == (288, 3)
        assert {
            name: int((events[:, -1] == event_code).sum())
            for event_code, name in CLASS_MAP.items()
        } == {"left": 72, "right": 72, "feet": 72, "tongue": 72}

    live_review = service.get_interpretation_review()
    live_candidate = live_review["candidate"]
    live_preview = live_review["preview"]
    [live_carrier] = live_candidate["label_carrier_plan"]
    assert live_candidate["choices"]["skip_labels"] is False
    assert live_carrier["selected_target_files"] == sorted(file_mapping)
    assert live_carrier["selected_target_event_codes"] == selected_events
    assert live_carrier["placement_review"]["selected_eeg_events"] == 288
    assert live_carrier["placement_review"][
        "selected_eeg_events_by_target"
    ] == dict.fromkeys(sorted(file_mapping), 288)
    assert live_carrier["placement_review"]["status"] == "ready"
    assert live_preview["label_carrier_preview"] == live_candidate["label_carrier_plan"]
    assert (
        imported.state.interpretation.label_carrier_plan
        == (live_candidate["label_carrier_plan"])
    )
    assert live_review["validation_decision"]["decision"] == "safe"
    assert live_review["validation_decision"]["blocked_reasons"] == []
    validated_live = service.execute(
        ValidateInterpretationCommand(candidate_id=live_candidate["candidate_id"])
    )
    assert validated_live.ok is True, validated_live.message
    assert validated_live.diagnostics["validation_decision"]["decision"] == "safe"
    assert validated_live.diagnostics["validation_decision"]["blocked_reasons"] == []

    recipe_path = tmp_path / "multi-target-recipe.json"
    saved = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path))
    )
    assert saved.ok is True, saved.message
    saved_recipe = saved.diagnostics["recipe"]
    assert saved_recipe["label_carrier_plan"] == live_candidate["label_carrier_plan"]
    [saved_carrier] = saved_recipe["label_carrier_plan"]
    assert saved_carrier["path"] == str(shared_labels)
    assert saved_carrier["selected_target_file"] == ""
    assert saved_carrier["selected_target_files"] == sorted(file_mapping)
    assert saved_carrier["selected_target_event_codes"] == selected_events
    assert saved_recipe["label_imports"][-1]["file_mapping"] == file_mapping
    assert saved_recipe["label_imports"][-1]["selected_event_names"] == (
        selected_events
    )

    replay_service = ApplicationService()
    reloaded = replay_service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path))
    )
    assert reloaded.ok is True, reloaded.message
    candidate = reloaded.diagnostics["candidate"]
    candidate_event_rows = candidate["internal_event_preview"]["candidate_label_events"]
    assert candidate_event_rows
    for event_row in candidate_event_rows:
        assert {filesystem_path_key(path) for path in event_row["file_counts"]} == {
            filesystem_path_key(path) for path in file_mapping
        }
    [replayed_carrier] = candidate["label_carrier_plan"]
    assert replayed_carrier["selected_target_files"] == sorted(file_mapping)
    assert replayed_carrier["selected_target_event_codes"] == selected_events
    assert replayed_carrier["placement_review"]["selected_eeg_events"] == 288
    assert replayed_carrier["placement_review"][
        "selected_eeg_events_by_target"
    ] == dict.fromkeys(sorted(file_mapping), 288)
    assert replayed_carrier["placement_review"]["status"] == "ready"
    replayed_choices = candidate["choices"]["label_carrier_choices"][str(shared_labels)]
    assert replayed_choices["target_files"] == sorted(file_mapping)
    assert replayed_choices["target_event_codes"] == selected_events

    validated = replay_service.execute(
        ValidateInterpretationCommand(candidate_id=candidate["candidate_id"])
    )
    assert validated.ok is True, validated.message
    applied = replay_service.execute(
        ApplyInterpretationCommand(
            candidate_id=candidate["candidate_id"],
            confirmed=True,
        )
    )
    assert applied.ok is True, applied.message
    assert applied.diagnostics["success_count"] == 2
    assert applied.diagnostics["label_apply"]["success_count"] == 2

    replayed_targets = replay_service.dataset.get_loaded_data_list()
    assert len(replayed_targets) == 2
    for target in replayed_targets:
        events, event_id = target.get_event_list()
        assert event_id == EVENT_ID
        assert events.shape == (288, 3)
        assert {
            name: int((events[:, -1] == event_code).sum())
            for event_code, name in CLASS_MAP.items()
        } == {"left": 72, "right": 72, "feet": 72, "tongue": 72}


def test_import_labels_rolls_back_raw_events_when_recipe_recording_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _real_interpreted_service()
    preview = _preview(service)
    assert preview.ok is True, preview.message
    plan = _plan(preview.diagnostics["label_preview"]["preview_id"])
    target = _loaded_target(service)
    before_events, before_event_id, before_imported = _event_signature(target)
    before_state = service.get_state().interpretation
    before_review = service.get_interpretation_review()
    interpretation_service = service.interpretation._service()

    def fail_recording(**_kwargs):
        raise RuntimeError("injected recipe recording failure")

    monkeypatch.setattr(
        interpretation_service,
        "record_label_import_for_recipe",
        fail_recording,
    )

    failed = service.execute(ImportLabelsCommand(plan=plan))

    assert failed.failed is True
    assert failed.diagnostics["rolled_back"] is True
    after_target = _loaded_target(service)
    after_events, after_event_id, after_imported = _event_signature(after_target)
    assert np.array_equal(after_events, before_events)
    assert after_event_id == before_event_id
    assert after_imported is before_imported is False
    assert service.get_state().interpretation == before_state
    assert service.get_interpretation_review() == before_review


def test_import_labels_rolls_back_raw_and_interpretation_when_recipe_commit_fails(
    tmp_path: Path,
) -> None:
    class FailOnSet(dict):
        def __setitem__(self, _key, _value) -> None:
            raise RuntimeError("injected interpretation recipe state failure")

    service = _real_interpreted_service()
    saved = service.execute(
        SaveInterpretationRecipeCommand(
            recipe_path=str(tmp_path / "pre-import-recipe.json")
        )
    )
    assert saved.ok is True, saved.message
    preview = _preview(service)
    assert preview.ok is True, preview.message
    plan = _plan(preview.diagnostics["label_preview"]["preview_id"])
    target = _loaded_target(service)
    before_events, before_event_id, before_imported = _event_signature(target)
    before_state = service.get_state().interpretation
    before_review = service.get_interpretation_review()
    interpretation_state = service.interpretation._service().state
    existing_recipe = interpretation_state.resolve_recipe(None)
    before_recipe = existing_recipe.to_dict()
    interpretation_state._recipes = FailOnSet(
        {existing_recipe.recipe_id: existing_recipe}
    )

    failed = service.execute(ImportLabelsCommand(plan=plan))

    assert failed.failed is True
    assert failed.diagnostics["rolled_back"] is True
    after_target = _loaded_target(service)
    after_events, after_event_id, after_imported = _event_signature(after_target)
    assert np.array_equal(after_events, before_events)
    assert after_event_id == before_event_id
    assert after_imported is before_imported is False
    assert service.get_state().interpretation == before_state
    assert service.get_interpretation_review() == before_review
    assert interpretation_state.resolve_recipe(None).to_dict() == before_recipe


def test_post_load_label_recipe_binds_actual_carrier_identity_and_detects_changes(
    tmp_path: Path,
) -> None:
    service = _real_interpreted_service()
    mutable_labels = (tmp_path / "post-load-labels.mat").resolve()
    label_values = np.tile(np.array([1, 2, 3, 4]), 72)
    savemat(mutable_labels, {"classlabel": label_values})

    preview = _preview(service, mutable_labels)
    assert preview.ok is True, preview.message
    imported = service.execute(
        ImportLabelsCommand(
            plan=_plan(
                preview.diagnostics["label_preview"]["preview_id"],
                mutable_labels,
            )
        )
    )
    assert imported.ok is True, imported.message

    recipe_path = tmp_path / "post-load-label-recipe.json"
    saved = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path))
    )
    assert saved.ok is True, saved.message
    saved_recipe = saved.diagnostics["recipe"]
    assert saved_recipe["label_sources"] == [str(mutable_labels)]
    assert saved_recipe["label_carriers"] == [str(mutable_labels)]
    assert saved_recipe["excluded_label_carriers"] == [str(MAT_PATH)]
    identity = saved_recipe["content_identity"]
    files_by_path = {row["path"]: row for row in identity["files"]}
    assert str(MAT_PATH) not in files_by_path
    carrier_identity = files_by_path[str(mutable_labels)]
    assert carrier_identity["role"] == "label_carrier"
    assert carrier_identity["file_bytes"] == mutable_labels.stat().st_size
    assert (
        carrier_identity["sha256"]
        == hashlib.sha256(mutable_labels.read_bytes()).hexdigest()
    )
    [binding] = [
        row for row in identity["bindings"] if row["path"] == str(mutable_labels)
    ]
    assert binding["selected_target_file"] == str(GDF_PATH)
    assert binding["selected_label_field"] == "classlabel"

    unchanged = ApplicationService().execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path))
    )
    assert unchanged.ok is True, unchanged.message
    unchanged_rows = unchanged.diagnostics["preview"]["recipe_reload_summary"][
        "diff_rows"
    ]
    unchanged_identity = unchanged.diagnostics["candidate"]["content_identity"]
    assert unchanged_identity["content_sha256"] == identity["content_sha256"]
    assert any(row["item"] == "Reviewed label content" for row in unchanged_rows)

    changed_values = label_values.copy()
    changed_values[0] = 2
    savemat(mutable_labels, {"classlabel": changed_values})
    changed = ApplicationService().execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path))
    )
    assert changed.ok is True, changed.message
    changed_identity = changed.diagnostics["candidate"]["content_identity"]
    assert changed_identity["content_sha256"] != identity["content_sha256"]
    changed_rows = changed.diagnostics["preview"]["recipe_reload_summary"]["diff_rows"]
    assert {
        "item": "Reviewed label content",
        "status": "Changed",
        "detail": "Label/event carrier content changed and requires review.",
    } in changed_rows


def test_real_a01t_corrupt_middle_preview_clears_cache_without_state_pollution(
    tmp_path: Path,
) -> None:
    service = _real_interpreted_service()
    valid_preview = _preview(service)
    assert valid_preview.ok is True
    stale_id = valid_preview.diagnostics["label_preview"]["preview_id"]
    corrupt = tmp_path / "corrupt-middle.mat"
    corrupt.write_bytes(b"not a MATLAB label payload")

    failed = service.execute(
        PreviewLabelImportCommand(
            label_paths=[str(MAT_PATH), str(corrupt), str(A02_MAT_PATH)],
            label_configs={
                str(MAT_PATH): {"label_field": "classlabel"},
                str(corrupt): {"label_field": "classlabel"},
                str(A02_MAT_PATH): {"label_field": "classlabel"},
            },
        )
    )

    assert failed.failed is True
    assert failed.error_type is ErrorType.FILE_CORRUPTED
    assert str(corrupt) not in failed.message
    assert "[REDACTED_PATH]" in failed.message
    assert failed.state.interpretation.label_import_count == 0
    assert failed.state.raw.unique_events != ["feet", "left", "right", "tongue"]

    stale = service.execute(ImportLabelsCommand(plan=_plan(stale_id)))
    assert stale.failed is True
    assert stale.diagnostics["code"] == "label_preview_unavailable"
    assert stale.state.interpretation.label_import_count == 0
    assert stale.state.raw.unique_events == failed.state.raw.unique_events


def test_real_a01t_same_size_mutation_invalidates_preview_without_state_pollution(
    tmp_path: Path,
) -> None:
    service = _real_interpreted_service()
    mutable_mat = tmp_path / "A01T-copy.mat"
    shutil.copyfile(MAT_PATH, mutable_mat)
    preview = _preview(service, mutable_mat)
    assert preview.ok is True
    preview_id = preview.diagnostics["label_preview"]["preview_id"]
    before = mutable_mat.stat()
    payload = bytearray(mutable_mat.read_bytes())
    payload[-1] ^= 1
    mutable_mat.write_bytes(payload)
    os.utime(mutable_mat, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert mutable_mat.stat().st_size == before.st_size

    failed = service.execute(ImportLabelsCommand(plan=_plan(preview_id, mutable_mat)))

    assert failed.failed is True
    assert failed.error_type is ErrorType.PRECONDITION
    assert (
        failed.diagnostics["code"] == "interpretation_resource_changed_after_admission"
    )
    assert failed.state.interpretation.label_import_count == 0
    assert failed.state.raw.unique_events != ["feet", "left", "right", "tongue"]

    consumed = service.execute(ImportLabelsCommand(plan=_plan(preview_id, mutable_mat)))
    assert consumed.failed is True
    assert consumed.diagnostics["code"] == "label_preview_unavailable"


def test_middle_only_mutation_is_detected_by_private_full_content_digest(
    tmp_path: Path,
) -> None:
    service = _real_interpreted_service()
    mutable_labels = tmp_path / "middle-mutation.npy"
    np.save(mutable_labels, np.tile(np.array([1, 2, 3, 4]), 3_000))
    initial_stat = mutable_labels.stat()
    stable_mtime_ns = (initial_stat.st_mtime_ns // 1_000_000_000) * 1_000_000_000
    os.utime(
        mutable_labels,
        ns=(stable_mtime_ns, stable_mtime_ns),
    )
    preview = _preview(service, mutable_labels)
    assert preview.ok is True
    preview_id = preview.diagnostics["label_preview"]["preview_id"]
    before_stat = mutable_labels.stat()
    before_payload = mutable_labels.read_bytes()
    mutation_offset = len(before_payload) // 2
    assert mutation_offset > 4_096
    assert mutation_offset < len(before_payload) - 4_096

    with mutable_labels.open("r+b") as handle:
        handle.seek(mutation_offset)
        original = handle.read(1)
        handle.seek(mutation_offset)
        handle.write(bytes([original[0] ^ 1]))
    os.utime(
        mutable_labels,
        ns=(before_stat.st_atime_ns, before_stat.st_mtime_ns),
    )
    after_payload = mutable_labels.read_bytes()
    assert mutable_labels.stat().st_size == before_stat.st_size
    assert mutable_labels.stat().st_mtime_ns == before_stat.st_mtime_ns
    assert after_payload[:4_096] == before_payload[:4_096]
    assert after_payload[-4_096:] == before_payload[-4_096:]

    failed = service.execute(
        ImportLabelsCommand(plan=_plan(preview_id, mutable_labels))
    )

    assert failed.failed is True
    assert failed.error_type is ErrorType.PRECONDITION
    assert (
        failed.diagnostics["code"] == "interpretation_resource_changed_after_admission"
    )
    assert failed.diagnostics["changed_fields"] == ["sha256"]
    assert failed.state.interpretation.label_import_count == 0


def test_public_attach_and_direct_import_commands_share_cardinality_policy(
    tmp_path: Path,
) -> None:
    high_cardinality = tmp_path / "high-cardinality.npy"
    np.save(high_cardinality, np.arange(20_000, dtype=np.int32))

    attach_service = _real_interpreted_service()
    attached = attach_service.execute(
        AttachLabelsCommand(
            mapping={GDF_PATH.name: str(high_cardinality)},
            label_paths=[str(high_cardinality)],
        )
    )
    assert attached.failed is True
    assert attached.error_type is ErrorType.PRECONDITION
    assert attached.diagnostics["code"] == "label_mapping_cardinality_exceeded"
    assert attached.diagnostics["observed_count"] == 257
    assert attached.state.interpretation.label_import_count == 0

    import_service = _real_interpreted_service()
    imported = import_service.execute(
        ImportLabelsCommand(
            plan=LabelImportPlan(
                target_indices=[0],
                label_paths=[str(high_cardinality)],
                file_mapping={str(GDF_PATH): str(high_cardinality)},
                mapping={},
                mode="sequence",
            )
        )
    )
    assert imported.failed is True
    assert imported.error_type is ErrorType.PRECONDITION
    assert imported.diagnostics["code"] == "label_mapping_cardinality_exceeded"
    assert imported.diagnostics["observed_count"] == 257
    assert imported.state.interpretation.label_import_count == 0

    bounded_labels = tmp_path / "bounded-labels.npy"
    np.save(bounded_labels, np.tile(np.array([1, 2, 3, 4]), 72))
    mapping_service = _real_interpreted_service()
    oversized_mapping = mapping_service.execute(
        ImportLabelsCommand(
            plan=LabelImportPlan(
                target_indices=[0],
                label_paths=[str(bounded_labels)],
                file_mapping={str(GDF_PATH): str(bounded_labels)},
                mapping={index: f"class-{index}" for index in range(20_000)},
                mode="sequence",
            )
        )
    )
    assert oversized_mapping.failed is True
    assert oversized_mapping.error_type is ErrorType.PRECONDITION
    assert oversized_mapping.diagnostics["code"] == "label_mapping_cardinality_exceeded"
    assert oversized_mapping.diagnostics["observed_count"] == 257
    assert oversized_mapping.state.interpretation.label_import_count == 0
