"""ApplicationService-backed command surface for LLM tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from XBrainLab.backend.application import CommandName
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
