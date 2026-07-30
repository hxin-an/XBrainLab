"""Focused contracts for application publication identity and delivery."""

from dataclasses import replace
from threading import Thread

from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.view_event_publisher import (
    ApplicationViewEventPublisher,
)
from XBrainLab.backend.application.view_publication import (
    ApplicationViewStore,
)
from XBrainLab.backend.training_state_contract import TrainingReadBoundary
from XBrainLab.backend.utils.observer import ObserverDeliveryStatus


def test_view_store_revisions_include_stale_and_recovery_transitions() -> None:
    state = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(state, TrainingReadBoundary.no_trainer())
    initial = store.read()

    stale = store.mark_stale("background read failed")
    duplicate_stale = store.mark_stale("background read failed")
    recovered = store.restore_verified(initial)

    assert stale.generation == initial.generation
    assert stale.revision == initial.revision + 1
    assert duplicate_stale == stale
    assert recovered.generation == initial.generation
    assert recovered.revision == stale.revision + 1
    assert recovered.usable is True


def test_view_event_publisher_suppresses_delivered_revision_duplicates() -> None:
    state = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(state, TrainingReadBoundary.no_trainer())
    initial = store.read()
    changed = store.publish(
        replace(state, pipeline_stage="data_loaded"),
        TrainingReadBoundary.no_trainer(),
    )
    delivered = []
    publisher = ApplicationViewEventPublisher(
        initial_revision=initial.revision,
        deliver=lambda publication: delivered.append(publication) is None,
    )

    assert publisher.publish(changed) is True
    assert publisher.publish(changed) is True

    assert delivered == [changed]


def test_view_event_publisher_retries_unacknowledged_revision() -> None:
    state = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(state, TrainingReadBoundary.no_trainer())
    initial = store.read()
    changed = store.publish(
        replace(state, pipeline_stage="data_loaded"),
        TrainingReadBoundary.no_trainer(),
    )
    attempts = []

    def deliver(publication):
        attempts.append(publication.revision)
        return len(attempts) > 1

    publisher = ApplicationViewEventPublisher(
        initial_revision=initial.revision,
        deliver=deliver,
    )

    assert publisher.publish(changed) is False
    assert publisher.publish(changed) is True
    assert publisher.publish(changed) is True

    assert attempts == [changed.revision, changed.revision]


def test_view_event_publisher_accepts_late_ui_acknowledgement() -> None:
    state = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(state, TrainingReadBoundary.no_trainer())
    initial = store.read()
    changed = store.publish(
        replace(state, pipeline_stage="data_loaded"),
        TrainingReadBoundary.no_trainer(),
    )
    attempts = []
    publisher = ApplicationViewEventPublisher(
        initial_revision=initial.revision,
        deliver=lambda publication: (
            attempts.append(publication.revision) or ObserverDeliveryStatus.DEFERRED
        ),
    )

    assert publisher.publish(changed) is False
    assert publisher.publish(changed) is False
    assert attempts == [changed.revision]
    assert publisher.acknowledge(changed.revision) is True
    assert publisher.publish(changed) is True

    assert attempts == [changed.revision]


def test_view_event_publisher_allows_synchronous_observer_reentry() -> None:
    state = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(state, TrainingReadBoundary.no_trainer())
    initial = store.read()
    changed = store.publish(
        replace(state, pipeline_stage="data_loaded"),
        TrainingReadBoundary.no_trainer(),
    )
    delivered = []
    nested_results = []
    publisher: ApplicationViewEventPublisher

    def deliver(publication):
        delivered.append(publication)
        nested_results.append(publisher.publish(publication))
        return True

    publisher = ApplicationViewEventPublisher(
        initial_revision=initial.revision,
        deliver=deliver,
    )
    results = []
    worker = Thread(
        target=lambda: results.append(publisher.publish(changed)),
        daemon=True,
    )

    worker.start()
    worker.join(timeout=1)

    assert worker.is_alive() is False
    assert results == [True]
    assert nested_results == [True]
    assert delivered == [changed]
