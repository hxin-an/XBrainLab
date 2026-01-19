import logging

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Qdrant
from qdrant_client import QdrantClient

from .config import RAGConfig

logger = logging.getLogger(__name__)


class RAGRetriever:
    """Handles retrieval of similar examples from Qdrant."""

    def __init__(self):
        self.client: QdrantClient | None = None
        self.vectorstore: Qdrant | None = None
        self.embeddings: HuggingFaceEmbeddings | None = None

        try:
            self.embeddings = HuggingFaceEmbeddings(
                model_name=RAGConfig.EMBEDDING_MODEL
            )

            # Initialize Client explicitly
            self.client = QdrantClient(path=RAGConfig.get_storage_path())

            # Load existing collection
            self.vectorstore = Qdrant(
                client=self.client,
                collection_name=RAGConfig.COLLECTION_NAME,
                embeddings=self.embeddings,
            )
            logger.info("RAGRetriever initialized.")
        except Exception as e:
            logger.error(f"Failed to init RAGRetriever: {e}")
            self.vectorstore = None
            self.client = None

    def close(self):
        """Closes the Qdrant client connection."""
        if self.client:
            self.client.close()

    def get_similar_examples(self, query: str, k: int = 3) -> str:
        """
        Retrieves similar examples and formats them as a string.
        Returns empty string if RAG is disabled or failed.
        """
        if not self.client or not self.embeddings:
            return ""

        try:
            # 1. Embed the query
            query_vector = self.embeddings.embed_query(query)

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
            logger.error(f"Retrieval failed: {e}")
            return ""

        return result_str
