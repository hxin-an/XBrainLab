"""Result envelopes returned by the backend application service."""

from __future__ import annotations

import math
import os
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import PosixPath, PurePosixPath, PureWindowsPath, WindowsPath
from typing import Any, cast

from XBrainLab.backend.utils.public_diagnostics import (
    PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER,
    public_diagnostic_text,
    public_diagnostic_value,
)

from .state import ApplicationStateSnapshot

_UNSAFE_VALUE = object()
_SAFE_PATH_TYPES = (PosixPath, WindowsPath, PurePosixPath, PureWindowsPath)


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
    state_unknown: bool = False

    def any_changed(self) -> bool:
        """Return whether any tracked state area changed."""
        return any(self.to_dict().values())

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True)
class CommandResult:
    """Detached JSON-safe command result with before/after state details."""

    status: CommandStatus
    command_name: str
    message: str
    state: Any
    changed_state: ChangedState
    error_type: ErrorType = ErrorType.NONE
    recoverable: bool = True
    error_message: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.status) is not CommandStatus:
            object.__setattr__(self, "status", CommandStatus.FAILED)
        if type(self.command_name) is not str:
            object.__setattr__(
                self,
                "command_name",
                PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER,
            )
        object.__setattr__(self, "message", public_diagnostic_text(self.message))
        if self.error_message is not None:
            object.__setattr__(
                self,
                "error_message",
                public_diagnostic_text(self.error_message),
            )
        if type(self.changed_state) is not ChangedState:
            object.__setattr__(
                self,
                "changed_state",
                ChangedState(error_changed=True, state_unknown=True),
            )
        if type(self.error_type) is not ErrorType:
            object.__setattr__(self, "error_type", ErrorType.INTERNAL)
        if type(self.recoverable) is not bool:
            object.__setattr__(self, "recoverable", False)
        object.__setattr__(self, "state", _copy_result_state(self.state))
        object.__setattr__(
            self,
            "diagnostics",
            _copy_json_diagnostic_fields(self.diagnostics),
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
            diagnostics=diagnostics if type(diagnostics) is dict else {},
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
            error_message=error_message if type(error_message) is str else message,
            diagnostics=diagnostics if type(diagnostics) is dict else {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the public-safe JSON contract for compatibility callers."""
        return self.to_public_dict()

    def to_internal_dict(self) -> dict[str, Any]:
        """Return the unredacted, detached JSON-safe result projection."""
        return {
            "status": self.status.value,
            "command_name": self.command_name,
            "message": self.message,
            "state": _serialize_result_state(self.state),
            "changed_state": self.changed_state.to_dict(),
            "error_type": self.error_type.value,
            "recoverable": self.recoverable,
            "error_message": self.error_message,
            "diagnostics": _clone_exact_json_value(self.diagnostics),
        }

    def to_public_dict(self) -> dict[str, Any]:
        """Serialize the fixed public-safe command-result projection."""
        projected = public_diagnostic_value(self.to_internal_dict())
        if type(projected) is dict and "status" in projected:
            return projected
        return {
            "status": self.status.value,
            "command_name": self.command_name,
            "message": PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER,
            "state": {},
            "changed_state": ChangedState(
                error_changed=True,
                state_unknown=True,
            ).to_dict(),
            "error_type": ErrorType.INTERNAL.value,
            "recoverable": False,
            "error_message": PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER,
            "diagnostics": {"truncated": True},
        }


def _copy_result_state(value: Any) -> Any:
    if type(value) is ApplicationStateSnapshot:
        return deepcopy(value)
    cloned = _clone_exact_json_value(value)
    return cloned if cloned is not _UNSAFE_VALUE else {}


def _serialize_result_state(value: Any) -> Any:
    if type(value) is ApplicationStateSnapshot:
        return value.to_dict()
    cloned = _clone_exact_json_value(value)
    return cloned if cloned is not _UNSAFE_VALUE else {}


def _copy_json_diagnostic_fields(values: Any) -> dict[str, Any]:
    if type(values) is not dict:
        return {}
    diagnostics: dict[str, Any] = {}
    for key, value in dict.items(values):
        public_key = _exact_mapping_key(key)
        if public_key is None:
            continue
        cloned = _clone_exact_json_value(value)
        if cloned is not _UNSAFE_VALUE:
            diagnostics[public_key] = cloned
    return diagnostics


def _clone_exact_json_value(
    value: Any,
    *,
    _active: set[int] | None = None,
    _depth: int = 0,
) -> Any:
    value_type = type(value)
    if value_type is float:
        numeric_value = cast(float, value)
        return numeric_value if math.isfinite(numeric_value) else _UNSAFE_VALUE
    if value is None or value_type in {str, bool, int}:
        return value
    if value_type in _SAFE_PATH_TYPES:
        path = os.fspath(cast(os.PathLike[str] | os.PathLike[bytes], value))
        return os.fsdecode(path)
    if value_type not in {dict, list, tuple} or _depth >= 32:
        return _UNSAFE_VALUE

    container = cast(dict[Any, Any] | list[Any] | tuple[Any, ...], value)
    active = _active if _active is not None else set()
    identity = id(container)
    if identity in active:
        return _UNSAFE_VALUE
    active.add(identity)
    try:
        if value_type is dict:
            cloned_mapping: dict[str, Any] = {}
            for key, item in dict.items(cast(dict[Any, Any], container)):
                public_key = _exact_mapping_key(key)
                if public_key is None:
                    return _UNSAFE_VALUE
                cloned_item = _clone_exact_json_value(
                    item,
                    _active=active,
                    _depth=_depth + 1,
                )
                if cloned_item is _UNSAFE_VALUE:
                    return _UNSAFE_VALUE
                cloned_mapping[public_key] = cloned_item
            return cloned_mapping

        cloned_items: list[Any] = []
        for item in cast(list[Any] | tuple[Any, ...], container):
            cloned_item = _clone_exact_json_value(
                item,
                _active=active,
                _depth=_depth + 1,
            )
            if cloned_item is _UNSAFE_VALUE:
                return _UNSAFE_VALUE
            cloned_items.append(cloned_item)
        return cloned_items
    finally:
        active.remove(identity)


def _exact_mapping_key(value: Any) -> str | None:
    if type(value) is str:
        return value
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) in {int, float}:
        try:
            rendered = str(value)
        except (OverflowError, ValueError):
            return None
        return rendered if len(rendered) <= 4096 else None
    return None
