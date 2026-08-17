"""Abstract base tool definitions for model training operations.

Each class defines the tool's name, description, and JSON-schema
parameters.  Concrete (mock or real) implementations must override
:meth:`execute`.
"""

from typing import Any

from ..base import BaseTool
from ..result_contract import ToolExecutionResult


class BaseStartTrainingTool(BaseTool):
    """Start the training process.

    Requires that a model and training configuration have been set.
    """

    @property
    def name(self) -> str:
        return "start_training"

    @property
    def description(self) -> str:
        return "Start the training process."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    @property
    def requires_confirmation(self) -> bool:
        """Training is a long-running GPU operation and requires confirmation."""
        return True

    def execute(self, study: Any, **kwargs) -> ToolExecutionResult:
        raise NotImplementedError


class BaseStopTrainingTool(BaseTool):
    """Request that the currently active training run stop."""

    @property
    def name(self) -> str:
        return "stop_training"

    @property
    def description(self) -> str:
        return "Stop the active training run without starting a new run."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    def execute(self, study: Any, **kwargs) -> ToolExecutionResult:
        raise NotImplementedError
