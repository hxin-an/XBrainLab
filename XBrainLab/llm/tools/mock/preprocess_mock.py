"""Mock implementations of EEG preprocessing tools.

Return canned success/error strings without modifying any data,
enabling offline agent testing and development.
"""

from typing import Any

from ..definitions.preprocess_def import (
    BaseBandPassFilterTool,
    BaseChannelSelectionTool,
    BaseEpochDataTool,
    BaseNormalizeTool,
    BaseNotchFilterTool,
    BaseRereferenceTool,
    BaseResampleTool,
    BaseSetMontageTool,
    BaseStandardPreprocessTool,
)


class MockStandardPreprocessTool(BaseStandardPreprocessTool):
    """Mock implementation of :class:`BaseStandardPreprocessTool`."""

    def execute(
        self,
        study: Any,
        l_freq: float = 4.0,
        h_freq: float = 40.0,
        notch_freq: float = 50.0,
        rereference: str | None = None,
        resample_rate: int | None = None,
        normalize_method: str | None = None,
        **kwargs,
    ) -> str:
        """Return a simulated standard-preprocessing result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            l_freq: Lower bandpass frequency in Hz.
            h_freq: Upper bandpass frequency in Hz.
            notch_freq: Notch filter frequency in Hz.
            rereference: Re-reference method name.
            resample_rate: Target sampling rate in Hz.
            normalize_method: Normalisation method name.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation message summarising the pipeline.
        """
        return (
            f"Applied standard preprocessing pipeline (BP: {l_freq}-{h_freq}Hz, "
            f"Notch: {notch_freq}Hz)."
        )


class MockBandPassFilterTool(BaseBandPassFilterTool):
    """Mock implementation of :class:`BaseBandPassFilterTool`."""

    def execute(
        self,
        study: Any,
        low_freq: float | None = None,
        high_freq: float | None = None,
        **kwargs,
    ) -> str:
        """Return a simulated bandpass-filter result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            low_freq: Lower cutoff frequency in Hz.
            high_freq: Upper cutoff frequency in Hz.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.
        """
        if low_freq is None or high_freq is None:
            return "Error: frequencies are required"
        return f"Applied bandpass filter ({low_freq}-{high_freq} Hz)."


class MockNotchFilterTool(BaseNotchFilterTool):
    """Mock implementation of :class:`BaseNotchFilterTool`."""

    def execute(self, study: Any, freq: float | None = None, **kwargs) -> str:
        """Return a simulated notch-filter result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            freq: Notch frequency in Hz.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.
        """
        if freq is None:
            return "Error: frequency is required"
        return f"Applied notch filter at {freq} Hz."


class MockResampleTool(BaseResampleTool):
    """Mock implementation of :class:`BaseResampleTool`."""

    def execute(self, study: Any, rate: int | None = None, **kwargs) -> str:
        """Return a simulated resample result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            rate: Target sampling rate in Hz.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.
        """
        if rate is None:
            return "Error: rate is required"
        return f"Resampled data to {rate} Hz."


class MockNormalizeTool(BaseNormalizeTool):
    """Mock implementation of :class:`BaseNormalizeTool`."""

    def execute(self, study: Any, method: str | None = None, **kwargs) -> str:
        """Return a simulated normalisation result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            method: Normalisation method (``'z-score'`` or ``'min-max'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.
        """
        if method is None:
            return "Error: method is required"
        return f"Normalized data using {method} method."


class MockRereferenceTool(BaseRereferenceTool):
    """Mock implementation of :class:`BaseRereferenceTool`."""

    def execute(self, study: Any, method: str | None = None, **kwargs) -> str:
        """Return a simulated re-reference result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            method: Reference method name.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.
        """
        if method is None:
            return "Error: method is required"
        return f"Re-referenced data to {method}."


class MockChannelSelectionTool(BaseChannelSelectionTool):
    """Mock implementation of :class:`BaseChannelSelectionTool`."""

    def execute(self, study: Any, channels: list[str] | None = None, **kwargs) -> str:
        """Return a simulated channel-selection result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            channels: List of channel names to keep.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.
        """
        if channels is None:
            return "Error: channels list is required"
        return f"Selected {len(channels)} channels."


class MockSetMontageTool(BaseSetMontageTool):
    """Mock implementation of :class:`BaseSetMontageTool`."""

    def execute(self, study: Any, montage_name: str | None = None, **kwargs) -> str:
        """Return a simulated set-montage result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            montage_name: Standard montage name (e.g., ``'standard_1020'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.
        """
        if montage_name is None:
            return "Error: montage_name is required"
        return f"Set montage to {montage_name}."


class MockEpochDataTool(BaseEpochDataTool):
    """Mock implementation of :class:`BaseEpochDataTool`."""

    def execute(
        self,
        study: Any,
        t_min: float | None = None,
        t_max: float | None = None,
        event_id: dict[str, int] | None = None,
        baseline: list[float] | None = None,
        **kwargs,
    ) -> str:
        """Return a simulated epoching result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            t_min: Start time of each epoch in seconds.
            t_max: End time of each epoch in seconds.
            event_id: Event identifiers to epoch around.
            baseline: Baseline correction interval ``[start, end]``.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation message with the epoch window.
        """
        return f"Epoched data from {t_min}s to {t_max}s."
