"""Real implementations of model training tools.

These tools interact with the ApplicationService command spine to configure
and launch actual deep-learning training runs.
"""

from typing import Any

from .. import execute_real_application_tool
from ..definitions.training_def import (
    BaseStartTrainingTool,
    BaseStopTrainingTool,
)
from ..result_contract import ToolResult


class RealStartTrainingTool(BaseStartTrainingTool):
    """Real implementation of :class:`BaseStartTrainingTool`.

    Launches the training process through ApplicationService.
    """

    def execute(self, study: Any, **kwargs) -> ToolResult:
        """Start the training process in a background thread.

        Args:
            study: The global ``Study`` instance.
            **kwargs: Additional keyword arguments.

        Returns:
            A success message or an error description.

        """
        return execute_real_application_tool(
            study,
            self.name,
            {
                "append": kwargs.get("append", True),
                "interactive": kwargs.get("interactive", True),
                "confirmed": kwargs.get("confirmed", False),
                "resource_preflight_confirmed": kwargs.get(
                    "resource_preflight_confirmed",
                    False,
                ),
                "resource_preflight_token": kwargs.get("resource_preflight_token"),
            },
        )


class RealStopTrainingTool(BaseStopTrainingTool):
    """Request training cancellation through ApplicationService."""

    def execute(self, study: Any, **kwargs) -> ToolResult:
        """Stop the active run without waiting on the UI thread."""
        return execute_real_application_tool(study, self.name, {})
