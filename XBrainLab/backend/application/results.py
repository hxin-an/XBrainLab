"""Result envelopes returned by the backend application service."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, cast


class CommandStatus(str, Enum):
    """Execution status for an application command."""

    OK = "ok"
    FAILED = "failed"


class ErrorType(str, Enum):
    """Serializable error categories for command failures."""

    NONE = "none"
    PRECONDITION = "precondition"
    CONFIRMATION_REQUIRED = "confirmation_required"
    VALIDATION = "validation"
    UNSUPPORTED_FORMAT = "unsupported_format"
    FILE_CORRUPTED = "file_corrupted"
    DATA_MISMATCH = "data_mismatch"
    PREPROCESSING = "preprocessing"
    TRAINING = "training"
    EVALUATION = "evaluation"
    VISUALIZATION = "visualization"
    UNSUPPORTED_COMMAND = "unsupported_command"
    RUNTIME = "runtime"
    INTERNAL = "internal"


@dataclass(frozen=True)
class ChangedState:
    """Summary of state changes produced by a command."""

    raw_changed: bool = False
    preprocessed_changed: bool = False
    epoch_changed: bool = False
    datasets_changed: bool = False
    training_changed: bool = False
    evaluation_changed: bool = False
    visualization_changed: bool = False
    interpretation_changed: bool = False
    error_changed: bool = False

    def any_changed(self) -> bool:
        """Return whether any tracked state area changed."""
        return any(self.to_dict().values())

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True)
class CommandResult:
    """Serializable command result with before/after state details."""

    status: CommandStatus
    command_name: str
    message: str
    state: Any
    changed_state: ChangedState
    error_type: ErrorType = ErrorType.NONE
    recoverable: bool = True
    error_message: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == CommandStatus.OK

    @property
    def ok(self) -> bool:
        return self.success

    @property
    def failed(self) -> bool:
        return self.status == CommandStatus.FAILED

    @classmethod
    def success_result(
        cls,
        command_name: str,
        message: str,
        state: Any,
        changed_state: ChangedState,
        diagnostics: dict[str, Any] | None = None,
    ) -> CommandResult:
        return cls(
            status=CommandStatus.OK,
            command_name=command_name,
            message=message,
            state=state,
            changed_state=changed_state,
            diagnostics=diagnostics or {},
        )

    @classmethod
    def failure_result(
        cls,
        command_name: str,
        message: str,
        state: Any,
        changed_state: ChangedState,
        error_type: ErrorType,
        recoverable: bool,
        error_message: str | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> CommandResult:
        return cls(
            status=CommandStatus.FAILED,
            command_name=command_name,
            message=message,
            state=state,
            changed_state=changed_state,
            error_type=error_type,
            recoverable=recoverable,
            error_message=error_message or message,
            diagnostics=diagnostics or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {k: _serialize(v) for k, v in asdict(cast(Any, value)).items()}
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value
