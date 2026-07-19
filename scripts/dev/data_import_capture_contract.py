"""Source-bound manifest contract for canonical Data Import wizard captures."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.dev.app_polish_capture_contract import (
    SCHEMA_VERSION,
    build_source_bound_capture_session,
    validate_source_bound_capture_session,
    validate_source_bound_identity,
    validate_source_bound_screenshot,
)
from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    inspect_screenshot_artifact,
)

ARTIFACT_TYPE = "xbrainlab.data_import_wizard_steps"
MANIFEST_NAME = "data-import-wizard-steps-evidence.json"
GENERATOR = "scripts/dev/capture_data_import_wizard_steps.py"
DEFAULT_MAX_AGE = timedelta(hours=24)


def build_data_import_capture_manifest(
    output_dir: Path,
    *,
    expected_surfaces: Sequence[str],
    selected_surfaces: Sequence[str],
    source_identity: Mapping[str, Any],
    source_identity_at_start: Mapping[str, Any] | None,
    capture_started_at: datetime,
    generated_at: datetime,
    qt_platform: str,
    session_id: str,
) -> dict[str, Any]:
    """Build one complete-or-explicitly-partial Data Import capture manifest."""
    root = output_dir.expanduser().resolve()
    expected = list(dict.fromkeys(map(str, expected_surfaces)))
    selected = list(dict.fromkeys(map(str, selected_surfaces)))
    completed_at = generated_at.astimezone(UTC)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "generator": GENERATOR,
        "generated_at_utc": completed_at.isoformat(),
        "capture_environment": {
            "qt_platform": str(qt_platform),
            "capture_kind": "xcb_native_window",
            "qt_style": "Fusion",
        },
        "capture_scope": {
            "expected_surfaces": expected,
            "selected_surfaces": selected,
            "complete": selected == expected,
        },
        "capture_session": build_source_bound_capture_session(
            source_identity=source_identity,
            source_identity_at_start=source_identity_at_start,
            capture_started_at=capture_started_at,
            completed_at=completed_at,
            session_id=session_id,
        ),
        "source_identity": dict(source_identity),
        "screenshots": {
            filename: _screenshot_metadata(root, filename) for filename in selected
        },
        "claim_boundary": (
            "Automated xcb Data Import capture evidence; not human Windows desktop "
            "acceptance."
        ),
    }


def write_data_import_capture_manifest(
    output_dir: Path,
    payload: Mapping[str, Any],
) -> Path:
    """Atomically write a manifest after its referenced screenshots are present."""
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / MANIFEST_NAME
    temporary = output_dir / f".{MANIFEST_NAME}.tmp"
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def load_data_import_capture_manifest(output_dir: Path) -> dict[str, Any]:
    value = json.loads((output_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Data Import capture manifest root must be a JSON object.")
    return value


def validate_data_import_capture_manifest(
    payload: Mapping[str, Any],
    *,
    output_dir: Path,
    expected_surfaces: Sequence[str],
    require_complete: bool = True,
    max_age: timedelta | None = DEFAULT_MAX_AGE,
    now: datetime | None = None,
    refresh_source_identity: bool = True,
    current_source_identity: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    """Reject stale source, partial canonical, or tampered Data Import evidence."""
    if refresh_source_identity and current_source_identity is not None:
        return False, "Current source identity override cannot bypass refresh."
    if not refresh_source_identity and current_source_identity is None:
        return False, "Disabled source refresh requires an explicit current identity."
    if payload.get("schema_version") != SCHEMA_VERSION:
        return False, "Data Import capture schema version is missing or unsupported."
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        return False, "Artifact is not Data Import wizard capture evidence."
    if payload.get("generator") != GENERATOR:
        return (
            False,
            "Data Import capture generator identity is missing or unsupported.",
        )
    environment = _mapping(payload.get("capture_environment"))
    if (
        environment.get("capture_kind") != "xcb_native_window"
        or environment.get("qt_style") != "Fusion"
        or not str(environment.get("qt_platform") or "")
    ):
        return False, "Data Import capture environment is incomplete."

    ok, reason = _validate_timestamp(
        payload.get("generated_at_utc"), now=now, max_age=max_age
    )
    if not ok:
        return ok, reason
    ok, reason = validate_source_bound_identity(
        payload.get("source_identity"),
        refresh=refresh_source_identity,
        current_identity=current_source_identity,
        artifact_name="Data Import capture",
    )
    if not ok:
        return ok, reason
    ok, reason = validate_source_bound_capture_session(
        payload.get("capture_session"),
        generated_at=payload.get("generated_at_utc"),
        source_identity=payload.get("source_identity"),
        artifact_name="Data Import capture",
    )
    if not ok:
        return ok, reason

    scope = _mapping(payload.get("capture_scope"))
    expected = _string_list(scope.get("expected_surfaces"))
    selected = _string_list(scope.get("selected_surfaces"))
    canonical = list(dict.fromkeys(map(str, expected_surfaces)))
    if expected != canonical:
        return (
            False,
            "Data Import expected surfaces do not match the canonical inventory.",
        )
    if not expected or len(expected) != len(set(expected)):
        return False, "Data Import expected surface list is missing or duplicated."
    if not selected or len(selected) != len(set(selected)):
        return False, "Data Import selected surface list is missing or duplicated."
    if any(filename not in expected for filename in selected):
        return False, "Data Import selected surfaces are outside the capture contract."
    complete = selected == expected
    if bool(scope.get("complete")) is not complete:
        return False, "Data Import capture completeness flag is inconsistent."
    if require_complete and not complete:
        return False, "Data Import evidence is a partial capture, not current evidence."

    screenshots = _mapping(payload.get("screenshots"))
    if set(screenshots) != set(selected):
        return (
            False,
            "Data Import screenshot manifest does not match selected surfaces.",
        )
    root = output_dir.expanduser().resolve()
    for filename in selected:
        ok, reason = validate_source_bound_screenshot(
            root,
            filename,
            screenshots.get(filename),
            artifact_name="Data Import capture",
        )
        if not ok:
            return ok, reason
    if "not human Windows desktop acceptance" not in str(
        payload.get("claim_boundary") or ""
    ):
        return (
            False,
            "Data Import capture claim boundary does not exclude human acceptance.",
        )
    return True, ""


def _screenshot_metadata(root: Path, filename: str) -> dict[str, Any]:
    metadata = inspect_screenshot_artifact(root / filename)
    metadata["path"] = filename
    return metadata


def _validate_timestamp(
    value: object,
    *,
    now: datetime | None,
    max_age: timedelta | None,
) -> tuple[bool, str]:
    try:
        generated = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return False, "Data Import capture UTC timestamp is invalid."
    if generated.tzinfo is None or generated.utcoffset() != timedelta(0):
        return False, "Data Import capture timestamp is not UTC."
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if max_age is not None and current - generated.astimezone(UTC) > max_age:
        return False, "Data Import capture evidence timestamp is stale."
    return True, ""


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return []
    return list(value)
