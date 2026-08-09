"""Optional real-data evidence for multi-subject BIDS selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    ReviewInterpretationCommand,
    ScanSourceCommand,
)

OPENNEURO_P300_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "data"
    / "public"
    / "openneuro-ds003061-p300"
)
ALL_SUBJECTS = ("001", "002", "003")
RUNS = (1, 2, 3)

pytestmark = pytest.mark.optional_public_fixture


@pytest.fixture(scope="module", autouse=True)
def _require_multisubject_extension() -> None:
    missing_subjects = [
        subject
        for subject in ("002", "003")
        if not (OPENNEURO_P300_ROOT / f"sub-{subject}").is_dir()
    ]
    if missing_subjects:
        pytest.skip(
            "Optional OpenNeuro ds003061 multi-subject fixture is not installed; "
            "fetch profile p300-multisubject first."
        )


def _run_paths(subjects: tuple[str, ...], suffix: str) -> list[str]:
    return [
        str(
            (
                OPENNEURO_P300_ROOT
                / f"sub-{subject}"
                / "eeg"
                / f"sub-{subject}_task-P300_run-{run}_{suffix}"
            ).resolve()
        )
        for subject in subjects
        for run in RUNS
    ]


def _selected_scope(subjects: tuple[str, ...]) -> dict[str, object]:
    return {
        "eeg_file_count": len(subjects) * len(RUNS),
        "subjects": list(subjects),
        "sessions": [],
        "tasks": ["P300"],
        "runs": [str(run) for run in RUNS],
        "datatypes": ["eeg"],
        "eeg_files": _run_paths(subjects, "eeg.set"),
        "events_files": _run_paths(subjects, "events.tsv"),
        "channels_files": _run_paths(subjects, "channels.tsv"),
    }


def _subjects_in_paths(paths: list[str]) -> set[str]:
    return {
        part.removeprefix("sub-")
        for path in paths
        for part in Path(path).parent.parts
        if part.startswith("sub-")
    }


def test_catalog_reports_three_complete_subjects_and_nine_recordings() -> None:
    result = ApplicationService().execute(
        ScanSourceCommand(
            source_path=str(OPENNEURO_P300_ROOT),
            source_hint="bids",
            catalog_only=True,
        )
    )

    assert result.ok, result.message
    catalog = result.diagnostics["bids_subject_catalog"]
    assert catalog == {
        "root": str(OPENNEURO_P300_ROOT.resolve()),
        "subject_count": 3,
        "eeg_file_count": 9,
        "subjects": [
            {
                "subject": subject,
                "label": f"sub-{subject}",
                "eeg_file_count": 3,
                "sessions": [],
                "tasks": ["P300"],
                "runs": ["1", "2", "3"],
            }
            for subject in ALL_SUBJECTS
        ],
        "warnings": [],
    }


@pytest.mark.parametrize(
    "subjects",
    [("001",), ("002",), ("003",), ("002", "003")],
    ids=["subject-001", "subject-002", "subject-003", "subjects-002-003"],
)
def test_scan_uses_only_the_exact_selected_subject_scope(
    subjects: tuple[str, ...],
) -> None:
    result = ApplicationService().execute(
        ScanSourceCommand(
            source_path=str(OPENNEURO_P300_ROOT),
            source_hint="bids",
            selected_bids_subjects=list(subjects),
        )
    )

    assert result.ok, result.message
    scan = result.diagnostics["scan_result"]
    expected_scope = _selected_scope(subjects)
    expected_eeg_files = expected_scope["eeg_files"]
    expected_events_files = expected_scope["events_files"]
    assert isinstance(expected_eeg_files, list)
    assert isinstance(expected_events_files, list)

    assert scan["eeg_files"] == expected_eeg_files
    assert scan["label_carriers"] == expected_events_files
    assert scan["bids"]["selected_scope"] == expected_scope


def test_review_pairs_events_only_with_selected_subjects_002_and_003() -> None:
    subjects = ("002", "003")
    result = ApplicationService().execute(
        ReviewInterpretationCommand(
            source_path=str(OPENNEURO_P300_ROOT),
            source_hint="bids",
            choices={"selected_bids_subjects": list(subjects)},
        )
    )

    assert result.ok, result.message
    scan = result.diagnostics["scan_result"]
    candidate = result.diagnostics["candidate"]
    preview = result.diagnostics["preview"]
    expected_scope = _selected_scope(subjects)
    expected_eeg_files = expected_scope["eeg_files"]
    expected_events_files = expected_scope["events_files"]
    assert isinstance(expected_eeg_files, list)
    assert isinstance(expected_events_files, list)

    assert scan["eeg_files"] == expected_eeg_files
    assert scan["label_carriers"] == expected_events_files
    assert scan["bids"]["selected_scope"] == expected_scope
    assert candidate["selected_eeg_files"] == expected_eeg_files
    assert candidate["label_carriers"] == expected_events_files
    assert preview["bids"]["selected_scope"] == expected_scope

    event_review = preview["bids"]["event_validation"]
    expected_pairing = dict(zip(expected_eeg_files, expected_events_files, strict=True))
    assert event_review["file_mapping"] == expected_pairing
    assert event_review["pairing_issues"] == []
    assert [
        (run["eeg_file"], run["events_file"]) for run in event_review["runs"]
    ] == list(expected_pairing.items())

    reviewed_paths = [
        *event_review["file_mapping"].keys(),
        *event_review["file_mapping"].values(),
    ]
    assert _subjects_in_paths(reviewed_paths) == set(subjects)
