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
from XBrainLab.backend.application.pipeline_stage import (
    pipeline_stage_status_label,
    workflow_command_label,
)
from XBrainLab.backend.application.view_publication import (
    PUBLIC_VIEW_UNAVAILABLE_MESSAGE,
    ApplicationViewPublication,
)
from XBrainLab.backend.application.workflow_projection import (
    build_workflow_projection,
)

STEP_BY_STEP_MODE = "step_by_step"
CONTINUE_UNTIL_DECISION_MODE = "continue_until_decision"


@dataclass(frozen=True)
class WorkflowDecisionContext:
    """Compact state-driven context for one assistant turn."""

    mode: str
    workflow_stage: str
    latest_user_request: str
    recommended_next_step: str | None = None
    blocked_command: str | None = None
    recommended_label: str | None = None
    can_auto_continue: bool = False
    decision_needed: list[str] = field(default_factory=list)
    suggested_values: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    allowed_actions: list[str] = field(default_factory=list)
    stop_reason: str | None = None

    def format_for_prompt(self) -> str:
        """Return a stable, compact prompt section."""
        lines = [
            "Workflow Decision Context:",
            f"- mode: {self.mode}",
            f"- workflow_stage: {self.workflow_stage}",
            f"- latest_user_request: {self.latest_user_request or '(none)'}",
            f"- can_auto_continue: {str(self.can_auto_continue).lower()}",
            "- decision_needed: " + _format_list(self.decision_needed),
            "- blocked_reasons: " + _format_list(self.blocked_reasons),
            "- evidence: " + _format_list(self.evidence),
            "- stop_reason: " + (self.stop_reason or "(none)"),
        ]
        if self.mode == CONTINUE_UNTIL_DECISION_MODE:
            lines.extend(
                (
                    "- continuation_candidate: "
                    + (self.recommended_next_step or "(none)"),
                    "- continuation_role: backend_advice_not_user_request",
                    "- continuation_allowed_actions: "
                    + _format_list(self.allowed_actions),
                )
            )
        else:
            lines.append("- continuation: disabled_in_step_by_step")
        if self.suggested_values:
            lines.append(f"- suggested_values: {self.suggested_values}")
        return "\n".join(lines)


def build_workflow_decision_context(
    study: Any,
    latest_user_text: str = "",
    mode: str = STEP_BY_STEP_MODE,
    publication: ApplicationViewPublication | None = None,
) -> WorkflowDecisionContext:
    """Build a state/capability-driven decision packet for the LLM."""
    normalized_mode = normalize_workflow_mode(mode)
    try:
        current_publication = publication
        if current_publication is None:
            current_publication = get_application_service(study).get_view_publication()
        state = current_publication.state
        capabilities = current_publication.effective_capabilities
    except Exception:
        return WorkflowDecisionContext(
            mode=normalized_mode,
            workflow_stage="Workflow status unavailable",
            latest_user_request=latest_user_text.strip(),
            blocked_reasons=[PUBLIC_VIEW_UNAVAILABLE_MESSAGE],
            stop_reason="status_unavailable",
        )

    if not current_publication.usable:
        reason = (
            current_publication.unavailable_reason or PUBLIC_VIEW_UNAVAILABLE_MESSAGE
        )
        return WorkflowDecisionContext(
            mode=normalized_mode,
            workflow_stage="Workflow status unavailable",
            latest_user_request=latest_user_text.strip(),
            blocked_reasons=[reason],
            stop_reason="status_unavailable",
        )

    projection = build_workflow_projection(state, capabilities)
    recommended = projection.recommended_command
    blocked_command = projection.blocked_command
    decision_needed = list(projection.decision_fields)
    context_command = recommended or (blocked_command if decision_needed else None)
    if context_command is None:
        return WorkflowDecisionContext(
            mode=normalized_mode,
            workflow_stage=pipeline_stage_status_label(state.pipeline_stage),
            latest_user_request=latest_user_text.strip(),
            blocked_command=blocked_command,
            evidence=list(projection.evidence),
            blocked_reasons=list(projection.blocked_reasons),
            stop_reason=(
                "active_operation"
                if state.active_training.is_running
                else "no_available_workflow_step"
            ),
        )

    capability = capabilities.get(context_command)
    boundary_stop = _stop_reason_for(context_command, capability, decision_needed)
    can_auto_continue = (
        recommended is not None
        and normalized_mode == CONTINUE_UNTIL_DECISION_MODE
        and capability.enabled
        and capability.can_auto_execute
        and not decision_needed
        and not capability.requires_confirmation
        and not capability.confirmation_required
        and not capability.stop_after_success
    )

    return WorkflowDecisionContext(
        mode=normalized_mode,
        workflow_stage=pipeline_stage_status_label(state.pipeline_stage),
        latest_user_request=latest_user_text.strip(),
        recommended_next_step=recommended,
        blocked_command=blocked_command,
        recommended_label=(
            workflow_command_label(recommended) if recommended is not None else None
        ),
        can_auto_continue=can_auto_continue,
        decision_needed=decision_needed,
        evidence=list(projection.evidence),
        blocked_reasons=list(projection.blocked_reasons),
        allowed_actions=(
            _allowed_actions_for(recommended, capability)
            if recommended is not None
            else []
        ),
        stop_reason=boundary_stop,
    )


def normalize_workflow_mode(mode: str | None) -> str:
    """Normalize UI/runtime mode names to prompt-facing workflow modes."""
    value = str(mode or "").strip().lower()
    if value in {"multi", "continue", "continue_until_decision"}:
        return CONTINUE_UNTIL_DECISION_MODE
    return STEP_BY_STEP_MODE


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


def _allowed_actions_for(
    command_name: str,
    capability: Any,
) -> list[str]:
    if not capability.enabled:
        return []
    actions = [command_name]
    if capability.reasons:
        actions.append("explain_blocker")
    return actions


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "(none)"
