from typing import Any

from ..base import BaseTool


class BaseStandardPreprocessTool(BaseTool):
    @property
    def name(self) -> str:
        return "apply_standard_preprocess"

    @property
    def description(self) -> str:
        return (
            "Apply standard EEG preprocessing pipeline (Bandpass, Notch, Rereference, "
            "Normalize)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "l_freq": {"type": "number", "default": 4.0},
                "h_freq": {"type": "number", "default": 40.0},
                "notch_freq": {"type": "number", "default": 50.0},
                "rereference": {"type": "string"},
                "resample_rate": {"type": "integer"},
                "normalize_method": {"type": "string", "enum": ["z-score", "min-max"]},
            },
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseBandPassFilterTool(BaseTool):
    @property
    def name(self) -> str:
        return "apply_bandpass_filter"

    @property
    def description(self) -> str:
        return "Apply bandpass filter to the data."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "low_freq": {"type": "number"},
                "high_freq": {"type": "number"},
            },
            "required": ["low_freq", "high_freq"],
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseNotchFilterTool(BaseTool):
    @property
    def name(self) -> str:
        return "apply_notch_filter"

    @property
    def description(self) -> str:
        return "Apply notch filter to remove power line noise."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"freq": {"type": "number"}},
            "required": ["freq"],
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseResampleTool(BaseTool):
    @property
    def name(self) -> str:
        return "resample_data"

    @property
    def description(self) -> str:
        return "Resample data to a new sampling rate."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"rate": {"type": "integer"}},
            "required": ["rate"],
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseNormalizeTool(BaseTool):
    @property
    def name(self) -> str:
        return "normalize_data"

    @property
    def description(self) -> str:
        return "Normalize data using Z-Score or Min-Max scaling."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["z-score", "min-max"]}
            },
            "required": ["method"],
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseRereferenceTool(BaseTool):
    @property
    def name(self) -> str:
        return "set_reference"

    @property
    def description(self) -> str:
        return "Set EEG reference (e.g., average or specific channels)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"method": {"type": "string"}},
            "required": ["method"],
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseChannelSelectionTool(BaseTool):
    @property
    def name(self) -> str:
        return "select_channels"

    @property
    def description(self) -> str:
        return "Select specific channels to keep."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"channels": {"type": "array", "items": {"type": "string"}}},
            "required": ["channels"],
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseSetMontageTool(BaseTool):
    @property
    def name(self) -> str:
        return "set_montage"

    @property
    def description(self) -> str:
        return "Set standard EEG montage (channel locations) for visualization."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"montage_name": {"type": "string"}},
            "required": ["montage_name"],
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseEpochDataTool(BaseTool):
    @property
    def name(self) -> str:
        return "epoch_data"

    @property
    def description(self) -> str:
        return "Epoch continuous data based on events."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "t_min": {"type": "number"},
                "t_max": {"type": "number"},
                "event_id": {"type": "object"},
                "baseline": {"type": "array", "items": {"type": "number"}},
            },
            "required": ["t_min", "t_max"],
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError
