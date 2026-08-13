from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from scripts.dev.moabb_gui_campaign_v2.contract import (
    DATASET_MATRIX,
    JOURNEY_MODES,
    REQUIRED_STAGES,
)
from scripts.dev.moabb_gui_campaign_v2.runner import _write_ready_checklists
from scripts.dev.moabb_gui_campaign_v2.visual_review import (
    REVIEW_DIMENSIONS,
    build_pending_visual_review_template,
    validate_visual_review_attestation,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt_inventory(root: Path) -> list[dict[str, object]]:
    receipts: list[dict[str, object]] = []
    for dataset in DATASET_MATRIX:
        for mode in JOURNEY_MODES:
            artifact_dir = root / dataset / mode
            screenshots: dict[str, str] = {}
            for stage in REQUIRED_STAGES:
                path = artifact_dir / "screenshots" / f"{stage}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"{dataset}/{mode}/{stage}".encode())
                screenshots[stage] = str(path)
            receipt = {
                "dataset": dataset,
                "journey_mode": mode,
                "artifacts": {"screenshots": screenshots},
            }
            receipt_path = artifact_dir / "journey-receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            receipts.append(receipt)
    return receipts


def _completed(template: dict[str, object]) -> dict[str, object]:
    completed = copy.deepcopy(template)
    completed["status"] = "completed"
    completed["reviewer"] = {
        "reviewer_id": "main-agent-manual-review",
        "reviewer_role": "independent_manual_reviewer",
        "reviewed_at": "2026-08-13T12:00:00+00:00",
        "attestation": "I independently inspected every bound artifact.",
    }
    for journey in completed["journeys"]:  # type: ignore[index]
        journey["verdicts"] = dict.fromkeys(REVIEW_DIMENSIONS, "pass")
    return completed


def test_visual_review_rejects_pending_forged_stale_and_partial_attestations(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "ready-plan.json"
    plan_path.write_text('{"profile_id":"test"}\n', encoding="utf-8")
    receipts = _receipt_inventory(tmp_path / "evidence")
    template = build_pending_visual_review_template(
        plan_path=plan_path,
        receipts=receipts,
        evidence_root=tmp_path / "evidence",
    )

    assert (
        "visual review attestation is not completed"
        in validate_visual_review_attestation(
            template,
            plan_path=plan_path,
            receipts=receipts,
            evidence_root=tmp_path / "evidence",
        )
    )

    completed = _completed(template)
    assert (
        validate_visual_review_attestation(
            completed,
            plan_path=plan_path,
            receipts=receipts,
            evidence_root=tmp_path / "evidence",
        )
        == []
    )

    missing_producer = _completed(template)
    missing_producer.pop("producer")
    assert any(
        "producer" in error
        for error in validate_visual_review_attestation(
            missing_producer,
            plan_path=plan_path,
            receipts=receipts,
            evidence_root=tmp_path / "evidence",
        )
    )

    forged_producer = _completed(template)
    forged_producer["producer"] = {
        "kind": "manual_reviewer",
        "completion_authority": "campaign_runner_only",
    }
    assert any(
        "producer" in error
        for error in validate_visual_review_attestation(
            forged_producer,
            plan_path=plan_path,
            receipts=receipts,
            evidence_root=tmp_path / "evidence",
        )
    )

    extra_producer_field = _completed(template)
    extra_producer_field["producer"]["forged"] = True  # type: ignore[index]
    assert any(
        "producer" in error
        for error in validate_visual_review_attestation(
            extra_producer_field,
            plan_path=plan_path,
            receipts=receipts,
            evidence_root=tmp_path / "evidence",
        )
    )

    forged = _completed(template)
    forged["reviewer"]["reviewer_id"] = "campaign-runner"  # type: ignore[index]
    assert any(
        "independent" in error
        for error in validate_visual_review_attestation(
            forged,
            plan_path=plan_path,
            receipts=receipts,
            evidence_root=tmp_path / "evidence",
        )
    )

    stale = _completed(template)
    screenshot = (
        tmp_path / "evidence" / "BNCI2014_001" / "cold" / "screenshots" / "training.png"
    )
    screenshot.write_bytes(b"changed after review template")
    assert any(
        "artifact SHA-256" in error
        for error in validate_visual_review_attestation(
            stale,
            plan_path=plan_path,
            receipts=receipts,
            evidence_root=tmp_path / "evidence",
        )
    )
    screenshot.write_bytes(b"BNCI2014_001/cold/training")

    partial = _completed(template)
    partial["journeys"][0]["verdicts"].pop("nested_scroll")  # type: ignore[index]
    assert any(
        "verdicts do not cover" in error
        for error in validate_visual_review_attestation(
            partial,
            plan_path=plan_path,
            receipts=receipts,
            evidence_root=tmp_path / "evidence",
        )
    )

    receipt_path = (
        tmp_path / "evidence" / "BNCI2014_001" / "cold" / "journey-receipt.json"
    )
    receipt_path.write_text('{"changed":true}\n', encoding="utf-8")
    assert any(
        "receipt SHA-256" in error
        for error in validate_visual_review_attestation(
            _completed(template),
            plan_path=plan_path,
            receipts=receipts,
            evidence_root=tmp_path / "evidence",
        )
    )


def test_runner_emits_pending_template_and_never_ready_manual_checklist(
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    receipts = _receipt_inventory(evidence_root)
    source_identity = {
        "application_commit": "a" * 40,
        "poetry_lock_sha256": "b" * 64,
        "cuda": "13.0",
        "gpu": "Test GPU",
    }
    for receipt in receipts:
        receipt.update(
            {
                "source_identity": source_identity,
                "ui_options": {},
                "event_class_summary": {},
                "stages": [
                    {"stage": stage, "elapsed_seconds": 0.1}
                    for stage in REQUIRED_STAGES
                ],
            }
        )
    plan_path = tmp_path / "ready-plan.json"
    plan_path.write_text('{"profile_id":"test"}\n', encoding="utf-8")
    plan = {
        "datasets": [
            {
                "moabb_class": dataset,
                "subjects": list(subjects),
                "bids": {
                    "root": f"/mnt/d/frozen/{dataset}",
                    "dataset_revision_sha256": "c" * 64,
                },
            }
            for dataset, subjects in DATASET_MATRIX.items()
        ]
    }

    _write_ready_checklists(
        plan_path=plan_path,
        plan=plan,
        receipts=receipts,
        evidence_root=evidence_root,
    )

    checklist = json.loads((evidence_root / "manual-test-checklist.json").read_text())
    attestation = json.loads(
        (evidence_root / "visual-review-attestation.json").read_text()
    )
    assert checklist["status"] == "pending_visual_review"
    assert attestation["status"] == "pending_manual_review"
    assert len(attestation["journeys"]) == 30
