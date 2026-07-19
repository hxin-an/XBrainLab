"""Application-level errors and exception mapping helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from XBrainLab.backend.exceptions import (
    DataMismatchError,
    FileCorruptedError,
    SaliencyCancellationTimeoutError,
    SaliencyRecomputationResourceError,
    StaleSaliencyUpdateError,
    UnsupportedFormatError,
)

from .results import ErrorType


@dataclass
class ApplicationError(Exception):
    """Base recoverable application error."""

    message: str
    error_type: ErrorType = ErrorType.RUNTIME
    recoverable: bool = True
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


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
            diagnostics=dict(diagnostics or {}),
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
        return exc
    if isinstance(exc, UnsupportedFormatError):
        return ApplicationError(
            message=str(exc),
            error_type=ErrorType.UNSUPPORTED_FORMAT,
            recoverable=True,
        )
    if isinstance(exc, FileCorruptedError):
        return ApplicationError(
            message=str(exc),
            error_type=ErrorType.FILE_CORRUPTED,
            recoverable=True,
        )
    if isinstance(exc, DataMismatchError):
        return ApplicationError(
            message=str(exc),
            error_type=ErrorType.DATA_MISMATCH,
            recoverable=True,
        )
    if isinstance(exc, StaleSaliencyUpdateError):
        return ApplicationError(
            message=str(exc),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            diagnostics={
                "retryable": True,
                "stale_saliency_update": True,
                "state_preserved": True,
            },
        )
    if isinstance(exc, SaliencyRecomputationResourceError):
        return ApplicationError(
            message=str(exc),
            error_type=ErrorType.VISUALIZATION,
            recoverable=True,
            diagnostics={
                "retryable": True,
                "resource": "cuda_memory",
                "operation": "saliency_recomputation",
                "state_preserved": True,
            },
        )
    if isinstance(exc, SaliencyCancellationTimeoutError):
        return ApplicationError(
            message=str(exc),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            diagnostics={
                "retryable": True,
                "operation": "saliency_cancellation",
                "state_preserved": True,
            },
        )
    if isinstance(exc, (TypeError, ValueError)):
        message = str(exc)
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
        message=str(exc),
        error_type=ErrorType.INTERNAL,
        recoverable=False,
    )
