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


def test_apply_checkpoint_restores_applied_and_recipe_state() -> None:
    state = _state()
    old_scan = _scan(state.next_id("scan"))
    old_candidate = _candidate(old_scan, state.next_id("candidate"))
    old_applied = _applied(state, old_candidate)
    old_recipe = _recipe(state, old_applied)
    state.record_applied(old_applied)
    state.record_recipe(old_recipe, recipe_path="/tmp/xbrainlab/old-recipe.json")
    checkpoint = state.checkpoint_apply_state()
    new_scan = _scan(state.next_id("scan"))
    new_candidate = _candidate(new_scan, state.next_id("candidate"))
    new_applied = _applied(state, new_candidate)
    state.record_applied(new_applied)

    state.restore_apply_state(checkpoint)

    assert state.resolve_applied_interpretation() is old_applied
    assert state.resolve_recipe(None) is old_recipe
    snapshot = state.snapshot()
    assert snapshot.latest_interpretation_id == old_applied.interpretation_id
    assert snapshot.latest_recipe_id == old_recipe.recipe_id
    assert snapshot.recipe_path == "/tmp/xbrainlab/old-recipe.json"


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
            label_map={carrier: ["left"]},
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
