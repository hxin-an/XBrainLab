
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import QThread
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.tools import AVAILABLE_TOOLS

# Mock Study object
class MockStudy:
    def __init__(self):
        self.loaded_data = []

    def load_raw_data_list(self, paths):
        self.loaded_data.extend(paths)

@pytest.fixture
def controller(qtbot):
    study = MockStudy()
    # Mock the worker to avoid actual LLM loading
    with patch('XBrainLab.llm.agent.controller.AgentWorker') as MockWorker:
        ctrl = LLMController(study)
        qtbot.addWidget(ctrl) # Register with qtbot if it was a widget, but it's QObject. 
                              # For QObject, we don't strictly need addWidget but it helps cleanup.
        yield ctrl

def test_tool_execution_flow(controller):
    """
    Test that the controller correctly parses a tool command and executes the mock tool.
    """
    # 1. Simulate LLM response containing a tool call
    tool_call_json = '''
    Thinking process...
    ```json
    {
        "command": "load_data",
        "parameters": {
            "file_paths": ["/data/test.gdf"]
        }
    }
    ```
    '''
    
    # We manually trigger the finished logic as if the worker sent this text
    controller.current_response = tool_call_json
    
    # Mock the _generate_response to prevent infinite loop (since tool execution triggers generation again)
    controller._generate_response = MagicMock()
    
    # 2. Trigger the finish handler
    controller._on_generation_finished()
    
    # 3. Verify tool execution
    # The tool execution happens via QTimer or direct call. 
    # Since we removed QTimer, it should be immediate.
    
    # Check if history updated with tool output
    last_msg = controller.history[-1]
    assert last_msg['role'] == 'user'
    assert "Tool Output" in last_msg['content']
    assert "Successfully loaded 1 files" in last_msg['content']
    
    # Check if the loop continued
    controller._generate_response.assert_called_once()

def test_unknown_tool(controller):
    """Test handling of unknown tools."""
    tool_call_json = '''
    ```json
    {
        "command": "non_existent_tool",
        "parameters": {}
    }
    ```
    '''
    controller.current_response = tool_call_json
    controller._generate_response = MagicMock()
    controller._on_generation_finished()
    
    last_msg = controller.history[-1]
    assert "Unknown tool" in last_msg['content']
    controller._generate_response.assert_called_once()

def test_malformed_json(controller):
    """Test handling of invalid JSON."""
    tool_call_json = '''
    ```json
    {
        "command": "load_data",
        "parameters": { ... broken json ...
    ```
    '''
    controller.current_response = tool_call_json
    controller._generate_response = MagicMock()
    
    # Since parser returns None for broken JSON, it should be treated as text response
    # We need to mock the signal to verify
    with patch.object(controller.response_ready, 'emit') as mock_emit:
        controller._on_generation_finished()
        mock_emit.assert_called_once()
        # It should just output the raw text
