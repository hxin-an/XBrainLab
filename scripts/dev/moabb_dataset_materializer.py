#!/usr/bin/env python3
"""Materialize and checksum-pin a manifest-selected MOABB BIDS campaign.

The command is deliberately no-download by default.  Real source access and
conversion require ``--allow-download``; ``--dry-run`` never creates roots,
performs a resource probe, imports a dataset class, or calls MOABB.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final

from tomllib import TOMLDecodeError, load

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST_PATH: Final = (
    REPO_ROOT / "artifacts/user-journeys/moabb-15-campaign-preflight-v1.json"
)
DEFAULT_GUI_PLAN_PATH: Final = (
    REPO_ROOT / "artifacts/user-journeys/moabb-gui-campaign-v2.json"
)
FREEZE_MANIFEST_NAME: Final = "moabb-15-freeze-manifest-v1.json"
READY_GUI_PLAN_NAME: Final = "moabb-gui-campaign-v2.ready.json"
CONVERT_OUTPUT_FORMATS: Final = frozenset({"EDF", "BrainVision", "EEGLAB"})
FORMAL_BIDS_MIRROR_FORMATS: Final = frozenset({"BDF"})
SUPPORTED_FORMATS: Final = CONVERT_OUTPUT_FORMATS | FORMAL_BIDS_MIRROR_FORMATS
SOURCE_MODE_MOABB_CONVERT: Final = "moabb_convert"
SOURCE_MODE_FORMAL_BIDS_MIRROR: Final = "formal_bids_mirror"
FORMAL_BIDS_MIRROR_REQUIRED: Final = "FORMAL_BIDS_MIRROR_REQUIRED"
_MIRROR_PROJECTION_FIELDS: Final = (
    "path",
    "size",
    "checksum_algorithm",
    "checksum",
    "bytes_url",
)
_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CONTENT_RANGE = re.compile(r"bytes\s+0-(\d+)/(\d+)\Z", re.IGNORECASE)
REQUIRED_BIDS_VALIDATOR_VERSION: Final = "2.4.1"
CRITICAL_RUNTIME_DISTRIBUTIONS: Final = (
    "moabb",
    "mne",
    "mne-bids",
    "pybv",
    "edfio",
    "edflib-python",
    "eeglabio",
    "numpy",
    "torch",
    "pyxdf",
    "pymatreader",
    "pyriemann",
    "scipy",
    "scikit-learn",
)
CAMPAIGN_RUNTIME_DISTRIBUTIONS: Final = (
    *CRITICAL_RUNTIME_DISTRIBUTIONS,
    "bids-validator-deno",
)


class MaterializationContractError(ValueError):
    """The tracked spec, roots, or environment cannot safely be executed."""


@dataclass(frozen=True)
class MaterializationInputs:
    """Explicit and dependency-injected inputs for one materialization run."""

    manifest_path: Path
    gui_plan_path: Path
    mne_data_root: Path
    output_root: Path
    checksum_root: Path
    source_seed_root: Path | None
    dataset: str | None
    dry_run: bool
    allow_download: bool
    resume: bool
    free_bytes: int
    dataset_factory: Callable[[str], Any]
    environment_identity: Callable[[], dict[str, Any]]
    resource_probe: Callable[[dict[str, Any]], dict[str, Any]]
    mirror_manifest_fetcher: Callable[[str, frozenset[str], int], bytes]
    mirror_file_downloader: Callable[[str, Path, frozenset[str], int], dict[str, Any]]
    bids_validator: Callable[[Path], dict[str, Any]]
    d_mount_validator: Callable[[Path], bool]

    @classmethod
    def from_environment(
        cls,
        *,
        manifest_path: Path,
        gui_plan_path: Path,
        mne_data_root: Path,
        output_root: Path,
        checksum_root: Path,
        source_seed_root: Path | None,
        dataset: str | None,
        dry_run: bool,
        allow_download: bool,
        resume: bool,
    ) -> MaterializationInputs:
        probe_root = _nearest_existing_parent(
            Path(
                os.path.commonpath(
                    (
                        mne_data_root.resolve(),
                        output_root.resolve(),
                        checksum_root.resolve(),
                    )
                )
            )
        )
        return cls(
            manifest_path=manifest_path,
            gui_plan_path=gui_plan_path,
            mne_data_root=mne_data_root,
            output_root=output_root,
            checksum_root=checksum_root,
            source_seed_root=source_seed_root,
            dataset=dataset,
            dry_run=dry_run,
            allow_download=allow_download,
            resume=resume,
            free_bytes=shutil.disk_usage(probe_root).free,
            dataset_factory=_installed_dataset_factory,
            environment_identity=exact_environment_identity,
            resource_probe=_bounded_http_resource_probe,
            mirror_manifest_fetcher=_bounded_https_fetch,
            mirror_file_downloader=_download_https_file,
            bids_validator=_run_bids_validator,
            d_mount_validator=_is_d_drive_mount,
        )


def run_materialization(inputs: MaterializationInputs) -> dict[str, Any]:
    """Validate, materialize or replay one generic manifest-driven campaign."""
    try:
        spec = _load_object(inputs.manifest_path, "materialization manifest")
        gui_plan = _load_object(inputs.gui_plan_path, "GUI campaign plan")
        rows, gui_rows = _validate_contracts(spec, gui_plan)
        selected = _select_rows(rows, inputs.dataset)
        roots = _validated_roots(inputs)
        source_seed_root = _validated_source_seed_root(
            inputs, selected=selected, roots=roots
        )
        environment = inputs.environment_identity()
        _validate_environment(spec, environment)
        headroom_phase = (
            "acquisition"
            if inputs.dry_run or inputs.allow_download
            else "frozen-replay"
        )
        required_bytes = _required_headroom(
            spec,
            selected if headroom_phase == "acquisition" else [],
        )
    except (MaterializationContractError, OSError, json.JSONDecodeError) as exc:
        return _blocked_result(str(exc))

    base = {
        "schema_version": "1.0.0",
        "selected_datasets": [str(row["moabb_class"]) for row in selected],
        "network_used": False,
        "headroom_phase": headroom_phase,
        "required_headroom_bytes": required_bytes,
        "free_bytes": inputs.free_bytes,
        "roots": {name: str(path) for name, path in roots.items()},
        "environment": environment,
        "blockers": [],
    }
    if inputs.free_bytes < required_bytes:
        return {
            **base,
            "status": "blocked",
            "blockers": [
                "insufficient D-drive free space: "
                f"{inputs.free_bytes} available, {required_bytes} required"
            ],
            "datasets": [],
        }
    if inputs.dry_run:
        return {
            **base,
            "status": "dry-run-ready",
            "datasets": [
                {
                    "dataset": row["moabb_class"],
                    "action": "would-verify-or-materialize",
                    "source_mode": row["source_mode"],
                    "output_format": row["output_format"],
                    "subjects": list(row["subjects"]),
                    "resource_preflight_required": bool(_resource_policy(row))
                    or row["source_mode"] == SOURCE_MODE_FORMAL_BIDS_MIRROR,
                }
                for row in selected
            ],
        }
    if not inputs.resume and not inputs.allow_download:
        return {
            **base,
            "status": "blocked",
            "datasets": [],
            "blockers": ["--no-resume requires explicit --allow-download"],
        }

    # A missing no-download cache is a pure validation failure.  Do not create
    # roots just to report that explicit download authority is required.
    if not inputs.allow_download and not inputs.checksum_root.exists():
        return {
            **base,
            "status": "blocked",
            "datasets": [
                {
                    "dataset": row["moabb_class"],
                    "status": "blocked",
                    "error": "dataset is not frozen; rerun with --allow-download",
                }
                for row in selected
            ],
        }

    for root in roots.values():
        root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    verified_datasets: set[str] = set()
    network_used = False
    for row in selected:
        dataset_result = _materialize_one(
            row=row,
            spec=spec,
            gui_plan=gui_plan,
            gui_rows=gui_rows,
            inputs=inputs,
            roots=roots,
            environment=environment,
            source_seed_root=source_seed_root,
        )
        network_used = network_used or bool(dataset_result.pop("network_used", False))
        results.append(dataset_result)
        if dataset_result.get("status") == "ready":
            verified_datasets.add(str(dataset_result["dataset"]))

    freeze_path = roots["checksum_root"] / FREEZE_MANIFEST_NAME
    ready_plan_path = roots["checksum_root"] / READY_GUI_PLAN_NAME
    preserve_prior_seal = (
        any(row.get("action") == "reseal-blocked" for row in results)
        and freeze_path.is_file()
        and ready_plan_path.is_file()
    )
    if preserve_prior_seal:
        all_ready = False
    else:
        try:
            freeze_path, ready_plan_path, all_ready = _publish_campaign_outputs(
                spec=spec,
                rows=rows,
                gui_plan=gui_plan,
                inputs=inputs,
                roots=roots,
                environment=environment,
                verified_datasets=verified_datasets,
            )
        except MaterializationContractError as exc:
            return {
                **base,
                "status": "blocked",
                "network_used": network_used,
                "datasets": results,
                "freeze_manifest": str(freeze_path) if freeze_path.is_file() else None,
                "gui_plan": str(ready_plan_path) if ready_plan_path.is_file() else None,
                "campaign_ready": False,
                "blockers": [str(exc)],
            }
    selected_ready = all(row.get("status") == "ready" for row in results)
    return {
        **base,
        "status": "ready" if selected_ready else "blocked",
        "network_used": network_used,
        "datasets": results,
        "freeze_manifest": str(freeze_path),
        "gui_plan": str(ready_plan_path),
        "campaign_ready": all_ready,
    }


def _materialize_one(
    *,
    row: dict[str, Any],
    spec: dict[str, Any],
    gui_plan: dict[str, Any],
    gui_rows: dict[str, dict[str, Any]],
    inputs: MaterializationInputs,
    roots: dict[str, Path],
    environment: dict[str, Any],
    source_seed_root: Path | None,
) -> dict[str, Any]:
    class_name = str(row["moabb_class"])
    source_final = roots["mne_data_root"] / class_name
    output_final = roots["output_root"] / class_name
    receipt_path = roots["checksum_root"] / f"{class_name}.freeze.json"
    checksum_path = roots["checksum_root"] / f"{class_name}.sha256"
    source_checksum_path = roots["checksum_root"] / f"{class_name}.source.sha256"
    validation_path = roots["checksum_root"] / "bids-validation" / f"{class_name}.json"
    expected = {
        "dataset": class_name,
        "dataset_spec_sha256": _dataset_spec_sha256(row),
        "conversion_identity_sha256": environment["conversion_identity_sha256"],
        "source_root": str(source_final),
        "conversion_parent": str(output_final),
        "checksum_manifest": str(checksum_path),
        "source_checksum_manifest": str(source_checksum_path),
        "bids_validation_report": str(validation_path),
    }
    receipt = _read_optional_object(receipt_path)
    receipt_error = _receipt_error(receipt, expected)
    if receipt_error is None and receipt is not None:
        receipt_error = _tree_receipt_error(receipt)
    if receipt_error is None and receipt is not None and inputs.resume:
        current_product_identity = environment["campaign_product_identity_sha256"]
        if receipt.get("campaign_product_identity_sha256") != current_product_identity:
            try:
                bids_root = Path(str(receipt["bids_root"])).resolve(strict=True)
                validation = _normalize_bids_validation(
                    inputs.bids_validator(bids_root),
                    bids_root=bids_root,
                )
                _require_passed_bids_validation(validation)
                _require_unchanged_receipt_tree_after_validation(receipt)
            except (
                MaterializationContractError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as exc:
                return {
                    "dataset": class_name,
                    "status": "failed",
                    "action": "reseal-blocked",
                    "error": str(exc),
                    "network_used": False,
                }
            receipt = {
                **receipt,
                "campaign_product_identity_sha256": current_product_identity,
                "environment_identity_sha256": environment["identity_sha256"],
                "bids_validation": validation,
            }
            _atomic_write_json(validation_path, validation)
            _atomic_write_json(receipt_path, receipt)
            return {
                "dataset": class_name,
                "status": "ready",
                "action": "resealed",
                "bids_root": receipt["bids_root"],
                "dataset_revision_sha256": receipt["dataset_revision_sha256"],
                "network_used": False,
            }
        return {
            "dataset": class_name,
            "status": "ready",
            "action": "reused",
            "bids_root": receipt["bids_root"],
            "dataset_revision_sha256": receipt["dataset_revision_sha256"],
            "network_used": False,
        }
    if receipt_error is None and receipt is not None:
        receipt_error = "resume is disabled"

    has_partial = any(path.exists() for path in (source_final, output_final))
    if receipt is not None or has_partial:
        _invalidate_receipt(
            receipt_path,
            expected=expected,
            reason=receipt_error or "unreceipted materialization exists",
        )
        _publish_campaign_outputs(
            spec=spec,
            rows=[dict(item) for item in spec["datasets"]],
            gui_plan=gui_plan,
            inputs=inputs,
            roots=roots,
            environment=environment,
            verified_datasets=set(),
        )
    if not inputs.allow_download:
        return {
            "dataset": class_name,
            "status": "blocked",
            "action": "invalidated"
            if receipt is not None or has_partial
            else "missing",
            "error": (
                f"{receipt_error}; rerun with --allow-download"
                if receipt_error
                else "dataset is not frozen; rerun with --allow-download"
            ),
            "network_used": False,
        }

    resource_policy = _resource_policy(row)
    resource_receipt: dict[str, Any] | None = None
    if resource_policy:
        resource_result = inputs.resource_probe(resource_policy)
        if resource_result.get("status") != "passed":
            return {
                "dataset": class_name,
                "status": "failed",
                "action": "resource-preflight-blocked",
                "error": "resource preflight failed: "
                + str(resource_result.get("reason") or "unverified response"),
                "network_used": True,
            }
        try:
            resource_receipt = _verified_resource_probe_receipt(
                resource_policy,
                resource_result,
            )
        except MaterializationContractError as exc:
            return {
                "dataset": class_name,
                "status": "failed",
                "action": "resource-preflight-blocked",
                "error": f"resource preflight failed: {exc}",
                "network_used": True,
            }

    source_stage_root = roots["mne_data_root"] / ".staging"
    output_stage_root = roots["output_root"] / ".staging"
    _quarantine_orphan_stages(source_stage_root, roots["mne_data_root"], class_name)
    _quarantine_orphan_stages(output_stage_root, roots["output_root"], class_name)
    token = uuid.uuid4().hex
    source_stage = source_stage_root / f"{class_name}.{token}"
    output_stage = output_stage_root / f"{class_name}.{token}"
    source_stage.mkdir(parents=True)
    output_stage.mkdir(parents=True)
    created_finals: list[tuple[Path, Path, str]] = []
    action = "rebuilt" if receipt is not None or has_partial else "materialized"
    try:
        source_mode = str(row["source_mode"])
        dataset: Any | None = None
        source_seed_receipt: dict[str, Any] | None = None
        if source_seed_root is not None:
            source_seed_receipt = _copy_verified_source_seed(
                source_seed_root, source_stage
            )
        if source_mode == SOURCE_MODE_MOABB_CONVERT:
            with _temporary_mne_environment(source_stage):
                dataset = inputs.dataset_factory(class_name)
                converter = _require_converter(
                    getattr(dataset, "convert_to_bids", None), class_name
                )
                returned = Path(
                    converter(
                        path=output_stage,
                        subjects=list(row["subjects"]),
                        overwrite=False,
                        format=str(row["output_format"]),
                        verbose="ERROR",
                        generate_figures=False,
                    )
                )
            staged_bids_root = _validate_returned_bids_root(
                returned,
                output_stage=output_stage,
                gui_row=gui_rows[class_name],
            )
        else:
            staged_bids_root, resource_receipt = _materialize_formal_bids_mirror(
                row=row,
                source_stage=source_stage,
                output_stage=output_stage,
                inputs=inputs,
            )
        returned_relative = staged_bids_root.relative_to(output_stage.resolve())

        _quarantine_existing(source_final, roots["mne_data_root"], class_name, "source")
        _quarantine_existing(output_final, roots["output_root"], class_name, "bids")
        source_stage.replace(source_final)
        created_finals.append(
            (source_final, roots["mne_data_root"], "published-source")
        )
        output_stage.replace(output_final)
        created_finals.append((output_final, roots["output_root"], "published-bids"))
        bids_final = (output_final / returned_relative).resolve(strict=True)
        oracle = (
            _verified_bids_oracle(
                dataset=dataset,
                bids_root=bids_final,
                supervised_classes=row["supervised_classes"],
            )
            if source_mode == SOURCE_MODE_MOABB_CONVERT
            else _verified_formal_bids_mirror_oracle(
                bids_root=bids_final,
                supervised_classes=row["supervised_classes"],
                expected_trial_type_values=row["formal_bids_mirror"][
                    "expected_trial_type_values"
                ],
            )
        )
        # Bind the published tree before authoritative validation. The exact
        # aggregate is stored alongside the validator report below.
        source_artifacts, source_revision = _hash_tree(source_final)
        bids_artifacts, bids_revision = _hash_tree(bids_final)
        _require_source_artifacts(source_artifacts)
        upstream_download_artifacts = (
            list(resource_receipt["upstream_download_artifacts"])
            if source_mode == SOURCE_MODE_FORMAL_BIDS_MIRROR
            and isinstance(resource_receipt, dict)
            else []
        )
        validation = _normalize_bids_validation(
            inputs.bids_validator(bids_final),
            bids_root=bids_final,
        )
        _require_passed_bids_validation(validation)
        post_source_artifacts, post_source_revision = _hash_tree(source_final)
        post_bids_artifacts, post_bids_revision = _hash_tree(bids_final)
        _require_matching_tree_snapshots(
            before_source_artifacts=source_artifacts,
            before_source_revision=source_revision,
            before_bids_artifacts=bids_artifacts,
            before_bids_revision=bids_revision,
            after_source_artifacts=post_source_artifacts,
            after_source_revision=post_source_revision,
            after_bids_artifacts=post_bids_artifacts,
            after_bids_revision=post_bids_revision,
        )
        _atomic_write_json(validation_path, validation)
        receipt_payload = {
            "schema_version": "1.0.0",
            "status": "ready",
            **expected,
            "campaign_product_identity_sha256": environment[
                "campaign_product_identity_sha256"
            ],
            "environment_identity_sha256": environment["identity_sha256"],
            "subjects": list(row["subjects"]),
            "output_format": row["output_format"],
            "source_mode": source_mode,
            "bids_root": str(bids_final),
            "source_revision_sha256": source_revision,
            "dataset_revision_sha256": bids_revision,
            "source_artifacts": source_artifacts,
            "bids_artifacts": bids_artifacts,
            "retained_source_bytes": sum(
                int(item["size_bytes"]) for item in source_artifacts
            ),
            "upstream_download_status": (
                "verified"
                if source_mode == SOURCE_MODE_FORMAL_BIDS_MIRROR
                else "not-applicable"
            ),
            "upstream_download_bytes": sum(
                int(item["size_bytes"]) for item in upstream_download_artifacts
            ),
            "upstream_download_artifacts": upstream_download_artifacts,
            "upstream_download_revision_sha256": (
                _canonical_sha256(upstream_download_artifacts)
                if upstream_download_artifacts
                else None
            ),
            **oracle,
            "license_status": row["license_status"],
            "redistribution_allowed": row.get("redistribution_allowed"),
            "license_note": row.get("license_note"),
            "resource_status": "verified",
            "resource_preflight_receipt": resource_receipt,
            "source_seed_receipt": source_seed_receipt,
            "bids_validation": validation,
        }
        _write_sha256_manifest(checksum_path, bids_artifacts)
        _write_sha256_manifest(source_checksum_path, source_artifacts)
        _atomic_write_json(receipt_path, receipt_payload)
        return {
            "dataset": class_name,
            "status": "ready",
            "action": action,
            "bids_root": str(bids_final),
            "dataset_revision_sha256": bids_revision,
            "network_used": True,
        }
    except Exception as exc:
        for path, owner_root, label in reversed(created_finals):
            _quarantine_path(path, owner_root, class_name, label)
        _quarantine_path(
            source_stage, roots["mne_data_root"], class_name, "source-stage"
        )
        _quarantine_path(output_stage, roots["output_root"], class_name, "bids-stage")
        _atomic_write_json(
            roots["checksum_root"] / "failures" / f"{class_name}.{token}.json",
            {
                "schema_version": "1.0.0",
                "status": "failed",
                "dataset": class_name,
                "dataset_spec_sha256": expected["dataset_spec_sha256"],
                "conversion_identity_sha256": expected["conversion_identity_sha256"],
                "campaign_product_identity_sha256": environment[
                    "campaign_product_identity_sha256"
                ],
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        _invalidate_receipt(receipt_path, expected=expected, reason=str(exc))
        return {
            "dataset": class_name,
            "status": "failed",
            "action": "quarantined",
            "error": str(exc),
            "network_used": True,
        }


def _require_converter(
    converter: Any,
    class_name: str,
) -> Callable[..., Any]:
    if not callable(converter):
        raise MaterializationContractError(
            f"{class_name} has no BaseDataset.convert_to_bids method"
        )
    return converter


def _require_source_artifacts(artifacts: list[dict[str, Any]]) -> None:
    if not artifacts:
        raise MaterializationContractError(
            "MOABB source cache is empty or escaped the declared MNE_DATA root"
        )


def _materialize_formal_bids_mirror(
    *,
    row: dict[str, Any],
    source_stage: Path,
    output_stage: Path,
    inputs: MaterializationInputs,
) -> tuple[Path, dict[str, Any]]:
    """Materialize one manifest-pinned formal BIDS subset without conversion."""
    policy = dict(row["formal_bids_mirror"])
    manifest_hosts = frozenset(str(item) for item in policy["manifest_hosts"])
    raw_manifest = inputs.mirror_manifest_fetcher(
        str(policy["manifest_url"]),
        manifest_hosts,
        int(policy["manifest_maximum_bytes"]),
    )
    entries = _verified_formal_bids_mirror_entries(
        raw_manifest,
        policy=policy,
        subjects=list(row["subjects"]),
    )
    root_basename = str(policy["root_basename"])
    output_bids_root = output_stage / root_basename
    output_bids_root.mkdir(parents=True)
    allowed_final_hosts = frozenset(
        str(item) for item in (*policy["download_hosts"], *policy["redirect_hosts"])
    )
    downloads: list[dict[str, Any]] = []
    for entry in entries:
        relative = str(entry["path"])
        target = output_bids_root.joinpath(*PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        receipt = inputs.mirror_file_downloader(
            str(entry["bytes_url"]),
            target,
            allowed_final_hosts,
            int(entry["size"]),
        )
        downloads.append(
            _verified_mirror_download_receipt(
                entry=entry,
                target=target,
                receipt=receipt,
                allowed_final_hosts=allowed_final_hosts,
            )
        )
    _atomic_write_json(
        source_stage / "formal-bids-mirror-provenance.json",
        {
            "schema_version": "1.0.0",
            "source_mode": SOURCE_MODE_FORMAL_BIDS_MIRROR,
            "manifest_url": policy["manifest_url"],
            "manifest_projection": dict(policy["full_projection"]),
            "selected_projection": dict(policy["selected_projection"]),
            "selected_subjects": list(row["subjects"]),
            "provenance": dict(policy["provenance"]),
        },
    )
    marker = output_bids_root / "dataset_description.json"
    if not marker.is_file() or marker.is_symlink():
        raise MaterializationContractError(
            "formal BIDS mirror lacks dataset_description.json"
        )
    selected_pin = dict(policy["selected_projection"])
    return output_bids_root.resolve(strict=True), {
        "status": "verified",
        "kind": SOURCE_MODE_FORMAL_BIDS_MIRROR,
        "manifest_url": policy["manifest_url"],
        "manifest_projection": dict(policy["full_projection"]),
        "selected_projection": selected_pin,
        "selected_subjects": list(row["subjects"]),
        "provenance": dict(policy["provenance"]),
        "downloads": downloads,
        "upstream_download_artifacts": [
            {
                "relative_path": item["path"],
                "size_bytes": item["size_bytes"],
                "source_url": item["bytes_url"],
                "upstream_checksum": {
                    "algorithm": item["upstream_checksum_algorithm"],
                    "value": item["upstream_checksum"],
                },
                "checksum": {
                    "algorithm": "sha256",
                    "value": item["sha256"],
                },
            }
            for item in downloads
        ],
    }


def _verified_formal_bids_mirror_entries(
    raw_manifest: bytes,
    *,
    policy: dict[str, Any],
    subjects: list[int],
) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(raw_manifest)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MaterializationContractError(
            f"formal BIDS mirror manifest is invalid JSON: {exc}"
        ) from exc
    if policy.get("entries_pointer") != "$" or not isinstance(parsed, list):
        raise MaterializationContractError(
            "formal BIDS mirror manifest must be the pinned top-level list"
        )
    projection = [_normalized_mirror_entry(value) for value in parsed]
    projection.sort(key=lambda item: str(item["path"]))
    if len({str(item["path"]) for item in projection}) != len(projection):
        raise MaterializationContractError(
            "formal BIDS mirror manifest contains duplicate paths"
        )
    _require_projection_matches_pin(
        projection,
        dict(policy["full_projection"]),
        label="full formal BIDS mirror manifest",
    )
    download_hosts = {str(item) for item in policy["download_hosts"]}
    for entry in projection:
        parsed_url = urllib.parse.urlparse(str(entry["bytes_url"]))
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname not in download_hosts
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise MaterializationContractError(
                "formal BIDS mirror bytes_url must be stable, HTTPS, and allowlisted"
            )
    subject_roots = {
        str(policy["subject_path_template"]).format(subject=subject)
        for subject in subjects
    }
    include_paths = {str(item) for item in policy["include_paths"]}
    include_prefixes = tuple(str(item) for item in policy["include_prefixes"])
    selected = [
        entry
        for entry in projection
        if str(entry["path"]) in include_paths
        or str(entry["path"]).startswith(include_prefixes)
        or str(entry["path"]).split("/", 1)[0] in subject_roots
    ]
    selected_paths = {str(entry["path"]) for entry in selected}
    if not include_paths.issubset(selected_paths):
        raise MaterializationContractError(
            "formal BIDS mirror is missing an explicitly included root file"
        )
    for subject_root in subject_roots:
        if not any(path.startswith(subject_root + "/") for path in selected_paths):
            raise MaterializationContractError(
                f"formal BIDS mirror has no entries for {subject_root}"
            )
    _require_projection_matches_pin(
        selected,
        dict(policy["selected_projection"]),
        label="selected formal BIDS mirror projection",
    )
    return selected


def _normalized_mirror_entry(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(_MIRROR_PROJECTION_FIELDS).difference(value):
        raise MaterializationContractError(
            "formal BIDS mirror entry lacks a projection field"
        )
    relative = str(value["path"])
    size = value["size"]
    algorithm = str(value["checksum_algorithm"]).casefold()
    checksum = str(value["checksum"]).casefold()
    if (
        not _safe_mirror_relative_path(relative, allow_directory=False)
        or type(size) is not int
        or size <= 0
        or algorithm not in {"sha256", "git"}
        or (algorithm == "sha256" and not _SHA256.fullmatch(checksum))
        or (algorithm == "git" and not re.fullmatch(r"[0-9a-f]{40}", checksum))
    ):
        raise MaterializationContractError(
            "formal BIDS mirror entry path/size/checksum is invalid"
        )
    return {
        "path": relative,
        "size": size,
        "checksum_algorithm": algorithm,
        "checksum": checksum,
        "bytes_url": str(value["bytes_url"]),
    }


def _require_projection_matches_pin(
    projection: Sequence[dict[str, Any]],
    pin: dict[str, Any],
    *,
    label: str,
) -> None:
    total_bytes = sum(int(item["size"]) for item in projection)
    digest = _canonical_sha256(list(projection))
    if (
        len(projection) != pin.get("entry_count")
        or total_bytes != pin.get("total_bytes")
        or digest != pin.get("projection_sha256")
    ):
        raise MaterializationContractError(f"{label} differs from its pinned identity")


def _verified_mirror_download_receipt(
    *,
    entry: dict[str, Any],
    target: Path,
    receipt: dict[str, Any],
    allowed_final_hosts: frozenset[str],
) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise MaterializationContractError(
            "formal BIDS mirror downloader returned no receipt"
        )
    final_url = str(receipt.get("final_url") or entry["bytes_url"])
    final = urllib.parse.urlparse(final_url)
    if final.scheme != "https" or final.hostname not in allowed_final_hosts:
        raise MaterializationContractError(
            "formal BIDS mirror download redirected off allowlist"
        )
    size, sha256_digest, git_digest = _mirror_file_digests(target)
    algorithm = str(entry["checksum_algorithm"])
    observed = sha256_digest if algorithm == "sha256" else git_digest
    if size != entry["size"] or observed != entry["checksum"]:
        raise MaterializationContractError(
            f"formal BIDS mirror checksum changed: {entry['path']}"
        )
    if receipt.get("size_bytes") not in {None, size}:
        raise MaterializationContractError(
            f"formal BIDS mirror downloader size disagrees: {entry['path']}"
        )
    return {
        "path": entry["path"],
        "size_bytes": size,
        "upstream_checksum_algorithm": algorithm,
        "upstream_checksum": entry["checksum"],
        "sha256": sha256_digest,
        "bytes_url": entry["bytes_url"],
        "final_host": final.hostname,
    }


def _mirror_file_digests(path: Path) -> tuple[int, str, str]:
    before = _file_identity(path)
    sha256 = hashlib.sha256()
    git = hashlib.sha1(usedforsecurity=False)
    git.update(f"blob {before[3]}\0".encode())
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            sha256.update(chunk)
            git.update(chunk)
    after = _file_identity(path)
    if before != after:
        raise MaterializationContractError(
            f"formal BIDS mirror file changed while verified: {path}"
        )
    return after[3], sha256.hexdigest(), git.hexdigest()


def _publish_campaign_outputs(
    *,
    spec: dict[str, Any],
    rows: list[dict[str, Any]],
    gui_plan: dict[str, Any],
    inputs: MaterializationInputs,
    roots: dict[str, Path],
    environment: dict[str, Any],
    verified_datasets: set[str],
) -> tuple[Path, Path, bool]:
    candidates: list[
        tuple[dict[str, Any], str, dict[str, Any] | None, dict[str, Any], str | None]
    ] = []
    for row in rows:
        class_name = str(row["moabb_class"])
        receipt = _read_optional_object(
            roots["checksum_root"] / f"{class_name}.freeze.json"
        )
        expected = {
            "dataset": class_name,
            "dataset_spec_sha256": _dataset_spec_sha256(row),
            "conversion_identity_sha256": environment["conversion_identity_sha256"],
            "source_root": str(roots["mne_data_root"] / class_name),
            "conversion_parent": str(roots["output_root"] / class_name),
            "checksum_manifest": str(roots["checksum_root"] / f"{class_name}.sha256"),
            "source_checksum_manifest": str(
                roots["checksum_root"] / f"{class_name}.source.sha256"
            ),
            "bids_validation_report": str(
                roots["checksum_root"] / "bids-validation" / f"{class_name}.json"
            ),
        }
        receipt_error = _receipt_error(receipt, expected)
        if (
            receipt_error is None
            and receipt is not None
            and receipt.get("campaign_product_identity_sha256")
            != environment["campaign_product_identity_sha256"]
        ):
            receipt_error = "campaign product identity requires reseal"
        candidates.append((row, class_name, receipt, expected, receipt_error))

    # A ready campaign is sealed only after a final full-tree pass immediately
    # before publication.  This deliberately rechecks datasets verified in the
    # same invocation: the validator and concurrent processes sit outside our
    # ownership boundary and may have changed bytes since their earlier pass.
    structurally_complete = all(
        receipt is not None and receipt_error is None
        for _row, _class_name, receipt, _expected, receipt_error in candidates
    )
    if structurally_complete:
        rehashed_candidates = []
        for row, class_name, receipt, expected, _receipt_error_value in candidates:
            receipt_error = _tree_receipt_error(receipt or {})
            if receipt_error is not None and class_name in verified_datasets:
                raise MaterializationContractError(
                    f"{class_name} changed during final campaign seal: {receipt_error}"
                )
            rehashed_candidates.append(
                (row, class_name, receipt, expected, receipt_error)
            )
        candidates = rehashed_candidates

    receipt_by_dataset: dict[str, dict[str, Any]] = {}
    frozen_rows: list[dict[str, Any]] = []
    for row, class_name, receipt, expected, receipt_error in candidates:
        if receipt_error is None and receipt is not None:
            receipt_by_dataset[class_name] = receipt
            frozen_rows.append(_frozen_dataset_row(row, receipt))
        else:
            if (
                receipt is not None
                and receipt.get("status") == "ready"
                and receipt_error != "campaign product identity requires reseal"
            ):
                _invalidate_receipt(
                    roots["checksum_root"] / f"{class_name}.freeze.json",
                    expected=expected,
                    reason=receipt_error or "freeze receipt is not ready",
                )
            frozen_rows.append(
                {
                    **row,
                    "status": "pending",
                    "bids_checksum_status": "ABSENT",
                }
            )
    all_ready = len(receipt_by_dataset) == len(rows)
    freeze_payload = {
        "schema_version": "1.0.0",
        "profile_id": spec.get("profile_id"),
        "status": "ready" if all_ready else "partial",
        "moabb_release": spec["moabb_release"],
        "resource_policy": spec["resource_policy"],
        "materialization": {
            "manifest_sha256": _sha256_file(inputs.manifest_path),
            "gui_plan_sha256": _sha256_file(inputs.gui_plan_path),
            "environment": environment,
            "environment_identity_sha256": environment["identity_sha256"],
            "conversion_identity_sha256": environment["conversion_identity_sha256"],
            "campaign_product_identity_sha256": environment[
                "campaign_product_identity_sha256"
            ],
            "mne_data_root": str(roots["mne_data_root"]),
            "output_root": str(roots["output_root"]),
            "checksum_root": str(roots["checksum_root"]),
            "ready_count": len(receipt_by_dataset),
            "dataset_count": len(rows),
        },
        "datasets": frozen_rows,
    }
    freeze_path = roots["checksum_root"] / FREEZE_MANIFEST_NAME
    _atomic_write_json(freeze_path, freeze_payload)

    plan_payload = json.loads(json.dumps(gui_plan))
    plan_resource_policy = plan_payload.get("resource_policy")
    if isinstance(plan_resource_policy, dict):
        plan_resource_policy["data_root"] = str(roots["output_root"])
        plan_resource_policy["checksum_root"] = str(roots["checksum_root"])
    for plan_row in plan_payload["datasets"]:
        class_name = str(plan_row["moabb_class"])
        receipt = receipt_by_dataset.get(class_name)
        bids = plan_row.setdefault("bids", {})
        bids["conversion_parent"] = str(roots["output_root"] / class_name)
        bids["checksum_manifest"] = str(roots["checksum_root"] / f"{class_name}.sha256")
        if receipt is None:
            plan_row["execution_state"] = "awaiting_dataset_materialization"
            bids["root"] = None
            bids["dataset_revision_sha256"] = None
            plan_row["oracle"] = {"state": "awaiting_dataset_materialization"}
        else:
            plan_row["execution_state"] = "ready"
            bids["root"] = receipt["bids_root"]
            bids["dataset_revision_sha256"] = receipt["dataset_revision_sha256"]
            plan_row["oracle"] = {
                "state": "pinned",
                "expected_events": list(receipt["event_names"]),
                "expected_classes": list(receipt["supervised_classes"]),
                "source_event_id": dict(receipt["event_id"]),
                "expected_product_class_mapping": (
                    _expected_product_class_mapping(receipt["supervised_classes"])
                ),
                "bids_event_values": dict(receipt["bids_event_values"]),
                "bids_value_crosscheck": receipt["bids_value_crosscheck"],
            }
            plan_row["source_policy"] = {
                "license_status": receipt["license_status"],
                "redistribution_allowed": receipt.get("redistribution_allowed"),
            }
    plan_payload["materialization"] = {
        "status": "ready" if all_ready else "partial",
        "freeze_manifest": str(freeze_path),
        "freeze_manifest_sha256": _sha256_file(freeze_path),
        "environment_identity_sha256": environment["identity_sha256"],
        "conversion_identity_sha256": environment["conversion_identity_sha256"],
        "campaign_product_identity_sha256": environment[
            "campaign_product_identity_sha256"
        ],
    }
    ready_plan_path = roots["checksum_root"] / READY_GUI_PLAN_NAME
    _atomic_write_json(ready_plan_path, plan_payload)
    return freeze_path, ready_plan_path, all_ready


def _expected_product_class_mapping(
    supervised_classes: list[str],
) -> list[dict[str, int | str]]:
    """Mirror the product timestamp sort and epoch label-map reindex contract."""
    return [
        {
            "class_index": index,
            "event_code": str(index),
            "class_name": class_name,
        }
        for index, class_name in enumerate(sorted(supervised_classes))
    ]


def _frozen_dataset_row(
    spec_row: dict[str, Any], receipt: dict[str, Any]
) -> dict[str, Any]:
    source_artifacts = list(receipt["source_artifacts"])
    source_mode = str(receipt.get("source_mode") or SOURCE_MODE_MOABB_CONVERT)
    retained_source_bytes = sum(int(item["size_bytes"]) for item in source_artifacts)
    source_download_bytes = (
        int(receipt["upstream_download_bytes"])
        if source_mode == SOURCE_MODE_FORMAL_BIDS_MIRROR
        else retained_source_bytes
    )
    return {
        **spec_row,
        "status": "ready",
        "source_mode": source_mode,
        "source_download_bytes": source_download_bytes,
        "retained_source_bytes": retained_source_bytes,
        "source_checksum_status": "verified",
        "source_artifacts": source_artifacts,
        "resource_status": receipt["resource_status"],
        "source_root": receipt["source_root"],
        "conversion_parent": receipt["conversion_parent"],
        "source_revision_sha256": receipt["source_revision_sha256"],
        "bids_root": receipt["bids_root"],
        "bids_checksum_status": "verified",
        "bids_artifacts": list(receipt["bids_artifacts"]),
        "dataset_revision_sha256": receipt["dataset_revision_sha256"],
        "checksum_manifest": receipt["checksum_manifest"],
        "source_checksum_manifest": receipt["source_checksum_manifest"],
        "event_names": list(receipt["event_names"]),
        "event_id": dict(receipt["event_id"]),
        "bids_event_values": dict(receipt["bids_event_values"]),
        "bids_value_crosscheck": receipt["bids_value_crosscheck"],
        "supervised_classes": list(receipt["supervised_classes"]),
        "resource_preflight_receipt": receipt.get("resource_preflight_receipt"),
        "upstream_download_status": receipt.get("upstream_download_status"),
        "upstream_download_bytes": receipt.get("upstream_download_bytes"),
        "upstream_download_artifacts": list(
            receipt.get("upstream_download_artifacts") or []
        ),
        "upstream_download_revision_sha256": receipt.get(
            "upstream_download_revision_sha256"
        ),
        "bids_validation_report": receipt["bids_validation_report"],
        "bids_validation": dict(receipt["bids_validation"]),
    }


def _validate_contracts(
    spec: dict[str, Any], gui_plan: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    release = spec.get("moabb_release")
    if not isinstance(release, dict) or not str(release.get("version") or ""):
        raise MaterializationContractError("manifest MOABB release is missing")
    policy = spec.get("resource_policy")
    if not isinstance(policy, dict):
        raise MaterializationContractError("manifest resource_policy is missing")
    rows_value = spec.get("datasets")
    plan_value = gui_plan.get("datasets")
    if not isinstance(rows_value, list) or not rows_value:
        raise MaterializationContractError("manifest datasets must be a non-empty list")
    if not isinstance(plan_value, list) or not plan_value:
        raise MaterializationContractError("GUI plan datasets must be a non-empty list")
    rows: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, value in enumerate(rows_value):
        if not isinstance(value, dict):
            raise MaterializationContractError(f"datasets[{index}] must be an object")
        row = dict(value)
        class_name = str(row.get("moabb_class") or "")
        if (
            not _SAFE_COMPONENT.fullmatch(class_name)
            or class_name in {".", ".."}
            or class_name in names
        ):
            raise MaterializationContractError(
                f"datasets[{index}].moabb_class is unsafe or duplicated"
            )
        names.add(class_name)
        source_mode = str(row.get("source_mode") or SOURCE_MODE_MOABB_CONVERT)
        if source_mode not in {
            SOURCE_MODE_MOABB_CONVERT,
            SOURCE_MODE_FORMAL_BIDS_MIRROR,
        }:
            raise MaterializationContractError(
                f"{class_name}.source_mode is unsupported: {source_mode}"
            )
        row["source_mode"] = source_mode
        subjects = row.get("subjects")
        if (
            not isinstance(subjects, list)
            or not subjects
            or any(type(subject) is not int or subject <= 0 for subject in subjects)
            or len(set(subjects)) != len(subjects)
        ):
            raise MaterializationContractError(
                f"{class_name}.subjects must be unique positive integers"
            )
        output_format = row.get("output_format")
        if output_format not in SUPPORTED_FORMATS:
            raise MaterializationContractError(
                f"{class_name}.output_format is not a supported BIDS EEG format"
            )
        if (
            source_mode == SOURCE_MODE_MOABB_CONVERT
            and output_format not in CONVERT_OUTPUT_FORMATS
        ):
            raise MaterializationContractError(
                f"{class_name}.output_format is not supported by convert_to_bids"
            )
        expected_bytes = row.get("source_download_bytes")
        if type(expected_bytes) is not int or expected_bytes <= 0:
            raise MaterializationContractError(
                f"{class_name}.source_download_bytes must be a positive disk bound"
            )
        supervised_classes = row.get("supervised_classes")
        if (
            not isinstance(supervised_classes, list)
            or not supervised_classes
            or any(
                not isinstance(label, str) or not label.strip()
                for label in supervised_classes
            )
            or len(set(supervised_classes)) != len(supervised_classes)
        ):
            raise MaterializationContractError(
                f"{class_name}.supervised_classes must be explicit unique labels"
            )
        _validate_license_policy(row, class_name)
        _validate_resource_policy(row, class_name)
        if source_mode == SOURCE_MODE_FORMAL_BIDS_MIRROR:
            _validate_formal_bids_mirror_policy(row, class_name)
        rows.append(row)

    gui_rows: dict[str, dict[str, Any]] = {}
    for value in plan_value:
        if not isinstance(value, dict):
            raise MaterializationContractError("GUI plan dataset row is not an object")
        class_name = str(value.get("moabb_class") or "")
        if class_name in gui_rows:
            raise MaterializationContractError(
                f"GUI plan dataset {class_name} is duplicated"
            )
        gui_rows[class_name] = value
    if set(gui_rows) != names:
        raise MaterializationContractError(
            "materialization manifest and GUI plan dataset inventories differ"
        )
    for row in rows:
        class_name = str(row["moabb_class"])
        plan_row = gui_rows[class_name]
        if list(plan_row.get("subjects") or ()) != list(row["subjects"]):
            raise MaterializationContractError(
                f"{class_name} subjects differ between manifest and GUI plan"
            )
        bids = plan_row.get("bids")
        if not isinstance(bids, dict) or bids.get("format") != row["output_format"]:
            raise MaterializationContractError(
                f"{class_name} output format differs between manifest and GUI plan"
            )
        if (
            str(plan_row.get("source_mode") or SOURCE_MODE_MOABB_CONVERT)
            != row["source_mode"]
        ):
            raise MaterializationContractError(
                f"{class_name} source mode differs between manifest and GUI plan"
            )
        resolution = bids.get("root_resolution")
        expected_resolution_source = (
            "formal_bids_mirror_receipt"
            if row["source_mode"] == SOURCE_MODE_FORMAL_BIDS_MIRROR
            else "convert_to_bids_return_value"
        )
        if not isinstance(resolution, dict) or resolution != {
            "source": expected_resolution_source,
            "must_be_descendant_of_conversion_parent": True,
            "required_basename_prefix": "MNE-BIDS-",
            "required_marker": "dataset_description.json",
        }:
            raise MaterializationContractError(
                f"{class_name} GUI root resolution differs from its source mode"
            )
    return rows, gui_rows


def _validate_license_policy(row: dict[str, Any], class_name: str) -> None:
    status = row.get("license_status")
    if status == "verified":
        return
    if status == "local-use-only":
        if row.get("redistribution_allowed") is not False:
            raise MaterializationContractError(
                f"{class_name} local-use-only data must prohibit redistribution"
            )
        if not str(row.get("license_note") or "").strip():
            raise MaterializationContractError(
                f"{class_name} local-use-only policy must explain the unknown license"
            )
        return
    raise MaterializationContractError(
        f"{class_name} license policy is unresolved: {status or 'missing'}"
    )


def _validate_resource_policy(row: dict[str, Any], class_name: str) -> None:
    status = row.get("resource_status")
    policy = row.get("resource_preflight")
    if row.get("source_mode") == SOURCE_MODE_FORMAL_BIDS_MIRROR:
        if status != FORMAL_BIDS_MIRROR_REQUIRED or policy is not None:
            raise MaterializationContractError(
                f"{class_name} formal BIDS mirror must use its pinned manifest gate"
            )
        return
    if status == "verified" and policy is None:
        return
    if status != "RESOURCE_PREFLIGHT_REQUIRED" or not isinstance(policy, dict):
        raise MaterializationContractError(
            f"{class_name} resource policy must be verified or require a probe"
        )
    if policy.get("kind") != "http_range":
        raise MaterializationContractError(
            f"{class_name} resource preflight kind must be http_range"
        )
    allowed_hosts = policy.get("allowed_hosts")
    statuses = policy.get("accepted_statuses")
    resources = policy.get("resources")
    maximum_total = policy.get("maximum_total_bytes")
    if (
        not isinstance(allowed_hosts, list)
        or not allowed_hosts
        or not isinstance(statuses, list)
        or not statuses
        or any(type(status) is not int for status in statuses)
        or not isinstance(resources, list)
        or not resources
        or type(maximum_total) is not int
        or maximum_total <= 0
        or maximum_total != row.get("source_download_bytes")
    ):
        raise MaterializationContractError(
            f"{class_name} resource preflight is not fail-closed"
        )
    seen_urls: set[str] = set()
    for index, resource in enumerate(resources):
        if not isinstance(resource, dict):
            raise MaterializationContractError(
                f"{class_name} resource_preflight.resources[{index}] is invalid"
            )
        url = str(resource.get("url") or "")
        parsed = urllib.parse.urlparse(url)
        maximum = resource.get("maximum_bytes")
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.hostname not in allowed_hosts
            or url in seen_urls
            or type(maximum) is not int
            or maximum <= 0
            or maximum > maximum_total
        ):
            raise MaterializationContractError(
                f"{class_name} resource_preflight.resources[{index}] is not fail-closed"
            )
        seen_urls.add(url)


def _validate_formal_bids_mirror_policy(
    row: dict[str, Any],
    class_name: str,
) -> None:
    policy = row.get("formal_bids_mirror")
    if not isinstance(policy, dict):
        raise MaterializationContractError(
            f"{class_name}.formal_bids_mirror must be an object"
        )
    manifest_url = str(policy.get("manifest_url") or "")
    manifest = urllib.parse.urlparse(manifest_url)
    manifest_hosts = policy.get("manifest_hosts")
    download_hosts = policy.get("download_hosts")
    redirect_hosts = policy.get("redirect_hosts")
    if (
        manifest.scheme != "https"
        or not manifest.hostname
        or manifest.query
        or manifest.fragment
        or not isinstance(manifest_hosts, list)
        or manifest.hostname not in manifest_hosts
        or not _valid_host_list(download_hosts)
        or not _valid_host_list(redirect_hosts)
        or policy.get("entries_pointer") != "$"
        or policy.get("projection_fields") != list(_MIRROR_PROJECTION_FIELDS)
    ):
        raise MaterializationContractError(
            f"{class_name}.formal_bids_mirror manifest/host contract is invalid"
        )
    manifest_maximum_bytes = policy.get("manifest_maximum_bytes")
    root_basename = str(policy.get("root_basename") or "")
    subject_template = str(policy.get("subject_path_template") or "")
    include_paths = policy.get("include_paths")
    include_prefixes = policy.get("include_prefixes")
    if (
        type(manifest_maximum_bytes) is not int
        or manifest_maximum_bytes <= 0
        or not _SAFE_COMPONENT.fullmatch(root_basename)
        or not root_basename.startswith("MNE-BIDS-")
        or root_basename in {".", ".."}
        or subject_template != "sub-{subject}"
        or not isinstance(include_paths, list)
        or not include_paths
        or not isinstance(include_prefixes, list)
        or any(
            not _safe_mirror_relative_path(str(path), allow_directory=False)
            for path in include_paths
        )
        or any(not _safe_mirror_prefix(str(prefix)) for prefix in include_prefixes)
        or len(set(include_paths)) != len(include_paths)
        or len(set(include_prefixes)) != len(include_prefixes)
    ):
        raise MaterializationContractError(
            f"{class_name}.formal_bids_mirror selection contract is invalid"
        )
    full = policy.get("full_projection")
    selected = policy.get("selected_projection")
    _validate_projection_pin(full, f"{class_name} full mirror projection")
    _validate_projection_pin(selected, f"{class_name} selected mirror projection")
    if not isinstance(selected, dict) or selected.get("total_bytes") != row.get(
        "source_download_bytes"
    ):
        raise MaterializationContractError(
            f"{class_name} source byte count must equal the selected mirror projection"
        )
    expected_events = policy.get("expected_trial_type_values")
    if (
        not isinstance(expected_events, dict)
        or set(expected_events) != set(row["supervised_classes"])
        or any(
            not isinstance(label, str)
            or not label
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for label, value in expected_events.items()
        )
        or len(set(expected_events.values())) != len(expected_events)
    ):
        raise MaterializationContractError(
            f"{class_name} mirror event oracle must pin each supervised class"
        )
    if (
        policy.get("native_format") != row.get("output_format")
        or policy.get("native_format") not in FORMAL_BIDS_MIRROR_FORMATS
    ):
        raise MaterializationContractError(
            f"{class_name} mirror native format must match the preserved BIDS bytes"
        )
    provenance = policy.get("provenance")
    if not isinstance(provenance, dict) or any(
        not str(provenance.get(field) or "").strip()
        for field in (
            "dataset_id",
            "version",
            "source_doi",
            "bids_doi",
            "repository_tag",
            "repository_tag_object",
            "repository_commit",
            "generated_by",
        )
    ):
        raise MaterializationContractError(
            f"{class_name} mirror provenance is incomplete"
        )


def _valid_host_list(value: Any) -> bool:
    return bool(
        isinstance(value, list)
        and value
        and all(
            isinstance(host, str)
            and host
            and host == host.casefold()
            and "/" not in host
            for host in value
        )
        and len(set(value)) == len(value)
    )


def _validate_projection_pin(value: Any, label: str) -> None:
    if (
        not isinstance(value, dict)
        or type(value.get("entry_count")) is not int
        or int(value["entry_count"]) <= 0
        or type(value.get("total_bytes")) is not int
        or int(value["total_bytes"]) <= 0
        or not _SHA256.fullmatch(str(value.get("projection_sha256") or ""))
    ):
        raise MaterializationContractError(f"{label} is invalid")


def _safe_mirror_relative_path(value: str, *, allow_directory: bool) -> bool:
    if not value or "\\" in value or value.startswith("/") or value.endswith("/"):
        return False
    parts = PurePosixPath(value).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return False
    return allow_directory or bool(PurePosixPath(value).name)


def _safe_mirror_prefix(value: str) -> bool:
    return bool(
        value.endswith("/")
        and _safe_mirror_relative_path(value[:-1], allow_directory=True)
    )


def _resource_policy(row: dict[str, Any]) -> dict[str, Any] | None:
    policy = row.get("resource_preflight")
    return dict(policy) if isinstance(policy, dict) else None


def _select_rows(
    rows: list[dict[str, Any]], selected: str | None
) -> list[dict[str, Any]]:
    if selected is None:
        return rows
    matches = [row for row in rows if row["moabb_class"] == selected]
    if not matches:
        raise MaterializationContractError(
            f"unknown --dataset {selected}; choose a manifest class"
        )
    return matches


def _validated_roots(inputs: MaterializationInputs) -> dict[str, Path]:
    roots = {
        "mne_data_root": inputs.mne_data_root.expanduser().resolve(),
        "output_root": inputs.output_root.expanduser().resolve(),
        "checksum_root": inputs.checksum_root.expanduser().resolve(),
    }
    for name, path in roots.items():
        if not path.is_absolute() or not inputs.d_mount_validator(path):
            raise MaterializationContractError(
                f"{name} must be an absolute D-drive (/mnt/d) path"
            )
    values = list(roots.items())
    for index, (first_name, first) in enumerate(values):
        for second_name, second in values[index + 1 :]:
            if (
                first == second
                or first.is_relative_to(second)
                or second.is_relative_to(first)
            ):
                raise MaterializationContractError(
                    f"{first_name} and {second_name} must be distinct and non-overlapping"
                )
    return roots


def _validated_source_seed_root(
    inputs: MaterializationInputs,
    *,
    selected: list[dict[str, Any]],
    roots: dict[str, Path],
) -> Path | None:
    raw_seed = inputs.source_seed_root
    if raw_seed is None:
        return None
    if inputs.dry_run or not inputs.allow_download:
        raise MaterializationContractError(
            "--source-seed-root requires an executable --allow-download run"
        )
    if inputs.dataset is None or len(selected) != 1:
        raise MaterializationContractError(
            "--source-seed-root requires exactly one manifest-selected --dataset"
        )
    seed = raw_seed.expanduser().resolve(strict=True)
    if not seed.is_dir() or seed.is_symlink() or not inputs.d_mount_validator(seed):
        raise MaterializationContractError(
            "source seed must be a real directory on the D drive"
        )
    for name, root in roots.items():
        if seed == root or seed.is_relative_to(root) or root.is_relative_to(seed):
            raise MaterializationContractError(
                f"source seed and {name} must be distinct and non-overlapping"
            )
    return seed


def _copy_verified_source_seed(seed_root: Path, source_stage: Path) -> dict[str, Any]:
    before_artifacts, before_revision = _hash_tree(seed_root)
    _require_source_artifacts(before_artifacts)
    for child in sorted(seed_root.iterdir(), key=lambda path: path.name):
        target = source_stage / child.name
        if child.is_symlink():
            raise MaterializationContractError(
                f"source seed contains a symbolic link: {child}"
            )
        if child.is_dir():
            shutil.copytree(child, target, copy_function=shutil.copy2)
        elif child.is_file():
            shutil.copy2(child, target)
        else:
            raise MaterializationContractError(
                f"source seed contains a non-regular entry: {child}"
            )
    copied_artifacts, copied_revision = _hash_tree(source_stage)
    if copied_artifacts != before_artifacts or copied_revision != before_revision:
        raise MaterializationContractError(
            "source seed changed or copied bytes differ from the verified inventory"
        )
    return {
        "schema_version": "1.0.0",
        "kind": "independent-copy",
        "source_root": str(seed_root),
        "revision_sha256": before_revision,
        "artifact_count": len(before_artifacts),
        "total_bytes": sum(int(row["size_bytes"]) for row in before_artifacts),
    }


def _validate_environment(spec: dict[str, Any], environment: dict[str, Any]) -> None:
    digest = str(environment.get("identity_sha256") or "").casefold()
    if not _SHA256.fullmatch(digest):
        raise MaterializationContractError(
            "exact environment identity lacks a valid identity_sha256"
        )
    packages = environment.get("packages")
    locked_packages = environment.get("locked_packages")
    expected = str(spec["moabb_release"]["version"])
    if not isinstance(packages, dict) or packages.get("moabb") != expected:
        raise MaterializationContractError(
            f"exact environment must contain MOABB {expected}"
        )
    if not isinstance(locked_packages, dict):
        raise MaterializationContractError(
            "exact environment lacks the Poetry lock package inventory"
        )
    for distribution in CAMPAIGN_RUNTIME_DISTRIBUTIONS:
        installed = packages.get(distribution) if isinstance(packages, dict) else None
        locked = locked_packages.get(distribution)
        if (
            not isinstance(installed, str)
            or not installed
            or not isinstance(locked, list)
            or installed not in locked
        ):
            raise MaterializationContractError(
                f"installed {distribution} {installed or 'missing'} does not match "
                "the Poetry lock"
            )
    if (
        packages.get("bids-validator-deno") != REQUIRED_BIDS_VALIDATOR_VERSION
        or REQUIRED_BIDS_VALIDATOR_VERSION
        not in locked_packages.get("bids-validator-deno", [])
    ):
        raise MaterializationContractError(
            "exact environment must contain locked bids-validator-deno "
            f"{REQUIRED_BIDS_VALIDATOR_VERSION}"
        )
    torch_cuda = environment.get("torch_cuda")
    nvidia_smi = environment.get("nvidia_smi")
    if (
        not isinstance(torch_cuda, dict)
        or torch_cuda.get("cuda_available") is not True
        or type(torch_cuda.get("device_count")) is not int
        or int(torch_cuda["device_count"]) <= 0
        or torch_cuda.get("selected_device_index") != 0
        or not str(torch_cuda.get("cuda_runtime") or "")
        or not str(torch_cuda.get("selected_device_name") or "")
        or type(torch_cuda.get("selected_device_total_memory_bytes")) is not int
        or int(torch_cuda["selected_device_total_memory_bytes"]) <= 0
        or not isinstance(torch_cuda.get("compute_capability"), list)
        or len(torch_cuda["compute_capability"]) != 2
    ):
        raise MaterializationContractError(
            "exact environment lacks the required CUDA device-0 identity"
        )
    if (
        not isinstance(nvidia_smi, dict)
        or nvidia_smi.get("selected_device_index") != 0
        or not str(nvidia_smi.get("uuid") or "")
        or not str(nvidia_smi.get("driver_version") or "")
        or type(nvidia_smi.get("memory_total_mib")) is not int
        or int(nvidia_smi["memory_total_mib"]) <= 0
    ):
        raise MaterializationContractError(
            "exact environment lacks the nvidia-smi GPU/driver identity"
        )
    torch_memory_bytes = int(torch_cuda["selected_device_total_memory_bytes"])
    nvidia_memory_bytes = int(nvidia_smi["memory_total_mib"]) * 1024 * 1024
    if (
        str(torch_cuda["selected_device_name"]).strip()
        != str(nvidia_smi.get("name") or "").strip()
        or abs(torch_memory_bytes - nvidia_memory_bytes) > 1024 * 1024
    ):
        raise MaterializationContractError(
            "torch CUDA device 0 disagrees with the nvidia-smi GPU identity"
        )
    git = environment.get("git")
    if isinstance(git, dict) and git.get("dirty") is True:
        raise MaterializationContractError(
            "dataset freeze requires a clean exact Git source identity"
        )
    conversion_digest = str(
        environment.get("conversion_identity_sha256") or ""
    ).casefold()
    product_digest = str(
        environment.get("campaign_product_identity_sha256") or ""
    ).casefold()
    if conversion_digest != _conversion_identity_digest(environment):
        raise MaterializationContractError(
            "conversion environment identity digest does not match its captured facts"
        )
    if product_digest != _campaign_product_identity_digest(environment):
        raise MaterializationContractError(
            "campaign product identity digest does not match its captured facts"
        )
    if digest != product_digest:
        raise MaterializationContractError(
            "exact environment identity digest does not match its captured facts"
        )


def _required_headroom(spec: dict[str, Any], rows: list[dict[str, Any]]) -> int:
    policy = spec["resource_policy"]
    multiplier = policy.get("minimum_headroom_multiplier")
    artifact_bytes = policy.get("minimum_artifact_headroom_bytes")
    if type(multiplier) is not int or multiplier < 4:
        raise MaterializationContractError(
            "minimum_headroom_multiplier must be an integer of at least 4"
        )
    if type(artifact_bytes) is not int or artifact_bytes <= 0:
        raise MaterializationContractError(
            "minimum_artifact_headroom_bytes must be positive"
        )
    return sum(int(row["source_download_bytes"]) for row in rows) * multiplier + int(
        artifact_bytes
    )


def _validate_returned_bids_root(
    returned: Path, *, output_stage: Path, gui_row: dict[str, Any]
) -> Path:
    resolved = returned.expanduser().resolve(strict=True)
    stage = output_stage.resolve(strict=True)
    try:
        resolved.relative_to(stage)
    except ValueError as exc:
        raise MaterializationContractError(
            "convert_to_bids returned a root outside atomic staging"
        ) from exc
    raw_bids = gui_row.get("bids")
    bids: dict[str, Any] = raw_bids if isinstance(raw_bids, dict) else {}
    raw_resolution = bids.get("root_resolution")
    root_resolution: dict[str, Any] = (
        raw_resolution if isinstance(raw_resolution, dict) else {}
    )
    prefix = str(root_resolution.get("required_basename_prefix") or "MNE-BIDS-")
    marker = str(root_resolution.get("required_marker") or "dataset_description.json")
    if not resolved.name.startswith(prefix):
        raise MaterializationContractError(
            f"convert_to_bids returned root without required prefix {prefix}"
        )
    if not (resolved / marker).is_file():
        raise MaterializationContractError(
            f"convert_to_bids returned root without required marker {marker}"
        )
    return resolved


def _event_id(dataset: Any) -> dict[str, int]:
    event_id = getattr(dataset, "event_id", None)
    if not isinstance(event_id, Mapping) or not event_id:
        raise MaterializationContractError(
            "MOABB dataset event_id is empty; GUI oracle cannot be pinned"
        )
    result: dict[str, int] = {}
    for raw_label, raw_value in event_id.items():
        label = str(raw_label).strip()
        if (
            not label
            or isinstance(raw_value, bool)
            or not isinstance(raw_value, int)
            or raw_value < 0
            or label in result
            or raw_value in result.values()
        ):
            raise MaterializationContractError(
                "MOABB dataset event_id must contain unique labels and integer values"
            )
        result[label] = raw_value
    names = list(result)
    if not all(names) or len(set(names)) != len(names):
        raise MaterializationContractError(
            "MOABB dataset event_id contains empty or duplicate labels"
        )
    return result


def _bids_event_semantics(root: Path) -> tuple[list[str], dict[str, int], str]:
    """Read exact trial labels and cross-check BIDS values when present."""
    labels: list[str] = []
    seen: set[str] = set()
    values_by_label: dict[str, set[int]] = {}
    value_column_presence: set[bool] = set()
    event_tables = sorted(root.rglob("*_events.tsv"))
    if not event_tables:
        raise MaterializationContractError(
            "frozen BIDS dataset contains no events.tsv tables"
        )
    for table in event_tables:
        if table.is_symlink() or not table.is_file():
            raise MaterializationContractError(
                f"BIDS events table is not a regular file: {table}"
            )
        with table.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if "trial_type" not in (reader.fieldnames or ()):
                raise MaterializationContractError(
                    f"BIDS events table lacks trial_type: {table}"
                )
            has_value = "value" in (reader.fieldnames or ())
            value_column_presence.add(has_value)
            table_values_by_label: dict[str, set[int]] = {}
            for row in reader:
                label = str(row.get("trial_type") or "").strip()
                if label and label.casefold() != "n/a" and label not in seen:
                    labels.append(label)
                    seen.add(label)
                if not label or label.casefold() == "n/a" or not has_value:
                    continue
                raw_value = str(row.get("value") or "").strip()
                try:
                    value = int(raw_value)
                except ValueError as exc:
                    raise MaterializationContractError(
                        f"BIDS event value is not an integer in {table}: {raw_value}"
                    ) from exc
                table_values_by_label.setdefault(label, set()).add(value)
                values_by_label.setdefault(label, set()).add(value)
            if has_value:
                ambiguous_in_table = [
                    label
                    for label, values in table_values_by_label.items()
                    if len(values) != 1
                ]
                table_values = {
                    label: next(iter(values))
                    for label, values in table_values_by_label.items()
                    if len(values) == 1
                }
                if (
                    ambiguous_in_table
                    or len(table_values) != len(table_values_by_label)
                    or len(set(table_values.values())) != len(table_values)
                ):
                    raise MaterializationContractError(
                        "BIDS events value mapping is missing, duplicated, or "
                        f"inconsistent within {table}"
                    )
    if not labels:
        raise MaterializationContractError("frozen BIDS event labels are empty")
    if value_column_presence == {False}:
        return labels, {}, "not-present"
    if value_column_presence != {True}:
        raise MaterializationContractError(
            "BIDS events value column is inconsistently present across recordings"
        )
    ambiguous = [label for label, values in values_by_label.items() if len(values) != 1]
    values = {
        label: next(iter(values_by_label[label]))
        for label in labels
        if len(values_by_label.get(label, ())) == 1
    }
    if set(values_by_label) != set(labels):
        raise MaterializationContractError(
            "BIDS events value mapping is missing from one or more trial labels"
        )
    if (
        ambiguous
        or len(values) != len(labels)
        or len(set(values.values())) != len(values)
    ):
        return labels, {}, "run-local"
    return labels, values, "matched"


def _verified_bids_oracle(
    *,
    dataset: Any,
    bids_root: Path,
    supervised_classes: list[str],
) -> dict[str, Any]:
    """Cross-check MOABB, formal BIDS bytes, and explicit class semantics."""
    event_id = _event_id(dataset)
    moabb_event_names = list(event_id)
    event_names, bids_event_values, value_crosscheck = _bids_event_semantics(bids_root)
    if set(moabb_event_names) != set(event_names):
        raise MaterializationContractError(
            "frozen BIDS event labels differ from the pinned MOABB event map"
        )
    classes = [str(item) for item in supervised_classes]
    if not set(classes).issubset(event_names):
        raise MaterializationContractError(
            "supervised class oracle is absent from frozen BIDS events"
        )
    return {
        "event_names": event_names,
        "event_id": event_id,
        "bids_event_values": bids_event_values,
        "bids_value_crosscheck": value_crosscheck,
        "supervised_classes": classes,
    }


def _verified_formal_bids_mirror_oracle(
    *,
    bids_root: Path,
    supervised_classes: list[str],
    expected_trial_type_values: Mapping[str, Any],
) -> dict[str, Any]:
    """Pin mirror label truth to selected formal BIDS bytes, not raw MOABB IDs."""
    event_names, bids_event_values, value_crosscheck = _bids_event_semantics(bids_root)
    expected_values = {
        str(label): int(value) for label, value in expected_trial_type_values.items()
    }
    classes = [str(item) for item in supervised_classes]
    if set(event_names) != set(classes):
        raise MaterializationContractError(
            "formal BIDS mirror events differ from the supervised class oracle"
        )
    if bids_event_values != expected_values:
        raise MaterializationContractError(
            "formal BIDS mirror trial_type/value mapping differs from its pin"
        )
    return {
        "event_names": event_names,
        "event_id": expected_values,
        "bids_event_values": bids_event_values,
        "bids_value_crosscheck": (
            "formal-bids-mirror-authoritative"
            if value_crosscheck == "matched"
            else value_crosscheck
        ),
        "supervised_classes": classes,
    }


def _hash_tree(root: Path) -> tuple[list[dict[str, Any]], str]:
    canonical_root = root.resolve(strict=True)
    artifacts: list[dict[str, Any]] = []
    for directory, directory_names, file_names in os.walk(
        canonical_root, topdown=True, followlinks=False
    ):
        current = Path(directory)
        admitted_directories: list[str] = []
        for name in sorted(directory_names):
            candidate = current / name
            if candidate.is_symlink():
                raise MaterializationContractError(
                    f"checksum tree contains a symbolic-link directory: {candidate}"
                )
            admitted_directories.append(name)
        directory_names[:] = admitted_directories
        for name in sorted(file_names):
            candidate = current / name
            if candidate.is_symlink():
                raise MaterializationContractError(
                    f"checksum tree contains a symbolic-link file: {candidate}"
                )
            if not candidate.is_file():
                raise MaterializationContractError(
                    f"checksum tree contains a non-regular file: {candidate}"
                )
            try:
                candidate.resolve(strict=True).relative_to(canonical_root)
            except ValueError as exc:
                raise MaterializationContractError(
                    f"checksum file escapes its declared tree: {candidate}"
                ) from exc
            relative = candidate.relative_to(canonical_root).as_posix()
            before = _file_identity(candidate)
            digest = _sha256_file(candidate)
            after = _file_identity(candidate)
            if before != after:
                raise MaterializationContractError(
                    f"checksum file changed while it was read: {relative}"
                )
            artifacts.append(
                {
                    "relative_path": relative,
                    "size_bytes": after[3],
                    "checksum": {
                        "algorithm": "sha256",
                        "value": digest,
                    },
                }
            )
    artifacts.sort(key=lambda item: str(item["relative_path"]))
    return artifacts, _canonical_sha256(artifacts)


def _file_identity(path: Path) -> tuple[int, int, int, int, int, int]:
    status = path.stat(follow_symlinks=False)
    return (
        int(status.st_dev),
        int(status.st_ino),
        int(status.st_mode),
        int(status.st_size),
        int(status.st_mtime_ns),
        int(status.st_ctime_ns),
    )


def _tree_receipt_error(receipt: dict[str, Any]) -> str | None:
    try:
        source_root = Path(receipt["source_root"]).resolve(strict=True)
        conversion_parent = Path(receipt["conversion_parent"]).resolve(strict=True)
        bids_root = Path(receipt["bids_root"]).resolve(strict=True)
        bids_root.relative_to(conversion_parent)
        source_artifacts, source_revision = _hash_tree(source_root)
        bids_artifacts, bids_revision = _hash_tree(bids_root)
    except ValueError:
        return "frozen BIDS root escapes its conversion parent"
    except (KeyError, OSError, MaterializationContractError) as exc:
        return f"frozen checksum tree is unavailable: {exc}"
    if source_artifacts != receipt.get("source_artifacts"):
        return "source checksum inventory changed"
    if bids_artifacts != receipt.get("bids_artifacts"):
        return "BIDS checksum inventory changed"
    if source_revision != receipt.get("source_revision_sha256"):
        return "source aggregate checksum changed"
    if bids_revision != receipt.get("dataset_revision_sha256"):
        return "BIDS aggregate checksum changed"
    if receipt.get("source_mode") == SOURCE_MODE_FORMAL_BIDS_MIRROR:
        mirror_error = _formal_bids_mirror_receipt_error(
            receipt,
            bids_artifacts=bids_artifacts,
        )
        if mirror_error is not None:
            return mirror_error
    checksum_path = Path(str(receipt.get("checksum_manifest") or ""))
    if not checksum_path.is_file():
        return "BIDS checksum manifest is missing"
    expected_text = _sha256_manifest_text(bids_artifacts)
    if checksum_path.read_text(encoding="utf-8") != expected_text:
        return "BIDS checksum manifest changed"
    source_checksum_path = Path(str(receipt.get("source_checksum_manifest") or ""))
    if not source_checksum_path.is_file():
        return "source checksum manifest is missing"
    expected_source_text = _sha256_manifest_text(source_artifacts)
    if source_checksum_path.read_text(encoding="utf-8") != expected_source_text:
        return "source checksum manifest changed"
    validation_path = Path(str(receipt.get("bids_validation_report") or ""))
    if not validation_path.is_file() or validation_path.is_symlink():
        return "authoritative BIDS validation report is missing"
    validation = receipt.get("bids_validation")
    if not isinstance(validation, dict):
        return "authoritative BIDS validation receipt is missing"
    try:
        persisted_validation = _load_object(
            validation_path,
            "authoritative BIDS validation report",
        )
        _require_passed_bids_validation(validation)
    except (MaterializationContractError, OSError, json.JSONDecodeError) as exc:
        return f"authoritative BIDS validation is unavailable: {exc}"
    if persisted_validation != validation:
        return "authoritative BIDS validation report changed"
    return None


def _require_unchanged_receipt_tree_after_validation(
    receipt: dict[str, Any],
) -> None:
    error = _tree_receipt_error(receipt)
    if error is not None:
        raise MaterializationContractError(
            "frozen bytes changed during authoritative BIDS validation: " + error
        )


def _require_matching_tree_snapshots(
    *,
    before_source_artifacts: list[dict[str, Any]],
    before_source_revision: str,
    before_bids_artifacts: list[dict[str, Any]],
    before_bids_revision: str,
    after_source_artifacts: list[dict[str, Any]],
    after_source_revision: str,
    after_bids_artifacts: list[dict[str, Any]],
    after_bids_revision: str,
) -> None:
    if (
        after_source_artifacts != before_source_artifacts
        or after_source_revision != before_source_revision
        or after_bids_artifacts != before_bids_artifacts
        or after_bids_revision != before_bids_revision
    ):
        raise MaterializationContractError(
            "source or BIDS bytes changed during authoritative BIDS validation"
        )


def _formal_bids_mirror_receipt_error(
    receipt: dict[str, Any],
    *,
    bids_artifacts: list[dict[str, Any]],
) -> str | None:
    upstream = receipt.get("upstream_download_artifacts")
    if not isinstance(upstream, list) or not upstream:
        return "formal BIDS mirror upstream inventory is missing"
    if receipt.get("upstream_download_status") != "verified":
        return "formal BIDS mirror upstream status is not verified"
    if receipt.get("upstream_download_revision_sha256") != _canonical_sha256(upstream):
        return "formal BIDS mirror upstream aggregate identity changed"
    upstream_bytes = sum(
        int(item.get("size_bytes") or 0) for item in upstream if isinstance(item, dict)
    )
    if upstream_bytes != receipt.get("upstream_download_bytes"):
        return "formal BIDS mirror upstream byte total changed"
    projected_bids = [
        {
            "relative_path": item.get("relative_path"),
            "size_bytes": item.get("size_bytes"),
            "checksum": item.get("checksum"),
        }
        for item in upstream
        if isinstance(item, dict)
    ]
    if projected_bids != bids_artifacts:
        return "formal BIDS mirror upstream inventory differs from BIDS bytes"
    return None


def bids_tree_integrity_error(
    *,
    root: Path,
    checksum_manifest: Path,
    expected_revision_sha256: str,
) -> str | None:
    """Re-hash a frozen BIDS tree against its exact manifest and aggregate ID."""
    try:
        if root.is_symlink():
            return "BIDS root is a symbolic link"
        if checksum_manifest.is_symlink():
            return "BIDS checksum manifest is a symbolic link"
        artifacts, revision = _hash_tree(root)
        manifest_text = checksum_manifest.read_text(encoding="utf-8")
    except (OSError, MaterializationContractError, UnicodeError) as exc:
        return f"BIDS checksum tree is unavailable: {exc}"
    if revision != expected_revision_sha256:
        return "BIDS aggregate checksum changed"
    if manifest_text != _sha256_manifest_text(artifacts):
        return "BIDS checksum inventory changed"
    return None


def frozen_dataset_integrity_error(
    dataset: dict[str, Any],
    *,
    source_owner: Path,
    bids_owner: Path,
    checksum_owner: Path,
) -> str | None:
    """Verify one final frozen row against its exact on-disk source/BIDS bytes."""
    try:
        source_root = Path(str(dataset["source_root"])).resolve(strict=True)
        bids_root = Path(str(dataset["bids_root"])).resolve(strict=True)
        conversion_parent = Path(str(dataset["conversion_parent"])).resolve(strict=True)
        checksum_manifest = Path(str(dataset["checksum_manifest"])).resolve(strict=True)
        source_checksum_manifest = Path(
            str(dataset["source_checksum_manifest"])
        ).resolve(strict=True)
        validation_report = Path(str(dataset["bids_validation_report"])).resolve(
            strict=True
        )
        source_root.relative_to(source_owner.resolve(strict=True))
        bids_root.relative_to(bids_owner.resolve(strict=True))
        conversion_parent.relative_to(bids_owner.resolve(strict=True))
        bids_root.relative_to(conversion_parent)
        checksum_root = checksum_owner.resolve(strict=True)
        checksum_manifest.relative_to(checksum_root)
        source_checksum_manifest.relative_to(checksum_root)
        validation_report.relative_to(checksum_root)
        marker = bids_root / "dataset_description.json"
        if marker.is_symlink() or not marker.is_file():
            return "formal BIDS dataset_description.json marker is unavailable"
    except ValueError:
        return "frozen source/BIDS/checksum path escapes its declared owner root"
    except (KeyError, OSError) as exc:
        return f"frozen source/BIDS/checksum path is unavailable: {exc}"
    return _tree_receipt_error(dict(dataset))


def _receipt_error(
    receipt: dict[str, Any] | None, expected: dict[str, Any]
) -> str | None:
    if receipt is None:
        return "freeze receipt is missing"
    if receipt.get("status") != "ready":
        return str(receipt.get("reason") or "freeze receipt is not ready")
    for field, value in expected.items():
        if receipt.get(field) != value:
            label = (
                "conversion identity"
                if field == "conversion_identity_sha256"
                else field.replace("_", " ")
            )
            return f"{label} changed"
    return None


def _invalidate_receipt(path: Path, *, expected: dict[str, Any], reason: str) -> None:
    _atomic_write_json(
        path,
        {
            "schema_version": "1.0.0",
            "status": "invalid",
            **expected,
            "reason": reason,
        },
    )


def _quarantine_orphan_stages(
    staging_root: Path, owner_root: Path, class_name: str
) -> None:
    if not staging_root.is_dir():
        return
    for candidate in sorted(staging_root.iterdir()):
        if candidate.name.startswith(f"{class_name}."):
            _quarantine_path(candidate, owner_root, class_name, "orphan-stage")


def _quarantine_existing(
    path: Path, owner_root: Path, class_name: str, label: str
) -> None:
    if path.exists():
        _quarantine_path(path, owner_root, class_name, label)


def _quarantine_path(
    path: Path, owner_root: Path, class_name: str, label: str
) -> Path | None:
    if not path.exists():
        return None
    quarantine = owner_root / ".quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    target = quarantine / f"{class_name}.{label}.{uuid.uuid4().hex}"
    path.replace(target)
    return target


def _write_sha256_manifest(path: Path, artifacts: list[dict[str, Any]]) -> None:
    _atomic_write_text(path, _sha256_manifest_text(artifacts))


def _sha256_manifest_text(artifacts: list[dict[str, Any]]) -> str:
    return "".join(
        f"{item['checksum']['value']}  {item['relative_path']}\n" for item in artifacts
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _dataset_spec_sha256(row: dict[str, Any]) -> str:
    return _canonical_sha256(
        {
            "moabb_class": row["moabb_class"],
            "source_mode": row.get("source_mode", SOURCE_MODE_MOABB_CONVERT),
            "subjects": row["subjects"],
            "output_format": row["output_format"],
            "license_status": row["license_status"],
            "redistribution_allowed": row.get("redistribution_allowed"),
            "license_note": row.get("license_note"),
            "supervised_classes": row["supervised_classes"],
            "resource_preflight": row.get("resource_preflight"),
            "formal_bids_mirror": row.get("formal_bids_mirror"),
        }
    )


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MaterializationContractError(f"{label} must be a JSON object")
    return value


def _read_optional_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "invalid", "reason": "freeze receipt cannot be parsed"}
    return (
        value
        if isinstance(value, dict)
        else {
            "status": "invalid",
            "reason": "freeze receipt is not an object",
        }
    )


@contextmanager
def _temporary_mne_environment(source_stage: Path) -> Iterator[None]:
    """Give one conversion an isolated MNE config and dataset-path namespace."""
    config_home = source_stage / ".mne-config"
    config_home.mkdir(parents=True, exist_ok=True)
    explicit = {
        "MNE_DATA": str(source_stage),
        "MNE_DONTWRITE_HOME": "true",
        "_MNE_FAKE_HOME_DIR": str(config_home),
    }
    wildcard_names = {name for name in os.environ if name.startswith("MNE_DATASETS_")}
    retained_names = set(explicit).union(wildcard_names)
    previous = {name: os.environ.get(name) for name in retained_names}
    for name in wildcard_names:
        os.environ.pop(name, None)
    os.environ.update(explicit)
    try:
        yield
    finally:
        for name in tuple(os.environ):
            if name.startswith("MNE_DATASETS_") or name in explicit:
                os.environ.pop(name, None)
        for name, value in previous.items():
            if value is not None:
                os.environ[name] = value


def _installed_dataset_factory(class_name: str) -> Any:
    os.environ.setdefault("MNE_DONTWRITE_HOME", "true")
    module = importlib.import_module("moabb.datasets")
    dataset_class = getattr(module, class_name, None)
    if not isinstance(dataset_class, type):
        raise MaterializationContractError(
            f"MOABB class {class_name} is absent from the pinned environment"
        )
    return dataset_class()


def _bounded_https_fetch(
    url: str,
    allowed_hosts: frozenset[str],
    maximum_bytes: int,
) -> bytes:
    """Fetch one small pinned manifest with bounded redirect containment."""
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed_hosts
        or parsed.query
        or parsed.fragment
        or maximum_bytes <= 0
    ):
        raise MaterializationContractError(
            "formal BIDS mirror manifest URL is not safely bounded"
        )
    request = urllib.request.Request(  # noqa: S310 - exact HTTPS host checked
        url,
        headers={"User-Agent": "XBrainLab-MOABB-Materializer/1"},
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 - exact HTTPS host checked
            request,
            timeout=30,
        ) as response:
            final = urllib.parse.urlparse(response.geturl())
            if final.scheme != "https" or final.hostname not in allowed_hosts:
                raise MaterializationContractError(
                    "formal BIDS mirror manifest redirected off allowlist"
                )
            payload = response.read(maximum_bytes + 1)
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise MaterializationContractError(
            f"formal BIDS mirror manifest request failed: {exc}"
        ) from exc
    if len(payload) > maximum_bytes:
        raise MaterializationContractError(
            "formal BIDS mirror manifest exceeded its byte bound"
        )
    return payload


def _download_https_file(
    url: str,
    target: Path,
    allowed_hosts: frozenset[str],
    maximum_bytes: int,
) -> dict[str, Any]:
    """Stream one mirror file into fresh staging with an exact byte bound."""
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed_hosts
        or parsed.query
        or parsed.fragment
        or maximum_bytes <= 0
        or target.exists()
    ):
        raise MaterializationContractError(
            "formal BIDS mirror file URL/target is not safely bounded"
        )
    request = urllib.request.Request(  # noqa: S310 - exact HTTPS host checked
        url,
        headers={"User-Agent": "XBrainLab-MOABB-Materializer/1"},
    )
    written = 0
    try:
        with (
            urllib.request.urlopen(  # noqa: S310 - exact HTTPS host checked
                request,
                timeout=120,
            ) as response,
            target.open("xb") as handle,
        ):
            final_url = response.geturl()
            final = urllib.parse.urlparse(final_url)
            if final.scheme != "https" or final.hostname not in allowed_hosts:
                raise MaterializationContractError(
                    "formal BIDS mirror file redirected off allowlist"
                )
            while chunk := response.read(min(1024 * 1024, maximum_bytes + 1)):
                written += len(chunk)
                if written > maximum_bytes:
                    raise MaterializationContractError(
                        "formal BIDS mirror file exceeded its pinned size"
                    )
                handle.write(chunk)
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise MaterializationContractError(
            f"formal BIDS mirror file request failed: {exc}"
        ) from exc
    return {"final_url": final_url, "size_bytes": written}


def _bounded_http_resource_probe(policy: dict[str, Any]) -> dict[str, Any]:
    """Probe every declared resource with a trustworthy bounded size."""
    allowed_hosts = {str(value) for value in policy["allowed_hosts"]}
    observed: list[dict[str, Any]] = []
    for resource in policy["resources"]:
        result = _probe_http_resource(
            resource=dict(resource),
            policy=policy,
            allowed_hosts=allowed_hosts,
        )
        if result.get("status") != "passed":
            return result
        observed.append(result)
    total_bytes = sum(int(item["total_bytes"]) for item in observed)
    maximum_total = int(policy["maximum_total_bytes"])
    if total_bytes <= 0 or total_bytes > maximum_total:
        return {
            "status": "blocked",
            "reason": (
                f"resource aggregate size {total_bytes} exceeds maximum total "
                f"{maximum_total}"
            ),
        }
    return {
        "status": "passed",
        "resources": observed,
        "total_bytes": total_bytes,
    }


def _probe_http_resource(
    *,
    resource: dict[str, Any],
    policy: dict[str, Any],
    allowed_hosts: set[str],
) -> dict[str, Any]:
    url = str(resource["url"])
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname not in allowed_hosts:
        return {
            "status": "blocked",
            "url": url,
            "reason": "resource host is not allowlisted",
        }
    request = urllib.request.Request(  # noqa: S310 - HTTPS + host checked above
        url,
        headers={
            "Range": "bytes=0-511",
            "User-Agent": "XBrainLab-MOABB-Materializer/1",
            "Accept": "application/octet-stream,*/*;q=0.1",
        },
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 - policy validates HTTPS/host
            request, timeout=15
        ) as response:
            status = int(getattr(response, "status", 0))
            final = urllib.parse.urlparse(response.geturl())
            content_type = str(response.headers.get("Content-Type") or "").casefold()
            content_length = str(response.headers.get("Content-Length") or "").strip()
            content_range = str(response.headers.get("Content-Range") or "").strip()
            body = response.read(512).lower()
    except (OSError, urllib.error.URLError, ValueError) as exc:
        return {
            "status": "blocked",
            "url": url,
            "reason": f"resource request failed: {exc}",
        }
    if final.scheme != "https" or final.hostname not in allowed_hosts:
        return {
            "status": "blocked",
            "url": url,
            "reason": "resource redirected off allowlist",
        }
    if status not in set(policy["accepted_statuses"]):
        return {
            "status": "blocked",
            "url": url,
            "reason": f"unexpected HTTP status {status}",
        }
    denied_types = tuple(
        str(value).casefold() for value in policy.get("denied_content_types", [])
    )
    if denied_types and content_type.startswith(denied_types):
        return {
            "status": "blocked",
            "url": url,
            "reason": f"denied content type {content_type}",
        }
    for marker in policy.get("denied_body_markers", []):
        if str(marker).casefold().encode("utf-8") in body:
            return {
                "status": "blocked",
                "url": url,
                "reason": "WAF marker found in response",
            }
    try:
        total_bytes, size_source = _trusted_http_resource_size(
            status=status,
            content_length=content_length,
            content_range=content_range,
        )
    except MaterializationContractError as exc:
        return {"status": "blocked", "url": url, "reason": str(exc)}
    except ValueError:
        return {
            "status": "blocked",
            "url": url,
            "reason": "response lacks a trustworthy positive Content-Length",
        }
    maximum_bytes = int(resource["maximum_bytes"])
    if total_bytes > maximum_bytes:
        return {
            "status": "blocked",
            "url": url,
            "reason": (f"resource size {total_bytes} exceeds maximum {maximum_bytes}"),
        }
    return {
        "status": "passed",
        "url": url,
        "http_status": status,
        "content_type": content_type,
        "size_source": size_source,
        "total_bytes": total_bytes,
        "final_url": response.geturl(),
        "final_host": final.hostname,
    }


def _trusted_http_resource_size(
    *,
    status: int,
    content_length: str,
    content_range: str,
) -> tuple[int, str]:
    if status == 206:
        match = _CONTENT_RANGE.fullmatch(content_range)
        if match is None:
            raise MaterializationContractError(
                "206 response lacks a trustworthy Content-Range total"
            )
        last_byte, total_bytes = (int(value) for value in match.groups())
        if last_byte < 0 or total_bytes <= last_byte:
            raise MaterializationContractError(
                "206 response has a malformed Content-Range total"
            )
        return total_bytes, "content-range"
    if status == 200:
        total_bytes = int(content_length)
        if total_bytes <= 0:
            raise ValueError
        return total_bytes, "content-length"
    raise MaterializationContractError(
        f"HTTP status {status} has no supported size contract"
    )


def _verified_resource_probe_receipt(
    policy: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    resources = result.get("resources")
    if not isinstance(resources, list):
        raise MaterializationContractError("resource probe receipt has no resources")
    expected_resources = list(policy["resources"])
    expected_urls = [str(item["url"]) for item in expected_resources]
    observed_urls = [
        str(item.get("url") or "") if isinstance(item, dict) else ""
        for item in resources
    ]
    if observed_urls != expected_urls:
        raise MaterializationContractError(
            "resource probe receipt does not cover every exact manifest URL"
        )
    total = 0
    normalized: list[dict[str, Any]] = []
    for index, (resource, expected) in enumerate(
        zip(resources, expected_resources, strict=True)
    ):
        if not isinstance(resource, dict):
            raise MaterializationContractError(
                f"resource probe receipt row {index} is invalid"
            )
        size = resource.get("total_bytes")
        if type(size) is not int or size <= 0 or size > int(expected["maximum_bytes"]):
            raise MaterializationContractError(
                f"resource probe receipt row {index} has an unsafe size"
            )
        total += size
        normalized.append(dict(resource))
    if result.get("total_bytes") != total or total > int(policy["maximum_total_bytes"]):
        raise MaterializationContractError(
            "resource probe aggregate does not match the bounded resource sizes"
        )
    return {
        "status": "verified",
        "policy_sha256": _canonical_sha256(policy),
        "resources": normalized,
        "total_bytes": total,
        "maximum_total_bytes": int(policy["maximum_total_bytes"]),
    }


def _run_bids_validator(root: Path) -> dict[str, Any]:
    """Run the exact locked official validator and retain its full JSON truth."""
    executable = shutil.which("bids-validator-deno")
    argv = [
        executable or "bids-validator-deno",
        str(root),
        "--format",
        "json",
        "--max-rows",
        "-1",
    ]
    try:
        version = importlib.metadata.version("bids-validator-deno")
    except importlib.metadata.PackageNotFoundError:
        version = None
    if executable is None or version != REQUIRED_BIDS_VALIDATOR_VERSION:
        return {
            "status": "blocked",
            "validator": "bids-validator-deno",
            "required_version": REQUIRED_BIDS_VALIDATOR_VERSION,
            "version": version,
            "argv": argv,
            "exit_code": None,
            "error_count": None,
            "warning_count": None,
            "report": None,
            "reason": (
                "authoritative bids-validator-deno "
                f"{REQUIRED_BIDS_VALIDATOR_VERSION} is unavailable"
            ),
        }
    try:
        completed = subprocess.run(  # noqa: S603
            tuple(argv),
            check=False,
            capture_output=True,
            text=True,
            timeout=1200,
        )
        report = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return {
            "status": "blocked",
            "validator": "bids-validator-deno",
            "required_version": REQUIRED_BIDS_VALIDATOR_VERSION,
            "version": version,
            "argv": argv,
            "exit_code": None,
            "error_count": None,
            "warning_count": None,
            "report": None,
            "reason": f"authoritative BIDS validator failed: {exc}",
        }
    issue_container = report.get("issues") if isinstance(report, dict) else None
    issues = (
        issue_container.get("issues") if isinstance(issue_container, dict) else None
    )
    if not isinstance(issues, list) or any(
        not isinstance(issue, dict) for issue in issues
    ):
        return {
            "status": "blocked",
            "validator": "bids-validator-deno",
            "required_version": REQUIRED_BIDS_VALIDATOR_VERSION,
            "version": version,
            "argv": argv,
            "exit_code": completed.returncode,
            "error_count": None,
            "warning_count": None,
            "report": report,
            "reason": "authoritative BIDS validator JSON has no issues.issues list",
        }
    errors = [
        issue
        for issue in issues
        if str(issue.get("severity") or "").casefold() == "error"
    ]
    warnings = [
        issue
        for issue in issues
        if str(issue.get("severity") or "").casefold() == "warning"
    ]
    return {
        "status": "passed" if completed.returncode == 0 and not errors else "blocked",
        "validator": "bids-validator-deno",
        "required_version": REQUIRED_BIDS_VALIDATOR_VERSION,
        "version": version,
        "argv": argv,
        "exit_code": completed.returncode,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "warning_codes": sorted(
            {
                str(issue.get("code") or "")
                for issue in warnings
                if str(issue.get("code") or "")
            }
        ),
        "report": report,
        **(
            {}
            if completed.returncode == 0 and not errors
            else {"reason": "validator reported BIDS errors"}
        ),
    }


def _normalize_bids_validation(
    value: dict[str, Any],
    *,
    bids_root: Path,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MaterializationContractError(
            "authoritative BIDS validator returned no structured receipt"
        )
    argv = value.get("argv")
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(item, str) or not item for item in argv)
        or str(bids_root) not in argv
        or "--format" not in argv
        or "json" not in argv
        or "--max-rows" not in argv
        or "-1" not in argv
    ):
        raise MaterializationContractError(
            "authoritative BIDS validator argv is not bound to the exact root/json mode"
        )
    report = value.get("report")
    normalized = {
        "status": str(value.get("status") or "blocked"),
        "validator": str(value.get("validator") or ""),
        "required_version": REQUIRED_BIDS_VALIDATOR_VERSION,
        "version": value.get("version"),
        "argv": list(argv),
        "exit_code": value.get("exit_code"),
        "error_count": value.get("error_count"),
        "warning_count": value.get("warning_count"),
        "warning_codes": list(value.get("warning_codes") or []),
        "report": report,
        "report_sha256": _canonical_sha256(report),
    }
    reason = str(value.get("reason") or "").strip()
    if reason:
        normalized["reason"] = reason
    return normalized


def _require_passed_bids_validation(validation: dict[str, Any]) -> None:
    if (
        validation.get("status") != "passed"
        or validation.get("validator") != "bids-validator-deno"
        or validation.get("version") != REQUIRED_BIDS_VALIDATOR_VERSION
        or validation.get("exit_code") != 0
        or validation.get("error_count") != 0
        or not isinstance(validation.get("warning_count"), int)
        or validation.get("report_sha256")
        != _canonical_sha256(validation.get("report"))
    ):
        reason = str(validation.get("reason") or "validator did not pass")
        raise MaterializationContractError(
            "authoritative BIDS validator gate is blocked: " + reason
        )


def exact_environment_identity() -> dict[str, Any]:
    """Capture deterministic source, Poetry, package, Python, CUDA and GPU facts."""
    packages: dict[str, str | None] = {}
    for name in CAMPAIGN_RUNTIME_DISTRIBUTIONS:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    git_commit = _git_value("rev-parse", "HEAD")
    git_tree = _git_value("rev-parse", "HEAD^{tree}")
    dirty_text = _git_value("status", "--porcelain=v1", "--untracked-files=all")
    protected_changes, unprotected_changes = _git_status_policy(dirty_text)
    locked_packages = _locked_package_versions(REPO_ROOT / "poetry.lock")
    try:
        torch = importlib.import_module("torch")
        cuda_available = bool(torch.cuda.is_available())
        device_count = int(torch.cuda.device_count())
        if not cuda_available or device_count <= 0:
            raise MaterializationContractError(
                "CUDA device 0 is unavailable for the fixed GPU campaign"
            )
        properties = torch.cuda.get_device_properties(0)
        capability = torch.cuda.get_device_capability(0)
        torch_cuda = {
            "torch_version": str(torch.__version__),
            "cuda_runtime": str(
                getattr(getattr(torch, "version", None), "cuda", None) or ""
            ),
            "cuda_available": cuda_available,
            "device_count": device_count,
            "selected_device_index": 0,
            "selected_device_name": str(torch.cuda.get_device_name(0)),
            "selected_device_total_memory_bytes": int(properties.total_memory),
            "compute_capability": [int(capability[0]), int(capability[1])],
        }
    except (ImportError, RuntimeError, AttributeError) as exc:
        raise MaterializationContractError(
            f"CUDA environment identity cannot be captured: {exc}"
        ) from exc
    nvidia_smi = _nvidia_smi_identity()
    converter_path = Path(
        str(
            importlib.metadata.distribution("moabb").locate_file(
                "moabb/datasets/base.py"
            )
        )
    )
    if not converter_path.is_file():
        raise MaterializationContractError(
            "MOABB BaseDataset converter source cannot be identified"
        )
    unprotected_status = "\n".join(unprotected_changes)
    identity: dict[str, Any] = {
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": str(Path(sys.executable).resolve()),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "git": {
            "commit": git_commit,
            "tree": git_tree,
            "dirty": bool(unprotected_changes),
            "protected_local_changes": protected_changes,
            "status_sha256": hashlib.sha256(
                unprotected_status.encode("utf-8")
            ).hexdigest(),
        },
        "poetry_lock_sha256": _sha256_file(REPO_ROOT / "poetry.lock"),
        "packages": packages,
        "locked_packages": locked_packages,
        "converter_code": {
            "distribution": "moabb",
            "relative_path": "moabb/datasets/base.py",
            "sha256": _sha256_file(converter_path),
        },
        "torch_cuda": torch_cuda,
        "nvidia_smi": nvidia_smi,
        # Compatibility projections for existing GUI preflight consumers. The
        # sealed identity is the structured torch_cuda/nvidia_smi payload above.
        "cuda": torch_cuda["cuda_runtime"],
        "gpu": nvidia_smi["name"],
    }
    identity["conversion_identity_sha256"] = _conversion_identity_digest(identity)
    product_digest = _campaign_product_identity_digest(identity)
    identity["campaign_product_identity_sha256"] = product_digest
    identity["identity_sha256"] = product_digest
    return identity


def _locked_package_versions(path: Path) -> dict[str, list[str]]:
    try:
        with path.open("rb") as handle:
            payload = load(handle)
    except (OSError, TOMLDecodeError) as exc:
        raise MaterializationContractError(
            f"Poetry lock package inventory cannot be read: {exc}"
        ) from exc
    rows = payload.get("package")
    if not isinstance(rows, list):
        raise MaterializationContractError("Poetry lock package inventory is missing")
    versions: dict[str, list[str]] = {
        name: [] for name in CAMPAIGN_RUNTIME_DISTRIBUTIONS
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").casefold()
        version = str(row.get("version") or "")
        if name in versions and version and version not in versions[name]:
            versions[name].append(version)
    return versions


def _nvidia_smi_identity() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        raise MaterializationContractError("nvidia-smi is unavailable")
    try:
        completed = subprocess.run(  # noqa: S603
            (
                executable,
                "--query-gpu=uuid,name,driver_version,memory.total",
                "--format=csv,noheader,nounits",
                "--id=0",
            ),
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MaterializationContractError(f"nvidia-smi failed: {exc}") from exc
    rows = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if completed.returncode != 0 or len(rows) != 1:
        raise MaterializationContractError(
            "nvidia-smi did not return one exact device-0 identity"
        )
    return _parse_nvidia_smi_row(rows[0])


def _parse_nvidia_smi_row(value: str) -> dict[str, Any]:
    fields = [field.strip() for field in value.split(",")]
    if len(fields) != 4 or not all(fields):
        raise MaterializationContractError("nvidia-smi returned a malformed GPU row")
    try:
        memory_mib = int(fields[3])
    except ValueError as exc:
        raise MaterializationContractError(
            "nvidia-smi returned malformed total VRAM"
        ) from exc
    if memory_mib <= 0:
        raise MaterializationContractError(
            "nvidia-smi returned non-positive total VRAM"
        )
    return {
        "selected_device_index": 0,
        "uuid": fields[0],
        "name": fields[1],
        "driver_version": fields[2],
        "memory_total_mib": memory_mib,
    }


def _environment_identity_digest(identity: dict[str, Any]) -> str:
    """Seal executable source facts without hashing protected local settings."""
    return _campaign_product_identity_digest(identity)


def _conversion_identity_digest(identity: dict[str, Any]) -> str:
    """Seal only facts that can change converted source/BIDS bytes."""
    packages = identity.get("packages")
    locked_packages = identity.get("locked_packages")
    payload = {
        "python": identity.get("python"),
        "platform": identity.get("platform"),
        "packages": {
            name: packages.get(name) if isinstance(packages, dict) else None
            for name in CRITICAL_RUNTIME_DISTRIBUTIONS
        },
        "locked_packages": {
            name: locked_packages.get(name)
            if isinstance(locked_packages, dict)
            else None
            for name in CRITICAL_RUNTIME_DISTRIBUTIONS
        },
        "converter_code": identity.get("converter_code"),
    }
    return _canonical_sha256(payload)


def _campaign_product_identity_digest(identity: dict[str, Any]) -> str:
    """Seal exact product/lock/GPU facts without forcing reconversion."""
    sealed = json.loads(json.dumps(identity))
    sealed.pop("identity_sha256", None)
    sealed.pop("campaign_product_identity_sha256", None)
    git = sealed.get("git")
    if isinstance(git, dict):
        git.pop("protected_local_changes", None)
    return _canonical_sha256(sealed)


def _git_status_policy(status: str) -> tuple[list[str], list[str]]:
    protected: list[str] = []
    unprotected: list[str] = []
    for line in status.splitlines():
        if line[:3] == " M " and line[3:] == "settings.json":
            protected.append("settings.json")
        elif line:
            unprotected.append(line)
    return protected, unprotected


def _git_value(*arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603
        ("git", *arguments),
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        raise MaterializationContractError(
            f"Git environment identity failed: {' '.join(arguments)}"
        )
    return completed.stdout.rstrip()


def _is_d_drive_mount(path: Path) -> bool:
    parts = PurePosixPath(path).parts
    return len(parts) >= 3 and parts[:3] == ("/", "mnt", "d")


def _nearest_existing_parent(path: Path) -> Path:
    candidate = path.resolve()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _blocked_result(message: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "status": "blocked",
        "network_used": False,
        "datasets": [],
        "blockers": [message],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze manifest-selected MOABB datasets into checksum-pinned BIDS; "
            "downloads are disabled unless explicitly allowed."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--gui-plan", type=Path, default=DEFAULT_GUI_PLAN_PATH)
    parser.add_argument("--mne-data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--checksum-root", type=Path, required=True)
    parser.add_argument("--dataset")
    parser.add_argument(
        "--source-seed-root",
        type=Path,
        help=(
            "Independently copy a pre-fetched, checksum-verified MOABB cache tree "
            "into the atomic source stage for one selected dataset."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reuse only exact current receipts and checksums (default: true).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.dry_run and args.allow_download:
        print(
            json.dumps(
                _blocked_result(
                    "--dry-run and --allow-download are mutually exclusive"
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    inputs = MaterializationInputs.from_environment(
        manifest_path=args.manifest.resolve(),
        gui_plan_path=args.gui_plan.resolve(),
        mne_data_root=args.mne_data_root.resolve(),
        output_root=args.output_root.resolve(),
        checksum_root=args.checksum_root.resolve(),
        source_seed_root=(
            args.source_seed_root.resolve() if args.source_seed_root else None
        ),
        dataset=args.dataset,
        dry_run=args.dry_run,
        allow_download=args.allow_download,
        resume=args.resume,
    )
    result = run_materialization(inputs)
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] in {"ready", "dry-run-ready"} else 1


if __name__ == "__main__":
    sys.exit(main())
