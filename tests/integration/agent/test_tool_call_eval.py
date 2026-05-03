from __future__ import annotations

import json
from pathlib import Path

from scripts.agent.evals.run_tool_call_eval import (
    build_eval_cases,
    run_eval,
    write_artifacts,
)


def test_deterministic_tool_call_eval_passes_and_writes_artifacts(tmp_path: Path):
    cases = build_eval_cases()
    assert len(cases) >= 50
    assert sum(len(case.user_turns) > 1 for case in cases) >= 15
    negative_cases = [
        case
        for case in cases
        if case.expected_blocked
        or case.expected_confirmation_required
        or case.expected_recovery
        or case.expected_result_interpretation == "recoverable_failure"
    ]
    assert len(negative_cases) / len(cases) >= 0.30
    assert {
        "scan_source",
        "preview_interpretation",
        "validate_interpretation",
        "apply_interpretation",
        "save_interpretation_recipe",
        "reload_interpretation_recipe",
    }.issubset({case.expected_intent for case in cases})

    result = run_eval(repeat_count=2)
    summary = result["summary"]

    assert summary["total_cases"] == len(cases)
    assert summary["failed_cases"] == 0
    assert summary["tool_selection_accuracy"] == 1.0
    assert summary["argument_correctness_accuracy"] == 1.0
    assert summary["blocked_command_accuracy"] == 1.0
    assert summary["state_aware_accuracy"] == 1.0
    assert summary["verification_result_match_accuracy"] == 1.0
    assert summary["state_delta_accuracy"] == 1.0
    assert summary["local_llm_reliability_accuracy"] == 1.0

    json_path, md_path = write_artifacts(result, tmp_path)

    assert json_path.exists()
    assert md_path.exists()
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["summary"]["failed_cases"] == 0
    first_case = saved["cases"][0]
    assert "available_command_summary" in first_case
    assert "parsed_tool_calls" in first_case
    assert "verification_result" in first_case
    assert "backend_result" in first_case
    assert "visible_response" in first_case
    assert "score_breakdown" in first_case
    assert "XBrainLab Tool-Call Eval" in md_path.read_text(encoding="utf-8")
