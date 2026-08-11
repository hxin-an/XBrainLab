"""Build epoch setup context from imported label and event interpretation."""

from __future__ import annotations

import contextlib
import hmac
import secrets
from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation
from enum import Enum
from numbers import Real
from typing import Any

import numpy as np

from .capabilities import CommandCapability
from .errors import PreconditionError
from .resource_receipt import fingerprint_resource_scope

EPOCH_HINT_KEY = "data_interpretation_epoch_hint"
EPOCH_CONTEXT_AVAILABILITY_KEY = "context_availability"
EPOCH_DIALOG_CONTEXT_UNAVAILABLE_MESSAGE = "Workflow state is temporarily unavailable."
EPOCH_CONFIRMATION_CODE = "bids_duration_review"
EPOCH_CONFIRMATION_VERSION = 1

_EPOCH_CONFIRMATION_SECRET = secrets.token_bytes(32)

_EPOCH_HANDOFF_BOOLEAN_FIELDS = ("ready", "supervised_ready")
_EPOCH_HANDOFF_TEXT_LIST_FIELDS = (
    "default_epoch_events",
    "placement_modes",
    "selected_event_names",
    "supervised_blocker_codes",
    "supervised_blockers",
)


class EpochWindowMode(str, Enum):
    """Supported epoch-window interpretations exposed to product surfaces."""

    EVENT_LOCKED = "event_locked"
    DURATION = "duration"


class EpochContextAvailabilityCode(str, Enum):
    """Stable semantic result codes for epoch-context admission."""

    AVAILABLE = "available"
    NO_DATA = "no_data"
    HINT_MISSING = "hint_missing"
    HINT_READ_FAILED = "hint_read_failed"
    HINT_SEMANTICS_INVALID = "hint_semantics_invalid"
    HANDOFF_UNAVAILABLE = "handoff_unavailable"
    HANDOFF_SOURCE_MISMATCH = "handoff_source_mismatch"
    HANDOFF_PLACEMENT_MISMATCH = "handoff_placement_mismatch"
    DURATION_UNAVAILABLE = "duration_unavailable"
    SAMPLING_FREQUENCY_MISMATCH = "sampling_frequency_mismatch"
    INVALID_CONTEXT = "invalid_context"


@dataclass(frozen=True)
class EpochContextAvailability:
    """Authoritative semantic availability for one detached epoch context."""

    available: bool
    code: EpochContextAvailabilityCode
    reason: str
    window_mode: EpochWindowMode | None
    window_explanation: str

    @classmethod
    def ready(
        cls,
        *,
        window_mode: EpochWindowMode,
        window_explanation: str,
    ) -> EpochContextAvailability:
        return cls(
            available=True,
            code=EpochContextAvailabilityCode.AVAILABLE,
            reason="",
            window_mode=window_mode,
            window_explanation=window_explanation,
        )

    @classmethod
    def unavailable(
        cls,
        code: EpochContextAvailabilityCode,
        reason: str,
    ) -> EpochContextAvailability:
        if code is EpochContextAvailabilityCode.AVAILABLE:
            raise ValueError("Unavailable epoch context requires a blocking code")
        return cls(
            available=False,
            code=code,
            reason=str(reason).strip(),
            window_mode=None,
            window_explanation="",
        )

    def to_payload(self) -> dict[str, object]:
        """Return the detached representation consumed by UI and backend gates."""
        return {
            "available": self.available,
            "code": self.code.value,
            "reason": self.reason,
            "window_mode": (
                self.window_mode.value if self.window_mode is not None else None
            ),
            "window_explanation": self.window_explanation,
        }


@dataclass(frozen=True)
class _EpochHintRead:
    data_count: int
    hints: tuple[dict[str, Any], ...]
    missing_count: int
    failed_count: int


@dataclass(frozen=True)
class _EpochWindowSuggestion:
    t_min: float
    t_max: float
    baseline: tuple[float | None, float | None] | None
    evidence: str
    mode: EpochWindowMode | None
    explanation: str
    warning: str
    confirmation_message: str
    unavailable_reason: str = ""


def validated_epoch_window_mode(value: object) -> EpochWindowMode:
    """Return one exact window-mode contract value or reject the payload."""
    if isinstance(value, EpochWindowMode):
        return value
    if not isinstance(value, str):
        raise ValueError("epoch_context.window_mode must be a supported string")
    try:
        return EpochWindowMode(value)
    except ValueError as exc:
        raise ValueError(
            "epoch_context.window_mode must be 'event_locked' or 'duration'"
        ) from exc


def validated_epoch_context_availability(
    epoch_context: Mapping[str, Any],
) -> EpochContextAvailability:
    """Parse one detached availability payload without semantic fallbacks."""
    raw = epoch_context.get(EPOCH_CONTEXT_AVAILABILITY_KEY)
    if not isinstance(raw, Mapping):
        raise ValueError("epoch_context.context_availability must be a mapping")
    available = raw.get("available")
    if not isinstance(available, bool):
        raise ValueError("epoch context availability must be a boolean")
    try:
        code = EpochContextAvailabilityCode(raw.get("code"))
    except (TypeError, ValueError) as exc:
        raise ValueError("epoch context availability code is invalid") from exc
    reason = raw.get("reason")
    explanation = raw.get("window_explanation")
    if not isinstance(reason, str) or not isinstance(explanation, str):
        raise ValueError("epoch context availability text fields must be strings")

    raw_mode = raw.get("window_mode")
    if available:
        if code is not EpochContextAvailabilityCode.AVAILABLE or reason.strip():
            raise ValueError("available epoch context has inconsistent status fields")
        mode = validated_epoch_window_mode(raw_mode)
        if not explanation.strip():
            raise ValueError("available epoch context requires a window explanation")
        return EpochContextAvailability.ready(
            window_mode=mode,
            window_explanation=explanation,
        )

    if code is EpochContextAvailabilityCode.AVAILABLE:
        raise ValueError("unavailable epoch context requires a blocking code")
    if not reason.strip() or raw_mode is not None or explanation.strip():
        raise ValueError("unavailable epoch context has inconsistent status fields")
    return EpochContextAvailability.unavailable(code, reason)


def require_epoch_context_available(
    epoch_context: Mapping[str, Any],
) -> EpochContextAvailability:
    """Return semantic availability or raise the shared backend precondition."""
    try:
        availability = validated_epoch_context_availability(epoch_context)
    except ValueError as exc:
        raise PreconditionError(
            "EEG epoch setup needs review because its workflow context is invalid.",
            diagnostics={
                "epoch_context_error": (
                    EpochContextAvailabilityCode.INVALID_CONTEXT.value
                )
            },
        ) from exc
    if not availability.available:
        raise PreconditionError(
            availability.reason,
            diagnostics={"epoch_context_error": availability.code.value},
        )
    return availability


@dataclass(frozen=True)
class EpochDialogContext:
    """One authoritative publication generation used to open epoch setup."""

    capability: CommandCapability | None
    epoch_handoff: dict[str, Any] | None
    epoch_setup: dict[str, Any] | None
    publication_generation: int | None
    usable: bool
    unavailable_reason: str | None

    def __post_init__(self) -> None:
        generation = self.publication_generation
        if generation is not None and (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation < 1
        ):
            raise ValueError("publication_generation must be a positive integer")
        if self.usable:
            if (
                self.capability is None
                or self.epoch_handoff is None
                or self.epoch_setup is None
            ):
                raise ValueError(
                    "A usable epoch dialog context requires capability, handoff, "
                    "and setup data"
                )
            if generation is None:
                raise ValueError(
                    "A usable epoch dialog context requires a publication generation"
                )
            if self.unavailable_reason is not None:
                raise ValueError(
                    "A usable epoch dialog context cannot have an unavailable reason"
                )
            return
        if self.epoch_handoff is not None or self.epoch_setup is not None:
            raise ValueError(
                "An unavailable epoch dialog context cannot expose workflow data"
            )
        if not str(self.unavailable_reason or "").strip():
            raise ValueError("An unavailable epoch dialog context requires a reason")

    @classmethod
    def unavailable(
        cls,
        *,
        reason: str = EPOCH_DIALOG_CONTEXT_UNAVAILABLE_MESSAGE,
        capability: CommandCapability | None = None,
        publication_generation: int | None = None,
    ) -> EpochDialogContext:
        """Build a typed unavailable context without fabricated defaults."""
        return cls(
            capability=capability,
            epoch_handoff=None,
            epoch_setup=None,
            publication_generation=publication_generation,
            usable=False,
            unavailable_reason=reason,
        )

    def require_usable(self) -> EpochDialogContext:
        """Return this context or raise the typed command precondition error."""
        if not self.usable:
            raise PreconditionError(
                self.unavailable_reason or EPOCH_DIALOG_CONTEXT_UNAVAILABLE_MESSAGE,
                diagnostics={"epoch_handoff_error": "publication_unavailable"},
            )
        return self


def validated_epoch_handoff(raw_handoff: object) -> dict[str, Any]:
    """Return an isolated handoff payload or reject malformed authoritative data."""
    if not isinstance(raw_handoff, dict):
        raise ValueError("epoch_handoff must be a mapping")
    if not all(isinstance(key, str) for key in raw_handoff):
        raise ValueError("epoch_handoff keys must be strings")

    for field_name in _EPOCH_HANDOFF_BOOLEAN_FIELDS:
        value = raw_handoff.get(field_name)
        if field_name in raw_handoff and not isinstance(value, bool):
            raise ValueError(f"epoch_handoff.{field_name} must be a boolean")

    for field_name in _EPOCH_HANDOFF_TEXT_LIST_FIELDS:
        if field_name not in raw_handoff:
            continue
        values = raw_handoff[field_name]
        if not isinstance(values, list) or any(
            not isinstance(value, str) for value in values
        ):
            raise ValueError(f"epoch_handoff.{field_name} must be a list of strings")

    aliases = raw_handoff.get("event_label_aliases")
    if "event_label_aliases" in raw_handoff and (
        not isinstance(aliases, dict)
        or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in aliases.items()
        )
    ):
        raise ValueError(
            "epoch_handoff.event_label_aliases must map strings to strings"
        )
    return deepcopy(raw_handoff)


def build_epoching_context(
    data_list: list[Any],
    *,
    epoch_handoff: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return UI/headless context for creating epochs from preprocessed data."""
    event_rows = _available_events(data_list)
    event_names = [row["name"] for row in event_rows]
    hint_read = _read_epoch_hints(data_list)
    hint = _aggregate_epoch_hints(list(hint_read.hints))
    recommended_events = _recommended_events(hint, event_names)
    sampling_frequencies = _sampling_frequencies_hz(data_list)
    suggestion = _suggested_window(
        hint,
        sampling_frequencies_hz=sampling_frequencies,
    )
    placement_method = str(hint.get("placement_method") or "").strip()
    source = str(hint.get("source") or "").strip() or "Manual EEG epoch setup"
    handoff_provided = epoch_handoff is not None
    handoff = validated_epoch_handoff(epoch_handoff or {})
    availability = _evaluate_epoch_context_availability(
        hint_read=hint_read,
        hint=hint,
        handoff=handoff,
        handoff_provided=handoff_provided,
        suggestion=suggestion,
        sampling_frequencies_hz=sampling_frequencies,
    )
    context = {
        "source": source,
        "placement_method": placement_method or "manual",
        "placement_label": _placement_label(placement_method),
        "label_field": str(hint.get("label_field") or "").strip(),
        "time_field": str(hint.get("time_field") or "").strip(),
        "duration_field": str(hint.get("duration_field") or "").strip(),
        "duration_stats": dict(hint.get("duration_stats") or {}),
        "sampling_frequencies_hz": sampling_frequencies,
        "requires_common_sampling_frequency": len(sampling_frequencies) > 1,
        "available_events": event_rows,
        "recommended_events": recommended_events,
        "suggested_t_min": suggestion.t_min,
        "suggested_t_max": suggestion.t_max,
        "suggested_t_max_decimals": _tmax_decimal_places(
            suggestion.t_max,
            sampling_frequencies_hz=sampling_frequencies,
        ),
        "suggested_baseline": suggestion.baseline,
        "window_evidence": suggestion.evidence,
        "window_warning": suggestion.warning,
        "window_confirmation_message": suggestion.confirmation_message,
        # Keep the proposed display mode available to diagnostics and reports.
        # Admission still depends exclusively on context_availability below.
        "window_mode": suggestion.mode,
        "window_explanation": suggestion.explanation,
        "has_import_hint": bool(hint),
        "epoch_handoff": handoff if handoff_provided else None,
        "handoff_ready": bool(handoff.get("ready"))
        and not bool(handoff.get("supervised_blockers")),
        "handoff_blockers": [
            str(item).strip()
            for item in handoff.get("supervised_blockers", []) or []
            if str(item).strip()
        ],
        EPOCH_CONTEXT_AVAILABILITY_KEY: availability.to_payload(),
    }
    if not availability.available:
        context["recommended_events"] = []
    context["confirmation_context_fingerprint"] = (
        _epoch_confirmation_context_fingerprint(
            context,
            epoch_handoff=handoff,
        )
    )
    context["confirmation_requirement"] = (
        build_epoch_confirmation_requirement(
            context,
            t_min=suggestion.t_min,
            t_max=suggestion.t_max,
            event_ids=recommended_events,
        )
        if availability.available
        else None
    )
    return context


def build_epoch_confirmation_requirement(
    epoch_context: Mapping[str, Any],
    *,
    t_min: float,
    t_max: float,
    event_ids: list[str] | dict[str, int] | None,
) -> dict[str, Any] | None:
    """Issue one receipt for an exact risky BIDS epoch proposal."""
    require_epoch_context_available(epoch_context)
    message = str(epoch_context.get("window_confirmation_message") or "").strip()
    if not message:
        return None
    context_fingerprint = str(
        epoch_context.get("confirmation_context_fingerprint") or ""
    ).strip()
    if not context_fingerprint:
        raise ValueError("Epoch confirmation context fingerprint is required.")
    scope = {
        "t_min": _finite_required_float(t_min, "t_min"),
        "t_max": _finite_required_float(t_max, "t_max"),
        "selected_events": _selected_event_names(event_ids),
    }
    receipt_payload = {
        "version": EPOCH_CONFIRMATION_VERSION,
        "code": EPOCH_CONFIRMATION_CODE,
        "context_fingerprint": context_fingerprint,
        "scope": scope,
    }
    receipt = hmac.new(
        _EPOCH_CONFIRMATION_SECRET,
        fingerprint_resource_scope(receipt_payload).encode("ascii"),
        "sha256",
    ).hexdigest()
    return {
        **receipt_payload,
        "title": "Review BIDS event durations",
        "message": message,
        "confirmation_label": (
            "I reviewed this warning for this exact event selection and time window."
        ),
        "receipt": receipt,
    }


def _epoch_confirmation_context_fingerprint(
    context: Mapping[str, Any],
    *,
    epoch_handoff: Mapping[str, Any],
) -> str:
    payload = {
        "source": context.get("source"),
        "placement_method": context.get("placement_method"),
        "label_field": context.get("label_field"),
        "time_field": context.get("time_field"),
        "duration_field": context.get("duration_field"),
        "duration_stats": context.get("duration_stats"),
        "sampling_frequencies_hz": context.get("sampling_frequencies_hz"),
        "available_events": context.get("available_events"),
        EPOCH_CONTEXT_AVAILABILITY_KEY: context.get(EPOCH_CONTEXT_AVAILABILITY_KEY),
        "window_confirmation_message": context.get("window_confirmation_message"),
        "epoch_handoff": epoch_handoff,
    }
    return fingerprint_resource_scope(payload)


def epoch_handoff_matches_context(
    epoch_context: Mapping[str, Any],
    raw_handoff: object,
) -> bool:
    """Return whether one detached handoff belongs to this exact epoch context."""
    try:
        handoff = validated_epoch_handoff(raw_handoff)
    except ValueError:
        return False
    expected = str(epoch_context.get("confirmation_context_fingerprint") or "").strip()
    if not expected:
        return False
    actual = _epoch_confirmation_context_fingerprint(
        epoch_context,
        epoch_handoff=handoff,
    )
    return hmac.compare_digest(expected, actual)


def _selected_event_names(
    event_ids: list[str] | dict[str, int] | None,
) -> list[str]:
    values = event_ids.keys() if isinstance(event_ids, dict) else event_ids or []
    return sorted(
        {str(value).strip() for value in values if str(value).strip()},
        key=str.casefold,
    )


def _finite_required_float(value: Any, field_name: str) -> float:
    number = _finite_float(value)
    if number is None:
        raise ValueError(f"{field_name} must be finite.")
    return number


def _available_events(data_list: list[Any]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    seen: set[str] = set()
    unknown_count_names: set[str] = set()
    for data in data_list:
        with contextlib.suppress(Exception):
            events, event_id = data.get_event_list()
            if not isinstance(event_id, dict):
                continue
            event_values = _event_values(events)
            for name, event_code in event_id.items():
                event_name = str(name).strip()
                if not event_name:
                    continue
                seen.add(event_name)
                count = _count_event_code(event_values, event_code)
                if count is None:
                    unknown_count_names.add(event_name)
                else:
                    counts[event_name] += count
    return [
        {
            "name": name,
            "count": None if name in unknown_count_names else counts.get(name, 0),
        }
        for name in sorted(seen, key=_event_sort_key)
    ]


def _event_values(events: Any) -> np.ndarray | None:
    if events is None:
        return None
    try:
        array = np.asarray(events)
    except Exception:
        return None
    if array.ndim != 2 or array.shape[1] < 3:
        return None
    return array[:, -1]


def _count_event_code(event_values: np.ndarray | None, event_code: Any) -> int | None:
    if event_values is None:
        return None
    try:
        return int(np.sum(event_values == event_code))
    except Exception:
        return None


def _aggregate_epoch_hints(hints: list[dict[str, Any]]) -> dict[str, Any]:
    if not hints:
        return {}
    if len(hints) == 1:
        result = dict(hints[0])
        semantic_error = _epoch_hint_semantic_error(result)
        result["semantic_errors"] = [semantic_error] if semantic_error else []
        return result

    result: dict[str, Any] = {"hint_count": len(hints)}
    for field_name in (
        "source",
        "placement_method",
        "label_field",
        "time_field",
        "duration_field",
        "time_model",
        "granularity",
        "label_import_mode",
    ):
        values = _unique_text_values(hint.get(field_name) for hint in hints)
        if len(values) == 1:
            result[field_name] = values[0]

    result["class_map"] = _merge_text_mappings(hint.get("class_map") for hint in hints)
    result["event_roles"] = _merge_text_mappings(
        hint.get("event_roles") for hint in hints
    )
    recommended_events = {
        str(value).strip()
        for hint in hints
        for value in (
            list((hint.get("class_map") or {}).values())
            if isinstance(hint.get("class_map"), dict)
            else []
        )
        + list(hint.get("recommended_events") or [])
        if str(value).strip()
    }
    result["recommended_events"] = sorted(
        recommended_events,
        key=_event_sort_key,
    )
    duration_stats, duration_ranges = _aggregate_duration_stats(hints)
    result["duration_stats"] = duration_stats
    result["duration_ranges"] = duration_ranges
    result["placement_event_count"] = sum(
        _nonnegative_int(hint.get("placement_event_count")) for hint in hints
    )
    result["unknown_duration_count"] = sum(
        _nonnegative_int(hint.get("unknown_duration_count")) for hint in hints
    )
    semantic_errors = [
        error
        for hint in hints
        if (error := _epoch_hint_semantic_error(hint)) is not None
    ]
    for field_name in ("source", "placement_method"):
        values = _unique_text_values(hint.get(field_name) for hint in hints)
        if len(values) != 1:
            semantic_errors.append(
                f"selected recordings disagree about {field_name.replace('_', ' ')}"
            )
    if all(_hint_source_kind(hint) == "bids" for hint in hints):
        for field_name in ("time_field", "duration_field"):
            values = _unique_text_values(hint.get(field_name) for hint in hints)
            if len(values) != 1:
                semantic_errors.append(
                    f"selected BIDS runs disagree about {field_name.replace('_', ' ')}"
                )
    result["semantic_errors"] = sorted(set(semantic_errors), key=str.casefold)
    return result


def _epoch_hint_semantic_error(hint: Mapping[str, Any]) -> str | None:
    source_kind = _hint_source_kind(hint)
    placement_method = str(hint.get("placement_method") or "").strip()
    if source_kind is None or not placement_method:
        return "label source or event placement is incomplete"
    if source_kind != "bids" or placement_method != "interval":
        return None
    if not str(hint.get("time_field") or "").strip():
        return "BIDS event onset field is missing"
    if not str(hint.get("duration_field") or "").strip():
        return "BIDS event duration field is missing"
    return None


def _read_epoch_hints(data_list: list[Any]) -> _EpochHintRead:
    hints: list[dict[str, Any]] = []
    missing_count = 0
    failed_count = 0
    for data in data_list:
        getter = getattr(data, "get_runtime_detail", None)
        if not callable(getter):
            missing_count += 1
            continue
        try:
            hint = getter(EPOCH_HINT_KEY)
        except Exception:
            failed_count += 1
            continue
        if isinstance(hint, dict) and hint:
            hints.append(dict(hint))
        else:
            missing_count += 1
    return _EpochHintRead(
        data_count=len(data_list),
        hints=tuple(hints),
        missing_count=missing_count,
        failed_count=failed_count,
    )


def _evaluate_epoch_context_availability(
    *,
    hint_read: _EpochHintRead,
    hint: dict[str, Any],
    handoff: dict[str, Any],
    handoff_provided: bool,
    suggestion: _EpochWindowSuggestion,
    sampling_frequencies_hz: list[float],
) -> EpochContextAvailability:
    unavailable = EpochContextAvailability.unavailable
    if hint_read.data_count <= 0:
        return unavailable(
            EpochContextAvailabilityCode.NO_DATA,
            "EEG epoch setup needs review because no preprocessed EEG data is "
            "available.",
        )
    sampling_frequency_reason = _sampling_frequency_warning(sampling_frequencies_hz)
    if sampling_frequency_reason:
        return unavailable(
            EpochContextAvailabilityCode.SAMPLING_FREQUENCY_MISMATCH,
            sampling_frequency_reason,
        )
    if hint_read.failed_count:
        return unavailable(
            EpochContextAvailabilityCode.HINT_READ_FAILED,
            "EEG epoch setup needs review because imported event timing could not "
            "be read. Reopen Data Import and review the applied interpretation.",
        )
    if hint_read.missing_count or len(hint_read.hints) != hint_read.data_count:
        return unavailable(
            EpochContextAvailabilityCode.HINT_MISSING,
            "EEG epoch setup needs review because the applied import does not "
            "provide event timing for every selected recording.",
        )

    source_kind = _hint_source_kind(hint)
    placement_method = str(hint.get("placement_method") or "").strip()
    semantic_errors = [
        str(item).strip()
        for item in hint.get("semantic_errors", []) or []
        if str(item).strip()
    ]
    if source_kind is None or not placement_method or semantic_errors:
        return unavailable(
            EpochContextAvailabilityCode.HINT_SEMANTICS_INVALID,
            "EEG epoch setup needs review because selected recordings disagree "
            "about label source, event placement, or timing evidence."
            + (f" Details: {'; '.join(semantic_errors)}." if semantic_errors else ""),
        )
    if not handoff_provided or not handoff:
        return unavailable(
            EpochContextAvailabilityCode.HANDOFF_UNAVAILABLE,
            "EEG epoch setup needs review because the applied import state is "
            "unavailable.",
        )
    blockers = [
        str(item).strip()
        for item in handoff.get("supervised_blockers", []) or []
        if str(item).strip()
    ]
    if handoff.get("ready") is not True or blockers:
        return unavailable(
            EpochContextAvailabilityCode.HANDOFF_UNAVAILABLE,
            "; ".join(blockers)
            or "EEG epoch setup needs review before the applied import can be used.",
        )

    handoff_source_kind = _handoff_source_kind(handoff.get("label_source"))
    if handoff_source_kind != source_kind:
        return unavailable(
            EpochContextAvailabilityCode.HANDOFF_SOURCE_MISMATCH,
            "EEG epoch setup needs review because the applied label source does not "
            "match the runtime event timing source.",
        )
    placement_modes = {
        str(item).strip()
        for item in handoff.get("placement_modes", []) or []
        if str(item).strip()
    }
    if handoff_source_kind == "internal" and not placement_modes:
        placement_modes.add("internal_events")
    if placement_method not in placement_modes:
        return unavailable(
            EpochContextAvailabilityCode.HANDOFF_PLACEMENT_MISMATCH,
            "EEG epoch setup needs review because the applied label placement does "
            "not match the runtime event timing placement.",
        )
    if suggestion.mode is None:
        return unavailable(
            EpochContextAvailabilityCode.DURATION_UNAVAILABLE,
            suggestion.unavailable_reason
            or "EEG epoch setup needs review because interval duration is unavailable.",
        )
    return EpochContextAvailability.ready(
        window_mode=suggestion.mode,
        window_explanation=suggestion.explanation,
    )


def _hint_source_kind(hint: Mapping[str, Any]) -> str | None:
    source = str(hint.get("source") or "").strip().casefold()
    placement = str(hint.get("placement_method") or "").strip()
    if "bids" in source and "event" in source:
        return "bids"
    if placement == "internal_events" and "inside eeg" in source:
        return "internal"
    if source and placement in {"eeg_event", "event_code", "interval", "time_field"}:
        return "external"
    return None


def _handoff_source_kind(value: object) -> str | None:
    source = str(value or "").strip()
    if source == "bids_events":
        return "bids"
    if source in {"embedded_events", "internal_events"}:
        return "internal"
    if source in {"external_files", "loaded_label_files"}:
        return "external"
    return None


def _unique_text_values(values: Any) -> list[str]:
    return sorted(
        {str(value).strip() for value in values if str(value or "").strip()},
        key=str.casefold,
    )


def _merge_text_mappings(values: Any) -> dict[str, str]:
    pairs = sorted(
        {
            (str(key).strip(), str(value).strip())
            for mapping in values
            if isinstance(mapping, dict)
            for key, value in mapping.items()
            if str(key).strip() and str(value).strip()
        },
        key=lambda item: (item[0].casefold(), item[1].casefold()),
    )
    result: dict[str, str] = {}
    for key, value in pairs:
        result.setdefault(key, value)
    return result


def _aggregate_duration_stats(
    hints: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, float]]]:
    stats_rows = [
        stats
        for hint in hints
        if isinstance((stats := hint.get("duration_stats")), dict)
    ]
    if not stats_rows:
        return {}, []

    minima = [
        value
        for stats in stats_rows
        if (value := _finite_float(stats.get("min"))) is not None
    ]
    maxima = [
        value
        for stats in stats_rows
        if (value := _finite_float(stats.get("max"))) is not None
    ]
    duration_ranges = sorted(
        [
            {"min": minimum, "max": maximum}
            for stats in stats_rows
            if (minimum := _finite_float(stats.get("min"))) is not None
            and (maximum := _finite_float(stats.get("max"))) is not None
        ],
        key=lambda item: (item["min"], item["max"]),
    )
    result: dict[str, Any] = {
        "numeric_count": sum(
            _nonnegative_int(stats.get("numeric_count")) for stats in stats_rows
        ),
        "min": min(minima) if minima else None,
        "max": max(maxima) if maxima else None,
    }
    if any("row_count" in stats for stats in stats_rows):
        result["row_count"] = sum(
            _nonnegative_int(stats.get("row_count")) for stats in stats_rows
        )
    value_counts: Counter[str] = Counter()
    for stats in stats_rows:
        counts = stats.get("value_counts")
        if not isinstance(counts, dict):
            continue
        for value, count in counts.items():
            value_counts[str(value)] += _nonnegative_int(count)
    if value_counts:
        result["value_counts"] = dict(sorted(value_counts.items()))
    return result, duration_ranges


def _recommended_events(hint: dict[str, Any], event_names: list[str]) -> list[str]:
    if not hint:
        return []
    class_map = hint.get("class_map")
    candidates: list[str] = []
    if isinstance(class_map, dict):
        for code, name in class_map.items():
            for value in (name, code):
                text = str(value).strip()
                if text and text not in candidates:
                    candidates.append(text)
    for raw_value in hint.get("recommended_events", []) or []:
        text = str(raw_value).strip()
        if text and text not in candidates:
            candidates.append(text)
    event_name_set = set(event_names)
    return [item for item in candidates if item in event_name_set]


def _bids_duration_evidence_status(hint: Mapping[str, Any]) -> str:
    """Classify reviewed BIDS duration evidence without guessing missing rows."""
    stats = hint.get("duration_stats")
    if not isinstance(stats, Mapping):
        return "invalid"
    placement_count = _strict_nonnegative_int(hint.get("placement_event_count"))
    unknown_count = _strict_nonnegative_int(hint.get("unknown_duration_count"))
    numeric_count = _strict_nonnegative_int(stats.get("numeric_count", 0))
    if (
        placement_count is None
        or placement_count <= 0
        or unknown_count is None
        or numeric_count is None
        or numeric_count + unknown_count != placement_count
    ):
        return "invalid"

    minimum = _finite_float(stats.get("min"))
    maximum = _finite_float(stats.get("max"))
    if numeric_count:
        if minimum is None or maximum is None or minimum < 0 or maximum < minimum:
            return "invalid"
        if unknown_count:
            return "unknown"
        return "positive" if maximum > 0 else "zero"
    if minimum is not None or maximum is not None:
        return "invalid"
    return "unknown" if unknown_count == placement_count else "invalid"


def _suggested_window(
    hint: dict[str, Any],
    *,
    sampling_frequencies_hz: list[float],
) -> _EpochWindowSuggestion:
    sampling_frequency_warning = _sampling_frequency_warning(sampling_frequencies_hz)
    placement_method = str(hint.get("placement_method") or "").strip()
    if placement_method == "interval":
        duration_stats = hint.get("duration_stats")
        duration_field = str(hint.get("duration_field") or "").strip()
        bids_duration_status = (
            _bids_duration_evidence_status(hint)
            if _is_bids_events_hint(hint)
            else "not_bids"
        )
        if bids_duration_status == "invalid":
            return _EpochWindowSuggestion(
                t_min=-0.2,
                t_max=1.0,
                baseline=(-0.2, 0.0),
                evidence="Imported BIDS duration evidence needs review.",
                mode=None,
                explanation="",
                warning=sampling_frequency_warning,
                confirmation_message="",
                unavailable_reason=(
                    "EEG epoch setup needs review because imported BIDS duration "
                    "evidence is missing, contradictory, or only partially covered."
                ),
            )
        max_duration = _positive_float(
            duration_stats.get("max") if isinstance(duration_stats, dict) else None
        )
        min_duration = _positive_float(
            duration_stats.get("min") if isinstance(duration_stats, dict) else None
        )
        if max_duration is not None:
            hint_count = _nonnegative_int(hint.get("hint_count"))
            multi_run_bids = hint_count > 1 and _is_bids_events_hint(hint)
            warning = _combined_duration_policy_warning(
                hint,
                min_duration=min_duration,
                max_duration=max_duration,
                multi_run_bids=multi_run_bids,
            )
            confirmation_message = warning if _is_bids_events_hint(hint) else ""
            evidence = f"Suggested from imported {duration_field} field."
            if multi_run_bids:
                evidence = (
                    f"Suggested from imported {duration_field} field across all "
                    f"{hint_count} selected runs; fixed EEG epochs use the longest "
                    "observed duration."
                )
            suggested_t_max = max_duration
            if _is_bids_events_hint(hint) and len(sampling_frequencies_hz) == 1:
                suggested_t_max = _inclusive_tmax_for_half_open_duration(
                    max_duration,
                    sampling_frequencies_hz=sampling_frequencies_hz,
                )
            warning = " ".join(
                part for part in (sampling_frequency_warning, warning) if part
            )
            return _EpochWindowSuggestion(
                t_min=0.0,
                t_max=suggested_t_max,
                baseline=None,
                evidence=evidence,
                mode=EpochWindowMode.DURATION,
                explanation=(
                    "Use one fixed window. Epochs start at onset and end at the "
                    "largest reviewed event duration."
                ),
                warning=warning,
                confirmation_message=confirmation_message,
            )
        if bids_duration_status in {"zero", "unknown"}:
            reason = (
                "reviewed events have zero duration"
                if bids_duration_status == "zero"
                else "reviewed event durations are unknown"
            )
            return _EpochWindowSuggestion(
                t_min=-0.2,
                t_max=1.0,
                baseline=(-0.2, 0.0),
                evidence=(
                    f"The {duration_field} field shows that {reason}; using an "
                    "event-locked review default."
                ),
                mode=EpochWindowMode.EVENT_LOCKED,
                explanation=(
                    "Event-locked window. EEG epochs are anchored to each reviewed "
                    "BIDS event onset; the analysis window remains a user decision."
                ),
                warning=sampling_frequency_warning,
                confirmation_message="",
            )
        return _EpochWindowSuggestion(
            t_min=0.0,
            t_max=1.0,
            baseline=None,
            evidence="No positive imported interval duration is available.",
            mode=None,
            explanation="",
            warning=sampling_frequency_warning,
            confirmation_message="",
            unavailable_reason=(
                "EEG epoch setup needs review because imported interval labels do "
                "not provide a positive duration. Review the duration field in Data "
                "Import before creating EEG epochs."
            ),
        )
    explanation = (
        "Event-locked window. EEG epochs are anchored to each reviewed event onset."
    )
    if _is_bids_events_hint(hint):
        explanation = (
            "Event-locked window. EEG epochs are anchored to each reviewed BIDS "
            "event onset; the analysis window remains a user decision."
        )
    return _EpochWindowSuggestion(
        t_min=-0.2,
        t_max=1.0,
        baseline=(-0.2, 0.0),
        evidence="standard event-locked review default",
        mode=EpochWindowMode.EVENT_LOCKED,
        explanation=explanation,
        warning=sampling_frequency_warning,
        confirmation_message="",
    )


def _sampling_frequency_warning(sampling_frequencies_hz: list[float]) -> str:
    if len(sampling_frequencies_hz) <= 1:
        return ""
    frequencies = ", ".join(
        f"{frequency:g} Hz" for frequency in sampling_frequencies_hz
    )
    return (
        "Selected EEG files use different sampling frequencies "
        f"({frequencies}). Resample them to one shared rate before creating epochs."
    )


def _sampling_frequencies_hz(data_list: list[Any]) -> list[float]:
    values: set[float] = set()
    for data in data_list:
        value = _sampling_frequency_hz(data)
        if value is not None:
            values.add(value)
    return sorted(values)


def _sampling_frequency_hz(data: Any) -> float | None:
    getter = getattr(data, "get_sfreq", None)
    if callable(getter):
        with contextlib.suppress(Exception):
            value = _real_sampling_frequency(getter())
            if value is not None:
                return value

    get_mne = getattr(data, "get_mne", None)
    if not callable(get_mne):
        return None
    with contextlib.suppress(Exception):
        mne_data = get_mne()
        info = getattr(mne_data, "info", None)
        if info is not None:
            value = _real_sampling_frequency(info["sfreq"])
            if value is not None:
                return value
    return None


def _real_sampling_frequency(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    return _positive_float(value)


def _inclusive_tmax_for_half_open_duration(
    duration: float,
    *,
    sampling_frequencies_hz: list[float],
) -> float:
    """Map ``[0, duration)`` to an inclusive MNE ``tmax`` sample."""
    if len(sampling_frequencies_hz) != 1:
        return duration
    sfreq = sampling_frequencies_hz[0]
    return _last_included_sample_offset(duration, sfreq) / sfreq


def _last_included_sample_offset(duration: float, sfreq: float) -> int:
    """Return the final sample offset strictly before a half-open interval end."""
    try:
        scaled_duration = Decimal(str(duration)) * Decimal(str(sfreq))
        sample_count = int(scaled_duration.to_integral_value(rounding=ROUND_CEILING))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Duration and sampling frequency must be finite.") from exc
    return max(sample_count - 1, 0)


def _tmax_decimal_places(
    tmax: float,
    *,
    sampling_frequencies_hz: list[float],
) -> int:
    """Keep Qt spinbox rounding on the same MNE sample offset."""
    if len(sampling_frequencies_hz) != 1:
        return 2
    expected_offsets = [round(tmax * sfreq) for sfreq in sampling_frequencies_hz]
    decimal_value = Decimal(str(tmax))
    for places in range(2, 10):
        quantum = Decimal(1).scaleb(-places)
        displayed = float(decimal_value.quantize(quantum, rounding=ROUND_HALF_UP))
        if all(
            round(displayed * sfreq) == expected
            for sfreq, expected in zip(
                sampling_frequencies_hz,
                expected_offsets,
                strict=True,
            )
        ):
            return places
    return 9


def _is_bids_events_hint(hint: dict[str, Any]) -> bool:
    source = str(hint.get("source") or "").casefold()
    return "bids" in source and "event" in source


def _duration_policy_warning(
    min_duration: float | None,
    max_duration: float,
) -> str:
    if max_duration > 10:
        return (
            "Some BIDS event durations are longer than 10 seconds; review the "
            "EEG epoch window before training."
        )
    if (
        min_duration is not None
        and min_duration > 0
        and max_duration / min_duration > 3
    ):
        return (
            "BIDS event durations vary by more than 3x; review the EEG epoch window "
            "before training."
        )
    return ""


def _combined_duration_policy_warning(
    hint: dict[str, Any],
    *,
    min_duration: float | None,
    max_duration: float,
    multi_run_bids: bool,
) -> str:
    messages: list[str] = []
    ranges = hint.get("duration_ranges")
    if multi_run_bids and isinstance(ranges, list):
        unique_ranges = {
            (row.get("min"), row.get("max")) for row in ranges if isinstance(row, dict)
        }
        if len(unique_ranges) > 1:
            messages.append(
                "Selected BIDS runs have different duration ranges; fixed EEG epochs "
                "use the longest observed duration across all selected runs."
            )
    generic_warning = _duration_policy_warning(min_duration, max_duration)
    if generic_warning:
        messages.append(generic_warning)
    return " ".join(messages)


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number) or number <= 0:
        return None
    return number


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _nonnegative_int(value: Any) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _strict_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _placement_label(method: str) -> str:
    return {
        "internal_events": "Events inside EEG files",
        "eeg_event": "EEG event order",
        "time_field": "Label time",
        "interval": "Label interval",
        "event_code": "Label event code",
    }.get(method, "Manual event selection")


def _event_sort_key(value: str) -> tuple[int, int | str]:
    text = str(value).strip()
    if text.isdigit():
        return (0, int(text))
    return (1, text.casefold())
