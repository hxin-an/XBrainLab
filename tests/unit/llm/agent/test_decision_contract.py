"""Public single-turn model schema and prompt agreement checks."""

import json

import pytest

from XBrainLab.llm.agent.decision_contract import model_proposal_schema
from XBrainLab.llm.agent.parser import CommandParser, ToolEnvelopeStatus
from XBrainLab.llm.agent.prompt_policy import StrictToolResponsePromptPolicy


@pytest.mark.parametrize(
    "payload",
    [
        {"tool_name": "resample_data", "parameters": {"rate": 128}},
        {
            "tool_name": "respond_to_user",
            "parameters": {"message": "Please restate the complete request."},
        },
    ],
)
def test_schema_and_parser_accept_single_turn_output(payload):
    schema = model_proposal_schema()
    assert set(payload) == set(schema["required"]) == {"tool_name", "parameters"}
    assert schema["additionalProperties"] is False
    result = CommandParser.parse_product(json.dumps(payload))
    assert result.status in (ToolEnvelopeStatus.VALID, ToolEnvelopeStatus.NO_TOOL)
    assert result.proposal_dict() == payload


@pytest.mark.parametrize(
    "parameters",
    [{}, {"message": ""}, {"message": "   "}, {"message": "Hi", "rate": 128}],
)
def test_schema_rejects_invalid_response_marker(parameters):
    result = CommandParser.parse_product(
        json.dumps({"tool_name": "respond_to_user", "parameters": parameters})
    )
    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    response_schema = model_proposal_schema()["allOf"][0]["then"]["properties"][
        "parameters"
    ]
    assert response_schema["required"] == ["message"]
    assert response_schema["additionalProperties"] is False


def test_normal_and_recovery_policy_use_only_single_turn_contract():
    policy = StrictToolResponsePromptPolicy()
    for text in (policy.decision_instructions(), policy.recovery_instructions()):
        assert "tool_name" in text
        assert "parameters" in text
        assert "respond_to_user" in text
        for retired in (
            "source_turn",
            "pending_request",
            "update_pending",
            "new_request",
            "cancel_pending",
        ):
            assert retired not in text
    assert "Example " not in policy.decision_instructions()
    assert policy.max_format_recovery_attempts == 1


def test_policy_keeps_current_turn_sources_and_backend_execution_separate():
    text = StrictToolResponsePromptPolicy().decision_instructions()
    for invariant in (
        "current_user.text",
        "complete request",
        "never fill missing parameters",
        "For multiple actions or an explanation plus an action",
        "Zero-parameter GUI",
        "Host confirmation is separate",
        "trusted tool result",
        "Starting training is not training completion",
    ):
        assert invariant in text
    for answer_field in ("case_id", "expected_intent", "expected_tools"):
        assert answer_field not in text
