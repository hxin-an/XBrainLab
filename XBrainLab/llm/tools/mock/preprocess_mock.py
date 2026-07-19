"""Mock implementations of EEG preprocessing tools.

Return deterministic results without modifying any data, enabling
offline agent testing and development.
"""

from typing import Any

from XBrainLab.backend.training.input_contract import (
    TrainingInputContractError,
    normalize_strict_boolean,
)

from ..definitions.preprocess_def import (
    BaseBandPassFilterTool,
    BaseChannelSelectionTool,
    BaseEpochDataTool,
    BaseNormalizeTool,
    BaseNotchFilterTool,
    BaseRereferenceTool,
    BaseResampleTool,
    BaseResetPreprocessTool,
    BaseSetMontageTool,
    BaseStandardPreprocessTool,
)
from ..result_contract import ToolResult
from .state import MockWorkflowState


class _RequiresLoadedData:
    """Keep mock preprocessing prerequisites aligned with ApplicationService."""

    def __init__(self, state: MockWorkflowState | None = None) -> None:
        self._state = state if state is not None else MockWorkflowState()

    def _loaded_data_precondition(self) -> ToolResult | None:
        if self._state.data_loaded:
            return None
        return ToolResult(
            ok=False,
            message="Load EEG data before preprocessing.",
            error_type="precondition",
        )


class MockStandardPreprocessTool(_RequiresLoadedData, BaseStandardPreprocessTool):
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
    ) -> ToolResult:
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
        blocked = self._loaded_data_precondition()
        if blocked is not None:
            return blocked
        return ToolResult(
            ok=True,
            message=(
                f"Applied standard preprocessing pipeline (BP: {l_freq}-{h_freq}Hz, "
                f"Notch: {notch_freq}Hz)."
            ),
        )


class MockResetPreprocessTool(_RequiresLoadedData, BaseResetPreprocessTool):
    """Mock the narrow preprocessing reset without clearing loaded raw data."""

    def execute(self, study: Any, **kwargs) -> ToolResult:
        blocked = self._loaded_data_precondition()
        if blocked is not None:
            return blocked
        try:
            normalize_strict_boolean(
                "confirmed",
                kwargs.get("confirmed", False),
            )
        except TrainingInputContractError as exc:
            return ToolResult(False, str(exc), error_type="input")
        self._state.reset_preprocess()
        return ToolResult(
            ok=True,
            message="Preprocessing reset to loaded raw data.",
        )


class MockBandPassFilterTool(_RequiresLoadedData, BaseBandPassFilterTool):
    """Mock implementation of :class:`BaseBandPassFilterTool`."""

    def execute(
        self,
        study: Any,
        low_freq: float | None = None,
        high_freq: float | None = None,
        **kwargs,
    ) -> ToolResult:
        """Return a simulated bandpass-filter result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            low_freq: Lower cutoff frequency in Hz.
            high_freq: Upper cutoff frequency in Hz.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        blocked = self._loaded_data_precondition()
        if blocked is not None:
            return blocked
        if low_freq is None or high_freq is None:
            return ToolResult(
                ok=False,
                message="Error: frequencies are required",
                error_type="input",
            )
        return ToolResult(
            ok=True,
            message=f"Applied bandpass filter ({low_freq}-{high_freq} Hz).",
        )


class MockNotchFilterTool(_RequiresLoadedData, BaseNotchFilterTool):
    """Mock implementation of :class:`BaseNotchFilterTool`."""

    def execute(
        self,
        study: Any,
        freq: float | None = None,
        **kwargs,
    ) -> ToolResult:
        """Return a simulated notch-filter result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            freq: Notch frequency in Hz.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        blocked = self._loaded_data_precondition()
        if blocked is not None:
            return blocked
        if freq is None:
            return ToolResult(
                ok=False,
                message="Error: frequency is required",
                error_type="input",
            )
        return ToolResult(
            ok=True,
            message=f"Applied notch filter at {freq} Hz.",
        )


class MockResampleTool(_RequiresLoadedData, BaseResampleTool):
    """Mock implementation of :class:`BaseResampleTool`."""

    def execute(
        self,
        study: Any,
        rate: int | None = None,
        **kwargs,
    ) -> ToolResult:
        """Return a simulated resample result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            rate: Target sampling rate in Hz.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        blocked = self._loaded_data_precondition()
        if blocked is not None:
            return blocked
        if rate is None:
            return ToolResult(
                ok=False,
                message="Error: rate is required",
                error_type="input",
            )
        return ToolResult(ok=True, message=f"Resampled data to {rate} Hz.")


class MockNormalizeTool(_RequiresLoadedData, BaseNormalizeTool):
    """Mock implementation of :class:`BaseNormalizeTool`."""

    def execute(
        self,
        study: Any,
        method: str | None = None,
        **kwargs,
    ) -> ToolResult:
        """Return a simulated normalisation result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            method: Normalisation method (``'z-score'`` or ``'min-max'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        blocked = self._loaded_data_precondition()
        if blocked is not None:
            return blocked
        if method is None:
            return ToolResult(
                ok=False,
                message="Error: method is required",
                error_type="input",
            )
        return ToolResult(
            ok=True,
            message=f"Normalized data using {method} method.",
        )


class MockRereferenceTool(_RequiresLoadedData, BaseRereferenceTool):
    """Mock implementation of :class:`BaseRereferenceTool`."""

    def execute(
        self,
        study: Any,
        method: str | None = None,
        **kwargs,
    ) -> ToolResult:
        """Return a simulated re-reference result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            method: Reference method name.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        blocked = self._loaded_data_precondition()
        if blocked is not None:
            return blocked
        if method is None:
            return ToolResult(
                ok=False,
                message="Error: method is required",
                error_type="input",
            )
        return ToolResult(ok=True, message=f"Re-referenced data to {method}.")


class MockChannelSelectionTool(_RequiresLoadedData, BaseChannelSelectionTool):
    """Mock implementation of :class:`BaseChannelSelectionTool`."""

    def execute(
        self,
        study: Any,
        channels: list[str] | None = None,
        **kwargs,
    ) -> ToolResult:
        """Return a simulated channel-selection result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            channels: List of channel names to keep.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        blocked = self._loaded_data_precondition()
        if blocked is not None:
            return blocked
        if channels is None:
            return ToolResult(
                ok=False,
                message="Error: channels list is required",
                error_type="input",
            )
        return ToolResult(
            ok=True,
            message=f"Selected {len(channels)} channels.",
        )


class MockSetMontageTool(_RequiresLoadedData, BaseSetMontageTool):
    """Mock implementation of :class:`BaseSetMontageTool`."""

    def execute(
        self,
        study: Any,
        montage_name: str | None = None,
        **kwargs,
    ) -> ToolResult:
        """Return a simulated set-montage result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            montage_name: Standard montage name (e.g., ``'standard_1020'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        blocked = self._loaded_data_precondition()
        if blocked is not None:
            return blocked
        if montage_name is None:
            return ToolResult(
                ok=False,
                message="Error: montage_name is required",
                error_type="input",
            )
        return ToolResult(ok=True, message=f"Set montage to {montage_name}.")


class MockEpochDataTool(BaseEpochDataTool):
    """Mock implementation of :class:`BaseEpochDataTool`."""

    def __init__(self, state: MockWorkflowState | None = None) -> None:
        self._state = state if state is not None else MockWorkflowState()

    def execute(
        self,
        study: Any,
        t_min: float | None = None,
        t_max: float | None = None,
        event_id: list[str] | None = None,
        baseline: list[float] | None = None,
        **kwargs,
    ) -> ToolResult:
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
        if not self._state.data_loaded:
            return ToolResult(
                ok=False,
                message="Load EEG data before creating epochs.",
                error_type="precondition",
            )
        self._state.mark_epochs_ready()
        return ToolResult(
            ok=True,
            message=f"Epoched data from {t_min}s to {t_max}s.",
        )
