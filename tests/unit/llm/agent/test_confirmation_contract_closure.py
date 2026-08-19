"""Regression contracts for target lifecycle confirmation correlation."""

from __future__ import annotations

from typing import Any

import pytest

from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
)
from XBrainLab.llm.agent.pending_interaction import (
    PendingConfirmationDecision,
    PendingInteractionCoordinator,
)
from XBrainLab.llm.agent.tool_attempt_coordinator import (
    ToolAttemptAction,
    ToolAttemptDecision,
)

_TARGET_CONFIRMATIONS = (
    ("reset_preprocessing", {}),
    ("clear_training_history", {}),
    ("start_training", {}),
)


@pytest.mark.parametrize(("tool_name", "params"), _TARGET_CONFIRMATIONS)
@pytest.mark.parametrize(
    ("resolution_case", "expected", "consumed"),
    [
        ("approve", PendingConfirmationDecision.APPROVE, True),
        ("cancel", PendingConfirmationDecision.CANCEL, True),
        ("stale", PendingConfirmationDecision.STALE, False),
        ("mismatched_fingerprint", PendingConfirmationDecision.STALE, False),
    ],
)
def test_confirmation_resolution_is_correlated_for_target_lifecycle_action(
    tool_name: str,
    params: dict[str, Any],
    resolution_case: str,
    expected: PendingConfirmationDecision,
    consumed: bool,
) -> None:
    decision = ToolAttemptDecision(
        action=ToolAttemptAction.CONFIRMATION_REQUIRED,
        command_name=tool_name,
        params=params,
    )
    request = AgentConfirmationRequest.for_action(
        command_name=tool_name,
        params=params,
        action_label="Apply change",
        description="Apply the reviewed change.",
        destructive=tool_name in {"reset_preprocessing", "clear_training_history"},
        publication_generation=41,
        request_id=f"{tool_name}-request",
    )
    session = PendingInteractionCoordinator()
    session.begin_confirmation(decision, request)

    status = (
        AgentConfirmationResolutionStatus.CANCELLED
        if resolution_case == "cancel"
        else AgentConfirmationResolutionStatus.APPROVED
    )
    if resolution_case == "stale":
        resolution = AgentConfirmationResolution(
            request_id=f"{tool_name}-stale",
            command_name=tool_name,
            params_fingerprint=request.params_fingerprint,
            publication_generation=41,
            status=status,
        )
    elif resolution_case == "mismatched_fingerprint":
        resolution = AgentConfirmationResolution(
            request_id=request.request_id,
            command_name=tool_name,
            params_fingerprint="0" * 64,
            publication_generation=41,
            status=status,
        )
    else:
        resolution = AgentConfirmationResolution.for_request(request, status=status)

    result = session.resolve_confirmation(resolution)

    assert result.decision is expected
    assert (session.confirmation is None) is consumed
