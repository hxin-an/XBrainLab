"""Real evaluation and analysis-readiness tools."""

from typing import Any

from XBrainLab.backend.application import (
    EvaluateCommand,
    SaliencyCommand,
    VisualizeCommand,
)
from XBrainLab.backend.facade import BackendFacade

from ..definitions.analysis_def import (
    BaseEvaluateTool,
    BaseSaliencyTool,
    BaseVisualizeTool,
)


class RealEvaluateTool(BaseEvaluateTool):
    """Real implementation of :class:`BaseEvaluateTool`."""

    def execute(self, study: Any, target: str | None = None, **kwargs) -> str:
        result = BackendFacade(study).service.evaluate(EvaluateCommand(target=target))
        return result.message


class RealVisualizeTool(BaseVisualizeTool):
    """Real implementation of :class:`BaseVisualizeTool`."""

    def execute(self, study: Any, view: str | None = None, **kwargs) -> str:
        result = BackendFacade(study).service.visualize(VisualizeCommand(view=view))
        return result.message


class RealSaliencyTool(BaseSaliencyTool):
    """Real implementation of :class:`BaseSaliencyTool`."""

    def execute(
        self,
        study: Any,
        method: str | None = None,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> str:
        result = BackendFacade(study).service.saliency(
            SaliencyCommand(method=method, params=params),
        )
        return result.message
