"""Unit tests for EventBus — singleton and signals."""

import pytest

from XBrainLab.ui.core.event_bus import EventBus


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset EventBus singleton between tests."""
    EventBus._instance = None
    yield
    EventBus._instance = None


class TestEventBusSingleton:
    def test_get_instance_returns_eventbus(self):
        bus = EventBus.get_instance()
        assert isinstance(bus, EventBus)

    def test_get_instance_returns_same_object(self):
        bus1 = EventBus.get_instance()
        bus2 = EventBus.get_instance()
        assert bus1 is bus2

    def test_direct_init_after_singleton_raises(self):
        EventBus.get_instance()  # creates singleton
        with pytest.raises(RuntimeError, match="singleton"):
            EventBus()


class TestEventBusSignals:
    def test_status_message_signal(self, qtbot):
        bus = EventBus.get_instance()
        received = []
        bus.status_message.connect(lambda msg, dur: received.append((msg, dur)))
        bus.status_message.emit("hello", 3000)
        qtbot.wait(50)
        assert received == [("hello", 3000)]

    def test_error_occurred_signal(self, qtbot):
        bus = EventBus.get_instance()
        received = []
        bus.error_occurred.connect(received.append)
        bus.error_occurred.emit("oops")
        qtbot.wait(50)
        assert received == ["oops"]

    def test_data_refreshed_signal(self, qtbot):
        bus = EventBus.get_instance()
        received = []
        bus.data_refreshed.connect(lambda: received.append(True))
        bus.data_refreshed.emit()
        qtbot.wait(50)
        assert received == [True]

    def test_model_updated_signal(self, qtbot):
        bus = EventBus.get_instance()
        received = []
        bus.model_updated.connect(received.append)
        bus.model_updated.emit("EEGNet")
        qtbot.wait(50)
        assert received == ["EEGNet"]
