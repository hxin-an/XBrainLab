"""Unit tests for Observable (Observer pattern)."""

import pytest

from XBrainLab.backend.utils.observer import Observable


@pytest.fixture
def obs():
    return Observable()


class TestSubscribe:
    def test_subscribe_adds_callback(self, obs):
        cb = lambda: None  # noqa: E731
        obs.subscribe("evt", cb)
        assert cb in obs._observers["evt"]

    def test_subscribe_no_duplicates(self, obs):
        cb = lambda: None  # noqa: E731
        obs.subscribe("evt", cb)
        obs.subscribe("evt", cb)
        assert len(obs._observers["evt"]) == 1

    def test_subscribe_multiple_events(self, obs):
        cb1 = lambda: None  # noqa: E731
        cb2 = lambda: None  # noqa: E731
        obs.subscribe("a", cb1)
        obs.subscribe("b", cb2)
        assert "a" in obs._observers
        assert "b" in obs._observers


class TestUnsubscribe:
    def test_unsubscribe_removes_callback(self, obs):
        cb = lambda: None  # noqa: E731
        obs.subscribe("evt", cb)
        obs.unsubscribe("evt", cb)
        assert cb not in obs._observers["evt"]

    def test_unsubscribe_nonexistent_event(self, obs):
        # Should not raise
        obs.unsubscribe("no_such_event", lambda: None)

    def test_unsubscribe_nonexistent_callback(self, obs):
        obs.subscribe("evt", lambda: None)
        obs.unsubscribe("evt", lambda x: x)  # different callback


class TestNotify:
    def test_notify_calls_subscribers(self, obs):
        received = []
        obs.subscribe("evt", lambda *a, **k: received.append((a, k)))
        obs.notify("evt", 1, 2, key="val")
        assert len(received) == 1
        assert received[0] == ((1, 2), {"key": "val"})

    def test_notify_no_subscribers(self, obs):
        # Should not raise
        obs.notify("no_event")

    def test_notify_multiple_subscribers(self, obs):
        calls = []
        obs.subscribe("evt", lambda: calls.append("a"))
        obs.subscribe("evt", lambda: calls.append("b"))
        obs.notify("evt")
        assert calls == ["a", "b"]


class TestSafeCall:
    def test_error_in_subscriber_does_not_propagate(self, obs):
        def bad_callback():
            raise RuntimeError("boom")

        received = []
        obs.subscribe("evt", bad_callback)
        obs.subscribe("evt", lambda: received.append("ok"))
        # Should not raise
        obs.notify("evt")
        assert received == ["ok"]
