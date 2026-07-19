"""Real evaluation and analysis-readiness tools."""

from typing import Any

from .. import execute_real_application_tool
from ..definitions.analysis_def import (
    BaseEvaluateTool,
    BaseSaliencyTool,
    BaseVisualizeTool,
)
from ..result_contract import ToolResult


class RealEvaluateTool(BaseEvaluateTool):
    """Real implementation of :class:`BaseEvaluateTool`."""

    def execute(
        self,
        study: Any,
        target: str | None = None,
        **kwargs,
    ) -> ToolResult:
        return execute_real_application_tool(
            study,
            self.name,
            {"target": target},
        )


class RealVisualizeTool(BaseVisualizeTool):
    """Real implementation of :class:`BaseVisualizeTool`."""

    def execute(
        self,
        study: Any,
        view: str | None = None,
        **kwargs,
    ) -> ToolResult:
        return execute_real_application_tool(
            study,
            self.name,
            {"view": view},
        )


class RealSaliencyTool(BaseSaliencyTool):
    """Real implementation of :class:`BaseSaliencyTool`."""

    def execute(
        self,
        study: Any,
        method: str | None = None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> ToolResult:
        return execute_real_application_tool(
            study,
            self.name,
            {"method": method, "params": params},
        )
