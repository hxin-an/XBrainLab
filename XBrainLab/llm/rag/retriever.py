"""RAG retriever for querying similar examples from Qdrant.

Provides lazy initialization, auto-indexing from bundled gold-set data,
and semantic similarity search against a Qdrant vector store.
Embedding queries are executed in a background thread to avoid blocking
the Qt event loop.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_community.vectorstores import Qdrant
    from qdrant_client import QdrantClient

from .config import RAGConfig

logger = logging.getLogger(__name__)


class RAGRetriever:
    """Retrieves similar gold-set examples from a Qdrant vector store.

    Supports lazy initialization: the embedding model and Qdrant client
    are loaded on first use.  If the collection does not exist, it is
    automatically populated from the bundled ``gold_set.json``.

    Attributes:
        client: The ``QdrantClient`` instance (``None`` until initialized).
        vectorstore: The LangChain ``Qdrant`` vectorstore wrapper.
        embeddings: The HuggingFace embedding model.
        is_initialized: Whether initialization has completed successfully.

    """

    def __init__(self):
        """Initializes the RAGRetriever in an unloaded state."""
        self.client: QdrantClient | None = None
        self.vectorstore: Qdrant | None = None
        self.embeddings: HuggingFaceEmbeddings | None = None
        self.is_initialized = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rag")

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
            self.is_initialized = True
            logger.info("RAGRetriever initialized.")
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

    def close(self):
        """Closes the Qdrant client connection and releases resources."""
        if self.client:
            self.client.close()
        self._executor.shutdown(wait=False)

    def get_similar_examples(self, query: str, k: int = 3) -> str:
        """Retrieves similar gold-set examples formatted as a prompt string.

        Embeds the query in a background thread to avoid blocking the Qt
        main thread, then searches the Qdrant collection and formats
        matching examples as numbered conversation snippets.

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
            # Offload embedding to a worker thread (non-blocking for Qt)
            future = self._executor.submit(self.embeddings.embed_query, query)
            query_vector = future.result(timeout=30)

            # 2. Search using native client (bypassing LangChain issue)
            # Use query_points which supports local mode
            search_result = self.client.query_points(
                collection_name=RAGConfig.COLLECTION_NAME,
                query=query_vector,
                limit=k,
                with_payload=True,
            ).points

            if not search_result:
                return ""

            # 3. Format results
            result_str = "\n### Similar Examples:\n"
            for i, point in enumerate(search_result, 1):
                # Point payload matches what we indexed
                payload = point.payload or {}
                # LangChain stores content here
                user_input = payload.get("page_content", "")

                # Fallback if structure varies
                if not user_input:
                    user_input = payload.get("input", "")

                metadata = payload.get("metadata", {})
                if isinstance(metadata, dict):
                    tool_calls_json = metadata.get("tool_calls", "[]")
                else:
                    tool_calls_json = "[]"

                # Format as a conversation snippet
                result_str += f"\nExample {i}:\n"
                result_str += f'User: "{user_input}"\n'
                result_str += f"Assistant: ```json\n{tool_calls_json}\n```\n"

        except Exception as e:
            logger.error("Retrieval failed: %s", e)
            return ""

        return result_str
