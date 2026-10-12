"""Application boundary: training lifecycle behavior."""

from __future__ import annotations

from dataclasses import replace
from threading import Condition, Event, Lock, Thread, current_thread
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from tests.unit.backend.application.application_test_support import (
    THREAD_WATCHDOG_SECONDS,
    _prepare_saved_training_split,
    _publish_mock_training_identity,
    _RecoveryBlockingPlan,
    _valid_model_holder,
    _valid_training_option,
)
from XBrainLab.backend.application import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationService,
    ChangedState,
    CommandName,
    CommandResult,
    ErrorType,
    QueryStateCommand,
    StopTrainingCommand,
    TrainCommand,
    get_application_service,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import (
    Trainer,
    TrainingPlanHolder,
)
from XBrainLab.backend.training_state_contract import (
    TrainingLifecycleEvent,
    TrainingOutcomeState,
)


class _SlowCancellationPlan(TrainingPlanHolder):
    """Keep the worker alive after interruption until the test releases cleanup."""

    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.interrupt_requested = Event()
        self.error: str | None = None
        self.tracker = None

    def bind_state_tracker(self, tracker) -> None:
        self.tracker = tracker

    def get_name(self) -> str:
        return "Slow cancellation plan"

    def get_plans(self) -> list[Any]:
        return []

    def get_training_status(self) -> str:
        return "Pending"

    def train(self) -> None:
        self.started.set()
        assert self.release.wait(timeout=THREAD_WATCHDOG_SECONDS)

    def set_interrupt(self) -> None:
        self.interrupt_requested.set()

    def clear_interrupt(self) -> None:
        self.interrupt_requested.clear()


def test_synchronous_train_command_allows_stop_command_to_reach_active_worker() -> None:
    service = ApplicationService(Study())
    _prepare_saved_training_split(service)
    service.study.set_model_holder(_valid_model_holder())
    service.study.set_training_option(_valid_training_option())
    plan = _RecoveryBlockingPlan()
    trainer = Trainer([cast(TrainingPlanHolder, plan)])

    def install_blocking_plan(
        *,
        force_update: bool = False,
        append: bool = False,
    ) -> None:
        del force_update, append
        service.study.training_manager.trainer = trainer

    service.study.generate_plan = install_blocking_plan  # type: ignore[method-assign]
    train_results: list[CommandResult] = []
    stop_results: list[CommandResult] = []
    train_thread = Thread(
        target=lambda: train_results.append(
            service.execute(
                TrainCommand(
                    confirmed=True,
                    interactive=False,
                    resource_preflight_confirmed=True,
                )
            )
        )
    )
    stop_thread = Thread(
        target=lambda: stop_results.append(
            service.execute(StopTrainingCommand(wait_timeout=THREAD_WATCHDOG_SECONDS))
        )
    )

    train_thread.start()
    assert plan.started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    stop_thread.start()
    stop_reached_worker = plan._interrupt.wait(timeout=0.25)
    if not stop_reached_worker:
        # Release only this test's worker so a red assertion cannot leak a thread.
        plan.set_interrupt()

    train_thread.join(timeout=THREAD_WATCHDOG_SECONDS)
    stop_thread.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not train_thread.is_alive()
    assert not stop_thread.is_alive()
    assert stop_reached_worker is True
    assert len(stop_results) == 1
    assert stop_results[0].ok is True
    assert stop_results[0].diagnostics["terminal_outcome"] == "cancelled"
    assert len(train_results) == 1
    assert train_results[0].failed is True
    assert train_results[0].error_type is ErrorType.TRAINING
    assert train_results[0].message == "Training was cancelled."


def test_stop_command_reports_requested_until_real_worker_exit() -> None:
    service = ApplicationService(Study())
    plan = _SlowCancellationPlan()
    trainer = Trainer([cast(TrainingPlanHolder, plan)])
    service.study.training_manager.trainer = trainer
    trainer.run(interact=True)
    assert plan.started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    committed_before_stop = service.get_view_publication().state

    try:
        result = service.execute(StopTrainingCommand(wait_timeout=0.01))

        assert result.ok is True
        assert result.message == "Training stop requested."
        assert result.diagnostics["stopped"] is False
        assert result.diagnostics["terminal_outcome"] == "stop_requested"
        assert result.diagnostics["state_publication_deferred"] is True
        assert result.state == committed_before_stop
        assert trainer.is_running() is True
    finally:
        plan.release.set()
        thread = trainer.job_thread
        if thread is not None:
            thread.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert trainer.is_running() is False
    assert trainer.get_terminal_outcome().state is TrainingOutcomeState.CANCELLED


def test_train_command_blocked_until_backend_ready():
    service = ApplicationService(Study())

    result = service.execute(TrainCommand())

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert (
        "Save a valid data splitting specification before training." in result.message
    )
    assert result.state.training.has_trainer is False


def test_train_command_requires_confirmation_before_long_running_start():
    service = ApplicationService(Study())
    _prepare_saved_training_split(service)
    service.study.set_model_holder(_valid_model_holder())
    service.study.set_training_option(_valid_training_option())
    service.training.start_training = MagicMock(return_value=1)

    result = service.execute(TrainCommand())
    _publish_mock_training_identity(service)
    confirmed = service.execute(TrainCommand(confirmed=True))

    assert result.failed is True
    assert result.error_type == ErrorType.CONFIRMATION_REQUIRED
    assert confirmed.ok is True
    service.training.start_training.assert_called_once()


class _SynchronousFailingTrainingPlan(TrainingPlanHolder):
    """Real Trainer-compatible plan that publishes one terminal failure."""

    def __init__(self, message: str) -> None:
        self.error: str | None = None
        self._message = message
        self._tracker: Any | None = None

    def bind_state_tracker(self, tracker: Any) -> None:
        self._tracker = tracker

    def get_name(self) -> str:
        return "Failing plan"

    def get_plans(self) -> list[Any]:
        return []

    def train(self) -> None:
        self.error = self._message

    def set_interrupt(self) -> None:
        return None

    def clear_interrupt(self) -> None:
        return None


@pytest.mark.parametrize(
    ("failure_message", "is_oom"),
    [
        ("CUDA out of memory during training. Reduce batch size.", True),
        ("training data loader failed", False),
    ],
)
def test_synchronous_train_command_returns_failed_result_for_plan_failure(
    failure_message: str,
    is_oom: bool,
) -> None:
    service = ApplicationService(Study())
    _prepare_saved_training_split(service)
    service.study.set_model_holder(_valid_model_holder())
    service.study.set_training_option(_valid_training_option())

    def install_failing_plan(
        *,
        force_update: bool = False,
        append: bool = False,
    ) -> None:
        del force_update, append
        service.study.trainer = Trainer(
            [cast(TrainingPlanHolder, _SynchronousFailingTrainingPlan(failure_message))]
        )

    service.study.generate_plan = install_failing_plan  # type: ignore[method-assign]

    result = service.execute(
        TrainCommand(
            confirmed=True,
            interactive=False,
            resource_preflight_confirmed=True,
        ),
    )

    assert result.ok is False
    assert result.failed is True
    assert result.error_type is ErrorType.TRAINING
    assert result.recoverable is True
    assert result.message == failure_message
    assert result.diagnostics["training_failed"] is True
    assert result.diagnostics["cuda_oom"] is is_oom
    assert result.state.training.progress_message == f"Error: {failure_message}"


def test_synchronous_training_failure_waits_for_exact_terminal_handoff(
    monkeypatch,
) -> None:
    """Worker failure is not returned until its monitor publication is terminal."""
    service = ApplicationService(Study())
    _prepare_saved_training_split(service)
    service.study.set_model_holder(_valid_model_holder())
    service.study.set_training_option(_valid_training_option())
    failure_message = "training data loader failed"
    plan = _SynchronousFailingTrainingPlan(failure_message)
    trainer = Trainer([cast(TrainingPlanHolder, plan)])
    plan_started = Event()
    release_plan = Event()
    monitor_waiting = Event()
    release_monitor_poll = Event()
    results: list[CommandResult] = []

    def install_failing_plan(
        *,
        force_update: bool = False,
        append: bool = False,
    ) -> None:
        del force_update, append
        service.study.training_manager.trainer = trainer

    def controlled_monitor_wait(_timeout: float | None = None) -> bool:
        monitor_waiting.set()
        assert release_monitor_poll.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return False

    def blocking_failure() -> None:
        plan_started.set()
        assert release_plan.wait(timeout=THREAD_WATCHDOG_SECONDS)
        plan.error = failure_message

    plan.train = blocking_failure  # type: ignore[method-assign]
    service.study.generate_plan = install_failing_plan  # type: ignore[method-assign]
    training_state = cast(Any, service.training)
    monkeypatch.setattr(
        training_state._shutdown_event,
        "wait",
        controlled_monitor_wait,
    )
    train_thread = Thread(
        target=lambda: results.append(
            service.execute(
                TrainCommand(
                    confirmed=True,
                    interactive=False,
                    resource_preflight_confirmed=True,
                )
            )
        ),
        name="synchronous-failing-train",
    )

    train_thread.start()
    assert plan_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    assert monitor_waiting.wait(timeout=THREAD_WATCHDOG_SECONDS)
    release_plan.set()
    worker = trainer.job_thread
    assert worker is not None
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)
    assert not worker.is_alive()
    returned_before_terminal_handoff = not train_thread.is_alive()

    release_monitor_poll.set()
    train_thread.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert returned_before_terminal_handoff is False
    assert not train_thread.is_alive()
    assert len(results) == 1
    assert results[0].failed is True
    assert results[0].error_type is ErrorType.TRAINING
    assert results[0].message == failure_message


def test_train_restart_cleanup_waits_before_command_lock_and_fails_recoverably(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    command_lock = Lock()
    service._command_lock = command_lock
    lock_was_free: list[bool] = []

    def wait_until_restart_safe(*, timeout: float | None = None) -> bool:
        assert timeout == 2.0
        acquired = command_lock.acquire(blocking=False)
        lock_was_free.append(acquired)
        if acquired:
            command_lock.release()
        return False

    monkeypatch.setattr(service.training, "is_training", lambda: False)
    monkeypatch.setattr(
        service.training,
        "wait_until_restart_safe",
        wait_until_restart_safe,
    )
    execute_with_lock = MagicMock()
    monkeypatch.setattr(service, "_execute_with_command_lock", execute_with_lock)

    result = service.execute(TrainCommand(confirmed=True, interactive=True))

    assert lock_was_free == [True]
    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.diagnostics["training_restart_pending"] is True
    execute_with_lock.assert_not_called()


def test_wait_for_background_tasks_waits_for_saliency_job() -> None:
    service = ApplicationService(Study())
    call_order: list[str] = []
    service.training.wait_for_terminal_notification = MagicMock(
        side_effect=lambda generation=None, timeout=None: (
            call_order.append(f"monitor_terminal:{generation}") or True
        ),
    )
    service.publication_lifecycle.publish_training_terminal_state = MagicMock(
        side_effect=lambda: call_order.append("terminal_reconcile") or True,
    )
    service.training_publications.wait_for_training_delivery = MagicMock(
        side_effect=lambda timeout=None: call_order.append("training_terminal") or True,
    )
    service.training_runtime.wait_for_saliency_job = MagicMock(
        side_effect=lambda timeout=None: call_order.append("saliency") or True,
    )
    service.training_runtime.wait_for_saliency_delivery = MagicMock(
        side_effect=lambda timeout=None: call_order.append("manager_terminal") or True,
    )
    service.training_publications.wait_for_saliency_delivery = MagicMock(
        side_effect=lambda timeout=None: call_order.append("saliency_terminal") or True,
    )

    assert (
        service.wait_for_background_tasks(
            timeout=1.0,
            training_handoff_generation=23,
        )
        is True
    )

    assert call_order == [
        "monitor_terminal:23",
        "terminal_reconcile",
        "training_terminal",
        "saliency",
        "manager_terminal",
        "saliency_terminal",
    ]
    monitor_terminal_timeout = (
        service.training.wait_for_terminal_notification.call_args.kwargs["timeout"]
    )
    training_terminal_timeout = (
        service.training_publications.wait_for_training_delivery.call_args.kwargs[
            "timeout"
        ]
    )
    saliency_timeout = service.training_runtime.wait_for_saliency_job.call_args.kwargs[
        "timeout"
    ]
    assert (
        0.0
        <= saliency_timeout
        <= training_terminal_timeout
        <= monitor_terminal_timeout
        <= 1.0
    )


def test_wait_for_background_tasks_retries_terminal_reconciliation_after_empty_ledger(
    monkeypatch,
) -> None:
    """A transient monitor refresh failure cannot look like an idle success."""
    service = ApplicationService(Study())
    reconcile = MagicMock(side_effect=[False, True])
    monkeypatch.setattr(
        service.publication_lifecycle,
        "publish_training_terminal_state",
        reconcile,
    )

    assert service.wait_for_background_tasks(timeout=1.0) is True

    assert reconcile.call_count == 2


def test_wait_for_background_tasks_rejects_persistent_terminal_reconciliation_failure(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    reconcile = MagicMock(return_value=False)
    monkeypatch.setattr(
        service.publication_lifecycle,
        "publish_training_terminal_state",
        reconcile,
    )

    assert service.wait_for_background_tasks(timeout=1.0) is False

    assert reconcile.call_count == 2


def test_synchronous_train_waits_for_application_background_tasks() -> None:
    service = ApplicationService(Study())
    expected = MagicMock(ok=True)
    expected.diagnostics = {"training_handoff_generation": 7}
    service._execute_serialized = MagicMock(return_value=expected)
    service.wait_for_background_tasks = MagicMock(return_value=True)

    result = service.execute(TrainCommand(interactive=False))

    assert result is expected
    service.wait_for_background_tasks.assert_called_once_with(
        timeout=300.0, training_handoff_generation=7
    )


def test_synchronous_train_waits_for_real_monitor_terminal_handoff(monkeypatch) -> None:
    """Worker exit alone is not completion until monitor callbacks have returned."""
    service = ApplicationService(Study())
    _prepare_saved_training_split(service)
    service.study.set_model_holder(_valid_model_holder())
    service.study.set_training_option(_valid_training_option())
    plan = _SlowCancellationPlan()
    trainer = Trainer([cast(TrainingPlanHolder, plan)])
    monitor_waiting = Event()
    release_monitor_poll = Event()
    terminal_events: list[TrainingLifecycleEvent] = []
    results: list[CommandResult] = []
    failures: list[BaseException] = []

    def install_plan(
        *,
        force_update: bool = False,
        append: bool = False,
    ) -> None:
        del force_update, append
        service.study.training_manager.trainer = trainer

    def controlled_monitor_wait(_timeout: float | None = None) -> bool:
        monitor_waiting.set()
        assert release_monitor_poll.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return False

    def execute_train() -> None:
        try:
            results.append(
                service.execute(
                    TrainCommand(
                        confirmed=True,
                        interactive=False,
                        resource_preflight_confirmed=True,
                    )
                )
            )
        except BaseException as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    service.study.generate_plan = install_plan  # type: ignore[method-assign]
    training_state = cast(Any, service.training)
    monkeypatch.setattr(
        training_state._shutdown_event,
        "wait",
        controlled_monitor_wait,
    )
    service.training.subscribe("training_terminal_published", terminal_events.append)
    train_thread = Thread(target=execute_train, name="synchronous-train")

    train_thread.start()
    assert plan.started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    assert monitor_waiting.wait(timeout=THREAD_WATCHDOG_SECONDS)
    plan.release.set()
    worker = trainer.job_thread
    assert worker is not None
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)
    returned_before_terminal_handoff = not train_thread.is_alive()
    release_monitor_poll.set()
    train_thread.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert returned_before_terminal_handoff is False
    assert not train_thread.is_alive()
    assert failures == []
    assert len(results) == 1
    assert results[0].ok is True
    assert isinstance(results[0].diagnostics["training_handoff_generation"], int)
    assert len(terminal_events) == 1


def test_parallel_services_keep_synchronous_training_handoffs_isolated() -> None:
    """Deferred waits may overlap without mixing either run's evidence."""
    study = Study()
    first_service = ApplicationService(study)
    second_service = ApplicationService(study)
    state = first_service.get_view_publication().state
    first_waiting = Event()
    release_first = Event()
    second_completed = Event()
    results: dict[str, CommandResult] = {}
    waited_generations: dict[str, list[int | None]] = {
        "first": [],
        "second": [],
    }

    def started_result(generation: int, identity: str) -> CommandResult:
        return CommandResult.success_result(
            command_name=CommandName.TRAIN.value,
            message="Training started.",
            state=state,
            changed_state=ChangedState(training_changed=True),
            diagnostics={
                "synchronous_completion_deferred": True,
                "training_handoff_generation": generation,
                "training_trainer_identity": identity,
            },
        )

    def complete_first(started: CommandResult) -> CommandResult:
        assert started.diagnostics["training_handoff_generation"] == 41
        assert started.diagnostics["training_trainer_identity"] == "trainer-A"
        assert study._synchronous_training_lifecycle_lock.locked() is False
        first_waiting.set()
        assert release_first.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return replace(
            started,
            message="Training A completed.",
            diagnostics={
                "training_handoff_generation": 41,
                "training_trainer_identity": "trainer-A",
            },
        )

    def complete_second(started: CommandResult) -> CommandResult:
        assert started.diagnostics["training_handoff_generation"] == 42
        assert started.diagnostics["training_trainer_identity"] == "trainer-B"
        assert study._synchronous_training_lifecycle_lock.locked() is False
        second_completed.set()
        return replace(
            started,
            message="Training B completed.",
            diagnostics={
                "training_handoff_generation": 42,
                "training_trainer_identity": "trainer-B",
            },
        )

    def background_wait(owner: str):
        def wait(
            timeout: float | None = None,
            *,
            training_handoff_generation: int | None = None,
        ) -> bool:
            assert timeout is not None and timeout > 0
            waited_generations[owner].append(training_handoff_generation)
            return True

        return wait

    first_service._execute_serialized = MagicMock(  # type: ignore[method-assign]
        return_value=started_result(41, "trainer-A")
    )
    second_service._execute_serialized = MagicMock(  # type: ignore[method-assign]
        return_value=started_result(42, "trainer-B")
    )
    first_service.synchronous_training_lifecycle.complete_deferred = complete_first  # type: ignore[method-assign]
    second_service.synchronous_training_lifecycle.complete_deferred = complete_second  # type: ignore[method-assign]
    first_service.wait_for_background_tasks = background_wait("first")  # type: ignore[method-assign]
    second_service.wait_for_background_tasks = background_wait("second")  # type: ignore[method-assign]

    first = Thread(
        target=lambda: results.__setitem__(
            "first",
            first_service.execute(TrainCommand(interactive=False)),
        ),
        name="first-synchronous-train",
    )
    second = Thread(
        target=lambda: results.__setitem__(
            "second",
            second_service.execute(TrainCommand(interactive=False)),
        ),
        name="second-synchronous-train",
    )
    first.start()
    assert first_waiting.wait(timeout=THREAD_WATCHDOG_SECONDS)
    second.start()
    assert second_completed.wait(timeout=THREAD_WATCHDOG_SECONDS)
    release_first.set()
    first.join(timeout=THREAD_WATCHDOG_SECONDS)
    second.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not first.is_alive()
    assert not second.is_alive()
    assert results["first"].diagnostics["training_trainer_identity"] == "trainer-A"
    assert results["second"].diagnostics["training_trainer_identity"] == "trainer-B"
    assert waited_generations == {"first": [41], "second": [42]}


def test_close_wakes_synchronous_train_waiting_for_terminal_handoff() -> None:
    service = ApplicationService(Study())
    state = service.get_view_publication().state
    wait_entered = Event()
    release_wait = Event()
    close_done = Event()
    cancelled: list[str] = []
    train_results: list[CommandResult] = []
    service._execute_serialized = MagicMock(
        return_value=CommandResult.success_result(
            command_name=CommandName.TRAIN.value,
            message="Training completed.",
            state=state,
            changed_state=ChangedState(training_changed=True),
            diagnostics={"training_handoff_generation": 51},
        )
    )

    def wait_for_terminal(
        generation: int | None = None,
        *,
        timeout: float | None = None,
    ) -> bool:
        del timeout
        assert generation == 51
        wait_entered.set()
        assert release_wait.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return False

    def cancel_terminal_waits(reason: str) -> None:
        cancelled.append(reason)
        release_wait.set()

    service.training.wait_for_terminal_notification = wait_for_terminal  # type: ignore[method-assign]
    service.training.cancel_terminal_notification_waits = cancel_terminal_waits  # type: ignore[attr-defined,method-assign]
    train_thread = Thread(
        target=lambda: train_results.append(
            service.execute(TrainCommand(interactive=False))
        ),
        name="closing-synchronous-train",
    )

    def close_service() -> None:
        service.close()
        close_done.set()

    close_thread = Thread(target=close_service, name="application-service-close")
    train_thread.start()
    assert wait_entered.wait(timeout=THREAD_WATCHDOG_SECONDS)
    close_thread.start()
    closed_without_manual_release = close_done.wait(timeout=0.5)
    if not closed_without_manual_release:
        release_wait.set()
    close_thread.join(timeout=THREAD_WATCHDOG_SECONDS)
    train_thread.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert closed_without_manual_release is True
    assert cancelled == ["Application service is closing."]
    assert not close_thread.is_alive()
    assert not train_thread.is_alive()
    assert len(train_results) == 1
    assert train_results[0].failed is True


def test_close_stops_worker_blocking_synchronous_training_completion() -> None:
    service = ApplicationService(Study())
    state = service.get_view_publication().state
    worker_wait_entered = Event()
    worker_released = Event()
    close_done = Event()
    stop_timeouts: list[float | None] = []
    train_results: list[CommandResult] = []
    service._execute_serialized = MagicMock(
        return_value=CommandResult.success_result(
            command_name=CommandName.TRAIN.value,
            message="Training started.",
            state=state,
            changed_state=ChangedState(training_changed=True),
            diagnostics={
                "synchronous_completion_deferred": True,
                "training_handoff_generation": 52,
                "training_trainer_identity": "trainer-close-test",
            },
        )
    )

    def wait_for_worker(
        *,
        expected_trainer_identity: str | None = None,
        timeout: float | None = None,
    ) -> bool:
        assert expected_trainer_identity == "trainer-close-test"
        assert timeout is not None and timeout > 0
        worker_wait_entered.set()
        return worker_released.wait(timeout=THREAD_WATCHDOG_SECONDS)

    def stop_worker(*, wait_timeout: float | None = None) -> bool:
        stop_timeouts.append(wait_timeout)
        worker_released.set()
        return True

    service.training_runtime.wait_for_training_completion = wait_for_worker  # type: ignore[method-assign]
    service.training_runtime.stop_training = stop_worker  # type: ignore[method-assign]
    service.training.wait_for_terminal_notification = MagicMock(return_value=False)  # type: ignore[method-assign]
    service.training.cancel_terminal_notification_waits = MagicMock()  # type: ignore[attr-defined,method-assign]
    service._retry_synchronous_training_terminal_delivery = MagicMock(  # type: ignore[method-assign]
        return_value=False
    )

    train_thread = Thread(
        target=lambda: train_results.append(
            service.execute(TrainCommand(interactive=False))
        ),
        name="worker-blocked-synchronous-train",
    )
    close_thread = Thread(
        target=lambda: (service.close(), close_done.set()),
        name="application-service-close",
    )
    train_thread.start()
    assert worker_wait_entered.wait(timeout=THREAD_WATCHDOG_SECONDS)
    close_thread.start()
    closed_without_manual_release = close_done.wait(timeout=0.5)
    if not closed_without_manual_release:
        worker_released.set()
    close_thread.join(timeout=THREAD_WATCHDOG_SECONDS)
    train_thread.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert closed_without_manual_release is True
    assert stop_timeouts and stop_timeouts[0] is not None
    assert not close_thread.is_alive()
    assert not train_thread.is_alive()
    assert len(train_results) == 1
    assert train_results[0].failed is True


def test_close_does_not_commit_while_real_synchronous_worker_ignores_stop() -> None:
    service = ApplicationService(Study())
    _prepare_saved_training_split(service)
    service.study.set_model_holder(_valid_model_holder())
    service.study.set_training_option(_valid_training_option())
    plan = _SlowCancellationPlan()
    trainer = Trainer([cast(TrainingPlanHolder, plan)])
    results: list[CommandResult] = []

    def install_plan(
        *,
        force_update: bool = False,
        append: bool = False,
    ) -> None:
        del force_update, append
        service.study.training_manager.trainer = trainer

    service.study.generate_plan = install_plan  # type: ignore[method-assign]
    train_thread = Thread(
        target=lambda: results.append(
            service.execute(
                TrainCommand(
                    confirmed=True,
                    interactive=False,
                    resource_preflight_confirmed=True,
                )
            )
        ),
        name="stubborn-synchronous-train",
    )

    train_thread.start()
    assert plan.started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    try:
        service.close()
        closed_while_worker_was_alive = service.is_closed
    finally:
        plan.release.set()
        train_thread.join(timeout=THREAD_WATCHDOG_SECONDS)
        if not service.is_closed:
            service.close()

    assert plan.interrupt_requested.is_set()
    assert closed_while_worker_was_alive is False
    assert not train_thread.is_alive()
    assert len(results) == 1


def test_close_stop_exception_keeps_service_open_and_runtime_owned(monkeypatch) -> None:
    study = Study()
    service = get_application_service(study)
    original_stop = service.training_runtime.stop_training

    def fail_stop(*, wait_timeout: float | None = None) -> bool:
        del wait_timeout
        raise RuntimeError("stop failed")

    monkeypatch.setattr(service.training_runtime, "stop_training", fail_stop)

    service.close()

    assert service.is_closed is False
    assert get_application_service(study) is service

    monkeypatch.setattr(service.training_runtime, "stop_training", original_stop)
    service.close()


def test_close_retries_without_releasing_runtime_when_preview_is_not_quiescent(
    monkeypatch,
) -> None:
    study = Study()
    service = get_application_service(study)
    close_results = iter((False, True))
    monkeypatch.setattr(
        service.training_resource_preview,
        "close",
        lambda timeout=2.0: next(close_results),
    )

    service.close()

    assert service.is_closed is False
    assert get_application_service(study) is service

    service.close()

    assert service.is_closed is True


def test_close_waits_for_synchronous_completion_publication_to_quiesce(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    _prepare_saved_training_split(service)
    service.study.set_model_holder(_valid_model_holder())
    service.study.set_training_option(_valid_training_option())
    plan = _SlowCancellationPlan()
    trainer = Trainer([cast(TrainingPlanHolder, plan)])
    completion_wait_entered = Event()
    release_completion_wait = Event()
    close_done = Event()
    callback_states: list[bool] = []
    results: list[CommandResult] = []
    original_wait = service.training_runtime.wait_for_training_completion

    def install_plan(
        *,
        force_update: bool = False,
        append: bool = False,
    ) -> None:
        del force_update, append
        service.study.training_manager.trainer = trainer

    def delayed_completion_wait(
        *,
        expected_trainer_identity: str | None = None,
        timeout: float | None = None,
    ) -> bool:
        completion_wait_entered.set()
        assert release_completion_wait.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return original_wait(
            expected_trainer_identity=expected_trainer_identity,
            timeout=timeout,
        )

    def observe_publication(_publication: object) -> bool:
        callback_states.append(service.is_closed)
        return True

    service.study.generate_plan = install_plan  # type: ignore[method-assign]
    monkeypatch.setattr(
        service.training_runtime,
        "wait_for_training_completion",
        delayed_completion_wait,
    )
    service.subscribe(
        APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
        observe_publication,
    )
    train_thread = Thread(
        target=lambda: results.append(
            service.execute(
                TrainCommand(
                    confirmed=True,
                    interactive=False,
                    resource_preflight_confirmed=True,
                )
            )
        ),
        name="late-synchronous-completion",
    )
    close_thread = Thread(
        target=lambda: (service.close(), close_done.set()),
        name="close-during-synchronous-completion",
    )

    train_thread.start()
    assert plan.started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    plan.release.set()
    assert completion_wait_entered.wait(timeout=THREAD_WATCHDOG_SECONDS)
    close_thread.start()
    closed_while_completion_was_blocked = close_done.wait(timeout=0.25)
    release_completion_wait.set()
    train_thread.join(timeout=THREAD_WATCHDOG_SECONDS)
    close_thread.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert closed_while_completion_was_blocked is False
    assert close_done.is_set()
    assert service.is_closed is True
    assert not train_thread.is_alive()
    assert not close_thread.is_alive()
    assert len(results) == 1
    assert all(closed is False for closed in callback_states)


def test_close_fences_train_queued_before_lifecycle_admission() -> None:
    """A Train already approaching admission cannot pass a queued close."""

    class _FifoLifecycleLock:
        def __init__(self) -> None:
            self._condition = Condition()
            self._next_ticket = 0
            self._serving = 0
            self._held = False
            self.close_queued = Event()
            self.train_queued = Event()

        def __enter__(self) -> _FifoLifecycleLock:
            with self._condition:
                ticket = self._next_ticket
                self._next_ticket += 1
                if current_thread().name == "application-service-close":
                    self.close_queued.set()
                if current_thread().name == "queued-synchronous-train":
                    self.train_queued.set()
                admitted = self._condition.wait_for(
                    lambda: ticket == self._serving and not self._held,
                    timeout=THREAD_WATCHDOG_SECONDS,
                )
                assert admitted and ticket == self._serving and not self._held
                self._held = True
            return self

        def __exit__(self, *_args: Any) -> None:
            with self._condition:
                self._held = False
                self._serving += 1
                self._condition.notify_all()

    service = ApplicationService(Study())
    lifecycle_lock = _FifoLifecycleLock()
    service._synchronous_training_lifecycle_lock = cast(Any, lifecycle_lock)
    service.shutdown_lifecycle._synchronous_training_lifecycle_lock = cast(
        Any,
        lifecycle_lock,
    )
    close_done = Event()
    train_results: list[CommandResult] = []
    service._execute_serialized = MagicMock()  # type: ignore[method-assign]
    queued_train = Thread(
        target=lambda: train_results.append(
            service.execute(TrainCommand(interactive=False))
        ),
        name="queued-synchronous-train",
    )

    def close_service() -> None:
        service.close()
        close_done.set()

    closing = Thread(target=close_service, name="application-service-close")
    lifecycle_lock.__enter__()
    try:
        closing.start()
        assert lifecycle_lock.close_queued.wait(timeout=THREAD_WATCHDOG_SECONDS)
        assert service.shutdown_lifecycle.is_shutdown_fenced is True
        queued_train.start()
        assert lifecycle_lock.train_queued.wait(timeout=THREAD_WATCHDOG_SECONDS)
    finally:
        lifecycle_lock.__exit__(None, None, None)

    assert close_done.wait(timeout=THREAD_WATCHDOG_SECONDS)
    queued_train.join(timeout=THREAD_WATCHDOG_SECONDS)
    closing.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not queued_train.is_alive()
    assert not closing.is_alive()
    assert len(train_results) == 1
    assert train_results[0].failed is True
    assert train_results[0].diagnostics["application_service_closed"] is True
    service._execute_serialized.assert_not_called()


def test_synchronous_train_reports_incomplete_background_delivery() -> None:
    service = ApplicationService(Study())
    expected = CommandResult.success_result(
        command_name=CommandName.TRAIN.value,
        message="Training completed.",
        state=service.get_view_publication().state,
        changed_state=ChangedState(),
        diagnostics={
            "training_completed": True,
            "training_handoff_generation": 61,
        },
    )
    service._execute_serialized = MagicMock(return_value=expected)
    service.wait_for_background_tasks = MagicMock(return_value=False)

    result = service.execute(TrainCommand(interactive=False))

    assert result.failed is True
    assert result.error_type is ErrorType.INTERNAL
    assert result.recoverable is True
    assert result.diagnostics["background_delivery_incomplete"] is True
    assert result.diagnostics["training_completed"] is True
    service.wait_for_background_tasks.assert_called_once_with(
        timeout=300.0, training_handoff_generation=61
    )


def test_interactive_train_returns_without_waiting_for_background_tasks() -> None:
    service = ApplicationService(Study())
    expected = MagicMock(ok=True)
    service._execute_serialized = MagicMock(return_value=expected)
    service.wait_for_background_tasks = MagicMock(return_value=True)

    result = service.execute(TrainCommand(interactive=True))

    assert result is expected
    service.wait_for_background_tasks.assert_not_called()


def test_non_query_command_retries_retained_training_terminal_delivery() -> None:
    service = ApplicationService(Study())
    expected = MagicMock(ok=True)
    service._execute_serialized = MagicMock(return_value=expected)
    service.training_publications.retry_training_terminal_delivery = MagicMock(
        return_value=True
    )

    result = service.execute(TrainCommand(interactive=True))

    assert result is expected
    service.training_publications.retry_training_terminal_delivery.assert_called_once_with()


def test_published_state_query_does_not_retry_training_terminal_delivery() -> None:
    service = ApplicationService(Study())
    service.training_publications.retry_training_terminal_delivery = MagicMock(
        return_value=True
    )

    result = service.execute(QueryStateCommand(query="state"))

    assert result.ok is True
    service.training_publications.retry_training_terminal_delivery.assert_not_called()
