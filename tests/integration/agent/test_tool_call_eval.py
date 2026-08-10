from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.agent.evals import run_tool_call_eval as tool_eval
from tests.integration.agent.deferred_split_support import (
    build_training_ready_state,
)
from XBrainLab.backend.application import CommandName
from XBrainLab.backend.application.capabilities import build_capability_policy


@pytest.fixture
def deferred_split_eval_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Align deterministic fixtures with command-derived deferred split state."""
    original_build_eval_cases = tool_eval.build_eval_cases
    original_make_state = tool_eval.make_state
    training_ready = build_training_ready_state()

    def build_eval_cases() -> list[tool_eval.EvalCase]:
        return [
            replace(
                case,
                expected_reason_terms=[
                    "Save a valid data splitting specification before training",
                    "Select a model before training",
                ],
            )
            if case.case_id == "zh-blocked-train-empty"
            else case
            for case in original_build_eval_cases()
        ]

    def make_state(name: str):
        if name == "training_ready":
            return training_ready
        return original_make_state(name)

    monkeypatch.setattr(tool_eval, "build_eval_cases", build_eval_cases)
    monkeypatch.setattr(tool_eval, "make_state", make_state)


@pytest.mark.usefixtures("deferred_split_eval_contract")
def test_eval_epoch_states_publish_usable_multiclass_payload() -> None:
    epoch_state_names = {
        case.state_name
        for case in tool_eval.build_eval_cases()
        if tool_eval.make_state(case.state_name).epoch.available
    }

    for state_name in epoch_state_names:
        state = tool_eval.make_state(state_name)
        epoch = state.epoch

        assert epoch.exists, state_name
        assert (
            isinstance(epoch.epoch_count, int)
            and not isinstance(epoch.epoch_count, bool)
            and epoch.epoch_count > 0
        ), state_name
        assert isinstance(epoch.event_ids, dict), state_name
        assert len(epoch.event_ids) >= 2, state_name
        assert set(epoch.event_names) == set(epoch.event_ids), state_name
        assert len(set(epoch.event_ids.values())) >= 2, state_name

    positive_dataset_cases = [
        case
        for case in tool_eval.build_eval_cases()
        if any(
            call.tool_name == "configure_dataset_split" for call in case.expected_tools
        )
    ]
    for case in positive_dataset_cases:
        capability = build_capability_policy(tool_eval.make_state(case.state_name)).get(
            CommandName.CONFIGURE_DATASET_SPLIT
        )

        assert capability.enabled, f"{case.case_id}: {capability.reasons}"


@pytest.mark.usefixtures("deferred_split_eval_contract")
def test_deterministic_tool_call_eval_passes_and_writes_artifacts(
    tmp_path: Path,
) -> None:
    cases = tool_eval.build_eval_cases()
    assert len(cases) >= 100
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
    families = {family for case in cases for family in case.families}
    assert {
        "chinese",
        "mixed_language",
        "no_call",
        "ambiguous_request",
        "multi_intent",
        "wrong_tool_temptation",
        "confirmation_boundary",
        "bids",
        "label_ambiguity",
    }.issubset(families)
    apply_lock_case = next(
        (
            case
            for case in cases
            if case.case_id == "wrong-tool-temptation-apply-after-epoch"
        ),
        None,
    )
    assert apply_lock_case is not None
    assert apply_lock_case.expected_intent == "apply_interpretation"
    assert apply_lock_case.expected_blocked
    assert not apply_lock_case.expected_tools
    assert {
        "wrong_tool_temptation",
        "blocked_command",
        "data_interpretation",
    }.issubset(set(apply_lock_case.families))
    remap_case = next(
        (case for case in cases if case.case_id == "recipe-preview-eeg-file-remap"),
        None,
    )
    assert remap_case is not None
    assert remap_case.expected_tools[0].tool_name == "preview_interpretation"
    assert remap_case.expected_tools[0].arguments == {
        "choices": {
            "eeg_file_remap": {
                "/recipe/old_raw.fif": "/data/new_raw.fif",
            }
        }
    }
    assert {"recipe_reload", "data_interpretation"}.issubset(set(remap_case.families))

    training_ready = tool_eval.make_state("training_ready")
    assert training_ready.dataset.split_spec_saved is True
    assert training_ready.dataset.split_materialized is False
    assert training_ready.active_dataset.has_saved_split is True
    assert (
        build_capability_policy(training_ready).get(CommandName.TRAIN).enabled is True
    )

    result = tool_eval.run_eval(repeat_count=2)
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
    assert summary["tool_or_no_tool_decision_accuracy"] == 1.0
    assert summary["clarification_behavior_accuracy"] == 1.0
    assert summary["confirmation_boundary_accuracy"] == 1.0
    assert summary["visible_response_quality_accuracy"] == 1.0
    assert summary["family_pass_rates"]["chinese"]["pass_rate"] == 1.0

    json_path, md_path = tool_eval.write_artifacts(result, tmp_path)

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
    assert "families" in first_case
    assert "XBrainLab Tool-Call Eval" in md_path.read_text(encoding="utf-8")
    report = md_path.read_text(encoding="utf-8")
    assert "Case Families" in report
    assert "Failure Taxonomy" in report
    assert "Thesis Claim Boundary" in report
