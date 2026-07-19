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
UI_WRAPPER = str(ROOT / "scripts" / "dev" / "run_ui_pytest.sh")
DEFAULT_FRESH_MINUTES = 60
MAX_UI_MEAN_DIFF = 1.5
MAX_UI_CHANGED_RATIO = 0.02
PIXEL_DIFF_THRESHOLD = 12
RESOURCE_CALIBRATION_PATH = ROOT / "artifacts" / "resource_guard" / "calibration.json"
PROTECTED_LOCAL_CONFIG_PATHS = frozenset({"settings.json"})


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
    worktree_fingerprint: str = "unavailable"
    protected_local_changes: tuple[str, ...] = ()

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
            "worktree_fingerprint": self.worktree_fingerprint,
            "protected_local_changes": list(self.protected_local_changes),
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
    summary_pattern = re.compile(
        r"(passed|failed|error|skipped|warnings?)", re.IGNORECASE
    )
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if stripped and summary_pattern.search(stripped):
            return stripped
    return "No pytest summary line found."


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


def _git_output(args: list[str]) -> str:
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
    return completed.stdout.rstrip("\r\n") or "unknown"


def collect_git_state() -> GitState:
    """Return branch/commit/dirty metadata for the generated dashboard."""
    branch = _git_output(["branch", "--show-current"])
    commit = _git_output(["rev-parse", "--short=12", "HEAD"])
    status_output = _git_output(["status", "--short"])
    full_status = [] if status_output == "unknown" else status_output.splitlines()
    protected_local_changes = tuple(
        path
        for entry in full_status
        if (path := _status_entry_path(entry)) in PROTECTED_LOCAL_CONFIG_PATHS
    )
    return GitState(
        branch=branch,
        commit=commit,
        dirty=bool(full_status),
        status_summary=full_status[:40],
        dirty_count=len(full_status),
        status_truncated=len(full_status) > 40,
        worktree_fingerprint=_worktree_fingerprint(ROOT),
        protected_local_changes=protected_local_changes,
    )


def _status_entry_path(entry: str) -> str:
    """Extract a path from one human-readable porcelain-v1 status entry."""
    payload = entry[3:] if len(entry) > 3 else ""
    if " -> " in payload:
        payload = payload.rsplit(" -> ", maxsplit=1)[1]
    return payload.strip().strip('"')


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
        ":(exclude,literal)settings.json",
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


def workspace_traceability_check(git_state: GitState) -> CheckResult:
    """Return a non-command check that marks dirty release evidence as not clean."""
    if not git_state.dirty:
        status = "pass"
        summary = f"Clean worktree at {git_state.commit}."
    elif git_state.unprotected_dirty_count == 0:
        status = "pass"
        paths = ", ".join(git_state.protected_local_changes)
        summary = (
            "Tracked source is clean; declared local configuration remains "
            f"visible and unstaged: {paths}."
        )
    else:
        status = "warn"
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
        returncode=0,
        summary=summary,
        output_excerpt="\n".join(git_state.status_summary),
    )


def resource_calibration_evidence_check() -> CheckResult:
    """Require current, complete strict CUDA calibration evidence."""
    command = (
        "poetry run python scripts/dev/calibrate_resource_guard.py --strict "
        "--output artifacts/resource_guard/calibration.json"
    )
    if not RESOURCE_CALIBRATION_PATH.is_file():
        failures = ["resource calibration artifact is missing"]
    else:
        try:
            payload = json.loads(RESOURCE_CALIBRATION_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures = [f"resource calibration artifact is unreadable: {exc}"]
        else:
            failures = strict_calibration_failure_reasons(
                payload,
                repo_root=ROOT,
                validate_source=True,
                validate_freshness=True,
            )
    status = "fail" if failures else "pass"
    summary = (
        "; ".join(failures[:3])
        if failures
        else "Resource guard strict calibration evidence is current."
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
) -> CheckResult:
    """Run a command and normalize the result into dashboard format."""
    started = time.monotonic()
    env = configure_headless_env(ui=ui)
    completed = subprocess.run(  # noqa: S603
        shlex.split(command),
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    duration = time.monotonic() - started
    output = (completed.stdout or "") + (completed.stderr or "")
    excerpt = summarize_output(output)

    if validator is not None:
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


def validate_required_pytest_matrix(returncode: int, output: str) -> tuple[str, str]:
    """Require every case in a mandatory pytest matrix to execute and pass."""
    status, summary = validate_pytest_like(returncode, output)
    if status != "pass":
        return status, summary
    incomplete = re.search(
        r"\b\d+\s+(?:skipped|deselected|xfailed|xpassed)\b",
        output,
        flags=re.IGNORECASE,
    )
    if incomplete:
        return "fail", f"Required pytest matrix was incomplete: {summary}"
    if not re.search(r"\b\d+\s+passed\b", output, flags=re.IGNORECASE):
        return "fail", "Required pytest matrix reported no passing cases."
    return "pass", summary


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
    if bool(payload_git.get("dirty")) != current_git.dirty:
        return False
    if int(payload_git.get("dirty_count") or 0) != current_git.dirty_count:
        return False
    if bool(payload_git.get("status_truncated")) != current_git.status_truncated:
        return False
    payload_fingerprint = str(payload_git.get("worktree_fingerprint") or "")
    if (
        payload_fingerprint in {"", "unavailable"}
        or current_git.worktree_fingerprint in {"", "unavailable"}
        or payload_fingerprint != current_git.worktree_fingerprint
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
        f"- Overall status: `{report['overall_status'].upper()}`",
        f"- Workspace: `{report['workspace']}`",
    ]
    git = report.get("git")
    if isinstance(git, dict):
        lines.extend(
            [
                f"- Git branch: `{git.get('branch', 'unknown')}`",
                f"- Git commit: `{git.get('commit', 'unknown')}`",
                f"- Dirty worktree: `{'yes' if git.get('dirty') else 'no'}`",
                f"- Worktree fingerprint: "
                f"`{git.get('worktree_fingerprint', 'unavailable')}`",
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


def write_report(report: dict) -> None:
    """Write the latest dashboard files and append to history."""
    ensure_quality_dir()
    LATEST_JSON.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    LATEST_MD.write_text(render_markdown(report), encoding="utf-8")
    with HISTORY_JSONL.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False) + "\n")


def build_checks() -> list[CheckResult]:
    """Run the current dashboard check set."""
    return build_checks_for_mode(include_slow_checks=False)


def build_checks_for_mode(*, include_slow_checks: bool) -> list[CheckResult]:
    """Run the dashboard checks for the requested speed profile."""
    checks = [
        resource_calibration_evidence_check(),
        run_check(
            key="ruff_lint",
            label="Ruff Lint",
            category="quality",
            command=f"{POETRY} run ruff check .",
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
            command=f"{POETRY} run basedpyright",
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
            command=f"{POETRY} run python tests/architecture_compliance.py",
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
                f"{POETRY} run python run.py"
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
                f"{POETRY} run python scripts/dev/capture_ui_baseline.py"
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
            validator=validate_pytest_like,
        ),
        run_check(
            key="public_bids_visible_ui_wizard_format_matrix",
            label="Public BIDS Visible UI Wizard Format Matrix",
            category="ui",
            command=(
                f"{POETRY} run pytest --capture=sys "
                "tests/integration/ui/test_data_import_wizard_format_matrix.py -q"
            ),
            ui=True,
            validator=validate_required_pytest_matrix,
        ),
        run_check(
            key="ui_unit_suite",
            label="UI Unit Suite",
            category="ui",
            command=f"{POETRY} run python scripts/dev/run_tests.py ui",
            ui=True,
            validator=validate_pytest_like,
        ),
        run_check(
            key="io_integration",
            label="Real-Data IO Integration",
            category="io",
            command=(
                f"{POETRY} run pytest --capture=sys "
                "tests/integration/io/test_io_integration.py -q"
            ),
            ui=False,
        ),
    ]
    if include_slow_checks:
        checks.insert(
            2,
            run_check(
                key="mypy_type_check",
                label="Mypy Type Check",
                category="quality",
                command=f"{POETRY} run mypy XBrainLab/",
                ui=False,
                validator=lambda code, output: validate_text_command(
                    code,
                    output,
                    success_fallback="mypy passed.",
                ),
            ),
        )
    return checks


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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Refresh the dashboard unless it is still fresh enough."""
    args = parse_args(argv or sys.argv[1:])
    profile = "full" if args.include_slow_checks else "fast"
    git_state = collect_git_state()
    if latest_is_fresh(
        args.skip_if_fresh_minutes,
        profile=profile,
        git_state=git_state,
    ):
        print(
            f"Quality dashboard is fresh enough; skipping refresh (threshold: {args.skip_if_fresh_minutes} minutes)."
        )
        return 0

    checks = build_checks_for_mode(include_slow_checks=args.include_slow_checks)
    checks.insert(0, workspace_traceability_check(git_state))
    generated_at = datetime.now(UTC).isoformat()
    report = {
        "generated_at": generated_at,
        "profile": profile,
        "workspace": str(ROOT),
        "git": git_state.as_report_dict(),
        "overall_status": compute_overall_status(checks),
        "checks": [asdict(check) for check in checks],
    }
    write_report(report)
    print(f"Updated quality dashboard at {LATEST_MD}")
    print(f"Overall status: {report['overall_status'].upper()}")
    return 0 if report["overall_status"] != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
