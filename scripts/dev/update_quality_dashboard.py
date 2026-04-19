#!/usr/bin/env python3
"""Generate a lightweight quality dashboard for the current workspace."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from scripts.dev.capture_ui_baseline import CAPTURE_STEPS, is_nearly_black


ROOT = Path(__file__).resolve().parents[2]
QUALITY_DIR = ROOT / "artifacts" / "quality"
LATEST_JSON = QUALITY_DIR / "latest.json"
LATEST_MD = QUALITY_DIR / "latest.md"
HISTORY_JSONL = QUALITY_DIR / "history.jsonl"
EXPECTED_UI_ARTIFACTS = [filename for filename, _ in CAPTURE_STEPS]
POETRY = "/home/administrator/.local/bin/poetry"
UI_WRAPPER = str(ROOT / "scripts" / "dev" / "run_ui_pytest.sh")
DEFAULT_FRESH_MINUTES = 60


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


def configure_headless_env(*, ui: bool) -> dict[str, str]:
    """Return a process env suitable for unattended workspace checks."""
    env = os.environ.copy()
    env.setdefault("MPLBACKEND", "Agg")
    env.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-codex")
    Path(env["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)
    if ui:
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
    return env


def extract_pytest_summary(output: str) -> str:
    """Return the most useful pytest summary line available."""
    summary_pattern = re.compile(r"(passed|failed|error|skipped|warnings?)", re.IGNORECASE)
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


def compute_overall_status(checks: list[CheckResult]) -> str:
    """Collapse all check statuses into one overall state."""
    statuses = {check.status for check in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def validate_ui_artifacts(artifacts_dir: Path) -> tuple[str, str]:
    """Validate that the expected UI artifacts exist and are not black."""
    missing = [name for name in EXPECTED_UI_ARTIFACTS if not (artifacts_dir / name).exists()]
    if missing:
        return "fail", f"Missing UI artifacts: {', '.join(missing)}"

    unusable = [name for name in EXPECTED_UI_ARTIFACTS if is_nearly_black(artifacts_dir / name)]
    if unusable:
        return "fail", f"Nearly black UI artifacts: {', '.join(unusable)}"

    return "pass", f"{len(EXPECTED_UI_ARTIFACTS)} UI artifacts look usable."


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
        summary = extract_pytest_summary(output) if "pytest" in command else "Command passed."
        status = "pass"
    else:
        summary = extract_pytest_summary(output) if "pytest" in command else f"Command failed with exit code {completed.returncode}."
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
    summary = extract_pytest_summary(output)
    return ("pass", summary) if returncode == 0 else ("fail", summary)


def ensure_quality_dir() -> None:
    """Create the output directory for dashboard files."""
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)


def latest_is_fresh(max_age_minutes: int) -> bool:
    """Return True when the latest report is newer than the requested age."""
    if max_age_minutes <= 0 or not LATEST_JSON.exists():
        return False
    payload = json.loads(LATEST_JSON.read_text(encoding="utf-8"))
    generated_at = datetime.fromisoformat(payload["generated_at"])
    age_seconds = (datetime.now(UTC) - generated_at).total_seconds()
    return age_seconds < max_age_minutes * 60


def render_markdown(report: dict) -> str:
    """Render a human-readable dashboard markdown file."""
    status_icons = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
    checks = report["checks"]
    lines = [
        "# XBrainLab Quality Dashboard",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Overall status: `{report['overall_status'].upper()}`",
        f"- Workspace: `{report['workspace']}`",
        "",
        "## Summary",
        "",
        "| Check | Status | Duration | Summary |",
        "| --- | --- | ---: | --- |",
    ]
    for check in checks:
        lines.append(
            f"| {check['label']} | `{status_icons[check['status']]}` | `{check['duration_seconds']:.2f}s` | {check['summary']} |"
        )

    lines.extend(
        [
            "",
            "## UI Artifacts",
            "",
            "Expected artifacts:",
            "",
        ]
    )
    for filename in EXPECTED_UI_ARTIFACTS:
        lines.append(f"- `artifacts/ui/{filename}`")

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
    LATEST_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    LATEST_MD.write_text(render_markdown(report), encoding="utf-8")
    with HISTORY_JSONL.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False) + "\n")


def build_checks() -> list[CheckResult]:
    """Run the current dashboard check set."""
    return [
        run_check(
            key="startup_smoke",
            label="Startup Smoke",
            category="runtime",
            command=f"timeout 25s xvfb-run -a {POETRY} run python run.py",
            ui=True,
            validator=validate_startup,
        ),
        run_check(
            key="ui_baseline_capture",
            label="UI Baseline Capture",
            category="ui",
            command=f"xvfb-run -a {POETRY} run python scripts/dev/capture_ui_baseline.py",
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
            command=f"{POETRY} run pytest tests/integration/io/test_io_integration.py -q",
            ui=False,
        ),
    ]


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI args for the dashboard updater."""
    parser = argparse.ArgumentParser(description="Refresh the XBrainLab quality dashboard.")
    parser.add_argument(
        "--skip-if-fresh-minutes",
        type=int,
        default=0,
        help="Skip execution when the latest dashboard is newer than this age.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Refresh the dashboard unless it is still fresh enough."""
    args = parse_args(argv or sys.argv[1:])
    if latest_is_fresh(args.skip_if_fresh_minutes):
        print(
            f"Quality dashboard is fresh enough; skipping refresh (threshold: {args.skip_if_fresh_minutes} minutes)."
        )
        return 0

    checks = build_checks()
    generated_at = datetime.now(UTC).isoformat()
    report = {
        "generated_at": generated_at,
        "workspace": str(ROOT),
        "overall_status": compute_overall_status(checks),
        "checks": [asdict(check) for check in checks],
    }
    write_report(report)
    print(f"Updated quality dashboard at {LATEST_MD}")
    print(f"Overall status: {report['overall_status'].upper()}")
    return 0 if report["overall_status"] != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
