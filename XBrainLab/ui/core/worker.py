"""Background worker utilities for Qt and Python-owned execution threads."""

import logging
import sys
import traceback
from threading import Thread
from typing import Any

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


def _run_worker_task(worker: Any) -> None:
    """Execute one worker callback through the shared signal contract."""
    try:
        result = worker.fn(*worker.args, **worker.kwargs)
    except Exception:
        logger.error("Worker task failed", exc_info=True)
        exctype, value = sys.exc_info()[:2]
        _safe_emit(worker, "error", (exctype, value, traceback.format_exc()))
    else:
        _safe_emit(worker, "result", result)
    finally:
        _safe_emit(worker, "finished")


def _safe_emit(worker: Any, signal_name: str, *args: Any) -> None:
    """Emit a worker signal unless Qt already destroyed its wrapper."""
    try:
        signal = getattr(worker.signals, signal_name)
        signal.emit(*args)
    except RuntimeError:
        logger.debug(
            "Skipped worker %s signal because Qt deleted the signal wrapper.",
            signal_name,
            exc_info=True,
        )


class Worker(QRunnable):
    """Worker for lightweight callbacks dispatched through ``QThreadPool``.

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

        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self) -> None:
        _run_worker_task(self)


class PythonThreadWorker:
    """Run native-heavy callbacks in a Python-owned thread.

    Qt-created pooled threads enter Python through SIP. Long scientific calls can
    repeatedly release the GIL while running there, which has produced native
    crashes in the WSL/PyQt runtime. A ``threading.Thread`` owns a regular Python
    thread state while preserving the same queued Qt signal delivery contract.
    """

    def __init__(
        self,
        fn,
        *args,
        name: str,
        daemon: bool = False,
        **kwargs,
    ):
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self._thread = Thread(target=self.run, name=name, daemon=daemon)

    @property
    def name(self) -> str:
        return self._thread.name

    @property
    def daemon(self) -> bool:
        return self._thread.daemon

    def start(self) -> None:
        self._thread.start()

    def run(self) -> None:
        _run_worker_task(self)

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout=timeout)
