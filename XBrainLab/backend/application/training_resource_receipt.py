"""One-shot resource receipts bound to an exact training scope."""

from __future__ import annotations

import json
import time
from pathlib import Path
from threading import RLock
from typing import Any

from .commands import TrainCommand
from .resource_guard import (
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
from .training_snapshot import (
    model_name,
    model_params_snapshot,
    training_option_snapshot,
)

TRAINING_PREFLIGHT_RECEIPT_TTL_SECONDS = DEFAULT_RESOURCE_RECEIPT_TTL_SECONDS
TRAINING_PREFLIGHT_RECEIPT_LIMIT = DEFAULT_RESOURCE_RECEIPT_LIMIT
ARRAY_FINGERPRINT_MAX_SAMPLES = 32
_ARRAY_FINGERPRINT_MAX_DIMENSIONS = 16
_ARRAY_FINGERPRINT_MAX_TEXT_CHARS = 128
_UNAVAILABLE_ARRAY_ITEM = object()

_TrainingPreflightReceipt = ResourceReceiptRecord[ResourcePreflightResult]


class TrainingResourceReceiptAuthority:
    """Issue, validate, and consume backend-owned training receipts."""

    def __init__(self) -> None:
        self._authority = ResourceReceiptAuthority[ResourcePreflightResult](
            command_name="start_training",
            ttl_seconds=TRAINING_PREFLIGHT_RECEIPT_TTL_SECONDS,
            max_receipts=TRAINING_PREFLIGHT_RECEIPT_LIMIT,
            clock=lambda: time.monotonic(),
        )
        self._lock = RLock()

    def annotate(
        self,
        command: TrainCommand,
        context: dict[str, Any],
        preflight: ResourcePreflightResult,
    ) -> ResourcePreflightResult:
        """Attach deterministic fingerprints without issuing a token."""
        configuration_fingerprint = _configuration_fingerprint(command, context)
        preflight_fingerprint = _preflight_fingerprint(preflight)
        scope_fingerprint = fingerprint_resource_scope(
            {
                "command": "start_training",
                "configuration_fingerprint": configuration_fingerprint,
                "preflight_fingerprint": preflight_fingerprint,
            }
        )
        return ResourcePreflightResult(
            issues=preflight.issues,
            warnings=preflight.warnings,
            unknowns=preflight.unknowns,
            diagnostics={
                **preflight.diagnostics,
                "configuration_fingerprint": configuration_fingerprint,
                "preflight_fingerprint": preflight_fingerprint,
                "scope_fingerprint": scope_fingerprint,
            },
        )

    def authorize(
        self,
        command: TrainCommand,
        preflight: ResourcePreflightResult,
    ) -> bool:
        """Return receipt reuse, or raise before any training side effect."""
        with self._lock:
            if preflight.blocking:
                self.discard(command.resource_preflight_token)
                enforce_resource_preflight(preflight, confirmed=False)

            if not preflight.requires_confirmation:
                self.discard(command.resource_preflight_token)
                enforce_resource_preflight(preflight, confirmed=False)
                return False

            receipt = self._matching(command.resource_preflight_token, preflight)
            if receipt is not None:
                if not command.resource_preflight_confirmed:
                    raise self._confirmation_error(receipt)
                enforce_resource_preflight(preflight, confirmed=True)
                # A token authorizes one attempt, including an attempt whose trainer
                # startup later fails. Consume it before the side-effect boundary.
                consumed = self._authority.consume(
                    receipt.challenge.challenge_id,
                    scope_fingerprint=receipt.challenge.scope_fingerprint,
                    configuration_fingerprint=(
                        receipt.challenge.configuration_fingerprint
                    ),
                    preflight_fingerprint=receipt.challenge.preflight_fingerprint,
                )
                if consumed is None:
                    fresh = self._issue(preflight)
                    raise self._confirmation_error(fresh)
                return True

            if command.resource_preflight_token:
                self.discard(command.resource_preflight_token)
                receipt = self._issue(preflight)
            else:
                receipt = self._pending(preflight) or self._issue(preflight)
            raise self._confirmation_error(receipt)

    def discard(self, token: str | None) -> None:
        """Discard a presented token if it is still stored."""
        self._authority.discard(token)

    def _matching(
        self,
        token: str | None,
        preflight: ResourcePreflightResult,
    ) -> _TrainingPreflightReceipt | None:
        diagnostics = preflight.diagnostics
        return self._authority.peek(
            token,
            scope_fingerprint=str(diagnostics.get("scope_fingerprint") or ""),
            configuration_fingerprint=str(
                diagnostics.get("configuration_fingerprint") or ""
            ),
            preflight_fingerprint=str(diagnostics.get("preflight_fingerprint") or ""),
        )

    def _pending(
        self,
        preflight: ResourcePreflightResult,
    ) -> _TrainingPreflightReceipt | None:
        diagnostics = preflight.diagnostics
        return self._authority.pending(
            scope_fingerprint=str(diagnostics["scope_fingerprint"]),
            configuration_fingerprint=str(diagnostics["configuration_fingerprint"]),
            preflight_fingerprint=str(diagnostics["preflight_fingerprint"]),
        )

    def _issue(
        self,
        preflight: ResourcePreflightResult,
    ) -> _TrainingPreflightReceipt:
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
            raise RuntimeError("Issued training resource challenge was not stored.")
        return receipt

    @staticmethod
    def _confirmation_error(
        receipt: _TrainingPreflightReceipt,
    ) -> ResourceConfirmationRequiredError:
        return ResourceConfirmationRequiredError(
            receipt.payload,
            challenge=receipt.challenge,
        )


def _configuration_fingerprint(
    command: TrainCommand,
    context: dict[str, Any],
) -> str:
    model_holder = context.get("model_holder")
    payload = {
        "command": {
            "append": bool(command.append),
            "interactive": bool(command.interactive),
        },
        "training_option": training_option_snapshot(context.get("training_option")),
        "model": {
            "name": model_name(model_holder),
            "params": model_params_snapshot(model_holder),
            "pretrained_weight": _path_descriptor(
                getattr(model_holder, "pretrained_weight_path", None)
            ),
        },
        "datasets": [
            _dataset_descriptor(dataset, index=index)
            for index, dataset in enumerate(context.get("datasets", []) or [])
        ],
    }
    return fingerprint_resource_scope(payload)


def _dataset_descriptor(dataset: Any, *, index: int) -> dict[str, Any]:
    epoch_data = _safe_call(dataset, "get_epoch_data")
    data = _safe_call(epoch_data, "get_data")
    labels = _safe_call(epoch_data, "get_label_list")
    return {
        "index": index,
        "type": _type_name(dataset),
        "object_id": id(dataset),
        "dataset_id": getattr(dataset, "dataset_id", None),
        "name": _safe_call(dataset, "get_name"),
        "selected": getattr(dataset, "is_selected", None),
        "revision": _resource_fingerprint_revision(dataset),
        "epoch": {
            "type": _type_name(epoch_data),
            "object_id": id(epoch_data) if epoch_data is not None else None,
            "revision": _resource_fingerprint_revision(epoch_data),
            "data": _array_descriptor(data),
            "labels": _array_descriptor(labels),
        },
        "splits": {
            name: _array_descriptor(getattr(dataset, name, None))
            for name in ("train_mask", "val_mask", "test_mask")
        },
    }


def _array_descriptor(
    value: Any,
) -> dict[str, Any] | None:
    if value is None:
        return None
    shape = _normalized_shape(value)
    shape_count = _shape_element_count(shape)
    descriptor: dict[str, Any] = {
        "type": _type_name(value),
        "object_id": id(value),
        "shape": _canonical_value(shape),
        "shape_element_count": shape_count,
        "declared_size": _safe_int(getattr(value, "size", None)),
        "dtype": str(getattr(value, "dtype", "")) or None,
        "nbytes": _safe_int(getattr(value, "nbytes", None)),
        "revision": _resource_fingerprint_revision(value),
        "bounded_sample": _bounded_array_sample(
            value,
            shape=shape,
            element_count=shape_count,
        ),
    }
    return descriptor


def _bounded_array_sample(
    value: Any,
    *,
    shape: tuple[int, ...] | None,
    element_count: int | None,
) -> dict[str, Any]:
    """Read a fixed number of scalar sentinels without copying array storage.

    Official dataset mutations are guarded by a revision. These sentinels add
    bounded protection for array-like objects changed outside those mutators;
    they deliberately do not claim to be a collision-free content digest.
    """
    if element_count is None:
        element_count = _safe_int(getattr(value, "size", None))
    if element_count is None or element_count < 0:
        return {"status": "unavailable", "values": []}
    if element_count == 0:
        return {"status": "empty", "values": []}

    indices = _bounded_sample_indices(
        element_count,
        limit=ARRAY_FINGERPRINT_MAX_SAMPLES,
    )
    samples: list[list[Any]] = []
    for index in indices:
        available, item = _read_flat_item(value, index=index, shape=shape)
        if not available:
            return {
                "status": "partial" if samples else "unavailable",
                "values": samples,
            }
        samples.append([index, _canonical_sample_value(item)])
    return {"status": "sampled", "values": samples}


def _bounded_sample_indices(element_count: int, *, limit: int) -> tuple[int, ...]:
    sample_count = min(max(int(limit), 0), element_count)
    if sample_count <= 0:
        return ()
    if sample_count == 1:
        return (0,)
    last_index = element_count - 1
    return tuple(
        (sample_index * last_index) // (sample_count - 1)
        for sample_index in range(sample_count)
    )


def _read_flat_item(
    value: Any,
    *,
    index: int,
    shape: tuple[int, ...] | None,
) -> tuple[bool, Any]:
    flat = getattr(value, "flat", None)
    if flat is not None:
        item = _try_array_item(flat, index)
        if item is not _UNAVAILABLE_ARRAY_ITEM:
            return True, item

    if shape:
        coordinates = _flat_index_coordinates(index, shape)
        if coordinates is not None:
            item = _try_array_item(value, coordinates)
            if item is not _UNAVAILABLE_ARRAY_ITEM:
                return True, item
    item = _try_array_item(value, index)
    if item is _UNAVAILABLE_ARRAY_ITEM:
        return False, None
    return True, item


def _try_array_item(value: Any, index: Any) -> Any:
    try:
        return value[index]
    except Exception:
        return _UNAVAILABLE_ARRAY_ITEM


def _flat_index_coordinates(
    index: int,
    shape: tuple[int, ...],
) -> tuple[int, ...] | None:
    if not shape or any(dimension <= 0 for dimension in shape):
        return None
    remaining = index
    coordinates = [0] * len(shape)
    for dimension_index in range(len(shape) - 1, -1, -1):
        remaining, coordinate = divmod(remaining, shape[dimension_index])
        coordinates[dimension_index] = coordinate
    if remaining:
        return None
    return tuple(coordinates)


def _normalized_shape(value: Any) -> tuple[int, ...] | None:
    raw_shape = getattr(value, "shape", None)
    if raw_shape is None:
        return None
    try:
        dimension_count = len(raw_shape)
    except (TypeError, ValueError):
        return None
    if dimension_count > _ARRAY_FINGERPRINT_MAX_DIMENSIONS:
        return None
    try:
        dimensions = tuple(raw_shape[index] for index in range(dimension_count))
    except (IndexError, KeyError, TypeError, ValueError):
        return None
    normalized: list[int] = []
    for dimension in dimensions:
        parsed = _safe_int(dimension)
        if parsed is None or parsed < 0:
            return None
        normalized.append(parsed)
    return tuple(normalized)


def _shape_element_count(shape: tuple[int, ...] | None) -> int | None:
    if shape is None:
        return None
    count = 1
    for dimension in shape:
        count *= dimension
    return count


def _canonical_sample_value(value: Any) -> Any:
    item = getattr(value, "item", None)
    if callable(item):
        try:
            value = item()
        except Exception:
            return {"type": _type_name(value)}
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return _bounded_text(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        view = memoryview(value)
        prefix = bytes(view[:_ARRAY_FINGERPRINT_MAX_TEXT_CHARS]).hex()
        return {"type": "bytes", "length": len(view), "prefix_hex": prefix}
    if isinstance(value, complex):
        return {"real": value.real, "imag": value.imag}
    return {"type": _type_name(value)}


def _bounded_text(value: str) -> str | dict[str, Any]:
    if len(value) <= _ARRAY_FINGERPRINT_MAX_TEXT_CHARS:
        return value
    edge = _ARRAY_FINGERPRINT_MAX_TEXT_CHARS // 2
    return {
        "length": len(value),
        "prefix": value[:edge],
        "suffix": value[-edge:],
    }


def _resource_fingerprint_revision(value: Any) -> Any:
    if value is None:
        return None
    getter = getattr(value, "get_resource_fingerprint_revision", None)
    if callable(getter):
        try:
            revision = getter()
        except Exception:
            return None
    else:
        revision = getattr(value, "_resource_fingerprint_revision", None)
    if revision is None or isinstance(revision, (str, int, float, bool)):
        return revision
    enum_value = getattr(revision, "value", None)
    if isinstance(enum_value, (str, int, float, bool)):
        return enum_value
    return {"type": _type_name(revision)}


def _path_descriptor(value: Any) -> dict[str, Any] | None:
    if value is None or value == "":
        return None
    path = Path(str(value)).expanduser()
    descriptor: dict[str, Any] = {"path": str(path.resolve(strict=False))}
    try:
        stat = path.stat()
    except OSError as exc:
        descriptor.update({"status": "unavailable", "error": exc.__class__.__name__})
        return descriptor
    descriptor.update(
        {
            "status": "available",
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "ctime_ns": stat.st_ctime_ns,
            "device": stat.st_dev,
            "inode": stat.st_ino,
        }
    )
    return descriptor


def _preflight_fingerprint(preflight: ResourcePreflightResult) -> str:
    return fingerprint_resource_preflight(
        {
            "risk_level": preflight.risk_level.value,
            "issue_count": len(preflight.issues),
            "warning_count": len(preflight.warnings),
            "unknown_count": len(preflight.unknowns),
            "diagnostics": preflight.diagnostics,
        }
    )


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_canonical_value(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, sort_keys=True, default=str),
        )
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, (str, int, float, bool)):
        return enum_value
    return repr(value)


def _safe_call(target: Any, method_name: str) -> Any:
    method = getattr(target, method_name, None)
    if not callable(method):
        return None
    try:
        return method()
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _type_name(value: Any) -> str | None:
    if value is None:
        return None
    target_type = type(value)
    return f"{target_type.__module__}.{target_type.__qualname__}"
