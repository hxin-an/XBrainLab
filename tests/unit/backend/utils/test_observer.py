"""Unit tests for Observable (Observer pattern)."""

import pytest

from XBrainLab.backend.utils.observer import Observable, ObserverDeliveryStatus


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
        obs.unsubscribe("no_such_event", lambda: None)
        assert obs._observers == {}

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
        obs.notify("no_event")
        assert obs._pending_events == {}

    def test_notify_multiple_subscribers(self, obs):
        calls = []
        obs.subscribe("evt", lambda: calls.append("a"))
        obs.subscribe("evt", lambda: calls.append("b"))
        obs.notify("evt")
        assert calls == ["a", "b"]

    def test_notify_delivery_preserves_deferred_consumer_result(self, obs):
        obs.subscribe("evt", lambda: ObserverDeliveryStatus.DEFERRED)
        obs.subscribe("evt", lambda: None)

        assert obs.notify_delivery("evt") is ObserverDeliveryStatus.DEFERRED

    def test_notify_delivery_fails_when_any_consumer_rejects(self, obs):
        obs.subscribe("evt", lambda: ObserverDeliveryStatus.DEFERRED)
        obs.subscribe("evt", lambda: False)

        assert obs.notify_delivery("evt") is ObserverDeliveryStatus.FAILED

    def test_notify_delivery_does_not_acknowledge_zero_subscribers(self, obs):
        assert obs.notify_delivery("evt") is ObserverDeliveryStatus.NO_SUBSCRIBERS

    def test_notify_delivery_requires_an_explicit_acknowledgement(self, obs):
        obs.subscribe("evt", lambda: None)

        assert obs.notify_delivery("evt") is ObserverDeliveryStatus.UNACKNOWLEDGED

    def test_notify_delivery_keeps_deferred_owner_pending_despite_other_ack(self, obs):
        obs.subscribe("evt", lambda: None)
        obs.subscribe("evt", lambda: ObserverDeliveryStatus.DEFERRED)
        obs.subscribe("evt", lambda: True)

        assert obs.notify_delivery("evt") is ObserverDeliveryStatus.DEFERRED


class TestSafeCall:
    def test_error_in_subscriber_does_not_propagate(self, obs):
        def bad_callback():
            raise RuntimeError("boom")

        received = []
        logged = []
        obs.subscribe("evt", bad_callback)
        obs.subscribe("evt", lambda: received.append("ok"))
        with pytest.MonkeyPatch.context() as monkeypatch:

            def error(*args, **_kwargs):
                logged.append(args[0])

            monkeypatch.setattr(
                "XBrainLab.backend.utils.observer.logger.error",
                error,
            )
            obs.notify("evt")

        assert logged == ["Error in subscriber for %s: %s"]
        assert received == ["ok"]
