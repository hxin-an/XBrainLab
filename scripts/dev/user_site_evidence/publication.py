"""Validate exact MOABB capture evidence before publishing immutable site assets."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    SOURCE_IDENTITY_REQUIRED_FIELDS,
    source_identity_digest,
)
from scripts.dev.moabb_ui_evidence.contract import validate_capture_manifest

CAPTURE_MANIFEST_NAME = "qt-capture-manifest.json"
PUBLICATION_SCHEMA_VERSION = "1.0.0"
PUBLICATION_STATUS = "bounded"
MAX_PUBLISHED_FILE_BYTES = 64 * 1024 * 1024
MAX_PUBLISHED_TOTAL_BYTES = 256 * 1024 * 1024
MAX_LIMITATIONS = 20
MAX_LIMITATION_LENGTH = 500
MAX_METRIC_ROWS = 20
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
HEX_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
OBSERVED_METRICS = (
    "accuracy",
    "balanced_accuracy",
    "macro_f1",
    "roc_auc_ovr",
)
REQUIRED_TRACE = (
    "scan",
    "preview",
    "validate",
    "apply",
    "save_recipe",
    "preprocess:*",
    "epoch",
    "split",
    "configure_training",
    "configure_saliency",
    "train",
    "training_history",
    "evaluate",
    "saliency_query",
)


class EvidencePublicationError(ValueError):
    """The supplied evidence cannot be promoted to the user-facing site."""


@dataclass(frozen=True)
class _CopySource:
    path: Path
    sha256: str
    size_bytes: int
    kind: str


@dataclass(frozen=True)
class _WritePlan:
    target: Path
    reference: str
    sha256: str
    size_bytes: int
    kind: str
    source: Path | None = None
    content: bytes | None = None


def publish_capture_manifest(
    *,
    capture_manifest_path: Path,
    registry_path: Path,
    docs_dir: Path,
    case_map: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    """Validate one exact Qt capture and publish only bounded immutable assets."""
    capture_path = capture_manifest_path.expanduser().resolve()
    registry_path = registry_path.expanduser().resolve()
    docs_root = docs_dir.expanduser().resolve()
    capture = _read_json(capture_path, "capture manifest")
    registry = _read_json(registry_path, "MOABB journey registry")
    manifest_sha = _sha256(capture_path)
    verified = _validate_capture(
        capture,
        capture_path=capture_path,
        manifest_sha=manifest_sha,
        registry=registry,
        registry_path=registry_path,
        case_map=case_map,
    )
    write_plans, published_datasets = _publication_plans(
        verified,
        capture=capture,
        manifest_sha=manifest_sha,
        docs_root=docs_root,
        case_map=case_map,
    )
    _preflight_targets(write_plans, docs_root=docs_root)
    created_assets = _write_assets(write_plans)
    return {
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        "publication_status": PUBLICATION_STATUS,
        "run_id": capture["run_id"],
        "manifest_sha256": manifest_sha,
        "application_source_digest": capture["application_source"]["source_digest"],
        "registry_sha256": _sha256(registry_path),
        "datasets": published_datasets,
        "_created_asset_paths": [str(path) for path in created_assets],
    }


def _validate_capture(
    capture: dict[str, Any],
    *,
    capture_path: Path,
    manifest_sha: str,
    registry: dict[str, Any],
    registry_path: Path,
    case_map: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    if capture_path.name != CAPTURE_MANIFEST_NAME:
        raise EvidencePublicationError(
            f"capture manifest must be named {CAPTURE_MANIFEST_NAME}"
        )
    run_id = str(capture.get("run_id") or "")
    if not RUN_ID.fullmatch(run_id) or "latest" in run_id.casefold():
        raise EvidencePublicationError("capture run identity is not immutable")
    if capture_path.parent.name != run_id:
        raise EvidencePublicationError(
            "capture run identity does not match its directory"
        )
    _validate_source_identity(_mapping(capture.get("application_source")))
    try:
        valid, reason = validate_capture_manifest(
            capture,
            output_dir=capture_path.parent,
        )
    except (OSError, ValueError) as exc:
        raise EvidencePublicationError(f"capture manifest is invalid: {exc}") from exc
    if not valid:
        raise EvidencePublicationError(f"capture manifest is invalid: {reason}")
    qualification = _mapping(capture.get("site_qualification"))
    if (
        capture.get("status") != "completed"
        or qualification.get("eligible") is not True
        or qualification.get("publication_status_ceiling") != PUBLICATION_STATUS
        or qualification.get("reason_codes") != []
        or capture.get("failures") != []
    ):
        raise EvidencePublicationError(
            "capture is not eligible for bounded publication"
        )
    _validate_timestamps(capture)
    if not HEX_SHA256.fullmatch(manifest_sha):
        raise EvidencePublicationError("capture manifest digest is invalid")

    registry_sha = _sha256(registry_path)
    recorded_registry = _mapping(capture.get("registry"))
    if recorded_registry.get("sha256") != registry_sha:
        raise EvidencePublicationError("capture registry digest is stale")
    if recorded_registry.get("profile_id") != registry.get("profile_id"):
        raise EvidencePublicationError("capture registry profile does not match")
    release = _mapping(registry.get("moabb_release"))
    if not HEX_GIT_SHA.fullmatch(str(release.get("commit") or "")):
        raise EvidencePublicationError("registry MOABB source revision is incomplete")

    registry_rows = registry.get("datasets")
    if not isinstance(registry_rows, list):
        raise EvidencePublicationError("registry dataset inventory is invalid")
    registry_by_id = {
        str(item.get("id")): item
        for item in registry_rows
        if isinstance(item, Mapping) and item.get("id")
    }
    expected_ids = list(case_map)
    if list(registry_by_id) != expected_ids:
        raise EvidencePublicationError("registry dataset inventory is not exact")
    capture_rows = capture.get("datasets")
    if not isinstance(capture_rows, list):
        raise EvidencePublicationError("capture dataset inventory is invalid")
    capture_by_id = {
        str(item.get("dataset_id")): item
        for item in capture_rows
        if isinstance(item, Mapping) and item.get("dataset_id")
    }
    if list(capture_by_id) != expected_ids:
        raise EvidencePublicationError("capture dataset inventory is not exact")

    verified: dict[str, Any] = {}
    for dataset_id in expected_ids:
        verified[dataset_id] = _validate_dataset(
            capture_by_id[dataset_id],
            registry_by_id[dataset_id],
            capture_root=capture_path.parent,
            manifest_sha=manifest_sha,
            capture=capture,
        )
    return verified


def _validate_dataset(
    capture_dataset: Mapping[str, Any],
    registry_dataset: Mapping[str, Any],
    *,
    capture_root: Path,
    manifest_sha: str,
    capture: Mapping[str, Any],
) -> dict[str, Any]:
    dataset_id = str(capture_dataset.get("dataset_id") or "")
    revision = _json_digest(registry_dataset)
    if capture_dataset.get("dataset_revision") != revision:
        raise EvidencePublicationError(f"{dataset_id}: dataset revision is stale")
    exact_source = _mapping(capture_dataset.get("exact_source"))
    source_files = _validate_source_files(
        exact_source.get("files"),
        registry_dataset.get("files"),
        dataset_id=dataset_id,
    )
    execution = _mapping(capture_dataset.get("execution"))
    if execution.get("profile") != "showcase":
        raise EvidencePublicationError(
            f"{dataset_id}: smoke evidence cannot publish observed metrics"
        )
    if (
        execution.get("status") != "completed"
        or execution.get("quality_evidence_status") != "complete"
    ):
        raise EvidencePublicationError(
            f"{dataset_id}: execution evidence is incomplete"
        )
    evidence_path = _relative_file(
        capture_root,
        execution.get("evidence_path"),
        label=f"{dataset_id} execution evidence",
    )
    if _sha256(evidence_path) != execution.get("evidence_sha256"):
        raise EvidencePublicationError(f"{dataset_id}: execution evidence hash changed")
    evidence = _read_json(evidence_path, f"{dataset_id} execution evidence")
    if _mapping(evidence.get("dataset")).get("id") != dataset_id:
        raise EvidencePublicationError(f"{dataset_id}: execution run identity is wrong")
    if evidence.get("failures") != []:
        raise EvidencePublicationError(f"{dataset_id}: execution contains failures")
    if evidence.get("quality_evidence_status") != "complete":
        raise EvidencePublicationError(f"{dataset_id}: quality evidence is incomplete")
    _validate_source_files(
        evidence.get("source_artifacts"),
        registry_dataset.get("files"),
        dataset_id=dataset_id,
    )
    _validate_workflow_state(evidence, dataset_id=dataset_id)
    _validate_trace(evidence.get("command_trace"), dataset_id=dataset_id)
    metrics = _observed_metrics(evidence, dataset_id=dataset_id)
    curves = _validate_training_curves(
        evidence.get("training_curves"), capture_root, dataset_id=dataset_id
    )
    _validate_artifact(
        _mapping(evidence.get("import")).get("recipe_artifact"),
        capture_root,
        dataset_id=dataset_id,
        label="import recipe",
    )
    _validate_saliency(evidence, capture_root=capture_root, dataset_id=dataset_id)
    screenshots = _validate_screenshots(
        capture_dataset,
        evidence,
        capture_root=capture_root,
        dataset_id=dataset_id,
    )
    limitations = _limitations(
        capture.get("claim_boundary"),
        capture_dataset.get("limitations"),
        evidence.get("claim_boundary"),
        dataset_id=dataset_id,
    )
    return {
        "dataset_id": dataset_id,
        "dataset_revision": revision,
        "execution_sha256": str(execution["evidence_sha256"]),
        "source_files": source_files,
        "metrics": metrics,
        "limitations": limitations,
        "curves": curves,
        "screenshots": screenshots,
        "manifest_sha256": manifest_sha,
        "saliency_methods": list(_mapping(evidence.get("saliency")).get("methods", [])),
    }


def _validate_source_identity(identity: Mapping[str, Any]) -> None:
    missing = [
        field for field in SOURCE_IDENTITY_REQUIRED_FIELDS if field not in identity
    ]
    if missing:
        raise EvidencePublicationError(
            f"application source identity is missing fields: {', '.join(missing)}"
        )
    if identity.get("error"):
        raise EvidencePublicationError("application source identity reports an error")
    if (
        identity.get("dirty") is not False
        or identity.get("untracked_source_count") != 0
    ):
        raise EvidencePublicationError("application source is dirty")
    if (
        identity.get("version") != 3
        or not Path(str(identity.get("repo_root") or "")).is_absolute()
        or not str(identity.get("branch") or "")
        or not HEX_GIT_SHA.fullmatch(str(identity.get("commit_sha") or ""))
        or not HEX_GIT_SHA.fullmatch(str(identity.get("head_tree_sha") or ""))
        or not HEX_SHA256.fullmatch(str(identity.get("dirty_digest") or ""))
        or not HEX_SHA256.fullmatch(str(identity.get("source_content_digest") or ""))
        or not isinstance(identity.get("excluded_generated_prefixes"), list)
        or not isinstance(identity.get("excluded_local_paths"), list)
        or not str(identity.get("included_file_policy") or "")
    ):
        raise EvidencePublicationError("application source revision is incomplete")
    try:
        expected_digest = source_identity_digest(identity)
    except (TypeError, ValueError) as exc:
        raise EvidencePublicationError(
            "application source identity cannot be hashed"
        ) from exc
    if expected_digest != identity.get("source_digest"):
        raise EvidencePublicationError("application source digest is inconsistent")
    capture_digest = str(identity.get("source_digest") or "")
    if not HEX_SHA256.fullmatch(capture_digest):
        raise EvidencePublicationError("application source digest is invalid")


def _validate_source_files(
    observed: object,
    declared: object,
    *,
    dataset_id: str,
) -> list[dict[str, Any]]:
    if not isinstance(observed, list) or not observed:
        raise EvidencePublicationError(f"{dataset_id}: exact source files are missing")
    if not isinstance(declared, list) or len(observed) != len(declared):
        raise EvidencePublicationError(f"{dataset_id}: exact source inventory differs")
    observed_by_url = {
        str(_mapping(item).get("url") or ""): _mapping(item) for item in observed
    }
    result: list[dict[str, Any]] = []
    for expected_value in declared:
        expected = _mapping(expected_value)
        url = str(expected.get("url") or "")
        source = observed_by_url.get(url)
        if source is None or not url.startswith("https://"):
            raise EvidencePublicationError(f"{dataset_id}: source URL does not match")
        checksum = _mapping(expected.get("checksum"))
        if source.get("expected_checksum") != checksum:
            raise EvidencePublicationError(
                f"{dataset_id}: source checksum does not match"
            )
        path = Path(str(source.get("path") or "")).expanduser()
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise EvidencePublicationError(
                f"{dataset_id}: exact source file is missing"
            )
        size = source.get("size_bytes")
        if (
            isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
            or size != expected.get("size_bytes")
            or path.stat().st_size != size
        ):
            raise EvidencePublicationError(f"{dataset_id}: source size does not match")
        sha256 = _hash_file(path, "sha256")
        if source.get("sha256") != sha256:
            raise EvidencePublicationError(
                f"{dataset_id}: source SHA-256 does not match"
            )
        algorithm = str(checksum.get("algorithm") or "").casefold()
        expected_digest = str(checksum.get("value") or "").casefold()
        try:
            actual_digest = _hash_file(path, algorithm)
        except ValueError as exc:
            raise EvidencePublicationError(
                f"{dataset_id}: source checksum algorithm is unsupported"
            ) from exc
        if actual_digest != expected_digest:
            raise EvidencePublicationError(f"{dataset_id}: source checksum changed")
        result.append(
            {
                "url": url,
                "relative_path": str(expected.get("relative_path") or ""),
                "size_bytes": size,
                "expected_checksum": dict(checksum),
                "sha256": sha256,
            }
        )
    return result


def _validate_workflow_state(evidence: Mapping[str, Any], *, dataset_id: str) -> None:
    import_state = _mapping(evidence.get("import"))
    if import_state.get("applied") is not True or not str(
        import_state.get("validation_decision") or ""
    ):
        raise EvidencePublicationError(f"{dataset_id}: import was not applied")
    if not evidence.get("preprocessing"):
        raise EvidencePublicationError(f"{dataset_id}: preprocess evidence is missing")
    if not _mapping(_mapping(evidence.get("epoch")).get("state")):
        raise EvidencePublicationError(f"{dataset_id}: epoch evidence is missing")
    if not _mapping(_mapping(evidence.get("split")).get("state")):
        raise EvidencePublicationError(f"{dataset_id}: split evidence is missing")
    model = _mapping(evidence.get("model"))
    if not str(model.get("actual_device") or ""):
        raise EvidencePublicationError(f"{dataset_id}: training device is missing")
    seed = evidence.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise EvidencePublicationError(f"{dataset_id}: run seed is invalid")


def _validate_trace(value: object, *, dataset_id: str) -> None:
    if not isinstance(value, list) or not value:
        raise EvidencePublicationError(f"{dataset_id}: command trace is missing")
    successful: list[str] = []
    for index, raw in enumerate(value):
        item = _mapping(raw)
        stage = str(item.get("stage") or "")
        if item.get("status") == "success":
            successful.append(stage.removesuffix(":resource_confirmed"))
            continue
        next_item = _mapping(value[index + 1]) if index + 1 < len(value) else {}
        confirmation_completed = (
            item.get("error_type") == "confirmation_required"
            and next_item.get("stage") == f"{stage}:resource_confirmed"
            and next_item.get("status") == "success"
        )
        if not confirmation_completed:
            raise EvidencePublicationError(
                f"{dataset_id}: unsuccessful command trace stage {stage or 'unknown'}"
            )
    cursor = 0
    for required in REQUIRED_TRACE:
        found = False
        while cursor < len(successful):
            stage = successful[cursor]
            cursor += 1
            if (required == "preprocess:*" and stage.startswith("preprocess:")) or (
                stage == required
            ):
                found = True
                break
        if not found:
            raise EvidencePublicationError(
                f"{dataset_id}: successful {required} stage is missing"
            )


def _observed_metrics(
    evidence: Mapping[str, Any], *, dataset_id: str
) -> list[dict[str, Any]]:
    acceptance = _mapping(evidence.get("quality_acceptance"))
    evaluations = acceptance.get("evaluations")
    if (
        acceptance.get("passed") is not True
        or acceptance.get("status") != "accepted"
        or not isinstance(evaluations, list)
        or not evaluations
        or len(evaluations) > MAX_METRIC_ROWS
    ):
        raise EvidencePublicationError(f"{dataset_id}: accepted metrics are missing")
    rows: list[dict[str, Any]] = []
    for raw in evaluations:
        evaluation = _mapping(raw)
        if (
            evaluation.get("valid") is not True
            or evaluation.get("passed") is not True
            or evaluation.get("split") != "test"
            or evaluation.get("test_prediction_read_count") != 1
        ):
            raise EvidencePublicationError(
                f"{dataset_id}: held-out metric evidence is not accepted"
            )
        rules = evaluation.get("acceptance_rules")
        if (
            not isinstance(rules, list)
            or not rules
            or not all(_mapping(rule).get("passed") is True for rule in rules)
        ):
            raise EvidencePublicationError(
                f"{dataset_id}: metric acceptance rules did not pass"
            )
        raw_metrics = _mapping(evaluation.get("metrics"))
        values = {
            name: raw_metrics[name]
            for name in OBSERVED_METRICS
            if name in raw_metrics and _valid_metric(raw_metrics[name])
        }
        if not values:
            raise EvidencePublicationError(f"{dataset_id}: observed metrics are empty")
        sample_count = evaluation.get("sample_count")
        if (
            isinstance(sample_count, bool)
            or not isinstance(sample_count, int)
            or sample_count <= 0
        ):
            raise EvidencePublicationError(
                f"{dataset_id}: metric sample count is invalid"
            )
        rows.append(
            {
                "plan_index": int(evaluation.get("plan_index", len(rows))),
                "split": "test",
                "sample_count": sample_count,
                "class_labels": dict(_mapping(evaluation.get("class_labels"))),
                "values": values,
                "acceptance_rules": [
                    {
                        key: _mapping(rule).get(key)
                        for key in (
                            "metric",
                            "value",
                            "operator",
                            "threshold_name",
                            "threshold_value",
                            "passed",
                            "rationale",
                        )
                    }
                    for rule in rules
                ],
            }
        )
    return rows


def _validate_training_curves(
    value: object,
    capture_root: Path,
    *,
    dataset_id: str,
) -> list[_CopySource]:
    if not isinstance(value, list) or not value:
        raise EvidencePublicationError(f"{dataset_id}: training curve file is missing")
    curves: list[_CopySource] = []
    for record in value:
        source = _validate_artifact(
            record,
            capture_root,
            dataset_id=dataset_id,
            label="training curve",
            required_kind="training_curves",
        )
        try:
            payload = json.loads(source.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvidencePublicationError(
                f"{dataset_id}: training curve file is unreadable"
            ) from exc
        rows = payload.get("rows") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not _has_multi_point_curve(rows):
            raise EvidencePublicationError(
                f"{dataset_id}: training curve has no observed multi-point history"
            )
        curves.append(source)
    return curves


def _validate_saliency(
    evidence: Mapping[str, Any], *, capture_root: Path, dataset_id: str
) -> None:
    saliency = _mapping(evidence.get("saliency"))
    methods = saliency.get("methods")
    artifacts = saliency.get("artifacts")
    if not isinstance(methods, list) or not methods or not isinstance(artifacts, list):
        raise EvidencePublicationError(f"{dataset_id}: saliency evidence is missing")
    verified: set[str] = set()
    for record in artifacts:
        mapping = _mapping(record)
        _validate_artifact(
            mapping,
            capture_root,
            dataset_id=dataset_id,
            label="saliency artifact",
            required_kind="saliency",
        )
        if mapping.get("source") != "application_service_saliency_render":
            raise EvidencePublicationError(
                f"{dataset_id}: saliency artifact source is invalid"
            )
        verified.add(str(mapping.get("method") or ""))
    if not {str(item) for item in methods}.issubset(verified):
        raise EvidencePublicationError(f"{dataset_id}: saliency methods are incomplete")


def _validate_screenshots(
    capture_dataset: Mapping[str, Any],
    evidence: Mapping[str, Any],
    *,
    capture_root: Path,
    dataset_id: str,
) -> dict[str, _CopySource]:
    stages = _mapping(capture_dataset.get("stages"))
    result: dict[str, _CopySource] = {}
    for stage_name in ("import_review", "evaluation", "saliency"):
        stage = _mapping(stages.get(stage_name))
        screenshot = _mapping(stage.get("screenshot"))
        path = _relative_file(
            capture_root,
            screenshot.get("path"),
            label=f"{dataset_id} {stage_name} screenshot",
        )
        if path.suffix.casefold() != ".png":
            raise EvidencePublicationError(
                f"{dataset_id}: {stage_name} screenshot is not PNG"
            )
        digest = _sha256(path)
        if (
            screenshot.get("sha256") != digest
            or screenshot.get("size_bytes") != path.stat().st_size
        ):
            raise EvidencePublicationError(
                f"{dataset_id}: {stage_name} screenshot hash changed"
            )
        result[stage_name] = _CopySource(
            path=path,
            sha256=digest,
            size_bytes=path.stat().st_size,
            kind=f"{stage_name}_screenshot",
        )
    execution_screens = evidence.get("screenshots")
    if not isinstance(execution_screens, list):
        raise EvidencePublicationError(
            f"{dataset_id}: execution screenshots are missing"
        )
    by_stage = {
        str(_mapping(item).get("stage") or ""): _mapping(item)
        for item in execution_screens
    }
    for stage_name in ("evaluation", "saliency"):
        record = by_stage.get(stage_name)
        artifact = _validate_artifact(
            record,
            capture_root,
            dataset_id=dataset_id,
            label=f"{stage_name} execution screenshot",
            required_kind="qt_screenshot",
        )
        if artifact.sha256 != result[stage_name].sha256:
            raise EvidencePublicationError(
                f"{dataset_id}: {stage_name} screenshot identities disagree"
            )
    return result


def _validate_artifact(
    value: object,
    capture_root: Path,
    *,
    dataset_id: str,
    label: str,
    required_kind: str | None = None,
) -> _CopySource:
    record = _mapping(value)
    candidate = Path(str(record.get("path") or "")).expanduser()
    if not candidate.is_absolute():
        candidate = capture_root / candidate
    if candidate.is_symlink():
        raise EvidencePublicationError(f"{dataset_id}: {label} file is a symlink")
    path = candidate.resolve()
    root = capture_root.resolve()
    if not path.is_relative_to(root) or path.is_symlink() or not path.is_file():
        raise EvidencePublicationError(f"{dataset_id}: {label} file is missing")
    kind = str(record.get("kind") or "")
    if required_kind is not None and kind != required_kind:
        raise EvidencePublicationError(f"{dataset_id}: {label} kind is invalid")
    size = record.get("size_bytes")
    digest = str(record.get("sha256") or "")
    if (
        isinstance(size, bool)
        or not isinstance(size, int)
        or size <= 0
        or size != path.stat().st_size
        or not HEX_SHA256.fullmatch(digest)
        or _sha256(path) != digest
    ):
        raise EvidencePublicationError(f"{dataset_id}: {label} integrity failed")
    return _CopySource(path=path, sha256=digest, size_bytes=size, kind=kind or label)


def _limitations(
    *values: object,
    dataset_id: str,
) -> list[str]:
    limitations: list[str] = []
    for value in values:
        if not isinstance(value, list):
            raise EvidencePublicationError(f"{dataset_id}: limitations are invalid")
        for item in value:
            if not isinstance(item, str):
                raise EvidencePublicationError(f"{dataset_id}: limitation is not text")
            normalized = re.sub(r"\s+", " ", item).strip()
            if not normalized or len(normalized) > MAX_LIMITATION_LENGTH:
                raise EvidencePublicationError(f"{dataset_id}: limitation is invalid")
            if normalized not in limitations:
                limitations.append(normalized)
    if not limitations or len(limitations) > MAX_LIMITATIONS:
        raise EvidencePublicationError(f"{dataset_id}: limitation count is invalid")
    return limitations


def _publication_plans(
    verified: Mapping[str, Mapping[str, Any]],
    *,
    capture: Mapping[str, Any],
    manifest_sha: str,
    docs_root: Path,
    case_map: Mapping[str, Mapping[str, str]],
) -> tuple[list[_WritePlan], dict[str, Any]]:
    plans: list[_WritePlan] = []
    published: dict[str, Any] = {}
    for dataset_id, evidence in verified.items():
        case_id = str(case_map[dataset_id].get("case_id") or "")
        if not RUN_ID.fullmatch(case_id):
            raise EvidencePublicationError(f"{dataset_id}: case id is invalid")
        prefix = (
            Path("assets")
            / "evidence"
            / "moabb"
            / case_id
            / f"{capture['run_id']}-{manifest_sha}"
        )
        receipts: list[dict[str, Any]] = []
        stage_references: dict[str, list[str]] = {
            "source_and_dataset": [],
            "import_scope": [],
            "labels_and_metadata": [],
            "preprocess": [],
            "epoch": [],
            "split": [],
            "model_and_training": [],
            "evaluation": [],
            "saliency": [],
            "reproducibility_and_limitations": [],
        }
        for curve in evidence["curves"]:
            plan = _copy_plan(curve, prefix=prefix, docs_root=docs_root)
            plans.append(plan)
            receipts.append(_receipt(plan))
            stage_references["model_and_training"].append(plan.reference)
            stage_references["evaluation"].append(plan.reference)
        for stage_name, screenshot in evidence["screenshots"].items():
            plan = _copy_plan(screenshot, prefix=prefix, docs_root=docs_root)
            plans.append(plan)
            receipts.append(_receipt(plan))
            if stage_name == "import_review":
                stage_references["import_scope"].append(plan.reference)
                stage_references["labels_and_metadata"].append(plan.reference)
            else:
                stage_references[stage_name].append(plan.reference)

        summary = _bounded_summary(
            capture=capture,
            evidence=evidence,
            manifest_sha=manifest_sha,
        )
        summary_content = (
            json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        ).encode("utf-8")
        summary_sha = hashlib.sha256(summary_content).hexdigest()
        summary_ref = (prefix / f"bounded-metrics-{summary_sha}.json").as_posix()
        summary_plan = _WritePlan(
            target=docs_root / summary_ref,
            reference=summary_ref,
            sha256=summary_sha,
            size_bytes=len(summary_content),
            kind="bounded_metrics",
            content=summary_content,
        )
        plans.append(summary_plan)
        receipts.append(_receipt(summary_plan))
        for references in stage_references.values():
            references.insert(0, summary_ref)
        evidence_files = [item["reference"] for item in receipts]
        published[dataset_id] = {
            "publication_status": PUBLICATION_STATUS,
            "identity": {
                "manifest_id": f"sha256:{manifest_sha}",
                "app_revision": capture["application_source"]["commit_sha"],
                "run_id": capture["run_id"],
                "dataset_revision": evidence["dataset_revision"],
                "evidence_files": evidence_files,
            },
            "publication": {
                "schema_version": PUBLICATION_SCHEMA_VERSION,
                "input_manifest_sha256": manifest_sha,
                "application_source_digest": capture["application_source"][
                    "source_digest"
                ],
                "registry_sha256": capture["registry"]["sha256"],
                "execution_sha256": evidence["execution_sha256"],
                "published_artifacts": receipts,
            },
            "published_artifacts": receipts,
            "metrics": evidence["metrics"],
            "limitations": evidence["limitations"],
            "saliency_methods": evidence["saliency_methods"],
            "stage_evidence": stage_references,
        }
    total = sum(plan.size_bytes for plan in plans)
    if total > MAX_PUBLISHED_TOTAL_BYTES:
        raise EvidencePublicationError(
            "verified publication exceeds the site asset budget"
        )
    return plans, published


def _bounded_summary(
    *,
    capture: Mapping[str, Any],
    evidence: Mapping[str, Any],
    manifest_sha: str,
) -> dict[str, Any]:
    return {
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        "publication_status": PUBLICATION_STATUS,
        "manifest_id": f"sha256:{manifest_sha}",
        "run_id": capture["run_id"],
        "application": {
            "commit_sha": capture["application_source"]["commit_sha"],
            "source_digest": capture["application_source"]["source_digest"],
        },
        "registry_sha256": capture["registry"]["sha256"],
        "dataset_id": evidence["dataset_id"],
        "dataset_revision": evidence["dataset_revision"],
        "source_files": evidence["source_files"],
        "successful_through": "saliency",
        "observed_metrics": evidence["metrics"],
        "saliency_methods": evidence["saliency_methods"],
        "limitations": evidence["limitations"],
        "source_evidence": {
            "capture_manifest_sha256": manifest_sha,
            "execution_sha256": evidence["execution_sha256"],
        },
    }


def _copy_plan(source: _CopySource, *, prefix: Path, docs_root: Path) -> _WritePlan:
    if source.size_bytes > MAX_PUBLISHED_FILE_BYTES:
        raise EvidencePublicationError(
            f"verified {source.kind} exceeds the per-file publication budget"
        )
    suffix = source.path.suffix.casefold()
    kind = re.sub(r"[^a-z0-9]+", "-", source.kind.casefold()).strip("-")
    reference = (prefix / f"{kind}-{source.sha256}{suffix}").as_posix()
    return _WritePlan(
        target=docs_root / reference,
        reference=reference,
        sha256=source.sha256,
        size_bytes=source.size_bytes,
        kind=source.kind,
        source=source.path,
    )


def _preflight_targets(plans: Sequence[_WritePlan], *, docs_root: Path) -> None:
    references: set[str] = set()
    for plan in plans:
        if plan.reference in references:
            continue
        references.add(plan.reference)
        parent = plan.target.parent.resolve()
        target_is_unsafe = (
            not parent.is_relative_to(docs_root.resolve()) or plan.target.is_symlink()
        )
        target_conflicts = plan.target.exists() and (
            not plan.target.is_file()
            or plan.target.stat().st_size != plan.size_bytes
            or _sha256(plan.target) != plan.sha256
        )
        if target_is_unsafe or target_conflicts:
            raise EvidencePublicationError(
                f"immutable publication target conflicts: {plan.reference}"
            )


def _write_assets(plans: Sequence[_WritePlan]) -> list[Path]:
    written: set[str] = set()
    created: list[Path] = []
    try:
        for plan in plans:
            if plan.reference in written or plan.target.is_file():
                continue
            written.add(plan.reference)
            plan.target.parent.mkdir(parents=True, exist_ok=True)
            temporary = plan.target.with_name(f".{plan.target.name}.part")
            temporary.unlink(missing_ok=True)
            try:
                if plan.source is not None:
                    shutil.copyfile(plan.source, temporary)
                elif plan.content is not None:
                    temporary.write_bytes(plan.content)
                else:  # pragma: no cover - guarded by construction
                    raise EvidencePublicationError("publication plan has no source")
                if (
                    temporary.stat().st_size != plan.size_bytes
                    or _sha256(temporary) != plan.sha256
                ):
                    raise EvidencePublicationError(
                        f"verified asset changed during publication: {plan.reference}"
                    )
                temporary.replace(plan.target)
                created.append(plan.target)
            finally:
                temporary.unlink(missing_ok=True)
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    return created


def _receipt(plan: _WritePlan) -> dict[str, Any]:
    return {
        "reference": plan.reference,
        "kind": plan.kind,
        "sha256": plan.sha256,
        "size_bytes": plan.size_bytes,
    }


def _validate_timestamps(capture: Mapping[str, Any]) -> None:
    try:
        started = datetime.fromisoformat(str(capture["started_at_utc"]))
        completed = datetime.fromisoformat(str(capture["completed_at_utc"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidencePublicationError("capture run timestamps are invalid") from exc
    if started.tzinfo is None or completed.tzinfo is None or completed < started:
        raise EvidencePublicationError("capture run timestamps are not exact")


def _relative_file(root: Path, value: object, *, label: str) -> Path:
    relative = Path(str(value or ""))
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        raise EvidencePublicationError(f"{label} path is not canonical")
    candidate = root / relative
    if candidate.is_symlink():
        raise EvidencePublicationError(f"{label} file is a symlink")
    target = candidate.resolve()
    if (
        not target.is_relative_to(root.resolve())
        or target.is_symlink()
        or not target.is_file()
    ):
        raise EvidencePublicationError(f"{label} file is missing")
    return target


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidencePublicationError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidencePublicationError(f"{label} must contain an object")
    return value


def _hash_file(path: Path, algorithm: str) -> str:
    try:
        digest = hashlib.new(algorithm)
    except ValueError:
        raise
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    return _hash_file(path, "sha256")


def _json_digest(value: Mapping[str, Any]) -> str:
    content = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _valid_metric(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
    )


def _has_multi_point_curve(rows: Sequence[object]) -> bool:
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if any(isinstance(value, list) and len(value) > 1 for value in row.values()):
            return True
    return False


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
