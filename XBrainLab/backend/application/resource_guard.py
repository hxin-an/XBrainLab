"""Resource preflight checks for import, epoch, and training commands."""

from __future__ import annotations

import math
import os
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass, field
from enum import Enum
from importlib import import_module
from itertools import islice
from pathlib import Path
from typing import Any

from XBrainLab.backend.utils.cuda_errors import (
    is_cuda_oom_error as _is_cuda_oom_error,
)
from XBrainLab.backend.utils.cuda_errors import (
    release_cuda_cache as _release_cuda_cache,
)
from XBrainLab.backend.utils.logger import logger

from .data_interpretation_bids_resources import is_bids_events_json_sidecar
from .data_interpretation_formats import (
    is_bids_metadata_table,
)
from .eeglab_set_preflight import (
    MAT_COMPRESSED_HEADER_BUDGET_BYTES,
    EeglabSetHeaderInspection,
    inspect_eeglab_set_header,
)
from .errors import ApplicationError, PreconditionError
from .resource_label_estimation import (
    SUPPORTED_EXTERNAL_LABEL_EXTENSIONS,
    create_mat_preflight_read_budget,
    estimate_label_carrier_working_set,
)
from .resource_preflight import (
    ResourceConfirmationChallenge,
    ResourcePreflightView,
)
from .results import ErrorType

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
EEGLAB_FDT_TO_FLOAT64_MULTIPLIER = 2.0
IMPORT_METADATA_BYTES_PER_FILE = 1_048_576
TRAINING_RAM_WORKING_SET_MULTIPLIER = 2.0
TRAINING_RAM_SAFETY_MARGIN = 1.25
TRAINING_RETAINED_GRADIENT_COPIES = 1
TRAINING_BEST_CHECKPOINT_COPIES = 3
TRAINING_INPUT_DTYPE_BYTES = 4
DEFAULT_ACTIVATION_FACTOR = 4.0
TRAINING_RUNTIME_WORKSPACE_BYTES = 64 * 1024 * 1024
MODEL_PARAMETER_FALLBACK_BYTES = 16 * 1024 * 1024
CLASS_COUNT_SCAN_LIMIT = 4_096
EPOCH_DTYPE_BYTES = 8
EPOCH_COPY_BUFFER_FACTOR = 2.0
EPOCH_PRELOAD_BUFFER_FACTOR = 1.0
EPOCH_RAM_SAFETY_MARGIN = 1.25
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
EPOCH_RAM_SUGGESTIONS = (
    "select fewer event classes",
    "shorten the epoch window",
    "select fewer channels before epoching",
    "resample to a lower sampling frequency",
    "close other applications",
)


class ResourceRiskLevel(str, Enum):
    """Aggregate resource-preflight risk exposed across application clients."""

    SAFE = RISK_SAFE
    WARNING = RISK_WARNING
    BLOCKING = RISK_BLOCKING
    UNKNOWN = RISK_UNKNOWN


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
            **dict(self.details),
            "required_memory_bytes": self.required_memory_bytes,
            "available_memory_bytes": self.available_memory_bytes,
            "total_memory_bytes": self.total_memory_bytes,
            "used_memory_bytes": self.used_memory_bytes,
            "risk_level": self.risk_level,
            "message": self.message,
            "suggestions": list(self.suggestions),
        }


@dataclass(frozen=True, slots=True)
class _ModelParameterMemoryEstimate:
    """Model-memory estimate plus whether it came from a real model instance."""

    bytes: int
    source: str
    reliable: bool
    error_type: str | None = None


@dataclass(frozen=True)
class ResourcePreflightResult:
    """Command preflight result.

    ``issues`` are blocking. ``warnings`` are non-blocking but should be shown
    by interactive UI callers before they start the expensive operation.
    """

    issues: tuple[str, ...]
    diagnostics: dict[str, Any]
    warnings: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()

    @property
    def risk_level(self) -> ResourceRiskLevel:
        """Return one deterministic aggregate risk for all checked resources."""
        if self.issues:
            return ResourceRiskLevel.BLOCKING
        if self.warnings:
            return ResourceRiskLevel.WARNING
        if self.unknowns:
            return ResourceRiskLevel.UNKNOWN

        diagnostic_levels = _resource_risk_levels(self.diagnostics)
        for risk_level in (
            ResourceRiskLevel.BLOCKING,
            ResourceRiskLevel.WARNING,
            ResourceRiskLevel.UNKNOWN,
        ):
            if risk_level in diagnostic_levels:
                return risk_level
        return ResourceRiskLevel.SAFE

    @property
    def ok(self) -> bool:
        return not self.blocking

    @property
    def blocking(self) -> bool:
        return self.risk_level is ResourceRiskLevel.BLOCKING

    @property
    def requires_confirmation(self) -> bool:
        return self.risk_level in {
            ResourceRiskLevel.WARNING,
            ResourceRiskLevel.UNKNOWN,
        }

    @property
    def message(self) -> str:
        messages = self.issues or (*self.warnings, *self.unknowns)
        if messages:
            return " ".join(messages)
        return str(self.diagnostics.get("message") or "")

    def to_view(
        self,
        *,
        challenge: ResourceConfirmationChallenge | None = None,
    ) -> ResourcePreflightView:
        """Return the typed application-client view for this preflight."""
        return ResourcePreflightView.create(
            risk_level=self.risk_level.value,
            requires_confirmation=self.requires_confirmation,
            message=self.message,
            issues=self.issues,
            warnings=self.warnings,
            unknowns=self.unknowns,
            suggestions=tuple(
                str(item) for item in self.diagnostics.get("suggestions", ()) or ()
            ),
            details=self.diagnostics,
            challenge=challenge,
        )

    def to_diagnostics(
        self,
        *,
        challenge: ResourceConfirmationChallenge | None = None,
    ) -> dict[str, Any]:
        """Return the sole versioned JSON-safe preflight wire contract."""
        return self.to_view(challenge=challenge).to_diagnostics()


class ResourceConfirmationRequiredError(ApplicationError):
    """Raised before mutation when warning/unknown resource risk needs consent."""

    def __init__(
        self,
        preflight: ResourcePreflightResult,
        *,
        challenge: ResourceConfirmationChallenge | None = None,
    ):
        super().__init__(
            message=preflight.message,
            error_type=ErrorType.CONFIRMATION_REQUIRED,
            recoverable=True,
            diagnostics={
                "resource_preflight": preflight.to_diagnostics(
                    challenge=challenge,
                )
            },
        )


def enforce_resource_preflight(
    preflight: ResourcePreflightResult,
    *,
    confirmed: bool,
) -> None:
    """Enforce blocking and explicit warning/unknown continuation semantics."""
    diagnostics = {"resource_preflight": preflight.to_diagnostics()}
    if preflight.blocking:
        raise PreconditionError(preflight.message, diagnostics=diagnostics)
    if preflight.requires_confirmation and not confirmed:
        raise ResourceConfirmationRequiredError(preflight)


class ResourceChecker:
    """Centralized RAM/VRAM estimator for memory-sensitive workflows."""

    @staticmethod
    def estimate_epoch_ram(
        preprocessed_data: Iterable[Any],
        *,
        selected_event_names: list[str] | dict[str, int] | None,
        tmin: float,
        tmax: float,
    ) -> dict[str, Any]:
        """Estimate peak RAM for eager epoch copy and preload materialization."""
        tmin_value = float(tmin)
        tmax_value = float(tmax)
        if not math.isfinite(tmin_value) or not math.isfinite(tmax_value):
            raise ValueError("Epoch window values must be finite.")
        if tmax_value < tmin_value:
            raise ValueError("Epoch end time must not be before its start time.")

        selected_names = (
            None
            if selected_event_names is None
            else {str(name) for name in selected_event_names}
        )
        source_details: list[dict[str, Any]] = []
        total_selected_events = 0
        total_channel_samples = 0

        for index, source in enumerate(list(preprocessed_data or [])):
            events, event_id = source.get_event_list()
            if not isinstance(event_id, dict):
                raise ValueError("Epoch event identifiers could not be inspected.")
            selected_ids = {
                int(identifier)
                for name, identifier in event_id.items()
                if selected_names is None or str(name) in selected_names
            }
            selected_count = sum(
                1 for event in events if int(event[-1]) in selected_ids
            )
            channel_count = int(source.get_nchan())
            sfreq = float(source.get_sfreq())
            if channel_count <= 0 or not math.isfinite(sfreq) or sfreq <= 0:
                raise ValueError("Epoch channel or sampling metadata is invalid.")
            start_offset = round(tmin_value * sfreq)
            stop_offset = round(tmax_value * sfreq)
            window_samples = stop_offset - start_offset + 1
            if window_samples <= 0:
                raise ValueError("Epoch window does not contain any samples.")

            channel_samples = selected_count * channel_count * window_samples
            total_selected_events += selected_count
            total_channel_samples += channel_samples
            filename_getter = getattr(source, "get_filename", None)
            filename = (
                str(filename_getter())
                if callable(filename_getter)
                else f"source-{index}"
            )
            source_details.append(
                {
                    "index": index,
                    "filename": filename,
                    "selected_event_count": selected_count,
                    "channel_count": channel_count,
                    "sfreq": sfreq,
                    "window_samples": window_samples,
                    "channel_samples": channel_samples,
                }
            )

        epoch_payload_bytes = total_channel_samples * EPOCH_DTYPE_BYTES
        copy_buffer_bytes = int(epoch_payload_bytes * EPOCH_COPY_BUFFER_FACTOR)
        preload_buffer_bytes = int(epoch_payload_bytes * EPOCH_PRELOAD_BUFFER_FACTOR)
        estimated_before_safety_bytes = copy_buffer_bytes + preload_buffer_bytes
        estimated_ram_working_set_bytes = math.ceil(
            estimated_before_safety_bytes * EPOCH_RAM_SAFETY_MARGIN
        )
        return {
            "source_count": len(source_details),
            "selected_event_count": total_selected_events,
            "channel_samples": total_channel_samples,
            "dtype_bytes": EPOCH_DTYPE_BYTES,
            "epoch_payload_bytes": epoch_payload_bytes,
            "copy_buffer_factor": EPOCH_COPY_BUFFER_FACTOR,
            "copy_buffer_bytes": copy_buffer_bytes,
            "preload_buffer_factor": EPOCH_PRELOAD_BUFFER_FACTOR,
            "preload_buffer_bytes": preload_buffer_bytes,
            "estimated_before_safety_bytes": estimated_before_safety_bytes,
            "safety_margin": EPOCH_RAM_SAFETY_MARGIN,
            "estimated_ram_working_set_bytes": estimated_ram_working_set_bytes,
            "sources": source_details,
            "formula": (
                "selected_events * channels * window_samples * dtype_bytes * "
                "(copy_buffer_factor + preload_buffer_factor) * safety_margin"
            ),
        }

    @staticmethod
    def check_epoch_materialization_safe(
        preprocessed_data: Iterable[Any],
        *,
        selected_event_names: list[str] | dict[str, int] | None,
        tmin: float,
        tmax: float,
    ) -> ResourceCheckResult:
        """Return whether eager epoch materialization fits available RAM."""
        ram = ResourceChecker.get_system_ram_status()
        try:
            estimate = ResourceChecker.estimate_epoch_ram(
                preprocessed_data,
                selected_event_names=selected_event_names,
                tmin=tmin,
                tmax=tmax,
            )
        except Exception as exc:
            return ResourceCheckResult(
                required_memory_bytes=None,
                available_memory_bytes=ram.get("available_bytes"),
                total_memory_bytes=ram.get("total_bytes"),
                used_memory_bytes=ram.get("used_bytes"),
                risk_level=RISK_UNKNOWN,
                message=(
                    "Unable to bound epoch materialization RAM before creating epochs."
                ),
                suggestions=EPOCH_RAM_SUGGESTIONS,
                details={
                    "estimate_status": RISK_UNKNOWN,
                    "reason": "epoch_metadata_unavailable",
                    "exception_type": exc.__class__.__name__,
                },
            )
        return _memory_check_result(
            required_memory_bytes=estimate["estimated_ram_working_set_bytes"],
            available_memory_bytes=ram.get("available_bytes"),
            total_memory_bytes=ram.get("total_bytes"),
            used_memory_bytes=ram.get("used_bytes"),
            warning_ratio=RAM_WARNING_RATIO,
            blocking_ratio=RAM_BLOCKING_RATIO,
            resource_name="RAM",
            blocking_title="Epoch materialization is too large for available RAM.",
            warning_title="Epoch materialization is close to available RAM.",
            operation_risk=(
                "Creating these epochs may freeze or crash the application."
            ),
            suggestions=EPOCH_RAM_SUGGESTIONS,
            details=estimate,
        )

    @staticmethod
    def estimate_dataset_ram(paths: Iterable[str]) -> dict[str, Any]:
        """Estimate EEG and label-carrier RAM without loading their payloads."""
        path_list = _deduplicated_resource_paths(paths)
        eeglab_headers: dict[str, EeglabSetHeaderInspection] = {}
        eeglab_dependency_owners: dict[str, str] = {}
        for path in tuple(path_list):
            resource_path = Path(path)
            if _normalized_suffix(resource_path) != ".set":
                continue
            inspection = inspect_eeglab_set_header(resource_path)
            eeglab_headers[_path_key(resource_path)] = inspection
            dependency = str(inspection.external_data_file or "").strip()
            if not dependency:
                continue
            dependency_key = _path_key(Path(dependency))
            eeglab_dependency_owners[dependency_key] = str(resource_path)
            if dependency_key not in {_path_key(Path(item)) for item in path_list}:
                path_list.append(dependency)
        total_file_bytes = sum(_path_size(path) for path in path_list)
        raw_bytes = 0
        metadata_bytes = 0
        label_carrier_file_bytes = 0
        label_carrier_persistent_bytes = 0
        label_parser_transient_peak_bytes = 0
        scan_metadata_file_bytes = 0
        scan_metadata_persistent_bytes = 0
        scan_metadata_parser_transient_peak_bytes = 0
        preprocessing_buffer_bytes = 0
        epoch_cache_bytes = 0
        eeg_path_count = 0
        label_carrier_count = 0
        scan_metadata_count = 0
        unbounded_eeg_files: list[dict[str, str]] = []
        file_details: list[dict[str, Any]] = []
        mat_read_budget = create_mat_preflight_read_budget()

        for path in path_list:
            resource_path = Path(path)
            resource_key = _path_key(resource_path)
            suffix = _normalized_suffix(resource_path)
            dependency_owner = eeglab_dependency_owners.get(resource_key)
            if dependency_owner is not None:
                file_bytes = _path_size(path)
                file_details.append(
                    {
                        "path": path,
                        "resource_kind": "eeg_data_sidecar",
                        "format": suffix,
                        "file_bytes": file_bytes,
                        "estimated_working_set_bytes": 0,
                        "estimate_source": "eeglab_external_data_dependency",
                        "referenced_by": dependency_owner,
                    }
                )
                continue
            is_scan_metadata = _is_scan_metadata_path(resource_path)
            if is_scan_metadata or suffix in SUPPORTED_EXTERNAL_LABEL_EXTENSIONS:
                file_bytes = _path_size(path)
                working_set_bytes, carrier_details = estimate_label_carrier_working_set(
                    path,
                    suffix=suffix,
                    file_bytes=file_bytes,
                    mat_read_budget=mat_read_budget,
                )
                resource_kind = "scan_metadata" if is_scan_metadata else "label_carrier"
                if is_scan_metadata:
                    scan_metadata_count += 1
                    scan_metadata_file_bytes += file_bytes
                    scan_metadata_persistent_bytes += int(
                        carrier_details.get("persistent_bytes", working_set_bytes)
                    )
                    scan_metadata_parser_transient_peak_bytes = max(
                        scan_metadata_parser_transient_peak_bytes,
                        int(carrier_details.get("parser_transient_bytes", 0)),
                    )
                else:
                    label_carrier_count += 1
                    label_carrier_file_bytes += file_bytes
                    label_carrier_persistent_bytes += int(
                        carrier_details.get("persistent_bytes", working_set_bytes)
                    )
                    label_parser_transient_peak_bytes = max(
                        label_parser_transient_peak_bytes,
                        int(carrier_details.get("parser_transient_bytes", 0)),
                    )
                file_details.append(
                    {
                        "path": path,
                        "resource_kind": resource_kind,
                        "format": suffix,
                        "file_bytes": file_bytes,
                        "estimated_working_set_bytes": working_set_bytes,
                        **carrier_details,
                    }
                )
                continue

            eeg_path_count += 1
            header = _estimate_eeg_file_from_header(
                path,
                eeglab_inspection=eeglab_headers.get(resource_key),
            )
            if header is None:
                fallback_bytes = int(
                    _path_size(path) * IMPORT_FILE_SIZE_FALLBACK_MULTIPLIER
                )
                raw_bytes += fallback_bytes
                metadata_bytes += IMPORT_METADATA_BYTES_PER_FILE
                file_details.append(
                    {
                        "path": path,
                        "resource_kind": "eeg",
                        "estimate_source": "file_size_fallback",
                        "file_bytes": _path_size(path),
                        "estimated_raw_bytes": fallback_bytes,
                    }
                )
                continue

            header = {**header, "resource_kind": "eeg"}
            if not bool(header.get("size_bound_known", True)):
                unbounded_eeg_files.append(
                    {
                        "path": str(path),
                        "reason_code": str(header.get("reason_code") or "unknown"),
                        "reason": str(header.get("estimate_reason") or ""),
                    }
                )
            else:
                raw_bytes += int(header["raw_bytes"])
            annotations_bytes = int(header.get("annotations_bytes") or 0)
            metadata_bytes += IMPORT_METADATA_BYTES_PER_FILE + annotations_bytes
            file_details.append(header)

        label_carrier_working_set_bytes = (
            label_carrier_persistent_bytes + label_parser_transient_peak_bytes
        )
        scan_metadata_working_set_bytes = (
            scan_metadata_persistent_bytes + scan_metadata_parser_transient_peak_bytes
        )
        external_parser_transient_peak_bytes = max(
            label_parser_transient_peak_bytes,
            scan_metadata_parser_transient_peak_bytes,
        )
        preprocessing_buffer_bytes = int(
            raw_bytes * (IMPORT_HEADER_OVERHEAD_MULTIPLIER - 1.0)
        )
        partial_required = int(
            (
                raw_bytes
                + metadata_bytes
                + label_carrier_persistent_bytes
                + scan_metadata_persistent_bytes
                + external_parser_transient_peak_bytes
                + preprocessing_buffer_bytes
                + epoch_cache_bytes
            )
            * RAM_SAFETY_MARGIN
        )
        required: int | None = None if unbounded_eeg_files else partial_required
        return {
            "path_count": len(path_list),
            "eeg_path_count": eeg_path_count,
            "label_carrier_count": label_carrier_count,
            "scan_metadata_count": scan_metadata_count,
            "file_bytes": int(total_file_bytes),
            "raw_eeg_bytes": int(raw_bytes),
            "metadata_bytes": int(metadata_bytes),
            "label_carrier_file_bytes": int(label_carrier_file_bytes),
            "label_carrier_working_set_bytes": int(label_carrier_working_set_bytes),
            "label_carrier_persistent_bytes": int(label_carrier_persistent_bytes),
            "label_parser_transient_peak_bytes": int(label_parser_transient_peak_bytes),
            "scan_metadata_file_bytes": int(scan_metadata_file_bytes),
            "scan_metadata_working_set_bytes": int(
                scan_metadata_working_set_bytes,
            ),
            "scan_metadata_persistent_bytes": int(scan_metadata_persistent_bytes),
            "scan_metadata_parser_transient_peak_bytes": int(
                scan_metadata_parser_transient_peak_bytes
            ),
            "external_parser_transient_peak_bytes": int(
                external_parser_transient_peak_bytes
            ),
            "mat_preflight_read_budget_bytes": mat_read_budget.limit_bytes,
            "mat_preflight_bytes_read": mat_read_budget.bytes_read,
            "mat_preflight_budget_exhausted": mat_read_budget.exhausted,
            "labels_metadata_bytes": int(
                metadata_bytes
                + label_carrier_persistent_bytes
                + scan_metadata_persistent_bytes
                + external_parser_transient_peak_bytes
            ),
            "preprocessing_intermediate_bytes": int(preprocessing_buffer_bytes),
            "epoch_cache_bytes": int(epoch_cache_bytes),
            "estimated_ram_working_set_bytes": required,
            "partial_estimated_ram_working_set_bytes": partial_required,
            "size_bound_known": not unbounded_eeg_files,
            "unbounded_eeg_files": unbounded_eeg_files,
            "estimate_source": "header_or_file_size",
            "files": file_details,
            "safety_margin": RAM_SAFETY_MARGIN,
            "raw_import_dtype": "float64",
            "raw_import_dtype_bytes": RAW_IMPORT_DTYPE_BYTES,
            "file_size_fallback_multiplier": (IMPORT_FILE_SIZE_FALLBACK_MULTIPLIER),
            "ram_formula": (
                "(raw_eeg + metadata + persistent_label_payloads + "
                "persistent_scan_metadata + max_sequential_parser_transient + "
                "preprocessing_intermediate + epoch_cache) * safety_margin"
            ),
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
            logger.debug("System RAM detail query failed", exc_info=True)
        if total is not None and used is None and available is not None:
            used = max(total - available, 0)
        return {
            "total_bytes": total,
            "available_bytes": available,
            "used_bytes": used,
        }

    @staticmethod
    def check_dataset_load_safe(paths: Iterable[str]) -> ResourceCheckResult:
        """Return whether selected EEG and label payloads are safe to import."""
        estimate = ResourceChecker.estimate_dataset_ram(paths)
        ram = ResourceChecker.get_system_ram_status()
        unbounded = estimate.get("unbounded_eeg_files")
        if isinstance(unbounded, list) and unbounded:
            first = unbounded[0] if isinstance(unbounded[0], dict) else {}
            path = str(first.get("path") or "the selected .set file")
            reason = str(first.get("reason") or "").strip()
            message = (
                "EEGLAB .set signal memory could not be bounded safely before "
                f"loading: {path}."
            )
            if reason:
                message = f"{message} {reason}"
            return ResourceCheckResult(
                required_memory_bytes=None,
                available_memory_bytes=ram.get("available_bytes"),
                total_memory_bytes=ram.get("total_bytes"),
                used_memory_bytes=ram.get("used_bytes"),
                risk_level=RISK_BLOCKING,
                message=message,
                suggestions=(
                    "resave the EEGLAB dataset with a readable data header",
                    "use an external .fdt file referenced by the SET header",
                    "choose a smaller or verified source file",
                ),
                details={
                    **estimate,
                    "estimate_status": RISK_UNKNOWN,
                    "risk_level": RISK_BLOCKING,
                },
            )
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
        try:
            torch_module = _torch_module()
        except Exception as exc:
            return _unknown_gpu_vram_status(
                gpu_idx,
                reason="torch_unavailable",
                query_error_type=type(exc).__name__,
            )
        try:
            cuda_available = bool(torch_module.cuda.is_available())
        except Exception as exc:
            return _unknown_gpu_vram_status(
                gpu_idx,
                reason="cuda_availability_query_failed",
                query_error_type=type(exc).__name__,
            )
        if not cuda_available:
            return _unknown_gpu_vram_status(
                gpu_idx,
                reason="cuda_not_available",
            )
        try:
            device_index = 0 if gpu_idx is None else int(gpu_idx)
        except (TypeError, ValueError):
            return _unknown_gpu_vram_status(
                gpu_idx,
                reason="invalid_gpu_index",
            )
        try:
            device_count = int(torch_module.cuda.device_count())
        except Exception as exc:
            return _unknown_gpu_vram_status(
                device_index,
                reason="gpu_device_query_failed",
                query_error_type=type(exc).__name__,
            )
        if device_index < 0 or device_index >= device_count:
            return _unknown_gpu_vram_status(
                device_index,
                reason="invalid_gpu_index",
                device_count=device_count,
            )

        try:
            available, total = torch_module.cuda.mem_get_info(device_index)
            available = int(available)
            total = int(total)
        except Exception as exc:
            return _unknown_gpu_vram_status(
                device_index,
                reason="gpu_memory_query_failed",
                device_count=device_count,
                query_error_type=type(exc).__name__,
                torch_module=torch_module,
            )
        allocated = None
        reserved = None
        gpu_name = None
        try:
            allocated = int(torch_module.cuda.memory_allocated(device_index))
            reserved = int(torch_module.cuda.memory_reserved(device_index))
        except Exception:
            logger.debug(
                "CUDA allocated/reserved memory query failed for device %s",
                device_index,
                exc_info=True,
            )
        try:
            gpu_name = str(torch_module.cuda.get_device_name(device_index))
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
            "gpu_index": device_index,
            "device_count": device_count,
            "reason": None,
            "query_error_type": None,
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
            reason = str(vram.get("reason") or "gpu_memory_unavailable")
            return ResourceCheckResult(
                required_memory_bytes=estimate["estimated_vram_bytes"],
                available_memory_bytes=None,
                total_memory_bytes=vram.get("total_bytes"),
                used_memory_bytes=vram.get("used_bytes"),
                risk_level=RISK_UNKNOWN,
                message=_gpu_memory_unavailable_message(reason, gpu_idx),
                suggestions=TRAINING_VRAM_SUGGESTIONS,
                details={**estimate, **vram, "uses_cpu": False, "gpu_index": gpu_idx},
            )
        result = _memory_check_result(
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
        if not estimate["model_parameter_estimate_reliable"] and not result.blocking:
            details = dict(result.details)
            details["reason"] = "model_parameter_estimate_unavailable"
            return ResourceCheckResult(
                required_memory_bytes=result.required_memory_bytes,
                available_memory_bytes=result.available_memory_bytes,
                total_memory_bytes=result.total_memory_bytes,
                used_memory_bytes=result.used_memory_bytes,
                risk_level=RISK_UNKNOWN,
                message=(
                    "Unable to verify GPU memory because the selected model could "
                    "not be instantiated for estimation."
                ),
                suggestions=TRAINING_VRAM_SUGGESTIONS,
                details=details,
            )
        return result

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
    dataset_list = list(datasets or [])
    dataset_result = _training_dataset_ram_check(
        dataset_list,
        training_option,
        model_holder,
    )
    vram_result = ResourceChecker.check_training_config_safe(
        dataset_list,
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
    unknowns = []
    for result in (dataset_result, vram_result):
        if result.blocking:
            issues.append(result.message)
        elif result.warning:
            warnings.append(result.message)
        elif result.risk_level == RISK_UNKNOWN:
            unknowns.append(result.message)
    return ResourcePreflightResult(
        tuple(issues),
        diagnostics,
        tuple(warnings),
        tuple(unknowns),
    )


def check_import_resource_preflight(paths: Iterable[str]) -> ResourcePreflightResult:
    """Return resource issues before loading EEG or label payloads into memory."""
    result = ResourceChecker.check_dataset_load_safe(paths)
    diagnostics = result.to_diagnostics()
    diagnostics.update(
        {
            "path_count": result.details.get("path_count", 0),
            "file_bytes": result.details.get("file_bytes", 0),
            "estimated_ram_working_set_bytes": result.required_memory_bytes,
            "available_ram_bytes": result.available_memory_bytes,
        }
    )
    issues = (result.message,) if result.blocking else ()
    warnings = (result.message,) if result.warning else ()
    unknowns = (result.message,) if result.risk_level == RISK_UNKNOWN else ()
    return ResourcePreflightResult(issues, diagnostics, warnings, unknowns)


def _resource_risk_levels(diagnostics: dict[str, Any]) -> set[ResourceRiskLevel]:
    """Read aggregate/component risk values from compatibility diagnostics."""
    values = {
        diagnostics.get("risk_level"),
        diagnostics.get("dataset_ram_risk_level"),
        diagnostics.get("vram_risk_level"),
    }
    known_levels = {risk_level.value: risk_level for risk_level in ResourceRiskLevel}
    levels: set[ResourceRiskLevel] = set()
    for value in values:
        risk_level = known_levels.get(str(value))
        if risk_level is not None:
            levels.add(risk_level)
    return levels


def estimate_training_resources(
    datasets: Iterable[Any],
    option: Any,
    *,
    model_holder: Any | None = None,
) -> dict[str, Any]:
    """Estimate CPU and GPU working-set sizes for selected training datasets."""
    dataset_list = list(datasets or [])
    dataset_bytes = 0
    peak_input_batch_bytes = 0
    peak_validation_batch_bytes = 0
    peak_batch_samples = 0
    seen_epoch_data: set[int] = set()
    batch_size = max(_positive_int(getattr(option, "bs", None), default=1), 1)
    repeat_count = max(
        _positive_int(getattr(option, "repeat_num", None), default=1),
        1,
    )
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
        class_count = max(class_count, _epoch_class_count(epoch_data, labels))
        per_sample_gpu_bytes = _per_sample_tensor_bytes(data)
        train_count = _mask_count(getattr(dataset, "train_mask", None), n_samples)
        val_count = max(
            _mask_count(getattr(dataset, "val_mask", None), n_samples),
            _mask_count(getattr(dataset, "test_mask", None), n_samples),
        )
        train_batch_samples = min(batch_size, max(train_count, 1))
        validation_batch_samples = min(batch_size, max(val_count, 1))
        peak_input_batch_bytes = max(
            peak_input_batch_bytes,
            per_sample_gpu_bytes * train_batch_samples,
        )
        peak_validation_batch_bytes = max(
            peak_validation_batch_bytes,
            per_sample_gpu_bytes * validation_batch_samples,
        )
        peak_batch_samples = max(
            peak_batch_samples,
            train_batch_samples,
            validation_batch_samples,
        )

    model_estimate = _estimate_model_parameter_memory(
        model_holder,
        dataset_list,
    )
    model_parameter_bytes = model_estimate.bytes
    gradient_bytes = model_parameter_bytes
    optimizer_state_multiplier = _optimizer_state_multiplier(option)
    optimizer_state_bytes = int(model_parameter_bytes * optimizer_state_multiplier)
    # Final evaluation creates a second model while the archived training model
    # and optimizer still exist. Folds and repeats themselves execute serially.
    evaluation_model_bytes = model_parameter_bytes
    peak_batch_bytes = max(peak_input_batch_bytes, peak_validation_batch_bytes)
    activation_factor = _activation_factor(model_holder)
    activation_bytes = int(peak_batch_bytes * activation_factor)
    logits_bytes = int(
        peak_batch_samples * class_count * TRAINING_INPUT_DTYPE_BYTES * 3
    )
    estimated_gpu_before_margin = int(
        model_parameter_bytes
        + gradient_bytes
        + optimizer_state_bytes
        + evaluation_model_bytes
        + peak_batch_bytes
        + activation_bytes
        + logits_bytes
        + TRAINING_RUNTIME_WORKSPACE_BYTES
    )
    estimated_gpu = int(estimated_gpu_before_margin * VRAM_SAFETY_MARGIN)
    fold_count = len(dataset_list)
    training_record_count = fold_count * repeat_count
    dataset_ram_working_set_bytes = int(
        dataset_bytes * TRAINING_RAM_WORKING_SET_MULTIPLIER
    )
    retained_model_bytes = model_parameter_bytes * training_record_count
    retained_gradient_bytes = (
        model_parameter_bytes
        * TRAINING_RETAINED_GRADIENT_COPIES
        * training_record_count
    )
    retained_optimizer_state_bytes = optimizer_state_bytes * training_record_count
    retained_checkpoint_bytes = (
        model_parameter_bytes * TRAINING_BEST_CHECKPOINT_COPIES * training_record_count
    )
    retained_training_record_bytes = int(
        retained_model_bytes
        + retained_gradient_bytes
        + retained_optimizer_state_bytes
        + retained_checkpoint_bytes
    )
    estimated_ram_before_margin = int(
        dataset_ram_working_set_bytes + retained_training_record_bytes
    )
    estimated_ram = int(estimated_ram_before_margin * TRAINING_RAM_SAFETY_MARGIN)
    return {
        "dataset_count": len(dataset_list),
        "fold_count": fold_count,
        "repeat_count": repeat_count,
        "training_record_count": training_record_count,
        "folds_repeats_concurrent": False,
        "peak_execution_scope": "one_fold_one_repeat_one_batch",
        "dataset_bytes": int(dataset_bytes),
        "dataset_ram_working_set_bytes": dataset_ram_working_set_bytes,
        "retained_model_bytes": int(retained_model_bytes),
        "retained_gradient_bytes": int(retained_gradient_bytes),
        "retained_optimizer_state_bytes": int(retained_optimizer_state_bytes),
        "retained_checkpoint_bytes": int(retained_checkpoint_bytes),
        "retained_training_record_bytes": retained_training_record_bytes,
        "training_best_checkpoint_copies": TRAINING_BEST_CHECKPOINT_COPIES,
        "training_retained_gradient_copies": TRAINING_RETAINED_GRADIENT_COPIES,
        "estimated_ram_before_margin_bytes": estimated_ram_before_margin,
        "estimated_ram_working_set_bytes": estimated_ram,
        "training_ram_safety_margin": TRAINING_RAM_SAFETY_MARGIN,
        "ram_formula": (
            "(dataset_working_set + fold_repeat_records * "
            "(model + gradient + optimizer_states + best_checkpoints)) * "
            "safety_margin"
        ),
        "peak_input_batch_bytes": int(peak_input_batch_bytes),
        "peak_validation_batch_bytes": int(peak_validation_batch_bytes),
        "peak_batch_bytes": int(peak_batch_bytes),
        "peak_batch_samples": int(peak_batch_samples),
        "model_parameter_bytes": int(model_parameter_bytes),
        "model_parameter_estimate_source": model_estimate.source,
        "model_parameter_estimate_reliable": model_estimate.reliable,
        "model_parameter_estimate_error": model_estimate.error_type,
        "gradient_bytes": int(gradient_bytes),
        "optimizer_state_bytes": int(optimizer_state_bytes),
        "optimizer_state_multiplier": float(optimizer_state_multiplier),
        "evaluation_model_bytes": int(evaluation_model_bytes),
        "activation_bytes": int(activation_bytes),
        "activation_factor": float(activation_factor),
        "logits_bytes": int(logits_bytes),
        "runtime_workspace_bytes": TRAINING_RUNTIME_WORKSPACE_BYTES,
        "class_count": int(class_count),
        "batch_size": int(batch_size),
        "training_dtype": "float32",
        "training_dtype_bytes": TRAINING_INPUT_DTYPE_BYTES,
        "mixed_precision_applied": False,
        "estimated_gpu_before_margin_bytes": estimated_gpu_before_margin,
        "estimated_gpu_batch_working_set_bytes": estimated_gpu,
        "vram_safety_margin": VRAM_SAFETY_MARGIN,
        "vram_formula": (
            "(parameters + gradients + optimizer_states + evaluation_model + "
            "peak_batch + activations + logits + runtime_workspace) * "
            "safety_margin"
        ),
    }


def available_ram_bytes() -> int | None:
    """Return available system RAM when the platform exposes it."""
    try:
        psutil = import_module("psutil")
        return int(psutil.virtual_memory().available)
    except Exception:
        logger.debug("psutil available-RAM query failed", exc_info=True)

    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        available_pages = os.sysconf("SC_AVPHYS_PAGES")
        return int(page_size * available_pages)
    except (AttributeError, OSError, ValueError):
        return None


def available_vram_bytes(gpu_idx: int | None = None) -> int | None:
    """Return free CUDA memory for the selected device, if CUDA is available."""
    try:
        torch_module = _torch_module()
        if not torch_module.cuda.is_available():
            return None
        device_index = 0 if gpu_idx is None else int(gpu_idx)
        free_bytes, _total = torch_module.cuda.mem_get_info(device_index)
        return int(free_bytes)
    except Exception:
        return None


def is_cuda_oom_error(exc: BaseException) -> bool:
    """Return whether an exception represents CUDA memory exhaustion."""
    return _is_cuda_oom_error(exc)


def release_cuda_cache() -> None:
    """Release cached CUDA memory when CUDA is available."""
    _release_cuda_cache(_torch_module())


def _training_dataset_ram_check(
    datasets: Iterable[Any],
    training_option: Any,
    model_holder: Any | None,
) -> ResourceCheckResult:
    estimate = estimate_training_resources(
        datasets,
        training_option,
        model_holder=model_holder,
    )
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
    result_details = {
        **dict(details),
        "warning_ratio": float(warning_ratio),
        "blocking_ratio": float(blocking_ratio),
        "required_to_available_ratio": (
            None
            if required is None or not available_memory_bytes
            else float(required / available_memory_bytes)
        ),
    }
    if required is None or available_memory_bytes is None:
        return ResourceCheckResult(
            required_memory_bytes=required,
            available_memory_bytes=available_memory_bytes,
            total_memory_bytes=total_memory_bytes,
            used_memory_bytes=used_memory_bytes,
            risk_level=RISK_UNKNOWN,
            message=f"Unable to estimate available {resource_name}.",
            suggestions=suggestions,
            details=result_details,
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
        details=result_details,
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


def _estimate_eeg_file_from_header(
    path: str,
    *,
    eeglab_inspection: EeglabSetHeaderInspection | None = None,
) -> dict[str, Any] | None:
    file_path = Path(path)
    if not file_path.is_file():
        return None
    suffix = _normalized_suffix(file_path)
    if suffix == ".set":
        return _estimate_eeglab_set_without_materializing_data(
            file_path,
            inspection=eeglab_inspection,
        )
    reader_name = {
        ".bdf": "read_raw_bdf",
        ".cnt": "read_raw_cnt",
        ".edf": "read_raw_edf",
        ".fif": "read_raw_fif",
        ".fif.gz": "read_raw_fif",
        ".gdf": "read_raw_gdf",
        ".vhdr": "read_raw_brainvision",
    }.get(suffix)
    if reader_name is None:
        return None
    raw: Any | None = None
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
    finally:
        if raw is not None:
            with suppress(Exception):
                close = getattr(raw, "close", None)
                if callable(close):
                    close()


def _estimate_eeglab_set_without_materializing_data(
    file_path: Path,
    *,
    inspection: EeglabSetHeaderInspection | None = None,
) -> dict[str, Any]:
    """Estimate EEGLAB RAM from bounded MAT metadata, never signal payloads."""
    inspection = inspection or inspect_eeglab_set_header(file_path)
    set_file_bytes = _path_size(str(file_path))
    shape = inspection.source_shape
    sample_count = int(math.prod(shape)) if shape else 0
    if inspection.storage_mode == "external" and inspection.external_data_file_bytes:
        raw_bytes = int(
            inspection.external_data_file_bytes * EEGLAB_FDT_TO_FLOAT64_MULTIPLIER
        )
        estimate_source = "eeglab_mat_header_external_fdt"
    elif inspection.storage_mode == "embedded" and sample_count:
        raw_bytes = int(sample_count * RAW_IMPORT_DTYPE_BYTES)
        estimate_source = "eeglab_mat_header_embedded"
    else:
        raw_bytes = 0
        estimate_source = "eeglab_header_unknown"
    return {
        "path": str(file_path),
        "estimate_source": estimate_source,
        "estimate_reason": inspection.reason,
        "reason_code": inspection.reason_code,
        "size_bound_known": inspection.bound_known,
        "storage_mode": inspection.storage_mode,
        "materializes_signal_data": False,
        "file_bytes": set_file_bytes,
        "associated_data_file": inspection.external_data_file,
        "associated_data_file_bytes": inspection.external_data_file_bytes or 0,
        "data_reference": inspection.data_reference,
        "channels": inspection.channels,
        "time_samples": inspection.time_samples,
        "trials": inspection.trials,
        "sampling_rate_hz": inspection.sampling_rate_hz,
        "source_shape": list(shape) if shape is not None else None,
        "source_dtype": inspection.source_dtype,
        "dtype_size_bytes": RAW_IMPORT_DTYPE_BYTES,
        "estimated_raw_bytes": raw_bytes,
        "raw_bytes": raw_bytes,
        "annotations_bytes": 0,
        "mat_format": inspection.mat_format,
        "compressed_header": inspection.compressed_header,
        "header_bytes_read": inspection.header_bytes_read,
        "decoded_header_bytes": inspection.decoded_header_bytes,
        "compressed_header_budget_bytes": (
            MAT_COMPRESSED_HEADER_BUDGET_BYTES if inspection.compressed_header else 0
        ),
    }


def _normalized_suffix(path: Path) -> str:
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if len(suffixes) >= 2 and suffixes[-2:] == [".fif", ".gz"]:
        return ".fif.gz"
    return path.suffix.lower()


def _is_scan_metadata_path(path: Path) -> bool:
    return (
        is_bids_metadata_table(path)
        or path.name == "dataset_description.json"
        or is_bids_events_json_sidecar(path)
    )


def _unknown_gpu_vram_status(
    gpu_idx: Any,
    *,
    reason: str,
    device_count: int | None = None,
    query_error_type: str | None = None,
    torch_module: Any | None = None,
) -> dict[str, Any]:
    """Build one complete unknown-GPU diagnostic without hiding the cause."""
    try:
        device_index = 0 if gpu_idx is None else int(gpu_idx)
    except (TypeError, ValueError):
        device_index = None
    gpu_name = None
    allocated = None
    reserved = None
    if torch_module is not None and device_index is not None:
        with suppress(Exception):
            gpu_name = str(torch_module.cuda.get_device_name(device_index))
        with suppress(Exception):
            allocated = int(torch_module.cuda.memory_allocated(device_index))
            reserved = int(torch_module.cuda.memory_reserved(device_index))
    return {
        "gpu_name": gpu_name,
        "available_bytes": None,
        "total_bytes": None,
        "used_bytes": None,
        "allocated_bytes": allocated,
        "reserved_bytes": reserved,
        "gpu_index": device_index,
        "device_count": device_count,
        "reason": reason,
        "query_error_type": query_error_type,
    }


def _gpu_memory_unavailable_message(reason: str, gpu_idx: int | None) -> str:
    if reason == "cuda_not_available":
        return "Unable to estimate GPU memory because CUDA is not available."
    if reason == "invalid_gpu_index":
        return f"Unable to estimate GPU memory because GPU index {gpu_idx} is invalid."
    if reason == "torch_unavailable":
        return "Unable to estimate GPU memory because PyTorch is unavailable."
    if reason == "gpu_device_query_failed":
        return (
            "Unable to estimate GPU memory because CUDA devices could not be queried."
        )
    if reason == "cuda_availability_query_failed":
        return "Unable to estimate GPU memory because CUDA status could not be queried."
    return "Unable to estimate GPU memory because free VRAM could not be queried."


def _torch_module() -> Any:
    return import_module("torch")


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


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve(strict=False)))


def _deduplicated_resource_paths(paths: Iterable[str]) -> list[str]:
    """Return stable unique resource paths without opening their contents."""
    result: list[str] = []
    seen: set[str] = set()
    for raw_path in paths:
        text = str(raw_path).strip()
        if not text:
            continue
        path = Path(text).expanduser()
        normalized = os.path.normcase(str(path.resolve(strict=False)))
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(str(path))
    return result


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
    shape = getattr(labels, "shape", None)
    if shape and len(shape) > 1:
        try:
            return max(int(shape[-1]), 1)
        except (TypeError, ValueError, IndexError):
            pass
    try:
        unique = set(islice(iter(labels), CLASS_COUNT_SCAN_LIMIT))
        return max(len(unique), 1)
    except Exception:
        logger.debug("Label class-count scan failed", exc_info=True)
    return 1


def _epoch_class_count(epoch_data: Any, labels: Any) -> int:
    reported = _safe_call(epoch_data, "get_label_number")
    try:
        if int(reported) > 0:
            return int(reported)
    except (TypeError, ValueError):
        pass
    label_map = getattr(epoch_data, "label_map", None)
    if label_map is not None:
        try:
            if len(label_map) > 0:
                return len(label_map)
        except (TypeError, ValueError):
            pass
    return _class_count(labels)


def _estimate_model_parameter_memory(
    model_holder: Any | None,
    datasets: list[Any],
) -> _ModelParameterMemoryEstimate:
    if model_holder is None:
        return _ModelParameterMemoryEstimate(
            bytes=MODEL_PARAMETER_FALLBACK_BYTES,
            source="unavailable",
            reliable=False,
        )
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
        return _ModelParameterMemoryEstimate(
            bytes=max(total, 0),
            source="instantiated",
            reliable=True,
        )
    except Exception as exc:
        return _ModelParameterMemoryEstimate(
            bytes=MODEL_PARAMETER_FALLBACK_BYTES,
            source="fallback",
            reliable=False,
            error_type=type(exc).__name__,
        )


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
