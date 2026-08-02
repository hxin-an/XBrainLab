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
from numbers import Real
from typing import Any

import numpy as np

from .capabilities import CommandCapability
from .errors import PreconditionError
from .resource_receipt import fingerprint_resource_scope

EPOCH_HINT_KEY = "data_interpretation_epoch_hint"
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
    hint = _aggregate_epoch_hints(data_list)
    recommended_events = _recommended_events(hint, event_names)
    sampling_frequencies = _sampling_frequencies_hz(data_list)
    (
        t_min,
        t_max,
        baseline,
        evidence,
        window_mode,
        window_warning,
        confirmation_message,
    ) = _suggested_window(hint, sampling_frequencies_hz=sampling_frequencies)
    placement_method = str(hint.get("placement_method") or "").strip()
    source = str(hint.get("source") or "").strip() or "Manual EEG epoch setup"
    handoff = validated_epoch_handoff(epoch_handoff or {})
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
        "suggested_t_min": t_min,
        "suggested_t_max": t_max,
        "suggested_t_max_decimals": _tmax_decimal_places(
            t_max,
            sampling_frequencies_hz=sampling_frequencies,
        ),
        "suggested_baseline": baseline,
        "window_evidence": evidence,
        "window_mode": window_mode,
        "window_warning": window_warning,
        "window_confirmation_message": confirmation_message,
        "has_import_hint": bool(hint),
    }
    context["confirmation_context_fingerprint"] = (
        _epoch_confirmation_context_fingerprint(
            context,
            epoch_handoff=handoff,
        )
    )
    context["confirmation_requirement"] = build_epoch_confirmation_requirement(
        context,
        t_min=t_min,
        t_max=t_max,
        event_ids=recommended_events,
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
        "window_mode": context.get("window_mode"),
        "window_confirmation_message": context.get("window_confirmation_message"),
        "epoch_handoff": epoch_handoff,
    }
    return fingerprint_resource_scope(payload)


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


def _aggregate_epoch_hints(data_list: list[Any]) -> dict[str, Any]:
    hints = _epoch_hints(data_list)
    if not hints:
        return {}
    if len(hints) == 1:
        return hints[0]

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
    return result


def _epoch_hints(data_list: list[Any]) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for data in data_list:
        getter = getattr(data, "get_runtime_detail", None)
        if not callable(getter):
            continue
        with contextlib.suppress(Exception):
            hint = getter(EPOCH_HINT_KEY)
            if isinstance(hint, dict) and hint:
                hints.append(dict(hint))
    return hints


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


def _suggested_window(
    hint: dict[str, Any],
    *,
    sampling_frequencies_hz: list[float],
) -> tuple[
    float,
    float,
    tuple[float | None, float | None] | None,
    str,
    str,
    str,
    str,
]:
    sampling_frequency_warning = _sampling_frequency_warning(sampling_frequencies_hz)
    placement_method = str(hint.get("placement_method") or "").strip()
    if placement_method == "interval":
        duration_stats = hint.get("duration_stats")
        duration_field = str(hint.get("duration_field") or "duration").strip()
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
            return (
                0.0,
                suggested_t_max,
                None,
                evidence,
                "duration",
                warning,
                confirmation_message,
            )
        if _is_bids_events_hint(hint):
            return (
                -0.2,
                1.0,
                (-0.2, 0.0),
                (
                    f"{duration_field} field has no positive values; using "
                    "event-locked review default."
                ),
                "event_locked",
                sampling_frequency_warning,
                "",
            )
        return (
            0.0,
            1.0,
            None,
            "duration not available; using 1.0s review default",
            "duration",
            sampling_frequency_warning,
            "",
        )
    return (
        -0.2,
        1.0,
        (-0.2, 0.0),
        "standard event-locked review default",
        "event_locked",
        sampling_frequency_warning,
        "",
    )


def _sampling_frequency_warning(sampling_frequencies_hz: list[float]) -> str:
    if len(sampling_frequencies_hz) <= 1:
        return ""
    frequencies = ", ".join(
        f"{frequency:g} Hz" for frequency in sampling_frequencies_hz
    )
    return (
        "Selected EEG files use different sampling frequencies "
        f"({frequencies}). Resample them to one shared rate before creating EEG epochs."
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
