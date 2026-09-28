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
    parameters = {
        "switch_panel": {"panel_name": "evaluation"},
        "respond_to_user": {"message": "No operation will be performed."},
        "apply_bandpass_filter": {"low_freq": 2, "high_freq": 35},
        "apply_notch_filter": {"freq": 50},
        "resample_data": {"rate": 160},
        "set_reference": {"method": "average"},
        "normalize_data": {"method": "z-score"},
    }.get(tool_name, {})
    user_input = "test prompt " + json.dumps(parameters)
    proposal = {"tool_name": tool_name, "parameters": parameters}
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
                    "input": user_input,
                    "expected_proposal": proposal,
                },
            )
        ],
        max_chars=4_096,
        max_items=1,
        max_string_chars=768,
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


def test_response_example_is_legal_without_becoming_a_callable_tool() -> None:
    result = verify_rag.evaluate_probe_context(
        _encoded_tool_context("respond_to_user"),
        expected_tool="respond_to_user",
        allowed_tools=frozenset({"import_eeg_data"}),
    )
    assert result["membership_ok"] is True
    assert result["top1_hit"] is True


def test_prior_metadata_is_rejected_not_merged_by_verifier():
    payload = json.loads(_encoded_tool_context("apply_bandpass_filter"))
    payload["items"][0]["data"]["prior_turn"] = {"input": "2 Hz"}
    result = verify_rag.evaluate_probe_context(
        json.dumps(payload),
        expected_tool="apply_bandpass_filter",
        allowed_tools=frozenset({"apply_bandpass_filter"}),
    )
    assert not result["membership_ok"]


def test_index_count_contains_only_standalone_rows():
    corpus = json.loads(verify_rag.RAGConfig.get_gold_set_path().read_text())
    assert not any("prior_turn" in row for row in corpus)
    assert verify_rag._count_indexable_examples() == len(corpus) == 157


def test_response_name_does_not_hide_an_invalid_response_contract() -> None:
    payload = json.loads(_encoded_tool_context("respond_to_user"))
    payload["items"][0]["data"]["expected_proposal"]["parameters"]["message"] = None
    result = verify_rag.evaluate_probe_context(
        json.dumps(payload),
        expected_tool="respond_to_user",
        allowed_tools=frozenset(),
    )
    assert result["context_valid"] is False
    assert result["membership_ok"] is False


def test_paired_probes_are_separate_independent_and_stage_legal() -> None:
    paired = verify_rag.load_paired_probes()
    assert len(paired) == 24
    old = verify_rag.load_probes()
    old_queries = {
        case["query"].casefold()
        for case in old["positive_cases"] + old["boundary_cases"]
    }
    assert not old_queries.intersection(case["query"].casefold() for case in paired)
    publications = verify_rag.stage_tool_publications()
    for case in paired:
        assert case["expected_tool"] == "respond_to_user" or case["expected_tool"] in (
            publications[case["stage"]].tool_names
        )


def test_mixed_paired_probes_require_choose_first_without_partial_execution() -> None:
    mixed = [
        case
        for case in verify_rag.load_paired_probes()
        if case["category"] == "mixed_request"
    ]
    assert {case["id"] for case in mixed} == {
        "rag_pair_bandpass_action",
        "rag_pair_normalize_action",
    }
    for case in mixed:
        assert case["expected_tool"] == "respond_to_user"
        assert case["expected_parameters"] == {}
        assert case["response_requirement"] == "ask_which_to_do_first"


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
    # One repaired case must not conceal a different pass-to-fail regression.
    exchanged = json.loads(json.dumps(report))
    exchanged["retrieval_cases"][0]["candidate_tools"] = []
    exchanged["retrieval_cases"][34]["candidate_tools"] = [
        exchanged["retrieval_cases"][34]["expected_tool"]
    ]
    comparison = verify_rag.compare_baseline(exchanged, baseline)
    assert comparison["ok"] is False
    assert comparison["regressed_case_ids"] == [report["retrieval_cases"][0]["id"]]
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
        for case in probes["positive_cases"]
        + probes["boundary_cases"]
        + verify_rag.load_paired_probes()
    }
    observed: list[str] = []
    admission_fixture = verify_rag.load_admission_cases()
    admission_queries = {
        "\n".join(case["user_turns"])
        for split in ("calibration", "review")
        for case in admission_fixture[split]
    }
    observed_admission = []

    def retrieve(query, *, k, allowed_tool_names):
        if query in admission_queries:
            assert allowed_tool_names == frozenset(
                admission_fixture["eligible_tool_names"]
            )
            observed_admission.append(query)
            return ""
        case = cases[query]
        assert k == 3
        assert allowed_tool_names == publications[case["stage"]].tool_names
        assert len(allowed_tool_names) > 1
        observed.append(case["id"])
        tool = case.get("tool", case.get("expected_tool"))
        return _encoded_tool_context(tool) if tool else ""

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
    assert report["identity"]["sparse_minimum_matched_terms"] == 2
    assert report["identity"]["sparse_minimum_coverage"] == 0.5
    assert "sparse_threshold" not in report["identity"]
    assert len(observed) == 72
    assert set(observed_admission) == admission_queries
    assert len(observed_admission) == 20
    assert len(report["paired_cases"]) == 24
    assert report["retrieval_summary"]["top3_hits"] == 36
    # Existing positive probes cannot certify the newly frozen admission cases.
    assert report["ok"] is False
    assert any(
        check["name"] == "fixed_v4_retrieval_admission" and not check["ok"]
        for check in report["checks"]
    )
    assert report["fixed_v4_admission"]["dense_candidates"]["status"] == "not_assessed"
    assert (
        report["fixed_v4_admission"]["acceptance_scope"]
        == "selected_relevance_and_required_sparse_ids"
    )


@pytest.mark.parametrize("changed", ["fixture", "corpus"])
def test_admission_rejects_changed_frozen_inputs(tmp_path, monkeypatch, changed):
    path = tmp_path / "changed.json"
    path.write_text("{}", encoding="utf-8")
    if changed == "fixture":
        monkeypatch.setattr(verify_rag, "ADMISSION_PATH", path)
    else:
        monkeypatch.setattr(verify_rag.RAGConfig, "get_gold_set_path", lambda: path)
    with pytest.raises(ValueError, match="Frozen v4 RAG admission"):
        verify_rag.load_admission_cases()


def test_admission_keeps_real_sparse_candidates_distinct_from_wrong_final_examples():
    from XBrainLab.llm.rag.bm25 import BM25Index

    fixture = verify_rag.load_admission_cases()
    retriever = verify_rag.RAGRetriever()
    retriever.bm25_index = BM25Index()
    retriever.bm25_index.build_from_json(verify_rag.RAGConfig.get_gold_set_path())
    # Isolate only final context delivery; sparse admission/ranking stays real.
    wrong = json.loads(_encoded_tool_context("apply_notch_filter"))
    wrong["items"][0]["source"]["id"] = "apply_notch_filter_01"
    with patch.object(
        retriever, "get_similar_examples", return_value=json.dumps(wrong)
    ):
        result = verify_rag.evaluate_admission_cases(retriever, fixture)
    by_id = {row["id"]: row for row in result["cases"]}
    assert by_id["R01"]["sparse_candidates"]["missing_required_ids"] == []
    assert by_id["R01"]["selected_examples"]["wrong_ids"] == ["apply_notch_filter_01"]
    assert not by_id["R01"]["selected_examples"]["ok"]
    assert by_id["R02"]["sparse_candidates"]["missing_required_ids"] == []
    assert by_id["R02"]["sparse_candidates"]["ok"]
    assert "R10" not in by_id  # Retired multi-turn evidence stays only in v3.
    assert by_id["R12"]["query"] == "How long does a butterfly live?"
    assert result["measured_checks_ok"] is False
    assert result["fixture_sha256"] == verify_rag.ADMISSION_SHA256
    assert result["corpus_sha256"] == verify_rag.ADMISSION_CORPUS_SHA256


def test_admission_allows_empty_in_domain_but_requires_specified_sparse_ids():
    fixture = verify_rag.load_admission_cases()
    retriever = MagicMock()
    retriever.get_similar_examples.return_value = ""
    retriever.bm25_index.query.return_value = []
    result = verify_rag.evaluate_admission_cases(retriever, fixture)
    rows = {row["id"]: row for row in result["cases"]}
    assert rows["R03"]["selected_examples"]["ids"] == []
    assert rows["R03"]["selected_examples"]["ok"]
    assert rows["R03"]["sparse_candidates"]["ok"]
    assert rows["R02"]["selected_examples"]["ok"]
    assert not rows["R02"]["sparse_candidates"]["ok"]
    assert rows["R02"]["sparse_candidates"]["missing_required_ids"] == [
        "set_reference_07"
    ]
    assert not result["measured_checks_ok"]
    retriever.bm25_index.query.return_value = [
        (1.0, "apply_notch_filter_01", "candidate text", {})
    ]
    candidate_only = verify_rag.evaluate_admission_cases(retriever, fixture)
    row = next(row for row in candidate_only["cases"] if row["id"] == "R03")
    assert row["sparse_candidates"]["wrong_ids"] == ["apply_notch_filter_01"]
    assert row["sparse_candidates"]["ok"]
    assert row["selected_examples"]["ids"] == []


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
