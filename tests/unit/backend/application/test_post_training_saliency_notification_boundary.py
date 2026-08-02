"""Failure-atomic contracts for post-command saliency notifications."""

from __future__ import annotations

from threading import Barrier, Event, Lock, Thread

import pytest

from XBrainLab.backend.application.post_training_saliency import (
    PostCommandSaliencyNotificationBoundary,
    SaliencyTerminalNotification,
)
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyStatus,
    TrainingLifecycleEvent,
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingStateToken,
    TrainingTerminalOutcome,
)


def _notification(generation: int) -> SaliencyTerminalNotification:
    run = TrainingRunIdentity(trainer_id="boundary-test", run_id=generation)
    return SaliencyTerminalNotification(
        status=PostTrainingSaliencyStatus(
            phase=PostTrainingSaliencyPhase.SUCCEEDED,
            generation=generation,
            run=run,
            training_generation=generation,
            methods=("Gradient",),
            message="Automatic saliency completed.",
        ),
        analysis_event=TrainingLifecycleEvent(
            token=TrainingStateToken(generation=generation, stable=True),
            outcome=TrainingTerminalOutcome(
                state=TrainingOutcomeState.COMPLETED,
                run=run,
            ),
            publication_generation=generation,
        ),
    )


def test_released_reservation_can_retry_same_generation_exactly_once() -> None:
    delivered: list[SaliencyTerminalNotification] = []
    boundary = PostCommandSaliencyNotificationBoundary(delivered.append)
    notification = _notification(1)

    assert boundary.reserve(notification) is True
    assert boundary.release(notification) is True
    assert boundary.reserve(notification) is True
    boundary.publish_reserved(notification)

    assert delivered == [notification]
    assert boundary.reserve(notification) is False
    assert boundary.release(notification) is False
    assert boundary._reservations == {}


def test_capture_exit_queue_failure_keeps_nested_generation_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivered: list[SaliencyTerminalNotification] = []
    boundary = PostCommandSaliencyNotificationBoundary(delivered.append)
    notification = _notification(1)
    original_enqueue = boundary._enqueue_deliveries
    enqueue_attempts = 0

    def fail_first_enqueue(
        notifications: list[SaliencyTerminalNotification],
    ) -> None:
        nonlocal enqueue_attempts
        enqueue_attempts += 1
        if enqueue_attempts == 1:
            raise RuntimeError("transient queue handoff failure")
        original_enqueue(notifications)

    monkeypatch.setattr(boundary, "_enqueue_deliveries", fail_first_enqueue)

    with (
        pytest.raises(RuntimeError, match="transient queue handoff failure"),
        boundary.capture(),
        boundary.capture(),
    ):
        assert boundary.defer(notification) is True

    assert delivered == []

    with boundary.capture():
        assert boundary.defer(notification) is True

    assert delivered == [notification]
    assert boundary.defer(notification) is False
    assert enqueue_attempts == 2
    assert boundary._reservations == {}


def test_concurrent_capture_retry_after_handoff_failure_delivers_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivered: list[SaliencyTerminalNotification] = []
    boundary = PostCommandSaliencyNotificationBoundary(delivered.append)
    notification = _notification(1)
    original_enqueue = boundary._enqueue_deliveries

    def fail_enqueue(
        _notifications: list[SaliencyTerminalNotification],
    ) -> None:
        raise RuntimeError("transient queue handoff failure")

    monkeypatch.setattr(boundary, "_enqueue_deliveries", fail_enqueue)
    with (
        pytest.raises(RuntimeError, match="transient queue handoff failure"),
        boundary.capture(),
    ):
        assert boundary.defer(notification) is True
    monkeypatch.setattr(boundary, "_enqueue_deliveries", original_enqueue)

    barrier = Barrier(9)
    result_lock = Lock()
    results: list[bool] = []
    errors: list[BaseException] = []

    def retry() -> None:
        barrier.wait()
        try:
            with boundary.capture():
                result = boundary.defer(notification)
            with result_lock:
                results.append(result)
        except BaseException as exc:
            with result_lock:
                errors.append(exc)

    threads = [Thread(target=retry, daemon=True) for _ in range(8)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=2.0)
        assert not thread.is_alive()

    assert errors == []
    assert sorted(results) == [False] * 7 + [True]
    assert delivered == [notification]
    assert boundary._reservations == {}


def test_failed_old_reservation_does_not_block_new_generation() -> None:
    delivered: list[SaliencyTerminalNotification] = []
    boundary = PostCommandSaliencyNotificationBoundary(delivered.append)
    old = _notification(1)
    new = _notification(2)

    assert boundary.reserve(old) is True
    assert boundary.release(old) is True
    assert boundary.reserve(new) is True
    boundary.publish_reserved(new)

    assert delivered == [new]
    assert boundary.reserve(old) is False
    assert boundary._reservations == {}


def test_reentrant_delivery_and_callback_failure_do_not_stall_newer_event() -> None:
    delivered: list[SaliencyTerminalNotification] = []
    attempts: list[SaliencyTerminalNotification] = []
    first = _notification(1)
    second = _notification(2)
    boundary: PostCommandSaliencyNotificationBoundary

    def deliver(notification: SaliencyTerminalNotification) -> None:
        attempts.append(notification)
        if notification == first and attempts.count(first) == 1:
            assert boundary.defer(second) is True
            raise RuntimeError("observer failure")
        delivered.append(notification)

    boundary = PostCommandSaliencyNotificationBoundary(deliver)

    assert boundary.defer(first) is True
    assert boundary.wait_for_idle(timeout=2.0)

    assert delivered == [first, second]
    assert attempts == [first, first, second]
    assert boundary.defer(first) is False
    assert boundary.defer(second) is False
    assert boundary._reservations == {}


def test_timer_constructor_failure_uses_autonomous_thread_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notification = _notification(1)
    attempts: list[SaliencyTerminalNotification] = []
    delivered = Event()

    def fail_once(item: SaliencyTerminalNotification) -> bool:
        attempts.append(item)
        if len(attempts) == 1:
            return False
        delivered.set()
        return True

    class _TimerConstructorFailure:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("timer constructor failed")

    boundary = PostCommandSaliencyNotificationBoundary(fail_once)
    monkeypatch.setattr(
        "XBrainLab.backend.application.post_training_saliency.Timer",
        _TimerConstructorFailure,
    )

    assert boundary.defer(notification) is True
    assert delivered.wait(timeout=2.0)
    assert boundary.wait_for_idle(timeout=0.1)
    assert attempts == [notification, notification]


@pytest.mark.parametrize("timer_failure", ["construct", "start"])
@pytest.mark.parametrize("thread_failure", ["construct", "start"])
def test_retry_owner_constructor_matrix_fails_closed_without_losing_queue(
    monkeypatch: pytest.MonkeyPatch,
    timer_failure: str,
    thread_failure: str,
) -> None:
    notification = _notification(1)
    attempts: list[SaliencyTerminalNotification] = []

    def fail_once(item: SaliencyTerminalNotification) -> bool:
        attempts.append(item)
        return len(attempts) > 1

    class _TimerFailure:
        daemon = False

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            if timer_failure == "construct":
                raise RuntimeError("timer constructor failed")

        def start(self) -> None:
            raise RuntimeError("timer start failed")

    class _ThreadFailure:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            if thread_failure == "construct":
                raise RuntimeError("thread constructor failed")

        def start(self) -> None:
            raise RuntimeError("thread start failed")

    boundary = PostCommandSaliencyNotificationBoundary(fail_once)
    with monkeypatch.context() as retry_faults:
        retry_faults.setattr(
            "XBrainLab.backend.application.post_training_saliency.Timer",
            _TimerFailure,
        )
        retry_faults.setattr(
            "XBrainLab.backend.application.post_training_saliency.Thread",
            _ThreadFailure,
        )

        assert boundary.defer(notification) is True

        state = boundary.delivery_state()
        assert state.pending_generations == (notification.status.generation,)
        assert state.active_generation is None
        assert state.delivered_generation == -1
        assert state.retry_owner_active is False
        assert state.retry_unavailable is True
        assert boundary.wait_for_idle(timeout=0.01) is False

    boundary.retry_pending()

    assert attempts == [notification, notification]
    assert boundary.wait_for_idle(timeout=0.1)
    state = boundary.delivery_state()
    assert state.pending_generations == ()
    assert state.delivered_generation == notification.status.generation
    assert state.retry_unavailable is False


def test_concurrent_reservation_has_one_owner_and_remains_retryable() -> None:
    delivered: list[SaliencyTerminalNotification] = []
    boundary = PostCommandSaliencyNotificationBoundary(delivered.append)
    notification = _notification(1)
    barrier = Barrier(9)
    result_lock = Lock()
    results: list[bool] = []

    def reserve() -> None:
        barrier.wait()
        result = boundary.reserve(notification)
        with result_lock:
            results.append(result)

    threads = [Thread(target=reserve, daemon=True) for _ in range(8)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=2.0)
        assert not thread.is_alive()

    assert sorted(results) == [False] * 7 + [True]
    assert boundary.release(notification) is True
    assert boundary.defer(notification) is True
    assert delivered == [notification]
    assert boundary._reservations == {}
