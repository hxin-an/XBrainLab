from functools import wraps

from XBrainLab.backend.utils.logger import logger


class XBrainLabError(Exception):
    """Base exception for XBrainLab application."""


class DataNotLoadedError(XBrainLabError):
    """Raised when an operation requires data but none is loaded."""


class PreprocessingError(XBrainLabError):
    """Raised when a preprocessing step fails."""


class AgentError(XBrainLabError):
    """Raised when an Agent operation fails."""


def handle_error(func):
    """
    Decorator: Unified error handling mechanism.
    Intercepts XBrainLabError and logs it;
    Intercepts unexpected Exceptions and converts them to XBrainLabError.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except XBrainLabError as e:
            logger.error(f"XBrainLab Error in {func.__name__}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected Error in {func.__name__}: {e}")
            raise XBrainLabError(f"Unexpected error: {e!s}") from e

    return wrapper
