import pytest

from XBrainLab.llm.agent.parser import CommandParser, ToolEnvelopeStatus


def test_product_parser_accepts_two_fields_without_model_stage_echo():
    result = CommandParser.parse_product(
        '{"tool_name":"resample_data","parameters":{"sampling_rate":128}}'
    )
    assert result.status is ToolEnvelopeStatus.VALID
    assert result.commands == (("resample_data", {"sampling_rate": 128}),)


def test_product_parser_rejects_old_stage_echo_as_extra_field():
    result = CommandParser.parse_product(
        '{"workflow_stage":"data_loaded","tool_name":"resample_data",'
        '"parameters":{"sampling_rate":128}}'
    )
    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.commands == ()


def test_product_parser_accepts_one_complete_strict_envelope():
    text = (
        '  {"tool_name":"import_eeg_data",'
        '"parameters":{"file_paths":["/data/A.gdf"]}}\n'
    )

    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.VALID
    assert result.commands == (("import_eeg_data", {"file_paths": ["/data/A.gdf"]}),)
    assert result.error == ""


@pytest.mark.parametrize("opening", ["```json\n", "```\n", "```json\r\n"])
def test_product_parser_accepts_only_one_whole_response_json_fence(opening):
    envelope = '{"tool_name":"resample_data","parameters":{"sampling_rate":128}}'
    raw = " \n" + opening + envelope + "\n```\n "

    result = CommandParser.parse_product(raw)

    assert result == CommandParser.parse_product(envelope)
    assert result.status is ToolEnvelopeStatus.VALID
    assert result.commands == (("resample_data", {"sampling_rate": 128}),)
    assert raw == " \n" + opening + envelope + "\n```\n "


def test_product_parser_preserves_fenced_response_message_and_embedded_backticks():
    envelope = (
        '{"tool_name":"respond_to_user",'
        '"parameters":{"message":"The literal marker ``` is data."}}'
    )
    result = CommandParser.parse_product("```json\n" + envelope + "\n```")
    assert result.status is ToolEnvelopeStatus.NO_TOOL
    assert result.message == "The literal marker ``` is data."


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
    ],
)
def test_product_parser_rejects_non_whole_or_non_json_fences(wrapper):
    body = '{"tool_name":"resample_data","parameters":{"sampling_rate":128}}'
    result = CommandParser.parse_product(wrapper.format(body=body))
    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.commands == ()


@pytest.mark.parametrize(
    "body,error_fragment",
    [
        ('{"tool_name":"resample_data"}', "exactly"),
        (
            '{"tool_name":"resample_data","parameters":{},"extra":true}',
            "exactly",
        ),
        (
            '{"tool_name":"resample_data","tool_name":"reset_preprocessing","parameters":{}}',
            "duplicate",
        ),
        (
            '{"tool_name":"resample_data","parameters":{"sampling_rate":128,"sampling_rate":256}}',
            "duplicate",
        ),
        (
            '{"tool_name":"resample_data","parameters":{"sampling_rate":NaN}}',
            "non-standard",
        ),
        (
            '{"tool_name":"resample_data","parameters":{"sampling_rate":Infinity}}',
            "non-standard",
        ),
        (
            '{"tool_name":"resample_data","parameters":{"sampling_rate":-Infinity}}',
            "non-standard",
        ),
        (
            '[{"tool_name":"resample_data","parameters":{}}]',
            "top-level object",
        ),
        (
            '{"workflow_stage":"invented","tool_name":"resample_data","parameters":{}}',
            "exactly",
        ),
        (
            '{"tool_name":"resample_data","parameters":',
            "complete JSON",
        ),
    ],
)
def test_fence_normalization_preserves_strict_envelope_validation(body, error_fragment):
    result = CommandParser.parse_product("```json\n" + body + "\n```")
    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.commands == ()
    assert error_fragment in result.error


def test_fenced_multiple_objects_remain_non_executable():
    body = '{"tool_name":"resample_data","parameters":{"sampling_rate":128}}'
    result = CommandParser.parse_product("```json\n" + body + "\n" + body + "\n```")
    assert result.status is ToolEnvelopeStatus.MULTIPLE_OBJECTS
    assert result.commands == ()


@pytest.mark.parametrize("separator", ["", "\n"])
def test_product_parser_classifies_adjacent_complete_objects_without_commands(
    separator,
):
    result = CommandParser.parse_product(
        '{"tool_name":"resample_data",'
        '"parameters":{"rate":128}}' + separator + '{"tool_name":"apply_notch_filter",'
        '"parameters":{"freq":50}}'
    )

    assert result.status is ToolEnvelopeStatus.MULTIPLE_OBJECTS
    assert result.commands == ()


def test_product_parser_keeps_top_level_arrays_on_the_general_format_error_path():
    result = CommandParser.parse_product(
        '[{"tool_name":"resample_data","parameters":{"rate":128}}]'
    )

    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR


def test_product_parser_rejects_backend_context_in_model_output():
    result = CommandParser.parse_product(
        '{"backend_generation":42,"tool_name":"import_eeg_data","parameters":{}}'
    )

    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert "exactly" in result.error


def test_product_parser_accepts_message_only_response_contract():
    result = CommandParser.parse_product(
        '{"tool_name":"respond_to_user",'
        '"parameters":{"message":"Load EEG data before training."}}'
    )

    assert result.status is ToolEnvelopeStatus.NO_TOOL
    assert result.message == "Load EEG data before training."
    assert result.missing_inputs == ()


def test_product_parser_accepts_typed_direct_clarification_response_contract():
    result = CommandParser.parse_product(
        '{"tool_name":"respond_to_user",'
        '"parameters":{"message":"What cutoffs should I use?",'
        '"pending_action":"apply_bandpass_filter",'
        '"missing_inputs":["low_freq","high_freq"]}}'
    )

    assert result.status is ToolEnvelopeStatus.NO_TOOL
    assert result.pending_action == "apply_bandpass_filter"
    assert result.missing_inputs == ("low_freq", "high_freq")


def test_product_parser_rejects_retired_response_decision_fields():
    result = CommandParser.parse_product(
        '{"tool_name":"respond_to_user",'
        '"parameters":{"decision":"blocked","message":"Blocked."}}'
    )

    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert "message" in result.error


def test_product_parser_rejects_tool_call_wrapper_even_when_inner_shape_is_valid():
    text = (
        '{"tool_call":{"tool_name":"scan_source","parameters":'
        '{"source_path":"/data/A.gdf","label_sources":[]}}}'
    )

    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.commands == ()
    assert "exactly tool_name and parameters" in result.error


def test_product_parser_rejects_wrapped_respond_to_user_envelope():
    text = (
        '{"tool_call":{"tool_name":"respond_to_user","parameters":{'
        '"decision":"missing_input","missing_inputs":["source_path"],'
        '"message":"Please provide the EEG source path."}}}'
    )

    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.commands == ()
    assert result.missing_inputs == ()


def test_product_parser_rejects_plain_text_at_strict_action_boundary():
    result = CommandParser.parse_product("Just a normal conversation response.")

    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.commands == ()
    assert "JSON object" in result.error


def test_product_parser_preserves_model_owned_blocked_message():
    text = (
        '{"tool_name":"respond_to_user","parameters":{'
        '"message":"Load EEG data before training."}}'
    )

    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.NO_TOOL
    assert result.commands == ()
    assert result.missing_inputs == ()
    assert result.message == "Load EEG data before training."


def test_product_parser_preserves_model_owned_clarification_message():
    text = (
        '{"tool_name":"respond_to_user","parameters":{'
        '"message":"Please provide the EEG source path."}}'
    )

    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.NO_TOOL
    assert result.commands == ()
    assert result.missing_inputs == ()
    assert result.message == "Please provide the EEG source path."


def test_product_parser_preserves_model_owned_answer_message():
    text = (
        '{"tool_name":"respond_to_user",'
        '"parameters":{'
        '"message":"An epoch is a window around an event."}}'
    )

    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.NO_TOOL
    assert result.commands == ()
    assert result.missing_inputs == ()
    assert result.message == "An epoch is a window around an event."


def test_product_parser_keeps_direct_tool_decision_compact():
    text = '{"tool_name":"scan_source","parameters":{"source_path":"/data/A.gdf"}}'

    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.VALID
    assert result.commands == (("scan_source", {"source_path": "/data/A.gdf"}),)
    assert result.missing_inputs == ()
    assert result.message == ""


@pytest.mark.parametrize(
    "text",
    [
        (
            '{"tool_name":"respond_to_user","parameters":{'
            '"decision":"blocked","missing_inputs":[],'
            '"message":"Blocked."}}'
        ),
        (
            '{"tool_name":"respond_to_user","parameters":{'
            '"decision":"answer","missing_inputs":[],'
            '"message":"An epoch is a window around an event."}}'
        ),
        (
            '{"tool_name":"respond_to_user","parameters":{'
            '"decision":"missing_input",'
            '"message":"Please provide the path."}}'
        ),
        (
            '{"tool_name":"respond_to_user","parameters":{'
            '"decision":"missing_input","missing_inputs":[],'
            '"message":"Please provide the path."}}'
        ),
        (
            '{"tool_name":"respond_to_user","parameters":{'
            '"decision":"BLOCKED",'
            '"message":"Blocked."}}'
        ),
    ],
)
def test_product_parser_rejects_contradictory_structured_decisions(text):
    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.commands == ()
    assert result.error


def test_product_parser_rejects_abandoned_top_level_decision_shape():
    result = CommandParser.parse_product(
        '{"decision":"blocked","intent":"train","message":"Blocked."}'
    )

    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR


def test_product_parser_rejects_parameter_explanation_at_action_boundary():
    text = "These parameters: batch size and epochs can be adjusted in settings."

    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.commands == ()


@pytest.mark.parametrize(
    ("text", "error_fragment"),
    [
        (
            'Sure, here is the command:\n{"tool_name":"import_eeg_data","parameters":{}}',
            "entire response",
        ),
        (
            '```json\n{"tool_name":"import_eeg_data"}\n```',
            "exactly",
        ),
        ("import_eeg_data\nBlocked reasons: None.", "JSON object"),
        (
            '{"tool_name":"preview_interpretation","parameters":{"choices":',
            "complete JSON",
        ),
        (
            '[{"tool_name":"get_dataset_info","parameters":{}}]',
            "top-level object",
        ),
        (
            '{"command":"import_eeg_data","parameters":{}}',
            "exactly",
        ),
        (
            '{"tool_name":"scan_source","arguments":{"source_path":"/data"}}',
            "exactly",
        ),
        (
            '{"tool_name":"scan_source","parameters":{},"confidence":0.9}',
            "exactly",
        ),
        (
            '{"tool_calls":[{"tool_name":"query_state","parameters":{}}]}',
            "exactly",
        ),
        (
            '{"tool_name":"query_state","parameters":[],"parameters":{}}',
            "duplicate",
        ),
        (
            '{"tool_name":"query_state","parameters":{"value":NaN}}',
            "non-standard",
        ),
        (
            '{"tool_name":"none","parameters":{}}',
            "normal text",
        ),
        ("evaluate\nBlocked reasons: None.", "entire response"),
    ],
)
def test_product_parser_rejects_non_contract_tool_outputs(text, error_fragment):
    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.commands == ()
    assert error_fragment in result.error


@pytest.mark.parametrize(
    ("text", "error_fragment"),
    [
        (
            '{"workflow_stage":false,"tool_name":"import_eeg_data","parameters":{}}',
            "An assistant action must be exactly tool_name and parameters.",
        ),
        (
            '{"tool_name":"","parameters":{}}',
            "tool_name must be a non-empty string.",
        ),
        (
            '{"tool_name":42,"parameters":{}}',
            "tool_name must be a non-empty string.",
        ),
        (
            '{"tool_name":"import_eeg_data","parameters":null}',
            "parameters must be a JSON object.",
        ),
        (
            '{"tool_name":"import_eeg_data","parameters":"{}"}',
            "parameters must be a JSON object.",
        ),
    ],
)
def test_product_parser_rejects_invalid_envelope_field_types(text, error_fragment):
    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.commands == ()
    assert result.error == error_fragment


@pytest.mark.parametrize(
    "text",
    [
        ('Sure: {"tool_call":{"tool_name":"query_state","parameters":{}}}'),
        ('```json\n{"tool_call":{"tool_name":"query_state","parameters":{}}}\n```'),
        '[{"tool_call":{"tool_name":"query_state","parameters":{}}}]',
        (
            '{"tool_call":{"tool_name":"query_state","parameters":{}}}'
            '{"tool_call":{"tool_name":"query_state","parameters":{}}}'
        ),
        ('{"tool_call":{"tool_name":"query_state","parameters":{}},"extra":true}'),
        (
            '{"tool_call":{"tool_name":"query_state","parameters":{}},'
            '"tool_call":{"tool_name":"query_state","parameters":{}}}'
        ),
        (
            '{"tool_call":{"tool_name":"query_state","tool_name":"evaluate",'
            '"parameters":{}}}'
        ),
        ('{"tool_call":{"tool_name":"query_state","parameters":{},"parameters":{}}}'),
        ('{"tool_call":{"tool_name":"query_state","parameters":{},"confidence":0.9}}'),
        '{"tool_call":{"name":"query_state","arguments":{}}}',
        ('{"tool_call":{"tool_call":{"tool_name":"query_state","parameters":{}}}}'),
        '{"tool_call":[{"tool_name":"query_state","parameters":{}}]}',
        '{"tool_call":null}',
        '{"tool_call":"query_state"}',
        '{"tool_call":{"tool_name":42,"parameters":{}}}',
        '{"tool_call":{"tool_name":"query_state","parameters":[]}}',
        '{"tool_call":{"tool_name":"none","parameters":{}}}',
        '{"tool_call":{"tool_name":"query_state","parameters":{"value":NaN}}}',
    ],
)
def test_product_parser_rejects_non_contract_tool_call_wrappers(text):
    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.commands == ()
    assert result.error
