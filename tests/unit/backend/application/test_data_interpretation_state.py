"""Focused tests for Data Interpretation session state."""

from __future__ import annotations

from typing import Any

from XBrainLab.backend.application.commands import LabelImportPlan
from XBrainLab.backend.application.data_interpretation import AppliedInterpretation
from XBrainLab.backend.application.data_interpretation_candidate import (
    InterpretationCandidate,
)
from XBrainLab.backend.application.data_interpretation_recipe import ImportRecipe
from XBrainLab.backend.application.data_interpretation_review import (
    InterpretationPreview,
    ValidationDecision,
)
from XBrainLab.backend.application.data_interpretation_scan import ScanResult
from XBrainLab.backend.application.data_interpretation_state import (
    DataInterpretationSessionState,
)


class _LoadedData:
    def __init__(self, filepath: str) -> None:
        self.filepath = filepath


def _data_filepath(data: Any) -> str:
    return str(getattr(data, "filepath", ""))


def _state() -> DataInterpretationSessionState:
    return DataInterpretationSessionState(data_filepath=_data_filepath)


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
    assert snapshot.pending_confirmation is True
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
        label_map={"/tmp/xbrainlab/source/events.tsv": [{"label": "left"}]},
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
