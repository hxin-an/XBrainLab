"""Pinned representative import membership and portable, content-bound cases."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

CATALOG_PATH = Path(__file__).parent / "data" / "moabb-import-catalog-v1.json"
MOABB_COMMIT = "140809d8c48bdf2be953951ff75f688122edee34"  # pragma: allowlist secret
EXPORT_IDS_SHA256 = "54fb266eedcb549361f7dd7f5fe64af573e571f69467820f0fc599ce188f1bad"  # pragma: allowlist secret
INITIAL_NONREQUIRED_SHA256 = "599b54194c4e767433c0a6d2d7d7c632aba2c161dc2207bcc8e6033403484fe0"  # pragma: allowlist secret
STATUSES = frozenset({"required", "deferred_rights", "blocked"})


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    """Load membership; runtime binding readiness is checked before execution."""
    catalog = json.loads(path.read_text(encoding="utf-8"))
    validate_catalog(catalog)
    return catalog


def validate_catalog(catalog: dict[str, Any]) -> None:
    if catalog.get("schema_version") != 1 or catalog.get("moabb_release") != {
        "version": "1.5.0",
        "commit": MOABB_COMMIT,
    }:
        raise ValueError("Import catalog release identity changed")
    entries = catalog.get("entries")
    if not isinstance(entries, list) or len(entries) != 147:
        raise ValueError("Import catalog must account for all 147 exports")
    ids = [row.get("id") for row in entries if isinstance(row, dict)]
    if len(ids) != 147 or not all(isinstance(value, str) for value in ids):
        raise ValueError("Import catalog requires named entries")
    digest = hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()
    if digest != EXPORT_IDS_SHA256:
        raise ValueError("Import catalog export membership changed")
    for row in entries:
        if row.get("status") not in STATUSES:
            raise ValueError(f"Unknown import status: {row['id']}")
        if not row.get("module") or not row.get("evidence_note"):
            raise ValueError(f"Missing import disposition: {row['id']}")
        hashes = row.get("evidence_hashes")
        if (
            not isinstance(hashes, list)
            or (row["status"] == "required" and not hashes)
            or any(
                not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)
                for value in hashes
            )
        ):
            raise ValueError(f"Missing or incomplete evidence identity: {row['id']}")
    baseline = catalog.get("initial_nonrequired_ids")
    if not isinstance(baseline, list) or not all(
        isinstance(item, str) for item in baseline
    ):
        raise ValueError("Missing initial baseline membership")
    if (
        hashlib.sha256("\n".join(sorted(baseline)).encode()).hexdigest()
        != INITIAL_NONREQUIRED_SHA256
    ):
        raise ValueError("Initial baseline membership changed")
    lost = (
        set(ids)
        - set(baseline)
        - {row["id"] for row in entries if row["status"] == "required"}
    )
    if lost:
        raise ValueError(f"Import baseline regression: {', '.join(sorted(lost))}")


def require_no_regressions(previous: dict[str, Any], current: dict[str, Any]) -> None:
    """Compare release catalogs before admitting a new candidate baseline."""
    validate_catalog(previous)
    validate_catalog(current)
    required = {row["id"] for row in previous["entries"] if row["status"] == "required"}
    lost = required - {
        row["id"] for row in current["entries"] if row["status"] == "required"
    }
    if lost:
        raise ValueError(f"Import baseline regression: {', '.join(sorted(lost))}")


def resolve_data_path(data_root: Path, value: str) -> Path:
    """Reject nonportable paths, traversal and links before reading dataset bytes."""
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or ":" in value
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).drive
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("Data path must be a portable relative path")
    root = data_root.absolute()
    target = root / value
    for path in (target, *target.parents):
        if path.is_symlink() or (
            path.exists()
            and getattr(path.lstat(), "st_file_attributes", 0)
            & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise ValueError(f"Linked data path is not allowed: {path}")
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Data path must remain relative to the data root")
    return target


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def resolve_case_manifest(row: dict[str, Any], data_root: Path) -> dict[str, Any]:
    binding = row.get("case_manifest")
    if not isinstance(binding, dict):
        raise ValueError(f"Missing case manifest: {row['id']}")
    path = resolve_data_path(data_root, binding.get("path", ""))
    expected = binding.get("sha256", "")
    if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError(f"Invalid case manifest identity: {row['id']}")
    # Read once: validation and parsing must refer to the same bytes.
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError(f"Case manifest identity changed: {row['id']}")
    case = json.loads(content)
    if not isinstance(case, dict) or case.get("id") != row["id"]:
        raise ValueError(f"Case manifest dataset identity changed: {row['id']}")
    return case


def render_inventory_rows(catalog: dict[str, Any]) -> str:
    validate_catalog(catalog)
    lines = [
        "| Dataset export | Source module | Available runtime evidence |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| {row['id']} | `{row['module']}` | {row['evidence_note']} |"
        for row in catalog["entries"]
    )
    return "\n".join(lines) + "\n"
