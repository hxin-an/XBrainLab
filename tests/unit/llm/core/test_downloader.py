import multiprocessing
from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.core.downloader import ModelDownloader


# Mock multiprocessing.Process AND Queue
@pytest.fixture
def mock_multiprocessing():
    with patch("XBrainLab.llm.core.downloader.multiprocessing") as mock_mp:
        # Create a real queue for tests to simulate messages
        # But we need to patch Queue constructor to return our mock that wraps real queue?
        # Simpler: Let's mock Process, but use real Queue if possible,
        # OR mock Queue behavior completely.

        # Strategy: Mock Process.start() and Process.terminate().
        # Mock Queue to allow us to inject messages.

        mock_process = MagicMock()
        mock_process.is_alive.return_value = True
        mock_mp.Process.return_value = mock_process

        # We Mock Queue so we can inject values into it for the worker to read
        mock_queue = MagicMock()
        mock_queue.get_nowait.side_effect = list

        mock_mp.Queue.return_value = mock_queue

        yield mock_mp, mock_process, mock_queue


class TestModelDownloader:
    def test_download_success(self, mock_multiprocessing, qtbot):
        """Test successful download signal emission via queue."""
        mock_mp, mock_process, mock_queue = mock_multiprocessing

        # Setup Queue to return progress then finish
        # worker calls get_nowait().
        # We need side_effect to pop items.

        messages = [("progress", (50, "Halfway")), ("finished", "/path/to/model")]

        # Dynamic side effect for get_nowait
        def get_msg():
            if messages:
                return messages.pop(0)
            raise multiprocessing.queues.Empty

        mock_queue.get_nowait.side_effect = get_msg

        downloader = ModelDownloader()

        with qtbot.waitSignal(downloader.finished, timeout=1000) as blocker:
            downloader.start_download("repo/id", "/cache")

        assert blocker.args == ["/path/to/model"]
        mock_mp.Process.assert_called_once()
        mock_process.start.assert_called_once()

    def test_download_failure(self, mock_multiprocessing, qtbot):
        """Test failure signal emission."""
        _, _, mock_queue = mock_multiprocessing

        messages = [("error", "Network Error")]

        def get_msg():
            if messages:
                return messages.pop(0)
            raise multiprocessing.queues.Empty

        mock_queue.get_nowait.side_effect = get_msg

        downloader = ModelDownloader()

        with qtbot.waitSignal(downloader.failed, timeout=1000) as blocker:
            downloader.start_download("repo/id", "/cache")

        assert "Network Error" in blocker.args[0]

    def test_cancellation(self, mock_multiprocessing, qtbot):
        """Test that cancel() calls process.terminate()."""
        _, mock_process, mock_queue = mock_multiprocessing

        # Queue always empty -> worker keeps running until cancel
        mock_queue.get_nowait.side_effect = multiprocessing.queues.Empty

        downloader = ModelDownloader()
        downloader.start_download("repo/id", "/cache")

        # Wait for thread to start and mock process to be created
        qtbot.wait(100)

        with qtbot.waitSignal(downloader.failed, timeout=1000) as blocker:
            downloader.cancel_download()

        assert "Cancelled by user" in blocker.args[0]
        mock_process.terminate.assert_called_once()
        mock_process.join.assert_called_once()
