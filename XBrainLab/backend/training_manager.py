"""Training lifecycle management for model config, plan generation, and execution."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field
from threading import Event, Lock, RLock, Thread, Timer, current_thread
from time import monotonic
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from .exceptions import (
    SaliencyCancellationTimeoutError,
    SaliencyRecomputationResourceError,
    StaleSaliencyUpdateError,
    StaleTrainingPipelineMutationError,
)
from .training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyScheduleDisposition,
    PostTrainingSaliencyScheduleOutcome,
    PostTrainingSaliencyScheduleReason,
    PostTrainingSaliencyStatus,
    TrainingOutcomeState,
    TrainingPipelineMutationBoundary,
    TrainingReadBoundary,
    TrainingRunIdentity,
    TrainingStateToken,
    TrainingTerminalOutcome,
    read_training_terminal_outcome,
)
from .utils.check import validate_type
from .utils.cuda_errors import is_cuda_oom_error, release_cuda_cache
from .utils.logger import logger
from .utils.observer import Observable

if TYPE_CHECKING:
    from .training import ModelHolder, Trainer, TrainingOption
    from .training.record.train import TrainRecord
    from .training.training_plan import TrainingPlanHolder


_BASELINE_SALIENCY_METHODS = frozenset({"Gradient", "Gradient * Input"})
_POST_TRAINING_SALIENCY_CANCEL_WAIT_SECONDS = 2.0
_POST_TRAINING_SALIENCY_CANCELLED_MESSAGE = "Saliency computation was cancelled."
_POST_TRAINING_SALIENCY_FAILED_MESSAGE = (
    "Saliency computation failed. See the application log for details."
)
_POST_TRAINING_SALIENCY_OOM_MESSAGE = (
    "Saliency could not finish because GPU memory was exhausted."
)
_POST_TRAINING_SALIENCY_TERMINAL_EVENT = "post_training_saliency_terminal"
_POST_TRAINING_SALIENCY_TERMINAL_RETRY_SECONDS = 0.05
_POST_TRAINING_SALIENCY_SCHEDULE_MESSAGES = {
    PostTrainingSaliencyScheduleReason.TRAINER_UNAVAILABLE: (
        "Saliency was not scheduled because its trainer is no longer available."
    ),
    PostTrainingSaliencyScheduleReason.UNSUPPORTED_PROFILE: (
        "Saliency accepts only the recommended baseline profile."
    ),
    PostTrainingSaliencyScheduleReason.TRAINING_NOT_COMPLETED: (
        "Saliency was not scheduled because training did not complete successfully."
    ),
    PostTrainingSaliencyScheduleReason.TRAINING_RUN_CHANGED: (
        "Saliency was cancelled because the completed training run changed."
    ),
    PostTrainingSaliencyScheduleReason.TRAINING_STATE_UNAVAILABLE: (
        "Saliency could not verify the completed training state."
    ),
    PostTrainingSaliencyScheduleReason.TRAINING_STATE_UNSTABLE: (
        "Saliency was cancelled because training state is still changing."
    ),
    PostTrainingSaliencyScheduleReason.FINISHED_RUN_COUNT_CHANGED: (
        "Saliency was cancelled because the finished run set changed."
    ),
    PostTrainingSaliencyScheduleReason.NO_NEW_FINISHED_RUNS: (
        "Saliency found no newly finished runs to compute."
    ),
    PostTrainingSaliencyScheduleReason.NO_FINISHED_RECORDS: (
        "Saliency found no finished evaluation records to compute."
    ),
    PostTrainingSaliencyScheduleReason.PLAN_PREPARATION_FAILED: (
        "Saliency could not prepare a safe computation plan."
    ),
    PostTrainingSaliencyScheduleReason.TRAINING_GENERATION_CHANGED: (
        "Saliency was cancelled because the training generation changed."
    ),
    PostTrainingSaliencyScheduleReason.REQUEST_SUPERSEDED: (
        "Saliency was cancelled because a newer request owns the lifecycle."
    ),
    PostTrainingSaliencyScheduleReason.PREVIOUS_JOB_NOT_CANCELLED: (
        "Saliency could not start while the previous saliency job is still stopping."
    ),
    PostTrainingSaliencyScheduleReason.TRAINER_REPLACED: (
        "Saliency was cancelled because its trainer was replaced."
    ),
    PostTrainingSaliencyScheduleReason.THREAD_START_FAILED: (
        "Saliency could not start its background worker."
    ),
}


@dataclass(frozen=True, slots=True)
class PostTrainingSaliencyTarget:
    """Verified record range produced by one completed trainer run."""

    run: TrainingRunIdentity
    finished_runs_before: int
    finished_runs_after: int
    append: bool
    explicit: bool = False
    selected_members: tuple[tuple[int, int], ...] | None = None
    _command_completed: Event = field(
        default_factory=Event,
        init=False,
        repr=False,
        compare=False,
    )
    _schedule_outcome: PostTrainingSaliencyScheduleOutcome | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _schedule_outcome_lock: Any = field(
        default_factory=RLock,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.run, TrainingRunIdentity):
            raise TypeError("post-training saliency run identity is invalid")
        for name, value in (
            ("finished_runs_before", self.finished_runs_before),
            ("finished_runs_after", self.finished_runs_after),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise TypeError(f"{name} must be a non-negative integer")
        if not isinstance(self.append, bool):
            raise TypeError("append must be a boolean")
        if not isinstance(self.explicit, bool):
            raise TypeError("explicit must be a boolean")
        members = self.selected_members
        if members is not None:
            if not self.explicit or self.append:
                raise ValueError(
                    "selected saliency members require an explicit replacement target"
                )
            if not isinstance(members, tuple) or not members:
                raise ValueError("selected saliency members must be a non-empty tuple")
            for member in members:
                if (
                    not isinstance(member, tuple)
                    or len(member) != 2
                    or any(
                        isinstance(value, bool)
                        or not isinstance(value, int)
                        or value < 0
                        for value in member
                    )
                ):
                    raise TypeError(
                        "selected saliency members must contain non-negative indexes"
                    )
            if len(set(members)) != len(members):
                raise ValueError("selected saliency members must be unique")
            if members != tuple(sorted(members)):
                raise ValueError("selected saliency members must use canonical order")

    def mark_command_completed(self) -> None:
        """Release heavy computation after the command boundary has returned."""
        self._command_completed.set()

    def wait_for_command_completion(self) -> None:
        """Wait for the command boundary without holding backend locks."""
        self._command_completed.wait()

    @property
    def schedule_outcome(self) -> PostTrainingSaliencyScheduleOutcome | None:
        """Return the scheduler acknowledgement published by TrainingManager."""
        with self._schedule_outcome_lock:
            return self._schedule_outcome

    def publish_schedule_outcome(
        self,
        outcome: PostTrainingSaliencyScheduleOutcome,
    ) -> None:
        """Publish exactly one immutable scheduler acknowledgement."""
        if not isinstance(outcome, PostTrainingSaliencyScheduleOutcome):
            raise TypeError("post-training saliency schedule outcome is invalid")
        with self._schedule_outcome_lock:
            if self._schedule_outcome is not None and self._schedule_outcome != outcome:
                raise RuntimeError(
                    "post-training saliency target already has an outcome"
                )
            object.__setattr__(self, "_schedule_outcome", outcome)


@dataclass(frozen=True, slots=True)
class PostTrainingSaliencyTerminalDeliveryState:
    """Immutable manager ledger for terminal observer handoff."""

    pending_generations: tuple[int, ...]
    active_generation: int | None
    delivered_generation: int
    retry_owner_active: bool
    retry_unavailable: bool


@dataclass(frozen=True, slots=True)
class _PostTrainingSaliencyOwnership:
    """Identity-scoped ownership of one published saliency generation."""

    generation: int
    target: PostTrainingSaliencyTarget
    trainer: object
    training_generation: int
    cancellation_epoch: int


@dataclass(frozen=True, slots=True)
class _TrainingPipelineOperationLease:
    """Short manager-owned lease for work executed outside the lifecycle lock."""

    generation: int
    kind: str
    trainer: object | None


@dataclass(frozen=True, slots=True)
class _TrainingStartAdmission:
    """Coordinate cancellation while a run is preparing its worker admission."""

    lease: _TrainingPipelineOperationLease
    trainer: object
    stop_requested: Event = field(default_factory=Event)
    complete: Event = field(default_factory=Event)


@dataclass(frozen=True, slots=True)
class TrainingStartupRollbackSnapshot:
    """Quiescent trainer and saliency truth retained across deferred startup."""

    trainer: object | None
    trainer_startup_snapshot: object | None
    saliency_status: PostTrainingSaliencyStatus
    saliency_request_sequence: int
    saliency_cancellation_epoch: int
    saliency_job_sequence: int


class _PostTrainingSaliencyTerminalBoundary:
    """Defer typed terminal statuses until the outer command scope exits."""

    def __init__(
        self,
        deliver: Callable[[PostTrainingSaliencyStatus], object],
    ) -> None:
        self._deliver = deliver
        self._pending: ContextVar[
            tuple[
                list[PostTrainingSaliencyStatus],
                Callable[[PostTrainingSaliencyStatus], object] | None,
            ]
            | None
        ] = ContextVar(
            f"xbrainlab_manager_saliency_notifications_{id(self)}",
            default=None,
        )

    @contextmanager
    def capture(
        self,
        stage: Callable[[PostTrainingSaliencyStatus], object] | None = None,
    ) -> Iterator[None]:
        """Deliver nested statuses only after the outer command has returned."""
        active = self._pending.get()
        if active is not None:
            yield
            return

        pending: list[PostTrainingSaliencyStatus] = []
        token = self._pending.set((pending, stage))
        try:
            yield
        finally:
            self._pending.reset(token)
            for status in pending:
                self._deliver(status)

    def publish(self, status: PostTrainingSaliencyStatus) -> None:
        """Queue in an active command scope or deliver immediately."""
        if (
            not isinstance(status, PostTrainingSaliencyStatus)
            or not status.phase.terminal
        ):
            raise TypeError("post-training saliency terminal status is invalid")
        active = self._pending.get()
        if active is None:
            self._deliver(status)
            return
        pending, stage = active
        pending.append(status)
        if stage is not None:
            stage(status)


_POST_TRAINING_SALIENCY_TARGET: ContextVar[PostTrainingSaliencyTarget | None] = (
    ContextVar("xbrainlab_post_training_saliency_target", default=None)
)


@contextmanager
def post_training_saliency_target(
    target: PostTrainingSaliencyTarget,
) -> Iterator[None]:
    """Scope one automatic baseline command to its completed trainer run."""
    token = _POST_TRAINING_SALIENCY_TARGET.set(target)
    try:
        yield
    finally:
        _POST_TRAINING_SALIENCY_TARGET.reset(token)
        target.mark_command_completed()


def current_post_training_saliency_target() -> PostTrainingSaliencyTarget | None:
    """Return the automatic baseline target active on this command thread."""
    return _POST_TRAINING_SALIENCY_TARGET.get()


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
        self._model_holder: ModelHolder | None = None
        self._training_option: TrainingOption | None = None
        self.trainer: Trainer | None = None
        self.saliency_params: dict | None = None
        # Acquire pipeline before saliency when both are needed; never wait for a
        # worker while holding the saliency lock.
        self._training_pipeline_lock = RLock()
        self._training_operation_sequence = 0
        self._training_operation_owner: _TrainingPipelineOperationLease | None = None
        self._training_start_admission: _TrainingStartAdmission | None = None
        self._saliency_job_lock = Lock()
        self._saliency_request_sequence = 0
        self._saliency_cancellation_epoch = 0
        self._saliency_request_owner: _PostTrainingSaliencyOwnership | None = None
        self._saliency_request_cleanup_events: dict[int, Event] = {}
        self._saliency_job_sequence = 0
        self._saliency_job_owner: _PostTrainingSaliencyOwnership | None = None
        self._saliency_job_cancel: Event | None = None
        self._saliency_job_cleanup_complete: Event | None = None
        self._saliency_job_thread: Thread | None = None
        self._post_training_saliency_status = PostTrainingSaliencyStatus.idle()
        self._saliency_lifecycle_events = Observable()
        self._saliency_terminal_delivery_lock = Lock()
        self._saliency_terminal_delivery_active = False
        self._saliency_terminal_pending: dict[int, PostTrainingSaliencyStatus] = {}
        self._saliency_terminal_delivered_generation = 0
        self._saliency_terminal_retry_timer: Timer | None = None
        self._saliency_terminal_retry_fallback_thread: Thread | None = None
        self._saliency_terminal_retry_unavailable = False
        self._saliency_terminal_delivery_idle = Event()
        self._saliency_terminal_delivery_idle.set()
        self._saliency_terminal_boundary = _PostTrainingSaliencyTerminalBoundary(
            self._deliver_post_training_saliency_terminal,
        )

    # --- Configuration ---

    @property
    def model_holder(self) -> ModelHolder | None:
        """Return an isolated snapshot of the published model configuration."""
        return deepcopy(self._model_holder)

    @model_holder.setter
    def model_holder(self, value: ModelHolder | None) -> None:
        """Keep compatibility writes on the validated publication boundary."""
        if value is None:
            self._model_holder = None
            return
        self.set_model_holder(value)

    @property
    def training_option(self) -> TrainingOption | None:
        """Return an isolated snapshot of the published training option."""
        return deepcopy(self._training_option)

    @training_option.setter
    def training_option(self, value: TrainingOption | None) -> None:
        """Keep compatibility writes on the validated publication boundary."""
        if value is None:
            self._training_option = None
            return
        self.set_training_option(value)

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
        validated_option = self._validated_training_option_copy(training_option)
        # Do not clean trainer here to allow multi-experiment history
        self._training_option = validated_option

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
        from .training import ModelHolder  # noqa: PLC0415

        validate_type(model_holder, ModelHolder, "model_holder")
        # Do not clean trainer here to allow multi-experiment history
        self._model_holder = deepcopy(model_holder)

    def apply_configuration(
        self,
        *,
        model_holder: ModelHolder | None,
        training_option: TrainingOption | None,
        update_model: bool,
        update_option: bool,
    ) -> None:
        """Atomically apply a validated model/training configuration."""
        validated_model_holder = None
        if update_model:
            from .training import ModelHolder as ModelHolderType  # noqa: PLC0415

            validate_type(model_holder, ModelHolderType, "model_holder")
            validated_model_holder = deepcopy(model_holder)
        validated_option = None
        if update_option:
            validated_option = self._validated_training_option_copy(training_option)
        if update_model:
            self._model_holder = validated_model_holder
        if update_option:
            self._training_option = validated_option

    @staticmethod
    def _validated_training_option_copy(
        training_option: TrainingOption | None,
    ) -> TrainingOption:
        """Validate and isolate mutable options before state publication."""
        from .training import TrainingOption  # noqa: PLC0415

        validate_type(training_option, TrainingOption, "training_option")
        validated_option = deepcopy(cast("TrainingOption", training_option))
        validated_option.validate()
        return validated_option

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
        if not datasets:
            raise ValueError("No valid dataset is generated")
        with self._training_pipeline_lock:
            self._require_training_operation_idle_locked()
            option = self.training_option
            if option is None:
                raise ValueError("No valid training option is generated")
            model_holder = self.model_holder
            if model_holder is None:
                raise ValueError("No valid model holder is generated")
            trainer = self.trainer
            if not append and trainer is not None and not force_update:
                raise ValueError(
                    "This step has already been done, "
                    "all following data will be removed if you reset this step.\n"
                    "Please clean_trainer first.",
                )

            saliency_params = (
                deepcopy(self.saliency_params)
                if isinstance(self.saliency_params, dict)
                else self.saliency_params
            )
            append_to_existing = append and trainer is not None
            lease = self._begin_training_operation_locked(
                kind=(
                    "append_training_plan" if append_to_existing else "replace_trainer"
                ),
                trainer=trainer,
            )

        try:
            from .training import Trainer, TrainingPlanHolder  # noqa: PLC0415

            training_round_id = uuid4().hex
            training_plan_holders = [
                TrainingPlanHolder(
                    model_holder,
                    dataset,
                    option,
                    saliency_params,
                    training_round_id=training_round_id,
                )
                for dataset in datasets
            ]
            replacement = None if append_to_existing else Trainer(training_plan_holders)
        except BaseException:
            with self._training_pipeline_lock:
                self._finish_training_operation_locked(lease)
            raise

        if replacement is None:
            if trainer is None:
                raise RuntimeError("append operation lost its existing trainer")
            try:
                self._cancel_post_training_saliency(wait=True)
                with self._training_pipeline_lock:
                    if (
                        not self._training_operation_is_current_locked(lease)
                        or self.trainer is not trainer
                    ):
                        raise StaleTrainingPipelineMutationError
                    trainer.add_training_plan_holders(training_plan_holders)
                logger.info("Appended %s training plans", len(training_plan_holders))
            finally:
                with self._training_pipeline_lock:
                    self._finish_training_operation_locked(lease)
            return

        self._replace_trainer_with_lease(
            trainer=trainer,
            replacement=replacement,
            lease=lease,
            force_update=force_update,
        )
        logger.info("Generated training plan")

    # --- Execution ---

    def train(self, interact: bool = False) -> None:
        """Start training process.

        Args:
            interact: Whether to run interactively.

        """
        with self._training_pipeline_lock:
            trainer = self.trainer
            if trainer is None:
                raise ValueError("No valid trainer is generated")
            lease = self._begin_training_operation_locked(
                kind="start_training",
                trainer=trainer,
            )
            admission = _TrainingStartAdmission(lease=lease, trainer=trainer)
            self._training_start_admission = admission

        run_admitted = False
        stop_requested = False
        try:
            self._cancel_post_training_saliency(wait=True)
            with self._training_pipeline_lock:
                if (
                    not self._training_operation_is_current_locked(lease)
                    or self.trainer is not trainer
                    or self._training_start_admission is not admission
                ):
                    raise RuntimeError("Trainer changed before training could start")
                self._retire_post_training_saliency_status()
                # Trainer.run publishes RUNNING before starting the worker. The
                # manager lock is held only across this short admission.
                trainer.run(interact=True)
                run_admitted = True
                stop_requested = admission.stop_requested.is_set()
        finally:
            with self._training_pipeline_lock:
                self._finish_training_operation_locked(lease)
                if self._training_start_admission is admission:
                    self._training_start_admission = None
            if stop_requested:
                trainer.stop(wait_timeout=0.0)
            admission.complete.set()
        if not run_admitted:
            return
        if not interact:
            trainer.wait_for_completion()
        logger.info("Started training (interact=%s)", interact)

    def stop_training(self, wait_timeout: float | None = None) -> bool:
        """Stop training execution."""
        stopped = self._stop_training_if_present(wait_timeout=wait_timeout)
        if stopped is None:
            raise ValueError("No valid trainer is generated")
        if stopped:
            logger.info("Stopped training")
        else:
            logger.warning(
                "Training stop requested but worker did not exit within %.2fs",
                wait_timeout if wait_timeout is not None else 0.0,
            )
        return stopped

    def stop_training_if_present(self, wait_timeout: float | None = None) -> bool:
        """Atomically capture and stop the current trainer, if one exists."""
        stopped = self._stop_training_if_present(wait_timeout=wait_timeout)
        return bool(stopped)

    def _stop_training_if_present(
        self,
        *,
        wait_timeout: float | None,
    ) -> bool | None:
        """Stop an active or preparing run without losing an admission race."""
        with self._training_pipeline_lock:
            trainer = self.trainer
            admission = self._training_start_admission
            if admission is not None and admission.trainer is trainer:
                admission.stop_requested.set()
            else:
                admission = None
        if trainer is None:
            return None
        if admission is None:
            return bool(trainer.stop(wait_timeout=wait_timeout))

        # A preparing trainer may not yet expose an active worker. Record the
        # cancellation intent first, then wait outside the manager lock.
        trainer.stop(wait_timeout=0.0)
        if wait_timeout is None:
            return False
        deadline = monotonic() + max(0.0, float(wait_timeout))
        admission.complete.wait(timeout=max(0.0, deadline - monotonic()))
        if not admission.complete.is_set():
            return False
        return bool(
            trainer.stop(wait_timeout=max(0.0, deadline - monotonic())),
        )

    def wait_for_training_completion(
        self,
        timeout: float | None = None,
        *,
        expected_trainer_identity: str | None = None,
    ) -> bool:
        """Wait for one exact trainer without retaining mutable runtime access."""
        with self._training_pipeline_lock:
            trainer = self.trainer
            boundary = self._capture_training_read_boundary_locked()
        if trainer is None:
            return False
        if (
            expected_trainer_identity is not None
            and boundary.trainer_identity != expected_trainer_identity
        ):
            return False
        if not trainer.wait_for_completion(timeout=timeout):
            return False
        with self._training_pipeline_lock:
            if self.trainer is not trainer:
                return False
            current = self._capture_training_read_boundary_locked()
            return (
                expected_trainer_identity is None
                or current.trainer_identity == expected_trainer_identity
            )

    def is_training(self) -> bool:
        """Return whether training is currently running."""
        with self._training_pipeline_lock:
            if self.trainer:
                return self.trainer.is_running()
            return False

    def get_training_terminal_outcome(self) -> TrainingTerminalOutcome:
        """Return typed terminal truth from one lock-scoped trainer read."""
        with self._training_pipeline_lock:
            return read_training_terminal_outcome(self.trainer)

    def get_training_plan_holders_snapshot(self) -> tuple[Any, ...]:
        """Return the current plan-holder sequence from one trainer generation."""
        with self._training_pipeline_lock:
            trainer = self.trainer
            if trainer is None:
                return ()
            return tuple(trainer.get_training_plan_holders())

    def get_current_training_plan_index(self) -> int | None:
        """Return the current plan index without exposing trainer ownership."""
        with self._training_pipeline_lock:
            trainer = self.trainer
            if trainer is None:
                return None
            getter = getattr(trainer, "get_current_index", None)
            value = getter() if callable(getter) else None
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    def get_training_progress_text(self) -> str:
        """Return progress text without exposing the current trainer."""
        with self._training_pipeline_lock:
            trainer = self.trainer
        if trainer is None:
            return ""
        try:
            progress = trainer.get_progress_text()
        except Exception:
            return ""
        return str(progress or "")

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

    def get_post_training_saliency_status(self) -> PostTrainingSaliencyStatus:
        """Return the immutable status of the latest automatic saliency job."""
        with self._saliency_job_lock:
            return self._post_training_saliency_status

    def get_post_training_saliency_terminal_delivery_state(
        self,
    ) -> PostTrainingSaliencyTerminalDeliveryState:
        """Return terminal queue and acknowledgement truth under one lock."""
        with self._saliency_terminal_delivery_lock:
            pending_generations = tuple(sorted(self._saliency_terminal_pending))
            active_generation = (
                min(pending_generations)
                if self._saliency_terminal_delivery_active and pending_generations
                else None
            )
            return PostTrainingSaliencyTerminalDeliveryState(
                pending_generations=pending_generations,
                active_generation=active_generation,
                delivered_generation=(self._saliency_terminal_delivered_generation),
                retry_owner_active=(
                    self._saliency_terminal_retry_timer is not None
                    or self._saliency_terminal_retry_fallback_thread is not None
                ),
                retry_unavailable=self._saliency_terminal_retry_unavailable,
            )

    def subscribe_post_training_saliency_terminal(
        self,
        callback: Callable[[PostTrainingSaliencyStatus], object],
    ) -> None:
        """Subscribe to worker-terminal status after the saliency lock is released."""
        self._saliency_lifecycle_events.subscribe(
            _POST_TRAINING_SALIENCY_TERMINAL_EVENT,
            callback,
        )

    def unsubscribe_post_training_saliency_terminal(
        self,
        callback: Callable[[PostTrainingSaliencyStatus], object],
    ) -> None:
        """Remove a worker-terminal lifecycle subscriber."""
        self._saliency_lifecycle_events.unsubscribe(
            _POST_TRAINING_SALIENCY_TERMINAL_EVENT,
            callback,
        )

    @contextmanager
    def defer_post_training_saliency_terminal_notifications(
        self,
        stage: Callable[[PostTrainingSaliencyStatus], object] | None = None,
    ) -> Iterator[None]:
        """Hold synchronous terminal delivery until a command boundary exits."""
        with self._saliency_terminal_boundary.capture(stage):
            yield

    def set_saliency_params(
        self,
        saliency_params,
    ) -> PostTrainingSaliencyScheduleOutcome | None:
        """Compute manual settings or schedule the scoped automatic baseline."""
        params = dict(saliency_params or {})
        target = current_post_training_saliency_target()
        if target is not None:
            with self._saliency_job_lock:
                request_generation = self._saliency_request_sequence + 1
                cancellation_epoch = self._saliency_cancellation_epoch
            outcome = self._schedule_post_training_saliency(
                params,
                target,
                request_generation=request_generation,
                cancellation_epoch=cancellation_epoch,
            )
            target.publish_schedule_outcome(outcome)
            return outcome

        self._cancel_post_training_saliency(wait=True)
        lease: _TrainingPipelineOperationLease | None = None
        try:
            with self._training_pipeline_lock:
                trainer = self.trainer
                if trainer is None:
                    self.saliency_params = params
                    return None
                lease = self._begin_training_operation_locked(
                    kind="manual_saliency",
                    trainer=trainer,
                )
                holders = tuple(trainer.get_training_plan_holders())

            from .training.training_plan import (  # noqa: PLC0415
                publish_prepared_saliency_updates,
            )

            updates = [holder.prepare_saliency_update(params) for holder in holders]
            with self._training_pipeline_lock:
                self._require_manual_saliency_operation_current_locked(
                    lease,
                    trainer,
                )
                publish_prepared_saliency_updates(
                    updates,
                    manager_params=params,
                    publish_manager_params=self._publish_saliency_params,
                )
        except Exception as exc:
            if not is_cuda_oom_error(exc):
                raise
            import torch  # noqa: PLC0415

            release_cuda_cache(torch)
            raise SaliencyRecomputationResourceError from exc
        finally:
            if lease is not None:
                with self._training_pipeline_lock:
                    self._finish_training_operation_locked(lease)
        return None

    def _require_manual_saliency_operation_current_locked(
        self,
        lease: _TrainingPipelineOperationLease,
        trainer: object,
    ) -> None:
        if (
            not self._training_operation_is_current_locked(lease)
            or self.trainer is not trainer
        ):
            raise StaleSaliencyUpdateError

    def publish_post_training_saliency_submission_failure(
        self,
        target: PostTrainingSaliencyTarget,
        error: BaseException,
    ) -> PostTrainingSaliencyScheduleOutcome:
        """Publish a typed terminal generation when command submission cannot start."""
        if not isinstance(target, PostTrainingSaliencyTarget):
            raise TypeError("post-training saliency target is invalid")
        with self._training_pipeline_lock:
            trainer = self.trainer
            training_generation = 0
            if trainer is not None:
                try:
                    token = trainer.get_state_snapshot_token()
                    if isinstance(token, TrainingStateToken):
                        training_generation = token.generation
                except Exception:
                    logger.debug(
                        "Could not read training generation for saliency "
                        "submission failure",
                        exc_info=True,
                    )

            with self._saliency_job_lock:
                request_generation = self._saliency_request_sequence + 1
                cancellation_epoch = self._saliency_cancellation_epoch
                admitted_generation = (
                    self._admit_post_training_saliency_request_locked(
                        target=target,
                        trainer=trainer,
                        training_generation=training_generation,
                        request_generation=request_generation,
                        cancellation_epoch=cancellation_epoch,
                    )
                    if trainer is not None
                    else None
                )
                if admitted_generation is None:
                    outcome = self._terminal_schedule_outcome_locked(
                        target,
                        request_generation=request_generation,
                        methods=tuple(sorted(_BASELINE_SALIENCY_METHODS)),
                        disposition=PostTrainingSaliencyScheduleDisposition.STALE,
                        reason=PostTrainingSaliencyScheduleReason.REQUEST_SUPERSEDED,
                        training_generation=training_generation,
                    )
                else:
                    outcome = self._terminal_schedule_outcome_locked(
                        target,
                        request_generation=admitted_generation,
                        methods=tuple(sorted(_BASELINE_SALIENCY_METHODS)),
                        disposition=PostTrainingSaliencyScheduleDisposition.REJECTED,
                        reason=PostTrainingSaliencyScheduleReason.THREAD_START_FAILED,
                        training_generation=training_generation,
                        diagnostic_type=type(error).__name__,
                    )
        if admitted_generation is not None:
            self._complete_post_training_saliency_request(admitted_generation)
        target.publish_schedule_outcome(outcome)
        self._publish_terminal_schedule_outcome(outcome)
        return outcome

    def _schedule_post_training_saliency(
        self,
        params: dict,
        target: PostTrainingSaliencyTarget,
        *,
        request_generation: int,
        cancellation_epoch: int,
    ) -> PostTrainingSaliencyScheduleOutcome:
        """Capture one completed run and compute its baseline outside command lock."""
        methods = self._requested_saliency_methods(params)
        with self._training_pipeline_lock:
            trainer = self.trainer
        if trainer is None:
            return self._terminal_schedule_outcome(
                target,
                request_generation=request_generation,
                methods=methods,
                disposition=PostTrainingSaliencyScheduleDisposition.STALE,
                reason=PostTrainingSaliencyScheduleReason.TRAINER_UNAVAILABLE,
            )
        if not target.explicit and not self._is_automatic_baseline(params):
            return self._terminal_schedule_outcome(
                target,
                request_generation=request_generation,
                methods=methods,
                disposition=PostTrainingSaliencyScheduleDisposition.REJECTED,
                reason=PostTrainingSaliencyScheduleReason.UNSUPPORTED_PROFILE,
            )
        outcome = read_training_terminal_outcome(trainer)
        if outcome.state is not TrainingOutcomeState.COMPLETED:
            return self._terminal_schedule_outcome(
                target,
                request_generation=request_generation,
                methods=methods,
                disposition=PostTrainingSaliencyScheduleDisposition.STALE,
                reason=PostTrainingSaliencyScheduleReason.TRAINING_NOT_COMPLETED,
            )
        if outcome.run != target.run:
            return self._terminal_schedule_outcome(
                target,
                request_generation=request_generation,
                methods=methods,
                disposition=PostTrainingSaliencyScheduleDisposition.STALE,
                reason=PostTrainingSaliencyScheduleReason.TRAINING_RUN_CHANGED,
            )

        try:
            token = trainer.get_state_snapshot_token()
        except Exception as exc:
            logger.warning(
                "Automatic saliency could not read training state",
                exc_info=True,
            )
            return self._terminal_schedule_outcome(
                target,
                request_generation=request_generation,
                methods=methods,
                disposition=PostTrainingSaliencyScheduleDisposition.REJECTED,
                reason=PostTrainingSaliencyScheduleReason.TRAINING_STATE_UNAVAILABLE,
                diagnostic_type=type(exc).__name__,
            )
        if not isinstance(token, TrainingStateToken):
            logger.warning("Trainer returned an invalid training state token")
            return self._terminal_schedule_outcome(
                target,
                request_generation=request_generation,
                methods=methods,
                disposition=PostTrainingSaliencyScheduleDisposition.REJECTED,
                reason=PostTrainingSaliencyScheduleReason.TRAINING_STATE_UNAVAILABLE,
                diagnostic_type=TypeError.__name__,
            )
        if not token.stable:
            return self._terminal_schedule_outcome(
                target,
                request_generation=request_generation,
                methods=methods,
                disposition=PostTrainingSaliencyScheduleDisposition.STALE,
                reason=PostTrainingSaliencyScheduleReason.TRAINING_STATE_UNSTABLE,
                training_generation=token.generation,
            )
        try:
            indexed_entries = self._finished_record_entries(trainer)
        except Exception as exc:
            logger.warning(
                "Automatic saliency could not read finished records",
                exc_info=True,
            )
            return self._terminal_schedule_outcome(
                target,
                request_generation=request_generation,
                methods=methods,
                disposition=PostTrainingSaliencyScheduleDisposition.REJECTED,
                reason=PostTrainingSaliencyScheduleReason.TRAINING_STATE_UNAVAILABLE,
                training_generation=token.generation,
                diagnostic_type=type(exc).__name__,
            )
        if len(indexed_entries) != target.finished_runs_after:
            return self._terminal_schedule_outcome(
                target,
                request_generation=request_generation,
                methods=methods,
                disposition=PostTrainingSaliencyScheduleDisposition.STALE,
                reason=PostTrainingSaliencyScheduleReason.FINISHED_RUN_COUNT_CHANGED,
                training_generation=token.generation,
            )
        if target.append:
            new_count = target.finished_runs_after - target.finished_runs_before
            if new_count <= 0:
                return self._terminal_schedule_outcome(
                    target,
                    request_generation=request_generation,
                    methods=methods,
                    disposition=PostTrainingSaliencyScheduleDisposition.REJECTED,
                    reason=PostTrainingSaliencyScheduleReason.NO_NEW_FINISHED_RUNS,
                    training_generation=token.generation,
                )
            indexed_entries = indexed_entries[-new_count:]
        elif target.selected_members is not None:
            entries_by_member = {
                member: (holder, record) for member, holder, record in indexed_entries
            }
            if any(
                member not in entries_by_member for member in target.selected_members
            ):
                return self._terminal_schedule_outcome(
                    target,
                    request_generation=request_generation,
                    methods=methods,
                    disposition=PostTrainingSaliencyScheduleDisposition.STALE,
                    reason=(
                        PostTrainingSaliencyScheduleReason.FINISHED_RUN_COUNT_CHANGED
                    ),
                    training_generation=token.generation,
                )
            indexed_entries = [
                (member, *entries_by_member[member])
                for member in target.selected_members
            ]
        entries = [(holder, record) for _member, holder, record in indexed_entries]
        if not entries:
            return self._terminal_schedule_outcome(
                target,
                request_generation=request_generation,
                methods=methods,
                disposition=PostTrainingSaliencyScheduleDisposition.REJECTED,
                reason=PostTrainingSaliencyScheduleReason.NO_FINISHED_RECORDS,
                training_generation=token.generation,
            )

        with self._training_pipeline_lock, self._saliency_job_lock:
            admitted_generation = self._admit_post_training_saliency_request_locked(
                target=target,
                trainer=trainer,
                training_generation=token.generation,
                request_generation=request_generation,
                cancellation_epoch=cancellation_epoch,
            )
            if admitted_generation is None:
                terminal_outcome = self._terminal_schedule_outcome_locked(
                    target,
                    request_generation=request_generation,
                    methods=methods,
                    disposition=PostTrainingSaliencyScheduleDisposition.STALE,
                    reason=PostTrainingSaliencyScheduleReason.REQUEST_SUPERSEDED,
                    training_generation=token.generation,
                )
            else:
                terminal_outcome = None
                request_generation = admitted_generation
        if terminal_outcome is not None:
            self._publish_terminal_schedule_outcome(terminal_outcome)
            return terminal_outcome

        try:
            return self._prepare_and_start_post_training_saliency(
                params=params,
                target=target,
                request_generation=request_generation,
                methods=methods,
                trainer=trainer,
                token=token,
                entries=entries,
            )
        finally:
            self._complete_post_training_saliency_request(request_generation)

    def _prepare_and_start_post_training_saliency(
        self,
        *,
        params: dict,
        target: PostTrainingSaliencyTarget,
        request_generation: int,
        methods: tuple[str, ...],
        trainer: Trainer,
        token: TrainingStateToken,
        entries: list[tuple[TrainingPlanHolder, TrainRecord]],
    ) -> PostTrainingSaliencyScheduleOutcome:
        """Prepare one admitted request and CAS it into a worker generation."""
        records_by_holder: dict[TrainingPlanHolder, list[TrainRecord]] = {}
        for holder, record in entries:
            records_by_holder.setdefault(holder, []).append(record)
        try:
            plans = [
                holder.prepare_saliency_update_plan(params, records=records)
                for holder, records in records_by_holder.items()
            ]
        except Exception as exc:
            logger.warning(
                "Automatic saliency plan preparation failed",
                exc_info=True,
            )
            return self._terminal_schedule_outcome(
                target,
                request_generation=request_generation,
                methods=methods,
                disposition=PostTrainingSaliencyScheduleDisposition.REJECTED,
                reason=PostTrainingSaliencyScheduleReason.PLAN_PREPARATION_FAILED,
                training_generation=token.generation,
                diagnostic_type=type(exc).__name__,
            )
        if not plans:
            return self._terminal_schedule_outcome(
                target,
                request_generation=request_generation,
                methods=methods,
                disposition=PostTrainingSaliencyScheduleDisposition.REJECTED,
                reason=PostTrainingSaliencyScheduleReason.PLAN_PREPARATION_FAILED,
                training_generation=token.generation,
            )
        if any(plan.tracker_generation != token.generation for plan in plans):
            return self._terminal_schedule_outcome(
                target,
                request_generation=request_generation,
                methods=methods,
                disposition=PostTrainingSaliencyScheduleDisposition.STALE,
                reason=PostTrainingSaliencyScheduleReason.TRAINING_GENERATION_CHANGED,
                training_generation=token.generation,
            )

        try:
            request_is_current = self._cancel_post_training_saliency(
                wait=True,
                request_generation=request_generation,
            )
        except Exception as exc:
            logger.warning(
                "Automatic saliency could not retire the previous job",
                exc_info=True,
            )
            return self._terminal_schedule_outcome(
                target,
                request_generation=request_generation,
                methods=methods,
                disposition=PostTrainingSaliencyScheduleDisposition.REJECTED,
                reason=PostTrainingSaliencyScheduleReason.PREVIOUS_JOB_NOT_CANCELLED,
                training_generation=token.generation,
                diagnostic_type=type(exc).__name__,
            )
        if not request_is_current:
            return self._terminal_schedule_outcome(
                target,
                request_generation=request_generation,
                methods=methods,
                disposition=PostTrainingSaliencyScheduleDisposition.STALE,
                reason=PostTrainingSaliencyScheduleReason.REQUEST_SUPERSEDED,
                training_generation=token.generation,
            )
        terminal_outcome = None
        scheduled_outcome = None
        with self._training_pipeline_lock, self._saliency_job_lock:
            request_owner = self._saliency_request_owner
            if (
                request_generation != self._saliency_request_sequence
                or request_owner is None
                or request_owner.generation != request_generation
                or request_owner.target is not target
                or request_owner.trainer is not trainer
                or request_owner.training_generation != token.generation
            ):
                terminal_outcome = self._terminal_schedule_outcome_locked(
                    target,
                    request_generation=request_generation,
                    methods=methods,
                    disposition=PostTrainingSaliencyScheduleDisposition.STALE,
                    reason=PostTrainingSaliencyScheduleReason.REQUEST_SUPERSEDED,
                    training_generation=token.generation,
                )
            elif self.trainer is not trainer:
                terminal_outcome = self._terminal_schedule_outcome_locked(
                    target,
                    request_generation=request_generation,
                    methods=methods,
                    disposition=PostTrainingSaliencyScheduleDisposition.STALE,
                    reason=PostTrainingSaliencyScheduleReason.TRAINER_REPLACED,
                    training_generation=token.generation,
                )
            else:
                sequence = request_generation
                cancel = Event()
                cleanup_complete = Event()
                try:
                    thread = Thread(
                        target=self._run_post_training_saliency,
                        args=(
                            sequence,
                            cancel,
                            cleanup_complete,
                            trainer,
                            target,
                            token.generation,
                            params,
                            plans,
                        ),
                        name=f"xbrainlab-saliency-{target.run.run_id}",
                        daemon=True,
                    )
                except Exception as exc:
                    terminal_outcome = self._terminal_schedule_outcome_locked(
                        target,
                        request_generation=request_generation,
                        methods=methods,
                        disposition=(PostTrainingSaliencyScheduleDisposition.REJECTED),
                        reason=(PostTrainingSaliencyScheduleReason.THREAD_START_FAILED),
                        training_generation=token.generation,
                        diagnostic_type=type(exc).__name__,
                    )
                else:
                    self._saliency_job_sequence = sequence
                    self._saliency_job_owner = _PostTrainingSaliencyOwnership(
                        generation=sequence,
                        target=target,
                        trainer=trainer,
                        training_generation=token.generation,
                        cancellation_epoch=request_owner.cancellation_epoch,
                    )
                    self._saliency_request_owner = None
                    self._saliency_job_cancel = cancel
                    self._saliency_job_cleanup_complete = cleanup_complete
                    self._saliency_job_thread = thread
                    self._post_training_saliency_status = (
                        PostTrainingSaliencyStatus.pending(
                            generation=sequence,
                            run=target.run,
                            training_generation=token.generation,
                            methods=methods,
                        )
                    )
                    try:
                        thread.start()
                    except Exception as exc:
                        failed_status = self._transition_post_training_saliency_locked(
                            sequence,
                            PostTrainingSaliencyPhase.FAILED,
                            error_code=(
                                PostTrainingSaliencyScheduleReason.THREAD_START_FAILED.value
                            ),
                            message=_POST_TRAINING_SALIENCY_SCHEDULE_MESSAGES[
                                PostTrainingSaliencyScheduleReason.THREAD_START_FAILED
                            ],
                            diagnostic_type=type(exc).__name__,
                        )
                        self._saliency_job_cancel = None
                        self._saliency_job_cleanup_complete = None
                        self._saliency_job_thread = None
                        if failed_status is None:
                            raise RuntimeError(
                                "saliency thread start failure lost lifecycle ownership"
                            ) from exc
                        terminal_outcome = PostTrainingSaliencyScheduleOutcome(
                            disposition=(
                                PostTrainingSaliencyScheduleDisposition.REJECTED
                            ),
                            reason=(
                                PostTrainingSaliencyScheduleReason.THREAD_START_FAILED
                            ),
                            message=failed_status.message or "",
                            status=failed_status,
                        )
                    else:
                        status = self._post_training_saliency_status
                        scheduled_outcome = PostTrainingSaliencyScheduleOutcome(
                            disposition=(
                                PostTrainingSaliencyScheduleDisposition.SCHEDULED
                            ),
                            reason=PostTrainingSaliencyScheduleReason.SCHEDULED,
                            message=(status.message or "Saliency is waiting to start."),
                            status=status,
                        )

        if terminal_outcome is not None:
            self._publish_terminal_schedule_outcome(terminal_outcome)
            return terminal_outcome
        if scheduled_outcome is None:
            raise RuntimeError("saliency scheduler did not publish an outcome")
        return scheduled_outcome

    def _terminal_schedule_outcome(
        self,
        target: PostTrainingSaliencyTarget,
        *,
        request_generation: int,
        methods: tuple[str, ...],
        disposition: PostTrainingSaliencyScheduleDisposition,
        reason: PostTrainingSaliencyScheduleReason,
        training_generation: int | None = None,
        diagnostic_type: str | None = None,
    ) -> PostTrainingSaliencyScheduleOutcome:
        """Publish one terminal acknowledgement for a request that did not start."""
        if disposition is PostTrainingSaliencyScheduleDisposition.SCHEDULED:
            raise ValueError("terminal schedule outcome cannot be scheduled")
        with self._saliency_job_lock:
            outcome = self._terminal_schedule_outcome_locked(
                target,
                request_generation=request_generation,
                methods=methods,
                disposition=disposition,
                reason=reason,
                training_generation=training_generation,
                diagnostic_type=diagnostic_type,
            )
        self._publish_terminal_schedule_outcome(outcome)
        return outcome

    def _publish_terminal_schedule_outcome(
        self,
        outcome: PostTrainingSaliencyScheduleOutcome,
    ) -> None:
        """Enter the terminal boundary only after scheduler locks are released."""
        self._notify_post_training_saliency_terminal(outcome.status)

    def _terminal_schedule_outcome_locked(
        self,
        target: PostTrainingSaliencyTarget,
        *,
        request_generation: int,
        methods: tuple[str, ...],
        disposition: PostTrainingSaliencyScheduleDisposition,
        reason: PostTrainingSaliencyScheduleReason,
        training_generation: int | None = None,
        diagnostic_type: str | None = None,
    ) -> PostTrainingSaliencyScheduleOutcome:
        """Build a terminal acknowledgement while the saliency job lock is held."""
        if disposition is PostTrainingSaliencyScheduleDisposition.SCHEDULED:
            raise ValueError("terminal schedule outcome cannot be scheduled")
        message = _POST_TRAINING_SALIENCY_SCHEDULE_MESSAGES[reason]
        phase = (
            PostTrainingSaliencyPhase.FAILED
            if disposition is PostTrainingSaliencyScheduleDisposition.REJECTED
            else PostTrainingSaliencyPhase.CANCELLED
        )
        status = PostTrainingSaliencyStatus(
            phase=phase,
            generation=request_generation,
            run=target.run,
            training_generation=training_generation,
            methods=methods,
            error_code=(
                reason.value
                if disposition is PostTrainingSaliencyScheduleDisposition.REJECTED
                else None
            ),
            message=message,
            diagnostic_type=(
                diagnostic_type
                if disposition is PostTrainingSaliencyScheduleDisposition.REJECTED
                else None
            ),
        )
        request_owner = self._saliency_request_owner
        owns_admitted_request = (
            request_owner is not None
            and request_owner.generation == request_generation
            and request_owner.target is target
        )
        pristine_lifecycle = (
            self._saliency_job_owner is None
            and request_owner is None
            and self._saliency_request_sequence == 0
            and self._post_training_saliency_status == PostTrainingSaliencyStatus.idle()
        )
        if owns_admitted_request or pristine_lifecycle:
            if pristine_lifecycle:
                self._saliency_request_sequence = request_generation
            self._saliency_job_sequence = request_generation
            if request_owner is not None:
                self._saliency_job_owner = request_owner
                self._saliency_request_owner = None
            self._post_training_saliency_status = status
        return PostTrainingSaliencyScheduleOutcome(
            disposition=disposition,
            reason=reason,
            message=message,
            status=status,
        )

    def _admit_post_training_saliency_request_locked(
        self,
        *,
        target: PostTrainingSaliencyTarget,
        trainer: object,
        training_generation: int,
        request_generation: int,
        cancellation_epoch: int,
    ) -> int | None:
        """Claim scheduling only for the exact current and newer training lineage."""
        if (
            self._training_operation_owner is not None
            or self.trainer is not trainer
            or cancellation_epoch != self._saliency_cancellation_epoch
            or request_generation != self._saliency_request_sequence + 1
        ):
            return None
        outcome = read_training_terminal_outcome(trainer)
        if (
            outcome.state is not TrainingOutcomeState.COMPLETED
            or outcome.run != target.run
        ):
            return None
        incumbent = self._saliency_request_owner or self._saliency_job_owner
        if incumbent is not None:
            supersedes = self._target_supersedes_owner(
                target=target,
                trainer=trainer,
                training_generation=training_generation,
                owner=incumbent,
            )
            explicit_terminal_retry = (
                incumbent is self._saliency_job_owner
                and self._explicit_target_retries_terminal_owner_locked(
                    target=target,
                    trainer=trainer,
                    owner=incumbent,
                )
            )
            if not supersedes and not explicit_terminal_retry:
                return None
        self._saliency_request_sequence = request_generation
        self._saliency_request_owner = _PostTrainingSaliencyOwnership(
            generation=request_generation,
            target=target,
            trainer=trainer,
            training_generation=training_generation,
            cancellation_epoch=cancellation_epoch,
        )
        self._saliency_request_cleanup_events[request_generation] = Event()
        return request_generation

    def _explicit_target_retries_terminal_owner_locked(
        self,
        *,
        target: PostTrainingSaliencyTarget,
        trainer: object,
        owner: _PostTrainingSaliencyOwnership,
    ) -> bool:
        """Allow a fresh explicit retry only after the exact owner is terminal."""
        status = self._post_training_saliency_status
        return bool(
            target.explicit
            and not target.append
            and target.finished_runs_before == 0
            and trainer is owner.trainer
            and target.run == owner.target.run
            and target.finished_runs_after == owner.target.finished_runs_after
            and status.generation == owner.generation
            and status.phase
            in {
                PostTrainingSaliencyPhase.SUCCEEDED,
                PostTrainingSaliencyPhase.FAILED,
                PostTrainingSaliencyPhase.CANCELLED,
            }
        )

    def _complete_post_training_saliency_request(self, generation: int) -> None:
        """Release preparation ownership after worker publication or rejection."""
        with self._saliency_job_lock:
            cleanup_complete = self._saliency_request_cleanup_events.pop(
                generation,
                None,
            )
            owner = self._saliency_request_owner
            if owner is not None and owner.generation == generation:
                self._saliency_request_owner = None
        if cleanup_complete is not None:
            cleanup_complete.set()

    @staticmethod
    def _target_supersedes_owner(
        *,
        target: PostTrainingSaliencyTarget,
        trainer: object,
        training_generation: int,
        owner: _PostTrainingSaliencyOwnership,
    ) -> bool:
        """Compare training-run and finished-run lineage, independent of arrival."""
        if owner.target is target:
            return False
        if trainer is not owner.trainer:
            return True
        previous = owner.target
        if target.run.trainer_id != previous.run.trainer_id:
            return True
        if (
            target.run.run_id <= previous.run.run_id
            or training_generation <= owner.training_generation
        ):
            return False
        if target.append:
            return target.finished_runs_after > previous.finished_runs_after
        return True

    @staticmethod
    def _requested_saliency_methods(params: dict) -> tuple[str, ...]:
        methods = params.get("_methods") or params.get("methods") or ()
        if not isinstance(methods, (list, tuple, set)):
            return ()
        return tuple(str(method) for method in methods if str(method).strip())

    def _run_post_training_saliency(
        self,
        sequence: int,
        cancel: Event,
        cleanup_complete: Event,
        trainer,
        target: PostTrainingSaliencyTarget,
        generation: int,
        params: dict,
        plans: list,
    ) -> None:
        """Compute outside shared locks, then compare-and-publish once."""
        terminal_status: PostTrainingSaliencyStatus | None = None
        try:
            from .training.training_plan import (  # noqa: PLC0415
                publish_prepared_saliency_updates,
            )

            target.wait_for_command_completion()
            with self._saliency_job_lock:
                if not self._saliency_job_is_current_locked(
                    sequence,
                    cancel,
                    trainer,
                    target,
                    generation,
                ):
                    return
                self._transition_post_training_saliency_locked(
                    sequence,
                    PostTrainingSaliencyPhase.RUNNING,
                    message="Saliency is being computed.",
                )

            def should_cancel() -> bool:
                return not self._saliency_job_is_current(
                    sequence,
                    cancel,
                    trainer,
                    target,
                    generation,
                )

            updates = [
                plan.holder.compute_saliency_update(
                    plan,
                    should_cancel=should_cancel,
                )
                for plan in plans
            ]
            with self._saliency_job_lock:
                if not self._saliency_job_is_current_locked(
                    sequence,
                    cancel,
                    trainer,
                    target,
                    generation,
                ):
                    return
                if not any(update.eval_records for update in updates):
                    terminal_status = self._transition_post_training_saliency_locked(
                        sequence,
                        PostTrainingSaliencyPhase.FAILED,
                        error_code="evaluation_unavailable",
                        message="Saliency unavailable: incomplete evaluation coverage.",
                    )
                    return
                publish_prepared_saliency_updates(
                    updates,
                    manager_params=params,
                    publish_manager_params=self._publish_saliency_params,
                )
                terminal_status = self._transition_post_training_saliency_locked(
                    sequence,
                    PostTrainingSaliencyPhase.SUCCEEDED,
                    message="Saliency is available.",
                )
        except Exception as exc:
            from .exceptions import StaleSaliencyUpdateError  # noqa: PLC0415

            if isinstance(exc, StaleSaliencyUpdateError):
                logger.debug("Discarded stale post-training saliency result")
                terminal_status = self._transition_post_training_saliency(
                    sequence,
                    PostTrainingSaliencyPhase.CANCELLED,
                    message=_POST_TRAINING_SALIENCY_CANCELLED_MESSAGE,
                )
            elif is_cuda_oom_error(exc):
                logger.warning(
                    "Automatic post-training saliency ran out of GPU memory",
                    exc_info=True,
                )
                terminal_status = self._transition_post_training_saliency(
                    sequence,
                    PostTrainingSaliencyPhase.FAILED,
                    error_code="cuda_oom",
                    message=_POST_TRAINING_SALIENCY_OOM_MESSAGE,
                    diagnostic_type=type(exc).__name__,
                )
            else:
                logger.exception("Automatic post-training saliency failed")
                terminal_status = self._transition_post_training_saliency(
                    sequence,
                    PostTrainingSaliencyPhase.FAILED,
                    error_code="computation_failed",
                    message=_POST_TRAINING_SALIENCY_FAILED_MESSAGE,
                    diagnostic_type=type(exc).__name__,
                )
        finally:
            import torch  # noqa: PLC0415

            release_cuda_cache(torch)
            cleanup_complete.set()
            with self._saliency_job_lock:
                if (
                    self._saliency_job_thread is current_thread()
                    and terminal_status is None
                ):
                    terminal_status = self._transition_post_training_saliency_locked(
                        sequence,
                        PostTrainingSaliencyPhase.CANCELLED,
                        message=_POST_TRAINING_SALIENCY_CANCELLED_MESSAGE,
                    )
            if terminal_status is not None:
                self._notify_post_training_saliency_terminal(terminal_status)
            with self._saliency_job_lock:
                if self._saliency_job_thread is current_thread():
                    self._saliency_job_thread = None
                    self._saliency_job_cancel = None
                    if self._saliency_job_cleanup_complete is cleanup_complete:
                        self._saliency_job_cleanup_complete = None

    @staticmethod
    def _finished_record_entries(
        trainer: Trainer,
    ) -> list[tuple[tuple[int, int], TrainingPlanHolder, TrainRecord]]:
        """Return indexed finished records in stable holder/repeat order."""
        return [
            ((plan_index, run_index), holder, record)
            for plan_index, holder in enumerate(trainer.get_training_plan_holders())
            for run_index, record in enumerate(holder.get_plans())
            if record.is_finished()
        ]

    @staticmethod
    def _is_automatic_baseline(params: dict) -> bool:
        methods = params.get("_methods") or params.get("methods")
        return (
            params.get("_profile") in {None, "recommended"}
            and isinstance(methods, (list, tuple, set))
            and frozenset(str(method) for method in methods)
            == _BASELINE_SALIENCY_METHODS
        )

    def _saliency_job_is_current(
        self,
        sequence: int,
        cancel: Event,
        trainer,
        target: PostTrainingSaliencyTarget,
        generation: int,
    ) -> bool:
        with self._saliency_job_lock:
            return self._saliency_job_is_current_locked(
                sequence,
                cancel,
                trainer,
                target,
                generation,
            )

    def _saliency_job_is_current_locked(
        self,
        sequence: int,
        cancel: Event,
        trainer,
        target: PostTrainingSaliencyTarget,
        generation: int,
    ) -> bool:
        owner = self._saliency_job_owner
        if (
            cancel.is_set()
            or sequence != self._saliency_job_sequence
            or owner is None
            or owner.generation != sequence
            or owner.target is not target
            or self._saliency_job_cancel is not cancel
            or self.trainer is not trainer
        ):
            return False
        outcome = read_training_terminal_outcome(trainer)
        if (
            outcome.state is not TrainingOutcomeState.COMPLETED
            or outcome.run != target.run
        ):
            return False
        token = trainer.get_state_snapshot_token()
        return token.stable and token.generation == generation

    def _transition_post_training_saliency(
        self,
        generation: int,
        phase: PostTrainingSaliencyPhase,
        *,
        error_code: str | None = None,
        message: str | None = None,
        diagnostic_type: str | None = None,
    ) -> PostTrainingSaliencyStatus | None:
        """Publish one lifecycle transition when the generation is still current."""
        with self._saliency_job_lock:
            return self._transition_post_training_saliency_locked(
                generation,
                phase,
                error_code=error_code,
                message=message,
                diagnostic_type=diagnostic_type,
            )

    def _transition_post_training_saliency_locked(
        self,
        generation: int,
        phase: PostTrainingSaliencyPhase,
        *,
        error_code: str | None = None,
        message: str | None = None,
        diagnostic_type: str | None = None,
    ) -> PostTrainingSaliencyStatus | None:
        """Compare-and-transition while ``_saliency_job_lock`` is held."""
        current = self._post_training_saliency_status
        if current.generation != generation or current.phase not in {
            PostTrainingSaliencyPhase.PENDING,
            PostTrainingSaliencyPhase.RUNNING,
        }:
            return None
        self._post_training_saliency_status = current.transition(
            generation=generation,
            phase=phase,
            error_code=error_code,
            message=message,
            diagnostic_type=diagnostic_type,
        )
        return self._post_training_saliency_status

    def _notify_post_training_saliency_terminal(
        self,
        status: PostTrainingSaliencyStatus,
    ) -> None:
        """Notify observers only while this terminal generation remains current."""
        if not status.phase.terminal:
            return
        with self._saliency_job_lock:
            if (
                self._saliency_job_sequence != status.generation
                or self._post_training_saliency_status != status
            ):
                return
        self._saliency_terminal_boundary.publish(status)

    def _deliver_post_training_saliency_terminal(
        self,
        status: PostTrainingSaliencyStatus,
    ) -> None:
        """Serialize terminal callbacks by generation without holding manager locks."""
        with self._saliency_terminal_delivery_lock:
            if status.generation <= self._saliency_terminal_delivered_generation:
                return
            self._saliency_terminal_pending[status.generation] = status
            self._saliency_terminal_delivery_idle.clear()
            if (
                self._saliency_terminal_delivery_active
                or self._saliency_terminal_retry_timer is not None
                or self._saliency_terminal_retry_fallback_thread is not None
            ):
                return
            self._saliency_terminal_delivery_active = True
            self._saliency_terminal_retry_unavailable = False

        self._drain_post_training_saliency_terminals()

    def _drain_post_training_saliency_terminals(self) -> None:
        """Commit the delivery ledger only after the observer handoff succeeds."""
        while True:
            with self._saliency_terminal_delivery_lock:
                stale_generations = [
                    generation
                    for generation in self._saliency_terminal_pending
                    if generation <= self._saliency_terminal_delivered_generation
                ]
                for stale_generation in stale_generations:
                    self._saliency_terminal_pending.pop(stale_generation, None)
                pending_generations = [
                    generation
                    for generation in self._saliency_terminal_pending
                    if generation > self._saliency_terminal_delivered_generation
                ]
                if not pending_generations:
                    self._saliency_terminal_delivery_active = False
                    self._saliency_terminal_retry_unavailable = False
                    self._saliency_terminal_delivery_idle.set()
                    return
                generation = min(pending_generations)
                terminal_status = self._saliency_terminal_pending[generation]

            try:
                delivered = self._saliency_lifecycle_events.notify(
                    _POST_TRAINING_SALIENCY_TERMINAL_EVENT,
                    terminal_status,
                )
            except Exception:
                logger.exception(
                    "Could not hand off terminal saliency status to observers"
                )
                delivered = False
            if delivered is False:
                with self._saliency_terminal_delivery_lock:
                    self._saliency_terminal_delivery_active = False
                self._schedule_post_training_saliency_terminal_retry()
                return

            with self._saliency_terminal_delivery_lock:
                if (
                    self._saliency_terminal_pending.get(generation) == terminal_status
                    and generation > self._saliency_terminal_delivered_generation
                ):
                    self._saliency_terminal_pending.pop(generation, None)
                    self._saliency_terminal_delivered_generation = generation
                    self._saliency_terminal_retry_unavailable = False

    def _schedule_post_training_saliency_terminal_retry(self) -> None:
        """Own one delayed retry after an observer handoff failure."""
        try:
            with self._saliency_terminal_delivery_lock:
                if not self._saliency_terminal_pending:
                    self._saliency_terminal_retry_unavailable = False
                    self._saliency_terminal_delivery_idle.set()
                    return
                if (
                    self._saliency_terminal_retry_timer is not None
                    or self._saliency_terminal_retry_fallback_thread is not None
                ):
                    return
                timer = Timer(
                    _POST_TRAINING_SALIENCY_TERMINAL_RETRY_SECONDS,
                    self._retry_post_training_saliency_terminal_delivery,
                )
                timer.daemon = True
                self._saliency_terminal_retry_timer = timer
        except Exception:
            logger.exception("Could not construct terminal saliency delivery retry")
            self._schedule_post_training_saliency_terminal_retry_fallback()
            return
        try:
            timer.start()
        except Exception:
            with self._saliency_terminal_delivery_lock:
                if self._saliency_terminal_retry_timer is timer:
                    self._saliency_terminal_retry_timer = None
            logger.exception("Could not schedule terminal saliency delivery retry")
            self._schedule_post_training_saliency_terminal_retry_fallback()

    def _schedule_post_training_saliency_terminal_retry_fallback(self) -> None:
        """Use one sleeping daemon worker when Timer.start itself fails."""
        try:
            with self._saliency_terminal_delivery_lock:
                if not self._saliency_terminal_pending:
                    self._saliency_terminal_retry_unavailable = False
                    self._saliency_terminal_delivery_idle.set()
                    return
                if self._saliency_terminal_retry_fallback_thread is not None:
                    return
                thread = Thread(
                    target=self._run_post_training_saliency_terminal_retry_fallback,
                    name="xbrainlab-saliency-terminal-retry",
                    daemon=True,
                )
                self._saliency_terminal_retry_fallback_thread = thread
        except Exception:
            self._mark_post_training_saliency_terminal_retry_unavailable()
            logger.exception("Could not construct terminal saliency retry fallback")
            return
        try:
            thread.start()
        except Exception:
            with self._saliency_terminal_delivery_lock:
                if self._saliency_terminal_retry_fallback_thread is thread:
                    self._saliency_terminal_retry_fallback_thread = None
            self._mark_post_training_saliency_terminal_retry_unavailable()
            logger.exception("Could not start terminal saliency retry fallback")

    def _run_post_training_saliency_terminal_retry_fallback(self) -> None:
        self._saliency_terminal_delivery_idle.wait(
            _POST_TRAINING_SALIENCY_TERMINAL_RETRY_SECONDS
        )
        with self._saliency_terminal_delivery_lock:
            if self._saliency_terminal_retry_fallback_thread is current_thread():
                self._saliency_terminal_retry_fallback_thread = None
        self._retry_post_training_saliency_terminal_delivery()

    def _mark_post_training_saliency_terminal_retry_unavailable(self) -> None:
        """Keep pending/non-idle truth when no retry primitive can own delivery."""
        with self._saliency_terminal_delivery_lock:
            if self._saliency_terminal_pending:
                self._saliency_terminal_retry_unavailable = True
                self._saliency_terminal_delivery_idle.clear()

    def _retry_post_training_saliency_terminal_delivery(self) -> None:
        """Resume a retained generation once after the bounded retry delay."""
        with self._saliency_terminal_delivery_lock:
            if self._saliency_terminal_retry_timer is current_thread():
                self._saliency_terminal_retry_timer = None
            if self._saliency_terminal_delivery_active:
                return
            if not self._saliency_terminal_pending:
                self._saliency_terminal_retry_unavailable = False
                self._saliency_terminal_delivery_idle.set()
                return
            self._saliency_terminal_delivery_active = True
            self._saliency_terminal_retry_unavailable = False
        self._drain_post_training_saliency_terminals()

    def wait_for_saliency_terminal_delivery(
        self,
        timeout: float | None = None,
    ) -> bool:
        """Wait for retryable terminal observer handoffs in lifecycle tests."""
        return self._saliency_terminal_delivery_idle.wait(timeout=timeout)

    def retry_post_training_saliency_terminal_delivery(self) -> None:
        """Retry one retained terminal generation without another state event."""
        self._retry_post_training_saliency_terminal_delivery()

    def discard_post_training_saliency_terminal_delivery(self) -> None:
        """Release retained terminal delivery work during permanent shutdown."""
        with self._saliency_terminal_delivery_lock:
            timer = self._saliency_terminal_retry_timer
            self._saliency_terminal_retry_timer = None
            self._saliency_terminal_retry_fallback_thread = None
            self._saliency_terminal_pending.clear()
            self._saliency_terminal_delivery_active = False
            self._saliency_terminal_retry_unavailable = False
            self._saliency_terminal_delivery_idle.set()
        if timer is not None:
            timer.cancel()

    def _cancel_post_training_saliency(
        self,
        *,
        wait: bool,
        request_generation: int | None = None,
    ) -> bool:
        """Cancel one job, bounding any wait before the GPU can be reused."""
        cancelled_status: PostTrainingSaliencyStatus | None = None
        with self._saliency_job_lock:
            if (
                request_generation is not None
                and request_generation != self._saliency_request_sequence
            ):
                return False
            if request_generation is None:
                self._saliency_cancellation_epoch += 1
                self._saliency_request_owner = None
            cancel = self._saliency_job_cancel
            cleanup_complete = self._saliency_job_cleanup_complete
            thread = self._saliency_job_thread
            terminal = self._post_training_saliency_status.phase.terminal
            if cancel is not None:
                cancel.set()
            if thread is not None:
                cancelled_status = self._transition_post_training_saliency_locked(
                    self._saliency_job_sequence,
                    PostTrainingSaliencyPhase.CANCELLED,
                    message=_POST_TRAINING_SALIENCY_CANCELLED_MESSAGE,
                )
        if cancelled_status is not None:
            self._notify_post_training_saliency_terminal(cancelled_status)
        completed_thread: Thread | None = None
        if (
            wait
            and terminal
            and cleanup_complete is not None
            and thread is not None
            and thread is not current_thread()
        ):
            cleanup_complete.wait(
                timeout=_POST_TRAINING_SALIENCY_CANCEL_WAIT_SECONDS,
            )
            if not cleanup_complete.is_set():
                logger.warning(
                    "Post-training saliency cleanup did not finish within %.2fs",
                    _POST_TRAINING_SALIENCY_CANCEL_WAIT_SECONDS,
                )
                raise SaliencyCancellationTimeoutError
            completed_thread = thread
        if wait and not self._wait_for_saliency_work(
            timeout=_POST_TRAINING_SALIENCY_CANCEL_WAIT_SECONDS,
            exclude_request_generation=request_generation,
            completed_thread=completed_thread,
        ):
            logger.warning(
                "Post-training saliency did not stop within %.2fs; "
                "new GPU work remains blocked",
                _POST_TRAINING_SALIENCY_CANCEL_WAIT_SECONDS,
            )
            raise SaliencyCancellationTimeoutError
        if thread is not None and not thread.is_alive():
            with self._saliency_job_lock:
                if self._saliency_job_thread is thread:
                    self._saliency_job_thread = None
                    self._saliency_job_cancel = None
                    self._saliency_job_cleanup_complete = None
        return True

    def _retire_post_training_saliency_status(self) -> None:
        """Start a fresh lifecycle generation after its trainer becomes stale."""
        with self._saliency_job_lock:
            self._saliency_cancellation_epoch += 1
            self._saliency_request_sequence += 1
            self._saliency_request_owner = None
            self._saliency_job_sequence = self._saliency_request_sequence
            self._saliency_job_owner = None
            self._post_training_saliency_status = PostTrainingSaliencyStatus.idle(
                generation=self._saliency_job_sequence,
            )

    def wait_for_saliency_job(self, timeout: float | None = None) -> bool:
        """Wait for the current automatic saliency job; intended for lifecycle gates."""
        return self._wait_for_saliency_work(timeout=timeout)

    def _wait_for_saliency_work(
        self,
        *,
        timeout: float | None,
        exclude_request_generation: int | None = None,
        completed_thread: Thread | None = None,
    ) -> bool:
        """Wait for request preparation and worker cleanup across handoff races."""
        deadline = None if timeout is None else monotonic() + max(0.0, timeout)
        while True:
            with self._saliency_job_lock:
                request_events = tuple(
                    event
                    for generation, event in (
                        self._saliency_request_cleanup_events.items()
                    )
                    if generation != exclude_request_generation
                )
                thread = self._saliency_job_thread
            current = current_thread()
            active_thread = (
                thread
                if (
                    thread is not None
                    and thread is not current
                    and thread is not completed_thread
                    and thread.is_alive()
                )
                else None
            )
            if not request_events and active_thread is None:
                return True
            for event in request_events:
                remaining = (
                    None if deadline is None else max(0.0, deadline - monotonic())
                )
                if not event.wait(timeout=remaining):
                    return False
            if active_thread is not None:
                remaining = (
                    None if deadline is None else max(0.0, deadline - monotonic())
                )
                active_thread.join(timeout=remaining)
                if active_thread.is_alive():
                    return False

    def cancel_saliency_job(self) -> None:
        """Request cancellation without blocking the caller's thread."""
        self._cancel_post_training_saliency(wait=False)

    def _publish_saliency_params(self, params: dict) -> None:
        """Replace manager parameters inside the shared publication boundary."""
        self.saliency_params = params

    # --- State Queries ---

    def capture_training_read_boundary(self) -> TrainingReadBoundary:
        """Capture trainer identity and generation under the lifecycle lock."""
        with self._training_pipeline_lock:
            return self._capture_training_read_boundary_locked()

    def capture_pipeline_mutation_boundary(
        self,
    ) -> TrainingPipelineMutationBoundary:
        """Capture all training truth that a pipeline commit must preserve."""
        with self._training_pipeline_lock, self._saliency_job_lock:
            return self._capture_pipeline_mutation_boundary_locked()

    def capture_startup_rollback_snapshot(self) -> TrainingStartupRollbackSnapshot:
        """Retain one quiescent trainer, its results, and saliency lifecycle."""
        with self._training_pipeline_lock, self._saliency_job_lock:
            boundary = self._capture_pipeline_mutation_boundary_locked()
            trainer = self.trainer
            if (
                not boundary.read_boundary.stable
                or boundary.saliency_work_active
                or boundary.training_work_active
                or (trainer is not None and not boundary.terminal_outcome.is_quiescent)
            ):
                raise StaleTrainingPipelineMutationError
            trainer_snapshot = None
            if trainer is not None:
                capture = getattr(trainer, "capture_startup_snapshot", None)
                if not callable(capture):
                    raise RuntimeError(
                        "Trainer does not support startup rollback snapshots"
                    )
                # The trainer snapshot retains holder and evaluation-record
                # identities, including completed saliency results.
                trainer_snapshot = capture()
            return TrainingStartupRollbackSnapshot(
                trainer=trainer,
                trainer_startup_snapshot=trainer_snapshot,
                saliency_status=boundary.saliency_status,
                saliency_request_sequence=self._saliency_request_sequence,
                saliency_cancellation_epoch=self._saliency_cancellation_epoch,
                saliency_job_sequence=self._saliency_job_sequence,
            )

    def restore_startup_rollback_snapshot(
        self,
        snapshot: TrainingStartupRollbackSnapshot,
    ) -> None:
        """Clean failed startup state before atomically restoring prior truth."""
        if not isinstance(snapshot, TrainingStartupRollbackSnapshot):
            raise TypeError("snapshot must be a TrainingStartupRollbackSnapshot")
        with self._training_pipeline_lock, self._saliency_job_lock:
            self._require_training_operation_idle_locked()
            if self._has_active_saliency_work_locked():
                raise StaleTrainingPipelineMutationError
            current = self.trainer
            lease = self._begin_training_operation_locked(
                kind="restore_failed_training_start",
                trainer=current,
            )

        try:
            if current is not None:
                clean = getattr(current, "clean", None)
                if not callable(clean):
                    raise RuntimeError(
                        "Failed startup trainer does not support cleanup"
                    )
                clean(force_update=True)

            trainer = snapshot.trainer
            if trainer is not None and snapshot.trainer_startup_snapshot is not None:
                restore = getattr(trainer, "restore_startup_snapshot", None)
                if not callable(restore):
                    raise RuntimeError(
                        "Trainer does not support startup rollback snapshots"
                    )
                restore(snapshot.trainer_startup_snapshot)

            with self._training_pipeline_lock, self._saliency_job_lock:
                if (
                    not self._training_operation_is_current_locked(lease)
                    or self.trainer is not current
                    or self._has_active_saliency_work_locked()
                ):
                    raise StaleTrainingPipelineMutationError
                self.trainer = cast(Any, trainer)
                self._saliency_request_sequence = snapshot.saliency_request_sequence
                self._saliency_cancellation_epoch = snapshot.saliency_cancellation_epoch
                self._saliency_job_sequence = snapshot.saliency_job_sequence
                self._post_training_saliency_status = snapshot.saliency_status
        finally:
            with self._training_pipeline_lock:
                self._finish_training_operation_locked(lease)

    def _capture_pipeline_mutation_boundary_locked(
        self,
    ) -> TrainingPipelineMutationBoundary:
        return TrainingPipelineMutationBoundary(
            read_boundary=self._capture_training_read_boundary_locked(),
            terminal_outcome=read_training_terminal_outcome(self.trainer),
            saliency_status=self._post_training_saliency_status,
            saliency_work_active=self._has_active_saliency_work_locked(),
            training_work_active=self._training_operation_owner is not None,
        )

    def _require_training_operation_idle_locked(self) -> None:
        if self._training_operation_owner is not None:
            raise RuntimeError(
                "Another training lifecycle operation is still in progress"
            )

    def _begin_training_operation_locked(
        self,
        *,
        kind: str,
        trainer: object | None,
    ) -> _TrainingPipelineOperationLease:
        self._require_training_operation_idle_locked()
        self._training_operation_sequence += 1
        lease = _TrainingPipelineOperationLease(
            generation=self._training_operation_sequence,
            kind=kind,
            trainer=trainer,
        )
        self._training_operation_owner = lease
        return lease

    def _training_operation_is_current_locked(
        self,
        lease: _TrainingPipelineOperationLease,
    ) -> bool:
        return self._training_operation_owner == lease

    def _finish_training_operation_locked(
        self,
        lease: _TrainingPipelineOperationLease,
    ) -> None:
        if self._training_operation_is_current_locked(lease):
            self._training_operation_owner = None

    def _capture_training_read_boundary_locked(self) -> TrainingReadBoundary:
        trainer = self.trainer
        if trainer is None:
            return TrainingReadBoundary.no_trainer()
        token_getter = getattr(type(trainer), "get_state_snapshot_token", None)
        identity_getter = getattr(type(trainer), "get_state_snapshot_identity", None)
        if not callable(token_getter) or not callable(identity_getter):
            return self._untracked_training_boundary(trainer)
        try:
            token = token_getter(trainer)
            identity = identity_getter(trainer)
        except Exception:
            return self._untracked_training_boundary(trainer)
        if (
            not isinstance(token, TrainingStateToken)
            or not isinstance(identity, str)
            or not identity.strip()
        ):
            return self._untracked_training_boundary(trainer)
        return TrainingReadBoundary(identity.strip(), token)

    @staticmethod
    def _untracked_training_boundary(trainer: object) -> TrainingReadBoundary:
        return TrainingReadBoundary(
            trainer_identity=(
                f"untracked:{type(trainer).__module__}.{type(trainer).__qualname__}"
            ),
            token=TrainingStateToken(generation=0, stable=False),
        )

    def has_active_saliency_work(self) -> bool:
        """Return whether a saliency request, worker, or cleanup still owns work."""
        with self._saliency_job_lock:
            return self._has_active_saliency_work_locked()

    def _has_active_saliency_work_locked(self) -> bool:
        return bool(
            self._saliency_request_owner is not None
            or self._saliency_request_cleanup_events
            or self._saliency_job_thread is not None
            or self._saliency_job_cancel is not None
            or self._saliency_job_cleanup_complete is not None
            or self._post_training_saliency_status.phase
            in {
                PostTrainingSaliencyPhase.PENDING,
                PostTrainingSaliencyPhase.RUNNING,
            }
        )

    def retire_trainer_if_current(
        self,
        expected: TrainingPipelineMutationBoundary,
    ) -> bool:
        """Compare-and-retire one stable trainer after speculative data work."""
        return self.commit_pipeline_replacement(expected, publish=lambda: None)

    def commit_pipeline_replacement(
        self,
        expected: TrainingPipelineMutationBoundary,
        *,
        publish: Callable[[], None],
    ) -> bool:
        """Publish data and fence trainer retirement under one lifecycle lease."""
        if not isinstance(expected, TrainingPipelineMutationBoundary):
            raise TypeError("expected must be a TrainingPipelineMutationBoundary")
        if not callable(publish):
            raise TypeError("publish must be callable")
        with self._training_pipeline_lock:
            with self._saliency_job_lock:
                current = self._capture_pipeline_mutation_boundary_locked()
            if current != expected:
                raise StaleTrainingPipelineMutationError
            if (
                not current.read_boundary.stable
                or current.saliency_work_active
                or current.training_work_active
                or (
                    current.read_boundary.trainer_identity is not None
                    and not current.terminal_outcome.is_quiescent
                )
            ):
                raise StaleTrainingPipelineMutationError
            trainer = self.trainer
            lease = self._begin_training_operation_locked(
                kind="retire_trainer",
                trainer=trainer,
            )
            try:
                publish()
            except BaseException:
                self._finish_training_operation_locked(lease)
                raise
        self._replace_trainer_with_lease(
            trainer=trainer,
            replacement=None,
            lease=lease,
            force_update=True,
        )
        return trainer is not None

    def has_trainer(self) -> bool:
        """Return whether a trainer is configured."""
        with self._training_pipeline_lock:
            return self.trainer is not None

    # --- Cleanup ---

    def clean_trainer(self, force_update: bool = True) -> None:
        """Clean the trainer.

        Args:
            force_update: If ``False``, raises when a trainer exists.

        """
        with self._training_pipeline_lock:
            trainer = self.trainer
            if not force_update and trainer is not None:
                raise ValueError(
                    "This step has already been done, "
                    "all following data will be removed if you reset this step.\n"
                    "Please clean_trainer first.",
                )
            lease = self._begin_training_operation_locked(
                kind="clean_trainer",
                trainer=trainer,
            )
        self._replace_trainer_with_lease(
            trainer=trainer,
            replacement=None,
            lease=lease,
            force_update=force_update,
        )

    def _replace_trainer_with_lease(
        self,
        *,
        trainer: Trainer | None,
        replacement: Trainer | None,
        lease: _TrainingPipelineOperationLease,
        force_update: bool,
    ) -> None:
        """Clean outside the manager lock, then compare-and-publish replacement."""
        try:
            self._cancel_post_training_saliency(wait=True)
            if trainer is not None:
                force_running_cleanup = force_update and trainer.is_running()
                trainer.clean(force_update=force_running_cleanup)
            with self._training_pipeline_lock:
                if (
                    not self._training_operation_is_current_locked(lease)
                    or self.trainer is not trainer
                ):
                    raise StaleTrainingPipelineMutationError
                self.trainer = replacement
                self._retire_post_training_saliency_status()
        finally:
            with self._training_pipeline_lock:
                self._finish_training_operation_locked(lease)
