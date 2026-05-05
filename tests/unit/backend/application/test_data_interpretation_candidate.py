from XBrainLab.backend.application.data_interpretation_candidate import (
    InterpretationCandidate,
    build_interpretation_candidate,
)
from XBrainLab.backend.application.data_interpretation_metadata import (
    FileMetadataResolution,
    MetadataFieldResolution,
)
from XBrainLab.backend.application.data_interpretation_scan import ScanResult


def _field(name: str, value: str | None = None) -> MetadataFieldResolution:
    return MetadataFieldResolution(
        field=name,
        value=value,
        source="test",
        decision="safe" if value else "needs_confirmation",
        reason="test",
    )


def _scan(**overrides) -> ScanResult:
    data = {
        "scan_id": "scan-1",
        "source_path": "/data",
        "source_kind": "bids",
        "eeg_files": ["/data/sub-01_task-mi_raw.fif"],
        "label_carriers": ["/data/sub-01_task-mi_events.tsv"],
        "metadata": [
            FileMetadataResolution(
                file="/data/sub-01_task-mi_raw.fif",
                subject=_field("subject"),
                session=_field("session", "01"),
                task=_field("task", "mi"),
                run=_field("run", "1"),
            )
        ],
        "bids": {"is_bids": True, "events_files": ["/data/sub-01_task-mi_events.tsv"]},
        "format_capabilities": [{"format": "MNE FIF", "status": "supported"}],
        "warnings": ["Review external labels."],
        "blocked_reasons": [],
    }
    data.update(overrides)
    return ScanResult(**data)


def test_build_interpretation_candidate_applies_user_choices_and_recipe_trace():
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(),
        choices={
            "metadata_overrides": {
                "sub-01_task-mi_raw.fif": {"subject": "S01"},
            },
            "class_map": {"left": "0"},
            "event_roles": {"trial_type": "class cue"},
            "label_carrier_choices": {
                "sub-01_task-mi_events.tsv": {"label_field": "trial_type"},
            },
        },
    )

    assert isinstance(candidate, InterpretationCandidate)
    assert candidate.metadata[0].subject.value == "S01"
    assert candidate.metadata[0].subject.source == "user_override"
    assert candidate.event_roles["trial_type"] == "class cue"
    assert candidate.class_map == {"left": "0"}
    assert "choices:metadata_overrides" in candidate.recipe_trace
    assert "choices:class_map" in candidate.recipe_trace
    assert "choices:event_roles" in candidate.recipe_trace
    assert "choices:label_carriers" in candidate.recipe_trace


def test_build_interpretation_candidate_blocks_empty_selection():
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(eeg_files=[]),
        choices={"selected_eeg_files": []},
    )

    assert candidate.selected_eeg_files == []
    assert "No EEG files were selected for interpretation." in candidate.blocked_reasons


def test_build_interpretation_candidate_blocks_selected_files_missing_from_scan():
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(eeg_files=["/data/sub-01_task-mi_raw.fif"]),
        choices={
            "recipe_id": "recipe-1",
            "selected_eeg_files": [
                "/data/sub-01_task-mi_raw.fif",
                "/data/missing_raw.fif",
            ],
        },
    )

    assert "missing_raw.fif" in candidate.blocked_reasons[0]
    assert "not found in the current scan" in candidate.blocked_reasons[0]
