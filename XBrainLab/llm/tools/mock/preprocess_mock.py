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
        return (
            f"Applied standard preprocessing pipeline (BP: {l_freq}-{h_freq}Hz, "
            f"Notch: {notch_freq}Hz)."
        )


class MockBandPassFilterTool(BaseBandPassFilterTool):
    def execute(
        self,
        study: Any,
        low_freq: float | None = None,
        high_freq: float | None = None,
        **kwargs,
    ) -> str:
        if low_freq is None or high_freq is None:
            return "Error: frequencies are required"
        return f"Applied bandpass filter ({low_freq}-{high_freq} Hz)."


class MockNotchFilterTool(BaseNotchFilterTool):
    def execute(self, study: Any, freq: float | None = None, **kwargs) -> str:
        if freq is None:
            return "Error: frequency is required"
        return f"Applied notch filter at {freq} Hz."


class MockResampleTool(BaseResampleTool):
    def execute(self, study: Any, rate: int | None = None, **kwargs) -> str:
        if rate is None:
            return "Error: rate is required"
        return f"Resampled data to {rate} Hz."


class MockNormalizeTool(BaseNormalizeTool):
    def execute(self, study: Any, method: str | None = None, **kwargs) -> str:
        if method is None:
            return "Error: method is required"
        return f"Normalized data using {method} method."


class MockRereferenceTool(BaseRereferenceTool):
    def execute(self, study: Any, method: str | None = None, **kwargs) -> str:
        if method is None:
            return "Error: method is required"
        return f"Re-referenced data to {method}."


class MockChannelSelectionTool(BaseChannelSelectionTool):
    def execute(self, study: Any, channels: list[str] | None = None, **kwargs) -> str:
        if channels is None:
            return "Error: channels list is required"
        return f"Selected {len(channels)} channels."


class MockSetMontageTool(BaseSetMontageTool):
    def execute(self, study: Any, montage_name: str | None = None, **kwargs) -> str:
        if montage_name is None:
            return "Error: montage_name is required"
        return f"Set montage to {montage_name}."


class MockEpochDataTool(BaseEpochDataTool):
    def execute(
        self,
        study: Any,
        t_min: float | None = None,
        t_max: float | None = None,
        event_id: dict[str, int] | None = None,
        baseline: list[float] | None = None,
        **kwargs,
    ) -> str:
        return f"Epoched data from {t_min}s to {t_max}s."
