from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock

import mne
import numpy as np
import pytest

from tests.unit.backend.path_assertions import assert_filesystem_path_lists_equal
from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    PreviewInterpretationCommand,
    ReviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
    data_interpretation_bids,
    data_interpretation_internal_events,
    resource_guard,
)
from XBrainLab.backend.application.data_interpretation import (
    AppliedInterpretation,
    InterpretationCandidate,
    build_interpretation_candidate,
    scan_source_path,
    validate_interpretation_candidate,
)
from XBrainLab.backend.application.data_interpretation_apply import (
    DataInterpretationApplyService,
)
from XBrainLab.backend.application.data_interpretation_scan import ScanResult
from XBrainLab.backend.application.data_interpretation_state import (
    DataInterpretationSessionState,
)
from XBrainLab.backend.application.label_resource_admission import (
    LabelResourceAdmissionService,
    LabelResourceSpec,
)
from XBrainLab.backend.load_data.raw import Raw


def _write_bids_run(
    root: Path,
    *,
    run: str,
    event_rows: list[tuple[str, str, str, str]],
    sfreq: float = 100.0,
    n_times: int = 1000,
) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    description = root / "dataset_description.json"
    if not description.exists():
        description.write_text(
            json.dumps({"Name": "strict-bids-test", "BIDSVersion": "1.11.1"}),
            encoding="utf-8",
        )
    eeg_dir = root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True, exist_ok=True)
    stem = f"sub-01_task-mi_run-{run}"
    eeg_path = eeg_dir / f"{stem}_eeg.fif"
    events_path = eeg_dir / f"{stem}_events.tsv"
    info = mne.create_info(["Cz"], sfreq=sfreq, ch_types="eeg")
    raw = mne.io.RawArray(np.zeros((1, n_times)), info, verbose="ERROR")
    raw.save(eeg_path, overwrite=True, verbose="ERROR")
    events_path.write_text(
        "onset\tduration\ttrial_type\tvalue\n"
        + "".join("\t".join(row) + "\n" for row in event_rows),
        encoding="utf-8",
    )
    return eeg_path.resolve(), events_path.resolve()


def _candidate_for_bids(
    root: Path,
    *,
    selected_eeg_files: list[Path] | None = None,
    carrier_targets: dict[Path, Path] | None = None,
    run_event_mappings: dict[str, dict[str, str]] | None = None,
) -> InterpretationCandidate:
    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(root),
        source_hint="bids",
    )
    selected = selected_eeg_files or [Path(path) for path in scan.eeg_files]
    choices: dict[str, object] = {
        "selected_eeg_files": [str(path) for path in selected],
        "label_carrier_choices": {
            carrier: {
                "label_field": "trial_type",
                "anchor": "onset",
                "duration_field": "duration",
                "time_model": "seconds",
                "placement_method": "interval",
                "value_decisions": _value_decisions_from_events(Path(carrier)),
                **(
                    {"target_file": str(carrier_targets[Path(carrier)])}
                    if carrier_targets and Path(carrier) in carrier_targets
                    else {}
                ),
            }
            for carrier in scan.label_carriers
        },
    }
    if run_event_mappings is not None:
        choices["run_event_mappings"] = run_event_mappings
    return build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=scan,
        choices=choices,
    )


def _value_decisions_from_events(path: Path) -> dict[str, dict[str, object]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle, delimiter="\t")
        values = {
            str(row.get("trial_type") or "").strip()
            for row in rows
            if str(row.get("trial_type") or "").strip().casefold()
            not in {"", "n/a", "na", "nan", "null"}
        }
    return {
        value: {
            "role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": value,
        }
        for value in values
    }


def test_bids_label_field_recommendation_ignores_unselected_run_carriers(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    selected_eeg, selected_events = _write_bids_run(
        root,
        run="1",
        event_rows=[
            ("0", "0", "stimulus", "standard"),
            ("1", "0", "stimulus", "oddball"),
            ("2", "0", "response", "response"),
        ],
    )
    selected_events.with_suffix(".json").write_text(
        json.dumps(
            {
                "trial_type": {
                    "Levels": {
                        "stimulus": "Auditory stimulus",
                        "response": "Behavioral response",
                    }
                },
                "value": {
                    "Levels": {
                        "standard": "Standard tone",
                        "oddball": "Oddball tone",
                        "response": "Button response",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    unselected_eeg, unselected_events = _write_bids_run(
        root,
        run="2",
        event_rows=[
            ("0", "0", "left_hand", "769"),
            ("1", "0", "right_hand", "770"),
        ],
    )
    unselected_events.with_suffix(".json").write_text(
        json.dumps(
            {
                "trial_type": {
                    "Levels": {
                        "left_hand": "Left hand",
                        "right_hand": "Right hand",
                    }
                },
                "value": {"Description": "Hardware trigger code"},
            }
        ),
        encoding="utf-8",
    )

    selected_service = ApplicationService()
    assert selected_service.execute(
        ScanSourceCommand(source_path=str(root), source_hint="bids")
    ).ok
    selected_preview = selected_service.execute(
        PreviewInterpretationCommand(
            choices={"selected_eeg_files": [str(selected_eeg)]}
        )
    )

    assert selected_preview.ok is True
    selected_carriers = selected_preview.diagnostics["preview"]["label_carrier_preview"]
    assert [row["path"] for row in selected_carriers] == [str(selected_events)]
    assert [row["selected_target_file"] for row in selected_carriers] == [
        str(selected_eeg)
    ]
    assert selected_carriers[0]["selected_label_field"] == "value"
    recommendation = selected_carriers[0]["label_field_recommendation"]
    assert recommendation["field"] == "value"
    assert recommendation["facts"]["selected_run_count"] == 1

    combined_service = ApplicationService()
    assert combined_service.execute(
        ScanSourceCommand(source_path=str(root), source_hint="bids")
    ).ok
    combined_preview = combined_service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(selected_eeg), str(unselected_eeg)],
            }
        )
    )

    assert combined_preview.ok is True
    combined_carriers = combined_preview.diagnostics["preview"]["label_carrier_preview"]
    assert {row["path"] for row in combined_carriers} == {
        str(selected_events),
        str(unselected_events),
    }
    assert {row["selected_label_field"] for row in combined_carriers} == {"trial_type"}
    assert (
        combined_carriers[0]["label_field_recommendation"]["facts"][
            "selected_run_count"
        ]
        == 2
    )


def test_strict_bids_keeps_full_issue_evidence_but_bounds_blocker_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eeg_path = "/data/sub-01/eeg/sub-01_task-P300_eeg.set"
    events_path = "/data/sub-01/eeg/sub-01_task-P300_events.tsv"
    issues = [
        {
            "code": "unresolved_event_value_decisions",
            "row": None,
            "message": "selected event values need semantic decisions",
        },
        *[
            {
                "code": "value_decision_unresolved",
                "row": row,
                "message": "selected label has no complete semantic decision",
            }
            for row in range(2, 33)
        ],
    ]

    monkeypatch.setattr(
        data_interpretation_bids,
        "_review_one_run",
        lambda **_kwargs: (
            {
                "event_count": 31,
                "row_evidence": [],
                "placement": {
                    "status": "blocked",
                    "usable_event_count": 0,
                    "excluded_event_count": 0,
                },
                "bids_schema": {"issues": []},
                "issues": issues,
            },
            {},
        ),
    )

    review = data_interpretation_bids.review_strict_bids_event_runs(
        bids={
            "is_bids": True,
            "layout": [
                {
                    "file": eeg_path,
                    "events_file": events_path,
                }
            ],
        },
        selected_eeg_files=[eeg_path],
        label_carrier_plan=[{"path": events_path}],
    )

    assert review.evidence["runs"][0]["issues"] == issues
    [reason] = review.blocked_reasons
    assert "row 12 (selected label has no complete semantic decision)" in reason
    assert "row 13 (selected label has no complete semantic decision)" not in reason
    assert "20 more issues" in reason


def test_bids_preview_blocks_before_events_tsv_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "bids"
    _eeg_path, events_path = _write_bids_run(
        root,
        run="1",
        event_rows=[("0", "1", "left", "1")],
    )
    service = ApplicationService()
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 64,
                "total_bytes": 128,
                "used_bytes": 64,
            }
        ),
    )

    def _must_not_read_events(_path: Path):
        pytest.fail("events.tsv was materialized before the blocking RAM preflight")

    monkeypatch.setattr(
        data_interpretation_bids, "_read_events_rows", _must_not_read_events
    )

    result = service.execute(
        ReviewInterpretationCommand(
            source_path=str(root),
            source_hint="bids",
        ),
    )

    assert result.failed is True
    assert result.diagnostics["resource_preflight"]["risk_level"] == "blocking"
    assert result.diagnostics["resource_preflight"]["label_carrier_count"] == 1
    assert (
        result.diagnostics["resource_preflight"]["label_carrier_file_bytes"]
        == events_path.stat().st_size
    )


@pytest.mark.parametrize(
    ("invalid_row", "issue_code"),
    [
        (("-0.01", "0", "outside", "2"), "onset_before_stored_recording"),
        (("10", "0", "outside", "2"), "onset_at_or_after_recording_end"),
        (("9.9", "0.2", "outside", "2"), "interval_exceeds_recording_end"),
        (("n/a", "0", "outside", "2"), "onset_unknown"),
    ],
)
def test_strict_bids_blocks_partial_timestamp_placement_before_apply(
    tmp_path: Path,
    invalid_row: tuple[str, str, str, str],
    issue_code: str,
) -> None:
    root = tmp_path / "bids"
    eeg_path, events_path = _write_bids_run(
        root,
        run="1",
        event_rows=[("1", "0", "left", "1"), invalid_row],
    )
    service = ApplicationService()
    service.execute(ScanSourceCommand(source_path=str(root), source_hint="bids"))
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg_path)],
                "label_carrier_choices": {
                    str(events_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "duration_field": "duration",
                        "time_model": "seconds",
                        "placement_method": "interval",
                        "value_decisions": _value_decisions_from_events(events_path),
                    }
                },
            }
        )
    )
    validation = service.execute(ValidateInterpretationCommand())
    applied = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert preview.ok is True
    run = preview.diagnostics["preview"]["bids"]["event_validation"]["runs"][0]
    assert run["placement"]["status"] == "blocked"
    assert issue_code in {issue["code"] for issue in run["issues"]}
    assert validation.diagnostics["validation_decision"]["decision"] == "blocked"
    assert applied.ok is False
    assert applied.state.raw.count == 0


def test_strict_bids_excludes_missing_selected_labels_without_blocking_import(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    eeg_path, events_path = _write_bids_run(
        root,
        run="1",
        event_rows=[
            ("1", "0", "stimulus", "standard"),
            ("2", "0", "n/a", "ignore"),
        ],
    )
    service = ApplicationService()
    assert service.execute(
        ScanSourceCommand(source_path=str(root), source_hint="bids")
    ).ok
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg_path)],
                "label_carrier_choices": {
                    str(events_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "duration_field": "duration",
                        "time_model": "seconds",
                        "placement_method": "time_field",
                        "value_decisions": {
                            "stimulus": {
                                "role": "stimulus",
                                "keep_event": True,
                                "use_as_class": True,
                                "class_name": "stimulus",
                            }
                        },
                    }
                },
            }
        )
    )
    validation = service.execute(ValidateInterpretationCommand())
    applied = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert preview.ok is True
    run = preview.diagnostics["preview"]["bids"]["event_validation"]["runs"][0]
    assert run["placement"]["status"] == "ready_with_exclusions"
    assert run["placement"]["usable_event_count"] == 1
    assert run["placement"]["excluded_event_count"] == 1
    assert run["placement"]["excluded_row_count"] == 1
    assert "excluded_rows" not in run["placement"]
    decision = validation.diagnostics["validation_decision"]
    assert decision["decision"] == "safe"
    assert decision["blocked_reasons"] == []
    assert applied.ok is True
    assert applied.state.raw.count == 1
    assert applied.diagnostics["label_apply"]["bids_placement"][0][
        "excluded_reasons"
    ] == {"selected_label_missing": 1}


def test_strict_bids_legal_special_values_remain_schema_evidence_but_block_apply(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    eeg_path, events_path = _write_bids_run(
        root,
        run="1",
        event_rows=[
            ("-0.01", "0", "negative-onset", "1"),
            ("n/a", "0", "unknown-onset", "2"),
            ("1", "n/a", "unknown-duration", "3"),
            ("2", "0", "point", "4"),
            ("10", "0", "at-recording-end", "5"),
            ("9.9", "0.2", "past-recording-end", "6"),
        ],
    )

    candidate = _candidate_for_bids(root)
    decision = validate_interpretation_candidate(candidate)
    evidence = candidate.bids["event_validation"]
    run = evidence["runs"][0]

    assert decision.decision == "blocked"
    assert evidence["status"] == "blocked"
    assert evidence["file_mapping"] == {str(eeg_path): str(events_path)}
    assert run["bids_schema"] == {
        "status": "valid",
        "issues": [],
        "legal_special_values": {
            "negative_onset_count": 1,
            "unknown_onset_count": 1,
            "unknown_duration_count": 1,
        },
    }
    assert {issue["code"] for issue in run["issues"]} == {
        "interval_exceeds_recording_end",
        "onset_at_or_after_recording_end",
        "onset_before_stored_recording",
        "onset_unknown",
    }
    assert run["placement"]["status"] == "blocked"
    assert run["placement"]["usable_event_count"] == 2
    assert run["placement"]["excluded_event_count"] == 0
    assert run["placement"]["unknown_duration_count"] == 1
    assert run["placement"]["excluded_rows"] == []
    assert run["placement"]["unknown_duration_rows"] == [
        {
            "row": 4,
            "raw_duration": "n/a",
            "placement_duration_seconds": 0.0,
        }
    ]
    assert candidate.label_carrier_plan[0]["placement_review"]["status"] == "blocked"
    assert any(
        item["severity"] == "blocked"
        and item["target_step"] == "Match Labels"
        and eeg_path.name in item["issue"]
        for item in decision.action_items
    )

    dataset = MagicMock()
    raw = MagicMock()
    raw.get_filepath.return_value = str(eeg_path)
    dataset.get_loaded_data_list.return_value = [raw]
    apply_service = DataInterpretationApplyService(
        dataset,
        data_filename=lambda item: str(item.get_filepath()),
        data_filepath=lambda item: str(item.get_filepath()),
        record_label_import=lambda **_kwargs: None,
    )

    result = apply_service.apply_label_carriers(candidate)

    assert result["status"] == "failed"
    assert "Label placement is not ready" in result["reason"]
    dataset.apply_labels_batch.assert_not_called()


def test_application_rejects_non_placeable_bids_rows_before_loading_raw(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    eeg_path, events_path = _write_bids_run(
        root,
        run="1",
        event_rows=[
            ("-0.1", "0", "negative-onset", "1"),
            ("n/a", "0", "unknown-onset", "2"),
            ("1", "n/a", "unknown-duration", "3"),
            ("2", "0", "point", "4"),
        ],
    )
    service = ApplicationService()

    service.execute(ScanSourceCommand(source_path=str(root), source_hint="bids"))
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg_path)],
                "label_carrier_choices": {
                    str(events_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "duration_field": "duration",
                        "time_model": "seconds",
                        "placement_method": "interval",
                        "value_decisions": _value_decisions_from_events(events_path),
                    }
                },
            }
        )
    )
    validation = service.execute(ValidateInterpretationCommand())
    applied = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert preview.ok is True
    assert validation.diagnostics["validation_decision"]["decision"] == "blocked"
    assert applied.ok is False
    assert applied.state.raw.count == 0


@pytest.mark.parametrize(
    ("changed_rows", "changed_field"),
    [
        ([("2", "0", "left", "1")], "onset"),
        ([("1", "1", "left", "1")], "duration"),
        ([("1", "0", "foot", "1")], "label"),
        ([("1", "0", "left", "2")], "event code"),
    ],
)
def test_apply_fails_closed_when_reviewed_bids_event_content_changes(
    tmp_path: Path,
    changed_rows: list[tuple[str, str, str, str]],
    changed_field: str,
) -> None:
    root = tmp_path / "bids"
    eeg_path, events_path = _write_bids_run(
        root,
        run="1",
        event_rows=[("1", "0", "left", "1")],
    )
    reviewed_size = events_path.stat().st_size
    service = ApplicationService()

    scan = service.execute(ScanSourceCommand(source_path=str(root), source_hint="bids"))
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg_path)],
                "label_carrier_choices": {
                    str(events_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "duration_field": "duration",
                        "time_model": "seconds",
                        "placement_method": "interval",
                        "value_decisions": _value_decisions_from_events(events_path),
                    }
                },
            }
        )
    )
    validation = service.execute(ValidateInterpretationCommand())

    events_path.write_text(
        "onset\tduration\ttrial_type\tvalue\n"
        + "".join("\t".join(row) + "\n" for row in changed_rows),
        encoding="utf-8",
    )
    assert events_path.stat().st_size == reviewed_size, (
        f"{changed_field} mutation must preserve file size so the regression proves "
        "content identity, not stat metadata, protects Apply"
    )

    applied = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert scan.ok is True
    assert preview.ok is True
    assert validation.ok is True
    assert applied.failed is True
    assert applied.error_type.value == "precondition"
    assert "changed after preview" in applied.message.lower()
    assert "preview" in applied.message.lower()
    assert "review" in applied.message.lower()
    assert applied.diagnostics["code"] == (
        "interpretation_content_changed_after_review"
    )
    assert_filesystem_path_lists_equal(
        applied.diagnostics["changed_paths"],
        [events_path],
    )
    assert applied.diagnostics["next_action"] == "preview_and_review_again"
    assert applied.state.raw.count == 0


def test_validate_fails_closed_when_reviewed_bids_events_sidecar_changes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    eeg_path, events_path = _write_bids_run(
        root,
        run="1",
        event_rows=[("1", "0", "left", "1")],
    )
    sidecar_path = events_path.with_suffix(".json")
    sidecar_path.write_text(
        json.dumps({"trial_type": {"Levels": {"left": "Hand"}}}),
        encoding="utf-8",
    )
    reviewed_size = sidecar_path.stat().st_size
    service = ApplicationService()

    service.execute(ScanSourceCommand(source_path=str(root), source_hint="bids"))
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg_path)],
                "label_carrier_choices": {
                    str(events_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "duration_field": "duration",
                        "time_model": "seconds",
                        "placement_method": "interval",
                        "value_decisions": _value_decisions_from_events(events_path),
                    }
                },
            }
        )
    )
    identity = preview.diagnostics["preview"]["content_identity"]
    assert {row["role"] for row in identity["files"]} == {
        "selected_eeg",
        "label_carrier",
        "bids_events_json",
    }

    sidecar_path.write_text(
        json.dumps({"trial_type": {"Levels": {"left": "Foot"}}}),
        encoding="utf-8",
    )
    assert sidecar_path.stat().st_size == reviewed_size

    validation = service.execute(ValidateInterpretationCommand())

    decision = validation.diagnostics["validation_decision"]
    assert validation.ok is True
    assert decision["decision"] == "blocked"
    assert any(
        "changed after preview" in item.lower() for item in decision["blocked_reasons"]
    )
    assert any(
        item["target_step"] == "Load Labels" and item["severity"] == "blocked"
        for item in decision["action_items"]
    )
    assert validation.state.raw.count == 0


@pytest.mark.parametrize(
    ("onset", "duration", "issue_code"),
    [
        ("not-a-number", "0", "malformed_onset"),
        ("NaN", "0", "malformed_onset"),
        ("1", "not-a-number", "malformed_duration"),
        ("1", "N/A", "malformed_duration"),
    ],
)
def test_strict_bids_blocks_malformed_required_numeric_values(
    tmp_path: Path,
    onset: str,
    duration: str,
    issue_code: str,
) -> None:
    root = tmp_path / issue_code / onset.replace("/", "-")
    _write_bids_run(
        root,
        run="1",
        event_rows=[(onset, duration, "bad", "1"), ("1", "0", "usable", "2")],
    )

    candidate = _candidate_for_bids(root)
    run = candidate.bids["event_validation"]["runs"][0]

    assert validate_interpretation_candidate(candidate).decision == "blocked"
    assert run["bids_schema"]["status"] == "invalid"
    assert {issue["code"] for issue in run["bids_schema"]["issues"]} == {issue_code}
    assert any("field value" in reason for reason in candidate.blocked_reasons)


def test_strict_bids_blocks_known_negative_duration(tmp_path: Path) -> None:
    root = tmp_path / "bids"
    _write_bids_run(
        root,
        run="1",
        event_rows=[("1", "-0.1", "negative-duration", "1")],
    )

    candidate = _candidate_for_bids(root)
    run = candidate.bids["event_validation"]["runs"][0]

    assert validate_interpretation_candidate(candidate).decision == "blocked"
    assert run["bids_schema"]["status"] == "invalid"
    assert run["bids_schema"]["issues"] == [
        {
            "code": "negative_duration",
            "row": 2,
            "message": "known duration is negative",
        }
    ]


def test_strict_bids_blocks_when_no_selected_label_event_is_placeable(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    eeg_path, events_path = _write_bids_run(
        root,
        run="1",
        event_rows=[
            ("-0.01", "0", "negative-onset", "1"),
            ("n/a", "0", "unknown-onset", "2"),
            ("10", "0", "at-recording-end", "3"),
            ("9.9", "0.2", "past-recording-end", "4"),
        ],
    )

    candidate = _candidate_for_bids(root)
    decision = validate_interpretation_candidate(candidate)
    evidence = candidate.bids["event_validation"]
    run = evidence["runs"][0]

    assert decision.decision == "blocked"
    assert evidence["status"] == "blocked"
    assert evidence["file_mapping"] == {str(eeg_path): str(events_path)}
    assert run["bids_schema"]["status"] == "valid"
    assert run["bids_schema"]["issues"] == []
    assert run["placement"]["status"] == "blocked"
    assert run["placement"]["usable_event_count"] == 0
    assert run["placement"]["excluded_event_count"] == 0
    assert {issue["code"] for issue in run["issues"]} == {
        "interval_exceeds_recording_end",
        "onset_at_or_after_recording_end",
        "onset_before_stored_recording",
        "onset_unknown",
        "no_usable_selected_label_events",
    }
    assert any(
        "event placement" in reason.lower() and eeg_path.name in reason
        for reason in decision.blocked_reasons
    )
    assert any(
        item["severity"] == "blocked"
        and item["target_step"] == "Match Labels"
        and eeg_path.name in item["issue"]
        for item in decision.action_items
    )


def test_strict_bids_zero_usable_rows_block_application_before_loading_raw(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    eeg_path, events_path = _write_bids_run(
        root,
        run="1",
        event_rows=[("-0.01", "0", "negative-onset", "1")],
    )
    service = ApplicationService()

    scan_result = service.execute(
        ScanSourceCommand(source_path=str(root), source_hint="bids")
    )
    preview_result = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg_path)],
                "label_carrier_choices": {
                    str(events_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "duration_field": "duration",
                        "time_model": "seconds",
                        "placement_method": "interval",
                        "value_decisions": _value_decisions_from_events(events_path),
                    }
                },
            }
        )
    )
    validation_result = service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert scan_result.ok is True
    assert preview_result.ok is True
    assert validation_result.ok is True
    decision = validation_result.diagnostics["validation_decision"]
    assert decision["decision"] == "blocked"
    assert decision["action_items"][0]["severity"] == "blocked"
    assert eeg_path.name in decision["action_items"][0]["issue"]
    assert apply_result.ok is False
    assert "no usable selected-label BIDS events" in apply_result.message
    assert apply_result.state.raw.count == 0


def test_recording_metadata_cleanup_cannot_mask_original_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    raw = MagicMock()
    raw.close.side_effect = RuntimeError("cleanup failed")
    wrapper = MagicMock()
    wrapper.get_mne.return_value = raw
    monkeypatch.setattr(
        data_interpretation_bids,
        "load_raw_data",
        lambda _path: wrapper,
    )
    monkeypatch.setattr(
        data_interpretation_bids,
        "_validated_recording_metadata",
        lambda _wrapper: (_ for _ in ()).throw(ValueError("original metadata error")),
    )

    result = data_interpretation_bids._recording_metadata(tmp_path / "run_eeg.fif")

    assert result["issue"]["code"] == "recording_metadata_unavailable"
    assert "original metadata error" in result["issue"]["message"]
    assert "cleanup failed" not in result["issue"]["message"]
    raw.close.assert_called_once_with()


def test_strict_bids_accepts_zero_duration_and_interval_ending_at_recording_end(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    eeg_path, events_path = _write_bids_run(
        root,
        run="1",
        event_rows=[
            ("9.99", "0", "point", "1"),
            ("9.5", "0.5", "exact-end", "2"),
        ],
    )

    candidate = _candidate_for_bids(root)
    evidence = candidate.bids["event_validation"]
    run = evidence["runs"][0]

    assert evidence["status"] == "safe"
    assert evidence["file_mapping"] == {str(eeg_path): str(events_path)}
    assert run["status"] == "safe"
    assert run["recording_duration_seconds"] == 10.0
    assert run["event_count"] == 2
    assert run["zero_duration_event_count"] == 1
    assert run["bids_schema"]["status"] == "valid"
    assert run["placement"] == {
        "status": "ready",
        "usable_event_count": 2,
        "excluded_event_count": 0,
        "excluded_rows": [],
        "unknown_duration_count": 0,
        "unknown_duration_rows": [],
    }
    assert run["issues"] == []
    assert not any(
        "event timing" in reason.lower() for reason in candidate.blocked_reasons
    )


def test_strict_bids_preview_uses_admitted_header_bounds_without_loading_raw(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "bids"
    eeg_path, events_path = _write_bids_run(
        root,
        run="1",
        event_rows=[
            ("9.99", "0", "point", "1"),
            ("9.5", "0.5", "exact-end", "2"),
        ],
    )
    service = ApplicationService()
    scan_result = service.execute(
        ScanSourceCommand(source_path=str(root), source_hint="bids")
    )
    monkeypatch.setattr(
        data_interpretation_bids,
        "load_raw_data",
        lambda _path: pytest.fail("BIDS preview reloaded admitted EEG signal data"),
    )

    preview_result = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg_path)],
                "label_carrier_choices": {
                    str(events_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "duration_field": "duration",
                        "time_model": "seconds",
                        "placement_method": "interval",
                        "value_decisions": _value_decisions_from_events(events_path),
                    }
                },
            }
        )
    )

    assert scan_result.ok is True
    assert preview_result.ok is True
    run = preview_result.diagnostics["preview"]["bids"]["event_validation"]["runs"][0]
    assert run["status"] == "safe"
    assert run["sample_count"] == 1000
    assert run["sampling_frequency_hz"] == 100.0
    assert run["recording_duration_seconds"] == 10.0


def test_strict_bids_rejects_events_carriers_swapped_between_runs(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    eeg_1, events_1 = _write_bids_run(
        root,
        run="1",
        event_rows=[("1", "0", "left", "1")],
    )
    eeg_2, events_2 = _write_bids_run(
        root,
        run="2",
        event_rows=[("2", "0", "right", "2")],
    )

    candidate = _candidate_for_bids(
        root,
        carrier_targets={events_1: eeg_2, events_2: eeg_1},
    )
    evidence = candidate.bids["event_validation"]

    assert evidence["status"] == "blocked"
    assert evidence["file_mapping"] == {
        str(eeg_1): str(events_1),
        str(eeg_2): str(events_2),
    }
    assert {issue["code"] for issue in evidence["pairing_issues"]} == {
        "events_file_targets_wrong_run"
    }
    assert {
        Path(issue["affected_eeg_file"]).name for issue in evidence["pairing_issues"]
    } == {
        eeg_1.name,
        eeg_2.name,
    }
    assert any("wrong BIDS run" in reason for reason in candidate.blocked_reasons)


def test_strict_bids_namespaces_same_event_code_by_selected_run(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    eeg_1, _events_1 = _write_bids_run(
        root,
        run="1",
        event_rows=[("1", "0", "left", "1")],
    )
    eeg_2, _events_2 = _write_bids_run(
        root,
        run="2",
        event_rows=[("1", "0", "right", "1")],
    )

    candidate = _candidate_for_bids(root)
    evidence = candidate.bids["event_validation"]

    assert evidence["mapping_conflicts"] == []
    assert evidence["mapping_scope"] == "per_carrier_selected_run"
    plans = {
        Path(plan["selected_target_file"]).name: plan["run_class_map"]
        for plan in candidate.label_carrier_plan
    }
    assert plans == {
        eeg_1.name: {"left": "left"},
        eeg_2.name: {"right": "right"},
    }


def test_strict_bids_keeps_run_specific_events_json_levels_as_suggestions(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    eeg_1, events_1 = _write_bids_run(
        root,
        run="1",
        event_rows=[("1", "0", "1", "1")],
    )
    eeg_2, events_2 = _write_bids_run(
        root,
        run="2",
        event_rows=[("1", "0", "1", "1")],
    )
    events_1.with_suffix(".json").write_text(
        json.dumps({"trial_type": {"Levels": {"1": "left hand"}}}),
        encoding="utf-8",
    )
    events_2.with_suffix(".json").write_text(
        json.dumps({"trial_type": {"Levels": {"1": "right hand"}}}),
        encoding="utf-8",
    )

    candidate = _candidate_for_bids(root)
    evidence = candidate.bids["event_validation"]
    plans = {
        Path(plan["selected_target_file"]).name: plan
        for plan in candidate.label_carrier_plan
    }

    assert evidence["mapping_conflicts"] == []
    assert plans[eeg_1.name]["run_class_map"] == {"1": "1"}
    assert plans[eeg_2.name]["run_class_map"] == {"1": "1"}
    assert plans[eeg_1.name]["value_decisions"]["1"]["suggested_name"] == ("left hand")
    assert plans[eeg_2.name]["value_decisions"]["1"]["suggested_name"] == ("right hand")


def test_strict_bids_preserves_numeric_category_lexemes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    _eeg, _events = _write_bids_run(
        root,
        run="1",
        event_rows=[
            ("1", "0", "0.0", "1"),
            ("2", "0", "1.0", "2"),
        ],
    )

    candidate = _candidate_for_bids(root)

    plan = candidate.label_carrier_plan[0]
    run = candidate.bids["event_validation"]["runs"][0]
    assert set(plan["value_decisions"]) == {"0.0", "1.0"}
    assert plan["run_class_map"] == {"0.0": "0.0", "1.0": "1.0"}
    assert run["placement"]["status"] == "ready"
    assert {row["selected_label"] for row in run["row_evidence"]} == {"0.0", "1.0"}
    assert "unresolved_event_value_decisions" not in {
        issue["code"] for issue in run["issues"]
    }


def test_timestamp_label_apply_uses_per_run_mapping_instead_of_global_mapping(
    tmp_path: Path,
) -> None:
    events_1 = tmp_path / "sub-01_task-mi_run-1_events.tsv"
    events_2 = tmp_path / "sub-01_task-mi_run-2_events.tsv"
    for path in (events_1, events_2):
        path.write_text(
            "onset\tduration\ttrial_type\n1\t0\tT1\n",
            encoding="utf-8",
        )
    eeg_1 = tmp_path / "sub-01_task-mi_run-1_eeg.fif"
    eeg_2 = tmp_path / "sub-01_task-mi_run-2_eeg.fif"
    dataset = MagicMock()
    info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
    raw_1 = Raw(
        str(eeg_1),
        mne.io.RawArray(np.zeros((1, 300)), info, verbose=False),
    )
    raw_2 = Raw(
        str(eeg_2),
        mne.io.RawArray(np.zeros((1, 300)), info, verbose=False),
    )
    dataset.get_loaded_data_list.return_value = [raw_1, raw_2]
    service = DataInterpretationApplyService(
        dataset,
        data_filename=lambda raw: str(raw.get_filepath()),
        data_filepath=lambda raw: str(raw.get_filepath()),
        record_label_import=lambda **_kwargs: None,
    )
    candidate = InterpretationCandidate(
        candidate_id="candidate-1",
        scan_id="scan-1",
        source_path=str(tmp_path),
        source_kind="bids",
        selected_eeg_files=[str(eeg_1), str(eeg_2)],
        label_carriers=[str(events_1), str(events_2)],
        label_carrier_plan=[
            {
                "path": str(events_1),
                "name": events_1.name,
                "format": "BIDS events",
                "selected_label_field": "trial_type",
                "selected_anchor": "onset",
                "selected_duration_field": "duration",
                "time_model": "seconds",
                "placement_method": "interval",
                "granularity": "trial",
                "selected_target_file": str(eeg_1),
                "placement_review": {"status": "ready"},
            },
            {
                "path": str(events_2),
                "name": events_2.name,
                "format": "BIDS events",
                "selected_label_field": "trial_type",
                "selected_anchor": "onset",
                "selected_duration_field": "duration",
                "time_model": "seconds",
                "placement_method": "interval",
                "granularity": "trial",
                "selected_target_file": str(eeg_2),
                "placement_review": {"status": "ready"},
            },
        ],
        class_map={"T1": "global-wrong"},
        run_event_mappings={
            eeg_1.name: {"T1": "left hand"},
            eeg_2.name: {"T1": "right hand"},
        },
    )

    label_resources = LabelResourceAdmissionService(
        command_name="test_apply_interpretation"
    ).admit(
        [
            LabelResourceSpec(
                path=str(path),
                label_field="trial_type",
                anchor="onset",
                duration_field="duration",
            )
            for path in (events_1, events_2)
        ],
        confirmed=False,
        token=None,
    )

    result = service.apply_label_carriers(candidate, label_resources)

    assert result["status"] == "applied"
    assert raw_1.get_event_list()[1] == {"left hand": 1}
    assert raw_2.get_event_list()[1] == {"right hand": 1}
    dataset.apply_labels_batch.assert_not_called()
    hint_1 = raw_1.get_runtime_detail("data_interpretation_epoch_hint")
    hint_2 = raw_2.get_runtime_detail("data_interpretation_epoch_hint")
    assert isinstance(hint_1, dict)
    assert isinstance(hint_2, dict)
    assert hint_1["class_map"] == {"T1": "left hand"}
    assert hint_2["class_map"] == {"T1": "right hand"}
    assert hint_1["source"] == "BIDS events.tsv"
    assert hint_2["source"] == "BIDS events.tsv"


def test_bids_shaped_external_table_keeps_external_epoch_source() -> None:
    candidate = InterpretationCandidate(
        candidate_id="candidate-1",
        scan_id="scan-1",
        source_path="/data/recording.fif",
        source_kind="file",
    )

    source = DataInterpretationApplyService._epoch_hint_source(
        {"format": "BIDS events"},
        candidate=candidate,
    )

    assert source == "Loaded label file"


def test_internal_event_hints_use_each_run_mapping(tmp_path: Path) -> None:
    eeg_1 = tmp_path / "S001R04.edf"
    eeg_2 = tmp_path / "S001R08.edf"
    raw_1 = MagicMock()
    raw_1.get_filepath.return_value = str(eeg_1)
    raw_2 = MagicMock()
    raw_2.get_filepath.return_value = str(eeg_2)
    dataset = MagicMock()
    dataset.get_loaded_data_list.return_value = [raw_1, raw_2]
    service = DataInterpretationApplyService(
        dataset,
        data_filename=lambda raw: str(raw.get_filepath()),
        data_filepath=lambda raw: str(raw.get_filepath()),
        record_label_import=lambda **_kwargs: None,
    )
    candidate = InterpretationCandidate(
        candidate_id="candidate-1",
        scan_id="scan-1",
        source_path=str(tmp_path),
        source_kind="folder",
        selected_eeg_files=[str(eeg_1), str(eeg_2)],
        choices={"label_carrier": "embedded_events"},
        event_roles={"internal_events": "event role candidates"},
        class_map={},
        internal_event_selection={"label_event_codes": ["T1", "T2"]},
        run_event_mappings={
            eeg_1.name: {"T1": "left fist", "T2": "right fist"},
            eeg_2.name: {"T1": "both fists", "T2": "both feet"},
        },
    )

    records = service.record_internal_epoch_hints(candidate)

    assert len(records) == 2
    hint_1 = raw_1.set_runtime_detail.call_args.args[1]
    hint_2 = raw_2.set_runtime_detail.call_args.args[1]
    assert hint_1["class_map"] == {
        "T1": "left fist",
        "T2": "right fist",
    }
    assert hint_2["class_map"] == {
        "T1": "both fists",
        "T2": "both feet",
    }


def test_partial_internal_run_mapping_keeps_affected_run_in_confirmation_evidence(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "T1": {"count": 15, "description": "T1"},
                "T2": {"count": 15, "description": "T2"},
            }
        },
    )
    files = ["/data/S001R04.edf", "/data/S001R08.edf"]
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=ScanResult(
            scan_id="scan-1",
            source_path="/data",
            source_kind="folder",
            eeg_files=files,
            bids={"is_bids": False, "events_files": []},
        ),
        choices={
            "label_carrier": "embedded_events",
            "class_map": {"T1": "global-left", "T2": "global-right"},
            "run_event_mappings": {
                "S001R04.edf": {"T1": "left fist", "T2": "right fist"},
            },
        },
    )

    review = candidate.internal_event_preview["run_event_mapping_review"]

    assert review["status"] == "needs_confirmation"
    assert review["affected_files"] == ["S001R08.edf"]
    assert review["files"] == [
        {
            "file": "S001R04.edf",
            "run": "04",
            "status": "safe",
            "events": {"T1": "left fist", "T2": "right fist"},
            "missing_event_codes": [],
        },
        {
            "file": "S001R08.edf",
            "run": "08",
            "status": "needs_confirmation",
            "events": {"T1": "", "T2": ""},
            "missing_event_codes": ["T1", "T2"],
        },
    ]
    assert any(
        "S001R08.edf" in item and "T1, T2" in item
        for item in candidate.confirmation_items
    )

    raw_1 = MagicMock()
    raw_1.get_filepath.return_value = files[0]
    raw_2 = MagicMock()
    raw_2.get_filepath.return_value = files[1]
    dataset = MagicMock()
    dataset.get_loaded_data_list.return_value = [raw_1, raw_2]
    apply_service = DataInterpretationApplyService(
        dataset,
        data_filename=lambda raw: str(raw.get_filepath()),
        data_filepath=lambda raw: str(raw.get_filepath()),
        record_label_import=lambda **_kwargs: None,
    )

    records = apply_service.record_internal_epoch_hints(candidate)

    assert len(records) == 2
    assert raw_1.set_runtime_detail.call_args.args[1]["class_map"] == {
        "T1": "left fist",
        "T2": "right fist",
    }
    assert raw_2.set_runtime_detail.call_args.args[1]["class_map"] == {
        "T1": "T1",
        "T2": "T2",
    }

    applied = AppliedInterpretation(
        interpretation_id="interpretation-1",
        candidate_id=candidate.candidate_id,
        source_path=candidate.source_path,
        source_kind=candidate.source_kind,
        loaded_files=files,
        event_roles=dict(candidate.event_roles),
        class_map=dict(candidate.class_map),
        internal_event_selection=dict(candidate.internal_event_selection),
        run_event_mappings={
            key: dict(mapping) for key, mapping in candidate.run_event_mappings.items()
        },
    )

    handoff = DataInterpretationSessionState._epoch_handoff(None, applied)

    assert handoff["class_map"] == {}
    assert "event_label_aliases" not in handoff
    assert handoff["default_epoch_events"] == ["T1", "T2"]
    assert handoff["run_dependent_mapping"] is True
