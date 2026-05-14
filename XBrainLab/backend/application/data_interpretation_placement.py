"""Placement evidence for external label carriers."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any


def annotate_label_carrier_placements(
    label_carrier_plan: list[dict[str, Any]],
    internal_event_preview: dict[str, Any],
) -> list[dict[str, Any]]:
    """Attach method-specific placement evidence to every label carrier plan."""
    event_rows = _event_rows(internal_event_preview)
    result: list[dict[str, Any]] = []
    for carrier in label_carrier_plan:
        item = dict(carrier)
        reviews = {
            "eeg_event": _eeg_event_order_review(item, event_rows),
            "time_field": _time_field_review(item),
            "interval": _interval_review(item),
            "event_code": _event_code_review(item, event_rows),
        }
        method = str(item.get("placement_method") or "eeg_event").strip()
        item["placement_reviews"] = reviews
        item["placement_review"] = reviews.get(method, reviews["eeg_event"])
        result.append(item)
    return result


def placement_confirmation_items(
    label_carrier_plan: list[dict[str, Any]],
) -> list[str]:
    """Return concise review prompts for placement choices needing attention."""
    items: list[str] = []
    for carrier in label_carrier_plan:
        review = carrier.get("placement_review")
        if not isinstance(review, dict):
            continue
        status = str(review.get("status") or "").strip()
        if status not in {"needs_review", "blocked"}:
            continue
        name = str(carrier.get("name") or Path(str(carrier.get("path") or "")).name)
        summary = str(review.get("summary") or "Review label placement.").strip()
        items.append(f"Confirm label placement for {name}: {summary}")
    return sorted(set(items))


def _eeg_event_order_review(
    carrier: dict[str, Any],
    event_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    label_rows = _positive_int(carrier.get("label_row_count"))
    target_codes = _target_event_codes(carrier)
    review = _base_review("eeg_event", carrier)
    review["target_event"] = target_codes[0] if target_codes else ""
    review["target_events"] = target_codes
    review["label_rows"] = label_rows
    review["excluded_eeg_events"] = _excluded_event_count(event_rows)
    if not target_codes:
        review.update(
            {
                "status": "needs_review",
                "summary": "Choose the EEG events that label rows follow in order.",
                "next_action": "Select one or more target EEG events.",
            }
        )
        return review
    events = [(code, _event_row_by_code(event_rows, code)) for code in target_codes]
    missing = [code for code, event in events if event is None]
    if missing:
        review.update(
            {
                "status": "blocked",
                "summary": (
                    "Target EEG event(s) were not found: " + ", ".join(missing) + "."
                ),
                "next_action": "Choose EEG events present in the selected files.",
            }
        )
        return review
    event_counts = [_event_count(event) for _code, event in events if event is not None]
    event_count = (
        sum(value for value in event_counts if value is not None)
        if all(value is not None for value in event_counts)
        else None
    )
    review["selected_eeg_events"] = event_count
    if label_rows is None or event_count is None:
        review.update(
            {
                "status": "needs_review",
                "summary": "Label rows or target EEG event count is unknown.",
                "next_action": "Review the label field and target EEG event count.",
            }
        )
        return review
    matched = min(label_rows, event_count)
    review["matched"] = matched
    review["unmatched_label_rows"] = max(label_rows - event_count, 0)
    review["unlabeled_eeg_events"] = max(event_count - label_rows, 0)
    if label_rows == event_count:
        status = "ready"
        summary = f"{matched} label rows match {event_count} selected EEG events."
        next_action = "Confirm the target event selection."
    elif event_count > label_rows:
        difference = event_count - label_rows
        noun = "event" if difference == 1 else "events"
        verb = "has" if difference == 1 else "have"
        status = "needs_review"
        summary = (
            f"{difference} selected EEG {noun} {verb} no label "
            f"({label_rows} label rows, {event_count} selected events)."
        )
        next_action = (
            "Uncheck extra target events or choose a label field with more rows."
        )
    else:
        difference = label_rows - event_count
        noun = "row" if difference == 1 else "rows"
        verb = "has" if difference == 1 else "have"
        status = "needs_review"
        summary = (
            f"{difference} label {noun} {verb} no selected EEG event "
            f"({label_rows} label rows, {event_count} selected events)."
        )
        next_action = (
            "Select more target events or check whether the label file has extra rows."
        )
    review.update(
        {
            "status": status,
            "summary": summary,
            "next_action": next_action,
        }
    )
    return review


def _target_event_codes(carrier: dict[str, Any]) -> list[str]:
    result: list[str] = []
    raw_codes = carrier.get("selected_target_event_codes")
    if isinstance(raw_codes, str):
        values: Iterable[Any] = raw_codes.split(",")
    elif isinstance(raw_codes, (list, tuple, set)):
        values = raw_codes
    else:
        values = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    if result:
        return result
    target = str(carrier.get("selected_anchor") or "").strip()
    if target and target != "trial order":
        return [target]
    return []


def _time_field_review(carrier: dict[str, Any]) -> dict[str, Any]:
    review = _base_review("time_field", carrier)
    field = str(carrier.get("selected_anchor") or "").strip()
    stats = _dict(carrier.get("selected_anchor_stats"))
    label_rows = _positive_int(carrier.get("label_row_count"))
    review.update(
        {
            "time_field": field,
            "label_rows": label_rows,
            "numeric_rows": _positive_int(stats.get("numeric_count")) or 0,
            "time_min": stats.get("min"),
            "time_max": stats.get("max"),
            "time_model": str(carrier.get("time_model") or ""),
        }
    )
    if not field:
        review.update(
            {
                "status": "blocked",
                "summary": "No label time field is selected.",
                "next_action": "Choose a time, onset, sample, or latency field.",
            }
        )
        return review
    numeric_rows = int(review["numeric_rows"])
    if not numeric_rows:
        review.update(
            {
                "status": "blocked",
                "summary": f"{field} does not contain numeric time values.",
                "next_action": "Choose a numeric time/sample field.",
            }
        )
        return review
    status = "ready" if label_rows in {None, numeric_rows} else "needs_review"
    review.update(
        {
            "status": status,
            "summary": _numeric_field_summary(field, numeric_rows, label_rows, stats),
            "next_action": "Confirm the time base before epoch setup.",
        }
    )
    return review


def _interval_review(carrier: dict[str, Any]) -> dict[str, Any]:
    review = _time_field_review(carrier)
    review["method"] = "interval"
    duration = str(carrier.get("selected_duration_field") or "").strip()
    duration_stats = _dict(carrier.get("selected_duration_stats"))
    duration_numeric = _positive_int(duration_stats.get("numeric_count")) or 0
    review.update(
        {
            "duration_field": duration,
            "duration_numeric_rows": duration_numeric,
            "duration_min": duration_stats.get("min"),
            "duration_max": duration_stats.get("max"),
        }
    )
    if review.get("status") == "blocked":
        return review
    if not duration:
        review.update(
            {
                "status": "needs_review",
                "summary": "Interval placement needs a duration or end field.",
                "next_action": "Choose a duration, end, offset, or stop field.",
            }
        )
        return review
    label_rows = _positive_int(carrier.get("label_row_count"))
    if not duration_numeric:
        review.update(
            {
                "status": "blocked",
                "summary": f"{duration} does not contain numeric duration/end values.",
                "next_action": "Choose a numeric duration or end field.",
            }
        )
        return review
    status = "ready" if label_rows in {None, duration_numeric} else "needs_review"
    start = str(review.get("time_field") or "")
    review.update(
        {
            "status": status,
            "summary": (
                f"{duration_numeric} interval rows using {start} and {duration}."
            ),
            "next_action": "Confirm interval semantics before epoch setup.",
        }
    )
    return review


def _event_code_review(
    carrier: dict[str, Any],
    event_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    review = _base_review("event_code", carrier)
    field = str(carrier.get("selected_anchor") or "").strip()
    stats = _dict(carrier.get("selected_anchor_stats"))
    label_rows = _positive_int(carrier.get("label_row_count"))
    value_counts = {
        str(key): int(value)
        for key, value in _dict(stats.get("value_counts")).items()
        if str(key).strip() and isinstance(value, int)
    }
    event_counts = {
        _event_code(row): _event_count(row)
        for row in event_rows
        if _event_code(row) and _event_count(row) is not None
    }
    matched_codes = sorted(
        [code for code in value_counts if code in event_counts],
        key=_code_sort_key,
    )
    missing_codes = sorted(
        [code for code in value_counts if code not in event_counts],
        key=_code_sort_key,
    )
    code_mappings = _event_code_mapping_rows(
        value_counts=value_counts,
        label_counts_by_code=_dict(carrier.get("event_code_label_counts")),
        event_counts=event_counts,
    )
    conflict_codes = [
        str(row.get("event_code") or "")
        for row in code_mappings
        if row.get("status") == "needs_review" and row.get("conflict")
    ]
    unlabeled_eeg_events = _unlabeled_eeg_event_rows(event_rows, value_counts)
    review.update(
        {
            "event_code_field": field,
            "label_rows": label_rows,
            "label_code_count": len(value_counts),
            "matched_code_count": len(matched_codes),
            "matched_codes": matched_codes,
            "missing_codes": missing_codes,
            "conflict_codes": conflict_codes,
            "code_mappings": code_mappings,
            "unlabeled_eeg_events": unlabeled_eeg_events,
        }
    )
    if not field:
        review.update(
            {
                "status": "blocked",
                "summary": "No label event-code field is selected.",
                "next_action": "Choose a label-file event code field.",
            }
        )
        return review
    if not value_counts:
        review.update(
            {
                "status": "blocked",
                "summary": f"{field} does not contain event-code values.",
                "next_action": "Choose a code, marker, trigger, or value field.",
            }
        )
        return review
    if not event_counts:
        review.update(
            {
                "status": "needs_review",
                "summary": "No EEG event-code preview is available for matching.",
                "next_action": "Review internal EEG events before applying.",
            }
        )
        return review
    if missing_codes or conflict_codes:
        parts = [
            f"{len(matched_codes)}/{len(value_counts)} label event codes "
            "were found in EEG events"
        ]
        if conflict_codes:
            parts.append(f"{len(conflict_codes)} code(s) map to multiple label values")
        review.update(
            {
                "status": "needs_review",
                "summary": "; ".join(parts) + ".",
                "next_action": (
                    "Map missing codes or fix code rows with conflicting labels."
                ),
            }
        )
        return review
    review.update(
        {
            "status": "ready",
            "summary": f"All {len(value_counts)} label event codes match EEG events.",
            "next_action": "Confirm code meanings before epoch setup.",
        }
    )
    return review


def _event_code_mapping_rows(
    *,
    value_counts: dict[str, int],
    label_counts_by_code: dict[str, Any],
    event_counts: dict[str, int | None],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for code in sorted(value_counts, key=_code_sort_key):
        label_counts = {
            str(label): int(count)
            for label, count in _dict(label_counts_by_code.get(code)).items()
            if str(label).strip() and isinstance(count, int)
        }
        label_values = sorted(label_counts, key=lambda item: (item.casefold(), item))
        conflict = len(label_values) > 1
        eeg_count = event_counts.get(code)
        missing = code not in event_counts
        if conflict:
            status = "needs_review"
            review = "Same code maps to multiple label values."
        elif missing:
            status = "needs_review"
            review = "Not found in EEG events."
        else:
            status = "ready"
            review = "Ready."
        rows.append(
            {
                "event_code": code,
                "label_values": label_values,
                "label_rows": sum(label_counts.values()) or value_counts.get(code),
                "eeg_event_count": eeg_count,
                "status": status,
                "conflict": conflict,
                "review": review,
            }
        )
    return rows


def _unlabeled_eeg_event_rows(
    event_rows: list[dict[str, Any]],
    value_counts: dict[str, int],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in event_rows:
        code = _event_code(row)
        if not code or code in value_counts:
            continue
        rows.append(
            {
                "event_code": code,
                "use_as": str(row.get("use_as") or row.get("reason") or "").strip(),
                "event_count": _event_count(row),
            }
        )
    return sorted(rows, key=lambda item: _code_sort_key(str(item["event_code"])))


def _base_review(method: str, carrier: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": method,
        "status": "needs_review",
        "label_field": str(carrier.get("selected_label_field") or ""),
        "summary": "Review label placement.",
        "next_action": "Review Match Labels.",
    }


def _event_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("not_used_events", "candidate_label_events", "candidate_events"):
        value = payload.get(key)
        if isinstance(value, list):
            rows.extend(dict(item) for item in value if isinstance(item, dict))
    return rows


def _event_row_by_code(
    rows: list[dict[str, Any]],
    code: str,
) -> dict[str, Any] | None:
    target = str(code or "").strip()
    if not target:
        return None
    for row in rows:
        if _event_code(row) == target:
            return row
    return None


def _event_code(row: dict[str, Any]) -> str:
    for key in ("event_code", "code", "original_event_code", "label"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _event_count(row: dict[str, Any]) -> int | None:
    for key in (
        "event_count",
        "total_events",
        "occurrence_count",
        "occurrences",
        "count",
        "total_count",
    ):
        value = _positive_int(row.get(key))
        if value is not None:
            return value
    return None


def _excluded_event_count(rows: list[dict[str, Any]]) -> int:
    total = 0
    for row in rows:
        text = " ".join(
            str(row.get(key) or "").lower() for key in ("use_as", "reason", "evidence")
        )
        if not any(
            token in text
            for token in (
                "artifact",
                "artefact",
                "boundary",
                "ignore",
                "system",
                "exclude",
                "bad",
            )
        ):
            continue
        total += _event_count(row) or 0
    return total


def _numeric_field_summary(
    field: str,
    numeric_rows: int,
    label_rows: int | None,
    stats: dict[str, Any],
) -> str:
    count_text = (
        f"{numeric_rows}/{label_rows} numeric rows"
        if label_rows is not None
        else f"{numeric_rows} numeric rows"
    )
    min_value = stats.get("min")
    max_value = stats.get("max")
    if min_value is not None and max_value is not None:
        return f"{field}: {count_text}, range {min_value:g} to {max_value:g}."
    return f"{field}: {count_text}."


def _positive_int(value: Any) -> int | None:
    if isinstance(value, int) and value >= 0:
        return value
    text = str(value or "").strip()
    return int(text) if text.isdigit() else None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _code_sort_key(code: str) -> tuple[int, int | str]:
    return (0, int(code)) if code.isdigit() else (1, code.casefold())
