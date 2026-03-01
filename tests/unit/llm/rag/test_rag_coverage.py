"""Coverage tests for BM25 index, RAG retriever, and RAG indexer."""

import json
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# ── BM25 Index ──────────────────────────────────────────────


class TestBM25Index:
    """Cover BM25Index scoring + edge cases."""

    def test_add_and_query(self):
        from XBrainLab.llm.rag.bm25 import BM25Index

        idx = BM25Index()
        idx.add_document("d1", "load eeg data from file", {"cat": "dataset"})
        idx.add_document("d2", "apply bandpass filter to signal", {"cat": "preprocess"})
        idx.add_document("d3", "train EEGNet model", {"cat": "training"})

        results = idx.query("load data", k=2)
        assert len(results) >= 1
        assert results[0][1] == "d1"
        assert results[0][0] > 0

    def test_empty_index_returns_empty(self):
        from XBrainLab.llm.rag.bm25 import BM25Index

        idx = BM25Index()
        assert idx.query("anything") == []

    def test_empty_query_returns_empty(self):
        from XBrainLab.llm.rag.bm25 import BM25Index

        idx = BM25Index()
        idx.add_document("d1", "some text", {})
        assert idx.query("...") == []

    def test_build_from_json(self):
        from XBrainLab.llm.rag.bm25 import BM25Index

        data = [
            {"id": 1, "input": "load data from file", "category": "dataset"},
            {"id": 2, "input": "apply filter", "category": "preprocess"},
            {"id": 3, "input": "", "category": "empty"},
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            f.flush()
            path = f.name

        idx = BM25Index()
        idx.build_from_json(path)
        assert idx.doc_count == 2

    def test_build_from_json_missing_file(self):
        from XBrainLab.llm.rag.bm25 import BM25Index

        idx = BM25Index()
        idx.build_from_json("/nonexistent/path.json")
        assert idx.doc_count == 0

    def test_query_scoring_multiple_terms(self):
        from XBrainLab.llm.rag.bm25 import BM25Index

        idx = BM25Index()
        idx.add_document("d1", "bandpass filter low frequency high frequency", {})
        idx.add_document("d2", "notch filter power line noise", {})
        idx.add_document("d3", "bandpass filter narrow band", {})

        results = idx.query("bandpass filter frequency", k=3)
        assert len(results) >= 2
        assert results[0][1] == "d1"


# ── RAG Retriever ───────────────────────────────────────────


class TestRetrieverInitialization:
    def test_already_initialized_returns_early(self):
        from XBrainLab.llm.rag.retriever import RAGRetriever

        r = RAGRetriever()
        r.is_initialized = True
        r.initialize()

    def test_collection_check_exception_returns_false(self):
        from XBrainLab.llm.rag.retriever import RAGRetriever

        r = RAGRetriever()
        r.client = MagicMock()
        r.client.get_collection.side_effect = Exception("fail")
        assert r._collection_exists() is False

    def test_auto_init_failure_logs_error(self):
        from XBrainLab.llm.rag.retriever import RAGRetriever

        r = RAGRetriever()
        r.embeddings = MagicMock()
        r.client = MagicMock()

        # Lazy import inside _auto_initialize: ``from .indexer import RAGIndexer``
        # We must make the module-level attribute available for patch to find it.
        import XBrainLab.llm.rag.retriever as _mod

        # Pre-import so the attribute exists at module level
        from XBrainLab.llm.rag.indexer import RAGIndexer as _orig

        _mod.RAGIndexer = _orig  # ensure patchable
        with patch.object(
            _mod,
            "RAGIndexer",
            side_effect=Exception("fail"),
        ):
            r._auto_initialize()

    def test_hybrid_search_exception(self):
        from XBrainLab.llm.rag.retriever import RAGRetriever

        r = RAGRetriever()
        r.is_initialized = True
        r._executor = MagicMock()
        r._executor.submit.side_effect = Exception("thread fail")
        r.embeddings = MagicMock()

        result = r.get_similar_examples("test query")
        assert result == ""


# ── RAG Indexer ─────────────────────────────────────────────


class TestRAGIndexer:
    @patch("XBrainLab.llm.rag.indexer.HuggingFaceEmbeddings")
    @patch("XBrainLab.llm.rag.indexer.QdrantClient")
    def test_close_own_client(self, mock_qd, mock_emb):
        from XBrainLab.llm.rag.indexer import RAGIndexer

        indexer = RAGIndexer()
        indexer._owns_client = True
        mock_client = MagicMock()
        indexer.client = mock_client
        indexer.close()
        mock_client.close.assert_called_once()

    @patch("XBrainLab.llm.rag.indexer.HuggingFaceEmbeddings")
    @patch("XBrainLab.llm.rag.indexer.QdrantClient")
    def test_load_gold_set_failure(self, mock_qd, mock_emb):
        from XBrainLab.llm.rag.indexer import RAGIndexer

        indexer = RAGIndexer()
        with pytest.raises(Exception, match=r".*"):
            indexer.load_gold_set("/nonexistent/path.json")
