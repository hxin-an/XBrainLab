import json
import threading
import time
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.agent.assembler import ContextAssembler
from XBrainLab.llm.rag.bm25 import BM25Index
from XBrainLab.llm.rag.config import RAGConfig
from XBrainLab.llm.rag.retriever import RAGRetriever


@pytest.fixture
def mock_retriever():
    with (
        patch("langchain_huggingface.HuggingFaceEmbeddings"),
        patch("qdrant_client.QdrantClient") as mock_client_cls,
        patch("langchain_qdrant.Qdrant"),
        patch.object(RAGRetriever, "_auto_initialize", return_value=MagicMock()),
        patch.object(RAGRetriever, "_build_bm25_index", return_value=BM25Index()),
        patch.object(RAGConfig, "embedding_cache_ready", return_value=True),
    ):
        # Setup mock client to pass info check
        # self.client.get_collections().collections
        mock_instance = mock_client_cls.return_value
        mock_instance.get_collections.return_value.collections = []

        retriever = RAGRetriever()
        retriever.initialize()
        return retriever


def _metadata(example_id, action="start_training", text="Start training now."):
    return {
        "id": example_id,
        "source_text": text,
        "proposal": {
            "decision": "execute",
            "mode": "new_request",
            "action": action,
            "changes": {},
            "message": None,
        },
    }


def test_get_similar_examples_success(mock_retriever):
    """Test successful retrieval and formatting."""
    # Mock query_points result
    mock_point = MagicMock()
    mock_point.id = "point_0"
    mock_point.score = 0.95
    mock_point.payload = {
        "page_content": "User input",
        "metadata": _metadata("example", "import_eeg_data", "User input"),
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
    assert (
        example["data"]["expected_proposal"]
        == _metadata("example", "import_eeg_data")["proposal"]
    )
    assert "Assistant action:" not in result
    assert "```" not in result

    parsed_payload = example["data"]["expected_proposal"]
    assert set(parsed_payload) == {"decision", "mode", "action", "changes", "message"}


def test_contextual_transport_is_revalidated_before_pending_context_is_rendered(
    mock_retriever,
):
    rows = json.loads(RAGConfig.get_gold_set_path().read_text())
    row = next(
        row for row in rows if row["id"] == "apply_bandpass_filter_supplement_01"
    )
    metadata = {
        "id": row["id"],
        "source_text": row["input"],
        "proposal": row["expected_proposal"],
        "prior_turn": row["prior_turn"],
    }
    mock_retriever.client.query_points.return_value.points = [
        SimpleNamespace(
            score=0.95,
            payload={"page_content": "Search-only combined text", "metadata": metadata},
        )
    ]
    encoded = mock_retriever.get_similar_examples(
        "bandpass upper", allowed_tool_names=frozenset({"apply_bandpass_filter"})
    )
    payload = json.loads(encoded)
    data = payload["items"][0]["data"]
    assert data == {
        "input": row["input"],
        "expected_proposal": row["expected_proposal"],
        "prior_turn": row["prior_turn"],
    }
    # Even a transported claim of pending values must not become model context.
    data["context"] = {"pending_request": {"parameters": {"low_freq": 999}}}
    assembler = ContextAssembler(MagicMock(), MagicMock())
    assembler.context_notes = [json.dumps(payload)]
    rendered = assembler._context_note_items(frozenset({"apply_bandpass_filter"}))[
        0
    ].data
    assert "prior_turn" not in rendered
    assert rendered["context"]["current_user"] == {"id": "U2", "text": row["input"]}
    pending = rendered["context"]["pending_request"]
    assert pending["parameters"]["low_freq"]["value"] == 11
    assert pending["user_sources"] == {"U1": row["prior_turn"]["input"]}
    assert assembler._context_note_items(frozenset()) == ()
    data["prior_turn"]["expected_proposal"]["changes"]["low_freq"]["quote"] = (
        "fabricated 11"
    )
    assembler.context_notes = [json.dumps(payload)]
    assert assembler._context_note_items(frozenset({"apply_bandpass_filter"})) == ()


@pytest.mark.parametrize("extra", [" details" * 200, " /home/alice/private/eeg.edf"])
def test_contextual_example_is_dropped_whole_if_prior_source_would_change(
    mock_retriever, extra
):
    rows = json.loads(RAGConfig.get_gold_set_path().read_text())
    row = next(
        row for row in rows if row["id"] == "apply_bandpass_filter_supplement_01"
    )
    row["prior_turn"]["input"] += extra
    metadata = {
        "id": row["id"],
        "source_text": row["input"],
        "proposal": row["expected_proposal"],
        "prior_turn": row["prior_turn"],
    }
    mock_retriever.client.query_points.return_value.points = [
        SimpleNamespace(score=0.95, payload={"metadata": metadata})
    ]
    assert (
        mock_retriever.get_similar_examples(
            "bandpass upper", allowed_tool_names=frozenset({"apply_bandpass_filter"})
        )
        == ""
    )


def test_get_similar_examples_empty(mock_retriever):
    """Test empty result handling."""
    mock_result = MagicMock()
    mock_result.points = []
    mock_retriever.client.query_points.return_value = mock_result

    result = mock_retriever.get_similar_examples("query")

    assert result == ""


@pytest.mark.parametrize("dense_only", [False, True])
def test_sparse_failure_is_not_misreported_as_successful_hybrid(dense_only):
    client = MagicMock()
    with (
        patch.object(RAGConfig, "embedding_cache_ready", return_value=True),
        patch.object(RAGRetriever, "_create_embeddings", return_value=MagicMock()),
        patch.object(RAGRetriever, "_create_client", return_value=client),
        patch.object(RAGRetriever, "_auto_initialize", return_value=MagicMock()),
        patch.object(RAGRetriever, "_build_bm25_index", return_value=None) as sparse,
    ):
        retriever = RAGRetriever(dense_only=dense_only)
        retriever.initialize()
        try:
            if dense_only:
                sparse.assert_not_called()
                assert retriever.is_initialized
                assert retriever.bm25_index is None
            else:
                sparse.assert_called_once_with()
                assert not retriever.is_initialized
                client.close.assert_called_once_with()
        finally:
            retriever.close()


def test_raw_semantic_score_below_threshold_is_not_injected(mock_retriever):
    low_relevance = MagicMock(
        id="low",
        score=RAGConfig.SIMILARITY_THRESHOLD - 0.01,
        payload={
            "page_content": "start training",
            "metadata": _metadata("low"),
        },
    )
    mock_retriever.client.query_points.return_value.points = [low_relevance]

    result = mock_retriever.get_similar_examples(
        "inspect this unrelated recording",
        allowed_tool_names=frozenset({"start_training"}),
    )

    assert result == ""


@pytest.mark.parametrize("dense_present", [False, True])
def test_sparse_can_recall_without_dense_admission(mock_retriever, dense_present):
    low_relevance = MagicMock(
        id="low",
        score=RAGConfig.SIMILARITY_THRESHOLD - 0.01,
        payload={
            "page_content": "start training with EEGNet",
            "metadata": _metadata("low"),
        },
    )
    mock_retriever.client.query_points.return_value.points = (
        [low_relevance] if dense_present else []
    )
    mock_retriever.bm25_index = MagicMock()
    mock_retriever.bm25_index.query.return_value = [
        (
            8.0,
            "bm25-match",
            "start training with EEGNet",
            _metadata("bm25-match", text="start training with EEGNet"),
        )
    ]

    result = mock_retriever.get_similar_examples(
        "start training with EEGNet",
        allowed_tool_names=frozenset({"start_training"}),
    )

    assert "start training with EEGNet" in result


def test_rrf_promotes_shared_identity_and_uses_only_admitted_branch_ranks():
    class _Embeddings:
        @staticmethod
        def embed_query(_query: str) -> list[float]:
            return [0.1, 0.2, 0.3]

    semantic_first = SimpleNamespace(
        id="semantic-first",
        score=0.9,
        payload={
            "page_content": "semantic match",
            "metadata": _metadata("semantic-first", text="semantic match"),
        },
    )
    keyword_first = SimpleNamespace(
        id="keyword-first",
        score=0.8,
        payload={
            "page_content": "shared match",
            "metadata": _metadata("shared-id", text="shared match"),
        },
    )

    class _Client:
        @staticmethod
        def query_points(**_kwargs):
            return SimpleNamespace(points=[semantic_first, keyword_first])

    class _BM25:
        @staticmethod
        def query(_query: str, *, k: int, eligible):
            assert k == 10
            assert eligible(_metadata("sparse-only"))
            return [
                (
                    10.0,
                    "shared-id",
                    "shared match",
                    _metadata("shared-id", text="shared match"),
                ),
                (
                    5.0,
                    "sparse-only",
                    "lexical match",
                    _metadata("sparse-only", text="lexical match"),
                ),
            ]

    retriever = RAGRetriever()
    retriever.is_initialized = True
    retriever.embeddings = cast(Any, _Embeddings())
    retriever.client = cast(Any, _Client())
    retriever.bm25_index = cast(Any, _BM25())

    payload = json.loads(
        retriever.get_similar_examples(
            "current workflow status",
            k=3,
            allowed_tool_names=frozenset({"start_training"}),
        )
    )

    assert [item["data"]["input"] for item in payload["items"]] == [
        "shared match",
        "semantic match",
        "lexical match",
    ]
    assert all(
        item["data"]["expected_proposal"]["action"] == "start_training"
        for item in payload["items"]
    )


def test_retriever_filters_examples_to_request_scoped_tools(mock_retriever):
    scan_point = MagicMock(
        id="scan",
        score=0.8,
        payload={
            "page_content": "Scan the source",
            "metadata": _metadata("scan", "import_eeg_data"),
        },
    )
    browse_point = MagicMock(
        id="browse",
        score=0.95,
        payload={
            "page_content": "List the files",
            "metadata": _metadata("browse", "list_files"),
        },
    )
    mock_retriever.client.query_points.return_value.points = [
        browse_point,
        scan_point,
    ]

    result = mock_retriever.get_similar_examples(
        "Use the EEG recording at /data/eeg",
        allowed_tool_names=frozenset({"import_eeg_data"}),
    )

    assert "import_eeg_data" in result
    assert "list_files" not in result


def test_rrf_deduplicates_by_example_id_and_breaks_ties_stably(mock_retriever):
    mock_retriever.client.query_points.return_value.points = [
        SimpleNamespace(
            id=point_id,
            score=0.9,
            payload={
                "page_content": f"Example {example_id}",
                "metadata": _metadata(example_id),
            },
        )
        for point_id, example_id in [(99, "z"), (21, "a"), (22, "a")]
    ]
    payload = json.loads(mock_retriever.get_similar_examples("training", k=20))
    assert [item["source"]["id"] for item in payload["items"]] == ["a", "z"]


@pytest.mark.parametrize("missing", [False, True])
def test_sparse_failure_never_falls_back_to_available_dense_result(
    mock_retriever, missing
):
    mock_retriever.client.query_points.return_value.points = [
        SimpleNamespace(
            id=1,
            score=0.9,
            payload={"page_content": "Start training.", "metadata": _metadata("dense")},
        )
    ]
    if missing:
        mock_retriever.bm25_index = None
    else:
        mock_retriever.bm25_index = MagicMock()
        mock_retriever.bm25_index.query.side_effect = RuntimeError("sparse failed")
    with pytest.raises(RuntimeError, match=r"BM25|sparse"):
        mock_retriever.get_similar_examples("training")
    assert mock_retriever._active_operations == 0


def test_explicit_dense_only_does_not_query_sparse(mock_retriever):
    mock_retriever.dense_only = True
    mock_retriever.bm25_index = MagicMock()
    mock_retriever.client.query_points.return_value.points = []
    assert mock_retriever.get_similar_examples("training") == ""
    mock_retriever.bm25_index.query.assert_not_called()


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


def test_retrieval_failure_propagates_and_releases_lifecycle_lease():
    retriever = RAGRetriever()
    client = MagicMock()
    embeddings = MagicMock()
    embeddings.embed_query.side_effect = RuntimeError("embedding failed")
    retriever.client = client
    retriever.embeddings = embeddings
    retriever.is_initialized = True

    with pytest.raises(RuntimeError, match="embedding failed"):
        retriever.get_similar_examples("inspect the dataset")

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
        patch("langchain_huggingface.HuggingFaceEmbeddings"),
        patch("qdrant_client.QdrantClient", _FakeClient),
        patch("langchain_qdrant.Qdrant", return_value=object()),
        patch.object(RAGRetriever, "_build_bm25_index", return_value=BM25Index()),
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
        patch("langchain_huggingface.HuggingFaceEmbeddings", _fake_embeddings),
        patch("qdrant_client.QdrantClient") as mock_client_cls,
        patch("langchain_qdrant.Qdrant", return_value=object()),
        patch.object(RAGRetriever, "_auto_initialize", return_value=object()),
        patch.object(RAGRetriever, "_build_bm25_index", return_value=BM25Index()),
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
