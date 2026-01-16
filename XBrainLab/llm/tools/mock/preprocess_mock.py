
from typing import Any, Dict, List

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
    def execute(self, study: Any, l_freq: float = 4.0, h_freq: float = 40.0,
                notch_freq: float = 50.0, rereference: str = None,
                resample_rate: int = None, normalize_method: str = None) -> str:
        return f"Applied standard preprocessing pipeline (BP: {l_freq}-{h_freq}Hz, Notch: {notch_freq}Hz)."

class MockBandPassFilterTool(BaseBandPassFilterTool):
    def execute(self, study: Any, low_freq: float, high_freq: float) -> str:
        return f"Applied bandpass filter ({low_freq}-{high_freq} Hz)."

class MockNotchFilterTool(BaseNotchFilterTool):
    def execute(self, study: Any, freq: float) -> str:
        return f"Applied notch filter at {freq} Hz."

class MockResampleTool(BaseResampleTool):
    def execute(self, study: Any, rate: int) -> str:
        return f"Resampled data to {rate} Hz."

class MockNormalizeTool(BaseNormalizeTool):
    def execute(self, study: Any, method: str) -> str:
        return f"Normalized data using {method} method."

class MockRereferenceTool(BaseRereferenceTool):
    def execute(self, study: Any, method: str) -> str:
        return f"Re-referenced data to {method}."

class MockChannelSelectionTool(BaseChannelSelectionTool):
    def execute(self, study: Any, channels: List[str]) -> str:
        return f"Selected {len(channels)} channels."

class MockSetMontageTool(BaseSetMontageTool):
    def execute(self, study: Any, montage_name: str) -> str:
        return f"Set montage to {montage_name}."

class MockEpochDataTool(BaseEpochDataTool):
    def execute(self, study: Any, t_min: float, t_max: float, event_id: Dict[str, int] = None, baseline: List[float] = None) -> str:
        return f"Epoched data from {t_min}s to {t_max}s."
