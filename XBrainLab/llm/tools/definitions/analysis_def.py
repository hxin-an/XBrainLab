"""Tool definitions for evaluation and analysis-readiness commands."""

from typing import Any

from ..base import BaseTool


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

    def execute(self, study: Any, **kwargs) -> str:
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

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseSaliencyTool(BaseTool):
    """Configure or query saliency readiness through ApplicationService."""

    @property
    def name(self) -> str:
        return "saliency"

    @property
    def description(self) -> str:
        return "Query or configure saliency readiness for trained EEG models."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "Optional saliency method, such as Gradient.",
                },
                "params": {
                    "type": "object",
                    "description": "Optional saliency configuration parameters.",
                    "additionalProperties": True,
                },
            },
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError
