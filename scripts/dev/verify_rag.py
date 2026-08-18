#!/usr/bin/env python3
"""Verify the pinned XBrainLab RAG stack with real offline dependencies."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from XBrainLab.llm.agent.context_encoding import decode_untrusted_context
from XBrainLab.llm.rag import RAGConfig, RAGRetriever
from XBrainLab.llm.rag.example_policy import is_primary_workflow_example
from XBrainLab.llm.rag.indexer import RAGIndexer

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT = ROOT / "build" / "dev-artifacts" / "rag-offline.json"
_QUERY_CASES = (
    (
        "import_eeg_data",
        "Import an EEG dataset.",
        "import_eeg_data",
    ),
    (
        "bandpass",
        "Apply a bandpass filter from 4 to 40 Hz.",
        "apply_bandpass_filter",
    ),
    (
        "start_training",
        "Start training now.",
        "start_training",
    ),
)
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
    return parser.parse_args(argv)


def evaluate_context_result(
    encoded_context: str,
    *,
    expected_tool: str,
) -> dict[str, object]:
    """Evaluate one typed RAG result without treating it as instructions."""
    decoded = decode_untrusted_context(encoded_context)
    observed_tool: str | None = None
    if decoded:
        action = decoded[0].data.get("expected_action")
        if isinstance(action, dict):
            candidate = action.get("tool_name")
            if isinstance(candidate, str):
                observed_tool = candidate
    item_count = len(decoded or ())
    return {
        "ok": item_count > 0 and observed_tool == expected_tool,
        "expected_tool": expected_tool,
        "observed_tool": observed_tool,
        "item_count": item_count,
    }


def run_verification() -> dict[str, Any]:
    """Run the real local-only RAG gate and return a bounded report."""
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
        "schema": "xbrainlab.rag-verification.v1",
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
        },
        "checks": checks,
        "retrieval_cases": [],
        "claim_boundary": (
            "This verifies local embedding/index/retrieval behavior. It does not "
            "measure end-to-end local-LLM tool-call accuracy."
        ),
    }
    if not corpus_ok or not embedding_ready or expected_document_count <= 0:
        report["ok"] = False
        return report

    retriever = RAGRetriever()
    first_point_count = 0
    try:
        retriever.initialize()
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
        try:
            indexed_docs = indexer.load_gold_set(str(RAGConfig.get_gold_set_path()))
            expected_point_ids = indexer.document_ids(indexed_docs)
        finally:
            indexer.close()
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

        retrieval_cases = []
        for case_id, query, expected_tool in _QUERY_CASES:
            context = retriever.get_similar_examples(
                query,
                k=1,
                allowed_tool_names=frozenset({expected_tool}),
            )
            result = evaluate_context_result(
                context,
                expected_tool=expected_tool,
            )
            retrieval_cases.append({"id": case_id, **result})
        report["retrieval_cases"] = retrieval_cases
        _add_check(
            checks,
            "known_query_retrieval",
            all(bool(case["ok"]) for case in retrieval_cases),
            f"{sum(bool(case['ok']) for case in retrieval_cases)}/{len(retrieval_cases)} known queries matched.",
        )

        scoped_context = retriever.get_similar_examples(
            "Start training now.",
            k=1,
            allowed_tool_names=frozenset({"import_eeg_data"}),
        )
        _add_check(
            checks,
            "request_scoped_tool_filter",
            scoped_context == "",
            "A disallowed training example was not injected.",
        )

        no_tool_context = retriever.get_similar_examples(
            "Explain what an EEG epoch is.",
            k=1,
            allowed_tool_names=frozenset({"import_eeg_data"}),
        )
        _add_check(
            checks,
            "non_action_filter",
            no_tool_context == "",
            "An explanatory request did not receive an action example.",
        )
    finally:
        retriever.close()

    second = RAGRetriever()
    try:
        second.initialize()
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
            report = run_verification()
        except Exception as error:
            report = {
                "schema": "xbrainlab.rag-verification.v1",
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
            "tool_calls": json.dumps(item.get("expected_tool_calls")),
        }
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
