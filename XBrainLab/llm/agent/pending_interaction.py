"""Single owner for assistant confirmations and product-UI handoffs.

The coordinator is intentionally Qt-free. It owns pending interaction state,
request correlation, duplicate suppression, and typed resolution decisions.
The controller remains responsible for signals, verified command execution,
history, and product presentation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from .confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
)
from .interaction import AgentInteractionOutcome, AgentInteractionStatus
from .tool_attempt_coordinator import ToolAttemptDecision
from .turn import AssistantToolInputReceipt
from .ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
    WorkflowUiHandoffSession,
    WorkflowUiHandoffTransitionStatus,
)


class PendingConfirmationDecision(str, Enum):
    """Host action produced by resolving one confirmation callback."""

    APPROVE = "approve"
    CANCEL = "cancel"
    INVALID = "invalid"
    NO_PENDING = "no_pending"
    STALE = "stale"
    DUPLICATE = "duplicate"


class PendingWorkflowHandoffDecision(str, Enum):
    """Host action produced by resolving one product-UI callback."""

    PROGRESS = "progress"
    TERMINAL = "terminal"
    INVALID = "invalid"
    NO_PENDING = "no_pending"
    STALE = "stale"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class PendingConfirmation:
    """One policy decision paired with its exact visible confirmation request."""

    decision: ToolAttemptDecision
    request: AgentConfirmationRequest


@dataclass(frozen=True, slots=True)
class PendingInteractionSnapshot:
    """Pending values removed by an explicit clear/reset boundary."""

    confirmation: PendingConfirmation | None
    workflow_handoff: WorkflowUiHandoffRequest | None
    tool_input: AssistantToolInputReceipt | None
    active_tool_input: AssistantToolInputReceipt | None


@dataclass(frozen=True, slots=True)
class PendingConfirmationResolutionResult:
    """Exact host decision for one confirmation callback."""

    decision: PendingConfirmationDecision
    pending: PendingConfirmation | None = None
    resolution: AgentConfirmationResolution | None = None
    outcome: AgentInteractionOutcome | None = None


@dataclass(frozen=True, slots=True)
class PendingWorkflowHandoffResolutionResult:
    """Exact host decision for one product-UI handoff callback."""

    decision: PendingWorkflowHandoffDecision
    request: WorkflowUiHandoffRequest | None = None
    resolution: WorkflowUiHandoffResolution | None = None
    outcome: AgentInteractionOutcome | None = None

    @property
    def terminal(self) -> bool:
        return self.decision is PendingWorkflowHandoffDecision.TERMINAL


class PendingInteractionCoordinator:
    """Own and resolve one pending confirmation or UI handoff at a time."""

    def __init__(self) -> None:
        self._confirmation: PendingConfirmation | None = None
        self._workflow_handoff: WorkflowUiHandoffSession | None = None
        self._tool_input: AssistantToolInputReceipt | None = None
        self._active_tool_input: AssistantToolInputReceipt | None = None
        self._last_confirmation_request_id: str | None = None
        self._last_workflow_handoff_request_id: str | None = None

    @property
    def confirmation(self) -> PendingConfirmation | None:
        return self._confirmation

    @property
    def confirmation_decision(self) -> ToolAttemptDecision | None:
        pending = self._confirmation
        return pending.decision if pending is not None else None

    @property
    def confirmation_request(self) -> AgentConfirmationRequest | None:
        pending = self._confirmation
        return pending.request if pending is not None else None

    @property
    def workflow_handoff(self) -> WorkflowUiHandoffRequest | None:
        pending = self._workflow_handoff
        return pending.request if pending is not None else None

    @property
    def workflow_handoff_session(self) -> WorkflowUiHandoffSession | None:
        """Return the bounded phase owner for the current UI handoff."""
        return self._workflow_handoff

    @property
    def tool_input(self) -> AssistantToolInputReceipt | None:
        """Return the receipt waiting for the next admitted user turn."""
        return self._tool_input

    @property
    def active_tool_input(self) -> AssistantToolInputReceipt | None:
        """Return the bounded-reply receipt leased to the current user turn."""
        return self._active_tool_input

    @property
    def has_pending(self) -> bool:
        """Return whether a blocking confirmation or UI handoff is pending."""
        return self._confirmation is not None or self._workflow_handoff is not None

    def begin_tool_input(
        self,
        receipt: AssistantToolInputReceipt,
    ) -> AssistantToolInputReceipt:
        """Store one nonblocking receipt for the next admitted user turn."""
        if not isinstance(receipt, AssistantToolInputReceipt):
            raise TypeError("Pending tool input requires a typed receipt.")
        if self._confirmation is not None or self._workflow_handoff is not None:
            raise RuntimeError(
                "Cannot begin tool input while a blocking interaction is pending."
            )
        if self._active_tool_input is not None:
            raise RuntimeError("Assistant tool input is already active.")
        if self._tool_input is not None:
            raise RuntimeError("Assistant tool input is already pending.")
        self._tool_input = receipt
        return receipt

    def activate_tool_input(self) -> AssistantToolInputReceipt | None:
        """Lease a waiting receipt to exactly one admitted user turn."""
        if self._active_tool_input is not None:
            return None
        receipt = self._tool_input
        self._tool_input = None
        self._active_tool_input = receipt
        return receipt

    def clear_active_tool_input(self) -> AssistantToolInputReceipt | None:
        """End the current bounded clarification lease."""
        receipt = self._active_tool_input
        self._active_tool_input = None
        return receipt

    def requeue_active_tool_input_for_reply(self) -> AssistantToolInputReceipt | None:
        """Return one typed clarification lease for its bounded next reply."""
        receipt = self._active_tool_input
        if receipt is None or receipt.remaining_reply_budget <= 1:
            return None
        if self._tool_input is not None:
            raise RuntimeError("Assistant tool input is already pending.")
        requeued = replace(
            receipt,
            remaining_reply_budget=receipt.remaining_reply_budget - 1,
        )
        self._active_tool_input = None
        self._tool_input = requeued
        return requeued

    def replace_active_tool_input(
        self,
        receipt: AssistantToolInputReceipt,
    ) -> AssistantToolInputReceipt:
        """Persist verifier-approved user values on the current lease."""
        active = self._active_tool_input
        if active is None or not receipt.matches(
            active.command_name,
            active.publication_generation,
        ):
            raise RuntimeError("Assistant tool-input receipt is not active.")
        self._active_tool_input = receipt
        return receipt

    def begin_confirmation(
        self,
        decision: ToolAttemptDecision,
        request: AgentConfirmationRequest,
    ) -> PendingConfirmation:
        """Store one decision/request pair without allowing silent replacement."""
        pending = self._validated_confirmation(decision, request)
        if self._workflow_handoff is not None:
            raise RuntimeError(
                "Cannot begin confirmation while a workflow handoff is already pending."
            )
        if self._confirmation is not None:
            raise RuntimeError("An assistant confirmation is already pending.")
        self._confirmation = pending
        return pending

    def begin_workflow_handoff(
        self,
        request: WorkflowUiHandoffRequest,
    ) -> WorkflowUiHandoffRequest:
        """Store one typed UI handoff without allowing silent replacement."""
        if not isinstance(request, WorkflowUiHandoffRequest):
            raise TypeError("Pending workflow handoff requires a typed request.")
        if self._confirmation is not None:
            raise RuntimeError(
                "Cannot begin workflow handoff while a confirmation is already pending."
            )
        if self._workflow_handoff is not None:
            raise RuntimeError("A workflow handoff is already pending.")
        self._workflow_handoff = WorkflowUiHandoffSession(request)
        return request

    def resolve_confirmation(
        self,
        resolution: object,
    ) -> PendingConfirmationResolutionResult:
        """Resolve one callback into approve/cancel or an ignored condition."""
        if not isinstance(resolution, AgentConfirmationResolution):
            return PendingConfirmationResolutionResult(
                PendingConfirmationDecision.INVALID
            )
        pending = self._confirmation
        if pending is None:
            decision = (
                PendingConfirmationDecision.DUPLICATE
                if resolution.request_id == self._last_confirmation_request_id
                else PendingConfirmationDecision.NO_PENDING
            )
            return PendingConfirmationResolutionResult(
                decision,
                resolution=resolution,
            )
        if not resolution.matches(pending.request):
            return PendingConfirmationResolutionResult(
                PendingConfirmationDecision.STALE,
                resolution=resolution,
            )
        self._confirmation = None
        self._last_confirmation_request_id = pending.request.request_id
        decision = (
            PendingConfirmationDecision.APPROVE
            if resolution.approved
            else PendingConfirmationDecision.CANCEL
        )
        interaction_status = (
            AgentInteractionStatus.CONFIRMED
            if resolution.approved
            else AgentInteractionStatus.CANCELLED
        )
        return PendingConfirmationResolutionResult(
            decision=decision,
            pending=pending,
            resolution=resolution,
            outcome=AgentInteractionOutcome(
                status=interaction_status,
                command_name=pending.request.command_name,
                request_id=pending.request.request_id,
            ),
        )

    def resolve_workflow_handoff(
        self,
        resolution: object,
    ) -> PendingWorkflowHandoffResolutionResult:
        """Resolve progress/terminal UI callbacks without guessing identity."""
        pending = self._workflow_handoff
        if pending is None:
            if not isinstance(resolution, WorkflowUiHandoffResolution):
                return PendingWorkflowHandoffResolutionResult(
                    PendingWorkflowHandoffDecision.INVALID
                )
            decision = (
                PendingWorkflowHandoffDecision.DUPLICATE
                if resolution.request_id == self._last_workflow_handoff_request_id
                else PendingWorkflowHandoffDecision.NO_PENDING
            )
            return PendingWorkflowHandoffResolutionResult(
                decision,
                resolution=resolution,
            )
        if not isinstance(resolution, WorkflowUiHandoffResolution):
            resolution = WorkflowUiHandoffResolution.for_request(
                pending.request,
                status=WorkflowUiHandoffResolutionStatus.FAILED,
                message=("The settings command returned an invalid completion result."),
            )
        transition = pending.resolve(resolution)
        if transition is WorkflowUiHandoffTransitionStatus.STALE:
            return PendingWorkflowHandoffResolutionResult(
                PendingWorkflowHandoffDecision.STALE,
                resolution=resolution,
            )
        if transition is WorkflowUiHandoffTransitionStatus.INVALID:
            return PendingWorkflowHandoffResolutionResult(
                PendingWorkflowHandoffDecision.INVALID,
                resolution=resolution,
            )
        if transition is WorkflowUiHandoffTransitionStatus.DUPLICATE:
            return PendingWorkflowHandoffResolutionResult(
                PendingWorkflowHandoffDecision.DUPLICATE,
                resolution=resolution,
            )
        if transition is WorkflowUiHandoffTransitionStatus.ADVANCED:
            return self._workflow_handoff_result(
                PendingWorkflowHandoffDecision.PROGRESS,
                pending.request,
                resolution,
            )
        self._workflow_handoff = None
        self._last_workflow_handoff_request_id = pending.request.request_id
        return self._workflow_handoff_result(
            PendingWorkflowHandoffDecision.TERMINAL,
            pending.request,
            resolution,
        )

    def clear_confirmation(self) -> PendingConfirmation | None:
        """Remove an unresolved confirmation without marking it consumed."""
        pending = self._confirmation
        self._confirmation = None
        return pending

    def clear_workflow_handoff(self) -> WorkflowUiHandoffRequest | None:
        """Remove an unresolved UI handoff without marking it consumed."""
        pending = self._workflow_handoff
        self._workflow_handoff = None
        return pending.request if pending is not None else None

    def clear(self) -> PendingInteractionSnapshot:
        """Remove all pending interactions while retaining duplicate memory."""
        snapshot = PendingInteractionSnapshot(
            confirmation=self._confirmation,
            workflow_handoff=self.workflow_handoff,
            tool_input=self._tool_input,
            active_tool_input=self._active_tool_input,
        )
        self._confirmation = None
        self._workflow_handoff = None
        self._tool_input = None
        self._active_tool_input = None
        return snapshot

    def reset(self) -> PendingInteractionSnapshot:
        """Clear pending state and correlation history for a new conversation."""
        snapshot = self.clear()
        self._last_confirmation_request_id = None
        self._last_workflow_handoff_request_id = None
        return snapshot

    @staticmethod
    def _validated_confirmation(
        decision: ToolAttemptDecision,
        request: AgentConfirmationRequest,
    ) -> PendingConfirmation:
        if not isinstance(decision, ToolAttemptDecision):
            raise TypeError("Pending confirmation requires a tool attempt decision.")
        if not isinstance(request, AgentConfirmationRequest):
            raise TypeError("Pending confirmation requires a typed request.")
        if decision.command_name != request.command_name:
            raise ValueError(
                "Pending confirmation decision and request must use the same command."
            )
        expected_fingerprint = AgentConfirmationRequest.for_action(
            command_name=request.command_name,
            params=decision.params,
            action_label=request.action_label,
            description=request.description,
            destructive=request.destructive,
            publication_generation=request.publication_generation,
            confirmation_kind=request.confirmation_kind,
        ).params_fingerprint
        if expected_fingerprint != request.params_fingerprint:
            raise ValueError(
                "Pending confirmation decision and request must use the same "
                "parameters."
            )
        return PendingConfirmation(decision=decision, request=request)

    @staticmethod
    def _workflow_handoff_result(
        decision: PendingWorkflowHandoffDecision,
        request: WorkflowUiHandoffRequest,
        resolution: WorkflowUiHandoffResolution,
    ) -> PendingWorkflowHandoffResolutionResult:
        interaction_status = {
            WorkflowUiHandoffResolutionStatus.COMMAND_PENDING: (
                AgentInteractionStatus.DEFERRED_TO_UI
            ),
            WorkflowUiHandoffResolutionStatus.NAVIGATED: (
                AgentInteractionStatus.DEFERRED_TO_UI
            ),
            WorkflowUiHandoffResolutionStatus.DEFERRED_TO_UI: (
                AgentInteractionStatus.DEFERRED_TO_UI
            ),
            WorkflowUiHandoffResolutionStatus.COMPLETED: (
                AgentInteractionStatus.COMPLETED_IN_UI
            ),
            WorkflowUiHandoffResolutionStatus.CANCELLED: (
                AgentInteractionStatus.CANCELLED
            ),
            WorkflowUiHandoffResolutionStatus.BLOCKED: AgentInteractionStatus.BLOCKED,
            WorkflowUiHandoffResolutionStatus.UNAVAILABLE: (
                AgentInteractionStatus.UNAVAILABLE
            ),
            WorkflowUiHandoffResolutionStatus.FAILED: AgentInteractionStatus.FAILED,
        }[resolution.status]
        return PendingWorkflowHandoffResolutionResult(
            decision=decision,
            request=request,
            resolution=resolution,
            outcome=AgentInteractionOutcome(
                status=interaction_status,
                command_name=request.tool_name,
                request_id=request.request_id,
                decision_fields=request.decision_fields,
                message=resolution.message,
            ),
        )
