"""Resource-bounded planning and existing-cache verification."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .registry import (
    DEFAULT_REGISTRY_PATH,
    REPO_ROOT,
    expected_download_bytes,
    materialize_dataset,
    registry_sha256,
    select_datasets,
)

CHUNK_SIZE = 1024 * 1024


def utc_now() -> str:
    """Return an RFC 3339 timestamp."""
    return datetime.now(UTC).isoformat()


def default_plan_path(registry: dict[str, Any]) -> Path:
    return REPO_ROOT / registry["resource_policy"]["evidence_root"] / "plan.json"


def build_plan(
    registry: dict[str, Any],
    *,
    dataset_ids: list[str] | None = None,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    """Build a deterministic resource plan without network or EEG reads."""
    datasets = select_datasets(registry, dataset_ids)
    policy = registry["resource_policy"]
    data_root = (REPO_ROOT / policy["data_root"]).resolve()
    expected_bytes = expected_download_bytes(datasets)
    free_bytes = shutil.disk_usage(data_root.parent).free
    minimum_after = int(policy["minimum_free_space_after_fetch_bytes"])
    if expected_bytes > int(policy["max_download_bytes"]):
        raise ValueError("Selected datasets exceed the declared download budget.")
    if free_bytes - expected_bytes < minimum_after:
        raise OSError(
            "Insufficient D-drive free space for the selected profile and headroom."
        )

    files: list[dict[str, Any]] = []
    for dataset in datasets:
        materialized = materialize_dataset(dataset, data_root=data_root)
        for item in materialized["files"]:
            files.append(
                {
                    "dataset_id": dataset["id"],
                    "url": item["url"],
                    "cache_path": item["cache_path"],
                    "size_bytes": item["size_bytes"],
                    "checksum": item["checksum"],
                }
            )
    core = {
        "schema_version": "1.0.0",
        "registry_sha256": registry_sha256(registry_path),
        "registry_profile": registry["profile_id"],
        "moabb_release": registry["moabb_release"],
        "dataset_ids": [dataset["id"] for dataset in datasets],
        "data_root": str(data_root),
        "expected_download_bytes": expected_bytes,
        "max_download_bytes": int(policy["max_download_bytes"]),
        "minimum_free_space_after_fetch_bytes": minimum_after,
        "serial_downloads": True,
        "files": files,
    }
    plan = {
        **core,
        "plan_id": _canonical_sha256(core),
        "created_at": utc_now(),
        "free_bytes_at_plan": free_bytes,
        "validated": True,
    }
    return plan


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON without leaving a partially valid receipt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.part")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_validated_plan(
    path: Path,
    *,
    registry: dict[str, Any],
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    dataset_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Require the exact written plan for the current registry selection."""
    if not path.exists():
        raise FileNotFoundError(f"Validated plan is missing: {path}")
    plan = json.loads(path.read_text(encoding="utf-8"))
    expected = build_plan(
        registry,
        dataset_ids=dataset_ids,
        registry_path=registry_path,
    )
    stable_keys = (
        "schema_version",
        "registry_sha256",
        "registry_profile",
        "moabb_release",
        "dataset_ids",
        "data_root",
        "expected_download_bytes",
        "max_download_bytes",
        "minimum_free_space_after_fetch_bytes",
        "serial_downloads",
        "files",
        "plan_id",
    )
    mismatches = [key for key in stable_keys if plan.get(key) != expected.get(key)]
    if mismatches or plan.get("validated") is not True:
        detail = ", ".join(mismatches) or "validated"
        raise ValueError(
            f"Plan does not match the current registry selection: {detail}"
        )
    return plan


def validate_plan_cache(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate all selected files and return immutable evidence fields."""
    files = [validate_cached_file(item) for item in plan["files"]]
    return {
        "schema_version": "1.0.0",
        "plan_id": plan["plan_id"],
        "registry_sha256": plan["registry_sha256"],
        "validated_at": utc_now(),
        "files": files,
    }


def validate_cached_file(item: dict[str, Any]) -> dict[str, Any]:
    path = Path(item["cache_path"])
    if not path.is_file():
        raise FileNotFoundError(f"Cached dataset file is missing: {path}")
    actual_size = path.stat().st_size
    expected_size = int(item["size_bytes"])
    if actual_size != expected_size:
        raise ValueError(
            f"Cached size mismatch for {path.name}: expected {expected_size}, got {actual_size}"
        )
    _validate_checksum(path, item["checksum"])
    return {
        "path": str(path.resolve()),
        "url": item["url"],
        "size_bytes": actual_size,
        "expected_checksum": dict(item["checksum"]),
        "sha256": _hash_file(path, "sha256"),
    }


def _validate_checksum(path: Path, checksum: dict[str, str]) -> None:
    algorithm = str(checksum["algorithm"]).casefold()
    expected = str(checksum["value"]).casefold()
    actual = _hash_file(path, algorithm)
    if actual != expected:
        raise ValueError(
            f"Checksum mismatch for {path.name}: expected {algorithm}:{expected}, got {actual}"
        )


def _hash_file(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
