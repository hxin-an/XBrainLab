"""Bounded projections for user-facing Data Interpretation payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PUBLIC_EVIDENCE_PREVIEW_LIMIT = 12

_COUNTED_ROW_COLLECTIONS = {
    "row_evidence": "row_evidence_count",
    "unknown_duration_rows": "unknown_duration_row_count",
    "excluded_rows": "excluded_row_count",
}
_BOUNDED_COLLECTIONS = {
    "issues": "issue_count",
    "matched_codes": "matched_code_count",
    "missing_codes": "missing_code_count",
    "conflict_codes": "conflict_code_count",
    "duplicate_codes": "duplicate_code_count",
    "code_mappings": "code_mapping_count",
    "unlabeled_eeg_events": "unlabeled_eeg_event_count",
}


def project_label_carrier_plan(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return compact label-carrier rows suitable for UI and agent clients."""
    return [_project_mapping(row) for row in rows]


def project_bids_review(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return aggregate BIDS review evidence without per-event duplication."""
    return _project_mapping(payload)


def project_interpretation_candidate(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Bound the public form of a complete interpretation candidate."""
    return _project_mapping(payload)


def _project_mapping(
    payload: Mapping[str, Any],
    *,
    parent_key: str = "",
) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for raw_key, value in payload.items():
        key = str(raw_key)
        if key == "event_code_label_counts":
            continue
        if key == "value_counts" and parent_key.endswith("_stats"):
            continue
        if key in _COUNTED_ROW_COLLECTIONS and isinstance(value, list):
            projected[_COUNTED_ROW_COLLECTIONS[key]] = len(value)
            continue
        if key in _BOUNDED_COLLECTIONS and isinstance(value, list):
            count_key = _BOUNDED_COLLECTIONS[key]
            projected[count_key] = max(
                _integer(projected.get(count_key)),
                len(value),
            )
            projected[key] = [
                _project_value(item, parent_key=key)
                for item in value[:PUBLIC_EVIDENCE_PREVIEW_LIMIT]
            ]
            continue
        projected[key] = _project_value(value, parent_key=key)
    return projected


def _project_value(value: Any, *, parent_key: str) -> Any:
    if isinstance(value, Mapping):
        return _project_mapping(value, parent_key=parent_key)
    if isinstance(value, list):
        return [_project_value(item, parent_key=parent_key) for item in value]
    if isinstance(value, tuple):
        return [_project_value(item, parent_key=parent_key) for item in value]
    return value


def _integer(value: Any) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0
