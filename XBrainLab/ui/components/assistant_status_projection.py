"""Typed workflow status projected from one atomic application publication."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from XBrainLab.backend.application.commands import CommandName
from XBrainLab.backend.application.view_publication import (
    PUBLIC_VIEW_UNAVAILABLE_MESSAGE,
    ApplicationViewPublication,
)
from XBrainLab.backend.application.workflow_projection import (
    build_workflow_projection,
)
from XBrainLab.ui.chat.status_presenter import assistant_footer_hint
from XBrainLab.ui.product_language import (
    command_label,
    decision_field_labels,
    workflow_stage_label,
)


class AssistantWorkflowSurface(str, Enum):
    """Existing product surface that owns a projected workflow decision."""

    DATA_IMPORT = "Data Import"
    PREPROCESSING = "Preprocessing"
    EPOCH_SETTINGS = "EEG epoch settings"
    DATASET_SPLIT = "Dataset split"
    TRAINING_SETTINGS = "Training settings"
    TRAINING = "Training"
    EVALUATION = "Evaluation"
    VISUALIZATION = "Visualization"


@dataclass(frozen=True)
class AssistantStatusProjection:
    """One render-ready workflow status tied to a publication generation."""

    publication_generation: int
    usable: bool
    stage: str
    recommended_command: str | None = None
    blocked_command: str | None = None
    recommended_label: str | None = None
    decision_fields: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    blocked_reasons: tuple[str, ...] = ()
    existing_ui_surface: AssistantWorkflowSurface | None = None
    available_commands: tuple[str, ...] = ()
    blocked_reason: str | None = None
    tooltip: str = ""
    footer_hint: str = ""
    publication_revision: int = 1


_COMMAND_SURFACES: dict[str, AssistantWorkflowSurface] = {
    CommandName.SCAN_SOURCE.value: AssistantWorkflowSurface.DATA_IMPORT,
    CommandName.REVIEW_INTERPRETATION.value: AssistantWorkflowSurface.DATA_IMPORT,
    CommandName.PREVIEW_INTERPRETATION.value: AssistantWorkflowSurface.DATA_IMPORT,
    CommandName.VALIDATE_INTERPRETATION.value: AssistantWorkflowSurface.DATA_IMPORT,
    CommandName.APPLY_INTERPRETATION.value: AssistantWorkflowSurface.DATA_IMPORT,
    CommandName.RELOAD_INTERPRETATION_RECIPE.value: (
        AssistantWorkflowSurface.DATA_IMPORT
    ),
    CommandName.PREPROCESS.value: AssistantWorkflowSurface.PREPROCESSING,
    CommandName.CREATE_EPOCH.value: AssistantWorkflowSurface.EPOCH_SETTINGS,
    CommandName.CONFIGURE_DATASET_SPLIT.value: AssistantWorkflowSurface.DATASET_SPLIT,
    CommandName.CONFIGURE_TRAINING.value: (AssistantWorkflowSurface.TRAINING_SETTINGS),
    CommandName.TRAIN.value: AssistantWorkflowSurface.TRAINING,
    CommandName.EVALUATE.value: AssistantWorkflowSurface.EVALUATION,
    CommandName.VISUALIZE.value: AssistantWorkflowSurface.VISUALIZATION,
    CommandName.SALIENCY.value: AssistantWorkflowSurface.VISUALIZATION,
}


def build_assistant_status_projection(
    publication: ApplicationViewPublication,
) -> AssistantStatusProjection:
    """Build UI status from one atomic state/capability publication."""
    if not isinstance(publication, ApplicationViewPublication):
        raise TypeError(
            "Assistant status requires an ApplicationViewPublication.",
        )

    if not publication.usable or not publication.state.state_reliable:
        reason = (
            publication.public_unavailable_reason or PUBLIC_VIEW_UNAVAILABLE_MESSAGE
        )
        stage = "Workflow status unavailable"
        return AssistantStatusProjection(
            publication_generation=publication.generation,
            publication_revision=publication.revision,
            usable=False,
            stage=stage,
            blocked_reasons=(reason,),
            blocked_reason=reason,
            tooltip=reason,
            footer_hint="Workflow status unavailable · Try again",
        )

    capabilities = publication.effective_capabilities
    workflow = build_workflow_projection(publication.state, capabilities)
    recommended = workflow.recommended_command
    action_command = (
        recommended
        or workflow.blocked_command
        or next(iter(workflow.execution_controls), None)
    )
    surface = _COMMAND_SURFACES.get(action_command or "")
    blocked_reasons = tuple(workflow.blocked_reasons)
    blocked_reason = "; ".join(blocked_reasons) or None
    stage = workflow_stage_label(publication.state)
    available_commands = _assistant_available_commands(
        recommended_command=recommended,
        execution_controls=workflow.execution_controls,
    )
    recommended_label = command_label(recommended) if recommended else None
    display_labels = [recommended_label] if recommended_label else []

    return AssistantStatusProjection(
        publication_generation=publication.generation,
        publication_revision=publication.revision,
        usable=True,
        stage=stage,
        recommended_command=recommended,
        blocked_command=workflow.blocked_command,
        recommended_label=recommended_label,
        decision_fields=tuple(workflow.decision_fields),
        evidence=tuple(workflow.evidence),
        blocked_reasons=blocked_reasons,
        existing_ui_surface=surface,
        available_commands=available_commands,
        blocked_reason=blocked_reason,
        tooltip=_status_tooltip(
            stage=stage,
            recommended_label=recommended_label,
            blocked_command=workflow.blocked_command,
            decision_fields=tuple(workflow.decision_fields),
            evidence=tuple(workflow.evidence),
            blocked_reasons=blocked_reasons,
            surface=surface,
        ),
        footer_hint=assistant_footer_hint(
            stage,
            display_labels,
            blocked_reason,
        ),
    )


def _assistant_available_commands(
    *,
    recommended_command: str | None,
    execution_controls: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Expose backend-projected workflow actions and explicit runtime controls."""
    commands = (recommended_command,) if recommended_command else ()
    return commands + tuple(
        command for command in execution_controls if command not in commands
    )


def _status_tooltip(
    *,
    stage: str,
    recommended_label: str | None,
    blocked_command: str | None,
    decision_fields: tuple[str, ...],
    evidence: tuple[str, ...],
    blocked_reasons: tuple[str, ...],
    surface: AssistantWorkflowSurface | None,
) -> str:
    lines = [f"Workflow stage: {stage}"]
    if recommended_label:
        lines.append(f"Suggested next action: {recommended_label}")
    elif blocked_command:
        lines.append(f"Blocked next action: {command_label(blocked_command)}")
    else:
        lines.append("Suggested next action: none")
    if surface is not None:
        lines.append(f"Continue in: {surface.value}")
    fields = decision_field_labels(decision_fields)
    if fields:
        lines.append("Required choices: " + ", ".join(fields))
    if blocked_reasons:
        lines.append("Action required: " + "; ".join(blocked_reasons))
    if evidence:
        lines.append("Workflow evidence: " + " ".join(evidence))
    return "\n".join(lines)
