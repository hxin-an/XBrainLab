"""Project saliency artifacts into the application state coverage contract."""

from __future__ import annotations

from collections.abc import Iterable
from importlib import import_module
from typing import Any, cast

from XBrainLab.backend.saliency_methods import all_saliency_methods

from .state import (
    SaliencyClassCoverageSnapshot,
    SaliencyMethodCoverageSnapshot,
    SaliencyRunCoverageSnapshot,
)

_SALIENCY_STORE_BY_METHOD = {
    "Gradient": "gradient",
    "Gradient * Input": "gradient_input",
    "SmoothGrad": "smoothgrad",
    "SmoothGrad_Squared": "smoothgrad_sq",
    "VarGrad": "vargrad",
}
_SALIENCY_METHOD_STORES: tuple[tuple[str, str], ...] = tuple(
    (method, _SALIENCY_STORE_BY_METHOD[method]) for method in all_saliency_methods
)


class SaliencyCoverageProjector:
    """Apply one class/method/run coverage policy to saliency artifacts."""

    def project_eval_record(
        self,
        eval_record: Any,
        *,
        label_items: Iterable[tuple[object, object]] | None = None,
    ) -> list[SaliencyMethodCoverageSnapshot]:
        """Return method/class coverage for one evaluation record."""
        classes = _saliency_classes(eval_record, label_items=label_items)
        context, record_reason, payloads_verified = _saliency_record_contract(
            eval_record,
        )
        return [
            _saliency_method_coverage(
                method,
                getattr(eval_record, store_name, None),
                classes,
                context=context,
                record_reason=record_reason,
                payloads_verified=payloads_verified,
            )
            for method, store_name in _SALIENCY_METHOD_STORES
        ]

    def project_method(
        self,
        eval_record: Any,
        method: str,
        *,
        label_items: Iterable[tuple[object, object]] | None = None,
    ) -> SaliencyMethodCoverageSnapshot:
        """Return coverage for one method using the shared projection policy."""
        for coverage in self.project_eval_record(
            eval_record,
            label_items=label_items,
        ):
            if coverage.method == method:
                return coverage
        return SaliencyMethodCoverageSnapshot(method=method)

    def project_run(
        self,
        eval_record: Any,
        *,
        plan_index: int,
        run_index: int,
        label_items: Iterable[tuple[object, object]] | None = None,
    ) -> SaliencyRunCoverageSnapshot:
        """Return the complete saliency coverage contract for one finished run."""
        return SaliencyRunCoverageSnapshot(
            plan_index=plan_index,
            run_index=run_index,
            methods=self.project_eval_record(
                eval_record,
                label_items=label_items,
            ),
        )

    @staticmethod
    def label_items_from_epoch(
        epoch_data: Any,
    ) -> list[tuple[object, object]]:
        """Return code/name class identities without materializing epoch samples."""
        if epoch_data is None:
            return []
        label_map = getattr(epoch_data, "label_map", None)
        if isinstance(label_map, dict) and label_map:
            return [(key, value) for key, value in label_map.items()]
        event_id = getattr(epoch_data, "event_id", None)
        if isinstance(event_id, dict):
            return [(code, name) for name, code in event_id.items()]
        return []


def _saliency_classes(
    eval_record: Any,
    *,
    label_items: Iterable[tuple[object, object]] | None,
) -> list[tuple[int, object | None, str]]:
    context = getattr(eval_record, "saliency_context", None)
    context_items = getattr(context, "class_map", None)
    normalized_items = _valid_saliency_label_items(context_items)
    if not normalized_items:
        normalized_items = _valid_saliency_label_items(label_items)
    if normalized_items:
        return [
            (index, event_code, str(display_name))
            for index, (event_code, display_name) in enumerate(normalized_items)
        ]

    output = getattr(eval_record, "output", None)
    shape = getattr(output, "shape", None)
    if isinstance(shape, (tuple, list)) and len(shape) == 2:
        try:
            class_count = int(shape[1])
        except (TypeError, ValueError):
            class_count = 0
        if class_count > 0:
            return [(index, index, str(index)) for index in range(class_count)]

    keys: list[object] = []
    for _method, store_name in _SALIENCY_METHOD_STORES:
        store = getattr(eval_record, store_name, None)
        for key, _value in _saliency_store_items(store):
            if not any(_saliency_identity_equal(key, known) for known in keys):
                keys.append(key)
    return [(index, key, str(key)) for index, key in enumerate(keys)]


def _valid_saliency_label_items(value: Any) -> list[tuple[object, object]]:
    if not isinstance(value, (list, tuple)):
        return []
    items: list[tuple[object, object]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            return []
        items.append((item[0], item[1]))
    return items


def _saliency_method_coverage(
    method: str,
    store: Any,
    classes: list[tuple[int, object | None, str]],
    *,
    context: Any,
    record_reason: str | None,
    payloads_verified: bool,
) -> SaliencyMethodCoverageSnapshot:
    store_items = _saliency_store_items(store)
    normalized_store = _complete_normalized_saliency_store(store_items, len(classes))
    resolved_items = [
        _saliency_store_item_for_class(
            store_items,
            class_index=class_index,
            event_code=event_code,
            display_name=display_name,
            normalized_store=normalized_store,
        )
        for class_index, event_code, display_name in classes
    ]
    method_reason = record_reason
    if method_reason is None:
        for store_item in resolved_items:
            if store_item is None or not _has_nonempty_saliency_value(store_item[1]):
                continue
            method_reason = _saliency_payload_unavailability_reason(
                store_item[1],
                context=context,
                payloads_verified=payloads_verified,
            )
            if method_reason is not None:
                break

    coverage: list[SaliencyClassCoverageSnapshot] = []
    for (class_index, event_code, display_name), store_item in zip(
        classes,
        resolved_items,
        strict=True,
    ):
        store_key = store_item[0] if store_item is not None else None
        value = store_item[1] if store_item is not None else None
        available = (
            method_reason is None
            and store_item is not None
            and _has_nonempty_saliency_value(value)
        )
        reason = None
        if not available:
            reason = method_reason or (
                f"No {method} saliency is available for {display_name}. "
                "Recompute saliency for this run and class."
            )
        coverage.append(
            SaliencyClassCoverageSnapshot(
                class_index=class_index,
                display_name=display_name,
                event_code=event_code,
                store_key=store_key,
                available=available,
                reason=reason,
            )
        )
    available = any(item.available for item in coverage)
    complete = bool(coverage) and all(item.available for item in coverage)
    return SaliencyMethodCoverageSnapshot(
        method=method,
        available=available,
        complete=complete,
        classes=coverage,
    )


def _saliency_record_contract(
    eval_record: Any,
) -> tuple[Any, str | None, bool]:
    try:
        status = getattr(eval_record, "saliency_context_status", None)
    except Exception as exc:
        return None, _recompute_reason(f"Saliency context status failed: {exc}"), False
    try:
        context = getattr(eval_record, "saliency_context", None)
    except Exception as exc:
        return None, _recompute_reason(f"Saliency context read failed: {exc}"), False

    if status != "verified":
        try:
            detail = getattr(eval_record, "saliency_recompute_reason", None)
        except Exception as exc:
            detail = f"Saliency context reason failed: {exc}"
        if not detail:
            detail = (
                f"Saliency identity context is {status or 'unavailable'} and "
                "cannot be trusted."
            )
        return context, _recompute_reason(detail), False

    context_reason = _saliency_context_unavailability_reason(context)
    if context_reason is not None:
        return context, context_reason, False

    try:
        integrity_reason = getattr(eval_record, "saliency_integrity_reason", None)
    except Exception as exc:
        return (
            context,
            _recompute_reason(f"Saliency integrity status failed: {exc}"),
            False,
        )
    if integrity_reason is not None:
        return (
            context,
            _recompute_reason(
                f"Saliency artifact integrity failed: {integrity_reason}",
            ),
            False,
        )

    try:
        manifest = getattr(eval_record, "saliency_integrity_manifest", None)
    except Exception as exc:
        return (
            context,
            _recompute_reason(f"Saliency integrity manifest failed: {exc}"),
            False,
        )
    payloads_verified = isinstance(manifest, dict) and callable(
        getattr(eval_record, "validate_saliency_producer_identity", None),
    )
    return context, None, payloads_verified


def _saliency_context_unavailability_reason(context: Any) -> str | None:
    if context is None:
        return _recompute_reason("Saliency identity context is unavailable.")
    if not _valid_saliency_label_items(getattr(context, "class_map", None)):
        return _recompute_reason("Saliency class identity context is malformed.")
    channel_names = getattr(context, "channel_names", None)
    if (
        not isinstance(channel_names, (list, tuple))
        or not channel_names
        or any(not str(name).strip() for name in channel_names)
        or len({str(name) for name in channel_names}) != len(channel_names)
    ):
        return _recompute_reason("Saliency channel identity context is malformed.")
    sample_count = getattr(context, "epoch_sample_count", None)
    if (
        isinstance(sample_count, bool)
        or not isinstance(sample_count, int)
        or sample_count <= 0
    ):
        return _recompute_reason("Saliency epoch sample context is malformed.")
    return None


def _saliency_payload_unavailability_reason(
    value: Any,
    *,
    context: Any,
    payloads_verified: bool,
) -> str | None:
    if payloads_verified:
        raw_shape = getattr(value, "shape", None)
        if not isinstance(raw_shape, Iterable):
            return _recompute_reason("Saliency payload shape is unavailable.")
        try:
            shape = tuple(int(item) for item in raw_shape)
        except (OverflowError, TypeError, ValueError):
            return _recompute_reason("Saliency payload shape is unavailable.")
    else:
        try:
            descriptor = _describe_saliency_array(
                value,
                require_finite_float=True,
            )
        except Exception as exc:
            return _recompute_reason(str(exc))
        raw_shape = descriptor.get("shape")
        if not isinstance(raw_shape, tuple):
            return _recompute_reason("Saliency payload shape is unavailable.")
        shape = raw_shape

    if len(shape) != 3 or shape[0] <= 0:
        return _recompute_reason(
            "Saliency payload shape must be (epochs, channels, samples).",
        )
    channel_names = cast(tuple[object, ...] | list[object], context.channel_names)
    if shape[1] != len(channel_names):
        return _recompute_reason(
            "Saliency payload channel count does not match its identity context.",
        )
    if shape[2] != context.epoch_sample_count:
        return _recompute_reason(
            "Saliency payload sample count does not match its epoch context.",
        )
    return None


def _describe_saliency_array(
    value: object,
    *,
    require_finite_float: bool,
) -> dict[str, object]:
    provenance = import_module(
        "XBrainLab.backend.training.saliency_provenance",
    )
    describe = cast(Any, provenance).describe_saliency_array
    return cast(
        dict[str, object],
        describe(value, require_finite_float=require_finite_float),
    )


def _recompute_reason(detail: object) -> str:
    text = str(detail).strip() or "Saliency artifact validation failed."
    if "recompute saliency" not in text.lower():
        text = f"{text} Recompute saliency for this run."
    return text


def _saliency_store_items(store: Any) -> list[tuple[object, Any]]:
    if isinstance(store, dict):
        return list(store.items())
    if isinstance(store, (list, tuple)):
        return list(enumerate(store))
    return []


def _complete_normalized_saliency_store(
    store_items: list[tuple[object, Any]],
    class_count: int,
) -> bool:
    if class_count <= 0 or len(store_items) != class_count:
        return False
    normalized: set[int] = set()
    for key, _value in store_items:
        normalized_key = _normalized_saliency_key(key)
        if normalized_key is None:
            return False
        normalized.add(normalized_key)
    return normalized == set(range(class_count))


def _normalized_saliency_key(value: object) -> int | None:
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError):
        return None


def _saliency_store_item_for_class(
    store_items: list[tuple[object, Any]],
    *,
    class_index: int,
    event_code: object | None,
    display_name: str,
    normalized_store: bool,
) -> tuple[object, Any] | None:
    if normalized_store:
        for item in store_items:
            if _saliency_identity_equal(item[0], class_index):
                return item
        return None
    candidates = [event_code, display_name]
    matches = [
        item
        for item in store_items
        if any(
            candidate is not None and _saliency_identity_equal(item[0], candidate)
            for candidate in candidates
        )
    ]
    return matches[0] if len(matches) == 1 else None


def _saliency_identity_equal(left: object, right: object) -> bool:
    if type(left) is type(right) and left == right:
        return True
    if isinstance(left, (str, int)) and isinstance(right, (str, int)):
        return str(left).strip() == str(right).strip()
    return False


def _has_nonempty_saliency_value(value: Any) -> bool:
    try:
        return len(value) > 0
    except TypeError:
        return False


_DEFAULT_PROJECTOR = SaliencyCoverageProjector()


def saliency_coverage_for_eval_record(
    eval_record: Any,
    *,
    label_items: Iterable[tuple[object, object]] | None = None,
) -> list[SaliencyMethodCoverageSnapshot]:
    """Compatibility helper for callers migrating to the projector."""
    return _DEFAULT_PROJECTOR.project_eval_record(
        eval_record,
        label_items=label_items,
    )


def saliency_method_coverage(
    eval_record: Any,
    method: str,
    *,
    label_items: Iterable[tuple[object, object]] | None = None,
) -> SaliencyMethodCoverageSnapshot:
    """Compatibility helper for callers migrating to the projector."""
    return _DEFAULT_PROJECTOR.project_method(
        eval_record,
        method,
        label_items=label_items,
    )


def saliency_label_items_from_epoch(
    epoch_data: Any,
) -> list[tuple[object, object]]:
    """Compatibility helper for callers migrating to the projector."""
    return _DEFAULT_PROJECTOR.label_items_from_epoch(epoch_data)


__all__ = [
    "SaliencyCoverageProjector",
    "saliency_coverage_for_eval_record",
    "saliency_label_items_from_epoch",
    "saliency_method_coverage",
]
