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
    cmd, params = CommandParser.parse(text)[0]
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
    cmd, params = CommandParser.parse(text_caps)[0]
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
    cmd2, params2 = CommandParser.parse(text_no_lang)[0]
    assert cmd2 == "test_cmd_2"
    assert params2 == {"x": 1}
