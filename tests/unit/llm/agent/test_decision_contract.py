from __future__ import annotations

from XBrainLab.llm.agent.decision_contract import model_response_tool_contract
from XBrainLab.llm.agent.prompt_policy import StrictToolResponsePromptPolicy


def test_model_response_schema_allows_only_ordinary_or_typed_clarification() -> None:
    contract = model_response_tool_contract()
    parameters = contract["parameters"]

    assert contract["name"] == "respond_to_user"
    ordinary, clarification = parameters["oneOf"]
    assert set(ordinary["properties"]) == {"message"}
    assert ordinary["required"] == ["message"]
    assert ordinary["additionalProperties"] is False
    assert set(clarification["properties"]) == {
        "message",
        "pending_action",
        "missing_inputs",
    }
    assert clarification["required"] == [
        "message",
        "pending_action",
        "missing_inputs",
    ]
    assert clarification["additionalProperties"] is False


def test_prompt_policy_describes_typed_clarification_for_user_responses() -> None:
    policy = StrictToolResponsePromptPolicy()
    instructions = policy.decision_instructions()
    recovery = policy.recovery_instructions()

    for text in (instructions, recovery):
        assert "missing_inputs" in text
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
    decision = policy.decision_instructions().lower()
    recovery = policy.recovery_instructions().lower()

    assert (
        "root object must contain exactly workflow_stage, tool_name, and parameters"
        in decision
    )
    assert 'root object must be exactly {"workflow_stage":' in recovery
    for prompt in (decision, recovery):
        assert "never wrap it in tool-call, tool_call, action, or function" in prompt
        assert "tool-call branch" not in prompt


def test_prompt_policy_allows_two_bounded_repairs() -> None:
    assert StrictToolResponsePromptPolicy().max_format_recovery_attempts == 2


def test_prompt_policy_preserves_explicit_supported_optional_values() -> None:
    prompt = StrictToolResponsePromptPolicy().decision_instructions().lower()

    assert "copy every supported value explicitly stated" in prompt
    assert "even when the schema marks it optional" in prompt
    assert "never omit an explicitly requested supported value" in prompt


def test_prompt_policy_uses_no_action_for_ambiguous_or_negated_requests() -> None:
    prompt = StrictToolResponsePromptPolicy().decision_instructions().lower()

    assert "negated" in prompt
    assert "ambiguous" in prompt
    assert "use respond_to_user" in prompt


def test_prompt_policy_orders_meaning_before_callable_action_selection() -> None:
    prompt = StrictToolResponsePromptPolicy().decision_instructions().lower()

    assert "first identify the exact action requested by meaning" in prompt
    assert "only call it when that exact action is listed as callable" in prompt
    assert "a prerequisite named in a blocker is not a user request" in prompt
    assert "do not perform a prerequisite or substitute action" in prompt
    assert prompt.index("first identify") < prompt.index("direct preprocessing")


def test_prompt_policy_defers_multi_action_requests_without_execution() -> None:
    prompt = StrictToolResponsePromptPolicy().decision_instructions().lower()

    assert "multi-action request" in prompt
    assert "respond_to_user with message only" in prompt


def test_prompt_policy_forbids_unverified_completion_claims() -> None:
    prompt = StrictToolResponsePromptPolicy().decision_instructions().lower()

    assert "never claim that an action completed" in prompt
    assert "trusted tool result confirms completion" in prompt
