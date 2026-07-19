from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.training_runtime import StudyTrainingRuntime
from XBrainLab.backend.exceptions import StaleTrainingPipelineMutationError
from XBrainLab.backend.training_manager import (
    PostTrainingSaliencyTarget,
    PostTrainingSaliencyTerminalDeliveryState,
)
from XBrainLab.backend.training_state_contract import (
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
)


class _Trainer:
    current_idx = 0

    def get_terminal_outcome(self) -> TrainingTerminalOutcome:
        return TrainingTerminalOutcome(
            state=TrainingOutcomeState.COMPLETED,
            run=TrainingRunIdentity(trainer_id="runtime-port", run_id=1),
        )

    def get_state_snapshot_identity(self) -> str:
        return "runtime-port"

    def get_state_snapshot_token(self) -> TrainingStateToken:
        return TrainingStateToken(generation=7, stable=True)

    def get_training_plan_holders(self) -> list[str]:
        return ["plan-a", "plan-b"]


class _TrainingManager:
    def __init__(self) -> None:
        self.model_holder: Any | None = object()
        self.training_option: Any | None = object()
        self.saliency_params: Any | None = {"Gradient": {}}
        self.trainer: Any | None = _Trainer()
        self.calls: list[tuple[Any, ...]] = []
        self.status = PostTrainingSaliencyStatus.idle(generation=3)
        self.saliency_work_active = False
        self.training_work_active = False
        self.delivery_state = PostTrainingSaliencyTerminalDeliveryState(
            pending_generations=(),
            active_generation=None,
            delivered_generation=3,
            retry_owner_active=False,
            retry_unavailable=False,
        )

    def stop_training(self, wait_timeout: float | None = None) -> bool:
        self.calls.append(("stop", wait_timeout))
        return True

    def stop_training_if_present(self, wait_timeout: float | None = None) -> bool:
        if self.trainer is None:
            return False
        return self.stop_training(wait_timeout=wait_timeout)

    def wait_for_training_completion(self, timeout: float | None = None) -> bool:
        self.calls.append(("wait_training", timeout))
        return True

    def is_training(self) -> bool:
        self.calls.append(("is_training",))
        return True

    def has_trainer(self) -> bool:
        return self.trainer is not None

    def get_training_plan_holders_snapshot(self) -> tuple[Any, ...]:
        if self.trainer is None:
            return ()
        return tuple(self.trainer.get_training_plan_holders())

    def get_current_training_plan_index(self) -> int | None:
        if self.trainer is None:
            return None
        return int(self.trainer.current_idx)

    def get_training_terminal_outcome(self) -> TrainingTerminalOutcome:
        if self.trainer is None:
            return TrainingTerminalOutcome(state=TrainingOutcomeState.UNKNOWN)
        return self.trainer.get_terminal_outcome()

    def get_post_training_saliency_status(self) -> PostTrainingSaliencyStatus:
        self.calls.append(("status",))
        return self.status

    def get_post_training_saliency_terminal_delivery_state(
        self,
    ) -> PostTrainingSaliencyTerminalDeliveryState:
        self.calls.append(("delivery_state",))
        return self.delivery_state

    def subscribe_post_training_saliency_terminal(self, callback: Any) -> None:
        self.calls.append(("subscribe", callback))

    def unsubscribe_post_training_saliency_terminal(self, callback: Any) -> None:
        self.calls.append(("unsubscribe", callback))

    @contextmanager
    def defer_post_training_saliency_terminal_notifications(
        self,
        stage: Any = None,
    ) -> Iterator[None]:
        self.calls.append(("defer_enter", stage))
        try:
            yield
        finally:
            self.calls.append(("defer_exit", stage))

    def publish_post_training_saliency_submission_failure(
        self,
        target: PostTrainingSaliencyTarget,
        error: BaseException,
    ) -> PostTrainingSaliencyScheduleOutcome:
        self.calls.append(("submission_failure", target, error))
        reason = PostTrainingSaliencyScheduleReason.THREAD_START_FAILED
        message = str(error)
        status = PostTrainingSaliencyStatus(
            phase=PostTrainingSaliencyPhase.FAILED,
            generation=self.status.generation + 1,
            run=target.run,
            training_generation=7,
            methods=("Gradient",),
            error_code=reason.value,
            message=message,
            diagnostic_type=type(error).__name__,
        )
        self.status = status
        return PostTrainingSaliencyScheduleOutcome(
            disposition=PostTrainingSaliencyScheduleDisposition.REJECTED,
            reason=reason,
            message=message,
            status=status,
        )

    def wait_for_saliency_job(self, timeout: float | None = None) -> bool:
        self.calls.append(("wait_job", timeout))
        return True

    def cancel_saliency_job(self) -> None:
        self.calls.append(("cancel_job",))

    def wait_for_saliency_terminal_delivery(
        self,
        timeout: float | None = None,
    ) -> bool:
        self.calls.append(("wait_delivery", timeout))
        return True

    def retry_post_training_saliency_terminal_delivery(self) -> None:
        self.calls.append(("retry_delivery",))

    def capture_pipeline_mutation_boundary(self) -> TrainingPipelineMutationBoundary:
        trainer = self.trainer
        read_boundary = (
            TrainingReadBoundary.no_trainer()
            if trainer is None
            else TrainingReadBoundary(
                trainer_identity=trainer.get_state_snapshot_identity(),
                token=trainer.get_state_snapshot_token(),
            )
        )
        terminal_outcome = (
            TrainingTerminalOutcome(
                state=TrainingOutcomeState.UNKNOWN,
                detail="No trainer is configured.",
            )
            if trainer is None
            else trainer.get_terminal_outcome()
        )
        return TrainingPipelineMutationBoundary(
            read_boundary=read_boundary,
            terminal_outcome=terminal_outcome,
            saliency_status=self.status,
            saliency_work_active=self.saliency_work_active,
            training_work_active=self.training_work_active,
        )

    def capture_training_read_boundary(self) -> TrainingReadBoundary:
        return self.capture_pipeline_mutation_boundary().read_boundary

    def retire_trainer_if_current(
        self,
        expected: TrainingPipelineMutationBoundary,
    ) -> bool:
        current = self.capture_pipeline_mutation_boundary()
        if current != expected:
            raise StaleTrainingPipelineMutationError
        retired = self.trainer is not None
        self.trainer = None
        self.status = PostTrainingSaliencyStatus.idle(
            generation=self.status.generation + 1,
        )
        self.calls.append(("retire_pipeline", expected))
        return retired

    def commit_pipeline_replacement(
        self,
        expected: TrainingPipelineMutationBoundary,
        *,
        publish: Callable[[], None],
    ) -> bool:
        current = self.capture_pipeline_mutation_boundary()
        if current != expected:
            raise StaleTrainingPipelineMutationError
        publish()
        retired = self.trainer is not None
        self.trainer = None
        self.status = PostTrainingSaliencyStatus.idle(
            generation=self.status.generation + 1,
        )
        self.calls.append(("commit_replacement", expected))
        return retired


class _Study:
    def __init__(self, manager: _TrainingManager) -> None:
        self.datasets = ["dataset-a", "dataset-b"]
        self.training_manager = manager


def _runtime() -> tuple[StudyTrainingRuntime, _TrainingManager]:
    manager = _TrainingManager()
    study = _Study(manager)
    return StudyTrainingRuntime(study), manager


def test_training_runtime_publishes_typed_context_and_terminal_truth() -> None:
    runtime, manager = _runtime()

    context = runtime.resource_context()
    configuration = runtime.configuration_snapshot()

    assert context.datasets == ("dataset-a", "dataset-b")
    assert context.training_option is manager.training_option
    assert context.model_holder is manager.model_holder
    assert configuration.training_option is manager.training_option
    assert configuration.model_holder is manager.model_holder
    assert configuration.saliency_params == manager.saliency_params
    assert configuration.saliency_params is not manager.saliency_params
    assert runtime.has_trainer() is True
    assert runtime.is_training() is True
    assert runtime.training_plan_holders() == ("plan-a", "plan-b")
    assert runtime.current_training_plan_index() == 0
    assert runtime.capture_read_boundary().trainer_identity == "runtime-port"
    assert runtime.capture_read_boundary().token == TrainingStateToken(7, True)
    assert runtime.stop_training(wait_timeout=0.25) is True
    assert runtime.terminal_outcome().state is TrainingOutcomeState.COMPLETED
    assert manager.calls == [("is_training",), ("stop", 0.25)]


def test_training_configuration_snapshot_cannot_mutate_manager_saliency() -> None:
    runtime, manager = _runtime()

    configuration = runtime.configuration_snapshot()
    assert configuration.saliency_params is not None
    configuration.saliency_params["Gradient"]["nt_samples"] = 99

    assert manager.saliency_params == {"Gradient": {}}


def test_training_runtime_clear_configuration_owns_manager_fields() -> None:
    runtime, manager = _runtime()

    runtime.clear_configuration()

    assert manager.model_holder is None
    assert manager.training_option is None
    assert manager.saliency_params is None


def test_training_runtime_forwards_saliency_lifecycle_without_changing_identity() -> (
    None
):
    runtime, manager = _runtime()

    def callback(_status: PostTrainingSaliencyStatus) -> bool:
        return True

    def stage(_status: PostTrainingSaliencyStatus) -> bool:
        return True

    failure = RuntimeError("submission failed")

    assert runtime.saliency_status() is manager.status
    assert runtime.saliency_delivery_state() is manager.delivery_state
    runtime.subscribe_saliency_terminal(callback)
    runtime.unsubscribe_saliency_terminal(callback)
    with runtime.defer_saliency_terminal(stage):
        manager.calls.append(("inside",))
    target = PostTrainingSaliencyTarget(
        run=TrainingRunIdentity(trainer_id="runtime-port", run_id=1),
        finished_runs_before=0,
        finished_runs_after=1,
        append=True,
    )
    submission = runtime.publish_saliency_submission_failure(target, failure)
    assert submission.disposition is (PostTrainingSaliencyScheduleDisposition.REJECTED)
    assert submission.status.phase is PostTrainingSaliencyPhase.FAILED
    assert runtime.wait_for_saliency_job(timeout=0.5) is True
    runtime.cancel_saliency_job()
    assert runtime.wait_for_saliency_delivery(timeout=0.75) is True
    runtime.retry_saliency_delivery()

    assert manager.calls == [
        ("status",),
        ("delivery_state",),
        ("subscribe", callback),
        ("unsubscribe", callback),
        ("defer_enter", stage),
        ("inside",),
        ("defer_exit", stage),
        ("submission_failure", target, failure),
        ("wait_job", 0.5),
        ("cancel_job",),
        ("wait_delivery", 0.75),
        ("retry_delivery",),
    ]


def test_training_runtime_stop_without_trainer_is_a_noop() -> None:
    runtime, manager = _runtime()
    manager.trainer = None

    assert runtime.stop_training(wait_timeout=1.0) is False
    assert runtime.terminal_outcome().state is TrainingOutcomeState.UNKNOWN
    assert manager.calls == []


def test_training_runtime_raw_replacement_requires_no_trainer() -> None:
    runtime, _manager = _runtime()

    with pytest.raises(PreconditionError, match="training history"):
        runtime.begin_raw_replacement()


def test_training_runtime_rejects_unknown_outcome_when_trainer_exists() -> None:
    runtime, manager = _runtime()
    assert manager.trainer is not None
    manager.trainer.get_terminal_outcome = lambda: TrainingTerminalOutcome(
        state=TrainingOutcomeState.UNKNOWN,
        detail="backend read failed",
    )

    with pytest.raises(PreconditionError, match="could not be verified"):
        runtime.begin_downstream_replacement()


def test_training_runtime_allows_not_started_trainer_replacement() -> None:
    runtime, manager = _runtime()
    assert manager.trainer is not None
    manager.trainer.get_terminal_outcome = lambda: TrainingTerminalOutcome(
        state=TrainingOutcomeState.NOT_STARTED,
    )

    boundary = runtime.begin_downstream_replacement()

    assert boundary.terminal_outcome.state is TrainingOutcomeState.NOT_STARTED


def test_training_runtime_blocks_active_lifecycle_operation() -> None:
    runtime, manager = _runtime()
    manager.training_work_active = True

    with pytest.raises(PreconditionError, match="lifecycle operation"):
        runtime.begin_downstream_replacement()


@pytest.mark.parametrize(
    "phase",
    [PostTrainingSaliencyPhase.PENDING, PostTrainingSaliencyPhase.RUNNING],
)
def test_training_runtime_blocks_downstream_replacement_during_saliency(
    phase: PostTrainingSaliencyPhase,
) -> None:
    runtime, manager = _runtime()
    pending = PostTrainingSaliencyStatus.pending(
        generation=4,
        run=TrainingRunIdentity(trainer_id="runtime-port", run_id=1),
        training_generation=7,
        methods=("Gradient",),
    )
    manager.status = (
        pending
        if phase is PostTrainingSaliencyPhase.PENDING
        else pending.transition(
            generation=4,
            phase=PostTrainingSaliencyPhase.RUNNING,
        )
    )
    manager.saliency_work_active = True

    with pytest.raises(PreconditionError, match="saliency"):
        runtime.begin_downstream_replacement()


def test_training_runtime_commit_rejects_changed_boundary() -> None:
    runtime, manager = _runtime()
    boundary = runtime.begin_downstream_replacement()
    manager.status = PostTrainingSaliencyStatus.idle(generation=99)

    with pytest.raises(PreconditionError, match="changed"):
        runtime.commit_pipeline_invalidation(boundary)

    assert manager.trainer is not None


def test_training_runtime_commit_retires_stable_trainer_once() -> None:
    runtime, manager = _runtime()
    boundary = runtime.begin_downstream_replacement()

    assert runtime.commit_pipeline_invalidation(boundary) is True
    assert manager.trainer is None
    assert manager.status == PostTrainingSaliencyStatus.idle(generation=4)
    assert [call[0] for call in manager.calls].count("retire_pipeline") == 1


def test_training_runtime_waits_for_training_completion() -> None:
    runtime, manager = _runtime()

    assert runtime.wait_for_training_completion(timeout=0.5) is True
    assert manager.calls == [("wait_training", 0.5)]


def test_training_runtime_commits_publication_and_retirement_together() -> None:
    runtime, manager = _runtime()
    boundary = runtime.begin_downstream_replacement()
    published: list[str] = []

    retired = runtime.commit_pipeline_replacement(
        boundary,
        publish=lambda: published.append("datasets"),
    )

    assert retired is True
    assert published == ["datasets"]
    assert manager.trainer is None
    assert [call[0] for call in manager.calls].count("commit_replacement") == 1
