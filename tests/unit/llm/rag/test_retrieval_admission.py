"""Current admission keeps all 20 historical single-turn queries unchanged."""

import json
from pathlib import Path

import pytest

from XBrainLab.llm.agent.assembler import ContextAssembler
from XBrainLab.llm.rag.config import RAGConfig


def load_admission_cases(version=4):
    return json.loads(
        Path(__file__)
        .with_name(f"retrieval_admission_cases_v{version}.json")
        .read_text()
    )


def test_v4_preserves_every_single_turn_query_and_only_removes_retired_context_ids():
    old, current = load_admission_cases(3), load_admission_cases()
    assert current["version"] == 4
    assert current["rule"] == old["rule"]
    assert current["eligible_tool_names"] == old["eligible_tool_names"]
    removed = {
        "apply_bandpass_filter_supplement_01",
        "apply_bandpass_filter_correction_01",
    }
    for topic, ids in old["acceptable_sets"].items():
        assert current["acceptable_sets"][topic] == [
            identity for identity in ids if identity not in removed
        ]
    for split in ("calibration", "review"):
        assert len(current[split]) == 10
        assert current[split] == [
            case for case in old[split] if len(case["user_turns"]) == 1
        ]
        assert sum(case["family"] == "unrelated" for case in current[split]) == 2


def test_single_turn_query_cannot_accept_past_draft_values():
    assert ContextAssembler.retrieval_query("30 Hz.") == "30 Hz."
    with pytest.raises(TypeError):
        ContextAssembler.retrieval_query("30 Hz.", pending_request=object())


def test_current_labels_reference_only_current_corpus_and_real_query():
    corpus_ids = {
        row["id"] for row in json.loads(RAGConfig.get_gold_set_path().read_text())
    }
    fixture = load_admission_cases()
    assert all(set(ids) <= corpus_ids for ids in fixture["acceptable_sets"].values())
    for split in ("calibration", "review"):
        for case in fixture[split]:
            assert (
                ContextAssembler.retrieval_query(case["user_turns"][0])
                == case["user_turns"][0]
            )
