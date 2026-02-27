import multiprocessing
import queue as stdlib_queue
import time
from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.core.downloader import (
    DownloadWorker,
    ModelDownloader,
    run_download_task,
)


def _drain_queue(q, timeout=2.0, poll=0.05):
    """Drain all items from a multiprocessing.Queue with timeout.

    On Windows, the feeder thread may not have flushed yet when
    ``get_nowait`` is called immediately after ``put``.
    """
    messages = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            messages.append(q.get_nowait())
        except Exception:  # noqa: PERF203
            if messages:
                # Got at least one; try once more after short sleep
                time.sleep(poll)
                try:
                    messages.append(q.get_nowait())
                except Exception:
                    break
            else:
                time.sleep(poll)
    return messages


# Mock multiprocessing.Process AND Queue
@pytest.fixture
def mock_multiprocessing():
    with patch("XBrainLab.llm.core.downloader.multiprocessing") as mock_mp:
        mock_process = MagicMock()
        mock_process.is_alive.return_value = True
        mock_mp.Process.return_value = mock_process

        mock_queue = MagicMock()
        mock_queue.get_nowait.side_effect = list

        mock_mp.Queue.return_value = mock_queue

        yield mock_mp, mock_process, mock_queue


class TestModelDownloader:
    def test_download_success(self, mock_multiprocessing, qtbot):
        """Test successful download signal emission via queue."""
        mock_mp, mock_process, mock_queue = mock_multiprocessing

        messages = [("progress", (50, "Halfway")), ("finished", "/path/to/model")]

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

        mock_queue.get_nowait.side_effect = multiprocessing.queues.Empty

        downloader = ModelDownloader()
        downloader.start_download("repo/id", "/cache")

        qtbot.wait(100)

        with qtbot.waitSignal(downloader.failed, timeout=1000) as blocker:
            downloader.cancel_download()

        assert "Cancelled by user" in blocker.args[0]
        mock_process.terminate.assert_called_once()
        mock_process.join.assert_called_once()

    def test_start_download_ignores_if_running(self, mock_multiprocessing, qtbot):
        """If a download thread is already running, start_download is a no-op."""
        _, _, mock_queue = mock_multiprocessing
        messages = [("finished", "/path")]

        def get_msg():
            if messages:
                return messages.pop(0)
            raise multiprocessing.queues.Empty

        mock_queue.get_nowait.side_effect = get_msg

        downloader = ModelDownloader()
        downloader.start_download("repo/id", "/cache")
        qtbot.wait(200)
        # Try to start again while thread may still be alive
        downloader.start_download("repo/other", "/cache")
        # Should not crash

    def test_start_download_deleted_thread_recovery(self, qtbot):
        """If previous thread's C++ object was deleted, treat as not-running."""
        downloader = ModelDownloader()
        # Simulate a deleted C++ thread object
        mock_thread = MagicMock()
        mock_thread.isRunning.side_effect = RuntimeError(
            "Wrapped C++ object has been deleted"
        )
        downloader._thread = mock_thread
        # Should recover and start fresh
        with patch("XBrainLab.llm.core.downloader.QThread") as mock_qt:
            mock_qt_inst = MagicMock()
            mock_qt.return_value = mock_qt_inst
            with patch("XBrainLab.llm.core.downloader.DownloadWorker"):
                downloader.start_download("repo/id", "/cache")
        assert downloader._thread is mock_qt_inst

    def test_on_finished_clears_thread(self):
        downloader = ModelDownloader()
        downloader._thread = MagicMock()
        downloader._on_finished("/some/path")
        assert downloader._thread is None

    def test_cancel_no_worker(self):
        """cancel_download when no worker should not raise."""
        downloader = ModelDownloader()
        downloader.cancel_download()  # no crash


class TestRunDownloadTask:
    def test_success(self):
        q = multiprocessing.Queue()
        with patch(
            "XBrainLab.llm.core.downloader.snapshot_download",
            return_value="/model/path",
        ):
            run_download_task("repo/id", "/cache", q)

        messages = _drain_queue(q)

        types = [m[0] for m in messages]
        assert "progress" in types
        assert "finished" in types
        assert messages[-1] == ("finished", "/model/path")

    def test_missing_library(self):
        q = multiprocessing.Queue()
        import XBrainLab.llm.core.downloader as _dl_mod

        original = _dl_mod.snapshot_download
        try:
            _dl_mod.snapshot_download = None  # type: ignore[assignment]
            run_download_task("repo/id", "/cache", q)
        finally:
            _dl_mod.snapshot_download = original

        messages = _drain_queue(q)
        assert len(messages) == 1
        assert messages[0][0] == "error"
        assert "Missing" in messages[0][1]

    def test_exception_during_download(self):
        q = multiprocessing.Queue()
        with patch(
            "XBrainLab.llm.core.downloader.snapshot_download",
            side_effect=OSError("disk full"),
        ):
            run_download_task("repo/id", "/cache", q)

        messages = _drain_queue(q)
        # Should have progress then error
        errors = [m for m in messages if m[0] == "error"]
        assert len(errors) == 1
        assert "disk full" in errors[0][1]


class TestDownloadWorker:
    def test_check_queue_empty(self):
        worker = DownloadWorker.__new__(DownloadWorker)
        worker._queue = MagicMock()
        worker._queue.get_nowait.side_effect = stdlib_queue.Empty
        assert worker._check_queue() is False

    def test_check_queue_progress(self):
        worker = DownloadWorker.__new__(DownloadWorker)
        worker._queue = MagicMock()
        worker.progress_update = MagicMock()
        items = [("progress", (50, "half"))]

        def side_effect():
            if items:
                return items.pop(0)
            raise stdlib_queue.Empty

        worker._queue.get_nowait.side_effect = side_effect
        assert worker._check_queue() is False
        worker.progress_update.emit.assert_called_once_with(50, "half")

    def test_check_queue_finished(self):
        worker = DownloadWorker.__new__(DownloadWorker)
        worker._queue = MagicMock()
        worker.download_finished = MagicMock()
        items = [("finished", "/path")]

        def side_effect():
            if items:
                return items.pop(0)
            raise stdlib_queue.Empty

        worker._queue.get_nowait.side_effect = side_effect
        assert worker._check_queue() is True
        worker.download_finished.emit.assert_called_once_with("/path")

    def test_check_queue_error(self):
        worker = DownloadWorker.__new__(DownloadWorker)
        worker._queue = MagicMock()
        worker.download_failed = MagicMock()
        items = [("error", "boom")]

        def side_effect():
            if items:
                return items.pop(0)
            raise stdlib_queue.Empty

        worker._queue.get_nowait.side_effect = side_effect
        assert worker._check_queue() is True
        worker.download_failed.emit.assert_called_once_with("boom")

    def test_check_queue_none(self):
        worker = DownloadWorker.__new__(DownloadWorker)
        worker._queue = None
        assert worker._check_queue() is False

    def test_terminate_process_alive(self):
        worker = DownloadWorker.__new__(DownloadWorker)
        worker._process = MagicMock()
        worker._process.is_alive.return_value = True
        worker._terminate_process()
        worker._process.terminate.assert_called_once()
        worker._process.join.assert_called_once()

    def test_terminate_process_not_alive(self):
        worker = DownloadWorker.__new__(DownloadWorker)
        worker._process = MagicMock()
        worker._process.is_alive.return_value = False
        worker._terminate_process()
        worker._process.terminate.assert_not_called()

    def test_cancel_sets_flag(self):
        worker = DownloadWorker.__new__(DownloadWorker)
        worker._is_cancelled = False
        worker.cancel()
        assert worker._is_cancelled is True
