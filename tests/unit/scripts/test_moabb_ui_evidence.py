from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PIL import Image

from scripts.dev.moabb_ui_evidence.contract import (
    ARTIFACT_TYPE,
    build_capture_manifest,
    require_build_output_path,
    validate_capture_manifest,
)

DATASET_IDS = (
    "ofner2017-mi-gdf",
    "physionetmi-edf-run-semantics",
    "lee2021mobile-erp-brainvision",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_png(
    path: Path,
    color: tuple[int, int, int],
    *,
    relative_to: Path,
) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (96, 64), color).save(path)
    return {
        "path": path.relative_to(relative_to).as_posix(),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
        "dimensions": [96, 64],
        "format": "PNG",
    }


def _source_file(path: Path, content: bytes) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "path": str(path.resolve()),
        "size_bytes": len(content),
        "sha256": _sha256(path),
        "expected_checksum": {"algorithm": "sha256", "value": _sha256(path)},
        "url": "https://example.test/source",
    }


def _dataset_record(root: Path, dataset_id: str) -> dict[str, object]:
    dataset_dir = root / dataset_id
    source = _source_file(dataset_dir / "source.edf", dataset_id.encode())
    evidence_path = dataset_dir / "journey-evidence.json"
    evidence_path.write_text('{"status":"completed"}\n', encoding="utf-8")
    import_shot = _write_png(
        dataset_dir / "import-review.png", (24, 80, 120), relative_to=root
    )
    evaluation_shot = _write_png(
        dataset_dir / "evaluation.png", (80, 120, 24), relative_to=root
    )
    saliency_shot = _write_png(
        dataset_dir / "saliency.png", (120, 24, 80), relative_to=root
    )
    return {
        "dataset_id": dataset_id,
        "dataset_revision": hashlib.sha256(dataset_id.encode()).hexdigest(),
        "exact_source": {
            "status": "verified",
            "plan_id": "plan-123",
            "files": [source],
        },
        "execution": {
            "profile": "smoke",
            "status": "completed",
            "evidence_path": evidence_path.relative_to(root).as_posix(),
            "evidence_sha256": _sha256(evidence_path),
            "quality_evidence_status": "pending",
        },
        "stages": {
            "import_review": {
                "status": "observed",
                "application_service_commands": [
                    "scan_source",
                    "preview_interpretation",
                    "validate_interpretation",
                ],
                "application_state": {"interpretation": {"has_preview": True}},
                "screenshot": import_shot,
            },
            "evaluation": {
                "status": "bounded",
                "application_service_commands": ["evaluate"],
                "split": "test",
                "sample_count": 8,
                "class_count": 2,
                "expected_class_labels": ["left", "right"],
                "observed_class_labels": ["left", "right"],
                "route_semantics_match": True,
                "screenshot": evaluation_shot,
            },
            "saliency": {
                "status": "bounded",
                "application_service_commands": ["saliency"],
                "method": "Gradient",
                "source_split": "test",
                "route_semantics_match": True,
                "render_evidence": {
                    "axes_count": 2,
                    "image_count": 2,
                    "canvas_visible": True,
                    "explanation_context": "dataset - Fold 1 - Run 1",
                },
                "screenshot": saliency_shot,
            },
        },
        "limitations": [],
    }


def _manifest(root: Path) -> dict[str, object]:
    records = [_dataset_record(root, dataset_id) for dataset_id in DATASET_IDS]
    return build_capture_manifest(
        run_id="capture-20260809",
        registry_sha256=hashlib.sha256(b"registry").hexdigest(),
        registry_profile="moabb-compact-user-journeys-v1",
        plan_id="plan-123",
        application_source={
            "commit_sha": "a" * 40,
            "source_digest": hashlib.sha256(b"source").hexdigest(),
            "dirty": False,
        },
        qt_platform="offscreen",
        datasets=records,
    )


def test_complete_exact_source_capture_is_bounded_and_valid(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)

    assert manifest["artifact_type"] == ARTIFACT_TYPE
    assert manifest["status"] == "completed"
    assert manifest["site_qualification"] == {
        "eligible": True,
        "publication_status_ceiling": "bounded",
        "reason_codes": [],
    }
    assert validate_capture_manifest(manifest, output_dir=tmp_path) == (True, "")


def test_unverified_placeholder_can_never_qualify_site(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    saliency = manifest["datasets"][0]["stages"]["saliency"]
    saliency["status"] = "UNVERIFIED"
    saliency["placeholder"] = True

    ok, reason = validate_capture_manifest(manifest, output_dir=tmp_path)

    assert not ok
    assert "UNVERIFIED" in reason


def test_missing_exact_source_file_fails_closed(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    source_path = Path(manifest["datasets"][1]["exact_source"]["files"][0]["path"])
    source_path.unlink()

    ok, reason = validate_capture_manifest(manifest, output_dir=tmp_path)

    assert not ok
    assert "exact-source" in reason


def test_missing_final_stage_forces_unverified_site_ceiling(tmp_path: Path) -> None:
    records = [_dataset_record(tmp_path, dataset_id) for dataset_id in DATASET_IDS]
    records[2]["stages"]["saliency"] = {
        "status": "unverified",
        "reason": "ApplicationService saliency evidence is unavailable.",
    }

    manifest = build_capture_manifest(
        run_id="capture-partial",
        registry_sha256=hashlib.sha256(b"registry").hexdigest(),
        registry_profile="moabb-compact-user-journeys-v1",
        plan_id="plan-123",
        application_source={
            "commit_sha": "a" * 40,
            "source_digest": hashlib.sha256(b"source").hexdigest(),
            "dirty": False,
        },
        qt_platform="offscreen",
        datasets=records,
    )

    assert manifest["status"] == "partial"
    assert manifest["site_qualification"]["eligible"] is False
    assert manifest["site_qualification"]["publication_status_ceiling"] == "unverified"
    assert validate_capture_manifest(manifest, output_dir=tmp_path) == (True, "")


def test_output_path_must_remain_under_repo_build(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    build_root = repo_root / "build"
    build_root.mkdir(parents=True)

    assert (
        require_build_output_path(build_root / "moabb-ui", repo_root=repo_root)
        == (build_root / "moabb-ui").resolve()
    )
    with pytest.raises(ValueError, match="repo build"):
        require_build_output_path(tmp_path / "outside", repo_root=repo_root)


def test_source_change_during_capture_prevents_site_qualification(
    tmp_path: Path,
) -> None:
    records = [_dataset_record(tmp_path, dataset_id) for dataset_id in DATASET_IDS]
    start = {
        "commit_sha": "a" * 40,
        "source_digest": hashlib.sha256(b"source-before").hexdigest(),
        "dirty": False,
    }
    completed = {
        "commit_sha": "a" * 40,
        "source_digest": hashlib.sha256(b"source-after").hexdigest(),
        "dirty": False,
    }

    manifest = build_capture_manifest(
        run_id="capture-source-changed",
        registry_sha256=hashlib.sha256(b"registry").hexdigest(),
        registry_profile="moabb-compact-user-journeys-v1",
        plan_id="plan-123",
        application_source=completed,
        application_source_at_start=start,
        qt_platform="offscreen",
        datasets=records,
    )

    assert manifest["site_qualification"]["eligible"] is False
    assert manifest["site_qualification"]["reason_codes"] == [
        "application_source_changed_during_capture"
    ]
    assert validate_capture_manifest(manifest, output_dir=tmp_path) == (True, "")


def test_route_semantics_mismatch_keeps_real_screenshot_bounded_but_unqualified(
    tmp_path: Path,
) -> None:
    records = [_dataset_record(tmp_path, dataset_id) for dataset_id in DATASET_IDS]
    evaluation = records[1]["stages"]["evaluation"]
    evaluation["observed_class_labels"] = ["T1", "T2"]
    evaluation["route_semantics_match"] = False
    records[1]["stages"]["saliency"]["route_semantics_match"] = False

    manifest = build_capture_manifest(
        run_id="capture-semantic-mismatch",
        registry_sha256=hashlib.sha256(b"registry").hexdigest(),
        registry_profile="moabb-compact-user-journeys-v1",
        plan_id="plan-123",
        application_source={
            "commit_sha": "a" * 40,
            "source_digest": hashlib.sha256(b"source").hexdigest(),
            "dirty": False,
        },
        qt_platform="offscreen",
        datasets=records,
    )

    assert manifest["site_qualification"]["eligible"] is False
    assert manifest["site_qualification"]["reason_codes"] == [
        "physionetmi-edf-run-semantics:evaluation_route_semantics_mismatch",
        "physionetmi-edf-run-semantics:saliency_route_semantics_mismatch",
    ]
    assert validate_capture_manifest(manifest, output_dir=tmp_path) == (True, "")


def test_dirty_application_source_cannot_qualify_site(tmp_path: Path) -> None:
    records = [_dataset_record(tmp_path, dataset_id) for dataset_id in DATASET_IDS]
    source = {
        "commit_sha": "a" * 40,
        "source_digest": hashlib.sha256(b"source").hexdigest(),
        "dirty": True,
    }

    manifest = build_capture_manifest(
        run_id="capture-dirty-source",
        registry_sha256=hashlib.sha256(b"registry").hexdigest(),
        registry_profile="moabb-compact-user-journeys-v1",
        plan_id="plan-123",
        application_source=source,
        qt_platform="offscreen",
        datasets=records,
    )

    assert manifest["site_qualification"]["eligible"] is False
    assert manifest["site_qualification"]["reason_codes"] == [
        "application_source_dirty"
    ]
    assert validate_capture_manifest(manifest, output_dir=tmp_path) == (True, "")
