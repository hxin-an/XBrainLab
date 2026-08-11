"""Responsiveness contract for the real OpenNeuro ds003061 P300 fixture."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    PreviewInterpretationCommand,
    ReviewInterpretationCommand,
    ScanSourceCommand,
    data_interpretation_content_identity,
    resource_guard,
)
from XBrainLab.backend.study import Study

OPENNEURO_P300_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "data"
    / "public"
    / "openneuro-ds003061-p300"
)

pytestmark = pytest.mark.optional_public_fixture


def _timed_execute(service: ApplicationService, command):
    started_at = time.perf_counter()
    result = service.execute(command)
    return time.perf_counter() - started_at, result


def test_openneuro_p300_catalog_scan_and_preview_stay_bounded() -> None:
    if not OPENNEURO_P300_ROOT.exists():
        pytest.skip("OpenNeuro ds003061 P300 fixture is not installed.")

    service = ApplicationService(Study())
    catalog_seconds, catalog = _timed_execute(
        service,
        ScanSourceCommand(
            source_path=str(OPENNEURO_P300_ROOT),
            source_hint="bids",
            catalog_only=True,
        ),
    )
    catalog_publication = service.get_view_publication()
    scan_seconds, scan = _timed_execute(
        service,
        ScanSourceCommand(
            source_path=str(OPENNEURO_P300_ROOT),
            source_hint="bids",
            selected_bids_subjects=["001"],
        ),
    )
    choices = {"selected_bids_subjects": ["001"]}
    first_preview_seconds, first_preview = _timed_execute(
        service,
        PreviewInterpretationCommand(
            scan_id=scan.diagnostics["scan_result"]["scan_id"],
            choices=choices,
        ),
    )
    repeated_preview_seconds, repeated_preview = _timed_execute(
        service,
        PreviewInterpretationCommand(
            scan_id=scan.diagnostics["scan_result"]["scan_id"],
            choices=choices,
        ),
    )

    assert catalog.ok and scan.ok and first_preview.ok and repeated_preview.ok
    catalog_payload = catalog.diagnostics["bids_subject_catalog"]
    assert catalog_payload["subject_count"] >= 1
    assert "001" in {subject["subject"] for subject in catalog_payload["subjects"]}
    assert catalog_publication.generation == 1
    assert catalog_publication.revision == 1
    assert scan.diagnostics["scan_result"]["eeg_files"] == [
        str(
            OPENNEURO_P300_ROOT
            / "sub-001"
            / "eeg"
            / f"sub-001_task-P300_run-{run}_eeg.set"
        )
        for run in (1, 2, 3)
    ]
    assert (
        repeated_preview.diagnostics["resource_preflight"]["admission_cache_reused"]
        is True
    )

    runs = first_preview.diagnostics["preview"]["bids"]["event_validation"]["runs"]
    assert len(runs) == 3
    assert all(run["event_count"] > 800 for run in runs)
    assert all(run["issue_count"] > 800 for run in runs)
    assert all(len(run["issues"]) == 12 for run in runs)
    assert len(json.dumps(first_preview.diagnostics)) < 300_000
    assert len(json.dumps(first_preview.state.to_dict())) < 200_000

    # These ceilings detect accidental synchronous-scale regressions while
    # tolerating cold WSL/NTFS metadata and shared CI load.
    assert catalog_seconds < 2.0
    assert scan_seconds < 8.0
    assert first_preview_seconds < 8.0
    assert repeated_preview_seconds < 4.0


def test_openneuro_subject_review_never_materializes_unselected_subjects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not OPENNEURO_P300_ROOT.exists():
        pytest.skip("OpenNeuro ds003061 P300 fixture is not installed.")

    inspected_headers: list[Path] = []
    fingerprinted_files: list[Path] = []
    original_inspect = resource_guard.inspect_eeglab_set_header
    original_fingerprint = data_interpretation_content_identity._stable_stream_sha256

    def _assert_selected(path: str | Path) -> Path:
        resolved = Path(path).resolve()
        relative = resolved.relative_to(OPENNEURO_P300_ROOT.resolve())
        if relative.parts[0].startswith("sub-"):
            assert relative.parts[0] == "sub-001"
        return resolved

    def _inspect_selected(path: str | Path):
        resolved = _assert_selected(path)
        inspected_headers.append(resolved)
        return original_inspect(path)

    def _fingerprint_selected(path: Path) -> tuple[int, str]:
        resolved = _assert_selected(path)
        fingerprinted_files.append(resolved)
        return original_fingerprint(path)

    monkeypatch.setattr(resource_guard, "inspect_eeglab_set_header", _inspect_selected)
    monkeypatch.setattr(
        data_interpretation_content_identity,
        "_stable_stream_sha256",
        _fingerprint_selected,
    )

    service = ApplicationService(Study())
    review_seconds, review = _timed_execute(
        service,
        ReviewInterpretationCommand(
            source_path=str(OPENNEURO_P300_ROOT),
            source_hint="bids",
            choices={"selected_bids_subjects": ["001"]},
        ),
    )

    selected_eeg_files = {
        path.resolve()
        for path in (OPENNEURO_P300_ROOT / "sub-001" / "eeg").glob("*_eeg.set")
    }
    assert review.ok
    assert set(inspected_headers) == selected_eeg_files
    assert selected_eeg_files <= set(fingerprinted_files)
    assert len(review.diagnostics["preview"]["bids"]["event_validation"]["runs"]) == 3
    assert review_seconds < 15.0
