from __future__ import annotations

import json

import pytest

from scripts.dev import verify_required_ci_artifacts as verifier
from scripts.dev.run_app_polish_ui_dpi_gate import (
    DPI_APP_POLISH_SURFACES,
    REQUIRED_SCALE_FACTORS,
    build_dpi_gate_manifest,
)


@pytest.fixture
def public_smoke_artifact(tmp_path, monkeypatch):
    from scripts.dev import run_public_cross_source_training_smoke as smoke

    def passed_result(fixture, protocol):
        return smoke.SmokeResult(
            name=str(fixture["name"]),
            filename=str(fixture["filename"]),
            source_family=str(fixture["source_family"]),
            status="passed",
            dataset_count=1 if protocol == "training" else 0,
            message="observed success",
            protocol=protocol,
            artifacts_reloaded=protocol == "training",
        )

    monkeypatch.setattr(
        smoke, "run_fixture_smoke", lambda fixture: passed_result(fixture, "training")
    )
    monkeypatch.setattr(
        smoke,
        "run_fixture_boundary_smoke",
        lambda fixture: passed_result(fixture, "import-preprocess-only"),
    )
    payload = smoke.build_snapshot()
    # Files and the provenance consumer are real; only expensive EEG execution is
    # replaced because these tests protect the report admission boundary.
    provenance = tmp_path / "provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "schema": "xbrainlab.ci-source-provenance.v1",
                "job_key": "public-dataset-gate",
                "event_name": "pull_request",
                "repository": "example/XBrainLab",
                "workflow": "CI",
                "run_id": "1",
                "run_attempt": "1",
                "github_sha": "a" * 40,
                "expected_head_sha": "b" * 40,
                "pull_request_head_sha": "b" * 40,
                "pull_request_base_sha": "c" * 40,
                "checked_out_head_sha": "b" * 40,
                "checked_out_tree_sha": "d" * 40,
                "github_job": "public-dataset-gate",
                "runner_os": "Linux",
                "runner_arch": "X64",
            }
        ),
        encoding="utf-8",
    )
    return payload, tmp_path / "public.json", provenance


@pytest.mark.parametrize(
    "damage",
    [
        None,
        "absent",
        "empty",
        "duplicate",
        "failed",
        "missing",
        "protocol",
        "reload",
        "summary",
        "malformed-row",
        "malformed-config",
        "invalid-status",
        "no-datasets",
        "malformed-reload",
        "unconfigured",
        "extra-result",
    ],
)
def test_public_ci_consumer_checks_actual_cases(public_smoke_artifact, damage):
    payload, result_path, provenance_path = public_smoke_artifact
    if damage == "absent":
        payload.pop("results")
    elif damage == "empty":
        payload["results"] = []
    elif damage == "duplicate":
        payload["results"].append(dict(payload["results"][0]))
    elif damage in {"failed", "missing", "invalid-status"}:
        payload["results"][0]["status"] = damage
    elif damage == "protocol":
        payload["results"][0]["protocol"] = "import-preprocess-only"
    elif damage == "reload":
        payload["results"][0]["artifacts_reloaded"] = False
    elif damage == "summary":
        payload["summary"]["passed_required_case_count"] = 999
    elif damage == "malformed-row":
        payload["results"][0] = None
    elif damage == "malformed-config":
        payload["summary"]["configured_case_ids"] = None
    elif damage == "no-datasets":
        payload["results"][0]["dataset_count"] = 0
    elif damage == "malformed-reload":
        payload["results"][0]["artifacts_reloaded"] = "yes"
    elif damage == "unconfigured":
        payload["summary"]["configured_case_ids"] = []
    elif damage == "extra-result":
        payload["results"].append({**payload["results"][0], "name": "unregistered"})
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    failures = verifier.verify_required_ci_artifacts(
        required_artifacts=[("public-cross-source", result_path)],
        provenance_path=provenance_path,
        expected_job_key="public-dataset-gate",
        expected_github_job="public-dataset-gate",
        expected_runner_os="Linux",
    )

    if damage is None:
        assert failures == ()
    else:
        assert len(failures) == 1
        assert "failed 'public-cross-source'" in failures[0]


def _dpi_payload():
    return build_dpi_gate_manifest(
        captures=[
            {
                "requested_scale_factor": scale,
                "observed_device_pixel_ratio": scale,
                "platform_system": "Windows",
                "qt_platform": "windows",
                "evidence_valid": True,
                "selected_surfaces": list(DPI_APP_POLISH_SURFACES),
                "evidence_path": (
                    f"scale-{round(scale * 100):03d}/app-polish-evidence.json"
                ),
            }
            for scale in REQUIRED_SCALE_FACTORS
        ],
        source_identity={"source_digest": "a" * 64},
    )


@pytest.mark.parametrize("damage", ["nonfinite", "missing-scale", "offscreen"])
def test_ci_dpi_consumer_rejects_invalid_matrix_file(monkeypatch, tmp_path, damage):
    payload = _dpi_payload()
    if damage == "nonfinite":
        payload["captures"][0]["observed_device_pixel_ratio"] = "NaN"
    elif damage == "missing-scale":
        payload["captures"].pop()
    else:
        payload["captures"][0]["qt_platform"] = "offscreen"
    result = tmp_path / "dpi-gate.json"
    result.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        verifier, "validate_ci_source_provenance", lambda *_args, **_kwargs: ({}, None)
    )

    failures = verifier.verify_required_ci_artifacts(
        required_artifacts=[("windows-dpi", result)],
        provenance_path=tmp_path / "provenance.json",
        expected_job_key="ui-windows-dpi",
        expected_github_job="ui-windows-dpi",
        expected_runner_os="Windows",
    )

    assert len(failures) == 1
    assert "failed 'windows-dpi'" in failures[0]


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
                "command_args": ["platform-core-contracts"],
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


def test_required_ci_artifacts_reject_forged_failed_pytest_outcome(
    monkeypatch,
    tmp_path,
) -> None:
    result = tmp_path / "result.json"
    provenance = tmp_path / "provenance.json"
    result.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "runner": verifier.SHARDED_PYTEST_RUNNER_ID,
                "completed": True,
                "exit_code": 0,
                "command_args": ["platform-core-contracts"],
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
                "outcomes": {"tests/test_example.py::test_example": "failed"},
            }
        ),
        encoding="utf-8",
    )
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

    assert len(failures) == 1
    assert "outcomes do not match counts" in failures[0]


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
                "schema_version": 2,
                "artifact_type": "xbrainlab.ui_visual_baseline",
                "passed": True,
            },
        ),
        (
            "windows-dpi",
            _dpi_payload(),
        ),
        ("dataset-validation", {"strict_validation": {"ok": True}}),
        ("data-interpretation-format", {"strict_validation": {"ok": True}}),
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


@pytest.mark.parametrize(
    "payload",
    (
        {
            "schema_version": 1,
            "artifact_type": "xbrainlab.ui_visual_baseline",
            "passed": True,
        },
        {
            "schema_version": 3,
            "artifact_type": "xbrainlab.ui_visual_baseline",
            "passed": True,
        },
        {
            "schema_version": "2",
            "artifact_type": "xbrainlab.ui_visual_baseline",
            "passed": True,
        },
        {
            "schema_version": 2,
            "artifact_type": "xbrainlab.ui_visual_baseline",
            "passed": False,
        },
        {
            "schema_version": 2,
            "artifact_type": "wrong-artifact-type",
            "passed": True,
        },
    ),
)
def test_ui_baseline_contract_fails_closed_for_noncanonical_payload(payload) -> None:
    assert verifier._ui_baseline_failure(payload) == (
        "UI baseline is not a passed canonical result"
    )
