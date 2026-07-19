#!/usr/bin/env python3
"""
Test runner script for XBrainLab.
Provides functions referenced in pyproject.toml for running specific subsets of tests.
"""

import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

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
INTEGRATION_SHARDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("agent", ("tests/integration/agent",)),
    ("backend", ("tests/integration/backend",)),
    ("controller", ("tests/integration/controller",)),
    ("debug", ("tests/integration/debug",)),
    ("io", ("tests/integration/io",)),
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
    """Run pytest with given arguments."""
    python_cmd = [sys.executable, "-m", "pytest", *args]
    prlimit = shutil.which("prlimit") if os.name == "posix" else None
    cmd = [prlimit, "--core=0", "--", *python_cmd] if prlimit else python_cmd
    print(f"Running: {' '.join(cmd)}")
    timeout_seconds = int(
        os.environ.get(
            "XBL_TEST_SHARD_TIMEOUT_SECONDS",
            str(DEFAULT_SHARD_TIMEOUT_SECONDS),
        )
    )
    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        print(
            f"Test shard exceeded {timeout_seconds} seconds.",
            file=sys.stderr,
        )
        return 124
    return result.returncode


def _run_one_or_exit(args: Sequence[str]) -> None:
    raise SystemExit(run_pytest(args))


def backend() -> None:
    """Run backend unit tests."""
    print("Running Backend Tests...")
    # Using Agg backend to prevent UI issues if code accidentally imports
    # matplotlib.pyplot
    os.environ["MPLBACKEND"] = "Agg"
    _run_one_or_exit(["tests/unit/backend"])


def ui() -> None:
    """Run UI unit tests."""
    print("Running UI Tests...")
    configure_headless_ui_env()
    _run_one_or_exit(["--capture=sys", "tests/unit/ui"])


def run_llm_tests() -> None:
    """Run LLM unit tests."""
    print("Running LLM Tests...")
    _run_one_or_exit(["tests/unit/llm"])


def run_remote_tests() -> None:
    """
    Run tests suitable for remote/headless environment (skips UI that requires
    display).
    """
    print("Running Remote/Headless Tests (Backend + LLM)...")
    os.environ["MPLBACKEND"] = "Agg"
    # Run everything except the 'ui' directory or specific known failing files
    # For now, we explicitly run backend and llm.
    # If there are integration tests that are safe, those should be added too.
    _run_one_or_exit(["tests/unit/backend", "tests/unit/llm"])


def unit() -> None:
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
    )


def integration() -> None:
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
    )


def regression() -> None:
    """Run regression tests in their own process."""
    configure_headless_ui_env()
    _run_shards(
        gate_name="Regression",
        shards=REGRESSION_SHARDS,
    )


def mcp_compatibility() -> None:
    """Run historical MCP compatibility checks outside the active product gate."""
    configure_headless_ui_env()
    _run_shards(
        gate_name="MCP compatibility",
        shards=MCP_COMPATIBILITY_SHARDS,
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
            )
        )
    return tuple(args)


def _run_shards(
    *,
    gate_name: str,
    shards: Sequence[tuple[str, tuple[str, ...]]],
) -> None:
    """Run all declared test paths without sharing native-library state."""
    failures: list[tuple[str, int]] = []

    for label, paths in shards:
        if not paths:
            continue
        print(f"\n=== {gate_name} shard: {label} ===", flush=True)
        return_code = run_pytest(
            (
                "--capture=sys",
                *paths,
                "-q",
                *_shard_runtime_args(gate_name=gate_name, label=label),
            )
        )
        if return_code:
            failures.append((label, return_code))

    if failures:
        formatted = ", ".join(
            f"{label} (exit {return_code})" for label, return_code in failures
        )
        print(f"\n{gate_name} gate failed: {formatted}", file=sys.stderr)
        raise SystemExit(1)

    print(f"\n{gate_name} gate passed in isolated domain processes.")


def all_tests() -> None:
    """Run every test family in isolated processes."""
    print("Running All Tests...")
    unit()
    integration()
    regression()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "backend":
            backend()
        elif command == "ui":
            ui()
        elif command == "llm":
            run_llm_tests()
        elif command == "remote":
            run_remote_tests()
        elif command == "unit":
            unit()
        elif command == "integration":
            integration()
        elif command == "regression":
            regression()
        elif command == "mcp-compatibility":
            mcp_compatibility()
        elif command == "all":
            all_tests()
        else:
            print(f"Unknown command: {command}")
            print(
                "Available commands: backend, ui, llm, remote, unit, "
                "integration, regression, mcp-compatibility, all"
            )
            sys.exit(1)
    else:
        all_tests()
