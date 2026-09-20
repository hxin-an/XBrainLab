"""Contract tests for the real offline RAG verification command."""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.dev import verify_rag
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.agent.context_encoding import (
    UntrustedContextItem,
    UntrustedContextSource,
    encode_untrusted_context,
)


def _encoded_tool_context(tool_name: str) -> str:
    return encode_untrusted_context(
        [
            UntrustedContextItem(
                item_type="rag_example",
                source=UntrustedContextSource(
                    kind="xbrainlab_bundled_gold_set",
                    id="case-1",
                    category="test",
                ),
                data={
                    "input": "test prompt",
                    "expected_action": {
                        "tool_name": tool_name,
                        "parameters": {},
                    },
                },
            )
        ],
        max_chars=4_096,
        max_items=1,
        max_string_chars=768,
    )


def test_evaluate_context_result_requires_expected_tool() -> None:
    result = verify_rag.evaluate_context_result(
        _encoded_tool_context("import_eeg_data"),
        expected_tool="import_eeg_data",
    )

    assert result == {
        "ok": True,
        "expected_tool": "import_eeg_data",
        "observed_tool": "import_eeg_data",
        "item_count": 1,
    }


def test_evaluate_context_result_rejects_empty_or_wrong_context() -> None:
    assert (
        verify_rag.evaluate_context_result(
            "",
            expected_tool="start_training",
        )["ok"]
        is False
    )
    assert (
        verify_rag.evaluate_context_result(
            _encoded_tool_context("get_dataset_info"),
            expected_tool="start_training",
        )["ok"]
        is False
    )


def test_known_query_oracles_only_reference_approved_target_tools() -> None:
    probes = verify_rag.load_probes()
    positives = probes["positive_cases"]
    assert len(positives) == 36
    assert len(probes["boundary_cases"]) == 12
    assert {case["tool"] for case in positives} == (
        AGENT_ACTION_CONTRACTS.model_tool_names()
    )
    assert all(
        sum(case["tool"] == tool for case in positives) == 2
        for tool in AGENT_ACTION_CONTRACTS.model_tool_names()
    )


def _combine_contexts(*tools: str) -> str:
    payload = json.loads(_encoded_tool_context(tools[0]))
    payload["items"] = [
        json.loads(_encoded_tool_context(tool))["items"][0] for tool in tools
    ]
    return json.dumps(payload)


def test_rank_three_hit_does_not_hide_an_unauthorized_candidate() -> None:
    result = verify_rag.evaluate_probe_context(
        _combine_contexts("switch_panel", "get_dataset_info", "start_training"),
        expected_tool="start_training",
        allowed_tools=frozenset({"switch_panel", "start_training"}),
    )
    assert result["top1_hit"] is False
    assert result["top3_hit"] is True
    assert result["membership_ok"] is False
    assert result["unauthorized_tools"] == ["get_dataset_info"]


def test_empty_tool_name_cannot_hide_beside_a_valid_hit() -> None:
    result = verify_rag.evaluate_probe_context(
        _combine_contexts("start_training", ""),
        expected_tool="start_training",
        allowed_tools=frozenset({"switch_panel", "start_training"}),
    )
    assert result["top3_hit"] is True
    assert result["membership_ok"] is False


@pytest.mark.parametrize(
    "context", ["", "not json", _encoded_tool_context("switch_panel")]
)
def test_probe_distinguishes_empty_malformed_and_wrong_candidates(context: str) -> None:
    result = verify_rag.evaluate_probe_context(
        context,
        expected_tool="start_training",
        allowed_tools=frozenset({"switch_panel", "start_training"}),
    )
    assert result["top3_hit"] is False
    assert result["empty"] is (context == "")
    assert result["context_valid"] is (context != "not json")
    assert result["wrong_candidate"] is (
        context == _encoded_tool_context("switch_panel")
    )


def test_real_publications_cover_legal_probes_with_competing_tools() -> None:
    probes = verify_rag.load_probes()
    publications = verify_rag.stage_tool_publications()
    assert len(publications) == 7
    for case in probes["positive_cases"]:
        publication = publications[case["stage"]]
        assert case["tool"] in publication.tool_names, case["id"]
        assert len(publication.tool_names) > 1, case["id"]
    for case in probes["boundary_cases"]:
        if "blocked_tool" in case:
            assert case["blocked_tool"] not in publications[case["stage"]].tool_names


def test_probe_gate_requires_33_hits_and_every_tool() -> None:
    probes = verify_rag.load_probes()["positive_cases"]
    rows = [
        {
            **case,
            "expected_tool": case["tool"],
            "top1_hit": True,
            "top3_hit": True,
            "empty": False,
            "wrong_candidate": False,
        }
        for case in probes
    ]
    for row in rows[:2]:
        row["top3_hit"] = False
    summary = verify_rag.summarize_positive_cases(rows)
    assert summary["top3_hits"] == 34
    assert summary["gate_ok"] is False
    rows[1]["top3_hit"] = True
    for row in rows[3:8:2]:
        row["top3_hit"] = False
    assert verify_rag.summarize_positive_cases(rows)["gate_ok"] is False
    rows[3]["top3_hit"] = True
    assert verify_rag.summarize_positive_cases(rows)["gate_ok"] is True


def test_oversized_context_cannot_pass_the_retrieval_safety_gate() -> None:
    result = verify_rag.evaluate_probe_context(
        _encoded_tool_context("start_training") + " " * 4096,
        expected_tool="start_training",
        allowed_tools=frozenset({"start_training", "switch_panel"}),
    )
    assert result["bounded"] is False


def test_baseline_comparison_rejects_fewer_hits_or_changed_probe_identity() -> None:
    report = {
        "identity": {
            "probe_sha256": "frozen",
            "embedding_model": "pinned",
            "embedding_revision": "rev",
            "similarity_threshold": 0.7,
            "top_k": 3,
            "max_context_bytes": 4096,
            "max_example_content_chars": 768,
        },
        "stage_publications": {"empty": ["import_eeg_data", "switch_panel"]},
        "retrieval_summary": {"positive_count": 36, "top3_hits": 34},
        "retrieval_cases": [
            {
                "id": case["id"],
                "expected_tool": case["tool"],
                "stage": case["stage"],
                "query": case["query"],
                "candidate_tools": [case["tool"]] if index < 34 else [],
            }
            for index, case in enumerate(verify_rag.load_probes()["positive_cases"])
        ],
    }
    baseline = json.loads(json.dumps(report))
    assert verify_rag.compare_baseline(report, baseline)["ok"] is True
    baseline["retrieval_summary"]["top3_hits"] = 35
    baseline["retrieval_cases"][34]["candidate_tools"] = [
        baseline["retrieval_cases"][34]["expected_tool"]
    ]
    assert verify_rag.compare_baseline(report, baseline)["ok"] is False
    baseline["retrieval_summary"]["top3_hits"] = 32
    assert verify_rag.compare_baseline(report, baseline)["ok"] is False
    baseline["identity"]["probe_sha256"] = "different"
    assert verify_rag.compare_baseline(report, baseline)["ok"] is False
    baseline = json.loads(json.dumps(report))
    baseline["retrieval_cases"] = []
    assert verify_rag.compare_baseline(report, baseline)["ok"] is False


def test_verification_passes_the_entire_production_publication_to_retrieval() -> None:
    probes = verify_rag.load_probes()
    publications = verify_rag.stage_tool_publications()
    cases = {
        case["query"]: case
        for case in probes["positive_cases"] + probes["boundary_cases"]
    }
    observed: list[str] = []

    def retrieve(query, *, k, allowed_tool_names):
        case = cases[query]
        assert k == 3
        assert allowed_tool_names == publications[case["stage"]].tool_names
        assert len(allowed_tool_names) > 1
        observed.append(case["id"])
        return _encoded_tool_context(case["tool"]) if "tool" in case else ""

    retriever = MagicMock()
    retriever.is_initialized = True
    retriever.client.count.return_value.count = 1
    retriever.get_similar_examples.side_effect = retrieve
    indexer = MagicMock()
    indexer.document_ids.return_value = ["fixture-point"]
    manifest = verify_rag.RAGConfig.expected_index_manifest(
        1,
        point_ids=["fixture-point"],
    )
    with (
        patch.object(verify_rag, "RAGRetriever", return_value=retriever),
        patch.object(verify_rag, "RAGIndexer", return_value=indexer),
        patch.object(verify_rag, "_read_manifest", return_value=manifest),
        patch.object(verify_rag, "_count_indexable_examples", return_value=1),
        patch.object(verify_rag.RAGConfig, "gold_set_integrity_ok", return_value=True),
        patch.object(verify_rag.RAGConfig, "embedding_cache_ready", return_value=True),
        patch.object(
            verify_rag,
            "_git_provenance",
            return_value={"repo_root_matches_script": True},
        ),
    ):
        report = verify_rag.run_verification()
    assert len(observed) == 48
    assert report["retrieval_summary"]["top3_hits"] == 36
    assert report["ok"] is True


def test_strict_main_returns_failure_for_failed_report(capsys) -> None:
    failed = {
        "ok": False,
        "checks": [{"name": "embedding_cache", "ok": False}],
    }

    with patch.object(verify_rag, "run_verification", return_value=failed):
        exit_code = verify_rag.main(["--format", "json", "--strict"])

    assert exit_code == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_main_writes_the_same_json_artifact(tmp_path: Path, capsys) -> None:
    passed = {
        "ok": True,
        "checks": [{"name": "embedding_cache", "ok": True}],
    }
    artifact_path = tmp_path / "rag-verification.json"

    with patch.object(verify_rag, "run_verification", return_value=passed):
        exit_code = verify_rag.main(
            [
                "--format",
                "json",
                "--strict",
                "--write-artifact",
                "--artifact-path",
                str(artifact_path),
            ]
        )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == passed
    assert json.loads(artifact_path.read_text(encoding="utf-8")) == passed


def test_json_output_is_not_polluted_by_rag_runtime_logs(capsys) -> None:
    passed = {
        "ok": True,
        "checks": [{"name": "retriever_initialized", "ok": True}],
    }

    child_logger = logging.getLogger("XBrainLab.llm.rag.retriever")
    child_logger.setLevel(logging.NOTSET)
    emitted = io.StringIO()
    handler = logging.StreamHandler(emitted)
    child_logger.addHandler(handler)

    def run_with_error_log():
        child_logger.error("synthetic runtime diagnostic")
        return passed

    try:
        with patch.object(
            verify_rag,
            "run_verification",
            side_effect=run_with_error_log,
        ):
            assert verify_rag.main(["--format", "json", "--strict"]) == 0
    finally:
        child_logger.removeHandler(handler)
        handler.close()

    captured = capsys.readouterr()
    assert json.loads(captured.out) == passed
    assert "synthetic runtime diagnostic" not in captured.out
    assert emitted.getvalue() == ""
