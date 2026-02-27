"""Training lifecycle management for model config, plan generation, and execution."""

from .training import ModelHolder, Trainer, TrainingOption, TrainingPlanHolder
from .utils import validate_type
from .utils.logger import logger


class TrainingManager:
    """Manages the training lifecycle: model holder, option, plan, and execution.

    Extracted from the monolithic Study class, following the same pattern as
    :class:`DataManager`.

    Attributes:
        model_holder: The model with parameters, or None.
        training_option: The training option, or None.
        trainer: The model trainer, or None.
        saliency_params: Parameters for saliency computation, or None.

    """

    def __init__(self) -> None:
        self.model_holder: ModelHolder | None = None
        self.training_option: TrainingOption | None = None
        self.trainer: Trainer | None = None
        self.saliency_params: dict | None = None

    # --- Configuration ---

    def set_training_option(
        self,
        training_option: TrainingOption,
        force_update: bool = False,
    ) -> None:
        """Set training option.

        Args:
            training_option: The training option to set.
            force_update: Whether to force update.

        """
        validate_type(training_option, TrainingOption, "training_option")
        # Do not clean trainer here to allow multi-experiment history
        self.training_option = training_option

    def set_model_holder(
        self,
        model_holder: ModelHolder,
        force_update: bool = False,
    ) -> None:
        """Set model holder.

        Args:
            model_holder: The model holder to set.
            force_update: Whether to force update.

        """
        validate_type(model_holder, ModelHolder, "model_holder")
        # Do not clean trainer here to allow multi-experiment history
        self.model_holder = model_holder

    # --- Plan Generation ---

    def generate_plan(
        self,
        datasets: list,
        force_update: bool = False,
        append: bool = False,
    ) -> None:
        """Generate training plan based on current configuration.

        Args:
            datasets: List of datasets to create plans from.
            force_update: Whether to clear existing plan.
            append: Whether to append to existing plan.

        """
        if not append:
            self.clean_trainer(force_update=force_update)

        if not datasets:
            raise ValueError("No valid dataset is generated")
        if not self.training_option:
            raise ValueError("No valid training option is generated")
        if not self.model_holder:
            raise ValueError("No valid model holder is generated")

        option = self.training_option
        model_holder = self.model_holder
        training_plan_holders = [
            TrainingPlanHolder(model_holder, dataset, option, self.saliency_params)
            for dataset in datasets
        ]

        if append and self.trainer:
            self.trainer.add_training_plan_holders(training_plan_holders)
            logger.info("Appended %s training plans", len(training_plan_holders))
        else:
            self.trainer = Trainer(training_plan_holders)
            logger.info("Generated training plan")

    # --- Execution ---

    def train(self, interact: bool = False) -> None:
        """Start training process.

        Args:
            interact: Whether to run interactively.

        """
        if not self.trainer:
            raise ValueError("No valid trainer is generated")

        self.trainer.run(interact=interact)
        logger.info("Started training (interact=%s)", interact)

    def stop_training(self) -> None:
        """Stop training execution."""
        if not self.trainer:
            raise ValueError("No valid trainer is generated")
        self.trainer.set_interrupt()
        logger.info("Stopped training")

    def is_training(self) -> bool:
        """Return whether training is currently running."""
        if self.trainer:
            return self.trainer.is_running()
        return False

    # --- Evaluation Helpers ---

    def export_output_csv(self, filepath: str, plan_name: str, real_plan_name: str):
        """Export model inference output to csv file.

        Args:
            filepath: Path to save the CSV.
            plan_name: Name of the plan.
            real_plan_name: Real name of the plan.

        """
        if not self.trainer:
            raise ValueError("No valid training plan is generated")
        plan = self.trainer.get_real_training_plan(plan_name, real_plan_name)
        record = plan.get_eval_record()
        if not record:
            raise ValueError("No evaluation record for this training plan")
        record.export_csv(filepath)

    # --- Saliency ---

    def get_saliency_params(self) -> dict | None:
        """Return parameters for saliency computation."""
        return self.saliency_params

    def set_saliency_params(self, saliency_params) -> None:
        """Set saliency parameters for saliency computation."""
        self.saliency_params = saliency_params
        if self.trainer:
            for training_plan_holder in self.trainer.get_training_plan_holders():
                training_plan_holder.set_saliency_params(saliency_params)

    # --- State Queries ---

    def has_trainer(self) -> bool:
        """Return whether a trainer is configured."""
        return self.trainer is not None

    # --- Cleanup ---

    def clean_trainer(self, force_update: bool = True) -> None:
        """Clean the trainer.

        Args:
            force_update: If ``False``, raises when a trainer exists.

        """
        if not force_update and self.has_trainer():
            raise ValueError(
                "This step has already been done, "
                "all following data will be removed if you reset this step.\n"
                "Please clean_trainer first.",
            )
        if self.trainer:
            self.trainer.clean(force_update=force_update)
        self.trainer = None
