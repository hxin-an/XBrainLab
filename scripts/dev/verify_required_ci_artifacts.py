#!/usr/bin/env python3
"""Verify every declared authoritative CI artifact before upload."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from scripts.dev.ci_source_provenance import validate_ci_source_provenance
from scripts.dev.pytest_completion_attestation import (
    REQUIRED_PYTEST_RUNNER_ID,
    SHARDED_PYTEST_RUNNER_ID,
)

ArtifactValidator = Callable[[Mapping[str, Any]], str | None]


def _pytest_failure(
    payload: Mapping[str, Any],
    *,
    expected_runner: str,
) -> str | None:
    if payload.get("schema_version") != 2 or payload.get("runner") != expected_runner:
        return "pytest completion schema or runner does not match"
    if payload.get("completed") is not True or payload.get("exit_code") != 0:
        return "pytest execution did not complete successfully"
    counts = payload.get("counts")
    outcomes = payload.get("outcomes")
    if not isinstance(counts, Mapping) or not isinstance(outcomes, Mapping):
        return "pytest completion counts or outcomes are missing"
    if not outcomes or not isinstance(counts.get("executed"), int):
        return "pytest completion contains no terminal outcomes"
    if counts.get("executed", 0) <= 0:
        return "pytest completion did not execute any tests"
    if any(counts.get(name) != 0 for name in ("failed", "errors")):
        return "pytest completion contains a failed or error outcome"
    return None


def _sharded_pytest_failure(payload: Mapping[str, Any]) -> str | None:
    return _pytest_failure(payload, expected_runner=SHARDED_PYTEST_RUNNER_ID)


def _required_pytest_failure(payload: Mapping[str, Any]) -> str | None:
    return _pytest_failure(payload, expected_runner=REQUIRED_PYTEST_RUNNER_ID)


def _human_like_failure(payload: Mapping[str, Any]) -> str | None:
    summary = payload.get("pass_fail_summary")
    artifact_run = payload.get("artifact_run")
    if (
        payload.get("status") != "passed"
        or not isinstance(summary, Mapping)
        or summary.get("passed") is not True
        or not isinstance(artifact_run, Mapping)
        or artifact_run.get("schema_version") != 2
    ):
        return "human-like walkthrough is not a passed canonical result"
    return None


def _ui_baseline_failure(payload: Mapping[str, Any]) -> str | None:
    if (
        payload.get("schema_version") != 1
        or payload.get("artifact_type") != "xbrainlab.ui_visual_baseline"
        or payload.get("passed") is not True
    ):
        return "UI baseline is not a passed canonical result"
    return None


def _dpi_gate_failure(payload: Mapping[str, Any]) -> str | None:
    captures = payload.get("captures")
    if (
        payload.get("schema_version") != 1
        or payload.get("artifact_type") != "xbrainlab.app_polish_windows_dpi"
        or not isinstance(captures, list)
        or not captures
        or any(
            not isinstance(capture, Mapping)
            or capture.get("evidence_valid") is not True
            for capture in captures
        )
    ):
        return "Windows DPI artifact is not a valid successful capture matrix"
    return None


def _strict_validation_failure(payload: Mapping[str, Any]) -> str | None:
    strict = payload.get("strict_validation")
    if not isinstance(strict, Mapping) or strict.get("ok") is not True:
        return "strict validation is missing or failed"
    return None


def _public_cross_source_failure(payload: Mapping[str, Any]) -> str | None:
    summary = payload.get("summary")
    if (
        not isinstance(summary, Mapping)
        or summary.get("all_required_passed") is not True
    ):
        return "required public cross-source cases did not all pass"
    return None


_ARTIFACT_VALIDATORS: dict[str, ArtifactValidator] = {
    "data-interpretation-format": _strict_validation_failure,
    "dataset-validation": _strict_validation_failure,
    "human-like": _human_like_failure,
    "public-cross-source": _public_cross_source_failure,
    "required-pytest": _required_pytest_failure,
    "sharded-pytest": _sharded_pytest_failure,
    "ui-baseline": _ui_baseline_failure,
    "windows-dpi": _dpi_gate_failure,
}


def verify_required_ci_artifacts(
    *,
    required_artifacts: Sequence[tuple[str, Path]],
    provenance_path: Path,
    expected_job_key: str,
    expected_github_job: str,
    expected_runner_os: str,
) -> tuple[str, ...]:
    """Return failures for each missing/failed result and its source binding."""
    failures: list[str] = []
    for contract, path in required_artifacts:
        validator = _ARTIFACT_VALIDATORS.get(contract)
        if validator is None:
            failures.append(f"Unknown required CI artifact contract: {contract}")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError:
            failures.append(f"Required CI JSON is missing: {path.as_posix()}")
            continue
        except ValueError:
            failures.append(f"Required CI JSON is malformed: {path.as_posix()}")
            continue
        if not isinstance(payload, Mapping):
            failures.append(f"Required CI JSON is not an object: {path.as_posix()}")
            continue
        semantic_failure = validator(payload)
        if semantic_failure is not None:
            failures.append(
                f"Required CI JSON failed {contract!r}: {path.as_posix()}: "
                f"{semantic_failure}"
            )

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
    parser.add_argument(
        "--required-artifact",
        action="append",
        required=True,
        metavar="CONTRACT=PATH",
    )
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--expected-job-key", required=True)
    parser.add_argument("--expected-github-job", required=True)
    parser.add_argument("--expected-runner-os", required=True)
    return parser.parse_args()


def _parse_required_artifacts(values: Sequence[str]) -> tuple[tuple[str, Path], ...]:
    parsed: list[tuple[str, Path]] = []
    for value in values:
        contract, separator, raw_path = value.partition("=")
        if not separator or not contract or not raw_path:
            raise ValueError("--required-artifact must use the form CONTRACT=PATH")
        parsed.append((contract, Path(raw_path)))
    return tuple(parsed)


def main() -> int:
    args = _parse_args()
    try:
        required_artifacts = _parse_required_artifacts(args.required_artifact)
    except ValueError as error:
        print(f"ERROR: {error}")
        return 2
    failures = verify_required_ci_artifacts(
        required_artifacts=required_artifacts,
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
