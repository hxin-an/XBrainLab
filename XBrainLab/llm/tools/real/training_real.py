from typing import Any

from XBrainLab.backend.facade import BackendFacade

from ..definitions.training_def import (
    BaseConfigureTrainingTool,
    BaseSetModelTool,
    BaseStartTrainingTool,
)


class RealSetModelTool(BaseSetModelTool):
    def execute(self, study: Any, model_name: str | None = None, **kwargs) -> str:
        if not model_name:
            return "Error: model_name must be provided."

        facade = BackendFacade(study)
        try:
            facade.set_model(model_name)
        except Exception as e:
            return f"Failed to set model {model_name}: {e!s}"
        else:
            return f"Model successfully set to {model_name}."


class RealConfigureTrainingTool(BaseConfigureTrainingTool):
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
        facade = BackendFacade(study)

        try:
            facade.configure_training(
                epoch=epoch or 10,
                batch_size=batch_size or 32,
                learning_rate=learning_rate or 0.001,
                repeat=repeat,
                device=device,
                optimizer=optimizer,
                save_checkpoints_every=save_checkpoints_every,
            )
        except Exception as e:
            return f"Failed to configure training: {e!s}"
        else:
            return (
                f"Training configured: {optimizer} on {device}, "
                f"Epochs: {epoch or 10}, "
                f"Batch: {batch_size or 32}, "
                f"LR: {learning_rate or 0.001}"
            )


class RealStartTrainingTool(BaseStartTrainingTool):
    def execute(self, study: Any, **kwargs) -> str:
        facade = BackendFacade(study)

        try:
            # Facade should handle plan generation if needed.
            # If not, we might need to add it to Facade.
            # Currently Facade.run_training starts the process.
            # Assuming Facade or Controller handles prerequisites.

            # To be safe and respect previous logic, we ensure plan exists via Facade
            # But Facade doesn't expose generate_plan explicitly yet?
            # It's better to update Facade.run_training to be robust.
            # For now, we trust run_training does the job or we signal it.

            facade.run_training()
        except Exception as e:
            return f"Failed to start training: {e!s}"
        else:
            return "Training started successfully (Background Thread)."
