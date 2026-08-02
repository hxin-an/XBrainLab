#!/usr/bin/env python3
"""Run the strict real-data gate used before a teacher GUI walkthrough."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.dev.fetch_public_eeg_fixtures import (
    fixture_file_is_valid,
    fixture_groups_for_profile,
    fixture_profile_size_bytes,
)
from scripts.dev.report_teacher_dataset_preflight import (
    TEACHER_FIXTURE_GROUP_COUNT,
    TEACHER_FIXTURE_PROFILE_SIZE_BYTES,
)

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIR = ROOT / "tests" / "fixtures" / "data" / "public"
DATA_ARTIFACT_DIR = ROOT / "build" / "dev-artifacts" / "teacher-data-preflight"
UI_ARTIFACT_DIR = DATA_ARTIFACT_DIR / "ui"
EVIDENCE_JSON = UI_ARTIFACT_DIR / "teacher-handoff-gate.json"
EVIDENCE_MARKDOWN = UI_ARTIFACT_DIR / "README.md"
EXPECTED_SCREENSHOTS = (
    "openneuro-match-labels-dialog.png",
    "openneuro-event-value-controls.png",
    "openneuro-review-and-import.png",
)
_PROTECTED_LOCAL_PATHS = {"settings.json"}


def verify_teacher_fixture_profile() -> dict[str, Any]:
    """Fail closed unless every exact teacher fixture byte is present."""
    groups = fixture_groups_for_profile("teacher-preflight")
    invalid_files = sorted(
        str(fixture_file["filename"])
        for group in groups
        for fixture_file in group["files"]
        if not fixture_file_is_valid(
            PUBLIC_DIR / str(fixture_file["filename"]),
            str(fixture_file["sha256"]),
            int(fixture_file["size_bytes"]),
        )
    )
    size_bytes = fixture_profile_size_bytes(groups)
    return {
        "group_count": len(groups),
        "size_bytes": size_bytes,
        "invalid_files": invalid_files,
        "ok": (
            len(groups) == TEACHER_FIXTURE_GROUP_COUNT
            and size_bytes == TEACHER_FIXTURE_PROFILE_SIZE_BYTES
            and not invalid_files
        ),
    }


def _run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: int,
) -> dict[str, Any]:
    started = time.monotonic()
    completed = subprocess.run(  # noqa: S603 - commands are fixed by this script
        command,
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "stdout_tail": completed.stdout[-4_000:],
        "stderr_tail": completed.stderr[-4_000:],
        "ok": completed.returncode == 0,
    }


def _git_output(*args: str) -> str:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise OSError("git executable is unavailable.")
    completed = subprocess.run(  # noqa: S603 - args are fixed internal queries
        [git_executable, *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    # Git porcelain output uses a leading status column. Preserve leading
    # whitespace so the first path is parsed from the same offset as later rows.
    return completed.stdout.rstrip()


def _source_dirty_paths() -> list[str]:
    paths: list[str] = []
    for line in _git_output("status", "--short").splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", maxsplit=1)[1]
        if path and path not in _PROTECTED_LOCAL_PATHS:
            paths.append(path)
    return sorted(set(paths))


def _write_evidence(snapshot: dict[str, Any]) -> None:
    UI_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_JSON.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    commands = snapshot["commands"]
    lines = [
        "# Teacher Handoff Gate",
        "",
        f"- Source commit: `{snapshot['source_commit']}`",
        f"- Strict result: `{'PASS' if snapshot['strict_ok'] else 'FAIL'}`",
        (
            "- Fixture profile: "
            f"`{snapshot['fixture_profile']['group_count']} groups / "
            f"{snapshot['fixture_profile']['size_bytes']:,} bytes`"
        ),
        "",
        "| Gate | Result | Duration |",
        "| --- | --- | ---: |",
        *[
            (
                f"| {name} | {'PASS' if result['ok'] else 'FAIL'} | "
                f"{result['duration_seconds']:.3f}s |"
            )
            for name, result in commands.items()
        ],
        "",
        "## Current UI Artifacts",
        "",
        *[f"- `{name}`" for name in snapshot["screenshots"]],
        "",
        "## Claim Boundary",
        "",
        (
            "- This gate covers the pinned teacher fixture profile, backend "
            "timing/epoch handoff, and the real Qt five-step wizard paths."
        ),
        (
            "- It does not replace human Windows DPI, remote-desktop, or "
            "teacher acceptance, and it does not certify unsupported clinical "
            "annotation sidecars."
        ),
        "",
    ]
    EVIDENCE_MARKDOWN.write_text("\n".join(lines), encoding="utf-8")


def run_gate(*, require_clean_source: bool) -> dict[str, Any]:
    source_dirty_paths = _source_dirty_paths()
    fixture_profile = verify_teacher_fixture_profile()
    if require_clean_source and source_dirty_paths:
        raise RuntimeError(
            "Teacher handoff gate requires clean product source: "
            + ", ".join(source_dirty_paths)
        )
    if not fixture_profile["ok"]:
        raise RuntimeError(
            "Teacher fixture verification failed: "
            + json.dumps(fixture_profile, sort_keys=True)
        )

    UI_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    for filename in EXPECTED_SCREENSHOTS:
        (UI_ARTIFACT_DIR / filename).unlink(missing_ok=True)

    backend = _run(
        [
            sys.executable,
            "scripts/dev/report_teacher_dataset_preflight.py",
            "--strict",
            "--format",
            "json",
            "--write-artifacts",
            "--output-dir",
            str(DATA_ARTIFACT_DIR),
        ],
        timeout_seconds=600,
    )
    gui_env = dict(os.environ)
    gui_env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "XBRAINLAB_REQUIRE_REAL_FIXTURES": "1",
            "XBRAINLAB_TEACHER_UI_ARTIFACT_DIR": str(UI_ARTIFACT_DIR),
        }
    )
    gui = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--capture=sys",
            "tests/integration/ui/test_data_import_wizard_real_fixture_acceptance.py",
            "-q",
        ],
        env=gui_env,
        timeout_seconds=900,
    )
    screenshots = sorted(
        name
        for name in EXPECTED_SCREENSHOTS
        if (UI_ARTIFACT_DIR / name).is_file()
        and (UI_ARTIFACT_DIR / name).stat().st_size > 0
    )
    snapshot = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_commit": _git_output("rev-parse", "HEAD"),
        "source_dirty_paths_before_gate": source_dirty_paths,
        "fixture_profile": fixture_profile,
        "commands": {
            "backend_timing_and_epoch": backend,
            "real_gui_workflows": gui,
        },
        "screenshots": screenshots,
        "strict_ok": (
            fixture_profile["ok"]
            and backend["ok"]
            and gui["ok"]
            and screenshots == sorted(EXPECTED_SCREENSHOTS)
        ),
    }
    _write_evidence(snapshot)
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-clean-source", action="store_true")
    args = parser.parse_args()
    try:
        snapshot = run_gate(require_clean_source=args.require_clean_source)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Teacher handoff gate failed before completion: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0 if snapshot["strict_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
