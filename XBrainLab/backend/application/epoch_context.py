"""Build epoch setup context from imported label and event interpretation."""

from __future__ import annotations

import contextlib
from collections import Counter
from typing import Any

import numpy as np

EPOCH_HINT_KEY = "data_interpretation_epoch_hint"


def build_epoching_context(data_list: list[Any]) -> dict[str, Any]:
    """Return UI/headless context for creating epochs from preprocessed data."""
    event_rows = _available_events(data_list)
    event_names = [row["name"] for row in event_rows]
    hint = _first_epoch_hint(data_list)
    recommended_events = _recommended_events(hint, event_names)
    t_min, t_max, baseline, evidence = _suggested_window(hint)
    placement_method = str(hint.get("placement_method") or "").strip()
    source = str(hint.get("source") or "").strip() or "Manual epoch setup"
    return {
        "source": source,
        "placement_method": placement_method or "manual",
        "placement_label": _placement_label(placement_method),
        "label_field": str(hint.get("label_field") or "").strip(),
        "time_field": str(hint.get("time_field") or "").strip(),
        "duration_field": str(hint.get("duration_field") or "").strip(),
        "available_events": event_rows,
        "recommended_events": recommended_events,
        "suggested_t_min": t_min,
        "suggested_t_max": t_max,
        "suggested_baseline": baseline,
        "window_evidence": evidence,
        "has_import_hint": bool(hint),
    }


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


def _first_epoch_hint(data_list: list[Any]) -> dict[str, Any]:
    for data in data_list:
        getter = getattr(data, "get_runtime_detail", None)
        if not callable(getter):
            continue
        with contextlib.suppress(Exception):
            hint = getter(EPOCH_HINT_KEY)
            if isinstance(hint, dict) and hint:
                return dict(hint)
    return {}


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
) -> tuple[float, float, tuple[float | None, float | None] | None, str]:
    placement_method = str(hint.get("placement_method") or "").strip()
    if placement_method == "interval":
        duration_stats = hint.get("duration_stats")
        duration_field = str(hint.get("duration_field") or "duration").strip()
        max_duration = _positive_float(
            duration_stats.get("max") if isinstance(duration_stats, dict) else None
        )
        if max_duration is not None:
            return (
                0.0,
                max_duration,
                None,
                f"duration max {max_duration:g}s from {duration_field}",
            )
        return 0.0, 1.0, None, "duration not available; using 1.0s review default"
    return -0.2, 1.0, (-0.2, 0.0), "standard event-locked review default"


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number) or number <= 0:
        return None
    return number


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
