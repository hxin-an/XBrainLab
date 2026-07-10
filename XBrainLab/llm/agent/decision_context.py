"""Workflow decision context for bounded Copilot-style agent turns.

This module keeps workflow truth outside the LLM conversation history.  The
LLM receives a compact decision packet derived from ApplicationService state
and capability policy, then chooses language or a listed action around that
packet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from XBrainLab.backend.application import CommandName, get_application_service
from XBrainLab.backend.application.capabilities import CapabilityPolicy
from XBrainLab.ui.product_language import command_label, workflow_stage_label

STEP_BY_STEP_MODE = "step_by_step"
CONTINUE_UNTIL_DECISION_MODE = "continue_until_decision"


@dataclass(frozen=True)
class WorkflowDecisionContext:
    """Compact state-driven context for one assistant turn."""

    mode: str
    workflow_stage: str
    latest_user_request: str
    recommended_next_step: str | None = None
    recommended_label: str | None = None
    can_auto_continue: bool = False
    decision_needed: list[str] = field(default_factory=list)
    suggested_values: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    allowed_actions: list[str] = field(default_factory=list)
    existing_ui_surface: str | None = None
    stop_reason: str | None = None

    def format_for_prompt(self) -> str:
        """Return a stable, compact prompt section."""
        lines = [
            "Workflow Decision Context:",
            f"- mode: {self.mode}",
            f"- workflow_stage: {self.workflow_stage}",
            f"- latest_user_request: {self.latest_user_request or '(none)'}",
            (f"- recommended_next_step: {self.recommended_next_step or '(none)'}"),
            f"- recommended_label: {self.recommended_label or '(none)'}",
            f"- can_auto_continue: {str(self.can_auto_continue).lower()}",
            "- decision_needed: " + _format_list(self.decision_needed),
            "- existing_ui_surface: " + (self.existing_ui_surface or "(none)"),
            "- allowed_actions: " + _format_list(self.allowed_actions),
            "- blocked_reasons: " + _format_list(self.blocked_reasons),
            "- evidence: " + _format_list(self.evidence),
            "- stop_reason: " + (self.stop_reason or "(none)"),
        ]
        if self.suggested_values:
            lines.append(f"- suggested_values: {self.suggested_values}")
        return "\n".join(lines)


def build_workflow_decision_context(
    study: Any,
    latest_user_text: str = "",
    mode: str = STEP_BY_STEP_MODE,
) -> WorkflowDecisionContext:
    """Build a state/capability-driven decision packet for the LLM."""
    normalized_mode = normalize_workflow_mode(mode)
    try:
        service = get_application_service(study)
        state = service.get_state()
        capabilities = service.get_capabilities()
    except Exception:
        return WorkflowDecisionContext(
            mode=normalized_mode,
            workflow_stage="Workflow status unavailable",
            latest_user_request=latest_user_text.strip(),
            blocked_reasons=["ApplicationService state is unavailable."],
            stop_reason="status_unavailable",
        )

    recommended = recommended_next_step(state, capabilities)
    if recommended is None:
        return WorkflowDecisionContext(
            mode=normalized_mode,
            workflow_stage=workflow_stage_label(state),
            latest_user_request=latest_user_text.strip(),
            blocked_reasons=_top_blocked_reasons(capabilities),
            stop_reason="no_available_workflow_step",
        )

    capability = capabilities.get(recommended)
    decision_needed = _decision_needed_for(recommended, state)
    existing_surface = _existing_ui_surface_for(recommended)
    boundary_stop = _stop_reason_for(recommended, capability, decision_needed)
    can_auto_continue = (
        normalized_mode == CONTINUE_UNTIL_DECISION_MODE
        and capability.enabled
        and capability.can_auto_execute
        and not decision_needed
        and not capability.requires_confirmation
        and not capability.confirmation_required
        and not capability.stop_after_success
    )

    return WorkflowDecisionContext(
        mode=normalized_mode,
        workflow_stage=workflow_stage_label(state),
        latest_user_request=latest_user_text.strip(),
        recommended_next_step=recommended,
        recommended_label=command_label(recommended),
        can_auto_continue=can_auto_continue,
        decision_needed=decision_needed,
        evidence=_evidence_for(recommended, state),
        blocked_reasons=list(capability.reasons),
        allowed_actions=_allowed_actions_for(recommended, capability),
        existing_ui_surface=existing_surface,
        stop_reason=boundary_stop,
    )


def normalize_workflow_mode(mode: str | None) -> str:
    """Normalize UI/runtime mode names to prompt-facing workflow modes."""
    value = str(mode or "").strip().lower()
    if value in {"multi", "continue", "continue_until_decision"}:
        return CONTINUE_UNTIL_DECISION_MODE
    return STEP_BY_STEP_MODE


def recommended_next_step(
    state: Any,
    capabilities: CapabilityPolicy,
) -> str | None:
    """Return the shared next command for assistant policy and product status."""
    active_dataset = state.active_dataset
    training = state.training
    evaluation = state.evaluation

    interpretation_step = _interpretation_next_step(state)
    if interpretation_step is not None:
        candidates = [interpretation_step]
    elif evaluation.finished_runs:
        candidates = [
            CommandName.EVALUATE.value,
            CommandName.VISUALIZE.value,
            CommandName.SALIENCY.value,
        ]
    elif active_dataset.has_datasets:
        candidates = [
            CommandName.TRAIN.value
            if training.has_model and training.has_training_option
            else CommandName.CONFIGURE_TRAINING.value
        ]
    elif active_dataset.has_epoch_data:
        candidates = [CommandName.GENERATE_DATASET.value]
    elif active_dataset.has_preprocessed_data:
        candidates = [CommandName.CREATE_EPOCH.value]
    elif active_dataset.has_raw_data:
        candidates = [CommandName.PREPROCESS.value]
    else:
        candidates = [CommandName.SCAN_SOURCE.value]

    for command_name in candidates:
        capability = capabilities.get(command_name)
        if capability is not None and capability.enabled:
            return command_name
    return candidates[0] if candidates else None


def _interpretation_next_step(state: Any) -> str | None:
    interpretation = getattr(state, "interpretation", None)
    if interpretation is None:
        return None
    if getattr(interpretation, "has_applied_interpretation", False):
        return None
    if getattr(interpretation, "has_validation_decision", False):
        return CommandName.APPLY_INTERPRETATION.value
    if getattr(interpretation, "has_candidate", False):
        return CommandName.VALIDATE_INTERPRETATION.value
    if getattr(interpretation, "has_scan_result", False):
        return CommandName.PREVIEW_INTERPRETATION.value
    if getattr(interpretation, "source_path", None) and not getattr(
        state.active_dataset,
        "has_raw_data",
        False,
    ):
        return CommandName.SCAN_SOURCE.value
    return None


def _decision_needed_for(command_name: str, state: Any) -> list[str]:
    if command_name == CommandName.SCAN_SOURCE.value:
        source_path = getattr(state.interpretation, "source_path", None)
        return [] if source_path else ["source_path"]
    if command_name == CommandName.CREATE_EPOCH.value:
        return ["target_event", "epoch_window"]
    if command_name == CommandName.GENERATE_DATASET.value:
        return ["split_strategy"]
    if command_name == CommandName.CONFIGURE_TRAINING.value:
        missing = []
        if not state.training.has_model:
            missing.append("model")
        if not state.training.has_training_option:
            missing.append("training_options")
        return missing or ["training_options"]
    return []


def _existing_ui_surface_for(command_name: str) -> str | None:
    return {
        CommandName.SCAN_SOURCE.value: "Data Import wizard",
        CommandName.REVIEW_INTERPRETATION.value: "Data Import wizard",
        CommandName.PREVIEW_INTERPRETATION.value: "Data Import wizard",
        CommandName.VALIDATE_INTERPRETATION.value: "Data Import wizard",
        CommandName.APPLY_INTERPRETATION.value: "Data Import wizard",
        CommandName.PREPROCESS.value: "Preprocess panel",
        CommandName.CREATE_EPOCH.value: "Epoch dialog",
        CommandName.GENERATE_DATASET.value: "Dataset split dialog",
        CommandName.CONFIGURE_TRAINING.value: "Training settings",
        CommandName.TRAIN.value: "Training panel confirmation",
        CommandName.EVALUATE.value: "Evaluation panel",
        CommandName.VISUALIZE.value: "Visualization panel",
        CommandName.SALIENCY.value: "Saliency settings",
    }.get(command_name)


def _stop_reason_for(
    command_name: str,
    capability: Any,
    decision_needed: list[str],
) -> str | None:
    if decision_needed:
        return "user_decision_required"
    if capability.requires_confirmation or capability.confirmation_required:
        return capability.decision_boundary or "confirmation_required"
    if capability.long_running:
        return "long_running"
    if capability.destructive:
        return "destructive"
    if capability.stop_after_success:
        return capability.decision_boundary or "stop_after_success"
    if command_name == CommandName.SCAN_SOURCE.value:
        return "needs_data_source"
    return None


def _allowed_actions_for(command_name: str, capability: Any) -> list[str]:
    actions = [command_name]
    surface = _existing_ui_surface_for(command_name)
    if surface:
        actions.append("open_existing_ui_surface")
    if capability.reasons:
        actions.append("explain_blocker")
    return actions


def _evidence_for(command_name: str, state: Any) -> list[str]:
    active_dataset = state.active_dataset
    interpretation = getattr(state, "interpretation", None)
    if command_name == CommandName.SCAN_SOURCE.value:
        source_path = getattr(interpretation, "source_path", None)
        if source_path:
            return [f"Data source is selected: {source_path}."]
        return ["No raw EEG data is loaded in the active session."]
    if command_name == CommandName.PREVIEW_INTERPRETATION.value:
        return [
            "A data source scan is ready for import preview.",
            _interpretation_reference(interpretation),
        ]
    if command_name == CommandName.VALIDATE_INTERPRETATION.value:
        return [
            "An import interpretation candidate is ready for validation.",
            _interpretation_reference(interpretation),
        ]
    if command_name == CommandName.APPLY_INTERPRETATION.value:
        decision = getattr(interpretation, "validation_decision", None)
        return [
            f"Import validation decision: {decision or 'ready'}.",
            _interpretation_reference(interpretation),
        ]
    if command_name == CommandName.PREPROCESS.value:
        return [f"{state.raw.count} raw EEG file(s) are loaded."]
    if command_name == CommandName.CREATE_EPOCH.value:
        return [f"{state.preprocessed.count} preprocessed item(s) are available."]
    if command_name == CommandName.GENERATE_DATASET.value:
        return ["Epoch data is available."]
    if command_name == CommandName.CONFIGURE_TRAINING.value:
        return ["A generated dataset is available."]
    if command_name == CommandName.TRAIN.value:
        return ["Dataset, model, and training options are configured."]
    if active_dataset.has_datasets:
        return ["A generated dataset is available."]
    return []


def _interpretation_reference(interpretation: Any) -> str:
    for attr in (
        "latest_candidate_id",
        "latest_preview_id",
        "latest_scan_id",
        "source_path",
    ):
        value = getattr(interpretation, attr, None)
        if value:
            return f"Import reference: {value}."
    return "Import reference is available in ApplicationService state."


def _top_blocked_reasons(capabilities: CapabilityPolicy) -> list[str]:
    reasons: list[str] = []
    for command_name in (
        CommandName.TRAIN.value,
        CommandName.GENERATE_DATASET.value,
        CommandName.CREATE_EPOCH.value,
        CommandName.PREPROCESS.value,
    ):
        capability = capabilities.get(command_name)
        reasons.extend(capability.reasons[:2])
        if reasons:
            return reasons
    return reasons


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "(none)"
