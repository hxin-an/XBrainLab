"""Tool definitions for the five direct Assistant preprocessing actions."""

from typing import Any

from ..base import BaseTool
from ..result_contract import ToolExecutionResult


class BaseBandPassFilterTool(BaseTool):
    @property
    def name(self) -> str:
        return "apply_bandpass_filter"

    @property
    def description(self) -> str:
        return "Apply only a single bandpass filter to the data."

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

    def execute(self, study: Any, **kwargs) -> ToolExecutionResult:
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

    def execute(self, study: Any, **kwargs) -> ToolExecutionResult:
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

    def execute(self, study: Any, **kwargs) -> ToolExecutionResult:
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
                "method": {"type": "string", "enum": ["z-score", "min-max"]},
            },
            "required": ["method"],
        }

    def execute(self, study: Any, **kwargs) -> ToolExecutionResult:
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

    def execute(self, study: Any, **kwargs) -> ToolExecutionResult:
        raise NotImplementedError
