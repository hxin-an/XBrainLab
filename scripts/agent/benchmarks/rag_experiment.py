#!/usr/bin/env python3
"""RAG Retrieval Quality Experiment (CPU-only).

Tests whether the RAG system can correctly retrieve relevant golden-set
examples given unseen user queries.  Runs entirely on CPU using
sentence-transformers (all-MiniLM-L6-v2) — no LLM or API needed.

Design:
    - Knowledge base : train.json  (indexed into a fresh Qdrant collection)
    - Evaluation set  : test.json   (held-out queries, never indexed)
    - For each test query we retrieve top-k examples and measure:
        * Tool Recall@k   — does any retrieved example share the same
                            expected tool_name as the query?
        * Category Recall  — does any retrieved example share the
                            same category?
        * MRR (Mean Reciprocal Rank) — position of the first
                            tool-name match in the ranked list
        * Exact-Match@1    — does the top-1 result have the exact same
                            tool_name AND category?

Usage:
    poetry run python scripts/agent/benchmarks/rag_experiment.py
    poetry run python scripts/agent/benchmarks/rag_experiment.py --eval-set val --k 5
"""

import argparse
import json
import shutil
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ── Project setup ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from XBrainLab.llm.rag.config import RAGConfig

DATA_DIR = Path(__file__).resolve().parent / "data"


# ═══════════════════════════════════════════════════════════════
# Indexing helpers
# ═══════════════════════════════════════════════════════════════


def build_index(train_path: Path, tmp_dir: str):
    """Build a Qdrant index from *train_path* in *tmp_dir*.

    Returns ``(client, embeddings, collection_name, index_metadata)``.
    *index_metadata* is a dict mapping each indexed doc's page_content
    to its metadata (tool_calls, category, id) for later evaluation.
    """
    from langchain.docstore.document import Document
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_community.vectorstores import Qdrant
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as rest

    embeddings = HuggingFaceEmbeddings(model_name=RAGConfig.EMBEDDING_MODEL)
    client = QdrantClient(path=tmp_dir)

    collection_name = "rag_experiment"
    client.create_collection(
        collection_name=collection_name,
        vectors_config=rest.VectorParams(size=384, distance=rest.Distance.COSINE),
    )

    with open(train_path, encoding="utf-8") as f:
        data = json.load(f)

    docs = []
    index_meta: dict[str, dict] = {}
    for item in data:
        content = item.get("input", "")
        tool_calls = item.get("expected_tool_calls", [])
        tool_names = [tc["tool_name"] for tc in tool_calls]
        metadata = {
            "id": item.get("id"),
            "category": item.get("category"),
            "tool_calls": json.dumps(tool_calls),
            "tool_names": json.dumps(tool_names),
        }
        if content:
            docs.append(Document(page_content=content, metadata=metadata))
            index_meta[content] = {
                "id": item.get("id"),
                "category": item.get("category"),
                "tool_names": tool_names,
            }

    vectorstore = Qdrant(
        client=client,
        collection_name=collection_name,
        embeddings=embeddings,
    )
    vectorstore.add_documents(docs)
    print(f"  Indexed {len(docs)} train examples (model: {RAGConfig.EMBEDDING_MODEL})")

    return client, embeddings, collection_name, index_meta


def retrieve(client, embeddings, collection_name: str, query: str, k: int):
    """Retrieve top-*k* results for *query*.

    Returns a list of dicts: ``[{page_content, category, tool_names, score}, ...]``
    """
    query_vector = embeddings.embed_query(query)
    results = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=k,
        with_payload=True,
        score_threshold=0.0,  # return everything, we evaluate rank
    ).points

    parsed = []
    for pt in results:
        payload = pt.payload or {}
        meta = payload.get("metadata", {})
        if not isinstance(meta, dict):
            meta = {}
        tool_names_str = meta.get("tool_names", "[]")
        try:
            tool_names = json.loads(tool_names_str)
        except (json.JSONDecodeError, TypeError):
            tool_names = []

        parsed.append(
            {
                "page_content": payload.get("page_content", ""),
                "category": meta.get("category", ""),
                "id": meta.get("id", ""),
                "tool_names": tool_names,
                "score": pt.score,
            }
        )
    return parsed


# ═══════════════════════════════════════════════════════════════
# Evaluation
# ═══════════════════════════════════════════════════════════════


def evaluate(test_cases: list[dict], client, embeddings, collection_name: str, k: int):
    """Run retrieval evaluation on *test_cases*.

    Returns a metrics dict and per-case detail list.
    """
    metrics = {
        "total": 0,
        "tool_recall_hits": 0,  # any retrieved has matching tool
        "category_recall_hits": 0,  # any retrieved has matching category
        "exact_match_at_1": 0,  # top-1 matches tool + category
        "reciprocal_ranks": [],  # for MRR calculation
        "per_category": defaultdict(
            lambda: {
                "total": 0,
                "tool_recall": 0,
                "cat_recall": 0,
                "exact1": 0,
            }
        ),
        "per_tool": defaultdict(
            lambda: {
                "total": 0,
                "tool_recall": 0,
                "exact1": 0,
                "rr_sum": 0.0,
            }
        ),
    }
    case_details = []

    for idx, case in enumerate(test_cases):
        metrics["total"] += 1
        user_input = case["input"]
        category = case.get("category", "unknown")
        expected_tools = [tc["tool_name"] for tc in case.get("expected_tool_calls", [])]
        expected_tool_set = set(expected_tools)

        cat_stats = metrics["per_category"][category]
        cat_stats["total"] += 1

        # Per-tool tracking (use first expected tool for single-tool cases)
        primary_tool = expected_tools[0] if expected_tools else "unknown"
        tool_stats = metrics["per_tool"][primary_tool]
        tool_stats["total"] += 1

        # Retrieve
        results = retrieve(client, embeddings, collection_name, user_input, k)

        # ── Tool Recall@k ──
        tool_hit = False
        first_tool_rank = None
        for rank, res in enumerate(results, 1):
            if expected_tool_set & set(res["tool_names"]):
                if first_tool_rank is None:
                    first_tool_rank = rank
                tool_hit = True

        if tool_hit:
            metrics["tool_recall_hits"] += 1
            cat_stats["tool_recall"] += 1
            metrics["reciprocal_ranks"].append(1.0 / first_tool_rank)
            tool_stats["tool_recall"] += 1
            tool_stats["rr_sum"] += 1.0 / first_tool_rank
        else:
            metrics["reciprocal_ranks"].append(0.0)

        # ── Category Recall@k ──
        cat_hit = any(res["category"] == category for res in results)
        if cat_hit:
            metrics["category_recall_hits"] += 1
            cat_stats["cat_recall"] += 1

        # ── Exact Match@1 (tool + category) ──
        exact1 = False
        if results:
            top1 = results[0]
            if (expected_tool_set & set(top1["tool_names"])) and top1[
                "category"
            ] == category:
                exact1 = True
                metrics["exact_match_at_1"] += 1
                cat_stats["exact1"] += 1
                tool_stats["exact1"] += 1

        # ── Log ──
        status = "✓" if tool_hit else "✗"
        retrieved_tools = [r["tool_names"] for r in results[:3]]
        score_str = f"score={results[0]['score']:.3f}" if results else "no results"
        print(
            f"  [{idx + 1:>2}/{len(test_cases)}] {status} {category:>12} | "
            f"expect={expected_tools}  "
            f"top-{min(3, k)} retrieved={retrieved_tools}  "
            f"{score_str}"
        )

        case_details.append(
            {
                "id": case.get("id"),
                "category": category,
                "input": user_input,
                "expected_tools": expected_tools,
                "tool_recall_hit": tool_hit,
                "category_recall_hit": cat_hit,
                "exact_match_at_1": exact1,
                "first_tool_rank": first_tool_rank,
                "top_results": [
                    {
                        "id": r["id"],
                        "tool_names": r["tool_names"],
                        "category": r["category"],
                        "score": round(r["score"], 4),
                    }
                    for r in results
                ],
            }
        )

    return metrics, case_details


# ═══════════════════════════════════════════════════════════════
# Reporting
# ═══════════════════════════════════════════════════════════════


def generate_report(metrics: dict, case_details: list, k: int, out_dir: Path):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    n = metrics["total"]
    tool_recall = metrics["tool_recall_hits"] / n * 100 if n else 0
    cat_recall = metrics["category_recall_hits"] / n * 100 if n else 0
    exact1 = metrics["exact_match_at_1"] / n * 100 if n else 0
    mrr = sum(metrics["reciprocal_ranks"]) / n if n else 0

    # ── Markdown ──
    md_path = out_dir / f"rag_retrieval_{timestamp}.md"
    lines = [
        "# RAG Retrieval Quality Report\n",
        f"**Date:** {timestamp}  ",
        f"**Embedding Model:** {RAGConfig.EMBEDDING_MODEL}  ",
        f"**k (top-k):** {k}  ",
        f"**Test Samples:** {n}\n",
        "## Overall Metrics\n",
        "| Metric | Value |",
        "|--------|------:|",
        f"| Tool Recall@{k} | {metrics['tool_recall_hits']}/{n} ({tool_recall:.1f}%) |",
        f"| Category Recall@{k} | {metrics['category_recall_hits']}/{n} ({cat_recall:.1f}%) |",
        f"| Exact Match@1 | {metrics['exact_match_at_1']}/{n} ({exact1:.1f}%) |",
        f"| MRR (Mean Reciprocal Rank) | {mrr:.4f} |",
        "",
        "## Per-Category Breakdown\n",
        f"| Category | Total | Tool Recall@{k} | Cat Recall@{k} | Exact@1 |",
        "|----------|------:|----------------:|---------------:|--------:|",
    ]
    for cat, s in sorted(metrics["per_category"].items()):
        t = s["total"]
        lines.append(
            f"| {cat} | {t} "
            f"| {s['tool_recall']}/{t} ({s['tool_recall'] / t * 100:.0f}%) "
            f"| {s['cat_recall']}/{t} ({s['cat_recall'] / t * 100:.0f}%) "
            f"| {s['exact1']}/{t} ({s['exact1'] / t * 100:.0f}%) |"
        )

    # Per-tool breakdown
    lines.append("\n## Per-Tool Breakdown\n")
    lines.append(f"| Tool | Total | Tool Recall@{k} | Exact@1 | MRR |")
    lines.append("|------|------:|----------------:|--------:|----:|")
    for tool_name, s in sorted(metrics["per_tool"].items()):
        t = s["total"]
        if t == 0:
            continue
        tool_mrr = s["rr_sum"] / t
        lines.append(
            f"| {tool_name} | {t} "
            f"| {s['tool_recall']}/{t} ({s['tool_recall'] / t * 100:.0f}%) "
            f"| {s['exact1']}/{t} ({s['exact1'] / t * 100:.0f}%) "
            f"| {tool_mrr:.3f} |"
        )

    # Failed cases
    failed = [c for c in case_details if not c["tool_recall_hit"]]
    if failed:
        lines.append(f"\n## Missed Retrievals ({len(failed)} cases)\n")
        for c in failed:
            top_ids = [r["id"] for r in c["top_results"][:3]]
            lines.append(
                f"- **{c['id']}** ({c['category']}): "
                f"expect `{c['expected_tools']}` — "
                f"retrieved: {top_ids}"
            )

    md_text = "\n".join(lines)
    md_path.write_text(md_text, encoding="utf-8")
    print(f"\n  Report: {md_path}")

    # ── JSON ──
    json_path = out_dir / f"rag_retrieval_{timestamp}.json"
    export = {
        "config": {
            "embedding_model": RAGConfig.EMBEDDING_MODEL,
            "k": k,
            "timestamp": timestamp,
        },
        "summary": {
            "total": n,
            "tool_recall": metrics["tool_recall_hits"],
            "category_recall": metrics["category_recall_hits"],
            "exact_match_at_1": metrics["exact_match_at_1"],
            "mrr": round(mrr, 4),
        },
        "per_category": dict(metrics["per_category"]),
        "per_tool": dict(metrics["per_tool"]),
        "cases": case_details,
    }
    json_path.write_text(
        json.dumps(export, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  JSON:   {json_path}")

    return tool_recall, cat_recall, exact1, mrr


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════


def main():
    ap = argparse.ArgumentParser(description="RAG Retrieval Quality Experiment (CPU)")
    ap.add_argument(
        "--eval-set",
        choices=["test", "val"],
        default="test",
        help="Which split to evaluate on (default: test)",
    )
    ap.add_argument("--k", type=int, default=3, help="Number of results to retrieve")
    args = ap.parse_args()

    train_path = DATA_DIR / "train.json"
    eval_path = DATA_DIR / f"{args.eval_set}.json"

    for p in [train_path, eval_path]:
        if not p.exists():
            print(f"ERROR: {p} not found. Run split_dataset.py first.")
            sys.exit(1)

    with open(eval_path, encoding="utf-8") as f:
        test_cases = json.load(f)
    print(f"Eval set : {eval_path.name} ({len(test_cases)} cases)")
    print(f"Top-k    : {args.k}")

    # ── Build index from train set ──
    print("\nBuilding RAG index from train set...")
    tmp_dir = tempfile.mkdtemp(prefix="rag_eval_")
    try:
        client, embeddings, col_name, _ = build_index(train_path, tmp_dir)

        # ── Evaluate ──
        print(f"\nEvaluating retrieval quality on {args.eval_set} set...\n")
        metrics, case_details = evaluate(
            test_cases,
            client,
            embeddings,
            col_name,
            args.k,
        )

        # ── Report ──
        out_dir = PROJECT_ROOT / "output" / "benchmarks"
        tool_r, cat_r, exact1, mrr = generate_report(
            metrics,
            case_details,
            args.k,
            out_dir,
        )

        # ── Quick summary ──
        n = metrics["total"]
        print(f"\n{'=' * 60}")
        print("RETRIEVAL QUALITY SUMMARY")
        print(f"{'=' * 60}")
        print(f"  Embedding       : {RAGConfig.EMBEDDING_MODEL}")
        with open(train_path, encoding="utf-8") as _tf:
            train_count = len(json.load(_tf))
        print(f"  Train examples  : {train_count}")
        print(f"  Eval examples   : {n}")
        print(f"  Top-k           : {args.k}")
        print(
            f"  Tool Recall@{args.k}   : {metrics['tool_recall_hits']}/{n} ({tool_r:.1f}%)"
        )
        print(
            f"  Cat  Recall@{args.k}   : {metrics['category_recall_hits']}/{n} ({cat_r:.1f}%)"
        )
        print(f"  Exact Match@1   : {metrics['exact_match_at_1']}/{n} ({exact1:.1f}%)")
        print(f"  MRR             : {mrr:.4f}")
        print()

    finally:
        client.close()
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
