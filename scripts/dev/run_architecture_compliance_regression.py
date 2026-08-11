#!/usr/bin/env python3
"""Fail only when architecture violations regress from an exact target SHA."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.dev.run_basedpyright_regression import (
    ArchiveBase,
    ExactTargetRegressionError,
    ResolveBase,
    archive_exact_target,
    resolve_exact_target,
    run_bounded,
)

Analyze = Callable[[Path, Path], tuple[int, str, str]]
Violation = tuple[str, str]


def _analyze(root: Path, checker: Path) -> tuple[int, str, str]:
    completed = run_bounded(
        [sys.executable, str(checker)],
        cwd=root,
        timeout=360,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _violations(output: str) -> Counter[Violation]:
    violations: Counter[Violation] = Counter()
    category: str | None = None
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line.endswith("Violations Found:"):
            category = " ".join(line.removesuffix(":").split())
            continue
        if line.startswith("- "):
            violation = " ".join(line[2:].split())
            if violation:
                if category is None:
                    raise ExactTargetRegressionError(
                        "architecture violation has no rule category"
                    )
                violations[(category, violation)] += 1
    return violations


def _records(violations: Counter[Violation]) -> list[dict[str, object]]:
    return [
        {"category": category, "count": count, "violation": violation}
        for (category, violation), count in sorted(violations.items())
    ]


def compare_violations(
    target_output: str,
    candidate_output: str,
) -> dict[str, object]:
    """Compare normalized violation multisets without trusting exit prose."""
    target = _violations(target_output)
    candidate = _violations(candidate_output)
    new = candidate - target
    resolved = target - candidate
    return {
        "passed": not new,
        "target_violation_count": target.total(),
        "candidate_violation_count": candidate.total(),
        "new_violations": _records(new),
        "resolved_violations": _records(resolved),
    }


def _require_supported_result(
    *,
    label: str,
    return_code: int,
    stdout: str,
    stderr: str,
) -> None:
    if return_code not in {0, 1}:
        raise ExactTargetRegressionError(
            f"{label} architecture checker failed: {stderr.strip()}"
        )
    violation_count = _violations(stdout).total()
    if (return_code == 0) != (violation_count == 0):
        raise ExactTargetRegressionError(
            f"{label} architecture checker result is internally inconsistent"
        )


def run_regression_check(
    repo_root: Path,
    *,
    target_sha: str,
    archive_target: ArchiveBase = archive_exact_target,
    analyze: Analyze = _analyze,
    resolve_target: ResolveBase = resolve_exact_target,
) -> tuple[int, dict[str, Any]]:
    """Run the candidate guard policy against candidate and exact target trees."""
    root = repo_root.expanduser().resolve(strict=True)
    exact_target = resolve_target(root, target_sha)
    checker = (root / "tests" / "architecture_compliance.py").resolve(strict=True)
    with tempfile.TemporaryDirectory(
        prefix="xbrainlab-architecture-target-"
    ) as raw_dir:
        target_root = Path(raw_dir)
        archive_target(root, exact_target, target_root)
        with ThreadPoolExecutor(max_workers=2) as executor:
            candidate_future = executor.submit(analyze, root, checker)
            target_future = executor.submit(analyze, target_root, checker)
            candidate_code, candidate_stdout, candidate_stderr = (
                candidate_future.result()
            )
            target_code, target_stdout, target_stderr = target_future.result()
        _require_supported_result(
            label="candidate",
            return_code=candidate_code,
            stdout=candidate_stdout,
            stderr=candidate_stderr,
        )
        _require_supported_result(
            label="target",
            return_code=target_code,
            stdout=target_stdout,
            stderr=target_stderr,
        )
        result = compare_violations(target_stdout, candidate_stdout)

    result.update(
        {
            "schema_version": 1,
            "target_sha": exact_target,
            "candidate_return_code": candidate_code,
            "target_return_code": target_code,
            "comparison_policy": (
                "candidate-policy normalized violation-line multiset; "
                "locations retained"
            ),
        }
    )
    return (0 if result["passed"] else 1), result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--target-sha", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        exit_code, result = run_regression_check(
            args.repo_root,
            target_sha=args.target_sha,
        )
    except (ExactTargetRegressionError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
