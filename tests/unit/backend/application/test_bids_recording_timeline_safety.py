"""Regression coverage for BIDS recording timeline placement safety."""

from __future__ import annotations

import json
from pathlib import Path

import mne
import numpy as np
import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    PreviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.application.data_interpretation_bids import (
    review_strict_bids_event_runs,
)
from XBrainLab.backend.application.data_interpretation_bids_resources import (
    bids_eeg_json_resources_by_recording,
)
from XBrainLab.backend.application.data_interpretation_content_identity import (
    assert_review_content_unchanged,
    build_review_content_identity,
)
from XBrainLab.backend.application.data_interpretation_event_values import RESOLVED
from XBrainLab.backend.application.errors import PreconditionError


def _write_bids_run(
    root: Path,
    *,
    recording_type: str,
    write_sidecar: bool = True,
) -> tuple[Path, Path, Path]:
    root.mkdir(parents=True)
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "timeline-safety", "BIDSVersion": "1.11.1"}),
        encoding="utf-8",
    )
    eeg_dir = root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    stem = "sub-01_task-mi_run-01"
    eeg_path = eeg_dir / f"{stem}_eeg.fif"
    events_path = eeg_dir / f"{stem}_events.tsv"
    sidecar_path = eeg_dir / f"{stem}_eeg.json"
    raw = mne.io.RawArray(
        np.zeros((1, 1_000)),
        mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg"),
        verbose="ERROR",
    )
    raw.save(eeg_path, overwrite=True, verbose="ERROR")
    events_path.write_text(
        "onset\tduration\ttrial_type\n1\t0\tleft\n",
        encoding="utf-8",
    )
    if write_sidecar:
        sidecar_path.write_text(
            json.dumps({"RecordingType": recording_type, "EpochLength": 1.0}),
            encoding="utf-8",
        )
    return eeg_path.resolve(), events_path.resolve(), sidecar_path.resolve()


@pytest.mark.parametrize(
    ("recording_type", "expected_status"),
    [("continuous", "ready"), ("epoched", "blocked"), ("discontinuous", "blocked")],
)
def test_timestamp_placement_respects_bids_recording_timeline(
    tmp_path: Path,
    recording_type: str,
    expected_status: str,
) -> None:
    eeg_path, events_path, sidecar_path = _write_bids_run(
        tmp_path / "bids", recording_type=recording_type
    )

    review = review_strict_bids_event_runs(
        bids={
            "is_bids": True,
            "layout": [
                {
                    "file": str(eeg_path),
                    "events_file": str(events_path),
                    "eeg_json_files": [str(sidecar_path)],
                }
            ],
        },
        selected_eeg_files=[str(eeg_path)],
        label_carrier_plan=[
            {
                "path": str(events_path),
                "selected_label_field": "trial_type",
                "placement_method": "time_field",
                "value_decisions": {
                    "left": {
                        "decision": RESOLVED,
                        "role": "stimulus",
                        "keep_event": True,
                        "use_as_class": True,
                        "class_name": "left",
                    }
                },
            }
        ],
    )

    run = review.evidence["runs"][0]
    assert run["placement"]["status"] == expected_status
    issue_codes = {issue["code"] for issue in run["issues"]}
    if recording_type == "continuous":
        assert (
            "unsupported_bids_recording_type_for_timestamp_placement" not in issue_codes
        )
    else:
        assert "unsupported_bids_recording_type_for_timestamp_placement" in issue_codes


def test_eeg_json_inheritance_catalog_is_scoped_and_ordered(tmp_path: Path) -> None:
    eeg_path, _events_path, local = _write_bids_run(
        tmp_path / "bids", recording_type="continuous"
    )
    root = eeg_path.parents[2]
    generic = root / "eeg.json"
    task = root / "task-mi_eeg.json"
    generic.write_text('{"RecordingType":"continuous"}', encoding="utf-8")
    task.write_text('{"RecordingType":"continuous"}', encoding="utf-8")
    unrelated = root / "task-other_eeg.json"
    unrelated.write_text('{"RecordingType":"epoched"}', encoding="utf-8")

    catalog = bids_eeg_json_resources_by_recording(
        {
            "root": str(root),
            "json_sidecar_files": [
                str(unrelated),
                str(local),
                str(task),
                str(generic),
            ],
        },
        [str(eeg_path)],
    )

    assert catalog[str(eeg_path)] == (
        str(generic),
        str(task),
        str(local),
    )


def test_eeg_json_catalog_does_not_cross_recording_entity(tmp_path: Path) -> None:
    root = tmp_path / "bids"
    eeg_dir = root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "timeline-safety", "BIDSVersion": "1.11.1"}),
        encoding="utf-8",
    )
    alpha = eeg_dir / "sub-01_task-mi_recording-alpha_eeg.fif"
    beta = eeg_dir / "sub-01_task-mi_recording-beta_eeg.fif"
    alpha.write_bytes(b"raw")
    beta.write_bytes(b"raw")
    alpha_sidecar = eeg_dir / "sub-01_task-mi_recording-alpha_eeg.json"
    alpha_sidecar.write_text('{"RecordingType":"epoched"}', encoding="utf-8")

    catalog = bids_eeg_json_resources_by_recording(
        {"root": str(root), "json_sidecar_files": [str(alpha_sidecar)]},
        [str(alpha), str(beta)],
    )

    assert catalog[str(alpha)] == (str(alpha_sidecar),)
    assert catalog[str(beta)] == ()


def test_eeg_timeline_sidecar_is_bound_to_review_content(tmp_path: Path) -> None:
    sidecar = tmp_path / "sub-01_task-mi_eeg.json"
    sidecar.write_text('{"RecordingType":"continuous"}', encoding="utf-8")
    expected = build_review_content_identity(
        label_carrier_plan=[],
        bids_eeg_json_files=[str(sidecar)],
    )
    reviewed_size = sidecar.stat().st_size
    sidecar.write_text('{"RecordingType":"epoched"}   ', encoding="utf-8")
    assert sidecar.stat().st_size == reviewed_size

    with pytest.raises(PreconditionError) as raised:
        assert_review_content_unchanged(
            expected=expected,
            label_carrier_plan=[],
        )

    assert raised.value.diagnostics["reason"] == (
        "reviewed_content_or_contract_changed"
    )


def _timestamp_choices(events_path: Path) -> dict[str, object]:
    return {
        "label_carrier_choices": {
            str(events_path): {
                "label_field": "trial_type",
                "anchor": "onset",
                "duration_field": "duration",
                "time_model": "seconds",
                "placement_method": "interval",
                "value_decisions": {
                    "left": {
                        "role": "stimulus",
                        "keep_event": True,
                        "use_as_class": True,
                        "class_name": "left",
                    }
                },
            }
        }
    }


def test_candidate_blocks_epoched_bids_before_mutating_data(tmp_path: Path) -> None:
    root = tmp_path / "bids"
    eeg_path, events_path, _sidecar = _write_bids_run(root, recording_type="epoched")
    service = ApplicationService()
    try:
        assert service.execute(
            ScanSourceCommand(source_path=str(root), source_hint="bids")
        ).ok
        preview = service.execute(
            PreviewInterpretationCommand(
                choices={
                    "selected_eeg_files": [str(eeg_path)],
                    **_timestamp_choices(events_path),
                }
            )
        )
        validation = service.execute(ValidateInterpretationCommand())
        applied = service.execute(ApplyInterpretationCommand(confirmed=True))

        run = preview.diagnostics["preview"]["bids"]["event_validation"]["runs"][0]
        assert preview.ok is True
        assert run["recording_timeline"]["recording_type"] == "epoched"
        assert run["placement"]["status"] == "blocked"
        assert {
            row["role"]
            for row in preview.diagnostics["preview"]["content_identity"]["files"]
        } >= {"selected_eeg", "label_carrier", "bids_eeg_json"}
        assert validation.diagnostics["validation_decision"]["decision"] == "blocked"
        assert applied.failed is True
        assert applied.state.raw.count == 0
    finally:
        service.close()


def test_candidate_rejects_timeline_sidecar_change_after_preview(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    eeg_path, events_path, sidecar = _write_bids_run(root, recording_type="continuous")
    (root / "eeg.json").write_text(
        json.dumps({"RecordingType": "epoched", "EpochLength": 1.0}),
        encoding="utf-8",
    )
    service = ApplicationService()
    try:
        assert service.execute(
            ScanSourceCommand(source_path=str(root), source_hint="bids")
        ).ok
        preview = service.execute(
            PreviewInterpretationCommand(
                choices={
                    "selected_eeg_files": [str(eeg_path)],
                    **_timestamp_choices(events_path),
                }
            )
        )
        reviewed_size = sidecar.stat().st_size
        sidecar.write_text(
            json.dumps({"RecordingType": "continuous", "EpochLength": 2.0}),
            encoding="utf-8",
        )
        assert sidecar.stat().st_size == reviewed_size

        validation = service.execute(ValidateInterpretationCommand())

        assert preview.ok is True
        preview_run = preview.diagnostics["preview"]["bids"]["event_validation"][
            "runs"
        ][0]
        assert preview_run["recording_timeline"]["recording_type"] == "continuous"
        assert validation.ok is True
        decision = validation.diagnostics["validation_decision"]
        assert decision["decision"] == "blocked"
        assert any(
            "changed after preview" in item.lower()
            for item in decision["blocked_reasons"]
        )
        assert validation.state.raw.count == 0
    finally:
        service.close()


def test_candidate_rejects_new_timeline_sidecar_after_preview(tmp_path: Path) -> None:
    root = tmp_path / "bids"
    eeg_path, events_path, sidecar = _write_bids_run(
        root,
        recording_type="continuous",
        write_sidecar=False,
    )
    service = ApplicationService()
    try:
        assert service.execute(
            ScanSourceCommand(source_path=str(root), source_hint="bids")
        ).ok
        preview = service.execute(
            PreviewInterpretationCommand(
                choices={
                    "selected_eeg_files": [str(eeg_path)],
                    **_timestamp_choices(events_path),
                }
            )
        )
        sidecar.write_text(
            json.dumps({"RecordingType": "epoched", "EpochLength": 1.0}),
            encoding="utf-8",
        )

        validation = service.execute(ValidateInterpretationCommand())

        assert preview.ok is True
        assert validation.diagnostics["validation_decision"]["decision"] == "blocked"
        assert validation.state.raw.count == 0
    finally:
        service.close()


def test_apply_rejects_new_timeline_sidecar_after_validation(tmp_path: Path) -> None:
    root = tmp_path / "bids"
    eeg_path, events_path, sidecar = _write_bids_run(
        root,
        recording_type="continuous",
        write_sidecar=False,
    )
    service = ApplicationService()
    try:
        assert service.execute(
            ScanSourceCommand(source_path=str(root), source_hint="bids")
        ).ok
        assert service.execute(
            PreviewInterpretationCommand(
                choices={
                    "selected_eeg_files": [str(eeg_path)],
                    **_timestamp_choices(events_path),
                }
            )
        ).ok
        assert (
            service.execute(ValidateInterpretationCommand()).diagnostics[
                "validation_decision"
            ]["decision"]
            == "safe"
        )
        sidecar.write_text(
            json.dumps({"RecordingType": "epoched", "EpochLength": 1.0}),
            encoding="utf-8",
        )

        applied = service.execute(ApplyInterpretationCommand(confirmed=True))

        assert applied.failed is True
        assert (
            applied.diagnostics["code"] == "bids_dataset_structure_changed_after_review"
        )
        assert applied.state.raw.count == 0
    finally:
        service.close()
