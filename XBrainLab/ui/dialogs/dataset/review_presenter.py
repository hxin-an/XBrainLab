"""Pure presenter helpers for the Data Import review step."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from XBrainLab.backend.application.data_interpretation_review import (
    target_step_for_interpretation_text,
)

ReviewRow = tuple[str, str, str, str]

_STEP_ORDER = {
    "Choose EEG Data": 0,
    "Load Labels": 1,
    "Review Metadata": 2,
    "Match Labels": 3,
    "Review and Import": 4,
}


def build_review_rows(
    *,
    preview: dict[str, Any],
    validation_decision: dict[str, Any],
    scan_result: dict[str, Any],
) -> list[ReviewRow]:
    """Build task-oriented review rows from backend preview/review payloads."""
    rows: list[ReviewRow] = []
    rows.extend(
        action_item_rows(
            preview.get("action_items") or validation_decision.get("action_items")
        )
    )
    if not rows:
        rows.extend(
            _legacy_review_rows(
                preview=preview,
                validation_decision=validation_decision,
            )
        )
    rows.extend(recipe_reload_rows(preview.get("recipe_reload_summary")))
    format_capabilities = preview.get("format_capabilities") or scan_result.get(
        "format_capabilities"
    )
    rows.extend(format_capability_rows(format_capabilities))
    return compact_review_rows(rows)


def build_primary_review_rows(
    *,
    preview: dict[str, Any],
    validation_decision: dict[str, Any],
) -> list[ReviewRow]:
    """Build the first-layer review items that require user action."""
    decision = str(validation_decision.get("decision") or "").strip().lower()
    action_items = primary_action_item_rows(
        preview.get("action_items") or validation_decision.get("action_items")
    )
    if action_items:
        return compact_review_rows(action_items)

    rows = _legacy_review_rows(
        preview=preview,
        validation_decision=validation_decision,
        include_warnings=False,
    )
    if decision == "blocked":
        rows = [row for row in rows if row[1] == "Cannot import yet"]
    elif decision == "safe":
        rows = []
    return compact_review_rows(rows)


def _legacy_review_rows(
    *,
    preview: dict[str, Any],
    validation_decision: dict[str, Any],
    include_warnings: bool = True,
) -> list[ReviewRow]:
    rows: list[ReviewRow] = []
    warnings = unique_strings(preview.get("warnings"))
    confirmations = unique_strings(
        [
            *(preview.get("confirmation_items") or []),
            *(validation_decision.get("required_confirmations") or []),
        ]
    )
    blocked = unique_strings(
        validation_decision.get("blocked_reasons") or preview.get("blocked_reasons")
    )
    groups = [
        ("Required choice", "Confirm", confirmations),
        ("Cannot import yet", "Fix first", blocked),
    ]
    if include_warnings:
        groups.insert(0, ("Possible issue", "Check", warnings))
    for label, status, values in groups:
        rows.extend(
            (target_step_for_review_text(item), label, item, status) for item in values
        )
    return rows


def unique_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in result:
            result.append(text)
    return result


def action_item_rows(values: Any) -> list[ReviewRow]:
    if not isinstance(values, list):
        return []
    rows: list[ReviewRow] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        target_step = str(value.get("target_step") or "Review and Import")
        rows.append(
            (
                target_step,
                str(value.get("issue") or "Review item"),
                str(value.get("impact") or ""),
                str(value.get("next_action") or ""),
            )
        )
    return sorted(rows, key=lambda row: (_STEP_ORDER.get(row[0], 99), row[1]))


def primary_action_item_rows(values: Any) -> list[ReviewRow]:
    if not isinstance(values, list):
        return []
    rows: list[ReviewRow] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        severity = str(value.get("severity") or "needs_confirmation").strip().lower()
        if severity not in {"blocked", "needs_confirmation", "limited"}:
            continue
        rows.append(
            (
                str(value.get("target_step") or "Review and Import"),
                str(value.get("issue") or "Review item"),
                str(value.get("impact") or ""),
                str(value.get("next_action") or ""),
            )
        )
    return sorted(rows, key=lambda row: (_STEP_ORDER.get(row[0], 99), row[1]))


def compact_review_rows(rows: list[ReviewRow]) -> list[ReviewRow]:
    metadata_rows: list[ReviewRow] = []
    compacted: list[ReviewRow] = []
    metadata_insert_index: int | None = None
    for row in rows:
        if is_optional_metadata_review_row(row):
            continue
        if is_metadata_review_row(row):
            if metadata_insert_index is None:
                metadata_insert_index = len(compacted)
            metadata_rows.append(row)
            continue
        compacted.append(row)
    if not metadata_rows:
        return compacted
    insert_at = (
        metadata_insert_index if metadata_insert_index is not None else len(compacted)
    )
    compacted.insert(insert_at, metadata_review_action_row(metadata_rows))
    return compacted


def is_metadata_review_row(row: ReviewRow) -> bool:
    target_step, issue, _impact, next_action = row
    text = " ".join((target_step, issue, next_action)).lower()
    return target_step == "Review Metadata" or "metadata" in text


def metadata_required_fields_complete(
    *,
    row_count: int,
    missing_fields: dict[str, int] | set[str],
    required_fields: set[str] | None = None,
) -> bool:
    """Return whether metadata review has no missing required fields."""
    if row_count <= 0:
        return False
    required = required_fields or {"subject", "task"}
    if isinstance(missing_fields, set):
        return not (required & missing_fields)
    return not {field for field in required if int(missing_fields.get(field) or 0) > 0}


def is_optional_metadata_review_row(row: ReviewRow) -> bool:
    if not is_metadata_review_row(row):
        return False
    fields = metadata_fields_in_review_rows([row])
    return bool(fields) and fields <= {"session", "run"}


def metadata_review_action_row(rows: list[ReviewRow]) -> ReviewRow:
    fields = [
        field
        for field in ("subject", "task")
        if field in metadata_fields_in_review_rows(rows)
    ]
    if fields:
        impact = "Required fields need review: " + ", ".join(fields) + "."
    else:
        impact = "Metadata choices need review."
    files = review_group_files(rows)
    if files:
        impact = f"{impact}\n{review_grouped_impact_text(files, [])}"
    return (
        "Review Metadata",
        "Review metadata",
        impact,
        "Review the metadata table.",
    )


def metadata_fields_in_review_rows(rows: list[ReviewRow]) -> set[str]:
    text = " ".join(" ".join(row) for row in rows).lower()
    return {
        field
        for field in ("subject", "session", "task", "run")
        if re.search(rf"\b{re.escape(field)}\b", text)
    }


def merge_review_rows(rows: list[ReviewRow]) -> list[ReviewRow]:
    grouped: dict[tuple[str, str, str, str], list[ReviewRow]] = {}
    order: list[tuple[str, str, str, str]] = []
    for row in rows:
        target_step, issue, impact, next_action = row
        key = (
            target_step,
            review_text_without_file_refs(issue),
            review_text_without_file_refs(impact),
            review_text_without_file_refs(next_action),
        )
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(row)

    merged: list[ReviewRow] = []
    for target_step, issue_key, impact_key, next_action_key in order:
        group_rows = grouped[(target_step, issue_key, impact_key, next_action_key)]
        files = review_group_files(group_rows)
        if len(group_rows) <= 1 or len(files) <= 1:
            merged.extend(group_rows)
            continue
        first_target_step, first_issue, _first_impact, first_next_action = group_rows[0]
        merged.append(
            (
                first_target_step,
                review_grouped_issue_text(first_issue),
                review_grouped_impact_text(
                    files, review_group_shared_details(group_rows)
                ),
                review_grouped_next_action_text(first_next_action),
            )
        )
    return merged


def review_group_files(rows: list[ReviewRow]) -> list[str]:
    files: list[str] = []
    for row in rows:
        for value in row[1:]:
            for file_name in review_file_refs(value):
                if file_name not in files:
                    files.append(file_name)
    return files


def review_group_shared_details(rows: list[ReviewRow]) -> list[str]:
    details: list[str] = []
    for _target_step, _issue, impact, _next_action in rows:
        detail = review_group_detail_text(impact)
        if detail and detail not in details:
            details.append(detail)
    return details[:2]


def review_group_detail_text(text: str) -> str:
    if not text or review_file_refs(text):
        return ""
    stripped = text.strip()
    if stripped.lower() in {"check", "confirm", "fix first", "no action needed."}:
        return ""
    return stripped


def review_text_without_file_refs(text: str) -> str:
    normalized = review_file_ref_pattern().sub("{file}", str(text).strip())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.lower()


def review_file_refs(text: str) -> list[str]:
    result: list[str] = []
    for match in review_file_ref_pattern().finditer(str(text)):
        file_name = Path(match.group(0).replace("\\", "/")).name
        if file_name and file_name not in result:
            result.append(file_name)
    return result


def review_file_ref_pattern() -> re.Pattern[str]:
    extensions_pattern = "|".join(
        re.escape(extension)
        for extension in ("gdf", "edf", "set", "fif", "vhdr", "mat", "csv", "tsv")
    )
    return re.compile(
        r"(?<![\w.-])(?:[A-Za-z]:)?(?:[\\/][^\s:;,]+)*[\\/]*"
        rf"[^\\/\s:;,]+\.({extensions_pattern})(?![\w-])",
        re.IGNORECASE,
    )


def review_grouped_issue_text(issue: str) -> str:
    text = issue.strip()
    text = review_file_ref_pattern().sub("{file}", text)
    replacements = {
        "{file} needs": "Files need",
        "{file} requires": "Files require",
        "{file} has": "Files have",
        "{file} is": "Files are",
        "{file} was": "Files were",
        "{file}": "Files",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def review_grouped_next_action_text(next_action: str) -> str:
    return review_file_ref_pattern().sub("these files", next_action.strip())


def review_grouped_impact_text(files: list[str], details: list[str]) -> str:
    shown = files[:4]
    text = f"{len(files)} files affected: " + ", ".join(shown)
    extra_count = len(files) - len(shown)
    if extra_count > 0:
        text = f"{text}; +{extra_count} more"
    if details:
        text = f"{text}\n" + "\n".join(details)
    return text


def target_step_for_review_text(text: str) -> str:
    return target_step_for_interpretation_text(text)


def format_capability_rows(values: Any) -> list[ReviewRow]:
    if not isinstance(values, list):
        return []
    grouped: dict[tuple[str, str, str], int] = {}
    for value in values:
        if not isinstance(value, dict):
            continue
        format_name = str(value.get("format") or value.get("name") or "Source")
        status = str(value.get("status") or "review").replace("_", " ")
        message = str(value.get("message") or "").strip()
        grouped[(format_name, status, message)] = (
            grouped.get((format_name, status, message), 0) + 1
        )
    rows: list[ReviewRow] = []
    for (format_name, status, message), count in grouped.items():
        detail = f"{format_name}: {status}."
        if count > 1:
            detail = f"{detail} {count} matching source(s)."
        if message:
            detail = f"{detail} {message}"
        rows.append(("Review and Import", "Format support", detail, "Check format"))
    return rows


def recipe_reload_rows(value: Any) -> list[ReviewRow]:
    if not isinstance(value, dict) or not value:
        return []
    rows: list[ReviewRow] = [
        (
            "Review and Import",
            "Reloaded recipe",
            str(
                value.get("message")
                or "Saved recipe choices were reapplied before validation."
            ),
            "Review any changed files before importing.",
        )
    ]
    for diff_row in value.get("diff_rows", []) or []:
        if not isinstance(diff_row, dict):
            continue
        item = str(diff_row.get("item") or "Recipe reload")
        status = str(diff_row.get("status") or "Review")
        detail = str(diff_row.get("detail") or "").strip()
        if detail:
            rows.append(("Review and Import", item, detail, status))
    return rows
