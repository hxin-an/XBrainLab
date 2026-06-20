"""Resource preflight checks for training commands."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import import_module
from typing import Any

import torch

RAM_WORKING_SET_MULTIPLIER = 2.0
IMPORT_WORKING_SET_MULTIPLIER = 3.0
GPU_BATCH_WORKING_SET_MULTIPLIER = 8.0
MEMORY_LIMIT_FRACTION = 0.85


@dataclass(frozen=True)
class ResourcePreflightResult:
    """Result of a training resource preflight."""

    issues: tuple[str, ...]
    diagnostics: dict[str, Any]

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def message(self) -> str:
        return " ".join(self.issues)


def check_training_resource_preflight(training: Any) -> ResourcePreflightResult:
    """Return blocking resource issues before a training run starts."""
    context = _training_resource_context(training)
    datasets = list(context.get("datasets") or [])
    option = context.get("training_option")
    estimate = estimate_training_resources(datasets, option)

    ram_available = available_ram_bytes()
    gpu_idx = _gpu_index(option)
    vram_available = None if _uses_cpu(option) else available_vram_bytes(gpu_idx)

    diagnostics: dict[str, Any] = {
        **estimate,
        "available_ram_bytes": ram_available,
        "available_vram_bytes": vram_available,
        "gpu_index": gpu_idx,
        "uses_cpu": _uses_cpu(option),
    }
    issues: list[str] = []

    if (
        ram_available is not None
        and estimate["estimated_ram_working_set_bytes"]
        > ram_available * MEMORY_LIMIT_FRACTION
    ):
        issues.append(
            "Training dataset is too large for available RAM: "
            f"estimated working set "
            f"{_format_bytes(estimate['estimated_ram_working_set_bytes'])}, "
            f"available RAM {_format_bytes(ram_available)}. "
            "Use fewer files, shorter epochs, a lower sampling rate, or split the "
            "dataset before training."
        )

    if (
        vram_available is not None
        and estimate["estimated_gpu_batch_working_set_bytes"]
        > vram_available * MEMORY_LIMIT_FRACTION
    ):
        issues.append(
            "Training batch is too large for available GPU memory: "
            f"estimated batch working set "
            f"{_format_bytes(estimate['estimated_gpu_batch_working_set_bytes'])}, "
            f"available GPU memory {_format_bytes(vram_available)}. "
            "Lower the batch size, use CPU, or reduce epoch/channel/sample size."
        )

    return ResourcePreflightResult(tuple(issues), diagnostics)


def check_import_resource_preflight(paths: Iterable[str]) -> ResourcePreflightResult:
    """Return blocking resource issues before loading EEG files into memory."""
    path_list = [str(path) for path in paths]
    total_file_bytes = sum(_path_size(path) for path in path_list)
    estimated_ram = int(total_file_bytes * IMPORT_WORKING_SET_MULTIPLIER)
    ram_available = available_ram_bytes()
    diagnostics = {
        "path_count": len(path_list),
        "file_bytes": total_file_bytes,
        "estimated_ram_working_set_bytes": estimated_ram,
        "available_ram_bytes": ram_available,
    }
    if (
        ram_available is not None
        and estimated_ram > ram_available * MEMORY_LIMIT_FRACTION
    ):
        return ResourcePreflightResult(
            (
                "Selected EEG files are too large for available RAM: "
                f"estimated import working set {_format_bytes(estimated_ram)}, "
                f"available RAM {_format_bytes(ram_available)}. "
                "Load fewer files, use a smaller sample, or preprocess the data "
                "outside XBrainLab before importing.",
            ),
            diagnostics,
        )
    return ResourcePreflightResult((), diagnostics)


def estimate_training_resources(
    datasets: Iterable[Any],
    option: Any,
) -> dict[str, int]:
    """Estimate CPU and GPU working-set sizes for selected training datasets."""
    dataset_bytes = 0
    batch_bytes = 0
    seen_epoch_data: set[int] = set()
    batch_size = max(_positive_int(getattr(option, "bs", None), default=1), 1)

    for dataset in datasets:
        epoch_data = _safe_call(dataset, "get_epoch_data")
        if epoch_data is None or id(epoch_data) in seen_epoch_data:
            continue
        seen_epoch_data.add(id(epoch_data))
        data = _safe_call(epoch_data, "get_data")
        labels = _safe_call(epoch_data, "get_label_list")
        data_bytes = _nbytes(data)
        label_bytes = _nbytes(labels)
        dataset_bytes += data_bytes + label_bytes
        n_samples = max(_first_dim(data), 1)
        per_sample_bytes = int(data_bytes / n_samples) if n_samples else data_bytes
        batch_bytes += per_sample_bytes * min(batch_size, n_samples)

    return {
        "dataset_bytes": int(dataset_bytes),
        "estimated_ram_working_set_bytes": int(
            dataset_bytes * RAM_WORKING_SET_MULTIPLIER
        ),
        "estimated_gpu_batch_working_set_bytes": int(
            batch_bytes * GPU_BATCH_WORKING_SET_MULTIPLIER
        ),
    }


def available_ram_bytes() -> int | None:
    """Return available system RAM when the platform exposes it."""
    try:
        psutil = import_module("psutil")
        return int(psutil.virtual_memory().available)
    except Exception:
        pass

    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        available_pages = os.sysconf("SC_AVPHYS_PAGES")
        return int(page_size * available_pages)
    except (AttributeError, OSError, ValueError):
        return None


def available_vram_bytes(gpu_idx: int | None = None) -> int | None:
    """Return free CUDA memory for the selected device, if CUDA is available."""
    try:
        if not torch.cuda.is_available():
            return None
        device_index = 0 if gpu_idx is None else int(gpu_idx)
        free_bytes, _total = torch.cuda.mem_get_info(device_index)
        return int(free_bytes)
    except Exception:
        return None


def _training_resource_context(training: Any) -> dict[str, Any]:
    getter = getattr(training, "get_resource_preflight_context", None)
    if callable(getter):
        value = getter()
        if isinstance(value, dict):
            return dict(value)

    study = getattr(training, "_study", None)
    if study is not None:
        return {
            "datasets": list(getattr(study, "datasets", []) or []),
            "training_option": getattr(study, "training_option", None),
            "model_holder": getattr(study, "model_holder", None),
        }
    return {}


def _uses_cpu(option: Any) -> bool:
    return bool(getattr(option, "use_cpu", True))


def _gpu_index(option: Any) -> int | None:
    value = getattr(option, "gpu_idx", None)
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _safe_call(obj: Any, method_name: str) -> Any:
    method = getattr(obj, method_name, None)
    if not callable(method):
        return None
    try:
        return method()
    except Exception:
        return None


def _nbytes(value: Any) -> int:
    try:
        return max(int(getattr(value, "nbytes", 0)), 0)
    except (TypeError, ValueError):
        return 0


def _path_size(path: str) -> int:
    try:
        if os.path.isfile(path):
            return max(int(os.path.getsize(path)), 0)
    except OSError:
        return 0
    return 0


def _first_dim(value: Any) -> int:
    shape = getattr(value, "shape", None)
    if not shape:
        return 0
    try:
        return max(int(shape[0]), 0)
    except (TypeError, ValueError, IndexError):
        return 0


def _positive_int(value: Any, *, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _format_bytes(value: int | float) -> str:
    number = float(value)
    units = ("B", "KB", "MB", "GB", "TB")
    unit = units[0]
    for unit in units:
        if number < 1024 or unit == units[-1]:
            break
        number /= 1024
    if unit == "B":
        return f"{int(number)} {unit}"
    return f"{number:.1f} {unit}"
