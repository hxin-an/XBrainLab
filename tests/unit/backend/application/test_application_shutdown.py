"""Application boundary: shutdown behavior."""

from __future__ import annotations

from dataclasses import replace
from threading import Event, Thread, current_thread
from unittest.mock import MagicMock

from XBrainLab.backend.application import (
    ApplicationService,
    ErrorType,
    NewSessionCommand,
    QueryStateCommand,
    StopTrainingCommand,
    TrainCommand,
    get_application_service,
)
from XBrainLab.backend.study import Study


def test_runtime_factory_shares_one_application_service_identity_per_study() -> None:
    study = Study()
    first = get_application_service(study)
    second = get_application_service(study)

    assert second is first
    assert first.study is study
    assert study._application_service is first


def test_shutdown_fence_blocks_mutations_until_cancelled() -> None:
    service = ApplicationService(Study())

    service.request_shutdown_fence()
    blocked = service.execute(NewSessionCommand(confirmed=True))
    blocked_train = service.execute(TrainCommand(confirmed=True))
    query = service.execute(QueryStateCommand(query="state"))
    stop = service.execute(StopTrainingCommand(wait_timeout=0.0))
    service.release_shutdown_fence()
    resumed = service.execute(NewSessionCommand(confirmed=True))

    assert blocked.failed is True
    assert blocked.error_type == ErrorType.PRECONDITION
    assert "closing" in blocked.message
    assert blocked_train.failed is True
    assert "closing" in blocked_train.message
    assert query.ok is True
    assert "closing" not in stop.message
    assert resumed.ok is True


def test_shutdown_fence_cancels_live_saliency_without_waiting() -> None:
    service = ApplicationService(Study())
    service.training_runtime.cancel_saliency_job = MagicMock()

    service.request_shutdown_fence()

    service.training_runtime.cancel_saliency_job.assert_called_once_with()


def test_shutdown_fence_does_not_wait_for_saliency_terminal_reconciliation() -> None:
    service = ApplicationService(Study())
    command_lock_held = Event()
    release_command_lock = Event()
    shutdown_returned = Event()
    pending_terminal = MagicMock()
    service.publication_lifecycle.pending_saliency_terminal = MagicMock(
        return_value=pending_terminal
    )
    service.training_runtime.cancel_saliency_job = MagicMock(
        side_effect=(
            lambda: service.publication_lifecycle.reconcile_pending_saliency_terminal()
        ),
    )

    def hold_command_lock() -> None:
        with service._command_lock:
            command_lock_held.set()
            assert release_command_lock.wait(timeout=2.0)

    lock_owner = Thread(target=hold_command_lock)
    lock_owner.start()
    assert command_lock_held.wait(timeout=1.0)

    def request_shutdown() -> None:
        service.request_shutdown_fence()
        shutdown_returned.set()

    shutdown_thread = Thread(target=request_shutdown)
    shutdown_thread.start()

    try:
        assert shutdown_returned.wait(timeout=0.25)
    finally:
        release_command_lock.set()
        lock_owner.join(timeout=1.0)
        shutdown_thread.join(timeout=1.0)

    assert not lock_owner.is_alive()
    assert not shutdown_thread.is_alive()
    service.training_runtime.cancel_saliency_job.assert_called_once_with()


def test_close_releases_saliency_delivery_when_runtime_cancel_fails() -> None:
    service = ApplicationService(Study())
    service.training_runtime.cancel_saliency_job = MagicMock(
        side_effect=RuntimeError("runtime cancel failed")
    )
    service.training_runtime.discard_saliency_delivery = MagicMock()

    service.close()

    assert service.is_closed is True
    service.training_runtime.cancel_saliency_job.assert_called_once_with()
    service.training_runtime.discard_saliency_delivery.assert_called_once_with()


def test_shutdown_fence_rechecks_command_queued_before_fence(monkeypatch) -> None:
    study = Study()
    service = ApplicationService(study)
    original_admission_lock = service._command_admission_lock
    admission_passed = Event()
    result_holder = []
    mutation_thread: Thread | None = None

    class _ObservedAdmissionLock:
        def __enter__(self):
            original_admission_lock.acquire()
            return self

        def __exit__(self, *_args):
            original_admission_lock.release()
            if current_thread() is mutation_thread:
                admission_passed.set()

    monkeypatch.setattr(
        service.shutdown_lifecycle,
        "_command_admission_lock",
        _ObservedAdmissionLock(),
    )

    def execute_queued_mutation() -> None:
        result_holder.append(service.execute(NewSessionCommand(confirmed=True)))

    with service._command_lock:
        mutation_thread = Thread(target=execute_queued_mutation)
        mutation_thread.start()
        assert admission_passed.wait(timeout=1.0)
        service.request_shutdown_fence()

    mutation_thread.join(timeout=1.0)

    assert not mutation_thread.is_alive()
    assert len(result_holder) == 1
    assert result_holder[0].failed is True
    assert result_holder[0].error_type == ErrorType.PRECONDITION
    assert "closing" in result_holder[0].message


def test_shutdown_fence_release_stays_exact_when_state_refresh_fails() -> None:
    service = ApplicationService(Study())
    service.get_state()
    service.request_shutdown_fence()
    fence_generation = service.shutdown_lifecycle.fence_generation
    original_build = service.state_snapshot.build
    service.state_snapshot.build = MagicMock(
        side_effect=RuntimeError("state backend unavailable"),
    )

    assert service.release_shutdown_fence() is False

    assert service.shutdown_lifecycle.is_shutdown_fenced is True
    assert service.shutdown_lifecycle.fence_generation == fence_generation

    service.state_snapshot.build = original_build

    assert service.release_shutdown_fence() is True
    assert service.shutdown_lifecycle.is_shutdown_fenced is False


def test_shutdown_fence_release_rejects_unusable_refresh_publication() -> None:
    service = ApplicationService(Study())
    reliable_state = service.get_state()
    unreliable_state = replace(reliable_state, state_reliable=False)
    service.request_shutdown_fence()
    fence_generation = service.shutdown_lifecycle.fence_generation
    original_build = service.state_snapshot.build
    service.state_snapshot.build = MagicMock(return_value=unreliable_state)

    assert service.release_shutdown_fence() is False
    assert service.shutdown_lifecycle.is_shutdown_fenced is True
    assert service.shutdown_lifecycle.fence_generation == fence_generation
    assert service._committed_view_publication().usable is False

    service.state_snapshot.build = original_build

    assert service.release_shutdown_fence() is True
    assert service.shutdown_lifecycle.is_shutdown_fenced is False
