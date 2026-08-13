"""Independent, artifact-bound visual review contract for MOABB journeys.

The campaign producer may create the pending template, but it cannot complete
it.  The delivery validator always re-hashes the plan, receipts, and every
required screenshot before allowing the manual review attestation to count.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from .contract import (
    DATASET_MATRIX,
    JOURNEY_MODES,
    REQUIRED_STAGES,
    campaign_plan_sha256,
)

VISUAL_REVIEW_FILENAME: Final = "visual-review-attestation.json"
VISUAL_REVIEW_SCHEMA_VERSION: Final = "1.0.0"
REVIEW_DIMENSIONS: Final = (
    "layout",
    "contrast",
    "primary_action",
    "text_fit",
    "nested_scroll",
    "dialog_geometry",
    "dpi",
    "error_overlays",
)
_INDEPENDENT_REVIEWER_ROLE: Final = "independent_manual_reviewer"
_EXPECTED_PRODUCER: Final = {
    "kind": "campaign_runner",
    "completion_authority": "independent_manual_reviewer_only",
}
_DISALLOWED_REVIEWER_IDS: Final = frozenset(
    {"campaign-runner", "journey-worker", "campaign-producer"}
)


def build_pending_visual_review_template(
    *,
    plan_path: Path,
    receipts: Sequence[Mapping[str, Any]],
    evidence_root: Path,
) -> dict[str, Any]:
    """Create a pending review template from already sealed journey artifacts."""
    root = evidence_root.resolve(strict=True)
    journeys = _bound_journeys(receipts, evidence_root=root)
    return {
        "schema_version": VISUAL_REVIEW_SCHEMA_VERSION,
        "artifact_type": "xbrainlab.moabb_gui_visual_review",
        "status": "pending_manual_review",
        "producer": dict(_EXPECTED_PRODUCER),
        "campaign_plan": {
            "path": str(plan_path.resolve()),
            "sha256": campaign_plan_sha256(plan_path),
        },
        "receipt_inventory_sha256": _inventory_sha256(journeys),
        "required_review_dimensions": list(REVIEW_DIMENSIONS),
        "reviewer": {
            "reviewer_id": "",
            "reviewer_role": _INDEPENDENT_REVIEWER_ROLE,
            "reviewed_at": "",
            "attestation": "",
        },
        "journeys": [
            {
                **journey,
                "verdicts": dict.fromkeys(REVIEW_DIMENSIONS),
            }
            for journey in journeys
        ],
    }


def validate_visual_review_attestation(
    attestation: Mapping[str, Any],
    *,
    plan_path: Path,
    receipts: Sequence[Mapping[str, Any]],
    evidence_root: Path,
) -> list[str]:
    """Return fail-closed errors for a completed independent visual review."""
    errors: list[str] = []
    root = evidence_root.resolve()
    if attestation.get("schema_version") != VISUAL_REVIEW_SCHEMA_VERSION:
        errors.append("visual review attestation schema version is invalid")
    if attestation.get("artifact_type") != "xbrainlab.moabb_gui_visual_review":
        errors.append("visual review attestation artifact type is invalid")
    if attestation.get("status") != "completed":
        errors.append("visual review attestation is not completed")
    if _mapping(attestation.get("producer")) != _EXPECTED_PRODUCER:
        errors.append(
            "visual review attestation producer must exactly identify the campaign "
            "runner and independent manual completion authority"
        )

    campaign_plan = _mapping(attestation.get("campaign_plan"))
    if campaign_plan.get("path") != str(plan_path.resolve()):
        errors.append("visual review attestation plan path differs from delivery plan")
    try:
        expected_plan_sha = campaign_plan_sha256(plan_path)
    except OSError as exc:
        errors.append(f"visual review attestation plan cannot be hashed: {exc}")
        expected_plan_sha = ""
    if campaign_plan.get("sha256") != expected_plan_sha:
        errors.append("visual review attestation plan SHA-256 is stale")

    try:
        expected_journeys = _bound_journeys(receipts, evidence_root=root)
    except ValueError as exc:
        return [*errors, str(exc)]
    supplied_journeys = attestation.get("journeys")
    if not isinstance(supplied_journeys, list):
        errors.append("visual review attestation journeys must be a list")
        supplied_journeys = []
    expected_by_identity = {
        (row["dataset"], row["journey_mode"]): row for row in expected_journeys
    }
    supplied_by_identity: dict[tuple[str, str], Mapping[str, Any]] = {}
    for index, row in enumerate(supplied_journeys):
        if not isinstance(row, Mapping):
            errors.append(f"visual review journey[{index}] must be an object")
            continue
        identity = (str(row.get("dataset") or ""), str(row.get("journey_mode") or ""))
        if identity in supplied_by_identity:
            errors.append(f"visual review attestation repeats journey {identity!r}")
        else:
            supplied_by_identity[identity] = row
    if set(supplied_by_identity) != set(expected_by_identity):
        errors.append("visual review attestation does not cover the exact 30 journeys")
    for identity, expected in expected_by_identity.items():
        supplied = supplied_by_identity.get(identity)
        if supplied is None:
            continue
        _journey_binding_errors(supplied, expected, errors)

    if attestation.get("receipt_inventory_sha256") != _inventory_sha256(
        expected_journeys
    ):
        errors.append("visual review attestation receipt inventory SHA-256 is stale")
    dimensions = attestation.get("required_review_dimensions")
    if dimensions != list(REVIEW_DIMENSIONS):
        errors.append("visual review attestation dimensions differ from contract")
    _reviewer_errors(_mapping(attestation.get("reviewer")), errors)
    return list(dict.fromkeys(errors))


def _bound_journeys(
    receipts: Sequence[Mapping[str, Any]],
    *,
    evidence_root: Path,
) -> list[dict[str, Any]]:
    expected_identities = [
        (dataset, mode) for dataset in DATASET_MATRIX for mode in JOURNEY_MODES
    ]
    receipt_by_identity: dict[tuple[str, str], Mapping[str, Any]] = {}
    for receipt in receipts:
        identity = (
            str(receipt.get("dataset") or ""),
            str(receipt.get("journey_mode") or ""),
        )
        if identity in receipt_by_identity:
            raise ValueError(f"visual review receipt inventory repeats {identity!r}")
        receipt_by_identity[identity] = receipt
    if set(receipt_by_identity) != set(expected_identities):
        raise ValueError(
            "visual review receipt inventory does not contain the exact 30 journeys"
        )
    journeys: list[dict[str, Any]] = []
    for dataset, mode in expected_identities:
        receipt = receipt_by_identity[(dataset, mode)]
        receipt_path = evidence_root / dataset / mode / "journey-receipt.json"
        receipt_record = _bound_file(receipt_path, evidence_root=evidence_root)
        screenshots = _mapping(_mapping(receipt.get("artifacts")).get("screenshots"))
        if set(screenshots) != set(REQUIRED_STAGES):
            raise ValueError(
                f"visual review {dataset}/{mode} screenshots do not cover required stages"
            )
        screenshot_records = {
            stage: _bound_file(
                Path(str(screenshots[stage])), evidence_root=evidence_root
            )
            for stage in REQUIRED_STAGES
        }
        journeys.append(
            {
                "dataset": dataset,
                "journey_mode": mode,
                "receipt": receipt_record,
                "screenshots": screenshot_records,
            }
        )
    return journeys


def _bound_file(path: Path, *, evidence_root: Path) -> dict[str, str]:
    if path.expanduser().is_symlink():
        raise ValueError(f"visual review artifact must not be a symlink: {path}")
    resolved = path.expanduser().resolve(strict=True)
    try:
        relative = resolved.relative_to(evidence_root)
    except ValueError as exc:
        raise ValueError(
            f"visual review artifact escapes evidence root: {resolved}"
        ) from exc
    if not resolved.is_file():
        raise ValueError(f"visual review artifact is not a regular file: {relative}")
    return {"path": relative.as_posix(), "sha256": _sha256_file(resolved)}


def _journey_binding_errors(
    supplied: Mapping[str, Any],
    expected: Mapping[str, Any],
    errors: list[str],
) -> None:
    label = f"{expected['dataset']}/{expected['journey_mode']}"
    receipt = _mapping(supplied.get("receipt"))
    if receipt != expected["receipt"]:
        errors.append(f"visual review {label} receipt SHA-256 or path is stale")
    screenshots = _mapping(supplied.get("screenshots"))
    if set(screenshots) != set(REQUIRED_STAGES):
        errors.append(f"visual review {label} screenshots do not cover required stages")
    else:
        for stage in REQUIRED_STAGES:
            if _mapping(screenshots.get(stage)) != expected["screenshots"][stage]:
                errors.append(
                    f"visual review {label}/{stage} artifact SHA-256 or path is stale"
                )
    verdicts = _mapping(supplied.get("verdicts"))
    if set(verdicts) != set(REVIEW_DIMENSIONS):
        errors.append(
            f"visual review {label} verdicts do not cover required dimensions"
        )
    elif any(verdicts[dimension] != "pass" for dimension in REVIEW_DIMENSIONS):
        errors.append(f"visual review {label} does not pass every required dimension")


def _reviewer_errors(reviewer: Mapping[str, Any], errors: list[str]) -> None:
    reviewer_id = str(reviewer.get("reviewer_id") or "").strip()
    if not reviewer_id:
        errors.append("visual review attestation lacks an independent reviewer id")
    elif reviewer_id.casefold() in _DISALLOWED_REVIEWER_IDS:
        errors.append(
            "visual review attestation reviewer is not independent from campaign production"
        )
    if reviewer.get("reviewer_role") != _INDEPENDENT_REVIEWER_ROLE:
        errors.append(
            "visual review attestation reviewer role is not independent manual review"
        )
    if not str(reviewer.get("reviewed_at") or "").strip():
        errors.append("visual review attestation lacks review time")
    if not str(reviewer.get("attestation") or "").strip():
        errors.append("visual review attestation lacks reviewer attestation text")


def _inventory_sha256(journeys: Sequence[Mapping[str, Any]]) -> str:
    canonical = [
        {
            "dataset": row["dataset"],
            "journey_mode": row["journey_mode"],
            "receipt": row["receipt"],
            "screenshots": row["screenshots"],
        }
        for row in journeys
    ]
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
