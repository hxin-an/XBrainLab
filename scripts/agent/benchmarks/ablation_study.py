#!/usr/bin/env python3
"""Ablation Study Runner — Paper-Grade Causal Attribution.

Systematically disables individual verification-layer components and
re-runs the benchmark to measure each one's contribution.  Produces
a comparison table suitable for direct inclusion in a paper's Results
section.

Ablation Conditions:
    full        — all components enabled (baseline)
    no-rag      — RAG few-shot retrieval disabled
    no-stage    — stage gate disabled (all 19 tools visible)
    no-nudge    — nudge-and-retry on empty JSON disabled
    no-subseq   — subsequence / harmless-tool matching disabled
    no-norm     — event_id normalisation disabled

Usage:
    poetry run python scripts/agent/benchmarks/ablation_study.py \\
        --model gemini --dataset test.json --delay 1 --timeout 60
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import torch

# ── project root ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from scripts.agent.benchmarks.simple_bench import (
    BenchmarkAssembler,
    StageAwareBenchmarkAssembler,
    _check_ambiguity,
    _is_subsequence_match,
    _normalize_event_id,
    _TimeoutError,
    build_benchmark_rag,
    compute_rounds,
    infer_stage_for_tool,
    rag_retrieve,
    run_with_timeout,
)
from XBrainLab.llm.agent.parser import CommandParser
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine
from XBrainLab.llm.pipeline_state import PipelineStage
from XBrainLab.llm.tools import AVAILABLE_TOOLS
from XBrainLab.llm.tools.tool_registry import ToolRegistry

# ═══════════════════════════════════════════════════════════════
# Ablation flags — a simple frozen dataclass-like container
# ═══════════════════════════════════════════════════════════════

ABLATION_CONDITIONS: dict[str, dict[str, bool]] = {
    "full": {
        "rag": True,
        "stage_gate": True,
        "nudge": True,
        "subsequence": True,
        "event_norm": True,
    },
    "no-rag": {
        "rag": False,
        "stage_gate": True,
        "nudge": True,
        "subsequence": True,
        "event_norm": True,
    },
    "no-stage": {
        "rag": True,
        "stage_gate": False,
        "nudge": True,
        "subsequence": True,
        "event_norm": True,
    },
    "no-nudge": {
        "rag": True,
        "stage_gate": True,
        "nudge": False,
        "subsequence": True,
        "event_norm": True,
    },
    "no-subseq": {
        "rag": True,
        "stage_gate": True,
        "nudge": True,
        "subsequence": False,
        "event_norm": True,
    },
    "no-norm": {
        "rag": True,
        "stage_gate": True,
        "nudge": True,
        "subsequence": True,
        "event_norm": False,
    },
}


# ═══════════════════════════════════════════════════════════════
# Param comparison variant — event_id norm can be toggled
# ═══════════════════════════════════════════════════════════════


def compare_params_ablation(
    expected: dict,
    actual: dict,
    *,
    event_norm: bool = True,
) -> tuple[bool, str]:
    """Like ``compare_params`` but respects the *event_norm* flag."""
    if not expected and not actual:
        return True, ""
    if expected is None:
        return True, ""
    if not actual:
        return False, f"Expected params {expected}, got None/Empty"

    mismatches: list[str] = []
    for k, v in expected.items():
        if v is None:
            continue
        if k not in actual:
            mismatches.append(f"Missing param '{k}'")
            continue

        act_val = actual[k]

        # Float tolerance
        try:
            f_exp, f_act = float(v), float(act_val)
            if abs(f_exp - f_act) > 1e-5:
                mismatches.append(f"Param '{k}': expected '{v}', got '{act_val}'")
            continue
        except (ValueError, TypeError):
            pass

        # event_id normalisation (toggle-able)
        if k == "event_id" and event_norm:
            if _normalize_event_id(v) != _normalize_event_id(act_val):
                mismatches.append(
                    f"Param '{k}': expected "
                    f"'{_normalize_event_id(v)}', "
                    f"got '{_normalize_event_id(act_val)}' (normalized)"
                )
            continue

        # Standard string comparison
        if str(act_val) != str(v):
            mismatches.append(f"Param '{k}': expected '{v}', got '{act_val}'")

    return (True, "") if not mismatches else (False, "; ".join(mismatches))


# ═══════════════════════════════════════════════════════════════
# Single-condition evaluator
# ═══════════════════════════════════════════════════════════════

_NUDGE_PROMPT = (
    "You MUST respond with a JSON tool-call block. "
    "Do NOT explain or refuse. Output the JSON now."
)
_RETRIABLE = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE")


def _do_llm_call(engine, msgs, timeout_sec: int):
    """Single LLM call with retry."""

    def _infer():
        return "".join(engine.generate_stream(msgs))

    for attempt in range(3):
        try:
            return run_with_timeout(_infer, timeout_sec)
        except Exception as err:
            if any(c in str(err) for c in _RETRIABLE):
                wait = (2**attempt) * 5
                print(f"    Retriable error, retrying in {wait}s…")
                time.sleep(wait)
                if attempt == 2:
                    raise
            else:
                raise
    return None  # unreachable


def run_condition(
    condition_name: str,
    flags: dict[str, bool],
    test_cases: list[dict],
    engine: LLMEngine,
    parser: CommandParser,
    registry: ToolRegistry,
    rag_client,
    rag_embeddings,
    rag_collection: str,
    timeout_sec: int,
    delay_sec: float,
) -> dict:
    """Run a single ablation condition, return metrics dict."""
    print(f"\n{'=' * 70}")
    print(f"ABLATION CONDITION: {condition_name}")
    print(f"  Flags: {flags}")
    print(f"{'=' * 70}\n")

    use_stage = flags["stage_gate"]
    use_rag = flags["rag"]
    use_nudge = flags["nudge"]
    use_subseq = flags["subsequence"]
    use_norm = flags["event_norm"]

    # Build assembler
    if use_stage:
        assembler = StageAwareBenchmarkAssembler(registry)
    else:
        assembler = BenchmarkAssembler(registry, study_state=None)

    total = len(test_cases)
    passed = 0
    failed = 0
    errors = 0
    llm_calls = 0
    failure_types: Counter = Counter()
    per_case: list[dict] = []

    for idx, case in enumerate(test_cases):
        case_id = idx + 1
        user_input = case["input"]
        expected_list = case["expected_tool_calls"]
        category = case.get("category", "unknown")
        expected_tool = expected_list[0]["tool_name"] if expected_list else None

        # Compute rounds
        if use_stage and expected_list:
            initial_stage = infer_stage_for_tool(expected_list[0]["tool_name"])
            rounds = compute_rounds(expected_list, initial_stage)
        else:
            initial_stage = PipelineStage.EMPTY
            rounds = [(PipelineStage.EMPTY, expected_list)]

        try:
            assembler.clear_context()
            if use_rag and rag_client:
                ctx = rag_retrieve(
                    rag_client, rag_embeddings, rag_collection, user_input, k=3
                )
                if ctx:
                    assembler.add_context(ctx)

            conversation = [{"role": "user", "content": user_input}]
            all_actual: list[tuple] = []
            case_pass = True
            fail_reasons: list[str] = []

            for ri, (round_stage, round_expected) in enumerate(rounds):
                if use_stage and hasattr(assembler, "current_stage"):
                    assembler.current_stage = round_stage

                messages = assembler.get_messages(conversation)
                llm_calls += 1
                raw = _do_llm_call(engine, messages, timeout_sec)
                if raw is None:
                    case_pass = False
                    fail_reasons.append("No response")
                    break

                actual_calls = _parse(parser, raw)

                # Nudge
                if not actual_calls and use_nudge:
                    nudge_msgs = [
                        *messages,
                        {"role": "assistant", "content": raw},
                        {"role": "user", "content": _NUDGE_PROMPT},
                    ]
                    llm_calls += 1
                    retry = _do_llm_call(engine, nudge_msgs, timeout_sec)
                    if retry:
                        actual_calls = _parse(parser, retry)

                all_actual.extend(actual_calls)

                if not actual_calls:
                    case_pass = False
                    fail_reasons.append("No JSON Output")
                    break

                expected_names = [e["tool_name"] for e in round_expected]
                actual_names = [c[0] for c in actual_calls]

                if actual_names == expected_names:
                    for i, exp in enumerate(round_expected):
                        m, r = compare_params_ablation(
                            exp.get("parameters", {}),
                            actual_calls[i][1],
                            event_norm=use_norm,
                        )
                        if not m:
                            case_pass = False
                            fail_reasons.append(f"Param: {r}")
                else:
                    if use_subseq:
                        ok, _ = _is_subsequence_match(expected_names, actual_names)
                        if ok:
                            # verify params for matched
                            ai = 0
                            for exp in round_expected:
                                while ai < len(actual_calls):
                                    if actual_calls[ai][0] == exp["tool_name"]:
                                        m, r = compare_params_ablation(
                                            exp.get("parameters", {}),
                                            actual_calls[ai][1],
                                            event_norm=use_norm,
                                        )
                                        if not m:
                                            case_pass = False
                                            fail_reasons.append(f"Param: {r}")
                                        ai += 1
                                        break
                                    ai += 1
                        else:
                            case_pass = False
                            fail_reasons.append(
                                f"Tool: expected {expected_names}, got {actual_names}"
                            )
                    else:
                        # No subsequence: strict positional
                        for i, exp in enumerate(round_expected):
                            if i >= len(actual_calls):
                                case_pass = False
                                fail_reasons.append(f"Missing {exp['tool_name']}")
                                break
                            act_name, act_params = actual_calls[i]
                            if act_name != exp["tool_name"]:
                                if not _check_ambiguity(
                                    user_input, exp["tool_name"], act_name
                                ):
                                    case_pass = False
                                    fail_reasons.append(
                                        f"Tool: expected {exp['tool_name']}, "
                                        f"got {act_name}"
                                    )
                            else:
                                m, r = compare_params_ablation(
                                    exp.get("parameters", {}),
                                    act_params,
                                    event_norm=use_norm,
                                )
                                if not m:
                                    case_pass = False
                                    fail_reasons.append(f"Param: {r}")

                if not case_pass:
                    break

                # History for next round
                if ri < len(rounds) - 1:
                    conversation.append({"role": "assistant", "content": raw})
                    tool_out = "\n".join(
                        f"[Tool Output] {e['tool_name']}: executed successfully."
                        for e in round_expected
                    )
                    conversation.append({"role": "user", "content": tool_out})

            if case_pass:
                passed += 1
                status = "PASS"
            else:
                failed += 1
                status = "FAIL"
                for r in fail_reasons:
                    if "Param" in r:
                        failure_types["Param Mismatch"] += 1
                    elif "Tool" in r:
                        failure_types["Tool Mismatch"] += 1
                    elif "No JSON" in r:
                        failure_types["No JSON Output"] += 1
                    else:
                        failure_types["Other"] += 1

        except _TimeoutError:
            errors += 1
            status = "TIMEOUT"
            fail_reasons = ["Timeout"]
            failure_types["Timeout"] += 1
        except Exception as e:
            errors += 1
            status = "ERROR"
            fail_reasons = [str(e)]
            failure_types["API Error"] += 1

        per_case.append(
            {
                "case_id": case.get("id", f"case_{case_id}"),
                "status": status,
                "failure_reason": "; ".join(fail_reasons) if fail_reasons else "",
            }
        )

        print(
            f"  [{case_id:>2}/{total}] {status:5} "
            f"{category:>12} | {expected_tool or '?'}"
        )

        if delay_sec > 0:
            time.sleep(delay_sec)
        if idx % 10 == 0 and torch.cuda.is_available():
            torch.cuda.empty_cache()

    accuracy = passed / total * 100 if total else 0
    return {
        "condition": condition_name,
        "flags": flags,
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "accuracy": accuracy,
        "llm_calls": llm_calls,
        "failure_types": dict(failure_types),
        "per_case": per_case,
    }


def _parse(parser: CommandParser, raw: str) -> list[tuple]:
    parsed = parser.parse(raw)
    if not parsed:
        return []
    if isinstance(parsed, list) and parsed and isinstance(parsed[0], tuple):
        return parsed
    if isinstance(parsed, tuple):
        return [parsed]
    return []


# ═══════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════


def run_ablation(
    model_name: str,
    timeout_sec: int = 60,
    delay_sec: float = 1,
    dataset_name: str = "test.json",
    conditions: list[str] | None = None,
):
    """Run all ablation conditions and produce a comparison report."""

    MODEL_CONFIGS = {
        "gemini": {
            "inference_mode": "gemini",
            "gemini_model_name": os.environ.get(
                "GEMINI_MODEL_NAME", "gemini-2.0-flash"
            ),
        },
        "qwen": {"model_name": "Qwen/Qwen2.5-7B-Instruct", "inference_mode": "local"},
    }

    if model_name not in MODEL_CONFIGS:
        print(f"Unknown model: {model_name}")
        return

    data_dir = PROJECT_ROOT / "scripts" / "agent" / "benchmarks" / "data"
    test_file = data_dir / dataset_name
    train_file = data_dir / "train.json"
    for p in [test_file, train_file]:
        if not p.exists():
            print(f"Missing: {p}")
            return

    with open(test_file, encoding="utf-8") as f:
        test_cases = json.load(f)

    # Model
    config = LLMConfig(**MODEL_CONFIGS[model_name])
    engine = LLMEngine(config)
    engine.load_model()

    # Tools
    registry = ToolRegistry()
    for tool in AVAILABLE_TOOLS:
        registry.register(tool)

    parser = CommandParser()

    # RAG (built once, reused across conditions)
    print("Building RAG index from train split…")
    rag_tmp = tempfile.mkdtemp(prefix="ablation_rag_")
    rag_client, rag_emb, rag_col = build_benchmark_rag(train_file, rag_tmp)
    print("RAG ready.\n")

    # Which conditions to run?
    if conditions:
        run_conds = {c: ABLATION_CONDITIONS[c] for c in conditions}
    else:
        run_conds = ABLATION_CONDITIONS

    all_results: list[dict] = []
    try:
        for cond_name, flags in run_conds.items():
            result = run_condition(
                cond_name,
                flags,
                test_cases,
                engine,
                parser,
                registry,
                rag_client if flags["rag"] else None,
                rag_emb if flags["rag"] else None,
                rag_col if flags["rag"] else "",
                timeout_sec,
                delay_sec,
            )
            all_results.append(result)
    except KeyboardInterrupt:
        print("\nInterrupted — saving partial results.")
    finally:
        rag_client.close()
        shutil.rmtree(rag_tmp, ignore_errors=True)

    # ── Report ──
    _generate_ablation_report(all_results, model_name, dataset_name)
    del engine


def _generate_ablation_report(
    results: list[dict],
    model_name: str,
    dataset_name: str,
):
    """Write Markdown + JSON ablation report."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / "output" / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Find baseline (full) ──
    baseline_acc = None
    for r in results:
        if r["condition"] == "full":
            baseline_acc = r["accuracy"]
            break

    # ── Markdown ──
    md_path = out_dir / f"ablation_{model_name}_{timestamp}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Ablation Study Report: {model_name}\n\n")
        f.write(f"**Date:** {timestamp}  \n")
        f.write(f"**Dataset:** {dataset_name}  \n")
        f.write(f"**Cases:** {results[0]['total'] if results else 0}  \n\n")

        f.write("## Condition Comparison\n\n")
        f.write(
            "| Condition | Accuracy | Δ vs Full | Passed | Failed | "
            "Errors | LLM Calls |\n"
        )
        f.write(
            "|-----------|--------:|----------:|-------:|-------:|-------:|----------:|\n"
        )
        for r in results:
            delta = (
                f"{r['accuracy'] - baseline_acc:+.1f}pp"
                if baseline_acc is not None
                else "—"
            )
            if r["condition"] == "full":
                delta = "baseline"
            f.write(
                f"| **{r['condition']}** | {r['accuracy']:.1f}% | {delta} | "
                f"{r['passed']} | {r['failed']} | {r['errors']} | "
                f"{r['llm_calls']} |\n"
            )

        # Component contribution (Δ from full)
        f.write("\n## Component Contribution (Δ from Full Baseline)\n\n")
        f.write("| Disabled Component | Accuracy Drop | Interpretation |\n")
        f.write("|-------------------|-------------:|----------------|\n")
        for r in results:
            if r["condition"] == "full" or baseline_acc is None:
                continue
            drop = baseline_acc - r["accuracy"]
            interp = "Critical" if drop > 3 else "Important" if drop > 1 else "Marginal"
            disabled = r["condition"].replace("no-", "").replace("-", " ").title()
            f.write(f"| {disabled} | {drop:+.1f}pp | {interp} |\n")

        # Failure type breakdown per condition
        f.write("\n## Failure Types per Condition\n\n")
        all_types = sorted({ft for r in results for ft in r.get("failure_types", {})})
        header = "| Condition | " + " | ".join(all_types) + " |"
        sep = "|---|" + "|".join(["---:"] * len(all_types)) + "|"
        f.write(header + "\n" + sep + "\n")
        for r in results:
            ft = r.get("failure_types", {})
            vals = " | ".join(str(ft.get(t, 0)) for t in all_types)
            f.write(f"| {r['condition']} | {vals} |\n")

        # Per-case delta (which cases flip between full and ablated)
        if len(results) >= 2 and baseline_acc is not None:
            baseline_cases = {c["case_id"]: c["status"] for c in results[0]["per_case"]}
            f.write("\n## Case-Level Impact (Flipped Cases)\n\n")
            f.write("| Case ID | Full | Ablated Condition | Ablated Status |\n")
            f.write("|---------|------|-------------------|----------------|\n")
            for r in results[1:]:
                for c in r["per_case"]:
                    base_st = baseline_cases.get(c["case_id"], "?")
                    if base_st != c["status"]:
                        f.write(
                            f"| {c['case_id']} | {base_st} | "
                            f"{r['condition']} | {c['status']} |\n"
                        )

    print(f"\n  Ablation Report: {md_path}")

    # ── JSON ──
    json_path = out_dir / f"ablation_{model_name}_{timestamp}.json"
    export = {
        "model": model_name,
        "dataset": dataset_name,
        "timestamp": timestamp,
        "conditions": results,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)
    print(f"  Ablation JSON:   {json_path}")

    # ── Summary ──
    print(f"\n{'=' * 60}")
    print("ABLATION STUDY SUMMARY")
    print(f"{'=' * 60}")
    for r in results:
        delta = ""
        if baseline_acc is not None and r["condition"] != "full":
            delta = f" (Δ {r['accuracy'] - baseline_acc:+.1f}pp)"
        print(f"  {r['condition']:12} : {r['accuracy']:5.1f}%{delta}")
    print()


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════


def main():
    ap = argparse.ArgumentParser(description="Ablation Study Runner")
    ap.add_argument("--model", required=True)
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--delay", type=float, default=1)
    ap.add_argument("--dataset", default="test.json")
    ap.add_argument(
        "--conditions",
        nargs="+",
        choices=list(ABLATION_CONDITIONS.keys()),
        default=None,
        help="Run specific conditions only (default: all)",
    )
    args = ap.parse_args()
    run_ablation(
        args.model,
        args.timeout,
        args.delay,
        args.dataset,
        args.conditions,
    )


if __name__ == "__main__":
    main()
