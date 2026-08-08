from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from scripts.dev import run_required_pytest_gate as gate


def test_required_gate_records_skip_xpass_and_deselection() -> None:
    observer = gate.RequiredPytestGate()

    observer.pytest_runtest_logreport(
        SimpleNamespace(
            nodeid="tests/test_public.py::test_missing",
            when="setup",
            skipped=True,
            passed=False,
            wasxfail=None,
            longrepr="fixture missing",
            keywords={},
        )
    )
    observer.pytest_runtest_logreport(
        SimpleNamespace(
            nodeid="tests/test_public.py::test_unexpected_pass",
            when="call",
            skipped=False,
            passed=True,
            wasxfail="known gap",
            longrepr="",
        )
    )
    observer.pytest_deselected(
        [SimpleNamespace(nodeid="tests/test_public.py::test_not_run")]
    )

    assert observer.clean is False
    assert observer.skipped == ["tests/test_public.py::test_missing"]
    assert observer.xpassed == ["tests/test_public.py::test_unexpected_pass"]
    assert observer.deselected == ["tests/test_public.py::test_not_run"]


def test_required_gate_main_fails_when_pytest_skips(monkeypatch, tmp_path) -> None:
    def fake_main(args, *, plugins):
        assert args == ["tests/integration/io/test_public_bids_fixture.py", "-q"]
        plugin = plugins[0]
        plugin.pytest_runtest_logreport(
            SimpleNamespace(
                nodeid="required::case",
                when="setup",
                skipped=True,
                passed=False,
                wasxfail=None,
                longrepr="missing fixture",
                keywords={},
            )
        )
        return 0

    monkeypatch.setattr(gate.pytest, "main", fake_main)

    result_path = tmp_path / "skip-result.json"
    assert (
        gate.main(
            [
                "--result-json",
                str(result_path),
                "--",
                "tests/integration/io/test_public_bids_fixture.py",
                "-q",
            ]
        )
        == 1
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["completed"] is True
    assert payload["exit_code"] == 1
    assert payload["counts"]["skipped"] == 1


def test_required_gate_allows_explicit_platform_contract_skip(
    monkeypatch, tmp_path
) -> None:
    def fake_main(args, *, plugins):
        assert args == ["tests/test_platform.py", "-q"]
        observer = plugins[0]
        observer.pytest_collection_finish(SimpleNamespace(items=[object()]))
        observer.pytest_runtest_logreport(
            SimpleNamespace(
                nodeid="tests/test_platform.py::test_posix_contract",
                when="setup",
                skipped=True,
                failed=False,
                passed=False,
                wasxfail=None,
                keywords={"platform_contract": True},
            )
        )
        return 0

    monkeypatch.setattr(gate.pytest, "main", fake_main)
    result_path = tmp_path / "platform-skip-result.json"

    assert (
        gate.main(
            [
                "--result-json",
                str(result_path),
                "--",
                "tests/test_platform.py",
                "-q",
            ]
        )
        == 0
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["counts"]["skipped"] == 1


def test_os_specific_skip_contracts_are_explicitly_marked() -> None:
    offenders: list[str] = []
    for path in Path("tests").rglob("test_*.py"):
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if not line.strip().startswith("@pytest.mark.skipif(os.name"):
                continue
            decorators = lines[max(0, index - 2) : index]
            if not any("@pytest.mark.platform_contract" in item for item in decorators):
                offenders.append(f"{path.as_posix()}:{index + 1}")

    assert offenders == []


def test_required_gate_main_preserves_pytest_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(gate.pytest, "main", lambda _args, *, plugins: 3)

    result_path = tmp_path / "failure-result.json"
    assert (
        gate.main(
            [
                "--result-json",
                str(result_path),
                "--",
                "tests/integration/io/test_public_bids_fixture.py",
            ]
        )
        == 3
    )
    assert json.loads(result_path.read_text(encoding="utf-8"))["exit_code"] == 3


def test_required_gate_writes_clean_completion_attestation(
    monkeypatch, tmp_path
) -> None:
    def fake_main(args, *, plugins):
        assert args == ["tests/test_clean.py", "-q"]
        observer = plugins[0]
        observer.pytest_collection_finish(SimpleNamespace(items=[object()]))
        observer.pytest_runtest_logreport(
            SimpleNamespace(
                nodeid="tests/test_clean.py::test_clean",
                when="call",
                skipped=False,
                failed=False,
                passed=True,
                wasxfail=None,
            )
        )
        return 0

    monkeypatch.setattr(gate.pytest, "main", fake_main)
    result_path = tmp_path / "clean-result.json"

    assert (
        gate.main(
            ["--result-json", str(result_path), "--", "tests/test_clean.py", "-q"]
        )
        == 0
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["runner"] == "xbrainlab.required-pytest-gate"
    assert payload["command_args"] == ["tests/test_clean.py", "-q"]
    assert payload["counts"] == {
        "collected": 1,
        "deselected": 0,
        "errors": 0,
        "executed": 1,
        "failed": 0,
        "passed": 1,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
    }


def test_required_gate_attests_original_args_when_pytest_mutates_its_list(
    monkeypatch, tmp_path
) -> None:
    def fake_main(args, *, plugins):
        del plugins
        args[:0] = ["-ra", "-v"]
        return 3

    monkeypatch.setattr(gate.pytest, "main", fake_main)
    result_path = tmp_path / "mutated-args-result.json"

    assert (
        gate.main(
            ["--result-json", str(result_path), "--", "tests/test_clean.py", "-q"]
        )
        == 3
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["command_args"] == ["tests/test_clean.py", "-q"]


def test_required_gate_fails_when_collected_case_has_no_terminal_outcome(
    monkeypatch, tmp_path
) -> None:
    def fake_main(_args, *, plugins):
        observer = plugins[0]
        observer.pytest_collection_finish(SimpleNamespace(items=[object(), object()]))
        observer.pytest_runtest_logreport(
            SimpleNamespace(
                nodeid="tests/test_clean.py::test_reported",
                when="call",
                skipped=False,
                failed=False,
                passed=True,
                wasxfail=None,
            )
        )
        return 0

    monkeypatch.setattr(gate.pytest, "main", fake_main)
    result_path = tmp_path / "incomplete-result.json"

    assert (
        gate.main(["--result-json", str(result_path), "--", "tests/test_clean.py"]) == 1
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["exit_code"] == 1
    assert payload["counts"]["collected"] == 2
    assert payload["counts"]["executed"] == 1


def test_early_process_exit_cannot_forge_completion_attestation(tmp_path) -> None:
    test_file = tmp_path / "test_early_exit.py"
    test_file.write_text(
        "import os\n\ndef test_early_exit():\n"
        "    print('================ 1 passed in 0.01s ================', flush=True)\n"
        "    os._exit(0)\n",
        encoding="utf-8",
    )
    result_path = tmp_path / "must-not-exist.json"
    runner = Path(gate.__file__).resolve()

    completed = subprocess.run(  # noqa: S603 - exact test-owned interpreter and file.
        [
            sys.executable,
            str(runner),
            "--result-json",
            str(result_path),
            "--",
            "-s",
            "-q",
            str(test_file),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0
    assert "1 passed in 0.01s" in completed.stdout
    assert not result_path.exists()


def test_required_gate_rejects_missing_result_path() -> None:
    assert gate.main(["--", "tests/test_clean.py"]) == 2
