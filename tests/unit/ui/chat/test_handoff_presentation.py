"""Parity coverage for workflow handoff activity presentation."""

from __future__ import annotations

import pytest

from XBrainLab.llm.agent.assistant_activity import (
    AssistantDecisionOwner,
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRouteDescriptor,
    workflow_ui_handoff_routes,
)
from XBrainLab.ui.chat.presentation import (
    ChatTurnCancelability,
    ChatTurnPresentationPhase,
    present_assistant_activity,
)


@pytest.mark.parametrize(
    "route",
    tuple(
        route
        for route in workflow_ui_handoff_routes()
        if route.decision_owner is not None
    ),
)
def test_workflow_handoff_presentation_uses_descriptor_copy(
    route: WorkflowUiHandoffRouteDescriptor,
) -> None:
    presentation = present_assistant_activity(
        AssistantTurnActivity(
            AssistantTurnActivityPhase.WAITING_FOR_DECISION,
            command_name=route.command.value,
            request_id=f"{route.command.value}-request",
            decision_owner=route.decision_owner,
        )
    )

    assert presentation.phase is ChatTurnPresentationPhase.WAITING
    assert presentation.primary_status == "Waiting for your input"
    assert presentation.step == route.presentation_step
    assert presentation.cancelability is ChatTurnCancelability.NOT_CANCELLABLE
    assert presentation.cancelability_text == route.decision_copy


def test_confirmation_card_copy_remains_independent_of_handoff_routes() -> None:
    presentation = present_assistant_activity(
        AssistantTurnActivity(
            AssistantTurnActivityPhase.WAITING_FOR_DECISION,
            command_name="configure_training",
            request_id="training-confirmation",
            decision_owner=AssistantDecisionOwner.CONFIRMATION_CARD,
        )
    )

    assert presentation.primary_status == "Waiting for your confirmation"
    assert presentation.cancelability_text == (
        "Use the confirmation card to continue or cancel."
    )
