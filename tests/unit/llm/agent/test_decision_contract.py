"""Public model schema and prompt agreement checks."""

from XBrainLab.llm.agent.decision_contract import model_proposal_schema
from XBrainLab.llm.agent.parser import CommandParser, ToolEnvelopeStatus
from XBrainLab.llm.agent.prompt_policy import StrictToolResponsePromptPolicy


def test_prompt_examples_are_complete_parseable_proposals():
    text = StrictToolResponsePromptPolicy().decision_instructions()
    examples = [
        line.split(": ", 1)[1]
        for line in text.splitlines()
        if line.startswith("Example ")
    ]
    results = [CommandParser.parse_product(example) for example in examples]
    assert {result.decision for result in results} == {"reply", "clarify", "execute"}
    assert [result.status for result in results] == [
        ToolEnvelopeStatus.NO_TOOL,
        ToolEnvelopeStatus.NO_TOOL,
        ToolEnvelopeStatus.VALID,
        ToolEnvelopeStatus.VALID,
        ToolEnvelopeStatus.NO_TOOL,
        ToolEnvelopeStatus.NO_TOOL,
        ToolEnvelopeStatus.NO_TOOL,
    ]
    assert set(dict(results[2].request.changes)) == {"low_freq", "high_freq"}
    assert all(change.source_turn == "U1" for _, change in results[2].request.changes)
    assert dict(results[3].request.changes)["high_freq"].source_turn == "U2"
    assert results[4].request.mode == "continue"
    assert dict(results[4].request.changes)["low_freq"].value == 5
    assert results[5].request.mode == "cancel"
    assert results[5].decision == "reply"
    assert results[6].request.mode == "replace"
    assert results[6].request.changes == ()
    schema = model_proposal_schema()
    for result in results:
        payload = result.proposal_dict()
        assert set(payload) == set(schema["required"])
        assert payload["decision"] in schema["properties"]["decision"]["enum"]
        assert "request" not in payload
        assert payload["mode"] in schema["properties"]["mode"]["enum"]


def test_repair_and_normal_prompt_use_only_the_current_response_contract():
    policy = StrictToolResponsePromptPolicy()
    for text in (policy.decision_instructions(), policy.recovery_instructions()):
        for field in (
            "decision",
            "mode",
            "action",
            "changes",
            "message",
            "source_turn",
            "quote",
        ):
            assert field in text
        for retired in ("respond_to_user", "pending_action", "missing_inputs"):
            assert retired not in text
    assert policy.max_format_recovery_attempts == 1


def test_prompt_keeps_sources_request_lifecycle_and_backend_execution_separate():
    text = StrictToolResponsePromptPolicy().decision_instructions()
    for invariant in (
        "all omitted saved parameters",
        "mode=null, action=null, changes={}",
        "cancel",
        "never Assistant, backend or example text",
        "Zero-parameter GUI",
        "Host confirmation is separate",
        "trusted tool result",
        "Starting training is not training completion",
    ):
        assert invariant in text
    for answer_field in ("case_id", "expected_intent", "expected_tools"):
        assert answer_field not in text
