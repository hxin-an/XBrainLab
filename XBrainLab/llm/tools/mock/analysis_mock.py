"""Mock evaluation and analysis-readiness tools."""

from typing import Any

from ..definitions.analysis_def import (
    BaseEvaluateTool,
    BaseSaliencyTool,
    BaseVisualizeTool,
)


class MockEvaluateTool(BaseEvaluateTool):
    """Mock implementation of :class:`BaseEvaluateTool`."""

    def execute(self, study: Any, target: str | None = None, **kwargs) -> str:
        suffix = f" for {target}" if target else ""
        return f"Evaluation summary ready{suffix}."


class MockVisualizeTool(BaseVisualizeTool):
    """Mock implementation of :class:`BaseVisualizeTool`."""

    def execute(self, study: Any, view: str | None = None, **kwargs) -> str:
        suffix = f": {view}" if view else ""
        return f"Visualization summary ready{suffix}."


class MockSaliencyTool(BaseSaliencyTool):
    """Mock implementation of :class:`BaseSaliencyTool`."""

    def execute(
        self,
        study: Any,
        method: str | None = None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> str:
        if method:
            return f"Saliency readiness checked with {method}."
        if params:
            return "Saliency readiness checked with custom parameters."
        return "Saliency readiness summary ready."
