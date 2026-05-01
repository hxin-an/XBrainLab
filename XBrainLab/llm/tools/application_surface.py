"""ApplicationService-backed command surface for LLM tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from XBrainLab.backend.application import CommandName, CommandResult
from XBrainLab.backend.application.capabilities import CommandCapability
from XBrainLab.backend.facade import BackendFacade
from XBrainLab.backend.study import Study


class CapabilityPolicyUnavailableError(RuntimeError):
    """Raised when a non-production Study object cannot provide real policy."""


CapabilityPolicyUnavailable = CapabilityPolicyUnavailableError


TOOL_TO_COMMAND: dict[str, CommandName] = {
    "load_data": CommandName.LOAD_DATA,
    "attach_labels": CommandName.ATTACH_LABELS,
    "apply_standard_preprocess": CommandName.PREPROCESS,
    "apply_bandpass_filter": CommandName.PREPROCESS,
    "apply_notch_filter": CommandName.PREPROCESS,
    "resample_data": CommandName.PREPROCESS,
    "normalize_data": CommandName.PREPROCESS,
    "set_reference": CommandName.PREPROCESS,
    "select_channels": CommandName.PREPROCESS,
    "set_montage": CommandName.PREPROCESS,
    "epoch_data": CommandName.CREATE_EPOCH,
    "generate_dataset": CommandName.GENERATE_DATASET,
    "set_model": CommandName.CONFIGURE_TRAINING,
    "configure_training": CommandName.CONFIGURE_TRAINING,
    "start_training": CommandName.TRAIN,
    "clear_dataset": CommandName.RESET_SESSION,
}

READ_ONLY_TOOLS = frozenset({"list_files", "get_dataset_info", "switch_panel"})


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
        }


@dataclass(frozen=True)
class ToolCommandResult:
    """Agent-facing structured result for ApplicationService-backed tools."""

    ok: bool
    tool_name: str
    message: str
    command_name: str | None = None
    raw_result: Any = None
    error_type: str | None = None
    recoverable: bool = True
    blocked_reason: str | None = None
    state: dict[str, Any] | None = None
    capability: dict[str, Any] | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    @classmethod
    def blocked(
        cls,
        tool_name: str,
        availability: ToolAvailability,
        state: dict[str, Any] | None = None,
    ) -> ToolCommandResult:
        """Build a failed result from a shared capability-policy block."""
        reason = availability.reason_text or "Tool is not available right now."
        message = (
            f"Tool '{tool_name}' is blocked by ApplicationService "
            f"command '{availability.command_name}': {reason}"
            if availability.command_name
            else f"Tool '{tool_name}' is blocked: {reason}"
        )
        return cls(
            ok=False,
            tool_name=tool_name,
            command_name=availability.command_name,
            message=message,
            error_type="precondition",
            recoverable=True,
            blocked_reason=reason,
            state=state,
            capability=availability.to_dict(),
        )

    @classmethod
    def failure(
        cls,
        tool_name: str,
        message: str,
        command_name: str | None = None,
        state: dict[str, Any] | None = None,
        capability: dict[str, Any] | None = None,
        raw_result: Any = None,
        error_type: str = "runtime",
        recoverable: bool = True,
    ) -> ToolCommandResult:
        """Build a failed structured result for a legacy tool failure."""
        return cls(
            ok=False,
            tool_name=tool_name,
            command_name=command_name,
            message=message,
            raw_result=raw_result,
            error_type=error_type,
            recoverable=recoverable,
            state=state,
            capability=capability,
        )

    @classmethod
    def from_command_result(
        cls,
        tool_name: str,
        result: CommandResult,
        capability: dict[str, Any] | None = None,
    ) -> ToolCommandResult:
        """Convert a backend :class:`CommandResult` into an agent result."""
        return cls(
            ok=result.ok,
            tool_name=tool_name,
            command_name=result.command_name,
            message=result.message,
            raw_result=result.to_dict(),
            error_type=result.error_type.value,
            recoverable=result.recoverable,
            blocked_reason=result.error_message if result.failed else None,
            state=result.state.to_dict() if hasattr(result.state, "to_dict") else None,
            capability=capability,
            diagnostics=result.diagnostics,
        )

    @classmethod
    def from_legacy_result(
        cls,
        tool_name: str,
        raw_result: Any,
        availability: ToolAvailability | None = None,
        state: dict[str, Any] | None = None,
    ) -> ToolCommandResult:
        """Wrap a legacy string/object tool result with stable semantics."""
        message = str(raw_result) if raw_result is not None else ""
        ok = legacy_tool_result_succeeded(message)
        return cls(
            ok=ok,
            tool_name=tool_name,
            command_name=(
                availability.command_name
                if availability
                else _command_name_for_tool(tool_name)
            ),
            message=message,
            raw_result=raw_result,
            error_type=None if ok else "runtime",
            recoverable=True,
            blocked_reason=None if ok else message,
            state=state,
            capability=availability.to_dict() if availability else None,
        )

    def to_payload(self) -> dict[str, Any]:
        """Return JSON-friendly payload for the next agent turn."""
        return {
            "ok": self.ok,
            "tool_name": self.tool_name,
            "command_name": self.command_name,
            "message": self.message,
            "error_type": self.error_type,
            "recoverable": self.recoverable,
            "blocked_reason": self.blocked_reason,
            "state": self.state,
            "capability": self.capability,
            "diagnostics": self.diagnostics,
            "raw_result": self.raw_result,
        }


def build_agent_tool_policy(study: Any) -> dict[str, ToolAvailability]:
    """Return agent tool availability from the ApplicationService policy."""
    if not isinstance(study, Study):
        raise CapabilityPolicyUnavailableError(
            "ApplicationService policy requires a real Study instance.",
        )

    facade = BackendFacade(study)
    app_policy = facade.get_capabilities()
    state = facade.get_state()

    tool_policy: dict[str, ToolAvailability] = {}
    for tool_name, command_name in TOOL_TO_COMMAND.items():
        capability = app_policy.get(command_name)
        tool_policy[tool_name] = _from_capability(tool_name, command_name, capability)

    has_raw_data = state.active_dataset.has_raw_data
    tool_policy["list_files"] = ToolAvailability(
        tool_name="list_files",
        enabled=True,
        read_only=True,
    )
    tool_policy["switch_panel"] = ToolAvailability(
        tool_name="switch_panel",
        enabled=True,
        read_only=True,
    )
    tool_policy["get_dataset_info"] = ToolAvailability(
        tool_name="get_dataset_info",
        enabled=has_raw_data,
        reasons=(
            () if has_raw_data else ("Load raw data before requesting dataset info.",)
        ),
        read_only=True,
    )
    return tool_policy


def get_application_context(
    study: Any,
    tool_name: str,
) -> tuple[ToolAvailability | None, dict[str, Any] | None]:
    """Return availability and current state for a tool, when available."""
    try:
        availability = get_tool_availability(study, tool_name)
    except CapabilityPolicyUnavailableError:
        return None, None

    state = _state_snapshot_dict(study)
    return availability, state


def get_tool_availability(study: Any, tool_name: str) -> ToolAvailability:
    """Return a single tool availability record."""
    policy = build_agent_tool_policy(study)
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
) -> ToolCommandResult:
    """Convert a real tool return value into a structured agent result."""
    if isinstance(raw_result, ToolCommandResult):
        return raw_result

    if availability is None:
        try:
            availability = get_tool_availability(study, tool_name)
        except CapabilityPolicyUnavailableError:
            availability = None

    capability = availability.to_dict() if availability else None
    if isinstance(raw_result, CommandResult):
        return ToolCommandResult.from_command_result(
            tool_name,
            raw_result,
            capability=capability,
        )

    return ToolCommandResult.from_legacy_result(
        tool_name,
        raw_result,
        availability=availability,
        state=_state_snapshot_dict(study),
    )


def legacy_tool_result_succeeded(message: str) -> bool:
    """Infer success from legacy string-only tool output."""
    text = message.strip().lower()
    if not text:
        return True
    failure_prefixes = (
        "error:",
        "failed",
        "failure:",
        "preprocessing failed",
        "dataset generation failed",
        "epoching failed",
        "bandpass filter failed",
        "notch filter failed",
        "resample failed",
        "normalization failed",
        "re-reference failed",
        "channel selection failed",
        "failed to",
    )
    if text.startswith(failure_prefixes):
        return False
    return " failed:" not in text


def enabled_tool_names(study: Any) -> list[str]:
    """Return tool names that are currently available to the agent."""
    return [
        tool_name
        for tool_name, availability in build_agent_tool_policy(study).items()
        if availability.enabled
    ]


def blocked_tool_reasons(study: Any) -> dict[str, str]:
    """Return blocked tool names and reasons for prompt diagnostics."""
    return {
        _blocked_prompt_name(availability): availability.reason_text
        for availability in build_agent_tool_policy(study).values()
        if not availability.enabled and availability.reasons
    }


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
    )


def _blocked_prompt_name(availability: ToolAvailability) -> str:
    return availability.command_name or availability.tool_name


def _command_name_for_tool(tool_name: str) -> str | None:
    command_name = TOOL_TO_COMMAND.get(tool_name)
    return command_name.value if command_name else None


def _state_snapshot_dict(study: Any) -> dict[str, Any] | None:
    if not isinstance(study, Study):
        return None
    try:
        return BackendFacade(study).get_state().to_dict()
    except Exception:
        return None
