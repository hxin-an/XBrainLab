from typing import List, Optional, Any
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import Trainer, TrainingPlanHolder

class TrainingController:
    """
    Controller for handling training operations and state management.
    Decouples UI from direct Study/Backend manipulation.
    """
    def __init__(self, study: Study):
        self._study = study

    def is_training(self) -> bool:
        """Check if training is currently in progress."""
        return self._study.is_training()

    def start_training(self) -> None:
        """
        Generate training plan and start training.
        Appends to existing plans to preserve history.
        """
        if self.is_training():
            return
            
        # Generate plan (append=True to keep history)
        self._study.generate_plan(force_update=True, append=True)
        
        # Start training in interactive mode (threaded)
        self._study.train(interact=True)

    def stop_training(self) -> None:
        """Interrupt the current training process."""
        if self.is_training():
            self._study.stop_training()

    def clear_history(self) -> None:
        """Clear all training history."""
        if self.is_training():
            raise RuntimeError("Cannot clear history while training is running")
            
        if self._study.trainer:
            self._study.trainer.clear_history()

    def get_trainer(self) -> Optional[Trainer]:
        """Access the underlying trainer (usually for polling status)."""
        return self._study.trainer

    def get_formatted_history(self) -> List[dict]:
        """
        Get structured training history for UI display.
        Returns a list of dictionaries suitable for table display.
        """
        trainer = self._study.trainer
        if not trainer:
            return []

        history = []
        holders = trainer.get_training_plan_holders()
        
        for plan_idx, plan in enumerate(holders):
            group_id = plan_idx + 1
            model_name = plan.model_holder.target_model.__name__
            is_active_plan = (trainer.is_running() and trainer.current_idx == plan_idx)

            for run_idx, record in enumerate(plan.get_plans()):
                history.append({
                    'plan': plan,
                    'record': record,
                    'group_name': f"Group {group_id}",
                    'run_name': f"{run_idx + 1}",
                    'model_name': model_name,
                    'is_active': is_active_plan,
                    'is_current_run': (is_active_plan and plan.get_training_repeat() == record.repeat)
                })
        return history

    def validate_ready(self) -> bool:
        """Check if configuration is ready for training."""
        return (
            self.has_datasets() and
            self.has_model() and
            self.has_training_option()
        )

    def get_missing_requirements(self) -> List[str]:
        """Get a list of missing requirements for training."""
        missing = []
        if not self.has_datasets():
            missing.append("Data Splitting")
        if not self.has_model():
            missing.append("Model Selection")
        if not self.has_training_option():
            missing.append("Training Settings")
        return missing

    # --- State Queries ---
    def has_loaded_data(self) -> bool:
        return bool(self._study.loaded_data_list)

    def has_epoch_data(self) -> bool:
        return self._study.epoch_data is not None

    def get_epoch_data(self) -> Any:
        return self._study.epoch_data

    def has_datasets(self) -> bool:
        return self._study.datasets is not None and len(self._study.datasets) > 0

    def has_model(self) -> bool:
        return self._study.model_holder is not None

    def has_training_option(self) -> bool:
        return self._study.training_option is not None

    # --- Configuration Methods ---
    def clean_datasets(self, force_update: bool = False) -> None:
        self._study.clean_datasets(force_update=force_update)

    def apply_data_splitting(self, generator: Any) -> None:
        """Apply data splitting strategy using the provided generator."""
        generator.apply(self._study)

    def set_model_holder(self, holder: Any) -> None:
        self._study.set_model_holder(holder)

    def set_training_option(self, option: Any) -> None:
        self._study.set_training_option(option)
