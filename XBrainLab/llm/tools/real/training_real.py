from typing import Any

from XBrainLab.backend.training.model_holder import ModelHolder
from XBrainLab.backend.training.option import TRAINING_EVALUATION, TrainingOption

from ..definitions.training_def import (
    BaseConfigureTrainingTool,
    BaseSetModelTool,
    BaseStartTrainingTool,
)
from .registry import ToolRegistry


class RealSetModelTool(BaseSetModelTool):
    def execute(self, study: Any, model_name: str) -> str:
        if not model_name:
            return "Error: model_name must be provided."

        model_class = ToolRegistry.get_model_class(model_name)
        if not model_class:
            return (
                f"Error: Unknown model '{model_name}'. "
                f"Supported: {list(ToolRegistry._MODELS.keys())}"
            )

        try:
            # Create ModelHolder with the resolved class
            # Note: We might need default params or empty dict if not provided by tool
            # Current BaseSetModelTool doesn't accept params via LLM yet,
            # usually assumes defaults
            holder = ModelHolder(model_class, model_params_map={})
            study.set_model_holder(holder)
        except Exception as e:
            return f"Failed to set model {model_name}: {e!s}"

        return f"Model successfully set to {model_name}."


class RealConfigureTrainingTool(BaseConfigureTrainingTool):
    def execute(
        self,
        study: Any,
        epoch: int,
        batch_size: int,
        learning_rate: float,
        repeat: int = 1,
        device: str = "cpu",
        optimizer: str = "adam",
        save_checkpoints_every: int = 0,
    ) -> str:
        optim_class = ToolRegistry.get_optimizer_class(optimizer)

        # Determine Device
        use_cpu = device.lower() == "cpu"
        gpu_idx = 0 if not use_cpu else None

        try:
            option = TrainingOption(
                output_dir=getattr(study, "output_dir", "./output"),  # Fallback
                optim=optim_class,
                optim_params={},  # Default params
                use_cpu=use_cpu,
                gpu_idx=gpu_idx,
                epoch=epoch,
                bs=batch_size,
                lr=learning_rate,
                checkpoint_epoch=save_checkpoints_every,
                evaluation_option=TRAINING_EVALUATION.LAST_EPOCH,  # Default
                repeat_num=repeat,
            )

            study.set_training_option(option)
        except Exception as e:
            return f"Failed to configure training: {e!s}"

        return (
            f"Training configured: {option.get_optim_name()} on "
            f"{option.get_device_name()}, Epochs: {epoch}."
        )


class RealStartTrainingTool(BaseStartTrainingTool):
    def execute(self, study: Any) -> str:
        try:
            # 1. Generate Plan (Backend requirement)
            # append=True allows adding to existing experiments if needed,
            # but usually for a new run we might want clean state?
            # Controller uses append=True. Let's stick to generating a fresh plan
            # if none exists?
            # Safe default: force_update=True to ensure consistency with
            # current settings
            study.generate_plan(force_update=True)

            # 2. Start Training
            # interact=True allows running in a separate thread
            # (non-blocking for UI/Agent)
            study.train(interact=True)

        except Exception as e:
            return f"Failed to start training: {e!s}"

        return "Training started successfully (Background Thread)."
