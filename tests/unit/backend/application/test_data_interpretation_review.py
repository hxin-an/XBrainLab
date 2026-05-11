from types import SimpleNamespace

from XBrainLab.backend.application.data_interpretation_metadata import (
    FileMetadataResolution,
    MetadataFieldResolution,
)
from XBrainLab.backend.application.data_interpretation_review import (
    InterpretationPreview,
    ValidationDecision,
    build_interpretation_preview,
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
        "selected_eeg_files": ["/data/sub-01.fif"],
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
    assert preview.metadata_preview[0]["file"] == "sub-01.fif"
    assert preview.metadata_preview[0]["subject"]["value"] == "01"
    assert preview.event_roles == {"trial_type": "class cue"}


def test_build_interpretation_preview_summarizes_recipe_reload_diff():
    recipe = SimpleNamespace(
        recipe_id="recipe-1",
        source_path="/data",
        selected_eeg_files=["/data/sub-01.fif", "/data/missing.fif"],
        label_carriers=["/data/old_events.tsv"],
        metadata=[],
        event_roles={"trial_type": "class cue"},
        class_map={"1": "left"},
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
    assert safe.decision == "safe"
