from __future__ import annotations

import json
from pathlib import Path

from scripts.agent.evals.write_tool_call_eval_dashboard import (
    load_eval_results,
    write_dashboard,
)


def test_dashboard_compares_models_and_families(tmp_path: Path):
    eval_dir = tmp_path / "agent_evals"
    primary_dir = eval_dir / "local_primary"
    fallback_dir = eval_dir / "local_fallback"
    primary_dir.mkdir(parents=True)
    fallback_dir.mkdir(parents=True)

    _write_result(eval_dir / "latest.json", "deterministic", "deterministic", 1.0)
    _write_result(
        primary_dir / "local_primary.json",
        "local-llm",
        "microsoft/Phi-4-mini-instruct",
        0.95,
    )
    _write_result(
        fallback_dir / "local_fallback.json",
        "local-llm",
        "microsoft/Phi-3.5-mini-instruct",
        0.9,
    )
    (primary_dir / "local_latest.json").write_text(
        json.dumps({"latest_result": "local_primary.json"}),
        encoding="utf-8",
    )
    (fallback_dir / "local_latest.json").write_text(
        json.dumps({"latest_result": "local_fallback.json"}),
        encoding="utf-8",
    )

    results = load_eval_results(eval_dir)
    dashboard_path = write_dashboard(eval_dir)
    dashboard = dashboard_path.read_text(encoding="utf-8")

    assert len(results) == 3
    assert "Model Comparison" in dashboard
    assert "Phi-4-mini-instruct" in dashboard
    assert "Family Pass Rates" in dashboard
    assert "chinese" in dashboard
    assert "Thesis Claim Boundary" in dashboard


def _write_result(
    path: Path,
    runner: str,
    model_id: str,
    pass_rate: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "runner": runner,
        "model_id": None if model_id == "deterministic" else model_id,
        "repeat_count": 3,
        "exploratory": False,
        "summary": {
            "total_cases": 117,
            "passed_cases": int(pass_rate * 117),
            "failed_cases": 117 - int(pass_rate * 117),
            "pass_rate": pass_rate,
            "intent_accuracy": pass_rate,
            "local_llm_reliability_accuracy": pass_rate,
            "family_pass_rates": {
                "chinese": {
                    "total": 2,
                    "passed": 2 if pass_rate >= 0.9 else 1,
                    "pass_rate": 1.0 if pass_rate >= 0.9 else 0.5,
                }
            },
        },
        "failure_taxonomy": {},
        "cases": [],
        "fixture_source_paths": ["scripts/agent/evals/run_tool_call_eval.py"],
        "artifact_paths": {"json": str(path)},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
