from __future__ import annotations

from scripts.dev.pytest_completion_attestation import (
    REQUIRED_PYTEST_RUNNER_ID,
    aggregate_outcomes,
    build_attestation,
    required_outcome_failure,
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


def _outcomes() -> dict[str, str]:
    return {
        "tests/example.py::test_one": "passed",
        "tests/example.py::test_two": "passed",
    }


def test_attestation_round_trip_requires_exact_runner_args_and_exit(tmp_path) -> None:
    path = tmp_path / "pytest-result.json"
    payload = build_attestation(
        runner=REQUIRED_PYTEST_RUNNER_ID,
        command_args=("tests/example.py", "-q"),
        exit_code=0,
        counts=_counts(),
        outcomes=_outcomes(),
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
            outcomes=_outcomes(),
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
            outcomes=_outcomes(),
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


def test_attestation_rejects_outcomes_that_do_not_match_counts(tmp_path) -> None:
    path = tmp_path / "invalid-outcomes.json"
    write_attestation(
        path,
        build_attestation(
            runner=REQUIRED_PYTEST_RUNNER_ID,
            command_args=("tests/example.py",),
            exit_code=0,
            counts=_counts(),
            outcomes={"tests/example.py::test_one": "passed"},
        ),
    )

    loaded, failure = validate_attestation(
        path,
        expected_runner=REQUIRED_PYTEST_RUNNER_ID,
        expected_args=("tests/example.py",),
        expected_exit_code=0,
    )

    assert loaded is None
    assert failure == "Pytest completion attestation outcomes do not match counts."


def test_required_outcome_selectors_match_files_and_exact_nodes() -> None:
    attestation = {"outcomes": _outcomes()}

    assert required_outcome_failure(attestation, ("tests/example.py",)) is None
    assert (
        required_outcome_failure(
            attestation,
            ("tests/example.py::test_two",),
        )
        is None
    )
    assert "no terminal evidence" in str(
        required_outcome_failure(attestation, ("tests/missing.py",))
    )


def test_required_outcome_selector_rejects_nonpassing_case() -> None:
    attestation = {
        "outcomes": {
            "tests/example.py::test_one": "passed",
            "tests/example.py::test_two": "skipped",
        }
    }

    failure = required_outcome_failure(attestation, ("tests/example.py",))

    assert failure is not None
    assert "test_two" in failure


def test_aggregate_outcomes_rejects_duplicate_node_evidence() -> None:
    try:
        aggregate_outcomes(
            (
                {"outcomes": {"tests/example.py::test_one": "passed"}},
                {"outcomes": {"tests/example.py::test_one": "passed"}},
            )
        )
    except ValueError as error:
        assert "Duplicate pytest outcome" in str(error)
    else:
        raise AssertionError("duplicate node evidence must fail closed")
