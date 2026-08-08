"""Unit tests for RAGConfig constants, identity, and storage paths."""

import hashlib
import os

from XBrainLab.llm.rag.config import RAGConfig


class TestRAGConfig:
    def test_collection_name(self):
        assert RAGConfig.COLLECTION_NAME == (
            "gold_set_examples_1110a243fdf4_b123eefe00fe"
        )

    def test_gold_set_identity_matches_bundled_corpus(self):
        bundled_bytes = RAGConfig.get_gold_set_path().read_bytes()
        canonical_bytes = bundled_bytes.replace(b"\r\n", b"\n")
        expected_digest = RAGConfig.GOLD_SET_SHA256
        raw_digest = hashlib.sha256(bundled_bytes).hexdigest()

        assert hashlib.sha256(canonical_bytes).hexdigest() == expected_digest
        assert bundled_bytes in {
            canonical_bytes,
            canonical_bytes.replace(b"\n", b"\r\n"),
        }
        assert RAGConfig.gold_set_integrity_ok() is (raw_digest == expected_digest)

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
        assert path.endswith("vectors")

    def test_index_manifest_path_is_inside_vector_storage(self):
        manifest_path = RAGConfig.get_index_manifest_path()

        assert manifest_path.parent == RAGConfig.get_cache_root() / "vectors"
        assert manifest_path.name == "index-manifest.json"
