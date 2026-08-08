#!/usr/bin/env python3
"""
Test runner script for XBrainLab.
Provides functions referenced in pyproject.toml for running specific subsets of tests.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.dev.owned_process_group import spawn_owned_process, terminate_and_collect
from scripts.dev.pytest_completion_attestation import (
    REQUIRED_PYTEST_RUNNER_ID,
    SHARDED_PYTEST_RUNNER_ID,
    aggregate_counts,
    build_attestation,
    validate_attestation,
    write_attestation,
)
from scripts.dev.run_required_pytest_gate import (
    OPTIONAL_PUBLIC_FIXTURE_SKIP_MARKER,
)
from scripts.dev.test_runtime_paths import (
    configure_test_temp_root,
    matplotlib_cache_root,
)

UNIT_SHARDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("backend", ("tests/unit/backend",)),
    ("llm", ("tests/unit/llm",)),
    ("developer-scripts", ("tests/unit/scripts",)),
    ("ui", ("tests/unit/ui",)),
)
UI_UNIT_ROOT_TESTS = tuple(
    str(path) for path in sorted(Path("tests/unit/ui").glob("test_*.py"))
)
UI_UNIT_SHARDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("root-contracts", UI_UNIT_ROOT_TESTS),
    ("chat", ("tests/unit/ui/chat",)),
    ("components", ("tests/unit/ui/components",)),
    ("core", ("tests/unit/ui/core",)),
    ("dataset", ("tests/unit/ui/dataset",)),
    ("dialogs", ("tests/unit/ui/dialogs",)),
    ("preprocess", ("tests/unit/ui/preprocess",)),
    ("styles", ("tests/unit/ui/styles",)),
    ("training", ("tests/unit/ui/training",)),
    ("visualization", ("tests/unit/ui/visualization",)),
)
INTEGRATION_SHARDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("agent", ("tests/integration/agent",)),
    ("backend", ("tests/integration/backend",)),
    ("controller", ("tests/integration/controller",)),
    ("debug", ("tests/integration/debug",)),
    ("io", ("tests/integration/io",)),
    ("llm", ("tests/integration/llm",)),
    ("pipeline", ("tests/integration/pipeline",)),
    ("training", ("tests/integration/training",)),
    ("ui", ("tests/integration/ui",)),
)
MCP_COMPATIBILITY_SHARDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("unit", ("tests/unit/mcp",)),
    ("integration", ("tests/integration/mcp",)),
)
REGRESSION_SHARDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("regression", ("tests/regression",)),
)
DEFAULT_SHARD_TIMEOUT_SECONDS = 1200
ROOT = Path(__file__).resolve().parents[2]
PYTEST_ALLOWED_SKIP_MARKERS = (OPTIONAL_PUBLIC_FIXTURE_SKIP_MARKER,)


@dataclass(frozen=True)
class AttestedPytestRun:
    """One isolated shard process and its verified completion artifact."""

    return_code: int
    attestation: dict[str, Any] | None


def configure_headless_ui_env() -> None:
    """Set deterministic env vars for unattended/headless Qt test runs."""
    repo_root = Path(__file__).resolve().parents[2]
    test_temp_root = configure_test_temp_root(repo_root)
    matplotlib_cache_dir = matplotlib_cache_root(test_temp_root)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("MPLBACKEND", "Agg")
    os.environ["MPLCONFIGDIR"] = str(matplotlib_cache_dir)
    matplotlib_cache_dir.mkdir(parents=True, exist_ok=True)


def run_pytest(args: Sequence[str]) -> int:
    """Run pytest through the source-controlled attesting wrapper."""
    return run_pytest_attested(args).return_code


def _required_pytest_command(result_path: Path, args: Sequence[str]) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "scripts.dev.run_required_pytest_gate",
        "--result-json",
        str(result_path),
    ]
    for marker in PYTEST_ALLOWED_SKIP_MARKERS:
        command.extend(("--allow-skip-marker", marker))
    command.extend(("--", *args))
    return command


def run_pytest_attested(args: Sequence[str]) -> AttestedPytestRun:
    """Run one shard and fail closed unless its wrapper returns evidence."""
    attestation_dir = ROOT / "build" / "tmp" / "pytest-attestations"
    attestation_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=attestation_dir,
        prefix="shard-",
        suffix=".json",
        delete=True,
    ) as handle:
        result_path = Path(handle.name)
    python_cmd = _required_pytest_command(result_path, args)
    prlimit = shutil.which("prlimit") if os.name == "posix" else None
    cmd = [prlimit, "--core=0", "--", *python_cmd] if prlimit else python_cmd
    print(f"Running: {' '.join(cmd)}")
    timeout_seconds = int(
        os.environ.get(
            "XBL_TEST_SHARD_TIMEOUT_SECONDS",
            str(DEFAULT_SHARD_TIMEOUT_SECONDS),
        )
    )
    process, owner = spawn_owned_process(
        cmd,
        cwd=ROOT,
    )
    timed_out = False
    try:
        process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        terminate_and_collect(process, owner)
    finally:
        owner.close()
    if timed_out:
        print(
            f"Test shard exceeded {timeout_seconds} seconds.",
            file=sys.stderr,
        )
        return AttestedPytestRun(return_code=124, attestation=None)
    return_code = int(process.returncode)
    attestation, failure = validate_attestation(
        result_path,
        expected_runner=REQUIRED_PYTEST_RUNNER_ID,
        expected_args=args,
        expected_exit_code=return_code,
    )
    result_path.unlink(missing_ok=True)
    if failure is not None:
        print(f"Test shard evidence failed: {failure}", file=sys.stderr)
        return AttestedPytestRun(return_code=2, attestation=None)
    return AttestedPytestRun(return_code=return_code, attestation=attestation)


def _run_one_or_exit(
    args: Sequence[str],
    *,
    attestation_sink: list[dict[str, Any]] | None = None,
) -> None:
    if attestation_sink is None:
        raise SystemExit(run_pytest(args))
    execution = run_pytest_attested(args)
    if execution.attestation is not None:
        attestation_sink.append(execution.attestation)
    raise SystemExit(execution.return_code)


def backend(attestation_sink: list[dict[str, Any]] | None = None) -> None:
    """Run backend unit tests."""
    print("Running Backend Tests...")
    # Using Agg backend to prevent UI issues if code accidentally imports
    # matplotlib.pyplot
    os.environ["MPLBACKEND"] = "Agg"
    _run_one_or_exit(["tests/unit/backend"], attestation_sink=attestation_sink)


def ui(attestation_sink: list[dict[str, Any]] | None = None) -> None:
    """Run UI unit domains without sharing Qt or native-library state."""
    print("Running UI Tests...")
    configure_headless_ui_env()
    _assert_all_test_domains_declared(
        root=Path("tests/unit/ui"),
        shards=UI_UNIT_SHARDS[1:],
    )
    _run_shards(
        gate_name="UI unit",
        shards=UI_UNIT_SHARDS,
        attestation_sink=attestation_sink,
    )


def run_llm_tests(attestation_sink: list[dict[str, Any]] | None = None) -> None:
    """Run LLM unit tests."""
    print("Running LLM Tests...")
    _run_one_or_exit(["tests/unit/llm"], attestation_sink=attestation_sink)


def run_remote_tests(attestation_sink: list[dict[str, Any]] | None = None) -> None:
    """
    Run tests suitable for remote/headless environment (skips UI that requires
    display).
    """
    print("Running Remote/Headless Tests (Backend + LLM)...")
    os.environ["MPLBACKEND"] = "Agg"
    # Run everything except the 'ui' directory or specific known failing files
    # For now, we explicitly run backend and llm.
    # If there are integration tests that are safe, those should be added too.
    _run_one_or_exit(
        ["tests/unit/backend", "tests/unit/llm"],
        attestation_sink=attestation_sink,
    )


def unit(attestation_sink: list[dict[str, Any]] | None = None) -> None:
    """Run every unit-test domain in a fresh native-library process."""
    configure_headless_ui_env()
    _assert_all_test_domains_declared(
        root=Path("tests/unit"),
        shards=(*UNIT_SHARDS, MCP_COMPATIBILITY_SHARDS[0]),
    )
    root_tests = tuple(
        str(path) for path in sorted(Path("tests/unit").glob("test_*.py"))
    )
    _run_shards(
        gate_name="Unit",
        shards=(*UNIT_SHARDS, ("root-contracts", root_tests)),
        attestation_sink=attestation_sink,
    )


def integration(attestation_sink: list[dict[str, Any]] | None = None) -> None:
    """Run every integration-test domain in a fresh native-library process."""
    configure_headless_ui_env()
    _assert_all_test_domains_declared(
        root=Path("tests/integration"),
        shards=(*INTEGRATION_SHARDS, MCP_COMPATIBILITY_SHARDS[1]),
    )
    root_tests = tuple(
        str(path) for path in sorted(Path("tests/integration").glob("test_*.py"))
    )
    _run_shards(
        gate_name="Integration",
        shards=(*INTEGRATION_SHARDS, ("root-contracts", root_tests)),
        attestation_sink=attestation_sink,
    )


def regression(attestation_sink: list[dict[str, Any]] | None = None) -> None:
    """Run regression tests in their own process."""
    configure_headless_ui_env()
    _run_shards(
        gate_name="Regression",
        shards=REGRESSION_SHARDS,
        attestation_sink=attestation_sink,
    )


def mcp_compatibility(attestation_sink: list[dict[str, Any]] | None = None) -> None:
    """Run historical MCP compatibility checks outside the active product gate."""
    configure_headless_ui_env()
    _run_shards(
        gate_name="MCP compatibility",
        shards=MCP_COMPATIBILITY_SHARDS,
        attestation_sink=attestation_sink,
    )


def _assert_all_test_domains_declared(
    *,
    root: Path,
    shards: Sequence[tuple[str, tuple[str, ...]]],
) -> None:
    """Fail closed when a test-domain directory is missing from the runner."""
    declared = {
        Path(path)
        for _label, paths in shards
        for path in paths
        if Path(path).parent == root
    }
    discovered = {
        path
        for path in root.iterdir()
        if path.is_dir() and any(path.rglob("test_*.py"))
    }
    if declared == discovered:
        return

    missing = sorted(str(path) for path in discovered - declared)
    stale = sorted(str(path) for path in declared - discovered)
    details = []
    if missing:
        details.append(f"missing domains: {', '.join(missing)}")
    if stale:
        details.append(f"stale domains: {', '.join(stale)}")
    raise RuntimeError(f"{root} shard declaration mismatch ({'; '.join(details)})")


def _shard_runtime_args(*, gate_name: str, label: str) -> tuple[str, ...]:
    """Build optional CI evidence arguments without coupling tests together."""
    args: list[str] = []
    junit_dir_value = os.environ.get("XBL_TEST_JUNIT_DIR", "").strip()
    if junit_dir_value:
        junit_dir = Path(junit_dir_value)
        junit_dir.mkdir(parents=True, exist_ok=True)
        safe_gate = gate_name.lower().replace(" ", "-")
        safe_label = label.lower().replace(" ", "-")
        args.append(f"--junitxml={junit_dir / f'{safe_gate}-{safe_label}.xml'}")

    if os.environ.get("XBL_TEST_COVERAGE") == "1":
        args.extend(
            (
                "--cov=XBrainLab",
                "--cov-append",
                "--cov-report=",
                "--cov-fail-under=0",
            )
        )
    return tuple(args)


def _run_coverage_command(command: str) -> int:
    """Run one coverage lifecycle command and fail closed on tool errors."""
    args = [sys.executable, "-m", "coverage", command]
    try:
        completed = subprocess.run(  # noqa: S603 - current Python, internal command.
            args,
            cwd=ROOT,
            check=False,
        )
    except OSError as error:
        print(f"Coverage {command} failed to start: {error}", file=sys.stderr)
        return 1
    if completed.returncode:
        print(
            f"Coverage {command} failed with exit {completed.returncode}.",
            file=sys.stderr,
        )
        return 1
    return 0


def _run_shards(
    *,
    gate_name: str,
    shards: Sequence[tuple[str, tuple[str, ...]]],
    attestation_sink: list[dict[str, Any]] | None = None,
) -> None:
    """Run all declared test paths without sharing native-library state."""
    failures: list[tuple[str, int]] = []

    for label, paths in shards:
        if not paths:
            continue
        print(f"\n=== {gate_name} shard: {label} ===", flush=True)
        args = (
            "--capture=sys",
            *paths,
            "-q",
            *_shard_runtime_args(gate_name=gate_name, label=label),
        )
        if attestation_sink is None:
            return_code = run_pytest(args)
        else:
            execution = run_pytest_attested(args)
            return_code = execution.return_code
            if execution.attestation is not None:
                attestation_sink.append(execution.attestation)
        if return_code:
            failures.append((label, return_code))

    if failures:
        formatted = ", ".join(
            f"{label} (exit {return_code})" for label, return_code in failures
        )
        print(f"\n{gate_name} gate failed: {formatted}", file=sys.stderr)
        raise SystemExit(1)

    print(f"\n{gate_name} gate passed in isolated domain processes.")


def all_tests(attestation_sink: list[dict[str, Any]] | None = None) -> None:
    """Run every test family in isolated processes."""
    print("Running All Tests...")
    if attestation_sink is None:
        unit()
        integration()
        regression()
        return
    unit(attestation_sink)
    integration(attestation_sink)
    regression(attestation_sink)


def _parse_cli(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        default="all",
        choices=(
            "backend",
            "ui",
            "llm",
            "remote",
            "unit",
            "integration",
            "regression",
            "mcp-compatibility",
            "all",
        ),
    )
    parser.add_argument("--result-json", type=Path)
    parsed = parser.parse_args(list(argv))
    if parsed.result_json is None:
        configured = os.environ.get("XBL_PYTEST_RESULT_JSON", "").strip()
        parsed.result_json = Path(configured) if configured else None
    return parsed


def _dispatch(
    command: str,
    attestation_sink: list[dict[str, Any]] | None,
) -> None:
    commands = {
        "backend": backend,
        "ui": ui,
        "llm": run_llm_tests,
        "remote": run_remote_tests,
        "unit": unit,
        "integration": integration,
        "regression": regression,
        "mcp-compatibility": mcp_compatibility,
        "all": all_tests,
    }
    commands[command](attestation_sink)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one isolated suite and optionally attest aggregate completion."""
    parsed = _parse_cli(sys.argv[1:] if argv is None else argv)
    result_path: Path | None = parsed.result_json
    if result_path is not None:
        result_path.unlink(missing_ok=True)
    attestations: list[dict[str, Any]] | None = [] if result_path else None
    exit_code = 0
    coverage_enabled = os.environ.get("XBL_TEST_COVERAGE") == "1"
    if coverage_enabled:
        exit_code = _run_coverage_command("erase")
    if exit_code == 0:
        try:
            _dispatch(parsed.command, attestations)
        except SystemExit as error:
            exit_code = int(error.code or 0)
    if coverage_enabled and exit_code == 0:
        exit_code = _run_coverage_command("report")
    if result_path is not None and attestations is not None:
        write_attestation(
            result_path,
            build_attestation(
                runner=SHARDED_PYTEST_RUNNER_ID,
                command_args=(parsed.command,),
                exit_code=exit_code,
                counts=aggregate_counts(attestations),
            ),
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
