"""Per-value semantic decisions for external label and event carriers."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from numbers import Real
from typing import Any

EVENT_VALUE_ROLES = frozenset(
    {
        "stimulus",
        "response",
        "artifact",
        "boundary",
        "system",
        "annotation",
        "unknown",
    }
)
RESOLVED = "resolved"
UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class EventValueReview:
    """Observed values reconciled with explicit or domain-owned decisions."""

    decisions: dict[str, dict[str, Any]] = field(default_factory=dict)
    unresolved_values: list[str] = field(default_factory=list)
    missing_values: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def review_event_values(
    *,
    value_counts: Mapping[Any, Any],
    selected_field: str,
    carrier_format: str,
    carrier_role: str,
    suggested_names: Mapping[Any, Any] | None,
    choices: Mapping[Any, Any] | None,
) -> EventValueReview:
    """Build one complete decision row for every currently observed raw value."""
    counts = _normalized_counts(value_counts)
    choice_rows = _normalized_choice_rows(choices)
    suggestions = _normalized_string_mapping(suggested_names)
    observed_values = _sorted_values(counts)
    missing_values = _sorted_values(set(choice_rows) - set(counts))
    decisions: dict[str, dict[str, Any]] = {}
    unresolved: list[str] = []

    for raw_value in observed_values:
        explicit = choice_rows.get(raw_value)
        suggested_name = str(
            (explicit or {}).get("suggested_name")
            or suggestions.get(raw_value)
            or raw_value
        ).strip()
        if explicit is not None:
            decision = _review_explicit_decision(
                explicit,
                suggested_name=suggested_name,
                count=counts[raw_value],
            )
        elif _is_generic_simple_class_label_series(
            selected_field=selected_field,
            carrier_format=carrier_format,
            carrier_role=carrier_role,
        ):
            decision = {
                "role": "unknown",
                "keep_event": True,
                "use_as_class": True,
                "class_name": suggested_name,
                "suggested_name": suggested_name,
                "decision": RESOLVED,
                "decision_source": "format_domain_rule",
                "provenance": (
                    "generic_simple_class_label_series:" + str(selected_field).strip()
                ),
                "count": counts[raw_value],
            }
        else:
            decision = {
                "role": "unknown",
                "keep_event": None,
                "use_as_class": None,
                "suggested_name": suggested_name,
                "decision": UNRESOLVED,
                "decision_source": "unresolved",
                "provenance": (
                    f"observed:{str(carrier_format).strip()}:"
                    f"{str(selected_field).strip()}"
                ),
                "count": counts[raw_value],
            }
        decisions[raw_value] = decision
        if decision["decision"] != RESOLVED:
            unresolved.append(raw_value)

    warnings = [
        "Saved event value is no longer present in the selected field: " + value + "."
        for value in missing_values
    ]
    return EventValueReview(
        decisions=decisions,
        unresolved_values=unresolved,
        missing_values=missing_values,
        warnings=warnings,
    )


def class_map_from_value_decisions(
    decisions: Mapping[Any, Any] | None,
) -> dict[str, str]:
    """Return the class view selected by resolved ``use_as_class`` decisions."""
    result: dict[str, str] = {}
    for raw_value in _sorted_values((decisions or {}).keys()):
        payload = (decisions or {}).get(raw_value)
        if not isinstance(payload, Mapping):
            continue
        class_name = str(payload.get("class_name") or "").strip()
        if (
            payload.get("decision") == RESOLVED
            and payload.get("keep_event") is True
            and payload.get("use_as_class") is True
            and class_name
        ):
            result[raw_value] = class_name
    return result


def derive_class_views(
    carrier_plans: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Derive collision-safe global and per-carrier/run class-map views."""
    observed_targets: dict[str, set[str]] = {}
    run_maps: dict[str, dict[str, str]] = {}
    for plan in carrier_plans:
        mapping = class_map_from_value_decisions(
            plan.get("value_decisions")
            if isinstance(plan.get("value_decisions"), Mapping)
            else {}
        )
        if not mapping:
            continue
        target = str(plan.get("selected_target_file") or plan.get("path") or "").strip()
        if target:
            run_maps[target] = mapping
        for raw_value, class_name in mapping.items():
            observed_targets.setdefault(raw_value, set()).add(class_name)
    global_map = {
        raw_value: next(iter(names))
        for raw_value, names in sorted(observed_targets.items())
        if len(names) == 1
    }
    return global_map, run_maps


def build_event_catalog(
    carrier_plans: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Flatten per-carrier decisions without losing carrier/run identity."""
    rows: list[dict[str, Any]] = []
    for plan in carrier_plans:
        decisions = plan.get("value_decisions")
        if not isinstance(decisions, Mapping):
            continue
        carrier = str(plan.get("path") or "").strip()
        target_file = str(plan.get("selected_target_file") or "").strip()
        field_name = str(plan.get("selected_label_field") or "").strip()
        for raw_value in _sorted_values(decisions.keys()):
            payload = decisions.get(raw_value)
            if not isinstance(payload, Mapping):
                continue
            row = {
                "raw_value": raw_value,
                "carrier": carrier,
                "target_file": target_file,
                "field": field_name,
                **{str(key): value for key, value in payload.items()},
            }
            rows.append(row)
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("target_file") or ""),
            str(row.get("carrier") or ""),
            _value_sort_key(str(row.get("raw_value") or "")),
        ),
    )


def class_targets_from_event_catalog(
    event_catalog: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return supervised targets selected from the full kept-event catalog."""
    targets: list[dict[str, Any]] = []
    for row in event_catalog:
        class_name = str(row.get("class_name") or "").strip()
        if (
            row.get("decision") != RESOLVED
            or row.get("keep_event") is not True
            or row.get("use_as_class") is not True
            or not class_name
        ):
            continue
        targets.append(
            {
                "event": class_name,
                "class_name": class_name,
                "raw_value": str(row.get("raw_value") or ""),
                "role": str(row.get("role") or "unknown"),
                "carrier": str(row.get("carrier") or ""),
                "target_file": str(row.get("target_file") or ""),
                "field": str(row.get("field") or ""),
                "count": int(row.get("count") or 0),
                "decision_source": str(row.get("decision_source") or ""),
                "provenance": str(row.get("provenance") or ""),
            }
        )
    return targets


def filter_kept_label_values(
    values: Iterable[Any],
    decisions: Mapping[Any, Any],
) -> list[Any]:
    """Keep only values explicitly resolved with ``keep_event=true``."""
    normalized = {
        _normalized_raw_value(key): value
        for key, value in decisions.items()
        if _normalized_raw_value(key)
    }
    kept: list[Any] = []
    for value in values:
        raw_value = _normalized_raw_value(value)
        decision = normalized.get(raw_value)
        if not isinstance(decision, Mapping) or decision.get("decision") != RESOLVED:
            raise ValueError(f"Event value has no resolved decision: {raw_value}.")
        if decision.get("keep_event") is True:
            kept.append(value)
    return kept


def unresolved_values_for_plan(plan: Mapping[str, Any]) -> list[str]:
    """Return observed values whose semantic decision is incomplete."""
    decisions = plan.get("value_decisions")
    if not isinstance(decisions, Mapping):
        counts = plan.get("label_value_counts")
        if isinstance(counts, Mapping) and counts:
            return _sorted_values(counts.keys())
        return []
    return [
        raw_value
        for raw_value in _sorted_values(decisions.keys())
        if not isinstance(decisions.get(raw_value), Mapping)
        or decisions[raw_value].get("decision") != RESOLVED
    ]


def _review_explicit_decision(
    payload: Mapping[str, Any],
    *,
    suggested_name: str,
    count: int,
) -> dict[str, Any]:
    raw_role = str(payload.get("role") or "").strip().lower()
    role = raw_role if raw_role in EVENT_VALUE_ROLES else "unknown"
    keep_event = payload.get("keep_event")
    use_as_class = payload.get("use_as_class")
    class_name = str(payload.get("class_name") or "").strip()
    complete = (
        raw_role in EVENT_VALUE_ROLES
        and isinstance(keep_event, bool)
        and isinstance(use_as_class, bool)
        and (not use_as_class or bool(class_name))
    )
    decision: dict[str, Any] = {
        "role": role,
        "keep_event": keep_event if isinstance(keep_event, bool) else None,
        "use_as_class": use_as_class if isinstance(use_as_class, bool) else None,
        "suggested_name": suggested_name,
        "decision": RESOLVED if complete else UNRESOLVED,
        "decision_source": "user_choice" if complete else "user_choice_incomplete",
        "provenance": "label_carrier_choice",
        "count": count,
    }
    if complete and use_as_class:
        decision["class_name"] = class_name
    return decision


def _is_generic_simple_class_label_series(
    *,
    selected_field: str,
    carrier_format: str,
    carrier_role: str,
) -> bool:
    if str(carrier_format).strip().casefold() == "bids events":
        return False
    normalized_field = "".join(
        character for character in str(selected_field).casefold() if character.isalnum()
    )
    strong_fields = {
        "class",
        "classes",
        "classlabel",
        "classlabels",
        "labels",
        "linelabelsequence",
    }
    if normalized_field in strong_fields:
        return True
    normalized_role = " ".join(str(carrier_role).casefold().replace("_", " ").split())
    return normalized_field in {"condition", "label", "target"} and normalized_role in {
        "class label",
        "class labels",
        "classification target",
    }


def _normalized_counts(payload: Mapping[Any, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for raw_value, raw_count in payload.items():
        value = _normalized_raw_value(raw_value)
        if not value:
            continue
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            continue
        if count > 0:
            result[value] = count
    return result


def _normalized_choice_rows(
    payload: Mapping[Any, Any] | None,
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        return {}
    return {
        _normalized_raw_value(raw_value): decision
        for raw_value, decision in payload.items()
        if _normalized_raw_value(raw_value) and isinstance(decision, Mapping)
    }


def _normalized_string_mapping(
    payload: Mapping[Any, Any] | None,
) -> dict[str, str]:
    if not isinstance(payload, Mapping):
        return {}
    return {
        str(key).strip(): str(value).strip()
        for key, value in payload.items()
        if str(key).strip() and str(value).strip()
    }


def _sorted_values(values: Iterable[Any]) -> list[str]:
    return sorted(
        {
            normalized
            for value in values
            if (normalized := _normalized_raw_value(value))
        },
        key=_value_sort_key,
    )


def _value_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value.casefold())


def _normalized_raw_value(value: Any) -> str:
    if isinstance(value, Real):
        numeric = float(value)
        if not math.isfinite(numeric):
            return ""
        return str(int(numeric)) if numeric.is_integer() else str(value).strip()
    text = str(value or "").strip()
    return "" if text.casefold() in {"n/a", "na", "nan", "null"} else text
