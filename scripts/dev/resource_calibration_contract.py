"""Pure evidence contract for resource-guard calibration artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

RESOURCE_CALIBRATION_SCHEMA_VERSION = 3
RESOURCE_CALIBRATION_MAX_AGE = timedelta(days=30)
EXPECTED_CALIBRATION_MODELS = ("EEGNet", "SCCNet", "ShallowConvNet")
PROTECTED_LOCAL_CONFIG_PATHS = frozenset({"settings.json"})
CALIBRATION_SOURCE_PATHS = (
    "scripts/dev/calibrate_resource_guard.py",
    "scripts/dev/resource_calibration_contract.py",
    "XBrainLab/backend/application/resource_guard.py",
    "XBrainLab/backend/training/model_holder.py",
    "XBrainLab/backend/training/input_contract.py",
    "XBrainLab/backend/model_base/EEGNet.py",
    "XBrainLab/backend/model_base/SCCNet.py",
    "XBrainLab/backend/model_base/ShallowConvNet.py",
    "pyproject.toml",
    "poetry.lock",
)


def collect_calibration_source_identity(
    repo_root: Path,
    *,
    source_paths: Sequence[str] = CALIBRATION_SOURCE_PATHS,
) -> dict[str, Any]:
    """Return traceability plus a content digest of calibration dependencies."""
    normalized_paths = tuple(str(path) for path in source_paths)
    raw_status_lines = _git_lines(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
    )
    status_available = raw_status_lines is not None
    status_lines = raw_status_lines or []
    dirty_paths = [_status_path(line) for line in status_lines]
    protected_local_changes = sorted(
        path
        for line, path in zip(status_lines, dirty_paths, strict=True)
        if path in PROTECTED_LOCAL_CONFIG_PATHS and not _status_entry_is_staged(line)
    )
    unprotected_dirty_paths = [
        path
        for line, path in zip(status_lines, dirty_paths, strict=True)
        if path not in PROTECTED_LOCAL_CONFIG_PATHS or _status_entry_is_staged(line)
    ]
    relevant_dirty_paths = sorted(
        path for path in unprotected_dirty_paths if path in normalized_paths
    )
    return {
        "branch": _git_value(repo_root, "branch", "--show-current"),
        "commit_sha": _git_value(repo_root, "rev-parse", "HEAD"),
        "tree_sha": _git_value(repo_root, "rev-parse", "HEAD^{tree}"),
        "status_available": status_available,
        "dirty": bool(unprotected_dirty_paths) if status_available else None,
        "dirty_count": len(unprotected_dirty_paths) if status_available else None,
        "relevant_dirty_paths": relevant_dirty_paths,
        "protected_local_changes": protected_local_changes,
        "source_paths": list(normalized_paths),
        "source_digest": calibration_source_digest(
            repo_root,
            normalized_paths,
        ),
    }


def calibration_source_digest(
    repo_root: Path,
    source_paths: Sequence[str] = CALIBRATION_SOURCE_PATHS,
) -> str:
    """Hash current source content without including generated artifacts."""
    digest = hashlib.sha256()
    for relative in sorted(str(path) for path in source_paths):
        encoded_path = relative.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        path = repo_root / relative
        if not path.is_file():
            digest.update(b"missing\0")
            continue
        digest.update(b"file\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def strict_calibration_failure_reasons(
    report: Mapping[str, Any],
    *,
    repo_root: Path | None = None,
    validate_source: bool = False,
    validate_freshness: bool = False,
    now: datetime | None = None,
) -> list[str]:
    """Return every reason an artifact cannot support strict calibration claims."""
    failures: list[str] = []
    if report.get("schema_version") != RESOURCE_CALIBRATION_SCHEMA_VERSION:
        failures.append("resource calibration schema is not the current strict version")

    generated_at = _parse_timestamp(report.get("generated_at_utc"))
    if generated_at is None:
        failures.append("generated_at_utc is missing or invalid")
    elif validate_freshness:
        reference = now or datetime.now(UTC)
        age = reference - generated_at
        if age < timedelta(minutes=-5) or age > RESOURCE_CALIBRATION_MAX_AGE:
            failures.append(
                "resource calibration artifact is outside its freshness window"
            )

    command = report.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) and item for item in command)
    ):
        failures.append("calibration command provenance is missing")

    environment = report.get("environment")
    if not isinstance(environment, Mapping):
        failures.append("calibration runtime environment is missing")
    else:
        for key in (
            "python",
            "torch",
            "torch_cuda",
            "cuda_available",
            "gpu_name",
            "driver_version",
        ):
            if key not in environment or environment.get(key) in {None, ""}:
                failures.append(f"calibration environment is missing {key}")

    identity = report.get("source_identity")
    failures.extend(
        _source_identity_failures(
            identity,
            repo_root=repo_root,
            validate_source=validate_source,
        )
    )

    expected_models = report.get("expected_models")
    if expected_models != list(EXPECTED_CALIBRATION_MODELS):
        failures.append("expected model set is missing or out of canonical order")

    probe = report.get("cuda_probe")
    if not isinstance(probe, Mapping) or probe.get("status") != "measured":
        failures.append("CUDA probe must be measured for strict calibration")
        return failures

    raw_models = probe.get("models")
    model_rows = raw_models if isinstance(raw_models, list) else []
    by_name = {
        str(row.get("model")): row
        for row in model_rows
        if isinstance(row, Mapping) and row.get("model")
    }
    model_names = [
        str(row.get("model"))
        for row in model_rows
        if isinstance(row, Mapping) and row.get("model")
    ]
    if len(model_names) != len(set(model_names)):
        failures.append("CUDA calibration contains duplicate model rows")
    missing = [name for name in EXPECTED_CALIBRATION_MODELS if name not in by_name]
    unexpected = sorted(set(by_name) - set(EXPECTED_CALIBRATION_MODELS))
    if missing:
        failures.append(
            "required calibration models are missing: " + ", ".join(missing)
        )
    if unexpected:
        failures.append(
            "unexpected calibration models are present: " + ", ".join(unexpected)
        )
    for model_name in EXPECTED_CALIBRATION_MODELS:
        row = by_name.get(model_name)
        if row is None:
            continue
        if row.get("status") != "measured":
            failures.append(f"{model_name} must be measured in strict calibration")
        elif row.get("estimate_covers_observed_peak") is not True:
            failures.append(f"{model_name} estimate underestimates the observed peak")
    if probe.get("all_estimates_cover_observed_peak") is not True:
        failures.append("not all resource estimates cover their observed peak")
    return failures


def _source_identity_failures(
    identity: Any,
    *,
    repo_root: Path | None,
    validate_source: bool,
) -> list[str]:
    if not isinstance(identity, Mapping):
        return ["calibration source identity is missing"]
    failures: list[str] = []
    if identity.get("status_available") is not True:
        failures.append("calibration source git status is unavailable")
    source_paths = identity.get("source_paths")
    if source_paths != list(CALIBRATION_SOURCE_PATHS):
        failures.append("calibration source path set is incomplete")
    for key, length in (("commit_sha", 40), ("tree_sha", 40), ("source_digest", 64)):
        value = str(identity.get(key) or "")
        if len(value) != length or any(
            char not in "0123456789abcdef" for char in value
        ):
            failures.append(f"calibration source identity has invalid {key}")
    if validate_source:
        if repo_root is None:
            failures.append("repo_root is required for source freshness validation")
        else:
            recorded_branch = identity.get("branch")
            if not isinstance(recorded_branch, str) or not recorded_branch.strip():
                failures.append("calibration source branch is missing")
            current_identity = collect_calibration_source_identity(
                repo_root,
                source_paths=CALIBRATION_SOURCE_PATHS,
            )
            current_branch = current_identity.get("branch")
            if not isinstance(current_branch, str) or not current_branch.strip():
                failures.append("current calibration source branch is unavailable")
            exact_fields = (
                "branch",
                "commit_sha",
                "tree_sha",
                "status_available",
                "dirty",
                "dirty_count",
                "relevant_dirty_paths",
                "protected_local_changes",
                "source_digest",
            )
            for key in exact_fields:
                if identity.get(key) != current_identity.get(key):
                    label = "digest" if key == "source_digest" else key
                    failures.append(f"calibration source {label} is stale")

            if (
                identity.get("dirty") is not False
                or identity.get("dirty_count") != 0
                or identity.get("relevant_dirty_paths") != []
            ):
                failures.append(
                    "exact-source calibration was recorded from a dirty worktree"
                )
            if (
                current_identity.get("dirty") is not False
                or current_identity.get("dirty_count") != 0
                or current_identity.get("relevant_dirty_paths") != []
            ):
                failures.append(
                    "exact-source calibration is being checked from a dirty worktree"
                )
    return failures


def _parse_timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _git_value(repo_root: Path, *args: str) -> str:
    git = shutil.which("git")
    if git is None:
        return ""
    try:
        completed = subprocess.run(  # noqa: S603 - resolved executable, no shell.
            [git, *args],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _git_lines(repo_root: Path, *args: str) -> list[str] | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        completed = subprocess.run(  # noqa: S603 - resolved executable, no shell.
            [git, *args],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.rstrip("\r\n").splitlines()


def _status_path(line: str) -> str:
    value = line[3:] if len(line) > 3 else line
    if " -> " in value:
        value = value.rsplit(" -> ", maxsplit=1)[-1]
    try:
        decoded = json.loads(value) if value.startswith('"') else value
    except json.JSONDecodeError:
        decoded = value
    return str(decoded)


def _status_entry_is_staged(line: str) -> bool:
    return bool(line) and line[0] not in {" ", "?"}
