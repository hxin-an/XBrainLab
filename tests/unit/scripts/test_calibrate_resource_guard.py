from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock

from scripts.dev import calibrate_resource_guard as calibration


def _ram_status() -> dict[str, int]:
    return {
        "total_bytes": 32 * 1024**3,
        "available_bytes": 20 * 1024**3,
        "used_bytes": 12 * 1024**3,
    }


def _gpu_status(*, available_bytes: int | None, reason: str | None = None):
    return {
        "gpu_name": "Test GPU" if available_bytes is not None else None,
        "available_bytes": available_bytes,
        "total_bytes": 16 * 1024**3 if available_bytes is not None else None,
        "used_bytes": None,
        "allocated_bytes": 0,
        "reserved_bytes": 0,
        "gpu_index": 0,
        "device_count": 1,
        "reason": reason,
        "query_error_type": None,
    }


def test_calibration_report_uses_resource_checker_and_exposes_thresholds(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        calibration.ResourceChecker,
        "get_system_ram_status",
        staticmethod(_ram_status),
    )
    monkeypatch.setattr(
        calibration.ResourceChecker,
        "get_gpu_vram_status",
        staticmethod(
            lambda _index: _gpu_status(
                available_bytes=None,
                reason="cuda_not_available",
            )
        ),
    )

    monkeypatch.setattr(
        calibration,
        "collect_calibration_source_identity",
        lambda: {
            "commit_sha": "a" * 40,
            "tree_sha": "b" * 40,
            "dirty": True,
            "dirty_count": 1,
            "relevant_dirty_paths": ["XBrainLab/backend/application/resource_guard.py"],
            "source_paths": list(calibration.CALIBRATION_SOURCE_PATHS),
            "source_digest": "c" * 64,
        },
    )

    report = calibration.build_calibration_report(
        run_cuda_probe=False,
        command=[sys.executable, "scripts/dev/calibrate_resource_guard.py"],
    )

    assert report["ram"] == _ram_status()
    assert report["thresholds"] == {
        "ram_warning_ratio": 0.60,
        "ram_blocking_ratio": 0.80,
        "vram_warning_ratio": 0.75,
        "vram_blocking_ratio": 0.90,
    }
    assert report["cuda_probe"] == {"status": "skipped", "reason": "disabled"}
    assert report["schema_version"] == 2
    assert report["expected_models"] == ["EEGNet", "SCCNet", "ShallowConvNet"]
    assert report["source_identity"]["source_digest"] == "c" * 64
    assert report["command"][-1] == "scripts/dev/calibrate_resource_guard.py"
    assert report["environment"]["python"]
    assert report["environment"]["torch"]


def test_calibration_report_skips_probe_when_cuda_memory_is_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        calibration.ResourceChecker,
        "get_system_ram_status",
        staticmethod(_ram_status),
    )
    monkeypatch.setattr(
        calibration.ResourceChecker,
        "get_gpu_vram_status",
        staticmethod(
            lambda _index: _gpu_status(
                available_bytes=None,
                reason="cuda_not_available",
            )
        ),
    )

    report = calibration.build_calibration_report()

    assert report["cuda_probe"] == {
        "status": "skipped",
        "reason": "cuda_not_available",
    }


def test_calibration_never_runs_model_above_bounded_probe_budget(monkeypatch) -> None:
    available = 4 * 1024**3
    monkeypatch.setattr(
        calibration.ResourceChecker,
        "get_system_ram_status",
        staticmethod(_ram_status),
    )
    monkeypatch.setattr(
        calibration.ResourceChecker,
        "get_gpu_vram_status",
        staticmethod(lambda _index: _gpu_status(available_bytes=available)),
    )
    estimate = MagicMock(
        return_value={
            "estimated_gpu_batch_working_set_bytes": (
                calibration.MAX_CUDA_PROBE_ESTIMATE_BYTES + 1
            )
        }
    )
    probe = MagicMock(side_effect=AssertionError("probe must not run"))
    monkeypatch.setattr(calibration, "estimate_training_resources", estimate)
    monkeypatch.setattr(calibration, "_calibrate_model_step", probe)

    report = calibration.build_calibration_report()

    model_reports = report["cuda_probe"]["models"]
    assert model_reports
    assert all(item["status"] == "skipped" for item in model_reports)
    assert all(
        item["reason"] == "estimate_exceeds_probe_budget" for item in model_reports
    )
    probe.assert_not_called()


def test_write_calibration_report_creates_reproducible_json_artifact(tmp_path) -> None:
    output_path = tmp_path / "nested" / "resource-guard-calibration.json"
    report = {"schema_version": 1, "cuda_probe": {"status": "measured"}}

    calibration.write_calibration_report(output_path, report)

    assert json.loads(output_path.read_text(encoding="utf-8")) == report


def _strict_report(*, probe_status: str = "measured") -> dict:
    return {
        "schema_version": 2,
        "generated_at_utc": "2026-07-16T00:00:00+00:00",
        "source_identity": {
            "commit_sha": "a" * 40,
            "tree_sha": "b" * 40,
            "dirty": False,
            "dirty_count": 0,
            "relevant_dirty_paths": [],
            "source_paths": list(calibration.CALIBRATION_SOURCE_PATHS),
            "source_digest": "c" * 64,
        },
        "command": ["python", "scripts/dev/calibrate_resource_guard.py", "--strict"],
        "environment": {
            "python": "3.12.0",
            "torch": "2.0.0",
            "torch_cuda": "12.0",
            "cuda_available": True,
            "gpu_name": "Test GPU",
            "driver_version": "999.0",
        },
        "expected_models": ["EEGNet", "SCCNet", "ShallowConvNet"],
        "cuda_probe": {
            "status": probe_status,
            "models": [
                {
                    "model": model,
                    "status": "measured",
                    "estimate_covers_observed_peak": True,
                }
                for model in ("EEGNet", "SCCNet", "ShallowConvNet")
            ],
            "all_estimates_cover_observed_peak": True,
        },
    }


def test_strict_calibration_accepts_only_complete_measured_expected_models() -> None:
    assert calibration.strict_calibration_failure_reasons(_strict_report()) == []


def test_strict_calibration_rejects_cuda_unavailable_or_skipped_probe() -> None:
    skipped = _strict_report(probe_status="skipped")
    skipped["cuda_probe"]["reason"] = "cuda_not_available"

    failures = calibration.strict_calibration_failure_reasons(skipped)

    assert any("measured" in failure for failure in failures)


def test_strict_calibration_rejects_missing_failed_or_undercovered_model() -> None:
    report = _strict_report()
    report["cuda_probe"]["models"] = report["cuda_probe"]["models"][:2]
    report["cuda_probe"]["models"][0]["status"] = "failed"
    report["cuda_probe"]["models"][1]["estimate_covers_observed_peak"] = False

    failures = calibration.strict_calibration_failure_reasons(report)

    assert any(
        "missing" in failure and "ShallowConvNet" in failure for failure in failures
    )
    assert any("EEGNet" in failure and "measured" in failure for failure in failures)
    assert any(
        "SCCNet" in failure and "underestimates" in failure for failure in failures
    )


def test_main_strict_returns_nonzero_for_skipped_probe(monkeypatch) -> None:
    report = _strict_report(probe_status="skipped")
    monkeypatch.setattr(
        calibration, "build_calibration_report", lambda **_kwargs: report
    )

    assert calibration.main(["--strict"]) == 1
