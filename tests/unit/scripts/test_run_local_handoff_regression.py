from __future__ import annotations

from pathlib import Path

from scripts.dev import run_local_handoff_regression as runner
from scripts.dev import run_tests


def test_fixed_phases_partition_authoritative_linux_groups_once() -> None:
    flattened = tuple(command for phase in runner.FIXED_PHASES for command in phase)

    assert flattened == run_tests.LINUX_CI_COMMANDS
    assert len(flattened) == len(set(flattened))
    assert runner.MAX_PARALLEL_GROUPS == 2


def test_failure_stops_before_next_phase_and_writes_failed_aggregate(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    verified: list[bool] = []

    def fake_group(command: str, *, evidence_dir: Path) -> int:
        calls.append(command)
        return 1 if command == runner.FIXED_PHASES[0][0] else 0

    def fake_verify(evidence_dir, result_path):
        verified.append(True)
        return 1

    monkeypatch.setattr(runner, "_execute_group", fake_group)
    monkeypatch.setattr(runner, "verify_linux_ci_evidence", fake_verify)

    result = runner.run_local_handoff_regression(
        evidence_dir=tmp_path / "groups",
        result_path=tmp_path / "complete.json",
    )

    assert result == 1
    assert set(calls) == set(runner.FIXED_PHASES[0])
    assert not set(calls).intersection(runner.FIXED_PHASES[1])
    assert verified == [True]


def test_success_runs_both_phases_and_verifies_group_coverage(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    verified: list[bool] = []
    monkeypatch.setattr(
        runner,
        "_execute_group",
        lambda command, *, evidence_dir: calls.append(command) or 0,
    )
    monkeypatch.setattr(
        runner,
        "verify_linux_ci_evidence",
        lambda _evidence, _result: (verified.append(True) or 0),
    )

    result = runner.run_local_handoff_regression(
        evidence_dir=tmp_path / "groups",
        result_path=tmp_path / "complete.json",
    )

    assert result == 0
    assert set(calls) == set(run_tests.LINUX_CI_COMMANDS)
    assert verified == [True]


def test_group_execution_uses_owned_coverage_file_except_timing_group(
    monkeypatch,
    tmp_path: Path,
) -> None:
    environments: list[dict[str, str]] = []

    class Process:
        def wait(self, *, timeout):
            return 0

    class Owner:
        def close(self, *, grace_seconds):
            return None

    def fake_spawn(_argv, **kwargs):
        environments.append(kwargs["env"])
        return Process(), Owner()

    monkeypatch.setattr(runner, "spawn_owned_process", fake_spawn)
    covered = run_tests.LINUX_CI_COMMANDS[0]
    timing = next(iter(run_tests.LINUX_CI_UNCOVERED_COMMANDS))

    assert runner._execute_group(covered, evidence_dir=tmp_path / "covered") == 0
    assert runner._execute_group(timing, evidence_dir=tmp_path / "timing") == 0

    assert environments[0]["COVERAGE_FILE"].endswith(f".coverage.{covered}")
    assert "COVERAGE_FILE" not in environments[1]
    assert not Path(environments[0]["XBRAINLAB_TEST_TMPDIR"]).is_relative_to(
        tmp_path / "covered"
    )
