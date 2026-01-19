from unittest.mock import MagicMock

from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.utils.observer_bridge import QtObserverBridge


class MockObservable(Observable):
    pass


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


def test_observer_bridge_cleanup():
    """Test that cleanup unsubscribes from the observable."""
    observable = MockObservable()
    bridge = QtObserverBridge(observable, "test_event")

    assert "test_event" in observable._observers
    assert len(observable._observers["test_event"]) == 1

    bridge.cleanup()

    assert len(observable._observers["test_event"]) == 0
