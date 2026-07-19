"""Custom exception classes for the XBrainLab backend."""


class XBrainLabError(Exception):
    """Base class for exceptions in XBrainLab."""


class FileCorruptedError(XBrainLabError):
    """Exception raised when a file is corrupted or cannot be read.

    Attributes:
        filepath: Path to the corrupted file.
        message: Human-readable error message.

    """

    def __init__(self, filepath, message="File is corrupted or unreadable"):
        self.filepath = filepath
        self.message = f"{message}: {filepath}"
        super().__init__(self.message)


class UnsupportedFormatError(XBrainLabError):
    """Exception raised when a file format is not supported.

    Attributes:
        file_extension: The unsupported file extension.
        message: Human-readable error message.

    """

    def __init__(self, file_extension, message="Unsupported file format"):
        self.file_extension = file_extension
        self.message = f"{message}: {file_extension}"
        super().__init__(self.message)


class DataMismatchError(XBrainLabError):
    """Exception raised when data parameters (e.g., sfreq) do not match.

    Attributes:
        message: Human-readable error message.

    """

    def __init__(self, message="Data parameters mismatch"):
        self.message = message
        super().__init__(self.message)


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
