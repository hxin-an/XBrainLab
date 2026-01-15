
import pytest
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
    cmd, params = CommandParser.parse(text)
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
    # The current parser expects markdown, so this might fail or return None depending on implementation.
    # If we want to support raw JSON, we'd need to update the parser. 
    # For now, let's assume strict markdown requirement.
    text = '{"command": "test"}'
    result = CommandParser.parse(text)
    assert result is None
