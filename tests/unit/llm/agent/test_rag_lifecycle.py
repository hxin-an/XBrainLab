"""Lifecycle tests for controller-owned RAG initialization."""

from __future__ import annotations

import threading
import time

from XBrainLab.llm.agent.rag_lifecycle import RAGRetrieverLifecycle


class _BlockingRetriever:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.initialize_finished = threading.Event()
        self.close_calls = 0
        self.allowed_tool_names: frozenset[str] | None = None

    def initialize(self) -> None:
        self.started.set()
        self.release.wait(timeout=2)
        self.initialize_finished.set()

    def get_similar_examples(
        self,
        query: str,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> str:
        self.allowed_tool_names = allowed_tool_names
        self.started.set()
        self.release.wait(timeout=2)
        return "features"

    def close(self) -> None:
        self.close_calls += 1
        self.release.set()


def test_lifecycle_close_fences_and_joins_owned_initializer_thread() -> None:
    retriever = _BlockingRetriever()
    lifecycle = RAGRetrieverLifecycle(retriever, shutdown_wait_seconds=1.0)

    lifecycle.start()
    assert retriever.started.wait(timeout=2)

    assert lifecycle.close()

    assert retriever.initialize_finished.is_set()
    assert retriever.close_calls >= 1
    assert not lifecycle.is_initializing


def test_lifecycle_does_not_restart_after_close() -> None:
    retriever = _BlockingRetriever()
    lifecycle = RAGRetrieverLifecycle(retriever, shutdown_wait_seconds=1.0)

    assert lifecycle.close()
    lifecycle.start()

    assert not retriever.started.is_set()
    assert retriever.close_calls == 1


class _StuckRetriever:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.close_calls = 0

    def initialize(self) -> None:
        self.started.set()
        self.release.wait()

    def get_similar_examples(
        self,
        query: str,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> str:
        del allowed_tool_names
        self.started.set()
        self.release.wait()
        return "features"

    def close(self) -> None:
        self.close_calls += 1


def test_lifecycle_close_is_bounded_when_initializer_does_not_return() -> None:
    retriever = _StuckRetriever()
    lifecycle = RAGRetrieverLifecycle(retriever, shutdown_wait_seconds=0.05)

    assert lifecycle.start()
    assert retriever.started.wait(timeout=2)
    assert lifecycle.initializer_thread_daemon is True

    started = time.monotonic()
    assert lifecycle.close() is False
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert retriever.close_calls == 1
    assert lifecycle.is_initializing

    retriever.release.set()


def test_lifecycle_retrieval_close_is_bounded_and_daemon_owned() -> None:
    retriever = _StuckRetriever()
    lifecycle = RAGRetrieverLifecycle(retriever, shutdown_wait_seconds=0.05)
    callbacks: list[tuple[int, str, str, str]] = []

    assert lifecycle.retrieve(7, "query", lambda *args: callbacks.append(args))
    assert retriever.started.wait(timeout=2)
    assert lifecycle.is_retrieving
    assert lifecycle.retrieval_thread_daemon is True

    started = time.monotonic()
    assert lifecycle.close() is False
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert retriever.close_calls == 1
    assert callbacks == []

    retriever.release.set()
    time.sleep(0.05)
    assert callbacks == []


def test_lifecycle_retrieval_callback_runs_once_before_close() -> None:
    retriever = _BlockingRetriever()
    lifecycle = RAGRetrieverLifecycle(retriever, shutdown_wait_seconds=1.0)
    callbacks: list[tuple[int, str, str, str]] = []

    assert lifecycle.retrieve(
        3,
        "query",
        lambda *args: callbacks.append(args),
        allowed_tool_names=frozenset({"scan_source"}),
    )
    assert retriever.started.wait(timeout=2)
    retriever.release.set()

    deadline = time.monotonic() + 2
    while not callbacks and time.monotonic() < deadline:
        time.sleep(0.01)

    assert callbacks == [(3, "query", "features", "")]
    assert retriever.allowed_tool_names == frozenset({"scan_source"})
