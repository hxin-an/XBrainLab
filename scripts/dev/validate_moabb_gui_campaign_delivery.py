#!/usr/bin/env python3
"""Read-only handoff validation for the frozen 15-dataset GUI campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scripts.dev import moabb_dataset_materializer
from scripts.dev.moabb_campaign_preflight import (
    DEFAULT_MANIFEST_PATH,
    PreflightInputs,
    evaluate_preflight,
)
from scripts.dev.moabb_dataset_materializer import (
    FREEZE_MANIFEST_NAME,
    READY_GUI_PLAN_NAME,
)
from scripts.dev.moabb_gui_campaign_v2.contract import (
    DATASET_MATRIX,
    JOURNEY_MODES,
    campaign_plan_sha256,
    execution_preflight_errors,
    load_campaign_plan,
    validate_campaign_receipts,
)
from scripts.dev.moabb_gui_campaign_v2.driver import missing_product_source_hooks
from scripts.dev.moabb_gui_campaign_v2.visual_review import (
    VISUAL_REVIEW_FILENAME,
    validate_visual_review_attestation,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLAN = REPO_ROOT / "artifacts" / "user-journeys" / "moabb-gui-campaign-v2.json"
EXPECTED_RECEIPT_COUNT = len(DATASET_MATRIX) * len(JOURNEY_MODES)


def validate_delivery_evidence(
    *,
    plan_path: Path,
    evidence_root: Path,
) -> dict[str, Any]:
    """Validate frozen bytes and exactly 30 existing receipts without executing work."""
    errors: list[str] = []
    seed_plan_file = plan_path.expanduser()
    root = evidence_root.expanduser()
    seed_plan: dict[str, Any] | None = None
    ready_plan: dict[str, Any] | None = None
    seed_plan_digest = ""
    ready_plan_digest = ""
    freeze_manifest_path: Path | None = None
    ready_plan_path: Path | None = None
    freeze_manifest: dict[str, Any] | None = None

    try:
        seed_plan = load_campaign_plan(seed_plan_file)
        seed_plan_digest = campaign_plan_sha256(seed_plan_file)
    except (OSError, ValueError, TypeError) as exc:
        errors.append(f"campaign seed plan cannot be loaded: {exc}")

    if seed_plan is not None:
        freeze_manifest_path, ready_plan_path, path_errors = (
            _resolve_materialization_paths(seed_plan)
        )
        errors.extend(path_errors)
    if freeze_manifest_path is not None:
        freeze_manifest, freeze_errors = _load_json_object(
            freeze_manifest_path,
            label="freeze manifest",
        )
        errors.extend(freeze_errors)
    if ready_plan_path is not None:
        try:
            ready_plan = load_campaign_plan(ready_plan_path)
            ready_plan_digest = campaign_plan_sha256(ready_plan_path)
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"ready campaign plan cannot be loaded: {exc}")
    if seed_plan is not None and ready_plan is None:
        errors.extend(_unresolved_seed_materialization_errors(seed_plan))

    if ready_plan is not None:
        errors.extend(_delivery_plan_readiness_errors(ready_plan))
        try:
            errors.extend(
                f"execution preflight: {error}"
                for error in execution_preflight_errors(ready_plan)
            )
        except Exception as exc:  # fail closed around environment/native probes
            errors.append(f"execution preflight could not complete: {exc}")
        errors.extend(
            f"product UI hook is missing: {name}"
            for name in missing_product_source_hooks(REPO_ROOT)
        )
    if (
        seed_plan is not None
        and freeze_manifest is not None
        and freeze_manifest_path is not None
        and ready_plan is not None
        and ready_plan_path is not None
    ):
        errors.extend(
            _freeze_ready_binding_errors(
                seed_plan=seed_plan,
                seed_plan_digest=seed_plan_digest,
                freeze_manifest=freeze_manifest,
                freeze_manifest_path=freeze_manifest_path,
                ready_plan=ready_plan,
            )
        )
        errors.extend(
            _materialization_preflight_errors(
                freeze_manifest_path=freeze_manifest_path,
                freeze_manifest=freeze_manifest,
            )
        )

    receipts, inventory_errors = _load_exact_receipt_inventory(root)
    errors.extend(inventory_errors)
    if len(receipts) != EXPECTED_RECEIPT_COUNT:
        errors.append(
            f"expected {EXPECTED_RECEIPT_COUNT} journey receipts, "
            f"loaded {len(receipts)}"
        )
    if ready_plan is not None:
        authoritative_environment = _mapping(
            _mapping(freeze_manifest).get("materialization")
        ).get("environment")
        errors.extend(
            validate_campaign_receipts(
                ready_plan,
                receipts,
                artifact_root=root,
                expected_plan_sha256=ready_plan_digest,
                authoritative_environment=(
                    authoritative_environment
                    if isinstance(authoritative_environment, Mapping)
                    else {}
                ),
            )
        )
    visual_review_path = root / VISUAL_REVIEW_FILENAME
    visual_review_status = "missing"
    if ready_plan is not None and ready_plan_path is not None:
        visual_review, visual_review_errors = _load_json_object(
            visual_review_path,
            label="visual review attestation",
        )
        if visual_review is None:
            errors.extend(visual_review_errors)
        else:
            visual_review_status = str(visual_review.get("status") or "unknown")
            errors.extend(
                f"visual review: {error}"
                for error in validate_visual_review_attestation(
                    visual_review,
                    plan_path=ready_plan_path,
                    receipts=receipts,
                    evidence_root=root,
                )
            )

    unique_errors = list(dict.fromkeys(errors))
    allowed = not unique_errors
    return {
        "schema_version": "1.0.0",
        "status": "ready" if allowed else "blocked",
        "delivery_allowed": allowed,
        "seed_plan": str(seed_plan_file.resolve()),
        "seed_plan_sha256": seed_plan_digest or None,
        "ready_plan": str(ready_plan_path.resolve()) if ready_plan_path else None,
        "campaign_plan_sha256": ready_plan_digest or None,
        "freeze_manifest": (
            str(freeze_manifest_path.resolve()) if freeze_manifest_path else None
        ),
        "evidence_root": str(root.resolve()),
        "expected_dataset_count": len(DATASET_MATRIX),
        "expected_receipt_count": EXPECTED_RECEIPT_COUNT,
        "loaded_receipt_count": len(receipts),
        "visual_review_attestation": str(visual_review_path.resolve()),
        "visual_review_status": visual_review_status,
        "errors": unique_errors,
    }


def _resolve_materialization_paths(
    seed_plan: Mapping[str, Any],
) -> tuple[Path | None, Path | None, list[str]]:
    resource_policy = seed_plan.get("resource_policy")
    checksum_value = (
        resource_policy.get("checksum_root")
        if isinstance(resource_policy, Mapping)
        else None
    )
    checksum_root = Path(str(checksum_value or "")).expanduser()
    if not checksum_root.is_absolute() or not _is_d_mounted(checksum_root):
        return (
            None,
            None,
            ["campaign checksum root must be an absolute /mnt/d path"],
        )
    if checksum_root.is_symlink():
        return None, None, ["campaign checksum root must not be a symlink"]
    return (
        checksum_root / FREEZE_MANIFEST_NAME,
        checksum_root / READY_GUI_PLAN_NAME,
        [],
    )


def _load_json_object(
    path: Path,
    *,
    label: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    if path.is_symlink():
        return None, [f"{label} must not be a symlink"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, [f"{label} cannot be loaded: {exc}"]
    if not isinstance(payload, dict):
        return None, [f"{label} must be a JSON object"]
    return payload, []


def _freeze_ready_binding_errors(
    *,
    seed_plan: Mapping[str, Any],
    seed_plan_digest: str,
    freeze_manifest: Mapping[str, Any],
    freeze_manifest_path: Path,
    ready_plan: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    freeze_materialization = _mapping(freeze_manifest.get("materialization"))
    ready_materialization = _mapping(ready_plan.get("materialization"))
    freeze_environment = _mapping(freeze_materialization.get("environment"))
    if freeze_manifest.get("status") != "ready":
        errors.append("freeze manifest status must be ready")
    if freeze_materialization.get("ready_count") != len(DATASET_MATRIX):
        errors.append("freeze manifest ready_count must be 15")
    if freeze_materialization.get("dataset_count") != len(DATASET_MATRIX):
        errors.append("freeze manifest dataset_count must be 15")
    if freeze_materialization.get("gui_plan_sha256") != seed_plan_digest:
        errors.append("freeze manifest does not match the tracked seed plan")
    try:
        tracked_manifest_sha256 = _sha256_file(DEFAULT_MANIFEST_PATH)
        tracked_manifest, manifest_errors = _load_json_object(
            DEFAULT_MANIFEST_PATH,
            label="tracked dataset manifest",
        )
    except OSError as exc:
        tracked_manifest_sha256 = ""
        tracked_manifest = None
        manifest_errors = [f"tracked dataset manifest cannot be loaded: {exc}"]
    errors.extend(manifest_errors)
    if freeze_materialization.get("manifest_sha256") != tracked_manifest_sha256:
        errors.append("freeze manifest does not match the tracked dataset manifest")
    if not freeze_environment:
        errors.append("freeze manifest lacks its authoritative environment")
    else:
        environment_identity_fields = {
            "identity_sha256": "environment_identity_sha256",
            "conversion_identity_sha256": "conversion_identity_sha256",
            "campaign_product_identity_sha256": ("campaign_product_identity_sha256"),
        }
        for (
            environment_field,
            materialization_field,
        ) in environment_identity_fields.items():
            if freeze_environment.get(environment_field) != (
                freeze_materialization.get(materialization_field)
            ):
                errors.append(
                    "freeze materialization environment "
                    f"{environment_field} differs from its projection"
                )
        git = _mapping(freeze_environment.get("git"))
        if not _hex_digest(git.get("commit"), length=40):
            errors.append("freeze environment application commit is invalid")
        if not _hex_digest(freeze_environment.get("poetry_lock_sha256"), length=64):
            errors.append("freeze environment Poetry lock identity is invalid")
        for field in ("cuda", "gpu"):
            if not str(freeze_environment.get(field) or "").strip():
                errors.append(f"freeze environment {field} identity is invalid")
        if freeze_environment.get("conversion_identity_sha256") != (
            moabb_dataset_materializer._conversion_identity_digest(
                dict(freeze_environment)
            )
        ):
            errors.append("freeze conversion environment seal is invalid")
        if freeze_environment.get("campaign_product_identity_sha256") != (
            moabb_dataset_materializer._campaign_product_identity_digest(
                dict(freeze_environment)
            )
        ):
            errors.append("freeze product environment seal is invalid")
    if ready_materialization.get("status") != "ready":
        errors.append("ready campaign plan materialization status must be ready")
    if ready_materialization.get("freeze_manifest") != str(
        freeze_manifest_path.resolve()
    ):
        errors.append("ready campaign plan points to a different freeze manifest")
    if ready_materialization.get("freeze_manifest_sha256") != _sha256_file(
        freeze_manifest_path
    ):
        errors.append("ready campaign plan freeze manifest digest is stale")
    for field in (
        "environment_identity_sha256",
        "conversion_identity_sha256",
        "campaign_product_identity_sha256",
    ):
        if ready_materialization.get(field) != freeze_materialization.get(field):
            errors.append(f"ready campaign plan {field} differs from freeze manifest")

    seed_policy = _mapping(seed_plan.get("resource_policy"))
    ready_policy = _mapping(ready_plan.get("resource_policy"))
    seed_output_root = str(seed_policy.get("data_root") or "")
    seed_checksum_root = str(seed_policy.get("checksum_root") or "")
    if freeze_materialization.get("output_root") != seed_output_root:
        errors.append("freeze manifest differs from the tracked seed output root")
    if freeze_materialization.get("checksum_root") != seed_checksum_root:
        errors.append("freeze manifest differs from the tracked seed checksum root")
    if ready_policy.get("data_root") != seed_output_root:
        errors.append("ready campaign plan differs from the tracked seed output root")
    if ready_policy.get("checksum_root") != seed_checksum_root:
        errors.append("ready campaign plan differs from the tracked seed checksum root")
    if tracked_manifest is not None:
        for field in ("profile_id", "moabb_release", "resource_policy"):
            if freeze_manifest.get(field) != tracked_manifest.get(field):
                errors.append(
                    f"freeze manifest {field} differs from the tracked dataset manifest"
                )

    seed_names = _dataset_names(seed_plan)
    freeze_rows = _dataset_rows(freeze_manifest)
    ready_rows = _dataset_rows(ready_plan)
    tracked_rows = _dataset_rows(tracked_manifest or {})
    if seed_names != tuple(DATASET_MATRIX):
        errors.append("tracked seed plan dataset inventory is not exact")
    if tuple(freeze_rows) != tuple(DATASET_MATRIX):
        errors.append("freeze manifest dataset inventory is not exact")
    if tuple(ready_rows) != tuple(DATASET_MATRIX):
        errors.append("ready campaign plan dataset inventory is not exact")
    if tuple(tracked_rows) != tuple(DATASET_MATRIX):
        errors.append("tracked dataset manifest inventory is not exact")
    for dataset in DATASET_MATRIX:
        seed = _dataset_rows(seed_plan).get(dataset)
        frozen = freeze_rows.get(dataset)
        ready = ready_rows.get(dataset)
        tracked = tracked_rows.get(dataset)
        if frozen is None or ready is None or seed is None or tracked is None:
            continue
        seed_bids = _mapping(seed.get("bids"))
        bids = _mapping(ready.get("bids"))
        oracle = _mapping(ready.get("oracle"))
        expected_conversion_parent = str(Path(seed_output_root) / dataset)
        expected_checksum_manifest = str(Path(seed_checksum_root) / f"{dataset}.sha256")
        for owner, conversion_parent, checksum_manifest in (
            (
                "tracked seed plan",
                seed_bids.get("conversion_parent"),
                seed_bids.get("checksum_manifest"),
            ),
            (
                "freeze manifest",
                frozen.get("conversion_parent"),
                frozen.get("checksum_manifest"),
            ),
            (
                "ready campaign plan",
                bids.get("conversion_parent"),
                bids.get("checksum_manifest"),
            ),
        ):
            if conversion_parent != expected_conversion_parent:
                errors.append(f"{dataset} {owner} output root projection differs")
            if checksum_manifest != expected_checksum_manifest:
                errors.append(f"{dataset} {owner} checksum root projection differs")

        if _manifest_row_projection(frozen) != _manifest_row_projection(tracked):
            errors.append(
                f"{dataset} frozen row differs from the tracked dataset manifest"
            )
        if _seed_row_projection(seed) != _seed_row_projection(tracked):
            errors.append(
                f"{dataset} tracked seed plan differs from the dataset manifest"
            )
        if _seed_row_projection(ready) != _seed_row_projection(tracked):
            errors.append(
                f"{dataset} ready campaign plan differs from the dataset manifest"
            )
        if frozen.get("resource_status") != "verified":
            errors.append(f"{dataset} frozen resource verification is not complete")
        expected = {
            "bids_root": bids.get("root"),
            "checksum_manifest": bids.get("checksum_manifest"),
            "dataset_revision_sha256": bids.get("dataset_revision_sha256"),
            "event_names": oracle.get("expected_events"),
            "supervised_classes": oracle.get("expected_classes"),
            "bids_event_values": oracle.get("bids_event_values"),
            "bids_value_crosscheck": oracle.get("bids_value_crosscheck"),
        }
        if any(frozen.get(field) != value for field, value in expected.items()):
            errors.append(f"{dataset} ready plan differs from the full frozen oracle")
        if oracle.get("source_event_id") != frozen.get("event_id"):
            errors.append(f"{dataset} ready plan differs from the full frozen oracle")
        frozen_classes = frozen.get("supervised_classes")
        product_classes = (
            [value for value in frozen_classes if isinstance(value, str)]
            if isinstance(frozen_classes, list)
            else []
        )
        expected_product_mapping = [
            {
                "class_index": index,
                "event_code": str(index),
                "class_name": class_name,
            }
            for index, class_name in enumerate(sorted(product_classes))
        ]
        if oracle.get("expected_product_class_mapping") != (expected_product_mapping):
            errors.append(
                f"{dataset} ready plan differs from the deterministic product "
                "class mapping"
            )
    return errors


def _manifest_row_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    """Project only tracked immutable policy fields preserved by materialization."""
    return {
        "moabb_class": row.get("moabb_class"),
        "source_mode": str(row.get("source_mode") or "moabb_convert"),
        "subjects": row.get("subjects"),
        "output_format": row.get("output_format"),
        "supervised_classes": row.get("supervised_classes"),
        "source_size_status": row.get("source_size_status"),
        "license_status": row.get("license_status"),
        "redistribution_allowed": row.get("redistribution_allowed"),
        "license_note": row.get("license_note"),
        "resource_status": (
            row.get("resource_status")
            if row.get("resource_status") != "verified"
            else (
                "FORMAL_BIDS_MIRROR_REQUIRED"
                if str(row.get("source_mode") or "moabb_convert")
                == "formal_bids_mirror"
                else (
                    "RESOURCE_PREFLIGHT_REQUIRED"
                    if row.get("resource_preflight") is not None
                    else "verified"
                )
            )
        ),
        "resource_preflight": row.get("resource_preflight"),
        "formal_bids_mirror": row.get("formal_bids_mirror"),
    }


def _seed_row_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    bids = _mapping(row.get("bids"))
    return {
        "moabb_class": row.get("moabb_class"),
        "source_mode": str(row.get("source_mode") or "moabb_convert"),
        "subjects": row.get("subjects"),
        "output_format": (bids.get("format") if bids else row.get("output_format")),
    }


def _hex_digest(value: Any, *, length: int) -> bool:
    text = str(value or "").casefold()
    return len(text) == length and all(
        character in "0123456789abcdef" for character in text
    )


def _materialization_preflight_errors(
    *,
    freeze_manifest_path: Path,
    freeze_manifest: Mapping[str, Any],
) -> list[str]:
    materialization = _mapping(freeze_manifest.get("materialization"))
    try:
        inputs = PreflightInputs.from_environment(
            manifest_path=freeze_manifest_path,
            mne_data_root=Path(str(materialization.get("mne_data_root") or "")),
            output_root=Path(str(materialization.get("output_root") or "")),
        )
        result = evaluate_preflight(inputs)
    except Exception as exc:
        return [f"frozen dataset preflight could not complete: {exc}"]
    if result.get("campaign_allowed") is True and result.get("status") == "ready":
        return []
    blockers = result.get("blockers")
    if isinstance(blockers, list) and blockers:
        return [f"frozen dataset preflight: {blocker}" for blocker in blockers]
    return ["frozen dataset preflight did not report ready"]


def _dataset_names(payload: Mapping[str, Any]) -> tuple[str, ...]:
    rows = payload.get("datasets")
    if not isinstance(rows, list):
        return ()
    return tuple(
        str(row.get("moabb_class") or "") for row in rows if isinstance(row, Mapping)
    )


def _dataset_rows(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = payload.get("datasets")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("moabb_class") or ""): row
        for row in rows
        if isinstance(row, Mapping)
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_d_mounted(path: Path) -> bool:
    resolved = path.resolve()
    return resolved == Path("/mnt/d") or str(resolved).startswith("/mnt/d/")


def _delivery_plan_readiness_errors(plan: Mapping[str, Any]) -> list[str]:
    """Make pending/null delivery state explicit even before filesystem probes."""
    errors: list[str] = []
    rows = plan.get("datasets")
    if not isinstance(rows, list):
        return ["campaign plan datasets must be a list"]
    for index, row in enumerate(rows):
        prefix = f"datasets[{index}]"
        if not isinstance(row, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        if row.get("execution_state") != "ready":
            errors.append(f"{prefix}.execution_state must be ready")
        bids = row.get("bids")
        root = bids.get("root") if isinstance(bids, Mapping) else None
        if root is None or not str(root).strip():
            errors.append(f"{prefix}.bids.root must be non-null")
    return errors


def _unresolved_seed_materialization_errors(
    seed_plan: Mapping[str, Any],
) -> list[str]:
    """Explain why an awaiting/null seed cannot substitute for a generated plan."""
    errors: list[str] = []
    rows = seed_plan.get("datasets")
    if not isinstance(rows, list):
        return errors
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        if row.get("execution_state") == "awaiting_dataset_materialization":
            errors.append(f"datasets[{index}] remains awaiting_dataset_materialization")
        bids = row.get("bids")
        if isinstance(bids, Mapping) and bids.get("root") is None:
            errors.append(f"datasets[{index}].bids.root remains null")
    return errors


def _load_exact_receipt_inventory(
    evidence_root: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    receipts: list[dict[str, Any]] = []
    if not evidence_root.is_absolute():
        return [], ["campaign evidence root must be absolute"]
    if evidence_root.is_symlink():
        return [], ["campaign evidence root must not be a symlink"]
    if not evidence_root.is_dir():
        return [], ["campaign evidence root is missing or is not a directory"]
    if not _is_d_mounted(evidence_root):
        return [], ["campaign evidence root must be stored under /mnt/d"]

    expected_paths = [
        evidence_root / dataset / mode / "journey-receipt.json"
        for dataset in DATASET_MATRIX
        for mode in JOURNEY_MODES
    ]
    expected_relative = {
        path.relative_to(evidence_root).as_posix() for path in expected_paths
    }
    observed_relative: set[str] = set()
    try:
        for path in evidence_root.rglob("*"):
            if path.is_symlink():
                errors.append(
                    "campaign evidence contains a symlink: "
                    f"{path.relative_to(evidence_root).as_posix()}"
                )
            if path.is_file() and path.name == "journey-receipt.json":
                observed_relative.add(path.relative_to(evidence_root).as_posix())
    except OSError as exc:
        errors.append(f"campaign evidence inventory cannot be read: {exc}")

    for relative in sorted(observed_relative - expected_relative):
        errors.append(f"unexpected journey receipt path: {relative}")
    for path in expected_paths:
        relative = path.relative_to(evidence_root).as_posix()
        if relative not in observed_relative:
            errors.append(f"missing journey receipt: {relative}")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"journey receipt cannot be loaded: {relative}: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"journey receipt is not an object: {relative}")
            continue
        receipts.append(payload)
    return receipts, errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = validate_delivery_evidence(
        plan_path=args.plan,
        evidence_root=args.evidence_root,
    )
    _atomic_write_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["delivery_allowed"] else 1


if __name__ == "__main__":
    sys.exit(main())
