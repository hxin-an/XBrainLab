"""ApplicationService-backed command surface for LLM tools."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Protocol, cast

from XBrainLab.backend.application import (
    ClearTrainingHistoryCommand,
    Command,
    CommandName,
    CommandResult,
    PreprocessCommand,
    PreprocessOperation,
    ResetPreprocessCommand,
    StopTrainingCommand,
    TrainCommand,
    get_application_service,
)
from XBrainLab.backend.application.capabilities import (
    CapabilityPolicy,
    CommandCapability,
    build_capability_policy,
)
from XBrainLab.backend.application.view_publication import (
    PUBLIC_VIEW_UNAVAILABLE_MESSAGE,
    ApplicationViewPublication,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.training.input_contract import (
    TrainingInputContractError,
    normalize_strict_boolean,
)
from XBrainLab.llm.action_contracts import (
    AGENT_ACTION_CONTRACTS,
    AgentExecutionKind,
)

from . import result_contract
from .result_contract import (
    APPLICATION_TOOL_RUNTIME_REQUIRED_FAILURE,
    UiRequest,
)


class CapabilityPolicyUnavailableError(RuntimeError):
    """Raised when no application runtime can provide capability policy."""


class AuthoritativeConfirmationParameter(str):
    """Display-only confirmation value projected from backend state."""


@dataclass(frozen=True, slots=True)
class StartTrainingConfirmationTruth:
    """Backend-owned values that must be shown before training starts."""

    output_directory: str
    checkpoint_epoch: int

    @property
    def checkpoint_policy(self) -> str:
        if self.checkpoint_epoch == 0:
            return "Disabled"
        suffix = "" if self.checkpoint_epoch == 1 else "s"
        return f"Every {self.checkpoint_epoch} epoch{suffix}"

    def as_host_parameters(
        self,
    ) -> dict[str, AuthoritativeConfirmationParameter]:
        return {
            "output_directory": AuthoritativeConfirmationParameter(
                self.output_directory
            ),
            "checkpoint_policy": AuthoritativeConfirmationParameter(
                self.checkpoint_policy
            ),
        }


def start_training_confirmation_truth(
    state: dict[str, Any] | None,
) -> StartTrainingConfirmationTruth | None:
    """Read confirmation values from one authoritative backend state snapshot."""
    if not isinstance(state, dict):
        return None
    training = state.get("training")
    if not isinstance(training, dict):
        return None
    option = training.get("training_option")
    if not isinstance(option, dict):
        return None
    output_directory = option.get("output_dir")
    checkpoint_epoch = option.get("checkpoint_epoch")
    if not isinstance(output_directory, str) or not output_directory.strip():
        return None
    if (
        isinstance(checkpoint_epoch, bool)
        or not isinstance(checkpoint_epoch, int)
        or checkpoint_epoch < 0
    ):
        return None
    return StartTrainingConfirmationTruth(
        output_directory=output_directory,
        checkpoint_epoch=checkpoint_epoch,
    )


class ApplicationToolRuntime(Protocol):
    """Application command boundary required by the agent tool surface."""

    def get_view_publication(self) -> ApplicationViewPublication:
        """Return one committed state/capability publication."""
        ...

    def execute(self, command: Command) -> CommandResult:
        """Execute a command through the application command spine."""
        ...


@dataclass(frozen=True)
class _StudyApplicationToolRuntime:
    """Production adapter from a real Study to ApplicationService."""

    study: Study

    def get_view_publication(self) -> ApplicationViewPublication:
        return get_application_service(self.study).get_view_publication()

    def execute(self, command: Command) -> CommandResult:
        return get_application_service(self.study).execute(command)


def application_tool_runtime(study: Any) -> ApplicationToolRuntime | None:
    """Return the production runtime only for a genuine Study implementation."""
    if not issubclass(type(study), Study):
        return None
    return _StudyApplicationToolRuntime(cast(Study, study))


def _resolve_application_tool_runtime(
    study: Any,
    runtime: ApplicationToolRuntime | None,
) -> ApplicationToolRuntime | None:
    return runtime if runtime is not None else application_tool_runtime(study)


TOOL_TO_COMMAND: dict[str, CommandName] = AGENT_ACTION_CONTRACTS.tool_to_command()

APPLICATION_COMMAND_TOOLS = AGENT_ACTION_CONTRACTS.tool_names_for_kind(
    AgentExecutionKind.APPLICATION_COMMAND
)
READ_ONLY_TOOLS = AGENT_ACTION_CONTRACTS.tool_names_for_kind(
    AgentExecutionKind.READ_ONLY
)
UI_REQUEST_TOOLS = AGENT_ACTION_CONTRACTS.tool_names_for_kind(
    AgentExecutionKind.UI_REQUEST
)


@dataclass(frozen=True)
class ToolAvailability:
    """Agent-facing availability derived from backend command capabilities."""

    tool_name: str
    enabled: bool
    reasons: tuple[str, ...] = ()
    command_name: str | None = None
    confirmation_required: bool = False
    destructive: bool = False
    long_running: bool = False
    read_only: bool = False
    can_auto_execute: bool = True
    requires_confirmation: bool = False
    decision_boundary: str | None = None
    continue_allowed_after_success: bool = True
    retry_limit: int = 2
    stop_after_success: bool = False
    blocks_downstream_until_confirmed: bool = False

    @property
    def reason_text(self) -> str:
        return "; ".join(self.reasons)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "enabled": self.enabled,
            "reasons": list(self.reasons),
            "command_name": self.command_name,
            "confirmation_required": self.confirmation_required,
            "destructive": self.destructive,
            "long_running": self.long_running,
            "read_only": self.read_only,
            "can_auto_execute": self.can_auto_execute,
            "requires_confirmation": self.requires_confirmation,
            "decision_boundary": self.decision_boundary,
            "continue_allowed_after_success": self.continue_allowed_after_success,
            "retry_limit": self.retry_limit,
            "stop_after_success": self.stop_after_success,
            "blocks_downstream_until_confirmed": (
                self.blocks_downstream_until_confirmed
            ),
        }


@dataclass(frozen=True)
class ToolAvailabilityContext:
    """One tool policy decision and state from the same publication."""

    availability: ToolAvailability
    state: dict[str, Any] | None
    generation: int | None
    policy_error: str | None = None
    capabilities: CapabilityPolicy | None = None


def _public_unsupported_result_type(value: object) -> str:
    value_type = type(value)
    for supported_type, public_name in (
        (str, "str"),
        (dict, "dict"),
        (list, "list"),
        (tuple, "tuple"),
        (set, "set"),
        (bool, "bool"),
        (int, "int"),
        (float, "float"),
        (bytes, "bytes"),
        (type(None), "NoneType"),
    ):
        if value_type is supported_type:
            return public_name
    return "unsupported"


def blocked_tool_result(
    tool_name: str,
    availability: ToolAvailability,
    state: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> result_contract.ToolCommandResult:
    """Build a failed result from a shared capability-policy block."""
    reason = availability.reason_text or "Tool is not available right now."
    message = (
        f"Tool '{tool_name}' is blocked by ApplicationService "
        f"command '{availability.command_name}': {reason}"
        if availability.command_name
        else f"Tool '{tool_name}' is blocked: {reason}"
    )
    return result_contract.ToolCommandResult(
        ok=False,
        tool_name=tool_name,
        command_name=availability.command_name,
        message=message,
        error_type="precondition",
        recoverable=True,
        blocked_reason=reason,
        state=state,
        capability=availability.to_dict(),
        diagnostics=(dict.copy(diagnostics) if type(diagnostics) is dict else {}),
    )


def build_agent_tool_policy(
    study: Any,
    *,
    publication: ApplicationViewPublication | None = None,
    runtime: ApplicationToolRuntime | None = None,
) -> dict[str, ToolAvailability]:
    """Return agent tool availability from the ApplicationService policy."""
    application_runtime = _resolve_application_tool_runtime(study, runtime)
    if application_runtime is None:
        raise CapabilityPolicyUnavailableError(
            "ApplicationService policy requires a genuine Study or an explicit "
            "ApplicationToolRuntime.",
        )

    current = publication
    if current is None:
        current = application_runtime.get_view_publication()
    return _build_agent_tool_policy_from_publication(current)


def _build_agent_tool_policy_from_publication(
    publication: ApplicationViewPublication,
) -> dict[str, ToolAvailability]:
    """Build one tool policy from a single committed application generation."""
    app_policy = publication.effective_capabilities
    tool_policy: dict[str, ToolAvailability] = {}
    for tool_name, command_name in TOOL_TO_COMMAND.items():
        capability = app_policy.get(command_name)
        tool_policy[tool_name] = _from_capability(tool_name, command_name, capability)
    tool_policy["switch_panel"] = ToolAvailability(
        tool_name="switch_panel",
        enabled=True,
        read_only=True,
    )
    if not publication.usable:
        reason = publication.public_unavailable_reason or (
            PUBLIC_VIEW_UNAVAILABLE_MESSAGE
        )
        tool_policy = {
            name: (
                availability
                if name == "switch_panel"
                else replace(
                    availability,
                    enabled=False,
                    reasons=(reason,),
                    can_auto_execute=False,
                )
            )
            for name, availability in tool_policy.items()
        }
    return tool_policy


def get_application_context(
    study: Any,
    tool_name: str,
    *,
    runtime: ApplicationToolRuntime | None = None,
) -> ToolAvailabilityContext | None:
    """Return availability and current state for a tool, when available."""
    application_runtime = _resolve_application_tool_runtime(study, runtime)
    if application_runtime is None:
        return None
    publication = application_runtime.get_view_publication()
    policy = _build_agent_tool_policy_from_publication(publication)
    availability = policy.get(
        tool_name,
        ToolAvailability(
            tool_name=tool_name,
            enabled=False,
            reasons=("Tool is not part of the unified ApplicationService surface.",),
        ),
    )
    policy_error = None
    if not publication.usable:
        policy_error = publication.public_unavailable_reason
    return ToolAvailabilityContext(
        availability=availability,
        state=publication.state.to_dict(),
        generation=publication.generation,
        policy_error=policy_error,
        capabilities=publication.effective_capabilities,
    )


def get_tool_availability(
    study: Any,
    tool_name: str,
    *,
    runtime: ApplicationToolRuntime | None = None,
) -> ToolAvailability:
    """Return a single tool availability record."""
    policy = build_agent_tool_policy(study, runtime=runtime)
    if tool_name in policy:
        return policy[tool_name]
    return ToolAvailability(
        tool_name=tool_name,
        enabled=False,
        reasons=("Tool is not part of the unified ApplicationService surface.",),
    )


def normalize_tool_result(
    study: Any,
    tool_name: str,
    raw_result: Any,
    availability: ToolAvailability | None = None,
    state: dict[str, Any] | None = None,
    *,
    runtime: ApplicationToolRuntime | None = None,
) -> result_contract.ToolCommandResult | UiRequest:
    """Convert a real tool return value into a structured agent result."""
    if type(raw_result) is result_contract.ToolCommandResult:
        return raw_result
    if type(raw_result) is UiRequest:
        return raw_result

    if availability is None:
        try:
            availability = get_tool_availability(
                study,
                tool_name,
                runtime=runtime,
            )
        except CapabilityPolicyUnavailableError:
            availability = None

    capability = availability.to_dict() if availability else None
    return result_contract.ToolCommandResult.failure(
        tool_name,
        "The assistant tool returned an invalid result contract.",
        command_name=(
            availability.command_name
            if availability
            else _command_name_for_tool(tool_name)
        ),
        state=(
            state if state is not None else _state_snapshot_dict(study, runtime=runtime)
        ),
        capability=capability,
        error_type="contract",
        recoverable=False,
        diagnostics={"returned_type": _public_unsupported_result_type(raw_result)},
    )


def execute_application_tool_command(
    study: Any,
    tool_name: str,
    params: dict[str, Any],
    availability: ToolAvailability | None = None,
    state: dict[str, Any] | None = None,
    *,
    runtime: ApplicationToolRuntime | None = None,
) -> result_contract.ToolCommandResult | None:
    """Execute a tool through ApplicationService when a direct command exists.

    ``None`` is reserved for tools outside the mapped product surface and for
    mapped UI-request adapters when a runtime is present. A mapped product tool
    without an application runtime fails closed before arguments are inspected.
    """
    contract = AGENT_ACTION_CONTRACTS.contract_for(tool_name)
    if contract is None:
        return None
    if contract.execution_kind is not AgentExecutionKind.APPLICATION_COMMAND:
        return None

    application_runtime = _resolve_application_tool_runtime(study, runtime)
    if application_runtime is None:
        mapped_command = contract.capability_command
        if mapped_command is None:  # guarded by registry validation
            raise RuntimeError(
                f"Application tool '{tool_name}' has no capability command."
            )
        failure = APPLICATION_TOOL_RUNTIME_REQUIRED_FAILURE
        return result_contract.ToolCommandResult.failure(
            tool_name,
            failure.message,
            command_name=mapped_command.value,
            state=state,
            capability=availability.to_dict() if availability else None,
            error_type=failure.error_type,
            error_code=failure.code,
            recovery_action=failure.recovery_action,
            recoverable=failure.recoverable,
            diagnostics={
                "boundary": "application_tool_runtime",
                "mapped_product_tool": True,
            },
        )

    command_params = dict(params)
    input_error: str | None = None
    try:
        command = _command_for_tool(tool_name, command_params)
    except TrainingInputContractError as exc:
        command = None
        input_error = str(exc)
    if command is None:
        mapped_command = contract.capability_command
        if mapped_command is None:  # guarded by registry validation
            raise RuntimeError(
                f"Application tool '{tool_name}' has no capability command."
            )

        if availability is None:
            try:
                availability = get_tool_availability(
                    study,
                    tool_name,
                    runtime=application_runtime,
                )
            except CapabilityPolicyUnavailableError:
                return None

        if not availability.enabled:
            return blocked_tool_result(
                tool_name,
                availability,
                state=(
                    state
                    if state is not None
                    else _state_snapshot_dict(study, runtime=application_runtime)
                ),
            )

        return result_contract.ToolCommandResult.failure(
            tool_name,
            input_error or "Required inputs are missing for this workflow command.",
            command_name=mapped_command.value,
            state=(
                state
                if state is not None
                else _state_snapshot_dict(study, runtime=application_runtime)
            ),
            capability=availability.to_dict(),
            error_type="input",
            recoverable=True,
        )

    if availability is None:
        try:
            availability = get_tool_availability(
                study,
                tool_name,
                runtime=application_runtime,
            )
        except CapabilityPolicyUnavailableError:
            availability = None

    result = application_runtime.execute(command)
    result_availability = availability
    mapped_command = TOOL_TO_COMMAND.get(tool_name)
    if mapped_command is not None and hasattr(result.state, "state_reliable"):
        capability = build_capability_policy(result.state).get(mapped_command)
        result_availability = _from_capability(
            tool_name,
            mapped_command,
            capability,
        )
    return result_contract.ToolCommandResult.from_command_result(
        tool_name,
        result,
        capability=result_availability.to_dict() if result_availability else None,
    )


def _command_for_tool(
    tool_name: str,
    params: dict[str, Any],
) -> Command | None:
    """Build an ApplicationService command for a supported agent tool."""
    contract = AGENT_ACTION_CONTRACTS.contract_for(tool_name)
    if (
        contract is None
        or contract.execution_kind is not AgentExecutionKind.APPLICATION_COMMAND
    ):
        return None
    if tool_name == "apply_bandpass_filter":
        low_freq = params.get("low_freq")
        high_freq = params.get("high_freq")
        if low_freq is None or high_freq is None:
            return None
        return PreprocessCommand(
            operation=PreprocessOperation.BANDPASS,
            low_freq=float(low_freq),
            high_freq=float(high_freq),
        )

    if tool_name == "apply_notch_filter":
        freq = params.get("freq")
        if freq is None:
            return None
        return PreprocessCommand(
            operation=PreprocessOperation.NOTCH,
            notch_freq=float(freq),
        )

    if tool_name == "resample_data":
        rate = params.get("rate")
        if rate is None:
            return None
        return PreprocessCommand(
            operation=PreprocessOperation.RESAMPLE,
            rate=int(rate),
        )

    if tool_name == "normalize_data":
        method = params.get("method")
        if method is None:
            return None
        return PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method=str(method),
        )

    if tool_name == "set_reference":
        method = params.get("method")
        if method is None:
            return None
        return PreprocessCommand(
            operation=PreprocessOperation.REREFERENCE,
            method=str(method),
        )

    if tool_name == "reset_preprocessing":
        return ResetPreprocessCommand(
            confirmed=_boolean_param(params, "confirmed"),
        )

    if tool_name == "clear_training_history":
        return ClearTrainingHistoryCommand(
            confirmed=_boolean_param(params, "confirmed"),
        )

    if tool_name == "start_training":
        return TrainCommand(
            append=_boolean_param(params, "append", default=True),
            interactive=_boolean_param(params, "interactive", default=True),
            confirmed=_boolean_param(params, "confirmed"),
            resource_preflight_confirmed=_boolean_param(
                params,
                "resource_preflight_confirmed",
            ),
            resource_preflight_token=_optional_str(
                params.get("resource_preflight_token")
            ),
        )

    if tool_name == "stop_training":
        return StopTrainingCommand()

    return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _boolean_param(
    params: dict[str, Any],
    name: str,
    *,
    default: bool = False,
) -> bool:
    return normalize_strict_boolean(name, params.get(name, default))


def _from_capability(
    tool_name: str,
    command_name: CommandName,
    capability: CommandCapability,
) -> ToolAvailability:
    return ToolAvailability(
        tool_name=tool_name,
        enabled=capability.enabled,
        reasons=tuple(capability.reasons),
        command_name=command_name.value,
        confirmation_required=capability.confirmation_required,
        destructive=capability.destructive,
        long_running=capability.long_running,
        can_auto_execute=capability.can_auto_execute,
        requires_confirmation=capability.requires_confirmation,
        decision_boundary=capability.decision_boundary,
        continue_allowed_after_success=capability.continue_allowed_after_success,
        retry_limit=capability.retry_limit,
        stop_after_success=capability.stop_after_success,
        blocks_downstream_until_confirmed=(
            capability.blocks_downstream_until_confirmed
        ),
    )


def _command_name_for_tool(tool_name: str) -> str | None:
    command_name = TOOL_TO_COMMAND.get(tool_name)
    return command_name.value if command_name else None


def _state_snapshot_dict(
    study: Any,
    *,
    runtime: ApplicationToolRuntime | None = None,
) -> dict[str, Any] | None:
    application_runtime = _resolve_application_tool_runtime(study, runtime)
    if application_runtime is None:
        return None
    try:
        publication = application_runtime.get_view_publication()
        return publication.state.to_dict()
    except Exception:
        return None
