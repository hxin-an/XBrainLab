"""Tests for AgentWorker timeout mechanism."""

from threading import Event, Lock
from unittest.mock import MagicMock, patch

from XBrainLab.llm.agent.worker import AgentWorker
from XBrainLab.llm.core.config import LLMConfig


class TestAgentWorkerTimeout:
    """Test suite for Agent timeout protection."""

    def test_timeout_timer_created_on_generation(self):
        """Verify timeout timer is created during generation."""
        worker = AgentWorker()
        worker.engine = MagicMock()
        worker.engine.config.timeout = 30  # 30 seconds

        # Mock GenerationThread to prevent actual execution
        # Also mock LLMConfig.load_from_file so it doesn't overwrite our engine.config.timeout
        with (
            patch("XBrainLab.llm.agent.worker.GenerationThread") as MockThread,
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file", return_value=None
            ),
        ):
            mock_thread = MockThread.return_value
            mock_thread.start = MagicMock()

            worker.generate_from_messages([{"role": "user", "content": "hi"}])

            # Verify timer was created and configured
            assert worker.timeout_timer is not None, "Timeout timer should be created"
            # Note: isActive() returns False in test env without QEventLoop
            # We verify configuration instead
            assert worker.timeout_timer.interval() == 30000, (
                f"Expected 30s, got {worker.timeout_timer.interval()}ms"
            )

    def test_on_timeout_sets_flag_and_emits_error(self):
        """Verify timeout handler sets flag and emits error."""
        worker = AgentWorker()
        worker.engine = MagicMock()

        # Setup mock signals
        worker.error = MagicMock()
        worker.finished = MagicMock()

        # Setup mock thread
        mock_thread = MagicMock()
        mock_thread.isRunning.return_value = True
        worker.generation_thread = mock_thread
        worker._is_timed_out = False

        # Trigger timeout
        worker._on_timeout()

        # Verify flag set
        assert worker._is_timed_out, "Timeout flag should be set"

        # Verify signals emitted
        worker.error.emit.assert_called_once()
        worker.finished.emit.assert_called_once_with([])

    def test_normal_completion_stops_timer(self):
        """Verify normal completion stops the timeout timer."""
        worker = AgentWorker()
        worker.engine = MagicMock()

        # Setup mocks
        worker.finished = MagicMock()
        worker.timeout_timer = MagicMock()
        worker._is_timed_out = False

        worker._on_generation_finished()

        # Verify timer stopped
        worker.timeout_timer.stop.assert_called_once()
        worker.finished.emit.assert_called_with([])

    def test_timeout_retry_never_overlaps_live_generation(self, qtbot):
        started = Event()
        release = Event()

        class BlockingEngine:
            def __init__(self) -> None:
                self.config = LLMConfig()
                self.config.timeout = 60
                self.config.available_local_model_id = MagicMock(
                    return_value=(
                        self.config.model_name,
                        "Local runtime ready.",
                    ),
                )
                self.calls = 0
                self.active = 0
                self.max_active = 0
                self.lock = Lock()

            def generate_stream(self, _messages):
                with self.lock:
                    self.calls += 1
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                started.set()
                release.wait(timeout=2)
                try:
                    yield "done"
                finally:
                    with self.lock:
                        self.active -= 1

            def cancel_generation(self, *, wait_timeout: float) -> bool:
                del wait_timeout
                return False

        worker = AgentWorker()
        engine = BlockingEngine()
        worker.engine = engine
        errors: list[str] = []
        worker.error.connect(errors.append)
        messages = [{"role": "user", "content": "run"}]
        with patch(
            "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
            return_value=engine.config,
        ):
            worker.generate_from_messages(messages)
            qtbot.waitUntil(started.is_set, timeout=1000)
            active_thread = worker.generation_thread

            worker._on_timeout()
            worker.generate_from_messages(messages)

            assert worker.generation_thread is active_thread
            assert engine.calls == 1
            assert engine.max_active == 1
            assert any("still stopping" in message.lower() for message in errors)
            release.set()
            qtbot.waitUntil(lambda: worker.generation_thread is None, timeout=2000)

        if worker.timeout_timer is not None:
            worker.timeout_timer.stop()
