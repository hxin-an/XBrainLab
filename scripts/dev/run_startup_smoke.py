#!/usr/bin/env python3
"""Run one bounded real-app startup probe and emit a machine-readable result."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from scripts.dev.owned_process_group import spawn_owned_process, terminate_and_collect

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = 25
TERMINATION_GRACE_SECONDS = 5
INITIALIZED_MARKER = "MainWindow initialized"
CLOSE_REQUESTED_MARKER = "XBrainLab startup smoke close requested"
PLATFORM_MARKER = "XBrainLab startup smoke platform:"
STARTUP_CLOSE_DELAY_MS = "1000"


def run_startup_smoke(*, expected_platform: str | None = None) -> dict[str, object]:
    """Launch the real entrypoint and stop only its owned process tree."""
    argv = (sys.executable, "run.py")
    environment = os.environ.copy()
    environment["XBRAINLAB_STARTUP_SMOKE_CLOSE_MS"] = STARTUP_CLOSE_DELAY_MS
    process, owner = spawn_owned_process(
        argv,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        timed_out = True
        stdout, stderr = terminate_and_collect(
            process,
            owner,
            grace_seconds=TERMINATION_GRACE_SECONDS,
        )
    finally:
        owner.close(grace_seconds=TERMINATION_GRACE_SECONDS)
    return_code = 124 if timed_out else int(process.returncode or 0)
    saw_initialized = INITIALIZED_MARKER in f"{stdout}\n{stderr}"
    combined_output = f"{stdout}\n{stderr}"
    saw_close_requested = CLOSE_REQUESTED_MARKER in combined_output
    platform_match = re.search(
        rf"{re.escape(PLATFORM_MARKER)}\s*([^\s]+)", combined_output
    )
    qt_platform = platform_match.group(1) if platform_match is not None else ""
    platform_matches = expected_platform is None or qt_platform == expected_platform
    passed = (
        saw_initialized
        and saw_close_requested
        and bool(qt_platform)
        and platform_matches
        and not timed_out
        and return_code == 0
    )
    return {
        "schema_version": 1,
        "artifact_type": "xbrainlab.startup_smoke",
        "command": list(argv),
        "timeout_seconds": TIMEOUT_SECONDS,
        "timed_out": timed_out,
        "return_code": return_code,
        "saw_main_window_initialized": saw_initialized,
        "saw_close_requested": saw_close_requested,
        "qt_platform": qt_platform,
        "expected_qt_platform": expected_platform,
        "passed": passed,
        "stdout_tail": stdout[-4_000:],
        "stderr_tail": stderr[-4_000:],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-platform")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = run_startup_smoke(expected_platform=args.expected_platform)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
