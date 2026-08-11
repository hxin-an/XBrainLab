#!/usr/bin/env python3
"""Generate a lightweight quality dashboard for the current workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from scripts.dev.capture_ui_baseline import CAPTURE_STEPS, is_nearly_black
from scripts.dev.owned_process_group import spawn_owned_process, terminate_and_collect
from scripts.dev.pytest_completion_attestation import (
    REQUIRED_PYTEST_RUNNER_ID,
    SHARDED_PYTEST_RUNNER_ID,
    validate_attestation,
)
from scripts.dev.pytest_terminal_summary import last_terminal_summary
from scripts.dev.resource_calibration_contract import (
    strict_calibration_failure_reasons,
)

ROOT = Path(__file__).resolve().parents[2]
QUALITY_DIR = ROOT / "artifacts" / "quality"
LATEST_JSON = QUALITY_DIR / "latest.json"
LATEST_MD = QUALITY_DIR / "latest.md"
HISTORY_JSONL = QUALITY_DIR / "history.jsonl"
EXPECTED_UI_ARTIFACTS = [filename for filename, _ in CAPTURE_STEPS]
REFERENCE_UI_DIR = ROOT / "tests" / "baselines" / "ui"
HEADLESS_CACHE_DIR = Path(tempfile.gettempdir()) / "matplotlib-codex"
POETRY = "/home/administrator/.local/bin/poetry"
POETRY_RUN = f"{POETRY} run --"
POETRY_PYTHON = f"{POETRY_RUN} python"
UI_WRAPPER = str(ROOT / "scripts" / "dev" / "run_ui_pytest.sh")
DEFAULT_FRESH_MINUTES = 60
MAX_UI_MEAN_DIFF = 1.5
MAX_UI_CHANGED_RATIO = 0.02
PIXEL_DIFF_THRESHOLD = 12
DEFAULT_CHECK_TIMEOUT_SECONDS = 300
UI_UNIT_SUITE_TIMEOUT_SECONDS = 900
CHECK_TERMINATION_GRACE_SECONDS = 5
RESOURCE_CALIBRATION_PATH = ROOT / "artifacts" / "resource_guard" / "calibration.json"
DEFAULT_HANDOFF_BRANCH = "main"
PROTECTED_LOCAL_CONFIG_PATHS = frozenset({"settings.json"})
REQUIRED_PUBLIC_IO_TEST_NODES = (
    "tests/integration/io/test_io_integration.py"
    "::TestIOIntegration::test_load_gdf_file_success",
    "tests/integration/io/test_io_integration.py"
    "::TestIOIntegration::test_load_gdf_file_restores_known_graz_channel_names",
    "tests/integration/io/test_io_integration.py"
    "::TestIOIntegration::test_load_supported_real_formats",
    "tests/integration/io/test_io_integration.py"
    "::TestIOIntegration::test_application_service_import_supported_real_formats",
    "tests/integration/io/test_io_integration.py"
    "::TestIOIntegration"
    "::test_application_service_summary_excludes_resolved_gdf_channel_normalization",
    "tests/integration/io/test_io_integration.py"
    "::TestIOIntegration::test_load_public_real_formats",
    "tests/integration/io/test_io_integration.py"
    "::TestIOIntegration::test_application_service_import_public_real_formats",
    "tests/integration/io/test_io_integration.py"
    "::TestIOIntegration::test_load_non_existent_file",
    "tests/integration/io/test_io_integration.py"
    "::TestIOIntegration::test_load_invalid_extension",
)
HANDOFF_EXTERNAL_MANIFEST_SECTIONS = (3, 4, 5, 6)
EMPTY_STATUS_FINGERPRINT = hashlib.sha256(b"").hexdigest()


@dataclass
class CheckResult:
    """Serializable check result for the quality dashboard."""

    key: str
    label: str
    category: str
    command: str
    status: str
    duration_seconds: float
    returncode: int
    summary: str
    output_excerpt: str


@dataclass(frozen=True)
class GitState:
    """Small reproducibility snapshot for dashboard evidence."""

    branch: str
    commit: str
    dirty: bool
    status_summary: list[str]
    dirty_count: int = 0
    status_truncated: bool = False
    status_available: bool = True
    status_fingerprint: str = EMPTY_STATUS_FINGERPRINT
    worktree_fingerprint: str = "unavailable"
    source_tree_fingerprint: str = "unavailable"
    upstream: str = "unknown"
    upstream_commit: str = "unknown"
    ahead_count: int | None = None
    behind_count: int | None = None
    protected_local_changes: tuple[str, ...] = ()
    staged_protected_local_changes: tuple[str, ...] = ()

    @property
    def unprotected_dirty_count(self) -> int:
        """Return changed paths that are not declared local configuration."""
        return max(self.dirty_count - len(self.protected_local_changes), 0)

    def as_report_dict(self) -> dict[str, object]:
        return {
            "branch": self.branch,
            "commit": self.commit,
            "dirty": self.dirty,
            "status_summary": self.status_summary,
            "dirty_count": self.dirty_count,
            "status_truncated": self.status_truncated,
            "status_available": self.status_available,
            "status_fingerprint": self.status_fingerprint,
            "worktree_fingerprint": self.worktree_fingerprint,
            "dirty_fingerprint": self.worktree_fingerprint,
            "source_tree_fingerprint": self.source_tree_fingerprint,
            "upstream": self.upstream,
            "upstream_commit": self.upstream_commit,
            "ahead_count": self.ahead_count,
            "behind_count": self.behind_count,
            "protected_local_changes": list(self.protected_local_changes),
            "staged_protected_local_changes": list(self.staged_protected_local_changes),
            "unprotected_dirty_count": self.unprotected_dirty_count,
        }


def configure_headless_env(*, ui: bool) -> dict[str, str]:
    """Return a process env suitable for unattended workspace checks."""
    env = os.environ.copy()
    env.setdefault("MPLBACKEND", "Agg")
    env.setdefault("MPLCONFIGDIR", str(HEADLESS_CACHE_DIR))
    Path(env["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)
    if ui:
        # The dashboard imports desktop capture helpers, which may select xcb for
        # an interactive WSLg parent process. Unit/integration UI checks must not
        # inherit that native platform because it makes their Qt lifecycle
        # nondeterministic and can trigger native backing-store crashes.
        env["QT_QPA_PLATFORM"] = "offscreen"
    return env


def extract_pytest_summary(output: str) -> str:
    """Return the most useful pytest summary line available."""
    return last_terminal_summary(output) or "No pytest summary line found."


def summarize_output(output: str, *, max_lines: int = 12) -> str:
    """Keep only the tail of command output for dashboard storage."""
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    if not lines:
        return ""
    tail = lines[-max_lines:]
    return "\n".join(tail)


def summarize_tail(output: str, fallback: str) -> str:
    """Return the last non-empty output line, or a fallback summary."""
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped
    return fallback


def _git_output(args: list[str], *, allow_empty: bool = False) -> str:
    git_executable = shutil.which("git")
    if git_executable is None:
        return "unknown"
    completed = subprocess.run(  # noqa: S603
        [git_executable, *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return "unknown"
    output = completed.stdout.rstrip("\r\n")
    return output if output or allow_empty else "unknown"


def collect_git_state() -> GitState:
    """Return branch/commit/dirty metadata for the generated dashboard."""
    branch = _git_output(["branch", "--show-current"])
    commit = _git_output(["rev-parse", "HEAD"])
    upstream = _git_output(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]
    )
    upstream_commit = _git_output(["rev-parse", "@{upstream}"])
    divergence = _git_output(
        ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"]
    )
    ahead_count, behind_count = _parse_git_divergence(divergence)
    status_output = _git_output(
        ["status", "--short", "--untracked-files=all"],
        allow_empty=True,
    )
    status_available = status_output != "unknown"
    full_status = status_output.splitlines() if status_available else []
    status_fingerprint = (
        hashlib.sha256(
            status_output.encode("utf-8", errors="surrogateescape")
        ).hexdigest()
        if status_available
        else "unavailable"
    )
    protected_local_changes = tuple(
        path
        for entry in full_status
        if (path := _status_entry_path(entry)) in PROTECTED_LOCAL_CONFIG_PATHS
    )
    staged_protected_local_changes = tuple(
        path
        for entry in full_status
        if (path := _status_entry_path(entry)) in PROTECTED_LOCAL_CONFIG_PATHS
        and _status_entry_is_staged(entry)
    )
    return GitState(
        branch=branch,
        commit=commit,
        dirty=bool(full_status),
        status_summary=full_status[:40],
        dirty_count=len(full_status),
        status_truncated=len(full_status) > 40,
        status_available=status_available,
        status_fingerprint=status_fingerprint,
        worktree_fingerprint=_worktree_fingerprint(ROOT),
        source_tree_fingerprint=_git_output(["rev-parse", "HEAD^{tree}"]),
        upstream=upstream,
        upstream_commit=upstream_commit,
        ahead_count=ahead_count,
        behind_count=behind_count,
        protected_local_changes=protected_local_changes,
        staged_protected_local_changes=staged_protected_local_changes,
    )


def _parse_git_divergence(value: str) -> tuple[int | None, int | None]:
    """Parse git's HEAD/upstream left-right counts without guessing failures."""
    fields = value.split()
    if len(fields) != 2:
        return None, None
    try:
        return int(fields[0]), int(fields[1])
    except ValueError:
        return None, None


def source_stability_check(before: GitState, after: GitState) -> CheckResult:
    """Fail closed unless source identity is unchanged across dashboard checks."""
    compared = {
        "branch": (before.branch, after.branch),
        "commit": (before.commit, after.commit),
        "status availability": (before.status_available, after.status_available),
        "status entries": (before.status_summary, after.status_summary),
        "status fingerprint": (
            before.status_fingerprint,
            after.status_fingerprint,
        ),
        "dirty count": (before.dirty_count, after.dirty_count),
        "status truncation": (before.status_truncated, after.status_truncated),
        "dirty state": (before.dirty, after.dirty),
        "dirty fingerprint": (
            before.worktree_fingerprint,
            after.worktree_fingerprint,
        ),
        "source-tree fingerprint": (
            before.source_tree_fingerprint,
            after.source_tree_fingerprint,
        ),
        "upstream": (before.upstream, after.upstream),
        "upstream commit": (before.upstream_commit, after.upstream_commit),
        "ahead count": (before.ahead_count, after.ahead_count),
        "behind count": (before.behind_count, after.behind_count),
        "protected local settings": (
            before.protected_local_changes,
            after.protected_local_changes,
        ),
        "staged protected local settings": (
            before.staged_protected_local_changes,
            after.staged_protected_local_changes,
        ),
    }
    required_identity_labels = {
        "branch",
        "commit",
        "dirty state",
        "dirty fingerprint",
        "status fingerprint",
        "source-tree fingerprint",
    }
    unavailable = [
        label
        for label, values in compared.items()
        if label in required_identity_labels
        and any(value in {"", "unknown", "unavailable", None} for value in values)
    ]
    if not before.status_available or not after.status_available:
        unavailable.append("status availability")
    changed = [
        label
        for label, (started, completed) in compared.items()
        if started != completed
    ]
    if unavailable:
        status = "fail"
        summary = (
            "Source identity was unavailable after checks: "
            + ", ".join(unavailable)
            + "."
        )
    elif changed:
        status = "fail"
        summary = (
            "Source identity changed during dashboard execution: "
            + ", ".join(changed)
            + ". Discard this report and rerun from stable source."
        )
    else:
        status = "pass"
        summary = (
            "Branch, commit, complete status metadata, upstream divergence, dirty "
            "fingerprint, and source-tree fingerprint remained stable across all checks."
        )
    return CheckResult(
        key="source_stability",
        label="Source Stability",
        category="quality",
        command="git identity before and after dashboard checks",
        status=status,
        duration_seconds=0.0,
        returncode=1 if status == "fail" else 0,
        summary=summary,
        output_excerpt="",
    )


def _status_entry_path(entry: str) -> str:
    """Extract a path from one human-readable porcelain-v1 status entry."""
    payload = entry[3:] if len(entry) > 3 else ""
    if " -> " in payload:
        payload = payload.rsplit(" -> ", maxsplit=1)[1]
    return payload.strip().strip('"')


def _status_entry_is_staged(entry: str) -> bool:
    """Return whether a porcelain-v1 entry has an index-side change."""
    return bool(entry) and entry[0] not in {" ", "?"}


def _worktree_fingerprint(repo_root: Path) -> str:
    """Hash source changes while excluding declared machine-local configuration."""
    git_executable = shutil.which("git")
    if git_executable is None:
        return "unavailable"
    tracked = _run_git_bytes(
        git_executable,
        repo_root,
        "diff",
        "--binary",
        "--no-ext-diff",
        "HEAD",
        "--",
        ".",
        *(
            f":(exclude,literal){relative_path}"
            for relative_path in sorted(PROTECTED_LOCAL_CONFIG_PATHS)
        ),
    )
    untracked = _run_git_bytes(
        git_executable,
        repo_root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    )
    if tracked is None or untracked is None:
        return "unavailable"

    digest = hashlib.sha256()
    digest.update(b"tracked-diff\0")
    digest.update(tracked)
    digest.update(b"untracked-files\0")
    for raw_path in sorted(path for path in untracked.split(b"\0") if path):
        try:
            relative = raw_path.decode("utf-8", errors="surrogateescape")
            if relative in PROTECTED_LOCAL_CONFIG_PATHS:
                continue
            path = repo_root / relative
            digest.update(len(raw_path).to_bytes(8, "big"))
            digest.update(raw_path)
            if path.is_symlink():
                content = os.readlink(path).encode("utf-8", errors="surrogateescape")
                digest.update(b"symlink\0")
                digest.update(content)
            elif path.is_file():
                digest.update(b"file\0")
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
            else:
                digest.update(b"missing\0")
        except OSError:
            return "unavailable"
    return digest.hexdigest()


def _run_git_bytes(
    git_executable: str,
    repo_root: Path,
    *args: str,
) -> bytes | None:
    try:
        completed = subprocess.run(  # noqa: S603 - resolved git binary, no shell.
            [git_executable, *args],
            cwd=repo_root,
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout if completed.returncode == 0 else None


def workspace_traceability_check(
    git_state: GitState,
    *,
    fail_on_unprotected_dirty: bool = False,
    expected_branch: str | None = None,
    require_upstream_sync: bool = False,
) -> CheckResult:
    """Validate source identity and protected local-setting hygiene."""
    exact_sha_available = re.fullmatch(r"[0-9a-f]{40}", git_state.commit) is not None
    if not git_state.status_available:
        status = "fail" if fail_on_unprotected_dirty else "warn"
        summary = "git status was unavailable; source cleanliness is unverified."
    elif git_state.staged_protected_local_changes:
        status = "fail"
        paths = ", ".join(git_state.staged_protected_local_changes)
        summary = (
            "Protected local configuration must never be staged; unstage before "
            f"continuing: {paths}."
        )
    elif fail_on_unprotected_dirty and not exact_sha_available:
        status = "fail"
        summary = (
            "Handoff evidence requires the full 40-character commit SHA; "
            f"observed {git_state.commit!r}."
        )
    elif expected_branch is not None and git_state.branch != expected_branch:
        status = "fail"
        summary = (
            f"Handoff evidence requires expected branch {expected_branch!r}; "
            f"observed {git_state.branch!r}."
        )
    elif require_upstream_sync and git_state.upstream in {"", "unknown", "unavailable"}:
        status = "fail"
        summary = "Handoff evidence requires a configured upstream branch."
    elif require_upstream_sync and not re.fullmatch(
        r"[0-9a-f]{40}", git_state.upstream_commit
    ):
        status = "fail"
        summary = "Handoff evidence could not resolve the configured upstream commit."
    elif require_upstream_sync and git_state.commit != git_state.upstream_commit:
        status = "fail"
        summary = (
            f"HEAD {git_state.commit} does not equal upstream "
            f"{git_state.upstream_commit}."
        )
    elif require_upstream_sync and (
        git_state.ahead_count is None or git_state.behind_count is None
    ):
        status = "fail"
        summary = "Handoff evidence could not determine ahead/behind divergence."
    elif require_upstream_sync and (
        git_state.ahead_count != 0 or git_state.behind_count != 0
    ):
        status = "fail"
        summary = (
            "Handoff branch is not synchronized with its upstream: "
            f"{git_state.ahead_count} ahead / {git_state.behind_count} behind."
        )
    elif not git_state.dirty:
        status = "pass"
        summary = f"Clean worktree at {git_state.commit}."
        if require_upstream_sync:
            summary += f" Upstream {git_state.upstream}: 0 ahead / 0 behind."
    elif git_state.unprotected_dirty_count == 0:
        status = "pass"
        paths = ", ".join(git_state.protected_local_changes)
        summary = (
            "Tracked source is clean; declared local configuration remains "
            f"visible and unstaged: {paths}."
        )
    else:
        status = "fail" if fail_on_unprotected_dirty else "warn"
        summary = (
            f"Dirty worktree has {git_state.unprotected_dirty_count} unprotected "
            f"changed path(s) ({git_state.dirty_count} total); commit source changes "
            "and rerun before claiming release-candidate clean evidence."
        )
    return CheckResult(
        key="workspace_traceability",
        label="Workspace Traceability",
        category="quality",
        command="git status --short",
        status=status,
        duration_seconds=0.0,
        returncode=1 if status == "fail" else 0,
        summary=summary,
        output_excerpt="\n".join(git_state.status_summary),
    )


def handoff_output_contract_check(
    output_dir: Path | None,
    *,
    commit: str,
) -> CheckResult:
    """Require final reports to use a SHA-scoped non-source destination."""
    resolved = output_dir.expanduser().resolve() if output_dir is not None else None
    if resolved is None:
        failure = "Handoff evidence requires an explicit --output-dir."
    elif commit not in resolved.parts:
        failure = f"Handoff output directory must contain the exact SHA {commit}."
    elif _is_path_inside(resolved, ROOT) and not _git_ignores_path(
        resolved / ".gitignore-probe"
    ):
        failure = "Handoff output inside the worktree must be git-ignored."
    else:
        failure = ""

    status = "fail" if failure else "pass"
    summary = (
        failure or f"SHA-scoped handoff output is outside tracked source: {resolved}."
    )
    return CheckResult(
        key="handoff_output_contract",
        label="Handoff Output Contract",
        category="quality",
        command="git check-ignore <handoff-output>/.gitignore-probe",
        status=status,
        duration_seconds=0.0,
        returncode=1 if failure else 0,
        summary=summary,
        output_excerpt="",
    )


def _is_path_inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _git_ignores_path(path: Path) -> bool:
    git_executable = shutil.which("git")
    if git_executable is None:
        return False
    completed = subprocess.run(  # noqa: S603 - resolved git binary, no shell.
        [git_executable, "check-ignore", "-q", str(path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        timeout=30,
    )
    return completed.returncode == 0


def resource_calibration_evidence_check(
    *,
    artifact_path: Path | None = None,
    require_exact_source: bool = False,
    commit: str | None = None,
) -> CheckResult:
    """Validate checkpoint or exact-source CUDA calibration evidence."""
    selected_path = artifact_path or RESOURCE_CALIBRATION_PATH
    if not selected_path.is_absolute():
        selected_path = ROOT / selected_path
    selected_path = selected_path.expanduser().resolve()
    command = (
        f"{POETRY_PYTHON} scripts/dev/calibrate_resource_guard.py --strict "
        f"--output {shlex.quote(str(selected_path))}"
    )

    failures: list[str] = []
    if require_exact_source:
        default_path = RESOURCE_CALIBRATION_PATH.expanduser().resolve()
        if artifact_path is None:
            failures.append(
                "handoff calibration requires an explicit --resource-calibration-path"
            )
        elif selected_path == default_path:
            failures.append(
                "tracked default calibration is checkpoint-only and cannot "
                "certify handoff"
            )
        elif commit is None or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
            failures.append(
                "handoff calibration requires the current full 40-character commit SHA"
            )
        elif commit not in selected_path.parts:
            failures.append(
                f"handoff calibration path must contain the exact SHA {commit}"
            )
        elif not _git_ignores_path(selected_path):
            failures.append("handoff calibration artifact path must be Git-ignored")

    if not failures:
        if not selected_path.is_file():
            failures = ["resource calibration artifact is missing"]
        else:
            try:
                payload = json.loads(selected_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                failures = [f"resource calibration artifact is unreadable: {exc}"]
            else:
                failures = strict_calibration_failure_reasons(
                    payload,
                    repo_root=ROOT,
                    validate_source=require_exact_source,
                    validate_freshness=True,
                )
    if failures:
        status = "fail"
        summary = "; ".join(failures[:3])
    elif require_exact_source:
        status = "pass"
        summary = "Resource guard strict exact-source calibration evidence is current."
    else:
        status = "warn"
        summary = (
            "Resource guard calibration is checkpoint-only; exact source identity "
            "is not certified."
        )
    return CheckResult(
        key="resource_calibration_evidence",
        label="Resource Calibration Evidence",
        category="resource",
        command=command,
        status=status,
        duration_seconds=0.0,
        returncode=1 if failures else 0,
        summary=summary,
        output_excerpt="",
    )


def compute_overall_status(checks: list[CheckResult]) -> str:
    """Collapse all check statuses into one overall state."""
    statuses = {check.status for check in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def compare_ui_images(
    reference_path: Path, candidate_path: Path
) -> tuple[str, dict[str, float | str]]:
    """Compare a captured UI artifact against an approved reference image."""
    with (
        Image.open(reference_path) as reference_image,
        Image.open(candidate_path) as candidate_image,
    ):
        reference_rgb = reference_image.convert("RGB")
        candidate_rgb = candidate_image.convert("RGB")

    if reference_rgb.size != candidate_rgb.size:
        return (
            "fail",
            {
                "reason": "size mismatch",
                "reference_size": str(reference_rgb.size),
                "candidate_size": str(candidate_rgb.size),
            },
        )

    diff = ImageChops.difference(reference_rgb, candidate_rgb)
    stat = ImageStat.Stat(diff)
    mean_diff = sum(stat.mean) / len(stat.mean)

    def threshold_pixel(value: int) -> int:
        return 255 if value > PIXEL_DIFF_THRESHOLD else 0

    diff_mask = diff.convert("L").point(threshold_pixel)
    histogram = diff_mask.histogram()
    total_pixels = sum(histogram)
    changed_pixels = total_pixels - histogram[0]
    changed_ratio = changed_pixels / total_pixels if total_pixels else 0.0

    status = (
        "pass"
        if mean_diff <= MAX_UI_MEAN_DIFF and changed_ratio <= MAX_UI_CHANGED_RATIO
        else "fail"
    )
    return (
        status,
        {
            "mean_diff": round(mean_diff, 3),
            "changed_ratio": round(changed_ratio, 4),
        },
    )


def validate_ui_artifacts(
    artifacts_dir: Path,
    *,
    reference_dir: Path = REFERENCE_UI_DIR,
) -> tuple[str, str]:
    """Validate that the expected UI artifacts exist and are not black."""
    missing = [
        name for name in EXPECTED_UI_ARTIFACTS if not (artifacts_dir / name).exists()
    ]
    if missing:
        return "fail", f"Missing UI artifacts: {', '.join(missing)}"

    unusable = [
        name for name in EXPECTED_UI_ARTIFACTS if is_nearly_black(artifacts_dir / name)
    ]
    if unusable:
        return "fail", f"Nearly black UI artifacts: {', '.join(unusable)}"

    missing_references = [
        name for name in EXPECTED_UI_ARTIFACTS if not (reference_dir / name).exists()
    ]
    if missing_references:
        return "fail", f"Missing UI references: {', '.join(missing_references)}"

    mismatches: list[str] = []
    matched_metrics: list[tuple[float, float]] = []
    for filename in EXPECTED_UI_ARTIFACTS:
        status, metrics = compare_ui_images(
            reference_dir / filename, artifacts_dir / filename
        )
        if status != "pass":
            if metrics.get("reason") == "size mismatch":
                mismatches.append(
                    f"{filename} (size {metrics['candidate_size']} vs ref {metrics['reference_size']})"
                )
                continue
            mismatches.append(
                f"{filename} (mean diff {metrics['mean_diff']}, changed {metrics['changed_ratio']:.2%})"
            )
            continue
        matched_metrics.append(
            (float(metrics["mean_diff"]), float(metrics["changed_ratio"]))
        )

    if mismatches:
        return "fail", f"UI baseline drift: {', '.join(mismatches[:3])}"

    max_mean = max((mean for mean, _ in matched_metrics), default=0.0)
    max_changed_ratio = max((ratio for _, ratio in matched_metrics), default=0.0)
    return (
        "pass",
        f"{len(EXPECTED_UI_ARTIFACTS)} UI artifacts match approved references (max mean diff {max_mean:.3f}, max changed {max_changed_ratio:.2%}).",
    )


def run_check(
    *,
    key: str,
    label: str,
    category: str,
    command: str,
    ui: bool = False,
    validator=None,
    timeout_seconds: int = DEFAULT_CHECK_TIMEOUT_SECONDS,
) -> CheckResult:
    """Run a command and normalize the result into dashboard format."""
    started = time.monotonic()
    env = configure_headless_env(ui=ui)
    command_args = shlex.split(command)
    pytest_contract = (
        _dashboard_pytest_attestation_contract(command_args)
        if validator is validate_required_pytest_matrix
        else None
    )
    attestation_path: Path | None = None
    if validator is validate_required_pytest_matrix:
        runtime_dir = ROOT / "build" / "tmp" / "quality-dashboard"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=runtime_dir,
            prefix=f"{key}-",
            suffix=".json",
            delete=True,
        ) as handle:
            attestation_path = Path(handle.name)
        env["XBL_PYTEST_RESULT_JSON"] = str(attestation_path)
    completed, timed_out = _run_bounded_command(
        command_args,
        env=env,
        timeout_seconds=timeout_seconds,
    )
    duration = time.monotonic() - started
    output = (completed.stdout or "") + (completed.stderr or "")
    excerpt = summarize_output(output)

    if timed_out:
        status = "fail"
        summary = f"Timed out after {timeout_seconds} seconds."
    elif validator is not None:
        if validator is validate_required_pytest_matrix:
            if pytest_contract is None:
                status, summary = "fail", "Required pytest runner is not attesting."
            else:
                expected_runner, expected_args = pytest_contract
                status, summary = validate_required_pytest_matrix(
                    completed.returncode,
                    output,
                    attestation_path=attestation_path,
                    expected_runner=expected_runner,
                    expected_args=expected_args,
                )
        else:
            status, summary = validator(completed.returncode, output)
    elif completed.returncode == 0:
        summary = (
            extract_pytest_summary(output) if "pytest" in command else "Command passed."
        )
        status = "pass"
    else:
        summary = (
            extract_pytest_summary(output)
            if "pytest" in command
            else f"Command failed with exit code {completed.returncode}."
        )
        status = "fail"

    if attestation_path is not None:
        attestation_path.unlink(missing_ok=True)
    return CheckResult(
        key=key,
        label=label,
        category=category,
        command=command,
        status=status,
        duration_seconds=round(duration, 2),
        returncode=completed.returncode,
        summary=summary,
        output_excerpt=excerpt,
    )


def _run_bounded_command(
    args: list[str],
    *,
    env: dict[str, str],
    timeout_seconds: int,
) -> tuple[subprocess.CompletedProcess[str], bool]:
    """Run one check and terminate its process group when the bound expires."""
    process, owner = spawn_owned_process(
        args,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        stdout, stderr = terminate_and_collect(
            process,
            owner,
            grace_seconds=CHECK_TERMINATION_GRACE_SECONDS,
        )
    finally:
        owner.close(grace_seconds=CHECK_TERMINATION_GRACE_SECONDS)
    return (
        subprocess.CompletedProcess(
            args,
            124 if timed_out else process.returncode,
            stdout,
            stderr,
        ),
        timed_out,
    )


def validate_startup(returncode: int, output: str) -> tuple[str, str]:
    """Interpret the startup smoke output."""
    if "MainWindow initialized" in output and returncode in {0, 124}:
        return "pass", "MainWindow initialized before timeout."
    if returncode == 124:
        return "warn", "Startup timed out without the expected init marker."
    return "fail", f"Startup smoke failed with exit code {returncode}."


def validate_ui_baseline(returncode: int, output: str) -> tuple[str, str]:
    """Interpret baseline capture plus artifact quality."""
    if returncode != 0:
        return "fail", f"Baseline capture failed with exit code {returncode}."
    return validate_ui_artifacts(ROOT / "artifacts" / "ui")


def validate_pytest_like(returncode: int, output: str) -> tuple[str, str]:
    """Interpret runner output that still ends in a pytest summary line."""
    exception_summary = extract_unhandled_exception_summary(output)
    if exception_summary:
        return "fail", exception_summary
    summary = extract_pytest_summary(output)
    return ("pass", summary) if returncode == 0 else ("fail", summary)


def validate_required_pytest_matrix(
    returncode: int,
    output: str,
    *,
    attestation_path: Path | None = None,
    expected_runner: str = REQUIRED_PYTEST_RUNNER_ID,
    expected_args: tuple[str, ...] = (),
) -> tuple[str, str]:
    """Require every case in a mandatory pytest matrix to execute and pass."""
    exception_summary = extract_unhandled_exception_summary(output)
    if exception_summary:
        return "fail", exception_summary
    if attestation_path is None:
        return "fail", "Required pytest completion attestation was not provided."
    attestation, failure = validate_attestation(
        attestation_path,
        expected_runner=expected_runner,
        expected_args=expected_args,
        expected_exit_code=returncode,
    )
    if failure is not None or attestation is None:
        return "fail", failure or "Required pytest completion attestation failed."
    outcomes = dict(attestation["counts"])
    summary = f"{outcomes.get('passed', 0)} passed (attested)."
    if returncode != 0:
        return "fail", f"Required pytest runner exited with status {returncode}."

    disallowed = {
        label: outcomes.get(label, 0)
        for label in (
            "failed",
            "errors",
            "skipped",
            "xfailed",
            "xpassed",
            "deselected",
        )
        if outcomes.get(label, 0) > 0
    }
    if disallowed:
        details = ", ".join(
            f"{label}={count}" for label, count in sorted(disallowed.items())
        )
        return (
            "fail",
            f"Required pytest matrix was incomplete ({details}): {summary}",
        )
    if outcomes.get("passed", 0) <= 0:
        return "fail", "Required pytest attestation reported no passing cases."
    return "pass", summary


def _dashboard_pytest_attestation_contract(
    args: list[str],
) -> tuple[str, tuple[str, ...]] | None:
    if not args:
        return None
    executable = Path(args[0]).name.casefold()
    if executable == "run_ui_pytest.sh":
        return REQUIRED_PYTEST_RUNNER_ID, ("--capture=sys", *args[1:])
    tokens = list(args)
    if tokens[:2] == [POETRY, "run"]:
        tokens = tokens[2:]
        if tokens[:1] == ["--"]:
            tokens = tokens[1:]
    if len(tokens) < 3 or not Path(tokens[0]).name.casefold().startswith("python"):
        return None
    if tokens[1:2] == ["-m"]:
        runner = tokens[2].casefold()
        runner_args = tokens[3:]
    else:
        runner = Path(tokens[1]).name.casefold()
        runner_args = tokens[2:]
    if (
        runner
        in {
            "run_required_pytest_gate.py",
            "scripts.dev.run_required_pytest_gate",
        }
        and "--" in runner_args
    ):
        separator = runner_args.index("--")
        return REQUIRED_PYTEST_RUNNER_ID, tuple(runner_args[separator + 1 :])
    if runner in {"run_tests.py", "scripts.dev.run_tests"} and runner_args:
        return SHARDED_PYTEST_RUNNER_ID, (runner_args[0],)
    return None


def extract_unhandled_exception_summary(output: str) -> str | None:
    """Detect uncaught exceptions in wrappers that can still exit with code 0."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    markers = (
        "Traceback (most recent call last):",
        "Fatal Python error:",
        "Segmentation fault",
    )
    marker_index = next(
        (
            index
            for index, line in enumerate(lines)
            if any(marker in line for marker in markers)
        ),
        None,
    )
    if marker_index is None:
        return None

    tail = lines[marker_index:]
    exception_line = next(
        (
            line
            for line in reversed(tail)
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*(Error|Exception):", line)
        ),
        tail[0],
    )
    return f"Unhandled exception output: {exception_line}"


def validate_text_command(
    returncode: int, output: str, *, success_fallback: str
) -> tuple[str, str]:
    """Interpret plain-text command output for non-pytest checks."""
    summary = summarize_tail(
        output,
        success_fallback
        if returncode == 0
        else f"Command failed with exit code {returncode}.",
    )
    return ("pass", summary) if returncode == 0 else ("fail", summary)


def ensure_quality_dir() -> None:
    """Create the output directory for dashboard files."""
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)


def latest_is_fresh(
    max_age_minutes: int,
    *,
    profile: str = "fast",
    git_state: GitState | None = None,
) -> bool:
    """Return True when the latest report is newer than the requested age."""
    # Downloaded fixture caches are ignored by git and must be reverified each time.
    if profile == "handoff":
        return False
    if max_age_minutes <= 0 or not LATEST_JSON.exists():
        return False
    payload = json.loads(LATEST_JSON.read_text(encoding="utf-8"))
    if payload.get("workspace") != str(ROOT):
        return False
    if payload.get("profile", "fast") != profile:
        return False
    current_git = git_state or collect_git_state()
    payload_git = payload.get("git") if isinstance(payload.get("git"), dict) else {}
    if payload_git.get("branch") != current_git.branch:
        return False
    if payload_git.get("commit") != current_git.commit:
        return False
    if payload_git.get("upstream") != current_git.upstream:
        return False
    if payload_git.get("upstream_commit") != current_git.upstream_commit:
        return False
    if payload_git.get("ahead_count") != current_git.ahead_count:
        return False
    if payload_git.get("behind_count") != current_git.behind_count:
        return False
    if bool(payload_git.get("dirty")) != current_git.dirty:
        return False
    if int(payload_git.get("dirty_count") or 0) != current_git.dirty_count:
        return False
    if bool(payload_git.get("status_truncated")) != current_git.status_truncated:
        return False
    if bool(payload_git.get("status_available", True)) != current_git.status_available:
        return False
    if payload_git.get("protected_local_changes", []) != list(
        current_git.protected_local_changes
    ):
        return False
    if payload_git.get("staged_protected_local_changes", []) != list(
        current_git.staged_protected_local_changes
    ):
        return False
    payload_fingerprint = str(payload_git.get("worktree_fingerprint") or "")
    if (
        payload_fingerprint in {"", "unavailable"}
        or current_git.worktree_fingerprint in {"", "unavailable"}
        or payload_fingerprint != current_git.worktree_fingerprint
    ):
        return False
    payload_source_tree = str(payload_git.get("source_tree_fingerprint") or "")
    if (
        payload_source_tree in {"", "unknown", "unavailable"}
        or current_git.source_tree_fingerprint in {"", "unknown", "unavailable"}
        or payload_source_tree != current_git.source_tree_fingerprint
    ):
        return False
    payload_status = payload_git.get("status_summary")
    if not isinstance(payload_status, list):
        return False
    if [str(item) for item in payload_status] != current_git.status_summary:
        return False
    generated_at = datetime.fromisoformat(payload["generated_at"])
    age_seconds = (datetime.now(UTC) - generated_at).total_seconds()
    return age_seconds < max_age_minutes * 60


def render_markdown(report: dict) -> str:
    """Render a human-readable dashboard markdown file."""
    status_icons = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
    checks = report["checks"]
    profile = report.get("profile", "fast")
    generated_at = datetime.fromisoformat(report["generated_at"]).astimezone()
    display_offset = generated_at.strftime("%z")
    display_offset = (
        f"{display_offset[:3]}:{display_offset[3:]}" if len(display_offset) == 5 else ""
    )
    generated_at_display = (
        f"{generated_at.strftime('%Y-%m-%d %H:%M:%S')} UTC{display_offset}"
    )
    lines = [
        "# XBrainLab Quality Dashboard",
        "",
        f"- Generated at: `{generated_at_display}`",
        f"- Profile: `{profile}`",
        f"- Overall dashboard status: `{report['overall_status'].upper()}`",
        f"- Workspace: `{report['workspace']}`",
    ]
    git = report.get("git_after") or report.get("git")
    if isinstance(git, dict):
        lines.extend(
            [
                f"- Git branch: `{git.get('branch', 'unknown')}`",
                f"- Git commit: `{git.get('commit', 'unknown')}`",
                f"- Git upstream: `{git.get('upstream', 'unknown')}`",
                f"- Upstream commit: `{git.get('upstream_commit', 'unknown')}`",
                f"- Upstream divergence: `{git.get('ahead_count', 'unknown')} ahead / "
                f"{git.get('behind_count', 'unknown')} behind`",
                f"- Dirty worktree: `{'yes' if git.get('dirty') else 'no'}`",
                f"- Git status available: "
                f"`{'yes' if git.get('status_available', True) else 'no'}`",
                f"- Worktree fingerprint: "
                f"`{git.get('worktree_fingerprint', 'unavailable')}`",
                f"- Source-tree fingerprint: "
                f"`{git.get('source_tree_fingerprint', 'unavailable')}`",
            ]
        )
        status_summary = git.get("status_summary") or []
        dirty_count = int(git.get("dirty_count") or len(status_summary))
        if status_summary:
            truncated = " (truncated)" if git.get("status_truncated") else ""
            lines.append(f"- Dirty summary: `{dirty_count}` path(s){truncated}")
            for item in status_summary[:12]:
                lines.append(f"  - `{item}`")
        protected_local_changes = git.get("protected_local_changes") or []
        if protected_local_changes:
            lines.append(
                "- Protected local configuration (visible, never staged): "
                + ", ".join(f"`{path}`" for path in protected_local_changes)
            )
        staged_protected_local_changes = git.get("staged_protected_local_changes") or []
        if staged_protected_local_changes:
            lines.append(
                "- Invalid staged protected configuration: "
                + ", ".join(f"`{path}`" for path in staged_protected_local_changes)
            )
    handoff_manifest = report.get("handoff_manifest")
    if isinstance(handoff_manifest, dict):
        external_sections = handoff_manifest.get("externally_required_sections") or []
        first_section = external_sections[0] if external_sections else "?"
        last_section = external_sections[-1] if external_sections else "?"
        lines.extend(
            [
                "",
                "## Handoff Evidence Boundary",
                "",
                "- Certifies full handoff manifest: `no`",
                "- External manifest evidence required: "
                + ", ".join(f"`{section}`" for section in external_sections),
                "",
                "Dashboard summary only: this command does not run or certify "
                f"manifest sections `{first_section}`-`{last_section}`. Their exact "
                "command logs and artifacts remain required external evidence.",
            ]
        )
    lines.extend(
        [
            "",
            "## Summary",
            "",
            "| Check | Status | Duration | Summary |",
            "| --- | --- | ---: | --- |",
        ]
    )
    for check in checks:
        lines.append(
            f"| {check['label']} | `{status_icons[check['status']]}` | `{check['duration_seconds']:.2f}s` | {check['summary']} |"
        )

    lines.extend(
        [
            "",
            "## UI Baseline Capture",
            "",
            "Generated capture paths (transient, git-ignored):",
            "",
        ]
    )
    for filename in EXPECTED_UI_ARTIFACTS:
        lines.append(f"- `artifacts/ui/{filename}`")

    lines.extend(
        [
            "",
            "Reference artifacts:",
            "",
        ]
    )
    for filename in EXPECTED_UI_ARTIFACTS:
        lines.append(f"- `tests/baselines/ui/{filename}`")

    lines.extend(["", "## Command Details", ""])
    for check in checks:
        lines.extend(
            [
                f"### {check['label']}",
                "",
                f"- Status: `{check['status'].upper()}`",
                f"- Command: `{check['command']}`",
                f"- Summary: {check['summary']}",
                "",
            ]
        )
        if check["output_excerpt"]:
            lines.extend(
                [
                    "```text",
                    check["output_excerpt"],
                    "```",
                    "",
                ]
            )

    return "\n".join(lines).rstrip() + "\n"


def write_report(report: dict, *, output_dir: Path | None = None) -> None:
    """Write the latest dashboard files and append to history."""
    if output_dir is None:
        ensure_quality_dir()
        latest_json = LATEST_JSON
        latest_md = LATEST_MD
        history_jsonl = HISTORY_JSONL
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        latest_json = output_dir / "latest.json"
        latest_md = output_dir / "latest.md"
        history_jsonl = output_dir / "history.jsonl"
    latest_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    with history_jsonl.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False) + "\n")


def build_checks() -> list[CheckResult]:
    """Run the current dashboard check set."""
    return build_checks_for_mode(
        include_slow_checks=False,
        include_handoff_checks=False,
    )


def build_checks_for_mode(
    *,
    include_slow_checks: bool,
    include_handoff_checks: bool = False,
    resource_calibration_path: Path | None = None,
    calibration_commit: str | None = None,
) -> list[CheckResult]:
    """Run the dashboard checks for the requested speed profile."""
    checks = [
        resource_calibration_evidence_check(
            artifact_path=resource_calibration_path,
            require_exact_source=include_handoff_checks,
            commit=calibration_commit,
        ),
        run_check(
            key="ruff_lint",
            label="Ruff Lint",
            category="quality",
            command=f"{POETRY_RUN} ruff check .",
            ui=False,
            validator=lambda code, output: validate_text_command(
                code,
                output,
                success_fallback="ruff check passed.",
            ),
        ),
        run_check(
            key="basedpyright_type_check",
            label="Basedpyright Type Check",
            category="quality",
            command=f"{POETRY_RUN} basedpyright",
            ui=False,
            validator=lambda code, output: validate_text_command(
                code,
                output,
                success_fallback="basedpyright passed.",
            ),
        ),
        run_check(
            key="architecture_compliance",
            label="Architecture Compliance",
            category="quality",
            command=f"{POETRY_PYTHON} tests/architecture_compliance.py",
            ui=False,
            validator=lambda code, output: validate_text_command(
                code,
                output,
                success_fallback="Architecture compliance passed.",
            ),
        ),
        run_check(
            key="startup_smoke",
            label="Startup Smoke",
            category="runtime",
            command=(
                "timeout 25s xvfb-run -a env QT_QPA_PLATFORM=xcb "
                f"{POETRY_PYTHON} run.py"
            ),
            ui=True,
            validator=validate_startup,
        ),
        run_check(
            key="ui_baseline_capture",
            label="UI Baseline Capture",
            category="ui",
            command=(
                "xvfb-run -a env QT_QPA_PLATFORM=xcb "
                f"{POETRY_PYTHON} scripts/dev/capture_ui_baseline.py"
            ),
            ui=True,
            validator=validate_ui_baseline,
        ),
        run_check(
            key="ui_dialog_acceptance",
            label="UI Dialog Acceptance",
            category="ui",
            command=f"{UI_WRAPPER} tests/integration/ui/test_dialog_acceptance.py -q",
            ui=True,
            validator=validate_required_pytest_matrix,
        ),
        run_check(
            key="ui_product_walkthrough",
            label="UI Product Walkthrough",
            category="ui",
            command=(
                f"{UI_WRAPPER} "
                "tests/integration/ui/test_product_walkthrough.py "
                "tests/integration/ui/test_data_import_wizard_runtime.py -q"
            ),
            ui=True,
            validator=validate_required_pytest_matrix,
        ),
        run_check(
            key="public_bids_visible_ui_wizard_format_matrix",
            label="Public BIDS Visible UI Wizard Format Matrix",
            category="ui",
            command=(
                f"{POETRY_PYTHON} -m scripts.dev.run_required_pytest_gate -- "
                "--capture=sys "
                "tests/integration/ui/test_data_import_wizard_format_matrix.py -q"
            ),
            ui=True,
            validator=validate_required_pytest_matrix,
        ),
        run_check(
            key="ui_unit_suite",
            label="UI Unit Suite",
            category="ui",
            command=f"{POETRY_PYTHON} scripts/dev/run_tests.py ui",
            ui=True,
            validator=validate_required_pytest_matrix,
            timeout_seconds=UI_UNIT_SUITE_TIMEOUT_SECONDS,
        ),
        run_check(
            key="io_integration",
            label="Real-Data IO Integration",
            category="io",
            command=(
                f"{POETRY_RUN} pytest --capture=sys "
                "tests/integration/io/test_io_integration.py -q"
            ),
            ui=False,
            validator=validate_pytest_like,
        ),
    ]
    if include_slow_checks:
        checks.insert(
            2,
            run_check(
                key="mypy_type_check",
                label="Mypy Type Check",
                category="quality",
                command=f"{POETRY_RUN} mypy XBrainLab/",
                ui=False,
                validator=lambda code, output: validate_text_command(
                    code,
                    output,
                    success_fallback="mypy passed.",
                ),
            ),
        )
    if include_handoff_checks:
        checks.extend(_build_handoff_dataset_checks())
    return checks


def _build_handoff_dataset_checks() -> list[CheckResult]:
    """Build mandatory public-data checks for a human-handoff candidate."""
    return [
        run_check(
            key="required_public_fixture_manifest",
            label="Required Public Fixture Manifest",
            category="io",
            command=(
                f"{POETRY_PYTHON} scripts/dev/fetch_public_eeg_fixtures.py "
                "--profile required-ci --verify-only"
            ),
            ui=False,
            validator=lambda code, output: validate_text_command(
                code,
                output,
                success_fallback="Required public fixture manifest verified.",
            ),
        ),
        run_check(
            key="required_dataset_validation_matrix",
            label="Required Dataset Validation Matrix",
            category="io",
            command=(
                f"{POETRY_PYTHON} "
                "scripts/dev/report_dataset_validation_matrix.py "
                "--strict --format json"
            ),
            ui=False,
            validator=lambda code, output: validate_text_command(
                code,
                output,
                success_fallback="Required dataset validation matrix passed.",
            ),
            timeout_seconds=900,
        ),
        run_check(
            key="required_data_interpretation_matrix",
            label="Required Data Interpretation Matrix",
            category="io",
            command=(
                f"{POETRY_PYTHON} "
                "scripts/dev/report_data_interpretation_format_matrix.py "
                "--strict --format json --write-artifacts"
            ),
            ui=False,
            validator=lambda code, output: validate_text_command(
                code,
                output,
                success_fallback="Required Data Interpretation matrix passed.",
            ),
            timeout_seconds=900,
        ),
        run_check(
            key="required_public_dataset_integration",
            label="Required Public Dataset Integration",
            category="io",
            command=(
                f"{POETRY_PYTHON} -m scripts.dev.run_required_pytest_gate -- "
                "--capture=sys "
                f"{' '.join(REQUIRED_PUBLIC_IO_TEST_NODES)} "
                "tests/integration/io/test_public_bids_fixture.py "
                "tests/integration/pipeline/"
                "test_public_cross_source_training_smoke.py -q"
            ),
            ui=False,
            validator=validate_required_pytest_matrix,
            timeout_seconds=1200,
        ),
        run_check(
            key="required_public_cross_source_smoke",
            label="Required Public Cross-Source Smoke",
            category="io",
            command=(
                f"{POETRY_PYTHON} "
                "scripts/dev/run_public_cross_source_training_smoke.py "
                "--format json --strict"
            ),
            ui=False,
            validator=lambda code, output: validate_text_command(
                code,
                output,
                success_fallback="Required public cross-source smoke passed.",
            ),
            timeout_seconds=1200,
        ),
    ]


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI args for the dashboard updater."""
    parser = argparse.ArgumentParser(
        description="Refresh the XBrainLab quality dashboard."
    )
    parser.add_argument(
        "--skip-if-fresh-minutes",
        type=int,
        default=0,
        help="Skip execution when the latest dashboard is newer than this age.",
    )
    parser.add_argument(
        "--include-slow-checks",
        action="store_true",
        help="Include slower full-repo checks such as mypy in addition to the default fast dashboard checks.",
    )
    parser.add_argument(
        "--handoff",
        action="store_true",
        help=(
            "Run the handoff dashboard summary, including strict hash-pinned "
            "multi-dataset gates. Manifest sections 3-6 require separate evidence."
        ),
    )
    parser.add_argument(
        "--expected-branch",
        default=None,
        help=(
            "Branch identity required by the handoff traceability check. "
            "Defaults to the current checkout; the full handoff manifest passes "
            "and verifies its candidate branch separately."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Write latest.json, latest.md, and history.jsonl to this directory. "
            "The handoff profile requires a git-ignored or external path scoped "
            "by the exact commit SHA."
        ),
    )
    parser.add_argument(
        "--resource-calibration-path",
        type=Path,
        default=None,
        help=(
            "Calibration artifact to validate. Handoff requires an explicit "
            "Git-ignored path scoped by the current full commit SHA."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Refresh the dashboard unless it is still fresh enough."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    include_slow_checks = bool(args.include_slow_checks or args.handoff)
    profile = "handoff" if args.handoff else ("full" if include_slow_checks else "fast")
    git_state = collect_git_state()
    handoff_expected_branch = args.expected_branch or git_state.branch
    traceability = workspace_traceability_check(
        git_state,
        fail_on_unprotected_dirty=bool(args.handoff),
        expected_branch=handoff_expected_branch if args.handoff else None,
        require_upstream_sync=bool(args.handoff),
    )
    if not args.handoff and latest_is_fresh(
        args.skip_if_fresh_minutes,
        profile=profile,
        git_state=git_state,
    ):
        print(
            f"Quality dashboard is fresh enough; skipping refresh (threshold: {args.skip_if_fresh_minutes} minutes)."
        )
        return 0

    preflight_checks = [traceability]
    output_contract = (
        handoff_output_contract_check(args.output_dir, commit=git_state.commit)
        if args.handoff
        else None
    )
    report_output_dir = args.output_dir
    if output_contract is not None and output_contract.status == "fail":
        report_output_dir = None
    if output_contract is not None and traceability.status != "fail":
        preflight_checks.append(output_contract)

    if args.handoff and any(check.status == "fail" for check in preflight_checks):
        checks = preflight_checks
        git_state_after = collect_git_state()
    else:
        checks = build_checks_for_mode(
            include_slow_checks=include_slow_checks,
            include_handoff_checks=bool(args.handoff),
            resource_calibration_path=args.resource_calibration_path,
            calibration_commit=git_state.commit,
        )
        checks[0:0] = preflight_checks
        git_state_after = collect_git_state()
        checks.append(source_stability_check(git_state, git_state_after))
    generated_at = datetime.now(UTC).isoformat()
    report = {
        "generated_at": generated_at,
        "profile": profile,
        "workspace": str(ROOT),
        "git": git_state.as_report_dict(),
        "git_before": git_state.as_report_dict(),
        "git_after": git_state_after.as_report_dict(),
        "evidence_output_dir": (
            str(report_output_dir.expanduser().resolve())
            if report_output_dir is not None
            else str(QUALITY_DIR)
        ),
        "overall_status": compute_overall_status(checks),
        "checks": [asdict(check) for check in checks],
    }
    if args.handoff:
        report["handoff_manifest"] = {
            "schema_version": 1,
            "role": "dashboard_summary",
            "certifies_full_manifest": False,
            "externally_required_sections": list(HANDOFF_EXTERNAL_MANIFEST_SECTIONS),
            "ordered_sections": list(range(1, 9)),
            "dashboard_clean_last": True,
            "expected_branch": handoff_expected_branch,
            "requires_upstream_sync": True,
        }
    if report_output_dir is None:
        write_report(report)
        report_path = LATEST_MD
    else:
        write_report(report, output_dir=report_output_dir)
        report_path = report_output_dir / "latest.md"
    print(f"Updated quality dashboard at {report_path}")
    print(f"Overall dashboard status: {report['overall_status'].upper()}")
    return 0 if report["overall_status"] != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
