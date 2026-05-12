"""Placement evidence for external label carriers."""

from __future__ import annotations

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
    target = str(carrier.get("selected_anchor") or "").strip()
    review = _base_review("eeg_event", carrier)
    review["target_event"] = target
    review["label_rows"] = label_rows
    review["excluded_eeg_events"] = _excluded_event_count(event_rows)
    event = _event_row_by_code(event_rows, target)
    if target in {"", "trial order"}:
        review.update(
            {
                "status": "needs_review",
                "summary": "Choose the EEG event that label rows follow in order.",
                "next_action": "Select a target EEG event.",
            }
        )
        return review
    if not event:
        review.update(
            {
                "status": "blocked",
                "summary": f"Target EEG event {target} was not found.",
                "next_action": "Choose an EEG event present in the selected files.",
            }
        )
        return review
    event_count = _event_count(event)
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
        summary = f"{matched} label rows match {event_count} target EEG events."
    else:
        status = "needs_review"
        summary = (
            f"{matched} rows match; "
            f"{review['unlabeled_eeg_events']} EEG events unlabeled; "
            f"{review['unmatched_label_rows']} label rows unmatched."
        )
    review.update(
        {
            "status": status,
            "summary": summary,
            "next_action": "Confirm the target event or adjust the label file.",
        }
    )
    return review


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
    review.update(
        {
            "event_code_field": field,
            "label_rows": label_rows,
            "label_code_count": len(value_counts),
            "matched_code_count": len(matched_codes),
            "matched_codes": matched_codes,
            "missing_codes": missing_codes,
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
    if missing_codes:
        review.update(
            {
                "status": "needs_review",
                "summary": (
                    f"{len(matched_codes)}/{len(value_counts)} label event codes "
                    "were found in EEG events."
                ),
                "next_action": "Map or remove missing label event codes.",
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
