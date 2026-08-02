"""Owned lifecycle for background RAG retriever initialization."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Protocol

from XBrainLab.llm.tools.result_contract import safe_unexpected_failure

logger = logging.getLogger(__name__)


class RAGLifecycleRetriever(Protocol):
    """Minimal retriever contract needed by the lifecycle owner."""

    def initialize(self) -> None: ...

    def get_similar_examples(
        self,
        query: str,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> str: ...

    def close(self) -> None: ...


RAGResultCallback = Callable[[int, str, str, str], None]


class RAGRetrieverLifecycle:
    """Own the background RAG initialization thread and bounded shutdown."""

    def __init__(
        self,
        retriever: RAGLifecycleRetriever,
        *,
        shutdown_wait_seconds: float = 2.0,
    ) -> None:
        self.retriever = retriever
        self._shutdown_wait_seconds = shutdown_wait_seconds
        self._lock = threading.Lock()
        self._closed = False
        self._init_thread: threading.Thread | None = None
        self._retrieval_thread: threading.Thread | None = None
        self._retrieval_turn_id: int | None = None
        self._cancelled_turns: set[int] = set()

    @property
    def is_initializing(self) -> bool:
        """Return whether the owned initializer thread is still running."""
        with self._lock:
            thread = self._init_thread
        return bool(thread and thread.is_alive())

    @property
    def initializer_thread_daemon(self) -> bool:
        """Return whether the owned initializer cannot block process exit."""
        with self._lock:
            thread = self._init_thread
        return bool(thread and thread.daemon)

    @property
    def is_retrieving(self) -> bool:
        """Return whether an owned retrieval worker is still running."""
        with self._lock:
            thread = self._retrieval_thread
        return bool(thread and thread.is_alive())

    @property
    def retrieval_thread_daemon(self) -> bool:
        """Return whether the owned retrieval worker cannot block process exit."""
        with self._lock:
            thread = self._retrieval_thread
        return bool(thread and thread.daemon)

    def start(self) -> bool:
        """Start initialization exactly once while the lifecycle is open."""
        with self._lock:
            if self._closed:
                return False
            if self._init_thread is not None and self._init_thread.is_alive():
                return False
            self._init_thread = threading.Thread(
                target=self._run_initialize,
                name="xbrainlab-rag-initializer",
                daemon=True,
            )
            self._init_thread.start()
            return True

    def _run_initialize(self) -> None:
        with self._lock:
            if self._closed:
                return
        try:
            self.retriever.initialize()
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="rag_retriever_lifecycle",
                operation="initialize",
            )

    def retrieve(
        self,
        turn_id: int,
        query: str,
        callback: RAGResultCallback,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> bool:
        """Start one owned daemon retrieval if lifecycle is open and idle."""
        with self._lock:
            if self._closed:
                return False
            if self._retrieval_thread is not None and self._retrieval_thread.is_alive():
                return False
            self._retrieval_thread = threading.Thread(
                target=self._run_retrieve,
                args=(turn_id, query, allowed_tool_names, callback),
                name=f"xbrainlab-rag-retrieval-{turn_id}",
                daemon=True,
            )
            self._retrieval_turn_id = int(turn_id)
            self._retrieval_thread.start()
            return True

    def _run_retrieve(
        self,
        turn_id: int,
        query: str,
        allowed_tool_names: frozenset[str] | None,
        callback: RAGResultCallback,
    ) -> None:
        features = ""
        error = ""
        try:
            features = self.retriever.get_similar_examples(
                query,
                allowed_tool_names=allowed_tool_names,
            )
        except Exception as exc:
            failure = safe_unexpected_failure(
                logger,
                exc,
                boundary="rag_retriever_lifecycle",
                operation="retrieve",
            )
            error = failure.message

        with self._lock:
            cancelled = turn_id in self._cancelled_turns
            self._cancelled_turns.discard(turn_id)
            if self._closed or cancelled:
                return
            if self._retrieval_turn_id == turn_id:
                self._retrieval_turn_id = None
        callback(turn_id, query, features, error)

    def cancel_retrieval(self, turn_id: int) -> bool:
        """Fence an injected retrieval; production uses process hard-cancel."""
        cancel = getattr(self.retriever, "cancel_retrieval", None)
        with self._lock:
            if self._retrieval_turn_id != int(turn_id):
                return False
            self._cancelled_turns.add(int(turn_id))
            self._retrieval_turn_id = None
        if callable(cancel):
            try:
                cancel()
            except Exception as exc:
                safe_unexpected_failure(
                    logger,
                    exc,
                    boundary="rag_retriever_lifecycle",
                    operation="cancel_retrieval",
                )
        return True

    def close(self) -> bool:
        """Fence retriever work, then join owned threads for bounded time."""
        with self._lock:
            should_close = not self._closed
            self._closed = True
            init_thread = self._init_thread
            retrieval_thread = self._retrieval_thread

        if should_close:
            try:
                self.retriever.close()
            except Exception as exc:
                safe_unexpected_failure(
                    logger,
                    exc,
                    boundary="rag_retriever_lifecycle",
                    operation="close",
                )

        ok = True
        for thread, label in (
            (init_thread, "initializer"),
            (retrieval_thread, "retrieval"),
        ):
            if thread is None or not thread.is_alive():
                continue
            thread.join(timeout=self._shutdown_wait_seconds)
            if thread.is_alive():
                logger.error("RAG %s did not stop within timeout", label)
                ok = False
        return ok
