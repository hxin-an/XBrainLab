from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.dev.product_scenario_manifest import (
    IMMEDIATE_PROFILE_ID,
    PRODUCT_SCENARIO_PROFILES,
    PRODUCT_SCENARIOS,
)
from scripts.dev.run_product_scenario_manifest import (
    CommandOutcome,
    ScenarioRunError,
    build_plan,
    evaluate_scenarios,
    require_source_stability,
    run_product_scenarios,
)


def _selected(count: int = 2):
    ids = PRODUCT_SCENARIO_PROFILES[IMMEDIATE_PROFILE_ID].scenario_ids[:count]
    return tuple(PRODUCT_SCENARIOS[item] for item in ids)


def test_build_plan_is_profile_aware_and_selectors_do_not_claim_full_gate() -> None:
    full = build_plan(profile_id=IMMEDIATE_PROFILE_ID)
    subset = build_plan(
        profile_id=IMMEDIATE_PROFILE_ID,
        scenario_selectors=[full.scenarios[0].scenario_id],
    )

    assert len(full.scenarios) == 20
    assert full.profile_complete is True
    assert len(subset.scenarios) == 1
    assert subset.profile_complete is False
    assert subset.profile_expected_count == 20
    assert full.execution_ids.count("fetch-required-ci") == 1
    assert full.execution_ids.count("verify-required-ci") == 1
    assert full.execution_ids.index("fetch-required-ci") < full.execution_ids.index(
        "verify-required-ci"
    )

    agent_only = build_plan(
        profile_id=IMMEDIATE_PROFILE_ID,
        scenario_selectors=["agent.runtime-error-retry"],
    )
    assert "fetch-required-ci" not in agent_only.execution_ids
    assert "verify-required-ci" not in agent_only.execution_ids


def test_source_stability_fails_closed_on_commit_or_fingerprint_drift() -> None:
    require_source_stability(
        start={"commit_sha": "a", "source_digest": "b"},
        end={"commit_sha": "a", "source_digest": "b"},
    )

    with pytest.raises(ScenarioRunError, match="source changed"):
        require_source_stability(
            start={"commit_sha": "a", "source_digest": "b"},
            end={"commit_sha": "a", "source_digest": "changed"},
        )


def test_evaluation_rejects_missing_artifact_even_after_zero_return_code(
    tmp_path: Path,
) -> None:
    scenario = PRODUCT_SCENARIOS["data.source-format-capability-matrix"]
    outcome = CommandOutcome(
        execution_id=scenario.execution_id,
        command=("example",),
        timeout_seconds=1,
        return_code=0,
        timed_out=False,
        duration_seconds=0.1,
        stdout_path="logs/example.stdout.log",
        stderr_path="logs/example.stderr.log",
        failure_reason="",
    )

    results = evaluate_scenarios(
        scenarios=(scenario,),
        outcomes={scenario.execution_id: outcome},
        evidence_root=tmp_path,
    )

    assert results[0]["passed"] is False
    assert "artifact" in results[0]["failure_reason"].casefold()


def test_evaluation_rejects_symlinked_artifact_path(
    tmp_path: Path,
) -> None:
    scenario = PRODUCT_SCENARIOS["data.source-format-capability-matrix"]
    outside = tmp_path.parent / "outside-matrix.json"
    outside.write_text("{}", encoding="utf-8")
    (tmp_path / "dataset-validation-matrix.json").symlink_to(outside)

    results = evaluate_scenarios(
        scenarios=(scenario,),
        outcomes={
            scenario.execution_id: CommandOutcome.passed_for_test(scenario.execution_id)
        },
        evidence_root=tmp_path,
    )

    assert results[0]["passed"] is False
    assert "symlink" in results[0]["failure_reason"].casefold() or "escapes" in (
        results[0]["failure_reason"].casefold()
    )


def test_evaluation_rejects_timed_out_shared_execution_for_every_dependent_case(
    tmp_path: Path,
) -> None:
    scenarios = tuple(
        item
        for item in PRODUCT_SCENARIOS.values()
        if item.execution_id == "agent-showcase-selected"
    )
    outcome = CommandOutcome(
        execution_id="agent-showcase-selected",
        command=("example",),
        timeout_seconds=1,
        return_code=None,
        timed_out=True,
        duration_seconds=1.0,
        stdout_path="logs/example.stdout.log",
        stderr_path="logs/example.stderr.log",
        failure_reason="command timed out",
    )

    results = evaluate_scenarios(
        scenarios=scenarios,
        outcomes={outcome.execution_id: outcome},
        evidence_root=tmp_path,
    )

    assert len(results) == 8
    assert all(item["passed"] is False for item in results)
    assert all("timed out" in item["failure_reason"] for item in results)


def test_agent_shared_report_requires_one_distinct_passing_case_per_scenario(
    tmp_path: Path,
) -> None:
    scenarios = tuple(
        item
        for item in PRODUCT_SCENARIOS.values()
        if item.execution_id == "agent-showcase-selected"
    )
    artifact = tmp_path / "agent-toolcall-showcase" / "selected.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        json.dumps(
            {
                "summary": {"status": "passed"},
                "cases": [
                    {
                        "case_id": scenario.validator.key,
                        "pass": True,
                        "terminal": {"kind": "command_result", "status": "ok"},
                    }
                    for scenario in scenarios[:-1]
                ],
            }
        ),
        encoding="utf-8",
    )
    artifact.with_suffix(".md").write_text("# Agent cases\n", encoding="utf-8")
    outcome = CommandOutcome.passed_for_test("agent-showcase-selected")

    results = evaluate_scenarios(
        scenarios=scenarios,
        outcomes={outcome.execution_id: outcome},
        evidence_root=tmp_path,
    )

    assert sum(item["passed"] is True for item in results) == 7
    assert results[-1]["passed"] is False
    assert scenarios[-1].validator.key in results[-1]["failure_reason"]


def test_dpi_shared_report_requires_the_requested_unique_scale_record(
    tmp_path: Path,
) -> None:
    scenarios = tuple(
        item
        for item in PRODUCT_SCENARIOS.values()
        if item.execution_id == "chatpanel-dpi"
    )
    artifact = tmp_path / "ui" / "chatpanel-dpi" / "dpi-gate.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        json.dumps(
            {
                "status": "passed",
                "records": [
                    {
                        "scale": scale,
                        "status": "passed",
                        "full_window_dock": [{"file": "full.png"}],
                        "narrow_crops": [{"file": "narrow.png"}],
                        "dpi_content": [{"file": "content.png"}],
                    }
                    for scale in (1.0, 1.25)
                ],
            }
        ),
        encoding="utf-8",
    )
    outcome = CommandOutcome.passed_for_test("chatpanel-dpi")

    results = evaluate_scenarios(
        scenarios=scenarios,
        outcomes={outcome.execution_id: outcome},
        evidence_root=tmp_path,
    )

    assert [item["passed"] for item in results] == [True, True, False]
    assert "1.5" in results[-1]["failure_reason"]


def test_runner_report_distinguishes_selected_pass_from_immediate_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario_id = "data.source-format-capability-matrix"

    def fake_execute(**kwargs):
        evidence_root = kwargs["evidence_root"]
        artifact = evidence_root / "dataset-validation-matrix.json"
        artifact.write_text("{}", encoding="utf-8")
        return CommandOutcome.passed_for_test(kwargs["execution"].execution_id)

    identities = iter(
        [
            {"commit_sha": "a", "source_digest": "b"},
            {"commit_sha": "a", "source_digest": "b"},
        ]
    )
    monkeypatch.setattr(
        "scripts.dev.run_product_scenario_manifest.collect_source_identity",
        lambda *_args, **_kwargs: next(identities),
    )
    monkeypatch.setattr(
        "scripts.dev.run_product_scenario_manifest.execute_bounded",
        fake_execute,
    )

    report = run_product_scenarios(
        repo_root=tmp_path,
        evidence_root=tmp_path / "evidence",
        profile_id=IMMEDIATE_PROFILE_ID,
        scenario_selectors=[scenario_id],
    )

    assert report["summary"]["selected_status"] == "passed"
    assert report["summary"]["immediate_20_gate_passed"] is False
    assert report["profile"]["complete_selection"] is False
    assert report["profile"]["expected_scenario_count"] == 20
    assert report["profile"]["denominator_kind"] == "product_scenarios"
    assert report["profile"]["moabb_dataset_campaign_in_scope"] is False
    assert "<5%" in report["claim_boundary"]
    assert "MOABB" in report["claim_boundary"]


def test_failed_shared_fixture_setup_skips_dependents_and_fails_scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_execute(**kwargs):
        execution_id = kwargs["execution"].execution_id
        calls.append(execution_id)
        return CommandOutcome(
            execution_id=execution_id,
            command=("test-command",),
            timeout_seconds=1,
            return_code=1,
            timed_out=False,
            duration_seconds=0.1,
            stdout_path="logs/fetch.stdout.log",
            stderr_path="logs/fetch.stderr.log",
            failure_reason="fixture fetch failed",
        )

    identities = iter(
        [
            {"commit_sha": "a", "source_digest": "b"},
            {"commit_sha": "a", "source_digest": "b"},
        ]
    )
    monkeypatch.setattr(
        "scripts.dev.run_product_scenario_manifest.collect_source_identity",
        lambda *_args, **_kwargs: next(identities),
    )
    monkeypatch.setattr(
        "scripts.dev.run_product_scenario_manifest.execute_bounded",
        fake_execute,
    )

    report = run_product_scenarios(
        repo_root=tmp_path,
        evidence_root=tmp_path / "evidence",
        profile_id=IMMEDIATE_PROFILE_ID,
        scenario_selectors=["data.source-format-capability-matrix"],
    )

    assert calls == ["fetch-required-ci"]
    assert report["summary"]["selected_status"] == "failed"
    assert report["scenarios"][0]["passed"] is False
    assert "dependency failed" in report["scenarios"][0]["failure_reason"].casefold()
