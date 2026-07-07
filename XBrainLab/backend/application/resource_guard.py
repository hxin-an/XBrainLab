"""Resource preflight checks for import and training commands."""

from __future__ import annotations

import os
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

import torch

from XBrainLab.backend.utils.cuda_errors import (
    is_cuda_oom_error as _is_cuda_oom_error,
)
from XBrainLab.backend.utils.cuda_errors import (
    release_cuda_cache as _release_cuda_cache,
)

RISK_SAFE = "safe"
RISK_WARNING = "warning"
RISK_BLOCKING = "blocking"
RISK_UNKNOWN = "unknown"

RAM_WARNING_RATIO = 0.60
RAM_BLOCKING_RATIO = 0.80
VRAM_WARNING_RATIO = 0.75
VRAM_BLOCKING_RATIO = 0.90

RAM_SAFETY_MARGIN = 1.25
VRAM_SAFETY_MARGIN = 1.25
RAW_IMPORT_DTYPE_BYTES = 8
IMPORT_HEADER_OVERHEAD_MULTIPLIER = 1.35
IMPORT_FILE_SIZE_FALLBACK_MULTIPLIER = 4.0
IMPORT_METADATA_BYTES_PER_FILE = 1_048_576
TRAINING_RAM_WORKING_SET_MULTIPLIER = 2.0
TRAINING_INPUT_DTYPE_BYTES = 4
DEFAULT_ACTIVATION_FACTOR = 4.0
MODEL_ACTIVATION_FACTORS = {
    "eegnet": 8.0,
    "sccnet": 10.0,
    "shallowconvnet": 6.0,
    "transformer": 18.0,
}

DATASET_RAM_SUGGESTIONS = (
    "select fewer subjects, sessions, or files",
    "reduce epoch length if applicable",
    "downsample before import if supported",
    "close other applications",
    "use a smaller dataset split",
)
TRAINING_VRAM_SUGGESTIONS = (
    "reduce batch size",
    "reduce input length or epoch window",
    "use mixed precision if supported",
    "close other GPU applications",
    "choose a smaller model",
)


@dataclass(frozen=True)
class ResourceCheckResult:
    """Structured resource safety result for UI and command preflight."""

    required_memory_bytes: int | None
    available_memory_bytes: int | None
    total_memory_bytes: int | None
    used_memory_bytes: int | None
    risk_level: str
    message: str
    suggestions: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.risk_level != RISK_BLOCKING

    @property
    def blocking(self) -> bool:
        return self.risk_level == RISK_BLOCKING

    @property
    def warning(self) -> bool:
        return self.risk_level == RISK_WARNING

    def to_diagnostics(self) -> dict[str, Any]:
        """Return JSON-friendly diagnostics for command results."""
        return {
            "required_memory_bytes": self.required_memory_bytes,
            "available_memory_bytes": self.available_memory_bytes,
            "total_memory_bytes": self.total_memory_bytes,
            "used_memory_bytes": self.used_memory_bytes,
            "risk_level": self.risk_level,
            "message": self.message,
            "suggestions": list(self.suggestions),
            **dict(self.details),
        }


@dataclass(frozen=True)
class ResourcePreflightResult:
    """Command preflight result.

    ``issues`` are blocking. ``warnings`` are non-blocking but should be shown
    by interactive UI callers before they start the expensive operation.
    """

    issues: tuple[str, ...]
    diagnostics: dict[str, Any]
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def message(self) -> str:
        return " ".join(self.issues or self.warnings)


class ResourceChecker:
    """Centralized RAM/VRAM estimator for import and training workflows."""

    @staticmethod
    def estimate_dataset_ram(paths: Iterable[str]) -> dict[str, Any]:
        """Estimate import RAM without loading full EEG samples."""
        path_list = [str(path) for path in paths if str(path).strip()]
        total_file_bytes = sum(_path_size(path) for path in path_list)
        raw_bytes = 0
        metadata_bytes = 0
        preprocessing_buffer_bytes = 0
        epoch_cache_bytes = 0
        file_details: list[dict[str, Any]] = []

        for path in path_list:
            header = _estimate_eeg_file_from_header(path)
            if header is None:
                fallback_bytes = int(
                    _path_size(path) * IMPORT_FILE_SIZE_FALLBACK_MULTIPLIER
                )
                raw_bytes += fallback_bytes
                metadata_bytes += IMPORT_METADATA_BYTES_PER_FILE
                file_details.append(
                    {
                        "path": path,
                        "estimate_source": "file_size_fallback",
                        "file_bytes": _path_size(path),
                        "estimated_raw_bytes": fallback_bytes,
                    }
                )
                continue

            raw_bytes += int(header["raw_bytes"])
            annotations_bytes = int(header.get("annotations_bytes") or 0)
            metadata_bytes += IMPORT_METADATA_BYTES_PER_FILE + annotations_bytes
            file_details.append(header)

        preprocessing_buffer_bytes = int(
            raw_bytes * (IMPORT_HEADER_OVERHEAD_MULTIPLIER - 1.0)
        )
        required = int(
            (
                raw_bytes
                + metadata_bytes
                + preprocessing_buffer_bytes
                + epoch_cache_bytes
            )
            * RAM_SAFETY_MARGIN
        )
        return {
            "path_count": len(path_list),
            "file_bytes": int(total_file_bytes),
            "raw_eeg_bytes": int(raw_bytes),
            "labels_metadata_bytes": int(metadata_bytes),
            "preprocessing_intermediate_bytes": int(preprocessing_buffer_bytes),
            "epoch_cache_bytes": int(epoch_cache_bytes),
            "estimated_ram_working_set_bytes": int(required),
            "estimate_source": "header_or_file_size",
            "files": file_details,
            "safety_margin": RAM_SAFETY_MARGIN,
        }

    @staticmethod
    def get_system_ram_status() -> dict[str, int | None]:
        """Return system RAM status in bytes."""
        available = available_ram_bytes()
        total = None
        used = None
        try:
            psutil = import_module("psutil")
            memory = psutil.virtual_memory()
            total = int(memory.total)
            used = int(memory.used)
        except Exception:
            pass
        if total is not None and used is None and available is not None:
            used = max(total - available, 0)
        return {
            "total_bytes": total,
            "available_bytes": available,
            "used_bytes": used,
        }

    @staticmethod
    def check_dataset_load_safe(paths: Iterable[str]) -> ResourceCheckResult:
        """Return whether selected EEG files are safe to import into RAM."""
        estimate = ResourceChecker.estimate_dataset_ram(paths)
        ram = ResourceChecker.get_system_ram_status()
        return _memory_check_result(
            required_memory_bytes=estimate["estimated_ram_working_set_bytes"],
            available_memory_bytes=ram.get("available_bytes"),
            total_memory_bytes=ram.get("total_bytes"),
            used_memory_bytes=ram.get("used_bytes"),
            warning_ratio=RAM_WARNING_RATIO,
            blocking_ratio=RAM_BLOCKING_RATIO,
            resource_name="RAM",
            blocking_title="Dataset is too large to load safely.",
            warning_title="Dataset may be large for available RAM.",
            operation_risk=(
                "Loading this dataset may exceed available RAM, freeze, or "
                "crash the application."
            ),
            suggestions=DATASET_RAM_SUGGESTIONS,
            details=estimate,
        )

    @staticmethod
    def estimate_training_vram(
        datasets: Iterable[Any],
        training_option: Any,
        model_holder: Any | None = None,
    ) -> dict[str, Any]:
        """Estimate per-step GPU peak memory for the current training setup."""
        estimate = estimate_training_resources(
            datasets,
            training_option,
            model_holder=model_holder,
        )
        return {
            "estimated_vram_bytes": estimate["estimated_gpu_batch_working_set_bytes"],
            **estimate,
        }

    @staticmethod
    def get_gpu_vram_status(gpu_idx: int | None = None) -> dict[str, Any]:
        """Return CUDA memory status for a device, or unknown values."""
        if not _cuda_available():
            return {
                "gpu_name": None,
                "available_bytes": None,
                "total_bytes": None,
                "used_bytes": None,
                "allocated_bytes": None,
                "reserved_bytes": None,
            }
        device_index = 0 if gpu_idx is None else int(gpu_idx)
        available = available_vram_bytes(device_index)
        total = None
        allocated = None
        reserved = None
        gpu_name = None
        try:
            _free, total = torch.cuda.mem_get_info(device_index)
            total = int(total)
        except Exception:
            pass
        try:
            allocated = int(torch.cuda.memory_allocated(device_index))
            reserved = int(torch.cuda.memory_reserved(device_index))
        except Exception:
            pass
        try:
            gpu_name = str(torch.cuda.get_device_name(device_index))
        except Exception:
            gpu_name = None
        used = None
        if total is not None and available is not None:
            used = max(total - available, 0)
        return {
            "gpu_name": gpu_name,
            "available_bytes": available,
            "total_bytes": total,
            "used_bytes": used,
            "allocated_bytes": allocated,
            "reserved_bytes": reserved,
        }

    @staticmethod
    def check_training_config_safe(
        datasets: Iterable[Any],
        training_option: Any,
        model_holder: Any | None = None,
    ) -> ResourceCheckResult:
        """Return whether the current training config fits available VRAM."""
        if training_option is None:
            return ResourceCheckResult(
                required_memory_bytes=None,
                available_memory_bytes=None,
                total_memory_bytes=None,
                used_memory_bytes=None,
                risk_level=RISK_UNKNOWN,
                message=(
                    "Unable to estimate GPU memory before training settings are saved."
                ),
                suggestions=(),
                details={"uses_cpu": True, "reason": "missing_training_option"},
            )
        if _uses_cpu(training_option):
            return ResourceCheckResult(
                required_memory_bytes=0,
                available_memory_bytes=None,
                total_memory_bytes=None,
                used_memory_bytes=None,
                risk_level=RISK_SAFE,
                message="CPU training selected; GPU memory check is not required.",
                suggestions=(),
                details={"uses_cpu": True},
            )

        estimate = ResourceChecker.estimate_training_vram(
            datasets,
            training_option,
            model_holder,
        )
        gpu_idx = _gpu_index(training_option)
        vram = ResourceChecker.get_gpu_vram_status(gpu_idx)
        if vram.get("available_bytes") is None:
            return ResourceCheckResult(
                required_memory_bytes=estimate["estimated_vram_bytes"],
                available_memory_bytes=None,
                total_memory_bytes=vram.get("total_bytes"),
                used_memory_bytes=vram.get("used_bytes"),
                risk_level=RISK_UNKNOWN,
                message=(
                    "Unable to estimate GPU memory. CUDA is unavailable or did "
                    "not report free VRAM."
                ),
                suggestions=TRAINING_VRAM_SUGGESTIONS,
                details={**estimate, **vram, "uses_cpu": False, "gpu_index": gpu_idx},
            )
        return _memory_check_result(
            required_memory_bytes=estimate["estimated_vram_bytes"],
            available_memory_bytes=vram.get("available_bytes"),
            total_memory_bytes=vram.get("total_bytes"),
            used_memory_bytes=vram.get("used_bytes"),
            warning_ratio=VRAM_WARNING_RATIO,
            blocking_ratio=VRAM_BLOCKING_RATIO,
            resource_name="GPU memory",
            blocking_title="Training configuration may exceed available GPU memory.",
            warning_title="Training configuration is close to available GPU memory.",
            operation_risk=(
                "The current configuration may fail with CUDA out of memory."
            ),
            suggestions=TRAINING_VRAM_SUGGESTIONS,
            details={**estimate, **vram, "uses_cpu": False, "gpu_index": gpu_idx},
        )

    @staticmethod
    def format_memory_size(value: int | float | None) -> str:
        """Return a compact human-readable memory string."""
        if value is None:
            return "Unknown"
        return _format_bytes(value)

    @staticmethod
    def build_resource_warning_message(result: ResourceCheckResult) -> str:
        """Build a user-facing warning/error message."""
        return result.message


def check_training_resource_preflight(
    datasets: Iterable[Any],
    training_option: Any,
    model_holder: Any | None = None,
) -> ResourcePreflightResult:
    """Return resource issues before a training run starts."""
    dataset_result = _training_dataset_ram_check(datasets)
    vram_result = ResourceChecker.check_training_config_safe(
        datasets,
        training_option,
        model_holder,
    )

    diagnostics = {
        **dataset_result.to_diagnostics(),
        "dataset_ram_risk_level": dataset_result.risk_level,
        "vram_risk_level": vram_result.risk_level,
        "vram": vram_result.to_diagnostics(),
        "estimated_gpu_batch_working_set_bytes": (
            vram_result.required_memory_bytes or 0
        ),
        "available_vram_bytes": vram_result.available_memory_bytes,
        "gpu_index": _gpu_index(training_option),
        "uses_cpu": _uses_cpu(training_option),
    }
    issues = []
    warnings = []
    for result in (dataset_result, vram_result):
        if result.blocking:
            issues.append(result.message)
        elif result.warning:
            warnings.append(result.message)
    return ResourcePreflightResult(tuple(issues), diagnostics, tuple(warnings))


def check_import_resource_preflight(paths: Iterable[str]) -> ResourcePreflightResult:
    """Return resource issues before loading EEG files into memory."""
    result = ResourceChecker.check_dataset_load_safe(paths)
    diagnostics = result.to_diagnostics()
    diagnostics.update(
        {
            "path_count": result.details.get("path_count", 0),
            "file_bytes": result.details.get("file_bytes", 0),
            "estimated_ram_working_set_bytes": result.required_memory_bytes or 0,
            "available_ram_bytes": result.available_memory_bytes,
        }
    )
    issues = (result.message,) if result.blocking else ()
    warnings = (result.message,) if result.warning else ()
    return ResourcePreflightResult(issues, diagnostics, warnings)


def estimate_training_resources(
    datasets: Iterable[Any],
    option: Any,
    *,
    model_holder: Any | None = None,
) -> dict[str, int | float | str | None]:
    """Estimate CPU and GPU working-set sizes for selected training datasets."""
    dataset_list = list(datasets or [])
    dataset_bytes = 0
    peak_input_batch_bytes = 0
    peak_validation_batch_bytes = 0
    seen_epoch_data: set[int] = set()
    batch_size = max(_positive_int(getattr(option, "bs", None), default=1), 1)
    class_count = 1

    for dataset in dataset_list:
        epoch_data = _safe_call(dataset, "get_epoch_data")
        if epoch_data is None:
            continue
        data = _safe_call(epoch_data, "get_data")
        labels = _safe_call(epoch_data, "get_label_list")
        data_bytes = _nbytes(data)
        label_bytes = _nbytes(labels)
        if id(epoch_data) not in seen_epoch_data:
            seen_epoch_data.add(id(epoch_data))
            dataset_bytes += data_bytes + label_bytes
        n_samples = max(_first_dim(data), 1)
        class_count = max(class_count, _class_count(labels))
        per_sample_gpu_bytes = _per_sample_tensor_bytes(data)
        train_count = _mask_count(getattr(dataset, "train_mask", None), n_samples)
        val_count = max(
            _mask_count(getattr(dataset, "val_mask", None), n_samples),
            _mask_count(getattr(dataset, "test_mask", None), n_samples),
        )
        peak_input_batch_bytes = max(
            peak_input_batch_bytes,
            per_sample_gpu_bytes * min(batch_size, max(train_count, 1)),
        )
        peak_validation_batch_bytes = max(
            peak_validation_batch_bytes,
            per_sample_gpu_bytes * min(batch_size, max(val_count, 1)),
        )

    model_parameter_bytes = _estimate_model_parameter_bytes(
        model_holder,
        dataset_list,
    )
    gradient_bytes = model_parameter_bytes
    optimizer_state_bytes = int(
        model_parameter_bytes * _optimizer_state_multiplier(option)
    )
    activation_factor = _activation_factor(model_holder)
    activation_bytes = int(peak_input_batch_bytes * activation_factor)
    logits_bytes = int(batch_size * class_count * TRAINING_INPUT_DTYPE_BYTES * 3)
    estimated_gpu = int(
        (
            model_parameter_bytes
            + gradient_bytes
            + optimizer_state_bytes
            + peak_input_batch_bytes
            + activation_bytes
            + logits_bytes
            + peak_validation_batch_bytes
        )
        * VRAM_SAFETY_MARGIN
    )
    return {
        "dataset_count": len(dataset_list),
        "dataset_bytes": int(dataset_bytes),
        "estimated_ram_working_set_bytes": int(
            dataset_bytes * TRAINING_RAM_WORKING_SET_MULTIPLIER
        ),
        "peak_input_batch_bytes": int(peak_input_batch_bytes),
        "peak_validation_batch_bytes": int(peak_validation_batch_bytes),
        "model_parameter_bytes": int(model_parameter_bytes),
        "gradient_bytes": int(gradient_bytes),
        "optimizer_state_bytes": int(optimizer_state_bytes),
        "activation_bytes": int(activation_bytes),
        "activation_factor": float(activation_factor),
        "logits_bytes": int(logits_bytes),
        "class_count": int(class_count),
        "batch_size": int(batch_size),
        "estimated_gpu_batch_working_set_bytes": estimated_gpu,
        "vram_safety_margin": VRAM_SAFETY_MARGIN,
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


def is_cuda_oom_error(exc: BaseException) -> bool:
    """Return whether an exception represents CUDA memory exhaustion."""
    return _is_cuda_oom_error(exc)


def release_cuda_cache() -> None:
    """Release cached CUDA memory when CUDA is available."""
    _release_cuda_cache(torch)


def _training_dataset_ram_check(datasets: Iterable[Any]) -> ResourceCheckResult:
    estimate = estimate_training_resources(datasets, None)
    ram = ResourceChecker.get_system_ram_status()
    required_ram = int(estimate["estimated_ram_working_set_bytes"] or 0)
    return _memory_check_result(
        required_memory_bytes=required_ram,
        available_memory_bytes=ram.get("available_bytes"),
        total_memory_bytes=ram.get("total_bytes"),
        used_memory_bytes=ram.get("used_bytes"),
        warning_ratio=RAM_WARNING_RATIO,
        blocking_ratio=RAM_BLOCKING_RATIO,
        resource_name="RAM",
        blocking_title="Training dataset is too large for available RAM.",
        warning_title="Training dataset is close to available RAM.",
        operation_risk="Training may freeze or crash the application.",
        suggestions=DATASET_RAM_SUGGESTIONS,
        details=estimate,
    )


def _memory_check_result(
    *,
    required_memory_bytes: int | float | None,
    available_memory_bytes: int | None,
    total_memory_bytes: int | None,
    used_memory_bytes: int | None,
    warning_ratio: float,
    blocking_ratio: float,
    resource_name: str,
    blocking_title: str,
    warning_title: str,
    operation_risk: str,
    suggestions: tuple[str, ...],
    details: dict[str, Any],
) -> ResourceCheckResult:
    required = None if required_memory_bytes is None else int(required_memory_bytes)
    if required is None or available_memory_bytes is None:
        return ResourceCheckResult(
            required_memory_bytes=required,
            available_memory_bytes=available_memory_bytes,
            total_memory_bytes=total_memory_bytes,
            used_memory_bytes=used_memory_bytes,
            risk_level=RISK_UNKNOWN,
            message=f"Unable to estimate available {resource_name}.",
            suggestions=suggestions,
            details=dict(details),
        )

    if required > available_memory_bytes * blocking_ratio:
        risk = RISK_BLOCKING
        title = blocking_title
        risk_text = "Too large"
    elif required > available_memory_bytes * warning_ratio:
        risk = RISK_WARNING
        title = warning_title
        risk_text = "Warning"
    else:
        risk = RISK_SAFE
        title = "Resource check: Safe"
        risk_text = "Safe"

    message = _resource_message(
        title=title,
        required=required,
        available=available_memory_bytes,
        resource_name=resource_name,
        risk_text=risk_text,
        operation_risk=operation_risk if risk != RISK_SAFE else "",
        suggestions=suggestions if risk != RISK_SAFE else (),
    )
    return ResourceCheckResult(
        required_memory_bytes=required,
        available_memory_bytes=available_memory_bytes,
        total_memory_bytes=total_memory_bytes,
        used_memory_bytes=used_memory_bytes,
        risk_level=risk,
        message=message,
        suggestions=suggestions if risk != RISK_SAFE else (),
        details=dict(details),
    )


def _resource_message(
    *,
    title: str,
    required: int,
    available: int,
    resource_name: str,
    risk_text: str,
    operation_risk: str,
    suggestions: tuple[str, ...],
) -> str:
    lines = [
        title,
        "",
        f"Estimated memory required: {_format_bytes(required)}",
        f"Available {resource_name}: {_format_bytes(available)}",
        f"Risk level: {risk_text}",
    ]
    if operation_risk:
        lines.extend(["", operation_risk])
    if suggestions:
        lines.extend(["", "Suggestions:"])
        lines.extend(f"- {item}" for item in suggestions)
    return "\n".join(lines)


def _estimate_eeg_file_from_header(path: str) -> dict[str, Any] | None:
    file_path = Path(path)
    if not file_path.is_file():
        return None
    suffix = _normalized_suffix(file_path)
    reader_name = {
        ".bdf": "read_raw_bdf",
        ".cnt": "read_raw_cnt",
        ".edf": "read_raw_edf",
        ".fif": "read_raw_fif",
        ".fif.gz": "read_raw_fif",
        ".gdf": "read_raw_gdf",
        ".set": "read_raw_eeglab",
        ".vhdr": "read_raw_brainvision",
    }.get(suffix)
    if reader_name is None:
        return None
    try:
        mne = import_module("mne")
        reader = getattr(mne.io, reader_name)
        raw = reader(str(file_path), preload=False, verbose="ERROR")
        n_channels = len(getattr(raw, "ch_names", []) or [])
        n_times = int(getattr(raw, "n_times", 0) or 0)
        info_getter = getattr(getattr(raw, "info", {}), "get", lambda *_: 0)
        sfreq = float(info_getter("sfreq", 0))
        raw_bytes = int(n_channels * n_times * RAW_IMPORT_DTYPE_BYTES)
        annotations = getattr(raw, "annotations", None)
        annotations_bytes = (
            int(len(annotations) * 256) if annotations is not None else 0
        )
        close = getattr(raw, "close", None)
        if callable(close):
            close()
        return {
            "path": str(file_path),
            "estimate_source": "mne_header",
            "file_bytes": _path_size(str(file_path)),
            "channels": n_channels,
            "time_samples": n_times,
            "sampling_rate_hz": sfreq,
            "dtype_size_bytes": RAW_IMPORT_DTYPE_BYTES,
            "estimated_raw_bytes": raw_bytes,
            "raw_bytes": raw_bytes,
            "annotations_bytes": annotations_bytes,
        }
    except Exception:
        return None


def _normalized_suffix(path: Path) -> str:
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if len(suffixes) >= 2 and suffixes[-2:] == [".fif", ".gz"]:
        return ".fif.gz"
    return path.suffix.lower()


def _cuda_available() -> bool:
    try:
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _uses_cpu(option: Any) -> bool:
    if option is None:
        return True
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
        if os.path.isdir(path):
            total = 0
            for root, _dirs, files in os.walk(path):
                for name in files:
                    total += _path_size(os.path.join(root, name))
            return total
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


def _per_sample_tensor_bytes(data: Any) -> int:
    shape = getattr(data, "shape", None)
    if shape and len(shape) > 1:
        elements = 1
        try:
            for dim in shape[1:]:
                elements *= max(int(dim), 1)
            return int(elements * TRAINING_INPUT_DTYPE_BYTES)
        except (TypeError, ValueError):
            pass
    n_samples = max(_first_dim(data), 1)
    return int(_nbytes(data) / n_samples) if n_samples else _nbytes(data)


def _mask_count(mask: Any, fallback: int) -> int:
    if mask is None:
        return fallback
    try:
        return max(int(sum(mask)), 0)
    except TypeError:
        try:
            return max(int(mask.sum()), 0)
        except Exception:
            return fallback


def _class_count(labels: Any) -> int:
    try:
        unique = set(labels)
        return max(len(unique), 1)
    except Exception:
        shape = getattr(labels, "shape", None)
        if shape:
            try:
                return max(int(shape[-1]), 1)
            except (TypeError, ValueError, IndexError):
                pass
    return 1


def _estimate_model_parameter_bytes(
    model_holder: Any | None,
    datasets: list[Any],
) -> int:
    if model_holder is None:
        return 0
    args: dict[str, Any] = {}
    for dataset in datasets:
        epoch_data = _safe_call(dataset, "get_epoch_data")
        if epoch_data is None:
            continue
        model_args = _safe_call(epoch_data, "get_model_args")
        if isinstance(model_args, dict):
            args = dict(model_args)
            break
    try:
        model = model_holder.get_model(args)
        total = sum(
            int(parameter.numel()) * int(parameter.element_size())
            for parameter in model.parameters()
        )
        with suppress(Exception):
            model.cpu()
        del model
        return max(total, 0)
    except Exception:
        return 0


def _optimizer_state_multiplier(option: Any) -> float:
    optim = getattr(option, "optim", None)
    name = str(getattr(optim, "__name__", optim) or "").lower()
    if "adam" in name:
        return 2.0
    if "sgd" in name:
        return 1.0
    return 1.5


def _activation_factor(model_holder: Any | None) -> float:
    target_model = getattr(model_holder, "target_model", None)
    name = str(getattr(target_model, "__name__", "") or "").lower()
    for key, factor in MODEL_ACTIVATION_FACTORS.items():
        if key in name:
            return factor
    return DEFAULT_ACTIVATION_FACTOR


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
