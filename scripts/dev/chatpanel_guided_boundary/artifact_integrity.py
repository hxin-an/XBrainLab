"""Content-addressed screenshot and dirty-source evidence helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
SOURCE_IDENTITY_VERSION = 3
_GENERATED_PREFIXES = (
    "artifacts/",
    "build/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "XBrainLab/llm/core/models/",
)
_LOCAL_STATE_PATHS = ("settings.json",)
_INCLUDED_FILE_POLICY = "all-non-generated-tracked-and-untracked-files"
_SOURCE_PATHSPECS = (":(glob)**",)
_SOURCE_EXCLUDE_PATHSPECS = (
    *(f":(exclude,glob){prefix}**" for prefix in _GENERATED_PREFIXES),
    *(f":(exclude,literal){path}" for path in _LOCAL_STATE_PATHS),
)
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_HEX_GIT_OBJECT = re.compile(r"^[0-9a-f]{40,64}$")
SOURCE_IDENTITY_REQUIRED_FIELDS = (
    "version",
    "repo_root",
    "branch",
    "commit_sha",
    "head_tree_sha",
    "dirty",
    "dirty_digest",
    "source_content_digest",
    "source_digest",
    "untracked_source_count",
)
SOURCE_IDENTITY_FRESHNESS_POLICY_FIELDS = (
    "version",
    "repo_root",
    "excluded_generated_prefixes",
    "excluded_local_paths",
    "included_file_policy",
)


def collect_screenshot_artifacts(
    screenshots: Mapping[str, object],
) -> dict[str, dict[str, Any]]:
    """Record path, content hash, and decoded dimensions for every screenshot."""
    return {
        str(name): inspect_screenshot_artifact(value)
        for name, value in screenshots.items()
    }


def inspect_screenshot_artifact(value: object) -> dict[str, Any]:
    """Return fail-closed metadata without raising on a missing/corrupt image."""
    path_text = str(value or "")
    artifact: dict[str, Any] = {
        "path": path_text,
        "exists": False,
        "readable": False,
        "byte_size": 0,
        "sha256": "",
        "dimensions": [],
        "format": "",
        "error": "",
    }
    if not path_text:
        return artifact
    path = Path(path_text).expanduser()
    if not path.is_file():
        artifact["error"] = "Screenshot path is not a regular file."
        return artifact
    artifact["exists"] = True
    try:
        content = path.read_bytes()
        artifact["byte_size"] = len(content)
        artifact["sha256"] = hashlib.sha256(content).hexdigest()
        with Image.open(path) as image:
            width, height = image.size
            image_format = str(image.format or "")
            image.verify()
        artifact["dimensions"] = [int(width), int(height)]
        artifact["format"] = image_format
        artifact["readable"] = bool(content and width > 0 and height > 0)
    except (OSError, ValueError) as exc:
        artifact["error"] = f"{type(exc).__name__}: {exc}"
    return artifact


def collect_source_identity(
    repo_root: Path = ROOT,
    *,
    refresh: bool = False,
) -> dict[str, Any]:
    """Fingerprint HEAD plus every non-generated dirty source byte."""
    root = Path(repo_root).expanduser().resolve()
    if refresh:
        _collect_source_identity_cached.cache_clear()
    return dict(_collect_source_identity_cached(str(root)))


@lru_cache(maxsize=8)
def _collect_source_identity_cached(repo_root: str) -> dict[str, Any]:
    root = Path(repo_root)
    git = shutil.which("git")
    if git is None:
        return _unavailable_source_identity(root, "git executable is unavailable")

    commit = _git_text(git, root, "rev-parse", "HEAD")
    tree = _git_text(git, root, "rev-parse", "HEAD^{tree}")
    branch = _git_text(git, root, "branch", "--show-current")
    tracked_diff = _git_bytes(
        git,
        root,
        "diff",
        "--binary",
        "--no-ext-diff",
        "HEAD",
        "--",
        *_SOURCE_PATHSPECS,
        *_SOURCE_EXCLUDE_PATHSPECS,
    )
    tracked_raw = _git_bytes(git, root, "ls-files", "-z")
    untracked_raw = _git_bytes(
        git,
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    )
    if (
        not commit
        or not tree
        or tracked_diff is None
        or tracked_raw is None
        or untracked_raw is None
    ):
        return _unavailable_source_identity(root, "git source identity query failed")

    untracked = sorted(
        path
        for path in untracked_raw.split(b"\0")
        if path and _is_included_source_path(path)
    )
    source_paths = sorted(
        {
            path
            for path in (*tracked_raw.split(b"\0"), *untracked)
            if path
            and _is_included_source_path(path)
            and _working_source_path_exists(root, path)
        }
    )
    dirty_digest = _dirty_source_digest(root, tracked_diff, untracked)
    source_content_digest = _source_content_digest(root, source_paths)
    if not dirty_digest or not source_content_digest:
        return _unavailable_source_identity(root, "dirty source hashing failed")
    identity: dict[str, Any] = {
        "version": SOURCE_IDENTITY_VERSION,
        "repo_root": str(root),
        "branch": branch,
        "commit_sha": commit,
        "head_tree_sha": tree,
        "dirty": bool(tracked_diff or untracked),
        "dirty_digest": dirty_digest,
        "source_content_digest": source_content_digest,
        "untracked_source_count": len(untracked),
        "excluded_generated_prefixes": list(_GENERATED_PREFIXES),
        "excluded_local_paths": list(_LOCAL_STATE_PATHS),
        "included_file_policy": _INCLUDED_FILE_POLICY,
        "error": "",
    }
    identity["source_digest"] = source_identity_digest(identity)
    return identity


def source_identity_digest(identity: Mapping[str, Any]) -> str:
    """Bind commit/tree and dirty bytes into one stable evidence identifier."""
    fields = {
        "version": identity.get("version"),
        "repo_root": identity.get("repo_root"),
        "branch": identity.get("branch"),
        "commit_sha": identity.get("commit_sha"),
        "head_tree_sha": identity.get("head_tree_sha"),
        "dirty": identity.get("dirty"),
        "dirty_digest": identity.get("dirty_digest"),
        "source_content_digest": identity.get("source_content_digest"),
        "untracked_source_count": identity.get("untracked_source_count"),
        "excluded_generated_prefixes": identity.get("excluded_generated_prefixes"),
        "excluded_local_paths": identity.get("excluded_local_paths"),
        "included_file_policy": identity.get("included_file_policy"),
    }
    encoded = json.dumps(
        fields,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_source_identity(
    value: object,
    *,
    expected_repo_root: Path,
    refresh: bool,
    current_identity: Mapping[str, Any] | None,
    artifact_name: str,
) -> tuple[bool, str]:
    """Validate provenance, then compare commit-independent source content."""
    identity = value if isinstance(value, Mapping) else {}
    missing = [
        field for field in SOURCE_IDENTITY_REQUIRED_FIELDS if field not in identity
    ]
    if missing:
        return False, f"{artifact_name} source identity is missing fields: {missing}."
    if identity.get("error"):
        return False, f"{artifact_name} source identity failed: {identity['error']}"
    commit = str(identity.get("commit_sha") or "")
    tree = str(identity.get("head_tree_sha") or "")
    dirty_digest = str(identity.get("dirty_digest") or "")
    content_digest = str(identity.get("source_content_digest") or "")
    source_digest = str(identity.get("source_digest") or "")
    if not _HEX_GIT_OBJECT.fullmatch(commit) or not _HEX_GIT_OBJECT.fullmatch(tree):
        return False, f"{artifact_name} source identity has invalid Git objects."
    if not _HEX_SHA256.fullmatch(dirty_digest):
        return False, f"{artifact_name} dirty source digest is invalid."
    if not _HEX_SHA256.fullmatch(content_digest):
        return False, f"{artifact_name} source content digest is invalid."
    if source_identity_digest(identity) != source_digest:
        return False, f"{artifact_name} source identity digest is inconsistent."

    expected_root = expected_repo_root.expanduser().resolve()
    recorded_root = Path(str(identity.get("repo_root") or "")).expanduser().resolve()
    if recorded_root != expected_root:
        return (
            False,
            f"{artifact_name} source identity references the wrong repository.",
        )
    current = (
        dict(current_identity)
        if current_identity is not None
        else collect_source_identity(expected_root, refresh=refresh)
    )
    if current.get("error"):
        return False, f"Current source identity failed: {current['error']}"
    for field in SOURCE_IDENTITY_FRESHNESS_POLICY_FIELDS:
        if identity.get(field) != current.get(field):
            return False, f"{artifact_name} source identity is stale ({field})."
    current_content_digest = str(current.get("source_content_digest") or "")
    if not _HEX_SHA256.fullmatch(current_content_digest):
        return False, "Current source content digest is invalid."
    if content_digest != current_content_digest:
        return (
            False,
            f"{artifact_name} source identity is stale (source_content_digest).",
        )
    return True, ""


def _dirty_source_digest(
    root: Path,
    tracked: bytes,
    untracked: list[bytes],
) -> str:
    digest = hashlib.sha256()
    digest.update(b"xbrainlab-dirty-source-v2\0tracked-diff\0")
    digest.update(tracked)
    digest.update(b"\0untracked-files\0")
    try:
        for raw_path in untracked:
            relative = raw_path.decode("utf-8", errors="surrogateescape")
            path = root / relative
            digest.update(len(raw_path).to_bytes(8, "big"))
            digest.update(raw_path)
            if path.is_symlink():
                digest.update(b"symlink\0")
                digest.update(
                    os.readlink(path).encode("utf-8", errors="surrogateescape")
                )
            elif path.is_file():
                digest.update(b"file\0")
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
            else:
                return ""
    except OSError:
        return ""
    return digest.hexdigest()


def _source_content_digest(root: Path, paths: list[bytes]) -> str:
    """Hash current source bytes independently of branch and commit metadata."""
    digest = hashlib.sha256()
    digest.update(b"xbrainlab-source-content-v2\0")
    try:
        for raw_path in paths:
            relative = raw_path.decode("utf-8", errors="surrogateescape")
            path = root / relative
            digest.update(len(raw_path).to_bytes(8, "big"))
            digest.update(raw_path)
            if path.is_symlink():
                digest.update(b"symlink\0")
                digest.update(
                    os.readlink(path).encode("utf-8", errors="surrogateescape")
                )
            elif path.is_file():
                digest.update(b"file\0")
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
            else:
                return ""
    except OSError:
        return ""
    return digest.hexdigest()


def _is_excluded_source_path(raw_path: bytes) -> bool:
    relative = raw_path.decode("utf-8", errors="surrogateescape").replace("\\", "/")
    return (
        relative.startswith(_GENERATED_PREFIXES)
        or relative in _LOCAL_STATE_PATHS
        or "/__pycache__/" in relative
    )


def _is_included_source_path(raw_path: bytes) -> bool:
    return bool(raw_path) and not _is_excluded_source_path(raw_path)


def _working_source_path_exists(root: Path, raw_path: bytes) -> bool:
    relative = raw_path.decode("utf-8", errors="surrogateescape")
    path = root / relative
    return path.is_file() or path.is_symlink()


def _git_text(git: str, root: Path, *args: str) -> str:
    value = _git_bytes(git, root, *args)
    return value.decode("utf-8", errors="replace").strip() if value is not None else ""


def _git_bytes(git: str, root: Path, *args: str) -> bytes | None:
    try:
        completed = subprocess.run(  # noqa: S603 - resolved executable, no shell.
            [git, *args],
            cwd=root,
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _unavailable_source_identity(root: Path, error: str) -> dict[str, Any]:
    return {
        "version": SOURCE_IDENTITY_VERSION,
        "repo_root": str(root),
        "branch": "",
        "commit_sha": "",
        "head_tree_sha": "",
        "dirty": None,
        "dirty_digest": "",
        "source_content_digest": "",
        "source_digest": "",
        "untracked_source_count": 0,
        "excluded_generated_prefixes": list(_GENERATED_PREFIXES),
        "excluded_local_paths": list(_LOCAL_STATE_PATHS),
        "included_file_policy": _INCLUDED_FILE_POLICY,
        "error": error,
    }
