"""Focused tests for Data Interpretation session state."""

from __future__ import annotations

import inspect
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from XBrainLab.backend.application.commands import LabelImportPlan
from XBrainLab.backend.application.data_interpretation import AppliedInterpretation
from XBrainLab.backend.application.data_interpretation_candidate import (
    InterpretationCandidate,
)
from XBrainLab.backend.application.data_interpretation_pairing import (
    resolve_label_file_pairing,
)
from XBrainLab.backend.application.data_interpretation_public_projection import (
    project_label_carrier_plan,
)
from XBrainLab.backend.application.data_interpretation_recipe import (
    ImportRecipe,
    choices_from_import_recipe,
    load_import_recipe,
)
from XBrainLab.backend.application.data_interpretation_review import (
    InterpretationPreview,
    ValidationDecision,
)
from XBrainLab.backend.application.data_interpretation_scan import ScanResult
from XBrainLab.backend.application.data_interpretation_state import (
    DataInterpretationSessionState,
    StagedInterpretationSessionState,
)


class _LoadedData:
    def __init__(self, filepath: str) -> None:
        self.filepath = filepath


def _data_filepath(data: Any) -> str:
    return str(getattr(data, "filepath", ""))


def _state() -> DataInterpretationSessionState:
    return DataInterpretationSessionState(data_filepath=_data_filepath)


def test_staged_session_state_transfers_once() -> None:
    state = _state()
    staged = StagedInterpretationSessionState(state.checkpoint_session_state())

    assert staged.take().scans == {}
    with pytest.raises(RuntimeError, match="already transferred"):
        staged.take()


def _scan(scan_id: str) -> ScanResult:
    return ScanResult(
        scan_id=scan_id,
        source_path="/tmp/xbrainlab/source",
        source_kind="folder",
        eeg_files=["/tmp/xbrainlab/source/sub-01_raw.fif"],
        label_carriers=["/tmp/xbrainlab/source/events.tsv"],
        format_capabilities=[{"format": "fif", "status": "safe"}],
        warnings=["External label/event carriers require preview before apply."],
    )


def _candidate(scan: ScanResult, candidate_id: str) -> InterpretationCandidate:
    return InterpretationCandidate(
        candidate_id=candidate_id,
        scan_id=scan.scan_id,
        source_path=scan.source_path,
        source_kind=scan.source_kind,
        selected_eeg_files=list(scan.eeg_files),
        label_carriers=list(scan.label_carriers),
        label_carrier_plan=[
            {
                "path": scan.label_carriers[0],
                "selected_label_field": "trial_type",
                "selected_anchor": "onset",
            },
        ],
        event_roles={"label_carrier": "external label or event source"},
        class_map={"left": "left hand"},
        format_capabilities=[{"format": "fif", "status": "safe"}],
        confirmation_items=["Confirm label carrier alignment."],
        recipe_trace=[f"scan:{scan.scan_id}", f"candidate:{candidate_id}"],
    )


def _preview(
    candidate: InterpretationCandidate, preview_id: str
) -> InterpretationPreview:
    return InterpretationPreview(
        preview_id=preview_id,
        candidate_id=candidate.candidate_id,
        summary="Found 1 EEG file(s) and 1 label/event carrier(s).",
        file_count=1,
        label_carrier_count=1,
        label_carrier_preview=[dict(candidate.label_carrier_plan[0])],
        metadata_preview=[{"file": "sub-01_raw.fif"}],
        format_capabilities=[{"format": "fif", "status": "safe"}],
        warnings=list(candidate.warnings),
        confirmation_items=list(candidate.confirmation_items),
        event_roles=dict(candidate.event_roles),
        class_map=dict(candidate.class_map),
    )


def _decision(candidate: InterpretationCandidate) -> ValidationDecision:
    return ValidationDecision(
        candidate_id=candidate.candidate_id,
        decision="needs_confirmation",
        required_confirmations=list(candidate.confirmation_items),
    )


def _applied(
    state: DataInterpretationSessionState,
    candidate: InterpretationCandidate,
) -> AppliedInterpretation:
    return AppliedInterpretation(
        interpretation_id=state.next_id("interpretation"),
        candidate_id=candidate.candidate_id,
        source_path=candidate.source_path,
        source_kind=candidate.source_kind,
        loaded_files=list(candidate.selected_eeg_files),
        label_carriers=list(candidate.label_carriers),
        label_carrier_plan=[dict(item) for item in candidate.label_carrier_plan],
        format_capabilities=[dict(item) for item in candidate.format_capabilities],
        validation_decision="needs_confirmation",
        confirmations=list(candidate.confirmation_items),
        event_roles=dict(candidate.event_roles),
        class_map=dict(candidate.class_map),
        recipe_trace=[*candidate.recipe_trace, "validation:needs_confirmation"],
    )


def _recipe(
    state: DataInterpretationSessionState,
    applied: AppliedInterpretation,
) -> ImportRecipe:
    return ImportRecipe(
        recipe_id=state.next_id("recipe"),
        interpretation_id=applied.interpretation_id,
        source_path=applied.source_path,
        source_kind=applied.source_kind,
        selected_eeg_files=list(applied.loaded_files),
        label_carriers=list(applied.label_carriers),
        label_carrier_plan=[dict(item) for item in applied.label_carrier_plan],
        validation_decision=applied.validation_decision,
        confirmations=list(applied.confirmations),
        event_roles=dict(applied.event_roles),
        class_map=dict(applied.class_map),
    )


def test_session_state_owns_lifecycle_snapshot_and_clear() -> None:
    state = _state()
    scan = _scan(state.next_id("scan"))
    candidate = _candidate(scan, state.next_id("candidate"))
    preview = _preview(candidate, state.next_id("preview"))
    decision = _decision(candidate)
    applied = _applied(state, candidate)
    recipe = _recipe(state, applied)

    state.record_scan(scan)
    state.record_preview(candidate, preview)
    state.record_validation(candidate.candidate_id, decision)
    state.record_applied(applied)
    state.record_recipe(recipe, recipe_path="/tmp/xbrainlab/recipe.json")
    snapshot = state.snapshot()

    assert state.resolve_scan(None) == scan
    assert state.resolve_candidate(None) == candidate
    assert state.resolve_validation_decision(candidate.candidate_id) == decision
    assert state.resolve_applied_interpretation() == applied
    assert state.resolve_recipe(None) == recipe
    assert snapshot.has_scan_result is True
    assert snapshot.has_candidate is True
    assert snapshot.has_preview is True
    assert snapshot.has_validation_decision is True
    assert snapshot.has_applied_interpretation is True
    assert snapshot.has_recipe is True
    assert snapshot.pending_confirmation is False
    assert snapshot.source_kind == "folder"
    assert snapshot.label_carrier_plan == candidate.label_carrier_plan
    assert snapshot.format_capabilities == candidate.format_capabilities
    assert snapshot.event_roles == {"label_carrier": "external label or event source"}
    assert snapshot.class_map == {"left": "left hand"}
    assert snapshot.recipe_path == "/tmp/xbrainlab/recipe.json"

    state.clear()

    cleared = state.snapshot()
    assert cleared.has_scan_result is False
    assert cleared.has_candidate is False
    assert cleared.has_preview is False
    assert cleared.has_validation_decision is False
    assert cleared.has_applied_interpretation is False
    assert cleared.has_recipe is False


def test_legacy_raw_mutation_invalidation_clears_the_whole_lifecycle() -> None:
    state = _state()
    scan = _scan(state.next_id("scan"))
    candidate = _candidate(scan, state.next_id("candidate"))
    applied = _applied(state, candidate)
    state.record_scan(scan)
    state.record_preview(candidate, _preview(candidate, state.next_id("preview")))
    state.record_validation(candidate.candidate_id, _decision(candidate))
    state.record_applied(applied)
    state.record_recipe(_recipe(state, applied), recipe_path="/tmp/recipe.json")

    invalidated = state.invalidate_for_legacy_raw_mutation()

    assert invalidated is True
    assert state.snapshot().epoch_handoff == {}
    assert state.snapshot().has_applied_interpretation is False
    assert state.invalidate_for_legacy_raw_mutation() is False


def test_discard_failed_replacement_restores_previous_applied_interpretation() -> None:
    state = _state()
    old_scan = _scan(state.next_id("scan"))
    old_candidate = _candidate(old_scan, state.next_id("candidate"))
    old_applied = _applied(state, old_candidate)
    new_scan = _scan(state.next_id("scan"))
    new_candidate = _candidate(new_scan, state.next_id("candidate"))
    new_applied = _applied(state, new_candidate)
    state.record_applied(old_applied)
    state.record_applied(new_applied)

    state.discard_applied(new_applied.interpretation_id)

    assert state.resolve_applied_interpretation() is old_applied
    assert state.snapshot().latest_interpretation_id == old_applied.interpretation_id


def test_session_checkpoint_restores_applied_and_recipe_state() -> None:
    state = _state()
    old_scan = _scan(state.next_id("scan"))
    old_candidate = _candidate(old_scan, state.next_id("candidate"))
    old_applied = _applied(state, old_candidate)
    old_recipe = _recipe(state, old_applied)
    state.record_applied(old_applied)
    state.record_recipe(old_recipe, recipe_path="/tmp/xbrainlab/old-recipe.json")
    checkpoint = state.checkpoint_session_state()
    new_scan = _scan(state.next_id("scan"))
    new_candidate = _candidate(new_scan, state.next_id("candidate"))
    new_applied = _applied(state, new_candidate)
    state.record_applied(new_applied)

    state.restore_session_state(checkpoint)

    restored_applied = state.resolve_applied_interpretation()
    restored_recipe = state.resolve_recipe(None)
    assert restored_applied == old_applied
    assert restored_recipe == old_recipe
    assert restored_applied is not old_applied
    assert restored_recipe is not old_recipe
    snapshot = state.snapshot()
    assert snapshot.latest_interpretation_id == old_applied.interpretation_id
    assert snapshot.latest_recipe_id == old_recipe.recipe_id
    assert snapshot.recipe_path == "/tmp/xbrainlab/old-recipe.json"


def test_session_checkpoint_current_guard_tracks_lifecycle_mutations() -> None:
    state = _state()
    checkpoint = state.checkpoint_session_state()

    assert state.session_checkpoint_is_current(checkpoint) is True

    scan = _scan(state.next_id("scan"))
    state.record_scan(scan)

    assert state.session_checkpoint_is_current(checkpoint) is False


def test_session_identity_is_lightweight_and_tracks_same_value_mutation() -> None:
    state = _state()
    scan = _scan(state.next_id("scan"))
    candidate = _candidate(scan, state.next_id("candidate"))
    decision = _decision(candidate)
    state.record_scan(scan)
    state.record_preview(candidate, _preview(candidate, state.next_id("preview")))
    state.record_validation(candidate.candidate_id, decision)
    identity = state.session_identity()

    assert state.session_identity_is_current(identity) is True

    state.record_validation(candidate.candidate_id, decision)

    assert state.session_identity_is_current(identity) is False


def test_empty_legacy_invalidation_keeps_session_checkpoint_current() -> None:
    state = _state()
    checkpoint = state.checkpoint_session_state()

    assert state.invalidate_for_legacy_raw_mutation() is False

    assert state.session_checkpoint_is_current(checkpoint) is True


def test_all_session_mutators_advance_the_lightweight_revision() -> None:
    mutation_methods = (
        "next_id",
        "restore_session_state",
        "stage_session_state",
        "publish_staged_session_state",
        "record_scan",
        "record_preview",
        "record_validation",
        "record_applied",
        "discard_applied",
        "record_recipe",
        "record_recipe_reload",
        "clear",
        "_record_label_import_transaction",
        "_restore_label_import_state",
    )

    for method_name in mutation_methods:
        source = inspect.getsource(getattr(DataInterpretationSessionState, method_name))
        assert "_advance_session_revision" in source, method_name


def test_resolved_nested_state_is_documented_read_only() -> None:
    resolve_methods = (
        "resolve_scan",
        "resolve_candidate",
        "resolve_validation_decision",
        "resolve_applied_interpretation",
        "resolve_recipe",
    )

    for method_name in resolve_methods:
        doc = inspect.getdoc(getattr(DataInterpretationSessionState, method_name))
        assert doc is not None
        assert "read-only" in doc
        assert "session mutators" in doc


def test_restored_session_checkpoint_keeps_nested_values_isolated() -> None:
    source = _state()
    scan = _scan(source.next_id("scan"))
    candidate = _candidate(scan, source.next_id("candidate"))
    preview = _preview(candidate, source.next_id("preview"))
    source.record_scan(scan)
    source.record_preview(candidate, preview)
    checkpoint = source.checkpoint_session_state()
    restored = _state()

    restored.restore_session_state(checkpoint)
    checkpoint.previews[preview.preview_id].metadata_preview.append(
        {"file": "mutated-after-restore.fif"}
    )

    assert restored.snapshot().metadata_preview == [{"file": "sub-01_raw.fif"}]


def test_staged_session_checkpoint_no_longer_describes_detached_owner() -> None:
    state = _state()
    scan = _scan(state.next_id("scan"))
    state.record_scan(scan)

    staged = state.stage_session_state()

    assert staged.scans == {scan.scan_id: scan}
    assert state.snapshot().has_scan_result is False
    assert state.session_checkpoint_is_current(staged) is False


def test_new_label_import_does_not_mutate_previous_recipe() -> None:
    state = _state()
    old_scan = _scan(state.next_id("scan"))
    old_candidate = _candidate(old_scan, state.next_id("candidate"))
    old_applied = _applied(state, old_candidate)
    old_recipe = _recipe(state, old_applied)
    state.record_applied(old_applied)
    state.record_recipe(old_recipe, recipe_path="/tmp/xbrainlab/old-recipe.json")
    new_scan = _scan(state.next_id("scan"))
    new_candidate = _candidate(new_scan, state.next_id("candidate"))
    state.record_applied(_applied(state, new_candidate))
    target = _LoadedData(new_candidate.selected_eeg_files[0])
    carrier = new_candidate.label_carriers[0]

    state.record_label_import_for_recipe(
        plan=LabelImportPlan(
            target_indices=[0],
            label_paths=[carrier],
            mapping={"left": "left hand"},
            file_mapping={target.filepath: carrier},
            mode="sequence",
        ),
        mode="sequence",
        target_files=[target],
        file_mapping={target.filepath: carrier},
        selected_event_names={"768"},
        success_count=1,
    )

    assert state.resolve_recipe(None) is old_recipe
    assert state.resolve_recipe(None).label_imports == []


def test_snapshot_uses_latest_review_state_before_previous_applied_truth() -> None:
    state = _state()
    old_scan = _scan(state.next_id("scan"))
    old_candidate = _candidate(old_scan, state.next_id("candidate"))
    state.record_scan(old_scan)
    state.record_preview(
        old_candidate, _preview(old_candidate, state.next_id("preview"))
    )
    state.record_validation(old_candidate.candidate_id, _decision(old_candidate))
    state.record_applied(_applied(state, old_candidate))
    new_scan = ScanResult(
        scan_id=state.next_id("scan"),
        source_path="/tmp/xbrainlab/new_source",
        source_kind="folder",
        eeg_files=["/tmp/xbrainlab/new_source/sub-02_raw.fif"],
        label_sources=["/tmp/xbrainlab/new_labels"],
        label_carriers=["/tmp/xbrainlab/new_labels/sub-02_events.tsv"],
        format_capabilities=[{"format": "EDF", "status": "safe"}],
    )

    state.record_scan(new_scan)
    snapshot = state.snapshot()

    assert snapshot.has_applied_interpretation is True
    assert snapshot.has_candidate is False
    assert snapshot.source_path == "/tmp/xbrainlab/new_source"
    assert snapshot.label_sources == ["/tmp/xbrainlab/new_labels"]
    assert snapshot.label_carriers == ["/tmp/xbrainlab/new_labels/sub-02_events.tsv"]
    assert snapshot.label_carrier_plan == []
    assert snapshot.format_capabilities == [{"format": "EDF", "status": "safe"}]
    assert snapshot.event_roles == {}
    assert snapshot.class_map == {}


def test_label_import_record_updates_applied_and_recipe_state() -> None:
    state = _state()
    scan = _scan(state.next_id("scan"))
    candidate = _candidate(scan, state.next_id("candidate"))
    state.record_scan(scan)
    state.record_preview(candidate, _preview(candidate, state.next_id("preview")))
    applied = _applied(state, candidate)
    recipe = _recipe(state, applied)
    state.record_applied(applied)
    state.record_recipe(recipe, recipe_path=None)
    plan = LabelImportPlan(
        target_indices=[0],
        label_paths=["/tmp/xbrainlab/source/events.tsv"],
        mapping={"left": "left hand"},
        file_mapping={
            "/tmp/xbrainlab/source/sub-01_raw.fif": (
                "/tmp/xbrainlab/source/events.tsv"
            ),
        },
        mode="timestamp",
    )

    record = state.record_label_import_for_recipe(
        plan=plan,
        mode="timestamp",
        target_files=[_LoadedData("/tmp/xbrainlab/source/sub-01_raw.fif")],
        file_mapping={
            "/tmp/xbrainlab/source/sub-01_raw.fif": (
                "/tmp/xbrainlab/source/events.tsv"
            ),
        },
        selected_event_names={"left"},
        success_count=1,
    )
    snapshot = state.snapshot()
    latest_recipe = state.resolve_recipe(None)

    assert record is not None
    assert record["mode"] == "timestamp"
    assert record["success_count"] == 1
    assert record["selected_event_names"] == ["left"]
    assert snapshot.label_import_count == 1
    assert snapshot.label_imports == [record]
    assert latest_recipe.label_imports == [record]
    assert latest_recipe.recipe_trace[-1] == "label_import:timestamp:1"


def test_external_label_import_supersedes_a_saved_skip_labels_decision(
    tmp_path: Path,
) -> None:
    state = _state()
    scan = _scan(state.next_id("scan"))
    candidate = _candidate(scan, state.next_id("candidate"))
    applied = replace(
        _applied(state, candidate),
        skip_labels=True,
        label_carriers=[],
        label_carrier_plan=[],
    )
    recipe = replace(
        _recipe(state, applied),
        skip_labels=True,
        label_carriers=[],
        label_carrier_plan=[],
    )
    state.record_applied(applied)
    state.record_recipe(recipe, recipe_path=None)
    source_path = tmp_path / "source"
    label_path = str((source_path / "external-labels.tsv").resolve())
    target_path = str((source_path / "sub-01_raw.fif").resolve())

    record = state.record_label_import_for_recipe(
        plan=LabelImportPlan(
            target_indices=[0],
            label_paths=[label_path],
            label_configs={
                label_path: {
                    "label_field": "trial_type",
                    "anchor": "onset",
                    "duration_field": "duration",
                }
            },
            mapping={1: "left hand", 2: "right hand"},
            file_mapping={
                target_path: label_path,
            },
            mode="sequence",
        ),
        mode="sequence",
        target_files=[_LoadedData(target_path)],
        file_mapping={
            target_path: label_path,
        },
        selected_event_names=None,
        success_count=1,
    )

    assert record is not None
    assert record["label_configs"] == {
        label_path: {
            "label_field": "trial_type",
            "anchor": "onset",
            "duration_field": "duration",
        }
    }
    updated_applied = state.resolve_applied_interpretation()
    assert updated_applied.skip_labels is False
    assert updated_applied.label_sources == [label_path]
    assert updated_applied.label_carriers == [label_path]
    assert updated_applied.class_map == {"1": "left hand", "2": "right hand"}
    assert updated_applied.confirmations == applied.confirmations
    [applied_carrier] = updated_applied.label_carrier_plan
    assert applied_carrier["path"] == label_path
    assert applied_carrier["selected_label_field"] == "trial_type"
    assert applied_carrier["selected_anchor"] == "onset"
    assert applied_carrier["selected_duration_field"] == "duration"
    assert applied_carrier["selected_target_file"] == target_path

    updated_recipe = state.resolve_recipe(None)
    assert updated_recipe.skip_labels is False
    assert updated_recipe.label_sources == [label_path]
    assert updated_recipe.label_carriers == [label_path]
    assert updated_recipe.validation_decision == updated_applied.validation_decision
    assert updated_recipe.confirmations == updated_applied.confirmations
    assert updated_recipe.label_imports == [record]
    choices = choices_from_import_recipe(updated_recipe)
    assert choices["label_sources"] == [label_path]
    assert choices["required_label_carriers"] == [label_path]
    carrier_choices = choices["label_carrier_choices"][label_path]
    assert carrier_choices["label_field"] == "trial_type"
    assert carrier_choices["anchor"] == "onset"
    assert carrier_choices["duration_field"] == "duration"
    assert carrier_choices["target_file"] == target_path
    assert {
        raw_value: decision["class_name"]
        for raw_value, decision in carrier_choices["value_decisions"].items()
    } == {"1": "left hand", "2": "right hand"}


def test_post_load_state_keeps_unproven_placement_blocked_across_projections() -> None:
    state = _state()
    scan = _scan(state.next_id("scan"))
    candidate = replace(
        _candidate(scan, state.next_id("candidate")),
        label_sources=[],
        label_carriers=[],
        label_carrier_plan=[],
        class_map={},
        internal_event_preview={},
        confirmation_items=[],
        choices={"skip_labels": True},
    )
    preview = InterpretationPreview(
        preview_id=state.next_id("preview"),
        candidate_id=candidate.candidate_id,
        summary="Labels skipped.",
        file_count=1,
        label_carrier_count=0,
    )
    applied = replace(
        _applied(state, candidate),
        skip_labels=True,
        label_carriers=[],
        label_carrier_plan=[],
        confirmations=[],
    )
    recipe = replace(
        _recipe(state, applied),
        skip_labels=True,
        label_carriers=[],
        label_carrier_plan=[],
        confirmations=[],
    )
    state.record_scan(scan)
    state.record_preview(candidate, preview)
    state.record_validation(
        candidate.candidate_id,
        ValidationDecision(candidate_id=candidate.candidate_id, decision="safe"),
    )
    state.record_applied(applied)
    state.record_recipe(recipe, recipe_path=None)
    target_path = candidate.selected_eeg_files[0]
    label_path = "/tmp/xbrainlab/source/external-labels.tsv"

    state.record_label_import_for_recipe(
        plan=LabelImportPlan(
            target_indices=[0],
            label_paths=[label_path],
            label_configs={label_path: {"label_field": "trial_type"}},
            mapping={1: "left", 2: "right"},
            file_mapping={target_path: label_path},
            selected_event_names=["769", "770"],
            mode="sequence",
        ),
        mode="sequence",
        target_files=[_LoadedData(target_path)],
        file_mapping={target_path: label_path},
        selected_event_names={"769", "770"},
        success_count=1,
    )

    updated_candidate = state.resolve_candidate(candidate.candidate_id)
    updated_preview = state.current_review()["preview"]
    updated_decision = state.resolve_validation_decision(candidate.candidate_id)
    updated_applied = state.resolve_applied_interpretation()
    updated_recipe = state.resolve_recipe(None)
    [carrier] = updated_candidate.label_carrier_plan
    assert carrier["placement_review"]["status"] == "blocked"
    assert updated_preview["label_carrier_preview"] == project_label_carrier_plan(
        updated_candidate.label_carrier_plan
    )
    assert updated_decision is not None
    assert updated_decision.decision == "blocked"
    assert set(updated_candidate.blocked_reasons).issubset(
        updated_decision.blocked_reasons
    )
    assert updated_applied.label_carrier_plan == updated_candidate.label_carrier_plan
    assert updated_applied.validation_decision == "blocked"
    assert updated_recipe.label_carrier_plan == updated_candidate.label_carrier_plan
    assert updated_recipe.validation_decision == "blocked"


def test_post_load_anchor_preserves_explicit_cue_onset_and_only_defaults_when_omitted() -> (
    None
):
    target_path = "/tmp/xbrainlab/source/sub-01_raw.fif"
    label_path = "/tmp/xbrainlab/source/external-labels.mat"

    explicit = DataInterpretationSessionState._label_import_carrier_plan(
        label_carriers=[label_path],
        label_configs={
            label_path: {
                "label_field": "classlabel",
                "anchor": "cue_onset",
            }
        },
        file_mapping={target_path: label_path},
        class_map={"1": "left", "2": "right"},
        mode="sequence",
        selected_event_names=None,
        target_files=[_LoadedData(target_path)],
    )
    omitted = DataInterpretationSessionState._label_import_carrier_plan(
        label_carriers=[label_path],
        label_configs={label_path: {"label_field": "classlabel"}},
        file_mapping={target_path: label_path},
        class_map={"1": "left", "2": "right"},
        mode="sequence",
        selected_event_names=None,
        target_files=[_LoadedData(target_path)],
    )

    assert explicit[0]["selected_anchor"] == "cue_onset"
    assert omitted[0]["selected_anchor"] == "trial order"
    merged = DataInterpretationSessionState._merge_label_carrier_plans(
        [{"path": label_path, "selected_anchor": "cue_onset"}],
        omitted,
    )
    assert merged[0]["selected_anchor"] == "cue_onset"


def test_label_import_carrier_plan_indexes_85_alias_aware_targets_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_root = tmp_path / "eeg"
    label_root = tmp_path / "labels"
    alias_root = tmp_path / "aliases"
    eeg_root.mkdir()
    label_root.mkdir()
    alias_root.mkdir()
    target_paths: list[str] = []
    label_paths: list[str] = []
    for index in range(85):
        target_path = eeg_root / f"sub-{index:02d}_eeg.edf"
        label_path = label_root / f"sub-{index:02d}_events.tsv"
        target_path.touch()
        label_path.touch()
        target_paths.append(str(target_path))
        label_paths.append(str(label_path))
    alias_path = alias_root / ".." / "labels" / "sub-00_events.tsv"
    file_mapping = {
        target_path: str(alias_path) if index == 0 else label_paths[index]
        for index, target_path in enumerate(target_paths)
    }
    real_label_path_key = DataInterpretationSessionState._label_path_key
    observed_path_key_calls = 0

    def observed_label_path_key(path: Any) -> str:
        nonlocal observed_path_key_calls
        observed_path_key_calls += 1
        return real_label_path_key(path)

    monkeypatch.setattr(
        DataInterpretationSessionState,
        "_label_path_key",
        staticmethod(observed_label_path_key),
    )

    carrier_plan = DataInterpretationSessionState._label_import_carrier_plan(
        label_carriers=label_paths,
        label_configs={path: {"label_field": "trial_type"} for path in label_paths},
        file_mapping=file_mapping,
        class_map={"left": "left"},
        mode="timestamp",
        selected_event_names=None,
        target_files=[_LoadedData(path) for path in target_paths],
    )

    assert len(carrier_plan) == 85
    assert [row["selected_target_files"] for row in carrier_plan] == [
        [target_path] for target_path in target_paths
    ]
    assert carrier_plan[0]["selected_target_file"] == target_paths[0]
    assert observed_path_key_calls < 600


def test_external_label_recipe_round_trip_preserves_multi_target_pairing_and_events(
    tmp_path: Path,
) -> None:
    state = _state()
    source_path = tmp_path / "source"
    shared_labels = str((source_path / "shared.mat").resolve())
    target_paths = [
        str((source_path / "sub01.gdf").resolve()),
        str((source_path / "sub02.gdf").resolve()),
    ]
    scan = replace(
        _scan(state.next_id("scan")),
        eeg_files=target_paths,
        label_carriers=[shared_labels],
    )
    candidate = replace(
        _candidate(scan, state.next_id("candidate")),
        selected_eeg_files=target_paths,
        label_carriers=[shared_labels],
        label_carrier_plan=[
            {
                "path": shared_labels,
                "selected_label_field": "classlabel",
            }
        ],
    )
    applied = _applied(state, candidate)
    state.record_applied(applied)
    state.record_recipe(_recipe(state, applied), recipe_path=None)
    file_mapping = dict.fromkeys(target_paths, shared_labels)

    record = state.record_label_import_for_recipe(
        plan=LabelImportPlan(
            target_indices=[0, 1],
            label_paths=[shared_labels],
            label_configs={
                shared_labels: {
                    "label_field": "classlabel",
                    "sequence_only": True,
                }
            },
            mapping={1: "left", 2: "right"},
            file_mapping=file_mapping,
            selected_event_names=["769", "770"],
            mode="sequence",
        ),
        mode="sequence",
        target_files=[_LoadedData(path) for path in target_paths],
        file_mapping=file_mapping,
        selected_event_names={"769", "770"},
        success_count=2,
    )

    assert record is not None
    assert record["file_mapping"] == file_mapping
    assert record["selected_event_names"] == ["769", "770"]
    recipe = state.resolve_recipe(None)
    recipe_path = tmp_path / "multi-target-recipe.json"
    recipe.write_json(str(recipe_path))
    reloaded = load_import_recipe(str(recipe_path))

    assert choices_from_import_recipe(reloaded) == choices_from_import_recipe(recipe)
    [carrier] = reloaded.label_carrier_plan
    assert carrier["selected_target_files"] == target_paths
    assert carrier["selected_target_event_codes"] == ["769", "770"]
    carrier_choices = choices_from_import_recipe(reloaded)["label_carrier_choices"][
        shared_labels
    ]
    assert carrier_choices["target_files"] == target_paths
    assert carrier_choices["target_event_codes"] == ["769", "770"]
    pairing = resolve_label_file_pairing(
        reloaded.label_carrier_plan,
        target_paths,
    )
    assert pairing.complete is True
    assert pairing.file_mapping == file_mapping

    audit_only_recipe = replace(
        reloaded,
        label_carrier_plan=[
            {
                "path": shared_labels,
                "selected_label_field": "",
                "selected_target_file": "",
            }
        ],
    )
    audit_choices = choices_from_import_recipe(audit_only_recipe)[
        "label_carrier_choices"
    ][shared_labels]
    assert audit_choices["label_field"] == "classlabel"
    assert audit_choices["target_files"] == target_paths
    assert audit_choices["target_event_codes"] == ["769", "770"]


def test_partial_label_import_count_cannot_update_recipe_truth() -> None:
    state = _state()
    scan = _scan(state.next_id("scan"))
    candidate = _candidate(scan, state.next_id("candidate"))
    applied = _applied(state, candidate)
    recipe = _recipe(state, applied)
    state.record_applied(applied)
    state.record_recipe(recipe, recipe_path=None)
    targets = [
        _LoadedData("/tmp/xbrainlab/source/sub-01_raw.fif"),
        _LoadedData("/tmp/xbrainlab/source/sub-02_raw.fif"),
    ]

    record = state.record_label_import_for_recipe(
        plan=LabelImportPlan(
            label_paths=["/tmp/xbrainlab/source/events.tsv"],
            mapping={"left": "left hand", "right": "right hand"},
            mode="sequence",
        ),
        mode="sequence",
        target_files=targets,
        file_mapping={
            target.filepath: "/tmp/xbrainlab/source/events.tsv" for target in targets
        },
        selected_event_names=None,
        success_count=1,
    )

    assert record is None
    assert state.snapshot().label_import_count == 0
    assert state.resolve_recipe(None).label_imports == []


def test_internal_event_epoch_handoff_keeps_raw_event_codes_with_aliases() -> None:
    state = _state()
    scan = ScanResult(
        scan_id=state.next_id("scan"),
        source_path="/tmp/xbrainlab/source",
        source_kind="file",
        eeg_files=["/tmp/xbrainlab/source/A01T.gdf"],
        label_carriers=[],
    )
    candidate = InterpretationCandidate(
        candidate_id=state.next_id("candidate"),
        scan_id=scan.scan_id,
        source_path=scan.source_path,
        source_kind=scan.source_kind,
        selected_eeg_files=list(scan.eeg_files),
        event_roles={"internal_events": "event role candidates"},
        class_map={
            "769": "Left hand",
            "770": "Right hand",
            "771": "Feet",
        },
        internal_event_selection={
            "label_event_codes": ["770", "769", "771"],
            "class_map": {
                "769": "Left hand",
                "770": "Right hand",
                "771": "Feet",
            },
        },
        choices={"label_carrier": "embedded_events"},
    )
    applied = AppliedInterpretation(
        interpretation_id=state.next_id("interpretation"),
        candidate_id=candidate.candidate_id,
        source_path=candidate.source_path,
        source_kind=candidate.source_kind,
        loaded_files=list(candidate.selected_eeg_files),
        validation_decision="safe",
        event_roles=dict(candidate.event_roles),
        class_map=dict(candidate.class_map),
        internal_event_selection=dict(candidate.internal_event_selection),
    )

    state.record_scan(scan)
    state.record_preview(
        candidate,
        InterpretationPreview(
            preview_id=state.next_id("preview"),
            candidate_id=candidate.candidate_id,
            summary="Found 1 EEG file(s).",
            file_count=1,
            label_carrier_count=0,
            event_roles=dict(candidate.event_roles),
            class_map=dict(candidate.class_map),
        ),
    )
    state.record_applied(applied)
    handoff = state.snapshot().epoch_handoff

    assert handoff["label_source"] == "internal_events"
    assert handoff["default_epoch_events"] == ["769", "770", "771"]
    assert handoff["event_label_aliases"] == {
        "769": "Left hand",
        "770": "Right hand",
        "771": "Feet",
    }
    assert handoff["epoch_targets"] == [
        {"event": "769", "source": "internal_events", "label": "Left hand"},
        {"event": "770", "source": "internal_events", "label": "Right hand"},
        {"event": "771", "source": "internal_events", "label": "Feet"},
    ]


def test_pending_recipe_review_does_not_replace_active_epoch_handoff() -> None:
    """A pending review must not rewrite truth for already-loaded EEG data."""
    state = _state()
    active_scan = ScanResult(
        scan_id=state.next_id("scan"),
        source_path="/tmp/xbrainlab/active",
        source_kind="file",
        eeg_files=["/tmp/xbrainlab/active/A01T.gdf"],
    )
    active_candidate = InterpretationCandidate(
        candidate_id=state.next_id("candidate"),
        scan_id=active_scan.scan_id,
        source_path=active_scan.source_path,
        source_kind=active_scan.source_kind,
        selected_eeg_files=list(active_scan.eeg_files),
        class_map={"769": "Left hand", "770": "Right hand"},
        internal_event_selection={
            "label_event_codes": ["769", "770"],
            "class_map": {"769": "Left hand", "770": "Right hand"},
        },
        choices={"label_carrier": "embedded_events"},
    )
    active_preview = InterpretationPreview(
        preview_id=state.next_id("preview"),
        candidate_id=active_candidate.candidate_id,
        summary="Active import",
        file_count=1,
        label_carrier_count=0,
        class_map=dict(active_candidate.class_map),
    )
    active_applied = AppliedInterpretation(
        interpretation_id=state.next_id("interpretation"),
        candidate_id=active_candidate.candidate_id,
        source_path=active_candidate.source_path,
        source_kind=active_candidate.source_kind,
        loaded_files=list(active_candidate.selected_eeg_files),
        validation_decision="safe",
        class_map=dict(active_candidate.class_map),
        internal_event_selection=dict(active_candidate.internal_event_selection),
    )
    state.record_scan(active_scan)
    state.record_preview(active_candidate, active_preview)
    state.record_applied(active_applied)

    pending_scan = _scan(state.next_id("scan"))
    pending_candidate = _candidate(
        pending_scan,
        state.next_id("candidate"),
    )
    pending_preview = _preview(
        pending_candidate,
        state.next_id("preview"),
    )
    state.record_recipe_reload(
        recipe=_recipe(state, active_applied),
        scan=pending_scan,
        candidate=pending_candidate,
        preview=pending_preview,
        decision=_decision(pending_candidate),
        recipe_path="/tmp/xbrainlab/pending.recipe.json",
    )

    snapshot = state.snapshot()

    assert snapshot.pending_confirmation is True
    assert snapshot.latest_candidate_id == pending_candidate.candidate_id
    assert snapshot.has_applied_interpretation is True
    assert snapshot.epoch_handoff["source"] == "applied_interpretation"
    assert snapshot.epoch_handoff["ready"] is True
    assert snapshot.epoch_handoff["supervised_ready"] is True
    assert snapshot.epoch_handoff["default_epoch_events"] == ["769", "770"]


def test_internal_event_handoff_requires_two_distinct_selected_classes() -> None:
    applied = AppliedInterpretation(
        interpretation_id="interpretation-one-class",
        candidate_id="candidate-one-class",
        source_path="/tmp/xbrainlab/source",
        source_kind="file",
        loaded_files=["/tmp/xbrainlab/source/run.gdf"],
        label_carrier="embedded_events",
        class_map={"769": "Left hand"},
        internal_event_selection={
            "label_event_codes": ["769"],
            "class_map": {"769": "Left hand"},
        },
    )

    handoff = DataInterpretationSessionState._epoch_handoff(None, applied)

    assert handoff["supervised_ready"] is False
    assert handoff["supervised_blocker_codes"] == ["insufficient_usable_classes"]


def test_internal_event_handoff_requires_trials_for_each_selected_class() -> None:
    applied = AppliedInterpretation(
        interpretation_id="interpretation-one-usable-class",
        candidate_id="candidate-one-usable-class",
        source_path="/tmp/xbrainlab/source",
        source_kind="file",
        loaded_files=["/tmp/xbrainlab/source/run.gdf"],
        label_carrier="embedded_events",
        class_map={"769": "Left hand", "770": "Right hand"},
        internal_event_selection={
            "label_event_codes": ["769", "770"],
            "label_event_counts": {"769": 12, "770": 0},
            "class_map": {"769": "Left hand", "770": "Right hand"},
        },
    )

    handoff = DataInterpretationSessionState._epoch_handoff(None, applied)

    assert handoff["usable_class_labels"] == ["Left hand"]
    assert handoff["supervised_ready"] is False
    assert handoff["supervised_blocker_codes"] == ["insufficient_usable_classes"]


def test_epoch_handoff_compacts_bids_event_evidence() -> None:
    event_rows = [
        {"row": index, "onset": float(index), "value": str(index % 2)}
        for index in range(50)
    ]
    applied = AppliedInterpretation(
        interpretation_id="interpretation-bids",
        candidate_id="candidate-bids",
        source_path="/tmp/xbrainlab/bids",
        source_kind="bids",
        loaded_files=["/tmp/xbrainlab/bids/sub-01_task-test_eeg.set"],
        bids={
            "is_bids": True,
            "event_validation": {
                "runs": [
                    {
                        "file": "/tmp/xbrainlab/bids/sub-01_task-test_eeg.set",
                        "row_evidence": event_rows,
                    }
                ]
            },
        },
    )

    handoff = DataInterpretationSessionState._epoch_handoff(None, applied)

    [run] = handoff["bids"]["event_validation"]["runs"]
    assert "row_evidence" not in run
    assert run["row_evidence_count"] == len(event_rows)
