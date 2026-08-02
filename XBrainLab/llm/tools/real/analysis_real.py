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
        nt_samples: int | None = None,
        nt_samples_batch_size: int | None = None,
        stdevs: float | None = None,
        **kwargs,
    ) -> ToolResult:
        saliency_params = dict(params or {})
        if nt_samples is not None:
            saliency_params["nt_samples"] = nt_samples
        if nt_samples_batch_size is not None:
            saliency_params["nt_samples_batch_size"] = nt_samples_batch_size
        if stdevs is not None:
            saliency_params["stdevs"] = stdevs
        return execute_real_application_tool(
            study,
            self.name,
            {
                "method": method,
                "params": saliency_params or None,
            },
        )
