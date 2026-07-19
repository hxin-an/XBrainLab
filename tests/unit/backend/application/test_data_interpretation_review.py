from types import SimpleNamespace

import pytest

from XBrainLab.backend.application.data_interpretation_candidate import (
    InterpretationCandidate,
)
from XBrainLab.backend.application.data_interpretation_metadata import (
    FileMetadataResolution,
    MetadataFieldResolution,
)
from XBrainLab.backend.application.data_interpretation_review import (
    InterpretationPreview,
    ValidationDecision,
    build_interpretation_preview,
    target_step_for_interpretation_text,
    validate_interpretation_candidate,
)


def _field(name: str, value: str | None = None) -> MetadataFieldResolution:
    return MetadataFieldResolution(
        field=name,
        value=value,
        source="test",
        decision="safe" if value else "needs_confirmation",
        reason="test",
    )


def _candidate(**overrides):
    data = {
        "candidate_id": "candidate-1",
        "source_kind": "file",
        "selected_eeg_files": ["/data/sub-01.fif"],
        "label_sources": [],
        "label_carriers": ["/data/events.tsv"],
        "label_carrier_plan": [{"name": "events.tsv"}],
        "metadata": [
            FileMetadataResolution(
                file="/data/sub-01.fif",
                subject=_field("subject", "01"),
                session=_field("session", "01"),
                task=_field("task", "mi"),
                run=_field("run", "1"),
            )
        ],
        "format_capabilities": [{"format": "MNE FIF"}],
        "warnings": ["Review labels."],
        "confirmation_items": ["Confirm label carrier."],
        "blocked_reasons": [],
        "event_roles": {"trial_type": "class cue"},
        "class_map": {"left": "0"},
        "internal_event_preview": {
            "candidate_label_events": [
                {
                    "event_code": "769",
                    "use_as": "Class label",
                    "event_count": 72,
                    "coverage": "1/1 files",
                    "evidence": "Known GDF class event code",
                }
            ],
            "not_used_events": [
                {
                    "event_code": "768",
                    "use_as": "Trial timing",
                    "reason": "Trial start marker",
                    "coverage": "1/1 files",
                }
            ],
        },
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_build_interpretation_preview_serializes_review_payload():
    preview = build_interpretation_preview(
        preview_id="preview-1",
        candidate=_candidate(),
    )

    assert isinstance(preview, InterpretationPreview)
    assert preview.file_count == 1
    assert preview.label_carrier_count == 1
    assert preview.source_selection == "Single file"
    assert preview.metadata_preview[0]["file"] == "sub-01.fif"
    assert preview.metadata_preview[0]["subject"]["value"] == "01"
    assert preview.event_roles == {"trial_type": "class cue"}
    assert (
        preview.internal_event_preview["candidate_label_events"][0]["event_code"]
        == "769"
    )
    assert preview.action_items
    assert {
        "issue": "Review labels.",
        "impact": "Import may still be usable, but downstream labels or metadata may need review.",
        "next_action": "Open the target step and resolve or confirm this item before import.",
        "target_step": "Match Labels",
        "severity": "warning",
    } in preview.action_items


def test_build_interpretation_preview_describes_selected_file_scope():
    preview = build_interpretation_preview(
        preview_id="preview-1",
        candidate=_candidate(
            source_kind="folder",
            selected_eeg_files=[
                "/data/A01T.gdf",
                "/data/A02T.gdf",
                "/data/A03T.gdf",
            ],
            choices={
                "selected_eeg_files": [
                    "/data/A01T.gdf",
                    "/data/A02T.gdf",
                    "/data/A03T.gdf",
                ],
            },
        ),
    )

    assert preview.file_count == 3
    assert preview.source_selection == "3 selected file(s)"
    assert preview.selected_eeg_files == [
        "/data/A01T.gdf",
        "/data/A02T.gdf",
        "/data/A03T.gdf",
    ]


def test_build_interpretation_preview_summarizes_recipe_reload_diff():
    recipe = SimpleNamespace(
        recipe_id="recipe-1",
        source_path="/data",
        selected_eeg_files=["/data/sub-01.fif", "/data/missing.fif"],
        label_carriers=["/data/old_events.tsv"],
        metadata=[],
        event_roles={"trial_type": "class cue"},
        class_map={"1": "left"},
        content_identity={"scope_sha256": "saved-content"},
    )
    scan = SimpleNamespace(
        source_path="/data",
        eeg_files=["/data/sub-01.fif", "/data/sub-02.fif"],
        label_carriers=["/data/events.tsv"],
    )

    preview = build_interpretation_preview(
        preview_id="preview-1",
        candidate=_candidate(
            selected_eeg_files=["/data/sub-01.fif", "/data/missing.fif"],
            label_carriers=["/data/events.tsv"],
            content_identity={"scope_sha256": "current-content"},
            choices={
                "recipe_id": "recipe-1",
                "selected_eeg_files": ["/data/sub-01.fif", "/data/missing.fif"],
                "event_roles": {"trial_type": "class cue"},
                "class_map": {"1": "left"},
            },
        ),
        recipe=recipe,
        scan=scan,
    )

    summary = preview.recipe_reload_summary

    assert summary["status"] == "needs_review"
    assert summary["recipe_id"] == "recipe-1"
    assert {
        "item": "EEG files",
        "status": "Changed",
        "detail": (
            "Matched 1 saved file(s). Missing from scan: missing.fif. "
            "New in scan: sub-02.fif."
        ),
    } in summary["diff_rows"]
    assert {
        "item": "Label carriers",
        "status": "Changed",
        "detail": (
            "Matched 0 saved carrier(s). Missing from scan: old_events.tsv. "
            "New in scan: events.tsv."
        ),
    } in summary["diff_rows"]
    assert summary["label_carrier_remap_options"] == [
        {
            "saved": "/data/old_events.tsv",
            "saved_name": "old_events.tsv",
            "candidates": [
                {"path": "/data/events.tsv", "name": "events.tsv"},
            ],
        }
    ]
    assert summary["eeg_file_remap_options"] == [
        {
            "saved": "/data/missing.fif",
            "saved_name": "missing.fif",
            "candidates": [
                {"path": "/data/sub-01.fif", "name": "sub-01.fif"},
                {"path": "/data/sub-02.fif", "name": "sub-02.fif"},
            ],
        }
    ]
    assert {
        "item": "Reviewed label content",
        "status": "Changed",
        "detail": "Label/event carrier content changed and requires review.",
    } in summary["diff_rows"]


def test_recipe_reload_duplicate_basename_preserves_full_identity_and_remap_options():
    saved = "/recipe/old/run_raw.fif"
    current = ["/scan/site-a/run_raw.fif", "/scan/site-b/run_raw.fif"]
    recipe = SimpleNamespace(
        recipe_id="recipe-1",
        selected_eeg_files=[saved],
        label_carriers=[],
        content_identity={},
    )
    scan = SimpleNamespace(
        eeg_files=current,
        label_carriers=[],
    )

    preview = build_interpretation_preview(
        preview_id="preview-ambiguous",
        candidate=_candidate(
            selected_eeg_files=[saved],
            label_carriers=[],
            blocked_reasons=[
                "Selected EEG file run_raw.fif is ambiguous in the current scan."
            ],
            choices={
                "recipe_id": "recipe-1",
                "selected_eeg_files": [saved],
            },
        ),
        recipe=recipe,
        scan=scan,
    )

    summary = preview.recipe_reload_summary
    eeg_row = next(row for row in summary["diff_rows"] if row["item"] == "EEG files")
    assert summary["status"] == "needs_review"
    assert eeg_row["status"] == "Changed"
    assert saved in eeg_row["detail"]
    assert current[0] in eeg_row["detail"]
    assert current[1] in eeg_row["detail"]
    assert summary["eeg_file_remap_options"] == [
        {
            "saved": saved,
            "saved_name": "run_raw.fif",
            "candidates": [
                {"path": current[0], "name": "run_raw.fif"},
                {"path": current[1], "name": "run_raw.fif"},
            ],
        }
    ]


def test_validate_interpretation_candidate_needs_confirmation_and_blocked():
    needs_confirmation = validate_interpretation_candidate(_candidate())
    blocked = validate_interpretation_candidate(
        _candidate(
            confirmation_items=[],
            blocked_reasons=["XDF / LSL stream selection is not available."],
        )
    )
    safe = validate_interpretation_candidate(
        _candidate(confirmation_items=[], warnings=[])
    )

    assert isinstance(needs_confirmation, ValidationDecision)
    assert needs_confirmation.decision == "needs_confirmation"
    assert blocked.decision == "blocked"
    assert blocked.blocked_reasons == ["XDF / LSL stream selection is not available."]
    assert blocked.action_items[0]["target_step"] == "Review and Import"
    assert blocked.action_items[0]["next_action"] == ("Fix this item before importing.")
    assert safe.decision == "safe"


def test_real_selected_eeg_candidate_without_identity_is_blocked() -> None:
    candidate = InterpretationCandidate(
        candidate_id="legacy-candidate",
        scan_id="scan-1",
        source_path="/data",
        source_kind="file",
        selected_eeg_files=["/data/sub-01.fif"],
    )

    decision = validate_interpretation_candidate(candidate)

    assert decision.decision == "blocked"
    assert any(
        "changed after preview" in reason.casefold()
        for reason in decision.blocked_reasons
    )
    assert decision.action_items[-1]["target_step"] == "Load Labels"


@pytest.mark.parametrize(
    ("confirmation", "target_step", "impact_fragment", "action_fragment"),
    [
        (
            "Confirm subject metadata for recording.fif.",
            "Review Metadata",
            "grouped under the wrong subject, session, task, or run",
            "Set or confirm the missing values in Review Metadata",
        ),
        (
            "Confirm label carrier alignment for labels.mat.",
            "Match Labels",
            "paired with the wrong EEG recording or event sequence",
            "Review EEG-to-label pairing and alignment in Match Labels",
        ),
        (
            "Confirm which events are trial anchors, class cues, responses, artifacts, or boundaries.",
            "Match Labels",
            "timing, artifact, or system events could be mistaken for training labels",
            "Assign each event role in Match Labels",
        ),
    ],
)
def test_confirmation_action_items_use_step_specific_guidance(
    confirmation,
    target_step,
    impact_fragment,
    action_fragment,
):
    decision = validate_interpretation_candidate(
        _candidate(confirmation_items=[confirmation], warnings=[])
    )

    item = next(row for row in decision.action_items if row["issue"] == confirmation)

    assert item["target_step"] == target_step
    assert impact_fragment in item["impact"]
    assert action_fragment in item["next_action"]
    assert "This choice affects imported metadata" not in item["impact"]
    assert item["next_action"] != "Review the target step and confirm the choice."


def test_build_interpretation_preview_marks_skipped_labels_as_limited():
    preview = build_interpretation_preview(
        preview_id="preview-1",
        candidate=_candidate(
            label_carriers=[],
            label_carrier_plan=[],
            choices={"skip_labels": True},
            warnings=[],
            confirmation_items=[],
        ),
    )

    assert {
        "issue": "Labels skipped for now.",
        "impact": (
            "Supervised dataset generation and training remain limited until "
            "labels or event semantics are added."
        ),
        "next_action": (
            "Continue only for inspection, or return to Load Labels before "
            "supervised training."
        ),
        "target_step": "Load Labels",
        "severity": "limited",
    } in preview.action_items


def test_build_interpretation_preview_does_not_ask_for_external_labels_when_embedded_events_selected():
    preview = build_interpretation_preview(
        preview_id="preview-1",
        candidate=_candidate(
            label_carriers=[],
            label_carrier_plan=[],
            choices={"label_carrier": "embedded_events"},
            internal_event_selection={"label_event_codes": ["769", "770"]},
            warnings=[],
            confirmation_items=["Confirm internal event labels."],
        ),
    )

    issues = {item["issue"] for item in preview.action_items}

    assert "No external label file or folder is attached." not in issues
    assert "Confirm internal event labels." in issues


def test_build_interpretation_preview_dedupes_bids_no_events_action_item_to_load_labels():
    warning = "BIDS folder has no events.tsv carrier for the selected scan scope."
    preview = build_interpretation_preview(
        preview_id="preview-1",
        candidate=_candidate(
            label_carriers=[],
            label_carrier_plan=[],
            warnings=[warning, warning],
            confirmation_items=[],
        ),
    )

    matching = [item for item in preview.action_items if item["issue"] == warning]

    assert len(matching) == 1
    assert matching[0]["target_step"] == "Load Labels"


def test_build_interpretation_preview_routes_empty_label_source_to_load_labels():
    warning = "Label source did not contain a supported label/event file: /tmp/empty"
    preview = build_interpretation_preview(
        preview_id="preview-1",
        candidate=_candidate(
            label_carriers=[],
            label_carrier_plan=[],
            warnings=[warning],
            confirmation_items=[],
        ),
    )

    matching = [item for item in preview.action_items if item["issue"] == warning]

    assert matching == [
        {
            "issue": warning,
            "impact": (
                "Import may still be usable, but downstream labels or metadata may "
                "need review."
            ),
            "next_action": (
                "Open the target step and resolve or confirm this item before import."
            ),
            "target_step": "Load Labels",
            "severity": "warning",
        }
    ]


def test_unresolved_event_values_collapse_consequential_placement_items() -> None:
    carrier_name = "sub-01_task-mi_events.tsv"
    candidate = _candidate(
        label_carrier_plan=[
            {
                "path": f"/data/{carrier_name}",
                "name": carrier_name,
                "unresolved_values": ["left", "button_press"],
            }
        ],
        blocked_reasons=[
            "Observed event values require complete role/keep/class decisions "
            f"for {carrier_name}: left, button_press.",
            "XBrainLab event placement for sub-01_task-mi_eeg.vhdr is blocked: "
            "selected event values have no complete semantic decision: left, "
            "button_press, no usable selected-label BIDS events remain after "
            "XBrainLab placement review",
            f"{carrier_name}: No selected-label BIDS event rows are approved for "
            "XBrainLab placement.",
        ],
        confirmation_items=[
            f"Confirm label placement for {carrier_name}: No selected-label BIDS "
            "event rows are approved for XBrainLab placement."
        ],
        warnings=[],
    )

    preview = build_interpretation_preview(
        preview_id="preview-1",
        candidate=candidate,
    )

    assert preview.action_items == [
        {
            "issue": f"Event value decisions are incomplete for {carrier_name}.",
            "impact": "2 observed values cannot be placed yet: left, button_press.",
            "next_action": "Choose a role and use for each value in Match Labels.",
            "target_step": "Match Labels",
            "severity": "blocked",
        }
    ]


def test_existing_label_placement_problem_routes_to_match_labels() -> None:
    assert (
        target_step_for_interpretation_text(
            "events.tsv: No selected-label BIDS event rows are approved for "
            "XBrainLab placement."
        )
        == "Match Labels"
    )
