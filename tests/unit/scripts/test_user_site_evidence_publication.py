from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from scripts.dev import validate_user_site as user_site
from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    source_identity_digest,
)
from scripts.dev.moabb_ui_evidence.contract import (
    build_capture_manifest,
    dataset_revision,
)
from scripts.dev.user_site_evidence.publication import (
    EvidencePublicationError,
    publish_capture_manifest,
)

DATASET_IDS = (
    "ofner2017-mi-gdf",
    "physionetmi-edf-run-semantics",
    "lee2021mobile-erp-brainvision",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(path: Path, *, kind: str, **metadata: Any) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "kind": kind,
        **metadata,
    }


def _screenshot(path: Path, *, root: Path, color: str) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (96, 64), color).save(path)
    return {
        "path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "dimensions": [96, 64],
        "format": "PNG",
    }


def _source_identity(repo_root: Path) -> dict[str, Any]:
    identity = {
        "version": 3,
        "repo_root": str(repo_root.resolve()),
        "branch": "test/evidence",
        "commit_sha": "a" * 40,
        "head_tree_sha": "b" * 40,
        "dirty": False,
        "dirty_digest": hashlib.sha256(b"clean").hexdigest(),
        "source_content_digest": hashlib.sha256(b"source").hexdigest(),
        "untracked_source_count": 0,
        "excluded_generated_prefixes": ["artifacts/", "build/"],
        "excluded_local_paths": ["settings.json"],
        "included_file_policy": "all-non-generated-tracked-and-untracked-files",
        "error": "",
    }
    identity["source_digest"] = source_identity_digest(identity)
    return identity


def _trace() -> list[dict[str, Any]]:
    stages = (
        "scan",
        "preview",
        "validate",
        "apply",
        "save_recipe",
        "preprocess:bandpass",
        "epoch",
        "split",
        "configure_training",
        "configure_saliency",
        "train",
        "training_history",
        "evaluate",
        "saliency_query",
    )
    return [
        {
            "stage": stage,
            "command": stage.split(":", 1)[0],
            "status": "success",
            "error_type": "none",
        }
        for stage in stages
    ]


def _dataset_fixture(
    tmp_path: Path,
    capture_root: Path,
    dataset_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_path = tmp_path / "source-data" / f"{dataset_id}.bin"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes((dataset_id * 3).encode("ascii"))
    source_sha = _sha256(source_path)
    source_url = f"https://example.test/{dataset_id}.bin"
    source_record = {
        "path": str(source_path.resolve()),
        "url": source_url,
        "size_bytes": source_path.stat().st_size,
        "expected_checksum": {"algorithm": "sha256", "value": source_sha},
        "sha256": source_sha,
    }
    registry_dataset = {
        "id": dataset_id,
        "files": [
            {
                "url": source_url,
                "relative_path": f"{dataset_id}/source.bin",
                "size_bytes": source_path.stat().st_size,
                "checksum": {"algorithm": "sha256", "value": source_sha},
            }
        ],
        "claim_boundary": [f"One identified {dataset_id} run only."],
    }

    dataset_root = capture_root / dataset_id
    import_shot = _screenshot(
        dataset_root / "import-review.png", root=capture_root, color="#184f78"
    )
    evaluation_shot = _screenshot(
        dataset_root / "evaluation.png", root=capture_root, color="#507818"
    )
    saliency_shot = _screenshot(
        dataset_root / "saliency.png", root=capture_root, color="#781850"
    )
    curve_path = dataset_root / "training-curves.json"
    curve_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "rows": [
                    {
                        "train_loss": [0.9, 0.4],
                        "validation_accuracy": [0.6, 0.8],
                        "test_accuracy": [0.75],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    recipe_path = dataset_root / "import-recipe.json"
    recipe_path.write_text('{"recipe": true}\n', encoding="utf-8")
    saliency_path = dataset_root / "gradient.npz"
    saliency_path.write_bytes(b"verified-saliency-array")

    evaluation = {
        "plan_index": 0,
        "split": "test",
        "test_prediction_read_count": 1,
        "sample_count": 20,
        "model_class_count": 2,
        "observed_class_count": 2,
        "metrics": {
            "accuracy": 0.75,
            "balanced_accuracy": 0.74,
            "macro_f1": 0.73,
            "roc_auc_ovr": 0.81,
            "internal_loss": 0.12,
        },
        "baselines": {"chance_baseline": 0.5},
        "class_labels": {"0": "left", "1": "right"},
        "valid": True,
        "acceptance_rules": [
            {
                "metric": "balanced_accuracy",
                "value": 0.74,
                "operator": ">",
                "threshold_name": "chance_baseline",
                "threshold_value": 0.5,
                "passed": True,
                "rationale": "Predeclared comparison.",
            }
        ],
        "passed": True,
    }
    journey = {
        "dataset": {"id": dataset_id},
        "selection": {"subjects": [1], "sessions": ["session"], "runs": [1]},
        "source_artifacts": [source_record],
        "import": {
            "recipe": {"source_hint": "file"},
            "recipe_artifact": _artifact(recipe_path, kind="import_recipe"),
            "validation_decision": "accepted",
            "applied": True,
        },
        "preprocessing": [{"command": {"operation": "bandpass"}}],
        "epoch": {"state": {"epoch_count": 20}},
        "split": {"state": {"has_datasets": True}},
        "model": {"name": "EEGNet", "actual_device": "cpu", "epochs": 30},
        "seed": 1729,
        "metrics": {"held_out_evaluations": [evaluation]},
        "training_curves": [_artifact(curve_path, kind="training_curves")],
        "quality_acceptance": {
            "specification": {"held_out_split": "test"},
            "evaluations": [evaluation],
            "passed": True,
            "status": "accepted",
        },
        "quality_evidence_status": "complete",
        "saliency": {
            "methods": ["Gradient"],
            "params": {},
            "artifacts": [
                _artifact(
                    saliency_path,
                    kind="saliency",
                    source="application_service_saliency_render",
                    method="Gradient",
                )
            ],
        },
        "screenshots": [
            _artifact(
                capture_root / evaluation_shot["path"],
                kind="qt_screenshot",
                stage="evaluation",
            ),
            _artifact(
                capture_root / saliency_shot["path"],
                kind="qt_screenshot",
                stage="saliency",
            ),
        ],
        "timings": {"total": 1.0},
        "command_trace": _trace(),
        "failures": [],
        "resume": {"attempt": 1},
        "claim_boundary": ["Observed metrics are from one held-out split."],
    }
    evidence_path = dataset_root / "journey-evidence.json"
    evidence_path.write_text(json.dumps(journey), encoding="utf-8")

    capture_dataset = {
        "dataset_id": dataset_id,
        "dataset_revision": dataset_revision(registry_dataset),
        "exact_source": {
            "status": "verified",
            "plan_id": "plan-123",
            "files": [source_record],
        },
        "execution": {
            "profile": "showcase",
            "status": "completed",
            "evidence_path": evidence_path.relative_to(capture_root).as_posix(),
            "evidence_sha256": _sha256(evidence_path),
            "quality_evidence_status": "complete",
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
                "sample_count": 20,
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
        "limitations": ["Automated Qt capture is not Windows acceptance."],
    }
    return registry_dataset, capture_dataset


def _publication_fixture(tmp_path: Path) -> dict[str, Any]:
    run_id = "capture-20260809"
    capture_root = tmp_path / run_id
    capture_root.mkdir()
    rows = [
        _dataset_fixture(tmp_path, capture_root, dataset_id)
        for dataset_id in DATASET_IDS
    ]
    registry = {
        "schema_version": "1.0.0",
        "profile_id": "moabb-compact-user-journeys-v1",
        "moabb_release": {
            "version": "1.5.0",
            "commit": "c" * 40,
            "repository": "https://github.com/NeuroTechX/moabb",
        },
        "datasets": [item[0] for item in rows],
    }
    registry_path = tmp_path / "moabb-datasets-v1.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    registry_sha = _sha256(registry_path)
    source_identity = _source_identity(tmp_path / "repo")
    capture = build_capture_manifest(
        run_id=run_id,
        registry_sha256=registry_sha,
        registry_profile=registry["profile_id"],
        plan_id="plan-123",
        application_source=source_identity,
        qt_platform="offscreen",
        datasets=[item[1] for item in rows],
    )
    manifest_path = capture_root / "qt-capture-manifest.json"
    manifest_path.write_text(json.dumps(capture), encoding="utf-8")
    return {
        "capture": capture,
        "manifest_path": manifest_path,
        "registry_path": registry_path,
        "docs_dir": tmp_path / "user_docs",
        "case_ids": {
            dataset_id: {"case_id": f"case-{index}"}
            for index, dataset_id in enumerate(DATASET_IDS, start=1)
        },
    }


def _rewrite_capture(fixture: dict[str, Any], dataset_index: int = 0) -> None:
    capture = fixture["capture"]
    capture_root = fixture["manifest_path"].parent
    execution = capture["datasets"][dataset_index]["execution"]
    evidence_path = capture_root / execution["evidence_path"]
    execution["evidence_sha256"] = _sha256(evidence_path)
    fixture["manifest_path"].write_text(json.dumps(capture), encoding="utf-8")


def _publish(fixture: dict[str, Any]) -> dict[str, Any]:
    return publish_capture_manifest(
        capture_manifest_path=fixture["manifest_path"],
        registry_path=fixture["registry_path"],
        docs_dir=fixture["docs_dir"],
        case_map=fixture["case_ids"],
    )


def test_valid_exact_run_publishes_content_addressed_bounded_evidence(
    tmp_path: Path,
) -> None:
    fixture = _publication_fixture(tmp_path)

    published = _publish(fixture)

    assert published["publication_status"] == "bounded"
    assert published["run_id"] == "capture-20260809"
    assert len(published["manifest_sha256"]) == 64
    first = published["datasets"][DATASET_IDS[0]]
    assert first["identity"]["app_revision"] == "a" * 40
    assert first["metrics"][0]["values"] == {
        "accuracy": 0.75,
        "balanced_accuracy": 0.74,
        "macro_f1": 0.73,
        "roc_auc_ovr": 0.81,
    }
    assert "internal_loss" not in json.dumps(first["metrics"])
    assert any("Windows acceptance" in item for item in first["limitations"])
    references = first["identity"]["evidence_files"]
    assert references
    assert all(published["manifest_sha256"] in item for item in references)
    assert all((fixture["docs_dir"] / item).is_file() for item in references)
    assert {item["kind"] for item in first["published_artifacts"]} >= {
        "bounded_metrics",
        "training_curves",
        "import_review_screenshot",
        "evaluation_screenshot",
        "saliency_screenshot",
    }


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("stale_registry", "registry"),
        ("dirty_source", "dirty"),
        ("missing_saliency_trace", "saliency_query"),
        ("missing_metrics_file", "training curve"),
        ("tampered_screenshot", "screenshot"),
    ],
)
def test_incomplete_or_stale_run_fails_without_publishing_assets(
    tmp_path: Path,
    mutation: str,
    match: str,
) -> None:
    fixture = _publication_fixture(tmp_path)
    capture = fixture["capture"]
    capture_root = fixture["manifest_path"].parent
    if mutation == "stale_registry":
        fixture["registry_path"].write_text("{}\n", encoding="utf-8")
    elif mutation == "dirty_source":
        capture["application_source"]["dirty"] = True
        fixture["manifest_path"].write_text(json.dumps(capture), encoding="utf-8")
    elif mutation == "missing_saliency_trace":
        execution = capture["datasets"][0]["execution"]
        path = capture_root / execution["evidence_path"]
        evidence = json.loads(path.read_text(encoding="utf-8"))
        evidence["command_trace"] = [
            item
            for item in evidence["command_trace"]
            if item["stage"] != "saliency_query"
        ]
        path.write_text(json.dumps(evidence), encoding="utf-8")
        _rewrite_capture(fixture)
    elif mutation == "missing_metrics_file":
        execution = capture["datasets"][0]["execution"]
        path = capture_root / execution["evidence_path"]
        evidence = json.loads(path.read_text(encoding="utf-8"))
        Path(evidence["training_curves"][0]["path"]).unlink()
    elif mutation == "tampered_screenshot":
        screenshot = capture["datasets"][0]["stages"]["saliency"]["screenshot"]
        (capture_root / screenshot["path"]).write_bytes(b"not a PNG")

    with pytest.raises(EvidencePublicationError, match=match):
        _publish(fixture)

    assert not (fixture["docs_dir"] / "assets").exists()


def test_published_asset_conflict_fails_closed(tmp_path: Path) -> None:
    fixture = _publication_fixture(tmp_path)
    published = _publish(fixture)
    first_reference = published["datasets"][DATASET_IDS[0]]["identity"][
        "evidence_files"
    ][0]
    (fixture["docs_dir"] / first_reference).write_bytes(b"changed after publication")

    with pytest.raises(EvidencePublicationError, match="immutable publication target"):
        _publish(fixture)


def test_generated_case_renders_bounded_metrics_screenshots_and_limits() -> None:
    source = json.loads(user_site.MOABB_SOURCE.read_text(encoding="utf-8"))
    dataset = next(item for item in source["datasets"] if item["id"] == DATASET_IDS[0])
    summary = "assets/evidence/moabb/case/run-" + "d" * 64 + "/metrics.json"
    screenshot = "assets/evidence/moabb/case/run-" + "d" * 64 + "/saliency.png"
    published = {
        "publication_status": "bounded",
        "identity": {
            "manifest_id": f"sha256:{'d' * 64}",
            "app_revision": "a" * 40,
            "run_id": "capture-20260809",
            "dataset_revision": "e" * 64,
            "evidence_files": [summary, screenshot],
        },
        "publication": {
            "schema_version": "1.0.0",
            "input_manifest_sha256": "d" * 64,
            "application_source_digest": "f" * 64,
            "registry_sha256": "1" * 64,
            "execution_sha256": "2" * 64,
            "published_artifacts": [
                {
                    "reference": summary,
                    "kind": "bounded_metrics",
                    "sha256": "3" * 64,
                    "size_bytes": 10,
                },
                {
                    "reference": screenshot,
                    "kind": "saliency_screenshot",
                    "sha256": "4" * 64,
                    "size_bytes": 20,
                },
            ],
        },
        "published_artifacts": [],
        "metrics": [
            {
                "plan_index": 0,
                "split": "test",
                "sample_count": 20,
                "class_labels": {"0": "left", "1": "right"},
                "values": {"accuracy": 0.75, "balanced_accuracy": 0.74},
                "acceptance_rules": [],
            }
        ],
        "limitations": ["One run only.", "No <external> Windows acceptance."],
        "saliency_methods": ["Gradient"],
        "stage_evidence": {
            key: [summary, screenshot] if key == "saliency" else [summary]
            for _, key in user_site.CASE_STAGES
        },
    }

    record = user_site._new_moabb_record(
        source,
        dataset,
        existing=None,
        published=published,
    )
    page = user_site._render_moabb_page(source, dataset, record)

    assert record["publication_status"] == "bounded"
    assert "Observed held-out metrics" in page
    assert "| Test plan | Samples | Accuracy | Balanced accuracy |" in page
    assert "| 1 | 20 | 0.750 | 0.740 |" in page
    assert f"![Saliency evidence] (../{screenshot})".replace("] (", "](") in page
    assert "No &lt;external&gt; Windows acceptance." in page
    assert "No measured value is published" not in page


def test_sync_does_not_preserve_manual_evidence_promotion() -> None:
    source = json.loads(user_site.MOABB_SOURCE.read_text(encoding="utf-8"))
    dataset = next(item for item in source["datasets"] if item["id"] == DATASET_IDS[0])
    manually_promoted = {
        "publication_status": "bounded",
        "identity": {
            "manifest_id": "manual",
            "app_revision": "a" * 40,
            "run_id": "manual",
            "dataset_revision": "manual",
            "evidence_files": ["assets/manual.png"],
        },
        "stages": {
            key: {"status": "bounded", "evidence_files": ["assets/manual.png"]}
            for _, key in user_site.CASE_STAGES
        },
    }

    record = user_site._new_moabb_record(source, dataset, manually_promoted)

    assert record["publication_status"] == "unverified"
    assert record["identity"]["evidence_files"] == []
    assert all(stage["status"] == "unverified" for stage in record["stages"].values())


def test_normal_site_validation_rehashes_published_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _publication_fixture(tmp_path)
    published = _publish(fixture)
    dataset_id = DATASET_IDS[0]
    result = published["datasets"][dataset_id]
    case_id = fixture["case_ids"][dataset_id]["case_id"]
    record = {
        "case_id": case_id,
        "publication_status": "bounded",
        "identity": result["identity"],
        "publication": result["publication"],
        "observations": {
            "metrics": result["metrics"],
            "limitations": result["limitations"],
            "saliency_methods": result["saliency_methods"],
        },
        "stages": {
            key: {"status": "bounded", "evidence_files": references}
            for key, references in result["stage_evidence"].items()
        },
    }
    monkeypatch.setattr(user_site, "ROOT", tmp_path)
    monkeypatch.setattr(user_site, "DOCS_DIR", fixture["docs_dir"])
    record_path = tmp_path / "record.yml"
    record_path.write_text("record: test\n", encoding="utf-8")

    failures: list[str] = []
    user_site._check_moabb_publication_record(
        record,
        record_path,
        dataset_id=dataset_id,
        source_digest=published["registry_sha256"],
        failures=failures,
    )
    assert failures == []

    metrics_receipt = next(
        item
        for item in result["publication"]["published_artifacts"]
        if item["kind"] == "bounded_metrics"
    )
    (fixture["docs_dir"] / metrics_receipt["reference"]).write_bytes(b"changed")
    user_site._check_moabb_publication_record(
        record,
        record_path,
        dataset_id=dataset_id,
        source_digest=published["registry_sha256"],
        failures=failures,
    )

    assert any("artifact integrity failed" in failure for failure in failures)


def test_publication_file_transaction_rolls_back_after_later_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs_dir = tmp_path / "user_docs"
    targets = [docs_dir / "case-a.md", docs_dir / "case-b.md", docs_dir / "case-c.md"]
    for index, target in enumerate(targets):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"old-{index}\n", encoding="utf-8")
    created_asset = docs_dir / "assets/evidence/moabb/new-run/screenshot.png"
    created_asset.parent.mkdir(parents=True)
    created_asset.write_bytes(b"new immutable asset")
    transaction = user_site._PublicationFileTransaction.prepare(
        [(target, f"new-{index}\n") for index, target in enumerate(targets)],
        docs_root=docs_dir,
        created_assets=[created_asset],
    )
    real_replace = os.replace
    replace_calls = 0

    def fail_second_replace(source: Path, target: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("injected later replacement failure")
        real_replace(source, target)

    monkeypatch.setattr(user_site.os, "replace", fail_second_replace)

    with pytest.raises(OSError, match="injected later replacement failure"):
        transaction.commit()

    assert [target.read_text(encoding="utf-8") for target in targets] == [
        "old-0\n",
        "old-1\n",
        "old-2\n",
    ]
    assert not created_asset.exists()
    assert not list(docs_dir.rglob("*.publication-part"))
    assert not list(docs_dir.rglob("*.publication-backup"))


def test_publication_file_transaction_rolls_back_after_post_write_rejection(
    tmp_path: Path,
) -> None:
    docs_dir = tmp_path / "user_docs"
    target = docs_dir / "case.md"
    target.parent.mkdir(parents=True)
    target.write_text("unverified\n", encoding="utf-8")
    created_asset = docs_dir / "assets/evidence/moabb/new-run/metrics.json"
    created_asset.parent.mkdir(parents=True)
    created_asset.write_text('{"bounded": true}\n', encoding="utf-8")
    transaction = user_site._PublicationFileTransaction.prepare(
        [(target, "bounded\n")],
        docs_root=docs_dir,
        created_assets=[created_asset],
    )

    transaction.commit()
    assert target.read_text(encoding="utf-8") == "bounded\n"
    transaction.rollback()

    assert target.read_text(encoding="utf-8") == "unverified\n"
    assert not created_asset.exists()


def test_publication_cli_rolls_back_when_post_write_site_validation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs_dir = tmp_path / "user_docs"
    target = docs_dir / "case.md"
    target.parent.mkdir(parents=True)
    target.write_text("unverified\n", encoding="utf-8")
    created_asset = docs_dir / "assets/evidence/moabb/new-run/metrics.json"
    created_asset.parent.mkdir(parents=True)
    created_asset.write_text('{"bounded": true}\n', encoding="utf-8")
    checks = iter(([], ["injected post-write validation failure"]))

    def publish_then_return_transaction(
        source: dict[str, Any], capture_manifest: Path
    ) -> user_site._PublicationFileTransaction:
        del source, capture_manifest
        transaction = user_site._PublicationFileTransaction.prepare(
            [(target, "bounded\n")],
            docs_root=docs_dir,
            created_assets=[created_asset],
        )
        transaction.commit()
        return transaction

    monkeypatch.setattr(user_site, "_read_json", lambda path, failures: {})
    monkeypatch.setattr(user_site, "_check_moabb_source", lambda source, failures: None)
    monkeypatch.setattr(
        user_site, "_run_site_checks", lambda source, built_dir: next(checks)
    )
    monkeypatch.setattr(
        user_site, "_publish_moabb_cases", publish_then_return_transaction
    )

    result = user_site.main(
        ["--publish-run-manifest", str(tmp_path / "qt-capture-manifest.json")]
    )

    assert result == 1
    assert target.read_text(encoding="utf-8") == "unverified\n"
    assert not created_asset.exists()
