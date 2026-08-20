from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.dev import ci_source_provenance


def _environment(event_path: Path, *, sha: str) -> dict[str, str]:
    return {
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_SHA": "merge-ref-sha",
        "GITHUB_REPOSITORY": "hxin-an/XBrainLab",
        "GITHUB_WORKFLOW": "CI",
        "GITHUB_JOB": "linux-shard",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "2",
        "RUNNER_OS": "Linux",
        "RUNNER_ARCH": "X64",
        "EXPECTED_SHA": sha,
    }


def _event(path: Path, *, head: str, base: str = "base-sha") -> None:
    path.write_text(
        json.dumps({"pull_request": {"head": {"sha": head}, "base": {"sha": base}}}),
        encoding="utf-8",
    )


def test_build_provenance_binds_pull_request_head_and_tree(
    monkeypatch, tmp_path
) -> None:
    event_path = tmp_path / "event.json"
    _event(event_path, head="head-sha")
    outputs = iter(("head-sha", "tree-sha"))
    monkeypatch.setattr(
        ci_source_provenance, "_git_output", lambda *args, **kw: next(outputs)
    )

    payload = ci_source_provenance.build_ci_source_provenance(
        job_key="linux-unit-backend",
        root=tmp_path,
        environ=_environment(event_path, sha="head-sha"),
    )

    assert payload["expected_head_sha"] == "head-sha"
    assert payload["pull_request_base_sha"] == "base-sha"
    assert payload["checked_out_head_sha"] == "head-sha"
    assert payload["checked_out_tree_sha"] == "tree-sha"


def test_build_provenance_binds_push_to_github_sha(monkeypatch, tmp_path) -> None:
    outputs = iter(("push-sha", "tree-sha"))
    monkeypatch.setattr(
        ci_source_provenance, "_git_output", lambda *args, **kw: next(outputs)
    )
    environment = _environment(tmp_path / "missing.json", sha="push-sha")
    environment["GITHUB_EVENT_NAME"] = "push"
    environment["GITHUB_SHA"] = "push-sha"

    payload = ci_source_provenance.build_ci_source_provenance(
        job_key="public-dataset-gate",
        root=tmp_path,
        environ=environment,
    )

    assert payload["expected_head_sha"] == "push-sha"
    assert payload["pull_request_head_sha"] == ""


def test_build_provenance_rejects_a_merge_ref_checkout(monkeypatch, tmp_path) -> None:
    event_path = tmp_path / "event.json"
    _event(event_path, head="head-sha")
    outputs = iter(("merge-ref-sha", "tree-sha"))
    monkeypatch.setattr(
        ci_source_provenance, "_git_output", lambda *args, **kw: next(outputs)
    )

    with pytest.raises(ValueError, match="expected event head"):
        ci_source_provenance.build_ci_source_provenance(
            job_key="linux-unit-backend",
            root=tmp_path,
            environ=_environment(event_path, sha="head-sha"),
        )


def _payload(job_key: str, *, tree: str = "tree-sha") -> dict[str, str]:
    return {
        "schema": ci_source_provenance.CI_SOURCE_PROVENANCE_SCHEMA,
        "job_key": job_key,
        "event_name": "pull_request",
        "repository": "hxin-an/XBrainLab",
        "workflow": "CI",
        "github_job": "linux-shard",
        "run_id": "123",
        "run_attempt": "1",
        "runner_os": "Linux",
        "runner_arch": "X64",
        "github_sha": "head-sha",
        "expected_head_sha": "head-sha",
        "pull_request_head_sha": "head-sha",
        "pull_request_base_sha": "base-sha",
        "checked_out_head_sha": "head-sha",
        "checked_out_tree_sha": tree,
    }


def _write_payload(path: Path, payload: dict[str, str]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_linux_provenance_requires_exact_checked_in_job_set(tmp_path) -> None:
    jobs = ("linux-a", "linux-b")
    for job in jobs:
        _write_payload(
            tmp_path / f"{ci_source_provenance.LINUX_PROVENANCE_PREFIX}{job}.json",
            _payload(job),
        )
    aggregate_path = tmp_path / "all-linux-source-provenance.json"

    aggregate, failures = ci_source_provenance.verify_linux_source_provenance(
        tmp_path,
        expected_job_keys=jobs,
        aggregate_path=aggregate_path,
    )

    assert failures == ()
    assert aggregate is not None
    assert aggregate["job_keys"] == list(jobs)
    assert aggregate_path.exists()


@pytest.mark.parametrize("failure_kind", ["missing", "unknown", "different-tree"])
def test_linux_provenance_rejects_incomplete_or_inconsistent_sets(
    tmp_path,
    failure_kind,
) -> None:
    jobs = ("linux-a", "linux-b")
    for job in jobs:
        tree = (
            "other-tree"
            if failure_kind == "different-tree" and job == "linux-b"
            else "tree-sha"
        )
        _write_payload(
            tmp_path / f"{ci_source_provenance.LINUX_PROVENANCE_PREFIX}{job}.json",
            _payload(job, tree=tree),
        )
    if failure_kind == "missing":
        (
            tmp_path / f"{ci_source_provenance.LINUX_PROVENANCE_PREFIX}linux-b.json"
        ).unlink()
    elif failure_kind == "unknown":
        _write_payload(
            tmp_path / f"{ci_source_provenance.LINUX_PROVENANCE_PREFIX}linux-c.json",
            _payload("linux-c"),
        )
    aggregate_path = tmp_path / "all-linux-source-provenance.json"

    aggregate, failures = ci_source_provenance.verify_linux_source_provenance(
        tmp_path,
        expected_job_keys=jobs,
        aggregate_path=aggregate_path,
    )

    assert aggregate is None
    assert failures
    assert not aggregate_path.exists()


def test_validate_provenance_rejects_malformed_or_wrong_job(tmp_path) -> None:
    path = tmp_path / "provenance.json"
    path.write_text("[]", encoding="utf-8")
    assert (
        ci_source_provenance.validate_ci_source_provenance(
            path, expected_job_key="linux-a"
        )[1]
        == "CI source provenance is malformed."
    )

    _write_payload(path, _payload("linux-b"))
    assert (
        ci_source_provenance.validate_ci_source_provenance(
            path, expected_job_key="linux-a"
        )[1]
        == "CI source provenance job key does not match."
    )
