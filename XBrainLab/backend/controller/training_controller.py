"""Training controller for managing model training lifecycle.

Provides a high-level interface for starting, stopping, and monitoring
training runs, as well as querying configuration readiness and
history.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from XBrainLab.backend.study import Study
    from XBrainLab.backend.training import Trainer

from XBrainLab.backend.utils.observer import Observable


class TrainingController(Observable):
    """Controller for training operations and state management.

    Decouples the UI from direct Study/Backend manipulation by
    providing methods for starting/stopping training, monitoring
    progress via a background thread, and querying configuration
    readiness.

    Events:
        training_started: Emitted when a training run begins.
        training_stopped: Emitted when training finishes or is
            interrupted.
        training_updated: Emitted periodically while training is
            in progress (approximately every second).
        config_changed: Emitted when training configuration is
            modified.
        history_cleared: Emitted when the training history is
            cleared.

    Attributes:
        _study: Reference to the :class:`Study` backend instance.
        _monitor_thread: Background thread that polls training status.
        _shutdown_event: Threading event used to signal the monitor
            thread to stop.

    """

    events: ClassVar[list[str]] = [
        "training_started",
        "training_stopped",
        "training_updated",
        "config_changed",
        "history_cleared",
    ]  # Explicitly list events for clarity

    def __init__(self, study: Study):
        """Initialise the training controller.

        Args:
            study: The :class:`Study` backend instance to operate on.

        """
        Observable.__init__(self)
        self._study = study
        self._monitor_thread: threading.Thread | None = None

        self._shutdown_event = threading.Event()

    def is_training(self) -> bool:
        """Check whether a training run is currently in progress.

        Returns:
            ``True`` if training is active, ``False`` otherwise.

        """
        return self._study.is_training()

    def start_training(self) -> None:
        """Generate a training plan and start training.

        Appends to existing plans to preserve history. If training
        is already running, the call is a no-op. A background
        monitoring thread is started automatically.
        """
        if self.is_training():
            return

        # Generate plan (append=True to keep history)
        self._study.generate_plan(force_update=True, append=True)

        # Start training in interactive mode (threaded)
        self._study.train(interact=True)
        self.notify("training_started")

        # Start monitoring
        self._start_monitoring()

    def stop_training(self) -> None:
        """Interrupt the current training process.

        If training is not running, the call is a no-op. The
        monitoring thread will stop naturally once
        :meth:`is_training` returns ``False``.
        """
        if self.is_training():
            self._study.stop_training()
            # Do NOT notify here — let _monitor_loop be the sole emitter
            # of "training_stopped" to avoid duplicate notifications.

    def shutdown(self):
        """Force-stop the monitoring thread.

        Sets the shutdown event and joins the thread with a 1-second
        timeout.
        """
        self._shutdown_event.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)

    def _start_monitoring(self):
        """Start a daemon thread to monitor training progress.

        If a monitoring thread is already running, this method is a
        no-op.
        """
        if self._monitor_thread and self._monitor_thread.is_alive():
            return

        self._shutdown_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def _monitor_loop(self):
        """Poll trainer status and emit ``training_updated`` events.

        Runs in a background thread. Exits when training finishes
        or the shutdown event is set.
        """
        while not self._shutdown_event.is_set():
            if not self.is_training():
                # Training finished naturally or stopped
                self.notify("training_stopped")  # Ensure UI knows it stopped
                break

            # Emit update event
            self.notify("training_updated")

            # Smart Sleep: Wait 1s OR break immediately if shutdown set
            if self._shutdown_event.wait(1.0):
                break

    def clear_history(self) -> None:
        """Clear all training history.

        Raises:
            RuntimeError: If training is currently running.

        """
        if self.is_training():
            raise RuntimeError("Cannot clear history while training is running")

        if self._study.trainer:
            self._study.trainer.clear_history()
            self.notify("history_cleared")

    def get_trainer(self) -> Trainer | None:
        """Return the underlying :class:`Trainer` instance.

        Returns:
            The active trainer, or ``None`` if no trainer exists.

        """
        return self._study.trainer

    def get_formatted_history(self) -> list[dict]:
        """Return structured training history for UI display.

        Each dictionary contains plan/record references and
        display-friendly fields such as group name, run name,
        model name, and active-run indicators.

        Returns:
            A list of dictionaries with the following keys:

            - ``plan``: The :class:`TrainingPlanHolder` instance.
            - ``record``: The :class:`TrainRecord` instance.
            - ``group_name`` (str): Human-readable group label.
            - ``run_name`` (str): Human-readable run label.
            - ``model_name`` (str): Name of the model class.
            - ``is_active`` (bool): Whether this plan is currently
              being trained.
            - ``is_current_run`` (bool): Whether this record is the
              active run within the plan.

        """
        trainer = self._study.trainer
        if not trainer:
            return []

        history = []
        holders = trainer.get_training_plan_holders()

        for plan_idx, plan in enumerate(holders):
            group_id = plan_idx + 1
            model_name = plan.model_holder.target_model.__name__
            is_active_plan = trainer.is_running() and trainer.current_idx == plan_idx

            for run_idx, record in enumerate(plan.get_plans()):
                history.append(
                    {
                        "plan": plan,
                        "record": record,
                        "group_name": f"Group {group_id}",
                        "run_name": f"{run_idx + 1}",
                        "model_name": model_name,
                        "is_active": is_active_plan,
                        "is_current_run": (
                            is_active_plan
                            and plan.get_training_repeat() == record.repeat
                        ),
                    },
                )
        return history

    def validate_ready(self) -> bool:
        """Check whether all prerequisites for training are met.

        Returns:
            ``True`` if datasets, model, and training option are all
            configured.

        """
        return self.has_datasets() and self.has_model() and self.has_training_option()

    def get_missing_requirements(self) -> list[str]:
        """Return a list of missing prerequisites for training.

        Returns:
            Human-readable requirement names that have not been
            configured yet (e.g. ``"Data Splitting"``).

        """
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
        """Check whether any raw data has been loaded.

        Returns:
            ``True`` if the loaded data list is non-empty.

        """
        return bool(self._study.loaded_data_list)

    def has_epoch_data(self) -> bool:
        """Check whether epoch data is available.

        Returns:
            ``True`` if epoch data has been set in the study.

        """
        return self._study.epoch_data is not None

    def get_epoch_data(self) -> Any:
        """Return the current epoch data object.

        Returns:
            The epoch data instance, or ``None`` if not set.

        """
        return self._study.epoch_data

    def has_datasets(self) -> bool:
        """Check whether split datasets are available.

        Returns:
            ``True`` if at least one dataset exists.

        """
        return self._study.datasets is not None and len(self._study.datasets) > 0

    def has_model(self) -> bool:
        """Check whether a model holder has been configured.

        Returns:
            ``True`` if a model holder is set.

        """
        return self._study.model_holder is not None

    def has_training_option(self) -> bool:
        """Check whether a training option has been configured.

        Returns:
            ``True`` if a training option is set.

        """
        return self._study.training_option is not None

    # --- Configuration Methods ---
    def clean_datasets(self, force_update: bool = False) -> None:
        """Remove all split datasets from the study.

        Args:
            force_update: If ``True``, force downstream state updates.

        """
        self._study.clean_datasets(force_update=force_update)

    def apply_data_splitting(self, generator: Any) -> None:
        """Apply a data-splitting strategy to the study.

        Args:
            generator: A splitting generator with an ``apply()``
                method that accepts a :class:`Study`.

        """
        generator.apply(self._study)

    def set_model_holder(self, holder: Any) -> None:
        """Set the model holder in the study.

        Args:
            holder: The model holder instance to use for training.

        """
        self._study.set_model_holder(holder)

    def set_training_option(self, option: Any) -> None:
        """Set the training option (hyper-parameters) in the study.

        Args:
            option: The training option instance.

        """
        self._study.set_training_option(option)

    # --- Data Accessors (for UI decoupling) ---
    def get_training_option(self) -> Any:
        """Return the current training option.

        Returns:
            The training option instance, or ``None``.

        """
        return self._study.training_option

    def get_model_holder(self) -> Any:
        """Return the current model holder.

        Returns:
            The model holder instance, or ``None``.

        """
        return self._study.model_holder

    def get_dataset_generator(self) -> Any:
        """Return the current dataset generator.

        Returns:
            The dataset generator instance, or ``None``.

        """
        return self._study.dataset_generator

    def get_loaded_data_list(self) -> list[Any]:
        """Return the loaded raw data list.

        Returns:
            List of raw data objects.

        """
        return self._study.loaded_data_list

    def get_preprocessed_data_list(self) -> list[Any]:
        """Return the preprocessed data list.

        Returns:
            List of preprocessed data objects.

        """
        return self._study.preprocessed_data_list
