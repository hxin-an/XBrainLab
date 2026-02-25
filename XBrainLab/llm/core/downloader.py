"""Model downloader with process-based isolation.

Provides a multi-process download mechanism for HuggingFace models,
with Qt signal integration for progress reporting and cancellation.
"""

import multiprocessing
import os
import queue  # Standard library queue for Empty exception
import time

from PyQt6.QtCore import QObject, QThread, pyqtSignal

try:
    from huggingface_hub import snapshot_download
except ImportError:
    snapshot_download = None  # type: ignore[assignment]


# -----------------------------------------------------------------------------
# Standalone Process Function (Must be picklable)
# -----------------------------------------------------------------------------
def run_download_task(repo_id, cache_dir, result_queue):
    """Runs a HuggingFace model download in a separate process.

    This function must be picklable for ``multiprocessing.Process``.
    Progress and completion/error status are communicated via
    ``result_queue``.

    Args:
        repo_id: HuggingFace repository identifier (e.g.
            ``'Qwen/Qwen2.5-7B-Instruct'``).
        cache_dir: Local directory for storing downloaded model files.
        result_queue: A ``multiprocessing.Queue`` for sending status
            messages back to the parent process.  Messages are tuples
            of ``(msg_type, data)`` where *msg_type* is one of
            ``'progress'``, ``'finished'``, or ``'error'``.

    """
    if snapshot_download is None:
        result_queue.put(("error", "Missing library: huggingface_hub"))
        return

    try:
        # Disable HF Hub progress bars to prevent messy terminal output
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

        result_queue.put(("progress", (0, "Starting download...")))

        # This BLOCKS until done.
        model_path = snapshot_download(
            repo_id=repo_id,
            cache_dir=cache_dir,
            local_dir=os.path.join(cache_dir, repo_id.replace("/", "_")),
            resume_download=True,
        )

        result_queue.put(("progress", (100, "Download Complete")))
        result_queue.put(("finished", model_path))

    except Exception as e:
        result_queue.put(("error", str(e)))


class DownloadWorker(QObject):
    """Worker that manages a download subprocess from a QThread.

    Spawns a ``multiprocessing.Process`` to perform the actual download
    and polls a shared queue for progress, completion, or error messages.

    Attributes:
        progress_update: Signal emitting ``(percent, status_message)``.
        download_finished: Signal emitting the local model path on success.
        download_failed: Signal emitting an error message on failure.
        repo_id: HuggingFace repository identifier.
        cache_dir: Local cache directory for model files.

    """

    progress_update = pyqtSignal(int, str)  # progress (%), status message
    download_finished = pyqtSignal(str)  # path to model
    download_failed = pyqtSignal(str)  # error message

    def __init__(self, repo_id, cache_dir):
        """Initializes the DownloadWorker.

        Args:
            repo_id: HuggingFace repository identifier to download.
            cache_dir: Local directory for storing downloaded files.

        """
        super().__init__()
        self.repo_id = repo_id
        self.cache_dir = cache_dir
        self._is_cancelled = False
        self._process = None
        self._queue = None

    def run(self):
        """Starts the download subprocess and polls its status queue.

        Runs in a QThread context.  Monitors for cancellation, unexpected
        process death, and queue messages until the download completes or
        fails.
        """
        # Create Queue
        self._queue = multiprocessing.Queue()

        # Start Process
        self._process = multiprocessing.Process(
            target=run_download_task,
            args=(self.repo_id, self.cache_dir, self._queue),
            daemon=True,
        )
        self._process.start()

        # Monitor Loop
        while True:
            # Check cancellation first
            if self._is_cancelled:
                self._terminate_process()
                self.download_failed.emit("Cancelled by user")
                return

            # Check if process died unexpectedly
            if not self._process.is_alive():
                # Process finished, but we should have received a message.
                # Check queue one last time
                if not self._check_queue():
                    # If queue empty and process dead -> crashed/finished
                    pass
                break

            # Check queue (non-blocking)
            if self._check_queue():
                return  # Finished or Error happened

            # Sleep briefly to avoid busy loop
            # We are in a background QThread, so sleep is fine.
            time.sleep(0.1)

    def _check_queue(self):
        """Reads and processes messages from the download queue.

        Returns:
            ``True`` if the download finished or failed (terminal state),
            ``False`` if only progress updates were received.

        """
        try:
            # Get all available messages
            while True:
                if self._queue is None:
                    break
                msg_type, data = self._queue.get_nowait()

                if msg_type == "progress":
                    pct, msg = data
                    self.progress_update.emit(pct, msg)

                elif msg_type == "finished":
                    self.download_finished.emit(data)
                    return True

                elif msg_type == "error":
                    self.download_failed.emit(data)
                    return True

        except queue.Empty:
            pass

        return False

    def _terminate_process(self):
        """Terminates the download subprocess and waits for cleanup."""
        if self._process and self._process.is_alive():
            self._process.terminate()
            self._process.join()  # Cleanup

    def cancel(self):
        """Requests cancellation of the in-progress download.

        Sets the cancellation flag; the ``run`` loop will terminate the
        subprocess on its next iteration.
        """
        self._is_cancelled = True
        # The run loop will pick this up and terminate the process


# Global set to keep references to running threads, preventing them from being
# garbage collected (and crashing) if the parent ModelDownloader is destroyed.
ACTIVE_THREADS = set()


class ModelDownloader(QObject):
    """High-level manager for model downloads with Qt threading.

    Handles QThread lifecycle, signal wiring, and ensures only one
    download runs at a time.  Active threads are tracked globally to
    prevent premature garbage collection.

    Attributes:
        progress: Signal emitting ``(percent, status_message)``.
        finished: Signal emitting the downloaded model path.
        failed: Signal emitting an error message.
        worker: The active ``DownloadWorker``, if any.

    """

    # ... (signals same)
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self):
        """Initializes the ModelDownloader."""
        super().__init__()
        self.worker = None
        self._thread = None

    def start_download(self, repo_id, cache_dir):
        """Starts a model download in a background thread.

        If a download is already running, this call is ignored.

        Args:
            repo_id: HuggingFace repository identifier to download.
            cache_dir: Local directory for storing downloaded files.

        """
        if self._thread:
            try:
                if self._thread.isRunning():
                    return
            except RuntimeError:
                # The C++ object is deleted, but Python wrapper exists.
                # Treat as not running.
                self._thread = None

        self._thread = QThread()
        self.worker = DownloadWorker(repo_id, cache_dir)
        self.worker.moveToThread(self._thread)

        # Connect signals
        self._thread.started.connect(self.worker.run)
        self.worker.progress_update.connect(self.progress.emit)
        self.worker.download_finished.connect(self._on_finished)
        self.worker.download_failed.connect(self._on_failed)

        # Cleanup
        self.worker.download_finished.connect(self._thread.quit)
        self.worker.download_failed.connect(self._thread.quit)
        self.worker.download_finished.connect(self.worker.deleteLater)
        self.worker.download_failed.connect(self.worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

        # Keep thread alive globally until it finishes
        ACTIVE_THREADS.add(self._thread)
        # Use a captured variable to avoid binding to 'self'
        t = self._thread
        t.finished.connect(lambda: ACTIVE_THREADS.discard(t))

    def cancel_download(self):
        """Cancels the active download, if any.

        Sets the worker's cancellation flag.  The worker loop will
        terminate the subprocess and emit ``failed`` with a cancellation
        message.
        """
        if self.worker:
            self.worker.cancel()

        # We DO NOT quit or kill the QThread immediately.
        # We let the worker loop process the cancellation and exit gracefully.
        # This ensures the process is consistently terminated.
        # Cleanup signals will handle the rest.

    def _on_finished(self, path):
        """Handles successful download completion.

        Args:
            path: Local filesystem path to the downloaded model.

        """
        self._thread = None
        self.finished.emit(path)

    def _on_failed(self, error):
        """Handles download failure.

        Args:
            error: Error message describing the failure.

        """
        self.failed.emit(error)
