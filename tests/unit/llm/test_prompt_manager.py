import pytest

from XBrainLab.llm.agent.prompt_manager import PromptManager


# Mock Tool
class MockTool:
    def __init__(self, name, description, parameters):
        self.name = name
        self.description = description
        self.parameters = parameters


@pytest.fixture
def mock_tools():
    return [
        MockTool("tool1", "Description 1", {"param": "str"}),
        MockTool("tool2", "Description 2", {"p2": "int"}),
    ]


@pytest.fixture
def manager(mock_tools):
    return PromptManager(mock_tools)


def test_system_prompt_structure(manager):
    """Test if system prompt contains tool definitions."""
    msg = manager.get_system_message()
    assert "You are XBrainLab Assistant" in msg
    assert "Available Tools:" in msg
    assert "tool1" in msg
    assert "Description 1" in msg
    # Verify JSON format instruction
    assert "MUST output a JSON object" in msg


def test_add_context(manager):
    """Test adding dynamic context."""
    manager.add_context("User prefers dark mode.")
    msg = manager.get_system_message()
    assert "Additional Context:" in msg
    assert "User prefers dark mode." in msg

    # Test clearing
    manager.clear_context()
    msg = manager.get_system_message()
    assert "Additional Context:" not in msg


def test_sliding_window(manager):
    """Test history sliding window (keep last 10)."""
    history = [{"role": "user", "content": f"msg {i}"} for i in range(15)]

    messages = manager.get_messages(history)

    # 1 system + 10 history = 11
    assert len(messages) == 11
    assert messages[0]["role"] == "system"

    # Check if we kept the *last* 10
    # The first history message in result should be "msg 5" (0-4 dropped)
    assert messages[1]["content"] == "msg 5"
    assert messages[-1]["content"] == "msg 14"


def test_empty_history(manager):
    messages = manager.get_messages([])
    assert len(messages) == 1
    assert messages[0]["role"] == "system"
