#!/usr/bin/env python3
"""Plan and copy verified EEG datasets into one durable storage hierarchy.

The command is deliberately copy-only. It never deletes an old source, never
follows a symlink as a migration authority, and never rewrites an existing
frozen campaign receipt. Cleanup is a later, separately authorized step after
the copied bytes and product workflows have been accepted.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from scripts.dev.fetch_public_eeg_fixtures import (
    FixtureGroup,
    fixture_groups_for_profile,
    validate_fixture_set,
)
from XBrainLab.platform_paths import dataset_storage_layout, user_data_dir

REPO_ROOT = Path(__file__).resolve().parents[2]
FORMAL_BIDS_SOURCE = Path("build/moabb-gui-campaign-v2/data")
FORMAL_BIDS_CHECKSUMS = Path("build/moabb-gui-campaign-v2/checksums")
PUBLIC_FIXTURE_SOURCE = Path("tests/fixtures/data/public")
COMPACT_SOURCE = Path("build/moabb-data")
ACTIVE_SOURCE = Path("build/moabb-gui-campaign-v2/mne-data")
ACTIVE_SOURCE_DATASET_ID = "moabb-15-source"
ACTIVE_SOURCE_EXCLUDED_TOP_LEVEL = (".quarantine", ".staging")
ACTIVE_SOURCE_MANIFEST_NAME = ".xbrainlab-source.sha256"


def _git_head(repo_root: Path) -> str:
    git_executable = shutil.which("git")
    if git_executable is None:
        return "unknown"
    completed = subprocess.run(  # noqa: S603 - resolved local Git executable
        [git_executable, "rev-parse", "HEAD"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _tree_size(path: Path) -> tuple[int, int]:
    file_count = 0
    size_bytes = 0
    if not path.is_dir() or path.is_symlink():
        return file_count, size_bytes
    for candidate in path.rglob("*"):
        if candidate.is_file() and not candidate.is_symlink():
            file_count += 1
            size_bytes += candidate.stat().st_size
    return file_count, size_bytes


def _active_source_relative_files(root: Path) -> tuple[Path, ...]:
    """Return exact active-source files while excluding rollback/staging roots."""
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"Active source root must be a real directory: {root}")
    _reject_symlink_components(root)
    files: list[Path] = []
    excluded = set(ACTIVE_SOURCE_EXCLUDED_TOP_LEVEL)
    for top_level in sorted(root.iterdir(), key=lambda path: path.name):
        if top_level.name in excluded:
            continue
        if top_level.is_symlink():
            raise ValueError(f"Active source tree contains a symlink: {top_level}")
        if top_level.is_file():
            files.append(top_level.relative_to(root))
            continue
        if not top_level.is_dir():
            raise ValueError(f"Active source entry is not regular: {top_level}")
        for candidate in sorted(top_level.rglob("*")):
            if candidate.is_symlink():
                raise ValueError(f"Active source tree contains a symlink: {candidate}")
            if candidate.is_file():
                files.append(candidate.relative_to(root))
    return tuple(files)


def _active_source_tree_size(root: Path) -> tuple[int, int]:
    files = _active_source_relative_files(root)
    return len(files), sum(
        (root / relative_path).stat().st_size for relative_path in files
    )


def _formal_bids_payload_root(
    *, dataset_container: Path, freeze_manifest: Path
) -> Path:
    if (dataset_container / "dataset_description.json").is_file():
        return dataset_container
    if freeze_manifest.is_file():
        try:
            payload = json.loads(freeze_manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        frozen_root = payload.get("bids_root") if isinstance(payload, dict) else None
        if isinstance(frozen_root, str) and frozen_root.strip():
            relocated = dataset_container / Path(frozen_root).name
            if (relocated / "dataset_description.json").is_file():
                return relocated
    candidates = sorted(
        path
        for path in dataset_container.iterdir()
        if path.is_dir()
        and not path.is_symlink()
        and (path / "dataset_description.json").is_file()
    )
    if len(candidates) != 1:
        raise ValueError(
            "Formal-BIDS container must expose exactly one dataset root: "
            f"{dataset_container}"
        )
    return candidates[0]


def _formal_bids_entries(repo_root: Path, data_root: Path) -> list[dict[str, Any]]:
    source_root = repo_root / FORMAL_BIDS_SOURCE
    checksum_root = repo_root / FORMAL_BIDS_CHECKSUMS
    target_root = (
        dataset_storage_layout(environ={"XBRAINLAB_DATA_DIR": str(data_root)}).bids_root
        / "moabb-15"
    )
    entries: list[dict[str, Any]] = []
    if not source_root.is_dir() or source_root.is_symlink():
        return entries
    for dataset_container in sorted(source_root.iterdir(), key=lambda path: path.name):
        if (
            not dataset_container.is_dir()
            or dataset_container.is_symlink()
            or dataset_container.name.startswith(".")
        ):
            continue
        checksum_manifest = checksum_root / f"{dataset_container.name}.sha256"
        freeze_manifest = checksum_root / f"{dataset_container.name}.freeze.json"
        root_error = ""
        try:
            source = _formal_bids_payload_root(
                dataset_container=dataset_container,
                freeze_manifest=freeze_manifest,
            )
        except ValueError as exc:
            source = dataset_container
            root_error = str(exc)
        file_count, size_bytes = _tree_size(source)
        target = target_root / dataset_container.name
        if root_error:
            copy_status = "blocked_invalid_bids_root"
        elif target.exists():
            copy_status = "target_present_unverified"
        elif checksum_manifest.is_file():
            copy_status = "manifest_present_unverified"
        else:
            copy_status = "blocked_missing_checksum_manifest"
        entries.append(
            {
                "dataset_id": dataset_container.name,
                "role": "formal-bids",
                "authority": "frozen-derived",
                "source_path": str(source),
                "target_path": str(target),
                "expected_file_count": file_count,
                "expected_bytes": size_bytes,
                "checksum": {
                    "algorithm": "sha256",
                    "manifest_path": str(checksum_manifest),
                    "path_basis": "dataset-relative",
                },
                "copy_status": copy_status,
                "root_error": root_error,
                "cutover_status": "not_started",
                "old_source_retained": True,
                "deletion_authorized": False,
            }
        )
    return entries


def _cache_entry(
    *,
    dataset_id: str,
    role: str,
    authority: str,
    source: Path,
    target: Path,
) -> dict[str, Any] | None:
    if not source.is_dir() or source.is_symlink():
        return None
    file_count, size_bytes = _tree_size(source)
    return {
        "dataset_id": dataset_id,
        "role": role,
        "authority": authority,
        "source_path": str(source),
        "target_path": str(target),
        "expected_file_count": file_count,
        "expected_bytes": size_bytes,
        "copy_status": "manifest_copy_required",
        "cutover_status": "not_started",
        "old_source_retained": True,
        "deletion_authorized": False,
    }


def _public_fixture_entry(*, source: Path, target: Path) -> dict[str, Any] | None:
    if not source.is_dir() or source.is_symlink():
        return None
    groups = fixture_groups_for_profile("all")
    pinned_files = {
        fixture_file["filename"]: fixture_file
        for group in groups
        for fixture_file in group["files"]
    }
    pinned_bytes = sum(int(item["size_bytes"]) for item in pinned_files.values())
    source_file_count, source_bytes = _tree_size(source)
    pinned_source_ready = all(
        (source / relative_name).is_file()
        and (source / relative_name).stat().st_size == int(item["size_bytes"])
        for relative_name, item in pinned_files.items()
    )
    if target.exists():
        copy_status = "target_present_unverified"
    elif pinned_source_ready:
        copy_status = "manifest_present_unverified"
    else:
        copy_status = "blocked_incomplete_profile"
    return {
        "dataset_id": "pinned-public-fixtures",
        "role": "public-fixtures",
        "authority": "pinned-upstream",
        "source_path": str(source),
        "target_path": str(target),
        "expected_file_count": len(pinned_files),
        "expected_bytes": pinned_bytes,
        "source_file_count": source_file_count,
        "source_bytes": source_bytes,
        "unmanaged_source_bytes": max(source_bytes - pinned_bytes, 0),
        "copy_status": copy_status,
        "cutover_status": "not_started",
        "old_source_retained": True,
        "deletion_authorized": False,
    }


def build_migration_plan(*, repo_root: Path, data_root: Path) -> dict[str, Any]:
    """Return a relocation-aware, non-destructive migration plan."""
    repo_root = repo_root.absolute()
    data_root = data_root.expanduser().absolute()
    layout = dataset_storage_layout(environ={"XBRAINLAB_DATA_DIR": str(data_root)})
    entries = _formal_bids_entries(repo_root, data_root)
    active_source = repo_root / ACTIVE_SOURCE
    if active_source.is_dir() and not active_source.is_symlink():
        file_count, size_bytes = _active_source_tree_size(active_source)
        entries.append(
            {
                "dataset_id": ACTIVE_SOURCE_DATASET_ID,
                "role": "source-cache",
                "authority": "accepted-active-source",
                "source_path": str(active_source),
                "target_path": str(layout.source_root / "moabb-15"),
                "expected_file_count": file_count,
                "expected_bytes": size_bytes,
                "excluded_top_level": list(ACTIVE_SOURCE_EXCLUDED_TOP_LEVEL),
                "checksum": {
                    "algorithm": "sha256",
                    "manifest_path": str(
                        layout.source_root / "moabb-15" / ACTIVE_SOURCE_MANIFEST_NAME
                    ),
                    "path_basis": "source-relative",
                },
                "copy_status": (
                    "target_present_unverified"
                    if (layout.source_root / "moabb-15").exists()
                    else "source_present_unverified"
                ),
                "cutover_status": "not_started",
                "old_source_retained": True,
                "deletion_authorized": False,
            }
        )
    for entry in (
        _public_fixture_entry(
            source=repo_root / PUBLIC_FIXTURE_SOURCE,
            target=layout.public_fixtures_root,
        ),
        _cache_entry(
            dataset_id="legacy-compact-moabb",
            role="source-cache",
            authority="rebuildable",
            source=repo_root / COMPACT_SOURCE,
            target=layout.source_root / "legacy-compact-moabb",
        ),
    ):
        if entry is not None:
            entries.append(entry)
    cleanup_candidates = [
        repo_root / "build/moabb-gui-campaign-v2/data/.quarantine",
        repo_root / "build/moabb-gui-campaign-v2/mne-data/.quarantine",
        repo_root / "build/moabb-download-seeds",
    ]
    return {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "source_head": _git_head(repo_root),
        "repo_root": str(repo_root),
        "data_root": str(data_root),
        "canonical_root": str(layout.datasets_root),
        "entries": entries,
        "cleanup_candidates": [
            {
                "path": str(path),
                "exists": path.exists(),
                "action": "retain_until_cutover_accepted",
                "deletion_authorized": False,
            }
            for path in cleanup_candidates
        ],
        "rollback": {
            "policy": "copy-only; keep every old source until product acceptance",
            "cutover_started": False,
        },
    }


def _read_sha256_manifest(path: Path) -> dict[Path, str]:
    entries: dict[Path, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            digest, raw_relative_path = line.split(maxsplit=1)
        except ValueError as exc:
            raise ValueError(
                f"Invalid checksum manifest row {line_number}: {raw_line!r}"
            ) from exc
        relative_path = Path(raw_relative_path.strip())
        if (
            len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest.lower())
            or relative_path.is_absolute()
            or ".." in relative_path.parts
        ):
            raise ValueError(
                f"Unsafe checksum manifest row {line_number}: {raw_line!r}"
            )
        entries[relative_path] = digest.lower()
    if not entries:
        raise ValueError(f"Checksum manifest is empty: {path}")
    return entries


def _reject_symlink_components(path: Path) -> None:
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise ValueError(f"Migration path contains a symlink: {candidate}")


def _reject_tree_symlinks(root: Path) -> None:
    _reject_symlink_components(root)
    for candidate in root.rglob("*"):
        if candidate.is_symlink():
            raise ValueError(f"Dataset tree contains a symlink: {candidate}")


def _safe_manifest_relative_path(raw_path: str) -> Path:
    relative_path = Path(raw_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"Unsafe manifest path: {raw_path!r}")
    return relative_path


def _resolved_child(*, root: Path, relative_path: Path) -> Path:
    candidate = (root / relative_path).resolve(strict=False)
    if candidate == root or root not in candidate.parents:
        raise ValueError(f"Manifest path escapes the dataset root: {relative_path}")
    return candidate


@contextmanager
def _open_regular_file_no_follow(
    *, root: Path, relative_path: Path
) -> Iterator[BinaryIO]:
    """Open one manifest-owned file without following late symlink swaps."""
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if no_follow and os.open in os.supports_dir_fd:
        directory_fds: list[int] = []
        try:
            try:
                current_fd = os.open(root, os.O_RDONLY | directory | no_follow)
                directory_fds.append(current_fd)
                for component in relative_path.parent.parts:
                    current_fd = os.open(
                        component,
                        os.O_RDONLY | directory | no_follow,
                        dir_fd=current_fd,
                    )
                    directory_fds.append(current_fd)
                file_fd = os.open(
                    relative_path.name,
                    os.O_RDONLY | no_follow,
                    dir_fd=current_fd,
                )
                if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                    os.close(file_fd)
                    raise ValueError(
                        f"Dataset resource is not a regular file: {relative_path}"
                    )
            except OSError as exc:
                raise ValueError(
                    f"Dataset resource changed or became unsafe: {relative_path}"
                ) from exc
            with os.fdopen(file_fd, "rb", closefd=True) as handle:
                yield handle
        finally:
            for directory_fd in reversed(directory_fds):
                with contextlib.suppress(OSError):
                    os.close(directory_fd)
        return

    candidate = root / relative_path
    _reject_symlink_components(candidate)
    resolved = _resolved_child(root=root, relative_path=relative_path)
    if candidate.is_symlink() or not resolved.is_file():
        raise ValueError(f"Dataset resource is not a regular file: {relative_path}")
    with candidate.open("rb") as handle:
        yield handle


def _copy_manifest_file_no_follow(
    *, source: Path, staging: Path, relative_path: Path
) -> None:
    destination = _resolved_child(root=staging, relative_path=relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        _open_regular_file_no_follow(
            root=source, relative_path=relative_path
        ) as source_handle,
        destination.open("xb") as destination_handle,
    ):
        shutil.copyfileobj(source_handle, destination_handle, length=1024 * 1024)


def _require_copy_entry(
    *, by_id: dict[str, dict[str, Any]], dataset_id: str, role: str
) -> dict[str, Any]:
    entry = by_id.get(dataset_id)
    if entry is None or entry["role"] != role:
        raise ValueError(f"Unknown {role} dataset ID: {dataset_id}")
    return entry


def _prepare_copy_roots(*, source: Path, target: Path) -> tuple[Path, Path]:
    source = source.expanduser().absolute()
    target = target.expanduser().absolute()
    _reject_tree_symlinks(source)
    _reject_symlink_components(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(target)
    resolved_source = source.resolve(strict=True)
    resolved_target = target.parent.resolve(strict=True) / target.name
    if (
        resolved_source == resolved_target
        or resolved_source in resolved_target.parents
        or resolved_target in resolved_source.parents
    ):
        raise ValueError("Source and target roots must be distinct and non-nested")
    return resolved_source, resolved_target


@contextmanager
def _owned_copy_staging(target: Path) -> Iterator[Path]:
    lock_path = target.with_name(f".{target.name}.migration.lock")
    try:
        with lock_path.open("x", encoding="utf-8") as lock_handle:
            lock_handle.write("xbrainlab-dataset-migration\n")
    except FileExistsError as exc:
        raise ValueError(f"Another migration owns this target: {target}") from exc
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{target.name}.copying-",
            dir=target.parent,
        )
    )
    try:
        yield staging
    finally:
        with contextlib.suppress(BaseException):
            if staging.exists():
                shutil.rmtree(staging)
        with contextlib.suppress(BaseException):
            lock_path.unlink(missing_ok=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_and_hash_manifest_file(
    *, source: Path, staging: Path, relative_path: Path
) -> tuple[str, int]:
    destination = _resolved_child(root=staging, relative_path=relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size_bytes = 0
    with (
        _open_regular_file_no_follow(
            root=source,
            relative_path=relative_path,
        ) as source_handle,
        destination.open("xb") as destination_handle,
    ):
        while chunk := source_handle.read(1024 * 1024):
            digest.update(chunk)
            destination_handle.write(chunk)
            size_bytes += len(chunk)
    return digest.hexdigest(), size_bytes


def _write_source_manifest(root: Path, entries: dict[Path, str]) -> None:
    manifest = root / ACTIVE_SOURCE_MANIFEST_NAME
    manifest.write_text(
        "".join(
            f"{digest}  {relative_path.as_posix()}\n"
            for relative_path, digest in sorted(
                entries.items(), key=lambda item: item[0].as_posix()
            )
        ),
        encoding="utf-8",
    )


def verify_active_source_cache(source_root: Path) -> dict[str, int]:
    """Verify one exact active source cache against its internal manifest."""
    if not source_root.is_dir() or source_root.is_symlink():
        raise ValueError(
            f"Active source target must be a real directory: {source_root}"
        )
    _reject_tree_symlinks(source_root)
    manifest = source_root / ACTIVE_SOURCE_MANIFEST_NAME
    if not manifest.is_file() or manifest.is_symlink():
        raise ValueError("Active source target has no trusted checksum manifest")
    expected = _read_sha256_manifest(manifest)
    actual = {
        path.relative_to(source_root)
        for path in source_root.rglob("*")
        if path.is_file() and path.name != ACTIVE_SOURCE_MANIFEST_NAME
    }
    if actual != set(expected):
        missing = sorted(str(path) for path in set(expected) - actual)
        extra = sorted(str(path) for path in actual - set(expected))
        raise ValueError(
            f"Active source inventory mismatch: missing={missing[:5]}, extra={extra[:5]}"
        )
    size_bytes = 0
    for relative_path, expected_digest in expected.items():
        candidate = source_root / relative_path
        if _sha256_file(candidate) != expected_digest:
            raise ValueError(f"Active source checksum mismatch: {relative_path}")
        size_bytes += candidate.stat().st_size
    return {"file_count": len(expected), "size_bytes": size_bytes}


def copy_verified_active_source_cache(*, source: Path, target: Path) -> dict[str, Any]:
    """Copy the accepted non-quarantine raw source cache as one exact authority."""
    source = source.expanduser().absolute()
    target = target.expanduser().absolute()
    _reject_symlink_components(source)
    _reject_symlink_components(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(target)
    resolved_source = source.resolve(strict=True)
    resolved_target = target.parent.resolve(strict=True) / target.name
    if (
        resolved_source == resolved_target
        or resolved_source in resolved_target.parents
        or resolved_target in resolved_source.parents
    ):
        raise ValueError("Source and target roots must be distinct and non-nested")
    relative_paths = _active_source_relative_files(resolved_source)
    if target.exists():
        target_result = verify_active_source_cache(target)
        expected = _read_sha256_manifest(target / ACTIVE_SOURCE_MANIFEST_NAME)
        if set(relative_paths) != set(expected):
            raise ValueError("Active source inventory differs from the central target")
        for relative_path, expected_digest in expected.items():
            if _sha256_file(resolved_source / relative_path) != expected_digest:
                raise ValueError(f"Active source checksum mismatch: {relative_path}")
        return {"status": "already_present_and_verified", **target_result}
    with _owned_copy_staging(target) as staging:
        digests: dict[Path, str] = {}
        size_bytes = 0
        for relative_path in relative_paths:
            digest, copied_bytes = _copy_and_hash_manifest_file(
                source=resolved_source,
                staging=staging,
                relative_path=relative_path,
            )
            digests[relative_path] = digest
            size_bytes += copied_bytes
        _write_source_manifest(staging, digests)
        target_result = verify_active_source_cache(staging)
        if target_result != {
            "file_count": len(relative_paths),
            "size_bytes": size_bytes,
        }:
            raise AssertionError("Verified active source inventory changed during copy")
        if target.exists():
            raise ValueError(f"Migration target appeared before publish: {target}")
        staging.replace(target)
    return {"status": "copied_and_verified", **target_result}


def finalize_verified_cleanup_receipt(plan: dict[str, Any]) -> dict[str, Any]:
    """Record a completed cutover only after copied targets exist and sources do not."""
    finalized = copy.deepcopy(plan)
    if finalized.get("copy_state") != "complete":
        raise ValueError("Cleanup receipt requires a complete copy operation")
    for entry in finalized.get("entries", []):
        if entry.get("cutover_status") != "copied_not_cut_over":
            continue
        target = Path(str(entry.get("target_path", "")))
        source = Path(str(entry.get("source_path", "")))
        if not target.exists():
            raise ValueError(f"Verified cleanup target is missing: {target}")
        if source.exists():
            raise ValueError(f"Old cleanup source still exists: {source}")
        entry["cutover_status"] = "cut_over"
        entry["old_source_retained"] = False
        entry["deletion_authorized"] = True
    finalized["cleanup_state"] = "complete"
    finalized["cleanup_completed_at"] = datetime.now(UTC).isoformat()
    return finalized


def verify_formal_bids_dataset(
    *, dataset_root: Path, checksum_manifest: Path
) -> dict[str, int]:
    """Validate an exact formal-BIDS tree against its relative checksum list."""
    if not dataset_root.is_dir():
        raise ValueError(f"Dataset root must be a real directory: {dataset_root}")
    _reject_tree_symlinks(dataset_root)
    expected = _read_sha256_manifest(checksum_manifest)
    actual_paths = {
        path.relative_to(dataset_root)
        for path in dataset_root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    if actual_paths != set(expected):
        missing = sorted(str(path) for path in set(expected) - actual_paths)
        extra = sorted(str(path) for path in actual_paths - set(expected))
        raise ValueError(
            f"Dataset file inventory mismatch: missing={missing[:5]}, extra={extra[:5]}"
        )
    size_bytes = 0
    for relative_path, expected_digest in expected.items():
        candidate = dataset_root / relative_path
        actual_digest = _sha256_file(candidate)
        if actual_digest != expected_digest:
            raise ValueError(f"Dataset checksum mismatch: {relative_path}")
        size_bytes += candidate.stat().st_size
    return {"file_count": len(expected), "size_bytes": size_bytes}


def copy_verified_formal_bids_dataset(
    *, source: Path, target: Path, checksum_manifest: Path
) -> dict[str, Any]:
    """Copy one verified tree atomically without deleting or mutating its source."""
    source, target = _prepare_copy_roots(source=source, target=target)
    source_result = verify_formal_bids_dataset(
        dataset_root=source,
        checksum_manifest=checksum_manifest,
    )
    if target.exists():
        target_result = verify_formal_bids_dataset(
            dataset_root=target,
            checksum_manifest=checksum_manifest,
        )
        return {"status": "already_present_and_verified", **target_result}
    with _owned_copy_staging(target) as staging:
        for relative_path in sorted(_read_sha256_manifest(checksum_manifest)):
            _copy_manifest_file_no_follow(
                source=source,
                staging=staging,
                relative_path=relative_path,
            )
        target_result = verify_formal_bids_dataset(
            dataset_root=staging,
            checksum_manifest=checksum_manifest,
        )
        if target.exists():
            raise ValueError(f"Migration target appeared before publish: {target}")
        staging.replace(target)
    if source_result != target_result:
        raise AssertionError("Verified source and target inventories differ")
    return {"status": "copied_and_verified", **target_result}


def copy_verified_public_fixture_profile(
    *, source: Path, target: Path, groups: list[FixtureGroup]
) -> dict[str, Any]:
    """Copy only pinned public fixture files, excluding unmanaged payloads."""
    source, target = _prepare_copy_roots(source=source, target=target)
    unique_files = {
        str(_safe_manifest_relative_path(fixture_file["filename"])): fixture_file
        for group in groups
        for fixture_file in group["files"]
    }
    validate_fixture_set(source, groups)
    size_bytes = sum(int(item["size_bytes"]) for item in unique_files.values())
    if target.exists():
        validate_fixture_set(target, groups)
        _reject_tree_symlinks(target)
        target_files = {
            str(path.relative_to(target))
            for path in target.rglob("*")
            if path.is_file()
        }
        unmanaged_files = sorted(target_files - set(unique_files))
        if unmanaged_files:
            raise ValueError(
                "Public fixture target contains unmanaged files: "
                + ", ".join(unmanaged_files[:5])
            )
        return {
            "status": "already_present_and_verified",
            "file_count": len(unique_files),
            "size_bytes": size_bytes,
        }
    with _owned_copy_staging(target) as staging:
        for relative_name in sorted(unique_files):
            relative_path = Path(relative_name)
            _copy_manifest_file_no_follow(
                source=source,
                staging=staging,
                relative_path=relative_path,
            )
        validate_fixture_set(staging, groups)
        if target.exists():
            raise ValueError(f"Migration target appeared before publish: {target}")
        staging.replace(target)
    return {
        "status": "copied_and_verified",
        "file_count": len(unique_files),
        "size_bytes": size_bytes,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=user_data_dir(),
        help="Application data root; datasets are stored below its datasets/ child.",
    )
    parser.add_argument("--write-plan", type=Path)
    parser.add_argument(
        "--copy-formal-bids",
        action="append",
        default=[],
        metavar="DATASET_ID",
        help="Copy and verify one named formal-BIDS dataset. Repeat as needed.",
    )
    parser.add_argument(
        "--copy-public-profile",
        choices=("all", "required-ci", "teacher-preflight", "p300-multisubject"),
        help="Copy only the pinned files in one public fixture profile.",
    )
    parser.add_argument(
        "--copy-active-source",
        action="store_true",
        help="Copy the accepted non-quarantine MOABB raw source cache.",
    )
    parser.add_argument(
        "--finalize-cleanup",
        action="store_true",
        help="Verify old sources are absent and finalize an existing plan receipt.",
    )
    args = parser.parse_args()
    copy_action_count = (
        len(args.copy_formal_bids)
        + int(args.copy_public_profile is not None)
        + int(args.copy_active_source)
    )
    if args.finalize_cleanup:
        if args.write_plan is None:
            parser.error("--finalize-cleanup requires --write-plan")
        if copy_action_count:
            parser.error("--finalize-cleanup cannot be combined with copy actions")
        existing = json.loads(args.write_plan.read_text(encoding="utf-8"))
        finalized = finalize_verified_cleanup_receipt(existing)
        _write_json(args.write_plan, finalized)
        print(json.dumps(finalized, indent=2, sort_keys=True))
        return 0
    if copy_action_count and args.write_plan is None:
        parser.error("Copy actions require --write-plan for durable recovery evidence.")
    plan = build_migration_plan(repo_root=args.repo_root, data_root=args.data_root)
    by_id = {entry["dataset_id"]: entry for entry in plan["entries"]}
    copy_results: dict[str, Any] = {}
    plan["copy_results"] = copy_results
    if copy_action_count and args.write_plan is not None:
        plan["copy_state"] = "in_progress"
        _write_json(args.write_plan, plan)
    try:
        for dataset_id in args.copy_formal_bids:
            entry = _require_copy_entry(
                by_id=by_id,
                dataset_id=dataset_id,
                role="formal-bids",
            )
            copy_result = copy_verified_formal_bids_dataset(
                source=Path(entry["source_path"]),
                target=Path(entry["target_path"]),
                checksum_manifest=Path(entry["checksum"]["manifest_path"]),
            )
            copy_results[dataset_id] = copy_result
            entry["copy_status"] = copy_result["status"]
            entry["cutover_status"] = "copied_not_cut_over"
            if args.write_plan is not None:
                _write_json(args.write_plan, plan)
        if args.copy_public_profile is not None:
            entry = _require_copy_entry(
                by_id=by_id,
                dataset_id="pinned-public-fixtures",
                role="public-fixtures",
            )
            copy_result = copy_verified_public_fixture_profile(
                source=Path(entry["source_path"]),
                target=Path(entry["target_path"]),
                groups=fixture_groups_for_profile(args.copy_public_profile),
            )
            copy_results["pinned-public-fixtures"] = copy_result
            entry["copy_status"] = copy_result["status"]
            entry["cutover_status"] = "copied_not_cut_over"
            if args.write_plan is not None:
                _write_json(args.write_plan, plan)
        if args.copy_active_source:
            entry = _require_copy_entry(
                by_id=by_id,
                dataset_id=ACTIVE_SOURCE_DATASET_ID,
                role="source-cache",
            )
            copy_result = copy_verified_active_source_cache(
                source=Path(entry["source_path"]),
                target=Path(entry["target_path"]),
            )
            copy_results[ACTIVE_SOURCE_DATASET_ID] = copy_result
            entry["copy_status"] = copy_result["status"]
            entry["cutover_status"] = "copied_not_cut_over"
            if args.write_plan is not None:
                _write_json(args.write_plan, plan)
    except BaseException as exc:
        plan["copy_state"] = "failed"
        plan["copy_error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        if args.write_plan is not None:
            with contextlib.suppress(BaseException):
                _write_json(args.write_plan, plan)
        raise
    plan["copy_state"] = "complete" if copy_action_count else "not_started"
    if args.write_plan is not None:
        _write_json(args.write_plan, plan)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
