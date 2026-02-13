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
    """
    Function to run in a separate PROCESS.
    Blocks until download finishes or process is killed.
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
    """
    Worker class to MANAGE the download process from a QThread.
    It spawns a multiprocessing.Process and monitors it.
    """

    progress_update = pyqtSignal(int, str)  # progress (%), status message
    download_finished = pyqtSignal(str)  # path to model
    download_failed = pyqtSignal(str)  # error message

    def __init__(self, repo_id, cache_dir):
        super().__init__()
        self.repo_id = repo_id
        self.cache_dir = cache_dir
        self._is_cancelled = False
        self._process = None
        self._queue = None

    def run(self):
        """
        Starts the process and polls the queue.
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
        """
        Reads from queue. Returns True if task finished/failed.
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
        if self._process and self._process.is_alive():
            self._process.terminate()
            self._process.join()  # Cleanup

    def cancel(self):
        self._is_cancelled = True
        # The run loop will pick this up and terminate the process


# Global set to keep references to running threads, preventing them from being
# garbage collected (and crashing) if the parent ModelDownloader is destroyed.
ACTIVE_THREADS = set()


class ModelDownloader(QObject):
    """
    Manager to handle threading and signal connections for downloads.
    """

    # ... (signals same)
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.worker = None
        self._thread = None

    def start_download(self, repo_id, cache_dir):
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
        """
        Cancel the download.
        Sets worker flag to cancelled. The worker loop will see this
        and call process.terminate().
        """
        if self.worker:
            self.worker.cancel()

        # We DO NOT quit or kill the QThread immediately.
        # We let the worker loop process the cancellation and exit gracefully.
        # This ensures the process is consistently terminated.
        # Cleanup signals will handle the rest.

    def _on_finished(self, path):
        self._thread = None
        self.finished.emit(path)

    def _on_failed(self, error):
        self.failed.emit(error)
