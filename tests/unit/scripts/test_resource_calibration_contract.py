from __future__ import annotations

from datetime import UTC, datetime

from scripts.dev import resource_calibration_contract as contract


def _report(source_digest: str) -> dict:
    return {
        "schema_version": contract.RESOURCE_CALIBRATION_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_identity": {
            "commit_sha": "a" * 40,
            "tree_sha": "b" * 40,
            "dirty": False,
            "dirty_count": 0,
            "relevant_dirty_paths": [],
            "source_paths": list(contract.CALIBRATION_SOURCE_PATHS),
            "source_digest": source_digest,
        },
        "command": ["python", "calibrate_resource_guard.py", "--strict"],
        "environment": {
            "python": "3.12.0",
            "torch": "2.0.0",
            "torch_cuda": "12.0",
            "cuda_available": True,
            "gpu_name": "Test GPU",
            "driver_version": "999.0",
        },
        "expected_models": list(contract.EXPECTED_CALIBRATION_MODELS),
        "cuda_probe": {
            "status": "measured",
            "models": [
                {
                    "model": model,
                    "status": "measured",
                    "estimate_covers_observed_peak": True,
                }
                for model in contract.EXPECTED_CALIBRATION_MODELS
            ],
            "all_estimates_cover_observed_peak": True,
        },
    }


def test_strict_contract_detects_source_content_staleness(monkeypatch, tmp_path):
    source = tmp_path / "source.py"
    source.write_text("first\n", encoding="utf-8")
    monkeypatch.setattr(contract, "CALIBRATION_SOURCE_PATHS", ("source.py",))
    digest = contract.calibration_source_digest(tmp_path, ("source.py",))
    report = _report(digest)
    report["source_identity"]["source_paths"] = ["source.py"]

    assert (
        contract.strict_calibration_failure_reasons(
            report,
            repo_root=tmp_path,
            validate_source=True,
        )
        == []
    )

    source.write_text("second\n", encoding="utf-8")
    failures = contract.strict_calibration_failure_reasons(
        report,
        repo_root=tmp_path,
        validate_source=True,
    )

    assert "calibration source digest is stale" in failures
