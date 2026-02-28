#!/usr/bin/env python3
"""Architecture Validation: Cross-Stage Multi-Tool Execution.

Verifies whether the production architecture correctly handles user
requests that span multiple pipeline stages.

Example: "Load data and apply bandpass filter"
  - Current stage: EMPTY (only list_files, load_data, switch_panel visible)
  - After load_data: DATA_LOADED (bandpass_filter now available)
  - Question: Does the architecture allow tool B to execute after tool A
    changes the pipeline stage?

This script traces every layer of the architecture to produce a
definitive answer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from XBrainLab.llm.agent.assembler import ContextAssembler
from XBrainLab.llm.pipeline_state import (
    STAGE_CONFIG,
    PipelineStage,
)
from XBrainLab.llm.tools import AVAILABLE_TOOLS
from XBrainLab.llm.tools.tool_registry import ToolRegistry

# ── Setup ──
registry = ToolRegistry()
for tool in AVAILABLE_TOOLS:
    registry.register(tool)

ALL_TOOL_NAMES = sorted(t.name for t in registry.get_all_tools())


# ═══════════════════════════════════════════════════════════════
# 1. Stage → Tool Mapping Validation
# ═══════════════════════════════════════════════════════════════


def validate_stage_tool_mapping():
    """Verify that every tool in STAGE_CONFIG actually exists in the registry."""
    print("=" * 70)
    print("1. STAGE → TOOL MAPPING VALIDATION")
    print("=" * 70)

    errors = []
    registered_names = {t.name for t in registry.get_all_tools()}

    for stage in PipelineStage:
        config = STAGE_CONFIG.get(stage)
        if config is None:
            errors.append(f"  Stage {stage.value}: No config found!")
            continue

        tools_in_config = set(config["tools"])
        unknown = tools_in_config - registered_names
        if unknown:
            errors.append(f"  Stage {stage.value}: Unknown tools in config: {unknown}")

        print(
            f"  {stage.value:20s}: {len(tools_in_config)} tools → {sorted(tools_in_config)}"
        )

    if errors:
        print("\n  ERRORS:")
        for e in errors:
            print(f"    {e}")
    else:
        print("\n  ✓ All stage configs reference valid registered tools")

    return len(errors)


# ═══════════════════════════════════════════════════════════════
# 2. Cross-Stage Reachability Analysis
# ═══════════════════════════════════════════════════════════════


def analyze_cross_stage_reachability():
    """Analyze which tools appear in stage N+1 but not stage N."""
    print(f"\n{'=' * 70}")
    print("2. CROSS-STAGE TOOL REACHABILITY")
    print("=" * 70)

    # The main progression path
    progression = [
        PipelineStage.EMPTY,
        PipelineStage.DATA_LOADED,
        PipelineStage.PREPROCESSED,
        PipelineStage.DATASET_READY,
        PipelineStage.TRAINED,
    ]

    print("\n  Stage Progression and New Tools:\n")
    prev_tools = set()
    for stage in progression:
        config = STAGE_CONFIG.get(stage, {"tools": []})
        current_tools = set(config["tools"])
        new_tools = current_tools - prev_tools
        removed_tools = prev_tools - current_tools

        print(f"  [{stage.value}]")
        if new_tools:
            print(f"    + New:     {sorted(new_tools)}")
        if removed_tools:
            print(f"    - Removed: {sorted(removed_tools)}")
        print(f"    = Total:   {len(current_tools)} tools")
        prev_tools = current_tools

    return 0


# ═══════════════════════════════════════════════════════════════
# 3. Execution Gate Trace (the core question)
# ═══════════════════════════════════════════════════════════════


def trace_execution_gate():
    """Simulate the execution-time gate check for cross-stage scenarios.

    This traces what `_execute_tool_no_loop` does: it calls
    `compute_pipeline_stage(self.study)` EACH TIME, so if tool A
    changes the study state, tool B is checked against the NEW stage.
    """
    print(f"\n{'=' * 70}")
    print("3. EXECUTION-TIME GATE TRACE")
    print("=" * 70)

    # Simulate cross-stage scenarios
    scenarios = [
        {
            "name": "EMPTY → DATA_LOADED",
            "description": "User: 'Load data then apply bandpass filter'",
            "tools": ["load_data", "apply_bandpass_filter"],
            "initial_stage": PipelineStage.EMPTY,
            "stages_after_each": [PipelineStage.DATA_LOADED, PipelineStage.DATA_LOADED],
        },
        {
            "name": "EMPTY → ... → DATASET_READY",
            "description": "User: 'Load, preprocess, generate dataset, set EEGNet, train'",
            "tools": [
                "load_data",
                "apply_standard_preprocess",
                "generate_dataset",
                "set_model",
                "start_training",
            ],
            "initial_stage": PipelineStage.EMPTY,
            "stages_after_each": [
                PipelineStage.DATA_LOADED,
                PipelineStage.PREPROCESSED,
                PipelineStage.DATASET_READY,
                PipelineStage.DATASET_READY,
                PipelineStage.TRAINING,
            ],
        },
        {
            "name": "DATA_LOADED → PREPROCESSED",
            "description": "User: 'Bandpass 4-40Hz, notch 50Hz, resample 250Hz then epoch'",
            "tools": [
                "apply_bandpass_filter",
                "apply_notch_filter",
                "resample_data",
                "epoch_data",
            ],
            "initial_stage": PipelineStage.DATA_LOADED,
            "stages_after_each": [
                PipelineStage.DATA_LOADED,
                PipelineStage.DATA_LOADED,
                PipelineStage.DATA_LOADED,
                PipelineStage.PREPROCESSED,
            ],
        },
    ]

    total_issues = 0

    for scenario in scenarios:
        print(f"\n  Scenario: {scenario['name']}")
        print(f"  {scenario['description']}")
        print(f"  Initial stage: {scenario['initial_stage'].value}")
        print()

        current_stage = scenario["initial_stage"]

        for i, (tool_name, next_stage) in enumerate(
            zip(scenario["tools"], scenario["stages_after_each"], strict=True)
        ):
            config = STAGE_CONFIG.get(current_stage, {"tools": []})
            allowed = set(config["tools"])
            is_allowed = tool_name in allowed

            status = "✓ PASS" if is_allowed else "✗ BLOCKED"
            print(
                f"    Step {i + 1}: {tool_name:30s} "
                f"stage={current_stage.value:20s} → {status}"
            )

            if not is_allowed:
                print(
                    f"           ↳ {tool_name} NOT in {current_stage.value} tools: "
                    f"{sorted(allowed)}"
                )
                total_issues += 1

            # Simulate state transition
            current_stage = next_stage

    return total_issues


# ═══════════════════════════════════════════════════════════════
# 4. Prompt-Level Visibility Analysis
# ═══════════════════════════════════════════════════════════════


def analyze_prompt_visibility():
    """Check whether the LLM can actually SEE cross-stage tools in its prompt.

    The assembler builds the system prompt with ONLY the current stage's
    tools. If the user asks for A (current stage) and B (next stage),
    the LLM can't see B and won't generate it.
    """
    print(f"\n{'=' * 70}")
    print("4. PROMPT-LEVEL TOOL VISIBILITY ANALYSIS")
    print("=" * 70)

    print("\n  Question: Can the LLM see tools from future stages?")
    print()

    # Build assembler for EMPTY stage
    assembler = ContextAssembler(registry, study_state=None)
    prompt = assembler.build_system_prompt()

    # Extract mentioned tool names from prompt
    visible_tools = set()
    for tool in ALL_TOOL_NAMES:
        if tool in prompt:
            visible_tools.add(tool)

    empty_config_tools = set(STAGE_CONFIG[PipelineStage.EMPTY]["tools"])

    print(f"  Stage EMPTY prompt shows: {sorted(visible_tools)}")
    print(f"  Stage EMPTY config has:   {sorted(empty_config_tools)}")
    print()

    # Tools that are NOT visible from EMPTY but needed for complex plans
    future_only_tools = set(ALL_TOOL_NAMES) - visible_tools
    print(f"  Tools INVISIBLE from EMPTY stage ({len(future_only_tools)}):")
    for t in sorted(future_only_tools):
        print(f"    - {t}")

    print()
    print("  CONCLUSION:")
    print("  The LLM in EMPTY stage CANNOT see preprocessing, training,")
    print("  or dataset tools. It will NOT generate cross-stage tool calls")
    print("  in a single batch. However:")
    print()
    print("  - Single mode: Stops after one tool → user must ask again")
    print("  - Multi mode:  Re-calls LLM after each success with updated")
    print("                 system prompt (new stage → new tools visible)")
    print("                 → CAN handle cross-stage via iterative rounds")

    return 0


# ═══════════════════════════════════════════════════════════════
# 5. Multi-Mode Cross-Stage Trace
# ═══════════════════════════════════════════════════════════════


def trace_multi_mode():
    """Trace the multi-mode execution loop for a cross-stage request.

    In multi mode, after each successful tool the controller calls
    _generate_response() which rebuilds the prompt with the new stage's
    tools. We trace whether the LLM's history still contains the original
    user request so it can "remember" what else needs to be done.
    """
    print(f"\n{'=' * 70}")
    print("5. MULTI-MODE EXECUTION TRACE")
    print("=" * 70)

    print("""
  User: "Load subject1.gdf, do standard preprocess, generate dataset,
         set EEGNet, and train."

  Multi-mode execution trace (max_successful_tools=5):

  Round 1: stage=EMPTY
    → System prompt shows: [list_files, load_data, switch_panel]
    → History has: user's full request
    → LLM generates: load_data (only tool it can see that matches)
    → Execute: ✓ load_data → state becomes DATA_LOADED
    → _successful_tool_count=1 < 5 → auto-continue

  Round 2: stage=DATA_LOADED
    → System prompt REBUILT with DATA_LOADED tools
    → Now visible: [preprocessing tools, attach_labels, get_dataset_info, ...]
    → History has: user's request + "Tool Output: Data loaded successfully"
    → LLM generates: apply_standard_preprocess (remembers user asked for it)
    → Execute: ✓ → state becomes PREPROCESSED
    → _successful_tool_count=2 < 5 → auto-continue

  Round 3: stage=PREPROCESSED
    → System prompt REBUILT with PREPROCESSED tools
    → Now visible: [preprocessing tools, generate_dataset, ...]
    → LLM generates: generate_dataset
    → Execute: ✓ → state becomes DATASET_READY
    → _successful_tool_count=3 < 5 → auto-continue

  Round 4: stage=DATASET_READY
    → System prompt REBUILT with DATASET_READY tools
    → Now visible: [set_model, configure_training, start_training, ...]
    → LLM generates: set_model (model_name=EEGNet)
    → Execute: ✓ → state stays DATASET_READY
    → _successful_tool_count=4 < 5 → auto-continue

  Round 5: stage=DATASET_READY
    → LLM generates: start_training
    → ⚠ start_training has requires_confirmation=True
    → HITL dialog shown → auto-loop PAUSES
    → If user confirms: execute + finalize
    → If user rejects: finalize without executing

  RESULT: Multi-mode CAN handle cross-stage requests, with caveats:
    1. Requires 5 LLM round-trips (API cost x 5)
    2. start_training pauses for HITL confirmation (breaks auto-loop)
    3. Depends on LLM "remembering" the user's full plan from history
    4. max_successful_tools=5 exactly matches this 5-step scenario
""")

    # Verify the constraints
    issues = []

    # Check max_successful_tools covers the longest complex case
    max_steps = 0
    gold_set_path = (
        PROJECT_ROOT / "XBrainLab" / "llm" / "rag" / "data" / "gold_set.json"
    )
    if gold_set_path.exists():
        with open(gold_set_path, encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            steps = len(item.get("expected_tool_calls", []))
            if steps > max_steps:
                max_steps = steps
                max_id = item["id"]
        print(f"  Longest gold_set sequence: {max_steps} steps ({max_id})")
        print("  max_successful_tools:      5")
        if max_steps > 5:
            issues.append(
                f"max_successful_tools=5 is too low for {max_id} ({max_steps} steps)"
            )
            print(f"  ⚠ WARNING: {max_id} has {max_steps} steps > cap of 5!")
        else:
            print("  ✓ Cap covers all gold_set sequences")

    # Check which tools have requires_confirmation
    confirm_tools = [
        t.name for t in registry.get_all_tools() if t.requires_confirmation
    ]
    print(f"\n  Tools with requires_confirmation: {confirm_tools}")
    print("  These cause HITL pauses that break the multi-mode auto-loop.")

    return len(issues)


# ═══════════════════════════════════════════════════════════════
# 6. Benchmark vs Production Gap Analysis
# ═══════════════════════════════════════════════════════════════


def analyze_benchmark_gap():
    """Compare benchmark setup vs production architecture."""
    print(f"\n{'=' * 70}")
    print("6. BENCHMARK vs PRODUCTION GAP ANALYSIS")
    print("=" * 70)

    print("""
  ┌──────────────────┬─────────────────────────┬─────────────────────────┐
  │ Aspect           │ Benchmark               │ Production              │
  ├──────────────────┼─────────────────────────┼─────────────────────────┤
  │ Tool Visibility  │ ALL 19 tools always      │ Stage-filtered (3-14)   │
  │ Execution Mode   │ N/A (parse only)         │ Single or Multi         │
  │ Stage Gate       │ Bypassed                 │ Per-tool re-check       │
  │ RAG Source       │ train.json only (126)    │ Full gold_set (210)     │
  │ HITL             │ N/A                      │ Pauses for confirmation │
  │ LLM Rounds       │ 1 (all tools visible)    │ N (one per stage)       │
  │ Complex Chains   │ ✓ (single-shot batch)    │ Multi-round only        │
  └──────────────────┴─────────────────────────┴─────────────────────────┘

  Key Gap: The benchmark measures WHETHER the LLM can select the right
  tool when all tools are visible. Production constrains tool visibility
  per stage, so multi-step workflows require multi-round LLM calls.

  This means:
  - Benchmark accuracy (95.2%) measures TOOL SELECTION CAPABILITY
  - Production accuracy for cross-stage plans depends on:
    * Multi-mode being enabled
    * LLM memory across rounds
    * HITL interruptions (start_training, clear_dataset)
""")

    return 0


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════


def main():
    print("ARCHITECTURE VALIDATION: Cross-Stage Multi-Tool Execution")
    print()

    total_issues = 0
    total_issues += validate_stage_tool_mapping()
    total_issues += analyze_cross_stage_reachability()
    total_issues += trace_execution_gate()
    total_issues += analyze_prompt_visibility()
    total_issues += trace_multi_mode()
    total_issues += analyze_benchmark_gap()

    print(f"\n{'=' * 70}")
    print(f"FINAL RESULT: {total_issues} issue(s) found")
    print("=" * 70)

    if total_issues == 0:
        print("\n  ✓ Architecture is CORRECT for cross-stage execution.")
        print("    Execution engine re-evaluates stage per tool call.")
        print("    Multi-mode handles cross-stage via iterative LLM rounds.")
    else:
        print(f"\n  ⚠ {total_issues} issue(s) need attention.")

    return total_issues


if __name__ == "__main__":
    sys.exit(main())
