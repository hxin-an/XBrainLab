from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from scripts.dev import run_tests


def test_headless_runner_uses_one_wsl_safe_temp_namespace(monkeypatch) -> None:
    monkeypatch.delenv("XBRAINLAB_TEST_TMPDIR", raising=False)
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu-Test")
    monkeypatch.setattr(tempfile, "tempdir", None)

    run_tests.configure_headless_ui_env()

    temp_root = Path(os.environ["TMPDIR"]).resolve()
    matplotlib_root = Path(os.environ["MPLCONFIGDIR"]).resolve()
    assert temp_root.is_relative_to("/dev/shm")
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
        path for _label, paths in run_tests.UI_UNIT_SHARDS for path in paths
    }
    root_tests = {str(path) for path in Path("tests/unit/ui").glob("test_*.py")}
    domain_paths = {
        str(path)
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
    )


def test_ci_uses_the_isolated_test_runner() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "scripts/dev/run_tests.py all" in workflow
    assert "poetry run pytest tests/" not in workflow
