"""RAG retriever for querying similar examples from Qdrant.

Explicitly initializes a pinned local embedding and verified gold-set index.
Dense and sparse branches independently admit eligible candidates, then
reciprocal-rank fusion orders their stable-identity union. The synchronous
retriever runs through the owned RAG process lifecycle for GUI callers.
"""

from __future__ import annotations

import logging
import math
import threading
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING

from XBrainLab.llm.agent.context_encoding import (
    UntrustedContextItem,
    UntrustedContextSource,
    decode_untrusted_context,
    encode_untrusted_context,
)
from XBrainLab.llm.agent.decision_contract import MODEL_RESPONSE_TOOL_NAME

if TYPE_CHECKING:
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_qdrant import Qdrant
    from qdrant_client import QdrantClient

from .bm25 import BM25Index
from .config import RAGConfig
from .example_policy import (
    example_decision_name,
    prompt_proposal_from_metadata,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RetrievalLease:
    """Snapshot of resources used by one retrieval operation."""

    client: QdrantClient
    embeddings: HuggingFaceEmbeddings
    bm25_index: BM25Index | None
    dense_only: bool


class RAGRetriever:
    """Retrieves similar gold-set examples from a Qdrant vector store.

    Call ``initialize`` before retrieval to load the local embedding and verify
    or rebuild the collection from the bundled ``gold_set.json``.

    Hybrid mode independently retrieves dense and sparse candidates. Explicit
    ``dense_only=True`` omits sparse construction and querying for ablation.

    Attributes:
        client: The ``QdrantClient`` instance (``None`` until initialized).
        vectorstore: The LangChain ``Qdrant`` vectorstore wrapper.
        embeddings: The HuggingFace embedding model.
        is_initialized: Whether initialization has completed successfully.
        bm25_index: In-memory BM25 index for keyword scoring.
        dense_only: Whether to omit the sparse branch explicitly.

    """

    def __init__(self, *, dense_only: bool = False):
        """Initialize unloaded resources with an explicit retrieval mode."""
        if type(dense_only) is not bool:
            raise ValueError("dense_only must be a boolean")
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
        self.dense_only = dense_only

    def initialize(self) -> None:
        """Explicitly initialize the local RAG components once.

        Imports heavy dependencies, sets up the embedding model and
        Qdrant client, and auto-indexes from the bundled gold-set if
        the collection does not yet exist.  Subsequent calls are no-ops.
        """
        if not self._begin_initialize():
            return

        if not RAGConfig.embedding_cache_ready():
            logger.info(
                "RAG disabled: pinned embedding snapshot is not available locally."
            )
            self._finish_initialize_failed()
            return

        local_client: QdrantClient | None = None
        local_embeddings: HuggingFaceEmbeddings | None = None
        local_vectorstore: Qdrant | None = None
        local_bm25_index: BM25Index | None = None
        try:
            logger.info("Initializing RAGRetriever...")
            local_embeddings = self._create_embeddings()
            local_client = self._create_client()

            local_vectorstore = self._auto_initialize(
                local_client,
                local_embeddings,
            )
            self._require_verified_vectorstore(local_vectorstore)
            if not self.dense_only:
                local_bm25_index = self._build_bm25_index()
                if local_bm25_index is None:
                    # Keep resource cleanup in the initialization failure path.
                    raise RuntimeError(  # noqa: TRY301
                        "Hybrid retrieval requires a valid BM25 index"
                    )

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
            "RAGRetriever initialized (dense_only=%s).",
            self.dense_only,
        )

    @staticmethod
    def _require_verified_vectorstore(vectorstore: Qdrant | None) -> None:
        if vectorstore is None:
            raise RuntimeError("The local RAG index could not be verified.")

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
        with suppress(Exception):
            client.close()

    @staticmethod
    def _create_embeddings() -> HuggingFaceEmbeddings:
        from langchain_huggingface import HuggingFaceEmbeddings

        if not RAGConfig.embedding_cache_ready():
            raise RuntimeError("Pinned RAG embedding cache is unavailable.")
        return HuggingFaceEmbeddings(**RAGConfig.embedding_constructor_kwargs())

    @staticmethod
    def _create_client() -> QdrantClient:
        from qdrant_client import QdrantClient

        return QdrantClient(path=RAGConfig.get_storage_path())

    @staticmethod
    def _create_vectorstore(
        client: QdrantClient,
        embeddings: HuggingFaceEmbeddings,
    ) -> Qdrant:
        from langchain_qdrant import Qdrant

        return Qdrant(
            client=client,
            collection_name=RAGConfig.COLLECTION_NAME,
            embeddings=embeddings,
        )

    def _auto_initialize(
        self,
        client: QdrantClient,
        embeddings: HuggingFaceEmbeddings,
    ) -> Qdrant | None:
        """Auto-indexes from the bundled ``gold_set.json`` via RAGIndexer.

        Looks for the gold-set file at ``rag/data/gold_set.json`` and
        delegates indexing to ``RAGIndexer``.
        """
        from .indexer import RAGIndexer

        gold_set_path = RAGConfig.get_gold_set_path()
        if not RAGConfig.gold_set_integrity_ok():
            logger.warning("Gold set not found: %s", gold_set_path)
            return None

        try:
            logger.info("Delegating auto-initialization to RAGIndexer...")
            indexer = RAGIndexer(
                client=client,
                embeddings=embeddings,
            )
            docs = indexer.load_gold_set(str(gold_set_path))
            if docs:
                indexer.index_data(docs)
                vectorstore = self._create_vectorstore(
                    client,
                    embeddings,
                )
                return vectorstore
        except Exception as e:
            logger.error("RAG auto-init failed: %s", e)
        return None

    def _build_bm25_index(self) -> BM25Index | None:
        """Builds the in-memory BM25 index from the bundled gold-set.

        Failure leaves hybrid initialization unavailable, never silently labelled
        as a successful hybrid run. Explicit dense-only mode skips this build.
        """
        from pathlib import Path

        gold_set_path = Path(__file__).parent / "data" / "gold_set.json"
        if not gold_set_path.exists():
            logger.warning("BM25: gold set not found — hybrid disabled.")
            return None

        try:
            idx = BM25Index()
            idx.build_from_json(gold_set_path)
            logger.info("BM25 index ready (%d docs).", idx.doc_count)
        except Exception as e:
            logger.error("BM25 index build failed: %s", e)
            return None
        else:
            return idx

    def close(self) -> None:
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
                dense_only=self.dense_only,
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
        """Retrieve independently admitted examples, ordered by equal-weight RRF.

        Each branch contributes only its admitted ranks, never a normalized
        confidence. Hybrid requires both components; failures propagate.

        This method performs embedding and vector search synchronously. The
        production controller runs it in an isolated RAG process.

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
        safe_k = min(max(int(k), 0), RAGConfig.TOP_K)
        if safe_k == 0:
            return ""
        lease = self._acquire_retrieval_lease()
        if lease is None:
            return ""
        try:
            # ── 1. Dense (semantic) retrieval ──
            query_vector = lease.embeddings.embed_query(query)
            if self._is_closed():
                return ""

            from qdrant_client.http import models

            # Filter inside search: unavailable examples must not consume the
            # candidate budget before the eligible examples can be ranked.
            query_filter = None
            if allowed_tool_names is not None:
                query_filter = models.Filter(
                    must=[
                        models.FieldCondition(
                            key="metadata.decision_name",
                            match=models.MatchAny(
                                any=sorted(
                                    allowed_tool_names | {MODEL_RESPONSE_TOOL_NAME}
                                ),
                            ),
                        ),
                    ],
                )
            search_result = lease.client.query_points(
                collection_name=RAGConfig.COLLECTION_NAME,
                query=query_vector,
                limit=RAGConfig.CANDIDATES_PER_BRANCH,
                with_payload=True,
                query_filter=query_filter,
            ).points
            if self._is_closed():
                return ""

            dense: list[tuple[float, str, str, dict]] = []
            for point in search_result:
                score = float(point.score)
                if not math.isfinite(score) or score < RAGConfig.SIMILARITY_THRESHOLD:
                    continue
                payload = point.payload or {}
                metadata = payload.get("metadata", {})
                if not self._example_is_allowed(
                    metadata, allowed_tool_names=allowed_tool_names
                ):
                    continue
                content = payload.get("page_content", "") or payload.get(
                    "input",
                    "",
                )
                dense.append((score, metadata["id"], content, metadata))

            # Sparse eligibility is independent of the dense search result.
            sparse: list[tuple[float, str, str, dict]] = []
            if not lease.dense_only:
                if lease.bm25_index is None:
                    raise RuntimeError("Hybrid retrieval requires a valid BM25 index")
                sparse = [
                    row
                    for row in lease.bm25_index.query(
                        query,
                        k=RAGConfig.CANDIDATES_PER_BRANCH,
                        eligible=lambda metadata: self._example_is_allowed(
                            metadata, allowed_tool_names=allowed_tool_names
                        ),
                    )
                    if math.isfinite(row[0]) and row[0] > 0
                ]
            if self._is_closed():
                return ""

            candidates: dict[str, tuple[str, dict]] = {}
            fused_scores: dict[str, float] = {}
            for branch in (dense, sparse):
                seen: set[str] = set()
                for _score, doc_id, content, metadata in sorted(
                    branch, key=lambda row: (-row[0], row[1])
                ):
                    if doc_id in seen:
                        continue
                    seen.add(doc_id)
                    candidates.setdefault(doc_id, (content, metadata))
                    fused_scores[doc_id] = fused_scores.get(doc_id, 0.0) + 1.0 / (
                        RAGConfig.RRF_RANK_CONSTANT + len(seen)
                    )
            ranked_ids = sorted(
                candidates, key=lambda doc_id: (-fused_scores[doc_id], doc_id)
            )

            context_items: list[UntrustedContextItem] = []
            encoded = ""
            for doc_id in ranked_ids:
                _content, meta = candidates[doc_id]
                proposal = prompt_proposal_from_metadata(meta)
                if proposal is None:
                    continue
                data = {"input": meta.get("source_text"), "expected_proposal": proposal}
                if "prior_turn" in meta:
                    data["prior_turn"] = meta["prior_turn"]
                candidate_items = [
                    *context_items,
                    UntrustedContextItem(
                        item_type="rag_example",
                        source=UntrustedContextSource(
                            kind="xbrainlab_bundled_gold_set",
                            id=doc_id,
                            category=str(meta.get("category") or "uncategorized"),
                        ),
                        data=data,
                    ),
                ]
                candidate_encoded = encode_untrusted_context(
                    candidate_items,
                    max_chars=RAGConfig.MAX_CONTEXT_CHARS,
                    max_items=safe_k,
                    max_string_chars=RAGConfig.MAX_EXAMPLE_CONTENT_CHARS,
                )
                # A proposal and its quoted source are an indivisible example.
                # Redaction or clipping cannot publish a changed demonstration.
                if decode_untrusted_context(candidate_encoded) != tuple(
                    candidate_items
                ):
                    continue
                context_items = candidate_items
                encoded = candidate_encoded
                if len(context_items) == safe_k:
                    break
            return encoded
        finally:
            self._release_retrieval_lease()

    @staticmethod
    def _example_is_allowed(
        metadata: dict,
        *,
        allowed_tool_names: frozenset[str] | None,
    ) -> bool:
        if not isinstance(metadata.get("id"), str) or not metadata["id"]:
            return False
        decision_name = example_decision_name(metadata)
        if decision_name is None:
            return False
        if allowed_tool_names is None:
            return True
        return decision_name in (allowed_tool_names | {MODEL_RESPONSE_TOOL_NAME})
