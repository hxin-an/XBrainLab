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
    assert parsed is not None
    cmd, params = parsed[0]
    assert cmd == "load_data"
    assert params == {"file_paths": ["/data/A.gdf"]}


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


def test_json_without_markdown():
    # Some models might output raw JSON without markdown code blocks
    # By upgrading the parser, we now support finding JSON anywhere!
    # But since parameters are missing in this example, it should still return None?
    # Or should we update the test to be a valid raw command?
    # Original test expected None. Let's keep it assuming params missing.
    text = '{"command": "test"}'
    result = CommandParser.parse(text)
    assert result is None


def test_parse_arguments_alias():
    text = '{"tool_name":"scan_source","arguments":{"source_path":"/data"}}'
    parsed = CommandParser.parse(text)
    assert parsed is not None
    cmd, params = parsed[0]
    assert cmd == "scan_source"
    assert params == {"source_path": "/data"}


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
    assert parsed is not None
    cmd, params = parsed[0]
    assert cmd == "test_cmd"
    assert params == {"k": "v"}

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
    assert parsed2 is not None
    cmd2, params2 = parsed2[0]
    assert cmd2 == "test_cmd_2"
    assert params2 == {"x": 1}
