"""Focused public-behavior tests for the in-memory BM25 index."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from XBrainLab.llm.rag.bm25 import BM25Index
from XBrainLab.llm.rag.config import RAGConfig


def test_eligible_keyword_match_is_not_lost_behind_global_top_ten():
    index = BM25Index()
    for number in range(12):
        index.add_document(str(number), "apply 60 hz notch filter", {"allowed": False})
    index.add_document("eligible", "apply 60 hz notch filter please", {"allowed": True})

    matches = index.query(
        "apply 60 hz notch filter", k=3, eligible=lambda metadata: metadata["allowed"]
    )

    assert len(matches) == 1
    assert matches[0][1] == "eligible"
    assert matches[0][0] > 0


def test_equal_sparse_scores_use_stable_identity_not_insertion_order():
    index = BM25Index()
    index.add_document("z-last", "notch filter")
    index.add_document("a-first", "notch filter")

    assert [row[1] for row in index.query("notch filter")] == ["a-first", "z-last"]


def test_duplicate_query_terms_do_not_change_sparse_admission_or_ranking():
    index = BM25Index()
    index.add_document("notch", "notch filter")
    index.add_document("other", "filter notch notch")
    assert index.query("notch filter notch filter") == index.query("notch filter")


def test_exact_half_symmetric_coverage_is_admitted_but_less_than_half_is_not():
    index = BM25Index()
    index.add_document("candidate", "alpha beta gamma delta")
    index.add_document("other", "epsilon zeta eta theta")
    assert [row[1] for row in index.query("alpha beta epsilon zeta")] == [
        "candidate",
        "other",
    ]
    assert index.query("alpha epsilon absent") == []

    below = BM25Index()
    below.add_document("candidate", "alpha beta gamma delta iota")
    below.add_document("other", "epsilon zeta eta theta kappa")
    assert [row[1] for row in below.query("alpha beta epsilon zeta eta")] == ["other"]


def test_short_document_containment_survives_long_query_including_oov_tradeoff():
    index = BM25Index()
    index.add_document("candidate", "notch filter")
    # v2 rejected this OOV-diluted query; v3 deliberately permits containment.
    assert index.query("notch filter coffee butterflies marathon") == index.query(
        "notch filter"
    )


def test_oov_terms_still_dilute_query_when_document_does_not_cover_half():
    index = BM25Index()
    index.add_document("candidate", "notch filter signal frequency removal")
    assert index.query("notch filter")
    assert index.query("notch filter coffee butterflies marathon") == []
    assert index.query("coffee butterflies marathon") == []


def test_unique_document_terms_define_coverage_not_repetition():
    index = BM25Index()
    index.add_document("candidate", "alpha beta gamma gamma gamma delta delta")
    index.add_document("other", "epsilon zeta eta theta")
    assert [
        row[1] for row in index.query("alpha beta coffee butterflies marathon")
    ] == ["candidate"]


def test_single_generic_term_cannot_admit_even_with_full_coverage():
    index = BM25Index()
    index.add_document("candidate", "the filter")
    assert index.query("the") == []
    assert index.query("the the") == []


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
                    "id": "import-eeg",
                    "input": "import an EEG dataset",
                    "category": "dataset",
                    "expected_proposal": {
                        "decision": "execute",
                        "mode": "new_request",
                        "action": "import_eeg_data",
                        "changes": {},
                        "message": None,
                    },
                },
                {
                    "id": "legacy-load",
                    "input": "load this EEG file",
                    "category": "dataset",
                    "expected_tool_calls": [
                        {"tool_name": "retired_action", "parameters": {}}
                    ],
                },
                {"id": "empty", "input": "", "category": "empty"},
            ]
        ),
        encoding="utf-8",
    )
    index = BM25Index()

    index.build_from_json(corpus)
    results = index.query("import EEG dataset")

    assert index.doc_count == 1
    assert len(results) == 1
    assert results[0][1] == "import-eeg"
    assert json.loads(results[0][3]["proposal"])["action"] == "import_eeg_data"


def test_contextual_sparse_index_keeps_original_user_sources_separate():
    index = BM25Index()
    index.build_from_json(RAGConfig.get_gold_set_path())
    rows = index.query(
        "bandpass upper cutoff",
        eligible=lambda metadata: metadata["id"]
        == "apply_bandpass_filter_supplement_01",
    )
    assert len(rows) == 1
    _, _, search_text, metadata = rows[0]
    assert (
        search_text == metadata["prior_turn"]["input"] + "\n" + metadata["source_text"]
    )
    assert metadata["source_text"] == "Set its upper cutoff to 47 Hz."


def test_build_from_missing_json_keeps_index_empty(tmp_path: Path) -> None:
    index = BM25Index()

    index.build_from_json(tmp_path / "missing.json")

    assert index.doc_count == 0
    assert index.query("dataset") == []
