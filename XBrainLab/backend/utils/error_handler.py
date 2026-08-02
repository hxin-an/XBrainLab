"""Custom exception classes and error handling decorator for XBrainLab."""

from functools import wraps
from typing import Any, cast

from XBrainLab.backend.exceptions import XBrainLabError
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.public_diagnostics import (
    DiagnosticTextLayout,
    public_diagnostic_text,
)


class DataNotLoadedError(XBrainLabError):
    """Raised when an operation requires data that has not been loaded yet."""


class PreprocessingError(XBrainLabError):
    """Raised when a preprocessing step fails."""


class AgentError(XBrainLabError):
    """Raised when an Agent operation fails."""


def handle_error(func):
    """Decorator providing unified error handling for XBrainLab functions.

    Intercepts :class:`XBrainLabError` and logs it. Catches unexpected
    exceptions and wraps them in :class:`XBrainLabError` before re-raising.

    Args:
        func: The function to wrap with error handling.

    Returns:
        The wrapped function with error logging and conversion.

    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except XBrainLabError:
            logger.error("XBrainLab Error in %s", func.__name__)
            raise
        except Exception as e:
            raw_message = _raw_exception_message(e)
            logger.error(
                "Unexpected Error in %s: %s",
                func.__name__,
                public_diagnostic_text(
                    raw_message,
                    layout=DiagnosticTextLayout.SINGLE_LINE,
                ),
            )
            raise XBrainLabError(f"Unexpected error: {raw_message}") from None

    return wrapper


def _raw_exception_message(error: Exception) -> str:
    storage = _safe_exception_storage(error)
    message = dict.get(storage, "message") if storage is not None else None
    if type(message) is str:
        return message
    try:
        args = cast(Any, BaseException.args).__get__(error, type(error))
    except BaseException:
        args = ()
    if type(args) is tuple and len(args) == 1 and type(args[0]) is str:
        return args[0]
    return "An unexpected error occurred."


def _safe_exception_storage(error: BaseException) -> dict[str, Any] | None:
    try:
        storage = object.__getattribute__(error, "__dict__")
    except BaseException:
        return None
    return storage if type(storage) is dict else None
