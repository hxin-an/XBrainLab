"""Abstract base tool definitions for model training operations.

Each class defines the tool's name, description, and JSON-schema
parameters.  Concrete (mock or real) implementations must override
:meth:`execute`.
"""

from typing import Any

from XBrainLab.backend.training.input_contract import (
    REQUIRED_TRAINING_FIELDS,
    TRAINING_DEVICE_NAMES,
    TRAINING_EVALUATION_NAMES,
    TRAINING_MODEL_NAMES,
    TRAINING_OPTIMIZER_NAMES,
    non_negative_integer_parameter_schema,
    positive_integer_parameter_schema,
    training_parameter_schema,
)

from ..base import BaseTool
from ..result_contract import ToolExecutionResult


class BaseSetModelTool(BaseTool):
    """Set the deep learning model architecture for training.

    Supported architectures include EEGNet, ShallowConvNet,
    and SCCNet.
    """

    @property
    def name(self) -> str:
        return "set_model"

    @property
    def description(self) -> str:
        return "Set the deep learning model architecture."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "model_name": {
                    "type": "string",
                    "enum": list(TRAINING_MODEL_NAMES),
                },
            },
            "required": ["model_name"],
        }

    def execute(self, study: Any, **kwargs) -> ToolExecutionResult:
        raise NotImplementedError


class BaseConfigureTrainingTool(BaseTool):
    """Configure training hyperparameters.

    Includes epoch count, batch size, learning rate, optimizer,
    device selection, and checkpoint settings. The output directory remains
    owned by the application unless the host verifies an explicit user path.
    """

    @property
    def name(self) -> str:
        return "configure_training"

    @property
    def description(self) -> str:
        return "Configure training hyperparameters."

    @property
    def parameters(self) -> dict[str, Any]:
        training_properties = training_parameter_schema()
        return {
            "type": "object",
            "properties": {
                "model_name": {
                    "type": "string",
                    "enum": list(TRAINING_MODEL_NAMES),
                },
                **training_properties,
                "repeat": positive_integer_parameter_schema(default=1),
                "device": {
                    "type": "string",
                    "enum": list(TRAINING_DEVICE_NAMES),
                },
                "optimizer": {
                    "type": "string",
                    "enum": list(TRAINING_OPTIMIZER_NAMES),
                    "default": "adam",
                },
                "evaluation_option": {
                    "type": "string",
                    "enum": list(TRAINING_EVALUATION_NAMES),
                    "default": "last_epoch",
                },
                "save_checkpoints_every": non_negative_integer_parameter_schema(
                    default=0
                ),
            },
            "required": list(REQUIRED_TRAINING_FIELDS),
            "additionalProperties": False,
        }

    def execute(self, study: Any, **kwargs) -> ToolExecutionResult:
        raise NotImplementedError


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
        return {"type": "object", "properties": {}}

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
        return {"type": "object", "properties": {}}

    def execute(self, study: Any, **kwargs) -> ToolExecutionResult:
        raise NotImplementedError
