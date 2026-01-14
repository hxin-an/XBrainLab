
from typing import Any
from ..definitions.training_def import (
    BaseSetModelTool, BaseConfigureTrainingTool, BaseStartTrainingTool
)

class MockSetModelTool(BaseSetModelTool):
    def execute(self, study: Any, model_name: str) -> str:
        return f"Model set to {model_name}."

class MockConfigureTrainingTool(BaseConfigureTrainingTool):
    def execute(self, study: Any, epoch: int, batch_size: int, learning_rate: float, 
                repeat: int = 1, device: str = "cpu") -> str:
        return f"Training configured (Epochs: {epoch}, LR: {learning_rate}, Device: {device})."

class MockStartTrainingTool(BaseStartTrainingTool):
    def execute(self, study: Any) -> str:
        return "Training started. (Mock: Training completed successfully.)"
