#!/usr/bin/env python3
"""Run the authoritative Linux test partition in two fixed local phases."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import psutil

from scripts.dev.owned_process_group import spawn_owned_process
from scripts.dev.run_tests import (
    LINUX_CI_COMMANDS,
    LINUX_CI_UNCOVERED_COMMANDS,
    verify_linux_ci_evidence,
)
from scripts.dev.test_runtime_paths import select_test_temp_root

ROOT = Path(__file__).resolve().parents[2]
MAX_PARALLEL_GROUPS = 3
GROUP_TIMEOUT_SECONDS = 2400
TERMINATION_GRACE_SECONDS = 5
RESOURCE_SAMPLE_SECONDS = 0.5
FIXED_PHASES = (
    LINUX_CI_COMMANDS[:5],
    LINUX_CI_COMMANDS[5:],
)
if tuple(command for phase in FIXED_PHASES for command in phase) != LINUX_CI_COMMANDS:
    raise RuntimeError("Local handoff phases drifted from the Linux test partition.")

# Warm timings from the last accepted two-worker handoff. These values only
# determine deterministic submission order; they do not alter group membership,
# timeout, coverage, or result policy.
GROUP_SCHEDULING_WEIGHTS_SECONDS = {
    "linux-unit-backend": 212.46,
    "linux-unit-llm-agent": 96.67,
    "linux-unit-scripts": 546.67,
    "linux-unit-ui": 363.23,
    "linux-unit-rest": 250.42,
    "linux-integration-agent-timing": 42.61,
    "linux-integration-ui": 465.38,
    "linux-integration-rest": 352.45,
}
if frozenset(GROUP_SCHEDULING_WEIGHTS_SECONDS) != frozenset(LINUX_CI_COMMANDS):
    raise RuntimeError("Local handoff scheduling weights drifted from Linux groups.")


def _ordered_phase_commands(commands: tuple[str, ...]) -> tuple[str, ...]:
    """Submit longest measured groups first with source order as a tie-breaker."""
    source_order = {command: index for index, command in enumerate(commands)}
    return tuple(
        sorted(
            commands,
            key=lambda command: (
                -GROUP_SCHEDULING_WEIGHTS_SECONDS[command],
                source_order[command],
            ),
        )
    )


def _sample_process_tree(
    process: subprocess.Popen[str],
    cpu_seconds_by_pid: dict[int, float],
) -> tuple[int, int] | None:
    """Return current combined RSS/process count and retain per-PID CPU maxima."""
    pid = getattr(process, "pid", None)
    if not isinstance(pid, int):
        return None
    try:
        processes = [psutil.Process(pid), *psutil.Process(pid).children(recursive=True)]
    except (psutil.Error, OSError):
        return None
    rss_bytes = 0
    observed = 0
    for observed_process in processes:
        try:
            cpu_times = observed_process.cpu_times()
            cpu_seconds_by_pid[observed_process.pid] = max(
                cpu_seconds_by_pid.get(observed_process.pid, 0.0),
                float(cpu_times.user + cpu_times.system),
            )
            rss_bytes += int(observed_process.memory_info().rss)
            observed += 1
        except (psutil.Error, OSError):
            continue
    return rss_bytes, observed


def _write_group_telemetry(
    path: Path,
    *,
    command: str,
    return_code: int,
    timed_out: bool,
    wall_seconds: float,
    cpu_seconds_by_pid: dict[int, float],
    peak_rss_bytes: int,
    max_process_count: int,
    sampling_available: bool,
) -> None:
    payload = {
        "schema_version": 1,
        "command": command,
        "return_code": return_code,
        "timed_out": timed_out,
        "wall_seconds": round(wall_seconds, 6),
        "cpu_seconds": round(sum(cpu_seconds_by_pid.values()), 6),
        "peak_rss_bytes": peak_rss_bytes,
        "max_process_count": max_process_count,
        "sampling_available": sampling_available,
    }
    staged = path.with_suffix(path.suffix + ".tmp")
    staged.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    staged.replace(path)


def _execute_group(command: str, *, evidence_dir: Path) -> int:
    """Run one canonical test group with process-owned temp and log paths."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    result_path = evidence_dir / f"{command}.json"
    log_path = evidence_dir / f"{command}.log"
    telemetry_dir = evidence_dir / "telemetry"
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    telemetry_path = telemetry_dir / f"{command}.json"
    temp_base = select_test_temp_root(ROOT)
    temp_base.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f"handoff-{command}-", dir=temp_base) as temp_name:
        temp_root = Path(temp_name)
        cache_root = temp_root / "matplotlib"
        cache_root.mkdir(parents=True, exist_ok=True)
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
        started_at = time.monotonic()
        cpu_seconds_by_pid: dict[int, float] = {}
        peak_rss_bytes = 0
        max_process_count = 0
        sampling_available = False
        with log_path.open("w", encoding="utf-8") as log:
            process, owner = spawn_owned_process(
                argv,
                cwd=ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            deadline = started_at + GROUP_TIMEOUT_SECONDS
            try:
                while True:
                    sample = _sample_process_tree(process, cpu_seconds_by_pid)
                    if sample is not None:
                        sampling_available = True
                        rss_bytes, process_count = sample
                        peak_rss_bytes = max(peak_rss_bytes, rss_bytes)
                        max_process_count = max(max_process_count, process_count)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        owner.signal(force=False)
                        try:
                            process.wait(timeout=TERMINATION_GRACE_SECONDS)
                        except subprocess.TimeoutExpired:
                            owner.signal(force=True)
                            process.wait(timeout=TERMINATION_GRACE_SECONDS)
                        return_code = 124
                        break
                    try:
                        return_code = process.wait(
                            timeout=min(RESOURCE_SAMPLE_SECONDS, remaining)
                        )
                        break
                    except subprocess.TimeoutExpired:
                        continue
            finally:
                owner.close(grace_seconds=TERMINATION_GRACE_SECONDS)
        _write_group_telemetry(
            telemetry_path,
            command=command,
            return_code=int(return_code),
            timed_out=timed_out,
            wall_seconds=time.monotonic() - started_at,
            cpu_seconds_by_pid=cpu_seconds_by_pid,
            peak_rss_bytes=peak_rss_bytes,
            max_process_count=max_process_count,
            sampling_available=sampling_available,
        )
    if timed_out:
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"\nGroup exceeded {GROUP_TIMEOUT_SECONDS} seconds.\n")
    return int(return_code)


def _run_phase(commands: tuple[str, ...], *, evidence_dir: Path) -> dict[str, int]:
    ordered_commands = _ordered_phase_commands(commands)
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_GROUPS) as executor:
        futures = {
            command: executor.submit(
                _execute_group,
                command,
                evidence_dir=evidence_dir,
            )
            for command in ordered_commands
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
