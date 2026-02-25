"""Custom exception classes and error handling decorator for XBrainLab."""

from functools import wraps

from XBrainLab.backend.exceptions import XBrainLabError
from XBrainLab.backend.utils.logger import logger


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
        except XBrainLabError as e:
            logger.error("XBrainLab Error in %s: %s", func.__name__, e)
            raise
        except Exception as e:
            logger.exception("Unexpected Error in %s: %s", func.__name__, e)
            raise XBrainLabError(f"Unexpected error: {e!s}") from e

    return wrapper
