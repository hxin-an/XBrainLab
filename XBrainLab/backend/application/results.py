"""Result envelopes returned by the backend application service."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from .serialization import serialize_json_value, split_runtime_fields


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
    runtime: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        safe_diagnostics, extracted_runtime = split_runtime_fields(self.diagnostics)
        object.__setattr__(self, "diagnostics", safe_diagnostics)
        object.__setattr__(
            self,
            "runtime",
            {**extracted_runtime, **self.runtime},
        )

    @property
    def success(self) -> bool:
        return self.status == CommandStatus.OK

    @property
    def ok(self) -> bool:
        return self.success

    @property
    def failed(self) -> bool:
        return self.status == CommandStatus.FAILED

    @property
    def local_payload(self) -> dict[str, Any]:
        """Return diagnostics plus process-local UI references."""
        return {**self.diagnostics, **self.runtime}

    @classmethod
    def success_result(
        cls,
        command_name: str,
        message: str,
        state: Any,
        changed_state: ChangedState,
        diagnostics: dict[str, Any] | None = None,
        runtime: dict[str, Any] | None = None,
    ) -> CommandResult:
        return cls(
            status=CommandStatus.OK,
            command_name=command_name,
            message=message,
            state=state,
            changed_state=changed_state,
            diagnostics=diagnostics or {},
            runtime=runtime or {},
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
        runtime: dict[str, Any] | None = None,
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
            runtime=runtime or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return serialize_json_value(
            {
                "status": self.status,
                "command_name": self.command_name,
                "message": self.message,
                "state": self.state,
                "changed_state": self.changed_state,
                "error_type": self.error_type,
                "recoverable": self.recoverable,
                "error_message": self.error_message,
                "diagnostics": self.diagnostics,
            },
        )
