#!/usr/bin/env python3
"""Multi-Turn Conversation Benchmark — Evaluates coreference, memory, and correction.

Unlike the single-turn ``simple_bench.py``, this evaluator maintains
conversation history across turns within each test case, testing whether
the LLM can:
    1. Resolve coreferences ("it", "that", "the same")
    2. Remember parameters from earlier turns
    3. Handle mid-conversation corrections
    4. Execute multi-turn pipeline sequences

Usage:
    poetry run python scripts/agent/benchmarks/multiturn_bench.py \\
        --model gemini --delay 1 --timeout 60
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from scripts.agent.benchmarks.simple_bench import (
    StageAwareBenchmarkAssembler,
    _is_subsequence_match,
    build_benchmark_rag,
    compare_params,
    infer_stage_for_tool,
    rag_retrieve,
    run_with_timeout,
    simulate_stage_transition,
)
from XBrainLab.llm.agent.parser import CommandParser
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine
from XBrainLab.llm.pipeline_state import PipelineStage
from XBrainLab.llm.tools import AVAILABLE_TOOLS
from XBrainLab.llm.tools.tool_registry import ToolRegistry

DATA_DIR = PROJECT_ROOT / "scripts" / "agent" / "benchmarks" / "data"

_RETRIABLE = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE")
_NUDGE_PROMPT = (
    "You MUST respond with a JSON tool-call block. "
    "Do NOT explain or refuse. Output the JSON now."
)


def _do_llm_call(engine: LLMEngine, msgs: list[dict], timeout_sec: int):
    def _infer():
        return "".join(engine.generate_stream(msgs))

    for attempt in range(3):
        try:
            return run_with_timeout(_infer, timeout_sec)
        except Exception as err:
            if any(c in str(err) for c in _RETRIABLE):
                wait = (2**attempt) * 5
                print(f"    Retriable error, waiting {wait}s…")
                time.sleep(wait)
                if attempt == 2:
                    raise
            else:
                raise
    return None


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
# Turn-level evaluation
# ═══════════════════════════════════════════════════════════════


def run_multiturn_benchmark(
    model_name: str,
    timeout_sec: int = 60,
    delay_sec: float = 1,
):
    """Run multi-turn conversation benchmark."""

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

    conv_file = DATA_DIR / "conversation_test_set.json"
    train_file = DATA_DIR / "train.json"
    for p in [conv_file, train_file]:
        if not p.exists():
            print(f"Missing: {p}")
            return

    with open(conv_file, encoding="utf-8") as f:
        test_cases = json.load(f)

    config = LLMConfig(**MODEL_CONFIGS[model_name])
    engine = LLMEngine(config)
    engine.load_model()

    registry = ToolRegistry()
    for tool in AVAILABLE_TOOLS:
        registry.register(tool)
    parser = CommandParser()

    # RAG
    print("Building RAG index…")
    rag_tmp = tempfile.mkdtemp(prefix="mt_rag_")
    rag_client, rag_emb, rag_col = build_benchmark_rag(train_file, rag_tmp)
    print("Ready.\n")

    assembler = StageAwareBenchmarkAssembler(registry)

    total_turns = 0
    passed_turns = 0
    total_cases = len(test_cases)
    passed_cases = 0
    llm_calls = 0
    category_stats: dict[str, dict] = {}
    all_results: list[dict] = []

    try:
        for ci, case in enumerate(test_cases):
            case_id = case["id"]
            category = case.get("category", "unknown")
            turns = case["turns"]
            n_turns = len(turns)
            description = case.get("description", "")

            if category not in category_stats:
                category_stats[category] = {
                    "total_cases": 0,
                    "passed_cases": 0,
                    "total_turns": 0,
                    "passed_turns": 0,
                }
            category_stats[category]["total_cases"] += 1

            print(f"\n{'─' * 60}")
            print(f"[{ci + 1}/{total_cases}] {case_id} ({category})")
            print(f"  {description}")
            print(f"  Turns: {n_turns}")

            # Build conversation history across turns
            conversation: list[dict] = []
            current_stage = PipelineStage.EMPTY
            case_all_pass = True
            turn_results: list[dict] = []

            for ti, turn in enumerate(turns):
                total_turns += 1
                category_stats[category]["total_turns"] += 1

                user_content = turn["content"]
                expected_calls = turn["expected_tool_calls"]
                expected_names = [e["tool_name"] for e in expected_calls]

                conversation.append({"role": "user", "content": user_content})

                # Stage for this turn's expected tools
                if expected_calls:
                    first_tool = expected_calls[0]["tool_name"]
                    needed_stage = infer_stage_for_tool(first_tool)
                    # Advance stage if needed
                    if needed_stage != current_stage and _stage_order(
                        needed_stage
                    ) > _stage_order(current_stage):
                        current_stage = needed_stage
                assembler.current_stage = current_stage

                # RAG context (per turn, like production)
                assembler.clear_context()
                ctx = rag_retrieve(rag_client, rag_emb, rag_col, user_content, k=3)
                if ctx:
                    assembler.add_context(ctx)

                messages = assembler.get_messages(conversation)

                # LLM call
                llm_calls += 1
                raw = _do_llm_call(engine, messages, timeout_sec)

                if raw is None:
                    turn_results.append(
                        _turn_result(
                            ti, user_content, expected_names, [], "No response"
                        )
                    )
                    case_all_pass = False
                    conversation.append(
                        {"role": "assistant", "content": "[No response]"}
                    )
                    continue

                actual_calls = _parse(parser, raw)

                # Nudge if needed
                if not actual_calls:
                    nudge_msgs = [
                        *messages,
                        {"role": "assistant", "content": raw},
                        {"role": "user", "content": _NUDGE_PROMPT},
                    ]
                    llm_calls += 1
                    retry = _do_llm_call(engine, nudge_msgs, timeout_sec)
                    if retry:
                        actual_calls = _parse(parser, retry)
                        raw += "\n[NUDGE]\n" + retry

                actual_names = [c[0] for c in actual_calls]

                # Evaluate
                turn_pass = True
                fail_reason = ""

                if not actual_calls:
                    turn_pass = False
                    fail_reason = "No JSON Output"
                elif actual_names == expected_names:
                    # Exact tool match → verify params
                    for i, exp in enumerate(expected_calls):
                        m, r = compare_params(
                            exp.get("parameters", {}),
                            actual_calls[i][1] if i < len(actual_calls) else {},
                        )
                        if not m:
                            turn_pass = False
                            fail_reason = f"Param: {r}"
                            break
                else:
                    # Try subsequence
                    ok, _ = _is_subsequence_match(expected_names, actual_names)
                    if ok:
                        # Verify params of matched tools
                        ai = 0
                        for exp in expected_calls:
                            while ai < len(actual_calls):
                                if actual_calls[ai][0] == exp["tool_name"]:
                                    m, r = compare_params(
                                        exp.get("parameters", {}),
                                        actual_calls[ai][1],
                                    )
                                    if not m:
                                        turn_pass = False
                                        fail_reason = f"Param: {r}"
                                    ai += 1
                                    break
                                ai += 1
                    else:
                        turn_pass = False
                        fail_reason = (
                            f"Tool mismatch: expected {expected_names}, "
                            f"got {actual_names}"
                        )

                if turn_pass:
                    passed_turns += 1
                    category_stats[category]["passed_turns"] += 1
                    status = "PASS"
                else:
                    case_all_pass = False
                    status = "FAIL"

                turn_results.append(
                    _turn_result(
                        ti, user_content, expected_names, actual_names, fail_reason
                    )
                )

                print(
                    f"  Turn {ti + 1}/{n_turns}: {status:5} "
                    f"expected={expected_names} actual={actual_names}"
                )
                if fail_reason:
                    print(f"    Reason: {fail_reason}")

                # Add assistant response to history for next turn
                conversation.append({"role": "assistant", "content": raw})

                # Simulate tool execution result
                if actual_calls:
                    tool_out = "\n".join(
                        f"[Tool Output] {c[0]}: executed successfully."
                        for c in actual_calls
                    )
                    conversation.append({"role": "user", "content": tool_out})
                    # Auto-remove the tool output from visible "user turns"
                    # but keep in conversation for context

                # State transitions
                for exp in expected_calls:
                    current_stage = simulate_stage_transition(
                        current_stage, exp["tool_name"]
                    )

                if delay_sec > 0:
                    time.sleep(delay_sec)

            if case_all_pass:
                passed_cases += 1
                category_stats[category]["passed_cases"] += 1
                print(f"  Case: PASS (all {n_turns} turns)")
            else:
                print("  Case: FAIL")

            all_results.append(
                {
                    "case_id": case_id,
                    "category": category,
                    "description": description,
                    "n_turns": n_turns,
                    "case_passed": case_all_pass,
                    "turns": turn_results,
                }
            )

            if ci % 5 == 0 and torch.cuda.is_available():
                torch.cuda.empty_cache()

    except KeyboardInterrupt:
        print("\nInterrupted — saving partial results.")
    finally:
        rag_client.close()
        shutil.rmtree(rag_tmp, ignore_errors=True)

    # ── Report ──
    _generate_report(
        all_results,
        model_name,
        total_cases,
        passed_cases,
        total_turns,
        passed_turns,
        llm_calls,
        category_stats,
    )
    del engine


def _turn_result(
    turn_idx: int,
    user_input: str,
    expected: list[str],
    actual: list[str],
    fail_reason: str,
) -> dict:
    return {
        "turn": turn_idx + 1,
        "input": user_input,
        "expected_tools": expected,
        "actual_tools": actual,
        "status": "PASS" if not fail_reason else "FAIL",
        "failure_reason": fail_reason,
    }


_STAGE_ORDER_MAP = {
    PipelineStage.EMPTY: 0,
    PipelineStage.DATA_LOADED: 1,
    PipelineStage.PREPROCESSED: 2,
    PipelineStage.DATASET_READY: 3,
    PipelineStage.TRAINING: 4,
    PipelineStage.TRAINED: 5,
}


def _stage_order(stage: PipelineStage) -> int:
    return _STAGE_ORDER_MAP.get(stage, 0)


def _generate_report(
    results: list[dict],
    model_name: str,
    total_cases: int,
    passed_cases: int,
    total_turns: int,
    passed_turns: int,
    llm_calls: int,
    category_stats: dict[str, dict],
):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / "output" / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)

    case_acc = passed_cases / total_cases * 100 if total_cases else 0
    turn_acc = passed_turns / total_turns * 100 if total_turns else 0

    # ── Markdown ──
    md_path = out_dir / f"multiturn_{model_name}_{timestamp}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Multi-Turn Conversation Benchmark: {model_name}\n\n")
        f.write(f"**Date:** {timestamp}  \n")
        f.write(f"**Total Conversations:** {total_cases}  \n")
        f.write(f"**Total Turns:** {total_turns}  \n")
        f.write(f"**LLM Calls:** {llm_calls}  \n\n")

        f.write("## Summary\n\n")
        f.write("| Metric | Value |\n|---|---:|\n")
        f.write(
            f"| **Case-Level Accuracy** | "
            f"**{passed_cases}/{total_cases} ({case_acc:.1f}%)** |\n"
        )
        f.write(
            f"| **Turn-Level Accuracy** | "
            f"**{passed_turns}/{total_turns} ({turn_acc:.1f}%)** |\n"
        )
        f.write(f"| LLM Calls | {llm_calls} |\n\n")

        # Per-category
        f.write("## Per-Category Performance\n\n")
        f.write(
            "| Category | Cases | Case Acc | Turns | Turn Acc |\n"
            "|----------|------:|---------:|------:|---------:|\n"
        )
        for cat in sorted(category_stats):
            s = category_stats[cat]
            ca = s["passed_cases"] / s["total_cases"] * 100 if s["total_cases"] else 0
            ta = s["passed_turns"] / s["total_turns"] * 100 if s["total_turns"] else 0
            f.write(
                f"| {cat} | {s['total_cases']} | {ca:.0f}% | "
                f"{s['total_turns']} | {ta:.0f}% |\n"
            )

        # Failed turns detail
        f.write("\n## Failed Turns\n\n")
        for r in results:
            for t in r["turns"]:
                if t["status"] == "FAIL":
                    f.write(
                        f"### {r['case_id']} Turn {t['turn']}\n"
                        f"- **Category:** {r['category']}\n"
                        f"- **Input:** {t['input']}\n"
                        f"- **Expected:** {t['expected_tools']}\n"
                        f"- **Actual:** {t['actual_tools']}\n"
                        f"- **Reason:** {t['failure_reason']}\n\n"
                    )

    print(f"\n  Report: {md_path}")

    # ── JSON ──
    json_path = out_dir / f"multiturn_{model_name}_{timestamp}.json"
    export = {
        "model": model_name,
        "timestamp": timestamp,
        "summary": {
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "case_accuracy": round(case_acc, 1),
            "total_turns": total_turns,
            "passed_turns": passed_turns,
            "turn_accuracy": round(turn_acc, 1),
            "llm_calls": llm_calls,
        },
        "per_category": category_stats,
        "cases": results,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)
    print(f"  JSON:   {json_path}")

    # Summary
    print(f"\n{'=' * 60}")
    print("MULTI-TURN BENCHMARK SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Case Accuracy : {passed_cases}/{total_cases} ({case_acc:.1f}%)")
    print(f"  Turn Accuracy : {passed_turns}/{total_turns} ({turn_acc:.1f}%)")
    print(f"  LLM Calls     : {llm_calls}")
    for cat in sorted(category_stats):
        s = category_stats[cat]
        ta = s["passed_turns"] / s["total_turns"] * 100 if s["total_turns"] else 0
        print(f"  {cat:20}: {ta:.0f}% turn accuracy")
    print()


def main():
    ap = argparse.ArgumentParser(description="Multi-Turn Conversation Benchmark")
    ap.add_argument("--model", required=True)
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--delay", type=float, default=1)
    args = ap.parse_args()
    run_multiturn_benchmark(args.model, args.timeout, args.delay)


if __name__ == "__main__":
    main()
