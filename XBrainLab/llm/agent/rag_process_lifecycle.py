"""Process-owned lifecycle for the production RAG retriever."""

from __future__ import annotations

import logging
import multiprocessing
import queue
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from XBrainLab.llm.tools.result_contract import safe_unexpected_failure

logger = logging.getLogger(__name__)

RAG_INITIALIZATION_TIMEOUT_SECONDS = 120.0
RAG_RETRIEVAL_TIMEOUT_SECONDS = 30.0
RAG_PROCESS_SHUTDOWN_SECONDS = 2.0
_MONITOR_POLL_SECONDS = 0.05

RAGResultCallback = Callable[[int, str, str, str], None]
RAGProcessTarget = Callable[[Any, Any], None]


def _run_rag_process(command_queue: Any, result_queue: Any) -> None:
    """Own all heavyweight RAG state inside one terminable child process."""
    from XBrainLab.llm.rag import RAGRetriever  # noqa: PLC0415

    retriever = RAGRetriever()
    try:
        retriever.initialize()
        result_queue.put(("ready", bool(retriever.is_initialized)))
        while True:
            command = command_queue.get()
            if not isinstance(command, tuple) or not command:
                continue
            kind = command[0]
            if kind == "close":
                return
            if kind != "retrieve" or len(command) != 4:
                continue
            _, turn_id, query_text, allowed_names = command
            try:
                features = retriever.get_similar_examples(
                    str(query_text),
                    allowed_tool_names=(
                        frozenset(str(name) for name in allowed_names)
                        if allowed_names is not None
                        else None
                    ),
                )
            except BaseException as exc:
                logger.exception("RAG child retrieval failed")
                result_queue.put(
                    (
                        "result",
                        int(turn_id),
                        str(query_text),
                        "",
                        f"RAG retrieval failed ({type(exc).__name__}).",
                    )
                )
            else:
                result_queue.put(
                    (
                        "result",
                        int(turn_id),
                        str(query_text),
                        str(features or ""),
                        "",
                    )
                )
    except BaseException as exc:
        logger.exception("RAG child initialization failed")
        result_queue.put(("initialization_error", type(exc).__name__))
    finally:
        try:
            retriever.close()
        except BaseException:
            logger.exception("RAG child cleanup failed")


@dataclass(slots=True)
class _PendingRetrieval:
    turn_id: int
    query: str
    callback: RAGResultCallback
    deadline: float | None


class ProcessRAGRetrieverLifecycle:
    """Own production RAG in a subprocess with hard timeout and cancellation."""

    retriever = None

    def __init__(
        self,
        *,
        initialization_timeout_seconds: float = RAG_INITIALIZATION_TIMEOUT_SECONDS,
        retrieval_timeout_seconds: float = RAG_RETRIEVAL_TIMEOUT_SECONDS,
        shutdown_wait_seconds: float = RAG_PROCESS_SHUTDOWN_SECONDS,
        process_target: RAGProcessTarget = _run_rag_process,
    ) -> None:
        self._initialization_timeout_seconds = max(
            0.01,
            float(initialization_timeout_seconds),
        )
        self._retrieval_timeout_seconds = max(
            0.01,
            float(retrieval_timeout_seconds),
        )
        self._shutdown_wait_seconds = max(0.01, float(shutdown_wait_seconds))
        self._process_target = process_target
        self._context = multiprocessing.get_context("spawn")
        self._lock = threading.Lock()
        self._closed = False
        self._generation = 0
        self._process: Any | None = None
        self._command_queue: Any | None = None
        self._result_queue: Any | None = None
        self._monitor_thread: threading.Thread | None = None
        self._started_at = 0.0
        self._ready = False
        self._pending: _PendingRetrieval | None = None

    @property
    def is_initializing(self) -> bool:
        with self._lock:
            process = self._process
            return bool(process is not None and process.is_alive() and not self._ready)

    @property
    def initializer_thread_daemon(self) -> bool:
        with self._lock:
            process = self._process
            return bool(process is not None and process.daemon)

    @property
    def is_retrieving(self) -> bool:
        with self._lock:
            return self._pending is not None

    @property
    def retrieval_thread_daemon(self) -> bool:
        with self._lock:
            monitor = self._monitor_thread
            return bool(monitor is not None and monitor.daemon)

    @property
    def has_active_process(self) -> bool:
        with self._lock:
            process = self._process
            return bool(process is not None and process.is_alive())

    def start(self) -> bool:
        """Start one process unless the lifecycle is closed or already alive."""
        with self._lock:
            if self._closed:
                return False
            process = self._process
            if process is not None and process.is_alive():
                return False
            return self._spawn_locked()

    def _spawn_locked(self) -> bool:
        command_queue = self._context.Queue()
        result_queue = self._context.Queue()
        process = self._context.Process(
            target=self._process_target,
            args=(command_queue, result_queue),
            name="xbrainlab-rag-runtime",
            daemon=True,
        )
        self._generation += 1
        generation = self._generation
        try:
            process.start()
        except BaseException as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="rag_process_lifecycle",
                operation="start",
            )
            self._close_queue(command_queue)
            self._close_queue(result_queue)
            return False

        self._process = process
        self._command_queue = command_queue
        self._result_queue = result_queue
        self._started_at = time.monotonic()
        self._ready = False
        monitor = threading.Thread(
            target=self._monitor,
            args=(generation, process, result_queue),
            name=f"xbrainlab-rag-monitor-{generation}",
            daemon=True,
        )
        self._monitor_thread = monitor
        monitor.start()
        return True

    def retrieve(
        self,
        turn_id: int,
        query_text: str,
        callback: RAGResultCallback,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> bool:
        """Queue one bounded retrieval on the process-owned runtime."""
        with self._lock:
            if self._closed or self._pending is not None:
                return False
            process = self._process
            if (process is None or not process.is_alive()) and not self._spawn_locked():
                return False
            command_queue = self._command_queue
            if command_queue is None:
                return False
            self._pending = _PendingRetrieval(
                turn_id=int(turn_id),
                query=str(query_text),
                callback=callback,
                deadline=(
                    time.monotonic() + self._retrieval_timeout_seconds
                    if self._ready
                    else None
                ),
            )
            try:
                command_queue.put(
                    (
                        "retrieve",
                        int(turn_id),
                        str(query_text),
                        (
                            tuple(sorted(allowed_tool_names))
                            if allowed_tool_names is not None
                            else None
                        ),
                    )
                )
            except BaseException as exc:
                self._pending = None
                safe_unexpected_failure(
                    logger,
                    exc,
                    boundary="rag_process_lifecycle",
                    operation="queue_retrieval",
                )
                return False
            return True

    def cancel_retrieval(self, turn_id: int) -> bool:
        """Hard-cancel one active retrieval by terminating its owner process."""
        with self._lock:
            pending = self._pending
            if pending is None or pending.turn_id != int(turn_id):
                return False
            self._pending = None
            resources = self._detach_generation_locked()
        self._stop_resources(*resources, graceful=False)
        return True

    def _monitor(self, generation: int, process: Any, result_queue: Any) -> None:
        while True:
            with self._lock:
                if self._closed or generation != self._generation:
                    return
                pending = self._pending
                ready = self._ready
                started_at = self._started_at

            message: tuple[Any, ...] | None = None
            try:
                candidate = result_queue.get(timeout=_MONITOR_POLL_SECONDS)
                if isinstance(candidate, tuple):
                    message = candidate
            except queue.Empty:
                pass
            except BaseException as exc:
                safe_unexpected_failure(
                    logger,
                    exc,
                    boundary="rag_process_lifecycle",
                    operation="read_result",
                )

            if message is not None and self._handle_message(generation, message):
                continue

            now = time.monotonic()
            if not ready and now - started_at >= self._initialization_timeout_seconds:
                logger.error("RAG initialization exceeded its bounded deadline")
                self._abort_generation(
                    generation,
                    terminal=pending,
                    error=(
                        "RAG initialization timed out; continuing without RAG context."
                    ),
                )
                return
            if (
                pending is not None
                and pending.deadline is not None
                and now >= pending.deadline
            ):
                self._abort_generation(
                    generation,
                    terminal=pending,
                    error="RAG retrieval timed out; continuing without RAG context.",
                )
                return
            if not process.is_alive():
                self._abort_generation(
                    generation,
                    terminal=pending,
                    error=(
                        "RAG retrieval stopped unexpectedly; continuing without "
                        "RAG context."
                    ),
                )
                return

    def _handle_message(self, generation: int, message: tuple[Any, ...]) -> bool:
        kind = str(message[0]) if message else ""
        if kind == "ready":
            with self._lock:
                if generation != self._generation or self._closed:
                    return True
                self._ready = True
                if self._pending is not None and self._pending.deadline is None:
                    self._pending.deadline = (
                        time.monotonic() + self._retrieval_timeout_seconds
                    )
            return True
        if kind == "initialization_error":
            self._abort_generation(
                generation,
                error="RAG initialization failed; continuing without RAG context.",
            )
            return True
        if kind != "result" or len(message) != 5:
            return False

        _, turn_id, query_text, features, error = message
        callback: RAGResultCallback | None = None
        with self._lock:
            pending = self._pending
            if (
                generation == self._generation
                and not self._closed
                and pending is not None
                and pending.turn_id == int(turn_id)
            ):
                self._pending = None
                callback = pending.callback
        if callback is not None:
            callback(
                int(turn_id),
                str(query_text),
                str(features or ""),
                str(error or ""),
            )
        return True

    def _abort_generation(
        self,
        generation: int,
        *,
        terminal: _PendingRetrieval | None = None,
        error: str = "",
    ) -> None:
        with self._lock:
            if generation != self._generation:
                return
            if terminal is None:
                terminal = self._pending
            self._pending = None
            resources = self._detach_generation_locked()
        self._stop_resources(*resources, graceful=False)
        if terminal is not None and error:
            terminal.callback(terminal.turn_id, terminal.query, "", error)

    def _detach_generation_locked(self) -> tuple[Any | None, Any | None, Any | None]:
        process = self._process
        command_queue = self._command_queue
        result_queue = self._result_queue
        self._generation += 1
        self._process = None
        self._command_queue = None
        self._result_queue = None
        self._monitor_thread = None
        self._ready = False
        self._started_at = 0.0
        return process, command_queue, result_queue

    def close(self) -> bool:
        """Gracefully stop, then terminate if the child ignores shutdown."""
        with self._lock:
            if self._closed:
                process = self._process
                if process is None or not process.is_alive():
                    return True
                monitor = None
                resources = self._detach_generation_locked()
            else:
                self._closed = True
                self._pending = None
                monitor = self._monitor_thread
                resources = self._detach_generation_locked()
        stopped = self._stop_resources(*resources, graceful=True)
        if monitor is not None and monitor is not threading.current_thread():
            monitor.join(timeout=self._shutdown_wait_seconds)
            stopped = stopped and not monitor.is_alive()
        if not stopped and resources[0] is not None:
            with self._lock:
                if self._process is None:
                    self._process = resources[0]
        return stopped

    def _stop_resources(
        self,
        process: Any | None,
        command_queue: Any | None,
        result_queue: Any | None,
        *,
        graceful: bool,
    ) -> bool:
        if process is not None:
            if graceful and command_queue is not None:
                with suppress(BaseException):
                    command_queue.put(("close",))
            process.join(timeout=self._shutdown_wait_seconds if graceful else 0.05)
            if process.is_alive():
                process.terminate()
                process.join(timeout=self._shutdown_wait_seconds)
            if process.is_alive():
                kill = getattr(process, "kill", None)
                if callable(kill):
                    kill()
                    process.join(timeout=self._shutdown_wait_seconds)
        stopped = process is None or not process.is_alive()
        self._close_queue(command_queue)
        self._close_queue(result_queue)
        return stopped

    @staticmethod
    def _close_queue(target: Any | None) -> None:
        if target is None:
            return
        with suppress(BaseException):
            target.cancel_join_thread()
        with suppress(BaseException):
            target.close()
