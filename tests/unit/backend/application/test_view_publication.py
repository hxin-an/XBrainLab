"""Recovery contracts for the atomic application view publication."""

from __future__ import annotations

import time
from dataclasses import replace
from threading import Event, Thread
from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.application.commands import QueryStateCommand
from XBrainLab.backend.application.service import ApplicationService
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.view_publication import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationViewCoordinator,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import Trainer
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyStatus,
    TrainingReadBoundary,
    TrainingRunIdentity,
    TrainingStateToken,
)

THREAD_WATCHDOG_SECONDS = 2.0


def test_live_training_updates_do_not_starve_a_stable_publication_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real tracked update arriving mid-read waits for one coherent capture."""
    study = Study()
    trainer = Trainer([])
    study.training_manager.trainer = trainer
    service = ApplicationService(study)
    original_build = service.state_snapshot.build
    writers: list[Thread] = []
    updates: list[Event] = []

    def build_while_training_updates(**kwargs):
        state = original_build(**kwargs)
        started = Event()
        updated = Event()

        def update_progress():
            started.set()
            trainer.set_interrupt()
            updated.set()

        writer = Thread(target=update_progress)
        writers.append(writer)
        updates.append(updated)
        writer.start()
        assert started.wait(THREAD_WATCHDOG_SECONDS)
        # Before the repair this completes inside every optimistic capture,
        # exhausting all attempts. A protected read releases the writer after
        # its state, training history and boundary have been captured together.
        updated.wait(0.05)
        return state

    monkeypatch.setattr(service.state_snapshot, "build", build_while_training_updates)
    try:
        for _ in range(3):
            state = service.get_state()
            publication = service._committed_view_publication()
            assert state.state_reliable is True
            assert publication.usable is True
            assert publication.state == state
            for writer in writers:
                writer.join(THREAD_WATCHDOG_SECONDS)
            assert all(update.is_set() for update in updates)
    finally:
        for writer in writers:
            writer.join(THREAD_WATCHDOG_SECONDS)
        assert not any(writer.is_alive() for writer in writers)


def test_publication_during_active_training_mutation_still_fails_closed() -> None:
    study = Study()
    trainer = Trainer([])
    study.training_manager.trainer = trainer
    service = ApplicationService(study)
    mutating = Event()
    finish = Event()

    def unfinished_update():
        with trainer._state_tracker.mutation():
            trainer.progress_text = "partial update"
            mutating.set()
            assert finish.wait(THREAD_WATCHDOG_SECONDS)
            trainer.progress_text = "completed update"

    writer = Thread(target=unfinished_update)
    writer.start()
    try:
        assert mutating.wait(THREAD_WATCHDOG_SECONDS)
        state = service.get_state()
        assert state.state_reliable is False
        assert service._committed_view_publication().usable is False
    finally:
        finish.set()
        writer.join(THREAD_WATCHDOG_SECONDS)
    assert not writer.is_alive()
    assert service.get_state().state_reliable is True
    assert service._committed_view_publication().usable is True


def test_failed_snapshot_releases_training_and_saliency_publication_locks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = Study()
    trainer = Trainer([])
    study.training_manager.trainer = trainer
    service = ApplicationService(study)
    original_build = service.state_snapshot.build

    def broken_build(**_kwargs):
        # The status read is reentrant inside the coherent publication scope.
        assert study.training_manager.get_post_training_saliency_status().phase is (
            PostTrainingSaliencyPhase.IDLE
        )
        raise RuntimeError("read failed inside snapshot")

    monkeypatch.setattr(service.state_snapshot, "build", broken_build)
    with pytest.raises(RuntimeError, match="read failed inside snapshot"):
        service.get_state()
    assert service._committed_view_publication().usable is False

    completed = Event()

    def next_update():
        study.training_manager.capture_training_read_boundary()
        trainer.set_interrupt()
        study.training_manager.get_post_training_saliency_status()
        completed.set()

    writer = Thread(target=next_update)
    writer.start()
    writer.join(THREAD_WATCHDOG_SECONDS)
    assert not writer.is_alive()
    assert completed.is_set()
    monkeypatch.setattr(service.state_snapshot, "build", original_build)
    assert service.get_state().state_reliable is True


def _boundary(
    identity: str | None = None,
    *,
    generation: int = 0,
    stable: bool = True,
) -> TrainingReadBoundary:
    return TrainingReadBoundary(
        trainer_identity=identity,
        token=TrainingStateToken(generation=generation, stable=stable),
    )


def test_opportunistic_failure_fails_closed_then_publishes_a_new_generation() -> None:
    initial = ApplicationStateSnapshot.empty()
    build_state = MagicMock(
        side_effect=[RuntimeError("transient snapshot failure"), initial]
    )
    boundary = _boundary()
    coordinator = ApplicationViewCoordinator(
        initial,
        initial_training_boundary=boundary,
        build_state=build_state,
        capture_training_boundary=lambda: boundary,
    )

    failed = coordinator.refresh_opportunistic()

    assert failed.usable is False
    assert failed.state.state_reliable is False
    assert failed.generation == 1
    assert failed.refresh_error == "transient snapshot failure"

    recovered = coordinator.refresh_opportunistic()

    assert recovered.usable is True
    assert recovered.state == initial
    assert recovered.generation > failed.generation
    assert recovered.refresh_error is None


def test_strict_failure_self_heals_on_the_next_safe_publication_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ApplicationService(Study())
    delivered = []
    service.subscribe(
        APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
        delivered.append,
    )
    initial = service._committed_view_publication()
    recovered_state = replace(initial.state, pipeline_stage="data_loaded")
    build_state = MagicMock(
        side_effect=[RuntimeError("transient strict read failure"), recovered_state]
    )
    monkeypatch.setattr(service.state_snapshot, "build", build_state)

    with pytest.raises(RuntimeError, match="transient strict read failure"):
        service.get_state()

    failed = service._committed_view_publication()
    assert failed.usable is False
    assert failed.generation == initial.generation

    recovered = service.get_view_publication()

    assert recovered.usable is True
    assert recovered.state == recovered_state
    assert recovered.generation > failed.generation
    assert build_state.call_count == 2
    assert delivered == [recovered]


def test_safe_read_does_not_recover_publication_during_a_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ApplicationService(Study())
    initial = service._committed_view_publication()
    recovered_state = replace(initial.state, pipeline_stage="data_loaded")
    build_state = MagicMock(return_value=recovered_state)
    monkeypatch.setattr(service.state_snapshot, "build", build_state)
    service._view_coordinator.mark_stale("mutation in progress")

    with service._command_lock:
        service._mutation_in_progress = True
        try:
            during_mutation = service.get_view_publication()
        finally:
            service._mutation_in_progress = False

    assert during_mutation.usable is False
    assert during_mutation.generation == initial.generation
    build_state.assert_not_called()

    recovered = service.get_view_publication()

    assert recovered.usable is True
    assert recovered.state == recovered_state
    assert recovered.generation > during_mutation.generation
    assert build_state.call_count == 1


def test_stale_publication_read_does_not_wait_for_the_command_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ApplicationService(Study())
    build_state = MagicMock(return_value=ApplicationStateSnapshot.empty())
    monkeypatch.setattr(service.state_snapshot, "build", build_state)
    service._view_coordinator.mark_stale("mutation owns the command lock")
    lock_acquired = Event()
    release_lock = Event()
    holder_timed_out = Event()
    query_completed = Event()
    publications = []

    def hold_command_lock() -> None:
        with service._command_lock:
            lock_acquired.set()
            if not release_lock.wait(timeout=THREAD_WATCHDOG_SECONDS):
                holder_timed_out.set()

    def read_publication() -> None:
        publications.append(service.get_view_publication())
        query_completed.set()

    holder = Thread(target=hold_command_lock)
    holder.start()
    assert lock_acquired.wait(timeout=THREAD_WATCHDOG_SECONDS)

    reader = Thread(target=read_publication)
    started_at = time.perf_counter()
    reader.start()
    completed_while_locked = query_completed.wait(timeout=0.2)
    elapsed = time.perf_counter() - started_at
    holder_owned_lock = (
        holder.is_alive()
        and not holder_timed_out.is_set()
        and not release_lock.is_set()
    )

    release_lock.set()
    holder.join(timeout=THREAD_WATCHDOG_SECONDS)
    reader.join(timeout=THREAD_WATCHDOG_SECONDS)
    assert completed_while_locked is True
    assert elapsed < 0.2
    assert holder_owned_lock is True
    assert holder.is_alive() is False
    assert reader.is_alive() is False
    publication = publications[0]
    assert publication.usable is False
    build_state.assert_not_called()


def test_published_state_query_does_not_wait_to_reconcile_pending_saliency() -> None:
    service = ApplicationService(Study())
    service.training_publications.remember_saliency_terminal(
        PostTrainingSaliencyStatus(
            phase=PostTrainingSaliencyPhase.CANCELLED,
            generation=1,
            run=TrainingRunIdentity(trainer_id="trainer-1", run_id=1),
            training_generation=None,
            methods=("Gradient",),
            message="Automatic saliency was cancelled.",
        )
    )
    lock_acquired = Event()
    release_lock = Event()
    query_finished = Event()

    def hold_command_lock() -> None:
        with service._command_lock:
            lock_acquired.set()
            release_lock.wait(timeout=THREAD_WATCHDOG_SECONDS)

    def query_published_state() -> None:
        service.query_published_state()
        query_finished.set()

    holder = Thread(target=hold_command_lock)
    query = Thread(target=query_published_state)
    holder.start()
    assert lock_acquired.wait(timeout=THREAD_WATCHDOG_SECONDS)
    query.start()

    completed_without_unlock = query_finished.wait(timeout=0.2)
    release_lock.set()
    holder.join(timeout=THREAD_WATCHDOG_SECONDS)
    query.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert completed_without_unlock is True
    assert holder.is_alive() is False
    assert query.is_alive() is False


def test_unreliable_recovery_snapshot_remains_fail_closed() -> None:
    initial = ApplicationStateSnapshot.empty()
    unreliable = replace(
        initial,
        pipeline_stage="data_loaded",
        state_reliable=False,
        read_errors=["training snapshot changed"],
    )
    coordinator = ApplicationViewCoordinator(
        initial,
        initial_training_boundary=_boundary(),
        build_state=MagicMock(return_value=unreliable),
        capture_training_boundary=lambda: _boundary(),
    )

    publication = coordinator.refresh_opportunistic()

    assert publication.usable is False
    assert publication.verified is False
    assert publication.stale is True
    assert publication.state.state_reliable is False
    assert publication.state.pipeline_stage == "unavailable"
    assert publication.generation == 1
    assert publication.refresh_error == "training snapshot changed"


def test_published_state_query_reads_only_the_committed_fail_closed_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ApplicationService(Study())
    initial = service._committed_view_publication()
    recovered_state = replace(initial.state, pipeline_stage="data_loaded")
    build_state = MagicMock(return_value=recovered_state)
    monkeypatch.setattr(service.state_snapshot, "build", build_state)
    service._view_coordinator.mark_stale("transient query read failure")

    result = service.execute(QueryStateCommand(query="state"))

    assert result.failed is True
    assert result.state.state_reliable is False
    assert result.diagnostics["view_verified"] is False
    assert result.diagnostics["view_stale"] is True
    assert result.diagnostics["publication_generation"] == initial.generation
    build_state.assert_not_called()


def test_publication_generation_changes_when_only_training_identity_changes() -> None:
    state = ApplicationStateSnapshot.empty()
    first = _boundary("trainer-a", generation=2)
    second = _boundary("trainer-b", generation=2)
    boundaries = iter((second, second))
    coordinator = ApplicationViewCoordinator(
        state,
        initial_training_boundary=first,
        build_state=lambda: state,
        capture_training_boundary=lambda: next(boundaries),
    )

    initial = coordinator.committed()
    refreshed = coordinator.refresh_strict()
    publication = coordinator.committed()

    assert refreshed == state
    assert publication.state == state
    assert publication.training_boundary == second
    assert publication.generation > initial.generation


def test_strict_refresh_retries_one_transient_training_boundary_change() -> None:
    state = ApplicationStateSnapshot.empty()
    first = _boundary("trainer-a", generation=1)
    second = _boundary("trainer-a", generation=2)
    boundaries = iter((first, second, second, second))
    build_state = MagicMock(return_value=state)
    coordinator = ApplicationViewCoordinator(
        state,
        initial_training_boundary=first,
        build_state=build_state,
        capture_training_boundary=lambda: next(boundaries),
    )

    refreshed = coordinator.refresh_strict()
    publication = coordinator.committed()

    assert refreshed == state
    assert publication.usable is True
    assert publication.training_boundary == second
    assert build_state.call_count == 2


def test_strict_refresh_captures_training_history_inside_the_same_boundary() -> None:
    state = ApplicationStateSnapshot.empty()
    first = _boundary("trainer-a", generation=2)
    second = _boundary("trainer-a", generation=4)
    boundaries = iter((first, second, second, second))
    build_state = MagicMock(return_value=state)
    build_history = MagicMock(
        side_effect=[
            [{"identity": {"plan_index": 0, "run_index": 0}, "epoch": 0}],
            [{"identity": {"plan_index": 0, "run_index": 0}, "epoch": 1}],
        ]
    )
    coordinator = ApplicationViewCoordinator(
        state,
        initial_training_boundary=first,
        build_state=build_state,
        build_training_history=build_history,
        capture_training_boundary=lambda: next(boundaries),
    )

    coordinator.refresh_strict()
    publication = coordinator.committed()

    assert publication.training_boundary == second
    assert publication.training_history == (
        {"identity": {"plan_index": 0, "run_index": 0}, "epoch": 1},
    )
    assert build_state.call_count == 2
    assert build_history.call_count == 2


def test_application_service_publication_captures_detached_data_summary_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Visible aggregate summaries must share the committed view revision."""
    service = ApplicationService(Study())
    raw_rows = [
        {
            "filepath": "/data/sub-01.edf",
            "filename": "sub-01.edf",
            "subject": "01",
            "session": "baseline",
            "n_channels": 22,
            "sampling_frequency": 250.0,
            "epochs_length": 0,
            "is_raw": True,
            "event": {"count": 48, "labels": ["left", "right"]},
            "highpass": 1.0,
            "lowpass": 40.0,
        }
    ]
    monkeypatch.setattr(
        service.dataset,
        "get_loaded_data_rows",
        MagicMock(return_value=raw_rows),
    )
    monkeypatch.setattr(
        service.dataset,
        "get_preprocessed_data_rows",
        MagicMock(return_value=[]),
    )

    try:
        service.get_state()
        publication = service.get_view_publication()

        assert publication.data_summary_rows == tuple(raw_rows)
        assert publication.usable is True
    finally:
        service.close()
