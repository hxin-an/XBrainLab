"""Focused public-behavior tests for the in-memory BM25 index."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from XBrainLab.llm.rag.bm25 import BM25Index


def test_query_ranks_matching_document_and_preserves_public_metadata() -> None:
    index = BM25Index()
    index.add_document(
        "dataset",
        "load eeg data from file",
        {"category": "dataset"},
    )
    index.add_document(
        "preprocess",
        "apply bandpass filter to signal",
        {"category": "preprocess"},
    )
    index.add_document("training", "train EEGNet model", {"category": "training"})

    results = index.query("load eeg data", k=1)

    assert len(results) == 1
    score, document_id, text, metadata = results[0]
    assert score > 0
    assert document_id == "dataset"
    assert text == "load eeg data from file"
    assert metadata == {"category": "dataset"}


@pytest.mark.parametrize("query", ["anything", "..."])
def test_query_without_searchable_terms_returns_no_results(query: str) -> None:
    index = BM25Index()
    if query == "...":
        index.add_document("dataset", "inspect eeg data", {})

    assert index.query(query) == []


def test_build_from_json_indexes_only_primary_workflow_examples(tmp_path: Path) -> None:
    corpus = tmp_path / "gold-set.json"
    corpus.write_text(
        json.dumps(
            [
                {
                    "id": "dataset-info",
                    "input": "inspect the current dataset",
                    "category": "dataset",
                    "expected_tool_calls": [
                        {"tool_name": "get_dataset_info", "parameters": {}}
                    ],
                },
                {
                    "id": "legacy-load",
                    "input": "load this EEG file",
                    "category": "dataset",
                    "expected_tool_calls": [
                        {"tool_name": "load_data", "parameters": {"paths": []}}
                    ],
                },
                {"id": "empty", "input": "", "category": "empty"},
            ]
        ),
        encoding="utf-8",
    )
    index = BM25Index()

    index.build_from_json(corpus)
    results = index.query("inspect dataset")

    assert index.doc_count == 1
    assert len(results) == 1
    assert results[0][1] == "dataset-info"
    assert json.loads(results[0][3]["tool_calls"]) == [
        {"tool_name": "get_dataset_info", "parameters": {}}
    ]


def test_build_from_missing_json_keeps_index_empty(tmp_path: Path) -> None:
    index = BM25Index()

    index.build_from_json(tmp_path / "missing.json")

    assert index.doc_count == 0
    assert index.query("dataset") == []
