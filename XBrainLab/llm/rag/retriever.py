"""RAG retriever for querying similar examples from Qdrant.

Provides lazy initialization, auto-indexing from bundled gold-set data,
and semantic similarity search against a Qdrant vector store.
Supports **hybrid retrieval** — a weighted combination of dense
(semantic) similarity and sparse (BM25 keyword) scoring — for improved
exact-match recall without sacrificing semantic coverage. The retriever
is synchronous; GUI callers must run it through the owned RAG lifecycle.
"""

from __future__ import annotations

import json
import logging
import threading
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING

from XBrainLab.llm.agent.intent import infer_user_intent

if TYPE_CHECKING:
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_community.vectorstores import Qdrant
    from qdrant_client import QdrantClient

from .bm25 import BM25Index
from .config import RAGConfig
from .example_policy import (
    prompt_tool_call_from_metadata,
)

logger = logging.getLogger(__name__)

_NON_ACTION_INTENTS = frozenset({"no_tool", "ask_clarification"})


@dataclass(frozen=True)
class _RetrievalLease:
    """Snapshot of resources used by one retrieval operation."""

    client: QdrantClient
    embeddings: HuggingFaceEmbeddings
    bm25_index: BM25Index | None
    hybrid_alpha: float


class RAGRetriever:
    """Retrieves similar gold-set examples from a Qdrant vector store.

    Supports lazy initialization: the embedding model and Qdrant client
    are loaded on first use.  If the collection does not exist, it is
    automatically populated from the bundled ``gold_set.json``.

    **Hybrid mode** (default, configurable via ``hybrid_alpha``):
    combines dense semantic scores with sparse BM25 keyword scores.
    ``alpha=1.0`` → pure semantic, ``alpha=0.0`` → pure BM25.

    Attributes:
        client: The ``QdrantClient`` instance (``None`` until initialized).
        vectorstore: The LangChain ``Qdrant`` vectorstore wrapper.
        embeddings: The HuggingFace embedding model.
        is_initialized: Whether initialization has completed successfully.
        bm25_index: In-memory BM25 index for keyword scoring.
        hybrid_alpha: Interpolation weight (1.0 = pure semantic).

    """

    # Default interpolation weight; tuned on validation split.
    DEFAULT_HYBRID_ALPHA = 0.7

    def __init__(self, hybrid_alpha: float | None = None):
        """Initializes the RAGRetriever in an unloaded state.

        Args:
            hybrid_alpha: Optional semantic weight override.  When
                ``None``, ``DEFAULT_HYBRID_ALPHA`` is used.
        """
        self.client: QdrantClient | None = None
        self.vectorstore: Qdrant | None = None
        self.embeddings: HuggingFaceEmbeddings | None = None
        self.is_initialized = False
        self._lifecycle = threading.Condition(threading.Lock())
        self._initializing = False
        self._closed = False
        self._active_operations = 0
        self._retired_clients: list[QdrantClient] = []
        self.bm25_index: BM25Index | None = None
        self.hybrid_alpha: float = (
            hybrid_alpha if hybrid_alpha is not None else self.DEFAULT_HYBRID_ALPHA
        )

    def initialize(self) -> None:
        """Lazily initializes RAG components.

        Imports heavy dependencies, sets up the embedding model and
        Qdrant client, and auto-indexes from the bundled gold-set if
        the collection does not yet exist.  Subsequent calls are no-ops.
        """
        if not self._begin_initialize():
            return

        local_client: QdrantClient | None = None
        local_embeddings: HuggingFaceEmbeddings | None = None
        local_vectorstore: Qdrant | None = None
        local_bm25_index: BM25Index | None = None
        try:
            logger.info("Initializing RAGRetriever...")
            local_embeddings = self._create_embeddings()
            local_client = self._create_client()

            if not self._collection_exists(local_client):
                logger.info("RAG collection not found, auto-initializing...")
                local_vectorstore = self._auto_initialize(
                    client=local_client,
                    embeddings=local_embeddings,
                    publish=False,
                )

            local_vectorstore = local_vectorstore or self._create_vectorstore(
                local_client,
                local_embeddings,
            )
            local_bm25_index = self._build_bm25_index(publish=False)

        except Exception as e:
            logger.error("Failed to init RAGRetriever: %s", e)
            self._finish_initialize_failed()
            if local_client is not None:
                self._close_client(local_client)
            return

        with self._lifecycle:
            if self._closed:
                self._initializing = False
                self._lifecycle.notify_all()
                if local_client is not None:
                    self._close_client(local_client)
                return

            self.embeddings = local_embeddings
            self.client = local_client
            self.vectorstore = local_vectorstore
            self.bm25_index = local_bm25_index
            self.is_initialized = True
            self._initializing = False
            self._lifecycle.notify_all()
            local_client = None

        logger.info(
            "RAGRetriever initialized (hybrid_alpha=%.2f).",
            self.hybrid_alpha,
        )

    def _begin_initialize(self) -> bool:
        """Reserve the single initializer slot unless closed or ready."""
        with self._lifecycle:
            if self._closed or self.is_initialized:
                return False
            while self._initializing:
                self._lifecycle.wait()
                if self._closed or self.is_initialized:
                    return False
            self._initializing = True
            return True

    def _finish_initialize_failed(self) -> None:
        with self._lifecycle:
            if not self._closed:
                self.client = None
                self.vectorstore = None
                self.embeddings = None
                self.bm25_index = None
                self.is_initialized = False
            self._initializing = False
            self._lifecycle.notify_all()

    @staticmethod
    def _close_client(client: QdrantClient) -> None:
        close = getattr(client, "close", None)
        if callable(close):
            with suppress(Exception):
                close()

    @staticmethod
    def _create_embeddings() -> HuggingFaceEmbeddings:
        from langchain_community.embeddings import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(model_name=RAGConfig.EMBEDDING_MODEL)

    @staticmethod
    def _create_client() -> QdrantClient:
        from qdrant_client import QdrantClient

        return QdrantClient(path=RAGConfig.get_storage_path())

    @staticmethod
    def _create_vectorstore(
        client: QdrantClient,
        embeddings: HuggingFaceEmbeddings,
    ) -> Qdrant:
        from langchain_community.vectorstores import Qdrant

        return Qdrant(
            client=client,
            collection_name=RAGConfig.COLLECTION_NAME,
            embeddings=embeddings,
        )

    def _collection_exists(self, client: QdrantClient | None = None) -> bool:
        """Checks whether the RAG collection exists in Qdrant.

        Returns:
            ``True`` if the collection is present, ``False`` otherwise.

        """
        target_client = client or self.client
        if not target_client:
            return False
        try:
            cols = target_client.get_collections().collections
            return any(c.name == RAGConfig.COLLECTION_NAME for c in cols)
        except Exception:
            logger.debug("Failed to check Qdrant collection existence", exc_info=True)
            return False

    def _auto_initialize(
        self,
        client: QdrantClient | None = None,
        embeddings: HuggingFaceEmbeddings | None = None,
        *,
        publish: bool = True,
    ) -> Qdrant | None:
        """Auto-indexes from the bundled ``gold_set.json`` via RAGIndexer.

        Looks for the gold-set file at ``rag/data/gold_set.json`` and
        delegates indexing to ``RAGIndexer``.
        """
        from pathlib import Path

        from .indexer import RAGIndexer

        gold_set_path = Path(__file__).parent / "data" / "gold_set.json"
        if not gold_set_path.exists():
            logger.warning("Gold set not found: %s", gold_set_path)
            return None

        target_client = client or self.client
        target_embeddings = embeddings or self.embeddings
        if target_client is None or target_embeddings is None:
            logger.warning("RAG auto-init skipped: client or embeddings missing.")
            return None
        try:
            logger.info("Delegating auto-initialization to RAGIndexer...")
            indexer = RAGIndexer(
                client=target_client,
                embeddings=target_embeddings,
            )
            try:
                docs = indexer.load_gold_set(str(gold_set_path))
                if docs:
                    indexer.index_data(docs)
                    vectorstore = self._create_vectorstore(
                        target_client,
                        target_embeddings,
                    )
                    if publish:
                        self.vectorstore = vectorstore
                    return vectorstore
            finally:
                indexer.close()
        except Exception as e:
            logger.error("RAG auto-init failed: %s", e)
        return None

    def _build_bm25_index(self, *, publish: bool = True) -> BM25Index | None:
        """Builds the in-memory BM25 index from the bundled gold-set.

        Falls back gracefully if the gold-set file is missing — hybrid
        retrieval degrades to pure semantic search.
        """
        from pathlib import Path

        gold_set_path = Path(__file__).parent / "data" / "gold_set.json"
        if not gold_set_path.exists():
            logger.warning("BM25: gold set not found — hybrid disabled.")
            return None

        try:
            idx = BM25Index()
            idx.build_from_json(gold_set_path)
            if publish:
                self.bm25_index = idx
            logger.info("BM25 index ready (%d docs).", idx.doc_count)
        except Exception as e:
            logger.error("BM25 index build failed: %s", e)
            return None
        else:
            return idx

    def close(self, *, wait: bool = False) -> None:
        """Closes the Qdrant client connection and releases resources."""
        close_now: QdrantClient | None = None
        with self._lifecycle:
            self._closed = True
            client = self.client
            self.client = None
            self.vectorstore = None
            self.embeddings = None
            self.bm25_index = None
            self.is_initialized = False
            self._lifecycle.notify_all()
            if client is not None:
                if self._active_operations > 0:
                    self._retired_clients.append(client)
                else:
                    close_now = client

        if close_now is not None:
            self._close_client(close_now)
        _ = wait

    def _acquire_retrieval_lease(self) -> _RetrievalLease | None:
        """Fence-aware snapshot for one retrieval without holding the lock."""
        with self._lifecycle:
            if self._closed or self.client is None or self.embeddings is None:
                return None
            self._active_operations += 1
            return _RetrievalLease(
                client=self.client,
                embeddings=self.embeddings,
                bm25_index=self.bm25_index,
                hybrid_alpha=self.hybrid_alpha,
            )

    def _release_retrieval_lease(self) -> None:
        close_later: list[QdrantClient] = []
        with self._lifecycle:
            if self._active_operations > 0:
                self._active_operations -= 1
            if self._closed and self._active_operations == 0:
                close_later = list(self._retired_clients)
                self._retired_clients.clear()
            self._lifecycle.notify_all()
        for client in close_later:
            self._close_client(client)

    def _is_closed(self) -> bool:
        with self._lifecycle:
            return self._closed

    def get_similar_examples(
        self,
        query: str,
        k: int = 3,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> str:
        """Retrieves similar gold-set examples via hybrid ranking.

        Combines dense (Qdrant cosine) and sparse (BM25 keyword)
        scores with a weighted interpolation controlled by
        ``self.hybrid_alpha``.  When BM25 is unavailable, falls back
        to pure semantic search.

        This method performs embedding and vector search synchronously. The
        controller uses ``RAGRetrieverLifecycle`` to run it off the GUI thread.

        Args:
            query: The user's input text to find similar examples for.
            k: Maximum number of examples to retrieve.
            allowed_tool_names: Exact request-scoped tools whose examples may
                be injected. ``None`` keeps standalone retrieval behavior.

        Returns:
            A formatted string of similar examples suitable for prompt
            injection, or an empty string if RAG is unavailable or no
            matches are found.

        """
        if infer_user_intent(query) in _NON_ACTION_INTENTS:
            return ""
        lease = self._acquire_retrieval_lease()
        if lease is None:
            return ""
        try:
            # ── 1. Dense (semantic) retrieval ──
            query_vector = lease.embeddings.embed_query(query)
            if self._is_closed():
                return ""

            # Fetch more candidates for re-ranking
            dense_k = max(k * 3, 10)
            search_result = lease.client.query_points(
                collection_name=RAGConfig.COLLECTION_NAME,
                query=query_vector,
                limit=dense_k,
                with_payload=True,
            ).points
            if self._is_closed():
                return ""

            if not search_result:
                return ""

            # ── 2. Build candidate pool with dense scores ──
            # Normalize dense scores to [0,1] via min-max
            raw_scores = [p.score for p in search_result]
            s_min, s_max = min(raw_scores), max(raw_scores)
            s_range = s_max - s_min if s_max > s_min else 1.0

            candidates: dict[str, dict] = {}
            for p in search_result:
                payload = p.payload or {}
                content = payload.get("page_content", "") or payload.get(
                    "input",
                    "",
                )
                doc_id = str(p.id)
                norm_dense = (p.score - s_min) / s_range
                candidates[doc_id] = {
                    "content": content,
                    "metadata": payload.get("metadata", {}),
                    "dense_score": norm_dense,
                    "bm25_score": 0.0,
                }
            candidates = {
                doc_id: candidate
                for doc_id, candidate in candidates.items()
                if self._example_is_allowed(
                    candidate.get("metadata", {}),
                    allowed_tool_names=allowed_tool_names,
                )
            }

            # ── 3. BM25 sparse scoring (if available) ──
            if lease.bm25_index is not None:
                bm25_results = lease.bm25_index.query(query, k=dense_k)
                if self._is_closed():
                    return ""
                if bm25_results:
                    bm25_max = bm25_results[0][0]  # already sorted desc
                    for score, bm_id, bm_text, bm_meta in bm25_results:
                        norm_bm25 = score / bm25_max if bm25_max > 0 else 0.0
                        # Try to match to dense candidate by content
                        matched = False
                        for cval in candidates.values():
                            if cval["content"] == bm_text:
                                cval["bm25_score"] = norm_bm25
                                matched = True
                                break
                        if not matched:
                            # BM25-only candidate
                            candidates[f"bm25_{bm_id}"] = {
                                "content": bm_text,
                                "metadata": bm_meta,
                                "dense_score": 0.0,
                                "bm25_score": norm_bm25,
                            }

            # ── 4. Hybrid interpolation ──
            alpha = lease.hybrid_alpha
            ranked: list[tuple[float, str, dict]] = []
            for c in candidates.values():
                if not self._example_is_allowed(
                    c.get("metadata", {}),
                    allowed_tool_names=allowed_tool_names,
                ):
                    continue
                hybrid = alpha * c["dense_score"] + (1 - alpha) * c["bm25_score"]
                ranked.append((hybrid, c["content"], c["metadata"]))

            ranked.sort(key=lambda x: x[0], reverse=True)
            if not ranked or self._is_closed():
                return ""

            # ── 5. Format top-k ──
            result_str = "\n### Similar Examples:\n"
            for i, (_score, content, meta) in enumerate(ranked[:k], 1):
                prompt_call = prompt_tool_call_from_metadata(meta)
                if prompt_call is None:
                    continue
                result_str += f"\nExample {i}:\n"
                result_str += f'User: "{content}"\n'
                result_str += "Assistant:\n"
                result_str += json.dumps(
                    prompt_call,
                    ensure_ascii=False,
                )
                result_str += "\n"
        except Exception as e:
            logger.error("Hybrid retrieval failed: %s", e)
            return ""
        else:
            return result_str
        finally:
            self._release_retrieval_lease()

    @staticmethod
    def _example_is_allowed(
        metadata: dict,
        *,
        allowed_tool_names: frozenset[str] | None,
    ) -> bool:
        prompt_call = prompt_tool_call_from_metadata(metadata)
        if prompt_call is None:
            return False
        if allowed_tool_names is None:
            return True
        return prompt_call["tool_name"] in allowed_tool_names
