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
        facade = BackendFacade(study)

        try:
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
    def execute(
        self,
        study: Any,
        low_freq: float | None = None,
        high_freq: float | None = None,
        **kwargs,
    ) -> str:
        if low_freq is None or high_freq is None:
            return "Error: low_freq and high_freq are required."

        facade = BackendFacade(study)
        facade.apply_filter(low_freq, high_freq)
        return f"Applied Bandpass Filter ({low_freq}-{high_freq} Hz)"


class RealNotchFilterTool(BaseNotchFilterTool):
    def execute(self, study: Any, freq: float | None = None, **kwargs) -> str:
        if freq is None:
            return "Error: freq is required."

        facade = BackendFacade(study)
        facade.apply_notch_filter(freq)
        return f"Applied Notch Filter ({freq} Hz)"


class RealResampleTool(BaseResampleTool):
    def execute(self, study: Any, rate: int | None = None, **kwargs) -> str:
        if rate is None:
            return "Error: rate is required."

        facade = BackendFacade(study)
        facade.resample_data(rate)
        return f"Resampled data to {rate} Hz"


class RealNormalizeTool(BaseNormalizeTool):
    def execute(self, study: Any, method: str | None = None, **kwargs) -> str:
        if method is None:
            return "Error: method is required."

        facade = BackendFacade(study)
        facade.normalize_data(method)
        return f"Normalized data using {method}"


class RealRereferenceTool(BaseRereferenceTool):
    def execute(self, study: Any, method: str | None = None, **kwargs) -> str:
        if method is None:
            return "Error: method is required."

        facade = BackendFacade(study)
        facade.set_reference(method)
        return f"Applied reference: {method}"


class RealChannelSelectionTool(BaseChannelSelectionTool):
    def execute(self, study: Any, channels: list[str] | None = None, **kwargs) -> str:
        if channels is None:
            return "Error: channels list is required."

        facade = BackendFacade(study)
        facade.select_channels(channels)
        return f"Selected {len(channels)} channels."


class RealSetMontageTool(BaseSetMontageTool):
    def execute(self, study: Any, montage_name: str | None = None, **kwargs) -> str:
        if montage_name is None:
            return "Error: montage_name is required."

        facade = BackendFacade(study)
        # All fuzzy matching logic is now in the Facade!
        return facade.set_montage(montage_name)


class RealEpochDataTool(BaseEpochDataTool):
    def execute(
        self,
        study: Any,
        t_min: float = -0.1,
        t_max: float = 1.0,
        baseline: list[float] | None = None,
        event_id: list[str] | None = None,  # Note: Definitions use 'event_id'
        **kwargs,
    ) -> str:
        facade = BackendFacade(study)

        try:
            # Facade expects event_ids as list of strings
            facade.epoch_data(t_min, t_max, baseline=baseline, event_ids=event_id)
        except Exception as e:
            return f"Epoching failed: {e!s}"
        else:
            return f"Data epoched from {t_min}s to {t_max}s."
