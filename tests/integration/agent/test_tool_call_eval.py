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
    assert len(cases) >= 20

    result = run_eval(repeat_count=2)
    summary = result["summary"]

    assert summary["total_cases"] == len(cases)
    assert summary["failed_cases"] == 0
    assert summary["tool_selection_accuracy"] == 1.0
    assert summary["argument_correctness_accuracy"] == 1.0
    assert summary["blocked_command_accuracy"] == 1.0
    assert summary["state_aware_accuracy"] == 1.0
    assert summary["local_llm_reliability_accuracy"] == 1.0

    json_path, md_path = write_artifacts(result, tmp_path)

    assert json_path.exists()
    assert md_path.exists()
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["summary"]["failed_cases"] == 0
    assert "XBrainLab Tool-Call Eval" in md_path.read_text(encoding="utf-8")
