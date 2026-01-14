
from typing import Any, Dict
from ..base import BaseTool

class BaseSetModelTool(BaseTool):
    @property
    def name(self) -> str: return "set_model"
    @property
    def description(self) -> str: return "Set the deep learning model architecture."
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "model_name": {"type": "string", "enum": ["EEGNet", "ShallowConvNet", "DeepConvNet", "SCCNet"]}
            },
            "required": ["model_name"]
        }
    def execute(self, study: Any, **kwargs) -> str: raise NotImplementedError

class BaseConfigureTrainingTool(BaseTool):
    @property
    def name(self) -> str: return "configure_training"
    @property
    def description(self) -> str: return "Configure training hyperparameters."
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "epoch": {"type": "integer"},
                "batch_size": {"type": "integer"},
                "learning_rate": {"type": "number"},
                "repeat": {"type": "integer", "default": 1},
                "device": {"type": "string", "enum": ["cpu", "cuda"]}
            },
            "required": ["epoch", "batch_size", "learning_rate"]
        }
    def execute(self, study: Any, **kwargs) -> str: raise NotImplementedError

class BaseStartTrainingTool(BaseTool):
    @property
    def name(self) -> str: return "start_training"
    @property
    def description(self) -> str: return "Start the training process."
    @property
    def parameters(self) -> Dict[str, Any]: return {"type": "object", "properties": {}}
    def execute(self, study: Any, **kwargs) -> str: raise NotImplementedError
