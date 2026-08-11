#!/usr/bin/env python3
"""Fail only when basedpyright diagnostics regress from an exact target SHA."""

from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from typing import Any

_FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
Diagnostic = tuple[str, str, str, str, int, int]
ArchiveBase = Callable[[Path, str, Path], None]
Analyze = Callable[[Path, str], tuple[int, str, str]]
ResolveBase = Callable[[Path, str], str]


class ExactTargetRegressionError(RuntimeError):
    """Raised when exact-target regression evidence cannot be produced."""


def run_bounded(
    argv: list[str],
    *,
    cwd: Path,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603 - executable is resolved or fixed.
            argv,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise ExactTargetRegressionError(
            f"Command timed out after {timeout:g}s: {argv[0]}"
        ) from error


def resolve_exact_target(repo_root: Path, target_sha: str) -> str:
    git = shutil.which("git")
    if git is None:
        raise ExactTargetRegressionError("git executable is unavailable")
    if not _FULL_SHA.fullmatch(target_sha):
        raise ExactTargetRegressionError("target SHA must be a full 40-character SHA")
    resolved = run_bounded(
        [git, "rev-parse", "--verify", f"{target_sha}^{{commit}}"],
        cwd=repo_root,
        timeout=30,
    )
    exact = resolved.stdout.strip()
    if resolved.returncode != 0 or exact.casefold() != target_sha.casefold():
        raise ExactTargetRegressionError("authorized target SHA is unavailable")
    ancestor = run_bounded(
        [git, "merge-base", "--is-ancestor", exact, "HEAD"],
        cwd=repo_root,
        timeout=30,
    )
    if ancestor.returncode != 0:
        raise ExactTargetRegressionError(
            "authorized target SHA is not an ancestor of candidate HEAD"
        )
    return exact.casefold()


def archive_exact_target(repo_root: Path, target_sha: str, destination: Path) -> None:
    git = shutil.which("git")
    if git is None:
        raise ExactTargetRegressionError("git executable is unavailable")
    try:
        completed = subprocess.run(  # noqa: S603 - resolved git, fixed arguments.
            [git, "archive", "--format=tar", target_sha],
            cwd=repo_root,
            check=False,
            capture_output=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as error:
        raise ExactTargetRegressionError("git archive timed out") from error
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ExactTargetRegressionError(f"git archive failed: {detail}")

    destination_root = destination.resolve()
    with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
        for member in archive.getmembers():
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ExactTargetRegressionError("git archive contains unsafe path")
            target = destination.joinpath(*relative.parts)
            if not target.resolve().is_relative_to(destination_root):
                raise ExactTargetRegressionError("git archive escapes destination")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ExactTargetRegressionError(
                    "git archive contains unsupported non-file entry"
                )
            source = archive.extractfile(member)
            if source is None:
                raise ExactTargetRegressionError("git archive member is unreadable")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _analyze(root: Path, executable: str) -> tuple[int, str, str]:
    completed = run_bounded(
        [executable, "--outputjson"],
        cwd=root,
        timeout=1500,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _diagnostics(report_text: str, *, root: Path) -> Counter[Diagnostic]:
    try:
        report = json.loads(report_text)
    except json.JSONDecodeError as error:
        raise ExactTargetRegressionError("basedpyright output is not JSON") from error
    if not isinstance(report, dict):
        raise ExactTargetRegressionError("basedpyright report is not an object")
    raw_diagnostics = report.get("generalDiagnostics")
    if not isinstance(raw_diagnostics, list):
        raise ExactTargetRegressionError(
            "basedpyright report has no generalDiagnostics list"
        )

    normalized: Counter[Diagnostic] = Counter()
    resolved_root = root.resolve()
    for raw in raw_diagnostics:
        if not isinstance(raw, Mapping):
            raise ExactTargetRegressionError("basedpyright diagnostic is malformed")
        raw_file = raw.get("file")
        severity = raw.get("severity")
        message = raw.get("message")
        rule = raw.get("rule", "")
        diagnostic_range = raw.get("range")
        if (
            not isinstance(raw_file, str)
            or not isinstance(severity, str)
            or not isinstance(message, str)
        ):
            raise ExactTargetRegressionError("basedpyright diagnostic is incomplete")
        if not isinstance(diagnostic_range, Mapping):
            raise ExactTargetRegressionError("basedpyright diagnostic range is missing")
        start = diagnostic_range.get("start")
        if not isinstance(start, Mapping):
            raise ExactTargetRegressionError("basedpyright diagnostic start is missing")
        line = start.get("line")
        character = start.get("character")
        if (
            isinstance(line, bool)
            or not isinstance(line, int)
            or line < 0
            or isinstance(character, bool)
            or not isinstance(character, int)
            or character < 0
        ):
            raise ExactTargetRegressionError("basedpyright diagnostic range is invalid")
        try:
            relative = Path(raw_file).resolve().relative_to(resolved_root).as_posix()
        except ValueError as error:
            raise ExactTargetRegressionError(
                "basedpyright diagnostic points outside analyzed tree"
            ) from error
        normalized[
            (
                relative,
                severity,
                str(rule or ""),
                " ".join(message.split()),
                line,
                character,
            )
        ] += 1
    return normalized


def _records(diagnostics: Counter[Diagnostic]) -> list[dict[str, object]]:
    return [
        {
            "count": count,
            "file": diagnostic[0],
            "severity": diagnostic[1],
            "rule": diagnostic[2],
            "message": diagnostic[3],
            "line": diagnostic[4],
            "character": diagnostic[5],
        }
        for diagnostic, count in sorted(diagnostics.items())
    ]


def compare_diagnostics(
    base_report: str,
    candidate_report: str,
    *,
    base_root: Path,
    candidate_root: Path,
) -> dict[str, object]:
    """Return a location-stable multiset comparison of two JSON reports."""
    baseline = _diagnostics(base_report, root=base_root)
    candidate = _diagnostics(candidate_report, root=candidate_root)
    new = candidate - baseline
    resolved = baseline - candidate
    return {
        "passed": not new,
        "baseline_diagnostic_count": baseline.total(),
        "candidate_diagnostic_count": candidate.total(),
        "baseline_error_count": sum(
            count for diagnostic, count in baseline.items() if diagnostic[1] == "error"
        ),
        "candidate_error_count": sum(
            count for diagnostic, count in candidate.items() if diagnostic[1] == "error"
        ),
        "new_diagnostics": _records(new),
        "resolved_diagnostics": _records(resolved),
    }


def run_regression_check(
    repo_root: Path,
    *,
    target_sha: str,
    basedpyright_executable: str,
    archive_base: ArchiveBase = archive_exact_target,
    analyze: Analyze = _analyze,
    resolve_base: ResolveBase = resolve_exact_target,
) -> tuple[int, dict[str, Any]]:
    """Analyze candidate and exact base with one executable and compare results."""
    root = repo_root.expanduser().resolve(strict=True)
    exact_target = resolve_base(root, target_sha)
    with tempfile.TemporaryDirectory(prefix="xbrainlab-basedpyright-base-") as raw_dir:
        base_root = Path(raw_dir)
        archive_base(root, exact_target, base_root)
        with ThreadPoolExecutor(max_workers=2) as executor:
            candidate_future = executor.submit(
                analyze,
                root,
                basedpyright_executable,
            )
            target_future = executor.submit(
                analyze,
                base_root,
                basedpyright_executable,
            )
            candidate_code, candidate_stdout, candidate_stderr = (
                candidate_future.result()
            )
            base_code, base_stdout, base_stderr = target_future.result()
        if candidate_code not in {0, 1}:
            raise ExactTargetRegressionError(
                "candidate basedpyright execution failed: " + candidate_stderr.strip()
            )
        if base_code not in {0, 1}:
            raise ExactTargetRegressionError(
                "target basedpyright execution failed: " + base_stderr.strip()
            )
        result = compare_diagnostics(
            base_stdout,
            candidate_stdout,
            base_root=base_root,
            candidate_root=root,
        )

    result.update(
        {
            "schema_version": 1,
            "target_sha": exact_target,
            "candidate_return_code": candidate_code,
            "target_return_code": base_code,
            "comparison_policy": (
                "relative-path,severity,rule,normalized-message,start-line,"
                "start-character multiset"
            ),
        }
    )
    return (0 if result["passed"] else 1), result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--target-sha", required=True)
    return parser


def _basedpyright_executable() -> str | None:
    executable = shutil.which("basedpyright")
    if executable is not None:
        return executable
    sibling = Path(sys.executable).with_name("basedpyright")
    return str(sibling) if sibling.is_file() else None


def main() -> int:
    args = _parser().parse_args()
    executable = _basedpyright_executable()
    if executable is None:
        print("basedpyright executable is unavailable", file=sys.stderr)
        return 2
    try:
        exit_code, result = run_regression_check(
            args.repo_root,
            target_sha=args.target_sha,
            basedpyright_executable=executable,
        )
    except (ExactTargetRegressionError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
