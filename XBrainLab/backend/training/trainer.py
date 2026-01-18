import threading
from enum import Enum

from ..utils import validate_list_type
from .training_plan import TrainingPlanHolder


class Status(Enum):
    """Utility class for training status"""

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
        validate_list_type(
            training_plan_holders, TrainingPlanHolder, "training_plan_holders"
        )
        self.interrupt = False
        self.progress_text: Status | str = Status.PENDING
        self.training_plan_holders = training_plan_holders
        self.current_idx = 0
        self.job_thread: threading.Thread | None = None

    def add_plan(self, plan: TrainingPlanHolder) -> None:
        """Add a new training plan to the queue"""
        self.training_plan_holders.append(plan)

    def add_training_plan_holders(self, plans: list[TrainingPlanHolder]) -> None:
        """Add a list of training plans to the queue"""
        self.training_plan_holders.extend(plans)

    def clear_history(self) -> None:
        """Clear training history and pending jobs"""
        if self.is_running():
            raise RuntimeError("Cannot clear history while training is running")
        self.training_plan_holders = []
        self.current_idx = 0
        self.progress_text = Status.PENDING

    def job(self) -> None:
        """Training job running in background"""
        while self.current_idx < len(self.training_plan_holders):
            if self.interrupt:
                break

            plan_holder = self.training_plan_holders[self.current_idx]
            self.progress_text = Status.TRAIN.value.format(plan_holder.get_name())

            plan_holder.train()

            self.current_idx += 1

        self.progress_text = Status.PENDING
        self.job_thread = None

    def run(self, interact: bool = False) -> None:
        """Run training job

        Parameters:
            interact: bool
                Whether to run training in background
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
        """Return string representation of training progress"""
        if isinstance(self.progress_text, Status):
            return self.progress_text.value
        return self.progress_text

    def is_running(self) -> bool:
        """Return whether training is running"""
        return self.job_thread is not None and self.job_thread.is_alive()

    def clean(self, force_update: bool = False) -> None:
        """Stop and clean training job

        Parameters:
            force_update: bool
                Whether to force update

        Raises:
            ValueError: If training is still in progress and
                        :attr:`force_update` is False
        """
        if force_update:
            self.set_interrupt()
        elif self.is_running():
            raise RuntimeError("Training still in progress")

    def get_training_plan_holders(self) -> list[TrainingPlanHolder]:
        """Get list of training plan holders"""
        return self.training_plan_holders

    def set_interrupt(self) -> None:
        """Set interrupt flag"""
        self.interrupt = True
        self.progress_text = Status.INTING
        for holder in self.training_plan_holders:
            holder.set_interrupt()

    def clear_interrupt(self) -> None:
        """Clear interrupt flag"""
        self.interrupt = False
        self.progress_text = Status.PENDING
        for holder in self.training_plan_holders:
            holder.clear_interrupt()

    def get_real_training_plan(self, plan_name: str, real_plan_name: str):
        """Get the real training plan (TrainRecord) from the holder"""
        for holder in self.training_plan_holders:
            if holder.get_name() == plan_name:
                for plan in holder.get_plans():
                    if plan.get_name() == real_plan_name:
                        return plan
                raise ValueError(f"Cannot find real plan {real_plan_name}")
        raise ValueError(f"Cannot find training plan {plan_name}")
