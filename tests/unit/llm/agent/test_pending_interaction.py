"""Pure contract tests for pending assistant interactions."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
)
from XBrainLab.llm.agent.pending_interaction import (
    PendingConfirmationDecision,
    PendingInteractionCoordinator,
    PendingWorkflowHandoffDecision,
)
from XBrainLab.llm.agent.tool_attempt_coordinator import (
    ToolAttemptAction,
    ToolAttemptDecision,
)
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
)


def _confirmation_pair(
    command_name: str = "clear_dataset",
) -> tuple[ToolAttemptDecision, AgentConfirmationRequest]:
    decision = ToolAttemptDecision(
        action=ToolAttemptAction.CONFIRMATION_REQUIRED,
        command_name=command_name,
        params={"reason": "test"},
    )
    request = AgentConfirmationRequest.for_action(
        command_name=command_name,
        params=decision.params,
        action_label="Clear dataset",
        description="Clear the current dataset",
        destructive=True,
        publication_generation=7,
    )
    return decision, request


def test_confirmation_is_created_and_exposed_as_one_pair() -> None:
    session = PendingInteractionCoordinator()
    decision, request = _confirmation_pair()

    session.begin_confirmation(decision, request)

    assert session.confirmation is not None
    assert session.confirmation.decision is decision
    assert session.confirmation.request is request
    assert session.confirmation_decision is decision
    assert session.confirmation_request is request
    assert session.workflow_handoff is None


def test_confirmation_pair_rejects_mismatched_command() -> None:
    session = PendingInteractionCoordinator()
    decision, _request = _confirmation_pair("clear_dataset")
    _other_decision, other_request = _confirmation_pair("start_training")

    with pytest.raises(ValueError, match="same command"):
        session.begin_confirmation(decision, other_request)

    assert session.confirmation is None


def test_confirmation_pair_rejects_mismatched_parameters() -> None:
    session = PendingInteractionCoordinator()
    decision, request = _confirmation_pair()
    mismatched_request = AgentConfirmationRequest.for_action(
        command_name=request.command_name,
        params={"reason": "different"},
        action_label=request.action_label,
        description=request.description,
        destructive=request.destructive,
        publication_generation=request.publication_generation,
    )

    with pytest.raises(ValueError, match="same parameters"):
        session.begin_confirmation(decision, mismatched_request)

    assert session.confirmation is None


def test_only_one_pending_interaction_kind_can_own_the_session() -> None:
    session = PendingInteractionCoordinator()
    decision, request = _confirmation_pair()
    handoff = WorkflowUiHandoffRequest.for_decision("create_epoch")
    session.begin_confirmation(decision, request)

    with pytest.raises(RuntimeError, match="confirmation is already pending"):
        session.begin_workflow_handoff(handoff)

    session.clear()
    session.begin_workflow_handoff(handoff)

    with pytest.raises(RuntimeError, match="workflow handoff is already pending"):
        session.begin_confirmation(decision, request)


def test_matching_confirmation_is_consumed_exactly_once() -> None:
    session = PendingInteractionCoordinator()
    decision, request = _confirmation_pair()
    resolution = AgentConfirmationResolution.for_request(
        request,
        status=AgentConfirmationResolutionStatus.APPROVED,
    )
    session.begin_confirmation(decision, request)

    consumed = session.resolve_confirmation(resolution)
    duplicate = session.resolve_confirmation(resolution)

    assert consumed.decision is PendingConfirmationDecision.APPROVE
    assert consumed.pending is not None
    assert consumed.pending.decision is decision
    assert consumed.pending.request is request
    assert consumed.outcome is not None
    assert consumed.outcome.status.value == "confirmed"
    assert duplicate.decision is PendingConfirmationDecision.DUPLICATE
    assert duplicate.pending is None
    assert duplicate.outcome is None
    assert session.confirmation is None


def test_cancelled_confirmation_uses_the_same_correlated_consume_boundary() -> None:
    session = PendingInteractionCoordinator()
    decision, request = _confirmation_pair()
    session.begin_confirmation(decision, request)

    consumed = session.resolve_confirmation(
        AgentConfirmationResolution.for_request(
            request,
            status=AgentConfirmationResolutionStatus.CANCELLED,
        )
    )

    assert consumed.decision is PendingConfirmationDecision.CANCEL
    assert consumed.pending is not None
    assert consumed.pending.decision is decision
    assert consumed.outcome is not None
    assert consumed.outcome.status.value == "cancelled"
    assert session.confirmation is None


def test_stale_confirmation_does_not_consume_current_pair() -> None:
    session = PendingInteractionCoordinator()
    decision, request = _confirmation_pair()
    _stale_decision, stale_request = _confirmation_pair()
    session.begin_confirmation(decision, request)

    result = session.resolve_confirmation(
        AgentConfirmationResolution.for_request(
            stale_request,
            status=AgentConfirmationResolutionStatus.APPROVED,
        )
    )

    assert result.decision is PendingConfirmationDecision.STALE
    assert result.pending is None
    assert session.confirmation is not None
    assert session.confirmation.request is request


def test_untyped_confirmation_is_invalid_and_does_not_consume_current_pair() -> None:
    session = PendingInteractionCoordinator()
    decision, request = _confirmation_pair()
    session.begin_confirmation(decision, request)

    result = session.resolve_confirmation(True)

    assert result.decision is PendingConfirmationDecision.INVALID
    assert result.pending is None
    assert session.confirmation is not None
    assert session.confirmation.request is request


def test_matching_workflow_handoff_is_consumed_exactly_once() -> None:
    session = PendingInteractionCoordinator()
    request = WorkflowUiHandoffRequest.for_decision(
        "create_epoch",
        decision_fields=("epoch_window",),
    )
    resolution = WorkflowUiHandoffResolution.for_request(
        request,
        status=WorkflowUiHandoffResolutionStatus.COMPLETED,
    )
    session.begin_workflow_handoff(request)

    consumed = session.resolve_workflow_handoff(resolution)
    duplicate = session.resolve_workflow_handoff(resolution)

    assert consumed.decision is PendingWorkflowHandoffDecision.TERMINAL
    assert consumed.request is request
    assert consumed.outcome is not None
    assert consumed.outcome.status.value == "completed_in_ui"
    assert duplicate.decision is PendingWorkflowHandoffDecision.DUPLICATE
    assert duplicate.request is None
    assert duplicate.outcome is None
    assert session.workflow_handoff is None


def test_nonterminal_workflow_handoff_update_does_not_consume_request() -> None:
    session = PendingInteractionCoordinator()
    request = WorkflowUiHandoffRequest.for_decision("create_epoch")
    session.begin_workflow_handoff(request)

    pending = session.resolve_workflow_handoff(
        WorkflowUiHandoffResolution.for_request(
            request,
            status=WorkflowUiHandoffResolutionStatus.COMMAND_PENDING,
        )
    )

    assert pending.decision is PendingWorkflowHandoffDecision.PROGRESS
    assert pending.request is request
    assert pending.outcome is not None
    assert pending.outcome.status.value == "deferred_to_ui"
    assert session.workflow_handoff is request
    assert session.workflow_handoff_session is not None
    assert (
        session.workflow_handoff_session.status.value
        == WorkflowUiHandoffResolutionStatus.COMMAND_PENDING.value
    )


def test_navigation_deferred_to_ui_consumes_pending_request() -> None:
    session = PendingInteractionCoordinator()
    request = WorkflowUiHandoffRequest.for_decision("evaluate")
    session.begin_workflow_handoff(request)

    resolved = session.resolve_workflow_handoff(
        WorkflowUiHandoffResolution.for_request(
            request,
            status=WorkflowUiHandoffResolutionStatus.DEFERRED_TO_UI,
        )
    )

    assert resolved.decision is PendingWorkflowHandoffDecision.TERMINAL
    assert resolved.request is request
    assert resolved.outcome is not None
    assert resolved.outcome.status.value == "deferred_to_ui"
    assert session.workflow_handoff is None


def test_terminal_workflow_handoff_callback_consumes_after_pending_update() -> None:
    session = PendingInteractionCoordinator()
    request = WorkflowUiHandoffRequest.for_decision("create_epoch")
    session.begin_workflow_handoff(request)
    session.resolve_workflow_handoff(
        WorkflowUiHandoffResolution.for_request(
            request,
            status=WorkflowUiHandoffResolutionStatus.COMMAND_PENDING,
        )
    )

    terminal = session.resolve_workflow_handoff(
        WorkflowUiHandoffResolution.for_request(
            request,
            status=WorkflowUiHandoffResolutionStatus.COMPLETED,
        )
    )

    assert terminal.decision is PendingWorkflowHandoffDecision.TERMINAL
    assert terminal.request is request
    assert terminal.outcome is not None
    assert terminal.outcome.status.value == "completed_in_ui"
    assert session.workflow_handoff is None


def test_stale_workflow_resolution_does_not_consume_current_request() -> None:
    session = PendingInteractionCoordinator()
    current = WorkflowUiHandoffRequest.for_decision("create_epoch")
    stale = WorkflowUiHandoffRequest.for_decision("generate_dataset")
    session.begin_workflow_handoff(current)

    result = session.resolve_workflow_handoff(
        WorkflowUiHandoffResolution.for_request(
            stale,
            status=WorkflowUiHandoffResolutionStatus.CANCELLED,
        )
    )

    assert result.decision is PendingWorkflowHandoffDecision.STALE
    assert session.workflow_handoff is current


def test_clear_removes_pending_state_and_reset_forgets_duplicate_history() -> None:
    session = PendingInteractionCoordinator()
    request = WorkflowUiHandoffRequest.for_decision("create_epoch")
    resolution = WorkflowUiHandoffResolution.for_request(
        request,
        status=WorkflowUiHandoffResolutionStatus.CANCELLED,
    )
    session.begin_workflow_handoff(request)
    session.resolve_workflow_handoff(resolution)
    assert (
        session.resolve_workflow_handoff(resolution).decision
        is PendingWorkflowHandoffDecision.DUPLICATE
    )

    decision, confirmation_request = _confirmation_pair()
    session.begin_confirmation(decision, confirmation_request)
    cleared = session.clear()

    assert cleared.confirmation is not None
    assert cleared.workflow_handoff is None
    assert session.has_pending is False

    session.reset()
    assert (
        session.resolve_workflow_handoff(resolution).decision
        is PendingWorkflowHandoffDecision.NO_PENDING
    )


def test_untyped_handoff_fails_and_consumes_the_current_request() -> None:
    session = PendingInteractionCoordinator()
    request = WorkflowUiHandoffRequest.for_decision("create_epoch")
    session.begin_workflow_handoff(request)

    result = session.resolve_workflow_handoff({"status": "completed"})

    assert result.decision is PendingWorkflowHandoffDecision.TERMINAL
    assert result.request is request
    assert result.outcome is not None
    assert result.outcome.status.value == "failed"
    assert result.resolution is not None
    assert result.resolution.message == (
        "The settings command returned an invalid completion result."
    )
    assert session.workflow_handoff is None


@pytest.mark.parametrize(
    ("resolution_status", "outcome_status"),
    [
        (WorkflowUiHandoffResolutionStatus.CANCELLED, "cancelled"),
        (WorkflowUiHandoffResolutionStatus.BLOCKED, "blocked"),
        (WorkflowUiHandoffResolutionStatus.UNAVAILABLE, "unavailable"),
        (WorkflowUiHandoffResolutionStatus.FAILED, "failed"),
    ],
)
def test_handoff_terminal_status_maps_to_one_interaction_outcome(
    resolution_status: WorkflowUiHandoffResolutionStatus,
    outcome_status: str,
) -> None:
    session = PendingInteractionCoordinator()
    request = WorkflowUiHandoffRequest.for_decision(
        "create_epoch",
        decision_fields=("epoch_window",),
    )
    session.begin_workflow_handoff(request)

    result = session.resolve_workflow_handoff(
        WorkflowUiHandoffResolution.for_request(
            request,
            status=resolution_status,
            message="Specific product surface outcome.",
        )
    )

    assert result.decision is PendingWorkflowHandoffDecision.TERMINAL
    assert result.outcome is not None
    assert result.outcome.status.value == outcome_status
    assert result.outcome.command_name == "create_epoch"
    assert result.outcome.request_id == request.request_id
    assert result.outcome.decision_fields == ("epoch_window",)
    assert result.outcome.message == "Specific product surface outcome."


def test_controller_delegates_resolution_decisions_to_coordinator() -> None:
    """Controller should wire outcomes, not reimplement correlation policy."""
    repo_root = Path(__file__).resolve().parents[4]
    source = (repo_root / "XBrainLab/llm/agent/controller.py").read_text(
        encoding="utf-8"
    )

    assert "PendingInteractionConsumeStatus" not in source
    assert ".consume_confirmation(" not in source


def test_controller_product_code_does_not_read_or_write_legacy_pending_fields() -> None:
    """Controller orchestration must use only the typed pending-state owner."""
    repo_root = Path(__file__).resolve().parents[4]
    source = (repo_root / "XBrainLab/llm/agent/controller.py").read_text(
        encoding="utf-8"
    )
    legacy_fields = {
        "_pending_confirmation",
        "_pending_confirmation_request",
        "_pending_workflow_handoff",
    }

    referenced = {
        node.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute) and node.attr in legacy_fields
    }

    assert referenced == set()
