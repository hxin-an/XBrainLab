"""RAG retriever for querying similar examples from Qdrant.

Provides lazy initialization, auto-indexing from bundled gold-set data,
and semantic similarity search against a Qdrant vector store.
Supports **hybrid retrieval** — a weighted combination of dense
(semantic) similarity and sparse (BM25 keyword) scoring — for improved
exact-match recall without sacrificing semantic coverage.

Embedding queries are executed in a background thread to avoid blocking
the Qt event loop.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_community.vectorstores import Qdrant
    from qdrant_client import QdrantClient

from .bm25 import BM25Index
from .config import RAGConfig

logger = logging.getLogger(__name__)


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
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rag")
        self.bm25_index: BM25Index | None = None
        self.hybrid_alpha: float = (
            hybrid_alpha if hybrid_alpha is not None else self.DEFAULT_HYBRID_ALPHA
        )

    def initialize(self):
        """Lazily initializes RAG components.

        Imports heavy dependencies, sets up the embedding model and
        Qdrant client, and auto-indexes from the bundled gold-set if
        the collection does not yet exist.  Subsequent calls are no-ops.
        """
        if self.is_initialized:
            return

        try:
            logger.info("Initializing RAGRetriever...")
            from langchain_community.embeddings import HuggingFaceEmbeddings
            from langchain_community.vectorstores import Qdrant
            from qdrant_client import QdrantClient

            self.embeddings = HuggingFaceEmbeddings(
                model_name=RAGConfig.EMBEDDING_MODEL,
            )

            # Initialize Client explicitly
            self.client = QdrantClient(path=RAGConfig.get_storage_path())

            # Auto-initialize if collection doesn't exist
            if not self._collection_exists():
                logger.info("RAG collection not found, auto-initializing...")
                self._auto_initialize()

            # Load existing collection
            self.vectorstore = Qdrant(
                client=self.client,
                collection_name=RAGConfig.COLLECTION_NAME,
                embeddings=self.embeddings,
            )

            # Build BM25 index for hybrid retrieval
            self._build_bm25_index()

            self.is_initialized = True
            logger.info(
                "RAGRetriever initialized (hybrid_alpha=%.2f).",
                self.hybrid_alpha,
            )
        except Exception as e:
            logger.error("Failed to init RAGRetriever: %s", e)
            self.vectorstore = None
            self.client = None

    def _collection_exists(self) -> bool:
        """Checks whether the RAG collection exists in Qdrant.

        Returns:
            ``True`` if the collection is present, ``False`` otherwise.

        """
        if not self.client:
            return False
        try:
            cols = self.client.get_collections().collections
            return any(c.name == RAGConfig.COLLECTION_NAME for c in cols)
        except Exception:
            logger.debug("Failed to check Qdrant collection existence", exc_info=True)
            return False

    def _auto_initialize(self):
        """Auto-indexes from the bundled ``gold_set.json`` via RAGIndexer.

        Looks for the gold-set file at ``rag/data/gold_set.json`` and
        delegates indexing to ``RAGIndexer``.
        """
        from pathlib import Path

        from langchain_community.vectorstores import Qdrant

        from .indexer import RAGIndexer

        gold_set_path = Path(__file__).parent / "data" / "gold_set.json"
        if not gold_set_path.exists():
            logger.warning("Gold set not found: %s", gold_set_path)
            return

        try:
            logger.info("Delegating auto-initialization to RAGIndexer...")
            indexer = RAGIndexer(
                client=self.client,
                embeddings=self.embeddings,
            )
            try:
                docs = indexer.load_gold_set(str(gold_set_path))
                if docs:
                    indexer.index_data(docs)
                    # Re-initialize vectorstore after indexing
                    self.vectorstore = Qdrant(
                        client=self.client,
                        collection_name=RAGConfig.COLLECTION_NAME,
                        embeddings=self.embeddings,
                    )
            finally:
                indexer.close()
        except Exception as e:
            logger.error("RAG auto-init failed: %s", e)

    def _build_bm25_index(self):
        """Builds the in-memory BM25 index from the bundled gold-set.

        Falls back gracefully if the gold-set file is missing — hybrid
        retrieval degrades to pure semantic search.
        """
        from pathlib import Path

        gold_set_path = Path(__file__).parent / "data" / "gold_set.json"
        if not gold_set_path.exists():
            logger.warning("BM25: gold set not found — hybrid disabled.")
            return

        try:
            idx = BM25Index()
            idx.build_from_json(gold_set_path)
            self.bm25_index = idx
            logger.info("BM25 index ready (%d docs).", idx.doc_count)
        except Exception as e:
            logger.error("BM25 index build failed: %s", e)

    def close(self):
        """Closes the Qdrant client connection and releases resources."""
        if self.client:
            self.client.close()
        self._executor.shutdown(wait=False)

    def get_similar_examples(self, query: str, k: int = 3) -> str:
        """Retrieves similar gold-set examples via hybrid ranking.

        Combines dense (Qdrant cosine) and sparse (BM25 keyword)
        scores with a weighted interpolation controlled by
        ``self.hybrid_alpha``.  When BM25 is unavailable, falls back
        to pure semantic search.

        Embedding is performed in a background thread to avoid
        blocking the Qt main loop.

        Args:
            query: The user's input text to find similar examples for.
            k: Maximum number of examples to retrieve.

        Returns:
            A formatted string of similar examples suitable for prompt
            injection, or an empty string if RAG is unavailable or no
            matches are found.

        """
        if not self.client or not self.embeddings:
            return ""

        try:
            # ── 1. Dense (semantic) retrieval ──
            future = self._executor.submit(self.embeddings.embed_query, query)
            query_vector = future.result(timeout=30)

            # Fetch more candidates for re-ranking
            dense_k = max(k * 3, 10)
            search_result = self.client.query_points(
                collection_name=RAGConfig.COLLECTION_NAME,
                query=query_vector,
                limit=dense_k,
                with_payload=True,
            ).points

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
                content = payload.get("page_content", "") or payload.get("input", "")
                doc_id = str(p.id)
                norm_dense = (p.score - s_min) / s_range
                candidates[doc_id] = {
                    "content": content,
                    "metadata": payload.get("metadata", {}),
                    "dense_score": norm_dense,
                    "bm25_score": 0.0,
                }

            # ── 3. BM25 sparse scoring (if available) ──
            if self.bm25_index is not None:
                bm25_results = self.bm25_index.query(query, k=dense_k)
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
            alpha = self.hybrid_alpha
            ranked: list[tuple[float, str, dict]] = []
            for c in candidates.values():
                hybrid = alpha * c["dense_score"] + (1 - alpha) * c["bm25_score"]
                ranked.append((hybrid, c["content"], c["metadata"]))

            ranked.sort(key=lambda x: x[0], reverse=True)

            # ── 5. Format top-k ──
            result_str = "\n### Similar Examples:\n"
            for i, (_score, content, meta) in enumerate(ranked[:k], 1):
                tool_calls_json = (
                    meta.get("tool_calls", "[]") if isinstance(meta, dict) else "[]"
                )
                result_str += f"\nExample {i}:\n"
                result_str += f'User: "{content}"\n'
                result_str += f"Assistant: ```json\n{tool_calls_json}\n```\n"
        except Exception as e:
            logger.error("Hybrid retrieval failed: %s", e)
            return ""
        else:
            return result_str
