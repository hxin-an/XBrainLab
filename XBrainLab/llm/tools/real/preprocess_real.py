"""Real implementations of EEG preprocessing tools.

These tools interact with the ``BackendFacade`` to apply actual
preprocessing operations (filtering, resampling, normalisation, etc.)
to the loaded EEG data.
"""

from typing import Any

from XBrainLab.backend.facade import BackendFacade

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


class RealStandardPreprocessTool(BaseStandardPreprocessTool):
    """Real implementation of :class:`BaseStandardPreprocessTool`.

    Applies a full preprocessing pipeline (bandpass, notch, resample,
    re-reference, normalise) via :class:`BackendFacade`.
    """

    def is_valid(self, study: Any) -> bool:
        """Require loaded data before preprocessing.

        Args:
            study: The global ``Study`` instance.

        Returns:
            ``True`` if data has been loaded.

        """
        return bool(study.loaded_data_list)

    def execute(
        self,
        study: Any,
        l_freq: float = 4,
        h_freq: float = 40,
        notch_freq: float = 50,
        rereference: str | None = None,
        resample_rate: int | None = None,
        normalize_method: str = "z-score",
        **kwargs,
    ) -> str:
        """Apply the standard preprocessing pipeline.

        Args:
            study: The global ``Study`` instance.
            l_freq: Lower bandpass cutoff in Hz.
            h_freq: Upper bandpass cutoff in Hz.
            notch_freq: Notch filter frequency in Hz.
            rereference: Re-reference method (e.g., ``'average'``).
            resample_rate: Target sampling rate in Hz.
            normalize_method: Normalisation method (``'z-score'`` or
                ``'min-max'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A success message or an error description.

        """
        facade = BackendFacade(study)

        try:
            with facade.preprocess.batch_notifications():
                # 1. Bandpass
                facade.apply_filter(l_freq, h_freq)

                # 2. Notch
                if notch_freq:
                    facade.apply_notch_filter(notch_freq)

                # 3. Resample
                if resample_rate:
                    facade.resample_data(resample_rate)

                # 4. Rereference
                if rereference:
                    facade.set_reference(rereference)

                # 5. Normalize
                if normalize_method:
                    facade.normalize_data(normalize_method)

        except Exception as e:
            return f"Preprocessing failed: {e!s}"

        return "Standard preprocessing applied successfully via Facade."


class RealBandPassFilterTool(BaseBandPassFilterTool):
    """Real implementation of :class:`BaseBandPassFilterTool`."""

    def is_valid(self, study: Any) -> bool:
        """Require loaded data."""
        return bool(study.loaded_data_list)

    def execute(
        self,
        study: Any,
        low_freq: float | None = None,
        high_freq: float | None = None,
        **kwargs,
    ) -> str:
        """Apply a bandpass filter to loaded EEG data.

        Args:
            study: The global ``Study`` instance.
            low_freq: Lower cutoff frequency in Hz.
            high_freq: Upper cutoff frequency in Hz.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        if low_freq is None or high_freq is None:
            return "Error: low_freq and high_freq are required."

        facade = BackendFacade(study)
        facade.apply_filter(low_freq, high_freq)
        return f"Applied Bandpass Filter ({low_freq}-{high_freq} Hz)"


class RealNotchFilterTool(BaseNotchFilterTool):
    """Real implementation of :class:`BaseNotchFilterTool`."""

    def is_valid(self, study: Any) -> bool:
        """Require loaded data."""
        return bool(study.loaded_data_list)

    def execute(self, study: Any, freq: float | None = None, **kwargs) -> str:
        """Apply a notch filter to remove power-line noise.

        Args:
            study: The global ``Study`` instance.
            freq: Notch frequency in Hz.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        if freq is None:
            return "Error: freq is required."

        facade = BackendFacade(study)
        facade.apply_notch_filter(freq)
        return f"Applied Notch Filter ({freq} Hz)"


class RealResampleTool(BaseResampleTool):
    """Real implementation of :class:`BaseResampleTool`."""

    def is_valid(self, study: Any) -> bool:
        """Require loaded data."""
        return bool(study.loaded_data_list)

    def execute(self, study: Any, rate: int | None = None, **kwargs) -> str:
        """Resample the loaded EEG data to a new sampling rate.

        Args:
            study: The global ``Study`` instance.
            rate: Target sampling rate in Hz.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        if rate is None:
            return "Error: rate is required."

        facade = BackendFacade(study)
        facade.resample_data(rate)
        return f"Resampled data to {rate} Hz"


class RealNormalizeTool(BaseNormalizeTool):
    """Real implementation of :class:`BaseNormalizeTool`."""

    def is_valid(self, study: Any) -> bool:
        """Require loaded data."""
        return bool(study.loaded_data_list)

    def execute(self, study: Any, method: str | None = None, **kwargs) -> str:
        """Normalise the loaded EEG data.

        Args:
            study: The global ``Study`` instance.
            method: Normalisation method (``'z-score'`` or ``'min-max'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        if method is None:
            return "Error: method is required."

        facade = BackendFacade(study)
        facade.normalize_data(method)
        return f"Normalized data using {method}"


class RealRereferenceTool(BaseRereferenceTool):
    """Real implementation of :class:`BaseRereferenceTool`."""

    def is_valid(self, study: Any) -> bool:
        """Require loaded data."""
        return bool(study.loaded_data_list)

    def execute(self, study: Any, method: str | None = None, **kwargs) -> str:
        """Set the EEG reference.

        Args:
            study: The global ``Study`` instance.
            method: Reference method (e.g., ``'average'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        if method is None:
            return "Error: method is required."

        facade = BackendFacade(study)
        facade.set_reference(method)
        return f"Applied reference: {method}"


class RealChannelSelectionTool(BaseChannelSelectionTool):
    """Real implementation of :class:`BaseChannelSelectionTool`."""

    def is_valid(self, study: Any) -> bool:
        """Require loaded data."""
        return bool(study.loaded_data_list)

    def execute(self, study: Any, channels: list[str] | None = None, **kwargs) -> str:
        """Select specific EEG channels to keep.

        Args:
            study: The global ``Study`` instance.
            channels: List of channel names to retain.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        if channels is None:
            return "Error: channels list is required."

        facade = BackendFacade(study)
        facade.select_channels(channels)
        return f"Selected {len(channels)} channels."


class RealSetMontageTool(BaseSetMontageTool):
    """Real implementation of :class:`BaseSetMontageTool`.

    Requests UI confirmation instead of auto-applying, allowing the
    user to visually verify the channel-to-electrode mapping.
    """

    def is_valid(self, study: Any) -> bool:
        """Require loaded data."""
        return bool(study.loaded_data_list)

    def execute(self, study: Any, montage_name: str | None = None, **kwargs) -> str:
        """Request montage application with UI confirmation.

        Args:
            study: The global ``Study`` instance.
            montage_name: Standard montage name (e.g., ``'standard_1020'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A request string for UI confirmation, or an error message.

        """
        if montage_name is None:
            return "Error: montage_name is required."

        # Instead of auto-applying, request UI confirmation
        # This allows users to visually verify channel-to-electrode mapping
        return f"Request: confirm_montage '{montage_name}'"


class RealEpochDataTool(BaseEpochDataTool):
    """Real implementation of :class:`BaseEpochDataTool`."""

    def is_valid(self, study: Any) -> bool:
        """Require loaded data."""
        return bool(study.loaded_data_list)

    def execute(
        self,
        study: Any,
        t_min: float = -0.1,
        t_max: float = 1.0,
        baseline: list[float] | None = None,
        event_id: list[str] | None = None,  # Note: Definitions use 'event_id'
        **kwargs,
    ) -> str:
        """Epoch continuous EEG data based on event markers.

        Args:
            study: The global ``Study`` instance.
            t_min: Start time of each epoch in seconds.
            t_max: End time of each epoch in seconds.
            baseline: Baseline correction interval ``[start, end]``.
            event_id: Event identifiers to epoch around.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation message or an error description.

        """
        facade = BackendFacade(study)

        try:
            # Facade expects event_ids as list of strings
            facade.epoch_data(t_min, t_max, baseline=baseline, event_ids=event_id)
        except Exception as e:
            return f"Epoching failed: {e!s}"
        else:
            return f"Data epoched from {t_min}s to {t_max}s."
