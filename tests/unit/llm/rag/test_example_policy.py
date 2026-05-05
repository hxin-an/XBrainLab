from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from XBrainLab.llm.rag.bm25 import BM25Index
from XBrainLab.llm.rag.example_policy import (
    is_primary_workflow_example,
    tool_calls_from_metadata,
    tool_name_from_call,
)


def test_rag_example_policy_rejects_legacy_compatibility_tools() -> None:
    metadata = {
        "tool_calls": (
            '[{"tool_name": "load_data", "parameters": {"paths": ["/tmp/a.gdf"]}}]'
        ),
    }

    assert is_primary_workflow_example(metadata) is False


def test_rag_example_policy_accepts_data_interpretation_tools() -> None:
    metadata = {
        "tool_calls": (
            '[{"tool_name": "scan_source", "parameters": {"source_path": "/tmp/eeg"}}]'
        ),
    }

    assert tool_calls_from_metadata(metadata)[0]["tool_name"] == "scan_source"
    assert is_primary_workflow_example(metadata) is True


def test_rag_example_policy_rejects_dict_and_function_legacy_shapes() -> None:
    function_metadata = {
        "tool_calls": '{"function": {"name": "attach_labels"}, "arguments": {}}',
    }
    tool_metadata = {
        "expected_tool_calls": {"tool": "import_labels", "parameters": {}},
    }

    assert tool_name_from_call(tool_calls_from_metadata(function_metadata)[0]) == (
        "attach_labels"
    )
    assert is_primary_workflow_example(function_metadata) is False
    assert is_primary_workflow_example(tool_metadata) is False


def test_bm25_gold_set_excludes_legacy_data_entry_examples() -> None:
    gold_set = (
        Path(__file__).resolve().parents[4]
        / "XBrainLab"
        / "llm"
        / "rag"
        / "data"
        / "gold_set.json"
    )
    index = BM25Index()

    index.build_from_json(gold_set)

    assert index.doc_count > 0
    for _doc_id, _text, metadata in index._docs:
        assert is_primary_workflow_example(metadata) is True


def test_retriever_filters_legacy_examples_from_existing_vector_store() -> None:
    from XBrainLab.llm.rag.retriever import RAGRetriever

    legacy_payload = {
        "page_content": "Load the file /tmp/a.gdf",
        "metadata": {
            "tool_calls": (
                '[{"tool_name": "load_data", "parameters": {"paths": ["/tmp/a.gdf"]}}]'
            ),
        },
    }
    primary_payload = {
        "page_content": "Scan the EEG source /tmp/eeg",
        "metadata": {
            "tool_calls": (
                '[{"tool_name": "scan_source", "parameters": {"source_path": '
                '"/tmp/eeg"}}]'
            ),
        },
    }
    retriever = RAGRetriever()
    test_retriever = cast(Any, retriever)
    test_retriever.embeddings = SimpleNamespace(
        embed_query=lambda _query: [0.1, 0.2],
    )
    test_retriever.client = SimpleNamespace(
        close=lambda: None,
        query_points=lambda **_kwargs: SimpleNamespace(
            points=[
                SimpleNamespace(id="legacy", score=1.0, payload=legacy_payload),
                SimpleNamespace(id="primary", score=0.9, payload=primary_payload),
            ],
        ),
    )

    try:
        result = retriever.get_similar_examples("load EEG data", k=2)
    finally:
        retriever.close()

    assert "scan_source" in result
    assert "Scan the EEG source" in result
    assert "load_data" not in result
    assert "Load the file" not in result
