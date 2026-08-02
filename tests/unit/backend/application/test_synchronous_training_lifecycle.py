"""Synchronous training completion lifecycle contract tests."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.commands import CommandName, TrainCommand
from XBrainLab.backend.application.errors import ApplicationError
from XBrainLab.backend.application.results import (
    ChangedState,
    CommandResult,
    CommandStatus,
    ErrorType,
)
from XBrainLab.backend.application.service import ApplicationService
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.synchronous_training_lifecycle import (
    SynchronousTrainingLifecycleCoordinator,
)
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.study import Study


class _TrackingLock:
    def __init__(self) -> None:
        self.held = False

    def __enter__(self) -> _TrackingLock:
        assert self.held is False
        self.held = True
        return self

    def __exit__(self, *_args: object) -> None:
        assert self.held is True
        self.held = False


class _TrainingRuntime:
    def __init__(self, *, worker_complete: bool, lock: _TrackingLock) -> None:
        self.worker_complete = worker_complete
        self.lock = lock
        self.calls = 0
        self.expected_identities: list[str] = []
        self.timeouts: list[float | None] = []

    def wait_for_training_completion(
        self,
        *,
        expected_trainer_identity: str,
        timeout: float | None = None,
    ) -> bool:
        assert timeout is not None and timeout > 0
        assert self.lock.held is False
        self.calls += 1
        self.expected_identities.append(expected_trainer_identity)
        self.timeouts.append(timeout)
        return self.worker_complete


class _TerminalNotifications:
    def __init__(self, *, published: bool, lock: _TrackingLock) -> None:
        self.published = published
        self.lock = lock
        self.generations: list[int | None] = []
        self.timeouts: list[float | None] = []

    def wait_for_terminal_notification(
        self,
        generation: int | None = None,
        *,
        timeout: float | None = None,
    ) -> bool:
        assert timeout is not None and timeout > 0
        assert self.lock.held is False
        self.generations.append(generation)
        self.timeouts.append(timeout)
        return self.published


def _publication(state: ApplicationStateSnapshot) -> ApplicationViewPublication:
    return ApplicationViewPublication(
        generation=1,
        state=state,
        capabilities=build_capability_policy(state),
    )


def _started_result(
    *,
    handoff_generation: object = 17,
) -> CommandResult:
    return CommandResult.success_result(
        command_name=CommandName.TRAIN.value,
        message="Training started.",
        state=ApplicationStateSnapshot.empty(),
        changed_state=ChangedState(datasets_changed=True),
        diagnostics={
            "append": False,
            "synchronous_completion_deferred": True,
            "training_handoff_generation": handoff_generation,
            "training_trainer_identity": "trainer-A",
        },
    )


def _coordinator(
    *,
    runtime: _TrainingRuntime,
    notifications: _TerminalNotifications,
    lock: _TrackingLock,
    after: ApplicationStateSnapshot,
    complete_training: Any,
    handler_failure: Any,
    post_state_verification_failure: Any,
    clear_last_error: Any = lambda: None,
    state_after_command: Any | None = None,
    changed_state: Any = lambda _before, _after: ChangedState(
        training_changed=True,
    ),
    retry_terminal_delivery: Any = lambda _generation: False,
) -> SynchronousTrainingLifecycleCoordinator:
    publication = _publication(after)
    return SynchronousTrainingLifecycleCoordinator(
        training_runtime=runtime,
        terminal_notifications=notifications,
        retry_terminal_delivery=retry_terminal_delivery,
        command_lock=lock,
        complete_training=complete_training,
        committed_publication=lambda: publication,
        clear_last_error=clear_last_error,
        state_after_command=(
            state_after_command
            if state_after_command is not None
            else lambda: (after, None)
        ),
        changed_state=changed_state,
        post_state_verification_failure=post_state_verification_failure,
        handler_failure=handler_failure,
        completion_is_closed=lambda: False,
    )


def test_completion_waits_for_exact_terminal_then_verifies_and_merges_result() -> None:
    lock = _TrackingLock()
    runtime = _TrainingRuntime(worker_complete=True, lock=lock)
    notifications = _TerminalNotifications(published=True, lock=lock)
    after = replace(
        ApplicationStateSnapshot.empty(),
        training=replace(
            ApplicationStateSnapshot.empty().training,
            progress_message="Training completed.",
        ),
    )
    call_order: list[str] = []

    def complete_training(expected_trainer_identity: str) -> tuple[str, dict[str, Any]]:
        assert lock.held is True
        assert expected_trainer_identity == "trainer-A"
        call_order.append("verify_terminal_outcome")
        return "Training completed.", {"terminal_outcome": "completed"}

    def clear_last_error() -> None:
        assert lock.held is True
        call_order.append("clear_last_error")

    def state_after_command() -> tuple[ApplicationStateSnapshot, None]:
        assert lock.held is True
        call_order.append("verify_state")
        return after, None

    def changed_state(
        before: ApplicationStateSnapshot,
        current: ApplicationStateSnapshot,
    ) -> ChangedState:
        assert lock.held is True
        assert before == ApplicationStateSnapshot.empty()
        assert current == after
        call_order.append("build_changed_state")
        return ChangedState(training_changed=True, visualization_changed=True)

    coordinator = _coordinator(
        runtime=runtime,
        notifications=notifications,
        lock=lock,
        after=after,
        complete_training=complete_training,
        clear_last_error=clear_last_error,
        state_after_command=state_after_command,
        changed_state=changed_state,
        post_state_verification_failure=lambda **_kwargs: pytest.fail(
            "state verification should succeed"
        ),
        handler_failure=lambda *_args: pytest.fail(
            "completion should not map to failure"
        ),
    )

    result = coordinator.complete_deferred(_started_result())

    assert runtime.calls == 1
    assert runtime.expected_identities == ["trainer-A"]
    assert len(runtime.timeouts) == 1
    assert notifications.generations == [17]
    assert call_order == [
        "verify_terminal_outcome",
        "clear_last_error",
        "verify_state",
        "build_changed_state",
    ]
    assert result.ok is True
    assert result.message == "Training completed."
    assert result.state == after
    assert result.changed_state == ChangedState(
        datasets_changed=True,
        training_changed=True,
        visualization_changed=True,
    )
    assert result.diagnostics == {
        "append": False,
        "training_handoff_generation": 17,
        "training_trainer_identity": "trainer-A",
        "terminal_outcome": "completed",
    }


def test_late_completion_after_close_cannot_mutate_application_state() -> None:
    service = ApplicationService(Study())
    before_error = service._last_error
    before_publication = service._committed_view_publication()
    callbacks: list[ApplicationViewPublication] = []
    service.subscribe("application_view_publication_changed", callbacks.append)
    service.close()

    result = service.synchronous_training_lifecycle.complete_deferred(_started_result())

    assert service.is_closed is True
    assert service._last_error is before_error
    assert service._committed_view_publication() == before_publication
    assert callbacks == []
    assert result.failed is True
    assert result.changed_state == ChangedState()
    assert result.diagnostics["application_service_closed"] is True


@pytest.mark.parametrize(
    ("worker_complete", "handoff_generation", "terminal_published", "message"),
    [
        (False, 17, True, "Training completion could not be verified."),
        (True, None, True, "Training terminal handoff identity is unavailable."),
        (True, 17, False, "Training terminal status could not be verified."),
    ],
)
def test_completion_resolution_failures_use_normal_handler_failure_mapping(
    worker_complete: bool,
    handoff_generation: object,
    terminal_published: bool,
    message: str,
) -> None:
    lock = _TrackingLock()
    runtime = _TrainingRuntime(worker_complete=worker_complete, lock=lock)
    notifications = _TerminalNotifications(
        published=terminal_published,
        lock=lock,
    )
    state = ApplicationStateSnapshot.empty()
    captured_errors: list[Exception] = []

    def handler_failure(
        name: CommandName,
        before: ApplicationStateSnapshot,
        _publication: ApplicationViewPublication,
        error: Exception,
    ) -> CommandResult:
        assert lock.held is True
        assert name is CommandName.TRAIN
        assert before == state
        captured_errors.append(error)
        assert isinstance(error, ApplicationError)
        return CommandResult.failure_result(
            command_name=name.value,
            message=str(error),
            state=state,
            changed_state=ChangedState(error_changed=True),
            error_type=error.error_type,
            recoverable=error.recoverable,
            diagnostics=error.diagnostics,
        )

    coordinator = _coordinator(
        runtime=runtime,
        notifications=notifications,
        lock=lock,
        after=state,
        complete_training=lambda _identity: pytest.fail(
            "terminal outcome verification must not run"
        ),
        post_state_verification_failure=lambda **_kwargs: pytest.fail(
            "post-state verification must not run"
        ),
        handler_failure=handler_failure,
    )

    result = coordinator.complete_deferred(
        _started_result(handoff_generation=handoff_generation)
    )

    assert len(captured_errors) == 1
    assert result.failed is True
    assert result.message == message
    assert result.error_type is ErrorType.TRAINING
    assert result.changed_state == ChangedState(
        datasets_changed=True,
        error_changed=True,
    )
    assert "synchronous_completion_deferred" not in result.diagnostics
    assert notifications.generations == (
        [17] if worker_complete and handoff_generation == 17 else []
    )
    assert runtime.calls == (0 if handoff_generation is None else 1)


def test_unreliable_terminal_state_fails_closed_and_preserves_both_envelopes() -> None:
    lock = _TrackingLock()
    runtime = _TrainingRuntime(worker_complete=True, lock=lock)
    notifications = _TerminalNotifications(published=True, lock=lock)
    after = ApplicationStateSnapshot.empty(
        read_errors=["training projection unavailable"]
    )
    verification_errors: list[Exception] = []

    def post_state_verification_failure(
        *,
        name: CommandName,
        state: ApplicationStateSnapshot,
        diagnostics: dict[str, Any],
        error: Exception,
    ) -> CommandResult:
        assert lock.held is True
        assert name is CommandName.TRAIN
        assert state == after
        assert diagnostics == {"terminal_outcome": "completed"}
        verification_errors.append(error)
        return CommandResult.failure_result(
            command_name=name.value,
            message="Updated state could not be verified.",
            state=state,
            changed_state=ChangedState(error_changed=True, state_unknown=True),
            error_type=ErrorType.INTERNAL,
            recoverable=False,
            diagnostics={"state_refresh_failed": True},
        )

    coordinator = _coordinator(
        runtime=runtime,
        notifications=notifications,
        lock=lock,
        after=after,
        complete_training=lambda _identity: (
            "Training completed.",
            {"terminal_outcome": "completed"},
        ),
        post_state_verification_failure=post_state_verification_failure,
        handler_failure=lambda *_args: pytest.fail(
            "unreliable state uses verification failure mapping"
        ),
    )

    result = coordinator.complete_deferred(_started_result())

    assert len(verification_errors) == 1
    assert str(verification_errors[0]) == "training projection unavailable"
    assert result.failed is True
    assert result.changed_state == ChangedState(
        datasets_changed=True,
        error_changed=True,
        state_unknown=True,
    )
    assert result.diagnostics == {
        "append": False,
        "training_handoff_generation": 17,
        "training_trainer_identity": "trainer-A",
        "state_refresh_failed": True,
    }


def test_background_delivery_failure_keeps_completion_evidence() -> None:
    started = _started_result()

    result = SynchronousTrainingLifecycleCoordinator.background_delivery_failure(
        started,
        reason="Terminal delivery could not be verified.",
        invalid_handoff=True,
    )

    assert result.status is CommandStatus.FAILED
    assert result.error_type is ErrorType.INTERNAL
    assert result.recoverable is True
    assert result.changed_state == started.changed_state
    assert result.diagnostics == {
        **started.diagnostics,
        "background_delivery_incomplete": True,
        "training_handoff_generation_invalid": True,
    }


@pytest.mark.parametrize("value", [None, True, False, 0, -1, 1.5, "17"])
def test_handoff_generation_rejects_invalid_values(value: object) -> None:
    result = _started_result(handoff_generation=value)

    assert SynchronousTrainingLifecycleCoordinator.handoff_generation(result) is None


def test_handoff_generation_accepts_positive_integer() -> None:
    result = _started_result(handoff_generation=23)

    assert SynchronousTrainingLifecycleCoordinator.handoff_generation(result) == 23


def test_terminal_notification_can_be_recovered_without_unbounded_wait() -> None:
    lock = _TrackingLock()
    runtime = _TrainingRuntime(worker_complete=True, lock=lock)
    notifications = _TerminalNotifications(published=False, lock=lock)
    after = ApplicationStateSnapshot.empty()
    retries: list[int] = []

    def retry(generation: int) -> bool:
        retries.append(generation)
        notifications.published = True
        return True

    coordinator = _coordinator(
        runtime=runtime,
        notifications=notifications,
        lock=lock,
        after=after,
        complete_training=lambda _identity: ("Training completed.", {}),
        post_state_verification_failure=lambda **_kwargs: pytest.fail(
            "state verification should succeed"
        ),
        handler_failure=lambda *_args: pytest.fail("recovery should succeed"),
        retry_terminal_delivery=retry,
    )

    result = coordinator.complete_deferred(_started_result())

    assert result.ok is True
    assert retries == [17]
    assert notifications.generations == [17, 17]
    assert all(
        timeout is not None and timeout > 0 for timeout in notifications.timeouts
    )


def test_terminal_notification_retry_is_bounded_when_delivery_stays_missing() -> None:
    lock = _TrackingLock()
    runtime = _TrainingRuntime(worker_complete=True, lock=lock)
    notifications = _TerminalNotifications(published=False, lock=lock)
    state = ApplicationStateSnapshot.empty()
    retries: list[int] = []

    def handler_failure(
        name: CommandName,
        _before: ApplicationStateSnapshot,
        _publication: ApplicationViewPublication,
        error: Exception,
    ) -> CommandResult:
        return CommandResult.failure_result(
            command_name=name.value,
            message=str(error),
            state=state,
            changed_state=ChangedState(error_changed=True),
            error_type=ErrorType.TRAINING,
            recoverable=True,
        )

    coordinator = _coordinator(
        runtime=runtime,
        notifications=notifications,
        lock=lock,
        after=state,
        complete_training=lambda _identity: pytest.fail(
            "terminal verification must not run"
        ),
        post_state_verification_failure=lambda **_kwargs: pytest.fail(
            "post-state verification must not run"
        ),
        handler_failure=handler_failure,
        retry_terminal_delivery=lambda generation: (retries.append(generation) or True),
    )

    result = coordinator.complete_deferred(_started_result())

    assert result.failed is True
    assert result.message == "Training terminal status could not be verified."
    assert retries == [17]
    assert notifications.generations == [17, 17]
    assert len(notifications.timeouts) == 2


def test_start_phase_identity_cannot_be_overwritten_by_completion_diagnostics() -> None:
    started = _started_result(handoff_generation=37)
    completed = replace(
        started,
        diagnostics={
            "training_handoff_generation": 99,
            "training_trainer_identity": "trainer-B",
            "terminal_outcome": "completed",
        },
    )

    merged = SynchronousTrainingLifecycleCoordinator._merge_result_envelopes(
        started,
        completed,
    )

    assert merged.diagnostics["training_handoff_generation"] == 37
    assert merged.diagnostics["training_trainer_identity"] == "trainer-A"
    assert merged.diagnostics["terminal_outcome"] == "completed"


def test_application_service_delegates_deferred_completion_to_coordinator() -> None:
    service = ApplicationService(Study())
    started = _started_result(handoff_generation=29)
    completed = replace(
        started,
        message="Training completed.",
        diagnostics={"training_handoff_generation": 29},
    )
    delegated: list[CommandResult] = []
    background_generations: list[int | None] = []
    service._execute_serialized = lambda _command: started  # type: ignore[method-assign]
    service.synchronous_training_lifecycle.complete_deferred = (  # type: ignore[method-assign]
        lambda result: (
            delegated.append(result)
            or (
                pytest.fail("lifecycle admission lock leaked into deferred wait")
                if service._synchronous_training_lifecycle_lock.locked()
                else completed
            )
        )
    )
    service.wait_for_background_tasks = (  # type: ignore[method-assign]
        lambda timeout=None, *, training_handoff_generation=None: (
            pytest.fail("synchronous background wait must be bounded")
            if timeout is None or timeout <= 0
            else (background_generations.append(training_handoff_generation) or True)
        )
    )

    result = service.execute(TrainCommand(interactive=False))

    assert result == completed
    assert delegated == [started]
    assert background_generations == [29]


def test_application_services_share_one_study_training_admission_lock() -> None:
    study = Study()
    first = ApplicationService(study)
    second = ApplicationService(study)
    try:
        assert first._synchronous_training_lifecycle_lock is (
            second._synchronous_training_lifecycle_lock
        )
        assert first._synchronous_training_lifecycle_lock is (
            study._synchronous_training_lifecycle_lock
        )
    finally:
        first.close()
        second.close()
