"""Shape- and device-aware resource admission for saliency recomputation."""

from __future__ import annotations

import math
import operator
import time
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass
from threading import RLock
from typing import Any, cast

from XBrainLab.backend.utils.logger import logger

from .commands import CommandName, SaliencyCommand
from .resource_guard import (
    DEFAULT_ACTIVATION_FACTOR,
    MODEL_ACTIVATION_FACTORS,
    RAM_BLOCKING_RATIO,
    RAM_SAFETY_MARGIN,
    RAM_WARNING_RATIO,
    RISK_BLOCKING,
    RISK_SAFE,
    RISK_UNKNOWN,
    RISK_WARNING,
    TRAINING_INPUT_DTYPE_BYTES,
    TRAINING_RUNTIME_WORKSPACE_BYTES,
    VRAM_BLOCKING_RATIO,
    VRAM_SAFETY_MARGIN,
    VRAM_WARNING_RATIO,
    ResourceChecker,
    ResourceCheckResult,
    ResourceConfirmationRequiredError,
    ResourcePreflightResult,
    enforce_resource_preflight,
)
from .resource_receipt import (
    DEFAULT_RESOURCE_RECEIPT_LIMIT,
    DEFAULT_RESOURCE_RECEIPT_TTL_SECONDS,
    ResourceReceiptAuthority,
    ResourceReceiptRecord,
    fingerprint_resource_preflight,
    fingerprint_resource_scope,
)
from .saliency_policy import (
    ADVANCED_SALIENCY_METHODS,
    selected_saliency_methods_from_params,
)

SALIENCY_RUNTIME_WORKSPACE_BYTES = TRAINING_RUNTIME_WORKSPACE_BYTES
SALIENCY_ATTRIBUTION_DTYPE_BYTES = TRAINING_INPUT_DTYPE_BYTES
SALIENCY_RESULT_PEAK_COPIES = 2
SALIENCY_BASE_TENSOR_COPIES = 2
SALIENCY_NOISE_TENSOR_COPIES = 6
SALIENCY_RAM_SAFETY_MARGIN = RAM_SAFETY_MARGIN
SALIENCY_VRAM_SAFETY_MARGIN = VRAM_SAFETY_MARGIN
SALIENCY_PREFLIGHT_RECEIPT_TTL_SECONDS = DEFAULT_RESOURCE_RECEIPT_TTL_SECONDS
SALIENCY_PREFLIGHT_RECEIPT_LIMIT = DEFAULT_RESOURCE_RECEIPT_LIMIT

SALIENCY_MEMORY_SUGGESTIONS = (
    "reduce noise samples",
    "set a smaller samples-per-batch value",
    "select fewer saliency methods",
    "reduce the training batch size",
    "shorten the epoch window or reduce channels",
    "close other memory-intensive applications",
)


@dataclass(frozen=True, slots=True)
class _ModelMemoryEstimate:
    bytes: int
    source: str


_SaliencyPreflightReceipt = ResourceReceiptRecord[ResourcePreflightResult]


class SaliencyResourceAdmission:
    """Authorize one exact saliency recomputation before evaluator mutation."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._authority = ResourceReceiptAuthority[ResourcePreflightResult](
            command_name=CommandName.SALIENCY.value,
            ttl_seconds=SALIENCY_PREFLIGHT_RECEIPT_TTL_SECONDS,
            max_receipts=SALIENCY_PREFLIGHT_RECEIPT_LIMIT,
            clock=clock or time.monotonic,
        )
        self._lock = RLock()

    def authorize(
        self,
        command: SaliencyCommand,
        params: dict[str, Any],
        preflight: ResourcePreflightResult,
    ) -> ResourcePreflightResult:
        """Consume a matching receipt or raise a backend-issued challenge."""
        annotated = self._annotate(command, params, preflight)
        token = command.resource_preflight_token
        with self._lock:
            if annotated.blocking:
                self._authority.discard(token)
                enforce_resource_preflight(annotated, confirmed=False)

            if not annotated.requires_confirmation:
                self._authority.discard(token)
                enforce_resource_preflight(annotated, confirmed=False)
                return _with_diagnostics(
                    annotated,
                    confirmation_receipt_reused=False,
                )

            receipt = self._matching(token, annotated)
            if receipt is not None:
                if not command.resource_preflight_confirmed:
                    raise self._confirmation_error(receipt)
                enforce_resource_preflight(annotated, confirmed=True)
                consumed = self._authority.consume(
                    receipt.challenge.challenge_id,
                    scope_fingerprint=receipt.challenge.scope_fingerprint,
                    configuration_fingerprint=(
                        receipt.challenge.configuration_fingerprint
                    ),
                    preflight_fingerprint=receipt.challenge.preflight_fingerprint,
                )
                if consumed is None:
                    raise self._confirmation_error(self._issue(annotated))
                return _with_diagnostics(
                    annotated,
                    confirmation_receipt_reused=True,
                )

            if token:
                self._authority.discard(token)
            receipt = None
            if not command.resource_preflight_confirmed:
                receipt = self._pending(annotated)
            raise self._confirmation_error(receipt or self._issue(annotated))

    @staticmethod
    def _annotate(
        command: SaliencyCommand,
        params: dict[str, Any],
        preflight: ResourcePreflightResult,
    ) -> ResourcePreflightResult:
        target = command.target
        target_serializer = getattr(target, "to_dict", None)
        target_payload = target_serializer() if callable(target_serializer) else None
        raw_members = getattr(target, "members", None)
        target_member_count = (
            len(raw_members)
            if isinstance(raw_members, tuple)
            else 1
            if target is not None
            else None
        )
        configuration_fingerprint = fingerprint_resource_scope(
            {
                "command": CommandName.SALIENCY.value,
                "params": params,
                "target": target_payload,
            }
        )
        preflight_fingerprint = fingerprint_resource_preflight(
            {
                "risk_level": preflight.risk_level.value,
                "issues": preflight.issues,
                "warnings": preflight.warnings,
                "unknowns": preflight.unknowns,
                "diagnostics": _without_live_memory_ratio(preflight.diagnostics),
            }
        )
        scope_fingerprint = fingerprint_resource_scope(
            {
                "command": CommandName.SALIENCY.value,
                "configuration_fingerprint": configuration_fingerprint,
                "preflight_fingerprint": preflight_fingerprint,
            }
        )
        return _with_diagnostics(
            preflight,
            payload_type="saliency_resource_preflight",
            target_member_count=target_member_count,
            configuration_fingerprint=configuration_fingerprint,
            preflight_fingerprint=preflight_fingerprint,
            scope_fingerprint=scope_fingerprint,
        )

    def _matching(
        self,
        token: str | None,
        preflight: ResourcePreflightResult,
    ) -> _SaliencyPreflightReceipt | None:
        diagnostics = preflight.diagnostics
        return self._authority.peek(
            token,
            scope_fingerprint=str(diagnostics["scope_fingerprint"]),
            configuration_fingerprint=str(diagnostics["configuration_fingerprint"]),
            preflight_fingerprint=str(diagnostics["preflight_fingerprint"]),
        )

    def _pending(
        self,
        preflight: ResourcePreflightResult,
    ) -> _SaliencyPreflightReceipt | None:
        diagnostics = preflight.diagnostics
        return self._authority.pending(
            scope_fingerprint=str(diagnostics["scope_fingerprint"]),
            configuration_fingerprint=str(diagnostics["configuration_fingerprint"]),
            preflight_fingerprint=str(diagnostics["preflight_fingerprint"]),
        )

    def _issue(
        self,
        preflight: ResourcePreflightResult,
    ) -> _SaliencyPreflightReceipt:
        diagnostics = preflight.diagnostics
        challenge = self._authority.issue(
            scope_fingerprint=str(diagnostics["scope_fingerprint"]),
            payload=preflight,
            configuration_fingerprint=str(diagnostics["configuration_fingerprint"]),
            preflight_fingerprint=str(diagnostics["preflight_fingerprint"]),
        )
        receipt = self._authority.peek(
            challenge.challenge_id,
            scope_fingerprint=challenge.scope_fingerprint,
            configuration_fingerprint=challenge.configuration_fingerprint,
            preflight_fingerprint=challenge.preflight_fingerprint,
        )
        if receipt is None:  # pragma: no cover - issue and lookup share one lock
            raise RuntimeError("Issued saliency resource challenge was not stored.")
        return receipt

    @staticmethod
    def _confirmation_error(
        receipt: _SaliencyPreflightReceipt,
    ) -> ResourceConfirmationRequiredError:
        return ResourceConfirmationRequiredError(
            receipt.payload,
            challenge=receipt.challenge,
        )


def estimate_saliency_resources(
    datasets: Iterable[Any],
    training_option: Any,
    model_holder: Any,
    saliency_params: dict[str, Any],
    *,
    training_plan_holders: Iterable[Any] = (),
) -> dict[str, Any]:
    """Estimate incremental saliency RAM and device working sets."""
    dataset_list = list(datasets or [])
    if not dataset_list:
        raise ValueError(
            "Saliency resource admission requires a generated training dataset."
        )
    if training_option is None:
        raise ValueError(
            "Saliency resource admission requires saved training settings."
        )

    selected_methods = sorted(selected_saliency_methods_from_params(saliency_params))
    if not selected_methods:
        raise ValueError(
            "Saliency resource admission requires at least one selected method."
        )
    batch_size = _positive_int(
        getattr(training_option, "bs", None),
        field="training batch size",
    )
    repeat_count = _positive_int(
        getattr(training_option, "repeat_num", 1),
        field="training repeat count",
    )
    if not hasattr(training_option, "use_cpu"):
        raise ValueError(
            "Saliency resource admission could not determine the selected device."
        )
    uses_cpu = bool(training_option.use_cpu)
    model_estimate = _estimate_model_memory(
        model_holder,
        dataset_list,
        training_plan_holders,
    )

    noise_details, peak_noise_partition = _noise_partition_details(
        selected_methods,
        saliency_params,
    )
    dataset_details: list[dict[str, Any]] = []
    total_evaluation_input_bytes = 0
    peak_evaluation_input_bytes = 0
    peak_record_attribution_bytes = 0
    method_count = len(selected_methods)
    for index, dataset in enumerate(dataset_list):
        epoch_data = _call(dataset, "get_epoch_data")
        data = _call(epoch_data, "get_data") if epoch_data is not None else None
        if data is None and epoch_data is not None:
            data = getattr(epoch_data, "data", None)
        shape = _epoch_shape(data, dataset_index=index)
        epoch_count, channel_count, sample_count = shape
        evaluation_split, evaluation_count = _evaluation_count(
            dataset,
            epoch_count=epoch_count,
            dataset_index=index,
        )
        per_epoch_bytes = (
            channel_count * sample_count * SALIENCY_ATTRIBUTION_DTYPE_BYTES
        )
        evaluation_input_bytes = evaluation_count * per_epoch_bytes
        evaluation_batch_size = min(batch_size, evaluation_count)
        evaluation_batch_bytes = evaluation_batch_size * per_epoch_bytes
        record_attribution_bytes = evaluation_input_bytes * method_count
        total_evaluation_input_bytes += evaluation_input_bytes
        peak_evaluation_input_bytes = max(
            peak_evaluation_input_bytes,
            evaluation_batch_bytes,
        )
        peak_record_attribution_bytes = max(
            peak_record_attribution_bytes,
            record_attribution_bytes,
        )
        dataset_details.append(
            {
                "dataset_index": index,
                "epoch_shape": list(shape),
                "evaluation_split": evaluation_split,
                "evaluation_epoch_count": evaluation_count,
                "evaluation_batch_size": evaluation_batch_size,
                "per_epoch_bytes": per_epoch_bytes,
                "evaluation_input_bytes": evaluation_input_bytes,
                "record_attribution_bytes": record_attribution_bytes,
            }
        )

    retained_attribution_bytes = (
        total_evaluation_input_bytes * method_count * repeat_count
    )
    concatenation_peak_bytes = (
        peak_record_attribution_bytes * SALIENCY_RESULT_PEAK_COPIES
    )
    expanded_batch_bytes = peak_evaluation_input_bytes * peak_noise_partition
    tensor_copy_count = (
        SALIENCY_NOISE_TENSOR_COPIES if noise_details else SALIENCY_BASE_TENSOR_COPIES
    )
    tensor_workspace_bytes = expanded_batch_bytes * tensor_copy_count
    activation_factor = _activation_factor(model_holder)
    activation_bytes = int(expanded_batch_bytes * activation_factor)
    device_before_margin_bytes = int(
        model_estimate.bytes
        + tensor_workspace_bytes
        + activation_bytes
        + SALIENCY_RUNTIME_WORKSPACE_BYTES
    )
    host_transfer_peak_bytes = peak_evaluation_input_bytes * 2
    ram_before_margin_bytes = int(
        retained_attribution_bytes
        + concatenation_peak_bytes
        + host_transfer_peak_bytes
        + (
            device_before_margin_bytes
            if uses_cpu
            else model_estimate.bytes + SALIENCY_RUNTIME_WORKSPACE_BYTES
        )
    )
    estimated_ram_bytes = math.ceil(
        ram_before_margin_bytes * SALIENCY_RAM_SAFETY_MARGIN
    )
    estimated_vram_bytes = (
        0
        if uses_cpu
        else math.ceil(device_before_margin_bytes * SALIENCY_VRAM_SAFETY_MARGIN)
    )
    return {
        "operation": "saliency_recomputation",
        "dataset_count": len(dataset_list),
        "datasets": dataset_details,
        "selected_methods": selected_methods,
        "method_count": method_count,
        "noise_methods": sorted(noise_details),
        "noise_parameters": noise_details,
        "training_batch_size": batch_size,
        "repeat_count": repeat_count,
        "uses_cpu": uses_cpu,
        "gpu_index": None if uses_cpu else _gpu_index(training_option),
        "attribution_dtype": "float32",
        "attribution_dtype_bytes": SALIENCY_ATTRIBUTION_DTYPE_BYTES,
        "peak_noise_partition": peak_noise_partition,
        "peak_evaluation_input_bytes": peak_evaluation_input_bytes,
        "expanded_batch_bytes": expanded_batch_bytes,
        "tensor_copy_count": tensor_copy_count,
        "tensor_workspace_bytes": tensor_workspace_bytes,
        "activation_factor": activation_factor,
        "activation_bytes": activation_bytes,
        "model_parameter_bytes": model_estimate.bytes,
        "model_parameter_estimate_source": model_estimate.source,
        "retained_attribution_bytes": retained_attribution_bytes,
        "concatenation_peak_bytes": concatenation_peak_bytes,
        "host_transfer_peak_bytes": host_transfer_peak_bytes,
        "runtime_workspace_bytes": SALIENCY_RUNTIME_WORKSPACE_BYTES,
        "estimated_ram_before_margin_bytes": ram_before_margin_bytes,
        "estimated_ram_working_set_bytes": estimated_ram_bytes,
        "estimated_vram_before_margin_bytes": (
            0 if uses_cpu else device_before_margin_bytes
        ),
        "estimated_vram_working_set_bytes": estimated_vram_bytes,
        "ram_safety_margin": SALIENCY_RAM_SAFETY_MARGIN,
        "vram_safety_margin": SALIENCY_VRAM_SAFETY_MARGIN,
        "ram_formula": (
            "(retained_attributions + concatenate_peak + host_transfer + "
            "cpu_device_working_set_or_gpu_host_model_workspace) * safety_margin"
        ),
        "device_formula": (
            "(model + expanded_batch * tensor_copies + expanded_batch * "
            "activation_factor + runtime_workspace) * safety_margin"
        ),
    }


def check_saliency_resource_preflight(
    datasets: Iterable[Any],
    training_option: Any,
    model_holder: Any,
    saliency_params: dict[str, Any],
    *,
    training_plan_holders: Iterable[Any] = (),
) -> ResourcePreflightResult:
    """Reject saliency requests that cannot fit current RAM or selected VRAM."""
    try:
        estimate = estimate_saliency_resources(
            datasets,
            training_option,
            model_holder,
            saliency_params,
            training_plan_holders=training_plan_holders,
        )
    except ValueError as exc:
        message = str(exc)
        return ResourcePreflightResult(
            issues=(message,),
            diagnostics={
                "operation": "saliency_recomputation",
                "risk_level": RISK_BLOCKING,
                "message": message,
                "reason": "resource_context_unavailable",
                "suggestions": list(SALIENCY_MEMORY_SUGGESTIONS),
            },
        )

    ram = ResourceChecker.get_system_ram_status()
    ram_result = _memory_check(
        required_bytes=estimate["estimated_ram_working_set_bytes"],
        status=ram,
        warning_ratio=RAM_WARNING_RATIO,
        blocking_ratio=RAM_BLOCKING_RATIO,
        resource_name="RAM",
        blocking_title="Oversized saliency request exceeds available RAM.",
        warning_title="Saliency recomputation is close to available RAM.",
        details=estimate,
    )
    results = [ram_result]
    vram_result: ResourceCheckResult | None = None
    if not estimate["uses_cpu"]:
        gpu_idx = estimate["gpu_index"]
        vram = ResourceChecker.get_gpu_vram_status(gpu_idx)
        vram_result = _memory_check(
            required_bytes=estimate["estimated_vram_working_set_bytes"],
            status=vram,
            warning_ratio=VRAM_WARNING_RATIO,
            blocking_ratio=VRAM_BLOCKING_RATIO,
            resource_name="GPU memory",
            blocking_title=("Oversized saliency request exceeds available GPU memory."),
            warning_title="Saliency recomputation is close to available GPU memory.",
            details=estimate,
        )
        results.append(vram_result)

    issues: list[str] = []
    warnings: list[str] = []
    unknowns: list[str] = []
    for result in results:
        if result.blocking:
            issues.append(result.message)
        elif result.warning:
            warnings.append(result.message)
        elif result.risk_level == RISK_UNKNOWN:
            unknowns.append(result.message)
    diagnostics = {
        **estimate,
        "ram_risk_level": ram_result.risk_level,
        "ram": ram_result.to_diagnostics(),
        "vram_risk_level": (
            RISK_SAFE if vram_result is None else vram_result.risk_level
        ),
        "vram": None if vram_result is None else vram_result.to_diagnostics(),
        "suggestions": list(SALIENCY_MEMORY_SUGGESTIONS),
    }
    return ResourcePreflightResult(
        issues=tuple(issues),
        diagnostics=diagnostics,
        warnings=tuple(warnings),
        unknowns=tuple(unknowns),
    )


def _noise_partition_details(
    selected_methods: list[str],
    saliency_params: dict[str, Any],
) -> tuple[dict[str, dict[str, int]], int]:
    details: dict[str, dict[str, int]] = {}
    peak_partition = 1
    for method in selected_methods:
        if method not in ADVANCED_SALIENCY_METHODS:
            continue
        raw_params = saliency_params.get(method)
        if not isinstance(raw_params, dict):
            raise ValueError(
                f"Saliency resource admission requires parameters for {method}."
            )
        nt_samples = _positive_int(
            raw_params.get("nt_samples"),
            field=f"{method} nt_samples",
        )
        raw_batch = raw_params.get("nt_samples_batch_size")
        requested_batch = (
            nt_samples
            if raw_batch is None
            else _positive_int(
                raw_batch,
                field=f"{method} nt_samples_batch_size",
            )
        )
        effective_batch = min(nt_samples, requested_batch)
        peak_partition = max(peak_partition, effective_batch)
        details[method] = {
            "nt_samples": nt_samples,
            "requested_batch_size": requested_batch,
            "effective_batch_size": effective_batch,
        }
    return details, peak_partition


def _memory_check(
    *,
    required_bytes: int,
    status: dict[str, Any],
    warning_ratio: float,
    blocking_ratio: float,
    resource_name: str,
    blocking_title: str,
    warning_title: str,
    details: dict[str, Any],
) -> ResourceCheckResult:
    available = _optional_non_negative_int(status.get("available_bytes"))
    total = _optional_non_negative_int(status.get("total_bytes"))
    used = _optional_non_negative_int(status.get("used_bytes"))
    result_details = {
        **details,
        **status,
        "warning_ratio": warning_ratio,
        "blocking_ratio": blocking_ratio,
        "required_to_available_ratio": (
            None if not available else required_bytes / available
        ),
    }
    if available is None:
        reason = str(status.get("reason") or "memory_query_unavailable")
        return ResourceCheckResult(
            required_memory_bytes=required_bytes,
            available_memory_bytes=None,
            total_memory_bytes=total,
            used_memory_bytes=used,
            risk_level=RISK_UNKNOWN,
            message=(
                "Unable to admit saliency recomputation because available "
                f"{resource_name} could not be queried ({reason})."
            ),
            suggestions=SALIENCY_MEMORY_SUGGESTIONS,
            details=result_details,
        )
    ratio = required_bytes / available if available else math.inf
    if ratio > blocking_ratio:
        risk_level = RISK_BLOCKING
        title = blocking_title
    elif ratio > warning_ratio:
        risk_level = RISK_WARNING
        title = warning_title
    else:
        risk_level = RISK_SAFE
        title = "Saliency resource check is safe."
    message = (
        f"{title} Estimated {ResourceChecker.format_memory_size(required_bytes)}; "
        f"available {ResourceChecker.format_memory_size(available)}."
    )
    return ResourceCheckResult(
        required_memory_bytes=required_bytes,
        available_memory_bytes=available,
        total_memory_bytes=total,
        used_memory_bytes=used,
        risk_level=risk_level,
        message=message,
        suggestions=(SALIENCY_MEMORY_SUGGESTIONS if risk_level != RISK_SAFE else ()),
        details=result_details,
    )


def _estimate_model_memory(
    model_holder: Any,
    datasets: list[Any],
    training_plan_holders: Iterable[Any],
) -> _ModelMemoryEstimate:
    largest_bytes: int | None = None
    for holder in training_plan_holders:
        records = _call(holder, "get_plans")
        if records is None:
            continue
        try:
            record_list = list(records)
        except TypeError:
            continue
        for record in record_list:
            model = getattr(record, "model", None)
            parameters = getattr(model, "parameters", None)
            if not callable(parameters):
                continue
            try:
                parameter_bytes = _parameter_bytes(parameters())
            except Exception:
                logger.debug(
                    "Saliency model parameter inspection failed",
                    exc_info=True,
                )
                continue
            largest_bytes = max(largest_bytes or 0, parameter_bytes)
    if largest_bytes is not None:
        return _ModelMemoryEstimate(largest_bytes, "finished_training_record")
    if model_holder is None:
        raise ValueError(
            "Saliency model memory could not be estimated from the selected model."
        )
    model_args: dict[str, Any] = {}
    for dataset in datasets:
        epoch_data = _call(dataset, "get_epoch_data")
        candidate = _call(epoch_data, "get_model_args")
        if isinstance(candidate, dict):
            model_args = dict(candidate)
            break
    try:
        model = model_holder.get_model(model_args)
        parameter_bytes = _parameter_bytes(model.parameters())
        with suppress(Exception):
            model.cpu()
        del model
    except Exception as exc:
        raise ValueError(
            "Saliency model memory could not be estimated from the selected "
            f"model ({type(exc).__name__})."
        ) from exc
    return _ModelMemoryEstimate(parameter_bytes, "instantiated")


def _parameter_bytes(parameters: object) -> int:
    return sum(
        int(parameter.numel()) * int(parameter.element_size())
        for parameter in cast(Iterable[Any], parameters)
    )


def _positive_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Saliency {field} must be a positive integer.")
    try:
        normalized = operator.index(value)
    except TypeError as exc:
        raise ValueError(f"Saliency {field} must be a positive integer.") from exc
    if normalized < 1:
        raise ValueError(f"Saliency {field} must be a positive integer.")
    return normalized


def _epoch_shape(data: Any, *, dataset_index: int) -> tuple[int, int, int]:
    raw_shape = getattr(data, "shape", None)
    if raw_shape is None:
        raise ValueError(
            "Saliency resource admission could not inspect epoch shape for "
            f"dataset {dataset_index + 1}."
        )
    try:
        shape = tuple(operator.index(dimension) for dimension in raw_shape)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Saliency resource admission found an invalid epoch shape for "
            f"dataset {dataset_index + 1}."
        ) from exc
    if len(shape) != 3 or any(dimension < 1 for dimension in shape):
        raise ValueError(
            "Saliency resource admission requires a positive 3D epoch shape; "
            f"dataset {dataset_index + 1} reported {shape!r}."
        )
    return cast(tuple[int, int, int], shape)


def _evaluation_count(
    dataset: Any,
    *,
    epoch_count: int,
    dataset_index: int,
) -> tuple[str, int]:
    test_count = _mask_count(
        getattr(dataset, "test_mask", None),
        epoch_count=epoch_count,
        label="test",
        dataset_index=dataset_index,
    )
    validation_count = _mask_count(
        getattr(dataset, "val_mask", None),
        epoch_count=epoch_count,
        label="validation",
        dataset_index=dataset_index,
    )
    if test_count > 0:
        return "test", test_count
    if validation_count > 0:
        return "validation", validation_count
    raise ValueError(
        "Saliency resource admission requires validation or test epochs for "
        f"dataset {dataset_index + 1}."
    )


def _mask_count(
    mask: Any,
    *,
    epoch_count: int,
    label: str,
    dataset_index: int,
) -> int:
    if mask is None:
        raise ValueError(
            "Saliency resource admission could not inspect the "
            f"{label} split for dataset {dataset_index + 1}."
        )
    try:
        mask_length = len(mask)
        count = int(sum(mask))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Saliency resource admission found an invalid "
            f"{label} split for dataset {dataset_index + 1}."
        ) from exc
    if mask_length != epoch_count or count < 0 or count > epoch_count:
        raise ValueError(
            "Saliency resource admission found a mismatched "
            f"{label} split for dataset {dataset_index + 1}."
        )
    return count


def _activation_factor(model_holder: Any) -> float:
    target_model = getattr(model_holder, "target_model", None)
    name = str(getattr(target_model, "__name__", "") or "").lower()
    for key, factor in MODEL_ACTIVATION_FACTORS.items():
        if key in name:
            return factor
    return DEFAULT_ACTIVATION_FACTOR


def _gpu_index(option: Any) -> int | None:
    value = getattr(option, "gpu_idx", None)
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _call(obj: Any, method_name: str) -> Any:
    method = getattr(obj, method_name, None)
    if not callable(method):
        return None
    try:
        return method()
    except Exception:
        return None


def _optional_non_negative_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return max(normalized, 0)


def _without_live_memory_ratio(value: Any) -> Any:
    """Exclude volatile occupancy ratios while retaining estimated resource scope."""
    if isinstance(value, dict):
        return {
            str(key): _without_live_memory_ratio(item)
            for key, item in value.items()
            if str(key) != "required_to_available_ratio"
        }
    if isinstance(value, (list, tuple)):
        return [_without_live_memory_ratio(item) for item in value]
    return value


def _with_diagnostics(
    preflight: ResourcePreflightResult,
    **updates: Any,
) -> ResourcePreflightResult:
    return ResourcePreflightResult(
        issues=preflight.issues,
        diagnostics={**preflight.diagnostics, **updates},
        warnings=preflight.warnings,
        unknowns=preflight.unknowns,
    )


__all__ = [
    "SaliencyResourceAdmission",
    "check_saliency_resource_preflight",
    "estimate_saliency_resources",
]
