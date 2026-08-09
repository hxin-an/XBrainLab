import json
import threading
import time
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.rag.config import RAGConfig
from XBrainLab.llm.rag.retriever import RAGRetriever


@pytest.fixture
def mock_retriever():
    with (
        patch("langchain_community.embeddings.HuggingFaceEmbeddings"),
        patch("qdrant_client.QdrantClient") as mock_client_cls,
        patch("langchain_community.vectorstores.Qdrant"),
        patch.object(RAGRetriever, "_auto_initialize", return_value=MagicMock()),
        patch.object(RAGRetriever, "_build_bm25_index", return_value=None),
        patch.object(RAGConfig, "embedding_cache_ready", return_value=True),
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
    mock_point.id = "point_0"
    mock_point.score = 0.95
    mock_point.payload = {
        "page_content": "User input",
        "metadata": {
            "tool_calls": ('[{"tool_name": "get_dataset_info", "parameters": {}}]')
        },
    }

    mock_result = MagicMock()
    mock_result.points = [mock_point]
    mock_retriever.client.query_points.return_value = mock_result

    result = mock_retriever.get_similar_examples("query")

    payload = json.loads(result)
    assert payload["schema"] == "xbrainlab.untrusted_context.v1"
    assert payload["trust"] == "untrusted"
    assert len(payload["items"]) == 1
    example = payload["items"][0]
    assert example["type"] == "rag_example"
    assert example["source"]["kind"] == "xbrainlab_bundled_gold_set"
    assert example["data"]["input"] == "User input"
    assert example["data"]["expected_action"] == {
        "tool_name": "get_dataset_info",
        "parameters": {},
    }
    assert "Assistant action:" not in result
    assert "```" not in result

    parsed_payload = example["data"]["expected_action"]
    assert list(parsed_payload) == ["parameters", "tool_name"]


def test_get_similar_examples_empty(mock_retriever):
    """Test empty result handling."""
    mock_result = MagicMock()
    mock_result.points = []
    mock_retriever.client.query_points.return_value = mock_result

    result = mock_retriever.get_similar_examples("query")

    assert result == ""


def test_raw_semantic_score_below_threshold_is_not_injected(mock_retriever):
    low_relevance = MagicMock(
        id="low",
        score=RAGConfig.SIMILARITY_THRESHOLD - 0.01,
        payload={
            "page_content": "start training",
            "metadata": {
                "tool_calls": ('[{"tool_name":"start_training","parameters":{}}]')
            },
        },
    )
    mock_retriever.client.query_points.return_value.points = [low_relevance]

    result = mock_retriever.get_similar_examples(
        "inspect this unrelated recording",
        allowed_tool_names=frozenset({"start_training"}),
    )

    assert result == ""


def test_bm25_cannot_admit_a_candidate_below_semantic_threshold(mock_retriever):
    low_relevance = MagicMock(
        id="low",
        score=RAGConfig.SIMILARITY_THRESHOLD - 0.01,
        payload={
            "page_content": "start training with EEGNet",
            "metadata": {
                "tool_calls": ('[{"tool_name":"start_training","parameters":{}}]')
            },
        },
    )
    mock_retriever.client.query_points.return_value.points = [low_relevance]
    mock_retriever.bm25_index = MagicMock()
    mock_retriever.bm25_index.query.return_value = [
        (
            8.0,
            "bm25-match",
            "start training with EEGNet",
            {"tool_calls": ('[{"tool_name":"start_training","parameters":{}}]')},
        )
    ]

    result = mock_retriever.get_similar_examples(
        "start training with EEGNet",
        allowed_tool_names=frozenset({"start_training"}),
    )

    assert result == ""


def test_bm25_reranks_only_semantically_admitted_candidates():
    class _Embeddings:
        @staticmethod
        def embed_query(_query: str) -> list[float]:
            return [0.1, 0.2, 0.3]

    metadata = {
        "tool_calls": [
            {"tool_name": "query_state", "parameters": {}},
        ],
    }
    semantic_first = SimpleNamespace(
        id="semantic-first",
        score=0.9,
        payload={"page_content": "inspect current state", "metadata": metadata},
    )
    keyword_first = SimpleNamespace(
        id="keyword-first",
        score=0.8,
        payload={"page_content": "current workflow status", "metadata": metadata},
    )

    class _Client:
        @staticmethod
        def query_points(**_kwargs):
            return SimpleNamespace(points=[semantic_first, keyword_first])

    class _BM25:
        @staticmethod
        def query(_query: str, *, k: int):
            assert k >= 2
            return [(10.0, "keyword-first", "current workflow status", metadata)]

    retriever = RAGRetriever()
    retriever.is_initialized = True
    retriever.embeddings = cast(Any, _Embeddings())
    retriever.client = cast(Any, _Client())
    retriever.bm25_index = cast(Any, _BM25())

    payload = json.loads(
        retriever.get_similar_examples(
            "current workflow status",
            k=2,
            allowed_tool_names=frozenset({"query_state"}),
        )
    )

    assert [item["data"]["input"] for item in payload["items"]] == [
        "current workflow status",
        "inspect current state",
    ]
    assert all(
        item["data"]["expected_action"]["tool_name"] == "query_state"
        for item in payload["items"]
    )


def test_retriever_filters_examples_to_request_scoped_tools(mock_retriever):
    scan_point = MagicMock(
        id="scan",
        score=0.8,
        payload={
            "page_content": "Scan the source",
            "metadata": {
                "tool_calls": (
                    '[{"tool_name":"scan_source","parameters":'
                    '{"source_path":"/data/eeg"}}]'
                )
            },
        },
    )
    browse_point = MagicMock(
        id="browse",
        score=0.95,
        payload={
            "page_content": "List the files",
            "metadata": {
                "tool_calls": (
                    '[{"tool_name":"list_files","parameters":{"directory":"/data"}}]'
                )
            },
        },
    )
    mock_retriever.client.query_points.return_value.points = [
        browse_point,
        scan_point,
    ]

    result = mock_retriever.get_similar_examples(
        "Use the EEG recording at /data/eeg",
        allowed_tool_names=frozenset({"scan_source"}),
    )

    assert "scan_source" in result
    assert "list_files" not in result


@pytest.mark.parametrize(
    "query",
    (
        "Explain what an EEG epoch is.",
        "Help me process the data.",
    ),
)
def test_non_action_requests_do_not_retrieve_action_examples(query):
    retriever = RAGRetriever()
    retriever.embeddings = MagicMock()
    retriever.client = MagicMock()

    result = retriever.get_similar_examples(query)

    assert result == ""
    retriever.embeddings.embed_query.assert_not_called()
    retriever.client.query_points.assert_not_called()


def test_initialize_failure_remains_unavailable_and_closes_created_client(
    monkeypatch,
):
    retriever = RAGRetriever()
    client = MagicMock()
    monkeypatch.setattr(RAGConfig, "embedding_cache_ready", lambda: True)
    monkeypatch.setattr(
        retriever, "_create_embeddings", MagicMock(return_value=object())
    )
    monkeypatch.setattr(retriever, "_create_client", MagicMock(return_value=client))
    monkeypatch.setattr(
        retriever,
        "_auto_initialize",
        MagicMock(side_effect=RuntimeError("index inspection failed")),
    )

    retriever.initialize()

    assert retriever.is_initialized is False
    assert retriever.client is None
    assert retriever.vectorstore is None
    assert retriever.embeddings is None
    assert retriever.get_similar_examples("inspect the dataset") == ""
    client.close.assert_called_once_with()


def test_retrieval_failure_returns_empty_and_releases_lifecycle_lease():
    retriever = RAGRetriever()
    client = MagicMock()
    embeddings = MagicMock()
    embeddings.embed_query.side_effect = RuntimeError("embedding failed")
    retriever.client = client
    retriever.embeddings = embeddings
    retriever.is_initialized = True

    result = retriever.get_similar_examples("inspect the dataset")

    assert result == ""
    assert retriever._active_operations == 0
    client.query_points.assert_not_called()
    retriever.close()
    client.close.assert_called_once_with()


def test_close_fences_in_flight_initialize_and_prevents_resource_republish():
    """Closing during init must prevent late-published clients/vector stores."""
    constructor_entered = threading.Event()
    release_constructor = threading.Event()
    created_clients = []

    class _FakeClient:
        def __init__(self, path: str) -> None:
            self.path = path
            self.closed = False
            created_clients.append(self)
            constructor_entered.set()
            assert release_constructor.wait(timeout=2)

        def get_collections(self):
            return type("Collections", (), {"collections": []})()

        def close(self) -> None:
            self.closed = True

    retriever = RAGRetriever()

    with (
        patch("langchain_community.embeddings.HuggingFaceEmbeddings"),
        patch("qdrant_client.QdrantClient", _FakeClient),
        patch("langchain_community.vectorstores.Qdrant", return_value=object()),
        patch.object(RAGRetriever, "_collection_exists", return_value=True),
        patch.object(RAGRetriever, "_build_bm25_index", return_value=None),
        patch.object(RAGConfig, "embedding_cache_ready", return_value=True),
    ):
        init_thread = threading.Thread(target=retriever.initialize)
        init_thread.start()
        assert constructor_entered.wait(timeout=2)

        retriever.close()
        release_constructor.set()
        init_thread.join(timeout=2)

    assert not init_thread.is_alive()
    assert created_clients
    assert created_clients[0].closed
    assert retriever.client is None
    assert retriever.vectorstore is None
    assert retriever.embeddings is None
    assert retriever.is_initialized is False
    assert retriever.get_similar_examples("query") == ""


def test_concurrent_initialize_has_single_initializer():
    """Only one thread may perform RAG initialization work."""
    constructor_entered = threading.Event()
    release_constructor = threading.Event()
    embedding_constructor_count = 0
    constructor_lock = threading.Lock()

    def _fake_embeddings(*args, **kwargs):
        nonlocal embedding_constructor_count
        with constructor_lock:
            embedding_constructor_count += 1
        constructor_entered.set()
        assert release_constructor.wait(timeout=2)
        return MagicMock()

    retriever = RAGRetriever()
    threads = [threading.Thread(target=retriever.initialize) for _ in range(4)]

    with (
        patch("langchain_community.embeddings.HuggingFaceEmbeddings", _fake_embeddings),
        patch("qdrant_client.QdrantClient") as mock_client_cls,
        patch("langchain_community.vectorstores.Qdrant", return_value=object()),
        patch.object(RAGRetriever, "_auto_initialize", return_value=object()),
        patch.object(RAGRetriever, "_build_bm25_index", return_value=None),
        patch.object(RAGConfig, "embedding_cache_ready", return_value=True),
    ):
        mock_client_cls.return_value.get_collections.return_value.collections = []
        for thread in threads:
            thread.start()
        assert constructor_entered.wait(timeout=2)
        release_constructor.set()
        for thread in threads:
            thread.join(timeout=2)

    assert all(not thread.is_alive() for thread in threads)
    assert embedding_constructor_count == 1
    assert retriever.is_initialized is True
    retriever.close()


def test_close_does_not_wait_for_in_flight_retrieval_or_deadlock():
    """Close must fence quickly while a retrieval is blocked in embedding."""
    embed_started = threading.Event()
    release_embed = threading.Event()
    result_box: dict[str, str | None] = {"result": None}

    class _BlockingEmbeddings:
        def embed_query(self, query: str) -> list[float]:
            embed_started.set()
            assert release_embed.wait(timeout=2)
            return [0.1, 0.2]

    class _Client:
        def __init__(self) -> None:
            self.closed = threading.Event()
            self.query_calls = 0

        def query_points(self, **kwargs):
            self.query_calls += 1
            return type("Result", (), {"points": []})()

        def close(self) -> None:
            self.closed.set()

    retriever = RAGRetriever()
    client = _Client()
    test_retriever = cast(Any, retriever)
    test_retriever.client = client
    test_retriever.embeddings = _BlockingEmbeddings()
    retriever.is_initialized = True

    retrieval_thread = threading.Thread(
        target=lambda: result_box.update(result=retriever.get_similar_examples("query"))
    )
    retrieval_thread.start()
    assert embed_started.wait(timeout=2)

    started = time.monotonic()
    retriever.close()
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert retriever.client is None
    assert retriever.get_similar_examples("after close") == ""
    assert client.query_calls == 0

    release_embed.set()
    retrieval_thread.join(timeout=2)

    assert not retrieval_thread.is_alive()
    assert result_box["result"] == ""
    assert client.closed.is_set()


def test_close_rejects_new_retrieval_without_querying_detached_resources():
    client = MagicMock()
    retriever = RAGRetriever()
    retriever.client = client
    retriever.embeddings = MagicMock()
    retriever.is_initialized = True

    retriever.close()

    assert retriever.get_similar_examples("query") == ""
    client.query_points.assert_not_called()
