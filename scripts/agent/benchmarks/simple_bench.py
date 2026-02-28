#!/usr/bin/env python3
"""
Stage-Aware LLM Tool-Call Benchmark (Paper-Grade)

Evaluates LLM tool selection using **stage-filtered** tool sets that
match the production pipeline architecture.  Each test case is run at
the correct pipeline stage so the LLM only sees the tools it would see
in production.  Cross-stage multi-step cases are evaluated round-by-
round with simulated state transitions.

Modes:
    stage-aware (default) — tools filtered per pipeline stage
    all-visible           — all 19 tools shown (legacy, no architecture
                            validation)

Usage:
    poetry run benchmark-llm --model gemini
    poetry run benchmark-llm --model gemini --mode all-visible
    poetry run benchmark-llm --model qwen --dataset test.json
"""

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import torch

# Add project root
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Load .env for API keys
try:
    from dotenv import load_dotenv

    load_dotenv(project_root / ".env")
except ImportError:
    pass

from XBrainLab.llm.agent.assembler import ContextAssembler
from XBrainLab.llm.agent.parser import CommandParser
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine
from XBrainLab.llm.pipeline_state import STAGE_CONFIG, PipelineStage
from XBrainLab.llm.rag.config import RAGConfig
from XBrainLab.llm.tools import AVAILABLE_TOOLS
from XBrainLab.llm.tools.tool_registry import ToolRegistry


class _TimeoutError(Exception):
    """Cross-platform timeout error."""


def run_with_timeout(func, timeout_sec: int):
    """Execute *func* in a thread; raise on timeout (Windows-safe)."""
    result_box: list = []
    error_box: list = []

    def _target():
        try:
            result_box.append(func())
        except Exception as e:
            error_box.append(e)

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)
    if t.is_alive():
        raise _TimeoutError(f"Timed out after {timeout_sec}s")
    if error_box:
        raise error_box[0]
    return result_box[0] if result_box else None


# ---------------------------------------------------------------------------
# Tool Type Classification — ALL 19 tools
# ---------------------------------------------------------------------------
TOOL_TYPE_MAP = {
    # Dataset (6)
    "list_files": "dataset",
    "load_data": "dataset",
    "attach_labels": "dataset",
    "clear_dataset": "dataset",
    "get_dataset_info": "dataset",
    "generate_dataset": "dataset",
    # Preprocess (9)
    "apply_standard_preprocess": "preprocess",
    "apply_bandpass_filter": "preprocess",
    "apply_notch_filter": "preprocess",
    "resample_data": "preprocess",
    "normalize_data": "preprocess",
    "set_reference": "preprocess",
    "select_channels": "preprocess",
    "set_montage": "preprocess",
    "epoch_data": "preprocess",
    # Training (3)
    "set_model": "training",
    "configure_training": "training",
    "start_training": "training",
    # UI (1)
    "switch_panel": "ui",
}


def get_tool_type(tool_name: str) -> str:
    return TOOL_TYPE_MAP.get(tool_name, "other")


# ---------------------------------------------------------------------------
# Stage helpers — map tools to pipeline stages and simulate transitions
# ---------------------------------------------------------------------------
_STAGE_ORDER: list[PipelineStage] = [
    PipelineStage.EMPTY,
    PipelineStage.DATA_LOADED,
    PipelineStage.PREPROCESSED,
    PipelineStage.DATASET_READY,
    PipelineStage.TRAINING,
    PipelineStage.TRAINED,
]


def infer_stage_for_tool(tool_name: str) -> PipelineStage:
    """Return the *earliest* pipeline stage that includes *tool_name*."""
    for stage in _STAGE_ORDER:
        if tool_name in STAGE_CONFIG.get(stage, {}).get("tools", []):
            return stage
    return PipelineStage.EMPTY


def simulate_stage_transition(
    current_stage: PipelineStage,
    tool_name: str,
) -> PipelineStage:
    """Predict the pipeline stage after executing *tool_name*."""
    if tool_name == "clear_dataset":
        return PipelineStage.EMPTY
    if tool_name == "load_data":
        return PipelineStage.DATA_LOADED
    if tool_name in ("epoch_data", "apply_standard_preprocess"):
        return PipelineStage.PREPROCESSED
    if tool_name == "generate_dataset":
        return PipelineStage.DATASET_READY
    if tool_name == "start_training":
        return PipelineStage.TRAINED
    return current_stage


def compute_rounds(
    expected_calls: list[dict],
    initial_stage: PipelineStage,
) -> list[tuple[PipelineStage, list[dict]]]:
    """Group *expected_calls* into LLM rounds by stage boundaries.

    Consecutive tools that are all available at the same stage are
    grouped into one round.  When a tool requires a new stage (not
    present in the current stage's tool list), a new round begins after
    simulating the state transitions of the previous round.

    Returns a list of ``(stage, [call, ...])`` tuples.
    """
    if not expected_calls:
        return []

    rounds: list[tuple[PipelineStage, list[dict]]] = []
    stage = initial_stage
    current_round: list[dict] = []

    for call in expected_calls:
        tool_name = call["tool_name"]
        stage_tools = set(STAGE_CONFIG.get(stage, {}).get("tools", []))

        if tool_name not in stage_tools:
            # Flush the current round and transition
            if current_round:
                rounds.append((stage, current_round))
                for prev in current_round:
                    stage = simulate_stage_transition(
                        stage,
                        prev["tool_name"],
                    )
            current_round = []

        current_round.append(call)

    if current_round:
        rounds.append((stage, current_round))

    return rounds


# ---------------------------------------------------------------------------
# Benchmark-specific ContextAssembler — shows ALL tools
# ---------------------------------------------------------------------------
_BENCHMARK_SYSTEM_PROMPT = """\
You are XBrainLab Assistant — an expert EEG analysis guide.

You have access to ALL available tools. When the user's request requires
a tool, output a JSON object (see format below). When no tool is needed,
reply in natural language.

IMPORTANT: Always output the JSON tool-call block. Do NOT refuse by
saying "you need to load data first" or similar — this is a benchmark
environment where all tools are available regardless of pipeline state.
"""


class BenchmarkAssembler(ContextAssembler):
    """ContextAssembler override that exposes ALL 19 tools (legacy).

    In production, ``ContextAssembler`` stage-filters tools based on
    ``compute_pipeline_stage(study_state)``.  This class bypasses that
    filtering so the model sees *every* tool.  Use ``--mode all-visible``
    to enable this assembler.
    """

    def _get_stage_config(self):
        all_tool_names = [t.name for t in self.registry.get_all_tools()]
        return PipelineStage.EMPTY, {
            "tools": all_tool_names,
            "system_prompt": _BENCHMARK_SYSTEM_PROMPT,
        }


class StageAwareBenchmarkAssembler(ContextAssembler):
    """Assembler that uses **real stage-filtered** tool sets.

    Unlike :class:`BenchmarkAssembler`, this class returns the *actual*
    stage configuration (tools + system prompt) from :data:`STAGE_CONFIG`
    so the benchmark mirrors production behavior exactly.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        initial_stage: PipelineStage = PipelineStage.EMPTY,
    ):
        super().__init__(tool_registry, study_state=None)
        self._stage = initial_stage

    @property
    def current_stage(self) -> PipelineStage:
        return self._stage

    @current_stage.setter
    def current_stage(self, stage: PipelineStage) -> None:
        self._stage = stage

    def _get_stage_config(self):
        config = STAGE_CONFIG.get(self._stage, STAGE_CONFIG[PipelineStage.EMPTY])
        return self._stage, config


# ---------------------------------------------------------------------------
# Custom train-only RAG (no data leakage)
# ---------------------------------------------------------------------------
def build_benchmark_rag(train_path: Path, tmp_dir: str):
    """Build a Qdrant index from *train_path* only.

    Returns ``(client, embeddings, collection_name)`` for retrieval.
    """
    from langchain.docstore.document import Document
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_community.vectorstores import Qdrant
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as rest

    embeddings = HuggingFaceEmbeddings(model_name=RAGConfig.EMBEDDING_MODEL)
    client = QdrantClient(path=tmp_dir)

    collection_name = "bench_rag"
    client.create_collection(
        collection_name=collection_name,
        vectors_config=rest.VectorParams(size=384, distance=rest.Distance.COSINE),
    )

    with open(train_path, encoding="utf-8") as f:
        data = json.load(f)

    docs = []
    for item in data:
        content = item.get("input", "")
        tool_calls = item.get("expected_tool_calls", [])
        metadata = {
            "id": item.get("id"),
            "category": item.get("category"),
            "tool_calls": json.dumps(tool_calls),
        }
        if content:
            docs.append(Document(page_content=content, metadata=metadata))

    vectorstore = Qdrant(
        client=client,
        collection_name=collection_name,
        embeddings=embeddings,
    )
    vectorstore.add_documents(docs)
    print(
        f"  RAG indexed {len(docs)} train examples (model: {RAGConfig.EMBEDDING_MODEL})"
    )
    return client, embeddings, collection_name


def rag_retrieve(
    client, embeddings, collection_name: str, query: str, k: int = 3
) -> str:
    """Retrieve top-k examples and format as prompt context."""
    query_vector = embeddings.embed_query(query)
    results = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=k,
        with_payload=True,
    ).points

    if not results:
        return ""

    result_str = "\n### Similar Examples:\n"
    for i, point in enumerate(results, 1):
        payload = point.payload or {}
        user_input = payload.get("page_content", "") or payload.get("input", "")
        metadata = payload.get("metadata", {})
        if isinstance(metadata, dict):
            tool_calls_json = metadata.get("tool_calls", "[]")
        else:
            tool_calls_json = "[]"
        result_str += f"\nExample {i}:\n"
        result_str += f'User: "{user_input}"\n'
        result_str += f"Assistant: ```json\n{tool_calls_json}\n```\n"
    return result_str


def _normalize_event_id(val) -> list[int]:
    """Normalize event_id to a sorted list of ints for comparison.

    Handles dict (``{"769": 769}``), list (``["769", 770]``), nested
    list (``[[769, 770]]``), and scalar inputs.
    """
    if val is None:
        return []
    if isinstance(val, dict):
        # Use values (the int codes)
        items = list(val.values())
    elif isinstance(val, list):
        # Flatten nested lists
        items = []
        for item in val:
            if isinstance(item, (list, tuple)):
                items.extend(item)
            elif isinstance(item, dict):
                items.extend(item.values())
            else:
                items.append(item)
    else:
        items = [val]
    # Coerce every element to int (handles "769" → 769)
    result = []
    for x in items:
        try:
            result.append(int(x))
        except (ValueError, TypeError):
            result.append(x)  # keep as-is if not convertible
    return sorted(result)


# ---------------------------------------------------------------------------
# Cross-stage subsequence matching
# ---------------------------------------------------------------------------
_HARMLESS_EXTRA_TOOLS: frozenset[str] = frozenset(
    {
        "get_dataset_info",  # info-retrieval, no side effect
    }
)

_ACCEPTABLE_PREFIXES: dict[str, list[str]] = {
    # LLM often calls configure_training before start_training — correct practice
    "start_training": ["configure_training"],
}


def _is_subsequence_match(
    expected: list[str],
    actual: list[str],
) -> tuple[bool, str]:
    """Check if *expected* is a subsequence of *actual* after filtering.

    Harmless extra tools (like ``get_dataset_info``) are stripped.
    Known acceptable prefixes (like ``configure_training`` before
    ``start_training``) are also tolerated.

    Returns ``(match, reason)``.
    """
    # Remove harmless extras from actual
    filtered = [t for t in actual if t not in _HARMLESS_EXTRA_TOOLS]

    # Expand expected with acceptable prefixes
    expanded_expected: list[str] = []
    for tool in expected:
        expanded_expected.append(tool)

    # Try strict subsequence first
    ei = 0
    for at in filtered:
        if ei < len(expanded_expected) and at == expanded_expected[ei]:
            ei += 1
    if ei == len(expanded_expected):
        return True, ""

    # Try with acceptable prefixes inserted
    expanded_with_prefix: list[str] = []
    for tool in expected:
        for prefix in _ACCEPTABLE_PREFIXES.get(tool, []):
            expanded_with_prefix.append(prefix)
        expanded_with_prefix.append(tool)

    ei = 0
    for at in filtered:
        if ei < len(expanded_with_prefix) and at == expanded_with_prefix[ei]:
            ei += 1
    if ei == len(expanded_with_prefix):
        return True, ""

    return False, f"Expected subsequence {expected}, got {filtered}"


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
        # Expected: {"769": 769, ...} or [769, 770] or [[769, 770]]
        # Actual:   ["769", "770"] or {"769": 769, ...} or [769, 770]
        if k == "event_id":
            exp_list = _normalize_event_id(v)
            act_list = _normalize_event_id(act_val)

            if exp_list != act_list:
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


def run_benchmark(
    model_name: str,
    timeout_sec: int = 30,
    *,
    delay_sec: float = 0,
    dataset_name: str = "test.json",
    mode: str = "stage-aware",
):
    """Run benchmark with specified model.

    Args:
        mode: ``"stage-aware"`` (default) uses real stage-filtered tool
            sets; ``"all-visible"`` shows all 19 tools (legacy).
    """

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
        "gemini": {
            "inference_mode": "gemini",
            "gemini_model_name": os.environ.get(
                "GEMINI_MODEL_NAME", "gemini-2.0-flash"
            ),
        },
    }

    if model_name not in MODEL_CONFIGS:
        print(f"Unknown model: {model_name}")
        return

    config_dict = MODEL_CONFIGS[model_name]
    is_stage_aware = mode == "stage-aware"

    # Init
    print(f"\n{'=' * 80}")
    print(f"BENCHMARK START: {model_name}")
    print(f"Dataset: {dataset_name}")
    print(f"Mode: {mode}")
    print("RAG Enabled: True (train split only, no data leakage)")
    if is_stage_aware:
        print("Tool visibility: stage-filtered (matches production architecture)")
    else:
        print("Tool visibility: all 19 tools (stage filtering bypassed)")
    print(f"{'=' * 80}\n")

    data_dir = project_root / "scripts" / "agent" / "benchmarks" / "data"
    test_file = data_dir / dataset_name
    train_file = data_dir / "train.json"
    if not test_file.exists():
        print(f"Dataset not found: {test_file}")
        return
    if not train_file.exists():
        print(f"Train set not found: {train_file}")
        print("Run split_dataset.py first.")
        return
    with open(test_file) as f:
        test_cases = json.load(f)

    # Load Model
    config = LLMConfig(**config_dict)
    engine = LLMEngine(config)
    engine.load_model()

    # --- Setup: Assembler ---
    registry = ToolRegistry()
    for tool in AVAILABLE_TOOLS:
        registry.register(tool)

    if is_stage_aware:
        prompt_manager = StageAwareBenchmarkAssembler(registry)
    else:
        prompt_manager = BenchmarkAssembler(registry, study_state=None)

    parser = CommandParser()

    # --- Setup: Train-only RAG (no data leakage) ---
    print("Building RAG index from train split...")
    rag_tmp_dir = tempfile.mkdtemp(prefix="bench_rag_")
    rag_client, rag_embeddings, rag_collection = build_benchmark_rag(
        train_file,
        rag_tmp_dir,
    )
    print("RAG Ready.\n")

    results = []
    total_llm_calls = 0

    # Metrics — includes per-tool tracking
    metrics = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "error_types": Counter(),
        "category_stats": {},
        "tool_type_stats": {},
        "per_tool_stats": {},  # per individual tool_name
    }

    def _update_fail(category, tool_type, expected_tool, reason_str):
        """Helper: record a FAIL in all metric buckets."""
        metrics["failed"] += 1
        metrics["category_stats"][category]["failed"] += 1
        if tool_type in metrics["tool_type_stats"]:
            metrics["tool_type_stats"][tool_type]["failed"] += 1
        if expected_tool and expected_tool in metrics["per_tool_stats"]:
            metrics["per_tool_stats"][expected_tool]["failed"] += 1
        if "Tool Mismatch" in reason_str:
            metrics["error_types"]["Tool Mismatch"] += 1
        elif "Param" in reason_str:
            metrics["error_types"]["Param Mismatch"] += 1
        else:
            metrics["error_types"]["Other"] += 1

    def _do_llm_call(msgs, _timeout, _engine=engine):
        """Single LLM inference with retry on rate-limit / 503."""

        def _infer():
            chunks = []
            for chunk in _engine.generate_stream(msgs):
                chunks.append(chunk)
            return "".join(chunks)

        _RETRIABLE = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE")
        for _attempt in range(3):
            try:
                return run_with_timeout(_infer, _timeout)
            except Exception as err:
                err_str = str(err)
                if any(code in err_str for code in _RETRIABLE):
                    _wait = (2**_attempt) * 5
                    print(f"    Retriable error, retrying in {_wait}s...")
                    time.sleep(_wait)
                    if _attempt == 2:
                        raise
                else:
                    raise
        return None  # unreachable

    _NUDGE_PROMPT = (
        "You MUST respond with a JSON tool-call block. "
        "Do NOT explain or refuse. Output the JSON now."
    )

    def _parse_calls(raw):
        """Parse raw LLM response into list of (tool_name, params) tuples."""
        parsed = parser.parse(raw)
        if not parsed:
            return []
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], tuple):
            return parsed
        if isinstance(parsed, tuple):
            return [parsed]
        return []

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

            # Prepare first-tool metadata for per-tool tracking
            expected_tool = expected_list[0]["tool_name"] if expected_list else None
            expected_params = expected_list[0]["parameters"] if expected_list else {}

            tool_type = get_tool_type(expected_tool) if expected_tool else "other"
            if tool_type not in metrics["tool_type_stats"]:
                metrics["tool_type_stats"][tool_type] = {
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                }
            metrics["tool_type_stats"][tool_type]["total"] += 1

            if expected_tool:
                if expected_tool not in metrics["per_tool_stats"]:
                    metrics["per_tool_stats"][expected_tool] = {
                        "total": 0,
                        "passed": 0,
                        "failed": 0,
                    }
                metrics["per_tool_stats"][expected_tool]["total"] += 1

            # ── Compute rounds ──
            if is_stage_aware and expected_list:
                initial_stage = infer_stage_for_tool(expected_list[0]["tool_name"])
                rounds = compute_rounds(expected_list, initial_stage)
            else:
                # all-visible: single round with all expected tools
                initial_stage = PipelineStage.EMPTY
                rounds = [(PipelineStage.EMPTY, expected_list)]

            n_rounds = len(rounds)
            stage_label = initial_stage.value if is_stage_aware else "all"

            print(f"\n{'-' * 60}")
            print(f"[Case {case_id}/{len(test_cases)}] Category: {category}")
            if is_stage_aware:
                print(f"Stage:    {stage_label} | Rounds: {n_rounds}")
            print(f"Input:    {user_input}")
            print(f"Expected: {[c['tool_name'] for c in expected_list]}")

            result_entry = {
                "id": case_id,
                "case_id": case.get("id", f"case_{case_id}"),
                "category": category,
                "input": user_input,
                "expected_tool": expected_tool,
                "expected_params": json.dumps(expected_params),
                "actual_tool": None,
                "actual_params": None,
                "status": "FAIL",
                "failure_reason": "",
                "raw_response": "",
                "stage": stage_label,
                "rounds": n_rounds,
            }

            try:
                # --- RAG context (once per case, like production) ---
                prompt_manager.clear_context()
                rag_context = rag_retrieve(
                    rag_client,
                    rag_embeddings,
                    rag_collection,
                    user_input,
                    k=3,
                )
                if rag_context:
                    prompt_manager.add_context(rag_context)

                # ── Round-based evaluation ──
                conversation = [{"role": "user", "content": user_input}]
                all_actual_calls = []
                all_raw_responses = []
                case_passed = True
                failure_reasons = []

                for round_idx, (round_stage, round_expected) in enumerate(rounds):
                    # Set stage for this round
                    if is_stage_aware:
                        prompt_manager.current_stage = round_stage
                        visible_count = len(
                            STAGE_CONFIG.get(round_stage, {}).get("tools", []),
                        )
                        if n_rounds > 1:
                            print(
                                f"  Round {round_idx + 1}/{n_rounds}: "
                                f"stage={round_stage.value} "
                                f"({visible_count} tools visible)"
                            )

                    messages = prompt_manager.get_messages(conversation)

                    # LLM call
                    total_llm_calls += 1
                    raw_response = _do_llm_call(messages, timeout_sec)
                    all_raw_responses.append(raw_response or "")

                    if raw_response is None:
                        case_passed = False
                        failure_reasons.append(
                            f"Round {round_idx + 1}: No response",
                        )
                        break

                    actual_calls = _parse_calls(raw_response)

                    # ── Retry/nudge if no JSON produced ──
                    if not actual_calls:
                        print("    No JSON output, sending nudge prompt...")
                        nudge_msgs = [
                            *messages,
                            {"role": "assistant", "content": raw_response},
                            {"role": "user", "content": _NUDGE_PROMPT},
                        ]
                        total_llm_calls += 1
                        retry_response = _do_llm_call(nudge_msgs, timeout_sec)
                        if retry_response:
                            all_raw_responses[-1] += "\n[NUDGE]\n" + retry_response
                            actual_calls = _parse_calls(retry_response)

                    all_actual_calls.extend(actual_calls)

                    if not actual_calls:
                        case_passed = False
                        if raw_response and "{" in raw_response:
                            failure_reasons.append(
                                f"Round {round_idx + 1}: JSON Parse Error",
                            )
                            metrics["error_types"]["JSON Parse Error"] += 1
                        else:
                            failure_reasons.append(
                                f"Round {round_idx + 1}: No JSON Output",
                            )
                            metrics["error_types"]["No JSON Output"] += 1
                        break

                    # ── Compare: subsequence matching for cross-stage ──
                    expected_names = [e["tool_name"] for e in round_expected]
                    actual_names = [c[0] for c in actual_calls]

                    if actual_names == expected_names:
                        # Exact match — check params per step
                        for i, exp_item in enumerate(round_expected):
                            exp_params = exp_item.get("parameters", {})
                            _act_cmd, act_params = actual_calls[i]
                            match, reason = compare_params(
                                exp_params,
                                act_params,
                            )
                            if not match:
                                case_passed = False
                                failure_reasons.append(
                                    f"Round {round_idx + 1} Step {i + 1} "
                                    f"Params: {reason}",
                                )
                    else:
                        # Try subsequence / ambiguity matching
                        subseq_ok, subseq_reason = _is_subsequence_match(
                            expected_names,
                            actual_names,
                        )
                        if subseq_ok:
                            print(
                                f"    Subsequence match OK: "
                                f"{actual_names} contains {expected_names}",
                            )
                            # Verify params for the matched expected tools
                            ai = 0
                            for exp_item in round_expected:
                                exp_tool = exp_item["tool_name"]
                                exp_params = exp_item.get("parameters", {})
                                while ai < len(actual_calls):
                                    act_cmd, act_params = actual_calls[ai]
                                    ai += 1
                                    if act_cmd == exp_tool:
                                        pm, pr = compare_params(
                                            exp_params,
                                            act_params,
                                        )
                                        if not pm:
                                            case_passed = False
                                            failure_reasons.append(
                                                f"Round {round_idx + 1} "
                                                f"Params ({exp_tool}): {pr}",
                                            )
                                        break
                        else:
                            # Fall back to positional matching
                            for i, exp_item in enumerate(round_expected):
                                exp_tool = exp_item["tool_name"]
                                exp_params = exp_item.get("parameters", {})
                                if i >= len(actual_calls):
                                    case_passed = False
                                    failure_reasons.append(
                                        f"Round {round_idx + 1} Step "
                                        f"{i + 1}: Missing {exp_tool}",
                                    )
                                    break
                                act_cmd, act_params = actual_calls[i]
                                if act_cmd != exp_tool:
                                    if _check_ambiguity(
                                        user_input,
                                        exp_tool,
                                        act_cmd,
                                    ):
                                        print(
                                            f"  Ambiguity OK: {act_cmd} "
                                            f"accepted for {exp_tool}",
                                        )
                                    else:
                                        case_passed = False
                                        failure_reasons.append(
                                            f"Round {round_idx + 1} Step "
                                            f"{i + 1}: Expected "
                                            f"{exp_tool}, got {act_cmd}",
                                        )
                                else:
                                    pm, pr = compare_params(
                                        exp_params,
                                        act_params,
                                    )
                                    if not pm:
                                        case_passed = False
                                        failure_reasons.append(
                                            f"Round {round_idx + 1} Step "
                                            f"{i + 1} Params: {pr}",
                                        )

                    if not case_passed:
                        break

                    # Remove consumed actual_calls for next round
                    actual_calls = actual_calls[len(round_expected) :]

                    # Prepare history for next round (simulate tool results)
                    if round_idx < n_rounds - 1:
                        conversation.append(
                            {
                                "role": "assistant",
                                "content": raw_response,
                            }
                        )
                        tool_results = "\n".join(
                            f"[Tool Output] {exp['tool_name']}: executed successfully."
                            for exp in round_expected
                        )
                        conversation.append(
                            {
                                "role": "user",
                                "content": tool_results,
                            }
                        )

                # ── Record results ──
                result_entry["actual_tool"] = str(
                    [c[0] for c in all_actual_calls],
                )
                result_entry["actual_params"] = str(
                    [c[1] for c in all_actual_calls],
                )
                result_entry["raw_response"] = "\n---\n".join(all_raw_responses)

                print(f"Actual:   {[c[0] for c in all_actual_calls]}")

                if case_passed:
                    # Check for extra calls (warn but pass)
                    total_expected = sum(len(r[1]) for r in rounds)
                    if len(all_actual_calls) > total_expected:
                        extras = [c[0] for c in all_actual_calls[total_expected:]]
                        print(f"Note: Extra steps: {extras}")

                    result_entry["status"] = "PASS"
                    metrics["passed"] += 1
                    metrics["category_stats"][category]["passed"] += 1
                    metrics["tool_type_stats"][tool_type]["passed"] += 1
                    if expected_tool and expected_tool in metrics["per_tool_stats"]:
                        metrics["per_tool_stats"][expected_tool]["passed"] += 1
                    print("Status:   PASS")
                else:
                    reason_str = "; ".join(failure_reasons)
                    result_entry["status"] = "FAIL"
                    result_entry["failure_reason"] = reason_str
                    _update_fail(category, tool_type, expected_tool, reason_str)
                    print("Status:   FAIL")
                    print(f"Reason:   {reason_str}")

            except _TimeoutError:
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

            # Delay between requests to avoid rate limiting
            if delay_sec > 0:
                time.sleep(delay_sec)

            # CUDA Cleanup
            if idx % 10 == 0:
                try:
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass

    except KeyboardInterrupt:
        print("\n\nInterrupted! Saving partial results...")

    finally:
        # Cleanup RAG temp dir
        if "rag_client" in locals():
            rag_client.close()
        if "rag_tmp_dir" in locals():
            shutil.rmtree(rag_tmp_dir, ignore_errors=True)

    # ==========================
    # Generate Reports
    # ==========================
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = project_root / "output" / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Derived statistics
    total = metrics["total"]
    passed = metrics["passed"]
    failed = metrics["failed"]
    errors = metrics["errors"]
    accuracy = passed / total * 100 if total else 0

    # Multi-step analysis
    single_step = [r for r in results if r["rounds"] == 1]
    multi_step = [r for r in results if r["rounds"] > 1]
    single_pass = sum(1 for r in single_step if r["status"] == "PASS")
    multi_pass = sum(1 for r in multi_step if r["status"] == "PASS")

    # Per-stage breakdown
    stage_stats: dict[str, dict] = {}
    for r in results:
        s = r.get("stage", "?")
        if s not in stage_stats:
            stage_stats[s] = {"total": 0, "passed": 0}
        stage_stats[s]["total"] += 1
        if r["status"] == "PASS":
            stage_stats[s]["passed"] += 1

    # Failure taxonomy
    failure_taxonomy: dict[str, int] = Counter()
    for r in results:
        if r["status"] == "PASS":
            continue
        reason = r.get("failure_reason", "")
        if "Param" in reason:
            failure_taxonomy["Param Mismatch"] += 1
        elif "Expected" in reason and "got" in reason:
            failure_taxonomy["Tool Mismatch"] += 1
        elif "No JSON" in reason:
            failure_taxonomy["No JSON Output"] += 1
        elif "JSON Parse" in reason:
            failure_taxonomy["JSON Parse Error"] += 1
        elif "Exception" in reason or "Timeout" in reason:
            failure_taxonomy["API/Infra Error"] += 1
        else:
            failure_taxonomy["Other"] += 1

    # 1. MARKDOWN REPORT
    md_path = out_dir / f"report_{model_name}_{mode}_{timestamp}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Benchmark Report: {model_name}\n\n")
        f.write("## Summary\n\n")
        f.write("| Metric | Value |\n|---|---|\n")
        f.write(f"| Date | {timestamp} |\n")
        f.write(f"| Mode | {mode} |\n")
        f.write(f"| Dataset | {dataset_name} |\n")
        f.write(f"| Total Cases | {total} |\n")
        f.write(f"| Total LLM Calls | {total_llm_calls} |\n")
        f.write(f"| **Accuracy** | **{passed}/{total} ({accuracy:.1f}%)** |\n")
        f.write(f"| Failed | {failed} |\n")
        f.write(f"| Errors | {errors} |\n\n")

        # Single vs multi-step
        f.write("## 1. Single-Step vs Multi-Step Accuracy\n\n")
        f.write("| Type | Total | Passed | Accuracy |\n|---|---|---|---|\n")
        s_rate = single_pass / len(single_step) * 100 if single_step else 0
        m_rate = multi_pass / len(multi_step) * 100 if multi_step else 0
        f.write(
            f"| Single-step (1 round) | {len(single_step)} | "
            f"{single_pass} | {s_rate:.1f}% |\n",
        )
        f.write(
            f"| Multi-step (>1 round) | {len(multi_step)} | "
            f"{multi_pass} | {m_rate:.1f}% |\n",
        )
        f.write(
            f"| **Overall** | **{total}** | **{passed}** | **{accuracy:.1f}%** |\n\n",
        )

        # Failure taxonomy
        f.write("## 2. Failure Taxonomy\n\n")
        f.write("| Failure Type | Count | % of Failures |\n|---|---|---|\n")
        total_failures = failed + errors
        for ftype, cnt in sorted(
            failure_taxonomy.items(),
            key=lambda x: -x[1],
        ):
            pct = cnt / total_failures * 100 if total_failures else 0
            f.write(f"| {ftype} | {cnt} | {pct:.0f}% |\n")
        f.write(f"| **Total** | **{total_failures}** | **100%** |\n\n")

        # Per-stage
        if is_stage_aware:
            f.write("## 3. Per-Stage Accuracy\n\n")
            f.write("| Stage | Total | Passed | Accuracy |\n|---|---|---|---|\n")
            for stg in [
                "empty",
                "data_loaded",
                "preprocessed",
                "dataset_ready",
                "trained",
                "all",
            ]:
                if stg in stage_stats:
                    ss = stage_stats[stg]
                    sr = ss["passed"] / ss["total"] * 100 if ss["total"] else 0
                    f.write(
                        f"| {stg} | {ss['total']} | {ss['passed']} | {sr:.1f}% |\n",
                    )
            f.write("\n")

        # Category
        f.write(f"## {'4' if is_stage_aware else '3'}. Category Performance\n\n")
        f.write("| Category | Total | Passed | Accuracy |\n|---|---|---|---|\n")
        for cat in sorted(metrics["category_stats"]):
            stats = metrics["category_stats"][cat]
            rate = stats["passed"] / stats["total"] * 100 if stats["total"] else 0
            f.write(
                f"| {cat} | {stats['total']} | {stats['passed']} | {rate:.1f}% |\n",
            )

        # Tool type
        sec_n = 5 if is_stage_aware else 4
        f.write(f"\n## {sec_n}. Tool Type Performance\n\n")
        f.write(
            "| Tool Type | Total | Passed | Failed | Accuracy |\n"
            "|---|---|---|---|---|\n",
        )
        for ttype in sorted(metrics["tool_type_stats"]):
            stats = metrics["tool_type_stats"][ttype]
            rate = stats["passed"] / stats["total"] * 100 if stats["total"] else 0
            f.write(
                f"| {ttype} | {stats['total']} | {stats['passed']} | "
                f"{stats['failed']} | {rate:.1f}% |\n",
            )

        # Per-tool
        sec_n += 1
        f.write(f"\n## {sec_n}. Per-Tool Accuracy\n\n")
        f.write(
            "| Tool Name | Total | Passed | Failed | Accuracy |\n"
            "|---|---|---|---|---|\n",
        )
        for tool_name in sorted(metrics["per_tool_stats"]):
            stats = metrics["per_tool_stats"][tool_name]
            rate = stats["passed"] / stats["total"] * 100 if stats["total"] else 0
            f.write(
                f"| {tool_name} | {stats['total']} | {stats['passed']} | "
                f"{stats['failed']} | {rate:.1f}% |\n",
            )

        # Failed cases detail
        sec_n += 1
        f.write(f"\n## {sec_n}. Failed Cases\n\n")
        for res in results:
            if res["status"] != "PASS":
                f.write(f"### Case {res['id']}: {res['input']}\n")
                f.write(f"- **Category:** {res['category']}\n")
                if is_stage_aware:
                    f.write(f"- **Stage:** {res.get('stage', '?')}\n")
                    f.write(f"- **Rounds:** {res.get('rounds', 1)}\n")
                f.write(f"- **Reason:** {res['failure_reason']}\n")
                f.write(
                    f"- **Expected:** `{res['expected_tool']}` "
                    f"params: `{res['expected_params']}`\n",
                )
                f.write(
                    f"- **Actual:** `{res['actual_tool']}` "
                    f"params: `{res['actual_params']}`\n",
                )
                f.write(
                    f"- **Raw Output:**\n```\n{res['raw_response']}\n```\n\n",
                )

    print(f"\nReport Saved: {md_path}")

    # 2. CSV EXPORT (For Excel)
    csv_path = out_dir / f"data_{model_name}_{mode}_{timestamp}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "case_id",
                "category",
                "stage",
                "rounds",
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


def _check_ambiguity(user_input: str, expected: str, actual: str) -> bool:
    """Return True if *actual* is an acceptable alternative for *expected*."""
    # Model Info
    if any(
        kw in user_input
        for kw in ("What model was used", "model info", "model details")
    ):
        if actual in ("get_dataset_info", "set_model", "switch_panel"):
            return True
    # Preprocess (Standard vs Manual)
    lower = user_input.lower()
    if "standard preprocess" in lower or "preprocess techniques" in lower:
        if actual in ("apply_bandpass_filter", "apply_standard_preprocess"):
            return True
    return False


def main():
    ap = argparse.ArgumentParser(
        description="Stage-Aware LLM Tool-Call Benchmark",
    )
    ap.add_argument("--model", required=True)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument(
        "--delay",
        type=float,
        default=0,
        help="Delay (sec) between API calls to avoid rate limiting",
    )
    ap.add_argument(
        "--dataset",
        default="test.json",
        help="Dataset filename inside data/ (default: test.json)",
    )
    ap.add_argument(
        "--mode",
        default="stage-aware",
        choices=["stage-aware", "all-visible"],
        help="stage-aware (default): real pipeline tool filtering; "
        "all-visible: legacy mode showing all 19 tools",
    )
    args = ap.parse_args()
    run_benchmark(
        args.model,
        args.timeout,
        delay_sec=args.delay,
        dataset_name=args.dataset,
        mode=args.mode,
    )


if __name__ == "__main__":
    main()
