"""Focused contracts for application publication identity and delivery."""

from dataclasses import replace
from threading import Thread

from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.view_event_publisher import (
    ApplicationViewEventPublisher,
    UnobservedDeliveryPolicy,
)
from XBrainLab.backend.application.view_publication import (
    ApplicationViewStore,
)
from XBrainLab.backend.training_state_contract import TrainingReadBoundary
from XBrainLab.backend.utils.observer import Observable, ObserverDeliveryStatus


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


def test_view_event_publisher_requires_explicit_no_render_policy() -> None:
    state = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(state, TrainingReadBoundary.no_trainer())
    initial = store.read()
    changed = store.publish(
        replace(state, pipeline_stage="data_loaded"),
        TrainingReadBoundary.no_trainer(),
    )
    observable = Observable()
    desktop_publisher = ApplicationViewEventPublisher(
        initial_revision=initial.revision,
        deliver=lambda publication: observable.notify_delivery(
            "view_publication_changed",
            publication,
        ),
    )
    headless_publisher = ApplicationViewEventPublisher(
        initial_revision=initial.revision,
        deliver=lambda publication: observable.notify_delivery(
            "view_publication_changed",
            publication,
        ),
        unobserved_delivery_policy=(
            UnobservedDeliveryPolicy.ACKNOWLEDGE_WITHOUT_RENDER
        ),
    )

    assert desktop_publisher.publish(changed) is False
    assert desktop_publisher.has_delivered_revision(changed.revision) is False
    assert headless_publisher.publish(changed) is True
    assert headless_publisher.has_delivered_revision(changed.revision) is True


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


def test_visible_owner_mode_rejects_non_owner_success_while_owner_is_deferred() -> None:
    state = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(state, TrainingReadBoundary.no_trainer())
    initial = store.read()
    changed = store.publish(
        replace(state, pipeline_stage="data_loaded"),
        TrainingReadBoundary.no_trainer(),
    )
    observable = Observable()
    non_owner_attempts: list[int] = []
    owner_attempts: list[int] = []
    observable.subscribe(
        "view_publication_changed",
        lambda publication: non_owner_attempts.append(publication.revision) or True,
    )
    observable.subscribe(
        "view_publication_changed",
        lambda publication: (
            owner_attempts.append(publication.revision)
            or ObserverDeliveryStatus.DEFERRED
        ),
    )
    publisher = ApplicationViewEventPublisher(
        initial_revision=initial.revision,
        deliver=lambda publication: observable.notify_delivery(
            "view_publication_changed",
            publication,
        ),
    )
    visible_owner = object()
    publisher.require_acknowledging_subscriber(visible_owner)

    assert publisher.publish(changed) is False
    assert publisher.has_delivered_revision(changed.revision) is False
    assert publisher.acknowledge(changed.revision, owner=object()) is False
    assert publisher.reject(changed, owner=object()) is False
    assert publisher.has_delivered_revision(changed.revision) is False
    assert publisher.acknowledge(changed.revision, owner=visible_owner) is True

    assert non_owner_attempts == [changed.revision]
    assert owner_attempts == [changed.revision]


def test_visible_owner_mode_never_promotes_aggregate_observer_success() -> None:
    state = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(state, TrainingReadBoundary.no_trainer())
    initial = store.read()
    changed = store.publish(
        replace(state, pipeline_stage="data_loaded"),
        TrainingReadBoundary.no_trainer(),
    )
    publisher = ApplicationViewEventPublisher(
        initial_revision=initial.revision,
        deliver=lambda _publication: ObserverDeliveryStatus.DELIVERED,
    )
    visible_owner = object()
    publisher.require_acknowledging_subscriber(visible_owner)

    assert publisher.publish(changed) is False
    assert publisher.has_delivered_revision(changed.revision) is False

    assert publisher.acknowledge(changed.revision, owner=visible_owner) is True


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


def test_reentrant_deferred_publication_drains_in_revision_order() -> None:
    state = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(state, TrainingReadBoundary.no_trainer())
    initial = store.read()
    first = store.publish(
        replace(state, pipeline_stage="data_loaded"),
        TrainingReadBoundary.no_trainer(),
    )
    second = store.publish(
        replace(state, pipeline_stage="preprocessed"),
        TrainingReadBoundary.no_trainer(),
    )
    delivered_revisions: list[int] = []
    nested_results: list[bool] = []
    delivery_depth = 0
    max_delivery_depth = 0
    publisher: ApplicationViewEventPublisher

    def deliver(publication):
        nonlocal delivery_depth, max_delivery_depth
        delivery_depth += 1
        max_delivery_depth = max(max_delivery_depth, delivery_depth)
        try:
            delivered_revisions.append(publication.revision)
            if publication.revision == first.revision:
                nested_results.append(publisher.publish(second))
            return ObserverDeliveryStatus.DEFERRED
        finally:
            delivery_depth -= 1

    publisher = ApplicationViewEventPublisher(
        initial_revision=initial.revision,
        deliver=deliver,
    )

    assert publisher.publish(first) is False

    assert nested_results == [True]
    assert delivered_revisions == [first.revision, second.revision]
    assert max_delivery_depth == 1
    assert publisher.has_delivered_revision(first.revision) is False
    assert publisher.acknowledge(first.revision) is True
    assert publisher.has_delivered_revision(first.revision) is True
    assert publisher.has_delivered_revision(second.revision) is False
    assert publisher.acknowledge(second.revision) is True
    assert publisher.publish(second) is True
    assert delivered_revisions == [first.revision, second.revision]


def test_owned_reentrant_publication_drains_after_synchronous_acknowledgement() -> None:
    state = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(state, TrainingReadBoundary.no_trainer())
    initial = store.read()
    first = store.publish(
        replace(state, pipeline_stage="data_loaded"),
        TrainingReadBoundary.no_trainer(),
    )
    second = store.publish(
        replace(state, pipeline_stage="preprocessed"),
        TrainingReadBoundary.no_trainer(),
    )
    acknowledgement_owner = object()
    delivered_revisions: list[int] = []
    acknowledged_revisions: list[int] = []
    nested_results: list[bool] = []
    delivery_depth = 0
    max_delivery_depth = 0
    publisher: ApplicationViewEventPublisher

    def deliver(publication):
        nonlocal delivery_depth, max_delivery_depth
        delivery_depth += 1
        max_delivery_depth = max(max_delivery_depth, delivery_depth)
        try:
            delivered_revisions.append(publication.revision)
            if publication.revision == first.revision:
                nested_results.append(publisher.publish(second))
            acknowledged_revisions.append(publication.revision)
            assert (
                publisher.acknowledge(
                    publication.revision,
                    owner=acknowledgement_owner,
                )
                is True
            )
            return ObserverDeliveryStatus.DELIVERED
        finally:
            delivery_depth -= 1

    publisher = ApplicationViewEventPublisher(
        initial_revision=initial.revision,
        deliver=deliver,
    )
    publisher.require_acknowledging_subscriber(acknowledgement_owner)

    assert publisher.publish(first) is True

    assert nested_results == [True]
    assert delivered_revisions == [first.revision, second.revision]
    assert acknowledged_revisions == [first.revision, second.revision]
    assert max_delivery_depth == 1
    assert publisher.has_delivered_revision(second.revision) is True
    assert publisher.publish(second) is True
    assert delivered_revisions == [first.revision, second.revision]
