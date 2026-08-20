"""ApplicationService-backed command surface for LLM tools."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any, Protocol, cast

from XBrainLab.backend.application import (
    ApplyInterpretationCommand,
    ClearTrainingHistoryCommand,
    Command,
    CommandName,
    CommandResult,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    DatasetSplitPreviewReceipt,
    EvaluateCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ReloadInterpretationRecipeCommand,
    ResetPreprocessCommand,
    SaliencyCommand,
    SaveDatasetSplitCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    StopTrainingCommand,
    TrainCommand,
    TrainingRecommendationField,
    ValidateInterpretationCommand,
    VisualizeCommand,
    get_application_service,
)
from XBrainLab.backend.application.capabilities import (
    CapabilityPolicy,
    CommandCapability,
    build_capability_policy,
)
from XBrainLab.backend.application.training_submission import (
    attach_training_submission_provenance,
)
from XBrainLab.backend.application.view_publication import (
    PUBLIC_VIEW_UNAVAILABLE_MESSAGE,
    ApplicationViewPublication,
)
from XBrainLab.backend.model_base.model_catalog import get_model_spec
from XBrainLab.backend.study import Study
from XBrainLab.backend.training.input_contract import (
    REQUIRED_TRAINING_FIELDS,
    TrainingInputContractError,
    normalize_non_negative_integer,
    normalize_positive_integer,
    normalize_strict_boolean,
    normalize_training_input,
)
from XBrainLab.backend.utils.public_diagnostics import (
    PUBLIC_DIAGNOSTIC_MAX_OUTPUT_BYTES,
    PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER,
    PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER,
    DiagnosticTextLayout,
    public_diagnostic_text,
    public_diagnostic_value,
)
from XBrainLab.llm.action_contracts import (
    AGENT_ACTION_CONTRACTS,
    AgentExecutionKind,
)

from .result_contract import (
    APPLICATION_TOOL_RUNTIME_REQUIRED_FAILURE,
    ToolResult,
    UiRequest,
    public_safe_result_projection,
)


class CapabilityPolicyUnavailableError(RuntimeError):
    """Raised when no application runtime can provide capability policy."""


CapabilityPolicyUnavailable = CapabilityPolicyUnavailableError


class HostAuthorizedToolParameter(str):
    """Marker for values created by host policy rather than model JSON."""


class UserProvidedTrainingOutputDir(HostAuthorizedToolParameter):
    """Output directory authorized against the current user-authored turn."""


class AuthoritativeConfirmationParameter(HostAuthorizedToolParameter):
    """Display-only confirmation value projected from backend state."""


@dataclass(frozen=True, slots=True)
class AssistantSettingConfirmation:
    """Host-only evidence that one exact setting proposal was approved."""

    tool_name: str
    params_fingerprint: str
    publication_generation: int
    edited_recommendation_fields: tuple[TrainingRecommendationField, ...] = ()

    def __post_init__(self) -> None:
        if type(self.tool_name) is not str or not self.tool_name.strip():
            raise ValueError("Setting confirmation tool name cannot be empty.")
        if type(self.params_fingerprint) is not str or not self.params_fingerprint:
            raise ValueError("Setting confirmation fingerprint cannot be empty.")
        if (
            type(self.publication_generation) is not int
            or self.publication_generation < 0
        ):
            raise ValueError(
                "Setting confirmation publication generation must be non-negative."
            )
        if any(
            not isinstance(field, TrainingRecommendationField)
            for field in self.edited_recommendation_fields
        ):
            raise TypeError("Edited recommendation fields must be typed values.")

    def matches(
        self,
        tool_name: str,
        params: dict[str, Any],
        publication_generation: int,
    ) -> bool:
        """Match only the reviewed proposal from the reviewed publication."""
        return bool(
            self.tool_name == tool_name
            and self.params_fingerprint
            == _assistant_setting_proposal_fingerprint(tool_name, params)
            and self.publication_generation == publication_generation
        )


SETTING_CHANGE_CONFIRMATION_KIND = "setting_change"
_ASSISTANT_SETTING_CONFIRMATION_PARAM = "assistant_setting_confirmation"
_ASSISTANT_HIGH_IMPACT_SETTING_TOOLS = frozenset(
    {"configure_dataset_split", "configure_training", "set_model"}
)
_RECOMMENDATION_PARAM_FIELDS = {
    "epoch": TrainingRecommendationField.EPOCHS,
    "batch_size": TrainingRecommendationField.BATCH_SIZE,
    "learning_rate": TrainingRecommendationField.LEARNING_RATE,
    "optimizer": TrainingRecommendationField.OPTIMIZER,
    "evaluation_option": TrainingRecommendationField.EVALUATION_STRATEGY,
}
_NON_PROPOSAL_CONFIRMATION_PARAMS = frozenset(
    {
        _ASSISTANT_SETTING_CONFIRMATION_PARAM,
        "confirmed",
        "resource_preflight_confirmed",
        "resource_preflight_token",
    }
)


def authorize_assistant_setting_change(
    tool_name: str,
    params: dict[str, Any],
    *,
    publication_generation: int,
    edited_recommendation_fields: tuple[TrainingRecommendationField, ...] | None = None,
) -> dict[str, Any]:
    """Attach host-only approval evidence without mutating model parameters."""
    edited_fields = (
        assistant_edited_recommendation_fields(tool_name, params)
        if edited_recommendation_fields is None
        else tuple(edited_recommendation_fields)
    )
    authorized = setting_confirmation_params(tool_name, params)
    authorized[_ASSISTANT_SETTING_CONFIRMATION_PARAM] = AssistantSettingConfirmation(
        tool_name=tool_name,
        params_fingerprint=_assistant_setting_proposal_fingerprint(
            tool_name,
            authorized,
        ),
        publication_generation=publication_generation,
        edited_recommendation_fields=edited_fields,
    )
    return authorized


def assistant_edited_recommendation_fields(
    tool_name: str,
    params: dict[str, Any],
) -> tuple[TrainingRecommendationField, ...]:
    """Return recommendation fields explicitly present in a tool proposal."""
    return tuple(
        field
        for key, field in _RECOMMENDATION_PARAM_FIELDS.items()
        if tool_name == "configure_training"
        and key in params
        and params[key] is not None
    )


def assistant_setting_params_fingerprint(params: dict[str, Any]) -> str:
    """Return the canonical identity of one normalized setting proposal."""
    payload = json.dumps(
        _canonical_confirmation_value(params),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _canonical_confirmation_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _canonical_confirmation_value(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_confirmation_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_canonical_confirmation_value(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, (str, int, float, bool)):
        return enum_value
    return repr(value)


def setting_confirmation_params(
    tool_name: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Project the complete effective setting proposal shown for approval."""
    projected = dict(params)
    if tool_name == "configure_dataset_split":
        if all(
            field in projected and projected[field] is not None
            for field in ("split_strategy", "training_mode")
        ):
            projected.setdefault("test_ratio", 0.2)
            projected.setdefault("val_ratio", 0.2)
        return projected
    if tool_name != "configure_training" or not all(
        field in projected and projected[field] is not None
        for field in REQUIRED_TRAINING_FIELDS
    ):
        return projected
    projected.setdefault("repeat", 1)
    projected.setdefault("device", "cpu")
    projected.setdefault("optimizer", "adam")
    projected.setdefault("evaluation_option", "last_epoch")
    projected.setdefault("save_checkpoints_every", 0)
    return projected


def _assistant_setting_proposal_fingerprint(
    tool_name: str,
    params: dict[str, Any],
) -> str:
    proposal = {
        key: value
        for key, value in params.items()
        if key not in _NON_PROPOSAL_CONFIRMATION_PARAMS
    }
    return assistant_setting_params_fingerprint(
        setting_confirmation_params(tool_name, proposal)
    )


def assistant_setting_change_requires_confirmation(
    tool_name: str,
    params: dict[str, Any],
    state: dict[str, Any] | None,
) -> bool:
    """Return whether a complete proposal changes authoritative settings."""
    if tool_name == "configure_dataset_split":
        return all(
            isinstance(params.get(field), str) and bool(params[field].strip())
            for field in ("split_strategy", "training_mode")
        )

    training = state.get("training") if isinstance(state, dict) else None
    if not isinstance(training, dict):
        return tool_name in _ASSISTANT_HIGH_IMPACT_SETTING_TOOLS

    if tool_name == "set_model":
        proposed_model = params.get("model_name")
        if not isinstance(proposed_model, str) or not proposed_model.strip():
            return False
        current_model = training.get("model_name")
        return not _same_model_setting(current_model, proposed_model)

    if tool_name != "configure_training" or not all(
        field in params and params[field] is not None
        for field in REQUIRED_TRAINING_FIELDS
    ):
        return False
    if not training.get("has_training_option"):
        return True
    current_option = training.get("training_option")
    if not isinstance(current_option, dict):
        return True

    proposed = setting_confirmation_params(tool_name, params)
    if "model_name" in proposed and not _same_model_setting(
        training.get("model_name"),
        proposed["model_name"],
    ):
        return True
    current_fields = {
        "epoch": current_option.get("epoch"),
        "batch_size": current_option.get("batch_size"),
        "learning_rate": current_option.get("learning_rate"),
        "repeat": current_option.get("repeat"),
        "device": current_option.get("device"),
        "optimizer": current_option.get("optimizer"),
        "evaluation_option": current_option.get("evaluation_option"),
        "save_checkpoints_every": current_option.get("checkpoint_epoch"),
    }
    return any(
        not _same_training_setting(field, current_fields[field], proposed[field])
        for field in current_fields
    )


def _same_model_setting(current: object, proposed: object) -> bool:
    if not isinstance(current, str) or not isinstance(proposed, str):
        return False
    try:
        spec = get_model_spec(proposed)
    except (ImportError, ValueError):
        return current.strip().casefold() == proposed.strip().casefold()
    identities = {spec.model_id.casefold(), spec.display_name.casefold()}
    return current.strip().casefold() in identities


def _same_training_setting(field: str, current: object, proposed: object) -> bool:
    if field == "device":
        current_device = str(current or "").strip().casefold()
        proposed_device = str(proposed or "").strip().casefold()
        if proposed_device == "cuda":
            return current_device.startswith("cuda:")
        return current_device == proposed_device
    if field == "optimizer":
        return str(current or "").strip().casefold() == str(proposed).casefold()
    if field == "evaluation_option":
        aliases = {
            "best validation loss": "val_loss",
            "best validation auc": "val_auc",
            "best validation performance": "val_acc",
            "last epoch": "last_epoch",
        }
        current_value = str(current or "").strip().casefold()
        return aliases.get(current_value, current_value) == str(proposed).casefold()
    return current == proposed


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


_PUBLIC_TOOL_IDENTIFIER_MAX_BYTES = 1024
_PUBLIC_TOOL_MESSAGE_MAX_BYTES = 64 * 1024
_PUBLIC_TOOL_METADATA_MAX_BYTES = 4096


def _bounded_public_text(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    marker = PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER.encode("utf-8")
    prefix = encoded[: max(0, max_bytes - len(marker))].decode(
        "utf-8",
        errors="ignore",
    )
    return f"{prefix}{PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER}"


def _public_text_field(
    value: object,
    *,
    max_bytes: int,
    fallback: str,
    layout: DiagnosticTextLayout = DiagnosticTextLayout.SINGLE_LINE,
) -> str:
    if type(value) is not str:
        return fallback
    return _bounded_public_text(
        public_diagnostic_text(
            value,
            layout=layout,
        ),
        max_bytes,
    )


def _public_optional_text_field(
    value: object,
    *,
    max_bytes: int = _PUBLIC_TOOL_METADATA_MAX_BYTES,
) -> str | None:
    if value is None or type(value) is not str:
        return None
    return _public_text_field(value, max_bytes=max_bytes, fallback="")


def _public_mapping_field(
    value: object,
    *,
    none_allowed: bool,
) -> dict[str, Any] | None:
    if value is None and none_allowed:
        return None
    if type(value) is not dict:
        return None if none_allowed else {}
    projected = public_diagnostic_value(value)
    if type(projected) is not dict:
        return None if none_allowed else {}
    return projected


def _public_changed_state_field(value: object) -> dict[str, bool]:
    projected = _public_mapping_field(value, none_allowed=False)
    if type(projected) is not dict:
        return {}
    return {
        key: item
        for key, item in dict.items(projected)
        if type(key) is str and type(item) is bool
    }


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


def _serialized_public_payload_size(payload: dict[str, Any]) -> int:
    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _fit_public_tool_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if _serialized_public_payload_size(payload) <= PUBLIC_DIAGNOSTIC_MAX_OUTPUT_BYTES:
        return payload

    replacements: tuple[tuple[str, Any], ...] = (
        ("raw_result", PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER),
        ("diagnostics", {}),
        ("state", None),
        ("capability", None),
        ("changed_state", {}),
        ("blocked_reason", None),
    )
    for field_name, replacement in replacements:
        payload[field_name] = replacement
        if (
            _serialized_public_payload_size(payload)
            <= PUBLIC_DIAGNOSTIC_MAX_OUTPUT_BYTES
        ):
            return payload

    payload["message"] = _bounded_public_text(
        payload["message"],
        _PUBLIC_TOOL_METADATA_MAX_BYTES,
    )
    return payload


@dataclass(frozen=True)
class ToolCommandResult:
    """Agent-facing structured result for ApplicationService-backed tools."""

    ok: bool
    tool_name: str
    message: str
    command_name: str | None = None
    raw_result: Any = None
    error_type: str | None = None
    error_code: str | None = None
    recovery_action: str | None = None
    recoverable: bool = True
    blocked_reason: str | None = None
    state: dict[str, Any] | None = None
    capability: dict[str, Any] | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    changed_state: dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", self.ok if type(self.ok) is bool else False)
        object.__setattr__(
            self,
            "tool_name",
            _public_text_field(
                self.tool_name,
                max_bytes=_PUBLIC_TOOL_IDENTIFIER_MAX_BYTES,
                fallback=PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER,
            ),
        )
        object.__setattr__(
            self,
            "command_name",
            _public_optional_text_field(
                self.command_name,
                max_bytes=_PUBLIC_TOOL_IDENTIFIER_MAX_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "message",
            _public_text_field(
                self.message,
                max_bytes=_PUBLIC_TOOL_MESSAGE_MAX_BYTES,
                fallback=PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER,
                layout=DiagnosticTextLayout.PRESERVE_LINES,
            ),
        )
        for field_name in ("error_type", "error_code", "recovery_action"):
            object.__setattr__(
                self,
                field_name,
                _public_optional_text_field(getattr(self, field_name)),
            )
        object.__setattr__(
            self,
            "recoverable",
            self.recoverable if type(self.recoverable) is bool else False,
        )
        object.__setattr__(
            self,
            "blocked_reason",
            _public_optional_text_field(
                self.blocked_reason,
                max_bytes=_PUBLIC_TOOL_MESSAGE_MAX_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "changed_state",
            _public_changed_state_field(self.changed_state),
        )
        if self.ok is True:
            return
        projection = public_safe_result_projection(
            message=self.message,
            blocked_reason=self.blocked_reason,
        )
        object.__setattr__(self, "message", projection.message)
        object.__setattr__(self, "blocked_reason", projection.blocked_reason)

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
        diagnostics: dict[str, Any] | None = None,
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
            diagnostics=(dict.copy(diagnostics) if type(diagnostics) is dict else {}),
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
        error_code: str | None = None,
        recovery_action: str | None = None,
        recoverable: bool = True,
        diagnostics: dict[str, Any] | None = None,
        changed_state: dict[str, bool] | None = None,
    ) -> ToolCommandResult:
        """Build a failed structured tool result."""
        return cls(
            ok=False,
            tool_name=tool_name,
            command_name=command_name,
            message=message,
            raw_result=raw_result,
            error_type=error_type,
            error_code=error_code,
            recovery_action=recovery_action,
            recoverable=recoverable,
            state=state,
            capability=capability,
            diagnostics=(dict.copy(diagnostics) if type(diagnostics) is dict else {}),
            changed_state=(
                dict.copy(changed_state) if type(changed_state) is dict else {}
            ),
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
            state=(
                result.state.to_dict()
                if hasattr(result.state, "to_dict")
                else dict(result.state)
                if isinstance(result.state, dict)
                else None
            ),
            capability=capability,
            diagnostics=result.diagnostics,
            changed_state=result.changed_state.to_dict(),
        )

    @classmethod
    def from_tool_result(
        cls,
        tool_name: str,
        result: ToolResult,
        availability: ToolAvailability | None = None,
        state: dict[str, Any] | None = None,
    ) -> ToolCommandResult:
        """Convert an explicit non-ApplicationService tool result."""
        diagnostics = (
            dict.copy(result.diagnostics) if type(result.diagnostics) is dict else {}
        )
        if not diagnostics and type(result.payload) is dict:
            diagnostics = dict.copy(result.payload)
        return cls(
            ok=result.ok,
            tool_name=tool_name,
            command_name=result.command_name
            or (
                availability.command_name
                if availability
                else _command_name_for_tool(tool_name)
            ),
            message=result.message,
            raw_result=result.payload,
            error_type=result.error_type,
            error_code=result.error_code,
            recovery_action=result.recovery_action,
            recoverable=result.recoverable,
            blocked_reason=None if result.ok else result.message,
            state=result.state if result.state is not None else state,
            capability=(
                result.capability
                if result.capability is not None
                else availability.to_dict()
                if availability
                else None
            ),
            diagnostics=diagnostics,
            changed_state=(
                dict.copy(result.changed_state)
                if type(result.changed_state) is dict
                else {}
            ),
        )

    def to_payload(self) -> dict[str, Any]:
        """Return JSON-friendly payload for the next agent turn."""
        projection = public_safe_result_projection(
            message=self.message,
            blocked_reason=self.blocked_reason,
            raw_result=self.raw_result,
            state=self.state,
            capability=self.capability,
            diagnostics=self.diagnostics,
        )
        payload = {
            "ok": self.ok,
            "tool_name": self.tool_name,
            "command_name": self.command_name,
            "message": projection.message,
            "error_type": self.error_type,
            "error_code": self.error_code,
            "recovery_action": self.recovery_action,
            "recoverable": self.recoverable,
            "blocked_reason": projection.blocked_reason,
            "state": projection.state,
            "capability": projection.capability,
            "diagnostics": projection.diagnostics,
            "changed_state": self.changed_state,
            "raw_result": projection.raw_result,
        }
        safe_payload = public_diagnostic_value(payload)
        if type(safe_payload) is not dict:
            safe_payload = {}
        contract_payload: dict[str, Any] = {}
        for field_name, default in (
            ("ok", False),
            ("tool_name", PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER),
            ("command_name", None),
            ("message", PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER),
            ("error_type", None),
            ("error_code", None),
            ("recovery_action", None),
            ("recoverable", False),
            ("blocked_reason", None),
            ("state", None),
            ("capability", None),
            ("diagnostics", {}),
            ("changed_state", {}),
            ("raw_result", PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER),
        ):
            contract_payload[field_name] = dict.get(
                safe_payload,
                field_name,
                default,
            )
        return _fit_public_tool_payload(contract_payload)


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
) -> ToolCommandResult | UiRequest:
    """Convert a real tool return value into a structured agent result."""
    if type(raw_result) is ToolCommandResult:
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
    if type(raw_result) is CommandResult:
        return ToolCommandResult.from_command_result(
            tool_name,
            raw_result,
            capability=capability,
        )

    if type(raw_result) is not ToolResult:
        return ToolCommandResult.failure(
            tool_name,
            "The assistant tool returned an invalid result contract.",
            command_name=(
                availability.command_name
                if availability
                else _command_name_for_tool(tool_name)
            ),
            state=(
                state
                if state is not None
                else _state_snapshot_dict(study, runtime=runtime)
            ),
            capability=capability,
            error_type="contract",
            recoverable=False,
            diagnostics={"returned_type": _public_unsupported_result_type(raw_result)},
        )
    return ToolCommandResult.from_tool_result(
        tool_name,
        raw_result,
        availability=availability,
        state=(
            state if state is not None else _state_snapshot_dict(study, runtime=runtime)
        ),
    )


def execute_application_tool_command(
    study: Any,
    tool_name: str,
    params: dict[str, Any],
    availability: ToolAvailability | None = None,
    state: dict[str, Any] | None = None,
    *,
    runtime: ApplicationToolRuntime | None = None,
) -> ToolCommandResult | None:
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
        return ToolCommandResult.failure(
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
    setting_confirmation = command_params.pop(
        _ASSISTANT_SETTING_CONFIRMATION_PARAM,
        None,
    )
    setting_publication: ApplicationViewPublication | None = None
    if tool_name in _ASSISTANT_HIGH_IMPACT_SETTING_TOOLS:
        setting_publication = application_runtime.get_view_publication()
        state = setting_publication.state.to_dict()
        availability = _build_agent_tool_policy_from_publication(
            setting_publication
        ).get(tool_name)
    input_error: str | None = None
    try:
        command = _command_for_tool(tool_name, command_params, state=state)
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
            return ToolCommandResult.blocked(
                tool_name,
                availability,
                state=(
                    state
                    if state is not None
                    else _state_snapshot_dict(study, runtime=application_runtime)
                ),
            )

        return ToolCommandResult.failure(
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

    if setting_publication is not None:
        confirmation_matches = bool(
            type(setting_confirmation) is AssistantSettingConfirmation
            and setting_confirmation.matches(
                tool_name,
                command_params,
                setting_publication.generation,
            )
        )
        if (
            assistant_setting_change_requires_confirmation(
                tool_name,
                command_params,
                state,
            )
            and not confirmation_matches
        ):
            setting_availability = (
                replace(
                    availability,
                    confirmation_required=True,
                    requires_confirmation=True,
                    can_auto_execute=False,
                    decision_boundary="high_impact_setting_change",
                )
                if availability is not None
                else None
            )
            return ToolCommandResult.failure(
                tool_name,
                (
                    "Changing data splitting settings requires confirmation."
                    if tool_name == "configure_dataset_split"
                    else "Changing training settings requires confirmation."
                ),
                command_name=(
                    contract.capability_command.value
                    if contract.capability_command is not None
                    else None
                ),
                state=state,
                capability=(
                    setting_availability.to_dict()
                    if setting_availability is not None
                    else None
                ),
                error_type="confirmation_required",
                recoverable=True,
                diagnostics={"decision_boundary": "high_impact_setting_change"},
            )
        if confirmation_matches and tool_name == "configure_training":
            confirmed_command = _command_for_tool(
                tool_name,
                {
                    **command_params,
                    _ASSISTANT_SETTING_CONFIRMATION_PARAM: setting_confirmation,
                },
                state=state,
            )
            if confirmed_command is None:
                raise RuntimeError(
                    "Confirmed training settings could not be reconstructed."
                )
            command = confirmed_command

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
    return ToolCommandResult.from_command_result(
        tool_name,
        result,
        capability=result_availability.to_dict() if result_availability else None,
    )


def build_standard_preprocess_command(params: dict[str, Any]) -> PreprocessCommand:
    """Translate standard-preprocess tool arguments into one canonical command."""
    rereference = _optional_str(params.get("rereference"))
    return PreprocessCommand(
        operation=PreprocessOperation.STANDARD,
        low_freq=_optional_float(params.get("l_freq")),
        high_freq=_optional_float(params.get("h_freq")),
        notch_freq=_optional_float(params.get("notch_freq")),
        rate=_optional_int(params.get("resample_rate")),
        method=_optional_str(params.get("normalize_method")),
        channels=[rereference] if rereference is not None else None,
    )


def build_preview_interpretation_command(
    params: dict[str, Any],
) -> PreviewInterpretationCommand:
    """Translate preview arguments, including host-only resource consent."""
    choices = params.get("choices")
    return PreviewInterpretationCommand(
        scan_id=_optional_str(params.get("scan_id")),
        choices=dict(choices) if isinstance(choices, dict) else {},
        resource_preflight_confirmed=_boolean_param(
            params,
            "resource_preflight_confirmed",
        ),
        resource_preflight_token=_optional_str(params.get("resource_preflight_token")),
    )


def build_reload_interpretation_recipe_command(
    params: dict[str, Any],
) -> ReloadInterpretationRecipeCommand | None:
    """Translate recipe reload arguments through the canonical agent owner."""
    recipe_path = params.get("recipe_path")
    if not recipe_path:
        return None
    return ReloadInterpretationRecipeCommand(
        recipe_path=str(recipe_path),
        resource_preflight_confirmed=_boolean_param(
            params,
            "resource_preflight_confirmed",
        ),
        resource_preflight_token=_optional_str(params.get("resource_preflight_token")),
    )


def _command_for_tool(
    tool_name: str,
    params: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
) -> Command | None:
    """Build an ApplicationService command for a supported agent tool."""
    contract = AGENT_ACTION_CONTRACTS.contract_for(tool_name)
    if (
        contract is None
        or contract.execution_kind is not AgentExecutionKind.APPLICATION_COMMAND
    ):
        return None
    if tool_name == "scan_source":
        source_path = params.get("source_path")
        if not source_path:
            return None
        return ScanSourceCommand(
            source_path=str(source_path),
            source_hint=str(params.get("source_hint", "auto")),
            label_sources=[
                str(item)
                for item in params.get("label_sources", [])
                if str(item).strip()
            ]
            if isinstance(params.get("label_sources"), list)
            else [],
        )

    if tool_name == "preview_interpretation":
        return build_preview_interpretation_command(params)

    if tool_name == "validate_interpretation":
        return ValidateInterpretationCommand(
            candidate_id=_optional_str(params.get("candidate_id")),
        )

    if tool_name == "apply_interpretation":
        return ApplyInterpretationCommand(
            candidate_id=_optional_str(params.get("candidate_id")),
            confirmed=_boolean_param(params, "confirmed"),
            resource_preflight_confirmed=_boolean_param(
                params,
                "resource_preflight_confirmed",
            ),
            resource_preflight_token=_optional_str(
                params.get("resource_preflight_token")
            ),
        )

    if tool_name == "save_interpretation_recipe":
        return SaveInterpretationRecipeCommand(
            recipe_path=_optional_str(params.get("recipe_path")),
        )

    if tool_name == "reload_interpretation_recipe":
        return build_reload_interpretation_recipe_command(params)

    if tool_name == "apply_standard_preprocess":
        return build_standard_preprocess_command(params)

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

    if tool_name == "reset_preprocessing":
        return ResetPreprocessCommand(
            confirmed=_boolean_param(params, "confirmed"),
        )

    if tool_name == "clear_training_history":
        return ClearTrainingHistoryCommand(
            confirmed=_boolean_param(params, "confirmed"),
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

    if tool_name == "configure_dataset_split":
        split_strategy = params.get("split_strategy")
        training_mode = params.get("training_mode")
        if not split_strategy or not training_mode:
            return None
        preview_receipt = params.get("preview_receipt")
        if preview_receipt is not None and not isinstance(
            preview_receipt,
            DatasetSplitPreviewReceipt,
        ):
            return None
        return SaveDatasetSplitCommand(
            test_ratio=float(params.get("test_ratio", 0.2)),
            val_ratio=float(params.get("val_ratio", 0.2)),
            split_strategy=str(split_strategy),
            training_mode=str(training_mode),
            preview_receipt=preview_receipt,
        )

    if tool_name == "set_model":
        model_name = params.get("model_name")
        if not model_name:
            return None
        return ConfigureTrainingCommand(model_name=str(model_name))

    if tool_name == "configure_training":
        confirmation = params.get(_ASSISTANT_SETTING_CONFIRMATION_PARAM)
        edited_recommendation_fields = (
            frozenset(confirmation.edited_recommendation_fields)
            if isinstance(confirmation, AssistantSettingConfirmation)
            else frozenset()
        )
        training_input = normalize_training_input(params)
        output_dir_param = params.get("output_dir")
        if output_dir_param is not None and not isinstance(
            output_dir_param,
            UserProvidedTrainingOutputDir,
        ):
            return None
        if isinstance(output_dir_param, UserProvidedTrainingOutputDir):
            if not output_dir_param.strip():
                return None
            output_dir = str(output_dir_param)
        else:
            current = start_training_confirmation_truth(state)
            output_dir = (
                current.output_directory
                if current is not None
                else ConfigureTrainingCommand().output_dir
            )
        command = ConfigureTrainingCommand(
            model_name=_optional_str(params.get("model_name")),
            epoch=training_input.epoch,
            batch_size=training_input.batch_size,
            learning_rate=training_input.learning_rate,
            repeat=normalize_positive_integer("repeat", params.get("repeat", 1)),
            device=str(params.get("device", "cpu")),
            optimizer=str(params.get("optimizer", "adam")),
            evaluation_option=str(params.get("evaluation_option", "last_epoch")),
            save_checkpoints_every=normalize_non_negative_integer(
                "save_checkpoints_every",
                params.get("save_checkpoints_every", 0),
            ),
            output_dir=str(output_dir),
        )
        return attach_training_submission_provenance(
            command,
            edited_recommendation_fields,
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

    if tool_name == "evaluate":
        return EvaluateCommand(target=_optional_str(params.get("target")))

    if tool_name == "visualize":
        return VisualizeCommand(view=_optional_str(params.get("view")))

    if tool_name == "saliency":
        nested_saliency_params = params.get("params")
        saliency_params = (
            dict(nested_saliency_params)
            if isinstance(nested_saliency_params, dict)
            else {}
        )
        for parameter_name in (
            "nt_samples",
            "nt_samples_batch_size",
            "stdevs",
        ):
            if parameter_name in params:
                saliency_params[parameter_name] = params[parameter_name]
        return SaliencyCommand(
            method=_optional_str(params.get("method")),
            params=saliency_params or None,
            resource_preflight_confirmed=_boolean_param(
                params,
                "resource_preflight_confirmed",
            ),
            resource_preflight_token=_optional_str(
                params.get("resource_preflight_token")
            ),
        )

    if tool_name == "query_state":
        return QueryStateCommand(
            query=str(params.get("query", "state")),
            params=dict(params.get("params", {}))
            if isinstance(params.get("params"), dict)
            else {},
        )

    return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _optional_str_list(value: Any) -> list[str] | None:
    if not isinstance(value, (list, tuple)):
        return None
    normalized = [str(item).strip() for item in value if str(item).strip()]
    return list(dict.fromkeys(normalized)) or None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _boolean_param(
    params: dict[str, Any],
    name: str,
    *,
    default: bool = False,
) -> bool:
    return normalize_strict_boolean(name, params.get(name, default))


def enabled_tool_names(
    study: Any,
    *,
    publication: ApplicationViewPublication | None = None,
    runtime: ApplicationToolRuntime | None = None,
) -> list[str]:
    """Return tool names that are currently available to the agent."""
    return [
        tool_name
        for tool_name, availability in build_agent_tool_policy(
            study,
            publication=publication,
            runtime=runtime,
        ).items()
        if availability.enabled
    ]


def blocked_tool_reasons(
    study: Any,
    *,
    publication: ApplicationViewPublication | None = None,
    runtime: ApplicationToolRuntime | None = None,
) -> dict[str, str]:
    """Return blocked tool names and reasons for prompt diagnostics."""
    return {
        _blocked_prompt_name(availability): availability.reason_text
        for availability in build_agent_tool_policy(
            study,
            publication=publication,
            runtime=runtime,
        ).values()
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
