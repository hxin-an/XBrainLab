from XBrainLab.llm.agent.parser import CommandParser


def test_valid_json_command():
    text = """
    Sure, here is the command:
    ```json
    {
        "command": "load_data",
        "parameters": {"file_paths": ["/data/A.gdf"]}
    }
    ```
    """
    parsed = CommandParser.parse(text)
    assert parsed == [("load_data", {"file_paths": ["/data/A.gdf"]})]


def test_no_json_block():
    text = "Just a normal conversation response."
    result = CommandParser.parse(text)
    assert result is None


def test_malformed_json():
    text = """
    ```json
    { "command": "load_data", "parameters": { ... broken ...
    ```
    """
    result = CommandParser.parse(text)
    assert result is None


def test_parse_partial_tool_name_json_as_empty_parameters():
    text = """
    ```json
    {"tool_name": "preview_interpretation", "parameters": {"choices": {"task":
    ```
    """

    result = CommandParser.parse(text)

    assert result == [("preview_interpretation", {})]


def test_json_without_command_payload():
    text = '{"command": "test"}'
    result = CommandParser.parse(text)
    assert result is None


def test_parse_command_only_json_with_reason_as_empty_parameters():
    text = '{"command": "validate_interpretation", "reasons": []}'
    result = CommandParser.parse(text)
    assert result == [("validate_interpretation", {})]


def test_parse_command_only_json_with_decision_boundary_as_empty_parameters():
    text = (
        '{"command": "apply_interpretation", '
        '"requires_confirmation": false, "decision_boundary": "data_apply"}'
    )
    result = CommandParser.parse(text)
    assert result == [("apply_interpretation", {})]


def test_parse_none_tool_name_as_no_call():
    text = '{"tool_name": "none", "parameters": {}}'
    result = CommandParser.parse(text)
    assert result is None


def test_parse_bare_tool_name_at_start():
    result = CommandParser.parse("save_interpretation_recipe\nBlocked reasons: None.")
    assert result == [("save_interpretation_recipe", {})]


def test_does_not_parse_explanatory_sentence_starting_with_tool_name():
    result = CommandParser.parse("epoch_data is used to create time windows.")
    assert result is None


def test_parse_analysis_bare_tool_names():
    assert CommandParser.parse("evaluate\nBlocked reasons: None.") == [("evaluate", {})]
    assert CommandParser.parse("visualize\nBlocked reasons: None.") == [
        ("visualize", {})
    ]
    assert CommandParser.parse("saliency\nBlocked reasons: None.") == [("saliency", {})]


def test_parse_arguments_alias():
    text = '{"tool_name":"scan_source","arguments":{"source_path":"/data"}}'
    parsed = CommandParser.parse(text)
    assert parsed == [("scan_source", {"source_path": "/data"})]


def test_parse_tool_alias():
    text = '{"tool":"scan_source","parameters":{"source_path":"/data"}}'
    parsed = CommandParser.parse(text)
    assert parsed == [("scan_source", {"source_path": "/data"})]


def test_parse_tool_calls_list():
    text = """
    {
      "tool_calls": [
        {"tool_name": "scan_source", "arguments": {"source_path": "/data"}},
        {"tool_name": "preview_interpretation", "parameters": {}}
      ]
    }
    """
    result = CommandParser.parse(text)
    assert result == [
        ("scan_source", {"source_path": "/data"}),
        ("preview_interpretation", {}),
    ]


def test_parse_top_level_tool_call_array():
    text = '[{"tool_name":"get_dataset_info","parameters":{}}]'
    result = CommandParser.parse(text)
    assert result == [("get_dataset_info", {})]


def test_parse_openai_function_tool_call_shape():
    text = """
    {
      "tool_calls": [
        {
          "type": "function",
          "function": {
            "name": "scan_source",
            "arguments": "{\\"source_path\\":\\"/data/bids_mi\\",\\"source_hint\\":\\"bids\\"}"
          }
        }
      ]
    }
    """
    result = CommandParser.parse(text)
    assert result == [
        ("scan_source", {"source_path": "/data/bids_mi", "source_hint": "bids"})
    ]


def test_parse_relaxed_json_block():
    # Case 1: Uppercase JSON
    text_caps = """
    Here is the command:
    ```JSON
    {
        "command": "test_cmd",
        "parameters": {"k": "v"}
    }
    ```
    """
    parsed = CommandParser.parse(text_caps)
    assert parsed == [("test_cmd", {"k": "v"})]

    # Case 2: No language identifier
    text_no_lang = """
    ```
    {
        "command": "test_cmd_2",
        "parameters": {"x": 1}
    }
    ```
    """
    parsed2 = CommandParser.parse(text_no_lang)
    assert parsed2 == [("test_cmd_2", {"x": 1})]
