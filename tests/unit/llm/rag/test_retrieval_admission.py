"""Frozen subject-relevance inputs use the actual product query projection."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from XBrainLab.llm.agent.assembler import ContextAssembler
from XBrainLab.llm.agent.turn import AssistantPendingRequest
from XBrainLab.llm.rag.config import RAGConfig


def load_admission_cases(version=3):
    return json.loads(
        Path(__file__)
        .with_name(f"retrieval_admission_cases_v{version}.json")
        .read_text()
    )


def case_retrieval_query(case):
    turns = case["user_turns"]
    pending = None
    if len(turns) > 1:
        pending = AssistantPendingRequest(
            command_name=case["pending_action"],
            original_turn_id="U1",
            publication_generation=1,
            parameters=(),
            sources=tuple(
                (f"U{number}", text) for number, text in enumerate(turns[:-1], 1)
            ),
        )
    return ContextAssembler.retrieval_query(turns[-1], pending_request=pending)


@pytest.mark.parametrize("version", [2, 3])
def test_frozen_labels_use_the_product_user_only_query(version):
    cases = load_admission_cases(version)
    corpus_ids = {
        entry["id"] for entry in json.loads(RAGConfig.get_gold_set_path().read_text())
    }
    assert all(set(ids) <= corpus_ids for ids in cases["acceptable_sets"].values())
    for split in ("calibration", "review"):
        assert len(cases[split]) == 12
        assert (
            sorted(Counter(case["family"] for case in cases[split]).values()) == [2] * 6
        )
        for case in cases[split]:
            query = case_retrieval_query(case)
            assert query == "\n".join(case["user_turns"])
            assert "Assistant:" not in query
            assert "User:" not in query


def test_v3_preserves_queries_and_old_labels_with_only_declared_corpus_additions():
    old, current = load_admission_cases(2), load_admission_cases(3)
    assert old.pop("version") == 2
    assert current.pop("version") == 3
    old.pop("rule")
    rule = current.pop("rule")
    assert rule == {
        "minimum_matched_terms": RAGConfig.MIN_SPARSE_MATCHED_TERMS,
        "minimum_coverage": RAGConfig.MIN_SPARSE_COVERAGE,
        "coverage_metric": "matched_idf_over_min_query_document_idf",
        "include_oov_in_query_denominator": True,
        "unique_query_and_document_terms": True,
    }
    additions = {
        "bandpass": [
            "apply_bandpass_filter_missing_01",
            "apply_bandpass_filter_partial_low_01",
            "apply_bandpass_filter_partial_high_01",
            "apply_bandpass_filter_supplement_01",
            "apply_bandpass_filter_correction_01",
        ],
        "notch": ["apply_notch_filter_missing_01"],
        "resample": ["resample_data_missing_01"],
        "reference": ["set_reference_missing_01"],
        "normalize": ["normalize_data_missing_01"],
    }
    for topic, example_ids in additions.items():
        assert (
            current["acceptable_sets"][topic]
            == old["acceptable_sets"][topic] + example_ids
        )
        current["acceptable_sets"][topic] = current["acceptable_sets"][topic][
            : -len(example_ids)
        ]
    assert current == old
