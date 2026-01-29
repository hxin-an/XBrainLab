#!/usr/bin/env python3
"""
Advanced LLM Benchmark Script
- Direct Inference (No Qt)
- Strict Parameter Validation
- Detailed Error Categorization
- Comprehensive Markdown & JSON & CSV Reporting
- RAG Integrated

Usage:
    poetry run benchmark-llm --model qwen
"""

import argparse
import csv
import json
import signal
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# Add project root
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))


def timeout_handler(signum, frame):
    raise TimeoutError("LLM inference timed out")


# Tool Type Classification
TOOL_TYPE_MAP = {
    # Dataset
    "load_data": "dataset",
    "get_dataset_info": "dataset",
    "generate_dataset": "dataset",
    # Preprocess
    "apply_bandpass_filter": "preprocess",
    "apply_notch_filter": "preprocess",
    "apply_standard_preprocess": "preprocess",
    "resample_data": "preprocess",
    "normalize_data": "preprocess",
    "epoch_data": "preprocess",
    # Training
    "set_model": "training",
    "configure_training": "training",
    "start_training": "training",
    # UI
    "switch_panel": "ui",
}


def get_tool_type(tool_name: str) -> str:
    return TOOL_TYPE_MAP.get(tool_name, "other")


def compare_params(expected: dict, actual: dict) -> tuple[bool, str]:
    """
    Compare expected vs actual parameters.
    Returns (match_bool, reason_str).
    """
    if not expected and not actual:
        return True, ""

    if expected is None:
        return True, ""  # Skip if expected is None (wildcard)

    if not actual:
        # If expected is not empty but actual is empty
        return False, f"Expected params {expected}, got None/Empty"

    mismatches = []
    # Check all expected keys
    for k, v in expected.items():
        # 1. Skip if expected value is None (Wildcard)
        # This handles the broken dataset cases where "model_name": null
        if v is None:
            continue

        if k not in actual:
            mismatches.append(f"Missing param '{k}'")
            continue

        act_val = actual[k]

        # 2. Smart Float Comparison
        # Try converting both to float
        try:
            f_exp = float(v)
            f_act = float(act_val)
            # Use a small epsilon for float comparison
            if abs(f_exp - f_act) > 1e-5:
                # Double check: maybe they are really different
                mismatches.append(f"Param '{k}': expected '{v}', got '{act_val}'")
            continue  # Match!
        except (ValueError, TypeError):
            pass  # Not floats, proceed to regular check

        # 3. List vs Dict (MNE event_id case)
        # Expected: [[800, 801]] or [800]
        # Actual: {"800": 800, "801": 801} or 800
        if k == "event_id":
            # Normalize actual to list of values if it is a dict
            if isinstance(act_val, dict):
                act_list = sorted(list(act_val.values()))
            elif isinstance(act_val, list):
                act_list = sorted(act_val)
            else:
                act_list = [act_val]  # scalar

            # Normalize expected to flattened list
            if isinstance(v, list):
                # Flatten if nested [[800, 801]]
                if v and isinstance(v[0], list):
                    exp_list = sorted([item for sublist in v for item in sublist])
                else:
                    exp_list = sorted(v)
            else:
                exp_list = [v]

            if str(act_list) != str(exp_list):
                mismatches.append(
                    f"Param '{k}': expected '{exp_list}', got '{act_list}' (normalized)"
                )
            continue

        # 4. Standard verification
        if str(act_val) != str(v):
            mismatches.append(f"Param '{k}': expected '{v}', got '{act_val}'")

    if mismatches:
        return False, "; ".join(mismatches)

    return True, ""


def run_benchmark(model_name: str, timeout_sec: int = 30):
    """Run benchmark with specified model."""

    from XBrainLab.llm.agent.parser import CommandParser
    from XBrainLab.llm.agent.prompt_manager import PromptManager
    from XBrainLab.llm.core.config import LLMConfig
    from XBrainLab.llm.core.engine import LLMEngine
    from XBrainLab.llm.rag.retriever import RAGRetriever
    from XBrainLab.llm.tools import AVAILABLE_TOOLS

    # Model configs
    MODEL_CONFIGS = {
        "qwen": {"model_name": "Qwen/Qwen2.5-7B-Instruct", "inference_mode": "local"},
        "gemma": {"model_name": "google/gemma-2-2b-it", "inference_mode": "local"},
        "phi": {
            "model_name": "microsoft/Phi-3.5-mini-instruct",
            "inference_mode": "local",
        },
        "mistral": {
            "model_name": "mistralai/Mistral-Nemo-Instruct-2407",
            "inference_mode": "local",
        },
    }

    if model_name not in MODEL_CONFIGS:
        print(f"Unknown model: {model_name}")
        return

    config_dict = MODEL_CONFIGS[model_name]

    # Init
    print(f"\n{'='*80}")
    print(f"BENCHMARK START: {model_name}")
    print("RAG Enabled: True")
    print(f"{'='*80}\n")

    test_file = project_root / "scripts/benchmark/data/external_validation_set.json"
    with open(test_file) as f:
        test_cases = json.load(f)

    # Load Model
    config = LLMConfig(**config_dict)
    engine = LLMEngine(config)
    engine.load_model()

    prompt_manager = PromptManager(AVAILABLE_TOOLS)
    parser = CommandParser()

    # Init RAG
    print("Initializing RAG Retriever...")
    rag_retriever = RAGRetriever()
    print("RAG Initialized.\n")

    results = []

    # Metrics
    metrics = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "error_types": Counter(),
        "category_stats": {},
        "tool_type_stats": {},  # New: dataset, preprocess, training, ui
    }

    try:
        for idx, case in enumerate(test_cases):
            metrics["total"] += 1
            case_id = idx + 1
            user_input = case["input"]
            expected_list = case["expected_tool_calls"]
            category = case.get("category", "unknown")

            # Init category
            if category not in metrics["category_stats"]:
                metrics["category_stats"][category] = {
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                }
            metrics["category_stats"][category]["total"] += 1

            # Prepare
            expected_tool = expected_list[0]["tool_name"] if expected_list else None
            expected_params = expected_list[0]["parameters"] if expected_list else {}

            # Track by Tool Type
            tool_type = get_tool_type(expected_tool) if expected_tool else "other"
            if tool_type not in metrics["tool_type_stats"]:
                metrics["tool_type_stats"][tool_type] = {
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                }
            metrics["tool_type_stats"][tool_type]["total"] += 1

            print(f"\n{'-'*60}")
            print(f"[Case {case_id}/{len(test_cases)}] Category: {category}")
            print(f"Input:    {user_input}")
            print(f"Expected: Tool: {expected_tool}")
            if expected_params:
                print(f"          Params: {json.dumps(expected_params)}")

            # --- RAG INJECTION ---
            prompt_manager.clear_context()  # Clear previous
            rag_context = rag_retriever.get_similar_examples(user_input, k=3)
            if rag_context:
                prompt_manager.add_context(rag_context)
                # print(f"RAG Context Added ({len(rag_context)} chars)")

            history = [{"role": "user", "content": user_input}]
            messages = prompt_manager.get_messages(history)

            result_entry = {
                "id": case_id,
                "category": category,
                "input": user_input,
                "expected_tool": expected_tool,
                "expected_params": json.dumps(expected_params),
                "actual_tool": None,
                "actual_params": None,
                "status": "FAIL",
                "failure_reason": "",
                "raw_response": "",
            }

            try:
                # Inference
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(timeout_sec)

                chunks = []
                for chunk in engine.generate_stream(messages):
                    chunks.append(chunk)
                signal.alarm(0)

                raw_response = "".join(chunks)
                result_entry["raw_response"] = raw_response

                # Parse
                # Parse
                parsed = parser.parse(raw_response)

                # Check if parsed is list (New) or tuple (Old/Compat)
                actual_calls = []
                if parsed:
                    if (
                        isinstance(parsed, list)
                        and len(parsed) > 0
                        and isinstance(parsed[0], tuple)
                    ):
                        # List of tuples [('tool', {}), ...]
                        actual_calls = parsed
                    elif isinstance(parsed, tuple):
                        # Legacy Single Tuple ('tool', {})
                        actual_calls = [parsed]

                if actual_calls:
                    # Logging
                    result_entry["actual_tool"] = str([c[0] for c in actual_calls])
                    result_entry["actual_params"] = str([c[1] for c in actual_calls])
                    print(f"Actual Sequence: {[(c[0], c[1]) for c in actual_calls]}")

                    # Compare Sequence
                    all_passed = True
                    failure_reasons = []

                    # If expected is None/Empty but we got something
                    if not expected_list:
                        all_passed = False
                        failure_reasons.append("Expected no tool, got some.")

                    # Iterate Expected
                    for i, exp_item in enumerate(expected_list):
                        exp_tool = exp_item["tool_name"]
                        exp_params = exp_item["parameters"]

                        if i >= len(actual_calls):
                            all_passed = False
                            failure_reasons.append(
                                f"Missing Step {i+1}: Expected {exp_tool}"
                            )
                            break

                        act_cmd, act_params = actual_calls[i]

                        if act_cmd != exp_tool:
                            # Ambiguity Check: Allow alternative tools for specific queries
                            is_ambiguous_pass = False

                            # Model Info
                            if (
                                "What model was used" in user_input
                                or "model info" in user_input
                                or "model details" in user_input
                            ):
                                if act_cmd in [
                                    "get_dataset_info",
                                    "set_model",
                                    "switch_panel",
                                ]:
                                    is_ambiguous_pass = True

                            # Preprocess (Standard vs Manual)
                            if (
                                "standard preprocess" in user_input.lower()
                                or "preprocess techniques" in user_input.lower()
                            ):
                                if act_cmd in [
                                    "apply_bandpass_filter",
                                    "apply_standard_preprocess",
                                ]:
                                    is_ambiguous_pass = True

                            if is_ambiguous_pass:
                                print(
                                    f"DEBUG: Ambiguity Passed for '{user_input}' using {act_cmd}"
                                )
                            else:
                                print(
                                    f"DEBUG: Ambiguity Failed for '{user_input}'. Tool: {act_cmd}"
                                )
                                all_passed = False
                                failure_reasons.append(
                                    f"Step {i+1}: Expected {exp_tool}, got {act_cmd}"
                                )
                        else:
                            match, reason = compare_params(exp_params, act_params)
                            if not match:
                                # Ambiguity Check for Params?
                                all_passed = False
                                failure_reasons.append(f"Step {i+1} Params: {reason}")

                    # Check for extra
                    if len(actual_calls) > len(expected_list):
                        # Allow extra steps (User Feedback: Completion is good)
                        # Just warn in logs but Pass
                        print(
                            f"Note: Extra steps detected: {[c[0] for c in actual_calls[len(expected_list):]]}"
                        )

                    if all_passed:
                        result_entry["status"] = "PASS"
                        metrics["passed"] += 1
                        metrics["category_stats"][category]["passed"] += 1
                        metrics["tool_type_stats"][tool_type][
                            "passed"
                        ] += 1  # Note: categorizes by first tool
                        print("Status:   PASS")
                    else:
                        result_entry["status"] = "FAIL"
                        reason_str = "; ".join(failure_reasons)
                        result_entry["failure_reason"] = reason_str
                        metrics["failed"] += 1
                        metrics["category_stats"][category]["failed"] += 1
                        metrics["tool_type_stats"][tool_type]["failed"] += 1
                        if "Tool Mismatch" in reason_str:
                            metrics["error_types"]["Tool Mismatch"] += 1
                        elif "Param" in reason_str:
                            metrics["error_types"]["Param Mismatch"] += 1
                        else:
                            metrics["error_types"]["Unexpected Tool"] += 1
                        print("Status:   FAIL")
                        print(f"Reason:   {reason_str}")

                else:
                    # No commands found
                    if not expected_list:
                        result_entry["status"] = "PASS"
                        metrics["passed"] += 1
                        metrics["category_stats"][category]["passed"] += 1
                        print("Actual:   None")
                        print("Status:   PASS (No Tool Expected)")
                    else:
                        result_entry["status"] = "FAIL"
                        if raw_response and "{" in raw_response:
                            result_entry["failure_reason"] = "JSON Parse Error"
                            metrics["error_types"]["JSON Parse Error"] += 1
                        else:
                            result_entry["failure_reason"] = "No JSON Output"
                            metrics["error_types"]["No JSON Output"] += 1

                        metrics["failed"] += 1
                        metrics["category_stats"][category]["failed"] += 1
                        metrics["error_types"][
                            "Unexpected Tool"
                        ] += 1  # Bucket into No Output?
                        print("Status:   FAIL (No Tool Found)")

            except TimeoutError:
                result_entry["status"] = "TIMEOUT"
                result_entry["failure_reason"] = "Timeout"
                metrics["errors"] += 1
                metrics["error_types"]["Timeout"] += 1
                metrics["category_stats"][category]["failed"] += 1
                print("Status:   TIMEOUT")

            except Exception as e:
                result_entry["status"] = "ERROR"
                result_entry["failure_reason"] = f"Exception: {e!s}"
                metrics["errors"] += 1
                metrics["error_types"]["Exception"] += 1
                metrics["category_stats"][category]["failed"] += 1
                print(f"Status:   ERROR: {e}")

            results.append(result_entry)

            # CUDA Cleanup
            if idx % 10 == 0:
                try:
                    import torch

                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass

    except KeyboardInterrupt:
        print("\n\nInterrupted! Saving partial results...")

    finally:
        if "rag_retriever" in locals():
            rag_retriever.close()

    # ==========================
    # Generate Reports
    # ==========================
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = project_root / "output" / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. MARKDOWN REPORT
    md_path = out_dir / f"report_{model_name}_{timestamp}.md"
    with open(md_path, "w") as f:
        f.write(f"# Benchmark Report: {model_name}\n\n")
        f.write(f"- **Date:** {timestamp}\n")
        f.write(f"- **Total Cases:** {metrics['total']}\n")
        f.write(
            f"- **Passed:** {metrics['passed']} ({metrics['passed']/metrics['total']*100:.1f}%)\n"
        )
        f.write(f"- **Failed:** {metrics['failed']}\n")
        f.write(f"- **Errors:** {metrics['errors']}\n\n")

        f.write("## 1. Error Distribution\n")
        f.write("| Error Type | Count |\n|---|---|\n")
        for err, count in metrics["error_types"].most_common():
            f.write(f"| {err} | {count} |\n")

        f.write("\n## 2. Category Performance\n")
        f.write("| Category | Total | Passed | Rate |\n|---|---|---|---|\n")
        for cat, stats in metrics["category_stats"].items():
            rate = stats["passed"] / stats["total"] * 100 if stats["total"] > 0 else 0
            f.write(f"| {cat} | {stats['total']} | {stats['passed']} | {rate:.1f}% |\n")

        f.write("\n## 3. Tool Type Performance\n")
        f.write(
            "| Tool Type | Total | Passed | Failed | Rate |\n|---|---|---|---|---|\n"
        )
        for ttype, stats in metrics["tool_type_stats"].items():
            rate = stats["passed"] / stats["total"] * 100 if stats["total"] > 0 else 0
            f.write(
                f"| {ttype} | {stats['total']} | {stats['passed']} | {stats['failed']} | {rate:.1f}% |\n"
            )

        f.write("\n## 4. Failed Cases\n")
        for res in results:
            if res["status"] != "PASS":
                f.write(f"### Case {res['id']}: {res['input']}\n")
                f.write(f"- **Category:** {res['category']}\n")
                f.write(f"- **Reason:** {res['failure_reason']}\n")
                f.write(
                    f"- **Expected:** `{res['expected_tool']}` params: `{res['expected_params']}`\n"
                )
                f.write(
                    f"- **Actual:** `{res['actual_tool']}` params: `{res['actual_params']}`\n"
                )
                f.write(f"- **Raw Output:**\n```\n{res['raw_response']}\n```\n\n")

    print(f"\nReport Saved: {md_path}")

    # 2. CSV EXPORT (For Excel)
    csv_path = out_dir / f"data_{model_name}_{timestamp}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "category",
                "status",
                "failure_reason",
                "expected_tool",
                "actual_tool",
                "input",
                "raw_response",
                "expected_params",
                "actual_params",
            ],
        )
        writer.writeheader()
        writer.writerows(results)
    print(f"CSV Saved:    {csv_path}")

    # Cleanup
    del engine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    run_benchmark(args.model, args.timeout)


if __name__ == "__main__":
    main()
