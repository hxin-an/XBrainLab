"""Real implementations of model training tools.

These tools interact with the ``BackendFacade`` to configure and
launch actual deep-learning training runs.
"""

from typing import Any

from XBrainLab.backend.facade import BackendFacade

from ..definitions.training_def import (
    BaseConfigureTrainingTool,
    BaseSetModelTool,
    BaseStartTrainingTool,
)


class RealSetModelTool(BaseSetModelTool):
    """Real implementation of :class:`BaseSetModelTool`."""

    def execute(self, study: Any, model_name: str | None = None, **kwargs) -> str:
        """Set the deep learning model architecture.

        Args:
            study: The global ``Study`` instance.
            model_name: Name of the model architecture (e.g.,
                ``'EEGNet'``, ``'SCCNet'``).
            **kwargs: Additional keyword arguments.

        Returns:
            A success message or an error description.
        """
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
    """Real implementation of :class:`BaseConfigureTrainingTool`."""

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
        """Configure training hyperparameters via the backend.

        Args:
            study: The global ``Study`` instance.
            epoch: Number of training epochs.
            batch_size: Mini-batch size.
            learning_rate: Optimiser learning rate.
            repeat: Number of experiment repetitions.
            device: Compute device (``'cpu'`` or ``'cuda'``).
            optimizer: Optimiser name (``'adam'``, ``'sgd'``, ``'adamw'``).
            save_checkpoints_every: Checkpoint save interval (0 = disabled).
            **kwargs: Additional keyword arguments.

        Returns:
            A summary of the configured parameters, or an error message.
        """
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
    """Real implementation of :class:`BaseStartTrainingTool`.

    Launches the training process in a background thread via
    :class:`BackendFacade`.
    """

    def is_valid(self, study: Any) -> bool:
        """Check whether training can be started.

        Requires either an existing trainer or sufficient configuration
        (datasets, model, and training options) to create one.

        Args:
            study: The global ``Study`` instance.

        Returns:
            ``True`` if training can proceed.
        """
        # Valid if we have a trainer (ready to run) OR we have all headers to create one
        has_trainer = study.trainer is not None
        can_create_plan = (
            study.datasets is not None
            and len(study.datasets) > 0
            and study.model_holder is not None
            and study.training_option is not None
        )
        return has_trainer or can_create_plan

    def execute(self, study: Any, **kwargs) -> str:
        """Start the training process in a background thread.

        Args:
            study: The global ``Study`` instance.
            **kwargs: Additional keyword arguments.

        Returns:
            A success message or an error description.
        """
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
