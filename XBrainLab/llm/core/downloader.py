"""Model downloader with process-based isolation.

Provides a multi-process download mechanism for HuggingFace models,
with Qt signal integration for progress reporting and cancellation.
"""

from __future__ import annotations

import contextlib
import math
import multiprocessing
import os
import queue  # Standard library queue for Empty exception
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Protocol, cast

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.core.model_catalog import (
    inspect_model_download_consumption,
    local_model_spec,
    model_cache_candidates,
    model_cache_complete,
    plan_model_download,
    validate_downloaded_model_cache,
)

snapshot_download: Callable[..., Any] | None
try:
    from huggingface_hub import snapshot_download as _snapshot_download
except ImportError:
    snapshot_download = None
else:
    snapshot_download = _snapshot_download


PROCESS_JOIN_TIMEOUT_SEC = 2.0
PROCESS_TERMINATE_JOIN_TIMEOUT_SEC = 5.0
PROCESS_KILL_JOIN_TIMEOUT_SEC = 1.0
PROCESS_CLEANUP_MAX_ATTEMPTS = 3
PROCESS_CLEANUP_RETRY_DELAY_SEC = 0.05
DOWNLOAD_PROCESS_START_METHOD = "spawn"
DOWNLOAD_CONSUMPTION_POLL_INTERVAL_SEC = 0.5
MODEL_DOWNLOAD_DEADLINE_SEC = 2 * 60 * 60
MODEL_DOWNLOAD_TIMEOUT_PUBLIC_MESSAGE = (
    "Model download reached the two-hour time limit and was stopped safely. "
    "Check your internet connection, then try again."
)
MODEL_DOWNLOAD_FAILURE_PUBLIC_MESSAGE = (
    "Model download failed. Check the application log and try again."
)
MODEL_DOWNLOAD_TIMEOUT_DIAGNOSTIC = "model_download_deadline_exceeded"


class _DownloadQueue(Protocol):
    def put(self, item: tuple[str, Any]) -> None: ...

    def get_nowait(self) -> tuple[str, Any]: ...

    def close(self) -> None: ...

    def join_thread(self) -> None: ...


class _DownloadProcess(Protocol):
    exitcode: int | None
    pid: int | None

    def start(self) -> None: ...

    def is_alive(self) -> bool: ...

    def join(self, timeout: float | None = None) -> None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def close(self) -> None: ...


class _DownloadProcessContext(Protocol):
    def Queue(self) -> _DownloadQueue: ...  # noqa: N802

    def Process(  # noqa: N802
        self,
        group: None = None,
        target: Callable[..., Any] | None = None,
        name: str | None = None,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        *,
        daemon: bool | None = None,
    ) -> _DownloadProcess: ...


class ModelDownloadStatus(str, Enum):
    """Terminal result of one immutable model download request."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelDownloadFailureCode(str, Enum):
    """Stable failure categories safe for UI presentation decisions."""

    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    FAILED = "failed"


@dataclass(frozen=True)
class ModelDownloadTarget:
    """Immutable repository and cache identity captured at admission."""

    repo_id: str
    cache_dir: str
    cache_candidates: tuple[str, ...]
    complete_cache_at_start: bool = False

    @classmethod
    def create(cls, repo_id: str, cache_dir: str) -> ModelDownloadTarget:
        normalized_cache = os.path.abspath(os.path.expanduser(cache_dir))
        return cls(
            repo_id=str(repo_id),
            cache_dir=normalized_cache,
            cache_candidates=tuple(
                model_cache_candidates(normalized_cache, str(repo_id))
            ),
            complete_cache_at_start=model_cache_complete(
                normalized_cache,
                str(repo_id),
            ),
        )


class ProcessCleanupPhase(str, Enum):
    """Observable child-process cleanup phase."""

    IDLE = "idle"
    CLEANING = "cleaning"
    RETRY_PENDING = "retry_pending"
    RECOVERY_REQUIRED = "recovery_required"
    REAPED = "reaped"


@dataclass(frozen=True)
class ProcessCleanupSnapshot:
    """One bounded child-process cleanup attempt."""

    phase: ProcessCleanupPhase
    attempt: int = 0
    message: str = ""
    diagnostic_message: str = ""


@dataclass(frozen=True)
class ModelDownloadOutcome:
    """Target-aware outcome published only after native resources are terminal."""

    target: ModelDownloadTarget
    status: ModelDownloadStatus
    message: str
    model_path: str | None = None
    failure_code: ModelDownloadFailureCode | None = None
    process_cleanup: ProcessCleanupSnapshot | None = None
    diagnostic_message: str = ""

    @property
    def ok(self) -> bool:
        return self.status is ModelDownloadStatus.SUCCEEDED

    @property
    def cancelled(self) -> bool:
        return self.status is ModelDownloadStatus.CANCELLED


def model_download_public_failure_message(outcome: ModelDownloadOutcome) -> str:
    """Return only reviewed product copy for a typed download failure."""
    if outcome.failure_code is ModelDownloadFailureCode.TIMEOUT:
        return MODEL_DOWNLOAD_TIMEOUT_PUBLIC_MESSAGE
    return MODEL_DOWNLOAD_FAILURE_PUBLIC_MESSAGE


# -----------------------------------------------------------------------------
# Standalone Process Function (Must be picklable)
# -----------------------------------------------------------------------------
def run_download_task(repo_id, cache_dir, result_queue: _DownloadQueue):
    """Runs a HuggingFace model download in a separate process.

    This function must be picklable for ``multiprocessing.Process``.
    Progress and completion/error status are communicated via
    ``result_queue``.

    Args:
        repo_id: HuggingFace repository identifier (e.g.
            ``'ibm-granite/granite-3.3-2b-instruct'``).
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
        preflight = plan_model_download(repo_id, cache_dir)
        if not preflight.ok:
            result_queue.put(("error", preflight.message))
            return
        spec = local_model_spec(repo_id)
        if spec is None:
            result_queue.put(("error", f"Unsupported local model: {repo_id}."))
            return

        # Disable HF Hub progress bars to prevent messy terminal output
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

        result_queue.put(("progress", (0, preflight.message)))

        # This BLOCKS until done.
        model_path = snapshot_download(
            repo_id=repo_id,
            cache_dir=cache_dir,
            revision=spec.revision,
            resume_download=True,
        )

        validation = validate_downloaded_model_cache(
            repo_id,
            cache_dir,
            str(model_path),
        )
        if not validation.ok:
            result_queue.put(("error", validation.message))
            return

        result_queue.put(("progress", (100, "Download Complete")))
        result_queue.put(("finished", validation.snapshot_path or str(model_path)))

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
    download_failed = pyqtSignal(str)
    cleanup_state_changed = pyqtSignal(object)

    def __init__(
        self,
        repo_id,
        cache_dir,
        *,
        deadline_seconds: float = MODEL_DOWNLOAD_DEADLINE_SEC,
    ):
        """Initializes the DownloadWorker.

        Args:
            repo_id: HuggingFace repository identifier to download.
            cache_dir: Local directory for storing downloaded files.

        """
        super().__init__()
        self.repo_id = repo_id
        self.cache_dir = cache_dir
        deadline = float(deadline_seconds)
        if not math.isfinite(deadline) or deadline <= 0:
            raise ValueError("Model download deadline must be a positive number.")
        self._deadline_seconds = deadline
        self._started_at = 0.0
        self._is_cancelled = False
        self._process: _DownloadProcess | None = None
        self._queue: _DownloadQueue | None = None
        self._cleanup_attempts = 0
        self._cleanup_snapshot = ProcessCleanupSnapshot(ProcessCleanupPhase.IDLE)
        self._child_start_confirmed = False
        self._pending_terminal_kind: str | None = None
        self._pending_terminal_payload = ""
        self._terminal_emitted = False
        self._next_consumption_check_at = 0.0

    def run(self):
        """Starts the download subprocess and polls its status queue.

        Runs in a QThread context.  Monitors for cancellation, unexpected
        process death, and queue messages until the download completes or
        fails.
        """
        try:
            process_context = cast(
                _DownloadProcessContext,
                multiprocessing.get_context(DOWNLOAD_PROCESS_START_METHOD),
            )
            self._queue = process_context.Queue()
            process = process_context.Process(
                target=run_download_task,
                args=(self.repo_id, self.cache_dir, self._queue),
                daemon=True,
            )
            # Ownership starts before Process.start(). A spawn implementation may
            # create the child and then raise while finalizing the parent handle.
            self._process = process
            try:
                process.start()
                self._child_start_confirmed = True
                self._started_at = time.monotonic()
                self._next_consumption_check_at = (
                    self._started_at + DOWNLOAD_CONSUMPTION_POLL_INTERVAL_SEC
                )
            except Exception as exc:
                self._child_start_confirmed = self._started_child_may_exist(process)
                self._record_pending_failure(f"Model download could not start: {exc}")
                self._finish_or_defer_terminal()
                return

            while self._pending_terminal_kind is None:
                if self._is_cancelled:
                    self._record_pending_failure("Cancelled by user")
                    break
                if self._download_deadline_exceeded():
                    self._record_pending_failure(MODEL_DOWNLOAD_TIMEOUT_DIAGNOSTIC)
                    break

                alive = self._query_process_alive(
                    process,
                    operation="monitor is_alive",
                )
                if alive is None:
                    self._record_pending_failure(
                        "Model download process state could not be verified."
                    )
                    break
                if not alive:
                    if not self._check_queue():
                        self._record_pending_failure(
                            "Download process terminated unexpectedly "
                            f"(exit code: {self._safe_exit_code(process)})"
                        )
                    break
                if self._check_queue():
                    break
                if not self._check_consumption_if_due():
                    break
                time.sleep(0.1)
        except Exception as exc:
            self._record_pending_failure(f"Model download failed: {exc}")

        self._finish_or_defer_terminal()

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
                    self._record_pending_success(str(data))
                    return True

                elif msg_type == "error":
                    self._record_pending_failure(str(data))
                    return True

        except queue.Empty:
            pass

        return False

    def _check_consumption_if_due(self, *, now: float | None = None) -> bool:
        """Enforce actual cache and disk limits at a bounded polling cadence."""
        observed_at = time.monotonic() if now is None else now
        if observed_at < self._next_consumption_check_at:
            return True
        consumption = inspect_model_download_consumption(
            self.repo_id,
            self.cache_dir,
        )
        completed_at = observed_at if now is not None else time.monotonic()
        self._next_consumption_check_at = (
            completed_at + DOWNLOAD_CONSUMPTION_POLL_INTERVAL_SEC
        )
        if consumption.ok:
            return True
        if consumption.public_message:
            self.progress_update.emit(0, consumption.public_message)
        self._record_pending_failure(
            consumption.diagnostic_message or consumption.public_message
        )
        return False

    def _download_deadline_exceeded(self, *, now: float | None = None) -> bool:
        """Return whether this owned download exceeded its wall-clock budget."""
        observed_at = time.monotonic() if now is None else float(now)
        return observed_at - self._started_at >= self._deadline_seconds

    def _record_pending_success(self, path: str) -> None:
        if self._pending_terminal_kind is None:
            self._pending_terminal_kind = "finished"
            self._pending_terminal_payload = path

    def _record_pending_failure(self, error: str) -> None:
        if self._pending_terminal_kind is None:
            self._pending_terminal_kind = "failed"
            self._pending_terminal_payload = str(error)

    @staticmethod
    def _safe_exit_code(process: _DownloadProcess) -> object:
        try:
            return process.exitcode
        except Exception:
            return "unknown"

    @staticmethod
    def _started_child_may_exist(process: _DownloadProcess) -> bool:
        """Conservatively detect whether a failed start may own a child."""
        try:
            if bool(process.is_alive()):
                return True
        except Exception:
            return True
        try:
            pid = getattr(process, "pid", None)
            popen = getattr(process, "_popen", None)
        except Exception:
            return True
        return pid is not None or popen is not None

    def _finish_or_defer_terminal(self) -> bool:
        """Publish terminal only after all native process ownership is released."""
        if not self._reap_process():
            return False
        self._close_queue()
        self._emit_pending_terminal()
        return True

    def _emit_pending_terminal(self) -> None:
        if self._terminal_emitted:
            return
        self._terminal_emitted = True
        kind = self._pending_terminal_kind or "failed"
        payload = self._pending_terminal_payload or (
            "Download worker stopped without a terminal result."
        )
        if kind == "finished":
            self.download_finished.emit(payload)
        else:
            self.download_failed.emit(payload)

    def retry_cleanup(self) -> None:
        """Run one bounded recovery cycle in the worker QThread."""
        if self._terminal_emitted:
            return
        self._finish_or_defer_terminal()

    def _terminate_process(self) -> bool:
        """Run one bounded terminate/kill attempt on the owned child."""
        process = self._process
        if not process:
            return True

        self._begin_cleanup_attempt()
        alive = self._query_process_alive(process, operation="is_alive")
        if alive is None:
            return False

        if not alive:
            if not self._child_start_confirmed:
                return self._release_unstarted_process(process)
            if not self._join_process(
                process,
                PROCESS_JOIN_TIMEOUT_SEC,
                operation="join",
            ):
                return False
            alive = self._query_process_alive(process, operation="is_alive after join")
            if alive is None:
                return False
            if alive:
                self._publish_cleanup_retry("Child process revived after join.")
                return False
            return self._release_reaped_process(process)

        self._child_start_confirmed = True
        try:
            process.terminate()
        except Exception as exc:
            self._publish_cleanup_exception("terminate", exc)
            return False
        if not self._join_process(
            process,
            PROCESS_TERMINATE_JOIN_TIMEOUT_SEC,
            operation="join after terminate",
        ):
            return False
        alive = self._query_process_alive(
            process,
            operation="is_alive after terminate",
        )
        if alive is None:
            return False
        if not alive:
            return self._release_reaped_process(process)

        if not hasattr(process, "kill"):
            self._publish_cleanup_retry(
                "Child process is still alive and kill() is unavailable."
            )
            return False
        try:
            process.kill()
        except Exception as exc:
            self._publish_cleanup_exception("kill", exc)
            return False
        if not self._join_process(
            process,
            PROCESS_KILL_JOIN_TIMEOUT_SEC,
            operation="join after kill",
        ):
            return False
        alive = self._query_process_alive(
            process,
            operation="is_alive after kill",
        )
        if alive is None:
            return False
        if alive:
            self._publish_cleanup_retry("Child process is still alive after kill().")
            return False
        return self._release_reaped_process(process)

    def _begin_cleanup_attempt(self) -> None:
        self._cleanup_attempts = int(getattr(self, "_cleanup_attempts", 0)) + 1
        self._publish_cleanup_state(
            ProcessCleanupPhase.CLEANING,
            "Stopping model download subprocess.",
        )

    def _query_process_alive(
        self,
        process: _DownloadProcess,
        *,
        operation: str,
    ) -> bool | None:
        try:
            return bool(process.is_alive())
        except Exception as exc:
            self._publish_cleanup_exception(operation, exc)
            return None

    def _join_process(
        self,
        process: _DownloadProcess,
        timeout_sec: float,
        *,
        operation: str,
    ) -> bool:
        try:
            process.join(timeout_sec)
        except Exception as exc:
            self._publish_cleanup_exception(operation, exc)
            return False
        return True

    def _release_reaped_process(self, process: _DownloadProcess) -> bool:
        """Release ownership only after join and a reliable dead observation."""
        if self._process is not process:
            return self._process is None
        try:
            process.close()
        except Exception as exc:
            self._publish_cleanup_exception("close reaped handle", exc)
            return False
        self._process = None
        self._publish_cleanup_state(
            ProcessCleanupPhase.REAPED,
            "Model download subprocess cleanup completed.",
        )
        return True

    def _release_unstarted_process(self, process: _DownloadProcess) -> bool:
        """Release a Process object only when no child was ever observed."""
        if self._process is not process:
            return self._process is None
        try:
            process.close()
        except Exception as exc:
            self._publish_cleanup_exception("close unstarted handle", exc)
            return False
        self._process = None
        self._publish_cleanup_state(
            ProcessCleanupPhase.REAPED,
            "Model download process handle cleanup completed.",
        )
        return True

    def _publish_cleanup_exception(self, operation: str, exc: Exception) -> None:
        self._publish_cleanup_retry(
            "Model download cleanup needs another attempt.",
            diagnostic_message=(
                f"Model download subprocess cleanup {operation} failed: "
                f"{type(exc).__name__}: {exc}"
            ),
        )

    def _publish_cleanup_retry(
        self,
        message: str,
        *,
        diagnostic_message: str = "",
    ) -> None:
        self._publish_cleanup_state(
            ProcessCleanupPhase.RETRY_PENDING,
            message,
            diagnostic_message=diagnostic_message,
        )

    def _publish_cleanup_state(
        self,
        phase: ProcessCleanupPhase,
        message: str,
        *,
        diagnostic_message: str = "",
    ) -> None:
        snapshot = ProcessCleanupSnapshot(
            phase=phase,
            attempt=int(getattr(self, "_cleanup_attempts", 0)),
            message=message,
            diagnostic_message=diagnostic_message,
        )
        self._cleanup_snapshot = snapshot
        signal = getattr(self, "cleanup_state_changed", None)
        emit = getattr(signal, "emit", None)
        if callable(emit):
            emit(snapshot)

    @property
    def cleanup_snapshot(self) -> ProcessCleanupSnapshot:
        return getattr(
            self,
            "_cleanup_snapshot",
            ProcessCleanupSnapshot(ProcessCleanupPhase.IDLE),
        )

    def _reap_process(
        self,
        max_attempts: int = PROCESS_CLEANUP_MAX_ATTEMPTS,
    ) -> bool:
        """Run a bounded cleanup cycle while retaining unresolved ownership."""
        process = self._process
        if not process:
            return True

        attempt_limit = max(1, int(max_attempts))
        for attempt_index in range(attempt_limit):
            if self._terminate_process():
                return True
            if self._process is not process:
                return self._process is None
            if attempt_index + 1 < attempt_limit:
                time.sleep(PROCESS_CLEANUP_RETRY_DELAY_SEC)

        last_diagnostic = self._cleanup_snapshot.diagnostic_message
        self._publish_cleanup_state(
            ProcessCleanupPhase.RECOVERY_REQUIRED,
            (
                "Model download cleanup is still pending. XBrainLab will keep "
                "ownership and retry during safe shutdown."
            ),
            diagnostic_message=last_diagnostic,
        )
        return False

    def _close_queue(self):
        """Close the multiprocessing queue after the worker loop exits."""
        q = self._queue
        if q is None:
            return
        with contextlib.suppress(AttributeError, OSError, ValueError):
            q.close()
        with contextlib.suppress(AttributeError, OSError, ValueError):
            q.join_thread()
        self._queue = None

    def cancel(self):
        """Requests cancellation of the in-progress download.

        Sets the cancellation flag; the ``run`` loop will terminate the
        subprocess on its next iteration.
        """
        self._is_cancelled = True
        # The run loop will pick this up and terminate the process


class ModelDownloader(QObject):
    """High-level manager for model downloads with Qt threading.

    Handles QThread lifecycle, signal wiring, and ensures only one
    download runs at a time. The owning application lifecycle must retain this
    object until ``terminal`` reports that the QThread and subprocess are gone.

    Attributes:
        progress: Signal emitting ``(percent, status_message)``.
        finished: Signal emitting the downloaded model path.
        failed: Signal emitting an error message.
        terminal: Signal emitted after all native download resources are reaped.
        worker: The active ``DownloadWorker``, if any.

    """

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(object)
    terminal = pyqtSignal(object)
    cleanup_state_changed = pyqtSignal(object)
    cleanup_retry_requested = pyqtSignal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        download_deadline_seconds: float = MODEL_DOWNLOAD_DEADLINE_SEC,
    ):
        """Initializes the ModelDownloader."""
        super().__init__(parent)
        deadline = float(download_deadline_seconds)
        if not math.isfinite(deadline) or deadline <= 0:
            raise ValueError("Model download deadline must be a positive number.")
        self._download_deadline_seconds = deadline
        self.worker: DownloadWorker | None = None
        self._thread: QThread | None = None
        self._active_target: ModelDownloadTarget | None = None
        self._pending_outcome: ModelDownloadOutcome | None = None
        self._last_cleanup_snapshot = ProcessCleanupSnapshot(ProcessCleanupPhase.IDLE)

    def start_download(self, repo_id: str, cache_dir: str) -> bool:
        """Starts a model download in a background thread.

        If a download is already running, this call is rejected.

        Args:
            repo_id: HuggingFace repository identifier to download.
            cache_dir: Local directory for storing downloaded files.

        Returns:
            ``True`` when a new worker was started, otherwise ``False``.

        """
        if not self.is_idle():
            return False

        self._active_target = ModelDownloadTarget.create(repo_id, cache_dir)
        self._pending_outcome = None
        self._last_cleanup_snapshot = ProcessCleanupSnapshot(ProcessCleanupPhase.IDLE)
        thread = QThread(self)
        worker = DownloadWorker(
            self._active_target.repo_id,
            self._active_target.cache_dir,
            deadline_seconds=self._download_deadline_seconds,
        )
        self._thread = thread
        self.worker = worker
        worker.moveToThread(thread)

        # Connect signals
        thread.started.connect(worker.run)
        worker.progress_update.connect(self.progress.emit)
        worker.download_finished.connect(self._record_success)
        worker.download_failed.connect(self._record_failure)
        worker.cleanup_state_changed.connect(self._record_cleanup_state)
        self.cleanup_retry_requested.connect(worker.retry_cleanup)

        # Cleanup
        worker.download_finished.connect(thread.quit)
        worker.download_failed.connect(thread.quit)
        worker.download_finished.connect(worker.deleteLater)
        worker.download_failed.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        thread.finished.connect(thread.deleteLater)

        try:
            thread.start()
        except Exception as exc:
            self._publish_thread_start_failure(
                target=self._active_target,
                thread=thread,
                worker=worker,
                exc=exc,
            )
            return False
        return True

    def _publish_thread_start_failure(
        self,
        *,
        target: ModelDownloadTarget,
        thread: QThread,
        worker: DownloadWorker,
        exc: Exception,
    ) -> None:
        """Release startup ownership and publish one safe terminal failure."""
        diagnostic = f"Download QThread could not start: {type(exc).__name__}: {exc}"
        logger.error(
            "Model download thread start failed for %s: %s",
            target.repo_id,
            exc,
        )
        with contextlib.suppress(RuntimeError, TypeError):
            self.cleanup_retry_requested.disconnect(worker.retry_cleanup)
        with contextlib.suppress(RuntimeError):
            worker.deleteLater()
        with contextlib.suppress(RuntimeError):
            thread.deleteLater()

        self._thread = None
        self.worker = None
        self._active_target = None
        self._pending_outcome = None
        cleanup = ProcessCleanupSnapshot(
            phase=ProcessCleanupPhase.REAPED,
            message="Model download thread startup was released.",
            diagnostic_message=diagnostic,
        )
        self._last_cleanup_snapshot = cleanup
        outcome = ModelDownloadOutcome(
            target=target,
            status=ModelDownloadStatus.FAILED,
            message=(
                "Model download could not start. "
                "Check the application log and try again."
            ),
            process_cleanup=cleanup,
            diagnostic_message=diagnostic,
        )
        self.terminal.emit(outcome)
        self.failed.emit(outcome)

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

    def shutdown(self, wait_ms: int | None = None) -> bool:
        """Request cancellation without blocking the Qt GUI thread.

        ``wait_ms`` remains accepted for compatibility but is deliberately
        ignored. Callers must retry from the event loop or observe ``terminal``.

        Returns:
            ``True`` only when no active thread ownership remains.

        """
        del wait_ms
        self.cancel_download()
        self.request_cleanup_retry()
        return self.is_idle()

    def request_cleanup_retry(self) -> bool:
        """Queue one bounded cleanup recovery cycle without blocking the GUI."""
        if self.worker is None:
            return self.is_idle()
        self.cleanup_retry_requested.emit()
        return False

    def is_idle(self) -> bool:
        """Return whether this owner has released all QThread ownership."""
        thread = self._thread
        if thread is None:
            return True
        try:
            thread.isRunning()
        except RuntimeError:
            snapshot = ProcessCleanupSnapshot(
                phase=ProcessCleanupPhase.RETRY_PENDING,
                attempt=self._last_cleanup_snapshot.attempt,
                message=(
                    "Download QThread state is unavailable; ownership is retained "
                    "until a terminal callback arrives."
                ),
            )
            self._record_cleanup_state(snapshot)
            return False
        return False

    def _record_success(self, path: str) -> None:
        """Store a worker outcome until QThread terminal cleanup finishes."""
        self._pending_outcome = ModelDownloadOutcome(
            target=self._require_active_target(),
            status=ModelDownloadStatus.SUCCEEDED,
            message="Model downloaded successfully.",
            model_path=path,
        )

    def _record_failure(self, error: str) -> None:
        """Store a worker failure until QThread terminal cleanup finishes."""
        failure_code = (
            ModelDownloadFailureCode.CANCELLED
            if error == "Cancelled by user"
            else (
                ModelDownloadFailureCode.TIMEOUT
                if error == MODEL_DOWNLOAD_TIMEOUT_DIAGNOSTIC
                else ModelDownloadFailureCode.FAILED
            )
        )
        status = (
            ModelDownloadStatus.CANCELLED
            if failure_code is ModelDownloadFailureCode.CANCELLED
            else ModelDownloadStatus.FAILED
        )
        public_message = (
            "Model download cancelled."
            if status is ModelDownloadStatus.CANCELLED
            else (
                MODEL_DOWNLOAD_TIMEOUT_PUBLIC_MESSAGE
                if failure_code is ModelDownloadFailureCode.TIMEOUT
                else MODEL_DOWNLOAD_FAILURE_PUBLIC_MESSAGE
            )
        )
        self._pending_outcome = ModelDownloadOutcome(
            target=self._require_active_target(),
            status=status,
            message=public_message,
            failure_code=failure_code,
            diagnostic_message=error,
        )
        if status is not ModelDownloadStatus.CANCELLED:
            logger.error(
                "Model download failed for %s: %s",
                self._require_active_target().repo_id,
                error,
            )

    def _record_cleanup_state(self, snapshot: ProcessCleanupSnapshot) -> None:
        self._last_cleanup_snapshot = snapshot
        if snapshot.phase is ProcessCleanupPhase.RECOVERY_REQUIRED:
            logger.error(
                "Model download process ownership retained for recovery: %s",
                snapshot.diagnostic_message or snapshot.message,
            )
        self.cleanup_state_changed.emit(snapshot)

    def _require_active_target(self) -> ModelDownloadTarget:
        target = self._active_target
        if target is None:
            return ModelDownloadTarget.create("unknown/model", os.curdir)
        return target

    @property
    def active_target(self) -> ModelDownloadTarget | None:
        return self._active_target

    def _on_thread_finished(self) -> None:
        """Publish one outcome only after the worker reaped its subprocess."""
        self._thread = None
        self.worker = None
        outcome = self._pending_outcome or ModelDownloadOutcome(
            target=self._require_active_target(),
            status=ModelDownloadStatus.FAILED,
            message="Model download stopped unexpectedly. Try again.",
            diagnostic_message="Download worker stopped without a terminal result.",
        )
        outcome = replace(
            outcome,
            process_cleanup=self._last_cleanup_snapshot,
        )
        self._pending_outcome = None
        self._active_target = None
        self.terminal.emit(outcome)
        if outcome.ok:
            self.finished.emit(outcome)
        else:
            self.failed.emit(outcome)
