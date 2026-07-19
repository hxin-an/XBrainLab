"""Run a bounded, non-destructive RAM/VRAM resource-guard calibration."""

from __future__ import annotations

import argparse
import gc
import json
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import torch

from scripts.dev.resource_calibration_contract import (
    CALIBRATION_SOURCE_PATHS as _CALIBRATION_SOURCE_PATHS,
)
from scripts.dev.resource_calibration_contract import (
    EXPECTED_CALIBRATION_MODELS,
    RESOURCE_CALIBRATION_SCHEMA_VERSION,
)
from scripts.dev.resource_calibration_contract import (
    collect_calibration_source_identity as _collect_calibration_source_identity,
)
from scripts.dev.resource_calibration_contract import (
    strict_calibration_failure_reasons as _strict_calibration_failure_reasons,
)
from XBrainLab.backend.application.resource_guard import (
    RAM_BLOCKING_RATIO,
    RAM_WARNING_RATIO,
    VRAM_BLOCKING_RATIO,
    VRAM_WARNING_RATIO,
    ResourceChecker,
    estimate_training_resources,
    is_cuda_oom_error,
)
from XBrainLab.backend.model_base.EEGNet import EEGNet
from XBrainLab.backend.model_base.SCCNet import SCCNet
from XBrainLab.backend.model_base.ShallowConvNet import ShallowConvNet
from XBrainLab.backend.training.model_holder import ModelHolder

CALIBRATION_BATCH_SIZE = 8
CALIBRATION_CHANNELS = 22
CALIBRATION_CLASSES = 4
CALIBRATION_EPOCHS = 32
CALIBRATION_SAMPLES = 301
CALIBRATION_SFREQ = 250.0
CALIBRATION_FOLDS = 3
CALIBRATION_REPEATS = 5
MIN_CUDA_FREE_BYTES = 1024**3
MAX_CUDA_PROBE_ESTIMATE_BYTES = 256 * 1024**2
MAX_CUDA_PROBE_AVAILABLE_RATIO = 0.10

_MODEL_TYPES = (EEGNet, SCCNet, ShallowConvNet)
ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_SOURCE_PATHS = _CALIBRATION_SOURCE_PATHS


class _CalibrationEpochData:
    def __init__(self) -> None:
        self.data = np.zeros(
            (CALIBRATION_EPOCHS, CALIBRATION_CHANNELS, CALIBRATION_SAMPLES),
            dtype=np.float32,
        )
        self.labels = np.arange(CALIBRATION_EPOCHS, dtype=np.int64)
        self.labels %= CALIBRATION_CLASSES
        self.label_map = {index: str(index) for index in range(CALIBRATION_CLASSES)}

    def get_data(self) -> np.ndarray:
        return self.data

    def get_label_list(self) -> np.ndarray:
        return self.labels

    def get_label_number(self) -> int:
        return CALIBRATION_CLASSES

    def get_model_args(self) -> dict[str, int | float]:
        return {
            "n_classes": CALIBRATION_CLASSES,
            "channels": CALIBRATION_CHANNELS,
            "samples": CALIBRATION_SAMPLES,
            "sfreq": CALIBRATION_SFREQ,
        }


class _CalibrationDataset:
    def __init__(self, epoch_data: _CalibrationEpochData) -> None:
        self._epoch_data = epoch_data
        self.train_mask = np.zeros(CALIBRATION_EPOCHS, dtype=bool)
        self.val_mask = np.zeros(CALIBRATION_EPOCHS, dtype=bool)
        self.test_mask = np.zeros(CALIBRATION_EPOCHS, dtype=bool)
        self.train_mask[:24] = True
        self.val_mask[24:28] = True
        self.test_mask[28:] = True

    def get_epoch_data(self) -> _CalibrationEpochData:
        return self._epoch_data


def collect_calibration_source_identity() -> dict[str, Any]:
    """Collect traceability for the source files that define this calibration."""
    return _collect_calibration_source_identity(ROOT)


def build_calibration_report(
    *,
    run_cuda_probe: bool = True,
    command: list[str] | None = None,
) -> dict[str, Any]:
    """Return real resource status and bounded model-step calibration evidence."""
    ram = ResourceChecker.get_system_ram_status()
    gpu = ResourceChecker.get_gpu_vram_status(0)
    report: dict[str, Any] = {
        "schema_version": RESOURCE_CALIBRATION_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_identity": collect_calibration_source_identity(),
        "command": list(command or [sys.executable, str(Path(__file__))]),
        "environment": _runtime_environment(gpu),
        "expected_models": list(EXPECTED_CALIBRATION_MODELS),
        "ram": ram,
        "gpu": gpu,
        "thresholds": {
            "ram_warning_ratio": RAM_WARNING_RATIO,
            "ram_blocking_ratio": RAM_BLOCKING_RATIO,
            "vram_warning_ratio": VRAM_WARNING_RATIO,
            "vram_blocking_ratio": VRAM_BLOCKING_RATIO,
        },
        "probe_scope": {
            "batch_size": CALIBRATION_BATCH_SIZE,
            "channels": CALIBRATION_CHANNELS,
            "classes": CALIBRATION_CLASSES,
            "epochs": CALIBRATION_EPOCHS,
            "samples": CALIBRATION_SAMPLES,
            "folds": CALIBRATION_FOLDS,
            "repeats": CALIBRATION_REPEATS,
            "maximum_estimated_vram_bytes": MAX_CUDA_PROBE_ESTIMATE_BYTES,
            "maximum_available_vram_ratio": MAX_CUDA_PROBE_AVAILABLE_RATIO,
        },
    }
    available = gpu.get("available_bytes")
    if not run_cuda_probe:
        report["cuda_probe"] = {"status": "skipped", "reason": "disabled"}
        return report
    if available is None:
        report["cuda_probe"] = {
            "status": "skipped",
            "reason": gpu.get("reason") or "gpu_memory_unavailable",
        }
        return report
    if int(available) < MIN_CUDA_FREE_BYTES:
        report["cuda_probe"] = {
            "status": "skipped",
            "reason": "insufficient_free_vram_for_bounded_probe",
        }
        return report

    epoch_data = _CalibrationEpochData()
    datasets = [_CalibrationDataset(epoch_data) for _index in range(CALIBRATION_FOLDS)]
    option = SimpleNamespace(
        bs=CALIBRATION_BATCH_SIZE,
        optim=torch.optim.Adam,
        repeat_num=CALIBRATION_REPEATS,
    )
    probe_budget = min(
        MAX_CUDA_PROBE_ESTIMATE_BYTES,
        int(int(available) * MAX_CUDA_PROBE_AVAILABLE_RATIO),
    )
    model_reports = []
    for model_type in _MODEL_TYPES:
        holder = ModelHolder(model_type, {})
        estimate = estimate_training_resources(
            datasets,
            option,
            model_holder=holder,
        )
        estimated_bytes = int(estimate["estimated_gpu_batch_working_set_bytes"])
        if estimated_bytes > probe_budget:
            model_reports.append(
                {
                    "model": model_type.__name__,
                    "status": "skipped",
                    "reason": "estimate_exceeds_probe_budget",
                    "estimated_vram_bytes": estimated_bytes,
                    "probe_budget_bytes": probe_budget,
                }
            )
            continue
        model_reports.append(
            _calibrate_model_step(
                model_type,
                estimate=estimate,
                probe_budget=probe_budget,
            )
        )

    failures = [
        item
        for item in model_reports
        if item.get("status") == "measured"
        and not item.get("estimate_covers_observed_peak")
    ]
    report["cuda_probe"] = {
        "status": "measured",
        "probe_budget_bytes": probe_budget,
        "models": model_reports,
        "all_estimates_cover_observed_peak": not failures,
    }
    report["gpu_after_probe"] = ResourceChecker.get_gpu_vram_status(0)
    return report


def strict_calibration_failure_reasons(
    report: dict[str, Any],
    *,
    validate_source: bool = False,
) -> list[str]:
    """Return strict failures, including current calibration-source freshness."""
    return _strict_calibration_failure_reasons(
        report,
        repo_root=ROOT,
        validate_source=validate_source,
    )


def _runtime_environment(gpu: dict[str, Any]) -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "python_executable": sys.executable,
        "torch": str(torch.__version__),
        "torch_cuda": str(torch.version.cuda) if torch.version.cuda else None,
        "cudnn": torch.backends.cudnn.version(),
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu_name": gpu.get("gpu_name"),
        "gpu_index": gpu.get("gpu_index"),
        "driver_version": _nvidia_driver_version(),
    }


def _nvidia_driver_version() -> str | None:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return None
    try:
        completed = subprocess.run(  # noqa: S603 - resolved binary, no shell.
            [
                executable,
                "--query-gpu=driver_version",
                "--format=csv,noheader",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.splitlines()
    return value[0].strip() if value and value[0].strip() else None


def _calibrate_model_step(
    model_type: type[torch.nn.Module],
    *,
    estimate: dict[str, Any],
    probe_budget: int,
) -> dict[str, Any]:
    device = "cuda:0"
    torch.cuda.empty_cache()
    gc.collect()
    torch.cuda.reset_peak_memory_stats(device)
    baseline_allocated = int(torch.cuda.memory_allocated(device))
    baseline_reserved = int(torch.cuda.memory_reserved(device))
    try:
        measured = _run_one_training_step(model_type, device)
    except Exception as exc:  # pragma: no cover - hardware/runtime specific
        return {
            "model": model_type.__name__,
            "status": "failed",
            "error_type": type(exc).__name__,
            "cuda_oom": is_cuda_oom_error(exc),
            "estimated_vram_bytes": int(
                estimate["estimated_gpu_batch_working_set_bytes"]
            ),
            "probe_budget_bytes": probe_budget,
        }
    finally:
        gc.collect()
        torch.cuda.empty_cache()

    peak_allocated = int(torch.cuda.max_memory_allocated(device))
    peak_reserved = int(torch.cuda.max_memory_reserved(device))
    observed_allocated = max(peak_allocated - baseline_allocated, 0)
    observed_reserved = max(peak_reserved - baseline_reserved, 0)
    estimated_bytes = int(estimate["estimated_gpu_batch_working_set_bytes"])
    return {
        "model": model_type.__name__,
        "status": "measured",
        "estimated_vram_bytes": estimated_bytes,
        "observed_peak_allocated_delta_bytes": observed_allocated,
        "observed_peak_reserved_delta_bytes": observed_reserved,
        "loss": measured["loss"],
        "estimate_to_observed_allocated_ratio": (
            None if observed_allocated == 0 else estimated_bytes / observed_allocated
        ),
        "estimate_covers_observed_peak": estimated_bytes >= observed_allocated,
        "fold_count": estimate["fold_count"],
        "repeat_count": estimate["repeat_count"],
        "peak_execution_scope": estimate["peak_execution_scope"],
        "formula": estimate["vram_formula"],
    }


def _run_one_training_step(
    model_type: type[torch.nn.Module],
    device: str,
) -> dict[str, float]:
    model = model_type(
        n_classes=CALIBRATION_CLASSES,
        channels=CALIBRATION_CHANNELS,
        samples=CALIBRATION_SAMPLES,
        sfreq=CALIBRATION_SFREQ,
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    inputs = torch.randn(
        CALIBRATION_BATCH_SIZE,
        CALIBRATION_CHANNELS,
        CALIBRATION_SAMPLES,
        device=device,
    )
    labels = inputs.new_tensor(
        [index % CALIBRATION_CLASSES for index in range(CALIBRATION_BATCH_SIZE)]
    ).long()
    optimizer.zero_grad(set_to_none=True)
    loss = torch.nn.functional.cross_entropy(model(inputs), labels)
    loss.backward()
    optimizer.step()
    torch.cuda.synchronize(device)
    loss_value = float(loss.detach().cpu())
    optimizer.zero_grad(set_to_none=True)
    del loss, labels, inputs, optimizer, model
    return {"loss": loss_value}


def write_calibration_report(path: str | Path, report: dict[str, Any]) -> Path:
    """Persist one complete calibration report for validation review."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-cuda-probe",
        action="store_true",
        help="Report live RAM/GPU status without allocating a calibration batch.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when a measured model peak exceeds its estimate.",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON artifact path for the complete calibration report.",
    )
    parsed_argv = list(argv) if argv is not None else sys.argv[1:]
    args = parser.parse_args(parsed_argv)
    report = build_calibration_report(
        run_cuda_probe=not args.no_cuda_probe,
        command=[sys.executable, str(Path(__file__)), *parsed_argv],
    )
    if args.output:
        output_path = write_calibration_report(args.output, report)
        print(f"Wrote {output_path}", file=sys.stderr)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.strict:
        failures = strict_calibration_failure_reasons(report, validate_source=True)
        if failures:
            for failure in failures:
                print(f"STRICT FAILURE: {failure}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
