from __future__ import annotations

from scripts.dev.pytest_completion_attestation import (
    REQUIRED_PYTEST_RUNNER_ID,
    build_attestation,
    validate_attestation,
    write_attestation,
)


def _counts() -> dict[str, int]:
    return {
        "collected": 2,
        "executed": 2,
        "passed": 2,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "deselected": 0,
    }


def test_attestation_round_trip_requires_exact_runner_args_and_exit(tmp_path) -> None:
    path = tmp_path / "pytest-result.json"
    payload = build_attestation(
        runner=REQUIRED_PYTEST_RUNNER_ID,
        command_args=("tests/example.py", "-q"),
        exit_code=0,
        counts=_counts(),
    )
    write_attestation(path, payload)

    loaded, failure = validate_attestation(
        path,
        expected_runner=REQUIRED_PYTEST_RUNNER_ID,
        expected_args=("tests/example.py", "-q"),
        expected_exit_code=0,
    )

    assert failure is None
    assert loaded == payload


def test_attestation_missing_file_fails_closed(tmp_path) -> None:
    loaded, failure = validate_attestation(
        tmp_path / "missing.json",
        expected_runner=REQUIRED_PYTEST_RUNNER_ID,
        expected_args=("tests/example.py",),
        expected_exit_code=0,
    )

    assert loaded is None
    assert failure == "Pytest completion attestation was not produced."


def test_attestation_rejects_inconsistent_counts(tmp_path) -> None:
    path = tmp_path / "invalid.json"
    counts = _counts()
    counts["executed"] = 1
    write_attestation(
        path,
        build_attestation(
            runner=REQUIRED_PYTEST_RUNNER_ID,
            command_args=("tests/example.py",),
            exit_code=0,
            counts=counts,
        ),
    )

    loaded, failure = validate_attestation(
        path,
        expected_runner=REQUIRED_PYTEST_RUNNER_ID,
        expected_args=("tests/example.py",),
        expected_exit_code=0,
    )

    assert loaded is None
    assert failure == "Pytest completion attestation executed count is inconsistent."


def test_attestation_rejects_collected_case_without_terminal_outcome(tmp_path) -> None:
    path = tmp_path / "incomplete.json"
    counts = _counts()
    counts["collected"] = 3
    write_attestation(
        path,
        build_attestation(
            runner=REQUIRED_PYTEST_RUNNER_ID,
            command_args=("tests/example.py",),
            exit_code=0,
            counts=counts,
        ),
    )

    loaded, failure = validate_attestation(
        path,
        expected_runner=REQUIRED_PYTEST_RUNNER_ID,
        expected_args=("tests/example.py",),
        expected_exit_code=0,
    )

    assert loaded is None
    assert failure == "Pytest completion attestation collected count is inconsistent."
