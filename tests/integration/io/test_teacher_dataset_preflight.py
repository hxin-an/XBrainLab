"""Local-only larger dataset gate used before a teacher walkthrough."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest

from scripts.dev.fetch_public_eeg_fixtures import (
    fixture_file_is_valid,
    fixture_groups_for_profile,
    resolve_public_fixture_dir,
)
from scripts.dev.report_teacher_dataset_preflight import (
    build_teacher_preflight_snapshot,
)

pytestmark = pytest.mark.optional_public_fixture

ROOT = Path(__file__).resolve().parents[3]
PUBLIC_DIR = resolve_public_fixture_dir()
TEACHER_ENTRYPOINTS = (
    PUBLIC_DIR
    / "openneuro-ds003061-p300"
    / "sub-001"
    / "eeg"
    / "sub-001_task-P300_run-1_eeg.set",
    PUBLIC_DIR / "chbmit-chb01" / "chb01_03.edf",
    PUBLIC_DIR / "sleep-edfx-st7011" / "ST7011J0-PSG.edf",
)


def _profile_is_fully_valid(profile: str, fixture_dir: Path) -> bool:
    """Return whether every pinned file for one named profile is available."""
    return all(
        fixture_file_is_valid(
            fixture_dir / str(fixture_file["filename"]),
            str(fixture_file["sha256"]),
            int(fixture_file["size_bytes"]),
        )
        for group in fixture_groups_for_profile(profile)
        for fixture_file in group["files"]
    )


def _teacher_fixture_missing_state(
    fixture_dir: Path,
) -> Literal["partial-teacher", "valid-required-ci", "absent"]:
    """Classify missing teacher entrypoints from the pinned profile definitions."""
    required_group_names = {
        str(group["name"]) for group in fixture_groups_for_profile("required-ci")
    }
    teacher_only_files = (
        fixture_file
        for group in fixture_groups_for_profile("teacher-preflight")
        if str(group["name"]) not in required_group_names
        for fixture_file in group["files"]
    )
    if any(
        (fixture_dir / str(fixture_file["filename"])).exists()
        for fixture_file in teacher_only_files
    ):
        return "partial-teacher"
    if _profile_is_fully_valid("required-ci", fixture_dir):
        return "valid-required-ci"
    return "absent"


def test_teacher_dataset_preflight_real_application_workflows() -> None:
    missing = [str(path) for path in TEACHER_ENTRYPOINTS if not path.exists()]
    if missing:
        missing_state = _teacher_fixture_missing_state(PUBLIC_DIR)
        if missing_state == "partial-teacher":
            pytest.fail(
                "Teacher preflight fixture cache is partially installed. "
                "Re-run the pinned teacher-preflight download/verification. "
                "Missing: " + ", ".join(missing)
            )
        if missing_state == "valid-required-ci":
            pytest.skip(
                "Only the independently valid required-ci fixture profile is "
                "installed; teacher-preflight fixtures are local-only. Missing: "
                + ", ".join(missing)
            )
        pytest.skip(
            "Teacher preflight fixtures are local-only; download them with "
            "`scripts/dev/fetch_public_eeg_fixtures.py --profile "
            "teacher-preflight`. Missing: " + ", ".join(missing)
        )
    snapshot = build_teacher_preflight_snapshot(ROOT)
    results = {result["case_id"]: result for result in snapshot["results"]}

    assert snapshot["manifest"]["all_files_verified"] is True
    assert snapshot["manifest"]["group_count"] == 10
    assert snapshot["manifest"]["size_bytes"] == 277_106_963
    assert snapshot["summary"]["strict_ok"] is True
    assert snapshot["summary"]["passed_required_case_count"] == 3
    assert (
        results["openneuro_p300_bids"]["stages"]["post_apply_background"]["ok"] is True
    )
    assert results["openneuro_p300_bids"]["observations"]["usable_events_by_run"] == [
        747,
        750,
        748,
    ]
    assert results["openneuro_p300_bids"]["observations"]["supervised_ready"] is True
    assert (
        results["openneuro_p300_bids"]["observations"]["event_timing_all_match"] is True
    )
    timing_checks = results["openneuro_p300_bids"]["observations"][
        "event_timing_checks"
    ]
    assert len(timing_checks) == 3
    assert all(
        check["source_sample_label_digest"] == check["stored_sample_label_digest"]
        for check in timing_checks
    )
    assert results["openneuro_p300_bids"]["observations"]["epoch_count"] == 2_243
    assert (
        results["openneuro_p300_bids"]["observations"]["boundary_events_excluded"] == 2
    )
    assert results["openneuro_p300_bids"]["observations"]["epoch_event_ids"] == [
        "noise",
        "oddball",
        "standard",
    ]
    assert results["openneuro_p300_bids"]["observations"]["stored_events_by_run"] == [
        {
            "file": "sub-001_task-P300_run-1_eeg.set",
            "count": 747,
            "labels": ["noise", "oddball", "standard"],
        },
        {
            "file": "sub-001_task-P300_run-2_eeg.set",
            "count": 750,
            "labels": ["noise", "oddball", "standard"],
        },
        {
            "file": "sub-001_task-P300_run-3_eeg.set",
            "count": 748,
            "labels": ["noise", "oddball", "standard"],
        },
    ]
    assert results["chbmit_raw_edf"]["observations"]["supervised_ready"] is False
    assert results["chbmit_raw_edf"]["observations"]["label_carriers"] == []
    assert results["chbmit_raw_edf"]["observations"]["context_format"] == (
        "Seizure annotation sidecar"
    )
    assert results["chbmit_raw_edf"]["observations"]["context_status"] == "unsupported"
    assert (
        results["sleep_edfx_psg"]["observations"]["context_format"]
        == "EDF+ annotations"
    )
    assert results["sleep_edfx_psg"]["observations"]["supervised_ready"] is False
    assert (
        results["sleep_edfx_psg"]["observations"]["sidecar_evidence"][
            "annotation_count"
        ]
        == 231
    )


def test_missing_teacher_entrypoints_allow_a_valid_required_ci_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    required_files = {
        tmp_path / str(fixture_file["filename"])
        for group in fixture_groups_for_profile("required-ci")
        for fixture_file in group["files"]
    }
    monkeypatch.setattr(
        "tests.integration.io.test_teacher_dataset_preflight.fixture_file_is_valid",
        lambda path, _sha256, _size_bytes: path in required_files,
    )

    assert _teacher_fixture_missing_state(tmp_path) == "valid-required-ci"


def test_missing_teacher_entrypoints_reject_partial_teacher_profile(
    tmp_path: Path,
) -> None:
    required_group_names = {
        str(group["name"]) for group in fixture_groups_for_profile("required-ci")
    }
    teacher_only_file = next(
        fixture_file
        for group in fixture_groups_for_profile("teacher-preflight")
        if str(group["name"]) not in required_group_names
        for fixture_file in group["files"]
    )
    path = tmp_path / str(teacher_only_file["filename"])
    path.parent.mkdir(parents=True)
    path.touch()

    assert _teacher_fixture_missing_state(tmp_path) == "partial-teacher"
