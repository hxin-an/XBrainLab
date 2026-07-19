"""Staging and canonical publication for Guided Workflow evidence."""

from __future__ import annotations

import copy
import json
import shutil
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_screenshot_artifacts,
)
from scripts.dev.chatpanel_guided_boundary.evidence import (
    render_guided_boundary_markdown,
)

_CANONICAL_SCREENSHOT_NAMES = {
    "ready": "chatpanel-guided-boundary-ready.png",
    "auto_chain_complete": "chatpanel-guided-auto-chain-complete.png",
    "workflow_dialog_open": "chatpanel-guided-workflow-dialog-open.png",
    "post_cancel": "chatpanel-guided-post-cancel.png",
    "failure": "chatpanel-guided-boundary-failure.png",
}


def create_guided_boundary_staging_dir(current_root: Path) -> tuple[str, Path]:
    """Create a sibling staging directory that cannot be mistaken for current."""
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{run_id}-{uuid.uuid4().hex[:8]}"
    root = current_root.expanduser().resolve()
    staging = root.parent / f".{root.name}-staging-{run_id}"
    staging.mkdir(parents=True, exist_ok=False)
    return run_id, staging


def publish_guided_boundary_artifact_run(
    *,
    staging_dir: Path,
    current_root: Path,
    payload: Mapping[str, Any],
    frozen_source_identity: Mapping[str, Any],
    run_id: str,
    json_name: str,
    markdown_name: str,
) -> tuple[Path, dict[str, Any]]:
    """Publish passed evidence at the canonical root and retain failures by run."""
    source_digest = str(frozen_source_identity.get("source_digest") or "")
    if not source_digest:
        raise ValueError("Guided evidence publication requires frozen source identity.")
    canonical = current_root.expanduser().resolve()
    prepared = copy.deepcopy(dict(payload))
    if prepared.get("status") == "passed" and not _capture_source_is_frozen(
        prepared,
        source_digest=source_digest,
    ):
        prepared["status"] = "failed"
        prepared["failure_reason"] = (
            "Guided capture source was not frozen; current publication rejected."
        )
    passed = prepared.get("status") == "passed"
    destination = canonical if passed else canonical / "runs" / run_id
    destination.mkdir(parents=True, exist_ok=True)

    relocated = _relocate_payload(
        prepared,
        source_dir=staging_dir.expanduser().resolve(),
        destination_dir=destination,
    )
    relocated = _canonicalize_screenshot_paths(relocated, destination)
    relocated["source_identity"] = dict(frozen_source_identity)
    relocated["generated_at_utc"] = datetime.now(UTC).isoformat()
    _publish_screenshots(
        prepared,
        relocated,
        staging_dir=staging_dir.expanduser().resolve(),
        destination=destination,
        run_id=run_id,
    )
    relocated["screenshot_artifacts"] = collect_screenshot_artifacts(
        _mapping(relocated.get("screenshots"))
    )
    _write_current_reports(
        destination,
        relocated,
        run_id=run_id,
        json_name=json_name,
        markdown_name=markdown_name,
    )
    shutil.rmtree(staging_dir, ignore_errors=True)
    return destination, relocated


def _capture_source_is_frozen(
    payload: Mapping[str, Any],
    *,
    source_digest: str,
) -> bool:
    capture_source = _mapping(payload.get("capture_source"))
    started = str(capture_source.get("source_digest_at_start") or "")
    completed = str(capture_source.get("source_digest_at_completion") or "")
    return bool(
        capture_source.get("stable") is True
        and started
        and started == completed == source_digest
    )


def _publish_screenshots(
    original: Mapping[str, Any],
    relocated: Mapping[str, Any],
    *,
    staging_dir: Path,
    destination: Path,
    run_id: str,
) -> None:
    original_screenshots = _mapping(original.get("screenshots"))
    relocated_screenshots = _mapping(relocated.get("screenshots"))
    for name, original_value in original_screenshots.items():
        source_text = str(original_value or "")
        destination_text = str(relocated_screenshots.get(name) or "")
        if not source_text or not destination_text:
            continue
        source = Path(source_text).expanduser().resolve()
        target = Path(destination_text).expanduser().resolve()
        if source.parent != staging_dir or target.parent != destination:
            raise ValueError(f"Noncanonical Guided screenshot path: {name}.")
        if not source.is_file():
            raise FileNotFoundError(f"Guided screenshot does not exist: {source}.")
        temporary = destination / f".{target.name}.{run_id}.tmp"
        shutil.copy2(source, temporary)
        temporary.replace(target)


def _canonicalize_screenshot_paths(
    payload: dict[str, Any],
    destination: Path,
) -> dict[str, Any]:
    screenshots = _mapping(payload.get("screenshots"))
    replacements: dict[str, str] = {}
    for key, canonical_name in _CANONICAL_SCREENSHOT_NAMES.items():
        current = str(screenshots.get(key) or "")
        if not current:
            continue
        replacements[current] = str(destination / canonical_name)

    def replace(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): replace(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, tuple):
            return [replace(item) for item in value]
        if isinstance(value, str):
            return replacements.get(value, value)
        return value

    canonicalized = replace(payload)
    if not isinstance(canonicalized, dict):
        raise TypeError("Guided artifact payload must remain a mapping.")
    return canonicalized


def _write_current_reports(
    destination: Path,
    payload: Mapping[str, Any],
    *,
    run_id: str,
    json_name: str,
    markdown_name: str,
) -> None:
    json_path = destination / json_name
    markdown_path = destination / markdown_name
    json_temporary = destination / f".{json_name}.{run_id}.tmp"
    markdown_temporary = destination / f".{markdown_name}.{run_id}.tmp"
    json_temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    markdown_temporary.write_text(
        render_guided_boundary_markdown(payload),
        encoding="utf-8",
    )
    markdown_temporary.replace(markdown_path)
    json_temporary.replace(json_path)


def _relocate_payload(
    payload: Mapping[str, Any],
    *,
    source_dir: Path,
    destination_dir: Path,
) -> dict[str, Any]:
    source_prefix = str(source_dir)
    destination_prefix = str(destination_dir)

    def relocate(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): relocate(item) for key, item in value.items()}
        if isinstance(value, list):
            return [relocate(item) for item in value]
        if isinstance(value, tuple):
            return [relocate(item) for item in value]
        if isinstance(value, str) and value.startswith(source_prefix):
            return destination_prefix + value[len(source_prefix) :]
        return copy.deepcopy(value)

    result = relocate(payload)
    if not isinstance(result, dict):
        raise TypeError("Guided artifact payload must remain a mapping.")
    return result


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
