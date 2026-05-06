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


def test_build_interpretation_candidate_previews_tabular_label_class_values(tmp_path):
    events = tmp_path / "sub-01_task-mi_events.tsv"
    events.write_text(
        "onset\tduration\ttrial_type\n"
        "0.0\t1.0\tleft\n"
        "1.0\t1.0\tright\n"
        "2.0\t1.0\tleft\n",
        encoding="utf-8",
    )

    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            label_carriers=[str(events)],
            bids={"is_bids": True, "events_files": [str(events)]},
        ),
    )

    assert candidate.label_carrier_plan[0]["selected_label_field"] == "trial_type"
    assert candidate.class_map == {"left": "left", "right": "right"}
    assert (
        "Confirm label carrier alignment, anchor event, and class map before applying."
        in candidate.confirmation_items
    )
    assert "choices:class_map" not in candidate.recipe_trace


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


def test_build_interpretation_candidate_remaps_saved_selected_eeg_file_choices():
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(
            eeg_files=["/data/renamed_raw.fif"],
            metadata=[
                FileMetadataResolution(
                    file="/data/renamed_raw.fif",
                    subject=_field("subject"),
                    session=_field("session", "01"),
                    task=_field("task", "mi"),
                    run=_field("run", "1"),
                )
            ],
        ),
        choices={
            "recipe_id": "recipe-1",
            "selected_eeg_files": ["/data/original_raw.fif"],
            "eeg_file_remap": {
                "/data/original_raw.fif": "/data/renamed_raw.fif",
            },
            "metadata_overrides": {
                "/data/original_raw.fif": {"subject": "S01"},
            },
        },
    )

    assert candidate.blocked_reasons == []
    assert candidate.selected_eeg_files == ["/data/renamed_raw.fif"]
    assert candidate.metadata[0].subject.value == "S01"
    assert candidate.metadata[0].subject.source == "user_override"
    assert "choices:eeg_file_remap" in candidate.recipe_trace


def test_build_interpretation_candidate_blocks_required_label_carriers_missing_from_scan():
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(label_carriers=["/data/sub-01_task-mi_events.tsv"]),
        choices={
            "recipe_id": "recipe-1",
            "required_label_carriers": [
                "/data/sub-01_task-mi_events.tsv",
                "/data/missing_events.tsv",
            ],
        },
    )

    assert "missing_events.tsv" in candidate.blocked_reasons[0]
    assert "label/event carrier" in candidate.blocked_reasons[0]
    assert "choices:label_carriers" in candidate.recipe_trace


def test_build_interpretation_candidate_remaps_saved_label_carrier_choices():
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=_scan(label_carriers=["/data/renamed_events.tsv"]),
        choices={
            "recipe_id": "recipe-1",
            "required_label_carriers": ["/data/original_events.tsv"],
            "label_carrier_remap": {
                "/data/original_events.tsv": "/data/renamed_events.tsv",
            },
            "label_carrier_choices": {
                "/data/original_events.tsv": {
                    "label_field": "trial_type",
                    "anchor": "onset",
                    "time_model": "seconds",
                    "granularity": "trial",
                    "role": "class cue labels",
                }
            },
        },
    )

    assert candidate.blocked_reasons == []
    assert candidate.label_carrier_plan[0]["path"] == "/data/renamed_events.tsv"
    assert candidate.label_carrier_plan[0]["selected_label_field"] == "trial_type"
    assert candidate.label_carrier_plan[0]["selected_anchor"] == "onset"
    assert candidate.label_carrier_plan[0]["role"] == "class cue labels"
    assert "choices:label_carrier_remap" in candidate.recipe_trace
