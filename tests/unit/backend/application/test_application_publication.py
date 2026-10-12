"""Application boundary: publication behavior."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event, Lock, Thread
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from tests.unit.backend.application.application_test_support import (
    THREAD_WATCHDOG_SECONDS,
    _off_class_weighting,
    _raw_mock,
)
from XBrainLab.backend.application import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationService,
    ChangedState,
    CommandName,
    ErrorType,
    NewSessionCommand,
    QueryStateCommand,
    ScanSourceCommand,
)
from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.state import (
    ApplicationStateSnapshot,
)
from XBrainLab.backend.application.view_publication import ApplicationViewStore
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import (
    Trainer,
    TrainingPlanHolder,
)
from XBrainLab.backend.training.record import (
    RecordKey,
    TrainRecord,
    TrainRecordKey,
)
from XBrainLab.backend.training_state_contract import (
    TrainingLifecycleEvent,
    TrainingOutcomeState,
    TrainingReadBoundary,
    TrainingRunIdentity,
    TrainingStateToken,
    TrainingTerminalOutcome,
)
from XBrainLab.backend.utils.observer import ObserverDeliveryStatus


def test_shutdown_owner_exists_before_lifecycle_observers_can_publish(
    monkeypatch,
) -> None:
    study = Study()
    training_events = study.training_state_service
    original_subscribe = training_events.subscribe_training_started
    observed_callbacks: list[object] = []

    def subscribe_and_publish(callback) -> None:
        original_subscribe(callback)
        observed_callbacks.append(callback)
        callback()

    monkeypatch.setattr(
        training_events,
        "subscribe_training_started",
        subscribe_and_publish,
    )

    service = ApplicationService(study)

    assert observed_callbacks
    assert service.is_closed is False
    service.close()


def test_application_service_serializes_commands_across_calling_threads(monkeypatch):
    study = Study()
    service = ApplicationService(study)
    second_service = ApplicationService(study)
    original_execute_allowed = service._execute_allowed
    counter_lock = Lock()
    active_calls = 0
    max_active_calls = 0

    def tracked_execute_allowed(command, name):
        nonlocal active_calls, max_active_calls
        with counter_lock:
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
        try:
            time.sleep(0.03)
            return original_execute_allowed(command, name)
        finally:
            with counter_lock:
                active_calls -= 1

    monkeypatch.setattr(service, "_execute_allowed", tracked_execute_allowed)
    monkeypatch.setattr(second_service, "_execute_allowed", tracked_execute_allowed)
    commands = [NewSessionCommand(confirmed=True) for _ in range(2)]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda item: item[0].execute(item[1]),
                zip((service, second_service), commands, strict=True),
            )
        )

    assert all(result.ok for result in results)
    assert max_active_calls == 1


def test_query_state_command_reads_committed_publication_without_mutation_lock() -> (
    None
):
    study = Study()
    service = ApplicationService(study)
    initial = service.get_view_publication()
    lock_acquired = Event()
    release_lock = Event()
    holder_timed_out = Event()

    def hold_mutation_lock() -> None:
        with service._command_lock:
            lock_acquired.set()
            if not release_lock.wait(timeout=THREAD_WATCHDOG_SECONDS):
                holder_timed_out.set()

    holder = Thread(target=hold_mutation_lock)
    holder.start()
    assert lock_acquired.wait(timeout=THREAD_WATCHDOG_SECONDS)

    results = []
    query_completed = Event()

    def query_state() -> None:
        results.append(service.execute(QueryStateCommand(query="state")))
        query_completed.set()

    query_thread = Thread(target=query_state)
    started_at = time.perf_counter()
    query_thread.start()
    completed_while_locked = query_completed.wait(timeout=0.2)
    elapsed = time.perf_counter() - started_at
    holder_owned_lock = (
        holder.is_alive()
        and not holder_timed_out.is_set()
        and not release_lock.is_set()
    )

    release_lock.set()
    holder.join(timeout=THREAD_WATCHDOG_SECONDS)
    query_thread.join(timeout=THREAD_WATCHDOG_SECONDS)
    assert completed_while_locked is True
    assert elapsed < 0.2
    assert holder_owned_lock is True
    assert not holder.is_alive()
    assert not query_thread.is_alive()
    result = results[0]
    assert result.ok is True
    assert result.state == initial.state
    assert result.diagnostics["publication_generation"] == initial.generation
    assert result.diagnostics["publication_revision"] == initial.revision
    assert result.diagnostics["view_stale"] is False


def test_state_query_flags_do_not_mix_publication_generations() -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication().state
    updated = replace(before, pipeline_stage="data_loaded")
    service.state_snapshot.build = MagicMock(side_effect=[before, updated])

    result = service.execute(
        QueryStateCommand(
            query="state",
            params={"unused": True},
        )
    )

    assert result.ok is True
    assert result.state.pipeline_stage == result.diagnostics["state"]["pipeline_stage"]
    assert service.state_snapshot.build.call_count == 0


def test_published_state_query_returns_actionable_readiness_summary() -> None:
    service = ApplicationService(Study())

    result = service.execute(QueryStateCommand(query="state"))

    assert result.ok is True
    assert result.message == "No data loaded. Next: Scan data source."


def test_detached_data_query_fails_fast_instead_of_waiting_for_mutation_lock() -> None:
    service = ApplicationService(Study())
    lock_acquired = Event()
    release_lock = Event()

    def hold_mutation_lock() -> None:
        with service._command_lock:
            lock_acquired.set()
            release_lock.wait(timeout=THREAD_WATCHDOG_SECONDS)

    holder = Thread(target=hold_mutation_lock)
    holder.start()
    assert lock_acquired.wait(timeout=THREAD_WATCHDOG_SECONDS)

    results = []
    query_completed = Event()

    def query_objects() -> None:
        results.append(
            service.execute(
                QueryStateCommand(query="data_lists"),
            )
        )
        query_completed.set()

    query_thread = Thread(target=query_objects)
    query_thread.start()
    assert query_completed.wait(timeout=THREAD_WATCHDOG_SECONDS)
    assert release_lock.is_set() is False

    release_lock.set()
    holder.join(timeout=THREAD_WATCHDOG_SECONDS)
    query_thread.join(timeout=THREAD_WATCHDOG_SECONDS)
    assert not holder.is_alive()
    assert not query_thread.is_alive()
    result = results[0]
    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert result.diagnostics["application_busy"] is True


def test_data_summary_query_uses_committed_publication_while_command_lock_is_busy(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.get_state()
    live_read = MagicMock(
        side_effect=AssertionError(
            "published summary must not read mutable EEG objects"
        )
    )
    monkeypatch.setattr(service.dataset, "get_loaded_data_list", live_read)
    lock_acquired = Event()
    release_lock = Event()

    def hold_mutation_lock() -> None:
        with service._command_lock:
            lock_acquired.set()
            release_lock.wait(timeout=THREAD_WATCHDOG_SECONDS)

    holder = Thread(target=hold_mutation_lock)
    holder.start()
    assert lock_acquired.wait(timeout=THREAD_WATCHDOG_SECONDS)

    try:
        result = service.execute(QueryStateCommand(query="data_summary"))
    finally:
        release_lock.set()
        holder.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not holder.is_alive()
    assert result.ok is True
    assert result.message == "Dataset summary ready."
    assert result.diagnostics["count"] == 1
    assert result.diagnostics["files"] == [raw.get_filename()]
    live_read.assert_not_called()


def test_published_data_summary_prefers_preprocessed_then_falls_back_to_loaded_rows() -> (
    None
):
    """A published summary selects processed data without leaking mutable Raw."""
    service = ApplicationService(Study())
    loaded = _raw_mock()
    loaded.get_filepath.return_value = "/data/loaded.fif"
    preprocessed = _raw_mock()
    preprocessed.get_filepath.return_value = "/data/preprocessed.fif"
    service.study.data_manager.loaded_data_list = [loaded]
    service.study.data_manager.preprocessed_data_list = [preprocessed]

    try:
        service.get_state()
        publication = service.get_view_publication()

        assert publication.data_summary_rows is not None
        assert publication.data_summary_rows[0]["filepath"] == "/data/preprocessed.fif"
        preprocessed.get_filepath.return_value = "/data/changed-after-publication.fif"
        assert publication.data_summary_rows[0]["filepath"] == "/data/preprocessed.fif"

        service.study.data_manager.preprocessed_data_list = []
        service.get_state()
        loaded_publication = service.get_view_publication()
        assert loaded_publication.data_summary_rows is not None
        assert loaded_publication.data_summary_rows[0]["filepath"] == "/data/loaded.fif"
    finally:
        service.close()


def test_published_data_summary_is_empty_when_real_dataset_lists_are_empty() -> None:
    service = ApplicationService(Study())

    try:
        service.get_state()
        publication = service.get_view_publication()

        assert publication.data_summary_rows == ()
    finally:
        service.close()


def test_data_summary_query_rejects_stale_expected_publication_generation() -> None:
    service = ApplicationService(Study())
    publication = service.get_view_publication()

    result = service.execute(
        QueryStateCommand(query="data_summary"),
        expected_publication_generation=publication.generation + 1,
    )

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.diagnostics["stale_publication"] is True
    assert result.diagnostics["expected_publication_generation"] == (
        publication.generation + 1
    )
    assert result.diagnostics["current_publication_generation"] == (
        publication.generation
    )


def test_data_summary_query_fails_closed_for_unusable_publication() -> None:
    service = ApplicationService(Study())
    service._view_coordinator.mark_stale("forced summary publication failure")

    result = service.execute(QueryStateCommand(query="data_summary"))

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.diagnostics["view_stale"] is True
    assert result.diagnostics["view_verified"] is False


def test_view_publication_keeps_state_and_capabilities_on_one_generation() -> None:
    service = ApplicationService(Study())

    before = service.get_view_publication()
    result = service.execute(ScanSourceCommand(source_path="missing.fif"))
    after = service.get_view_publication()

    assert result.failed is True
    assert after.generation > before.generation
    assert after.state == result.state
    assert after.capabilities == build_capability_policy(after.state)


def test_bids_catalog_only_scan_preserves_application_publication(
    tmp_path: Path,
) -> None:
    bids_root = tmp_path / "bids"
    eeg_dir = bids_root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (bids_root / "dataset_description.json").write_text("{}", encoding="utf-8")
    (eeg_dir / "sub-01_task-P300_eeg.set").write_bytes(b"catalog only")
    service = ApplicationService(Study())
    delivered = []
    service.subscribe(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, delivered.append)
    before = service.get_view_publication()

    result = service.execute(
        ScanSourceCommand(
            source_path=str(bids_root),
            source_hint="bids",
            catalog_only=True,
        )
    )
    after = service.get_view_publication()

    assert result.ok is True
    assert result.diagnostics["bids_subject_catalog"]["subject_count"] == 1
    assert result.state == before.state
    assert after == before
    assert delivered == [before]
    assert service.acknowledge_view_publication_delivery(before.revision) is True

    repeated = service.execute(
        ScanSourceCommand(
            source_path=str(bids_root),
            source_hint="bids",
            catalog_only=True,
        )
    )

    assert repeated.ok is True
    assert service.get_view_publication() == before
    assert delivered == [before]


def test_auto_catalog_only_scan_classifies_generic_folder_without_publication(
    tmp_path: Path,
) -> None:
    source = tmp_path / "generic"
    source.mkdir()
    (source / "recording.edf").write_bytes(b"header only")
    service = ApplicationService(Study())
    before = service.get_view_publication()

    result = service.execute(
        ScanSourceCommand(
            source_path=str(source),
            source_hint="auto",
            catalog_only=True,
        )
    )

    assert result.ok is True
    assert result.diagnostics == {
        "payload_type": "source_classification",
        "source_kind": "folder",
    }
    assert service.get_view_publication() == before


def test_auto_catalog_only_scan_classifies_one_file_without_publication(
    tmp_path: Path,
) -> None:
    source = tmp_path / "recording.vhdr"
    source.write_text(
        "Brain Vision Data Exchange Header File Version 1.0",
        encoding="utf-8",
    )
    service = ApplicationService(Study())
    before = service.get_view_publication()

    result = service.execute(
        ScanSourceCommand(
            source_path=str(source),
            source_hint="auto",
            catalog_only=True,
        )
    )

    assert result.ok is True
    assert result.diagnostics["source_kind"] == "file"
    assert service.get_view_publication() == before


def test_auto_catalog_only_scan_missing_path_fails_without_partial_interpretation(
    tmp_path: Path,
) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()

    result = service.execute(
        ScanSourceCommand(
            source_path=str(tmp_path / "missing"),
            source_hint="auto",
            catalog_only=True,
        )
    )

    assert result.failed is True
    after = service.get_view_publication()
    assert after.state.interpretation == before.state.interpretation
    assert after.state.raw == before.state.raw


def test_auto_catalog_only_scan_classifies_bids_and_returns_subject_catalog(
    tmp_path: Path,
) -> None:
    bids_root = tmp_path / "bids"
    eeg_dir = bids_root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (bids_root / "dataset_description.json").write_text("{}", encoding="utf-8")
    (eeg_dir / "sub-01_task-P300_eeg.set").write_bytes(b"catalog only")
    service = ApplicationService(Study())
    before = service.get_view_publication()

    result = service.execute(
        ScanSourceCommand(
            source_path=str(bids_root),
            source_hint="auto",
            catalog_only=True,
        )
    )

    assert result.ok is True
    assert result.diagnostics["payload_type"] == "source_classification"
    assert result.diagnostics["source_kind"] == "bids"
    assert result.diagnostics["bids_subject_catalog"]["subject_count"] == 1
    assert service.get_view_publication() == before


def test_view_publication_consumers_cannot_mutate_committed_state_or_policy() -> None:
    service = ApplicationService(Study())
    lock_acquired = Event()
    release_lock = Event()

    def hold_mutation_lock() -> None:
        with service._command_lock:
            lock_acquired.set()
            release_lock.wait(timeout=2.0)

    holder = Thread(target=hold_mutation_lock)
    holder.start()
    assert lock_acquired.wait(timeout=1.0)

    exposed = service.get_view_publication()
    exposed.state.raw.files.append("tampered.gdf")
    train = exposed.capabilities.get(CommandName.TRAIN)
    exposed.capabilities.capabilities[CommandName.TRAIN.value] = replace(
        train,
        enabled=True,
    )
    committed = service.get_view_publication()

    release_lock.set()
    holder.join(timeout=1.0)
    assert not holder.is_alive()
    assert "tampered.gdf" not in committed.state.raw.files
    assert committed.capabilities.get(CommandName.TRAIN).enabled is False


def test_view_publication_read_never_rebuilds_backend_state(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    updated_state = replace(before.state, pipeline_stage="training")
    monkeypatch.setattr(
        service.state_snapshot,
        "build",
        MagicMock(return_value=updated_state),
    )

    after = service.get_view_publication()

    assert after == before
    service.state_snapshot.build.assert_not_called()


def test_training_stopped_event_publishes_a_fresh_backend_generation(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    updated_state = replace(before.state, pipeline_stage="trained")
    build = MagicMock(return_value=updated_state)
    monkeypatch.setattr(service.state_snapshot, "build", build)

    service.training.notify("training_stopped")
    after = service.get_view_publication()

    assert build.call_count == 1
    assert after.generation > before.generation
    assert after.state.pipeline_stage == "trained"


def test_training_terminal_event_is_emitted_once_after_its_publication() -> None:
    service = ApplicationService(Study())
    trainer = Trainer([])
    service.study.training_manager.trainer = trainer
    trainer.run(interact=False)
    terminal_events = []
    service.training.subscribe("training_terminal_published", terminal_events.append)

    service.training.notify("training_stopped")
    service.training.notify("training_stopped")

    assert len(terminal_events) == 1
    event = terminal_events[0]
    publication = service.get_view_publication()
    assert event.publication_generation == publication.generation
    assert event.token == trainer.get_state_snapshot_token()
    assert event.outcome.state is TrainingOutcomeState.COMPLETED


def test_training_terminal_delivery_waits_for_canonical_view_acknowledgement(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    state = service.get_state()
    lifecycle_event = MagicMock(spec=TrainingLifecycleEvent)
    publish_view = MagicMock(return_value=False)
    deliver_terminal = MagicMock(return_value=True)
    monkeypatch.setattr(
        service.publication_lifecycle,
        "_refresh_training_publication",
        MagicMock(return_value=state),
    )
    monkeypatch.setattr(
        service.publication_lifecycle,
        "terminal_training_publication_event",
        MagicMock(return_value=lifecycle_event),
    )
    monkeypatch.setattr(
        service.publication_lifecycle,
        "_publish_view_changed",
        publish_view,
    )
    monkeypatch.setattr(
        service.publication_lifecycle,
        "deliver_training_terminal_publication",
        deliver_terminal,
    )

    assert service.publication_lifecycle.publish_training_terminal_state() is False
    publish_view.assert_called_once()
    deliver_terminal.assert_called_once_with(lifecycle_event)


def test_nonterminal_training_reconciliation_does_not_republish_application_view(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    state = service.get_state()
    publish_view = MagicMock(return_value=False)
    monkeypatch.setattr(
        service.publication_lifecycle,
        "_refresh_training_publication",
        MagicMock(return_value=state),
    )
    monkeypatch.setattr(
        service.publication_lifecycle,
        "_publish_view_changed",
        publish_view,
    )

    assert state.training.terminal_outcome.is_terminal is False
    assert service.publication_lifecycle.publish_training_terminal_state() is True
    publish_view.assert_not_called()


def test_terminal_training_reconciliation_fails_when_identity_cannot_be_built(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    trainer = Trainer([])
    service.study.training_manager.trainer = trainer
    trainer.run(interact=False)
    state = service.get_state()
    publish_view = MagicMock(return_value=True)
    monkeypatch.setattr(
        service.publication_lifecycle,
        "_refresh_training_publication",
        MagicMock(return_value=state),
    )
    monkeypatch.setattr(
        service.publication_lifecycle,
        "terminal_training_publication_event",
        MagicMock(return_value=None),
    )
    monkeypatch.setattr(
        service.publication_lifecycle,
        "_publish_view_changed",
        publish_view,
    )

    assert state.training.terminal_outcome.is_terminal is True
    assert service.publication_lifecycle.publish_training_terminal_state() is False
    publish_view.assert_not_called()


def test_deferred_view_ack_releases_retained_training_terminal_event() -> None:
    service = ApplicationService(Study())
    trainer = Trainer([])
    service.study.training_manager.trainer = trainer
    trainer.run(interact=False)
    deferred_revisions: list[int] = []
    terminal_events: list[TrainingLifecycleEvent] = []

    def defer_view(publication) -> ObserverDeliveryStatus:
        deferred_revisions.append(publication.revision)
        return ObserverDeliveryStatus.DEFERRED

    service.subscribe(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, defer_view)
    service.training.subscribe(
        "training_terminal_published",
        terminal_events.append,
    )

    assert service.publication_lifecycle.publish_training_terminal_state() is False
    publication = service.get_view_publication()
    delivery = service.training_publications.training_delivery_state()

    assert deferred_revisions == [publication.revision]
    assert terminal_events == []
    assert delivery.pending_count == 1

    assert service.acknowledge_view_publication_delivery(publication.revision) is True

    delivery = service.training_publications.training_delivery_state()
    assert len(terminal_events) == 1
    assert delivery.pending_count == 0
    assert delivery.delivered_count == 1


def test_saliency_delivery_waits_for_canonical_view_acknowledgement(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    publish_view = MagicMock(return_value=False)
    notify_visualization = MagicMock(return_value=True)
    monkeypatch.setattr(
        service.publication_lifecycle,
        "_publish_view_changed",
        publish_view,
    )
    monkeypatch.setattr(
        service.publication_lifecycle._visualization,
        "notify",
        notify_visualization,
    )

    assert service.publication_lifecycle.notify_saliency_publication_changed() is False

    publish_view.assert_called_once()
    notify_visualization.assert_not_called()


def test_saliency_delivery_does_not_publish_stale_view_during_mutation(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    publish_view = MagicMock(return_value=True)
    notify_visualization = MagicMock(return_value=True)
    monkeypatch.setattr(
        service.publication_lifecycle,
        "_publish_view_changed",
        publish_view,
    )
    monkeypatch.setattr(
        service.publication_lifecycle._visualization,
        "notify",
        notify_visualization,
    )
    service._view_coordinator.mark_stale("mutation in progress")
    service._mutation_in_progress = True
    try:
        assert (
            service.publication_lifecycle.notify_saliency_publication_changed() is False
        )
    finally:
        service._mutation_in_progress = False

    publish_view.assert_not_called()
    notify_visualization.assert_not_called()


def test_training_terminal_event_rejects_mismatched_trainer_identity(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    trainer = Trainer([])
    service.study.training_manager.trainer = trainer
    trainer.run(interact=False)
    service.training.notify("training_stopped")
    publication = service.get_view_publication()
    outcome = publication.state.training.terminal_outcome
    assert outcome.run is not None
    mismatched_state = replace(
        publication.state,
        training=replace(
            publication.state.training,
            terminal_outcome=replace(
                outcome,
                run=TrainingRunIdentity(
                    trainer_id="different-trainer",
                    run_id=outcome.run.run_id,
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        service,
        "_committed_view_publication",
        lambda: replace(publication, state=mismatched_state),
    )

    assert (
        service.publication_lifecycle.terminal_training_publication_event(
            mismatched_state
        )
        is None
    )


def test_training_terminal_publication_ledger_accepts_each_new_generation_once(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    state = service.get_state()
    first_run = TrainingRunIdentity(trainer_id="terminal-ledger", run_id=1)
    second_run = TrainingRunIdentity(trainer_id="terminal-ledger", run_id=2)
    first = TrainingLifecycleEvent(
        token=TrainingStateToken(generation=11, stable=True),
        outcome=TrainingTerminalOutcome(
            state=TrainingOutcomeState.COMPLETED,
            run=first_run,
        ),
        publication_generation=21,
    )
    second = TrainingLifecycleEvent(
        token=TrainingStateToken(generation=12, stable=True),
        outcome=TrainingTerminalOutcome(
            state=TrainingOutcomeState.COMPLETED,
            run=second_run,
        ),
        publication_generation=22,
    )
    stale = TrainingLifecycleEvent(
        token=TrainingStateToken(generation=10, stable=True),
        outcome=TrainingTerminalOutcome(
            state=TrainingOutcomeState.FAILED,
            run=TrainingRunIdentity(trainer_id="terminal-ledger", run_id=3),
        ),
        publication_generation=20,
    )
    terminal_events: list[TrainingLifecycleEvent] = []

    def observe(event: TrainingLifecycleEvent) -> None:
        terminal_events.append(event)

    generated_events = iter((first, first, second, second, stale))
    monkeypatch.setattr(
        service.publication_lifecycle,
        "_refresh_training_publication",
        lambda: state,
    )
    monkeypatch.setattr(
        service.publication_lifecycle,
        "terminal_training_publication_event",
        lambda _state: next(generated_events),
    )
    service.training.subscribe("training_terminal_published", observe)

    service.publication_lifecycle.publish_training_terminal_state()
    service.publication_lifecycle.publish_training_terminal_state()
    service.publication_lifecycle.publish_training_terminal_state()
    service.publication_lifecycle.publish_training_terminal_state()
    service.publication_lifecycle.publish_training_terminal_state()

    assert terminal_events == [first, second]
    delivery_state = service.training_publications.training_delivery_state()
    assert delivery_state.active_count == 0
    assert delivery_state.delivered_count == 2
    assert delivery_state.latest_publication_generation == 22


def test_training_updated_event_publishes_live_progress_and_policy(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    updated_state = replace(
        before.state,
        pipeline_stage="training",
        training=replace(
            before.state.training,
            is_running=True,
            progress_message="Epoch 2/5",
        ),
        active_training=replace(
            before.state.active_training,
            is_running=True,
        ),
    )
    build = MagicMock(return_value=updated_state)
    monkeypatch.setattr(service.state_snapshot, "build", build)

    service.training.notify("training_updated")
    after = service.get_view_publication()
    query = service.execute(QueryStateCommand(query="state"))

    assert build.call_count == 1
    assert after.generation > before.generation
    assert after.state.training.progress_message == "Epoch 2/5"
    assert after.capabilities == build_capability_policy(after.state)
    assert query.ok is True
    assert query.state == after.state
    assert query.diagnostics["publication_generation"] == after.generation
    assert query.diagnostics["publication_revision"] == after.revision
    assert query.diagnostics["state"]["training"]["progress_message"] == "Epoch 2/5"


def test_real_training_updated_event_is_visible_through_query_state() -> None:
    study = Study()
    service = ApplicationService(study)
    trainer = Trainer([])
    study.training_manager.trainer = trainer
    trainer.progress_text = "Epoch 2/5"

    service.training.notify("training_updated")
    result = service.execute(QueryStateCommand(query="state"))

    assert result.ok is True
    assert result.state.training.has_trainer is True
    assert result.state.training.progress_message == "Epoch 2/5"
    assert result.diagnostics["state"]["training"]["progress_message"] == "Epoch 2/5"
    assert result.diagnostics["publication_generation"] > 1


def test_training_updated_skips_publication_while_training_token_is_unstable(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    unstable = TrainingReadBoundary(
        trainer_identity="unstable-training-test",
        token=TrainingStateToken(generation=3, stable=False),
    )
    monkeypatch.setattr(
        service.state_snapshot,
        "capture_training_read_boundary",
        MagicMock(return_value=unstable),
    )
    build = MagicMock()
    monkeypatch.setattr(service.state_snapshot, "build", build)

    service.training.notify("training_updated")
    after = service.get_view_publication()

    build.assert_not_called()
    assert after == before
    assert after.usable is True


def test_training_updated_does_not_wait_for_the_command_lock(monkeypatch) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    lock_acquired = Event()
    release_lock = Event()

    def hold_command_lock() -> None:
        with service._command_lock:
            lock_acquired.set()
            release_lock.wait(timeout=THREAD_WATCHDOG_SECONDS)

    holder = Thread(target=hold_command_lock)
    holder.start()
    assert lock_acquired.wait(timeout=THREAD_WATCHDOG_SECONDS)
    build = MagicMock()
    monkeypatch.setattr(service.state_snapshot, "build", build)
    update_returned = Event()

    notifier = Thread(
        target=lambda: (
            service.training.notify("training_updated"),
            update_returned.set(),
        )
    )
    notifier.start()

    assert update_returned.wait(timeout=THREAD_WATCHDOG_SECONDS)
    assert service._committed_view_publication() == before
    build.assert_not_called()

    release_lock.set()
    holder.join(timeout=THREAD_WATCHDOG_SECONDS)
    notifier.join(timeout=THREAD_WATCHDOG_SECONDS)
    assert not holder.is_alive()
    assert not notifier.is_alive()


def test_training_updated_recovers_after_a_transient_unstable_snapshot(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    updated_state = replace(
        before.state,
        pipeline_stage="training",
        training=replace(
            before.state.training,
            is_running=True,
            progress_message="Epoch 3/5",
        ),
        active_training=replace(before.state.active_training, is_running=True),
    )
    unstable_state = replace(
        updated_state,
        pipeline_stage="unavailable",
        state_reliable=False,
        training_liveness_reliable=False,
        read_errors=["training state changed during snapshot"],
    )
    build = MagicMock(side_effect=[unstable_state, updated_state])
    monkeypatch.setattr(service.state_snapshot, "build", build)

    service.training.notify("training_updated")
    transient = service._committed_view_publication()
    service.training.notify("training_updated")
    recovered = service._committed_view_publication()

    assert transient.usable is False
    assert transient.generation == before.generation
    assert recovered.usable is True
    assert recovered.generation > before.generation
    assert recovered.state.training.progress_message == "Epoch 3/5"
    assert build.call_count == 2


def test_training_history_query_reuses_live_event_publication(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    updated_state = replace(
        before.state,
        pipeline_stage="training",
        training=replace(
            before.state.training,
            is_running=True,
            progress_message="Epoch 1/5",
        ),
        active_training=replace(
            before.state.active_training,
            is_running=True,
        ),
    )
    build = MagicMock(return_value=updated_state)
    monkeypatch.setattr(service.state_snapshot, "build", build)

    service.training.notify("training_updated")
    published = service.get_view_publication()
    result = service.execute(
        QueryStateCommand(query="training_history"),
    )

    assert result.ok is True
    assert result.state == published.state
    assert build.call_count == 1


def test_training_history_query_rejects_when_training_token_outgrows_publication(
    monkeypatch,
) -> None:
    study = Study()
    trainer = Trainer([])
    study.training_manager.trainer = trainer
    service = ApplicationService(study)
    build = MagicMock(wraps=service.state_snapshot.build)
    monkeypatch.setattr(service.state_snapshot, "build", build)

    trainer.add_training_plan_holders([])
    result = service.execute(
        QueryStateCommand(query="training_history"),
    )

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.diagnostics["read_only_query"] is True
    assert result.diagnostics["query"] == "training_history"
    assert build.call_count == 0


def test_view_publication_health_and_policy_are_atomic_under_concurrent_reads() -> None:
    initial = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(initial, TrainingReadBoundary.no_trainer())
    start = Event()

    def publish_updates() -> None:
        start.wait(timeout=1.0)
        for index in range(80):
            state = replace(initial, pipeline_stage=f"stage-{index}")
            store.publish(state, TrainingReadBoundary.no_trainer())
            store.mark_stale(f"refresh-{index}")

    def read_and_validate() -> None:
        start.wait(timeout=1.0)
        for _ in range(240):
            publication = store.read()
            assert publication.capabilities == build_capability_policy(
                publication.state
            )
            assert publication.verified is publication.state.state_reliable
            if publication.stale:
                assert publication.refresh_error
            else:
                assert publication.refresh_error is None

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(publish_updates)]
        futures.extend(executor.submit(read_and_validate) for _ in range(4))
        start.set()
        for future in futures:
            future.result(timeout=5.0)


def test_view_store_restores_only_the_same_verified_generation() -> None:
    initial = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(initial, TrainingReadBoundary.no_trainer())
    expected = store.read()
    store.mark_stale("command is awaiting confirmation")

    restored = store.restore_verified(expected)

    assert restored.generation == expected.generation
    assert restored.revision == expected.revision + 2
    assert restored.state == expected.state
    assert restored.capabilities == expected.capabilities
    assert restored.training_boundary == expected.training_boundary
    assert restored.usable is True


def test_view_store_refuses_to_restore_over_a_newer_domain_generation() -> None:
    initial = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(initial, TrainingReadBoundary.no_trainer())
    old = store.read()
    updated = replace(initial, pipeline_stage="data_loaded")
    current = store.publish(updated, TrainingReadBoundary.no_trainer())

    with pytest.raises(RuntimeError, match="changed during control-flow recovery"):
        store.restore_verified(old)

    assert store.read() == current


def test_stale_committed_view_exposes_fail_closed_consumer_capabilities() -> None:
    service = ApplicationService(Study())
    service._view_coordinator.mark_stale("background state unavailable")

    publication = service._committed_view_publication()

    assert publication.usable is False
    assert publication.public_unavailable_code == "application_state_unavailable"
    assert (
        publication.unavailable_reason == "Workflow state is temporarily unavailable."
    )
    assert publication.diagnostic_error == "background state unavailable"
    effective = publication.effective_capabilities
    assert effective.get(CommandName.QUERY_STATE).enabled is True
    assert effective.get(CommandName.STOP_TRAINING).enabled is True
    assert effective.get(CommandName.RESET_SESSION).enabled is True
    assert effective.get(CommandName.NEW_SESSION).enabled is True
    assert effective.get(CommandName.RESET_SESSION).requires_confirmation is True
    assert effective.get(CommandName.NEW_SESSION).requires_confirmation is True
    assert effective.get(CommandName.SCAN_SOURCE).enabled is False
    assert any(
        "Workflow state is temporarily unavailable." in reason
        for reason in publication.effective_capabilities.get(
            CommandName.SCAN_SOURCE
        ).reasons
    )


def test_query_state_fails_closed_when_publication_recovery_still_fails(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    service._view_coordinator.mark_stale("background state unavailable")
    monkeypatch.setattr(
        service.state_snapshot,
        "build",
        MagicMock(side_effect=RuntimeError("background state unavailable")),
    )

    result = service.execute(QueryStateCommand(query="state"))

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.state.state_reliable is False
    assert result.state.active_training.is_running is True
    assert result.state.training.terminal_outcome.state is TrainingOutcomeState.UNKNOWN
    assert result.diagnostics["publication_generation"] == before.generation
    assert result.diagnostics["view_stale"] is True
    assert result.diagnostics["view_refresh_error"] == "background state unavailable"
    assert (
        result.diagnostics["capabilities"][CommandName.SCAN_SOURCE.value]["enabled"]
        is False
    )


def test_repeated_view_refresh_failure_does_not_churn_generation_or_errors(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    service._view_coordinator.mark_stale("background state unavailable")
    build_state = MagicMock(side_effect=RuntimeError("background state unavailable"))
    monkeypatch.setattr(service.state_snapshot, "build", build_state)

    publications = [service.get_view_publication() for _ in range(5)]

    assert all(item.generation == before.generation for item in publications)
    assert all(item.usable is False for item in publications)
    assert all(item.state.state_reliable is False for item in publications)
    assert all(item.state.active_training.is_running is True for item in publications)
    assert all(
        item.state.read_errors == ["Workflow state is temporarily unavailable."]
        for item in publications
    )
    assert all(item.stale is True for item in publications)
    assert all(
        item.refresh_error == "background state unavailable" for item in publications
    )
    build_calls_before_query = build_state.call_count

    query_result = service.execute(QueryStateCommand(query="state"))

    assert query_result.failed is True
    assert query_result.error_type is ErrorType.PRECONDITION
    assert query_result.diagnostics["publication_generation"] == before.generation
    assert query_result.diagnostics["view_refresh_error"] == (
        "background state unavailable"
    )
    assert query_result.state.read_errors == [
        "Workflow state is temporarily unavailable."
    ]
    assert build_calls_before_query == 5
    assert build_state.call_count == build_calls_before_query


def test_object_query_uses_committed_generation_without_refresh_side_effects(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    build = MagicMock(wraps=service.state_snapshot.build)
    reconcile = MagicMock(
        side_effect=AssertionError("read-only query must not reconcile callbacks")
    )
    monkeypatch.setattr(service.state_snapshot, "build", build)
    monkeypatch.setattr(
        service.publication_lifecycle,
        "reconcile_pending_saliency_terminal",
        reconcile,
    )

    result = service.execute(QueryStateCommand(query="data_summary"))

    assert result.ok is True
    assert build.call_count == 0
    reconcile.assert_not_called()
    assert result.diagnostics["count"] == result.state.raw.count


@pytest.mark.parametrize(
    "token_error_type",
    [RuntimeError, KeyError],
    ids=["runtime-error", "key-error"],
)
def test_explicit_throwing_trainer_token_fails_closed_without_breaking_service(
    token_error_type,
) -> None:
    class _ThrowingTokenTrainer:
        def get_state_snapshot_token(self):
            raise token_error_type("token backend broken")

    study = Study()
    study.training_manager.trainer = cast(Any, _ThrowingTokenTrainer())

    service = ApplicationService(study)
    publication = service.get_view_publication()

    assert publication.state.state_reliable is False
    assert publication.state.pipeline_stage == "unavailable"
    assert publication.state.read_errors == [
        "Workflow state is temporarily unavailable."
    ]
    assert publication.verified is False
    assert publication.stale is True
    assert publication.refresh_error is not None
    assert "training state changed during snapshot" in publication.refresh_error
    assert publication.diagnostic_error == publication.refresh_error


def test_transient_real_training_mutation_keeps_last_verified_view_until_publish() -> (
    None
):
    service = ApplicationService(Study())
    record = object.__new__(TrainRecord)
    record._state_tracker = None
    record.epoch = 0
    record.option = cast(Any, type("Option", (), {"epoch": 1})())
    record.train = {key: [] for key in TrainRecordKey()}
    record.val = {key: [] for key in RecordKey()}
    record.eval_record = None
    record.class_weighting = _off_class_weighting()

    holder = object.__new__(TrainingPlanHolder)
    holder.train_record_list = [record]
    holder._state_tracker = None
    holder._interrupt = Event()
    holder.error = None
    holder.status = "Pending"
    holder.model_holder = cast(
        Any,
        type(
            "ModelHolder",
            (),
            {"target_model": type("EEGNet", (), {})},
        )(),
    )
    trainer = Trainer([holder])
    service.study.training_manager.trainer = trainer
    service.get_state()
    before = service.get_view_publication()

    mutation_entered = Event()
    release_mutation = Event()

    class _BlockingMetrics(dict):
        def items(self):
            mutation_entered.set()
            assert release_mutation.wait(timeout=2.0)
            return super().items()

    worker = Thread(
        target=lambda: record.update_train(_BlockingMetrics({RecordKey.LOSS: 1.0}))
    )
    worker.start()
    assert mutation_entered.wait(timeout=2.0)

    during = service.get_view_publication()

    release_mutation.set()
    worker.join(timeout=2.0)
    assert not worker.is_alive()
    after = service.get_view_publication()

    assert during.generation == before.generation
    assert during.usable is True
    assert during.state == before.state
    assert after == during

    service.training.notify("training_stopped")
    terminal = service.get_view_publication()

    assert terminal.usable is True
    assert terminal.generation >= before.generation


def test_read_only_training_history_query_reuses_committed_publication(monkeypatch):
    service = ApplicationService(Study())
    original_get_state = service.get_state
    calls = 0

    def counted_get_state():
        nonlocal calls
        calls += 1
        return original_get_state()

    monkeypatch.setattr(service, "get_state", counted_get_state)

    result = service.execute(QueryStateCommand(query="training_history"))

    assert result.failed is False
    assert result.changed_state == ChangedState()
    assert calls == 0


def test_training_history_query_returns_detached_json_rows(monkeypatch):
    service = ApplicationService(Study())
    plan = SimpleNamespace(
        option=SimpleNamespace(epoch=3),
        get_training_status=lambda: "Training 1",
    )
    record = SimpleNamespace(
        epoch=2,
        train={
            TrainRecordKey.LOSS: [0.5, 0.4],
            TrainRecordKey.ACC: [80.0, 82.0],
            TrainRecordKey.AUC: [0.7, 0.75],
            TrainRecordKey.LR: [0.001, 0.0005],
            TrainRecordKey.TIME: [1.2, 1.1],
        },
        val={
            RecordKey.LOSS: [0.6, 0.45],
            RecordKey.ACC: [75.0, 79.0],
            RecordKey.AUC: [0.65, 0.72],
        },
        start_timestamp=10.0,
        end_timestamp=70.0,
    )
    record.get_epoch = lambda: record.epoch
    record.is_finished = lambda: False
    record.get_saved_evaluation_record = lambda _split: None
    source_row = {
        "plan": plan,
        "record": record,
        "group_name": "Group 1",
        "run_name": "2",
        "model_name": "EEGNet",
        "is_active": True,
        "is_current_run": True,
    }
    monkeypatch.setattr(
        service.state_snapshot.training_state,
        "get_formatted_history",
        lambda: [source_row],
    )

    result = service.execute(QueryStateCommand(query="training_history"))

    assert result.ok is True
    json.dumps(result.diagnostics, allow_nan=False)
    returned_row = result.diagnostics["rows"][0]
    expected_row = {
        "identity": {"plan_index": 0, "run_index": 0},
        "group_name": "Group 1",
        "run_name": "2",
        "model_name": "EEGNet",
        "status": "Running",
        "status_detail": None,
        "epoch": 2,
        "max_epochs": 3,
        "is_active": True,
        "is_current_run": True,
        "start_timestamp": 10.0,
        "end_timestamp": 70.0,
        "metrics": {
            "train": {
                "loss": [0.5, 0.4],
                "accuracy": [80.0, 82.0],
                "auc": [0.7, 0.75],
                "lr": [0.001, 0.0005],
                "time": [1.2, 1.1],
            },
            "validation": {
                "loss": [0.6, 0.45],
                "accuracy": [75.0, 79.0],
                "auc": [0.65, 0.72],
            },
            "test": {"accuracy": []},
        },
        "runtime_device": "",
        "class_weighting": {},
    }
    assert returned_row == expected_row

    record.train[TrainRecordKey.ACC].append(99.0)
    record.val[RecordKey.LOSS][0] = 9.9
    record.epoch = 3
    source_row["model_name"] = "MutatedNet"

    assert result.diagnostics["rows"][0] == expected_row
