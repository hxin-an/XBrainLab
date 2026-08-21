from __future__ import annotations

import json

from scripts.dev import verify_native_ci_evidence as verifier


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_native_evidence_rejects_missing_smoke_and_provenance(tmp_path) -> None:
    failures = verifier.verify_native_ci_evidence(
        smoke_path=tmp_path / "missing-smoke.json",
        provenance_path=tmp_path / "missing-provenance.json",
        expected_job_key="windows-product-py311",
        expected_runner_os="Windows",
        expected_artifact_type="xbrainlab.native_platform_product_smoke",
        expected_qt_platform="windows",
        expected_isolated_root=tmp_path / "Native 測試",
    )

    assert "Native platform smoke artifact is unreadable." in failures
    assert "CI source provenance is unreadable." in failures


def test_native_evidence_rejects_failed_or_wrong_platform_smoke(tmp_path) -> None:
    smoke_path = tmp_path / "smoke.json"
    provenance_path = tmp_path / "provenance.json"
    _write_json(
        smoke_path,
        {
            "artifact_type": "xbrainlab.native_platform_product_smoke",
            "passed": False,
            "qt_platform": "offscreen",
            "isolated_root": str((tmp_path / "Native 測試").resolve()),
        },
    )

    failures = verifier.verify_native_ci_evidence(
        smoke_path=smoke_path,
        provenance_path=provenance_path,
        expected_job_key="windows-product-py311",
        expected_runner_os="Windows",
        expected_artifact_type="xbrainlab.native_platform_product_smoke",
        expected_qt_platform="windows",
        expected_isolated_root=tmp_path / "Native 測試",
    )

    assert "Native platform smoke did not pass." in failures
    assert "Native platform smoke used the wrong Qt platform." in failures


def test_native_evidence_accepts_complete_smoke_and_provenance(
    monkeypatch,
    tmp_path,
) -> None:
    root = tmp_path / "Native 測試"
    smoke_path = tmp_path / "smoke.json"
    provenance_path = tmp_path / "provenance.json"
    _write_json(
        smoke_path,
        {
            "artifact_type": "xbrainlab.startup_smoke",
            "passed": True,
            "qt_platform": "windows",
            "isolated_root": str(root.resolve()),
        },
    )
    provenance_path.write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    def validate(path, **kwargs):
        captured["path"] = path
        captured.update(kwargs)
        return {"schema": "test"}, None

    monkeypatch.setattr(verifier, "validate_ci_source_provenance", validate)

    failures = verifier.verify_native_ci_evidence(
        smoke_path=smoke_path,
        provenance_path=provenance_path,
        expected_job_key="windows-startup-py312",
        expected_runner_os="Windows",
        expected_artifact_type="xbrainlab.startup_smoke",
        expected_qt_platform="windows",
        expected_isolated_root=root,
    )

    assert failures == ()
    assert captured == {
        "path": provenance_path,
        "expected_job_key": "windows-startup-py312",
        "expected_github_job": "native-platform-source",
        "expected_runner_os": "Windows",
    }


def test_product_evidence_rejects_startup_only_artifact(monkeypatch, tmp_path) -> None:
    root = tmp_path / "Native 測試"
    smoke_path = tmp_path / "smoke.json"
    provenance_path = tmp_path / "provenance.json"
    _write_json(
        smoke_path,
        {
            "artifact_type": "xbrainlab.startup_smoke",
            "passed": True,
            "qt_platform": "windows",
            "isolated_root": str(root.resolve()),
        },
    )
    provenance_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        verifier,
        "validate_ci_source_provenance",
        lambda *_args, **_kwargs: ({}, None),
    )

    failures = verifier.verify_native_ci_evidence(
        smoke_path=smoke_path,
        provenance_path=provenance_path,
        expected_job_key="windows-product-py311",
        expected_runner_os="Windows",
        expected_artifact_type="xbrainlab.native_platform_product_smoke",
        expected_qt_platform="windows",
        expected_isolated_root=root,
    )

    assert "Native platform smoke artifact type does not match." in failures


def test_native_evidence_rejects_wrong_isolated_root(monkeypatch, tmp_path) -> None:
    smoke_path = tmp_path / "smoke.json"
    provenance_path = tmp_path / "provenance.json"
    _write_json(
        smoke_path,
        {
            "artifact_type": "xbrainlab.startup_smoke",
            "passed": True,
            "qt_platform": "windows",
            "isolated_root": str((tmp_path / "other root").resolve()),
        },
    )
    provenance_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        verifier,
        "validate_ci_source_provenance",
        lambda *_args, **_kwargs: ({}, None),
    )

    failures = verifier.verify_native_ci_evidence(
        smoke_path=smoke_path,
        provenance_path=provenance_path,
        expected_job_key="windows-startup-py312",
        expected_runner_os="Windows",
        expected_artifact_type="xbrainlab.startup_smoke",
        expected_qt_platform="windows",
        expected_isolated_root=tmp_path / "Native 測試",
    )

    assert "Native platform smoke used the wrong isolated root." in failures
