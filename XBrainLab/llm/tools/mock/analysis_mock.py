"""Mock evaluation and analysis-readiness tools."""

from typing import Any

from ..definitions.analysis_def import (
    BaseEvaluateTool,
    BaseSaliencyTool,
    BaseVisualizeTool,
)
from ..result_contract import ToolResult


class MockEvaluateTool(BaseEvaluateTool):
    """Mock implementation of :class:`BaseEvaluateTool`."""

    def execute(
        self,
        study: Any,
        target: str | None = None,
        **kwargs,
    ) -> ToolResult:
        suffix = f" for {target}" if target else ""
        return ToolResult(ok=True, message=f"Evaluation summary ready{suffix}.")


class MockVisualizeTool(BaseVisualizeTool):
    """Mock implementation of :class:`BaseVisualizeTool`."""

    def execute(
        self,
        study: Any,
        view: str | None = None,
        **kwargs,
    ) -> ToolResult:
        suffix = f": {view}" if view else ""
        return ToolResult(ok=True, message=f"Visualization summary ready{suffix}.")


class MockSaliencyTool(BaseSaliencyTool):
    """Mock implementation of :class:`BaseSaliencyTool`."""

    def execute(
        self,
        study: Any,
        method: str | None = None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> ToolResult:
        if method:
            return ToolResult(
                ok=True,
                message=f"Saliency readiness checked with {method}.",
            )
        if params:
            return ToolResult(
                ok=True,
                message="Saliency readiness checked with custom parameters.",
            )
        return ToolResult(ok=True, message="Saliency readiness summary ready.")
