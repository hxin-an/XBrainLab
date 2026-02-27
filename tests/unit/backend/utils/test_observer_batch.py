"""Unit tests for Observable.batch_notifications context manager."""

import pytest

from XBrainLab.backend.utils.observer import Observable


@pytest.fixture
def obs():
    return Observable()


class TestBatchNotifications:
    def test_defers_notifications(self, obs):
        calls = []
        obs.subscribe("evt", lambda: calls.append("fired"))

        with obs.batch_notifications():
            obs.notify("evt")
            obs.notify("evt")
            obs.notify("evt")
            assert calls == [], "Should not fire during batch"

        assert calls == ["fired"], "Should fire exactly once after batch"

    def test_deduplicates_events(self, obs):
        calls = []
        obs.subscribe("a", lambda: calls.append("a"))
        obs.subscribe("b", lambda: calls.append("b"))

        with obs.batch_notifications():
            obs.notify("a")
            obs.notify("b")
            obs.notify("a")  # duplicate

        assert calls.count("a") == 1
        assert calls.count("b") == 1

    def test_keeps_last_args(self, obs):
        received = []
        obs.subscribe("evt", lambda val: received.append(val))

        with obs.batch_notifications():
            obs.notify("evt", 1)
            obs.notify("evt", 2)
            obs.notify("evt", 3)

        assert received == [3], "Should keep last notified args"

    def test_nested_batch(self, obs):
        calls = []
        obs.subscribe("evt", lambda: calls.append("fired"))

        with obs.batch_notifications():
            obs.notify("evt")
            with obs.batch_notifications():
                obs.notify("evt")
                assert calls == [], "Should not fire in nested batch"
            assert calls == [], "Should not fire until outermost exits"

        assert calls == ["fired"], "Should fire exactly once"

    def test_normal_notify_outside_batch(self, obs):
        """Verify notify still works normally outside batch."""
        calls = []
        obs.subscribe("evt", lambda: calls.append("fired"))

        obs.notify("evt")
        assert calls == ["fired"]

    def test_error_in_batch_still_flushes(self, obs):
        calls = []
        obs.subscribe("evt", lambda: calls.append("fired"))

        with pytest.raises(ValueError, match="boom"), obs.batch_notifications():
            obs.notify("evt")
            raise ValueError("boom")

        # batch_notifications should still flush pending events
        assert calls == ["fired"]

    def test_batch_depth_reset_after_error(self, obs):
        """Ensure batch depth returns to 0 after exception."""
        with pytest.raises(RuntimeError), obs.batch_notifications():
            raise RuntimeError("err")

        assert obs._batch_depth == 0

        # Normal notifications should work
        calls = []
        obs.subscribe("x", lambda: calls.append("ok"))
        obs.notify("x")
        assert calls == ["ok"]
