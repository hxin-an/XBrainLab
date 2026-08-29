"""Deterministic policy boundary for model-proposed assistant tools.

The controller owns turn orchestration and UI signals.  This module owns the
policy decision for a proposal: prompt publication, path provenance, schema
verification, backend capability, confirmation, retry, and loop limits.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, Protocol, TypeVar

from XBrainLab.backend.application.resource_preflight import (
    ResourceConfirmationChallenge,
    ResourcePreflightContractError,
    ResourcePreflightView,
)
from XBrainLab.backend.application.training_recommendation import (
    TrainingRecommendationField,
)
from XBrainLab.llm.tools.application_surface import (
    READ_ONLY_TOOLS,
    SETTING_CHANGE_CONFIRMATION_KIND,
    TOOL_TO_COMMAND,
    CapabilityPolicyUnavailable,
    ToolAvailability,
    ToolAvailabilityContext,
    ToolCommandResult,
    assistant_edited_recommendation_fields,
    assistant_setting_change_requires_confirmation,
    authorize_assistant_setting_change,
    get_application_context,
    setting_confirmation_params,
)
from XBrainLab.llm.tools.base import BaseTool
from XBrainLab.llm.tools.result_contract import (
    redact_public_text,
    safe_unexpected_failure,
)

from .assembler import PromptToolPublication
from .execution_policy import HostExecutionPolicy
from .turn import AssistantToolInputReceipt
from .verifier import (
    DIRECT_PARAMETER_TOOLS,
    PathProvenanceVerifier,
    VerificationResult,
    direct_parameter_action_request_matches,
    import_eeg_data_positive_origin_matches,
    verified_direct_parameter_origin_values,
    verify_direct_parameter_origins,
)

logger = logging.getLogger(__name__)

_Command = TypeVar("_Command")

_RECEIPT_BOUND_RESOURCE_COMMANDS = frozenset(
    {
        "apply_interpretation",
        "load_data",
        "preview_interpretation",
        "reload_interpretation_recipe",
        "saliency",
        "start_training",
    }
)

_FINGERPRINT_BOUND_RESOURCE_COMMANDS = frozenset(
    {
        "load_data",
        "preview_interpretation",
        "reload_interpretation_recipe",
        "saliency",
        "start_training",
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
    RESPOND = "respond"
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
    repeated: bool = False
    enforce_direct_parameter_origins: bool = True
    tool_input_receipt: AssistantToolInputReceipt | None = None
    supplied_parameters: dict[str, Any] | None = None
    single_proposal: bool = True


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
    edited_recommendation_fields: tuple[TrainingRecommendationField, ...] | None = None
    feedback: ToolAttemptFeedback = ToolAttemptFeedback.SYSTEM_REJECTION
    tool_input_receipt: AssistantToolInputReceipt | None = None


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
    ) -> None:
        self._registry = registry
        self._verifier = verifier
        self._context_source = context_source
        self._execution_policy = execution_policy or HostExecutionPolicy()
        self._path_verifier = path_verifier or PathProvenanceVerifier()

    def admit_typed_clarification(
        self,
        *,
        command_name: str,
        missing_inputs: tuple[str, ...],
        question: str,
        original_user_text: str,
        publication: PromptToolPublication,
        verified_parameters: tuple[tuple[str, Any], ...] = (),
    ) -> AssistantToolInputReceipt | None:
        """Admit one exact direct-tool clarification without granting execution."""
        if (
            command_name not in DIRECT_PARAMETER_TOOLS
            or not publication.permits(command_name)
            or not direct_parameter_action_request_matches(
                command_name,
                original_user_text,
            )
        ):
            return None
        generation = publication.backend_generation
        if type(generation) is not int or generation < 0:
            return None
        tool = self._registry.get_tool(command_name)
        schema = getattr(tool, "parameters", None)
        required = schema.get("required") if isinstance(schema, dict) else None
        if not isinstance(required, list):
            return None
        required_names = tuple(
            name.strip() for name in required if isinstance(name, str) and name.strip()
        )
        if (
            not 1 <= len(required_names) <= 2
            or len(set(required_names)) != len(required_names)
            or not 1 <= len(missing_inputs) <= 2
            or len(set(missing_inputs)) != len(missing_inputs)
            or bool(set(missing_inputs) - set(required_names))
            or any(
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or item[0] not in required_names
                for item in verified_parameters
            )
            or len({item[0] for item in verified_parameters})
            != len(verified_parameters)
        ):
            return None
        return AssistantToolInputReceipt(
            command_name=command_name,
            original_user_text=original_user_text,
            question=question,
            publication_generation=generation,
            missing_inputs=required_names,
            verified_parameters=verified_parameters,
        )

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
        if request.repeated:
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
        import_intent_result = (
            self._import_eeg_data_intent_result(request, context)
            if request.enforce_direct_parameter_origins
            else None
        )
        if import_intent_result is not None:
            return ToolAttemptDecision(
                ToolAttemptAction.INTENT_BLOCKED,
                command_name,
                params,
                context=context,
                result=import_intent_result,
            )
        receipt = request.tool_input_receipt
        receipt_matches = receipt is not None and receipt.matches(
            command_name,
            request.publication.backend_generation,
        )
        receipt_complete = receipt_matches and set(
            dict(receipt.verified_parameters)
        ) == set(receipt.missing_inputs)
        if receipt_matches and not receipt_complete:
            return ToolAttemptDecision(
                ToolAttemptAction.RESPOND,
                command_name,
                params,
                context=context,
                message=(
                    "I could not confirm all required values. Please start the "
                    "action again with all required parameters."
                ),
            )
        if receipt_complete:
            supplied = request.supplied_parameters or request.params
            if set(supplied) - set(receipt.missing_inputs):
                return ToolAttemptDecision(
                    ToolAttemptAction.VERIFICATION_BLOCKED,
                    command_name,
                    params,
                    context=context,
                    result=self._verification_result(
                        request,
                        context,
                        "Unknown parameter in a receipt-bound assistant action.",
                    ),
                    feedback=ToolAttemptFeedback.TOOL_OUTPUT,
                )
            params = dict(receipt.verified_parameters)
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

        if request.enforce_direct_parameter_origins:
            if receipt_complete:
                origin_validation = VerificationResult(True)
            else:
                origin_validation = verify_direct_parameter_origins(
                    command_name,
                    params,
                    request.latest_user_text,
                )
            if not origin_validation.is_valid:
                receipt = self._origin_receipt(request, context, origin_validation)
                return ToolAttemptDecision(
                    ToolAttemptAction.RESPOND,
                    command_name,
                    params,
                    context=context,
                    message=(
                        origin_validation.error_message
                        or "What parameters should I use for this action?"
                    ),
                    tool_input_receipt=receipt,
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
        edited_recommendation_fields = assistant_edited_recommendation_fields(
            command_name,
            params,
        )
        evaluated_params = setting_confirmation_params(command_name, params)
        setting_confirmation = assistant_setting_change_requires_confirmation(
            command_name,
            evaluated_params,
            context.state,
        )
        if setting_confirmation or self._execution_policy.needs_confirmation(
            context.availability,
            tool_requires_confirmation=bool(tool and tool.requires_confirmation),
        ):
            return ToolAttemptDecision(
                ToolAttemptAction.CONFIRMATION_REQUIRED,
                command_name,
                evaluated_params,
                context=context,
                tool=tool,
                confirmation_kind=(
                    SETTING_CHANGE_CONFIRMATION_KIND if setting_confirmation else None
                ),
                edited_recommendation_fields=edited_recommendation_fields,
            )
        return ToolAttemptDecision(
            ToolAttemptAction.EXECUTE,
            command_name,
            evaluated_params,
            context=context,
            tool=tool,
            edited_recommendation_fields=edited_recommendation_fields,
        )

    def _origin_receipt(
        self,
        request: ToolAttemptRequest,
        context: ToolAvailabilityContext,
        origin: VerificationResult,
    ) -> AssistantToolInputReceipt | None:
        """Turn one safe direct-parameter rejection into bounded follow-up state."""
        if (
            request.tool_input_receipt is not None
            or not request.single_proposal
            or not context.availability.enabled
            or not direct_parameter_action_request_matches(
                request.command_name,
                request.latest_user_text,
            )
        ):
            return None
        return self.admit_typed_clarification(
            command_name=request.command_name,
            missing_inputs=tuple(request.params),
            question=(
                origin.error_message or "What parameters should I use for this action?"
            ),
            original_user_text=request.latest_user_text,
            publication=request.publication,
            verified_parameters=verified_direct_parameter_origin_values(
                request.command_name,
                request.params,
                request.latest_user_text,
            ),
        )

    @staticmethod
    def _import_eeg_data_intent_result(
        request: ToolAttemptRequest,
        context: ToolAvailabilityContext,
    ) -> ToolCommandResult | None:
        """Keep the import chooser behind its one approved positive request."""
        if (
            request.command_name != "import_eeg_data"
            or import_eeg_data_positive_origin_matches(request.latest_user_text)
        ):
            return None
        mapped_command = TOOL_TO_COMMAND.get(request.command_name)
        return ToolCommandResult.failure(
            request.command_name,
            "Please make one direct request to import an EEG data, dataset, file, "
            "or folder.",
            command_name=(mapped_command.value if mapped_command is not None else None),
            state=context.state,
            capability=context.availability.to_dict(),
            error_type="intent_mismatch",
            recoverable=True,
            diagnostics={
                "policy": "import_eeg_data_positive_origin",
                "publication_generation": context.generation,
            },
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
        requires_command_confirmation: bool = True,
        publication_generation: int | None = None,
        confirmation_kind: str | None = None,
        resource_preflight_receipt: ResourceConfirmationChallenge | None = None,
        edited_recommendation_fields: tuple[TrainingRecommendationField, ...]
        | None = None,
    ) -> dict[str, Any]:
        """Inject backend confirmation fields after explicit user approval."""
        confirmed = dict(params)
        if requires_command_confirmation:
            confirmed["confirmed"] = True
        if confirmation_kind == SETTING_CHANGE_CONFIRMATION_KIND:
            if type(publication_generation) is not int or publication_generation < 0:
                raise ValueError(
                    "Setting confirmation requires an authoritative publication "
                    "generation."
                )
            confirmed = authorize_assistant_setting_change(
                command_name,
                confirmed,
                publication_generation=publication_generation,
                edited_recommendation_fields=edited_recommendation_fields,
            )
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
        context = decision.context
        requires_command_confirmation = self._execution_policy.needs_confirmation(
            (
                context.availability
                if isinstance(context, ToolAvailabilityContext)
                else None
            ),
            tool_requires_confirmation=bool(
                decision.tool and decision.tool.requires_confirmation
            ),
        )
        return self.confirmed_params(
            decision.command_name,
            decision.params,
            requires_command_confirmation=requires_command_confirmation,
            publication_generation=(
                context.generation if context is not None else None
            ),
            confirmation_kind=decision.confirmation_kind,
            resource_preflight_receipt=receipt,
            edited_recommendation_fields=decision.edited_recommendation_fields,
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
        del latest_user_text
        lower = message.lower()
        if "missing required parameter" in lower:
            return message.replace("Missing required parameter(s)", "Required input")
        return message
