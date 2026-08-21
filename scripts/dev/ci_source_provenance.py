#!/usr/bin/env python3
"""Write and validate exact-source provenance for authoritative CI evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CI_SOURCE_PROVENANCE_SCHEMA = "xbrainlab.ci-source-provenance.v1"
LINUX_PROVENANCE_PREFIX = "ci-source-provenance-"
LINUX_PROVENANCE_ARTIFACT_PREFIX = "linux-source-provenance-"
_GIT_OBJECT_RE = re.compile(r"[0-9a-f]{40}")

_COMMON_IDENTITY_FIELDS = (
    "event_name",
    "repository",
    "workflow",
    "run_id",
    "run_attempt",
    "github_sha",
    "expected_head_sha",
    "pull_request_head_sha",
    "pull_request_base_sha",
    "checked_out_head_sha",
    "checked_out_tree_sha",
)


def _git_output(*args: str, root: Path) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed git query, no shell
        ("git", *args),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _event_pull_request_shas(event_path: str) -> tuple[str, str]:
    if not event_path:
        return "", ""
    try:
        payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
        pull_request = payload.get("pull_request", {})
        head = pull_request.get("head", {}).get("sha", "")
        base = pull_request.get("base", {}).get("sha", "")
    except (OSError, ValueError, TypeError, AttributeError):
        return "", ""
    return str(head).strip(), str(base).strip()


def build_ci_source_provenance(
    *,
    job_key: str,
    root: Path,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    """Build a provenance payload and reject a checkout other than the event head."""
    event_name = environ.get("GITHUB_EVENT_NAME", "").strip()
    github_sha = environ.get("GITHUB_SHA", "").strip()
    pr_head, pr_base = _event_pull_request_shas(
        environ.get("GITHUB_EVENT_PATH", "").strip()
    )
    expected_head = pr_head if event_name == "pull_request" else github_sha
    checked_head = _git_output("rev-parse", "HEAD", root=root)
    checked_tree = _git_output("rev-parse", "HEAD^{tree}", root=root)

    if not job_key.strip():
        raise ValueError("CI source provenance requires a non-empty job key.")
    if not expected_head:
        raise ValueError("CI source provenance cannot determine the expected head SHA.")
    for label, value in (
        ("github SHA", github_sha),
        ("expected head SHA", expected_head),
        ("checked-out head SHA", checked_head),
        ("checked-out tree SHA", checked_tree),
    ):
        if _GIT_OBJECT_RE.fullmatch(value) is None:
            raise ValueError(f"CI source provenance {label} is not a Git SHA.")
    if checked_head != expected_head:
        raise ValueError(
            "CI checkout does not match the expected event head "
            f"({checked_head} != {expected_head})."
        )

    return {
        "schema": CI_SOURCE_PROVENANCE_SCHEMA,
        "job_key": job_key.strip(),
        "event_name": event_name,
        "repository": environ.get("GITHUB_REPOSITORY", "").strip(),
        "workflow": environ.get("GITHUB_WORKFLOW", "").strip(),
        "github_job": environ.get("GITHUB_JOB", "").strip(),
        "run_id": environ.get("GITHUB_RUN_ID", "").strip(),
        "run_attempt": environ.get("GITHUB_RUN_ATTEMPT", "").strip(),
        "runner_os": environ.get("RUNNER_OS", "").strip(),
        "runner_arch": environ.get("RUNNER_ARCH", "").strip(),
        "github_sha": github_sha,
        "expected_head_sha": expected_head,
        "pull_request_head_sha": pr_head,
        "pull_request_base_sha": pr_base,
        "checked_out_head_sha": checked_head,
        "checked_out_tree_sha": checked_tree,
    }


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically write one canonical JSON evidence file."""
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(dict(payload), handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    temporary.replace(destination)


def validate_ci_source_provenance(
    path: Path,
    *,
    expected_job_key: str,
    expected_github_job: str | None = None,
    expected_runner_os: str | None = None,
    expected_runner_arch: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate one exact-source payload without accepting partial evidence."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "CI source provenance is unreadable."
    if not isinstance(payload, dict):
        return None, "CI source provenance is malformed."
    if payload.get("schema") != CI_SOURCE_PROVENANCE_SCHEMA:
        return None, "CI source provenance schema is unsupported."
    if payload.get("job_key") != expected_job_key:
        return None, "CI source provenance job key does not match."
    for field in (*_COMMON_IDENTITY_FIELDS, "github_job", "runner_os", "runner_arch"):
        if not isinstance(payload.get(field), str):
            return None, f"CI source provenance field {field!r} is malformed."
    if not payload["expected_head_sha"]:
        return None, "CI source provenance expected head is missing."
    for field in (
        "github_sha",
        "expected_head_sha",
        "pull_request_head_sha",
        "pull_request_base_sha",
        "checked_out_head_sha",
        "checked_out_tree_sha",
    ):
        value = payload[field]
        if value and _GIT_OBJECT_RE.fullmatch(value) is None:
            return None, f"CI source provenance field {field!r} is not a Git SHA."
    if payload["checked_out_head_sha"] != payload["expected_head_sha"]:
        return None, "CI source provenance checkout does not match its expected head."
    if not payload["checked_out_tree_sha"]:
        return None, "CI source provenance tree identity is missing."
    if payload["event_name"] == "pull_request":
        if payload["pull_request_head_sha"] != payload["expected_head_sha"]:
            return None, "CI pull-request provenance head is inconsistent."
        if not payload["pull_request_base_sha"]:
            return None, "CI pull-request provenance base is missing."
    if expected_github_job is not None and payload["github_job"] != expected_github_job:
        return None, "CI source provenance producer job does not match."
    if expected_runner_os is not None and payload["runner_os"] != expected_runner_os:
        return None, "CI source provenance runner OS does not match."
    if (
        expected_runner_arch is not None
        and payload["runner_arch"] != expected_runner_arch
    ):
        return None, "CI source provenance runner architecture does not match."
    return payload, None


def verify_linux_source_provenance(
    provenance_dir: Path,
    *,
    expected_job_keys: Sequence[str],
    expected_provenance_path: Path,
    aggregate_path: Path,
) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    """Require one producer-isolated payload per Linux group and current checkout."""
    root = provenance_dir.expanduser().resolve()
    expected_directories = {
        f"{LINUX_PROVENANCE_ARTIFACT_PREFIX}{job_key}" for job_key in expected_job_keys
    }
    actual_directories = (
        {path.name for path in root.iterdir() if path.is_dir()}
        if root.is_dir()
        else set()
    )
    root_files = (
        {path.name for path in root.iterdir() if path.is_file()}
        if root.is_dir()
        else set()
    )
    failures: list[str] = []
    if actual_directories != expected_directories or root_files:
        failures.append(
            "Linux CI provenance artifact set mismatch "
            f"(expected directories {sorted(expected_directories)}, "
            f"got directories {sorted(actual_directories)} and files "
            f"{sorted(root_files)})."
        )

    expected_payload, expected_failure = validate_ci_source_provenance(
        expected_provenance_path,
        expected_job_key="linux-test",
        expected_github_job="linux-test",
        expected_runner_os="Linux",
    )
    if expected_failure is not None:
        failures.append(f"linux-test: {expected_failure}")

    payloads: list[dict[str, Any]] = []
    for job_key in expected_job_keys:
        artifact_dir = root / f"{LINUX_PROVENANCE_ARTIFACT_PREFIX}{job_key}"
        expected_file = artifact_dir / f"{LINUX_PROVENANCE_PREFIX}{job_key}.json"
        contained_files = (
            {
                path.relative_to(artifact_dir).as_posix()
                for path in artifact_dir.rglob("*")
                if path.is_file()
            }
            if artifact_dir.is_dir()
            else set()
        )
        if contained_files != {expected_file.name}:
            failures.append(
                f"{job_key}: provenance artifact contents differ "
                f"(got {sorted(contained_files)})."
            )
        payload, failure = validate_ci_source_provenance(
            expected_file,
            expected_job_key=job_key,
            expected_github_job="linux-shard",
            expected_runner_os="Linux",
        )
        if failure is not None:
            failures.append(f"{job_key}: {failure}")
        elif payload is not None:
            payloads.append(payload)

    if expected_payload is not None:
        reference = tuple(expected_payload[field] for field in _COMMON_IDENTITY_FIELDS)
        for payload in payloads:
            identity = tuple(payload[field] for field in _COMMON_IDENTITY_FIELDS)
            if identity != reference:
                failures.append(
                    f"{payload['job_key']}: CI source provenance differs from "
                    "the aggregate job checkout."
                )

    aggregate_path.unlink(missing_ok=True)
    if failures:
        return None, tuple(failures)
    if expected_payload is None or len(payloads) != len(expected_job_keys):
        return None, ("Linux CI source provenance is incomplete.",)

    aggregate = {
        "schema": CI_SOURCE_PROVENANCE_SCHEMA,
        "artifact_type": "linux-ci-source-aggregate",
        "job_keys": list(expected_job_keys),
        "source": {field: expected_payload[field] for field in _COMMON_IDENTITY_FIELDS},
        "members": payloads,
    }
    write_json_atomic(aggregate_path, aggregate)
    return aggregate, ()


def _parse_cli(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--job-key", required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    """Write provenance for the current GitHub Actions checkout."""
    args = _parse_cli(sys.argv[1:] if argv is None else argv)
    args.output.unlink(missing_ok=True)
    try:
        payload = build_ci_source_provenance(
            job_key=args.job_key,
            root=args.root.expanduser().resolve(),
            environ=os.environ,
        )
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"CI source provenance failed: {error}", file=sys.stderr)
        return 1
    write_json_atomic(args.output, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
