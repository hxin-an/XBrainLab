from typing import Any

from ..definitions.training_def import (
    BaseConfigureTrainingTool,
    BaseSetModelTool,
    BaseStartTrainingTool,
)


class MockSetModelTool(BaseSetModelTool):
    def execute(self, study: Any, model_name: str | None = None, **kwargs) -> str:
        if model_name is None:
            return "Error: model_name is required"
        return f"Model set to {model_name}."


class MockConfigureTrainingTool(BaseConfigureTrainingTool):
    def execute(
        self,
        study: Any,
        epoch: int | None = None,
        batch_size: int | None = None,
        learning_rate: float | None = None,
        repeat: int = 1,
        device: str = "cpu",
        optimizer: str = "adam",
        save_checkpoints_every: int = 0,
        **kwargs,
    ) -> str:
        if epoch is None or batch_size is None or learning_rate is None:
            return "Error: epoch, batch_size, and learning_rate are required"
        return (
            f"Training configured (Epochs: {epoch}, LR: {learning_rate}, Device: "
            f"{device}, Optim: {optimizer}, Ckt: {save_checkpoints_every})."
        )


class MockStartTrainingTool(BaseStartTrainingTool):
    def execute(self, study: Any, **kwargs) -> str:
        return "Training started. (Mock: Training completed successfully.)"
