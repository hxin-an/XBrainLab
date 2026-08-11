"""Production RAG process ownership and hard-stop regressions."""

from __future__ import annotations

import threading
import time
from typing import Any

from XBrainLab.llm.agent.rag_process_lifecycle import (
    ProcessRAGRetrieverLifecycle,
)

_CALLBACK_WAIT_SECONDS = 30.0


def _responsive_worker(command_queue: Any, result_queue: Any) -> None:
    result_queue.put(("ready", True))
    while True:
        command = command_queue.get()
        if command[0] == "close":
            return
        if command[0] == "retrieve":
            _, turn_id, query, _allowed_names = command
            result_queue.put(("result", turn_id, query, "features", ""))


def _stuck_worker(command_queue: Any, result_queue: Any) -> None:
    result_queue.put(("ready", True))
    while True:
        command = command_queue.get()
        if command[0] == "close":
            return
        if command[0] == "retrieve":
            time.sleep(30.0)


def _initialization_error_worker(command_queue: Any, result_queue: Any) -> None:
    del command_queue
    result_queue.put(("initialization_error", "RuntimeError"))


def _initialization_stuck_worker(command_queue: Any, result_queue: Any) -> None:
    del command_queue, result_queue
    time.sleep(30.0)


class _TerminateIgnoringProcess:
    def __init__(self) -> None:
        self.alive = True
        self.terminate_calls = 0
        self.kill_calls = 0

    def join(self, timeout: float) -> None:
        del timeout

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1
        self.alive = False


def test_process_lifecycle_delivers_result_and_closes_without_child() -> None:
    lifecycle = ProcessRAGRetrieverLifecycle(
        process_target=_responsive_worker,
        retrieval_timeout_seconds=2.0,
        shutdown_wait_seconds=0.5,
    )
    callback_ready = threading.Event()
    callbacks: list[tuple[int, str, str, str]] = []

    assert lifecycle.start()
    assert lifecycle.retrieve(
        4,
        "query",
        lambda *args: (callbacks.append(args), callback_ready.set()),
    )
    assert callback_ready.wait(timeout=_CALLBACK_WAIT_SECONDS)

    assert callbacks == [(4, "query", "features", "")]
    assert lifecycle.close() is True
    assert lifecycle.has_active_process is False


def test_process_lifecycle_timeout_terminates_stuck_child() -> None:
    lifecycle = ProcessRAGRetrieverLifecycle(
        process_target=_stuck_worker,
        retrieval_timeout_seconds=0.1,
        shutdown_wait_seconds=0.5,
    )
    callback_ready = threading.Event()
    callbacks: list[tuple[int, str, str, str]] = []

    assert lifecycle.start()
    assert lifecycle.retrieve(
        5,
        "query",
        lambda *args: (callbacks.append(args), callback_ready.set()),
    )
    assert callback_ready.wait(timeout=_CALLBACK_WAIT_SECONDS)

    assert callbacks[0][:3] == (5, "query", "")
    assert "timed out" in callbacks[0][3]
    assert lifecycle.has_active_process is False
    assert lifecycle.close() is True


def test_process_lifecycle_cancel_terminates_stuck_child_without_callback() -> None:
    lifecycle = ProcessRAGRetrieverLifecycle(
        process_target=_stuck_worker,
        retrieval_timeout_seconds=10.0,
        shutdown_wait_seconds=0.5,
    )
    callbacks: list[tuple[int, str, str, str]] = []

    assert lifecycle.start()
    assert lifecycle.retrieve(6, "query", lambda *args: callbacks.append(args))
    time.sleep(0.1)

    assert lifecycle.cancel_retrieval(6) is True
    assert lifecycle.has_active_process is False
    assert callbacks == []
    assert lifecycle.close() is True


def test_process_lifecycle_initialization_error_releases_pending_retrieval() -> None:
    lifecycle = ProcessRAGRetrieverLifecycle(
        process_target=_initialization_error_worker,
        initialization_timeout_seconds=20.0,
        shutdown_wait_seconds=0.5,
    )
    callback_ready = threading.Event()
    callbacks: list[tuple[int, str, str, str]] = []

    assert lifecycle.start()
    assert lifecycle.retrieve(
        7,
        "query",
        lambda *args: (callbacks.append(args), callback_ready.set()),
    )
    assert callback_ready.wait(timeout=_CALLBACK_WAIT_SECONDS)

    assert callbacks[0][:3] == (7, "query", "")
    assert "initialization failed" in callbacks[0][3].casefold()
    assert lifecycle.has_active_process is False
    assert lifecycle.close() is True


def test_process_lifecycle_initialization_timeout_releases_pending_retrieval() -> None:
    lifecycle = ProcessRAGRetrieverLifecycle(
        process_target=_initialization_stuck_worker,
        initialization_timeout_seconds=0.1,
        shutdown_wait_seconds=0.5,
    )
    callback_ready = threading.Event()
    callbacks: list[tuple[int, str, str, str]] = []

    assert lifecycle.start()
    assert lifecycle.retrieve(
        8,
        "query",
        lambda *args: (callbacks.append(args), callback_ready.set()),
    )
    assert callback_ready.wait(timeout=_CALLBACK_WAIT_SECONDS)

    assert callbacks[0][:3] == (8, "query", "")
    assert "initialization timed out" in callbacks[0][3].casefold()
    assert lifecycle.has_active_process is False
    assert lifecycle.close() is True


def test_process_lifecycle_escalates_from_terminate_to_kill() -> None:
    lifecycle = ProcessRAGRetrieverLifecycle(shutdown_wait_seconds=0.01)
    process = _TerminateIgnoringProcess()

    stopped = lifecycle._stop_resources(
        process,
        None,
        None,
        graceful=False,
    )

    assert stopped is True
    assert process.terminate_calls == 1
    assert process.kill_calls == 1
