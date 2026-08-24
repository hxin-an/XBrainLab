"""Tool definitions for the five direct Assistant preprocessing actions."""

from typing import Any

from ..base import BaseTool
from ..result_contract import ToolExecutionResult

_DIRECT_INPUT_POLICY = (
    " Required values must come from the latest user request. If any are absent, "
    "use respond_to_user with pending_action and missing_inputs instead of calling "
    "this action."
)
_REQUIRED_VALUE_ORIGIN = (
    " Copy only a value explicitly supplied in the latest user request. There is "
    "no model or product default."
)


class BaseBandPassFilterTool(BaseTool):
    @property
    def name(self) -> str:
        return "apply_bandpass_filter"

    @property
    def description(self) -> str:
        return "Apply only a single bandpass filter to the data." + _DIRECT_INPUT_POLICY

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "low_freq": {
                    "type": "number",
                    "description": "Required low cutoff in Hz."
                    + _REQUIRED_VALUE_ORIGIN,
                },
                "high_freq": {
                    "type": "number",
                    "description": "Required high cutoff in Hz."
                    + _REQUIRED_VALUE_ORIGIN,
                },
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
        return "Apply a notch filter to the data." + _DIRECT_INPUT_POLICY

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "freq": {
                    "type": "number",
                    "description": "Required notch frequency in Hz."
                    + _REQUIRED_VALUE_ORIGIN,
                }
            },
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
        return "Resample data to a new sampling rate." + _DIRECT_INPUT_POLICY

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "rate": {
                    "type": "integer",
                    "description": "Required resampling rate in Hz."
                    + _REQUIRED_VALUE_ORIGIN,
                }
            },
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
        return "Normalize data using the user's explicit method." + _DIRECT_INPUT_POLICY

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["z-score", "min-max"],
                    "description": (
                        "Required normalization method; enum values are constraints, "
                        "not recommendations." + _REQUIRED_VALUE_ORIGIN
                    ),
                },
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
        return (
            "Set the EEG reference using the user's explicit method."
            + _DIRECT_INPUT_POLICY
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "Required EEG reference method."
                    + _REQUIRED_VALUE_ORIGIN,
                }
            },
            "required": ["method"],
        }

    def execute(self, study: Any, **kwargs) -> ToolExecutionResult:
        raise NotImplementedError
