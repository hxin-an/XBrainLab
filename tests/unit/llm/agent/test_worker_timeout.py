"""Tests for AgentWorker timeout mechanism."""

from unittest.mock import MagicMock, patch

from XBrainLab.llm.agent.worker import AgentWorker


class TestAgentWorkerTimeout:
    """Test suite for Agent timeout protection."""

    def test_timeout_timer_created_on_generation(self):
        """Verify timeout timer is created during generation."""
        worker = AgentWorker()
        worker.engine = MagicMock()
        worker.engine.config.timeout = 30  # 30 seconds

        # Mock GenerationThread to prevent actual execution
        with patch("XBrainLab.llm.agent.worker.GenerationThread") as MockThread:
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
