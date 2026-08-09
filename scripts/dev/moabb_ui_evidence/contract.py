"""Fail-closed manifest contract for MOABB Qt journey captures."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from scripts.dev.moabb_user_journeys.registry import REPO_ROOT

SCHEMA_VERSION = "1.0.0"
ARTIFACT_TYPE = "xbrainlab.moabb_qt_user_journey_capture"
GENERATOR = "python -m scripts.dev.moabb_ui_evidence"
MANIFEST_NAME = "qt-capture-manifest.json"
REQUIRED_DATASET_IDS = (
    "ofner2017-mi-gdf",
    "physionetmi-edf-run-semantics",
    "lee2021mobile-erp-brainvision",
)
REQUIRED_STAGES = ("import_review", "evaluation", "saliency")
PROMOTED_STAGE_STATUSES = {"observed", "bounded"}
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_HEX_GIT = re.compile(r"^[0-9a-f]{40,64}$")


def require_build_output_path(
    path: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> Path:
    """Return a resolved output path only when it is inside repo ``build/``."""
    root = repo_root.expanduser().resolve()
    build_root = (root / "build").resolve()
    resolved = path.expanduser()
    if not resolved.is_absolute():
        resolved = root / resolved
    resolved = resolved.resolve()
    if not resolved.is_relative_to(build_root) or resolved == build_root:
        raise ValueError(
            f"MOABB UI evidence output must be inside repo build/: {resolved}"
        )
    return resolved


def dataset_revision(dataset: Mapping[str, Any]) -> str:
    """Hash one registry dataset entry as its immutable route revision."""
    encoded = json.dumps(
        dataset,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_capture_manifest(
    *,
    run_id: str,
    registry_sha256: str,
    registry_profile: str,
    plan_id: str,
    application_source: Mapping[str, Any],
    application_source_at_start: Mapping[str, Any] | None = None,
    qt_platform: str,
    datasets: Sequence[Mapping[str, Any]],
    started_at_utc: str | None = None,
    completed_at_utc: str | None = None,
    failures: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build a manifest whose publication ceiling is derived from stage evidence."""
    completed = completed_at_utc or datetime.now(UTC).isoformat()
    started = started_at_utc or completed
    dataset_rows = [dict(item) for item in datasets]
    source_at_start = dict(application_source_at_start or application_source)
    source_stable = bool(
        source_at_start.get("source_digest")
        and source_at_start.get("source_digest")
        == application_source.get("source_digest")
    )
    capture_session = {
        "source_digest_at_start": str(source_at_start.get("source_digest") or ""),
        "source_digest_at_completion": str(
            application_source.get("source_digest") or ""
        ),
        "source_identity_stable": source_stable,
    }
    qualification = _qualification(
        dataset_rows,
        source_identity_stable=source_stable,
        application_source_clean=application_source.get("dirty") is False,
    )
    status = "completed" if qualification["eligible"] else "partial"
    if failures and not any(_has_promoted_stage(item) for item in dataset_rows):
        status = "failed"
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "generator": GENERATOR,
        "run_id": str(run_id),
        "status": status,
        "started_at_utc": str(started),
        "completed_at_utc": str(completed),
        "registry": {
            "profile_id": str(registry_profile),
            "sha256": str(registry_sha256),
        },
        "plan_id": str(plan_id),
        "application_source": dict(application_source),
        "capture_session": capture_session,
        "capture_environment": {
            "qt_platform": str(qt_platform),
            "capture_kind": "qt_product_widget",
        },
        "datasets": dataset_rows,
        "site_qualification": qualification,
        "failures": [dict(item) for item in failures],
        "claim_boundary": [
            "Bounded screenshots show automated Qt state backed by ApplicationService.",
            "Smoke-profile captures do not establish model quality.",
            "Automated Qt capture is not human Windows desktop acceptance.",
        ],
    }


def write_capture_manifest(output_dir: Path, payload: Mapping[str, Any]) -> Path:
    """Write the capture manifest atomically after referenced files exist."""
    root = require_build_output_path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / MANIFEST_NAME
    temporary = root / f".{MANIFEST_NAME}.part"
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def validate_capture_manifest(
    payload: Mapping[str, Any],
    *,
    output_dir: Path,
    required_dataset_ids: Sequence[str] = REQUIRED_DATASET_IDS,
) -> tuple[bool, str]:
    """Validate exact sources, Qt screenshots, and derived site qualification."""
    if payload.get("schema_version") != SCHEMA_VERSION:
        return False, "MOABB Qt evidence schema version is unsupported."
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        return False, "Artifact is not MOABB Qt user-journey evidence."
    if payload.get("generator") != GENERATOR:
        return False, "MOABB Qt evidence generator identity is unsupported."
    if not str(payload.get("run_id") or "").strip():
        return False, "MOABB Qt evidence run id is missing."
    registry = _mapping(payload.get("registry"))
    if not str(registry.get("profile_id") or "") or not _HEX_SHA256.fullmatch(
        str(registry.get("sha256") or "")
    ):
        return False, "MOABB Qt evidence registry identity is invalid."
    if not str(payload.get("plan_id") or ""):
        return False, "MOABB Qt evidence plan identity is missing."
    app_source = _mapping(payload.get("application_source"))
    if not _HEX_GIT.fullmatch(str(app_source.get("commit_sha") or "")) or not (
        _HEX_SHA256.fullmatch(str(app_source.get("source_digest") or ""))
    ):
        return False, "MOABB Qt evidence application source identity is invalid."
    if not isinstance(app_source.get("dirty"), bool):
        return False, "MOABB Qt evidence dirty-source state is invalid."
    capture_session = _mapping(payload.get("capture_session"))
    source_stable = bool(
        capture_session.get("source_identity_stable") is True
        and capture_session.get("source_digest_at_start")
        == capture_session.get("source_digest_at_completion")
        == app_source.get("source_digest")
    )
    if not all(
        _HEX_SHA256.fullmatch(str(capture_session.get(field) or ""))
        for field in ("source_digest_at_start", "source_digest_at_completion")
    ):
        return False, "MOABB Qt capture source binding is invalid."
    environment = _mapping(payload.get("capture_environment"))
    if environment.get("capture_kind") != "qt_product_widget" or not str(
        environment.get("qt_platform") or ""
    ):
        return False, "MOABB Qt capture environment is incomplete."

    rows = payload.get("datasets")
    if not isinstance(rows, list) or not all(
        isinstance(item, Mapping) for item in rows
    ):
        return False, "MOABB Qt dataset evidence list is invalid."
    observed_ids = [str(item.get("dataset_id") or "") for item in rows]
    if observed_ids != list(required_dataset_ids):
        return False, "MOABB Qt evidence does not cover the exact dataset inventory."
    root = output_dir.expanduser().resolve()
    for item in rows:
        ok, reason = _validate_dataset_record(item, root=root)
        if not ok:
            return ok, reason

    expected_qualification = _qualification(
        rows,
        source_identity_stable=source_stable,
        application_source_clean=app_source.get("dirty") is False,
    )
    if payload.get("site_qualification") != expected_qualification:
        if _contains_unverified_placeholder(rows):
            return False, "UNVERIFIED placeholders can never qualify the user site."
        return False, "MOABB Qt site qualification is inconsistent with evidence."
    expected_status = "completed" if expected_qualification["eligible"] else "partial"
    failures = payload.get("failures")
    if (
        isinstance(failures, list)
        and failures
        and not any(_has_promoted_stage(item) for item in rows)
    ):
        expected_status = "failed"
    if payload.get("status") != expected_status:
        return False, "MOABB Qt aggregate status is inconsistent with evidence."
    return True, ""


def _validate_dataset_record(
    item: Mapping[str, Any],
    *,
    root: Path,
) -> tuple[bool, str]:
    dataset_id = str(item.get("dataset_id") or "")
    if not _HEX_SHA256.fullmatch(str(item.get("dataset_revision") or "")):
        return False, f"{dataset_id}: dataset revision is invalid."
    exact_source = _mapping(item.get("exact_source"))
    if exact_source.get("status") != "verified" or not str(
        exact_source.get("plan_id") or ""
    ):
        return False, f"{dataset_id}: exact-source evidence is not verified."
    files = exact_source.get("files")
    if not isinstance(files, list) or not files:
        return False, f"{dataset_id}: exact-source evidence has no files."
    for source in files:
        ok, reason = _validate_source_file(source)
        if not ok:
            return False, f"{dataset_id}: exact-source {reason}"

    execution = _mapping(item.get("execution"))
    execution_status = str(execution.get("status") or "")
    if execution_status not in {"completed", "failed", "not_run", "pending"}:
        return False, f"{dataset_id}: execution status is invalid."
    if execution_status in {"completed", "failed"}:
        ok, reason = _validate_execution_evidence(execution, root=root)
        if not ok:
            return False, f"{dataset_id}: {reason}"

    stages = _mapping(item.get("stages"))
    if set(stages) != set(REQUIRED_STAGES):
        return False, f"{dataset_id}: capture stages are incomplete."
    for stage_name in REQUIRED_STAGES:
        stage = _mapping(stages.get(stage_name))
        status = str(stage.get("status") or "")
        if status not in {*PROMOTED_STAGE_STATUSES, "unverified"}:
            if status.upper() == "UNVERIFIED":
                return False, "UNVERIFIED placeholders can never qualify the user site."
            return False, f"{dataset_id}: {stage_name} status is invalid."
        placeholder = stage.get("placeholder")
        if status == "unverified":
            if placeholder:
                if stage.get("label") != "UNVERIFIED":
                    return (
                        False,
                        f"{dataset_id}: placeholder is not labeled UNVERIFIED.",
                    )
                screenshot = _mapping(stage.get("screenshot"))
                if screenshot:
                    ok, reason = _validate_screenshot(screenshot, root=root)
                    if not ok:
                        return False, f"{dataset_id}: {stage_name} {reason}"
            elif stage.get("screenshot"):
                return False, f"{dataset_id}: unverified stage exposes evidence."
            if not str(stage.get("reason") or ""):
                return False, f"{dataset_id}: unverified stage has no limitation."
            continue
        commands = stage.get("application_service_commands")
        if not isinstance(commands, list) or not all(
            isinstance(command, str) and command for command in commands
        ):
            return False, f"{dataset_id}: {stage_name} has no ApplicationService trace."
        ok, reason = _validate_screenshot(_mapping(stage.get("screenshot")), root=root)
        if not ok:
            return False, f"{dataset_id}: {stage_name} {reason}"
        ok, reason = _validate_stage_product_facts(stage_name, stage)
        if not ok:
            return False, f"{dataset_id}: {reason}"
    return True, ""


def _validate_execution_evidence(
    execution: Mapping[str, Any],
    *,
    root: Path,
) -> tuple[bool, str]:
    relative = Path(str(execution.get("evidence_path") or ""))
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        return False, "journey evidence path is not canonical."
    path = (root / relative).resolve()
    digest = str(execution.get("evidence_sha256") or "")
    if not path.is_relative_to(root) or not path.is_file():
        return False, "journey evidence file is missing."
    if not _HEX_SHA256.fullmatch(digest) or _sha256(path) != digest:
        return False, "journey evidence hash does not match."
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "journey evidence file is unreadable."
    if not isinstance(payload, dict):
        return False, "journey evidence root is invalid."
    return True, ""


def _validate_stage_product_facts(
    stage_name: str,
    stage: Mapping[str, Any],
) -> tuple[bool, str]:
    commands = {str(item) for item in stage.get("application_service_commands", [])}
    if stage_name == "import_review":
        expected = {
            "scan_source",
            "preview_interpretation",
            "validate_interpretation",
        }
        if not expected.issubset(commands):
            return False, "import/review command trace is incomplete."
        if not _mapping(stage.get("application_state")):
            return False, "import/review ApplicationService state is missing."
        return True, ""
    if stage_name == "evaluation":
        if "evaluate" not in commands:
            return False, "evaluation command trace is incomplete."
        expected_labels = stage.get("expected_class_labels")
        observed_labels = stage.get("observed_class_labels")
        if (
            stage.get("split") != "test"
            or not _positive_int(stage.get("sample_count"))
            or not _positive_int(stage.get("class_count"))
            or not _string_list(expected_labels)
            or not _string_list(observed_labels)
            or not isinstance(stage.get("route_semantics_match"), bool)
        ):
            return False, "evaluation held-out render facts are incomplete."
        return True, ""
    if "saliency" not in commands:
        return False, "saliency command trace is incomplete."
    render = _mapping(stage.get("render_evidence"))
    if (
        not str(stage.get("method") or "")
        or not str(stage.get("source_split") or "")
        or not isinstance(stage.get("route_semantics_match"), bool)
        or not _positive_int(render.get("axes_count"))
        or not _positive_int(render.get("image_count"))
        or render.get("canvas_visible") is not True
        or not str(render.get("explanation_context") or "")
    ):
        return False, "saliency product render facts are incomplete."
    return True, ""


def _validate_source_file(value: object) -> tuple[bool, str]:
    source = _mapping(value)
    path = Path(str(source.get("path") or "")).expanduser()
    if not path.is_absolute() or not path.is_file():
        return False, "file is missing."
    expected_size = source.get("size_bytes")
    expected_sha = str(source.get("sha256") or "")
    if isinstance(expected_size, bool) or not isinstance(expected_size, int):
        return False, "size is invalid."
    if path.stat().st_size != expected_size:
        return False, "size no longer matches."
    if not _HEX_SHA256.fullmatch(expected_sha) or _sha256(path) != expected_sha:
        return False, "hash no longer matches."
    checksum = _mapping(source.get("expected_checksum"))
    if not str(checksum.get("algorithm") or "") or not str(checksum.get("value") or ""):
        return False, "declared checksum is missing."
    if not str(source.get("url") or "").startswith("https://"):
        return False, "source URL is invalid."
    return True, ""


def _validate_screenshot(
    value: Mapping[str, Any],
    *,
    root: Path,
) -> tuple[bool, str]:
    relative = Path(str(value.get("path") or ""))
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        return False, "screenshot path is not canonical."
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return False, "screenshot is missing."
    content = path.read_bytes()
    if int(value.get("size_bytes") or 0) != len(content):
        return False, "screenshot size does not match."
    digest = str(value.get("sha256") or "")
    if (
        not _HEX_SHA256.fullmatch(digest)
        or hashlib.sha256(content).hexdigest() != digest
    ):
        return False, "screenshot hash does not match."
    try:
        with Image.open(path) as image:
            dimensions = [int(image.width), int(image.height)]
            image_format = str(image.format or "")
            image.verify()
    except OSError:
        return False, "screenshot is unreadable."
    if value.get("dimensions") != dimensions or value.get("format") != image_format:
        return False, "screenshot decode metadata does not match."
    return True, ""


def _qualification(
    datasets: Sequence[Mapping[str, Any]],
    *,
    source_identity_stable: bool = True,
    application_source_clean: bool = True,
) -> dict[str, Any]:
    reasons: list[str] = []
    if not source_identity_stable:
        reasons.append("application_source_changed_during_capture")
    if not application_source_clean:
        reasons.append("application_source_dirty")
    expected_ids = list(REQUIRED_DATASET_IDS)
    observed_ids = [str(item.get("dataset_id") or "") for item in datasets]
    if observed_ids != expected_ids:
        reasons.append("dataset_inventory_incomplete")
    for item in datasets:
        dataset_id = str(item.get("dataset_id") or "unknown")
        exact_source = _mapping(item.get("exact_source"))
        if exact_source.get("status") != "verified" or not exact_source.get("files"):
            reasons.append(f"{dataset_id}:exact_source_unverified")
        stages = _mapping(item.get("stages"))
        for stage_name in REQUIRED_STAGES:
            stage = _mapping(stages.get(stage_name))
            if (
                stage.get("status") not in PROMOTED_STAGE_STATUSES
                or not stage.get("screenshot")
                or stage.get("placeholder")
            ):
                reasons.append(f"{dataset_id}:{stage_name}_unverified")
            elif (
                stage_name in {"evaluation", "saliency"}
                and stage.get("route_semantics_match") is not True
            ):
                reasons.append(f"{dataset_id}:{stage_name}_route_semantics_mismatch")
        execution = _mapping(item.get("execution"))
        if execution.get("status") != "completed":
            reasons.append(f"{dataset_id}:execution_incomplete")
    reasons = list(dict.fromkeys(reasons))
    return {
        "eligible": not reasons,
        "publication_status_ceiling": "bounded" if not reasons else "unverified",
        "reason_codes": reasons,
    }


def _has_promoted_stage(item: Mapping[str, Any]) -> bool:
    return any(
        _mapping(stage).get("status") in PROMOTED_STAGE_STATUSES
        for stage in _mapping(item.get("stages")).values()
    )


def _contains_unverified_placeholder(
    datasets: Sequence[Mapping[str, Any]],
) -> bool:
    return any(
        bool(_mapping(stage).get("placeholder"))
        for item in datasets
        for stage in _mapping(item.get("stages")).values()
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        return []
    return list(value)


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
