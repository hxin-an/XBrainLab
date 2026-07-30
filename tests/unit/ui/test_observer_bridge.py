import gc
from dataclasses import replace
from inspect import getsource
from threading import Thread, current_thread
from unittest.mock import MagicMock
from weakref import ref

from PyQt6 import sip
from PyQt6.QtCore import QObject

from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.view_event_publisher import (
    ApplicationViewEventPublisher,
)
from XBrainLab.backend.application.view_publication import ApplicationViewStore
from XBrainLab.backend.training_state_contract import TrainingReadBoundary
from XBrainLab.backend.utils.observer import Observable, ObserverDeliveryStatus
from XBrainLab.ui.core.observer_bridge import QtObserverBridge


class MockObservable(Observable):
    pass


def test_observer_bridge_has_no_blocking_queued_connection() -> None:
    assert "BlockingQueuedConnection" not in getsource(QtObserverBridge)


def test_observer_bridge_emission(qtbot):
    """
    Test that QtObserverBridge correctly connects to an Observable
    and emits a Qt signal when the Observable notifies.
    """
    observable = MockObservable()
    bridge = QtObserverBridge(observable, "test_event")

    # Mock slot to verify signal emission
    mock_slot = MagicMock()
    bridge.triggered.connect(lambda args, kwargs: mock_slot(*args, **kwargs))

    # Trigger event
    observable.notify("test_event", "arg1", key="value")

    # Process events
    qtbot.wait(50)

    # Verify slot was called with correct args
    mock_slot.assert_called_once()
    args, kwargs = mock_slot.call_args
    assert args[0] == "arg1"
    assert kwargs["key"] == "value"


def test_observer_bridge_connect_to(qtbot):
    """Test the connect_to helper method."""
    observable = MockObservable()
    bridge = QtObserverBridge(observable, "test_event")

    received_args = []

    def my_slot(*args, **kwargs):
        received_args.append((args, kwargs))

    bridge.connect_to(my_slot)

    observable.notify("test_event", 123)

    qtbot.wait(50)

    assert len(received_args) == 1
    assert received_args[0][0] == (123,)


def test_publication_delivery_retries_same_revision_after_qt_render_failure(qtbot):
    observable = MockObservable()
    bridge = QtObserverBridge(
        observable,
        "view_publication_changed",
        require_slot_acknowledgement=True,
    )
    state = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(state, TrainingReadBoundary.no_trainer())
    initial = store.read()
    publication = store.publish(
        replace(state, pipeline_stage="data_loaded"),
        TrainingReadBoundary.no_trainer(),
    )
    attempts: list[int] = []

    def render(candidate) -> bool:
        attempts.append(candidate.revision)
        if len(attempts) == 1:
            raise RuntimeError("transient render failure")
        return True

    bridge.connect_to(render)
    publisher = ApplicationViewEventPublisher(
        initial_revision=initial.revision,
        deliver=lambda candidate: observable.notify_delivery(
            "view_publication_changed",
            candidate,
        ),
    )

    assert publisher.publish(publication) is False
    assert publisher.publish(publication) is True
    qtbot.wait(20)

    assert attempts == [publication.revision, publication.revision]


def test_background_publication_is_acknowledged_only_after_qt_render(qtbot):
    observable = MockObservable()
    bridge = QtObserverBridge(
        observable,
        "view_publication_changed",
        require_slot_acknowledgement=True,
    )
    state = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(state, TrainingReadBoundary.no_trainer())
    initial = store.read()
    publication = store.publish(
        replace(state, pipeline_stage="data_loaded"),
        TrainingReadBoundary.no_trainer(),
    )
    attempts: list[int] = []
    publisher: ApplicationViewEventPublisher

    def render(candidate) -> bool:
        attempts.append(candidate.revision)
        publisher.acknowledge(candidate.revision)
        return True

    bridge.connect_to(render)
    publisher = ApplicationViewEventPublisher(
        initial_revision=initial.revision,
        deliver=lambda candidate: observable.notify_delivery(
            "view_publication_changed",
            candidate,
        ),
    )
    results: list[bool] = []
    worker = Thread(target=lambda: results.append(publisher.publish(publication)))

    worker.start()
    worker.join(timeout=1.0)

    assert worker.is_alive() is False
    assert results == [False]
    qtbot.waitUntil(lambda: attempts == [publication.revision], timeout=1_000)
    assert publisher.publish(publication) is True
    assert attempts == [publication.revision]


def test_background_publication_without_render_consumer_stays_unacknowledged(qtbot):
    observable = MockObservable()
    bridge = QtObserverBridge(
        observable,
        "view_publication_changed",
        require_slot_acknowledgement=True,
    )
    state = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(state, TrainingReadBoundary.no_trainer())
    initial = store.read()
    publication = store.publish(
        replace(state, pipeline_stage="data_loaded"),
        TrainingReadBoundary.no_trainer(),
    )
    publisher = ApplicationViewEventPublisher(
        initial_revision=initial.revision,
        deliver=lambda candidate: observable.notify_delivery(
            "view_publication_changed",
            candidate,
        ),
    )
    results: list[bool] = []
    worker = Thread(target=lambda: results.append(publisher.publish(publication)))

    worker.start()
    worker.join(timeout=1.0)

    assert worker.is_alive() is False
    assert results == [False]
    qtbot.wait(20)
    assert publisher.has_delivered_revision(publication.revision) is False
    assert publisher.publish(publication) is False
    bridge.cleanup()


def test_acknowledgement_bridge_rejects_missing_or_false_slot_result() -> None:
    observable = MockObservable()
    bridge = QtObserverBridge(
        observable,
        "view_publication_changed",
        require_slot_acknowledgement=True,
    )

    assert (
        observable.notify_delivery("view_publication_changed", object())
        is ObserverDeliveryStatus.FAILED
    )

    bridge.connect_to(lambda _publication: False)

    assert (
        observable.notify_delivery("view_publication_changed", object())
        is ObserverDeliveryStatus.FAILED
    )


def test_acknowledgement_bridge_accepts_only_explicit_true_slot_result() -> None:
    observable = MockObservable()
    bridge = QtObserverBridge(
        observable,
        "view_publication_changed",
        require_slot_acknowledgement=True,
    )
    bridge.connect_to(lambda _publication: True)

    assert (
        observable.notify_delivery("view_publication_changed", object())
        is ObserverDeliveryStatus.DELIVERED
    )


def test_observer_bridge_connect_to_dispatches_background_event_on_qt_thread(qtbot):
    observable = MockObservable()
    bridge = QtObserverBridge(observable, "test_event")
    received = []
    gui_thread = current_thread()
    bridge.connect_to(
        lambda value: received.append((value, current_thread())),
    )

    worker = Thread(target=lambda: observable.notify("test_event", "committed"))
    worker.start()
    worker.join(timeout=1.0)

    assert worker.is_alive() is False
    qtbot.waitUntil(lambda: len(received) == 1, timeout=1_000)
    assert received == [("committed", gui_thread)]


def test_observer_bridge_cleanup():
    """Test that cleanup unsubscribes from the observable."""
    observable = MockObservable()
    bridge = QtObserverBridge(observable, "test_event")

    assert "test_event" in observable._observers
    assert len(observable._observers["test_event"]) == 1

    bridge.cleanup()

    assert len(observable._observers["test_event"]) == 0


def test_observer_bridge_cleanup_ignores_late_backend_events(qtbot):
    observable = MockObservable()
    bridge = QtObserverBridge(observable, "test_event")
    slot = MagicMock()
    bridge.connect_to(slot)

    bridge.cleanup()
    bridge._on_event("late")
    qtbot.wait(50)

    slot.assert_not_called()


def test_observer_bridge_cleanup_and_qobject_destruction_unsubscribe_once(qtbot):
    observable = MockObservable()
    observable.unsubscribe = MagicMock(wraps=observable.unsubscribe)
    bridge = QtObserverBridge(observable, "test_event")

    bridge.cleanup()
    bridge.deleteLater()
    qtbot.waitUntil(
        lambda target=bridge: sip.isdeleted(target),
        timeout=1_000,
    )
    del bridge
    gc.collect()

    observable.unsubscribe.assert_called_once()


def test_observer_bridge_deleted_object_ignores_late_backend_events(qtbot):
    observable = MockObservable()
    bridge = QtObserverBridge(observable, "test_event")
    slot = MagicMock()
    bridge.connect_to(slot)

    bridge.deleteLater()
    qtbot.waitUntil(lambda: sip.isdeleted(bridge), timeout=1_000)
    bridge._on_event("late")
    qtbot.wait(50)

    slot.assert_not_called()


def test_observer_bridge_parent_destruction_unsubscribes_and_releases_bridge(
    qtbot,
):
    observable = MockObservable()
    parent = QObject()
    bridge = QtObserverBridge(observable, "test_event", parent)
    bridge_ref = ref(bridge)

    assert len(observable._observers["test_event"]) == 1

    parent.deleteLater()
    qtbot.waitUntil(
        lambda target=parent: sip.isdeleted(target),
        timeout=1_000,
    )
    del bridge
    del parent
    gc.collect()

    qtbot.waitUntil(
        lambda: len(observable._observers["test_event"]) == 0,
        timeout=1_000,
    )
    qtbot.waitUntil(lambda: bridge_ref() is None, timeout=1_000)


def test_observer_bridge_parent_destruction_unsubscribes_with_live_wrapper(
    qtbot,
):
    observable = MockObservable()
    observable.unsubscribe = MagicMock(wraps=observable.unsubscribe)
    parent = QObject()
    bridge = QtObserverBridge(observable, "test_event", parent)

    parent.deleteLater()
    qtbot.waitUntil(lambda: sip.isdeleted(bridge), timeout=1_000)

    observable.unsubscribe.assert_called_once()
    assert observable._observers["test_event"] == []


def test_parent_destruction_does_not_run_weakref_finalizer_inside_qt_teardown(
    qtbot,
):
    observable = MockObservable()
    parent = QObject()
    bridge = QtObserverBridge(observable, "test_event", parent)
    finalizer = bridge._observer_finalizer

    parent.deleteLater()
    qtbot.waitUntil(lambda: sip.isdeleted(bridge), timeout=1_000)

    assert observable._observers["test_event"] == []
    assert finalizer.alive is True

    bridge.cleanup()
    assert finalizer.alive is False
