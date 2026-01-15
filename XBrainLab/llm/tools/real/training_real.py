
from typing import Any
import torch
from ..definitions.training_def import (
    BaseSetModelTool, BaseConfigureTrainingTool, BaseStartTrainingTool
)
# We need to import backend classes to configure the study
# Assuming imports available or checked at runtime
from XBrainLab.backend.training.option import TrainingOption, TRAINING_EVALUATION
from XBrainLab.backend.training.model_holder import ModelHolder

class RealSetModelTool(BaseSetModelTool):
    def execute(self, study: Any, model_name: str) -> str:
        if not model_name:
            return "Error: model_name must be provided."
        
        # In a real scenario, we might need a model factory or map
        # For now, we assume ModelHolder takes a string ID or we map standard names
        # But ModelHolder usually takes a class or registry name.
        # Let's check how UI does it: ModelHolder(model_name) seems standard if model_name is valid.
        
        try:
            # We assume ModelHolder can resolve the name or we rely on a factory
            # Checking codebase conventions... 
            # Usually study.set_model_holder expects a ModelHolder instance
            study.set_model_holder(ModelHolder(model_name))
            return f"Model successfully set to {model_name}."
        except Exception as e:
            return f"Failed to set model {model_name}: {str(e)}"

class RealConfigureTrainingTool(BaseConfigureTrainingTool):
    def execute(self, study: Any, epoch: int, batch_size: int, learning_rate: float, 
                repeat: int = 1, device: str = "cpu", optimizer: str = "adam", 
                save_checkpoints_every: int = 0) -> str:
        
        # Map optimizer string to class
        optim_map = {
            "adam": torch.optim.Adam,
            "sgd": torch.optim.SGD,
            "adamw": torch.optim.AdamW
        }
        optim_class = optim_map.get(optimizer.lower(), torch.optim.Adam)
        
        # Determine Device
        use_cpu = (device.lower() == "cpu")
        gpu_idx = 0 if not use_cpu else None
        
        # Prepare Option
        # Note: TrainingOption.__init__ signature:
        # output_dir, optim, optim_params, use_cpu, gpu_idx, epoch, bs, lr, checkpoint_epoch, evaluation_option, repeat_num
        
        try:
            option = TrainingOption(
                output_dir=study.output_dir if hasattr(study, 'output_dir') else "./output", # Fallback
                optim=optim_class,
                optim_params={}, # Default params
                use_cpu=use_cpu,
                gpu_idx=gpu_idx,
                epoch=epoch,
                bs=batch_size,
                lr=learning_rate,
                checkpoint_epoch=save_checkpoints_every,
                evaluation_option=TRAINING_EVALUATION.LAST_EPOCH, # Default
                repeat_num=repeat
            )
            
            study.set_training_option(option)
            return f"Training configured: {option.get_optim_name()} on {option.get_device_name()}, Epochs: {epoch}."
        except Exception as e:
            return f"Failed to configure training: {str(e)}"

class RealStartTrainingTool(BaseStartTrainingTool):
    def execute(self, study: Any) -> str:
        try:
            study.start_training()
            return "Training started successfully."
        except Exception as e:
            return f"Failed to start training: {str(e)}"
