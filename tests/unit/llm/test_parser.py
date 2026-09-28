import json

import pytest

from XBrainLab.llm.agent.parser import CommandParser, ToolEnvelopeStatus


def proposal(
    decision="execute",
    *,
    action="apply_bandpass_filter",
    mode="new_request",
    changes=None,
    message=None,
):
    return {
        "decision": decision,
        "mode": mode,
        "action": action,
        "changes": changes if changes is not None else {},
        "message": message,
    }


def parse(value):
    return CommandParser.parse_product(json.dumps(value))


def test_partial_request_preserves_explicit_value_and_exact_source():
    result = parse(
        proposal(
            "clarify",
            changes={
                "low_freq": {
                    "value": 7,
                    "source_turn": "U1",
                    "quote": "a lower cutoff of 7 Hz",
                }
            },
            message="What upper cutoff should I use?",
        )
    )
    assert result.status is ToolEnvelopeStatus.NO_TOOL
    assert result.decision == "clarify"
    assert result.request.mode == "replace"
    assert result.request.action == "apply_bandpass_filter"
    change = dict(result.request.changes)["low_freq"]
    assert (change.value, change.source_turn, change.quote) == (
        7,
        "U1",
        "a lower cutoff of 7 Hz",
    )
    assert result.message == "What upper cutoff should I use?"


def test_continuation_exposes_only_new_values_without_inventing_old_values():
    result = parse(
        proposal(
            mode="update_pending",
            changes={
                "high_freq": {
                    "value": 30,
                    "source_turn": "U2",
                    "quote": "30 Hz.",
                }
            },
        )
    )
    assert result.status is ToolEnvelopeStatus.VALID
    assert result.decision == "execute"
    assert result.request.mode == "continue"
    assert tuple(dict(result.request.changes)) == ("high_freq",)
    assert result.message == ""


@pytest.mark.parametrize("decision", ["reply", "clarify"])
def test_answer_or_ambiguous_interruption_can_leave_pending_untouched(decision):
    result = parse(proposal(decision, mode=None, action=None, message="Which one?"))
    assert result.status is ToolEnvelopeStatus.NO_TOOL
    assert result.decision == decision
    assert result.request is None


def test_cancel_has_no_action_or_values():
    result = parse(
        proposal("reply", mode="cancel_pending", action=None, message="Cancelled.")
    )
    assert result.status is ToolEnvelopeStatus.NO_TOOL
    assert result.request.mode == "cancel"
    assert result.request.action is None
    assert result.request.changes == ()


def test_unresolved_operation_can_be_saved_without_unverified_values():
    result = parse(proposal("clarify", action=None, message="Which filter?"))
    assert result.status is ToolEnvelopeStatus.NO_TOOL
    assert result.request.action is None


def test_zero_parameter_action_keeps_empty_changes():
    result = parse(proposal(action="import_eeg_data"))
    assert result.status is ToolEnvelopeStatus.VALID
    assert result.request.changes == ()


@pytest.mark.parametrize("opening", ["```json\n", "```\n", "```json\r\n"])
def test_one_whole_response_json_fence_is_formatting_only(opening):
    body = json.dumps(proposal())
    raw = " \n" + opening + body + "\n```\n "
    assert CommandParser.parse_product(raw) == CommandParser.parse_product(body)
    assert raw == " \n" + opening + body + "\n```\n "


@pytest.mark.parametrize(
    "wrapper",
    [
        "Prose before.\n```json\n{body}\n```",
        "```json\n{body}\n```\nProse after.",
        "```json\n{body}\n```\n```json\n{body}\n```",
        "```json\n```json\n{body}\n```\n```",
        "```python\n{body}\n```",
        "```JSON\n{body}\n```",
        "```json extra\n{body}\n```",
        "````json\n{body}\n````",
        "```json{body}```",
        "~~~json\n{body}\n~~~",
        "```json\n{body}",
        "{body}\n```",
        "Before {body}",
        "{body} After",
    ],
)
def test_wrapper_cannot_hide_a_proposal(wrapper):
    result = CommandParser.parse_product(wrapper.format(body=json.dumps(proposal())))
    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.request is None


@pytest.mark.parametrize(
    "invalid",
    [
        {},
        [],
        None,
        "ordinary prose",
        5,
        {"tool_name": "resample_data", "parameters": {"rate": 128}},
        {"tool_name": "respond_to_user", "parameters": {"message": "Hello."}},
        {"tool_call": proposal()},
        {**proposal(), "backend_generation": 7},
        {**proposal(), "decision": "blocked"},
        {**proposal(), "decision": []},
        {**proposal(), "request": None},
        {**proposal(), "request": []},
        proposal(mode=None, action=None),
        proposal("reply", mode=None, message="Hello."),
        proposal(
            "clarify",
            mode=None,
            action=None,
            changes={"rate": {"value": 128, "source_turn": "U1", "quote": "128"}},
            message="Which one?",
        ),
        proposal(mode=[]),
        proposal(changes=[]),
        {**proposal(), "message": "Done."},
        proposal(action=None),
        proposal(action=""),
        proposal(action=" x "),
        proposal(action="x" * 129),
        proposal(action=5),
        proposal(mode="append"),
        proposal(mode="cancel_pending", action=None),
        proposal(
            "reply", mode="cancel_pending", action="resample_data", message="Cancelled."
        ),
        proposal("reply", action=None, message="Hello."),
        proposal("clarify", message=""),
        proposal("reply", message="   "),
        proposal("clarify", message=7),
        proposal(
            "clarify",
            action=None,
            changes={"rate": {"value": 128, "source_turn": "U1", "quote": "128"}},
            message="Which operation?",
        ),
        {key: value for key, value in proposal().items() if key != "changes"},
    ],
)
def test_invalid_contract_never_exposes_request(invalid):
    result = parse(invalid)
    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.request is None
    assert result.error


@pytest.mark.parametrize(
    "nested_request",
    [None, {"mode": "new_request", "action": "resample_data", "changes": {}}],
)
def test_retired_nested_proposal_has_no_compatibility_fallback(nested_request):
    result = parse(
        {"decision": "reply", "request": nested_request, "message": "An answer."}
    )
    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.request is None
    assert result.proposal_dict() is None


@pytest.mark.parametrize("old_mode", ["continue", "replace", "cancel"])
def test_old_flat_mode_names_are_rejected_without_aliases(old_mode):
    result = parse(
        proposal(
            "reply",
            mode=old_mode,
            action=None if old_mode == "cancel" else "resample_data",
            message="An answer.",
        )
    )
    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.request is None
    assert result.proposal_dict() is None


@pytest.mark.parametrize(
    "change",
    [
        128,
        [],
        {},
        {"value": 128},
        {"value": 128, "source_turn": "U1", "quote": "128", "extra": 1},
        {"value": 128, "source_turn": None, "quote": "128"},
        {"value": 128, "source_turn": " ", "quote": "128"},
        {"value": 128, "source_turn": "U" * 65, "quote": "128"},
        {"value": 128, "source_turn": "U1", "quote": None},
        {"value": 128, "source_turn": "U1", "quote": " "},
        {"value": 128, "source_turn": "U1", "quote": "a" * 4097},
    ],
)
def test_parameter_change_requires_bounded_source_reference(change):
    result = parse(proposal(changes={"rate": change}))
    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.request is None


@pytest.mark.parametrize("name", ["", " ", " rate", "x" * 129])
def test_invalid_parameter_name_cannot_be_normalized_into_a_supported_field(name):
    result = parse(
        proposal(
            changes={
                name: {
                    "value": 128,
                    "source_turn": "U1",
                    "quote": "128",
                }
            }
        )
    )
    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "ordinary prose",
        '{"decision":',
        '{"decision":"reply","decision":"execute","mode":null,"action":null,"changes":{},"message":"Hi"}',
        '{"decision":"execute","mode":"new_request","action":"resample_data",'
        '"changes":{"rate":{"value":128,"value":256,"source_turn":"U1","quote":"128"}},"message":null}',
    ],
)
def test_malformed_or_duplicate_json_fails_closed(raw):
    result = CommandParser.parse_product(raw)
    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.request is None


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e9999"])
def test_non_finite_numbers_are_rejected_at_any_depth(number):
    body = json.dumps(
        proposal(
            changes={
                "rate": {
                    "value": ["NUMBER"],
                    "source_turn": "U1",
                    "quote": "128",
                }
            }
        )
    ).replace('"NUMBER"', number)
    result = CommandParser.parse_product(body)
    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.request is None


@pytest.mark.parametrize("separator", ["", "\n"])
@pytest.mark.parametrize("fenced", [False, True])
def test_multiple_objects_never_expose_a_request(separator, fenced):
    body = json.dumps(proposal())
    raw = body + separator + body
    if fenced:
        raw = "```json\n" + raw + "\n```"
    result = CommandParser.parse_product(raw)
    assert result.status is ToolEnvelopeStatus.MULTIPLE_OBJECTS
    assert result.request is None


def test_null_parameter_value_is_preserved_for_schema_validation_not_deletion():
    result = parse(
        proposal(
            changes={
                "rate": {
                    "value": None,
                    "source_turn": "U1",
                    "quote": "clear rate",
                }
            }
        )
    )
    assert result.status is ToolEnvelopeStatus.VALID
    assert dict(result.request.changes)["rate"].value is None


@pytest.mark.parametrize(
    "value",
    [
        proposal(),
        proposal(
            "clarify",
            changes={
                "low_freq": {
                    "value": 7,
                    "source_turn": "U1",
                    "quote": " 7 Hz ",
                }
            },
            message="What upper cutoff?",
        ),
        proposal("reply", mode=None, action=None, message="An answer."),
        proposal(mode="update_pending"),
        proposal("reply", mode="cancel_pending", action=None, message="Cancelled."),
    ],
)
def test_valid_proposal_serialization_preserves_semantics_and_source_quotes(value):
    result = parse(value)
    assert result.proposal_dict() == value
    assert parse(result.proposal_dict()) == result


def test_invalid_proposal_cannot_be_serialized_for_a_consumer():
    assert parse({"decision": "execute"}).proposal_dict() is None
