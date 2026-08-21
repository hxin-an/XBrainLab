from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.dev import ci_source_provenance

HEAD_SHA = "a" * 40
BASE_SHA = "b" * 40
TREE_SHA = "c" * 40
OTHER_TREE_SHA = "d" * 40
MERGE_SHA = "e" * 40


def _environment(event_path: Path, *, sha: str) -> dict[str, str]:
    return {
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_SHA": MERGE_SHA,
        "GITHUB_REPOSITORY": "hxin-an/XBrainLab",
        "GITHUB_WORKFLOW": "CI",
        "GITHUB_JOB": "linux-shard",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "2",
        "RUNNER_OS": "Linux",
        "RUNNER_ARCH": "X64",
        "EXPECTED_SHA": sha,
    }


def _event(path: Path, *, head: str, base: str = BASE_SHA) -> None:
    path.write_text(
        json.dumps({"pull_request": {"head": {"sha": head}, "base": {"sha": base}}}),
        encoding="utf-8",
    )


def test_build_provenance_binds_pull_request_head_and_tree(
    monkeypatch, tmp_path
) -> None:
    event_path = tmp_path / "event.json"
    _event(event_path, head=HEAD_SHA)
    outputs = iter((HEAD_SHA, TREE_SHA))
    monkeypatch.setattr(
        ci_source_provenance, "_git_output", lambda *args, **kw: next(outputs)
    )

    payload = ci_source_provenance.build_ci_source_provenance(
        job_key="linux-unit-backend",
        root=tmp_path,
        environ=_environment(event_path, sha=HEAD_SHA),
    )

    assert payload["expected_head_sha"] == HEAD_SHA
    assert payload["pull_request_base_sha"] == BASE_SHA
    assert payload["checked_out_head_sha"] == HEAD_SHA
    assert payload["checked_out_tree_sha"] == TREE_SHA


def test_build_provenance_binds_push_to_github_sha(monkeypatch, tmp_path) -> None:
    outputs = iter((HEAD_SHA, TREE_SHA))
    monkeypatch.setattr(
        ci_source_provenance, "_git_output", lambda *args, **kw: next(outputs)
    )
    environment = _environment(tmp_path / "missing.json", sha=HEAD_SHA)
    environment["GITHUB_EVENT_NAME"] = "push"
    environment["GITHUB_SHA"] = HEAD_SHA

    payload = ci_source_provenance.build_ci_source_provenance(
        job_key="public-dataset-gate",
        root=tmp_path,
        environ=environment,
    )

    assert payload["expected_head_sha"] == HEAD_SHA
    assert payload["pull_request_head_sha"] == ""


def test_build_provenance_rejects_a_merge_ref_checkout(monkeypatch, tmp_path) -> None:
    event_path = tmp_path / "event.json"
    _event(event_path, head=HEAD_SHA)
    outputs = iter((MERGE_SHA, TREE_SHA))
    monkeypatch.setattr(
        ci_source_provenance, "_git_output", lambda *args, **kw: next(outputs)
    )

    with pytest.raises(ValueError, match="expected event head"):
        ci_source_provenance.build_ci_source_provenance(
            job_key="linux-unit-backend",
            root=tmp_path,
            environ=_environment(event_path, sha=HEAD_SHA),
        )


def _payload(
    job_key: str,
    *,
    tree: str = TREE_SHA,
    github_job: str = "linux-shard",
) -> dict[str, str]:
    return {
        "schema": ci_source_provenance.CI_SOURCE_PROVENANCE_SCHEMA,
        "job_key": job_key,
        "event_name": "pull_request",
        "repository": "hxin-an/XBrainLab",
        "workflow": "CI",
        "github_job": github_job,
        "run_id": "123",
        "run_attempt": "1",
        "runner_os": "Linux",
        "runner_arch": "X64",
        "github_sha": MERGE_SHA,
        "expected_head_sha": HEAD_SHA,
        "pull_request_head_sha": HEAD_SHA,
        "pull_request_base_sha": BASE_SHA,
        "checked_out_head_sha": HEAD_SHA,
        "checked_out_tree_sha": tree,
    }


def _write_payload(path: Path, payload: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_linux_provenance_set(root: Path, jobs: tuple[str, ...]) -> Path:
    for job in jobs:
        artifact_dir = (
            root / f"{ci_source_provenance.LINUX_PROVENANCE_ARTIFACT_PREFIX}{job}"
        )
        _write_payload(
            artifact_dir / f"{ci_source_provenance.LINUX_PROVENANCE_PREFIX}{job}.json",
            _payload(job),
        )
    expected_path = root.parent / "linux-test-source-provenance.json"
    _write_payload(
        expected_path,
        _payload("linux-test", github_job="linux-test"),
    )
    return expected_path


def test_linux_provenance_requires_exact_checked_in_job_set(tmp_path) -> None:
    jobs = ("linux-a", "linux-b")
    provenance_root = tmp_path / "source-provenance"
    expected_path = _write_linux_provenance_set(provenance_root, jobs)
    aggregate_path = tmp_path / "all-linux-source-provenance.json"

    aggregate, failures = ci_source_provenance.verify_linux_source_provenance(
        provenance_root,
        expected_job_keys=jobs,
        expected_provenance_path=expected_path,
        aggregate_path=aggregate_path,
    )

    assert failures == ()
    assert aggregate is not None
    assert aggregate["job_keys"] == list(jobs)
    assert aggregate_path.exists()


@pytest.mark.parametrize(
    "failure_kind",
    ["missing", "unknown", "duplicate-content", "different-tree", "wrong-producer"],
)
def test_linux_provenance_rejects_incomplete_or_inconsistent_sets(
    tmp_path,
    failure_kind,
) -> None:
    jobs = ("linux-a", "linux-b")
    provenance_root = tmp_path / "source-provenance"
    expected_path = _write_linux_provenance_set(provenance_root, jobs)
    linux_b_dir = (
        provenance_root
        / f"{ci_source_provenance.LINUX_PROVENANCE_ARTIFACT_PREFIX}linux-b"
    )
    linux_b_path = (
        linux_b_dir / f"{ci_source_provenance.LINUX_PROVENANCE_PREFIX}linux-b.json"
    )
    if failure_kind == "missing":
        linux_b_path.unlink()
    elif failure_kind == "unknown":
        unknown_dir = (
            provenance_root
            / f"{ci_source_provenance.LINUX_PROVENANCE_ARTIFACT_PREFIX}linux-c"
        )
        _write_payload(
            unknown_dir / f"{ci_source_provenance.LINUX_PROVENANCE_PREFIX}linux-c.json",
            _payload("linux-c"),
        )
    elif failure_kind == "duplicate-content":
        _write_payload(linux_b_dir / "duplicate.json", _payload("linux-b"))
    elif failure_kind == "different-tree":
        _write_payload(linux_b_path, _payload("linux-b", tree=OTHER_TREE_SHA))
    elif failure_kind == "wrong-producer":
        _write_payload(
            linux_b_path,
            _payload("linux-b", github_job="linux-test"),
        )
    aggregate_path = tmp_path / "all-linux-source-provenance.json"

    aggregate, failures = ci_source_provenance.verify_linux_source_provenance(
        provenance_root,
        expected_job_keys=jobs,
        expected_provenance_path=expected_path,
        aggregate_path=aggregate_path,
    )

    assert aggregate is None
    assert failures
    assert not aggregate_path.exists()


def test_linux_provenance_rejects_members_that_are_consistently_stale(
    tmp_path,
) -> None:
    jobs = ("linux-a", "linux-b")
    provenance_root = tmp_path / "source-provenance"
    expected_path = _write_linux_provenance_set(provenance_root, jobs)
    for job in jobs:
        path = (
            provenance_root
            / f"{ci_source_provenance.LINUX_PROVENANCE_ARTIFACT_PREFIX}{job}"
            / f"{ci_source_provenance.LINUX_PROVENANCE_PREFIX}{job}.json"
        )
        stale = _payload(job, tree=OTHER_TREE_SHA)
        _write_payload(path, stale)

    aggregate, failures = ci_source_provenance.verify_linux_source_provenance(
        provenance_root,
        expected_job_keys=jobs,
        expected_provenance_path=expected_path,
        aggregate_path=tmp_path / "all-linux-source-provenance.json",
    )

    assert aggregate is None
    assert any("aggregate job checkout" in failure for failure in failures)


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
