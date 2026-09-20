"""Pilot case admission never accepts Test, drifting identities or output reuse."""

from pathlib import Path

import pytest

from scripts.dev.assistant_pilot_case import (
    audit_initial_input,
    force_case_exit,
    validate_case_request,
    verify_prompt_captures,
)


def request():
    return {
        "case": {
            "case_id": "DEV-A01-01-V0",
            "split": "DEV",
            "input": "Open import",
            "fixture_id": "f",
            "expected_workflow_stage": "empty",
        },
        "fixture": {"metadata": {"fixture_id": "f"}, "conditions": {"stage": "empty"}},
        "model_id": "google/gemma-3-4b-it",
        "model_cache": "D:/cache",
        "rag_enabled": False,
        "seed": 0,
        "repeat": 0,
    }


def test_valid_case_and_frozen_launch():
    value = request()
    validate_case_request(value)


def test_hard_deadline_exits_even_when_owner_close_raises(tmp_path):
    from types import SimpleNamespace

    class Broken:
        def close(self, **_kwargs):
            raise RuntimeError("already closing")

    owner = Broken()
    manager = SimpleNamespace(
        agent_controller=SimpleNamespace(
            worker=SimpleNamespace(engine=owner), _rag_lifecycle=owner
        )
    )
    exits = []
    force_case_exit(
        manager,
        {"issues": []},
        tmp_path / "result.json",
        exit_process=exits.append,
        cleanup_wait=0.01,
    )
    assert exits == [124]


def test_hard_deadline_exits_when_worker_has_already_been_released(tmp_path):
    from types import SimpleNamespace

    exits = []
    force_case_exit(
        SimpleNamespace(agent_controller=SimpleNamespace(worker=None)),
        {"issues": []},
        tmp_path / "result.json",
        exit_process=exits.append,
        cleanup_wait=0.01,
    )
    assert exits == [124]


@pytest.mark.parametrize(
    "field,value",
    [
        ("split", "TEST"),
        ("case_id", "TEST-A01"),
        ("input", ""),
        ("fixture_id", "wrong"),
    ],
)
def test_reject_invalid_case(field, value):
    payload = request()
    payload["case"][field] = value
    with pytest.raises(ValueError):
        validate_case_request(payload)


@pytest.mark.parametrize(
    "field,value",
    [("model_id", "other/model"), ("rag_enabled", "false"), ("seed", 1), ("repeat", 1)],
)
def test_reject_unapproved_condition(field, value):
    payload = request()
    payload[field] = value
    with pytest.raises(ValueError):
        validate_case_request(payload)


def test_missing_capture_cannot_certify_trace(tmp_path: Path):
    assert verify_prompt_captures(
        tmp_path, [{"raw_response": "hello"}], warmup_count=0
    )["issues"]


def test_pre_generation_timeout_requires_actual_submission_and_cancellation():
    case = {"input": "Open import."}
    trace = {
        "generations": [],
        "turn_terminal": {"outcome": "cancelled"},
        "events": [{"kind": "submission", "payload": {"text": case["input"]}}],
    }
    result = audit_initial_input(case, {}, trace, decision_timed_out=True)
    assert result["issues"] == []
    assert result["sent_to_model"] is False
    trace["events"][0]["payload"]["text"] = "Different input."
    assert audit_initial_input(case, {}, trace, decision_timed_out=True)["issues"]


def _capture(root, raw, *, sequence=1, status="cancelled", corrupt=False):
    import hashlib
    import json

    target = root / "worker" / str(sequence)
    target.mkdir(parents=True)
    prompt = b"actual rendered prompt"
    raw_bytes = raw.encode("utf-8")
    (target / "prompt.txt").write_bytes(prompt)
    (target / "raw-output.txt").write_bytes(raw_bytes)
    (target / "metadata.json").write_text(
        json.dumps(
            {
                "status": status,
                "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
                "raw_output_sha256": "0" * 64
                if corrupt
                else hashlib.sha256(raw_bytes).hexdigest(),
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize("observed", ["", "partial", "partial尾"])
def test_cancelled_capture_retains_unobserved_tail_without_changing_trace(
    tmp_path, observed
):
    captured = "partial尾段"
    _capture(tmp_path, captured)
    generation = {"raw_response": observed, "terminal": "cancelled"}
    actual = verify_prompt_captures(tmp_path, [generation], warmup_count=0)
    assert actual["issues"] == []
    assert actual["captures"][0]["unobserved_tail_chars"] == len(captured) - len(
        observed
    )
    assert actual["captures"][0]["observed_raw_chars"] == len(observed)
    assert generation["raw_response"] == observed


def test_capture_boundary_excludes_prior_condition_warmup_and_case(tmp_path):
    _capture(tmp_path, "READY", sequence=1, status="completed")
    _capture(tmp_path, "old", sequence=2, status="completed")
    _capture(tmp_path, "current", sequence=3, status="completed")
    actual = verify_prompt_captures(
        tmp_path,
        [{"raw_response": "current", "terminal": "finished"}],
        warmup_count=0,
        start_index=2,
    )
    assert actual["issues"] == []
    assert len(actual["captures"]) == 1
    assert actual["captures"][0]["metadata"]["status"] == "completed"


@pytest.mark.parametrize(
    "status,terminal,observed",
    [
        ("completed", "finished", "partial"),
        ("completed", "cancelled", "partial"),
        ("failed", "cancelled", "partial"),
        ("cancelled", "finished", "partial"),
        ("cancelled", "error", "partial"),
        ("cancelled", "cancelled", "wrong prefix"),
        ("cancelled", "cancelled", "partial tail extra"),
    ],
)
def test_capture_prefix_exception_is_only_for_confirmed_cancellation(
    tmp_path, status, terminal, observed
):
    _capture(tmp_path, "partial tail", status=status)
    actual = verify_prompt_captures(
        tmp_path, [{"raw_response": observed, "terminal": terminal}], warmup_count=0
    )
    assert "capture_response_mismatch" in actual["issues"]


def test_cancelled_prefix_does_not_bypass_capture_hash_check(tmp_path):
    _capture(tmp_path, "partial tail", corrupt=True)
    actual = verify_prompt_captures(
        tmp_path,
        [{"raw_response": "partial", "terminal": "cancelled"}],
        warmup_count=0,
    )
    assert "capture_integrity" in actual["issues"]


def test_completed_capture_still_accepts_exact_observed_output(tmp_path):
    _capture(tmp_path, "exact", status="completed")
    actual = verify_prompt_captures(
        tmp_path,
        [{"raw_response": "exact", "terminal": "finished"}],
        warmup_count=0,
    )
    assert actual["issues"] == []
    assert actual["captures"][0]["unobserved_tail_chars"] == 0


def test_initial_input_audit_rejects_history_and_authoritative_missing_value():
    import json

    case = {"input": "Filter from 8 Hz."}
    fixture = {"conditions": {"missing_authoritative_values": ["high_freq"]}}
    context = {
        "schema": "xbrainlab.untrusted_context.v1",
        "trust": "untrusted",
        "items": [{"type": "state_card", "data": {"high_freq": 30}}],
    }
    messages = [
        {"role": "system", "content": "policy"},
        {"role": "user", "content": json.dumps(context)},
        {"role": "assistant", "content": "Old answer"},
        {"role": "user", "content": case["input"]},
    ]
    trace = {"generations": [{"request": {"messages": messages}}]}
    result = audit_initial_input(case, fixture, trace)
    assert "initial_conversation_not_fresh" in result["issues"]
    assert "missing_value_present_in_state:high_freq" in result["issues"]


def test_initial_input_audit_keeps_untrusted_rag_examples_separate_from_state():
    import json

    case = {"input": "Filter from 8 Hz."}
    fixture = {"conditions": {"missing_authoritative_values": ["high_freq"]}}
    context = {
        "schema": "xbrainlab.untrusted_context.v1",
        "trust": "untrusted",
        "items": [
            {"type": "state_card", "data": {"raw_count": 1}},
            {"type": "rag_example", "data": {"high_freq": 30}},
        ],
    }
    messages = [
        {"role": "system", "content": "policy"},
        {"role": "user", "content": json.dumps(context)},
        {"role": "user", "content": case["input"]},
    ]
    trace = {
        "generations": [{"request": {"messages": [list(m.items()) for m in messages]}}]
    }
    result = audit_initial_input(case, fixture, trace)
    assert result["issues"] == []
    assert result["untrusted_rag_example_count"] == 1
    assert result["human_review_required_for_input_semantics"] is True
