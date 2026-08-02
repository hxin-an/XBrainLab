"""Placement evidence for external label carriers."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class _AppliedEventScope:
    evidence_present: bool
    is_valid: bool
    event_count: int | None = None
    counts_by_target: dict[str, int] = field(default_factory=dict)
    decision_code: str = ""
    summary: str = ""


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


def placement_blocked_reasons(
    label_carrier_plan: list[dict[str, Any]],
) -> list[str]:
    """Return carrier-scoped reasons for placement states that cannot be applied."""
    reasons: list[str] = []
    for carrier in label_carrier_plan:
        review = carrier.get("placement_review")
        if not isinstance(review, dict):
            continue
        status = str(review.get("status") or "").strip()
        if status != "blocked" and not (
            status == "needs_review" and _is_trial_order_placement(carrier)
        ):
            continue
        name = str(carrier.get("name") or Path(str(carrier.get("path") or "")).name)
        summary = str(review.get("summary") or "Label placement is blocked.").strip()
        reason = f"{name}: {summary}" if name else summary
        if reason not in reasons:
            reasons.append(reason)
    return reasons


def _is_trial_order_placement(carrier: dict[str, Any]) -> bool:
    placement_method = (
        str(
            carrier.get("placement_method") or "",
        )
        .strip()
        .lower()
    )
    return (
        placement_method in {"", "eeg_event"}
        and str(carrier.get("time_model") or "").strip().lower() == "trial_order"
    )


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
    applied_scope = _applied_event_scope(carrier)
    if applied_scope.evidence_present:
        if applied_scope.counts_by_target:
            review["selected_eeg_events_by_target"] = applied_scope.counts_by_target
        review["selected_eeg_events"] = applied_scope.event_count
        if not applied_scope.is_valid:
            review.update(
                {
                    "status": "blocked",
                    "decision_code": applied_scope.decision_code,
                    "summary": applied_scope.summary,
                    "next_action": (
                        "Review the committed target paths and per-target event "
                        "counts before using these labels."
                    ),
                }
            )
            return review
        committed_label_rows = _committed_positive_int(
            carrier.get("label_row_count"),
        )
        if committed_label_rows is None:
            label_count_is_zero = _is_integer_zero(carrier.get("label_row_count"))
            review.update(
                {
                    "status": "blocked",
                    "decision_code": (
                        "post_commit_label_scope_empty"
                        if label_count_is_zero
                        else "post_commit_label_count_invalid"
                    ),
                    "summary": (
                        "The committed label import contains zero label rows; the "
                        "applied label scope must contain at least one label row."
                        if label_count_is_zero
                        else (
                            "The committed label import contains an invalid label "
                            "row count; it must be a positive integer."
                        )
                    ),
                    "next_action": (
                        "Review the imported labels before using this applied scope."
                    ),
                }
            )
            return review
        label_rows = committed_label_rows
        review["label_rows"] = label_rows
        applied_event_count = applied_scope.event_count
        if applied_event_count is None:
            review.update(
                {
                    "status": "blocked",
                    "decision_code": "post_commit_event_scope_inconsistent",
                    "summary": (
                        "The committed label import does not provide one consistent "
                        "event count for every selected target."
                    ),
                    "next_action": (
                        "Review the imported target scope before using these labels."
                    ),
                }
            )
            return review
        matched = min(label_rows, applied_event_count)
        review["matched"] = matched
        review["unmatched_label_rows"] = max(label_rows - applied_event_count, 0)
        review["unlabeled_eeg_events"] = max(applied_event_count - label_rows, 0)
        if label_rows != applied_event_count:
            review.update(
                {
                    "status": "blocked",
                    "decision_code": "post_commit_event_count_mismatch",
                    "summary": (
                        "The committed label count does not match the applied EEG "
                        f"event scope ({label_rows} label rows, "
                        f"{applied_event_count} applied events per target)."
                    ),
                    "next_action": (
                        "Review the imported labels and target event selection."
                    ),
                }
            )
            return review
        review.update(
            {
                "status": "ready",
                "matched": matched,
                "summary": (
                    f"{matched} label rows were applied to {applied_event_count} EEG "
                    "events for each selected target."
                ),
                "next_action": "Review the imported class mapping.",
            }
        )
        return review
    if not target_codes:
        review.update(
            {
                "status": "blocked",
                "decision_code": "sequence_target_events_required",
                "summary": (
                    "Trial-order label placement requires an explicit target EEG "
                    "event set. Confirmation alone cannot resolve the event anchor."
                ),
                "next_action": (
                    "Select one or more target EEG events before applying labels."
                ),
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
    event_count, scoped_event_counts = _event_scope_for_carrier(
        [event for _code, event in events if event is not None],
        carrier,
    )
    review["selected_eeg_events"] = event_count
    if scoped_event_counts:
        review["selected_eeg_events_by_target"] = scoped_event_counts
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
    excluded_class_names = _mne_excluded_class_names(carrier)
    if excluded_class_names:
        review.update(
            {
                "status": "blocked",
                "decision_code": "mne_excluded_class_description",
                "summary": (
                    "MNE excludes supervised class descriptions beginning with "
                    "Bad or Edge: " + ", ".join(excluded_class_names) + "."
                ),
                "next_action": (
                    "Rename the class, or mark the value as an artifact or boundary "
                    "instead of a supervised class."
                ),
            }
        )
        return review
    if not field:
        review.update(
            {
                "status": "blocked",
                "summary": "No label time field is selected.",
                "next_action": "Choose a time, onset, sample, or latency field.",
            }
        )
        return review
    time_model = str(carrier.get("time_model") or "").strip().lower()
    if time_model == "sample_index":
        sample_index_base = str(carrier.get("sample_index_base") or "").strip()
        sample_index_origin = str(carrier.get("sample_index_origin") or "").strip()
        review["sample_index_contract"] = {
            "base": sample_index_base,
            "origin": sample_index_origin,
        }
        if sample_index_base not in {"zero_based", "one_based"} or (
            sample_index_origin not in {"recording_relative", "absolute"}
        ):
            review.update(
                {
                    "status": "blocked",
                    "decision_code": "sample_index_contract_required",
                    "summary": (
                        "Sample indexes need an explicit zero- or one-based "
                        "contract and a recording-relative or absolute origin."
                    ),
                    "next_action": (
                        "Choose the sample index base and origin before applying "
                        "labels."
                    ),
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
            "next_action": "Confirm the time base before EEG epoch setup.",
        }
    )
    return review


def _mne_excluded_class_names(carrier: dict[str, Any]) -> list[str]:
    decisions = _dict(carrier.get("value_decisions"))
    result: list[str] = []
    for value in decisions.values():
        if not isinstance(value, dict):
            continue
        class_name = str(value.get("class_name") or "").strip()
        if (
            value.get("decision") == "resolved"
            and value.get("keep_event") is True
            and value.get("use_as_class") is True
            and class_name.casefold().startswith(("bad", "edge"))
            and class_name not in result
        ):
            result.append(class_name)
    return sorted(result, key=str.casefold)


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
            "next_action": "Confirm interval semantics before EEG epoch setup.",
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
    duplicate_codes = [
        str(row.get("event_code") or "")
        for row in code_mappings
        if (
            row.get("status") == "needs_review"
            and row.get("duplicate_rows")
            and not row.get("conflict")
        )
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
            "duplicate_codes": duplicate_codes,
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
    if missing_codes or conflict_codes or duplicate_codes:
        parts = [
            f"{len(matched_codes)}/{len(value_counts)} label event codes "
            "were found in EEG events"
        ]
        if conflict_codes:
            parts.append(f"{len(conflict_codes)} code(s) map to multiple label values")
        if duplicate_codes:
            parts.append(f"{len(duplicate_codes)} code(s) have repeated mapping rows")
        review.update(
            {
                "status": "needs_review",
                "summary": "; ".join(parts) + ".",
                "next_action": (
                    "Use one row per code for codebook matching, or choose "
                    "EEG event order/time if rows represent trials."
                ),
            }
        )
        return review
    review.update(
        {
            "status": "ready",
            "summary": f"All {len(value_counts)} label event codes match EEG events.",
            "next_action": "Confirm code meanings before EEG epoch setup.",
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
        duplicate_rows = int(value_counts.get(code) or 0) > 1
        eeg_count = event_counts.get(code)
        missing = code not in event_counts
        if conflict:
            status = "needs_review"
            review = "Same code maps to multiple label values."
        elif duplicate_rows:
            status = "needs_review"
            review = "Repeated rows; event-code placement expects one row per code."
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
                "duplicate_rows": duplicate_rows,
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


def _event_scope_for_carrier(
    rows: list[dict[str, Any]],
    carrier: dict[str, Any],
) -> tuple[int | None, dict[str, int]]:
    """Return one per-target event scope for a carrier replayed across files."""
    if not rows:
        return None, {}
    explicit_targets = _selected_target_file_identities(carrier)
    if explicit_targets:
        counts_by_target: dict[str, int] = {}
        for target_path in explicit_targets:
            target_total = 0
            for row in rows:
                file_counts = _dict(row.get("file_counts"))
                value = _target_file_count(
                    file_counts,
                    target_path=target_path,
                    all_target_paths=explicit_targets,
                )
                if value is None:
                    return None, {}
                target_total += value
            counts_by_target[target_path] = target_total
        distinct_counts = set(counts_by_target.values())
        event_count = next(iter(distinct_counts)) if len(distinct_counts) == 1 else None
        return event_count, counts_by_target

    event_counts = [_event_count_for_unscoped_carrier(row, carrier) for row in rows]
    event_count = (
        sum(value for value in event_counts if value is not None)
        if all(value is not None for value in event_counts)
        else None
    )
    return event_count, {}


def _applied_event_scope(
    carrier: dict[str, Any],
) -> _AppliedEventScope:
    evidence_key = "applied_event_counts_by_target"
    if evidence_key not in carrier:
        return _AppliedEventScope(evidence_present=False, is_valid=False)

    raw_counts = carrier.get(evidence_key)
    target_paths = _selected_target_file_identities(carrier)
    if not isinstance(raw_counts, dict) or not raw_counts:
        return _invalid_applied_event_scope(
            "post_commit_event_scope_not_per_target",
            "The committed label import does not provide per-target event counts.",
        )
    if not target_paths:
        return _invalid_applied_event_scope(
            "post_commit_event_scope_target_mismatch",
            "The committed label import has event counts but no selected target paths.",
        )

    normalized_counts: dict[str, int] = {}
    for path, raw_count in raw_counts.items():
        if not str(path).strip():
            return _invalid_applied_event_scope(
                "post_commit_event_scope_invalid",
                "The committed label import contains an invalid target path.",
            )
        path_key = _path_identity(path)
        if path_key in normalized_counts:
            return _invalid_applied_event_scope(
                "post_commit_event_scope_invalid",
                "The committed label import contains duplicate target identities.",
            )
        if _is_integer_zero(raw_count):
            return _invalid_applied_event_scope(
                "post_commit_event_scope_empty",
                (
                    "The committed label import contains a target with zero applied "
                    "EEG events; every selected target must have at least one applied "
                    "EEG event."
                ),
            )
        count = _committed_positive_int(raw_count)
        if count is None:
            return _invalid_applied_event_scope(
                "post_commit_event_scope_invalid",
                (
                    "The committed label import contains an invalid per-target "
                    "event count; it must be a positive integer."
                ),
            )
        normalized_counts[path_key] = count

    normalized_targets = [_path_identity(path) for path in target_paths]
    if len(set(normalized_targets)) != len(normalized_targets):
        return _invalid_applied_event_scope(
            "post_commit_event_scope_invalid",
            "The selected label targets contain duplicate path identities.",
        )
    if set(normalized_targets) != set(normalized_counts):
        return _invalid_applied_event_scope(
            "post_commit_event_scope_target_mismatch",
            (
                "The committed per-target event counts do not match every selected "
                "target by full path identity."
            ),
        )

    counts_by_target = {
        target_path: normalized_counts[target_key]
        for target_path, target_key in zip(
            target_paths,
            normalized_targets,
            strict=True,
        )
    }
    distinct_counts = set(counts_by_target.values())
    event_count = next(iter(distinct_counts)) if len(distinct_counts) == 1 else None
    return _AppliedEventScope(
        evidence_present=True,
        is_valid=True,
        event_count=event_count,
        counts_by_target=counts_by_target,
    )


def _invalid_applied_event_scope(
    decision_code: str,
    summary: str,
) -> _AppliedEventScope:
    return _AppliedEventScope(
        evidence_present=True,
        is_valid=False,
        decision_code=decision_code,
        summary=summary,
    )


def _event_count_for_unscoped_carrier(
    row: dict[str, Any],
    carrier: dict[str, Any],
) -> int | None:
    """Use a same-stem per-file count when no explicit target scope was saved."""
    file_counts = _dict(row.get("file_counts"))
    if not file_counts:
        return _event_count(row)
    label_stem = Path(
        str(carrier.get("path") or carrier.get("name") or ""),
    ).stem.casefold()
    if not label_stem:
        return _event_count(row)
    matches = [
        name for name in file_counts if Path(str(name)).stem.casefold() == label_stem
    ]
    if len(matches) == 1:
        value = _positive_int(file_counts.get(matches[0]))
        if value is not None:
            return value
    return _event_count(row)


def _selected_target_file_identities(carrier: dict[str, Any]) -> list[str]:
    raw_targets = carrier.get("selected_target_files")
    if isinstance(raw_targets, str):
        values: Iterable[Any] = raw_targets.split(",")
    elif isinstance(raw_targets, (list, tuple, set)):
        values = raw_targets
    else:
        values = []
    targets = [text for value in values if (text := str(value).strip())]
    explicit = str(carrier.get("selected_target_file") or "").strip()
    if explicit:
        targets.append(explicit)
    return list(dict.fromkeys(targets))


def _target_file_count(
    file_counts: dict[str, Any],
    *,
    target_path: str,
    all_target_paths: list[str],
) -> int | None:
    direct = _positive_int(file_counts.get(target_path))
    if direct is not None:
        return direct

    normalized_target = _path_identity(target_path)
    normalized_matches = [
        value
        for path, value in file_counts.items()
        if _path_identity(path) == normalized_target
    ]
    if len(normalized_matches) == 1:
        return _positive_int(normalized_matches[0])

    target_name = Path(target_path).name
    if sum(Path(path).name == target_name for path in all_target_paths) != 1:
        return None
    basename_matches = [
        value for path, value in file_counts.items() if Path(path).name == target_name
    ]
    if len(basename_matches) == 1:
        return _positive_int(basename_matches[0])
    return None


def _path_identity(path: Any) -> str:
    return os.path.normcase(str(Path(str(path)).expanduser().resolve()))


def _committed_positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return int(value)


def _is_integer_zero(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 0


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
