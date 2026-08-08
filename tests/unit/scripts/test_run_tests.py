from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from scripts.dev import run_tests
from scripts.dev.pytest_completion_attestation import (
    REQUIRED_PYTEST_RUNNER_ID,
    build_attestation,
)


@pytest.fixture(autouse=True)
def _isolate_ci_shard_evidence_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep runner unit tests independent from the outer CI shard settings."""
    monkeypatch.delenv("XBL_TEST_JUNIT_DIR", raising=False)
    monkeypatch.delenv("XBL_TEST_COVERAGE", raising=False)


def test_headless_runner_uses_one_wsl_safe_temp_namespace(monkeypatch) -> None:
    monkeypatch.delenv("XBRAINLAB_TEST_TMPDIR", raising=False)
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-Test")
    monkeypatch.setattr(tempfile, "tempdir", None)

    run_tests.configure_headless_ui_env()

    temp_root = Path(os.environ["TMPDIR"]).resolve()
    matplotlib_root = Path(os.environ["MPLCONFIGDIR"]).resolve()
    if Path("/dev/shm").is_dir() and os.access("/dev/shm", os.W_OK):
        assert temp_root.is_relative_to("/dev/shm")
    else:
        repo_root = Path(run_tests.__file__).resolve().parents[2]
        assert temp_root == (repo_root / ".test-tmp").resolve()
    assert matplotlib_root.parent == temp_root
    assert matplotlib_root.name == f"matplotlib-{os.getpid()}"
    assert Path(tempfile.gettempdir()).resolve() == temp_root


def test_run_shards_executes_every_declared_domain(monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []

    def record(args):
        calls.append(tuple(args))
        return 0

    monkeypatch.setattr(run_tests, "run_pytest", record)

    run_tests._run_shards(
        gate_name="Example",
        shards=(
            ("backend", ("tests/backend",)),
            ("ui", ("tests/ui",)),
        ),
    )

    assert calls == [
        ("--capture=sys", "tests/backend", "-q"),
        ("--capture=sys", "tests/ui", "-q"),
    ]


def test_generic_runner_explicitly_allows_only_optional_public_fixture_skips() -> None:
    result_path = Path("build/tmp/example-result.json")

    command = run_tests._required_pytest_command(
        result_path,
        ("tests/example.py", "-q"),
    )

    assert command == [
        sys.executable,
        "-m",
        "scripts.dev.run_required_pytest_gate",
        "--result-json",
        str(result_path),
        "--allow-skip-marker",
        "optional_public_fixture",
        "--",
        "tests/example.py",
        "-q",
    ]


def test_run_shards_reports_failures_after_running_remaining_domains(
    monkeypatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fail_first(args):
        calls.append(tuple(args))
        return 1 if "tests/backend" in args else 0

    monkeypatch.setattr(run_tests, "run_pytest", fail_first)

    with pytest.raises(SystemExit, match="1"):
        run_tests._run_shards(
            gate_name="Example",
            shards=(
                ("backend", ("tests/backend",)),
                ("ui", ("tests/ui",)),
            ),
        )

    assert calls == [
        ("--capture=sys", "tests/backend", "-q"),
        ("--capture=sys", "tests/ui", "-q"),
    ]


def test_all_tests_delegates_to_every_isolated_gate(
    monkeypatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(run_tests, "unit", lambda: calls.append("unit"))
    monkeypatch.setattr(
        run_tests,
        "integration",
        lambda: calls.append("integration"),
    )
    monkeypatch.setattr(
        run_tests,
        "regression",
        lambda: calls.append("regression"),
    )

    run_tests.all_tests()

    assert calls == ["unit", "integration", "regression"]


def test_declared_integration_shards_cover_every_test_domain() -> None:
    declared_paths = {
        Path(path)
        for _label, paths in (
            *run_tests.INTEGRATION_SHARDS,
            run_tests.MCP_COMPATIBILITY_SHARDS[1],
        )
        for path in paths
    }
    actual_domains = {
        path
        for path in Path("tests/integration").iterdir()
        if path.is_dir() and any(path.rglob("test_*.py"))
    }

    assert declared_paths == actual_domains


def test_ui_gate_runs_every_ui_domain_in_isolated_processes(
    monkeypatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(
        run_tests,
        "configure_headless_ui_env",
        lambda: None,
    )
    monkeypatch.setattr(
        run_tests,
        "run_pytest",
        lambda args: calls.append(tuple(args)) or 0,
    )

    run_tests.ui()

    expected_paths = {
        Path(path).as_posix()
        for _label, paths in run_tests.UI_UNIT_SHARDS
        for path in paths
    }
    root_tests = {path.as_posix() for path in Path("tests/unit/ui").glob("test_*.py")}
    domain_paths = {
        path.as_posix()
        for path in Path("tests/unit/ui").iterdir()
        if path.is_dir() and any(path.rglob("test_*.py"))
    }

    assert expected_paths == root_tests | domain_paths
    assert calls == [
        ("--capture=sys", *paths, "-q") for _label, paths in run_tests.UI_UNIT_SHARDS
    ]


def test_mcp_compatibility_is_explicitly_outside_default_all_gate() -> None:
    assert run_tests.MCP_COMPATIBILITY_SHARDS == (
        ("unit", ("tests/unit/mcp",)),
        ("integration", ("tests/integration/mcp",)),
    )
    assert all(
        "mcp" not in path
        for _label, paths in (
            *run_tests.UNIT_SHARDS,
            *run_tests.INTEGRATION_SHARDS,
        )
        for path in paths
    )


def test_regression_gate_is_declared() -> None:
    assert run_tests.REGRESSION_SHARDS == (("regression", ("tests/regression",)),)


def test_shard_runtime_args_keep_ci_evidence_isolated(
    monkeypatch,
    tmp_path,
) -> None:
    junit_dir = tmp_path / "junit"
    monkeypatch.setenv("XBL_TEST_JUNIT_DIR", str(junit_dir))
    monkeypatch.setenv("XBL_TEST_COVERAGE", "1")

    args = run_tests._shard_runtime_args(
        gate_name="Integration",
        label="UI",
    )

    assert args == (
        f"--junitxml={junit_dir / 'integration-ui.xml'}",
        "--cov=XBrainLab",
        "--cov-append",
        "--cov-report=",
        "--cov-fail-under=0",
    )


def test_main_owns_one_complete_coverage_lifecycle(monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []

    def record_command(args, **kwargs):
        assert kwargs == {"cwd": run_tests.ROOT, "check": False}
        calls.append(tuple(args))
        return subprocess.CompletedProcess(args, 0)

    def fake_dispatch(command, sink):
        assert command == "all"
        assert sink is None
        calls.append(("dispatch",))

    monkeypatch.setenv("XBL_TEST_COVERAGE", "1")
    monkeypatch.setattr(run_tests.subprocess, "run", record_command)
    monkeypatch.setattr(run_tests, "_dispatch", fake_dispatch)

    assert run_tests.main(["all"]) == 0
    assert calls == [
        (sys.executable, "-m", "coverage", "erase"),
        ("dispatch",),
        (sys.executable, "-m", "coverage", "report"),
    ]


def test_main_does_not_report_partial_coverage_after_shard_failure(
    monkeypatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def record_command(args, **kwargs):
        calls.append(tuple(args))
        return subprocess.CompletedProcess(args, 0)

    def fail_dispatch(command, sink):
        calls.append(("dispatch",))
        raise SystemExit(1)

    monkeypatch.setenv("XBL_TEST_COVERAGE", "1")
    monkeypatch.setattr(run_tests.subprocess, "run", record_command)
    monkeypatch.setattr(run_tests, "_dispatch", fail_dispatch)

    assert run_tests.main(["all"]) == 1
    assert calls == [
        (sys.executable, "-m", "coverage", "erase"),
        ("dispatch",),
    ]


@pytest.mark.parametrize("failing_command", ["erase", "report"])
def test_main_fails_closed_for_unusable_coverage_data(
    monkeypatch,
    tmp_path,
    failing_command,
) -> None:
    result_path = tmp_path / "all.json"
    dispatched = False

    def run_coverage(args, **kwargs):
        return_code = 1 if args[-1] == failing_command else 0
        return subprocess.CompletedProcess(args, return_code)

    def fake_dispatch(command, sink):
        nonlocal dispatched
        dispatched = True

    monkeypatch.setenv("XBL_TEST_COVERAGE", "1")
    monkeypatch.setattr(run_tests.subprocess, "run", run_coverage)
    monkeypatch.setattr(run_tests, "_dispatch", fake_dispatch)

    assert run_tests.main(["all", "--result-json", str(result_path)]) == 1
    assert dispatched is (failing_command == "report")
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["exit_code"] == 1


def test_ci_uses_the_isolated_test_runner() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "scripts/dev/run_tests.py all" in workflow
    assert "poetry run pytest tests/" not in workflow


def test_main_attests_aggregate_shard_completion(monkeypatch, tmp_path) -> None:
    result_path = tmp_path / "ui-suite.json"
    counts = {
        "collected": 3,
        "executed": 3,
        "passed": 3,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "deselected": 0,
    }

    def fake_dispatch(command, sink):
        assert command == "ui"
        assert sink is not None
        sink.append(
            build_attestation(
                runner=REQUIRED_PYTEST_RUNNER_ID,
                command_args=("tests/unit/ui", "-q"),
                exit_code=0,
                counts=counts,
            )
        )

    monkeypatch.setattr(run_tests, "_dispatch", fake_dispatch)

    assert run_tests.main(["ui", "--result-json", str(result_path)]) == 0
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["runner"] == "xbrainlab.sharded-test-runner"
    assert payload["command_args"] == ["ui"]
    assert payload["counts"] == counts
