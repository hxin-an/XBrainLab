from pathlib import Path


class RAGConfig:
    """Configuration for RAG (Retrieval Augmented Generation)."""

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
        """Returns parsed absolute path for storage."""
        # Use path relative to this config file: XBrainLab/llm/rag/storage
        base_dir = Path(__file__).parent
        path = base_dir / "storage"
        path.mkdir(exist_ok=True)
        return str(path)
