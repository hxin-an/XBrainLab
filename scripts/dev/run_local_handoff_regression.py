#!/usr/bin/env python3
"""Run the authoritative Linux test partition in two fixed local phases."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts.dev.owned_process_group import spawn_owned_process
from scripts.dev.run_tests import (
    LINUX_CI_COMMANDS,
    LINUX_CI_UNCOVERED_COMMANDS,
    verify_linux_ci_evidence,
)

ROOT = Path(__file__).resolve().parents[2]
MAX_PARALLEL_GROUPS = 2
GROUP_TIMEOUT_SECONDS = 2400
TERMINATION_GRACE_SECONDS = 5
FIXED_PHASES = (
    LINUX_CI_COMMANDS[:5],
    LINUX_CI_COMMANDS[5:],
)
if tuple(command for phase in FIXED_PHASES for command in phase) != LINUX_CI_COMMANDS:
    raise RuntimeError("Local handoff phases drifted from the Linux test partition.")


def _execute_group(command: str, *, evidence_dir: Path) -> int:
    """Run one canonical test group with process-owned temp and log paths."""
    runtime_root = evidence_dir / "runtime" / command
    temp_root = runtime_root / "tmp"
    cache_root = runtime_root / "matplotlib"
    temp_root.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    result_path = evidence_dir / f"{command}.json"
    log_path = evidence_dir / f"{command}.log"
    environment = os.environ.copy()
    environment.update(
        {
            "XBRAINLAB_TEST_TMPDIR": str(temp_root),
            "MPLCONFIGDIR": str(cache_root),
            "XBL_SHARED_CI_RUNNER": "1",
        }
    )
    for name in ("COVERAGE_PROCESS_START", "XBL_TEST_COVERAGE"):
        environment.pop(name, None)
    if command in LINUX_CI_UNCOVERED_COMMANDS:
        environment.pop("COVERAGE_FILE", None)
    else:
        environment["COVERAGE_FILE"] = str(evidence_dir / f".coverage.{command}")
    argv = (
        sys.executable,
        "-m",
        "scripts.dev.run_tests",
        command,
        "--result-json",
        str(result_path),
    )
    timed_out = False
    with log_path.open("w", encoding="utf-8") as log:
        process, owner = spawn_owned_process(
            argv,
            cwd=ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            return_code = process.wait(timeout=GROUP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            owner.signal(force=False)
            try:
                process.wait(timeout=TERMINATION_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                owner.signal(force=True)
                process.wait(timeout=TERMINATION_GRACE_SECONDS)
            return_code = 124
        finally:
            owner.close(grace_seconds=TERMINATION_GRACE_SECONDS)
    if timed_out:
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"\nGroup exceeded {GROUP_TIMEOUT_SECONDS} seconds.\n")
    return int(return_code)


def _run_phase(commands: tuple[str, ...], *, evidence_dir: Path) -> dict[str, int]:
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_GROUPS) as executor:
        futures = {
            command: executor.submit(
                _execute_group,
                command,
                evidence_dir=evidence_dir,
            )
            for command in commands
        }
        return {command: future.result() for command, future in futures.items()}


def run_local_handoff_regression(
    *,
    evidence_dir: Path,
    result_path: Path,
) -> int:
    """Execute both fixed phases and aggregate canonical pytest attestations."""
    evidence_root = evidence_dir.expanduser().resolve()
    evidence_root.mkdir(parents=True, exist_ok=False)
    result = result_path.expanduser().resolve()
    result.parent.mkdir(parents=True, exist_ok=True)
    for phase_index, commands in enumerate(FIXED_PHASES, start=1):
        print(
            f"[complete-regression] phase {phase_index}: {', '.join(commands)}",
            flush=True,
        )
        outcomes = _run_phase(commands, evidence_dir=evidence_root)
        failures = {
            command: return_code
            for command, return_code in outcomes.items()
            if return_code != 0
        }
        if failures:
            for command, return_code in failures.items():
                print(
                    f"{command} failed with exit {return_code}; see its registered log.",
                    file=sys.stderr,
                )
            verify_linux_ci_evidence(
                evidence_root,
                result,
            )
            return 1
    return verify_linux_ci_evidence(
        evidence_root,
        result,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--result-json", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    return run_local_handoff_regression(
        evidence_dir=args.evidence_dir,
        result_path=args.result_json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
