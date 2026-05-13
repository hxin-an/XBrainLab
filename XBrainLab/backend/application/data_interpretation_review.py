"""Review and validation boundaries for Data Interpretation candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class InterpretationPreview:
    """Human- and agent-readable preview of an interpretation candidate."""

    preview_id: str
    candidate_id: str
    summary: str
    file_count: int
    label_carrier_count: int
    source_selection: str = "Source"
    selected_eeg_files: list[str] = dc_field(default_factory=list)
    bids: dict[str, Any] = dc_field(default_factory=dict)
    action_items: list[dict[str, str]] = dc_field(default_factory=list)
    label_carrier_preview: list[dict[str, Any]] = dc_field(default_factory=list)
    metadata_preview: list[dict[str, Any]] = dc_field(default_factory=list)
    format_capabilities: list[dict[str, Any]] = dc_field(default_factory=list)
    warnings: list[str] = dc_field(default_factory=list)
    confirmation_items: list[str] = dc_field(default_factory=list)
    blocked_reasons: list[str] = dc_field(default_factory=list)
    downstream_impacts: list[str] = dc_field(default_factory=list)
    event_roles: dict[str, str] = dc_field(default_factory=dict)
    class_map: dict[str, str] = dc_field(default_factory=dict)
    class_map_source: str = ""
    internal_event_preview: dict[str, Any] = dc_field(default_factory=dict)
    recipe_reload_summary: dict[str, Any] = dc_field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


@dataclass(frozen=True)
class ValidationDecision:
    """Validation result for an interpretation candidate."""

    candidate_id: str
    decision: str
    reasons: list[str] = dc_field(default_factory=list)
    warnings: list[str] = dc_field(default_factory=list)
    required_confirmations: list[str] = dc_field(default_factory=list)
    blocked_reasons: list[str] = dc_field(default_factory=list)
    downstream_impacts: list[str] = dc_field(default_factory=list)
    action_items: list[dict[str, str]] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


def build_interpretation_preview(
    *,
    preview_id: str,
    candidate: Any,
    scan: Any | None = None,
    recipe: Any | None = None,
) -> InterpretationPreview:
    """Create a UI/agent-friendly preview for a candidate interpretation."""
    file_count = len(candidate.selected_eeg_files)
    label_count = len(candidate.label_carriers)
    summary = (
        f"Found {file_count} EEG file(s) and {label_count} label/event carrier(s)."
    )
    metadata_preview = [
        {
            "file": Path(item.file).name,
            "subject": item.subject.to_dict()
            if hasattr(item.subject, "to_dict")
            else _serialize(item.subject),
            "session": _serialize(item.session),
            "task": _serialize(item.task),
            "run": _serialize(item.run),
        }
        for item in candidate.metadata
    ]
    return InterpretationPreview(
        preview_id=preview_id,
        candidate_id=candidate.candidate_id,
        summary=summary,
        file_count=file_count,
        label_carrier_count=label_count,
        source_selection=_source_selection_text(candidate),
        selected_eeg_files=list(candidate.selected_eeg_files),
        bids=dict(getattr(candidate, "bids", {}) or {}),
        action_items=_build_action_items(candidate),
        label_carrier_preview=[dict(item) for item in candidate.label_carrier_plan],
        metadata_preview=metadata_preview,
        format_capabilities=[dict(item) for item in candidate.format_capabilities],
        warnings=list(candidate.warnings),
        confirmation_items=list(candidate.confirmation_items),
        blocked_reasons=list(candidate.blocked_reasons),
        downstream_impacts=[
            "Applying this interpretation will replace active raw data and "
            "invalidate downstream preprocessing, epochs, datasets, training, "
            "and saliency for the current session.",
        ],
        event_roles=dict(candidate.event_roles),
        class_map=dict(candidate.class_map),
        class_map_source=str(getattr(candidate, "class_map_source", "") or ""),
        internal_event_preview=dict(
            getattr(candidate, "internal_event_preview", {}) or {}
        ),
        recipe_reload_summary=_recipe_reload_summary(
            getattr(candidate, "choices", {}),
            scan=scan,
            recipe=recipe,
            candidate=candidate,
        ),
    )


def _source_selection_text(candidate: Any) -> str:
    choices = getattr(candidate, "choices", {}) or {}
    has_selected_files = bool(
        isinstance(choices, dict)
        and (choices.get("selected_eeg_files") or choices.get("eeg_files"))
    )
    file_count = len(getattr(candidate, "selected_eeg_files", []) or [])
    if has_selected_files:
        return f"{file_count} selected file(s)"
    source_kind = str(getattr(candidate, "source_kind", "") or "").lower()
    if source_kind == "file":
        return "Single file"
    if source_kind == "bids":
        return "BIDS folder"
    if source_kind == "folder":
        return "Folder"
    return source_kind or "Source"


def validate_interpretation_candidate(candidate: Any) -> ValidationDecision:
    """Validate a candidate using reviewable safe/confirm/blocked decisions."""
    if candidate.blocked_reasons:
        return ValidationDecision(
            candidate_id=candidate.candidate_id,
            decision="blocked",
            reasons=["Interpretation cannot be applied until blockers are resolved."],
            warnings=list(candidate.warnings),
            blocked_reasons=list(candidate.blocked_reasons),
            downstream_impacts=[
                "Preprocess, epoch, dataset, and training remain blocked.",
            ],
            action_items=_build_action_items(candidate),
        )
    if candidate.confirmation_items:
        return ValidationDecision(
            candidate_id=candidate.candidate_id,
            decision="needs_confirmation",
            reasons=["Candidate has reviewable semantic choices."],
            warnings=list(candidate.warnings),
            required_confirmations=list(candidate.confirmation_items),
            downstream_impacts=[
                "Downstream workflow remains blocked until the interpretation "
                "is confirmed and applied.",
            ],
            action_items=_build_action_items(candidate),
        )
    return ValidationDecision(
        candidate_id=candidate.candidate_id,
        decision="safe",
        reasons=["Source files and required metadata are sufficient for apply."],
        warnings=list(candidate.warnings),
        downstream_impacts=[
            "Applied interpretation becomes the source truth for preprocessing, "
            "epoching, dataset generation, training, and saliency.",
        ],
        action_items=_build_action_items(candidate),
    )


def _build_action_items(candidate: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    choices = getattr(candidate, "choices", {}) or {}
    skip_labels = bool(isinstance(choices, dict) and choices.get("skip_labels"))

    items.extend(
        [
            _action_item(
                issue=reason,
                impact="This import cannot be applied until the issue is fixed.",
                next_action="Fix this item before importing.",
                target_step=_target_step_for_text(reason),
                severity="blocked",
            )
            for reason in _unique_strings(getattr(candidate, "blocked_reasons", []))
        ]
    )
    items.extend(
        [
            _action_item(
                issue=confirmation,
                impact=(
                    "This choice affects imported metadata, labels, or downstream "
                    "training readiness."
                ),
                next_action="Review the target step and confirm the choice.",
                target_step=_target_step_for_text(confirmation),
                severity="needs_confirmation",
            )
            for confirmation in _unique_strings(
                getattr(candidate, "confirmation_items", [])
            )
        ]
    )
    items.extend(
        [
            _action_item(
                issue=warning,
                impact=(
                    "Import may still be usable, but downstream labels or "
                    "metadata may need review."
                ),
                next_action=(
                    "Open the target step and resolve or confirm this item "
                    "before import."
                ),
                target_step=_target_step_for_text(warning),
                severity="warning",
            )
            for warning in _unique_strings(getattr(candidate, "warnings", []))
        ]
    )

    label_carriers = list(getattr(candidate, "label_carriers", []) or [])
    if not label_carriers and skip_labels:
        items.append(
            _action_item(
                issue="Labels skipped for now.",
                impact=(
                    "Supervised dataset generation and training remain limited "
                    "until labels or event semantics are added."
                ),
                next_action=(
                    "Continue only for inspection, or return to Load Labels "
                    "before supervised training."
                ),
                target_step="Load Labels",
                severity="limited",
            )
        )
    elif not label_carriers:
        items.append(
            _action_item(
                issue="No external label file or folder is attached.",
                impact=(
                    "Supervised workflows may be limited unless reliable "
                    "internal events are confirmed."
                ),
                next_action=(
                    "Load a label file, load a label folder, or continue without "
                    "labels."
                ),
                target_step="Load Labels",
                severity="warning",
            )
        )
    return _dedupe_action_items(items)


def _action_item(
    *,
    issue: str,
    impact: str,
    next_action: str,
    target_step: str,
    severity: str,
) -> dict[str, str]:
    return {
        "issue": issue,
        "impact": impact,
        "next_action": next_action,
        "target_step": target_step,
        "severity": severity,
    }


def _target_step_for_text(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("eeg file", "source", "scan")):
        return "Choose EEG Data"
    if any(token in lowered for token in ("label", "event", "carrier")):
        if "no " in lowered or "missing" in lowered:
            return "Load Labels"
        return "Match Labels"
    if any(
        token in lowered for token in ("subject", "session", "task", "run", "metadata")
    ):
        return "Review Metadata"
    return "Review and Import"


def _unique_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _dedupe_action_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in items:
        key = (
            item.get("target_step", ""),
            item.get("issue", ""),
            item.get("impact", ""),
            item.get("next_action", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _recipe_reload_summary(
    choices: dict[str, Any],
    *,
    scan: Any | None = None,
    recipe: Any | None = None,
    candidate: Any | None = None,
) -> dict[str, Any]:
    recipe_id = str(choices.get("recipe_id") or "").strip()
    if not recipe_id:
        return {}
    choice_labels = [
        ("selected_eeg_files", "selected EEG files"),
        ("metadata_overrides", "metadata overrides"),
        ("label_carrier_choices", "label carrier choices"),
        ("event_roles", "event roles"),
        ("class_map", "class map"),
    ]
    reapplied = [label for key, label in choice_labels if choices.get(key)]
    if reapplied:
        message = (
            "Saved recipe choices were reapplied before validation: "
            + ", ".join(reapplied)
            + "."
        )
    else:
        message = "Saved recipe source was rescanned before validation."
    diff_rows = _recipe_reload_diff_rows(
        recipe=recipe,
        scan=scan,
        candidate=candidate,
        reapplied_choice_types=reapplied,
    )
    changed = any(row.get("status") == "Changed" for row in diff_rows)
    return {
        "recipe_id": recipe_id,
        "status": "needs_review" if changed else "matched",
        "reapplied_choice_types": reapplied,
        "message": message,
        "diff_rows": diff_rows,
        "eeg_file_remap_options": _eeg_file_remap_options(
            recipe=recipe,
            scan=scan,
        ),
        "label_carrier_remap_options": _label_carrier_remap_options(
            recipe=recipe,
            scan=scan,
        ),
    }


def _eeg_file_remap_options(
    *,
    recipe: Any | None,
    scan: Any | None,
) -> list[dict[str, Any]]:
    if recipe is None or scan is None:
        return []
    saved = _raw_paths(getattr(recipe, "selected_eeg_files", []))
    current = _raw_paths(getattr(scan, "eeg_files", []))
    return _replacement_options(saved=saved, current=current)


def _label_carrier_remap_options(
    *,
    recipe: Any | None,
    scan: Any | None,
) -> list[dict[str, Any]]:
    if recipe is None or scan is None:
        return []
    saved = _raw_label_carrier_paths(recipe)
    current = _raw_paths(getattr(scan, "label_carriers", []))
    return _replacement_options(saved=saved, current=current)


def _replacement_options(
    *,
    saved: list[str],
    current: list[str],
) -> list[dict[str, Any]]:
    if not saved or not current:
        return []
    current_exact = set(current)
    current_names = {Path(item).name or item for item in current}
    candidates = [{"path": item, "name": Path(item).name or item} for item in current]
    options: list[dict[str, Any]] = []
    for saved_path in saved:
        saved_name = Path(saved_path).name or saved_path
        if saved_path in current_exact or saved_name in current_names:
            continue
        options.append(
            {
                "saved": saved_path,
                "saved_name": saved_name,
                "candidates": candidates,
            }
        )
    return options


def _raw_label_carrier_paths(recipe: Any) -> list[str]:
    values = _raw_paths(getattr(recipe, "label_carriers", []))
    if values:
        return values
    return _raw_paths(
        item.get("path")
        for item in getattr(recipe, "label_carrier_plan", [])
        if isinstance(item, dict)
    )


def _raw_paths(values: Any) -> list[str]:
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _recipe_reload_diff_rows(
    *,
    recipe: Any | None,
    scan: Any | None,
    candidate: Any | None,
    reapplied_choice_types: list[str],
) -> list[dict[str, str]]:
    if recipe is None and scan is None and candidate is None:
        return []
    rows: list[dict[str, str]] = []
    saved_files = _path_values(
        getattr(recipe, "selected_eeg_files", []) if recipe is not None else []
    )
    current_files = _path_values(
        getattr(scan, "eeg_files", [])
        if scan is not None
        else getattr(candidate, "selected_eeg_files", [])
    )
    rows.append(
        _path_diff_row(
            item="EEG files",
            saved=saved_files,
            current=current_files,
            saved_label="saved file",
        )
    )

    saved_carriers = _path_values(
        getattr(recipe, "label_carriers", []) if recipe is not None else []
    )
    if not saved_carriers and recipe is not None:
        saved_carriers = _path_values(
            item.get("path")
            for item in getattr(recipe, "label_carrier_plan", [])
            if isinstance(item, dict)
        )
    current_carriers = _path_values(
        getattr(scan, "label_carriers", [])
        if scan is not None
        else getattr(candidate, "label_carriers", [])
    )
    if saved_carriers or current_carriers:
        rows.append(
            _path_diff_row(
                item="Label carriers",
                saved=saved_carriers,
                current=current_carriers,
                saved_label="saved carrier",
            )
        )
    if reapplied_choice_types:
        rows.append(
            {
                "item": "Saved choices",
                "status": "Reapplied",
                "detail": ", ".join(reapplied_choice_types) + ".",
            }
        )
    return rows


def _path_diff_row(
    *,
    item: str,
    saved: list[str],
    current: list[str],
    saved_label: str,
) -> dict[str, str]:
    matched = [name for name in saved if name in set(current)]
    missing = [name for name in saved if name not in set(current)]
    new = [name for name in current if name not in set(saved)]
    if missing or new:
        detail_parts = [
            f"Matched {len(matched)} {saved_label}(s).",
        ]
        if missing:
            detail_parts.append("Missing from scan: " + ", ".join(missing) + ".")
        if new:
            detail_parts.append("New in scan: " + ", ".join(new) + ".")
        return {
            "item": item,
            "status": "Changed",
            "detail": " ".join(detail_parts),
        }
    detail = (
        f"Saved recipe still matches {len(matched)} {saved_label}(s)."
        if saved
        else f"Current scan has {len(current)} item(s); recipe had no saved selection."
    )
    return {
        "item": item,
        "status": "Matched",
        "detail": detail,
    }


def _path_values(values: Any) -> list[str]:
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if not text:
            continue
        name = Path(text).name or text
        if name not in result:
            result.append(name)
    return result


def _serialize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return value
