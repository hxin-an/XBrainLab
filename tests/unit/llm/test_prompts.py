
import pytest
import json
from XBrainLab.llm.agent.prompts import get_system_prompt
from XBrainLab.llm.tools.base import BaseTool

class MockTool(BaseTool):
    @property
    def name(self): return "mock_tool"
    @property
    def description(self): return "A mock tool."
    @property
    def parameters(self): return {"type": "object"}
    def execute(self, study, **kwargs): return "Executed"

def test_prompt_structure():
    tools = [MockTool()]
    prompt = get_system_prompt(tools)
    
    assert "You are XBrainLab Assistant" in prompt
    assert "Available Tools:" in prompt
    assert "mock_tool" in prompt
    assert "A mock tool." in prompt

def test_tool_schema_formatting():
    tools = [MockTool()]
    prompt = get_system_prompt(tools)
    
    # Check if JSON schema is present
    assert '"name": "mock_tool"' in prompt
    assert '"type": "object"' in prompt
