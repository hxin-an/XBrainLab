"""Exercise candidate admission against real Qdrant search, not mock filters."""

import json
import math
from typing import Any, cast

import pytest
from qdrant_client import QdrantClient, models

from XBrainLab.llm.rag.config import RAGConfig
from XBrainLab.llm.rag.example_policy import example_decision_name
from XBrainLab.llm.rag.retriever import RAGRetriever


class _QueryEmbedding:
    def embed_query(self, _query: str) -> list[float]:
        return [1.0, 0.0]


def test_known_action_clarification_cannot_bypass_dense_publication_filter(
    scoped_retriever,
):
    proposal = {
        "decision": "clarify",
        "mode": "new_request",
        "action": "apply_bandpass_filter",
        "changes": {},
        "message": "Which cutoff frequencies should I use?",
    }
    metadata = {
        "id": "missing-bandpass",
        "source_text": "Use a bandpass filter.",
        "proposal": proposal,
    }
    metadata["decision_name"] = example_decision_name(metadata)
    scoped_retriever.client.upsert(
        RAGConfig.COLLECTION_NAME,
        points=[
            models.PointStruct(
                id=99,
                vector=[1.0, 0.0],
                payload={"page_content": metadata["source_text"], "metadata": metadata},
            )
        ],
    )
    blocked = scoped_retriever.get_similar_examples(
        "bandpass filter", allowed_tool_names=frozenset()
    )
    assert all(
        item["source"]["id"] != "missing-bandpass"
        for item in json.loads(blocked)["items"]
    )
    allowed = scoped_retriever.get_similar_examples(
        "bandpass filter", allowed_tool_names=frozenset({"apply_bandpass_filter"})
    )
    example = next(
        item
        for item in json.loads(allowed)["items"]
        if item["source"]["id"] == "missing-bandpass"
    )
    assert example["data"]["expected_proposal"] == proposal


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
                        "source_text": "Apply a 60 Hz notch filter.",
                        "proposal": (
                            {
                                "decision": "reply",
                                "mode": None,
                                "action": None,
                                "changes": {},
                                "message": parameters["message"],
                            }
                            if tool == "respond_to_user"
                            else {
                                "decision": "execute",
                                "mode": "new_request",
                                "action": tool,
                                "changes": {
                                    field: {
                                        "value": value,
                                        "source_turn": "U1",
                                        "quote": "60",
                                    }
                                    for field, value in parameters.items()
                                },
                                "message": None,
                            }
                        ),
                    },
                },
            )
            for index, (tool, parameters, score) in enumerate(decisions)
        ],
    )
    retriever = RAGRetriever(dense_only=True)
    retriever.client = client
    retriever.embeddings = cast(Any, _QueryEmbedding())
    retriever.is_initialized = True
    yield retriever
    retriever.close()


def _decisions(context: str) -> list[str]:
    return (
        [
            (
                item["data"]["expected_proposal"]["action"]
                if item["data"]["expected_proposal"]["decision"] == "execute"
                else "respond_to_user"
            )
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
