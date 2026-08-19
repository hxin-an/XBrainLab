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

LLM_UNIT_ROOT_TESTS = tuple(
    path.as_posix() for path in sorted(Path("tests/unit/llm").glob("test_*.py"))
)
UNIT_ROOT_TESTS = tuple(
    path.as_posix() for path in sorted(Path("tests/unit").glob("test_*.py"))
)
INTEGRATION_ROOT_TESTS = tuple(
    path.as_posix() for path in sorted(Path("tests/integration").glob("test_*.py"))
)
INTEGRATION_AGENT_TIMING_TESTS = (
    "tests/integration/agent/test_long_session_product_flow.py",
)
INTEGRATION_AGENT_COVERED_TESTS = tuple(
    path.as_posix()
    for path in sorted(Path("tests/integration/agent").glob("test_*.py"))
    if path.as_posix() not in INTEGRATION_AGENT_TIMING_TESTS
)
LLM_UNIT_SHARDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("root-contracts", LLM_UNIT_ROOT_TESTS),
    ("agent", ("tests/unit/llm/agent",)),
    ("core", ("tests/unit/llm/core",)),
    ("rag", ("tests/unit/llm/rag",)),
    ("tools", ("tests/unit/llm/tools",)),
)
UNIT_DOMAIN_SHARDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("backend", ("tests/unit/backend",)),
    ("llm", ("tests/unit/llm",)),
    ("developer-scripts", ("tests/unit/scripts",)),
    ("ui", ("tests/unit/ui",)),
)
UI_UNIT_ROOT_TESTS = tuple(
    path.as_posix() for path in sorted(Path("tests/unit/ui").glob("test_*.py"))
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
UNIT_SHARDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    UNIT_DOMAIN_SHARDS[0],
    *((f"llm-{label}", paths) for label, paths in LLM_UNIT_SHARDS),
    UNIT_DOMAIN_SHARDS[2],
    *((f"ui-{label}", paths) for label, paths in UI_UNIT_SHARDS),
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
REGRESSION_SHARDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("regression", ("tests/regression",)),
)
PLATFORM_SHARDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "portability-contracts",
        (
            "tests/regression/test_test_temp_location.py",
            "tests/unit/test_config.py",
            "tests/unit/backend/application/test_import_boundaries.py",
            "tests/unit/backend/application/test_label_resource_admission.py",
            "tests/unit/backend/training/record/test_output_path_policy.py",
            "tests/unit/backend/training/record/test_safe_artifact_store.py",
            "tests/unit/backend/utils/test_filesystem_identity.py",
            "tests/unit/backend/utils/test_logger.py",
        ),
    ),
    (
        "local-runtime-contracts",
        (
            "tests/unit/llm/core/test_config.py",
            "tests/unit/llm/core/test_model_catalog.py",
            "tests/unit/llm/core/test_model_download_lifecycle.py",
            "tests/unit/llm/core/test_runtime_process_owner.py",
            "tests/unit/llm/rag/test_security_policy.py",
            "tests/unit/llm/tools/test_authorized_paths.py",
        ),
    ),
    (
        "process-and-launcher-contracts",
        (
            "tests/unit/scripts/test_active_checkout.py",
            "tests/unit/scripts/test_bounded_qt_shutdown.py",
            "tests/unit/scripts/test_capture_windows_launcher_walkthrough.py",
            "tests/unit/scripts/test_handoff_evidence_recorder.py",
            "tests/unit/scripts/test_native_process_safety.py",
            "tests/unit/scripts/test_owned_process_group.py",
            "tests/unit/scripts/test_probe_pyvistaqt_runtime.py",
            "tests/unit/scripts/test_process_termination_safety.py",
            "tests/unit/scripts/test_run_required_pytest_gate.py",
            "tests/unit/scripts/test_run_tests.py",
            "tests/unit/scripts/test_run_ui_native_render_stress.py",
            "tests/unit/scripts/test_test_runtime_paths.py",
            "tests/unit/scripts/test_wsl_launcher_privacy.py",
        ),
    ),
    (
        "qt-layout-contracts",
        (
            "tests/unit/ui/chat/test_chat_panel.py",
            "tests/unit/ui/chat/test_message_bubble.py",
            "tests/unit/ui/components/test_info_panel.py",
            "tests/unit/ui/dataset/test_import_label.py",
            "tests/unit/ui/dataset/test_import_latency.py",
            "tests/unit/ui/dataset/test_panel.py",
            "tests/unit/ui/dataset/test_smart_parser.py",
            "tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py",
            "tests/unit/ui/preprocess/test_preview_presentation.py",
            "tests/unit/ui/test_data_splitting.py",
            "tests/unit/ui/test_evaluation_panel_redesign.py",
            "tests/unit/ui/test_qt_runtime.py",
            "tests/unit/ui/test_visualization.py",
            "tests/unit/ui/training/test_history_table.py",
        ),
    ),
    (
        "agent-platform-runtime",
        ("tests/integration/agent/test_long_session_product_flow.py",),
    ),
    (
        "ui-platform-runtime",
        (
            "tests/integration/ui/test_main_window_training_refresh_runtime.py",
            "tests/integration/ui/test_product_walkthrough.py",
            "tests/integration/ui/test_sidebar_geometry.py",
            "tests/integration/ui/test_window_geometry.py",
        ),
    ),
    (
        "native-render-lifecycle",
        ("tests/integration/ui/test_native_render_lifecycle.py",),
    ),
    (
        "preprocess-async-lifecycle",
        ("tests/integration/ui/test_preprocess_async_filter_lifecycle.py",),
    ),
    (
        "preprocess-native-lifecycle",
        ("tests/integration/ui/test_preprocess_native_lifecycle.py",),
    ),
)
PLATFORM_CI_GROUPS: tuple[tuple[str, tuple[tuple[str, tuple[str, ...]], ...]], ...] = (
    ("platform-core-contracts", PLATFORM_SHARDS[:2]),
    ("platform-product-lifecycle", PLATFORM_SHARDS[2:]),
)
PLATFORM_CI_COMMANDS = tuple(command for command, _shards in PLATFORM_CI_GROUPS)
LINUX_CI_GROUPS: tuple[tuple[str, tuple[tuple[str, tuple[str, ...]], ...]], ...] = (
    ("linux-unit-backend", (("backend", ("tests/unit/backend",)),)),
    ("linux-unit-llm-agent", (("llm-agent", ("tests/unit/llm/agent",)),)),
    (
        "linux-unit-scripts",
        (("developer-scripts", ("tests/unit/scripts",)),),
    ),
    ("linux-unit-ui", UI_UNIT_SHARDS),
    (
        "linux-unit-rest",
        (
            ("llm-root-contracts", LLM_UNIT_ROOT_TESTS),
            ("llm-core", ("tests/unit/llm/core",)),
            ("llm-rag", ("tests/unit/llm/rag",)),
            ("llm-tools", ("tests/unit/llm/tools",)),
            ("root-contracts", UNIT_ROOT_TESTS),
        ),
    ),
    (
        "linux-integration-agent-timing",
        (("agent-wall-clock", INTEGRATION_AGENT_TIMING_TESTS),),
    ),
    ("linux-integration-ui", (("ui", ("tests/integration/ui",)),)),
    (
        "linux-integration-rest",
        (
            ("agent-contracts", INTEGRATION_AGENT_COVERED_TESTS),
            ("backend", ("tests/integration/backend",)),
            ("controller", ("tests/integration/controller",)),
            ("debug", ("tests/integration/debug",)),
            ("io", ("tests/integration/io",)),
            ("llm", ("tests/integration/llm",)),
            ("pipeline", ("tests/integration/pipeline",)),
            ("training", ("tests/integration/training",)),
            ("root-contracts", INTEGRATION_ROOT_TESTS),
            *REGRESSION_SHARDS,
        ),
    ),
)
LINUX_CI_COMMANDS = tuple(command for command, _shards in LINUX_CI_GROUPS)
LINUX_CI_UNCOVERED_COMMANDS = frozenset({"linux-integration-agent-timing"})
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
    """Run LLM native-lifecycle domains in isolated processes."""
    print("Running LLM Tests...")
    configure_headless_ui_env()
    _assert_all_test_domains_declared(
        root=Path("tests/unit/llm"),
        shards=LLM_UNIT_SHARDS[1:],
    )
    _run_shards(
        gate_name="LLM unit",
        shards=LLM_UNIT_SHARDS,
        attestation_sink=attestation_sink,
    )


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
        shards=UNIT_DOMAIN_SHARDS,
    )
    _run_shards(
        gate_name="Unit",
        shards=(*UNIT_SHARDS, ("root-contracts", UNIT_ROOT_TESTS)),
        attestation_sink=attestation_sink,
    )


def integration(attestation_sink: list[dict[str, Any]] | None = None) -> None:
    """Run every integration-test domain in a fresh native-library process."""
    configure_headless_ui_env()
    _assert_all_test_domains_declared(
        root=Path("tests/integration"),
        shards=INTEGRATION_SHARDS,
    )
    _run_shards(
        gate_name="Integration",
        shards=(*INTEGRATION_SHARDS, ("root-contracts", INTEGRATION_ROOT_TESTS)),
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


def platform(attestation_sink: list[dict[str, Any]] | None = None) -> None:
    """Run OS-sensitive contracts without duplicating the authoritative suite."""
    print("Running Focused Cross-Platform Tests...")
    configure_headless_ui_env()
    _run_shards(
        gate_name="Platform",
        shards=PLATFORM_SHARDS,
        attestation_sink=attestation_sink,
    )


def run_linux_ci_group(
    command: str,
    attestation_sink: list[dict[str, Any]] | None = None,
) -> None:
    """Run one bounded authoritative Linux group using native-safe shards."""
    groups = dict(LINUX_CI_GROUPS)
    try:
        shards = groups[command]
    except KeyError as error:
        raise ValueError(f"Unknown Linux CI command: {command}") from error
    configure_headless_ui_env()
    _run_shards(
        gate_name=f"Linux CI {command}",
        shards=shards,
        attestation_sink=attestation_sink,
    )


def run_platform_ci_group(
    command: str,
    attestation_sink: list[dict[str, Any]] | None = None,
) -> None:
    """Run one required platform group without weakening process isolation."""
    groups = dict(PLATFORM_CI_GROUPS)
    try:
        shards = groups[command]
    except KeyError as error:
        raise ValueError(f"Unknown platform CI command: {command}") from error
    configure_headless_ui_env()
    _run_shards(
        gate_name=f"Platform CI {command}",
        shards=shards,
        attestation_sink=attestation_sink,
    )


def verify_linux_ci_evidence(evidence_dir: Path, result_path: Path) -> int:
    """Fail closed unless every Linux group and coverage file is present."""
    evidence_root = evidence_dir.expanduser().resolve()
    expected_results = {f"{command}.json" for command in LINUX_CI_COMMANDS}
    actual_results = {path.name for path in evidence_root.glob("linux-*.json")}
    expected_coverage = {
        f".coverage.{command}"
        for command in LINUX_CI_COMMANDS
        if command not in LINUX_CI_UNCOVERED_COMMANDS
    }
    actual_coverage = {path.name for path in evidence_root.glob(".coverage.linux-*")}
    missing_coverage = expected_coverage - actual_coverage
    unknown_coverage = {
        name
        for name in actual_coverage
        if not any(
            name == base_name or name.startswith(f"{base_name}.")
            for base_name in expected_coverage
        )
    }
    failures: list[str] = []
    attestations: list[dict[str, Any]] = []

    if actual_results != expected_results:
        failures.append(
            "Linux CI result set mismatch "
            f"(expected {sorted(expected_results)}, got {sorted(actual_results)})."
        )
    if missing_coverage or unknown_coverage:
        failures.append(
            "Linux CI coverage set mismatch "
            f"(missing {sorted(missing_coverage)}, "
            f"unknown {sorted(unknown_coverage)})."
        )

    for command in LINUX_CI_COMMANDS:
        attestation, failure = validate_attestation(
            evidence_root / f"{command}.json",
            expected_runner=SHARDED_PYTEST_RUNNER_ID,
            expected_args=(command,),
            expected_exit_code=0,
        )
        if failure is not None:
            failures.append(f"{command}: {failure}")
        elif attestation is not None:
            attestations.append(attestation)

    exit_code = 1 if failures else 0
    write_attestation(
        result_path,
        build_attestation(
            runner=SHARDED_PYTEST_RUNNER_ID,
            command_args=("all",),
            exit_code=exit_code,
            counts=aggregate_counts(attestations),
        ),
    )
    if failures:
        for failure in failures:
            print(f"Linux CI evidence failed: {failure}", file=sys.stderr)
    else:
        print(f"Verified {len(attestations)} authoritative Linux CI groups.")
    return exit_code


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
    if os.environ.get("XBL_TEST_COVERAGE") == "1":
        try:
            for command in LINUX_CI_COMMANDS:
                _configure_linux_ci_coverage(command)
                run_linux_ci_group(command, attestation_sink)
        finally:
            os.environ["XBL_TEST_COVERAGE"] = "1"
        return
    if attestation_sink is None:
        unit()
        integration()
        regression()
        return
    unit(attestation_sink)
    integration(attestation_sink)
    regression(attestation_sink)


def _configure_linux_ci_coverage(command: str) -> bool:
    """Apply the reviewed coverage policy for one authoritative Linux group."""
    if command in LINUX_CI_UNCOVERED_COMMANDS:
        os.environ.pop("XBL_TEST_COVERAGE", None)
        return False
    os.environ["XBL_TEST_COVERAGE"] = "1"
    return True


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
            "platform",
            "all",
            *LINUX_CI_COMMANDS,
            *PLATFORM_CI_COMMANDS,
            "verify-linux-ci",
        ),
    )
    parser.add_argument("--result-json", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parsed = parser.parse_args(list(argv))
    if parsed.result_json is None:
        configured = os.environ.get("XBL_PYTEST_RESULT_JSON", "").strip()
        parsed.result_json = Path(configured) if configured else None
    return parsed


def _dispatch(
    command: str,
    attestation_sink: list[dict[str, Any]] | None,
) -> None:
    if command in LINUX_CI_COMMANDS:
        run_linux_ci_group(command, attestation_sink)
        return
    if command in PLATFORM_CI_COMMANDS:
        run_platform_ci_group(command, attestation_sink)
        return
    commands = {
        "backend": backend,
        "ui": ui,
        "llm": run_llm_tests,
        "remote": run_remote_tests,
        "unit": unit,
        "integration": integration,
        "regression": regression,
        "platform": platform,
        "all": all_tests,
    }
    commands[command](attestation_sink)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one isolated suite and optionally attest aggregate completion."""
    parsed = _parse_cli(sys.argv[1:] if argv is None else argv)
    result_path: Path | None = parsed.result_json
    if parsed.command == "verify-linux-ci":
        if result_path is None or parsed.evidence_dir is None:
            print(
                "verify-linux-ci requires --evidence-dir and --result-json.",
                file=sys.stderr,
            )
            return 2
        result_path.unlink(missing_ok=True)
        return verify_linux_ci_evidence(parsed.evidence_dir, result_path)
    if result_path is not None:
        result_path.unlink(missing_ok=True)
    attestations: list[dict[str, Any]] | None = [] if result_path else None
    exit_code = 0
    linux_ci_command = parsed.command in LINUX_CI_COMMANDS
    if linux_ci_command:
        coverage_enabled = _configure_linux_ci_coverage(parsed.command)
    else:
        coverage_enabled = os.environ.get("XBL_TEST_COVERAGE") == "1"
    if coverage_enabled:
        exit_code = _run_coverage_command("erase")
    if exit_code == 0:
        try:
            _dispatch(parsed.command, attestations)
        except SystemExit as error:
            exit_code = int(error.code or 0)
    if coverage_enabled and exit_code == 0 and not linux_ci_command:
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
