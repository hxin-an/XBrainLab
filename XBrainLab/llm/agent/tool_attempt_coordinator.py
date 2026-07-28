"""Deterministic policy boundary for model-proposed assistant tools.

The controller owns turn orchestration and UI signals.  This module owns the
policy decision for a proposal: prompt publication, user intent, path
provenance, schema verification, backend capability, confirmation, retry, and
loop limits.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, Protocol, TypeVar

from XBrainLab.backend.application.resource_preflight import (
    ResourceConfirmationChallenge,
    ResourcePreflightContractError,
    ResourcePreflightView,
)
from XBrainLab.llm.tools.application_surface import (
    READ_ONLY_TOOLS,
    TOOL_TO_COMMAND,
    CapabilityPolicyUnavailable,
    ToolAvailability,
    ToolAvailabilityContext,
    ToolCommandResult,
    get_application_context,
)
from XBrainLab.llm.tools.base import BaseTool
from XBrainLab.llm.tools.result_contract import (
    redact_public_text,
    safe_unexpected_failure,
)

from .assembler import PromptToolPublication
from .execution_policy import (
    ExecutionDecision,
    ExecutionSnapshot,
    HostExecutionPolicy,
)
from .intent import (
    command_for_intent,
    infer_user_intent,
    is_explicit_workflow_continuation,
    path_label_for_intent,
)
from .verifier import PathProvenanceVerifier, VerificationResult

logger = logging.getLogger(__name__)

_Command = TypeVar("_Command")

_RECEIPT_BOUND_RESOURCE_COMMANDS = frozenset(
    {
        "apply_interpretation",
        "load_data",
        "preview_interpretation",
        "reload_interpretation_recipe",
        "start_training",
    }
)

_FINGERPRINT_BOUND_RESOURCE_COMMANDS = frozenset(
    {
        "load_data",
        "preview_interpretation",
        "reload_interpretation_recipe",
        "start_training",
    }
)

_HOST_DETERMINISTIC_CONTINUATION_TOOLS = frozenset(
    {
        "preview_interpretation",
        "validate_interpretation",
    }
)


def _resource_receipt_contract_error(
    command_name: str,
    receipt: ResourceConfirmationChallenge,
) -> str | None:
    if receipt.command_name != command_name:
        return "Resource receipt command does not match the pending action."
    if command_name == "apply_interpretation" and not receipt.candidate_id:
        return "Interpretation resource receipt is missing its candidate."
    if command_name == "preview_interpretation" and not receipt.candidate_id:
        return "Preview resource receipt is missing its scan identity."
    if command_name == "reload_interpretation_recipe" and not receipt.candidate_id:
        return "Recipe reload resource receipt is missing its recipe identity."
    if command_name in _FINGERPRINT_BOUND_RESOURCE_COMMANDS and (
        not receipt.configuration_fingerprint or not receipt.preflight_fingerprint
    ):
        return "Resource receipt is missing its configuration or preflight fingerprint."
    return None


class ToolAttemptAction(str, Enum):
    """Controller action selected for one model proposal."""

    LOOP = "loop"
    PUBLICATION_BLOCKED = "publication_blocked"
    PROVENANCE_BLOCKED = "provenance_blocked"
    INTENT_BLOCKED = "intent_blocked"
    VERIFICATION_BLOCKED = "verification_blocked"
    CAPABILITY_BLOCKED = "capability_blocked"
    RESOURCE_CONFIRMATION_BLOCKED = "resource_confirmation_blocked"
    CONFIRMATION_REQUIRED = "confirmation_required"
    EXECUTE = "execute"


class ToolAttemptFeedback(str, Enum):
    """History feedback shape retained by the presentation boundary."""

    SYSTEM_REJECTION = "system_rejection"
    TOOL_OUTPUT = "tool_output"


# Compatibility export for controller/tests that used the pre-contract name.
ResourcePreflightReceipt = ResourceConfirmationChallenge


@dataclass(frozen=True)
class ToolAttemptRequest:
    """Complete immutable input for one model-proposed tool attempt."""

    command_name: str
    params: dict[str, Any]
    confidence: float
    publication: PromptToolPublication
    latest_user_text: str


@dataclass(frozen=True)
class ToolAttemptDecision:
    """Complete decision for one command proposal and publication context."""

    action: ToolAttemptAction
    command_name: str
    params: dict[str, Any]
    context: ToolAvailabilityContext | None = None
    result: ToolCommandResult | None = None
    message: str | None = None
    tool: BaseTool | None = None
    confirmation_kind: str | None = None
    resource_preflight_receipt: ResourceConfirmationChallenge | None = None
    feedback: ToolAttemptFeedback = ToolAttemptFeedback.SYSTEM_REJECTION


@dataclass(frozen=True)
class ToolProposalDecision(Generic[_Command]):
    """Host-policy result for a normalized batch of model proposals."""

    command: _Command | None
    reason: str
    discarded_count: int = 0


class ToolContextSource(Protocol):
    """Read one backend publication-backed context for a tool."""

    def get_context(self, tool_name: str) -> ToolAvailabilityContext | None: ...


@dataclass(frozen=True)
class ApplicationToolContextSource:
    """Production context source backed by the current Study runtime."""

    study: Any

    def get_context(self, tool_name: str) -> ToolAvailabilityContext | None:
        return get_application_context(self.study, tool_name)


class ToolRegistryView(Protocol):
    """Registry surface needed by tool-attempt policy."""

    def get_tool(self, name: str) -> BaseTool | None: ...


class ToolCallVerifier(Protocol):
    """Schema/semantic verifier surface needed by tool-attempt policy."""

    def verify_tool_call(
        self,
        tool_call: tuple[str, dict[str, Any]],
        *,
        confidence: float,
    ) -> VerificationResult: ...


class PathPolicyVerifier(Protocol):
    """Path-provenance verifier surface used by the policy boundary."""

    def validate(
        self,
        name: str,
        params: dict[str, Any],
        *,
        latest_user_text: str,
        state: dict[str, Any] | None,
    ) -> VerificationResult: ...


class ToolAttemptCoordinator:
    """Own all deterministic policy for one assistant tool attempt.

    The coordinator has no dependency on ``LLMController`` and emits no UI
    signals.  It consumes explicit turn inputs and returns typed decisions for
    the controller to present or execute.
    """

    def __init__(
        self,
        *,
        registry: ToolRegistryView,
        verifier: ToolCallVerifier,
        context_source: ToolContextSource,
        execution_policy: HostExecutionPolicy | None = None,
        path_verifier: PathPolicyVerifier | None = None,
        recent_call_limit: int = 10,
    ) -> None:
        self._registry = registry
        self._verifier = verifier
        self._context_source = context_source
        self._execution_policy = execution_policy or HostExecutionPolicy()
        self._path_verifier = path_verifier or PathProvenanceVerifier()
        self._recent_tool_calls: deque[tuple[str, str]] = deque(
            maxlen=recent_call_limit
        )

    def reset_turn(self) -> None:
        """Clear proposal history scoped to one user-authored turn."""
        self._recent_tool_calls.clear()

    def select_proposal(
        self,
        commands: list[_Command],
        *,
        mode: str,
        execution_count: int,
        workflow_tool_cap: int,
        cancelled: bool,
    ) -> ToolProposalDecision[_Command]:
        """Select at most one proposal and enforce the per-turn host cap."""
        command = self._execution_policy.first_command(commands)
        if command is None:
            return ToolProposalDecision(None, "no_command")
        start = self._execution_policy.before_command(
            mode=mode,
            execution_count=execution_count,
            workflow_tool_cap=workflow_tool_cap,
            cancelled=cancelled,
        )
        if not start.continue_workflow:
            return ToolProposalDecision(None, start.reason)
        return ToolProposalDecision(
            command,
            start.reason,
            discarded_count=max(len(commands) - 1, 0),
        )

    def evaluate(self, request: ToolAttemptRequest) -> ToolAttemptDecision:
        """Evaluate one proposal against one immutable prompt publication."""
        command_name = request.command_name
        params = request.params
        signature = (command_name, self._stable_params(params))
        self._recent_tool_calls.append(signature)
        if self._is_loop(signature):
            return ToolAttemptDecision(ToolAttemptAction.LOOP, command_name, params)

        publication_result = self._publication_result(
            command_name,
            request.publication,
        )
        if publication_result is not None:
            return ToolAttemptDecision(
                ToolAttemptAction.PUBLICATION_BLOCKED,
                command_name,
                params,
                result=publication_result,
            )

        context = self.context_for(command_name)
        prompt_generation = request.publication.backend_generation
        current_generation = context.generation
        if (
            type(prompt_generation) is int
            and type(current_generation) is int
            and prompt_generation != current_generation
        ):
            mapped_command = TOOL_TO_COMMAND.get(command_name)
            return ToolAttemptDecision(
                ToolAttemptAction.PUBLICATION_BLOCKED,
                command_name,
                params,
                context=context,
                result=ToolCommandResult.failure(
                    command_name,
                    (
                        "Workflow state changed while the assistant was preparing "
                        "this action. Review the current step and try again."
                    ),
                    command_name=(
                        mapped_command.value if mapped_command is not None else None
                    ),
                    state=context.state,
                    error_type="stale_publication",
                    recoverable=True,
                    diagnostics={
                        "prompt_generation": prompt_generation,
                        "current_generation": current_generation,
                    },
                ),
            )
        intent_result = self._intent_result(request, context)
        if intent_result is not None:
            return ToolAttemptDecision(
                ToolAttemptAction.INTENT_BLOCKED,
                command_name,
                params,
                context=context,
                result=intent_result,
            )

        provenance_result = self._provenance_result(request, context)
        if provenance_result is not None:
            return ToolAttemptDecision(
                ToolAttemptAction.PROVENANCE_BLOCKED,
                command_name,
                params,
                context=context,
                result=provenance_result,
            )

        validation = self._verifier.verify_tool_call(
            (command_name, params),
            confidence=request.confidence,
        )
        if not validation.is_valid:
            message = validation.error_message or "Tool call did not pass validation."
            return ToolAttemptDecision(
                ToolAttemptAction.VERIFICATION_BLOCKED,
                command_name,
                params,
                context=context,
                result=self._verification_result(
                    request,
                    context,
                    message,
                ),
                feedback=ToolAttemptFeedback.TOOL_OUTPUT,
            )

        if not context.availability.enabled:
            return ToolAttemptDecision(
                ToolAttemptAction.CAPABILITY_BLOCKED,
                command_name,
                params,
                context=context,
                result=self.blocked_result(command_name, context),
            )

        tool = self._registry.get_tool(command_name)
        if self._execution_policy.needs_confirmation(
            context.availability,
            tool_requires_confirmation=bool(tool and tool.requires_confirmation),
        ):
            return ToolAttemptDecision(
                ToolAttemptAction.CONFIRMATION_REQUIRED,
                command_name,
                params,
                context=context,
                tool=tool,
            )
        return ToolAttemptDecision(
            ToolAttemptAction.EXECUTE,
            command_name,
            params,
            context=context,
            tool=tool,
        )

    def context_for(self, command_name: str) -> ToolAvailabilityContext:
        """Read one context or return a fail-closed typed context."""
        try:
            context = self._context_source.get_context(command_name)
        except CapabilityPolicyUnavailable as exc:
            safe_detail = redact_public_text(exc)
            return self.unavailable_context(
                command_name,
                "Backend capability policy is unavailable; execution is blocked "
                f"until workflow state can be verified. ({safe_detail})",
            )
        except Exception as exc:
            failure = safe_unexpected_failure(
                logger,
                exc,
                boundary="tool_attempt_coordinator",
                operation=command_name,
            )
            return self.unavailable_context(
                command_name,
                failure.message,
            )
        if context is None:
            return self.unavailable_context(
                command_name,
                "Backend capability policy is unavailable; execution is blocked "
                "until workflow state can be verified.",
            )
        return context

    def evaluate_host_deterministic_continuation(
        self,
        command_name: str,
        params: dict[str, Any],
    ) -> ToolAttemptDecision:
        """Verify one host-selected, parameter-free continuation fail closed.

        The host may select only an allowlisted workflow transition, but the
        transition still has to satisfy the same registry schema, capability,
        and confirmation policy as a model proposal.
        """
        if command_name not in _HOST_DETERMINISTIC_CONTINUATION_TOOLS:
            message = f"Tool '{command_name}' is not an allowlisted host continuation."
            return ToolAttemptDecision(
                ToolAttemptAction.VERIFICATION_BLOCKED,
                command_name,
                params,
                result=ToolCommandResult.failure(
                    command_name,
                    message,
                    command_name=command_name,
                    error_type="contract",
                    recoverable=False,
                ),
            )
        if params:
            message = (
                f"Tool '{command_name}' is an allowlisted host continuation only "
                "when it is parameter-free."
            )
            return ToolAttemptDecision(
                ToolAttemptAction.VERIFICATION_BLOCKED,
                command_name,
                params,
                result=ToolCommandResult.failure(
                    command_name,
                    message,
                    command_name=command_name,
                    error_type="contract",
                    recoverable=False,
                ),
            )
        context = self.context_for(command_name)
        validation = self._verifier.verify_tool_call(
            (command_name, params),
            confidence=1.0,
        )
        if not validation.is_valid:
            message = validation.error_message or "Tool call did not pass validation."
            return ToolAttemptDecision(
                ToolAttemptAction.VERIFICATION_BLOCKED,
                command_name,
                params,
                context=context,
                result=ToolCommandResult.failure(
                    command_name,
                    message,
                    command_name=context.availability.command_name,
                    state=context.state,
                    error_type="contract",
                    recoverable=False,
                    capability=context.availability.to_dict(),
                    diagnostics={"publication_generation": context.generation},
                ),
            )
        if not context.availability.enabled:
            return ToolAttemptDecision(
                ToolAttemptAction.CAPABILITY_BLOCKED,
                command_name,
                params,
                context=context,
                result=self.blocked_result(command_name, context),
            )
        tool = self._registry.get_tool(command_name)
        if tool is None:
            return ToolAttemptDecision(
                ToolAttemptAction.VERIFICATION_BLOCKED,
                command_name,
                params,
                context=context,
                result=ToolCommandResult.failure(
                    command_name,
                    "The deterministic continuation tool is not registered.",
                    command_name=context.availability.command_name,
                    state=context.state,
                    error_type="contract",
                    recoverable=False,
                    capability=context.availability.to_dict(),
                    diagnostics={"publication_generation": context.generation},
                ),
            )
        if self._execution_policy.needs_confirmation(
            context.availability,
            tool_requires_confirmation=tool.requires_confirmation,
        ):
            return ToolAttemptDecision(
                ToolAttemptAction.CONFIRMATION_REQUIRED,
                command_name,
                params,
                context=context,
                tool=tool,
            )
        return ToolAttemptDecision(
            ToolAttemptAction.EXECUTE,
            command_name,
            params,
            context=context,
            tool=tool,
        )

    @staticmethod
    def unavailable_context(
        command_name: str,
        message: str,
    ) -> ToolAvailabilityContext:
        """Build a fail-closed context when no publication can be read."""
        mapped_command = TOOL_TO_COMMAND.get(command_name)
        return ToolAvailabilityContext(
            availability=ToolAvailability(
                tool_name=command_name,
                enabled=False,
                reasons=(message,),
                command_name=(
                    mapped_command.value if mapped_command is not None else None
                ),
                read_only=command_name in READ_ONLY_TOOLS,
                can_auto_execute=False,
            ),
            state=None,
            generation=None,
            policy_error=message,
        )

    @staticmethod
    def blocked_result(
        command_name: str,
        context: ToolAvailabilityContext,
    ) -> ToolCommandResult:
        """Convert a capability block or context failure to a typed result."""
        diagnostics = {"publication_generation": context.generation}
        if context.policy_error is None:
            return ToolCommandResult.blocked(
                command_name,
                context.availability,
                state=context.state,
                diagnostics=diagnostics,
            )
        return ToolCommandResult.failure(
            command_name,
            context.policy_error,
            command_name=context.availability.command_name,
            state=context.state,
            error_type="runtime",
            recoverable=True,
            capability=context.availability.to_dict(),
            diagnostics=diagnostics,
        )

    @staticmethod
    def confirmed_params(
        command_name: str,
        params: dict[str, Any],
        *,
        confirmation_kind: str | None = None,
        resource_preflight_receipt: ResourceConfirmationChallenge | None = None,
    ) -> dict[str, Any]:
        """Inject backend confirmation fields after explicit user approval."""
        confirmed = dict(params)
        if command_name in {
            "apply_interpretation",
            "clear_dataset",
            "start_training",
        }:
            confirmed["confirmed"] = True
        if confirmation_kind != "resource_preflight":
            return confirmed
        if resource_preflight_receipt is None:
            raise ValueError("Resource confirmation requires an authoritative receipt.")
        if command_name not in _RECEIPT_BOUND_RESOURCE_COMMANDS:
            raise ValueError(
                f"Tool '{command_name}' does not support receipt-bound resource "
                "confirmation."
            )
        contract_error = _resource_receipt_contract_error(
            command_name,
            resource_preflight_receipt,
        )
        if contract_error is not None:
            raise ValueError(contract_error)

        receipt_candidate = str(resource_preflight_receipt.candidate_id or "").strip()
        if command_name == "apply_interpretation":
            requested_candidate = str(confirmed.get("candidate_id") or "").strip()
            if requested_candidate and requested_candidate != receipt_candidate:
                raise ValueError(
                    "Resource receipt candidate does not match the pending action."
                )
            confirmed["candidate_id"] = receipt_candidate
        elif command_name == "preview_interpretation":
            requested_scan = str(confirmed.get("scan_id") or "").strip()
            if requested_scan and requested_scan != receipt_candidate:
                raise ValueError(
                    "Resource receipt scan does not match the pending action."
                )
            confirmed["scan_id"] = receipt_candidate
        confirmed["resource_preflight_confirmed"] = True
        confirmed["resource_preflight_token"] = resource_preflight_receipt.challenge_id
        return confirmed

    def approved_params(
        self,
        decision: ToolAttemptDecision,
    ) -> dict[str, Any]:
        """Inject approval while preserving the opaque backend receipt."""
        receipt = decision.resource_preflight_receipt
        if decision.confirmation_kind == "resource_preflight" and receipt is None:
            raise ValueError("Resource confirmation requires an authoritative receipt.")
        return self.confirmed_params(
            decision.command_name,
            decision.params,
            confirmation_kind=decision.confirmation_kind,
            resource_preflight_receipt=receipt,
        )

    @staticmethod
    def resource_confirmation(
        decision: ToolAttemptDecision,
        result: object,
    ) -> ToolAttemptDecision | None:
        """Convert a backend resource warning into a typed confirmation."""
        if not isinstance(result, ToolCommandResult) or decision.context is None:
            return None
        if result.error_type != "confirmation_required":
            return None
        if decision.command_name not in _RECEIPT_BOUND_RESOURCE_COMMANDS:
            return ToolAttemptCoordinator._resource_confirmation_blocked(
                decision,
                result,
                message=(
                    f"Tool '{decision.command_name}' does not support "
                    "receipt-bound resource confirmation."
                ),
                contract_reason="unsupported_command",
            )
        try:
            preflight = ResourcePreflightView.from_diagnostics(result.diagnostics)
        except ResourcePreflightContractError:
            return ToolAttemptCoordinator._resource_confirmation_blocked(
                decision,
                result,
                message=(
                    "Backend resource confirmation returned an invalid contract. "
                    "The action remains blocked."
                ),
                contract_reason="invalid_contract",
            )
        if preflight is None or not preflight.requires_confirmation:
            return None
        receipt = preflight.challenge
        contract_error = (
            _resource_receipt_contract_error(decision.command_name, receipt)
            if receipt is not None
            else "Backend resource confirmation did not provide a receipt."
        )
        if contract_error is not None:
            receipt = None
        if receipt is None:
            message = (
                "Backend resource confirmation did not provide a complete "
                "command-bound receipt. "
                f"{contract_error} The action remains blocked."
            )
            return ToolAttemptCoordinator._resource_confirmation_blocked(
                decision,
                result,
                message=message,
                contract_reason="missing_receipt",
            )
        return ToolAttemptDecision(
            action=ToolAttemptAction.CONFIRMATION_REQUIRED,
            command_name=decision.command_name,
            params=dict(decision.params),
            context=decision.context,
            result=result,
            message=result.message,
            tool=decision.tool,
            confirmation_kind="resource_preflight",
            resource_preflight_receipt=receipt,
            feedback=ToolAttemptFeedback.TOOL_OUTPUT,
        )

    @staticmethod
    def _resource_confirmation_blocked(
        decision: ToolAttemptDecision,
        result: ToolCommandResult,
        *,
        message: str,
        contract_reason: str,
    ) -> ToolAttemptDecision:
        return ToolAttemptDecision(
            action=ToolAttemptAction.RESOURCE_CONFIRMATION_BLOCKED,
            command_name=decision.command_name,
            params=dict(decision.params),
            context=decision.context,
            result=ToolCommandResult.failure(
                decision.command_name,
                message,
                command_name=result.command_name,
                state=result.state,
                capability=result.capability,
                error_type="contract",
                recoverable=False,
                diagnostics={
                    **dict(result.diagnostics),
                    "resource_confirmation_contract": contract_reason,
                },
            ),
            message=message,
            tool=decision.tool,
            feedback=ToolAttemptFeedback.TOOL_OUTPUT,
        )

    def after_failure(
        self,
        *,
        mode: str,
        availability: ToolAvailability | None,
        failure_count: int,
        global_retry_limit: int,
        execution_count: int,
        tool_cap: int,
        cancelled: bool,
    ) -> ExecutionDecision:
        """Return the deterministic retry/stop decision after failure."""
        return self._execution_policy.after_failure(
            mode=mode,
            availability=availability,
            failure_count=failure_count,
            global_retry_limit=global_retry_limit,
            execution_count=execution_count,
            tool_cap=tool_cap,
            cancelled=cancelled,
        )

    def after_success(
        self,
        *,
        mode: str,
        availability: ToolAvailability | None,
        snapshot: ExecutionSnapshot,
        execution_count: int,
        tool_cap: int,
        after_confirmation: bool,
        cancelled: bool,
    ) -> ExecutionDecision:
        """Return the deterministic continue/stop decision after success."""
        return self._execution_policy.after_success(
            mode=mode,
            availability=availability,
            snapshot=snapshot,
            execution_count=execution_count,
            tool_cap=tool_cap,
            after_confirmation=after_confirmation,
            cancelled=cancelled,
        )

    def _publication_result(
        self,
        tool_name: str,
        publication: PromptToolPublication,
    ) -> ToolCommandResult | None:
        if publication.permits(tool_name):
            return None
        mapped_command = TOOL_TO_COMMAND.get(tool_name)
        blocked_reason = publication.blocked_reason(tool_name)
        if blocked_reason is None and mapped_command is not None:
            blocked_reason = publication.blocked_reason(mapped_command.value)
        diagnostics = {
            "publication_generation": publication.backend_generation,
            "published_tool_count": len(publication.tool_names),
        }
        if blocked_reason:
            return ToolCommandResult(
                ok=False,
                tool_name=tool_name,
                command_name=(
                    mapped_command.value if mapped_command is not None else None
                ),
                message=(
                    "This assistant tool was not published because the workflow "
                    f"step is blocked: {blocked_reason}"
                ),
                error_type="precondition",
                recoverable=True,
                blocked_reason=blocked_reason,
                diagnostics=diagnostics,
            )
        return ToolCommandResult.failure(
            tool_name,
            "This assistant tool was not published for the current model turn.",
            command_name=(mapped_command.value if mapped_command is not None else None),
            error_type="tool_not_published",
            recoverable=True,
            diagnostics=diagnostics,
        )

    def _intent_result(
        self,
        request: ToolAttemptRequest,
        context: ToolAvailabilityContext,
    ) -> ToolCommandResult | None:
        latest_request = request.latest_user_text
        if not latest_request:
            return None
        tool_name = request.command_name
        requested_intent = infer_user_intent(latest_request)
        requested_command = command_for_intent(requested_intent)
        chosen_command = TOOL_TO_COMMAND.get(tool_name)
        authorized_command = request.publication.authorized_command
        if (
            authorized_command
            and chosen_command is not None
            and chosen_command.value == authorized_command
        ):
            return None
        if requested_command is None:
            if self._explicit_read_only_intent_matches(tool_name, latest_request):
                return None
            recommended = request.publication.recommended_command
            if (
                is_explicit_workflow_continuation(latest_request)
                and recommended
                and chosen_command is not None
                and chosen_command.value == recommended
            ):
                return None
            reason = (
                "The latest user request does not authorize this tool. Ask for "
                "the intended workflow step instead of choosing one."
            )
            return ToolCommandResult(
                ok=False,
                tool_name=tool_name,
                command_name=chosen_command.value if chosen_command else None,
                message=reason,
                error_type="intent_mismatch",
                recoverable=True,
                blocked_reason=reason,
                state=context.state,
                capability=context.availability.to_dict(),
            )

        if chosen_command == requested_command:
            return None

        capability = (
            context.capabilities.get(requested_command)
            if context.capabilities is not None
            else None
        )
        if requested_intent in {"visualize", "saliency"}:
            reason = (
                "; ".join(capability.reasons) if capability is not None else ""
            ) or (
                "Use an ApplicationService readiness summary before opening "
                "visualization views."
            )
            return ToolCommandResult(
                ok=False,
                tool_name=tool_name,
                command_name=requested_command.value,
                message=(
                    f"Requested workflow step '{requested_command.value}' needs a "
                    f"readiness summary: {reason}"
                ),
                error_type="precondition",
                recoverable=True,
                blocked_reason=reason,
                state=context.state,
                capability=capability.to_dict() if capability is not None else None,
            )

        if capability is not None and not capability.enabled:
            reason = "; ".join(capability.reasons) or (
                "The requested workflow step is not available yet."
            )
            return ToolCommandResult(
                ok=False,
                tool_name=tool_name,
                command_name=requested_command.value,
                message=(
                    f"Requested workflow step '{requested_command.value}' is not "
                    f"available: {reason}"
                ),
                error_type="precondition",
                recoverable=True,
                blocked_reason=reason,
                state=context.state,
                capability=capability.to_dict(),
            )

        reason = (
            f"The proposed tool '{tool_name}' does not match the latest requested "
            f"workflow step '{requested_command.value}'."
        )
        return ToolCommandResult(
            ok=False,
            tool_name=tool_name,
            command_name=requested_command.value,
            message=reason,
            error_type="intent_mismatch",
            recoverable=True,
            blocked_reason=reason,
            state=context.state,
            capability=capability.to_dict() if capability is not None else None,
        )

    def _provenance_result(
        self,
        request: ToolAttemptRequest,
        context: ToolAvailabilityContext,
    ) -> ToolCommandResult | None:
        verification = self._path_verifier.validate(
            request.command_name,
            request.params,
            latest_user_text=request.latest_user_text,
            state=context.state,
        )
        if verification.is_valid:
            return None
        message = verification.error_message or (
            "Choose a file or folder in the app, or paste the exact path."
        )
        mapped_command = TOOL_TO_COMMAND.get(request.command_name)
        return ToolCommandResult.failure(
            request.command_name,
            message,
            command_name=(mapped_command.value if mapped_command is not None else None),
            state=context.state,
            capability=context.availability.to_dict(),
            error_type="input",
            recoverable=True,
            diagnostics={
                "policy": "path_provenance",
                "publication_generation": context.generation,
            },
        )

    @staticmethod
    def _verification_result(
        request: ToolAttemptRequest,
        context: ToolAvailabilityContext,
        message: str,
    ) -> ToolCommandResult:
        mapped_command = TOOL_TO_COMMAND.get(request.command_name)
        return ToolCommandResult.failure(
            request.command_name,
            ToolAttemptCoordinator._verification_failure_message(
                request.command_name,
                request.latest_user_text,
                message,
            ),
            command_name=(mapped_command.value if mapped_command is not None else None),
            state=context.state,
            raw_result=message,
            error_type="input",
            recoverable=True,
            capability=context.availability.to_dict(),
            diagnostics={"publication_generation": context.generation},
        )

    @staticmethod
    def _verification_failure_message(
        command_name: str,
        latest_user_text: str,
        message: str,
    ) -> str:
        intent = infer_user_intent(latest_user_text)
        path_label = path_label_for_intent(intent)
        lower = message.lower()
        if path_label and "actual path" in lower:
            return f"Required {path_label} must be an actual path provided by the user."
        if path_label and (
            "missing required parameter" in lower or "required input" in lower
        ):
            return f"Required {path_label} is missing."
        if command_name == "list_files" and "directory" in lower:
            return "directory is required"
        if "missing required parameter" in lower:
            return message.replace("Missing required parameter(s)", "Required input")
        return message

    @staticmethod
    def _explicit_read_only_intent_matches(tool_name: str, request: str) -> bool:
        normalized = request.casefold()
        if tool_name == "list_files":
            return (
                "file" in normalized
                and any(marker in normalized for marker in ("list", "show"))
            ) or any(marker in normalized for marker in ("列出檔案", "顯示檔案"))
        if tool_name in {"get_dataset_info", "query_state"}:
            return any(
                marker in normalized
                for marker in ("dataset info", "dataset summary", "資料集資訊")
            )
        return False

    def _is_loop(self, signature: tuple[str, str]) -> bool:
        return sum(call == signature for call in self._recent_tool_calls) >= 3

    @staticmethod
    def _stable_params(params: dict[str, Any]) -> str:
        try:
            return json.dumps(params, sort_keys=True)
        except (TypeError, ValueError):
            return str(params)
