from __future__ import annotations

import json

import pytest

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
        required_artifacts=[("sharded-pytest", tmp_path / "result.json")],
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
        required_artifacts=[("sharded-pytest", result)],
        provenance_path=provenance,
        expected_job_key="platform",
        expected_github_job="platform-test",
        expected_runner_os="Windows",
    )

    assert failures == (f"Required CI JSON is malformed: {result.as_posix()}",)


def test_required_ci_artifacts_bind_producer_and_runner(monkeypatch, tmp_path) -> None:
    result = tmp_path / "result.json"
    provenance = tmp_path / "provenance.json"
    result.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "runner": verifier.SHARDED_PYTEST_RUNNER_ID,
                "completed": True,
                "exit_code": 0,
                "counts": {
                    "collected": 1,
                    "executed": 1,
                    "passed": 1,
                    "failed": 0,
                    "errors": 0,
                    "skipped": 0,
                    "xfailed": 0,
                    "xpassed": 0,
                    "deselected": 0,
                },
                "outcomes": {"tests/test_example.py::test_example": "passed"},
            }
        ),
        encoding="utf-8",
    )
    provenance.write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    def validate(path, **kwargs):
        captured["path"] = path
        captured.update(kwargs)
        return {}, None

    monkeypatch.setattr(verifier, "validate_ci_source_provenance", validate)

    failures = verifier.verify_required_ci_artifacts(
        required_artifacts=[("sharded-pytest", result)],
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


def test_required_ci_artifacts_reject_empty_wrong_type_and_failed_results(
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
    cases = (
        ("empty.json", {}, "dataset-validation"),
        ("wrong-type.json", [], "dataset-validation"),
        ("failed.json", {"strict_validation": {"ok": False}}, "dataset-validation"),
    )
    required = []
    for filename, payload, contract in cases:
        path = tmp_path / filename
        path.write_text(json.dumps(payload), encoding="utf-8")
        required.append((contract, path))

    failures = verifier.verify_required_ci_artifacts(
        required_artifacts=required,
        provenance_path=provenance,
        expected_job_key="public",
        expected_github_job="public-dataset-gate",
        expected_runner_os="Linux",
    )

    assert len(failures) == 3
    assert "failed 'dataset-validation'" in failures[0]
    assert "is not an object" in failures[1]
    assert "strict validation is missing or failed" in failures[2]


def test_required_ci_artifacts_reject_unknown_contract(monkeypatch, tmp_path) -> None:
    provenance = tmp_path / "provenance.json"
    provenance.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        verifier,
        "validate_ci_source_provenance",
        lambda *_args, **_kwargs: ({}, None),
    )

    failures = verifier.verify_required_ci_artifacts(
        required_artifacts=[("unknown", tmp_path / "unused.json")],
        provenance_path=provenance,
        expected_job_key="job",
        expected_github_job="job",
        expected_runner_os="Linux",
    )

    assert failures == ("Unknown required CI artifact contract: unknown",)


@pytest.mark.parametrize(
    ("contract", "payload"),
    (
        (
            "human-like",
            {
                "status": "passed",
                "pass_fail_summary": {"passed": True},
                "artifact_run": {"schema_version": 2},
            },
        ),
        (
            "ui-baseline",
            {
                "schema_version": 1,
                "artifact_type": "xbrainlab.ui_visual_baseline",
                "passed": True,
            },
        ),
        (
            "windows-dpi",
            {
                "schema_version": 1,
                "artifact_type": "xbrainlab.app_polish_windows_dpi",
                "captures": [{"evidence_valid": True}],
            },
        ),
        ("dataset-validation", {"strict_validation": {"ok": True}}),
        ("data-interpretation-format", {"strict_validation": {"ok": True}}),
        ("public-cross-source", {"summary": {"all_required_passed": True}}),
    ),
)
def test_required_ci_artifact_contract_accepts_successful_payload(
    monkeypatch,
    tmp_path,
    contract,
    payload,
) -> None:
    result = tmp_path / f"{contract}.json"
    provenance = tmp_path / "provenance.json"
    result.write_text(json.dumps(payload), encoding="utf-8")
    provenance.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        verifier,
        "validate_ci_source_provenance",
        lambda *_args, **_kwargs: ({}, None),
    )

    failures = verifier.verify_required_ci_artifacts(
        required_artifacts=[(contract, result)],
        provenance_path=provenance,
        expected_job_key="job",
        expected_github_job="job",
        expected_runner_os="Linux",
    )

    assert failures == ()
