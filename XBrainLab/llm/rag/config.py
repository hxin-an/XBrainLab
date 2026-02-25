"""RAG configuration constants.

Centralizes embedding model selection, Qdrant collection naming,
retrieval thresholds, and storage path resolution.
"""

from pathlib import Path


class RAGConfig:
    """Configuration for Retrieval-Augmented Generation.

    Attributes:
        COLLECTION_NAME: Name of the Qdrant collection storing gold-set
            example embeddings.
        EMBEDDING_MODEL: Sentence-transformer model name used for
            embedding queries and documents.
        SIMILARITY_THRESHOLD: Minimum cosine similarity for a retrieved
            example to be considered relevant.
        TOP_K: Number of nearest examples to retrieve per query.
    """

    # Qdrant Settings
    COLLECTION_NAME = "gold_set_examples"

    # QDRANT_PATH is now dynamic in get_storage_path() to ensure it's inside the package

    # Embedding Model
    # Using a small, fast model suitable for CPU
    EMBEDDING_MODEL = "all-MiniLM-L6-v2"

    # Retrieval Settings
    SIMILARITY_THRESHOLD = 0.7  # Minimum similarity to be considered relevant
    TOP_K = 3  # Number of examples to retrieve

    @staticmethod
    def get_storage_path() -> str:
        """Returns the absolute path to the Qdrant storage directory.

        The directory is created if it does not already exist.  The path
        is resolved relative to this module's parent directory.

        Returns:
            Absolute filesystem path to the ``storage`` directory.
        """
        # Use path relative to this config file: XBrainLab/llm/rag/storage
        base_dir = Path(__file__).parent
        path = base_dir / "storage"
        path.mkdir(exist_ok=True)
        return str(path)
