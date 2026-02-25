"""Unit tests for RAGConfig — constants and storage path."""

import os

from XBrainLab.llm.rag.config import RAGConfig


class TestRAGConfig:
    def test_collection_name(self):
        assert RAGConfig.COLLECTION_NAME == "gold_set_examples"

    def test_embedding_model(self):
        assert isinstance(RAGConfig.EMBEDDING_MODEL, str)
        assert len(RAGConfig.EMBEDDING_MODEL) > 0

    def test_similarity_threshold_range(self):
        assert 0.0 <= RAGConfig.SIMILARITY_THRESHOLD <= 1.0

    def test_top_k_positive(self):
        assert RAGConfig.TOP_K > 0

    def test_get_storage_path_returns_string(self):
        path = RAGConfig.get_storage_path()
        assert isinstance(path, str)

    def test_get_storage_path_creates_directory(self):
        path = RAGConfig.get_storage_path()
        assert os.path.isdir(path)

    def test_get_storage_path_is_inside_rag_dir(self):
        path = RAGConfig.get_storage_path()
        assert "rag" in path.replace("\\", "/").lower()
        assert path.endswith("storage")
