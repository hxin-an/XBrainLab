from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.dev.run_basedpyright_regression import (
    ExactTargetRegressionError,
    compare_diagnostics,
    resolve_exact_target,
    run_regression_check,
)


def _report(*diagnostics: dict[str, object]) -> str:
    return json.dumps(
        {
            "version": "1.39.2",
            "generalDiagnostics": list(diagnostics),
            "summary": {"errorCount": len(diagnostics)},
        }
    )


def _diagnostic(
    root: Path,
    relative_path: str,
    message: str,
    *,
    line: int = 1,
) -> dict[str, object]:
    return {
        "file": str(root / relative_path),
        "severity": "error",
        "message": message,
        "rule": "reportCallIssue",
        "range": {
            "start": {"line": line, "character": 2},
            "end": {"line": line, "character": 3},
        },
    }


def test_compare_diagnostics_allows_exact_base_debt_and_reports_resolutions(
    tmp_path: Path,
) -> None:
    base_root = tmp_path / "base"
    candidate_root = tmp_path / "candidate"
    base = _report(
        _diagnostic(base_root, "XBrainLab/old.py", "old issue"),
        _diagnostic(base_root, "XBrainLab/fixed.py", "fixed issue"),
    )
    candidate = _report(
        _diagnostic(candidate_root, "XBrainLab/old.py", "old issue"),
    )

    result = compare_diagnostics(
        base,
        candidate,
        base_root=base_root,
        candidate_root=candidate_root,
    )

    assert result["passed"] is True
    assert result["baseline_error_count"] == 2
    assert result["candidate_error_count"] == 1
    assert result["new_diagnostics"] == []
    assert result["resolved_diagnostics"] == [
        {
            "count": 1,
            "file": "XBrainLab/fixed.py",
            "message": "fixed issue",
            "rule": "reportCallIssue",
            "severity": "error",
            "line": 1,
            "character": 2,
        }
    ]


def test_compare_diagnostics_fails_on_new_or_duplicated_candidate_error(
    tmp_path: Path,
) -> None:
    base_root = tmp_path / "base"
    candidate_root = tmp_path / "candidate"
    existing = _diagnostic(base_root, "XBrainLab/a.py", "same issue")
    candidate_existing = _diagnostic(
        candidate_root,
        "XBrainLab/a.py",
        "same issue",
    )
    new_issue = _diagnostic(candidate_root, "XBrainLab/b.py", "new issue")

    result = compare_diagnostics(
        _report(existing),
        _report(candidate_existing, candidate_existing, new_issue),
        base_root=base_root,
        candidate_root=candidate_root,
    )

    assert result["passed"] is False
    assert result["new_diagnostics"] == [
        {
            "count": 1,
            "file": "XBrainLab/a.py",
            "message": "same issue",
            "rule": "reportCallIssue",
            "severity": "error",
            "line": 1,
            "character": 2,
        },
        {
            "count": 1,
            "file": "XBrainLab/b.py",
            "message": "new issue",
            "rule": "reportCallIssue",
            "severity": "error",
            "line": 1,
            "character": 2,
        },
    ]


def test_compare_diagnostics_does_not_offset_a_fixed_site_with_a_new_site(
    tmp_path: Path,
) -> None:
    base_root = tmp_path / "base"
    candidate_root = tmp_path / "candidate"

    result = compare_diagnostics(
        _report(_diagnostic(base_root, "XBrainLab/a.py", "same issue", line=10)),
        _report(_diagnostic(candidate_root, "XBrainLab/a.py", "same issue", line=200)),
        base_root=base_root,
        candidate_root=candidate_root,
    )

    assert result["passed"] is False
    assert result["new_diagnostics"] == [
        {
            "count": 1,
            "file": "XBrainLab/a.py",
            "message": "same issue",
            "rule": "reportCallIssue",
            "severity": "error",
            "line": 200,
            "character": 2,
        }
    ]


def test_regression_check_compares_same_executable_against_exact_archived_base(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    calls: list[tuple[str, Path]] = []

    def archive(_root: Path, target_sha: str, destination: Path) -> None:
        assert target_sha == "b" * 40
        (destination / "XBrainLab").mkdir(parents=True)

    def analyze(root: Path, executable: str) -> tuple[int, str, str]:
        calls.append((executable, root))
        diagnostic_root = root
        return (
            1,
            _report(_diagnostic(diagnostic_root, "XBrainLab/a.py", "old issue")),
            "",
        )

    exit_code, result = run_regression_check(
        repo,
        target_sha="b" * 40,
        basedpyright_executable="/venv/bin/basedpyright",
        archive_base=archive,
        analyze=analyze,
        resolve_base=lambda _root, target_sha: target_sha,
    )

    assert exit_code == 0
    assert result["passed"] is True
    assert result["target_sha"] == "b" * 40
    assert calls[0] == ("/venv/bin/basedpyright", repo.resolve())
    assert calls[1][0] == "/venv/bin/basedpyright"
    assert calls[1][1] != repo.resolve()


def test_resolve_exact_target_rejects_target_tip_outside_candidate_history(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git_executable = shutil.which("git")
    assert git_executable is not None

    def git(*args: str) -> str:
        completed = subprocess.run(  # noqa: S603 - fixed test-only git commands.
            [
                git_executable,
                "-c",
                "user.name=Validation Test",
                "-c",
                "user.email=validation@example.invalid",
                *args,
            ],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    git("init", "--initial-branch=main")
    (repo / "root.txt").write_text("root\n", encoding="utf-8")
    git("add", "root.txt")
    git("commit", "-m", "root")
    root_sha = git("rev-parse", "HEAD")
    (repo / "target.txt").write_text("target\n", encoding="utf-8")
    git("add", "target.txt")
    git("commit", "-m", "target")
    target_sha = git("rev-parse", "HEAD")
    git("switch", "--create", "candidate", root_sha)
    (repo / "candidate.txt").write_text("candidate\n", encoding="utf-8")
    git("add", "candidate.txt")
    git("commit", "-m", "candidate")

    with pytest.raises(
        ExactTargetRegressionError,
        match="not an ancestor of candidate HEAD",
    ):
        resolve_exact_target(repo, target_sha)
