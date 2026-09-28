"""Exercise candidate admission against real Qdrant search, not mock filters."""

import json
import math
from typing import Any, cast

import pytest
from qdrant_client import QdrantClient, models

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
