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
    """Handles indexing of gold set examples into Qdrant."""

    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(model_name=RAGConfig.EMBEDDING_MODEL)
        self.storage_path = RAGConfig.get_storage_path()

        # Initialize Client
        self.client = QdrantClient(path=self.storage_path)
        logger.info(f"Initialized Qdrant at {self.storage_path}")

    def load_gold_set(self, json_path: str) -> list[Document]:
        """Parses gold_set.json into LangChain Documents."""
        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load gold set: {e}")
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

        logger.info(f"Loaded {len(docs)} documents from {json_path}")
        return docs

    def index_data(self, docs: list[Document]):
        """Embeds and indexes documents into Qdrant."""
        if not docs:
            logger.warning("No documents to index.")
            return

        try:
            # Check if collection exists
            collections = self.client.get_collections().collections
            exists = any(c.name == RAGConfig.COLLECTION_NAME for c in collections)

            if not exists:
                logger.info(f"Creating new collection: {RAGConfig.COLLECTION_NAME}")
                self.client.create_collection(
                    collection_name=RAGConfig.COLLECTION_NAME,
                    vectors_config=rest.VectorParams(
                        size=384,  # all-MiniLM-L6-v2 dim
                        distance=rest.Distance.COSINE,
                    ),
                )
            else:
                logger.info(
                    f"Appending to existing collection: {RAGConfig.COLLECTION_NAME}"
                )

            # Use LangChain wrapper with existing client
            qdrant = Qdrant(
                client=self.client,
                collection_name=RAGConfig.COLLECTION_NAME,
                embeddings=self.embeddings,
            )
            qdrant.add_documents(docs)

            logger.info(
                f"Successfully indexed {len(docs)} documents to "
                f"{RAGConfig.COLLECTION_NAME}"
            )

        except Exception as e:
            logger.error(f"Indexing failed: {e}")
            raise

    def close(self):
        """Closes the Qdrant client connection."""
        if self.client:
            self.client.close()
