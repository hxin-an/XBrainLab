import pytest

from XBrainLab.llm.agent.parser import CommandParser, ToolEnvelopeStatus


def test_product_parser_accepts_one_complete_strict_envelope():
    text = (
        '  {"workflow_stage":"empty","tool_name":"load_data",'
        '"parameters":{"file_paths":["/data/A.gdf"]}}\n'
    )

    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.VALID
    assert result.workflow_stage == "empty"
    assert result.commands == (("load_data", {"file_paths": ["/data/A.gdf"]}),)
    assert result.error == ""
    assert CommandParser.parse(text) == [("load_data", {"file_paths": ["/data/A.gdf"]})]


def test_product_parser_rejects_the_retired_two_field_root():
    result = CommandParser.parse_product(
        '{"tool_name":"scan_source","parameters":{"source_path":"/data/A.gdf"}}'
    )

    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert "workflow_stage" in result.error


def test_product_parser_accepts_message_only_response_contract():
    result = CommandParser.parse_product(
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"Load EEG data before training."}}'
    )

    assert result.status is ToolEnvelopeStatus.NO_TOOL
    assert result.workflow_stage == "data_loaded"
    assert result.message == "Load EEG data before training."
    assert result.decision is None
    assert result.missing_inputs == ()


def test_product_parser_accepts_typed_direct_clarification_response_contract():
    result = CommandParser.parse_product(
        '{"workflow_stage":"data_loaded","tool_name":"respond_to_user",'
        '"parameters":{"message":"What cutoffs should I use?",'
        '"pending_action":"apply_bandpass_filter",'
        '"missing_inputs":["low_freq","high_freq"]}}'
    )

    assert result.status is ToolEnvelopeStatus.NO_TOOL
    assert result.pending_action == "apply_bandpass_filter"
    assert result.missing_inputs == ("low_freq", "high_freq")


def test_product_parser_rejects_retired_response_decision_fields():
    result = CommandParser.parse_product(
        '{"workflow_stage":"empty","tool_name":"respond_to_user",'
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
    assert "exactly workflow_stage, tool_name, and parameters" in result.error
    assert CommandParser.parse(text) is None


def test_product_parser_rejects_wrapped_respond_to_user_envelope():
    text = (
        '{"tool_call":{"tool_name":"respond_to_user","parameters":{'
        '"decision":"missing_input","missing_inputs":["source_path"],'
        '"message":"Please provide the EEG source path."}}}'
    )

    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.commands == ()
    assert result.decision is None
    assert result.missing_inputs == ()


def test_product_parser_rejects_plain_text_at_strict_action_boundary():
    result = CommandParser.parse_product("Just a normal conversation response.")

    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.commands == ()
    assert "JSON object" in result.error
    assert CommandParser.parse("Just a normal conversation response.") is None


def test_product_parser_preserves_model_owned_blocked_message():
    text = (
        '{"workflow_stage":"empty","tool_name":"respond_to_user","parameters":{'
        '"message":"Load EEG data before training."}}'
    )

    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.NO_TOOL
    assert result.commands == ()
    assert result.workflow_stage == "empty"
    assert result.decision is None
    assert result.intent == "no_tool"
    assert result.missing_inputs == ()
    assert result.message == "Load EEG data before training."


def test_product_parser_preserves_model_owned_clarification_message():
    text = (
        '{"workflow_stage":"empty","tool_name":"respond_to_user","parameters":{'
        '"message":"Please provide the EEG source path."}}'
    )

    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.NO_TOOL
    assert result.commands == ()
    assert result.workflow_stage == "empty"
    assert result.decision is None
    assert result.intent == "no_tool"
    assert result.missing_inputs == ()
    assert result.message == "Please provide the EEG source path."


def test_product_parser_preserves_model_owned_answer_message():
    text = (
        '{"workflow_stage":"preprocessed","tool_name":"respond_to_user",'
        '"parameters":{'
        '"message":"An epoch is a window around an event."}}'
    )

    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.NO_TOOL
    assert result.commands == ()
    assert result.workflow_stage == "preprocessed"
    assert result.decision is None
    assert result.intent == "no_tool"
    assert result.missing_inputs == ()
    assert result.message == "An epoch is a window around an event."


def test_product_parser_keeps_direct_tool_decision_compact():
    text = (
        '{"workflow_stage":"empty","tool_name":"scan_source",'
        '"parameters":{"source_path":"/data/A.gdf"}}'
    )

    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.VALID
    assert result.commands == (("scan_source", {"source_path": "/data/A.gdf"}),)
    assert result.decision == "tool"
    assert result.intent == ""
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
            'Sure, here is the command:\n{"tool_name":"load_data","parameters":{}}',
            "entire response",
        ),
        (
            '```json\n{"tool_name":"load_data","parameters":{}}\n```',
            "entire response",
        ),
        ("load_data\nBlocked reasons: None.", "JSON object"),
        (
            '{"tool_name":"preview_interpretation","parameters":{"choices":',
            "complete JSON",
        ),
        (
            '[{"tool_name":"get_dataset_info","parameters":{}}]',
            "top-level object",
        ),
        (
            '{"tool_name":"query_state","parameters":{}}'
            '{"tool_name":"query_state","parameters":{}}',
            "complete JSON",
        ),
        (
            '{"command":"load_data","parameters":{}}',
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
            '{"workflow_stage":"empty","tool_name":"none","parameters":{}}',
            "normal text",
        ),
    ],
)
def test_product_parser_rejects_non_contract_tool_outputs(text, error_fragment):
    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.commands == ()
    assert error_fragment in result.error
    assert CommandParser.parse(text) is None


@pytest.mark.parametrize(
    "text",
    [
        '{"tool_name":"load_data"}',
        '{"tool_name":"","parameters":{}}',
        '{"tool_name":42,"parameters":{}}',
        '{"tool_name":"load_data","parameters":null}',
        '{"tool_name":"load_data","parameters":"{}"}',
    ],
)
def test_product_parser_rejects_invalid_envelope_field_types(text):
    result = CommandParser.parse_product(text)

    assert result.status is ToolEnvelopeStatus.FORMAT_ERROR
    assert result.commands == ()
    assert result.error


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
    assert CommandParser.parse(text) is None


def test_diagnostic_parser_is_explicitly_tolerant_for_legacy_artifacts():
    text = (
        "Legacy model output:\n```json\n"
        '{"command":"load_data","arguments":{"file_paths":["/data/A.gdf"]}}'
        "\n```"
    )

    assert CommandParser.parse_diagnostic(text) == [
        ("load_data", {"file_paths": ["/data/A.gdf"]})
    ]


def test_diagnostic_parser_never_changes_product_parser_result():
    text = "evaluate\nBlocked reasons: None."

    assert CommandParser.parse_diagnostic(text) == [("evaluate", {})]
    assert CommandParser.parse_product(text).status is ToolEnvelopeStatus.FORMAT_ERROR
    assert CommandParser.parse(text) is None
