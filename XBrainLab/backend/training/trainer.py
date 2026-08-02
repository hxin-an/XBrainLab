"""Trainer module for managing and executing training plan queues."""

import threading
from enum import Enum
from uuid import uuid4

from ..training_state_contract import (
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingStateToken,
    TrainingTerminalOutcome,
)
from ..utils import validate_list_type
from ..utils.logger import logger
from .state_tracker import TrainingStateTracker
from .training_plan import TrainingPlanHolder

TRAINER_CLEAN_JOIN_TIMEOUT_SEC = 2.0


class Status(Enum):
    """Enumeration of possible trainer states.

    Attributes:
        PENDING: No active training job.
        INIT: Trainer is initializing.
        INTERRUPTING: An interrupt has been requested.
        TRAIN: Training is in progress (formatted with plan name).

    """

    PENDING = "Pending"
    INIT = "Initializing"
    INTERRUPTING = "Interrupting"
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
            training_plan_holders,
            TrainingPlanHolder,
            "training_plan_holders",
        )
        self._state_lock = threading.RLock()
        self._state_tracker = TrainingStateTracker()
        self._interrupt = threading.Event()
        self._trainer_id = uuid4().hex
        self._run_sequence = 0
        self._run_admitted = False
        self._worker_started = False
        self._active_run: TrainingRunIdentity | None = None
        self._terminal_outcome = TrainingTerminalOutcome(
            state=TrainingOutcomeState.NOT_STARTED,
        )
        self.progress_text: Status | str = Status.PENDING
        self.training_plan_holders = list(training_plan_holders)
        self.current_idx = 0
        self._active_run_start_index = 0
        self._active_run_end_index = 0
        self.job_thread: threading.Thread | None = None
        for holder in self.training_plan_holders:
            self._bind_plan_holder(holder)

    def _bind_plan_holder(self, holder: TrainingPlanHolder) -> None:
        """Bind nested holder/record mutations to this trainer's token."""
        holder.bind_state_tracker(self._state_tracker)

    def add_plan(self, plan: TrainingPlanHolder) -> None:
        """Add a new training plan to the queue.

        Args:
            plan: The training plan holder to append.

        """
        with self._state_tracker.mutation(), self._state_lock:
            self._bind_plan_holder(plan)
            self.training_plan_holders.append(plan)

    def add_training_plan_holders(self, plans: list[TrainingPlanHolder]) -> None:
        """Add a list of training plans to the queue.

        Args:
            plans: List of :class:`TrainingPlanHolder` instances to append.

        """
        with self._state_tracker.mutation(), self._state_lock:
            for plan in plans:
                self._bind_plan_holder(plan)
            self.training_plan_holders.extend(plans)

    def clear_history(self) -> None:
        """Clear training history and pending jobs.

        Raises:
            RuntimeError: If training is currently running.

        """
        if self.is_running():
            raise RuntimeError("Cannot clear history while training is running")
        with self._state_tracker.mutation(), self._state_lock:
            self.training_plan_holders = []
            self.current_idx = 0
            self.progress_text = Status.PENDING
            self._active_run = None
            self._terminal_outcome = TrainingTerminalOutcome(
                state=TrainingOutcomeState.NOT_STARTED,
            )

    def job(self) -> None:
        """Execute the training job, iterating through all pending plan holders.

        Runs sequentially through :attr:`training_plan_holders` starting from
        :attr:`current_idx`. Stops early if :attr:`interrupt` is set. On
        exception, logs the error and updates :attr:`progress_text`.
        """
        run = self._ensure_active_run()
        outcome_state = TrainingOutcomeState.COMPLETED
        outcome_detail: str | None = None
        try:
            while True:
                with self._state_tracker.mutation(), self._state_lock:
                    if self.current_idx >= len(self.training_plan_holders):
                        break
                    if self._interrupt.is_set():
                        outcome_state = TrainingOutcomeState.CANCELLED
                        break
                    plan_holder = self.training_plan_holders[self.current_idx]
                    self.progress_text = Status.TRAIN.value.format(
                        plan_holder.get_name(),
                    )

                plan_holder.train()

                with self._state_tracker.mutation(), self._state_lock:
                    failure_message = self._plan_failure_message(plan_holder)
                    if failure_message is not None:
                        outcome_state = TrainingOutcomeState.FAILED
                        outcome_detail = failure_message
                        self.progress_text = f"Error: {failure_message}"
                        # Abort the current queue. A new confirmed training run
                        # can append fresh plans after the user adjusts settings.
                        self.current_idx = len(self.training_plan_holders)
                        break
                    if self._interrupt.is_set():
                        outcome_state = TrainingOutcomeState.CANCELLED
                        break
                    self.current_idx += 1
        except Exception as e:
            error_msg = f"Training thread crashed: {e}"
            logger.error(error_msg, exc_info=True)
            outcome_state = TrainingOutcomeState.FAILED
            outcome_detail = str(e) or e.__class__.__name__
            with self._state_tracker.mutation(), self._state_lock:
                self.progress_text = f"Error: {e}"
        finally:
            with self._state_tracker.mutation(), self._state_lock:
                if (
                    outcome_state is TrainingOutcomeState.COMPLETED
                    and self._interrupt.is_set()
                ):
                    outcome_state = TrainingOutcomeState.CANCELLED
                if outcome_state is TrainingOutcomeState.CANCELLED:
                    self._retire_cancelled_run_locked()
                if outcome_state is not TrainingOutcomeState.FAILED:
                    self.progress_text = Status.PENDING
                self._terminal_outcome = TrainingTerminalOutcome(
                    state=outcome_state,
                    run=run,
                    detail=outcome_detail,
                )
                self._run_admitted = False
                self._worker_started = False

    def _ensure_active_run(self) -> TrainingRunIdentity:
        """Create a run identity for direct ``job`` calls used by sync paths/tests."""
        with self._state_tracker.mutation(), self._state_lock:
            if (
                self._active_run is None
                or self._terminal_outcome.state is not TrainingOutcomeState.RUNNING
            ):
                self._run_sequence += 1
                self._active_run = TrainingRunIdentity(
                    trainer_id=self._trainer_id,
                    run_id=self._run_sequence,
                )
                self._terminal_outcome = TrainingTerminalOutcome(
                    state=TrainingOutcomeState.RUNNING,
                    run=self._active_run,
                )
                self._run_admitted = True
                self._active_run_start_index = self.current_idx
                self._active_run_end_index = len(self.training_plan_holders)
            return self._active_run

    def _retire_cancelled_run_locked(self) -> None:
        """Retire every holder admitted to a cancelled run exactly once."""
        holder_count = len(self.training_plan_holders)
        start = max(0, min(self._active_run_start_index, holder_count))
        end = max(start, min(self._active_run_end_index, holder_count))
        for holder in self.training_plan_holders[start:end]:
            holder.mark_cancelled()
        self.current_idx = max(self.current_idx, end)

    @staticmethod
    def _plan_failure_message(plan_holder: TrainingPlanHolder) -> str | None:
        """Return the holder's explicit failure field, never display status text."""
        error = str(getattr(plan_holder, "error", "") or "").strip()
        return error or None

    def run(self, interact: bool = False) -> None:
        """Start executing the training job.

        Args:
            interact: If ``True``, run the job in a background thread.
                If ``False``, run synchronously in the current thread.

        """
        if self.is_running():
            return

        thread: threading.Thread | None = None
        with self._state_tracker.mutation(), self._state_lock:
            current_thread = self.job_thread
            if self._run_admitted or (
                current_thread is not None and current_thread.is_alive()
            ):
                return

            self._run_admitted = True
            self._worker_started = False
            self._interrupt.clear()
            self.progress_text = Status.PENDING
            holders = list(self.training_plan_holders)
            self._run_sequence += 1
            self._active_run = TrainingRunIdentity(
                trainer_id=self._trainer_id,
                run_id=self._run_sequence,
            )
            self._terminal_outcome = TrainingTerminalOutcome(
                state=TrainingOutcomeState.RUNNING,
                run=self._active_run,
            )
            self._active_run_start_index = self.current_idx
            self._active_run_end_index = len(holders)
            admitted_holders = holders[
                self._active_run_start_index : self._active_run_end_index
            ]
            run = self._active_run
            if interact:
                try:
                    thread = threading.Thread(
                        target=self._run_background_job,
                        args=(run,),
                        name=f"xbrainlab-training-{run.run_id}",
                        daemon=True,
                    )
                except Exception as exc:
                    self._run_admitted = False
                    self._terminal_outcome = TrainingTerminalOutcome(
                        state=TrainingOutcomeState.FAILED,
                        run=run,
                        detail=str(exc) or exc.__class__.__name__,
                    )
                    raise
                self.job_thread = thread

        try:
            for holder in admitted_holders:
                holder.clear_interrupt()
            if thread is not None:
                with self._state_tracker.mutation(), self._state_lock:
                    if self._active_run != run or not self._run_admitted:
                        return
                    if self._interrupt.is_set():
                        self._run_admitted = False
                        self._worker_started = False
                        if self.job_thread is thread:
                            self.job_thread = None
                        self.progress_text = Status.PENDING
                        self._retire_cancelled_run_locked()
                        self._terminal_outcome = TrainingTerminalOutcome(
                            state=TrainingOutcomeState.CANCELLED,
                            run=run,
                        )
                        return
                    thread.start()
                    self._worker_started = True
            else:
                self.job()
                with self._state_tracker.mutation(), self._state_lock:
                    if self._active_run == run and self.job_thread is None:
                        self._run_admitted = False
        except Exception as exc:
            with self._state_tracker.mutation(), self._state_lock:
                if self._active_run == run:
                    self._run_admitted = False
                    self._worker_started = False
                    if self.job_thread is thread:
                        self.job_thread = None
                    self._terminal_outcome = TrainingTerminalOutcome(
                        state=TrainingOutcomeState.FAILED,
                        run=run,
                        detail=str(exc) or exc.__class__.__name__,
                    )
            raise

    def _run_background_job(self, run: TrainingRunIdentity) -> None:
        """Execute one admitted worker and commit its logical completion."""
        failure: Exception | None = None
        try:
            self.job()
        except Exception as exc:  # pragma: no cover - ``job`` normally contains it
            failure = exc
            logger.error("Training worker crashed: %s", exc, exc_info=True)

        with self._state_lock:
            needs_completion = self._active_run == run and (
                self._run_admitted
                or self._worker_started
                or self._terminal_outcome.state
                in {
                    TrainingOutcomeState.RUNNING,
                    TrainingOutcomeState.STOP_REQUESTED,
                }
            )
        if not needs_completion:
            return

        with self._state_tracker.mutation(), self._state_lock:
            if self._active_run != run:
                return
            if failure is not None:
                self._terminal_outcome = TrainingTerminalOutcome(
                    state=TrainingOutcomeState.FAILED,
                    run=run,
                    detail=str(failure) or failure.__class__.__name__,
                )
                self.progress_text = f"Error: {failure}"
            elif self._terminal_outcome.state in {
                TrainingOutcomeState.RUNNING,
                TrainingOutcomeState.STOP_REQUESTED,
            }:
                self._terminal_outcome = TrainingTerminalOutcome(
                    state=(
                        TrainingOutcomeState.CANCELLED
                        if self._interrupt.is_set()
                        else TrainingOutcomeState.COMPLETED
                    ),
                    run=run,
                )
                self.progress_text = Status.PENDING
            self._run_admitted = False
            self._worker_started = False

    def stop(self, wait_timeout: float | None = None) -> bool:
        """Request interruption and optionally wait for the training thread.

        Returns:
            ``True`` when no background training thread remains alive.

        """
        thread, thread_alive, requested = self._set_interrupt_state(require_active=True)
        if not requested or thread is None or not thread_alive:
            return True
        if wait_timeout is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, float(wait_timeout)))
            thread_alive = thread.is_alive()
            if not thread_alive:
                with self._state_tracker.mutation(), self._state_lock:
                    if self.job_thread is thread:
                        self.job_thread = None
                        self._run_admitted = False
                        self._worker_started = False
        else:
            thread_alive = thread.is_alive()
        return not thread_alive

    def wait_for_completion(self, timeout: float | None = None) -> bool:
        """Wait for the admitted background worker without holding manager locks."""
        with self._state_lock:
            thread = self.job_thread
        if thread is None or thread is threading.current_thread():
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    def get_progress_text(self) -> str:
        """Return a string representation of the current training progress.

        Returns:
            The current status or progress message.

        """
        with self._state_lock:
            progress_text = self.progress_text
        if isinstance(progress_text, Status):
            return progress_text.value
        return progress_text

    def get_terminal_outcome(self) -> TrainingTerminalOutcome:
        """Return typed truth for the active or most recently finished run."""
        with self._state_lock:
            return self._terminal_outcome

    def is_running(self) -> bool:
        """Return logical run admission without mutating lifecycle state.

        Returns:
            ``True`` if a run is admitted or its background worker is alive.

        """
        with self._state_lock:
            thread = self.job_thread
            return (
                self._run_admitted
                or self._worker_started
                or (thread is not None and thread.is_alive())
            )

    def clean(
        self,
        force_update: bool = False,
        wait_timeout: float = TRAINER_CLEAN_JOIN_TIMEOUT_SEC,
    ) -> None:
        """Stop and clean up the training job.

        Args:
            force_update: If ``True``, forcefully interrupt training.
                If ``False``, raises an error when training is still running.
            wait_timeout: Seconds to wait for a running training thread to stop.

        Raises:
            RuntimeError: If training is still in progress and
                ``force_update`` is ``False``.

        """
        if force_update:
            self.set_interrupt()
            with self._state_lock:
                thread = self.job_thread
            if thread is not None and thread.is_alive():
                if thread is threading.current_thread():
                    return
                thread.join(timeout=wait_timeout)
                if thread.is_alive():
                    raise RuntimeError("Training did not stop within cleanup timeout")
                with self._state_tracker.mutation(), self._state_lock:
                    if self.job_thread is thread:
                        self.job_thread = None
                    self._run_admitted = False
                    self._worker_started = False
        elif self.is_running():
            raise RuntimeError("Training still in progress")

    def get_training_plan_holders(self) -> list[TrainingPlanHolder]:
        """Return the list of all training plan holders.

        Returns:
            List of :class:`TrainingPlanHolder` instances.

        """
        with self._state_lock:
            return list(self.training_plan_holders)

    def get_state_generation(self) -> int:
        """Return the generation used to detect concurrent runtime transitions."""
        return self.get_state_snapshot_token().generation

    def get_state_snapshot_token(self) -> TrainingStateToken:
        """Return the shared nested-state generation and stability flag."""
        return self._state_tracker.token()

    def get_state_snapshot_identity(self) -> str:
        """Return the stable identity for this trainer instance."""
        return self._trainer_id

    def get_current_index(self) -> int:
        """Return the active training-plan index under the runtime lock."""
        with self._state_lock:
            return self.current_idx

    @property
    def interrupt(self) -> bool:
        """Whether an interrupt has been requested (thread-safe)."""
        return self._interrupt.is_set()

    def set_interrupt(self) -> None:
        """Set the interrupt flag and propagate to all plan holders."""
        self._set_interrupt_state(require_active=False)

    def _set_interrupt_state(
        self,
        *,
        require_active: bool,
    ) -> tuple[threading.Thread | None, bool, bool]:
        """Commit one stop request and return the captured worker liveness."""
        with self._state_tracker.mutation(), self._state_lock:
            thread = self.job_thread
            thread_alive = (
                thread is not None and thread.is_alive() if require_active else False
            )
            active = self._run_admitted or self._worker_started or thread_alive
            if require_active and not active:
                return thread, thread_alive, False
            self._interrupt.set()
            self.progress_text = Status.INTERRUPTING
            if self._terminal_outcome.state in {
                TrainingOutcomeState.RUNNING,
                TrainingOutcomeState.STOP_REQUESTED,
            }:
                self._terminal_outcome = TrainingTerminalOutcome(
                    state=TrainingOutcomeState.STOP_REQUESTED,
                    run=self._active_run,
                )
            holders = list(self.training_plan_holders)
        for holder in holders:
            holder.set_interrupt()
        return thread, thread_alive, True

    def clear_interrupt(self) -> None:
        """Clear the interrupt flag and propagate to all plan holders."""
        self._interrupt.clear()
        with self._state_tracker.mutation(), self._state_lock:
            self.progress_text = Status.PENDING
            holders = list(self.training_plan_holders)
        for holder in holders:
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
        for holder in self.get_training_plan_holders():
            if holder.get_name() == plan_name:
                for plan in holder.get_plans():
                    if plan.get_name() == real_plan_name:
                        return plan
                raise ValueError(f"Cannot find real plan {real_plan_name}")
        raise ValueError(f"Cannot find training plan {plan_name}")
