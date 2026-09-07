"""User-facing labels for backend workflow state and commands."""

from __future__ import annotations

import re
from typing import Any

from XBrainLab.backend.application.commands import CommandName
from XBrainLab.backend.application.pipeline_stage import (
    WORKFLOW_COMMAND_LABELS,
    pipeline_stage_contract,
    pipeline_stage_status_label,
    workflow_command_label,
)
from XBrainLab.product_language import tool_action_label as shared_tool_action_label

COMMAND_LABELS = WORKFLOW_COMMAND_LABELS

DECISION_FIELD_LABELS: dict[str, str] = {
    "epoch_window": "EEG epoch window",
    "target_event": "target events",
    "event_mapping": "event mapping",
    "label_alignment": "label alignment",
    "label_placement": "label placement",
    "metadata": "metadata",
    "metadata_review": "metadata review",
    "label_source": "label source",
    "label_matching": "label matching",
    "import_review": "import review",
    "preprocess_settings": "preprocessing settings",
    "split_strategy": "split strategy",
    "batch_size": "batch size",
    "device": "training device",
    "model": "model",
    "saliency_method": "saliency methods",
}

_INTERNAL_FOLD_NAME = re.compile(r"^fold(?:[_ -]?\d+)?$", re.IGNORECASE)
_GENERATED_SUBJECT_FOLD_NAME = re.compile(r"^Subject-(?P<subject>.+)_(?P<fold>\d+)$")


def command_label(command_name: str | CommandName) -> str:
    """Return a user-facing label for an application command."""
    return workflow_command_label(command_name)


def command_labels(command_names: list[str] | tuple[str, ...]) -> list[str]:
    """Return user-facing labels for application command names."""
    return [command_label(name) for name in command_names]


def tool_action_label(tool_name: str) -> str:
    """Return a user-facing label for an assistant tool/action name."""
    return shared_tool_action_label(tool_name)


def decision_field_label(field_name: str) -> str:
    """Return product language for one backend decision-field identifier."""
    normalized = str(field_name or "").strip().lower()
    return DECISION_FIELD_LABELS.get(normalized, normalized.replace("_", " "))


def decision_field_labels(field_names: tuple[str, ...]) -> list[str]:
    """Return unique product labels while preserving backend field order."""
    labels: list[str] = []
    for field_name in field_names:
        label = decision_field_label(field_name)
        if label and label not in labels:
            labels.append(label)
    return labels


def workflow_stage_label(state: Any) -> str:
    """Return product language for the backend-published workflow stage."""
    return pipeline_stage_status_label(getattr(state, "pipeline_stage", None))


def workflow_stage_text_label(stage: str) -> str:
    """Translate a raw pipeline stage string into product language."""
    return pipeline_stage_status_label(stage)


def workflow_stage_hint(stage: str | None) -> str:
    """Return status and next action from one backend-published stage."""
    try:
        contract = pipeline_stage_contract(stage or "")
    except ValueError:
        return pipeline_stage_status_label(stage)
    if contract.next_command is None:
        return contract.status_label
    return f"{contract.status_label} · {command_label(contract.next_command)}"


def fold_display_label(fold_index: int, source_name: str = "") -> str:
    """Return a 1-based fold label without repeating internal identifiers."""
    label = f"Fold {fold_index + 1}"
    descriptor = str(source_name or "").strip()
    if not descriptor or _INTERNAL_FOLD_NAME.fullmatch(descriptor):
        return label
    generated_subject_fold = _GENERATED_SUBJECT_FOLD_NAME.fullmatch(descriptor)
    if generated_subject_fold is not None:
        return (
            f"{label} (Subject-{generated_subject_fold['subject']}-"
            f"{int(generated_subject_fold['fold']) + 1})"
        )
    return f"{label} ({descriptor})"


def run_display_label(run_index: int) -> str:
    """Return the canonical 1-based run label used by result selectors."""
    return f"Run {run_index + 1}"
