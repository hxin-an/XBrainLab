"""Unit tests for Observable.batch_notifications context manager."""

from threading import Event, Thread

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

    def test_concurrent_batches_keep_independent_events_and_delivery_results(
        self,
        obs,
    ):
        """One command cannot join or consume another thread's notification batch."""
        first_entered = Event()
        release_first = Event()
        calls: list[str] = []
        generations: dict[str, int | None] = {}
        deliveries: dict[str, bool | None] = {}

        obs.subscribe("evt", calls.append)

        def run_first() -> None:
            with obs.batch_notifications():
                generations["first"] = obs.notification_batch_generation
                obs.notify("evt", "first")
                first_entered.set()
                assert release_first.wait(timeout=2.0)
            generation = generations["first"]
            assert generation is not None
            deliveries["first"] = obs.consume_batched_delivery("evt", generation)

        def run_second() -> None:
            assert first_entered.wait(timeout=2.0)
            with obs.batch_notifications():
                generations["second"] = obs.notification_batch_generation
                obs.notify("evt", "second")
            generation = generations["second"]
            assert generation is not None
            deliveries["second"] = obs.consume_batched_delivery("evt", generation)
            release_first.set()

        first = Thread(target=run_first, name="observer-first")
        second = Thread(target=run_second, name="observer-second")
        first.start()
        second.start()
        first.join(timeout=2.0)
        second.join(timeout=2.0)

        assert not first.is_alive()
        assert not second.is_alive()
        assert generations["first"] != generations["second"]
        assert calls == ["second", "first"]
        assert deliveries == {"second": True, "first": True}
