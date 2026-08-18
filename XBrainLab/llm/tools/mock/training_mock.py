"""Mock implementations of model training tools.

Return deterministic results without running any actual training,
enabling offline agent testing and development.
"""

from typing import Any

from XBrainLab.backend.training.input_contract import (
    TrainingInputContractError,
    normalize_strict_boolean,
)

from ..definitions.training_def import (
    BaseStartTrainingTool,
    BaseStopTrainingTool,
)
from ..result_contract import ToolResult
from .state import MockWorkflowState


class MockStartTrainingTool(BaseStartTrainingTool):
    """Mock implementation of :class:`BaseStartTrainingTool`."""

    def __init__(self, state: MockWorkflowState | None = None) -> None:
        self._state = state if state is not None else MockWorkflowState()

    def execute(self, study: Any, **kwargs) -> ToolResult:
        """Return a simulated training-start result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            **kwargs: Additional keyword arguments.

        Returns:
            A message indicating mock training completed.

        """
        try:
            confirmed = normalize_strict_boolean(
                "confirmed",
                kwargs.get("confirmed", False),
            )
        except TrainingInputContractError as exc:
            return ToolResult(False, str(exc), error_type="input")

        missing = self._state.missing_training_prerequisites()
        if missing:
            return ToolResult(
                ok=False,
                message=(
                    "Training cannot start until these prerequisites are ready: "
                    + ", ".join(missing)
                    + "."
                ),
                error_type="precondition",
            )
        if not confirmed:
            return ToolResult(
                ok=False,
                message="Training requires confirmation.",
                error_type="confirmation_required",
            )
        return ToolResult(
            ok=True,
            message="Training started. (Mock: Training completed successfully.)",
        )


class MockStopTrainingTool(BaseStopTrainingTool):
    """Mock cancellation of an explicitly active training run."""

    def __init__(self, state: MockWorkflowState | None = None) -> None:
        self._state = state if state is not None else MockWorkflowState()

    def execute(self, study: Any, **kwargs) -> ToolResult:
        if not self._state.training_running:
            return ToolResult(
                ok=False,
                message="No training run is active.",
                error_type="precondition",
            )
        self._state.training_running = False
        return ToolResult(ok=True, message="Training stop requested.")
