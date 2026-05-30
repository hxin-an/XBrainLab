"""Background worker utilities for offloading tasks to QThreadPool."""

import logging
import sys
import traceback

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    """Signals available from a running ``Worker`` thread.

    Attributes:
        finished: Emitted when the task completes (no data).
        error: Emitted with ``(exctype, value, formatted_traceback)``
            on failure.
        result: Emitted with the return value of the callback function.
        progress: Emitted with an ``int`` indicating percentage progress.

    """

    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)
    progress = pyqtSignal(int)


class Worker(QRunnable):
    """Worker thread for offloading heavy tasks via QThreadPool.

    Wraps a callable with arguments and emits signals for completion,
    errors, and results.

    Attributes:
        fn: The callback function to execute.
        args: Positional arguments for the callback.
        kwargs: Keyword arguments for the callback.
        signals: ``WorkerSignals`` instance for communicating results.

    """

    def __init__(self, fn, *args, **kwargs):
        """Initialize the worker.

        Args:
            fn: The callable to run in the worker thread.
            *args: Positional arguments passed to ``fn``.
            **kwargs: Keyword arguments passed to ``fn``.

        """
        super().__init__()

        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self):
        """Execute the callback and emit result or error signals."""
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception:
            # Emit error signal
            logger.error("Worker task failed", exc_info=True)
            exctype, value = sys.exc_info()[:2]
            self._safe_emit("error", (exctype, value, traceback.format_exc()))
        else:
            # Return the result of the processing
            self._safe_emit("result", result)
        finally:
            # Done
            self._safe_emit("finished")

    def _safe_emit(self, signal_name: str, *args) -> None:
        """Emit a worker signal unless Qt already destroyed the receiver wrapper."""
        try:
            signal = getattr(self.signals, signal_name)
            signal.emit(*args)
        except RuntimeError:
            logger.debug(
                "Skipped worker %s signal because Qt deleted the signal wrapper.",
                signal_name,
                exc_info=True,
            )
