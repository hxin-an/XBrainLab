"""RAG indexer for embedding and storing gold-set examples.

Loads gold-set JSON files, converts them into LangChain ``Document``
objects, and indexes their embeddings into a Qdrant vector store.
"""

import json
import logging

try:
    from langchain.docstore.document import Document
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_community.vectorstores import Qdrant
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as rest
except ImportError:
    # Optional dependencies — RAG is excluded from mypy
    Document = None
    HuggingFaceEmbeddings = None
    Qdrant = None
    QdrantClient = None
    rest = None

from .config import RAGConfig

logger = logging.getLogger(__name__)


class RAGIndexer:
    """Handles indexing of gold-set examples into a Qdrant collection.

    Attributes:
        embeddings: The HuggingFace sentence-transformer embedding model.
        storage_path: Absolute path to the Qdrant on-disk storage.
        client: The ``QdrantClient`` instance.

    """

    def __init__(self, client=None, embeddings=None):
        """Initializes the RAGIndexer with embedding model and Qdrant client.

        Args:
            client: Optional existing ``QdrantClient``. If ``None``, a new
                one is created from ``RAGConfig``.
            embeddings: Optional existing ``HuggingFaceEmbeddings``. If
                ``None``, a new one is created from ``RAGConfig``.

        """
        if HuggingFaceEmbeddings is None or QdrantClient is None:
            raise ImportError(
                "RAG dependencies not installed. "
                "Install with: pip install langchain-community qdrant-client"
            )
        self._owns_client = client is None
        self.embeddings = embeddings or HuggingFaceEmbeddings(
            model_name=RAGConfig.EMBEDDING_MODEL,
        )
        self.storage_path = RAGConfig.get_storage_path()

        # Initialize Client
        self.client = client or QdrantClient(path=self.storage_path)
        logger.info("Initialized Qdrant at %s", self.storage_path)

    def load_gold_set(self, json_path: str) -> list[Document]:
        """Parses a gold-set JSON file into LangChain Documents.

        Each entry in the JSON array is expected to have an ``input``
        field (used as searchable content) and optional ``id``,
        ``category``, and ``expected_tool_calls`` fields (stored as
        metadata).

        Args:
            json_path: Path to the gold-set JSON file.

        Returns:
            A list of ``Document`` objects ready for indexing.

        Raises:
            Exception: If the JSON file cannot be read or parsed.

        """
        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error("Failed to load gold set: %s", e)
            raise

        docs = []
        for item in data:
            # Content is what we search against (Subject's input)
            content = item.get("input", "")

            # Metadata contains the answer (Tool Calls)
            metadata = {
                "id": item.get("id"),
                "category": item.get("category"),
                "tool_calls": json.dumps(item.get("expected_tool_calls")),
            }

            if content:
                docs.append(Document(page_content=content, metadata=metadata))

        logger.info("Loaded %s documents from %s", len(docs), json_path)
        return docs

    def index_data(self, docs: list[Document]):
        """Embeds and indexes documents into the Qdrant collection.

        Creates the collection if it does not exist, then adds the
        provided documents using LangChain's Qdrant wrapper.

        Args:
            docs: List of ``Document`` objects to embed and store.

        Raises:
            Exception: If indexing fails.

        """
        if not docs:
            logger.warning("No documents to index.")
            return

        try:
            # Check if collection exists
            collections = self.client.get_collections().collections
            exists = any(c.name == RAGConfig.COLLECTION_NAME for c in collections)

            if not exists:
                logger.info("Creating new collection: %s", RAGConfig.COLLECTION_NAME)
                self.client.create_collection(
                    collection_name=RAGConfig.COLLECTION_NAME,
                    vectors_config=rest.VectorParams(
                        size=384,  # all-MiniLM-L6-v2 dim
                        distance=rest.Distance.COSINE,
                    ),
                )
            else:
                logger.info(
                    "Appending to existing collection: %s",
                    RAGConfig.COLLECTION_NAME,
                )

            # Use LangChain wrapper with existing client
            qdrant = Qdrant(
                client=self.client,
                collection_name=RAGConfig.COLLECTION_NAME,
                embeddings=self.embeddings,
            )
            qdrant.add_documents(docs)

            logger.info(
                "Successfully indexed %d documents to %s",
                len(docs),
                RAGConfig.COLLECTION_NAME,
            )

        except Exception as e:
            logger.error("Indexing failed: %s", e)
            raise

    def close(self):
        """Closes the Qdrant client connection and releases resources.

        Only closes the client if it was created internally (not passed in).
        """
        if self.client and self._owns_client:
            self.client.close()
