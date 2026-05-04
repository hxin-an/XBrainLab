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
    label_carrier_preview: list[dict[str, Any]] = dc_field(default_factory=list)
    metadata_preview: list[dict[str, Any]] = dc_field(default_factory=list)
    format_capabilities: list[dict[str, Any]] = dc_field(default_factory=list)
    warnings: list[str] = dc_field(default_factory=list)
    confirmation_items: list[str] = dc_field(default_factory=list)
    blocked_reasons: list[str] = dc_field(default_factory=list)
    downstream_impacts: list[str] = dc_field(default_factory=list)
    event_roles: dict[str, str] = dc_field(default_factory=dict)
    class_map: dict[str, str] = dc_field(default_factory=dict)
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

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


def build_interpretation_preview(
    *,
    preview_id: str,
    candidate: Any,
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
        recipe_reload_summary=_recipe_reload_summary(
            getattr(candidate, "choices", {}),
        ),
    )


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
    )


def _recipe_reload_summary(choices: dict[str, Any]) -> dict[str, Any]:
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
    return {
        "recipe_id": recipe_id,
        "reapplied_choice_types": reapplied,
        "message": message,
    }


def _serialize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return value
