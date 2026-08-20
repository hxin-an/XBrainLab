from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import pytest
import yaml

from scripts.dev import ci_source_provenance, run_tests
from scripts.dev.pytest_completion_attestation import (
    REQUIRED_PYTEST_RUNNER_ID,
    SHARDED_PYTEST_RUNNER_ID,
    build_attestation,
    write_attestation,
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


def test_covered_all_gate_uses_the_reviewed_wall_clock_split(monkeypatch) -> None:
    observed: list[tuple[str, bool]] = []
    monkeypatch.setenv("XBL_TEST_COVERAGE", "1")

    def capture_group(command, sink) -> None:
        assert sink is None
        observed.append((command, "XBL_TEST_COVERAGE" in os.environ))

    monkeypatch.setattr(run_tests, "run_linux_ci_group", capture_group)

    run_tests.all_tests()

    assert [command for command, _covered in observed] == list(
        run_tests.LINUX_CI_COMMANDS
    )
    assert observed == [
        (command, command not in run_tests.LINUX_CI_UNCOVERED_COMMANDS)
        for command in run_tests.LINUX_CI_COMMANDS
    ]
    assert os.environ["XBL_TEST_COVERAGE"] == "1"


def test_platform_gate_runs_only_explicit_cross_platform_regressions(
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

    run_tests.platform()

    expected_calls = [
        ("--capture=sys", *paths, "-q") for _label, paths in run_tests.PLATFORM_SHARDS
    ]
    assert calls == expected_calls

    selected_paths = [
        path for _label, paths in run_tests.PLATFORM_SHARDS for path in paths
    ]
    assert selected_paths
    assert len(selected_paths) == len(set(selected_paths))
    assert all(Path(path).is_file() for path in selected_paths)
    assert all(Path(path).name.startswith("test_") for path in selected_paths)
    assert "tests/unit" not in selected_paths
    assert "tests/integration" not in selected_paths
    assert "tests/regression" not in selected_paths


def test_platform_native_lifecycle_tests_keep_separate_process_boundaries() -> None:
    native_lifecycle_paths = {
        "tests/integration/ui/test_native_render_lifecycle.py",
        "tests/integration/ui/test_preprocess_async_filter_lifecycle.py",
        "tests/integration/ui/test_preprocess_native_lifecycle.py",
    }
    path_to_label = {
        path: label
        for label, paths in run_tests.PLATFORM_SHARDS
        for path in paths
        if path in native_lifecycle_paths
    }

    assert set(path_to_label) == native_lifecycle_paths
    assert len(set(path_to_label.values())) == len(native_lifecycle_paths)


def test_platform_ci_groups_partition_focused_platform_gate_exactly_once() -> None:
    grouped_shards = [
        shard for _command, shards in run_tests.PLATFORM_CI_GROUPS for shard in shards
    ]

    assert grouped_shards == list(run_tests.PLATFORM_SHARDS)
    assert len(grouped_shards) == len(set(grouped_shards))
    assert run_tests.PLATFORM_CI_COMMANDS == (
        "platform-core-contracts",
        "platform-product-lifecycle",
    )


def test_platform_gate_does_not_repeat_os_neutral_architecture_suite() -> None:
    selected_paths = {
        path for _label, paths in run_tests.PLATFORM_SHARDS for path in paths
    }

    assert "tests/unit/test_architecture_compliance.py" not in selected_paths


def _expand_test_paths(paths: tuple[str, ...]) -> list[Path]:
    expanded: list[Path] = []
    for value in paths:
        path = Path(value)
        if path.is_dir():
            expanded.extend(path.rglob("test_*.py"))
        else:
            expanded.append(path)
    return expanded


def test_expand_test_paths_preserves_duplicate_occurrences() -> None:
    test_path = "tests/unit/scripts/test_run_tests.py"

    expanded = _expand_test_paths((test_path, test_path))

    assert Counter(expanded) == Counter({Path(test_path): 2})


def test_linux_ci_groups_partition_the_authoritative_suite_exactly_once() -> None:
    grouped_files: list[Path] = []
    for _command, shards in run_tests.LINUX_CI_GROUPS:
        for _label, paths in shards:
            grouped_files.extend(sorted(_expand_test_paths(paths)))

    authoritative_files = {
        *Path("tests/unit").rglob("test_*.py"),
        *Path("tests/integration").rglob("test_*.py"),
        *Path("tests/regression").rglob("test_*.py"),
    }

    assert Counter(grouped_files) == Counter(authoritative_files)


def test_linux_ci_isolates_only_wall_clock_agent_timing_from_coverage() -> None:
    assert (
        frozenset({"linux-integration-agent-timing"})
        == run_tests.LINUX_CI_UNCOVERED_COMMANDS
    )
    groups = dict(run_tests.LINUX_CI_GROUPS)
    assert groups["linux-integration-agent-timing"] == (
        (
            "agent-wall-clock",
            ("tests/integration/agent/test_long_session_product_flow.py",),
        ),
    )


def test_linux_ci_isolates_ui_domains_in_separate_qt_processes() -> None:
    groups = dict(run_tests.LINUX_CI_GROUPS)

    assert groups["linux-unit-ui"] == run_tests.UI_UNIT_SHARDS
    assert all(paths != ("tests/unit/ui",) for _label, paths in groups["linux-unit-ui"])


def test_linux_ci_group_preserves_declared_process_boundaries(monkeypatch) -> None:
    observed: dict[str, object] = {}
    command, shards = run_tests.LINUX_CI_GROUPS[0]

    monkeypatch.setattr(run_tests, "configure_headless_ui_env", lambda: None)

    def capture_run(**kwargs) -> None:
        observed.update(kwargs)

    monkeypatch.setattr(run_tests, "_run_shards", capture_run)

    run_tests.run_linux_ci_group(command)

    assert observed == {
        "gate_name": f"Linux CI {command}",
        "shards": shards,
        "attestation_sink": None,
    }


def test_platform_ci_group_preserves_declared_process_boundaries(monkeypatch) -> None:
    observed: dict[str, object] = {}
    command, shards = run_tests.PLATFORM_CI_GROUPS[0]

    monkeypatch.setattr(run_tests, "configure_headless_ui_env", lambda: None)

    def capture_run(**kwargs) -> None:
        observed.update(kwargs)

    monkeypatch.setattr(run_tests, "_run_shards", capture_run)

    run_tests.run_platform_ci_group(command)

    assert observed == {
        "gate_name": f"Platform CI {command}",
        "shards": shards,
        "attestation_sink": None,
    }


def _write_linux_ci_evidence(root: Path) -> None:
    counts = {
        "collected": 1,
        "executed": 1,
        "passed": 1,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "deselected": 0,
    }
    for command, _shards in run_tests.LINUX_CI_GROUPS:
        write_attestation(
            root / f"{command}.json",
            build_attestation(
                runner=SHARDED_PYTEST_RUNNER_ID,
                command_args=(command,),
                exit_code=0,
                counts=counts,
                outcomes={f"tests/{command}.py::test_passes": "passed"},
            ),
        )
        if command not in run_tests.LINUX_CI_UNCOVERED_COMMANDS:
            (root / f".coverage.{command}").write_bytes(b"coverage-data")


def test_linux_ci_evidence_verifier_aggregates_every_required_group(tmp_path) -> None:
    result_path = tmp_path / "all-regression.json"
    _write_linux_ci_evidence(tmp_path)

    assert run_tests.verify_linux_ci_evidence(tmp_path, result_path) == 0

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["runner"] == SHARDED_PYTEST_RUNNER_ID
    assert payload["command_args"] == ["all"]
    assert payload["exit_code"] == 0
    assert payload["counts"]["passed"] == len(run_tests.LINUX_CI_GROUPS)
    assert not (tmp_path / "all-linux-source-provenance.json").exists()


def _write_remote_linux_provenance(
    root: Path,
    *,
    member_tree: str = "c" * 40,
) -> tuple[Path, Path]:
    provenance_root = root / "source-provenance"
    common = {
        "schema": ci_source_provenance.CI_SOURCE_PROVENANCE_SCHEMA,
        "event_name": "pull_request",
        "repository": "hxin-an/XBrainLab",
        "workflow": "CI",
        "run_id": "123",
        "run_attempt": "1",
        "runner_os": "Linux",
        "runner_arch": "X64",
        "github_sha": "e" * 40,
        "expected_head_sha": "a" * 40,
        "pull_request_head_sha": "a" * 40,
        "pull_request_base_sha": "b" * 40,
        "checked_out_head_sha": "a" * 40,
    }
    for command in run_tests.LINUX_CI_COMMANDS:
        artifact_dir = (
            provenance_root
            / f"{ci_source_provenance.LINUX_PROVENANCE_ARTIFACT_PREFIX}{command}"
        )
        artifact_dir.mkdir(parents=True)
        payload = {
            **common,
            "job_key": command,
            "github_job": "linux-shard",
            "checked_out_tree_sha": member_tree,
        }
        (artifact_dir / f"ci-source-provenance-{command}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    expected_path = root / "linux-test-source-provenance.json"
    expected_path.write_text(
        json.dumps(
            {
                **common,
                "job_key": "linux-test",
                "github_job": "linux-test",
                "checked_out_tree_sha": "c" * 40,
            }
        ),
        encoding="utf-8",
    )
    return provenance_root, expected_path


def test_linux_ci_evidence_verifier_rejects_all_stale_remote_members(
    tmp_path,
) -> None:
    result_path = tmp_path / "all-regression.json"
    _write_linux_ci_evidence(tmp_path)
    provenance_root, expected_path = _write_remote_linux_provenance(
        tmp_path,
        member_tree="d" * 40,
    )

    assert (
        run_tests.verify_linux_ci_evidence(
            tmp_path,
            result_path,
            provenance_dir=provenance_root,
            expected_provenance_path=expected_path,
        )
        == 1
    )
    assert not (tmp_path / "all-linux-source-provenance.json").exists()
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["exit_code"] == 1


def test_linux_ci_evidence_verifier_accepts_owned_parallel_coverage_fragments(
    tmp_path,
) -> None:
    result_path = tmp_path / "all-regression.json"
    _write_linux_ci_evidence(tmp_path)
    fragment = tmp_path / ".coverage.linux-unit-llm-agent.runner.pid123.random-fragment"
    fragment.write_bytes(b"parallel-coverage-data")

    assert run_tests.verify_linux_ci_evidence(tmp_path, result_path) == 0


def test_linux_ci_evidence_verifier_rejects_unknown_coverage_fragments(
    tmp_path,
) -> None:
    result_path = tmp_path / "all-regression.json"
    _write_linux_ci_evidence(tmp_path)
    (tmp_path / ".coverage.linux-unknown.pid123").write_bytes(b"unknown")

    assert run_tests.verify_linux_ci_evidence(tmp_path, result_path) == 1


def test_linux_ci_evidence_verifier_fails_closed_for_missing_coverage(
    tmp_path,
) -> None:
    result_path = tmp_path / "all-regression.json"
    _write_linux_ci_evidence(tmp_path)
    (tmp_path / ".coverage.linux-unit-backend").unlink()

    assert run_tests.verify_linux_ci_evidence(tmp_path, result_path) == 1

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["exit_code"] == 1


def test_declared_integration_shards_cover_every_test_domain() -> None:
    declared_paths = {
        Path(path) for _label, paths in run_tests.INTEGRATION_SHARDS for path in paths
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


def test_ui_shard_paths_are_portable_posix_cli_arguments() -> None:
    assert all(
        "\\" not in path for _label, paths in run_tests.UI_UNIT_SHARDS for path in paths
    )


def test_llm_gate_runs_every_native_domain_in_isolated_processes(
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

    run_tests.run_llm_tests()

    root = Path("tests/unit/llm")
    root_tests = {path.as_posix() for path in root.glob("test_*.py")}
    domain_paths = {
        path.as_posix()
        for path in root.iterdir()
        if path.is_dir() and any(path.rglob("test_*.py"))
    }
    executed_paths = {
        path for call in calls for path in call if path.startswith("tests/unit/llm")
    }

    assert executed_paths == root_tests | domain_paths
    assert len(calls) == len(domain_paths) + 1
    assert all("tests/unit/llm" not in call for call in calls)


def test_default_unit_gate_uses_the_llm_native_process_boundaries(
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

    run_tests.unit()

    llm_calls = [
        call
        for call in calls
        if any(path.startswith("tests/unit/llm") for path in call)
    ]
    assert len(llm_calls) == len(run_tests.LLM_UNIT_SHARDS)
    assert all("tests/unit/llm" not in call for call in llm_calls)


def test_default_unit_gate_uses_the_ui_native_process_boundaries(
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

    run_tests.unit()

    ui_calls = [
        call for call in calls if any(path.startswith("tests/unit/ui") for path in call)
    ]
    assert len(ui_calls) == len(run_tests.UI_UNIT_SHARDS)
    assert all("tests/unit/ui" not in call for call in ui_calls)


def test_retired_mcp_gate_is_not_exposed_by_test_runner() -> None:
    parser = run_tests._parse_cli

    with pytest.raises(SystemExit):
        parser(["mcp-compatibility"])


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


def test_linux_ci_covered_group_defers_coverage_report_until_aggregate(
    monkeypatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def record_command(args, **kwargs):
        calls.append(tuple(args))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.delenv("XBL_TEST_COVERAGE", raising=False)
    monkeypatch.setattr(run_tests.subprocess, "run", record_command)
    monkeypatch.setattr(
        run_tests,
        "_dispatch",
        lambda command, sink: calls.append(("dispatch", command)),
    )

    assert run_tests.main(["linux-unit-backend"]) == 0
    assert calls == [
        (sys.executable, "-m", "coverage", "erase"),
        ("dispatch", "linux-unit-backend"),
    ]


def test_linux_ci_wall_clock_group_disables_coverage_instrumentation(
    monkeypatch,
) -> None:
    observed: list[tuple[str, bool]] = []
    monkeypatch.setenv("XBL_TEST_COVERAGE", "1")

    def capture_dispatch(command, sink):
        observed.append((command, "XBL_TEST_COVERAGE" in os.environ))

    monkeypatch.setattr(run_tests, "_dispatch", capture_dispatch)

    assert run_tests.main(["linux-integration-agent-timing"]) == 0
    assert observed == [("linux-integration-agent-timing", False)]


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


def test_ci_uses_full_linux_and_focused_cross_platform_runners() -> None:
    workflow_text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    jobs = workflow["jobs"]

    expected_checkout_ref = (
        "${{ github.event_name == 'pull_request' && "
        "github.event.pull_request.head.sha || github.sha }}"
    )
    checkout_steps = [
        step
        for job in jobs.values()
        for step in job.get("steps", ())
        if step.get("uses") == "actions/checkout@v4"
    ]
    assert len(checkout_steps) == 10
    assert all(
        step.get("with") == {"ref": expected_checkout_ref} for step in checkout_steps
    )

    assert jobs["linux-shard"]["strategy"]["matrix"] == {
        "command": list(run_tests.LINUX_CI_COMMANDS),
    }
    assert jobs["platform-test"]["strategy"]["matrix"] == {
        "os": ["windows-latest", "macos-latest"],
        "command": list(run_tests.PLATFORM_CI_COMMANDS),
    }

    assert jobs["linux-shard"]["strategy"]["max-parallel"] == 8
    assert jobs["linux-shard"]["env"]["XBL_SHARED_CI_RUNNER"] == "1"
    assert jobs["platform-test"]["env"]["XBL_SHARED_CI_RUNNER"] == "1"
    linux_shard_steps = {
        step.get("name"): step for step in jobs["linux-shard"]["steps"]
    }
    sidecar_upload = linux_shard_steps["Upload source provenance sidecar"]
    assert sidecar_upload["with"]["name"] == (
        "linux-source-provenance-${{ matrix.command }}"
    )
    assert sidecar_upload["with"]["path"] == (
        "test-results/ci-source-provenance-${{ matrix.command }}.json"
    )
    linux_test_steps = {step.get("name"): step for step in jobs["linux-test"]["steps"]}
    provenance_download = linux_test_steps["Download source provenance sidecars"]
    assert provenance_download["with"] == {
        "pattern": "linux-source-provenance-*",
        "path": "source-provenance",
    }
    assert workflow_text.count("scripts/dev/run_tests.py ${{ matrix.command }}") == 2
    assert "python -m scripts.dev.run_tests verify-linux-ci" in workflow_text
    assert "--provenance-dir source-provenance" in workflow_text
    assert "--expected-provenance linux-test-source-provenance.json" in workflow_text
    assert "python scripts/dev/run_tests.py verify-linux-ci" not in workflow_text
    assert "fetch-depth: 0" not in workflow_text
    assert "coverage combine test-results" in workflow_text
    assert "poetry run pytest tests/" not in workflow_text


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
                outcomes={
                    f"tests/unit/ui/test_example.py::test_{index}": "passed"
                    for index in range(3)
                },
            )
        )

    monkeypatch.setattr(run_tests, "_dispatch", fake_dispatch)

    assert run_tests.main(["ui", "--result-json", str(result_path)]) == 0
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["runner"] == "xbrainlab.sharded-test-runner"
    assert payload["command_args"] == ["ui"]
    assert payload["counts"] == counts
