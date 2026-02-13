from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.rag.retriever import RAGRetriever


@pytest.fixture
def mock_retriever():
    with (
        patch("langchain_community.embeddings.HuggingFaceEmbeddings"),
        patch("qdrant_client.QdrantClient") as mock_client_cls,
        patch("langchain_community.vectorstores.Qdrant"),
    ):
        # Setup mock client to pass info check
        # self.client.get_collections().collections
        mock_instance = mock_client_cls.return_value
        mock_instance.get_collections.return_value.collections = []

        retriever = RAGRetriever()
        retriever.initialize()
        return retriever


def test_get_similar_examples_success(mock_retriever):
    """Test successful retrieval and formatting."""
    # Mock query_points result
    mock_point = MagicMock()
    mock_point.payload = {
        "page_content": "User input",
        "metadata": {"tool_calls": '{"command": "test"}'},
    }

    mock_result = MagicMock()
    mock_result.points = [mock_point]
    mock_retriever.client.query_points.return_value = mock_result

    result = mock_retriever.get_similar_examples("query")

    assert "Example 1:" in result
    assert 'User: "User input"' in result
    assert '{"command": "test"}' in result


def test_get_similar_examples_empty(mock_retriever):
    """Test empty result handling."""
    mock_result = MagicMock()
    mock_result.points = []
    mock_retriever.client.query_points.return_value = mock_result

    result = mock_retriever.get_similar_examples("query")

    assert result == ""
