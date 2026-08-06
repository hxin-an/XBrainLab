"""Review and validation boundaries for Data Interpretation candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any

from .data_interpretation_content_identity import assert_review_content_unchanged
from .data_interpretation_path_identity import (
    normalized_path_identity,
    path_basename,
    resolve_scan_path,
)
from .data_interpretation_public_projection import (
    project_bids_review,
    project_label_carrier_plan,
)
from .errors import PreconditionError


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
    action_items: list[dict[str, str]] = dc_field(default_factory=list)
    label_carrier_preview: list[dict[str, Any]] = dc_field(default_factory=list)
    metadata_preview: list[dict[str, Any]] = dc_field(default_factory=list)
    format_capabilities: list[dict[str, Any]] = dc_field(default_factory=list)
    warnings: list[str] = dc_field(default_factory=list)
    confirmation_items: list[str] = dc_field(default_factory=list)
    blocked_reasons: list[str] = dc_field(default_factory=list)
    downstream_impacts: list[str] = dc_field(default_factory=list)
    bids: dict[str, Any] = dc_field(default_factory=dict)
    event_roles: dict[str, str] = dc_field(default_factory=dict)
    class_map: dict[str, str] = dc_field(default_factory=dict)
    class_map_source: str = ""
    internal_event_preview: dict[str, Any] = dc_field(default_factory=dict)
    recipe_reload_summary: dict[str, Any] = dc_field(default_factory=dict)
    resource_preflight: dict[str, Any] = dc_field(default_factory=dict)
    content_identity: dict[str, Any] = dc_field(default_factory=dict)

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
    resource_preflight: dict[str, Any] | None = None,
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
        action_items=_build_action_items(candidate),
        label_carrier_preview=project_label_carrier_plan(candidate.label_carrier_plan),
        metadata_preview=metadata_preview,
        format_capabilities=[dict(item) for item in candidate.format_capabilities],
        warnings=list(candidate.warnings),
        confirmation_items=list(candidate.confirmation_items),
        blocked_reasons=list(candidate.blocked_reasons),
        downstream_impacts=[
            "Applying this interpretation will replace active raw data and "
            "invalidate downstream preprocessing, EEG epochs, datasets, training, "
            "and saliency for the current session.",
        ],
        bids=project_bids_review(getattr(candidate, "bids", {}) or {}),
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
        resource_preflight=dict(resource_preflight or {}),
        content_identity=dict(getattr(candidate, "content_identity", {}) or {}),
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


def validate_interpretation_candidate(
    candidate: Any,
    *,
    recheck_content_identity: bool = True,
) -> ValidationDecision:
    """Validate a candidate using reviewable safe/confirm/blocked decisions."""
    identity_error = (
        _review_content_identity_error(candidate) if recheck_content_identity else None
    )
    identity_reasons = [str(identity_error)] if identity_error is not None else []
    if candidate.blocked_reasons or identity_reasons:
        blocked_reasons = [*candidate.blocked_reasons, *identity_reasons]
        action_items = _build_action_items(candidate)
        if identity_error is not None:
            action_items.append(
                _action_item(
                    issue=str(identity_error),
                    impact=(
                        "The reviewed label/event content is no longer the content "
                        "that would be imported."
                    ),
                    next_action=(
                        "Preview and review the label source again before import."
                    ),
                    target_step="Load Labels",
                    severity="blocked",
                )
            )
        return ValidationDecision(
            candidate_id=candidate.candidate_id,
            decision="blocked",
            reasons=["Interpretation cannot be applied until blockers are resolved."],
            warnings=list(candidate.warnings),
            blocked_reasons=list(dict.fromkeys(blocked_reasons)),
            downstream_impacts=[
                "Preprocessing, EEG epoch creation, dataset generation, and training "
                "remain blocked.",
            ],
            action_items=_dedupe_action_items(action_items),
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
            "EEG epoching, dataset generation, training, and saliency.",
        ],
        action_items=_build_action_items(candidate),
    )


def _review_content_identity_error(candidate: Any) -> PreconditionError | None:
    has_identity_contract = hasattr(candidate, "content_identity")
    expected = getattr(candidate, "content_identity", {}) or {}
    selected_eeg_files = list(getattr(candidate, "selected_eeg_files", []) or [])
    if not expected and (not has_identity_contract or not selected_eeg_files):
        return None
    try:
        assert_review_content_unchanged(
            expected=expected,
            label_carrier_plan=list(getattr(candidate, "label_carrier_plan", []) or []),
            selected_eeg_files=selected_eeg_files,
            class_map=getattr(candidate, "class_map", {}) or {},
            event_roles=getattr(candidate, "event_roles", {}) or {},
            run_event_mappings=getattr(candidate, "run_event_mappings", {}) or {},
            candidate_id=str(getattr(candidate, "candidate_id", "") or "") or None,
        )
    except PreconditionError as exc:
        return exc
    return None


def _build_action_items(candidate: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    choices = getattr(candidate, "choices", {}) or {}
    skip_labels = bool(isinstance(choices, dict) and choices.get("skip_labels"))
    event_value_items = _event_value_decision_action_items(candidate)
    items.extend(event_value_items)
    blocked_reasons = _unique_strings(getattr(candidate, "blocked_reasons", []))
    confirmation_items = _unique_strings(getattr(candidate, "confirmation_items", []))
    if event_value_items:
        blocked_reasons = [
            reason
            for reason in blocked_reasons
            if not _is_event_value_consequence(reason)
        ]
        confirmation_items = [
            item for item in confirmation_items if not _is_event_value_consequence(item)
        ]

    items.extend(
        [
            _action_item(
                issue=reason,
                impact="This import cannot be applied until the issue is fixed.",
                next_action="Fix this item before importing.",
                target_step=_target_step_for_text(reason),
                severity="blocked",
            )
            for reason in blocked_reasons
        ]
    )
    items.extend(
        [_confirmation_action_item(confirmation) for confirmation in confirmation_items]
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
    elif not label_carriers and not _uses_internal_event_labels(candidate):
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


def _confirmation_action_item(confirmation: str) -> dict[str, str]:
    """Describe one review choice in terms of its concrete workflow consequence."""
    target_step = _target_step_for_text(confirmation)
    impact, next_action = _confirmation_guidance(
        confirmation,
        target_step=target_step,
    )
    return _action_item(
        issue=confirmation,
        impact=impact,
        next_action=next_action,
        target_step=target_step,
        severity="needs_confirmation",
    )


def _confirmation_guidance(
    confirmation: str,
    *,
    target_step: str,
) -> tuple[str, str]:
    lowered = confirmation.casefold()
    if target_step == "Review Metadata":
        return (
            "Files may be grouped under the wrong subject, session, task, or run "
            "in the import recipe.",
            "Set or confirm the missing values in Review Metadata.",
        )
    if target_step == "Match Labels" and any(
        marker in lowered
        for marker in (
            "which events",
            "event role",
            "trial anchor",
            "artifact",
            "boundary",
        )
    ):
        return (
            "Class, timing, artifact, or system events could be mistaken for "
            "training labels or omitted from the import.",
            "Assign each event role in Match Labels.",
        )
    if target_step == "Match Labels" and any(
        marker in lowered for marker in ("align", "pair", "placement", "follows")
    ):
        return (
            "Labels could be paired with the wrong EEG recording or event sequence.",
            "Review EEG-to-label pairing and alignment in Match Labels.",
        )
    if target_step == "Match Labels":
        return (
            "XBrainLab cannot safely associate the selected labels with EEG events "
            "until this mapping is reviewed.",
            "Review the label source, placement, and class mapping in Match Labels.",
        )
    if target_step == "Load Labels":
        return (
            "A missing or ambiguous label source limits supervised EEG epoching and "
            "training.",
            "Choose the label files used by this import in Load Labels.",
        )
    if target_step == "Choose EEG Data":
        return (
            "The import scope may include the wrong recordings or omit selected EEG "
            "files.",
            "Review the selected EEG files and scan location in Choose EEG Data.",
        )
    return (
        "The import recipe is not ready to apply until this choice is reviewed.",
        "Resolve this item in Review and Import.",
    )


def _event_value_decision_action_items(candidate: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    plans = getattr(candidate, "label_carrier_plan", []) or []
    if not isinstance(plans, list):
        return items
    for plan in plans:
        if not isinstance(plan, dict):
            continue
        unresolved = _unique_strings(plan.get("unresolved_values", []))
        if not unresolved:
            continue
        carrier_name = str(
            plan.get("name") or Path(str(plan.get("path") or "")).name
        ).strip()
        display_name = carrier_name or "the selected label file"
        preview = ", ".join(unresolved[:5])
        if len(unresolved) > 5:
            preview += f" +{len(unresolved) - 5} more"
        items.append(
            _action_item(
                issue=f"Event value decisions are incomplete for {display_name}.",
                impact=(
                    f"{len(unresolved)} observed values cannot be placed yet: "
                    f"{preview}."
                ),
                next_action=("Choose a role and use for each value in Match Labels."),
                target_step="Match Labels",
                severity="blocked",
            )
        )
    return items


def _is_event_value_consequence(text: str) -> bool:
    lowered = str(text).casefold()
    return any(
        marker in lowered
        for marker in (
            "complete role/keep/class decisions",
            "no complete semantic decision",
            "no selected-label bids event rows are approved",
            "no usable selected-label bids events remain",
        )
    )


def _uses_internal_event_labels(candidate: Any) -> bool:
    choices = getattr(candidate, "choices", {}) or {}
    if isinstance(choices, dict) and str(choices.get("label_carrier") or "") == (
        "embedded_events"
    ):
        return True
    selection = getattr(candidate, "internal_event_selection", {}) or {}
    if not isinstance(selection, dict):
        return False
    label_event_codes = selection.get("label_event_codes", [])
    return any(str(item).strip() for item in label_event_codes)


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


def target_step_for_interpretation_text(text: str) -> str:
    """Return the wizard step that should resolve an interpretation review item."""
    lowered = text.lower()
    if any(token in lowered for token in ("label", "event", "carrier")):
        load_label_markers = (
            "no external label file",
            "no label file",
            "no events.tsv carrier",
            "events.tsv was not found",
            "label source did not contain",
            "label source is empty",
            "label carrier was not found",
            "missing label carrier",
        )
        if any(marker in lowered for marker in load_label_markers):
            return "Load Labels"
        return "Match Labels"
    if any(token in lowered for token in ("eeg file", "source", "scan")):
        return "Choose EEG Data"
    if any(
        token in lowered for token in ("subject", "session", "task", "run", "metadata")
    ):
        return "Review Metadata"
    return "Review and Import"


def _target_step_for_text(text: str) -> str:
    return target_step_for_interpretation_text(text)


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
    all_candidates = [{"path": item, "name": path_basename(item)} for item in current]
    options: list[dict[str, Any]] = []
    for saved_path in saved:
        match = resolve_scan_path(saved_path, current)
        if match.accepted:
            continue
        candidate_paths = (
            list(match.candidates) if match.status == "ambiguous" else list(current)
        )
        candidates = [
            {"path": item, "name": path_basename(item)} for item in candidate_paths
        ]
        options.append(
            {
                "saved": saved_path,
                "saved_name": path_basename(saved_path),
                "candidates": candidates or all_candidates,
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
    saved_identity = (
        getattr(recipe, "content_identity", {}) if recipe is not None else {}
    )
    current_identity = (
        getattr(candidate, "content_identity", {}) if candidate is not None else {}
    )
    if saved_identity and current_identity:
        matched = saved_identity.get("scope_sha256") == current_identity.get(
            "scope_sha256"
        )
        rows.append(
            {
                "item": "Reviewed label content",
                "status": "Matched" if matched else "Changed",
                "detail": (
                    "Label/event carrier content matches the saved recipe."
                    if matched
                    else "Label/event carrier content changed and requires review."
                ),
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
    matches = [resolve_scan_path(path, current) for path in saved]
    matched = [match for match in matches if match.accepted]
    unresolved = [match for match in matches if not match.accepted]
    consumed = {
        normalized_path_identity(match.resolved) for match in matched if match.resolved
    }
    new = [path for path in current if normalized_path_identity(path) not in consumed]
    moved = [
        match
        for match in matched
        if match.status == "unique_basename"
        and normalized_path_identity(match.requested)
        != normalized_path_identity(match.resolved)
    ]
    if unresolved or new or moved:
        detail_parts = [
            f"Matched {len(matched)} {saved_label}(s).",
        ]
        missing = [match for match in unresolved if match.status == "missing"]
        ambiguous = [match for match in unresolved if match.status == "ambiguous"]
        if missing:
            detail_parts.append(
                "Missing from scan: "
                + ", ".join(_display_paths([match.requested])[0] for match in missing)
                + "."
            )
        if ambiguous:
            detail_parts.append(
                "Ambiguous in scan: "
                + "; ".join(
                    f"{match.requested} matches " + ", ".join(match.candidates)
                    for match in ambiguous
                )
                + "."
            )
        if moved:
            detail_parts.append(
                "Unique-name relocation: "
                + "; ".join(f"{match.requested} -> {match.resolved}" for match in moved)
                + "."
            )
        if new:
            detail_parts.append("New in scan: " + ", ".join(_display_paths(new)) + ".")
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
        if text not in result:
            result.append(text)
    return result


def _display_paths(values: list[str]) -> list[str]:
    """Use compact names unless duplicate names require full identities."""
    counts: dict[str, int] = {}
    for value in values:
        name = path_basename(value)
        counts[name.casefold()] = counts.get(name.casefold(), 0) + 1
    return [
        value
        if counts.get(path_basename(value).casefold(), 0) > 1
        else path_basename(value)
        for value in values
    ]


def _serialize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return value
