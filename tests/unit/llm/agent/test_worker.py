from unittest.mock import MagicMock, patch

from XBrainLab.llm.agent.worker import AgentWorker


class TestAgentWorker:
    def test_generate_from_messages_starts_thread(self):
        """
        Verify that generate_from_messages creates and starts the GenerationThread.
        This prevents the bug where the thread was never started (causing UI hang).
        """
        worker = AgentWorker()
        worker.engine = MagicMock()  # Mock engine

        start_mock = MagicMock()
        mock_thread_instance = MagicMock()
        mock_thread_instance.start = start_mock

        # We need to simulate the signals on the mock thread object so .connect works
        mock_thread_instance.chunk_received.connect = MagicMock()
        mock_thread_instance.finished_generation.connect = MagicMock()
        mock_thread_instance.error_occurred.connect = MagicMock()

        with patch(
            "XBrainLab.llm.agent.worker.GenerationThread",
            return_value=mock_thread_instance,
        ) as MockThreadClass:
            messages = [{"role": "user", "content": "Hello"}]
            worker.generate_from_messages(messages)

            # Verify Thread Instantiation
            MockThreadClass.assert_called_once_with(worker.engine, messages)

            # Verify Signals Connected
            mock_thread_instance.chunk_received.connect.assert_called_once()
            mock_thread_instance.finished_generation.connect.assert_called_once()
            mock_thread_instance.error_occurred.connect.assert_called_once()

            # CRITICAL: Verify Start Called
            start_mock.assert_called_once()
