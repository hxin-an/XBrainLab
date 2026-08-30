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
from XBrainLab.llm.agent.turn import AssistantToolInputReceipt
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
)


def _confirmation_pair(
    command_name: str = "destructive_probe",
) -> tuple[ToolAttemptDecision, AgentConfirmationRequest]:
    decision = ToolAttemptDecision(
        action=ToolAttemptAction.CONFIRMATION_REQUIRED,
        command_name=command_name,
        params={"reason": "test"},
    )
    request = AgentConfirmationRequest.for_action(
        command_name=command_name,
        params=decision.params,
        action_label="Run destructive probe",
        description="Exercise destructive confirmation ownership",
        destructive=True,
        publication_generation=7,
    )
    return decision, request


def _tool_input_receipt() -> AssistantToolInputReceipt:
    return AssistantToolInputReceipt(
        command_name="resample_data",
        original_user_text="Resample the EEG data.",
        question="What resampling rate should I use?",
        publication_generation=7,
        missing_inputs=("rate",),
    )


def test_tool_input_receipt_requires_typed_missing_fields() -> None:
    with pytest.raises(ValueError, match="one or two"):
        AssistantToolInputReceipt(
            command_name="resample_data",
            original_user_text="Resample the EEG data.",
            question="What resampling rate should I use?",
            publication_generation=7,
            missing_inputs=(),
        )


def test_bandpass_receipt_can_hold_one_finite_unassigned_cutoff_only() -> None:
    receipt = AssistantToolInputReceipt(
        command_name="apply_bandpass_filter",
        original_user_text="Apply a bandpass filter.",
        question="What low and high cutoff frequencies should I use?",
        publication_generation=7,
        missing_inputs=("low_freq", "high_freq"),
        unassigned_bandpass_cutoff=12.5,
    )

    assert receipt.unassigned_bandpass_cutoff == 12.5

    with pytest.raises(ValueError, match="unassigned bandpass cutoff"):
        AssistantToolInputReceipt(
            command_name="resample_data",
            original_user_text="Resample the EEG data.",
            question="What resampling rate should I use?",
            publication_generation=7,
            missing_inputs=("rate",),
            unassigned_bandpass_cutoff=12.5,
        )
    with pytest.raises(ValueError, match="finite positive"):
        AssistantToolInputReceipt(
            command_name="apply_bandpass_filter",
            original_user_text="Apply a bandpass filter.",
            question="What low and high cutoff frequencies should I use?",
            publication_generation=7,
            missing_inputs=("low_freq", "high_freq"),
            unassigned_bandpass_cutoff=float("nan"),
        )


def test_tool_input_receipt_is_nonblocking_and_activates_once() -> None:
    session = PendingInteractionCoordinator()
    receipt = _tool_input_receipt()

    session.begin_tool_input(receipt)

    assert session.tool_input is receipt
    assert session.active_tool_input is None
    assert session.has_pending is False

    assert session.activate_tool_input() is receipt
    assert session.tool_input is None
    assert session.active_tool_input is receipt
    assert session.activate_tool_input() is None

    assert session.clear_active_tool_input() is receipt
    assert session.active_tool_input is None


def test_active_typed_receipt_requeues_once_for_a_second_parameter_reply() -> None:
    session = PendingInteractionCoordinator()
    receipt = AssistantToolInputReceipt(
        command_name="apply_bandpass_filter",
        original_user_text="Apply a bandpass filter.",
        question="What low cutoff should I use?",
        publication_generation=7,
        missing_inputs=("low_freq", "high_freq"),
        remaining_reply_budget=2,
    )
    session.begin_tool_input(receipt)
    session.activate_tool_input()

    requeued = session.requeue_active_tool_input_for_reply()

    assert requeued is not None
    assert requeued.remaining_reply_budget == 1
    assert session.active_tool_input is None
    assert session.tool_input is requeued


def test_typed_receipt_cannot_requeue_a_third_parameter_reply() -> None:
    session = PendingInteractionCoordinator()
    receipt = AssistantToolInputReceipt(
        command_name="apply_bandpass_filter",
        original_user_text="Apply a bandpass filter.",
        question="What low cutoff should I use?",
        publication_generation=7,
        missing_inputs=("low_freq", "high_freq"),
        remaining_reply_budget=1,
    )
    session.begin_tool_input(receipt)
    session.activate_tool_input()

    assert session.requeue_active_tool_input_for_reply() is None
    assert session.active_tool_input is receipt
    assert session.tool_input is None


def test_active_tool_input_cannot_rearm_another_receipt() -> None:
    session = PendingInteractionCoordinator()
    active = _tool_input_receipt()
    waiting = AssistantToolInputReceipt(
        command_name="apply_notch_filter",
        original_user_text="Apply a notch filter.",
        question="What notch frequency should I use?",
        publication_generation=7,
        missing_inputs=("freq",),
    )
    session.begin_tool_input(active)
    session.activate_tool_input()

    with pytest.raises(RuntimeError, match="already active"):
        session.begin_tool_input(waiting)


def test_clear_removes_waiting_or_active_tool_input_receipt() -> None:
    waiting_session = PendingInteractionCoordinator()
    waiting = _tool_input_receipt()
    waiting_session.begin_tool_input(waiting)

    waiting_cleared = waiting_session.clear()

    assert waiting_cleared.tool_input is waiting
    assert waiting_session.tool_input is None

    active_session = PendingInteractionCoordinator()
    active = _tool_input_receipt()
    active_session.begin_tool_input(active)
    active_session.activate_tool_input()

    active_cleared = active_session.clear()

    assert active_cleared.active_tool_input is active
    assert active_session.active_tool_input is None


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
    decision, _request = _confirmation_pair("destructive_probe")
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
        tool_name="create_epochs",
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
    assert consumed.outcome.command_name == "create_epochs"
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
    stale = WorkflowUiHandoffRequest.for_decision("configure_dataset_split")
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
