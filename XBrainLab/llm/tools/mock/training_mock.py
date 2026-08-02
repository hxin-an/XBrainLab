"""Mock implementations of model training tools.

Return deterministic results without running any actual training,
enabling offline agent testing and development.
"""

from typing import Any

from XBrainLab.backend.training.input_contract import (
    TRAINING_DEVICE_NAMES,
    TRAINING_EVALUATION_NAMES,
    TRAINING_MODEL_NAMES,
    TRAINING_OPTIMIZER_NAMES,
    TrainingInputContractError,
    normalize_non_negative_integer,
    normalize_positive_integer,
    normalize_strict_boolean,
    normalize_training_input,
)

from ..definitions.training_def import (
    BaseConfigureTrainingTool,
    BaseSetModelTool,
    BaseStartTrainingTool,
    BaseStopTrainingTool,
)
from ..result_contract import ToolResult
from .state import MockWorkflowState


def _unsupported_choice(
    field: str,
    value: object,
    supported: tuple[str, ...],
) -> ToolResult:
    expected = ", ".join(supported)
    return ToolResult(
        ok=False,
        message=f"Unsupported {field}: {value}. Expected one of: {expected}.",
        error_type="input",
    )


def _canonical_choice(value: object, supported: tuple[str, ...]) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    return next(
        (candidate for candidate in supported if candidate.casefold() == normalized),
        None,
    )


class MockSetModelTool(BaseSetModelTool):
    """Mock implementation of :class:`BaseSetModelTool`."""

    def __init__(self, state: MockWorkflowState | None = None) -> None:
        self._state = state if state is not None else MockWorkflowState()

    def execute(
        self,
        study: Any,
        model_name: str | None = None,
        **kwargs,
    ) -> ToolResult:
        """Return a simulated model-set result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            model_name: Name of the model architecture.
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        if model_name is None:
            return ToolResult(
                ok=False,
                message="Error: model_name is required",
                error_type="input",
            )
        canonical_model = _canonical_choice(model_name, TRAINING_MODEL_NAMES)
        if canonical_model is None:
            return _unsupported_choice(
                "model_name",
                model_name,
                TRAINING_MODEL_NAMES,
            )
        self._state.model_name = canonical_model
        return ToolResult(ok=True, message=f"Model set to {canonical_model}.")


class MockConfigureTrainingTool(BaseConfigureTrainingTool):
    """Mock implementation of :class:`BaseConfigureTrainingTool`."""

    def __init__(self, state: MockWorkflowState | None = None) -> None:
        self._state = state if state is not None else MockWorkflowState()

    def execute(
        self,
        study: Any,
        model_name: str | None = None,
        epoch: int | None = None,
        batch_size: int | None = None,
        learning_rate: float | None = None,
        repeat: int = 1,
        device: str = "cpu",
        optimizer: str = "adam",
        evaluation_option: str = "last_epoch",
        save_checkpoints_every: int = 0,
        **kwargs,
    ) -> ToolResult:
        """Return a simulated training-configuration result.

        Args:
            study: The global ``Study`` instance (unused in mock).
            model_name: Optional model configured with the training options.
            epoch: Number of training epochs.
            batch_size: Mini-batch size.
            learning_rate: Optimiser learning rate.
            repeat: Number of experiment repetitions.
            device: Compute device (``'cpu'`` or ``'cuda'``).
            optimizer: Optimiser name.
            evaluation_option: Model-selection metric used after training.
            save_checkpoints_every: Checkpoint save interval (0 = disabled).
            **kwargs: Additional keyword arguments.

        Returns:
            A confirmation or error message.

        """
        canonical_model = (
            _canonical_choice(model_name, TRAINING_MODEL_NAMES)
            if model_name is not None
            else None
        )
        if model_name is not None and canonical_model is None:
            return _unsupported_choice(
                "model_name",
                model_name,
                TRAINING_MODEL_NAMES,
            )
        canonical_device = _canonical_choice(device, TRAINING_DEVICE_NAMES)
        if canonical_device is None:
            return _unsupported_choice("device", device, TRAINING_DEVICE_NAMES)
        canonical_optimizer = _canonical_choice(optimizer, TRAINING_OPTIMIZER_NAMES)
        if canonical_optimizer is None:
            return _unsupported_choice(
                "optimizer",
                optimizer,
                TRAINING_OPTIMIZER_NAMES,
            )
        canonical_evaluation = _canonical_choice(
            evaluation_option,
            TRAINING_EVALUATION_NAMES,
        )
        if canonical_evaluation is None:
            return _unsupported_choice(
                "evaluation_option",
                evaluation_option,
                TRAINING_EVALUATION_NAMES,
            )
        try:
            training_input = normalize_training_input(
                {
                    "epoch": epoch,
                    "batch_size": batch_size,
                    "learning_rate": learning_rate,
                }
            )
            normalize_positive_integer("repeat", repeat)
            normalized_checkpoint = normalize_non_negative_integer(
                "save_checkpoints_every",
                save_checkpoints_every,
            )
        except TrainingInputContractError as exc:
            return ToolResult(
                ok=False,
                message=str(exc),
                error_type="input",
            )
        if canonical_model is not None:
            self._state.model_name = canonical_model
        self._state.training_options_configured = True
        return ToolResult(
            ok=True,
            message=(
                f"Training configured (Training epochs: {training_input.epoch}, "
                f"LR: {training_input.learning_rate}, Device: {canonical_device}, "
                f"Optim: {canonical_optimizer}, Ckt: {normalized_checkpoint})."
            ),
        )


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
