import json
from unittest.mock import MagicMock, mock_open, patch

import pytest
from langchain.docstore.document import Document

from XBrainLab.llm.rag.indexer import RAGIndexer


@pytest.fixture
def mock_indexer():
    with (
        patch("XBrainLab.llm.rag.indexer.HuggingFaceEmbeddings"),
        patch("XBrainLab.llm.rag.indexer.QdrantClient"),
    ):
        indexer = RAGIndexer()
        return indexer


def test_load_gold_set(mock_indexer):
    """Test parsing of gold set JSON."""
    fake_json = [
        {
            "id": "test_01",
            "category": "test",
            "input": "User Input",
            "expected_tool_calls": [{"tool": "test"}],
        }
    ]

    with patch("builtins.open", mock_open(read_data=json.dumps(fake_json))):
        docs = mock_indexer.load_gold_set("dummy.json")

    assert len(docs) == 1
    assert docs[0].page_content == "User Input"
    assert docs[0].metadata["id"] == "test_01"
    assert "tool_calls" in docs[0].metadata


def test_index_data(mock_indexer):
    """Test indexing calls Qdrant methods."""
    docs = [Document(page_content="test", metadata={})]

    with patch("XBrainLab.llm.rag.indexer.Qdrant") as mock_qdrant_cls:
        mock_qdrant_instance = MagicMock()
        mock_qdrant_cls.return_value = mock_qdrant_instance

        mock_indexer.index_data(docs)

        # Verify collection recreation
        mock_indexer.client.recreate_collection.assert_called_once()

        # Verify add_documents called (not from_documents)
        mock_qdrant_instance.add_documents.assert_called_once_with(docs)
