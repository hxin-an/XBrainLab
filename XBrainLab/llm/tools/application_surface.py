"""ApplicationService-backed command surface for LLM tools."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import Mock

from XBrainLab.backend.application import (
    ApplyInterpretationCommand,
    AttachLabelsCommand,
    Command,
    CommandName,
    CommandResult,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    EvaluateCommand,
    GenerateDatasetCommand,
    LoadDataCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ReloadInterpretationRecipeCommand,
    ResetSessionCommand,
    SaliencyCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    TrainCommand,
    ValidateInterpretationCommand,
    VisualizeCommand,
)
from XBrainLab.backend.application.capabilities import CommandCapability
from XBrainLab.backend.facade import BackendFacade
from XBrainLab.backend.study import Study


class CapabilityPolicyUnavailableError(RuntimeError):
    """Raised when a non-production Study object cannot provide real policy."""


CapabilityPolicyUnavailable = CapabilityPolicyUnavailableError


TOOL_TO_COMMAND: dict[str, CommandName] = {
    "scan_source": CommandName.SCAN_SOURCE,
    "preview_interpretation": CommandName.PREVIEW_INTERPRETATION,
    "validate_interpretation": CommandName.VALIDATE_INTERPRETATION,
    "apply_interpretation": CommandName.APPLY_INTERPRETATION,
    "save_interpretation_recipe": CommandName.SAVE_INTERPRETATION_RECIPE,
    "reload_interpretation_recipe": CommandName.RELOAD_INTERPRETATION_RECIPE,
    "load_data": CommandName.LOAD_DATA,
    "attach_labels": CommandName.ATTACH_LABELS,
    "apply_standard_preprocess": CommandName.PREPROCESS,
    "apply_bandpass_filter": CommandName.PREPROCESS,
    "apply_notch_filter": CommandName.PREPROCESS,
    "resample_data": CommandName.PREPROCESS,
    "normalize_data": CommandName.PREPROCESS,
    "set_reference": CommandName.PREPROCESS,
    "select_channels": CommandName.PREPROCESS,
    "set_montage": CommandName.APPLY_MONTAGE,
    "epoch_data": CommandName.CREATE_EPOCH,
    "generate_dataset": CommandName.GENERATE_DATASET,
    "set_model": CommandName.CONFIGURE_TRAINING,
    "configure_training": CommandName.CONFIGURE_TRAINING,
    "start_training": CommandName.TRAIN,
    "evaluate": CommandName.EVALUATE,
    "visualize": CommandName.VISUALIZE,
    "saliency": CommandName.SALIENCY,
    "clear_dataset": CommandName.RESET_SESSION,
    "query_state": CommandName.QUERY_STATE,
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

    @property
    def user_correctable(self) -> bool:
        """Whether user input is the next useful step instead of LLM retry."""
        return self.error_type in {"input", "precondition", "confirmation_required"}

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
        error_type = None if ok else legacy_tool_error_type(message)
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
            error_type=error_type,
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
    if not isinstance(study, Study) or isinstance(study, Mock):
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


def execute_application_tool_command(
    study: Any,
    tool_name: str,
    params: dict[str, Any],
    availability: ToolAvailability | None = None,
) -> ToolCommandResult | None:
    """Execute a tool through ApplicationService when a direct command exists.

    ``None`` means the tool still needs the legacy real-tool path, either
    because it is read-only/UI-side or because the provided parameters are not
    enough to safely construct a backend command.
    """
    if not isinstance(study, Study) or isinstance(study, Mock):
        return None

    command = _command_for_tool(tool_name, params)
    if command is None:
        return None

    if availability is None:
        try:
            availability = get_tool_availability(study, tool_name)
        except CapabilityPolicyUnavailableError:
            availability = None

    result = BackendFacade(study).service.execute(command)
    return ToolCommandResult.from_command_result(
        tool_name,
        result,
        capability=availability.to_dict() if availability else None,
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


def legacy_tool_error_type(message: str) -> str:
    """Classify legacy string-only failures into product-level buckets."""
    text = message.strip().lower()
    if any(
        marker in text
        for marker in (
            "is required",
            "cannot be empty",
            "does not exist",
            "no valid files",
            "path does not exist",
        )
    ):
        return "input"
    if any(
        marker in text
        for marker in (
            "no data loaded",
            "before training",
            "before preprocessing",
            "before generating",
            "requires confirmation",
            "not available",
        )
    ):
        return "precondition"
    return "runtime"


def _command_for_tool(tool_name: str, params: dict[str, Any]) -> Command | None:
    """Build an ApplicationService command for a supported agent tool."""
    if tool_name == "scan_source":
        source_path = params.get("source_path")
        if not source_path:
            return None
        return ScanSourceCommand(
            source_path=str(source_path),
            source_hint=str(params.get("source_hint", "auto")),
        )

    if tool_name == "preview_interpretation":
        choices = params.get("choices")
        return PreviewInterpretationCommand(
            scan_id=_optional_str(params.get("scan_id")),
            choices=dict(choices) if isinstance(choices, dict) else {},
        )

    if tool_name == "validate_interpretation":
        return ValidateInterpretationCommand(
            candidate_id=_optional_str(params.get("candidate_id")),
        )

    if tool_name == "apply_interpretation":
        return ApplyInterpretationCommand(
            candidate_id=_optional_str(params.get("candidate_id")),
            confirmed=bool(params.get("confirmed", False)),
        )

    if tool_name == "save_interpretation_recipe":
        return SaveInterpretationRecipeCommand(
            recipe_path=_optional_str(params.get("recipe_path")),
        )

    if tool_name == "reload_interpretation_recipe":
        recipe_path = params.get("recipe_path")
        if not recipe_path:
            return None
        return ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path))

    if tool_name == "load_data":
        paths = params.get("paths")
        if not isinstance(paths, list) or not paths:
            return None
        expanded_paths = _expand_load_paths([str(path) for path in paths])
        if not expanded_paths:
            return None
        return LoadDataCommand(paths=expanded_paths)

    if tool_name == "attach_labels":
        mapping = params.get("mapping")
        if not isinstance(mapping, dict) or not mapping:
            return None
        return AttachLabelsCommand(mapping={str(k): str(v) for k, v in mapping.items()})

    if tool_name == "apply_standard_preprocess":
        return PreprocessCommand(
            operation=PreprocessOperation.STANDARD,
            low_freq=_optional_float(params.get("l_freq")),
            high_freq=_optional_float(params.get("h_freq")),
            notch_freq=_optional_float(params.get("notch_freq")),
            rate=_optional_int(params.get("resample_rate")),
            method=_optional_str(params.get("normalize_method")),
        )

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

    if tool_name == "select_channels":
        channels = params.get("channels")
        if not isinstance(channels, list) or not channels:
            return None
        return PreprocessCommand(
            operation=PreprocessOperation.SELECT_CHANNELS,
            channels=[str(channel) for channel in channels],
        )

    if tool_name == "epoch_data":
        t_min = params.get("t_min")
        t_max = params.get("t_max")
        if t_min is None or t_max is None:
            return None
        return CreateEpochCommand(
            t_min=float(t_min),
            t_max=float(t_max),
            baseline=params.get("baseline"),
            event_ids=params.get("event_id"),
        )

    if tool_name == "generate_dataset":
        return GenerateDatasetCommand(
            test_ratio=float(params.get("test_ratio", 0.2)),
            val_ratio=float(params.get("val_ratio", 0.2)),
            split_strategy=str(params.get("split_strategy", "trial")),
            training_mode=str(params.get("training_mode", "individual")),
        )

    if tool_name == "set_model":
        model_name = params.get("model_name")
        if not model_name:
            return None
        return ConfigureTrainingCommand(model_name=str(model_name))

    if tool_name == "configure_training":
        return ConfigureTrainingCommand(
            epoch=int(params.get("epoch", 10)),
            batch_size=int(params.get("batch_size", 32)),
            learning_rate=float(params.get("learning_rate", 0.001)),
            repeat=int(params.get("repeat", 1)),
            device=str(params.get("device", "cpu")),
            optimizer=str(params.get("optimizer", "adam")),
            save_checkpoints_every=int(params.get("save_checkpoints_every", 0)),
        )

    if tool_name == "start_training":
        return TrainCommand()

    if tool_name == "evaluate":
        return EvaluateCommand(target=_optional_str(params.get("target")))

    if tool_name == "visualize":
        return VisualizeCommand(view=_optional_str(params.get("view")))

    if tool_name == "saliency":
        saliency_params = params.get("params")
        return SaliencyCommand(
            method=_optional_str(params.get("method")),
            params=dict(saliency_params) if isinstance(saliency_params, dict) else None,
        )

    if tool_name == "clear_dataset":
        return ResetSessionCommand(confirmed=True)

    if tool_name == "query_state":
        return QueryStateCommand(
            query=str(params.get("query", "state")),
            params=dict(params.get("params", {}))
            if isinstance(params.get("params"), dict)
            else {},
            include_objects=bool(params.get("include_objects", False)),
        )

    return None


def _expand_load_paths(paths: list[str]) -> list[str]:
    """Expand directory arguments before routing load_data to ApplicationService."""
    expanded_paths: list[str] = []
    for path in paths:
        if os.path.isdir(path):
            try:
                for filename in sorted(os.listdir(path)):
                    full_path = os.path.join(path, filename)
                    if os.path.isfile(full_path):
                        expanded_paths.append(full_path)
            except OSError:
                continue
        else:
            expanded_paths.append(path)
    return expanded_paths


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


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


def _blocked_prompt_name(availability: ToolAvailability) -> str:
    return availability.command_name or availability.tool_name


def _command_name_for_tool(tool_name: str) -> str | None:
    command_name = TOOL_TO_COMMAND.get(tool_name)
    return command_name.value if command_name else None


def _state_snapshot_dict(study: Any) -> dict[str, Any] | None:
    if not isinstance(study, Study) or isinstance(study, Mock):
        return None
    try:
        return BackendFacade(study).get_state().to_dict()
    except Exception:
        return None
