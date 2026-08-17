"""Real adapters for the five direct Assistant preprocessing actions."""

from typing import Any

from XBrainLab.llm.tools import execute_real_application_tool
from XBrainLab.llm.tools.result_contract import ToolResult

from ..definitions.preprocess_def import (
    BaseBandPassFilterTool,
    BaseNormalizeTool,
    BaseNotchFilterTool,
    BaseRereferenceTool,
    BaseResampleTool,
)


class RealBandPassFilterTool(BaseBandPassFilterTool):
    def execute(
        self,
        study: Any,
        low_freq: float | None = None,
        high_freq: float | None = None,
        **kwargs,
    ) -> ToolResult:
        return execute_real_application_tool(
            study,
            self.name,
            {"low_freq": low_freq, "high_freq": high_freq},
        )


class RealNotchFilterTool(BaseNotchFilterTool):
    def execute(self, study: Any, freq: float | None = None, **kwargs) -> ToolResult:
        return execute_real_application_tool(study, self.name, {"freq": freq})


class RealResampleTool(BaseResampleTool):
    def execute(self, study: Any, rate: int | None = None, **kwargs) -> ToolResult:
        return execute_real_application_tool(study, self.name, {"rate": rate})


class RealNormalizeTool(BaseNormalizeTool):
    def execute(self, study: Any, method: str | None = None, **kwargs) -> ToolResult:
        return execute_real_application_tool(study, self.name, {"method": method})


class RealRereferenceTool(BaseRereferenceTool):
    def execute(self, study: Any, method: str | None = None, **kwargs) -> ToolResult:
        return execute_real_application_tool(study, self.name, {"method": method})
