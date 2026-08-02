"""Tool definitions for evaluation and analysis-readiness commands."""

from typing import Any

from XBrainLab.backend.application.saliency_policy import (
    MAX_SALIENCY_NT_SAMPLES,
    MAX_SALIENCY_NT_SAMPLES_BATCH_SIZE,
    MIN_SALIENCY_NT_SAMPLES,
    MIN_SALIENCY_NT_SAMPLES_BATCH_SIZE,
)

from ..base import BaseTool
from ..result_contract import ToolExecutionResult


class BaseEvaluateTool(BaseTool):
    """Read evaluation metrics and run summaries from ApplicationService."""

    @property
    def name(self) -> str:
        return "evaluate"

    @property
    def description(self) -> str:
        return "Read evaluation metrics and completed training summaries."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Optional evaluation target or run label.",
                },
            },
        }

    def execute(self, study: Any, **kwargs) -> ToolExecutionResult:
        raise NotImplementedError


class BaseVisualizeTool(BaseTool):
    """Read visualization readiness and available view summaries."""

    @property
    def name(self) -> str:
        return "visualize"

    @property
    def description(self) -> str:
        return "Read available visualization views for the current workflow state."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "view": {
                    "type": "string",
                    "description": (
                        "Optional view to check, such as summary or saliency map."
                    ),
                },
            },
        }

    def execute(self, study: Any, **kwargs) -> ToolExecutionResult:
        raise NotImplementedError


class BaseSaliencyTool(BaseTool):
    """Configure or query saliency readiness through ApplicationService."""

    @property
    def name(self) -> str:
        return "saliency"

    @property
    def description(self) -> str:
        return (
            "Query saliency readiness with no arguments, or configure one explicit "
            "saliency method for trained EEG models. Noise parameters apply only "
            "to SmoothGrad, SmoothGrad_Squared, or VarGrad."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": [
                        "Gradient",
                        "Gradient * Input",
                        "SmoothGrad",
                        "SmoothGrad_Squared",
                        "VarGrad",
                    ],
                    "description": (
                        "Saliency method to configure. Omit only for a readiness query."
                    ),
                },
                "nt_samples": {
                    "type": "integer",
                    "minimum": MIN_SALIENCY_NT_SAMPLES,
                    "maximum": MAX_SALIENCY_NT_SAMPLES,
                    "description": (
                        "Optional positive noise-sample count for SmoothGrad, "
                        "SmoothGrad_Squared, or VarGrad."
                    ),
                },
                "nt_samples_batch_size": {
                    "type": ["integer", "null"],
                    "minimum": MIN_SALIENCY_NT_SAMPLES_BATCH_SIZE,
                    "maximum": MAX_SALIENCY_NT_SAMPLES_BATCH_SIZE,
                    "description": (
                        "Optional positive noise-sample batch size, or null."
                    ),
                },
                "stdevs": {
                    "type": "number",
                    "minimum": 0,
                    "description": (
                        "Optional non-negative noise standard deviation for "
                        "SmoothGrad, SmoothGrad_Squared, or VarGrad."
                    ),
                },
            },
            "additionalProperties": False,
        }

    def execute(self, study: Any, **kwargs) -> ToolExecutionResult:
        raise NotImplementedError
