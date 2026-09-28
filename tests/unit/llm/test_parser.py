import json

import pytest

from XBrainLab.llm.agent.parser import CommandParser, ToolEnvelopeStatus


def proposal(tool_name="apply_bandpass_filter", parameters=None):
    return {
        "tool_name": tool_name,
        "parameters": parameters if parameters is not None else {},
    }


def parse(value):
    return CommandParser.parse_product(json.dumps(value))


def test_complete_single_action_exposes_unmodified_parameters():
    value = proposal(parameters={"low_freq": 7, "high_freq": 30})
    result = parse(value)
    assert result.status is ToolEnvelopeStatus.VALID
    assert result.command == ("apply_bandpass_filter", {"low_freq": 7, "high_freq": 30})
    assert result.message == ""
    assert result.decision == "execute"
    assert result.proposal_dict() == value


def test_missing_values_response_has_no_command_or_retained_draft():
    value = proposal(
        "respond_to_user",
        {"message": "Please restate the complete bandpass request with both cutoffs."},
    )
    result = parse(value)
    assert result.status is ToolEnvelopeStatus.NO_TOOL
    assert result.command is None
    assert result.message == value["parameters"]["message"]
    assert result.decision == "reply"
    assert result.proposal_dict() == value
    assert not hasattr(result, "request")


def test_zero_parameter_gui_action_is_valid():
    assert parse(proposal("import_eeg_data")).command == ("import_eeg_data", {})


@pytest.mark.parametrize(
    "value",
    [
        {
            "decision": "execute",
            "mode": "new_request",
            "action": "resample_data",
            "changes": {},
            "message": None,
        },
        {"decision": "reply", "request": None, "message": "Hello."},
    ],
)
def test_retired_proposal_formats_have_no_compatibility_fallback(value):
    result = parse(value)
    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.command is None
    assert result.proposal_dict() is None


@pytest.mark.parametrize(
    "invalid",
    [
        {},
        [],
        None,
        "ordinary prose",
        5,
        {"tool_call": proposal()},
        {**proposal(), "message": "Done."},
        {"tool_name": "resample_data"},
        {"parameters": {}},
        proposal(""),
        proposal(" "),
        proposal(" x "),
        proposal("x" * 129),
        proposal(5),
        proposal([]),
        {"tool_name": "resample_data", "parameters": None},
        {"tool_name": "resample_data", "parameters": []},
        proposal("respond_to_user"),
        proposal("respond_to_user", {"message": ""}),
        proposal("respond_to_user", {"message": "  "}),
        proposal("respond_to_user", {"message": 5}),
        proposal("respond_to_user", {"message": "Hello.", "rate": 128}),
    ],
)
def test_invalid_contract_never_exposes_command(invalid):
    result = parse(invalid)
    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.command is None
    assert result.proposal_dict() is None
    assert result.error


@pytest.mark.parametrize("opening", ["```json\n", "```\n", "```json\r\n"])
def test_one_whole_response_json_fence_is_formatting_only(opening):
    body = json.dumps(proposal())
    raw = " \n" + opening + body + "\n```\n "
    assert CommandParser.parse_product(raw) == CommandParser.parse_product(body)


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
def test_wrapper_cannot_hide_a_command(wrapper):
    result = CommandParser.parse_product(wrapper.format(body=json.dumps(proposal())))
    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.command is None


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "ordinary prose",
        '{"tool_name":',
        '{"tool_name":"respond_to_user","tool_name":"resample_data","parameters":{}}',
        '{"tool_name":"resample_data","parameters":{"rate":128,"rate":256}}',
    ],
)
def test_malformed_or_duplicate_json_fails_closed(raw):
    result = CommandParser.parse_product(raw)
    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.command is None


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e9999"])
def test_non_finite_numbers_are_rejected_at_any_depth(number):
    body = json.dumps(proposal(parameters={"nested": ["NUMBER"]})).replace(
        '"NUMBER"', number
    )
    result = CommandParser.parse_product(body)
    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.command is None


@pytest.mark.parametrize("separator", ["", "\n"])
@pytest.mark.parametrize("fenced", [False, True])
def test_multiple_objects_never_expose_a_command(separator, fenced):
    body = json.dumps(proposal())
    raw = body + separator + body
    if fenced:
        raw = "```json\n" + raw + "\n```"
    result = CommandParser.parse_product(raw)
    assert result.status is ToolEnvelopeStatus.MULTIPLE_OBJECTS
    assert result.command is None


@pytest.mark.parametrize(
    "parameters", [{"rate": None}, {"rate": "invalid"}, {"unknown": 3}, {"": 2}]
)
def test_tool_parameter_schema_validation_is_not_parser_authority(parameters):
    result = parse(proposal("resample_data", parameters))
    assert result.status is ToolEnvelopeStatus.VALID
    assert result.command == ("resample_data", parameters)


@pytest.mark.parametrize(
    "value",
    [
        proposal(),
        proposal(parameters={"low_freq": 7, "high_freq": 30}),
        proposal("respond_to_user", {"message": "An answer."}),
    ],
)
def test_successful_serialization_roundtrips(value):
    result = parse(value)
    assert result.proposal_dict() == value
    assert parse(result.proposal_dict()) == result
