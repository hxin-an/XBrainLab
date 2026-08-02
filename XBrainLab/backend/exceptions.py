"""Custom exception classes for the XBrainLab backend."""

import os
from pathlib import PosixPath, PurePosixPath, PureWindowsPath, WindowsPath
from typing import cast

from XBrainLab.backend.utils.public_diagnostics import (
    PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER,
    DiagnosticTextLayout,
    public_diagnostic_text,
)

_SAFE_PATH_TYPES = (PosixPath, WindowsPath, PurePosixPath, PureWindowsPath)


class XBrainLabError(Exception):
    """Base class for exceptions in XBrainLab."""

    def __init__(self, message: object = "") -> None:
        self.message = _safe_exception_component(message)
        super().__init__(self.message)

    def __str__(self) -> str:
        return public_diagnostic_text(
            self.message,
            layout=DiagnosticTextLayout.SINGLE_LINE,
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str(self)!r})"


class FileCorruptedError(XBrainLabError):
    """Exception raised when a file is corrupted or cannot be read.

    Attributes:
        filepath: Path to the corrupted file.
        message: Human-readable error message.

    """

    def __init__(
        self,
        filepath: object,
        message: object = "File is corrupted or unreadable",
    ):
        self.filepath = filepath
        self.message = (
            f"{_safe_exception_component(message)}: "
            f"{_safe_exception_component(filepath)}"
        )
        super().__init__(self.message)


class UnsupportedFormatError(XBrainLabError):
    """Exception raised when a file format is not supported.

    Attributes:
        file_extension: The unsupported file extension.
        message: Human-readable error message.

    """

    def __init__(
        self,
        file_extension: object,
        message: object = "Unsupported file format",
    ):
        self.file_extension = file_extension
        self.message = (
            f"{_safe_exception_component(message)}: "
            f"{_safe_exception_component(file_extension)}"
        )
        super().__init__(self.message)


class DataMismatchError(XBrainLabError):
    """Exception raised when data parameters (e.g., sfreq) do not match.

    Attributes:
        message: Human-readable error message.

    """

    def __init__(self, message: object = "Data parameters mismatch"):
        self.message = _safe_exception_component(message)
        super().__init__(self.message)


def _safe_exception_component(value: object) -> str:
    if type(value) is str:
        return value
    if type(value) in _SAFE_PATH_TYPES:
        path = os.fspath(cast(os.PathLike[str] | os.PathLike[bytes], value))
        if type(path) is str:
            return path
        if type(path) is bytes:
            return path.decode("utf-8", errors="replace")
    return PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER


class StaleSaliencyUpdateError(XBrainLabError):
    """Raised when prepared saliency results no longer match shared state."""

    def __init__(self) -> None:
        super().__init__(
            "Training or evaluation state changed during saliency recomputation. "
            "No saliency changes were applied; retry after training is idle."
        )


class SaliencyRecomputationResourceError(XBrainLabError):
    """Raised when saliency recomputation exhausts CUDA memory."""

    def __init__(self) -> None:
        super().__init__(
            "Not enough GPU memory to recompute saliency. Existing evaluation "
            "results were kept. Reduce the selected saliency methods or sample "
            "count, then retry."
        )


class SaliencyCancellationTimeoutError(XBrainLabError):
    """Raised when an attribution backend ignores a saliency cancel request."""

    def __init__(self) -> None:
        super().__init__(
            "The previous saliency calculation is still stopping. No new "
            "training or saliency work was started. Wait briefly and retry."
        )


class StaleTrainingPipelineMutationError(XBrainLabError):
    """Raised when training truth changes before a pipeline mutation commits."""

    def __init__(self) -> None:
        super().__init__(
            "Training or saliency state changed while the data pipeline was being "
            "prepared. No training history was removed; retry when background work "
            "is idle."
        )
