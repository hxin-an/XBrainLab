from __future__ import annotations

import json
from pathlib import Path

from scripts.agent.evals.write_tool_call_eval_dashboard import (
    load_eval_results,
    render_dashboard,
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
    assert "Raw Model Pass Rate" in dashboard
    assert "Host-Assisted Pass Rate" in dashboard
    assert "Phi-4-mini-instruct" in dashboard
    assert "Family Pass Rates" in dashboard
    assert "chinese" in dashboard
    assert "Thesis Claim Boundary" in dashboard


def test_dashboard_warns_when_local_results_do_not_cover_latest_cases(
    tmp_path: Path,
):
    eval_dir = tmp_path / "agent_evals"
    primary_dir = eval_dir / "local_primary"
    primary_dir.mkdir(parents=True)

    _write_result(
        eval_dir / "latest.json",
        "deterministic",
        "deterministic",
        1.0,
        total_cases=121,
    )
    _write_result(
        primary_dir / "local_primary.json",
        "local-llm",
        "microsoft/Phi-4-mini-instruct",
        1.0,
        total_cases=118,
    )
    (primary_dir / "local_latest.json").write_text(
        json.dumps({"latest_result": "local_primary.json"}),
        encoding="utf-8",
    )

    dashboard_path = write_dashboard(eval_dir)
    dashboard = dashboard_path.read_text(encoding="utf-8")

    assert "do not cover the latest deterministic case suite" in dashboard
    assert "supports a thesis-candidate tool-call claim" not in dashboard


def test_dashboard_reads_nested_local_score_failures(
    tmp_path: Path,
) -> None:
    eval_dir = tmp_path / "agent_evals"
    local_dir = eval_dir / "local_primary"
    local_path = local_dir / "local_primary.json"
    _write_result(
        local_path,
        "local-llm",
        "microsoft/Phi-4-mini-instruct",
        0.9,
    )
    payload = json.loads(local_path.read_text(encoding="utf-8"))
    payload["cases"] = [
        {
            "case_id": "blocked-tool-call",
            "score": {
                "passed": False,
                "failures": ["tool/no-tool decision mismatch"],
            },
        }
    ]
    local_path.write_text(json.dumps(payload), encoding="utf-8")
    (local_dir / "local_latest.json").write_text(
        json.dumps({"latest_result": local_path.name}),
        encoding="utf-8",
    )

    dashboard = write_dashboard(eval_dir).read_text(encoding="utf-8")

    assert "`blocked-tool-call`" in dashboard
    assert "tool/no-tool decision mismatch" in dashboard


def test_dashboard_prefers_current_unassisted_candidate_over_legacy_results(
    tmp_path: Path,
) -> None:
    eval_dir = tmp_path / "agent_evals"
    legacy_dir = eval_dir / "local_fallback"
    current_dir = eval_dir / "current_candidate_strict"
    legacy_path = legacy_dir / "legacy.json"
    current_path = current_dir / "current.json"
    _write_result(
        eval_dir / "latest.json",
        "deterministic-scripted-baseline",
        "deterministic",
        1.0,
        total_cases=121,
    )
    _write_result(
        legacy_path,
        "local-llm",
        "microsoft/Phi-3.5-mini-instruct",
        1.0,
        total_cases=121,
    )
    legacy_payload = json.loads(legacy_path.read_text(encoding="utf-8"))
    legacy_payload["schema_version"] = "xbrainlab.local_tool_call_eval.v4"
    legacy_path.write_text(json.dumps(legacy_payload), encoding="utf-8")
    (legacy_dir / "local_latest.json").write_text(
        json.dumps({"latest_result": legacy_path.name}),
        encoding="utf-8",
    )
    _write_result(
        current_path,
        "local-llm",
        "microsoft/Phi-4-mini-instruct",
        0.5,
        total_cases=12,
    )
    current = json.loads(current_path.read_text(encoding="utf-8"))
    current.update(
        {
            "schema_version": "xbrainlab.local_tool_call_eval.v5",
            "repeat_count": 1,
            "exploratory": True,
            "prompt_condition": {
                "name": "state_capability_unassisted",
                "primary_raw_accuracy": True,
            },
            "evidence_status": {
                "engineering_baseline_protocol_complete": False,
                "thesis_candidate_protocol_complete": False,
            },
        }
    )
    current["host_assisted_summary"]["pass_rate"] = 1.0
    current["summary"]["runtime_safety_accuracy"] = None
    current["raw_model_summary"]["runtime_safety_accuracy"] = None
    current_path.write_text(json.dumps(current), encoding="utf-8")
    (current_dir / "local_latest.json").write_text(
        json.dumps({"latest_result": current_path.name}),
        encoding="utf-8",
    )

    results = load_eval_results(eval_dir)
    dashboard = write_dashboard(eval_dir).read_text(encoding="utf-8")

    assert [result["model_id"] for result in results] == [
        None,
        "microsoft/Phi-4-mini-instruct",
    ]
    assert "50.00%" in dashboard
    assert "100.00%" in dashboard
    runtime_row = next(
        line for line in dashboard.splitlines() if line.startswith("| runtime safety |")
    )
    assert "N/A" in runtime_row
    assert "do not cover the latest deterministic case suite" in dashboard
    assert "supports a thesis-candidate tool-call claim" not in dashboard


def test_dashboard_surfaces_current_anti_overfit_slice_separately(
    tmp_path: Path,
) -> None:
    eval_dir = tmp_path / "agent_evals"
    current_dir = eval_dir / "current_candidate_strict"
    anti_overfit_dir = current_dir / "anti_overfit"
    baseline_path = current_dir / "baseline.json"
    robustness_path = anti_overfit_dir / "robustness.json"
    _write_current_result(baseline_path, raw_rate=0.5, host_rate=1.0, cases=12)
    _write_current_result(
        robustness_path,
        raw_rate=1 / 7,
        host_rate=1.0,
        cases=7,
    )
    (current_dir / "local_latest.json").write_text(
        json.dumps({"latest_result": baseline_path.name}),
        encoding="utf-8",
    )
    (anti_overfit_dir / "local_latest.json").write_text(
        json.dumps({"latest_result": robustness_path.name}),
        encoding="utf-8",
    )

    dashboard = write_dashboard(eval_dir).read_text(encoding="utf-8")

    assert "Robustness / Anti-Overfit Gate" in dashboard
    assert "| Anti-overfit paraphrases | Phi-4-mini-instruct | 7 | 3 |" in dashboard
    assert "14.29%" in dashboard
    assert "100.00%" in dashboard
    assert "Raw gate failed" in dashboard


def test_thesis_claim_requires_two_aligned_clean_protocol_complete_models(
    tmp_path: Path,
) -> None:
    primary = _thesis_candidate_result(
        "microsoft/Phi-4-mini-instruct",
        commit="abc123",
        evaluation_fingerprint="primary-run",
    )

    single_dashboard = render_dashboard([primary], tmp_path)

    assert "requires accepted primary and fallback model artifacts" in (
        single_dashboard
    )
    assert "supports a thesis-candidate tool-call claim" not in single_dashboard

    fallback = _thesis_candidate_result(
        "microsoft/Phi-3.5-mini-instruct",
        commit="abc123",
        evaluation_fingerprint="fallback-run",
    )
    aligned_dashboard = render_dashboard([primary, fallback], tmp_path)

    assert "supports a thesis-candidate tool-call claim" in aligned_dashboard

    dirty_fallback = {
        **fallback,
        "provenance": {
            **fallback["provenance"],
            "git": {**fallback["provenance"]["git"], "dirty": True},
        },
    }
    dirty_dashboard = render_dashboard([primary, dirty_fallback], tmp_path)

    assert "clean checkpoint" in dirty_dashboard
    assert "supports a thesis-candidate tool-call claim" not in dirty_dashboard


def test_dashboard_shows_conditional_argument_denominator_from_raw_summary(
    tmp_path: Path,
) -> None:
    result = _thesis_candidate_result(
        "microsoft/Phi-4-mini-instruct",
        commit="abc123",
        evaluation_fingerprint="primary-run",
    )
    result["raw_model_summary"]["argument_correctness_accuracy"] = 2 / 3
    result["raw_model_summary"]["dimension_metrics"] = {
        "argument_correctness": {
            "accuracy": 2 / 3,
            "applicable_cases": 3,
            "excluded_cases": 126,
            "status": "partial",
        }
    }
    result["summary"] = result["raw_model_summary"]
    result["host_assisted_summary"]["argument_correctness_accuracy"] = 1.0

    dashboard = render_dashboard([result], tmp_path)

    assert "66.67% (2/3)" in dashboard
    assert "Argument correctness is conditional on correct tool selection" in (
        dashboard
    )


def _write_result(
    path: Path,
    runner: str,
    model_id: str,
    pass_rate: float,
    total_cases: int = 117,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "runner": runner,
        "model_id": None if model_id == "deterministic" else model_id,
        "repeat_count": 3,
        "exploratory": False,
        "summary": {
            "total_cases": total_cases,
            "passed_cases": int(pass_rate * total_cases),
            "failed_cases": total_cases - int(pass_rate * total_cases),
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
    if runner == "local-llm":
        payload.update(
            {
                "schema_version": "xbrainlab.local_tool_call_eval.v5",
                "prompt_condition": {
                    "name": "state_capability_unassisted",
                    "primary_raw_accuracy": True,
                },
            }
        )
        payload["raw_model_summary"] = dict(payload["summary"])
        payload["host_assisted_summary"] = {
            **payload["summary"],
            "pass_rate": min(pass_rate + 0.03, 1.0),
        }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_current_result(
    path: Path,
    *,
    raw_rate: float,
    host_rate: float,
    cases: int,
) -> None:
    _write_result(
        path,
        "local-llm",
        "microsoft/Phi-4-mini-instruct",
        raw_rate,
        total_cases=cases,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(
        {
            "schema_version": "xbrainlab.local_tool_call_eval.v5",
            "prompt_condition": {
                "name": "state_capability_unassisted",
                "primary_raw_accuracy": True,
            },
            "cli_gate": {"passed": raw_rate == 1.0},
        }
    )
    payload["raw_model_summary"]["pass_rate"] = raw_rate
    payload["host_assisted_summary"]["pass_rate"] = host_rate
    payload["repeat_count"] = 3
    path.write_text(json.dumps(payload), encoding="utf-8")


def _thesis_candidate_result(
    model_id: str,
    *,
    commit: str,
    evaluation_fingerprint: str,
) -> dict:
    summary = {
        "total_cases": 129,
        "passed_cases": 124,
        "failed_cases": 5,
        "pass_rate": 124 / 129,
        "score_scope": "raw_model_decision",
        "intent_accuracy": 0.95,
        "local_llm_reliability_accuracy": 1.0,
        "dimension_metrics": {},
        "family_pass_rates": {},
    }
    return {
        "schema_version": "xbrainlab.local_tool_call_eval.v5",
        "runner": "local-llm",
        "model_id": model_id,
        "repeat_count": 3,
        "total_cases": 129,
        "exploratory": False,
        "prompt_condition": {
            "name": "state_capability_unassisted",
            "primary_raw_accuracy": True,
        },
        "evidence_status": {
            "thesis_candidate_protocol_complete": True,
        },
        "benchmark_coverage": {
            "negative_blocked_recovery_ratio": 0.35,
            "minimum_negative_blocked_recovery_ratio": 0.30,
            "required_categories_present": True,
            "protocol_mix_complete": True,
        },
        "measurement_contract": {
            "raw_model_score_scope": "raw_model_decision",
            "host_assisted_score_scope": "host_assisted_decision",
        },
        "cli_gate": {
            "mode": "strict",
            "score_scope": "raw_model_decision",
            "passed": True,
        },
        "provenance": {
            "git": {"commit": commit, "dirty": False},
            "case_fingerprint": "same-cases",
            "prompt_fingerprint": "same-prompt",
            "tool_contract_fingerprint": "same-tools",
            "evaluation_fingerprint": evaluation_fingerprint,
            "model_revision": f"revision-{model_id}",
        },
        "summary": summary,
        "raw_model_summary": summary,
        "host_assisted_summary": {
            **summary,
            "score_scope": "host_assisted_decision",
            "pass_rate": 1.0,
        },
        "failure_taxonomy": {},
        "cases": [],
        "fixture_source_paths": [],
        "artifact_paths": {},
    }
