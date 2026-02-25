"""Abstract base tool definitions for EEG preprocessing operations.

Each class defines the tool's name, description, and JSON-schema
parameters.  Concrete (mock or real) implementations must override
:meth:`execute`.
"""

from typing import Any

from ..base import BaseTool


class BaseStandardPreprocessTool(BaseTool):
    """Apply a standard EEG preprocessing pipeline.

    Sequentially applies bandpass filtering, notch filtering,
    re-referencing, resampling, and normalisation in one step.
    """

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
    """Apply a bandpass filter to the loaded EEG data."""

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
    """Apply a notch filter to remove power-line noise."""

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
    """Resample the loaded EEG data to a new sampling rate."""

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
    """Normalise data using Z-Score or Min-Max scaling."""

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
    """Set the EEG reference (e.g., average or specific channels)."""

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
    """Select a subset of EEG channels to keep."""

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
    """Set a standard EEG montage (channel locations) for visualisation."""

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
    """Epoch continuous EEG data based on event markers."""

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
                "event_id": {"type": "array", "items": {"type": "string"}},
                "baseline": {"type": "array", "items": {"type": "number"}},
            },
            "required": ["t_min", "t_max"],
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError
