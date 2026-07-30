"""Training controller for managing model training lifecycle.

Provides a high-level interface for starting, stopping, and monitoring
training runs, as well as querying configuration readiness and
history.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from XBrainLab.backend.study import Study
    from XBrainLab.backend.training import Trainer

from XBrainLab.backend.training_state_contract import (
    TrainingStateToken,
    TrainingTerminalOutcome,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.observer import Observable


@dataclass(frozen=True, slots=True)
class TrainingLifecycleEvent:
    """Generation-bound training truth safe to reconcile after Qt queuing."""

    token: TrainingStateToken
    outcome: TrainingTerminalOutcome
    publication_generation: int | None = None
    publication_revision: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.token, TrainingStateToken):
            raise TypeError("training lifecycle token is invalid")
        if not isinstance(self.outcome, TrainingTerminalOutcome):
            raise TypeError("training lifecycle outcome is invalid")
        generation = self.publication_generation
        if generation is not None and (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation < 1
        ):
            raise TypeError(
                "training lifecycle publication generation must be positive"
            )
        revision = self.publication_revision
        if revision is not None and (
            isinstance(revision, bool) or not isinstance(revision, int) or revision < 1
        ):
            raise TypeError("training lifecycle publication revision must be positive")


class _TerminalHandoffPhase(str, Enum):
    PENDING = "pending"
    NOTIFIED = "notified"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class _TerminalHandoff:
    """Completion state for one exact controller-admitted training run."""

    generation: int
    complete: threading.Event = field(default_factory=threading.Event)
    phase: _TerminalHandoffPhase = _TerminalHandoffPhase.PENDING
    detail: str | None = None


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
        "training_started_state",
        "training_stopped",
        "training_terminal_published",
        "training_analysis_published",
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
        self._terminal_handoff_lock = threading.Lock()
        self._terminal_handoff_sequence = 0
        self._active_terminal_handoff: int | None = None
        self._terminal_handoffs: dict[int, _TerminalHandoff] = {}

    def is_training(self) -> bool:
        """Check whether a training run is currently in progress.

        Returns:
            ``True`` if training is active, ``False`` otherwise.

        """
        return self._study.is_training()

    def start_training(self, *, append: bool = True, interactive: bool = True) -> int:
        """Generate a training plan and start training.

        Appends to existing plans to preserve history. An already-running
        training lifecycle is rejected so a second command cannot reuse its
        terminal handoff identity. A background monitoring thread is started
        automatically.
        """
        if self.is_training():
            raise RuntimeError("Training is already running")

        self._retire_previous_monitor()
        handoff = self._reserve_terminal_handoff()

        try:
            self._study.generate_plan(force_update=True, append=append)
            if interactive:
                self._study.train(interact=True)
                lifecycle = self._lifecycle_event()
                if lifecycle is not None:
                    self.notify("training_started_state", lifecycle)
                self.notify("training_started")
                self._start_monitoring(handoff.generation)
                return handoff.generation

            self.notify("training_started")
            try:
                self._study.train(interact=False)
            finally:
                self._publish_training_stopped(handoff.generation)
        except BaseException as exc:
            self._complete_terminal_handoff(
                handoff.generation,
                phase=_TerminalHandoffPhase.FAILED,
                detail=f"Training start failed: {type(exc).__name__}: {exc}",
            )
            raise
        return handoff.generation

    def _lifecycle_event(self) -> TrainingLifecycleEvent | None:
        """Capture one typed token/outcome pair for non-ordering UI consumers."""
        trainer = getattr(self._study, "trainer", None)
        get_token = getattr(trainer, "get_state_snapshot_token", None)
        get_outcome = getattr(trainer, "get_terminal_outcome", None)
        if not callable(get_token) or not callable(get_outcome):
            return None
        try:
            token = get_token()
            outcome = get_outcome()
        except Exception:
            return None
        if not isinstance(token, TrainingStateToken) or not isinstance(
            outcome,
            TrainingTerminalOutcome,
        ):
            return None
        return TrainingLifecycleEvent(token=token, outcome=outcome)

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
        self.cancel_terminal_notification_waits(
            "Training monitoring stopped during application shutdown."
        )

    def wait_for_terminal_notification(
        self,
        generation: int | None = None,
        *,
        timeout: float | None = None,
    ) -> bool:
        """Wait for callbacks from one exact controller-admitted training run."""
        with self._terminal_handoff_lock:
            target_generation = (
                self._terminal_handoff_sequence if generation is None else generation
            )
            if target_generation == 0:
                return True
            handoff = self._terminal_handoffs.get(target_generation)
        if handoff is None or not handoff.complete.wait(timeout=timeout):
            return False
        with self._terminal_handoff_lock:
            current = self._terminal_handoffs.get(target_generation)
            return (
                current is not None
                and current is handoff
                and current.phase is _TerminalHandoffPhase.NOTIFIED
            )

    def wait_until_restart_safe(self, *, timeout: float | None = None) -> bool:
        """Wait until the previous monitor can no longer overlap a new run.

        Call this boundary without the application command lock. The monitor
        publishes terminal state through that lock before it exits.
        """
        if self._study.is_training():
            return False

        deadline = None if timeout is None else monotonic() + max(0.0, timeout)

        def remaining() -> float | None:
            if deadline is None:
                return None
            return max(0.0, deadline - monotonic())

        with self._terminal_handoff_lock:
            active_generation = self._active_terminal_handoff
            handoff = (
                self._terminal_handoffs.get(active_generation)
                if active_generation is not None
                else None
            )
        if handoff is not None and not handoff.complete.wait(timeout=remaining()):
            return False

        thread = self._monitor_thread
        if thread is None:
            return True
        if thread is threading.current_thread():
            return False
        if thread.is_alive():
            thread.join(timeout=remaining())
        if thread.is_alive():
            return False
        if self._monitor_thread is thread:
            self._monitor_thread = None
        return True

    def cancel_terminal_notification_waits(self, reason: str) -> None:
        """Wake pending lifecycle waiters without reporting a terminal delivery."""
        detail = str(reason).strip() or "Training terminal notification was cancelled."
        with self._terminal_handoff_lock:
            pending = [
                handoff
                for handoff in self._terminal_handoffs.values()
                if handoff.phase is _TerminalHandoffPhase.PENDING
            ]
            for handoff in pending:
                handoff.phase = _TerminalHandoffPhase.CANCELLED
                handoff.detail = detail
                handoff.complete.set()
                if self._active_terminal_handoff == handoff.generation:
                    self._active_terminal_handoff = None

    def _start_monitoring(self, generation: int):
        """Start a daemon thread to monitor training progress.

        A previous monitor must be fully retired before a new run is admitted.
        """
        if self._monitor_thread and self._monitor_thread.is_alive():
            raise RuntimeError("The previous training monitor is still shutting down")

        self._shutdown_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(generation,),
            daemon=True,
        )
        self._monitor_thread.start()

    def _monitor_loop(self, generation: int):
        """Poll trainer status and emit ``training_updated`` events.

        Runs in a background thread. Exits when training finishes
        or the shutdown event is set.
        """
        terminal_attempted = False
        try:
            while not self._shutdown_event.is_set():
                if not self.is_training():
                    terminal_attempted = True
                    self._publish_training_stopped(generation)
                    return

                self.notify("training_updated")
                if self._shutdown_event.wait(1.0):
                    return
        except BaseException as exc:
            logger.exception("Training monitor failed")
            self._complete_terminal_handoff(
                generation,
                phase=_TerminalHandoffPhase.FAILED,
                detail=f"Training monitor failed: {type(exc).__name__}: {exc}",
            )
        finally:
            if not terminal_attempted:
                phase = (
                    _TerminalHandoffPhase.CANCELLED
                    if self._shutdown_event.is_set()
                    else _TerminalHandoffPhase.FAILED
                )
                self._complete_terminal_handoff(
                    generation,
                    phase=phase,
                    detail=(
                        "Training monitor stopped before terminal notification."
                        if phase is _TerminalHandoffPhase.CANCELLED
                        else "Training monitor exited before terminal notification."
                    ),
                )

    def _publish_training_stopped(self, generation: int) -> bool:
        """Attempt terminal callbacks before completing one exact handoff."""
        try:
            delivered = self.notify("training_stopped")
        except BaseException as exc:
            logger.exception("Training terminal notification failed")
            self._complete_terminal_handoff(
                generation,
                phase=_TerminalHandoffPhase.FAILED,
                detail=f"Terminal notification failed: {type(exc).__name__}: {exc}",
            )
            return False
        self._complete_terminal_handoff(
            generation,
            phase=_TerminalHandoffPhase.NOTIFIED,
            detail=(
                None
                if delivered
                else "One or more terminal observers requested publication retry."
            ),
        )
        return delivered

    def _reserve_terminal_handoff(self) -> _TerminalHandoff:
        with self._terminal_handoff_lock:
            active_generation = self._active_terminal_handoff
            if active_generation is not None:
                active = self._terminal_handoffs.get(active_generation)
                if active is not None and active.phase is _TerminalHandoffPhase.PENDING:
                    raise RuntimeError(
                        "The previous training terminal handoff is still pending"
                    )
            self._terminal_handoff_sequence += 1
            handoff = _TerminalHandoff(generation=self._terminal_handoff_sequence)
            self._terminal_handoffs[handoff.generation] = handoff
            self._active_terminal_handoff = handoff.generation
            self._prune_terminal_handoffs_locked()
            return handoff

    def _complete_terminal_handoff(
        self,
        generation: int,
        *,
        phase: _TerminalHandoffPhase,
        detail: str | None,
    ) -> None:
        with self._terminal_handoff_lock:
            handoff = self._terminal_handoffs.get(generation)
            if handoff is None or handoff.phase is not _TerminalHandoffPhase.PENDING:
                return
            handoff.phase = phase
            handoff.detail = detail
            handoff.complete.set()
            if self._active_terminal_handoff == generation:
                self._active_terminal_handoff = None

    def _retire_previous_monitor(self) -> None:
        thread = self._monitor_thread
        if thread is None or not thread.is_alive():
            return
        thread.join(timeout=1.0)
        if thread.is_alive():
            raise RuntimeError("The previous training monitor is still shutting down")

    def _prune_terminal_handoffs_locked(self) -> None:
        completed = [
            generation
            for generation, handoff in self._terminal_handoffs.items()
            if handoff.phase is not _TerminalHandoffPhase.PENDING
        ]
        for generation in completed[:-32]:
            self._terminal_handoffs.pop(generation, None)

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

    def get_progress_text(self) -> str:
        """Return the active trainer progress text, if available."""
        trainer = self._study.trainer
        if trainer is None or not hasattr(trainer, "get_progress_text"):
            return ""
        try:
            progress = trainer.get_progress_text()
        except Exception:
            return ""
        return str(progress or "")

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
        self.notify("config_changed")

    def set_model_holder(self, holder: Any) -> None:
        """Set the model holder in the study.

        Args:
            holder: The model holder instance to use for training.

        """
        self._study.set_model_holder(holder)
        self.notify("config_changed")

    def set_training_option(self, option: Any) -> None:
        """Set the training option (hyper-parameters) in the study.

        Args:
            option: The training option instance.

        """
        self._study.set_training_option(option)
        self.notify("config_changed")

    def apply_configuration(
        self,
        *,
        model_holder: Any | None,
        training_option: Any | None,
        update_model: bool,
        update_option: bool,
    ) -> None:
        """Apply one validated configuration and publish one observer event."""
        self._study.apply_training_configuration(
            model_holder=model_holder,
            training_option=training_option,
            update_model=update_model,
            update_option=update_option,
        )
        self.notify("config_changed")

    # --- Data Accessors (for UI decoupling) ---
    def get_training_option(self) -> Any:
        """Return the current training option.

        Returns:
            The training option instance, or ``None``.

        """
        return self._study.training_option

    def get_resource_preflight_context(self) -> dict[str, Any]:
        """Return runtime objects needed for resource preflight estimates."""
        return {
            "datasets": list(getattr(self._study, "datasets", []) or []),
            "training_option": getattr(self._study, "training_option", None),
            "model_holder": getattr(self._study, "model_holder", None),
        }

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
