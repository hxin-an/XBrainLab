#!/usr/bin/env python3
"""Run one bounded real-app startup probe and emit a machine-readable result."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.dev.owned_process_group import spawn_owned_process, terminate_and_collect

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = 25
TERMINATION_GRACE_SECONDS = 5
INITIALIZED_MARKER = "MainWindow initialized"


def run_startup_smoke() -> dict[str, object]:
    """Launch the real entrypoint and stop only its owned process tree."""
    argv = (sys.executable, "run.py")
    process, owner = spawn_owned_process(
        argv,
        cwd=ROOT,
        env=os.environ.copy(),
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
    passed = saw_initialized and return_code in {0, 124}
    return {
        "schema_version": 1,
        "artifact_type": "xbrainlab.startup_smoke",
        "command": list(argv),
        "timeout_seconds": TIMEOUT_SECONDS,
        "timed_out": timed_out,
        "return_code": return_code,
        "saw_main_window_initialized": saw_initialized,
        "passed": passed,
        "stdout_tail": stdout[-4_000:],
        "stderr_tail": stderr[-4_000:],
    }


def main() -> int:
    result = run_startup_smoke()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
