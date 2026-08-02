"""Application-level errors and exception mapping helpers."""

from __future__ import annotations

import builtins
from dataclasses import dataclass, field
from typing import Any, cast

from XBrainLab.backend.exceptions import (
    DataMismatchError,
    FileCorruptedError,
    SaliencyCancellationTimeoutError,
    SaliencyRecomputationResourceError,
    StaleSaliencyUpdateError,
    UnsupportedFormatError,
    XBrainLabError,
)
from XBrainLab.backend.services.label_import_errors import AtomicLabelApplyError
from XBrainLab.backend.utils.public_diagnostics import (
    PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER,
    public_diagnostic_text,
)

from .results import ErrorType

SAFE_INTERNAL_ERROR_MESSAGE = "An unexpected application error occurred."
_SAFE_BUILTIN_EXCEPTION_TYPES = frozenset(
    value
    for value in vars(builtins).values()
    if type(value) is type and issubclass(value, Exception)
)


@dataclass
class ApplicationError(Exception):
    """Base recoverable application error."""

    message: str
    error_type: ErrorType = ErrorType.RUNTIME
    recoverable: bool = True
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.message) is not str:
            self.message = PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER
        if type(self.error_type) is not ErrorType:
            self.error_type = ErrorType.INTERNAL
        if type(self.recoverable) is not bool:
            self.recoverable = False
        if type(self.diagnostics) is not dict:
            self.diagnostics = {}
        else:
            self.diagnostics = dict.copy(self.diagnostics)
        Exception.__init__(self, self.message)

    def __str__(self) -> str:
        return public_diagnostic_text(self.message)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str(self)!r})"


class PreconditionError(ApplicationError):
    """Raised when a command cannot run in the current state."""

    def __init__(
        self,
        message: str,
        recoverable: bool = True,
        diagnostics: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            error_type=ErrorType.PRECONDITION,
            recoverable=recoverable,
            diagnostics=(dict.copy(diagnostics) if type(diagnostics) is dict else {}),
        )


class ConfirmationRequiredError(ApplicationError):
    """Raised when a destructive command needs explicit confirmation."""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            error_type=ErrorType.CONFIRMATION_REQUIRED,
            recoverable=True,
        )


def map_exception(exc: Exception) -> ApplicationError:
    """Convert arbitrary exceptions to an application error."""
    if isinstance(exc, ApplicationError):
        return _copy_application_error(exc)
    if type(exc) is AtomicLabelApplyError:
        return ApplicationError(
            message=exc.user_message,
            error_type=ErrorType.VALIDATION,
            recoverable=exc.recoverable,
            diagnostics={
                "code": exc.error_code,
                "phase": exc.phase,
                "state_preserved": not exc.state_unknown,
            },
        )
    if type(exc) is UnsupportedFormatError:
        return ApplicationError(
            message=_raw_exception_message(exc),
            error_type=ErrorType.UNSUPPORTED_FORMAT,
            recoverable=True,
        )
    if type(exc) is FileCorruptedError:
        return ApplicationError(
            message=_raw_exception_message(exc),
            error_type=ErrorType.FILE_CORRUPTED,
            recoverable=True,
        )
    if type(exc) is DataMismatchError:
        return ApplicationError(
            message=_raw_exception_message(exc),
            error_type=ErrorType.DATA_MISMATCH,
            recoverable=True,
        )
    if type(exc) is StaleSaliencyUpdateError:
        return ApplicationError(
            message=_raw_exception_message(exc),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            diagnostics={
                "retryable": True,
                "stale_saliency_update": True,
                "state_preserved": True,
            },
        )
    if type(exc) is SaliencyRecomputationResourceError:
        return ApplicationError(
            message=_raw_exception_message(exc),
            error_type=ErrorType.VISUALIZATION,
            recoverable=True,
            diagnostics={
                "retryable": True,
                "resource": "cuda_memory",
                "operation": "saliency_recomputation",
                "state_preserved": True,
            },
        )
    if type(exc) is SaliencyCancellationTimeoutError:
        return ApplicationError(
            message=_raw_exception_message(exc),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            diagnostics={
                "retryable": True,
                "operation": "saliency_cancellation",
                "state_preserved": True,
            },
        )
    if type(exc) is XBrainLabError:
        return ApplicationError(
            message=_raw_exception_message(exc),
            error_type=ErrorType.INTERNAL,
            recoverable=False,
        )
    if type(exc) in {TypeError, ValueError}:
        message = _raw_exception_message(exc)
        if "No data" in message or "No valid" in message or "required" in message:
            return ApplicationError(
                message=message,
                error_type=ErrorType.PRECONDITION,
                recoverable=True,
            )
        return ApplicationError(
            message=message,
            error_type=ErrorType.VALIDATION,
            recoverable=True,
        )
    return ApplicationError(
        message=_raw_exception_message(exc),
        error_type=ErrorType.INTERNAL,
        recoverable=False,
    )


def _raw_exception_message(exc: Exception) -> str:
    if isinstance(exc, XBrainLabError):
        storage = _safe_exception_storage(exc)
        message = dict.get(storage, "message") if storage is not None else None
        return message if type(message) is str else SAFE_INTERNAL_ERROR_MESSAGE
    if type(exc) in _SAFE_BUILTIN_EXCEPTION_TYPES:
        args = cast(Any, BaseException.args).__get__(exc, type(exc))
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str:
            return args[0]
    return SAFE_INTERNAL_ERROR_MESSAGE


def _copy_application_error(exc: ApplicationError) -> ApplicationError:
    storage = _safe_exception_storage(exc)
    if storage is None:
        return ApplicationError(
            message=SAFE_INTERNAL_ERROR_MESSAGE,
            error_type=ErrorType.INTERNAL,
            recoverable=False,
        )
    message = dict.get(storage, "message")
    error_type = dict.get(storage, "error_type")
    recoverable = dict.get(storage, "recoverable")
    diagnostics = dict.get(storage, "diagnostics")
    return ApplicationError(
        message=message if type(message) is str else SAFE_INTERNAL_ERROR_MESSAGE,
        error_type=error_type if type(error_type) is ErrorType else ErrorType.INTERNAL,
        recoverable=recoverable if type(recoverable) is bool else False,
        diagnostics=dict.copy(diagnostics) if type(diagnostics) is dict else {},
    )


def _safe_exception_storage(exc: BaseException) -> dict[str, Any] | None:
    try:
        storage = object.__getattribute__(exc, "__dict__")
    except BaseException:
        return None
    return storage if type(storage) is dict else None
