from __future__ import annotations

from typing import Any

from XBrainLab.llm.agent.decision_contract import model_response_tool_contract
from XBrainLab.llm.agent.prompt_policy import StrictToolResponsePromptPolicy


def _response_branches() -> dict[str, dict[str, Any]]:
    parameters = model_response_tool_contract()["parameters"]
    return {
        branch["properties"]["decision"]["const"]: branch
        for branch in parameters["oneOf"]
    }


def test_model_response_schema_is_discriminated_by_decision() -> None:
    contract = model_response_tool_contract()
    parameters = contract["parameters"]

    assert contract["name"] == "respond_to_user"
    assert parameters["type"] == "object"
    assert set(_response_branches()) == {"blocked", "missing_input", "answer"}


def test_model_response_schema_exposes_exact_fields_for_each_branch() -> None:
    branches = _response_branches()

    assert set(branches["blocked"]["properties"]) == {"decision", "message"}
    assert branches["blocked"]["required"] == ["decision", "message"]
    assert branches["blocked"]["additionalProperties"] is False

    assert set(branches["missing_input"]["properties"]) == {
        "decision",
        "missing_inputs",
        "message",
    }
    assert branches["missing_input"]["required"] == [
        "decision",
        "missing_inputs",
        "message",
    ]
    assert branches["missing_input"]["additionalProperties"] is False
    missing_inputs = branches["missing_input"]["properties"]["missing_inputs"]
    assert missing_inputs["minItems"] == 1
    assert missing_inputs["uniqueItems"] is True
    assert missing_inputs["items"]["type"] == "string"
    assert missing_inputs["items"]["pattern"] == r"\S"

    assert set(branches["answer"]["properties"]) == {"decision", "message"}
    assert branches["answer"]["required"] == ["decision", "message"]
    assert branches["answer"]["additionalProperties"] is False

    for branch in branches.values():
        assert branch["properties"]["message"]["pattern"] == r"\S"


def test_prompt_policy_describes_only_fields_present_in_each_branch() -> None:
    policy = StrictToolResponsePromptPolicy()
    instructions = policy.decision_instructions()
    recovery = policy.recovery_instructions()

    for text in (instructions, recovery):
        assert "blocked uses exactly decision and message" in text
        assert (
            "missing_input uses exactly decision, missing_inputs, and message" in text
        )
        assert "answer uses exactly decision and message" in text
        assert "command, tool, name, arguments, or reasons" not in text


def test_prompt_policy_contains_no_evaluator_answer_fields() -> None:
    prompt = StrictToolResponsePromptPolicy().decision_instructions().lower()

    for answer_field in (
        "case_id",
        "expected_intent",
        "expected_tools",
        "expected_verification_result",
    ):
        assert answer_field not in prompt


def test_prompt_policy_keeps_enabled_direct_actions_behind_host_confirmation() -> None:
    prompt = StrictToolResponsePromptPolicy().decision_instructions().lower()

    assert "still propose that exact tool call" in prompt
    assert "host will request confirmation before execution" in prompt
    assert "do not describe it as blocked" in prompt


def test_prompt_policy_makes_the_action_root_shape_unambiguous() -> None:
    policy = StrictToolResponsePromptPolicy()

    for prompt in (
        policy.decision_instructions().lower(),
        policy.recovery_instructions().lower(),
    ):
        assert 'root object must be exactly {"tool_name":' in prompt
        assert "never wrap it in tool-call, tool_call, action, or function" in prompt
        assert "tool-call branch" not in prompt
