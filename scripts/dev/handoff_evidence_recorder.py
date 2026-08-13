#!/usr/bin/env python3
"""Run and record one exact-source XBrainLab handoff gate command."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
)
from scripts.dev.handoff_gate_spec import (
    HANDOFF_GATE_SPECS,
    MOABB_DELIVERY_DOSSIER_REVALIDATION,
    MODEL_CACHE_DIR_TOKEN,
    RAG_CACHE_DIR_TOKEN,
    GateSpec,
)
from scripts.dev.owned_process_group import spawn_owned_process, terminate_and_collect
from scripts.dev.pytest_completion_attestation import COUNT_NAMES, validate_attestation
from scripts.dev.pytest_terminal_summary import parse_terminal_outcomes
from scripts.dev.sensitive_path_redaction import (
    contains_sensitive_path as _contains_sensitive_path,
)
from scripts.dev.sensitive_path_redaction import (
    redact_sensitive_text as _redact_sensitive_text,
)

ROOT = Path(__file__).resolve().parents[2]
DOSSIER_NAME = "handoff-evidence.json"
SCHEMA_VERSION = 7
DEFAULT_BRANCH = "main"
_PROTECTED_LOCAL_PATHS = frozenset({"settings.json"})
_SANITIZED_INHERITED_ENVIRONMENT = (
    "COVERAGE_PROCESS_START",
    "PYTEST_ADDOPTS",
    "PYTEST_PLUGINS",
    "PYTHONBREAKPOINT",
    "PYTHONHOME",
    "PYTHONINSPECT",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "XBRAINLAB_MODEL_CACHE_DIR",
    "XBRAINLAB_RAG_CACHE_DIR",
)
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")


class HandoffEvidenceError(RuntimeError):
    """Raised when a command cannot enter the exact-source evidence boundary."""


def record_handoff_command(
    *,
    repo_root: Path,
    evidence_root: Path,
    section: str,
    check_id: str,
    command: Sequence[str],
    timeout_seconds: float,
    expected_branch: str = DEFAULT_BRANCH,
    require_upstream: bool = True,
    enforce_pytest_outcomes: bool | None = None,
    stdout_artifact: str | None = None,
    model_cache_dir: Path | None = None,
    rag_cache_dir: Path | None = None,
    allow_external_evidence_root: bool = False,
) -> dict[str, Any]:
    """Execute one gate and atomically append its exact-source evidence."""
    root = repo_root.expanduser().resolve(strict=True)
    check_name = _validated_id(check_id, field="check id")
    section_name = _validated_id(str(section), field="section")
    spec = _registered_gate(check_name)
    if section_name != spec.section:
        raise HandoffEvidenceError(
            f"Gate {check_name!r} must use registered section {spec.section!r}."
        )
    argv = tuple(str(part) for part in command)
    if not argv or not argv[0]:
        raise HandoffEvidenceError("A non-empty command is required.")
    if float(timeout_seconds) != spec.timeout_seconds:
        raise HandoffEvidenceError(
            f"Gate {check_name!r} must use its registered timeout of "
            f"{spec.timeout_seconds:g}s."
        )
    if enforce_pytest_outcomes is not None and enforce_pytest_outcomes != (
        spec.outcome.require_pytest_attestation
    ):
        raise HandoffEvidenceError(
            "Pytest outcome enforcement is controlled by the registered gate spec."
        )
    if stdout_artifact is not None and stdout_artifact != spec.stdout_artifact_path:
        raise HandoffEvidenceError(
            "Stdout artifact registration is controlled by the registered gate spec."
        )

    checkout = _checkout_identity(
        root,
        expected_branch=expected_branch,
        require_upstream=require_upstream,
    )
    output_root, evidence_root_policy = _validated_evidence_root(
        evidence_root,
        repo_root=root,
        commit_sha=str(checkout["commit_sha"]),
        allow_external=allow_external_evidence_root,
    )
    expected_argv = spec.resolve_argv(output_root)
    if argv != expected_argv:
        raise HandoffEvidenceError(
            f"Gate {check_name!r} argv does not match its exact registered argv."
        )
    _require_disjoint_preserved_inputs(spec)
    output_root.mkdir(parents=True, exist_ok=True)
    logs_dir = output_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    preserved_input_before = _preserved_input_records(output_root, spec=spec)
    _prepare_registered_artifacts(output_root, spec=spec)

    source_before = collect_source_identity(root, refresh=True)
    _require_clean_source(source_before)
    required_environment = _resolved_required_environment(
        spec,
        model_cache_dir=model_cache_dir,
        rag_cache_dir=rag_cache_dir,
    )
    recorded_environment = _recorded_environment(spec, required_environment)
    execution_environment = os.environ.copy()
    for name in _SANITIZED_INHERITED_ENVIRONMENT:
        execution_environment.pop(name, None)
    execution_environment.update(required_environment)
    started_at = datetime.now(UTC)
    started = time.monotonic()
    return_code, stdout, stderr, timed_out = _run_bounded_command(
        argv,
        cwd=root,
        timeout_seconds=float(timeout_seconds),
        environment=execution_environment,
    )
    if timed_out:
        stderr += (
            f"\nCommand exceeded the recorder timeout of {timeout_seconds:.3f}s.\n"
        )
    redactions = _sensitive_environment_redactions(spec, required_environment)
    stdout = _redact_sensitive_text(stdout, redactions)
    stderr = _redact_sensitive_text(stderr, redactions)
    duration_seconds = round(time.monotonic() - started, 3)

    stem = f"section-{section_name}-{check_name}"
    stdout_path = logs_dir / f"{stem}.stdout.log"
    stderr_path = logs_dir / f"{stem}.stderr.log"
    _write_text_exact(stdout_path, stdout)
    _write_text_exact(stderr_path, stderr)
    if spec.stdout_artifact_path:
        artifact_path = _contained_output_path(
            output_root,
            spec.stdout_artifact_path,
        )
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        _write_text_exact(artifact_path, stdout)
    _redact_registered_text_artifacts(
        output_root,
        spec=spec,
        redactions=redactions,
    )
    preserved_input_after: tuple[dict[str, Any], ...] = ()
    preserved_input_failure = ""
    try:
        preserved_input_after = _preserved_input_records(output_root, spec=spec)
    except HandoffEvidenceError as error:
        preserved_input_failure = f"Preserved input changed during validation: {error}"
    if not preserved_input_failure and preserved_input_before != preserved_input_after:
        preserved_input_failure = "Preserved input changed during validation."

    source_after = collect_source_identity(root, refresh=True)
    source_stable = bool(source_before.get("source_digest")) and (
        source_before == source_after
    )
    pytest_attestation, pytest_attestation_failure = _validated_pytest_attestation(
        output_root,
        spec=spec,
        return_code=return_code,
    )
    pytest_outcomes = _pytest_outcomes_from_evidence(
        spec,
        pytest_attestation,
        output=f"{stdout}\n{stderr}",
    )
    artifact_records, artifact_failures = _collect_registered_artifacts(
        output_root,
        spec=spec,
    )
    if preserved_input_failure:
        artifact_failures.append(preserved_input_failure)
    failure_reasons = _derive_failure_reasons(
        spec=spec,
        timed_out=timed_out,
        return_code=return_code,
        source_stable=source_stable,
        pytest_outcomes=pytest_outcomes,
        pytest_attestation_failure=pytest_attestation_failure,
        artifact_failures=artifact_failures,
    )

    record: dict[str, Any] = {
        "section": section_name,
        "check_id": check_name,
        "command": list(argv),
        "started_at": started_at.isoformat(),
        "duration_seconds": duration_seconds,
        "timeout_seconds": float(timeout_seconds),
        "environment": recorded_environment,
        "sanitized_environment_names": list(_SANITIZED_INHERITED_ENVIRONMENT),
        "outcome_policy": _outcome_policy_record(spec),
        "artifact_policy": _artifact_policy_record(spec),
        "timed_out": timed_out,
        "return_code": return_code,
        "passed": not failure_reasons,
        "failure_reason": " ".join(failure_reasons),
        "source_stable": bool(source_stable),
        "source_before": source_before,
        "source_after": source_after,
        "protected_dirty_paths": list(checkout["protected_dirty_paths"]),
        "pytest_attestation_enforced": spec.outcome.require_pytest_attestation,
        "pytest_outcomes": pytest_outcomes,
        "pytest_completion_attestation": pytest_attestation,
        "artifacts": artifact_records,
        "preserved_input_stable": not preserved_input_failure,
        "preserved_input_before": list(preserved_input_before),
        "preserved_input_after": list(preserved_input_after),
        "stdout_log": _file_record(stdout_path, root=output_root),
        "stderr_log": _file_record(stderr_path, root=output_root),
        "stdout_tail": stdout[-4_000:],
        "stderr_tail": stderr[-4_000:],
    }
    if spec.stdout_artifact_path:
        record["stdout_artifact"] = _file_record(
            _contained_output_path(output_root, spec.stdout_artifact_path),
            root=output_root,
        )
    _update_dossier(
        output_root,
        checkout=checkout,
        evidence_root_policy=evidence_root_policy,
        source_identity=source_before,
        record=record,
    )
    return record


def validate_handoff_dossier(
    *,
    repo_root: Path,
    evidence_root: Path,
    required_check_ids: Sequence[str],
    expected_branch: str = DEFAULT_BRANCH,
    require_upstream: bool = True,
    model_cache_dir: Path | None = None,
    rag_cache_dir: Path | None = None,
    allow_external_evidence_root: bool = False,
) -> tuple[bool, str]:
    """Validate one complete dossier against the current clean checkout."""
    try:
        required = _validated_required_check_ids(required_check_ids)
        root = repo_root.expanduser().resolve(strict=True)
        checkout = _checkout_identity(
            root,
            expected_branch=expected_branch,
            require_upstream=require_upstream,
        )
        output_root, evidence_root_policy = _validated_evidence_root(
            evidence_root,
            repo_root=root,
            commit_sha=str(checkout["commit_sha"]),
            allow_external=allow_external_evidence_root,
        )
        dossier_path = output_root / DOSSIER_NAME
        payload = json.loads(dossier_path.read_text(encoding="utf-8"))
    except (HandoffEvidenceError, OSError, ValueError, json.JSONDecodeError) as error:
        return False, str(error)

    if payload.get("schema_version") != SCHEMA_VERSION:
        return False, "Handoff dossier schema is unsupported."
    if payload.get("profile") != "handoff":
        return False, "Handoff dossier profile is invalid."
    if payload.get("evidence_root_policy") != evidence_root_policy:
        return False, "Handoff dossier evidence-root policy is stale."
    recorded_checkout = payload.get("checkout")
    if not isinstance(recorded_checkout, dict):
        return False, "Handoff dossier checkout identity is missing."
    for key in (
        "worktree",
        "branch",
        "commit_sha",
        "head_tree_sha",
        "upstream",
        "protected_dirty_paths",
    ):
        if recorded_checkout.get(key) != checkout.get(key):
            return False, f"Handoff dossier checkout is stale ({key})."

    current_source = collect_source_identity(root, refresh=True)
    try:
        _require_clean_source(current_source)
    except HandoffEvidenceError as error:
        return False, str(error)
    source_identity = payload.get("source_identity")
    if not isinstance(source_identity, dict) or source_identity != current_source:
        return False, "Handoff dossier source identity is stale."

    checks = payload.get("checks")
    if not isinstance(checks, dict):
        return False, "Handoff dossier contains no command checks."
    unregistered = sorted(set(checks).difference(HANDOFF_GATE_SPECS))
    if unregistered:
        return False, f"Handoff dossier contains unregistered checks: {unregistered}."
    execution_order = payload.get("execution_order")
    expected_execution_order = [
        check_id for check_id in HANDOFF_GATE_SPECS if check_id in checks
    ]
    if execution_order != expected_execution_order:
        return False, "Handoff dossier execution order is missing, stale, or edited."
    missing = [check_id for check_id in required if check_id not in checks]
    if missing:
        return False, f"Handoff dossier is missing required checks: {missing}."
    for check_id in required:
        ok, reason = _validate_check_record(
            output_root=output_root,
            checkout=checkout,
            current_source=current_source,
            check_id=check_id,
            raw_record=checks.get(check_id),
            model_cache_dir=model_cache_dir,
            rag_cache_dir=rag_cache_dir,
        )
        if not ok:
            return False, reason
    for check_id in required:
        spec = _registered_gate(check_id)
        dossier_revalidation_error = _dossier_revalidation_error(
            repo_root=root,
            output_root=output_root,
            spec=spec,
        )
        if dossier_revalidation_error is not None:
            return False, f"{check_id} {dossier_revalidation_error}"
    return True, ""


def _validate_check_record(
    *,
    output_root: Path,
    checkout: dict[str, Any],
    current_source: dict[str, Any],
    check_id: str,
    raw_record: object,
    model_cache_dir: Path | None,
    rag_cache_dir: Path | None,
) -> tuple[bool, str]:
    if not isinstance(raw_record, dict):
        return False, f"Handoff check record is malformed: {check_id}."
    spec = _registered_gate(check_id)
    if raw_record.get("check_id") != check_id:
        return False, f"Handoff check id was edited: {check_id}."
    if raw_record.get("section") != spec.section:
        return False, f"Handoff check section was edited: {check_id}."
    if raw_record.get("command") != list(spec.resolve_argv(output_root)):
        return False, f"Handoff check argv was edited: {check_id}."
    timeout_seconds = raw_record.get("timeout_seconds")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or float(timeout_seconds) != spec.timeout_seconds
    ):
        return False, f"Handoff check timeout was edited: {check_id}."
    try:
        required_environment = _resolved_required_environment(
            spec,
            model_cache_dir=model_cache_dir,
            rag_cache_dir=rag_cache_dir,
        )
    except HandoffEvidenceError as error:
        return False, str(error)
    redactions = _sensitive_environment_redactions(spec, required_environment)
    sensitive_redactions = redactions
    if raw_record.get("environment") != _recorded_environment(
        spec,
        required_environment,
    ):
        return False, f"Handoff check environment policy was edited: {check_id}."
    if _contains_sensitive_path(json.dumps(raw_record), sensitive_redactions):
        return False, f"Handoff check contains a sensitive cache path: {check_id}."
    if raw_record.get("sanitized_environment_names") != list(
        _SANITIZED_INHERITED_ENVIRONMENT
    ):
        return False, f"Handoff check sanitized environment was edited: {check_id}."
    if raw_record.get("outcome_policy") != _outcome_policy_record(spec):
        return False, f"Handoff check outcome policy was edited: {check_id}."
    if raw_record.get("artifact_policy") != _artifact_policy_record(spec):
        return False, f"Handoff check artifact policy was edited: {check_id}."
    if raw_record.get("pytest_attestation_enforced") is not (
        spec.outcome.require_pytest_attestation
    ):
        return False, f"Handoff check pytest policy was edited: {check_id}."
    if raw_record.get("protected_dirty_paths") != checkout.get("protected_dirty_paths"):
        return False, f"Handoff check protected paths were edited: {check_id}."

    source_before = raw_record.get("source_before")
    source_after = raw_record.get("source_after")
    computed_source_stable = (
        isinstance(source_before, dict)
        and isinstance(source_after, dict)
        and bool(source_before.get("source_digest"))
        and source_before == source_after
    )
    if raw_record.get("source_stable") is not computed_source_stable:
        return False, f"Handoff check source_stable summary was edited: {check_id}."
    if source_before != current_source or source_after != current_source:
        return False, f"Handoff check source is stale: {check_id}."

    stdout_ok, stdout_reason, stdout_content = _validate_file_record(
        output_root,
        raw_record.get("stdout_log"),
        expected_relative_path=(f"logs/section-{spec.section}-{check_id}.stdout.log"),
    )
    if not stdout_ok:
        return False, f"{check_id} {stdout_reason}"
    stderr_ok, stderr_reason, stderr_content = _validate_file_record(
        output_root,
        raw_record.get("stderr_log"),
        expected_relative_path=(f"logs/section-{spec.section}-{check_id}.stderr.log"),
    )
    if not stderr_ok:
        return False, f"{check_id} {stderr_reason}"
    stdout = stdout_content.decode("utf-8", errors="replace")
    stderr = stderr_content.decode("utf-8", errors="replace")
    if _contains_sensitive_path(
        stdout, sensitive_redactions
    ) or _contains_sensitive_path(
        stderr,
        sensitive_redactions,
    ):
        return False, f"Handoff check log contains a sensitive cache path: {check_id}."
    if raw_record.get("stdout_tail") != stdout[-4_000:]:
        return False, f"Handoff check stdout tail was edited: {check_id}."
    if raw_record.get("stderr_tail") != stderr[-4_000:]:
        return False, f"Handoff check stderr tail was edited: {check_id}."

    timed_out = raw_record.get("timed_out")
    return_code = raw_record.get("return_code")
    if not isinstance(timed_out, bool):
        return False, f"Handoff check timeout outcome is malformed: {check_id}."
    if isinstance(return_code, bool) or not isinstance(return_code, int):
        return False, f"Handoff check return code is malformed: {check_id}."
    if timed_out and return_code != 124:
        return False, f"Handoff check timeout outcome is inconsistent: {check_id}."
    pytest_attestation, pytest_attestation_failure = _validated_pytest_attestation(
        output_root,
        spec=spec,
        return_code=return_code,
    )
    if raw_record.get("pytest_completion_attestation") != pytest_attestation:
        return False, f"Handoff check pytest attestation was edited: {check_id}."
    pytest_outcomes = _pytest_outcomes_from_evidence(
        spec,
        pytest_attestation,
        output=f"{stdout}\n{stderr}",
    )
    if raw_record.get("pytest_outcomes") != pytest_outcomes:
        return False, f"Handoff check pytest summary was edited: {check_id}."
    artifacts_ok, artifacts_reason = _validate_registered_artifacts(
        output_root,
        spec=spec,
        raw_records=raw_record.get("artifacts"),
        sensitive_redactions=sensitive_redactions,
    )
    if not artifacts_ok:
        return False, f"{check_id} {artifacts_reason}"
    try:
        current_preserved_inputs = list(
            _preserved_input_records(output_root, spec=spec)
        )
    except HandoffEvidenceError as error:
        return False, f"{check_id} preserved input is invalid: {error}"
    preserved_before = raw_record.get("preserved_input_before")
    preserved_after = raw_record.get("preserved_input_after")
    if not isinstance(preserved_before, list) or not isinstance(preserved_after, list):
        return False, f"Handoff check preserved input identity is missing: {check_id}."
    if preserved_after != current_preserved_inputs:
        return False, f"Handoff check preserved input is stale: {check_id}."
    preserved_input_stable = preserved_before == preserved_after
    if raw_record.get("preserved_input_stable") is not preserved_input_stable:
        return False, f"Handoff check preserved input summary was edited: {check_id}."
    if spec.stdout_artifact_path:
        stdout_artifact_ok, stdout_artifact_reason, _content = _validate_file_record(
            output_root,
            raw_record.get("stdout_artifact"),
            expected_relative_path=spec.stdout_artifact_path,
        )
        if not stdout_artifact_ok:
            return False, f"{check_id} {stdout_artifact_reason}"
        if _contains_sensitive_path(
            _content.decode("utf-8", errors="replace"),
            sensitive_redactions,
        ):
            return (
                False,
                f"{check_id} stdout artifact contains a sensitive cache path.",
            )
    elif "stdout_artifact" in raw_record:
        return (
            False,
            f"Handoff check registered an unexpected stdout artifact: {check_id}.",
        )

    preserved_input_failures = (
        ()
        if preserved_input_stable
        else ("Preserved input changed during validation.",)
    )
    failure_reasons = _derive_failure_reasons(
        spec=spec,
        timed_out=timed_out,
        return_code=return_code,
        source_stable=computed_source_stable,
        pytest_outcomes=pytest_outcomes,
        pytest_attestation_failure=pytest_attestation_failure,
        artifact_failures=preserved_input_failures,
    )
    expected_failure_reason = " ".join(failure_reasons)
    computed_passed = not failure_reasons
    if raw_record.get("passed") is not computed_passed:
        return False, f"Handoff check passed summary was edited: {check_id}."
    if raw_record.get("failure_reason") != expected_failure_reason:
        return False, f"Handoff check failure summary was edited: {check_id}."
    if not computed_passed:
        return (
            False,
            f"Handoff check did not pass: {check_id}. {expected_failure_reason}",
        )
    return True, ""


def _checkout_identity(
    root: Path,
    *,
    expected_branch: str,
    require_upstream: bool,
) -> dict[str, Any]:
    branch = _git(root, "branch", "--show-current")
    commit = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    if branch != expected_branch:
        raise HandoffEvidenceError(
            f"Expected branch {expected_branch!r}, found {branch!r}."
        )
    dirty_paths, protected_paths = _dirty_paths(root)
    if dirty_paths:
        raise HandoffEvidenceError(
            "Handoff evidence refuses dirty product source: " + ", ".join(dirty_paths)
        )
    upstream = ""
    if require_upstream:
        upstream = _git(root, "rev-parse", "--abbrev-ref", "@{upstream}")
        upstream_commit = _git(root, "rev-parse", "@{upstream}")
        divergence = _git(
            root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}"
        )
        if upstream_commit != commit or divergence.split() != ["0", "0"]:
            raise HandoffEvidenceError(
                "Handoff evidence requires HEAD to equal its configured upstream."
            )
    return {
        "worktree": str(root),
        "branch": branch,
        "commit_sha": commit,
        "head_tree_sha": tree,
        "upstream": upstream,
        "protected_dirty_paths": protected_paths,
    }


def _dirty_paths(root: Path) -> tuple[list[str], list[str]]:
    status = _git_raw(root, "status", "--porcelain=v1", "--untracked-files=all")
    dirty: set[str] = set()
    protected: set[str] = set()
    for line in status.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", maxsplit=1)[1]
        staged = bool(line) and line[0] not in {" ", "?"}
        target = protected if path in _PROTECTED_LOCAL_PATHS and not staged else dirty
        if path:
            target.add(path)
    settings_path = root / "settings.json"
    if settings_path.exists() and not _git_path_is_tracked(root, "settings.json"):
        protected.add("settings.json")
    return sorted(dirty), sorted(protected)


def _git_path_is_tracked(root: Path, path: str) -> bool:
    git = shutil.which("git")
    if git is None:
        raise HandoffEvidenceError("git executable is unavailable.")
    completed = subprocess.run(  # noqa: S603 - fixed git query.
        [git, "ls-files", "--error-unmatch", "--", path],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.returncode == 0


def _git(root: Path, *args: str) -> str:
    return _git_raw(root, *args).strip()


def _git_raw(root: Path, *args: str) -> str:
    """Return Git output without corrupting porcelain's leading status column."""
    git = shutil.which("git")
    if git is None:
        raise HandoffEvidenceError("git executable is unavailable.")
    try:
        completed = subprocess.run(  # noqa: S603 - resolved git, fixed query args.
            [git, *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HandoffEvidenceError(f"git query failed: {args!r}") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise HandoffEvidenceError(f"git query failed: {detail}")
    return completed.stdout.rstrip("\r\n")


def _require_clean_source(identity: dict[str, Any]) -> None:
    if identity.get("error"):
        raise HandoffEvidenceError(str(identity["error"]))
    if identity.get("dirty") is not False:
        raise HandoffEvidenceError("Handoff evidence requires clean source identity.")


def _validated_evidence_root(
    path: Path,
    *,
    repo_root: Path,
    commit_sha: str,
    allow_external: bool,
) -> tuple[Path, dict[str, str]]:
    expanded = path.expanduser()
    absolute = expanded if expanded.is_absolute() else repo_root / expanded
    resolved = absolute.resolve()
    if commit_sha not in resolved.parts:
        raise HandoffEvidenceError(
            "Evidence root must include the full candidate commit SHA as a path segment."
        )
    try:
        relative = resolved.relative_to(repo_root)
    except ValueError:
        if not expanded.is_absolute():
            raise HandoffEvidenceError(
                "External evidence root must be an absolute path."
            ) from None
        if not allow_external:
            raise HandoffEvidenceError(
                "External evidence root requires explicit opt-in."
            ) from None
        return resolved, {
            "kind": "external",
            "path_sha256": hashlib.sha256(str(resolved).encode()).hexdigest(),
        }

    if not _git_path_is_ignored(repo_root, relative / ".gitignore-probe"):
        raise HandoffEvidenceError("Repo-contained evidence root must be git-ignored.")
    return resolved, {
        "kind": "repo-ignored",
        "relative_path": relative.as_posix(),
    }


def _git_path_is_ignored(root: Path, path: Path) -> bool:
    git = shutil.which("git")
    if git is None:
        raise HandoffEvidenceError("git executable is unavailable.")
    completed = subprocess.run(  # noqa: S603 - fixed git query.
        [git, "check-ignore", "--quiet", "--", path.as_posix()],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode not in {0, 1}:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise HandoffEvidenceError(f"git check-ignore failed: {detail}")
    return completed.returncode == 0


def _resolved_required_environment(
    spec: GateSpec,
    *,
    model_cache_dir: Path | None,
    rag_cache_dir: Path | None,
) -> dict[str, str]:
    replacements = {
        MODEL_CACHE_DIR_TOKEN: _optional_d_cache_path(
            model_cache_dir,
            flag="--model-cache-dir",
            required=MODEL_CACHE_DIR_TOKEN in spec.environment.as_dict().values(),
        ),
        RAG_CACHE_DIR_TOKEN: _optional_d_cache_path(
            rag_cache_dir,
            flag="--rag-cache-dir",
            required=RAG_CACHE_DIR_TOKEN in spec.environment.as_dict().values(),
        ),
    }
    resolved: dict[str, str] = {}
    for name, value in spec.environment.required:
        replacement = replacements.get(value)
        resolved[name] = str(replacement) if replacement is not None else value
    return resolved


def _optional_d_cache_path(
    path: Path | None,
    *,
    flag: str,
    required: bool,
) -> Path | None:
    if path is None:
        if required:
            raise HandoffEvidenceError(f"Registered gate requires {flag}.")
        return None
    expanded = path.expanduser()
    if not expanded.is_absolute():
        raise HandoffEvidenceError(f"{flag} must be an absolute D-mounted path.")
    resolved = expanded.resolve(strict=False)
    if os.name == "nt":
        on_d_drive = resolved.drive.casefold() == "d:"
    else:
        try:
            relative = resolved.relative_to(Path("/mnt/d").resolve(strict=False))
        except ValueError:
            on_d_drive = False
        else:
            on_d_drive = bool(relative.parts)
    if not on_d_drive:
        raise HandoffEvidenceError(f"{flag} must be an absolute D-mounted path.")
    return resolved


def _recorded_environment(
    spec: GateSpec,
    required_environment: dict[str, str],
) -> dict[str, object]:
    recorded: dict[str, object] = dict(required_environment)
    for name in spec.environment.redacted_path_names:
        path = Path(required_environment[name])
        recorded[name] = {
            "mount": "D:" if os.name == "nt" else "/mnt/d",
            "path_sha256": hashlib.sha256(str(path).encode()).hexdigest(),
            "redacted": True,
        }
    return recorded


def _sensitive_environment_redactions(
    spec: GateSpec,
    required_environment: dict[str, str],
) -> dict[str, str]:
    redactions: dict[str, str] = {}
    for name in spec.environment.redacted_path_names:
        value = required_environment.get(name)
        if not value:
            continue
        marker = f"<redacted:{name}>"
        redactions[value] = marker
    return redactions


_TEXT_EVIDENCE_SUFFIXES = frozenset(
    {".csv", ".json", ".jsonl", ".log", ".md", ".txt", ".tsv", ".yaml", ".yml"}
)


def _registered_text_files(root: Path, *, spec: GateSpec) -> list[Path]:
    files: list[Path] = []
    preserved = set(spec.preserved_input_artifact_paths)
    for relative_path in spec.required_artifact_paths:
        if relative_path in preserved:
            continue
        path = _contained_output_path(root, relative_path)
        candidates = [path] if path.is_file() else list(path.rglob("*"))
        files.extend(
            candidate
            for candidate in candidates
            if candidate.is_file()
            and candidate.suffix.casefold() in _TEXT_EVIDENCE_SUFFIXES
        )
    return files


def _redact_registered_text_artifacts(
    root: Path,
    *,
    spec: GateSpec,
    redactions: dict[str, str],
) -> None:
    if not redactions:
        return
    for path in _registered_text_files(root, spec=spec):
        try:
            original = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise HandoffEvidenceError(
                f"Could not inspect textual evidence artifact {path.name!r}."
            ) from error
        redacted = _redact_sensitive_text(original, redactions)
        if redacted != original:
            _write_text_exact(path, redacted)


def _write_text_exact(path: Path, content: str) -> None:
    """Write evidence text without platform newline translation."""
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(content)


def _contained_output_path(root: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute():
        raise HandoffEvidenceError("Evidence artifact path must be relative.")
    candidate = root / relative
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise HandoffEvidenceError(
            "Evidence artifact escapes its output root."
        ) from error
    cursor = root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise HandoffEvidenceError("Evidence artifact path contains a symlink.")
    return candidate


def _validated_id(value: str, *, field: str) -> str:
    normalized = str(value).strip().casefold()
    if not _SAFE_ID.fullmatch(normalized):
        raise HandoffEvidenceError(f"Invalid {field}: {value!r}.")
    return normalized


def _registered_gate(check_id: str) -> GateSpec:
    spec = HANDOFF_GATE_SPECS.get(check_id)
    if spec is None:
        raise HandoffEvidenceError(
            f"Check {check_id!r} is not a registered handoff gate."
        )
    return spec


def _validated_required_check_ids(values: Sequence[str]) -> tuple[str, ...]:
    required = tuple(_validated_id(item, field="required check id") for item in values)
    if not required:
        raise HandoffEvidenceError(
            "At least one required handoff check must be specified."
        )
    if len(required) != len(set(required)):
        raise HandoffEvidenceError("Required handoff checks must be unique.")
    for check_id in required:
        _registered_gate(check_id)
    return required


def _outcome_policy_record(spec: GateSpec) -> dict[str, Any]:
    return {
        "allowed_return_codes": list(spec.outcome.allowed_return_codes),
        "require_pytest_attestation": spec.outcome.require_pytest_attestation,
        "forbidden_pytest_outcomes": list(spec.outcome.forbidden_pytest_outcomes),
    }


def _artifact_policy_record(spec: GateSpec) -> dict[str, Any]:
    return {
        "required_paths": list(spec.required_artifact_paths),
        "preserved_input_paths": list(spec.preserved_input_artifact_paths),
        "pytest_attestation_path": spec.pytest_attestation_path,
        "dossier_revalidation": spec.dossier_revalidation,
    }


def _dossier_revalidation_error(
    *,
    repo_root: Path,
    output_root: Path,
    spec: GateSpec,
) -> str | None:
    if spec.dossier_revalidation is None:
        return None
    if spec.dossier_revalidation != MOABB_DELIVERY_DOSSIER_REVALIDATION:
        return "registered an unsupported final dossier revalidation."
    try:
        argv = spec.resolve_argv(output_root)
        plan_path = _registered_revalidation_path(argv, "--plan", base=repo_root)
        plan_path.relative_to(repo_root.resolve())
        evidence_root = _registered_revalidation_path(
            argv,
            "--evidence-root",
            base=repo_root,
        )
        evidence_root.relative_to(output_root.resolve())
        result_path = _registered_revalidation_path(
            argv,
            "--output",
            base=repo_root,
        )
        result_path.relative_to(output_root.resolve())
        recorded_result = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(recorded_result, dict):
            return "MOABB delivery final dossier revalidation could not complete."
        current_result = _load_current_moabb_delivery_validation(
            plan_path=plan_path,
            evidence_root=evidence_root,
        )
    except Exception:  # fail closed around external files and native probes
        return "MOABB delivery final dossier revalidation could not complete."
    if current_result.get("delivery_allowed") is not True:
        return "MOABB delivery evidence no longer passes final dossier revalidation."
    if current_result != recorded_result:
        return (
            "MOABB delivery evidence changed after its gate; final dossier "
            "revalidation failed."
        )
    return None


def _registered_revalidation_path(
    argv: Sequence[str],
    option: str,
    *,
    base: Path,
) -> Path:
    positions = [index for index, value in enumerate(argv) if value == option]
    if len(positions) != 1 or positions[0] + 1 >= len(argv):
        raise ValueError(f"registered dossier option is invalid: {option}")
    path = Path(argv[positions[0] + 1]).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve(strict=True)


def _load_current_moabb_delivery_validation(
    *,
    plan_path: Path,
    evidence_root: Path,
) -> dict[str, Any]:
    from scripts.dev.validate_moabb_gui_campaign_delivery import (
        validate_delivery_evidence,
    )

    return validate_delivery_evidence(
        plan_path=plan_path,
        evidence_root=evidence_root,
    )


def _derive_failure_reasons(
    *,
    spec: GateSpec,
    timed_out: bool,
    return_code: int,
    source_stable: bool,
    pytest_outcomes: dict[str, int],
    pytest_attestation_failure: str | None,
    artifact_failures: Sequence[str],
) -> list[str]:
    failure_reasons: list[str] = []
    if timed_out:
        failure_reasons.append("Command timed out.")
    elif return_code not in spec.outcome.allowed_return_codes:
        failure_reasons.append(f"Command exited with status {return_code}.")
    if not source_stable:
        failure_reasons.append("Source changed while the gate command was running.")
    if pytest_attestation_failure is not None:
        failure_reasons.append(pytest_attestation_failure)
    if (
        spec.outcome.require_pytest_attestation
        and pytest_outcomes.get("passed", 0) <= 0
    ):
        failure_reasons.append("Required pytest attestation reported no passing cases.")
    disallowed = {
        key: pytest_outcomes.get(key, 0)
        for key in spec.outcome.forbidden_pytest_outcomes
        if pytest_outcomes.get(key, 0) > 0
    }
    if disallowed:
        failure_reasons.append(
            "Disallowed pytest outcome was reported: "
            + ", ".join(f"{key}={value}" for key, value in sorted(disallowed.items()))
            + "."
        )
    failure_reasons.extend(artifact_failures)
    return failure_reasons


def _parse_pytest_outcomes(output: str) -> dict[str, int]:
    return parse_terminal_outcomes(output)


def _pytest_outcomes_from_evidence(
    spec: GateSpec,
    attestation: dict[str, Any] | None,
    *,
    output: str,
) -> dict[str, int]:
    if attestation is not None:
        return dict(attestation["counts"])
    if spec.outcome.require_pytest_attestation:
        return dict.fromkeys(COUNT_NAMES, 0)
    return _parse_pytest_outcomes(output)


def _validated_pytest_attestation(
    output_root: Path,
    *,
    spec: GateSpec,
    return_code: int,
) -> tuple[dict[str, Any] | None, str | None]:
    if not spec.outcome.require_pytest_attestation:
        return None, None
    contract = spec.pytest_attestation_contract()
    if contract is None or spec.pytest_attestation_path is None:
        return None, "Registered pytest completion policy is malformed."
    runner, expected_args = contract
    path = _contained_output_path(output_root, spec.pytest_attestation_path)
    return validate_attestation(
        path,
        expected_runner=runner,
        expected_args=expected_args,
        expected_exit_code=return_code,
    )


def _file_record(path: Path, *, root: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "relative_path": path.resolve().relative_to(root).as_posix(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "byte_size": len(content),
    }


def _registered_artifact_record(path: Path, *, root: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise HandoffEvidenceError("Registered artifact must not be a symlink.")
    if path.is_file():
        return {"kind": "file", **_file_record(path, root=root)}
    if not path.is_dir():
        raise HandoffEvidenceError("Registered artifact does not exist.")

    files: list[dict[str, Any]] = []
    for child in sorted(path.rglob("*"), key=lambda item: item.as_posix()):
        if child.is_symlink():
            raise HandoffEvidenceError(
                "Registered artifact directory contains a symlink."
            )
        if child.is_dir():
            continue
        if not child.is_file():
            raise HandoffEvidenceError(
                "Registered artifact directory contains a non-regular file."
            )
        files.append(_file_record(child, root=root))
    if not files:
        raise HandoffEvidenceError("Registered artifact directory is empty.")
    encoded = json.dumps(
        files,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return {
        "kind": "directory",
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "byte_size": sum(int(item["byte_size"]) for item in files),
        "files": files,
    }


def _collect_registered_artifacts(
    root: Path,
    *,
    spec: GateSpec,
) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    failures: list[str] = []
    for relative_path in spec.required_artifact_paths:
        try:
            path = _contained_output_path(root, relative_path)
            records.append(_registered_artifact_record(path, root=root))
        except (HandoffEvidenceError, OSError) as error:
            failures.append(
                f"Required registered artifact {relative_path!r} is invalid: {error}"
            )
    return records, failures


def _prepare_registered_artifacts(root: Path, *, spec: GateSpec) -> None:
    """Remove only registered rebuildable outputs before one gate execution."""
    preserved = set(spec.preserved_input_artifact_paths)
    for relative_path in spec.required_artifact_paths:
        if relative_path in preserved:
            continue
        path = _contained_output_path(root, relative_path)
        try:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
        except OSError as error:
            raise HandoffEvidenceError(
                f"Could not clear stale registered artifact {relative_path!r}."
            ) from error


def _require_disjoint_preserved_inputs(spec: GateSpec) -> None:
    """Refuse ambiguous artifact trees before clearing any rebuildable output."""
    preserved_paths = tuple(
        PurePosixPath(path) for path in spec.preserved_input_artifact_paths
    )
    for relative_path in spec.required_artifact_paths:
        if relative_path in spec.preserved_input_artifact_paths:
            continue
        rebuildable = PurePosixPath(relative_path)
        for preserved in preserved_paths:
            if rebuildable in preserved.parents or preserved in rebuildable.parents:
                raise HandoffEvidenceError(
                    f"Rebuildable artifact {relative_path!r} overlaps a preserved "
                    f"input {preserved.as_posix()!r}."
                )


def _preserved_input_records(
    root: Path,
    *,
    spec: GateSpec,
) -> tuple[dict[str, Any], ...]:
    """Hash every preserved input without allowing the recorder to rewrite it."""
    records: list[dict[str, Any]] = []
    for relative_path in spec.preserved_input_artifact_paths:
        try:
            path = _contained_output_path(root, relative_path)
            records.append(_registered_artifact_record(path, root=root))
        except (HandoffEvidenceError, OSError) as error:
            raise HandoffEvidenceError(
                f"preserved artifact {relative_path!r} is invalid: {error}"
            ) from error
    return tuple(records)


def _validate_registered_artifacts(
    root: Path,
    *,
    spec: GateSpec,
    raw_records: object,
    sensitive_redactions: Mapping[str, str] | None = None,
) -> tuple[bool, str]:
    if not isinstance(raw_records, list):
        return False, "registered artifact records are missing."
    if len(raw_records) != len(spec.required_artifact_paths):
        return False, "registered artifact set was edited."
    for relative_path, raw_record in zip(
        spec.required_artifact_paths,
        raw_records,
        strict=True,
    ):
        if (
            not isinstance(raw_record, dict)
            or raw_record.get("relative_path") != relative_path
        ):
            return False, "registered artifact path was edited."
        try:
            path = _contained_output_path(root, relative_path)
            current_record = _registered_artifact_record(path, root=root)
        except (HandoffEvidenceError, OSError):
            return False, f"registered artifact is missing or invalid: {relative_path}."
        if raw_record != current_record:
            return False, f"registered artifact identity is stale: {relative_path}."
    for path in _registered_text_files(root, spec=spec):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return False, f"registered text artifact is unreadable: {path.name}."
        if sensitive_redactions and _contains_sensitive_path(
            content,
            sensitive_redactions,
        ):
            return False, "registered artifact contains a sensitive cache path."
    return True, ""


def _validate_file_record(
    root: Path,
    raw_record: object,
    *,
    expected_relative_path: str,
) -> tuple[bool, str, bytes]:
    if not isinstance(raw_record, dict):
        return False, "file record is missing.", b""
    if raw_record.get("relative_path") != expected_relative_path:
        return False, "file record path was edited.", b""
    try:
        path = _contained_output_path(root, expected_relative_path)
    except HandoffEvidenceError:
        return False, "file is missing or outside the dossier.", b""
    if not path.is_file():
        return False, "file is missing or outside the dossier.", b""
    try:
        content = path.read_bytes()
    except OSError:
        return False, "file is missing or outside the dossier.", b""
    if hashlib.sha256(content).hexdigest() != raw_record.get("sha256") or len(
        content
    ) != raw_record.get("byte_size"):
        return False, "file identity is stale.", b""
    return True, "", content


def _update_dossier(
    output_root: Path,
    *,
    checkout: dict[str, Any],
    evidence_root_policy: dict[str, str],
    source_identity: dict[str, Any],
    record: dict[str, Any],
) -> None:
    dossier_path = output_root / DOSSIER_NAME
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "profile": "handoff",
        "generated_at": datetime.now(UTC).isoformat(),
        "checkout": checkout,
        "evidence_root_policy": evidence_root_policy,
        "source_identity": source_identity,
        "checks": {},
    }
    if dossier_path.exists():
        try:
            existing = json.loads(dossier_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise HandoffEvidenceError(
                "Existing handoff dossier is unreadable."
            ) from error
        if (
            existing.get("schema_version") != SCHEMA_VERSION
            or existing.get("checkout", {}).get("commit_sha")
            != checkout.get("commit_sha")
            or existing.get("evidence_root_policy") != evidence_root_policy
            or existing.get("source_identity", {}).get("source_digest")
            != source_identity.get("source_digest")
        ):
            raise HandoffEvidenceError(
                "Existing handoff dossier belongs to a different source identity."
            )
        payload = existing
        payload["generated_at"] = datetime.now(UTC).isoformat()
    checks = payload.setdefault("checks", {})
    if not isinstance(checks, dict):
        raise HandoffEvidenceError("Existing handoff dossier checks are malformed.")
    execution_order = payload.setdefault("execution_order", [])
    if not isinstance(execution_order, list) or not all(
        isinstance(check_id, str) for check_id in execution_order
    ):
        raise HandoffEvidenceError(
            "Existing handoff dossier execution order is malformed."
        )
    check_id = str(record["check_id"])
    registry_order = tuple(HANDOFF_GATE_SPECS)
    registry_index = {name: index for index, name in enumerate(registry_order)}
    current_index = registry_index[check_id]
    retained_order = [
        name
        for name in execution_order
        if name in registry_index and registry_index[name] < current_index
    ]
    retained_checks = {name: checks[name] for name in retained_order if name in checks}
    payload["checks"] = retained_checks
    payload["execution_order"] = [*retained_order, check_id]
    checks = retained_checks
    checks[check_id] = record
    _atomic_write_json(dossier_path, payload)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _run_bounded_command(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    environment: dict[str, str],
) -> tuple[int, str, str, bool]:
    """Run one command in an owned process group and reap it on timeout."""
    process, owner = spawn_owned_process(
        list(argv),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        env=environment,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        stdout, stderr = terminate_and_collect(process, owner)
    finally:
        owner.close()
    return (124 if timed_out else int(process.returncode)), stdout, stderr, timed_out


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    run = subparsers.add_parser("run", help="Run and record one gate command.")
    run.add_argument("--repo-root", type=Path, default=ROOT)
    run.add_argument("--evidence-root", type=Path, required=True)
    run.add_argument("--section", required=True)
    run.add_argument("--check-id", required=True)
    run.add_argument("--timeout-seconds", type=float, required=True)
    run.add_argument("--expected-branch", default=DEFAULT_BRANCH)
    run.add_argument("--no-upstream-check", action="store_true")
    run.add_argument("--model-cache-dir", type=Path)
    run.add_argument("--rag-cache-dir", type=Path)
    run.add_argument("--allow-external-evidence-root", action="store_true")
    run.add_argument(
        "--enforce-pytest-outcomes",
        action="store_true",
        default=None,
    )
    run.add_argument("--stdout-artifact")
    run.add_argument("command", nargs=argparse.REMAINDER)

    verify = subparsers.add_parser("verify", help="Verify a recorded dossier.")
    verify.add_argument("--repo-root", type=Path, default=ROOT)
    verify.add_argument("--evidence-root", type=Path, required=True)
    verify.add_argument("--required-check", action="append", default=[])
    verify.add_argument("--expected-branch", default=DEFAULT_BRANCH)
    verify.add_argument("--no-upstream-check", action="store_true")
    verify.add_argument("--model-cache-dir", type=Path)
    verify.add_argument("--rag-cache-dir", type=Path)
    verify.add_argument("--allow-external-evidence-root", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        if args.action == "run":
            command = list(args.command)
            if command and command[0] == "--":
                command = command[1:]
            record = record_handoff_command(
                repo_root=args.repo_root,
                evidence_root=args.evidence_root,
                section=args.section,
                check_id=args.check_id,
                command=command,
                timeout_seconds=args.timeout_seconds,
                expected_branch=args.expected_branch,
                require_upstream=not args.no_upstream_check,
                enforce_pytest_outcomes=args.enforce_pytest_outcomes,
                stdout_artifact=args.stdout_artifact,
                model_cache_dir=args.model_cache_dir,
                rag_cache_dir=args.rag_cache_dir,
                allow_external_evidence_root=args.allow_external_evidence_root,
            )
            print(json.dumps(record, indent=2, sort_keys=True))
            exit_code = 0 if record["passed"] else 1
        else:
            ok, reason = validate_handoff_dossier(
                repo_root=args.repo_root,
                evidence_root=args.evidence_root,
                required_check_ids=args.required_check,
                expected_branch=args.expected_branch,
                require_upstream=not args.no_upstream_check,
                model_cache_dir=args.model_cache_dir,
                rag_cache_dir=args.rag_cache_dir,
                allow_external_evidence_root=args.allow_external_evidence_root,
            )
            print(json.dumps({"ok": ok, "reason": reason}, sort_keys=True))
            exit_code = 0 if ok else 1
    except HandoffEvidenceError as error:
        print(str(error), file=sys.stderr)
        return 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
