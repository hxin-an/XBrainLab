"""Trainer module for managing and executing training plan queues."""

import threading
from enum import Enum

from ..utils import validate_list_type
from ..utils.logger import logger
from .training_plan import TrainingPlanHolder


class Status(Enum):
    """Enumeration of possible trainer states.

    Attributes:
        PENDING: No active training job.
        INIT: Trainer is initializing.
        INTING: An interrupt has been requested.
        TRAIN: Training is in progress (formatted with plan name).
    """

    PENDING = "Pending"
    INIT = "Initializing"
    INTING = "Interrupting"
    TRAIN = "Now training: {}"


class Trainer:
    """Class for storing training options and training models

    Attributes:
        interrupt: bool
            Whether to interrupt training
        progress_text: :class:`Status`
            Training progress
        training_plan_holders: List[:class:`TrainingPlanHolder`]
            List of training plan holders
        job_thread: :class:`threading.Thread`
            Thread for training in background
    """

    def __init__(self, training_plan_holders: list[TrainingPlanHolder]):
        """Initialize the trainer with a list of training plan holders.

        Args:
            training_plan_holders: List of :class:`TrainingPlanHolder` instances
                to be executed sequentially.

        Raises:
            TypeError: If any element is not a :class:`TrainingPlanHolder`.
        """
        validate_list_type(
            training_plan_holders, TrainingPlanHolder, "training_plan_holders"
        )
        self._interrupt = threading.Event()
        self.progress_text: Status | str = Status.PENDING
        self.training_plan_holders = training_plan_holders
        self.current_idx = 0
        self.job_thread: threading.Thread | None = None

    def add_plan(self, plan: TrainingPlanHolder) -> None:
        """Add a new training plan to the queue.

        Args:
            plan: The training plan holder to append.
        """
        self.training_plan_holders.append(plan)

    def add_training_plan_holders(self, plans: list[TrainingPlanHolder]) -> None:
        """Add a list of training plans to the queue.

        Args:
            plans: List of :class:`TrainingPlanHolder` instances to append.
        """
        self.training_plan_holders.extend(plans)

    def clear_history(self) -> None:
        """Clear training history and pending jobs.

        Raises:
            RuntimeError: If training is currently running.
        """
        if self.is_running():
            raise RuntimeError("Cannot clear history while training is running")
        self.training_plan_holders = []
        self.current_idx = 0
        self.progress_text = Status.PENDING

    def job(self) -> None:
        """Execute the training job, iterating through all pending plan holders.

        Runs sequentially through :attr:`training_plan_holders` starting from
        :attr:`current_idx`. Stops early if :attr:`interrupt` is set. On
        exception, logs the error and updates :attr:`progress_text`.
        """
        try:
            while self.current_idx < len(self.training_plan_holders):
                if self._interrupt.is_set():
                    break

                plan_holder = self.training_plan_holders[self.current_idx]
                self.progress_text = Status.TRAIN.value.format(plan_holder.get_name())

                plan_holder.train()

                self.current_idx += 1
        except Exception as e:
            error_msg = f"Training thread crashed: {e}"
            logger.error(error_msg, exc_info=True)
            self.progress_text = f"Error: {e}"
        finally:
            if not isinstance(
                self.progress_text, str
            ) or not self.progress_text.startswith("Error"):
                self.progress_text = Status.PENDING
            self.job_thread = None

    def run(self, interact: bool = False) -> None:
        """Start executing the training job.

        Args:
            interact: If ``True``, run the job in a background thread.
                If ``False``, run synchronously in the current thread.
        """
        if self.is_running():
            return

        self.clear_interrupt()
        if interact:
            self.job_thread = threading.Thread(target=self.job)
            self.job_thread.start()
        else:
            self.job()

    def get_progress_text(self) -> str:
        """Return a string representation of the current training progress.

        Returns:
            The current status or progress message.
        """
        if isinstance(self.progress_text, Status):
            return self.progress_text.value
        return self.progress_text

    def is_running(self) -> bool:
        """Check whether a training job is currently running.

        Returns:
            ``True`` if the background job thread is alive, ``False`` otherwise.
        """
        return self.job_thread is not None and self.job_thread.is_alive()

    def clean(self, force_update: bool = False) -> None:
        """Stop and clean up the training job.

        Args:
            force_update: If ``True``, forcefully interrupt training.
                If ``False``, raises an error when training is still running.

        Raises:
            RuntimeError: If training is still in progress and
                ``force_update`` is ``False``.
        """
        if force_update:
            self.set_interrupt()
        elif self.is_running():
            raise RuntimeError("Training still in progress")

    def get_training_plan_holders(self) -> list[TrainingPlanHolder]:
        """Return the list of all training plan holders.

        Returns:
            List of :class:`TrainingPlanHolder` instances.
        """
        return self.training_plan_holders

    @property
    def interrupt(self) -> bool:
        """Whether an interrupt has been requested (thread-safe)."""
        return self._interrupt.is_set()

    def set_interrupt(self) -> None:
        """Set the interrupt flag and propagate to all plan holders."""
        self._interrupt.set()
        self.progress_text = Status.INTING
        for holder in self.training_plan_holders:
            holder.set_interrupt()

    def clear_interrupt(self) -> None:
        """Clear the interrupt flag and propagate to all plan holders."""
        self._interrupt.clear()
        self.progress_text = Status.PENDING
        for holder in self.training_plan_holders:
            holder.clear_interrupt()

    def get_real_training_plan(self, plan_name: str, real_plan_name: str):
        """Retrieve a specific :class:`TrainRecord` from a named plan holder.

        Args:
            plan_name: The name of the :class:`TrainingPlanHolder`.
            real_plan_name: The name of the :class:`TrainRecord` within the holder.

        Returns:
            The matching :class:`TrainRecord` instance.

        Raises:
            ValueError: If the plan holder or the train record cannot be found.
        """
        for holder in self.training_plan_holders:
            if holder.get_name() == plan_name:
                for plan in holder.get_plans():
                    if plan.get_name() == real_plan_name:
                        return plan
                raise ValueError(f"Cannot find real plan {real_plan_name}")
        raise ValueError(f"Cannot find training plan {plan_name}")
