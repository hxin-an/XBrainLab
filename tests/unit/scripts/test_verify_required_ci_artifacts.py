from __future__ import annotations

import json

from scripts.dev import verify_required_ci_artifacts as verifier


def test_required_ci_artifacts_reject_provenance_without_primary_result(
    monkeypatch,
    tmp_path,
) -> None:
    provenance = tmp_path / "provenance.json"
    provenance.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        verifier,
        "validate_ci_source_provenance",
        lambda *_args, **_kwargs: ({}, None),
    )

    failures = verifier.verify_required_ci_artifacts(
        required_json=[tmp_path / "result.json"],
        provenance_path=provenance,
        expected_job_key="platform",
        expected_github_job="platform-test",
        expected_runner_os="Windows",
    )

    assert failures == (
        f"Required CI JSON is missing: {(tmp_path / 'result.json').as_posix()}",
    )


def test_required_ci_artifacts_reject_malformed_primary_result(
    monkeypatch,
    tmp_path,
) -> None:
    result = tmp_path / "result.json"
    provenance = tmp_path / "provenance.json"
    result.write_text("not-json", encoding="utf-8")
    provenance.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        verifier,
        "validate_ci_source_provenance",
        lambda *_args, **_kwargs: ({}, None),
    )

    failures = verifier.verify_required_ci_artifacts(
        required_json=[result],
        provenance_path=provenance,
        expected_job_key="platform",
        expected_github_job="platform-test",
        expected_runner_os="Windows",
    )

    assert failures == (f"Required CI JSON is malformed: {result.as_posix()}",)


def test_required_ci_artifacts_bind_producer_and_runner(monkeypatch, tmp_path) -> None:
    result = tmp_path / "result.json"
    provenance = tmp_path / "provenance.json"
    result.write_text(json.dumps({"passed": True}), encoding="utf-8")
    provenance.write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    def validate(path, **kwargs):
        captured["path"] = path
        captured.update(kwargs)
        return {}, None

    monkeypatch.setattr(verifier, "validate_ci_source_provenance", validate)

    failures = verifier.verify_required_ci_artifacts(
        required_json=[result],
        provenance_path=provenance,
        expected_job_key="windows-platform",
        expected_github_job="platform-test",
        expected_runner_os="Windows",
    )

    assert failures == ()
    assert captured == {
        "path": provenance,
        "expected_job_key": "windows-platform",
        "expected_github_job": "platform-test",
        "expected_runner_os": "Windows",
    }
