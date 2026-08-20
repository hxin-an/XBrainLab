#!/usr/bin/env python3
"""Fail closed on incomplete native platform smoke evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.dev.ci_source_provenance import validate_ci_source_provenance


def verify_native_ci_evidence(
    *,
    smoke_path: Path,
    provenance_path: Path,
    expected_job_key: str,
    expected_runner_os: str,
    expected_artifact_type: str,
    expected_qt_platform: str,
    expected_isolated_root: Path,
) -> tuple[str, ...]:
    """Return all bounded evidence failures without accepting partial output."""
    failures: list[str] = []
    try:
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        smoke = None
        failures.append("Native platform smoke artifact is unreadable.")
    if not isinstance(smoke, dict):
        if smoke is not None:
            failures.append("Native platform smoke artifact is malformed.")
    else:
        if smoke.get("artifact_type") != expected_artifact_type:
            failures.append("Native platform smoke artifact type does not match.")
        if smoke.get("passed") is not True:
            failures.append("Native platform smoke did not pass.")
        if smoke.get("qt_platform") != expected_qt_platform:
            failures.append("Native platform smoke used the wrong Qt platform.")
        expected_root = str(expected_isolated_root.expanduser().resolve())
        if smoke.get("isolated_root") != expected_root:
            failures.append("Native platform smoke used the wrong isolated root.")

    _payload, provenance_failure = validate_ci_source_provenance(
        provenance_path,
        expected_job_key=expected_job_key,
        expected_github_job="native-platform-source",
        expected_runner_os=expected_runner_os,
    )
    if provenance_failure is not None:
        failures.append(provenance_failure)
    return tuple(failures)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--expected-job-key", required=True)
    parser.add_argument("--expected-runner-os", required=True)
    parser.add_argument("--expected-artifact-type", required=True)
    parser.add_argument("--expected-platform", required=True)
    parser.add_argument("--expected-isolated-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    failures = verify_native_ci_evidence(
        smoke_path=args.smoke,
        provenance_path=args.provenance,
        expected_job_key=args.expected_job_key,
        expected_runner_os=args.expected_runner_os,
        expected_artifact_type=args.expected_artifact_type,
        expected_qt_platform=args.expected_platform,
        expected_isolated_root=args.expected_isolated_root,
    )
    for failure in failures:
        print(f"ERROR: {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
