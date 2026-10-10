"""The approved fixed 20 remain single-turn model evidence, not Host rescue."""

import json
from dataclasses import asdict

import pytest

from scripts.dev import run_stable_assistant_model_eval as runner
from XBrainLab.llm.core.config import LLMConfig


def test_manifest_fixed_twenty_preserves_reused_inputs_and_oracles():
    cases = runner.load_single_turn_cases()
    assert len(cases) == len({case.case_id for case in cases}) == 20
    existing = {
        case.case_id: case
        for case in (*runner.load_target_cases(), *runner.load_precision_cases())
    }
    for case in cases:
        if case.case_id in existing:
            assert case.user_input == existing[case.case_id].user_input
            if isinstance(case, runner.TargetEvalCase):
                assert (
                    case.expected_parameters
                    == existing[case.case_id].expected_parameters
                )
    assert cases[-1].user_input == "Apply a bandpass filter from 7 to 30 Hz."


def test_manifest_corruption_fails_closed(tmp_path):
    changed = tmp_path / "cases.json"
    changed.write_bytes(runner.DEFAULT_SINGLE_TURN_CASES.read_bytes() + b" ")
    with pytest.raises(ValueError, match="manifest changed"):
        runner.load_single_turn_cases(changed)


@pytest.mark.parametrize(
    "case", runner.load_single_turn_cases(), ids=lambda case: case.case_id
)
def test_all_twenty_publish_current_complete_input(case):
    messages = runner.build_case_messages(case, runner.target_tool_registry())
    assert case.user_input in messages[-1]["content"]
    assert "pending_request" not in messages[-1]["content"]
    assert "tool_name" in messages[0]["content"]


def test_valid_wrong_decision_never_retries_or_gets_host_rescued():
    case = next(
        case
        for case in runner.load_single_turn_cases()
        if case.case_id == "missing_bandpass_en"
    )
    calls = []

    def generate(messages):
        calls.append(messages)
        return '{"tool_name":"apply_bandpass_filter","parameters":{"low_freq":7,"high_freq":30}}'

    result = runner.evaluate_case_trajectory(
        case, runner.target_tool_registry(), generate
    )
    assert len(calls) == 1
    assert not result.raw_score.passed
    assert not result.post_recovery_score.passed
    assert not result.final_score.passed
    assert result.product_terminal["execution_boundary_reached"]
    assert result.product_terminal["execution_suppressed"]
    assert not result.product_terminal["gui_handoff_reached"]
    assert not result.product_terminal["application_service_called"]
    assert not result.product_terminal["tool_executor_called"]
    assert not result.product_terminal["state_mutation_observed"]


def test_one_format_repair_keeps_wrong_raw_separate_from_correct_final():
    case = runner.load_single_turn_cases()[-1]
    outputs = iter(
        [
            "not json",
            '{"tool_name":"apply_bandpass_filter","parameters":{"low_freq":7,"high_freq":30}}',
        ]
    )
    result = runner.evaluate_case_trajectory(
        case, runner.target_tool_registry(), lambda _messages: next(outputs)
    )
    assert len(result.attempts) == 2
    assert not result.raw_score.passed
    assert result.post_recovery_score.passed
    assert result.product_terminal["execution_suppressed"]


def test_run_report_does_not_promote_any_reply_to_semantic_pass(monkeypatch):
    closed = []

    class Engine:
        def __init__(self, _config):
            pass

        def load_model(self):
            pass

        def generate_stream(self, _messages, **_kwargs):
            yield '{"tool_name":"respond_to_user","parameters":{"message":"A reply."}}'

        def close(self):
            closed.append(True)
            return True

    monkeypatch.setattr(runner, "LLMEngine", Engine)
    case = next(
        case for case in runner.load_single_turn_cases() if case.case_id == "E10a"
    )
    report = runner.run_eval(LLMConfig(device="cpu"), (case,), rag_mode="off")
    assert closed == [True]
    assert report["case_summaries"]["total"]["complete"]
    assert report["results"][0]["post_recovery_score"]["passed"]
    assert report["candidate_gate"]["semantic_review"]["case_ids"] == ["E10a"]
    assert not report["candidate_gate"]["fixed_twenty_complete"]
    assert not runner.report_candidate_passed(report)
    json.dumps(report)


@pytest.mark.parametrize(
    "defect",
    [
        None,
        "missing_case",
        "wrong_model_choice",
        "capture",
        "cleanup",
        "rag_degraded",
        "excess_retry",
        "model",
        "capture_integrity",
        "generation_policy",
        "rag_protocol",
        "candidate_gate",
        "bad_retry",
        "null_attempts",
        "null_score",
        "null_trajectory",
        "format_retry",
        "multiple_object_retry",
        "valid_retry",
        "reply_retry",
        "unknown_retry",
        "missing_retry_status",
    ],
)
def test_automatic_gate_is_independent_of_semantic_review_and_fails_closed(defect):
    cases = runner.load_single_turn_cases()
    rows = [
        {
            "case": asdict(case),
            "first_generation_score": {"passed": True},
            "post_recovery_score": {"passed": True},
            "trajectory": {
                "format_recovery_attempts": 0,
                "actual_generation_call_indices": [index],
                "policy_attempts": [{"envelope_status": "valid"}],
            },
            "rag_context": {"status": "retrieved"},
        }
        for index, case in enumerate(cases, 1)
    ]
    report = {
        "schema_version": runner.REPORT_SCHEMA,
        "manifest_sha256": runner.SINGLE_TURN_CASES_SHA256,
        "model": {
            "id": runner.BOUNDED_BASELINE_MODEL_ID,
            "revision": runner.BOUNDED_BASELINE_MODEL_REVISION,
        },
        "results": rows,
        "engine_closed": True,
        "generation_trace": [
            {"global_call_index": index, "case_id": case.case_id}
            for index, case in enumerate(cases, 1)
        ],
        "capture_integrity": {
            "requested": True,
            "status": "verified",
            "artifact_count": 20,
        },
        "generation_policy": {"max_format_recovery_attempts": 1},
        "rag_protocol": {"name": "product_process_rag.v1"},
        "candidate_gate": {"passed": False, "semantic_review": {"status": "required"}},
    }
    if defect == "missing_case":
        rows.pop()
    elif defect == "wrong_model_choice":
        rows[0]["post_recovery_score"]["passed"] = False
    elif defect == "capture":
        report["capture_integrity"]["status"] = "not_requested"
    elif defect == "cleanup":
        report["engine_closed"] = False
    elif defect == "rag_degraded":
        rows[0]["rag_context"]["status"] = "error"
    elif defect == "excess_retry":
        rows[0]["trajectory"]["format_recovery_attempts"] = 2
    elif defect in {
        "model",
        "capture_integrity",
        "generation_policy",
        "rag_protocol",
        "candidate_gate",
    }:
        report[defect] = None
    elif defect == "bad_retry":
        rows[0]["trajectory"]["format_recovery_attempts"] = "bad"
    elif defect == "null_attempts":
        rows[0]["trajectory"]["policy_attempts"] = None
    elif defect == "null_score":
        rows[0]["post_recovery_score"] = None
    elif defect == "null_trajectory":
        rows[0]["trajectory"] = None
    elif defect in {
        "format_retry",
        "multiple_object_retry",
        "valid_retry",
        "reply_retry",
        "unknown_retry",
        "missing_retry_status",
    }:
        first_status = {
            "format_retry": "format_error",
            "multiple_object_retry": "multiple_objects",
            "valid_retry": "valid",
            "reply_retry": "no_tool",
            "unknown_retry": "unknown",
            "missing_retry_status": None,
        }[defect]
        rows[-1]["first_generation_score"]["passed"] = False
        rows[-1]["trajectory"] = {
            "format_recovery_attempts": 1,
            "actual_generation_call_indices": [20, 21],
            "policy_attempts": [
                {"envelope_status": first_status},
                {"envelope_status": "valid"},
            ],
        }
        report["generation_trace"].append(
            {"global_call_index": 21, "case_id": cases[-1].case_id}
        )
        report["capture_integrity"]["artifact_count"] = 21
    assert runner.report_automated_model_checks_passed(report) is (
        defect in {None, "candidate_gate", "format_retry"}
    )
    assert not runner.report_candidate_passed(report)


def test_candidate_reader_rejects_true_flags_with_no_evidence_and_failed_cleanup():
    report = {
        "schema_version": runner.REPORT_SCHEMA,
        "candidate_gate": {
            "passed": True,
            "fixed_twenty_complete": True,
            "post_format_repair_twenty_passed": True,
            "capture_verified": True,
            "semantic_review": {"status": "passed"},
        },
        "results": [],
        "engine_closed": False,
    }
    assert not runner.report_candidate_passed(report)
    assert not runner.report_automated_model_checks_passed(report)
