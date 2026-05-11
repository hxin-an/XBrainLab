"""Real evaluation and analysis-readiness tools."""

from typing import Any

from XBrainLab.backend.application import (
    EvaluateCommand,
    SaliencyCommand,
    VisualizeCommand,
    get_application_service,
)

from ..definitions.analysis_def import (
    BaseEvaluateTool,
    BaseSaliencyTool,
    BaseVisualizeTool,
)


class RealEvaluateTool(BaseEvaluateTool):
    """Real implementation of :class:`BaseEvaluateTool`."""

    def execute(self, study: Any, target: str | None = None, **kwargs) -> str:
        result = get_application_service(study).execute(EvaluateCommand(target=target))
        return result.message


class RealVisualizeTool(BaseVisualizeTool):
    """Real implementation of :class:`BaseVisualizeTool`."""

    def execute(self, study: Any, view: str | None = None, **kwargs) -> str:
        result = get_application_service(study).execute(VisualizeCommand(view=view))
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
        result = get_application_service(study).execute(
            SaliencyCommand(method=method, params=params),
        )
        return result.message
