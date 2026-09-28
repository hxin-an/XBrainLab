#!/usr/bin/env python3
"""Verify the pinned XBrainLab RAG stack with real offline dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.agent.context_encoding import decode_untrusted_context
from XBrainLab.llm.rag import RAGConfig, RAGRetriever
from XBrainLab.llm.rag.example_policy import (
    example_decision_name,
    is_primary_workflow_example,
    prompt_proposal_from_metadata,
)
from XBrainLab.llm.rag.indexer import RAGIndexer

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT = ROOT / "build" / "dev-artifacts" / "rag-offline.json"
PROBE_PATH = Path(__file__).with_name("rag_verification_probes.json")
PROBE_SHA256 = "d4222a3e1595db23d45622ec0b29348e65482c0cb7eb3c3cb4bf880ad2d96822"  # pragma: allowlist secret
PAIRED_PROBE_PATH = Path(__file__).with_name("rag_paired_probes.json")
PAIRED_PROBE_SHA256 = "bd9608f783c9ef9d534153bf0e6135c249ae9c989546a6db3124f0a6e88c3f5e"  # pragma: allowlist secret
ADMISSION_PATH = ROOT / "tests/unit/llm/rag/retrieval_admission_cases_v5.json"
ADMISSION_SHA256 = "ce8433d10326e800ee4cc602fdabcd696dba47faa137e3794317071ee2fda054"  # pragma: allowlist secret
ADMISSION_CORPUS_SHA256 = "78c71aa304abd5443ec76c492278aef38c0a34d1479ef7cbbd9a471c96a9000f"  # pragma: allowlist secret
_ALLOWED_GIT_ARGUMENTS = frozenset(
    {
        ("rev-parse", "--show-toplevel"),
        ("rev-parse", "HEAD"),
        ("status", "--porcelain"),
    }
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the exact offline MiniLM embedding, local Qdrant index, "
            "retrieval contract, and repeat initialization."
        )
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--write-artifact", action="store_true")
    parser.add_argument("--artifact-path", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--baseline-report", type=Path)
    parser.add_argument("--ranking", choices=("hybrid", "dense"), default="hybrid")
    return parser.parse_args(argv)


def load_probes() -> dict[str, Any]:
    """Load the frozen engineering probes, never any model evaluation bank."""
    content = PROBE_PATH.read_bytes()
    if hashlib.sha256(content).hexdigest() != PROBE_SHA256:
        raise ValueError("Frozen RAG engineering probes changed.")
    probes = json.loads(content)
    positives = probes["positive_cases"]
    boundaries = probes["boundary_cases"]
    counts = Counter(case["tool"] for case in positives)
    cases = positives + boundaries
    if (
        counts != dict.fromkeys(AGENT_ACTION_CONTRACTS.model_tool_names(), 2)
        or len(boundaries) != 12
        or len({case["id"] for case in cases}) != 48
        or len({case["query"].casefold() for case in cases}) != 48
    ):
        raise ValueError(
            "RAG probes must retain 36 independent positives and 12 boundaries."
        )
    return probes


def stage_tool_publications() -> dict[str, Any]:
    """Reuse stage fixtures and the actual product assembler/capability policy."""
    from scripts.dev.run_stable_assistant_model_eval import (
        TargetEvalCase,
        _case_assembler,
        target_tool_registry,
    )
    from XBrainLab.llm.pipeline_state import PipelineStage

    registry = target_tool_registry()
    publications = {}
    for stage in PipelineStage:
        # Only the stage is consumed by the fixture; no oracle/question is loaded.
        case = TargetEvalCase(f"rag-{stage.value}", "", stage.value, "", {})
        assembler, _publication = _case_assembler(case, registry)
        assembler.get_messages([])
        publications[stage.value] = assembler.latest_tool_publication
    return publications


def load_paired_probes() -> list[dict[str, Any]]:
    """Load the separate frozen engineering pairs, not any research bank."""
    content = PAIRED_PROBE_PATH.read_bytes()
    if hashlib.sha256(content).hexdigest() != PAIRED_PROBE_SHA256:
        raise ValueError("Frozen paired RAG engineering probes changed.")
    cases = json.loads(content)
    pairs = Counter(case["pair_id"] for case in cases)
    if (
        len(cases) != 24
        or len({case["id"] for case in cases}) != 24
        or len({case["query"].casefold() for case in cases}) != 24
        or len(pairs) != 12
        or set(pairs.values()) != {2}
        or any(
            sum(
                case["expected_tool"] == "respond_to_user"
                for case in cases
                if case["pair_id"] == pair
            )
            != (2 if pair in {"bandpass", "normalize"} else 1)
            for pair in pairs
        )
        or any(
            case["expected_tool"] != "respond_to_user"
            or case["expected_parameters"] != {}
            or case.get("response_requirement") != "ask_which_to_do_first"
            for case in cases
            if case["category"] == "mixed_request"
        )
    ):
        raise ValueError(
            "RAG engineering probes must retain twelve pairs, including two mixed requests requiring a choose-first response."
        )
    return cases


def evaluate_probe_context(
    encoded_context: str,
    *,
    expected_tool: str | None,
    allowed_tools: frozenset[str],
) -> dict[str, Any]:
    """Score every returned candidate, including wrong and unauthorized ranks."""
    decoded = decode_untrusted_context(encoded_context)
    tools: list[str | None] = []
    valid = not encoded_context or decoded is not None
    for item in decoded or ():
        metadata = (
            {
                "proposal": item.data.get("expected_proposal"),
                "source_text": item.data.get("input"),
            }
            if isinstance(item.data, dict)
            else {}
        )
        if isinstance(item.data, dict) and "prior_turn" in item.data:
            metadata["prior_turn"] = item.data["prior_turn"]
        proposal = prompt_proposal_from_metadata(metadata)
        # Keep a malformed proposal's claimed action visible to the safety report.
        raw = metadata.get("proposal")
        action = raw.get("tool_name") if isinstance(raw, dict) else None
        tool = example_decision_name(metadata) if proposal is not None else action
        tools.append(tool if isinstance(tool, str) else None)
        valid = (
            valid
            and item.item_type == "rag_example"
            and isinstance(tool, str)
            and bool(tool)
            and proposal is not None
        )
    if decoded is not None:
        # The production decoder deliberately skips malformed rows; a verifier
        # must not let those rows disappear from its safety check.
        valid = valid and len(json.loads(encoded_context)["items"]) == len(decoded)
    unauthorized = sorted(
        {
            tool
            for tool in tools
            if tool and tool != "respond_to_user" and tool not in allowed_tools
        }
    )
    top1 = expected_tool is not None and bool(tools) and tools[0] == expected_tool
    top3 = expected_tool is not None and expected_tool in tools[:3]
    return {
        "ok": top3,
        "expected_tool": expected_tool,
        "observed_tool": tools[0] if tools else None,
        "item_count": len(tools),
        "candidate_tools": tools,
        "candidate_ids": [item.source.id for item in decoded or ()],
        "top1_hit": top1,
        "top3_hit": top3,
        "empty": not encoded_context,
        "wrong_candidate": bool(tools) and expected_tool is not None and not top3,
        "context_valid": valid,
        "membership_ok": valid and not unauthorized,
        "unauthorized_tools": unauthorized,
        "context_utf8_bytes": len(encoded_context.encode("utf-8")),
        "bounded": len(encoded_context.encode("utf-8")) <= RAGConfig.MAX_CONTEXT_CHARS
        and len(tools) <= RAGConfig.TOP_K,
    }


def load_admission_cases() -> dict[str, Any]:
    """Preserve the fixed v5 labels and the corpus against which they were set."""
    content = ADMISSION_PATH.read_bytes()
    if hashlib.sha256(content).hexdigest() != ADMISSION_SHA256:
        raise ValueError("Frozen v5 RAG admission fixture changed.")
    if (
        hashlib.sha256(RAGConfig.get_gold_set_path().read_bytes()).hexdigest()
        != ADMISSION_CORPUS_SHA256
    ):
        raise ValueError("Frozen v5 RAG admission corpus changed.")
    return json.loads(content)


def evaluate_admission_cases(
    retriever: RAGRetriever, fixture: dict[str, Any]
) -> dict[str, Any]:
    """Measure actual packed examples and an independent product sparse query.

    Dense candidates are not exposed by the product API. Do not recreate its
    admission or RRF here, or call the final three examples the entire branch.
    """
    from XBrainLab.llm.agent.assembler import ContextAssembler

    allowed = frozenset(fixture["eligible_tool_names"])
    rows = []
    for split in ("calibration", "review"):
        for case in fixture[split]:
            turns = case["user_turns"]
            if len(turns) != 1:
                raise ValueError("Current admission cases must be single-turn")
            query = ContextAssembler.retrieval_query(turns[-1])
            context = retriever.get_similar_examples(
                query, k=RAGConfig.TOP_K, allowed_tool_names=allowed
            )
            selected = evaluate_probe_context(
                context, expected_tool=None, allowed_tools=allowed
            )
            acceptable = set(fixture["acceptable_sets"][case["acceptable"]])
            selected_ids = selected["candidate_ids"]
            selected_wrong = sorted(set(selected_ids) - acceptable)
            selected_ok = (
                selected["membership_ok"] and selected["bounded"] and not selected_wrong
            )
            sparse = retriever.bm25_index
            sparse_ids = (
                [
                    row[1]
                    for row in sparse.query(
                        query,
                        k=RAGConfig.CANDIDATES_PER_BRANCH,
                        eligible=lambda metadata: retriever._example_is_allowed(
                            metadata, allowed_tool_names=allowed
                        ),
                    )
                ]
                if sparse is not None
                else []
            )
            sparse_wrong = sorted(set(sparse_ids) - acceptable)
            missing = sorted(set(case.get("required_sparse_ids", [])) - set(sparse_ids))
            rows.append(
                {
                    "id": case["id"],
                    "split": split,
                    "family": case["family"],
                    "query": query,
                    "acceptable_ids": sorted(acceptable),
                    "selected_examples": {
                        "ids": selected_ids,
                        "wrong_ids": selected_wrong,
                        "ok": selected_ok,
                    },
                    "sparse_candidates": {
                        "status": "observed" if sparse is not None else "not_assessed",
                        "ids": sparse_ids,
                        "wrong_ids": sparse_wrong,
                        "missing_required_ids": missing,
                        "ok": sparse is not None and not missing,
                    },
                }
            )
    rule_matches = fixture["rule"] == {
        "minimum_matched_terms": RAGConfig.MIN_SPARSE_MATCHED_TERMS,
        "minimum_coverage": RAGConfig.MIN_SPARSE_COVERAGE,
        "coverage_metric": "matched_idf_over_min_query_document_idf",
        "include_oov_in_query_denominator": True,
        "unique_query_and_document_terms": True,
    }
    return {
        "fixture_sha256": ADMISSION_SHA256,
        "corpus_sha256": ADMISSION_CORPUS_SHA256,
        "dense_candidates": {
            "status": "not_assessed",
            "reason": "Product API exposes only final packed examples, not dense branch admission.",
        },
        "acceptance_scope": "selected_relevance_and_required_sparse_ids",
        "rule_matches": rule_matches,
        "measured_checks_ok": rule_matches
        and len(rows) == 20
        and all(
            row["selected_examples"]["ok"] and row["sparse_candidates"]["ok"]
            for row in rows
        ),
        "cases": rows,
    }


def summarize_positive_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    hits = Counter(case["expected_tool"] for case in cases if case["top3_hit"])
    top3 = sum(bool(case["top3_hit"]) for case in cases)
    coverage = {
        tool: hits[tool] for tool in sorted(AGENT_ACTION_CONTRACTS.model_tool_names())
    }
    return {
        "positive_count": len(cases),
        "top1_hits": sum(bool(case["top1_hit"]) for case in cases),
        "top3_hits": top3,
        "empty_count": sum(bool(case["empty"]) for case in cases),
        "wrong_candidate_count": sum(bool(case["wrong_candidate"]) for case in cases),
        "per_tool_top3_hits": coverage,
        "gate_ok": len(cases) == 36 and top3 >= 33 and all(coverage.values()),
    }


def compare_baseline(
    report: dict[str, Any], baseline: dict[str, Any]
) -> dict[str, Any]:
    """Require comparable frozen probes and no individual Top-3 regression."""
    keys = (
        "probe_sha256",
        "embedding_model",
        "embedding_revision",
        "similarity_threshold",
        "top_k",
        "max_context_bytes",
        "max_example_content_chars",
    )
    comparable = all(
        key in report.get("identity", {})
        and report["identity"][key] == baseline.get("identity", {}).get(key)
        for key in keys
    ) and report.get("stage_publications") == baseline.get("stage_publications")
    current_hits = _verified_top3_hits(report)
    previous_hits = _verified_top3_hits(baseline)
    comparable = comparable and current_hits is not None and previous_hits is not None
    regressed = []
    if comparable:
        current_passes = {
            row["id"]
            for row in report["retrieval_cases"]
            if row["expected_tool"] in row["candidate_tools"]
        }
        regressed = sorted(
            row["id"]
            for row in baseline["retrieval_cases"]
            if row["expected_tool"] in row["candidate_tools"]
            and row["id"] not in current_passes
        )
    return {
        "name": "baseline_non_regression",
        "ok": comparable and not regressed,
        "regressed_case_ids": regressed,
        "detail": (
            f"Comparable={comparable}; verified Top-3 hits {current_hits} versus "
            f"{previous_hits}; regressed cases={regressed}."
        ),
    }


def _verified_top3_hits(report: dict[str, Any]) -> int | None:
    """Reconcile all frozen positive rows before trusting a summary score."""
    rows = report.get("retrieval_cases")
    if not isinstance(rows, list) or len(rows) != 36:
        return None
    by_id = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            return None
        by_id[row["id"]] = row
    if len(by_id) != 36:
        return None
    hits = 0
    for case in load_probes()["positive_cases"]:
        row = by_id.get(case["id"], {})
        if any(
            row.get(key) != case[source]
            for key, source in (
                ("expected_tool", "tool"),
                ("query", "query"),
                ("stage", "stage"),
            )
        ):
            return None
        candidates = row.get("candidate_tools")
        if (
            not isinstance(candidates, list)
            or len(candidates) > 3
            or any(not isinstance(tool, str) or not tool.strip() for tool in candidates)
        ):
            return None
        hits += case["tool"] in candidates
    summary = report.get("retrieval_summary", {})
    if not isinstance(summary, dict) or summary.get("positive_count") != 36:
        return None
    declared_hits = summary.get("top3_hits")
    return hits if type(declared_hits) is int and declared_hits == hits else None


def run_verification(*, dense_only: bool = False) -> dict[str, Any]:
    """Run the real local-only RAG gate and return a bounded report."""
    started = perf_counter()
    probes = load_probes()
    paired_probes = load_paired_probes()
    admission_fixture = load_admission_cases()
    checks: list[dict[str, object]] = []
    provenance = _git_provenance()
    _add_check(
        checks,
        "active_checkout",
        provenance["repo_root_matches_script"],
        "Command ran from the checkout that owns this script.",
    )

    corpus_ok = RAGConfig.gold_set_integrity_ok()
    _add_check(
        checks,
        "gold_set_integrity",
        corpus_ok,
        f"Pinned corpus SHA-256: {RAGConfig.GOLD_SET_SHA256}.",
    )
    embedding_ready = RAGConfig.embedding_cache_ready()
    _add_check(
        checks,
        "embedding_cache",
        embedding_ready,
        (
            "Exact MiniLM revision is available in the dedicated offline cache."
            if embedding_ready
            else "Exact MiniLM revision is missing from the dedicated offline cache."
        ),
    )

    expected_document_count = _count_indexable_examples() if corpus_ok else 0
    report: dict[str, Any] = {
        "schema": "xbrainlab.rag-verification.v5",
        "generated_at": datetime.now(UTC).isoformat(),
        "ok": False,
        "provenance": provenance,
        "identity": {
            "embedding_model": RAGConfig.EMBEDDING_MODEL,
            "embedding_revision": RAGConfig.EMBEDDING_REVISION,
            "embedding_license": RAGConfig.EMBEDDING_LICENSE,
            "corpus_sha256": RAGConfig.GOLD_SET_SHA256,
            "collection_name": RAGConfig.COLLECTION_NAME,
            "similarity_threshold": RAGConfig.SIMILARITY_THRESHOLD,
            "expected_document_count": expected_document_count,
            "offline_only": True,
            "probe_sha256": PROBE_SHA256,
            "paired_probe_sha256": PAIRED_PROBE_SHA256,
            "admission_fixture_sha256": ADMISSION_SHA256,
            "ranking": "dense" if dense_only else "rrf",
            "sparse_minimum_matched_terms": RAGConfig.MIN_SPARSE_MATCHED_TERMS,
            "sparse_minimum_coverage": RAGConfig.MIN_SPARSE_COVERAGE,
            "sparse_coverage_metric": "matched_idf_over_min_query_document_idf",
            "candidates_per_branch": RAGConfig.CANDIDATES_PER_BRANCH,
            "rrf_rank_constant": RAGConfig.RRF_RANK_CONSTANT,
            "top_k": RAGConfig.TOP_K,
            "max_context_bytes": RAGConfig.MAX_CONTEXT_CHARS,
            "max_example_content_chars": RAGConfig.MAX_EXAMPLE_CONTENT_CHARS,
        },
        "checks": checks,
        "retrieval_cases": [],
        "boundary_cases": [],
        "paired_cases": [],
        "claim_boundary": (
            "This verifies local embedding/index/retrieval behavior. It does not "
            "measure end-to-end local-LLM tool-call accuracy. Fixed v5 checks separate "
            "sparse candidates from final packed examples; dense candidate admission "
            "is not observed. Acceptance checks returned-example relevance and required "
            "sparse IDs, not candidate-pool purity, decision equivalence or end-to-end model benefit."
        ),
    }
    if not corpus_ok or not embedding_ready or expected_document_count <= 0:
        report["ok"] = False
        return report

    retriever = RAGRetriever(dense_only=dense_only)
    first_point_count = 0
    try:
        initialization_started = perf_counter()
        retriever.initialize()
        report["initialization_seconds"] = round(
            perf_counter() - initialization_started, 6
        )
        _add_check(
            checks,
            "retriever_initialized",
            retriever.is_initialized,
            "Retriever initialized with offline-only dependencies.",
        )
        if not retriever.is_initialized or retriever.client is None:
            return report

        manifest = _read_manifest()
        indexer = RAGIndexer(
            client=retriever.client,
            embeddings=retriever.embeddings,
        )
        indexed_docs = indexer.load_gold_set(str(RAGConfig.get_gold_set_path()))
        expected_point_ids = indexer.document_ids(indexed_docs)
        expected_manifest = RAGConfig.expected_index_manifest(
            expected_document_count,
            point_ids=expected_point_ids,
        )
        manifest_ok = manifest == expected_manifest
        _add_check(
            checks,
            "index_manifest",
            manifest_ok,
            "Index manifest matches the pinned embedding and bundled corpus.",
        )

        first_point_count = int(
            retriever.client.count(
                collection_name=RAGConfig.COLLECTION_NAME,
                exact=True,
            ).count
        )
        _add_check(
            checks,
            "index_point_count",
            first_point_count == expected_document_count,
            (
                f"Observed {first_point_count} points; "
                f"expected {expected_document_count}."
            ),
        )

        publications = stage_tool_publications()
        report["stage_publications"] = {
            stage: sorted(publication.tool_names)
            for stage, publication in publications.items()
        }
        admission = evaluate_admission_cases(retriever, admission_fixture)
        report["fixed_v5_admission"] = admission
        _add_check(
            checks,
            "fixed_v5_retrieval_admission",
            admission["measured_checks_ok"],
            "Fixed 10+10 single-turn cases: actual packed example relevance and product sparse candidates/required IDs; four retired multi-turn cases remain historical v3 evidence.",
        )
        retrieval_cases = []
        boundary_cases = []
        for case in probes["positive_cases"] + probes["boundary_cases"]:
            allowed_tools = publications[case["stage"]].tool_names
            case_started = perf_counter()
            context = retriever.get_similar_examples(
                case["query"],
                k=RAGConfig.TOP_K,
                allowed_tool_names=allowed_tools,
            )
            result = evaluate_probe_context(
                context,
                expected_tool=case.get("tool"),
                allowed_tools=allowed_tools,
            )
            result.update(
                {
                    "id": case["id"],
                    "query": case["query"],
                    "stage": case["stage"],
                    "allowed_tools": sorted(allowed_tools),
                    "duration_seconds": round(perf_counter() - case_started, 6),
                    "oracle_stage_valid": case.get("tool") in allowed_tools
                    if "tool" in case
                    else case.get("blocked_tool") not in allowed_tools,
                }
            )
            if "tool" in case:
                retrieval_cases.append(result)
            else:
                result.update(
                    {
                        "kind": case["kind"],
                        "historical_expect_empty": case.get("expect_empty", False),
                        "blocked_tool": case.get("blocked_tool"),
                        "ok": result["membership_ok"]
                        and case.get("blocked_tool") not in result["candidate_tools"],
                    }
                )
                boundary_cases.append(result)
        report["retrieval_cases"] = retrieval_cases
        report["boundary_cases"] = boundary_cases
        summary = summarize_positive_cases(retrieval_cases)
        report["retrieval_summary"] = summary
        _add_check(
            checks,
            "known_query_retrieval",
            summary["gate_ok"],
            f"Top-1 {summary['top1_hits']}/36; Top-3 {summary['top3_hits']}/36; require >=33 and >=1 per tool.",
        )
        _add_check(
            checks,
            "retrieval_context_safety",
            all(
                case["membership_ok"] and case["bounded"] and case["oracle_stage_valid"]
                for case in retrieval_cases + boundary_cases
            ),
            "Every candidate uses the real stage publication and bounded typed context.",
        )
        _add_check(
            checks,
            "request_scoped_tool_filter",
            all(case["ok"] for case in boundary_cases if case["kind"] == "blocked"),
            "Blocked tools were not injected under their real stage publication.",
        )
        _add_check(
            checks,
            "informational_context_safety",
            all(
                case["ok"] for case in boundary_cases if case["kind"] == "informational"
            ),
            "Information requests permit safe retrieved examples; model no-action is measured separately.",
        )
        paired_results = []
        for case in paired_probes:
            allowed_tools = publications[case["stage"]].tool_names
            case_started = perf_counter()
            context = retriever.get_similar_examples(
                case["query"], k=RAGConfig.TOP_K, allowed_tool_names=allowed_tools
            )
            result = evaluate_probe_context(
                context,
                expected_tool=case["expected_tool"],
                allowed_tools=allowed_tools,
            )
            result.update(
                **case,
                allowed_tools=sorted(allowed_tools),
                duration_seconds=round(perf_counter() - case_started, 6),
                oracle_stage_valid=case["expected_tool"] == "respond_to_user"
                or case["expected_tool"] in allowed_tools,
            )
            paired_results.append(result)
        report["paired_cases"] = paired_results
        _add_check(
            checks,
            "paired_context_safety",
            all(
                case["membership_ok"] and case["bounded"] and case["oracle_stage_valid"]
                for case in paired_results
            ),
            "Twenty-four separate paired probes preserve membership and bounds; retrieval hits are not model decisions.",
        )
    finally:
        retriever.close()

    second = RAGRetriever(dense_only=dense_only)
    try:
        repeat_started = perf_counter()
        second.initialize()
        report["repeat_initialization_seconds"] = round(
            perf_counter() - repeat_started, 6
        )
        second_count = (
            int(
                second.client.count(
                    collection_name=RAGConfig.COLLECTION_NAME,
                    exact=True,
                ).count
            )
            if second.is_initialized and second.client is not None
            else -1
        )
        _add_check(
            checks,
            "repeat_initialization",
            (
                second.is_initialized
                and first_point_count == expected_document_count
                and second_count == first_point_count
            ),
            (f"Point count remained {second_count} after a second initialization."),
        )
    finally:
        second.close()

    report["ok"] = all(bool(check["ok"]) for check in checks)
    report["duration_seconds"] = round(perf_counter() - started, 6)
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logger = logging.getLogger("XBrainLab.llm.rag")
    original_level = logger.level
    # Keep stdout machine-readable. Runtime diagnostics remain available in
    # the secure file log; the JSON report carries the public failure state.
    logger.setLevel(logging.CRITICAL + 1)
    try:
        try:
            report = (
                run_verification(dense_only=True)
                if args.ranking == "dense"
                else run_verification()
            )
            if args.baseline_report:
                baseline = json.loads(args.baseline_report.read_text(encoding="utf-8"))
                comparison = compare_baseline(report, baseline)
                report["checks"].append(comparison)
                report["ok"] = bool(report["ok"]) and comparison["ok"]
        except Exception as error:
            report = {
                "schema": "xbrainlab.rag-verification.v5",
                "generated_at": datetime.now(UTC).isoformat(),
                "ok": False,
                "checks": [
                    {
                        "name": "verification_runtime",
                        "ok": False,
                        "detail": (
                            "RAG verification could not complete "
                            f"({type(error).__name__})."
                        ),
                    }
                ],
                "claim_boundary": (
                    "No RAG readiness claim is supported by this failed run."
                ),
            }
    finally:
        logger.setLevel(original_level)

    if args.write_artifact:
        _write_json(args.artifact_path, report)
    if args.format == "json":
        sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(_render_text(report))
    return 1 if args.strict and not bool(report.get("ok")) else 0


def _count_indexable_examples() -> int:
    data = json.loads(RAGConfig.get_gold_set_path().read_text(encoding="utf-8"))
    count = 0
    for item in data:
        if not isinstance(item, dict) or not item.get("input"):
            continue
        metadata = {
            "id": item.get("id"),
            "category": item.get("category"),
            "proposal": item.get("expected_proposal"),
            "source_text": item["input"],
        }
        if "prior_turn" in item:
            metadata["prior_turn"] = item["prior_turn"]
        if is_primary_workflow_example(metadata):
            count += 1
    return count


def _read_manifest() -> dict[str, object] | None:
    try:
        value = json.loads(
            RAGConfig.get_index_manifest_path().read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _git_provenance() -> dict[str, object]:
    git_root = _git_text("rev-parse", "--show-toplevel")
    commit = _git_text("rev-parse", "HEAD")
    status = _git_text("status", "--porcelain", allow_empty=True)
    root_matches = bool(git_root) and Path(git_root).resolve() == ROOT
    return {
        "commit": commit or "unavailable",
        "worktree_dirty": bool(status),
        "repo_root_matches_script": root_matches,
    }


def _git_text(*args: str, allow_empty: bool = False) -> str:
    git_executable = shutil.which("git")
    if git_executable is None or args not in _ALLOWED_GIT_ARGUMENTS:
        return ""
    try:
        result = subprocess.run(  # noqa: S603 - executable and args are allowlisted.
            [git_executable, *args],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    text = result.stdout.strip()
    return text if text or allow_empty else ""


def _add_check(
    checks: list[dict[str, object]],
    name: str,
    ok: object,
    detail: str,
) -> None:
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def _write_json(path: Path, report: dict[str, Any]) -> None:
    target = path.expanduser().resolve(strict=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _render_text(report: dict[str, Any]) -> str:
    lines = [
        "XBrainLab offline RAG verification",
        f"Result: {'PASS' if report.get('ok') else 'FAIL'}",
    ]
    for check in report.get("checks", []):
        status = "PASS" if check.get("ok") else "FAIL"
        lines.append(f"- [{status}] {check.get('name')}: {check.get('detail')}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
