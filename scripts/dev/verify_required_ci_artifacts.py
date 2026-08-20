#!/usr/bin/env python3
"""Verify every declared authoritative CI artifact before upload."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from scripts.dev.ci_source_provenance import validate_ci_source_provenance


def verify_required_ci_artifacts(
    *,
    required_json: Sequence[Path],
    provenance_path: Path,
    expected_job_key: str,
    expected_github_job: str,
    expected_runner_os: str,
) -> tuple[str, ...]:
    """Return failures for each missing/malformed result and its source binding."""
    failures: list[str] = []
    for path in required_json:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError:
            failures.append(f"Required CI JSON is missing: {path.as_posix()}")
            continue
        except ValueError:
            failures.append(f"Required CI JSON is malformed: {path.as_posix()}")
            continue
        if payload is None:
            failures.append(f"Required CI JSON is empty: {path.as_posix()}")

    _payload, provenance_failure = validate_ci_source_provenance(
        provenance_path,
        expected_job_key=expected_job_key,
        expected_github_job=expected_github_job,
        expected_runner_os=expected_runner_os,
    )
    if provenance_failure is not None:
        failures.append(provenance_failure)
    return tuple(failures)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--required-json", type=Path, action="append", required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--expected-job-key", required=True)
    parser.add_argument("--expected-github-job", required=True)
    parser.add_argument("--expected-runner-os", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    failures = verify_required_ci_artifacts(
        required_json=args.required_json,
        provenance_path=args.provenance,
        expected_job_key=args.expected_job_key,
        expected_github_job=args.expected_github_job,
        expected_runner_os=args.expected_runner_os,
    )
    for failure in failures:
        print(f"ERROR: {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
