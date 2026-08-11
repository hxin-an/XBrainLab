from __future__ import annotations

from pathlib import Path

from scripts.dev.run_architecture_compliance_regression import (
    compare_violations,
    run_regression_check,
)


def _output(*violations: str) -> str:
    if not violations:
        return "Architecture compliance checks passed.\n"
    return "Violations Found:\n" + "".join(
        f" - {violation}\n" for violation in violations
    )


def test_compare_violations_allows_resolved_target_debt() -> None:
    result = compare_violations(
        _output("tests/a.py:10 old", "tests/b.py:20 fixed"),
        _output("tests/a.py:10 old"),
    )

    assert result["passed"] is True
    assert result["new_violations"] == []
    assert result["resolved_violations"] == [
        {
            "category": "Violations Found",
            "count": 1,
            "violation": "tests/b.py:20 fixed",
        }
    ]


def test_compare_violations_fails_on_new_or_relocated_violation() -> None:
    result = compare_violations(
        _output("tests/a.py:10 same"),
        _output("tests/a.py:200 same", "tests/b.py:30 new"),
    )

    assert result["passed"] is False
    assert result["new_violations"] == [
        {
            "category": "Violations Found",
            "count": 1,
            "violation": "tests/a.py:200 same",
        },
        {
            "category": "Violations Found",
            "count": 1,
            "violation": "tests/b.py:30 new",
        },
    ]


def test_compare_violations_does_not_offset_same_text_across_rule_categories() -> None:
    result = compare_violations(
        "Early Violations Found:\n - same text\n",
        "Later Violations Found:\n - same text\n",
    )

    assert result["passed"] is False
    assert result["new_violations"] == [
        {"category": "Later Violations Found", "count": 1, "violation": "same text"}
    ]


def test_runner_uses_candidate_guard_policy_for_candidate_and_exact_target(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    checker = repo / "tests" / "architecture_compliance.py"
    checker.parent.mkdir()
    checker.write_text("# candidate policy\n", encoding="utf-8")
    calls: list[tuple[Path, Path]] = []

    def archive(_root: Path, target_sha: str, destination: Path) -> None:
        assert target_sha == "c" * 40
        (destination / "tests").mkdir(parents=True)

    def analyze(root: Path, checker_path: Path) -> tuple[int, str, str]:
        calls.append((root, checker_path))
        return 1, _output("tests/a.py:10 old"), ""

    exit_code, result = run_regression_check(
        repo,
        target_sha="c" * 40,
        archive_target=archive,
        analyze=analyze,
        resolve_target=lambda _root, target_sha: target_sha,
    )

    assert exit_code == 0
    assert result["target_sha"] == "c" * 40
    assert result["comparison_policy"] == (
        "candidate-policy category+normalized-violation multiset; locations retained"
    )
    assert {root for root, _checker in calls} != {repo.resolve()}
    assert {checker_path for _root, checker_path in calls} == {checker.resolve()}
