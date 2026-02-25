"""Abstract base tool definitions for model training operations.

Each class defines the tool's name, description, and JSON-schema
parameters.  Concrete (mock or real) implementations must override
:meth:`execute`.
"""

from typing import Any

from ..base import BaseTool


class BaseSetModelTool(BaseTool):
    """Set the deep learning model architecture for training.

    Supported architectures include EEGNet, ShallowConvNet,
    DeepConvNet, and SCCNet.
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
                    "enum": ["EEGNet", "ShallowConvNet", "SCCNet"],
                }
            },
            "required": ["model_name"],
        }

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError


class BaseConfigureTrainingTool(BaseTool):
    """Configure training hyperparameters.

    Includes epoch count, batch size, learning rate, optimizer,
    device selection, and checkpoint settings.
    """

    @property
    def name(self) -> str:
        return "configure_training"

    @property
    def description(self) -> str:
        return "Configure training hyperparameters."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "epoch": {"type": "integer"},
                "batch_size": {"type": "integer"},
                "learning_rate": {"type": "number"},
                "repeat": {"type": "integer", "default": 1},
                "device": {"type": "string", "enum": ["cpu", "cuda"]},
                "optimizer": {
                    "type": "string",
                    "enum": ["adam", "sgd", "adamw"],
                    "default": "adam",
                },
                "save_checkpoints_every": {"type": "integer", "default": 0},
            },
            "required": ["epoch", "batch_size", "learning_rate"],
        }

    def execute(self, study: Any, **kwargs) -> str:
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

    def execute(self, study: Any, **kwargs) -> str:
        raise NotImplementedError
