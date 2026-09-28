"""Exercise candidate admission against real Qdrant search, not mock filters."""

import json
import math
from typing import Any, cast

import pytest
from qdrant_client import QdrantClient, models

from XBrainLab.llm.rag.bm25 import BM25Index
from XBrainLab.llm.rag.config import RAGConfig
from XBrainLab.llm.rag.retriever import RAGRetriever


class _QueryEmbedding:
    def embed_query(self, _query: str) -> list[float]:
        return [1.0, 0.0]


@pytest.fixture
def scoped_retriever():
    client = QdrantClient(":memory:")
    client.create_collection(
        RAGConfig.COLLECTION_NAME,
        vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE),
    )
    decisions = [
        ("start_training", {}, 0.99 - offset * 0.005) for offset in range(12)
    ] + [
        ("apply_notch_filter", {"freq": 60}, 0.85),
        ("respond_to_user", {"message": "No operation was requested."}, 0.8),
    ]
    client.upsert(
        RAGConfig.COLLECTION_NAME,
        points=[
            models.PointStruct(
                id=index,
                vector=[score, math.sqrt(1 - score**2)],
                payload={
                    "page_content": f"Example {index}",
                    "metadata": {
                        "id": f"example-{index}",
                        "decision_name": tool,
                        "tool_calls": [{"tool_name": tool, "parameters": parameters}],
                    },
                },
            )
            for index, (tool, parameters, score) in enumerate(decisions)
        ],
    )
    retriever = RAGRetriever()
    retriever.client = client
    retriever.embeddings = cast(Any, _QueryEmbedding())
    retriever.is_initialized = True
    yield retriever
    retriever.close()


def _decisions(context: str) -> list[str]:
    return (
        [
            item["data"]["expected_action"]["tool_name"]
            for item in json.loads(context)["items"]
        ]
        if context
        else []
    )


def test_allowed_example_below_global_top_ten_is_still_retrieved(scoped_retriever):
    context = scoped_retriever.get_similar_examples(
        "Remove power line interference at 60 Hz.",
        allowed_tool_names=frozenset({"apply_notch_filter"}),
    )
    assert _decisions(context) == ["apply_notch_filter", "respond_to_user"]


@pytest.mark.parametrize(
    "query",
    [
        "Explain how a notch filter works.",
        "How does a notch filter work?",
        "Explain the filter and then apply a 60 Hz notch.",
    ],
)
def test_wording_does_not_short_circuit_example_search(scoped_retriever, query):
    context = scoped_retriever.get_similar_examples(
        query, allowed_tool_names=frozenset({"apply_notch_filter"})
    )
    assert _decisions(context) == ["apply_notch_filter", "respond_to_user"]


def test_no_callable_actions_still_allows_response_examples(scoped_retriever):
    context = scoped_retriever.get_similar_examples(
        "Do not perform any operation.", allowed_tool_names=frozenset()
    )
    assert _decisions(context) == ["respond_to_user"]


@pytest.mark.parametrize("dense_distractors", [1, 12])
def test_keyword_recall_rescues_eligible_example_outside_dense_admission(
    scoped_retriever, dense_distractors
):
    """A real sparse index must recover an example below .7 or outside top-10."""
    client = scoped_retriever.client
    bm25 = BM25Index()
    rows = [
        (
            100 + index,
            "Apply min-max scaling to the EEG.",
            "normalize_data",
            {"method": "min-max"},
            0.8,
        )
        for index in range(dense_distractors)
    ] + [
        (
            200,
            "Reset preprocessing and return to the imported EEG data.",
            "reset_preprocessing",
            {},
            0.64,
        )
    ]
    points = []
    for point_id, text, tool, parameters, score in rows:
        metadata = {
            "id": str(point_id),
            "decision_name": tool,
            "tool_calls": [{"tool_name": tool, "parameters": parameters}],
        }
        bm25.add_document(str(point_id), text, metadata)
        points.append(
            models.PointStruct(
                id=point_id,
                vector=[score, math.sqrt(1 - score**2)],
                payload={"page_content": text, "metadata": metadata},
            )
        )
    client.upsert(RAGConfig.COLLECTION_NAME, points=points)
    scoped_retriever.bm25_index = bm25

    context = scoped_retriever.get_similar_examples(
        "Reset preprocessing so I can start again from the imported data.",
        allowed_tool_names=frozenset({"reset_preprocessing", "normalize_data"}),
    )

    decisions = _decisions(context)
    assert "reset_preprocessing" in decisions
    assert len(decisions) <= 3
    assert set(decisions) <= {
        "reset_preprocessing",
        "normalize_data",
        "respond_to_user",
    }

    # The same lexical match must never resurrect a now-unavailable action.
    unavailable = scoped_retriever.get_similar_examples(
        "Reset preprocessing so I can start again from the imported data.",
        allowed_tool_names=frozenset({"normalize_data"}),
    )
    assert "reset_preprocessing" not in _decisions(unavailable)
