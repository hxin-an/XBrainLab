from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QObject

from XBrainLab.llm.agent.controller import LLMController


# Mock dependencies to avoid importing real backend/ui
class MockStudy(QObject):
    pass


# pytestmark = pytest.mark.skip(
#    reason=(
#        "Crashes in headless env with IOT instruction (Qt/Torch conflict). "
#        "Logic verified by eval_agent.py."
#    )
# )


@pytest.fixture
def controller(qtbot):
    # Patch AgentWorker to avoid importing real engine/backend
    with patch("XBrainLab.llm.agent.controller.AgentWorker"):
        # Patch AVAILABLE_TOOLS to avoid importing real tools if they have dependencies
        # (Though our mock tools are safe, it's good practice)
        # (Though our mock tools are safe, it's good practice)

        study = MockStudy()
        ctrl = LLMController(study)

        # Mock the worker instance created inside controller
        ctrl.worker = MagicMock()

        yield ctrl


def test_handle_user_input(controller):
    controller.handle_user_input("Hello Agent")

    assert len(controller.history) == 1
    assert controller.history[0]["role"] == "user"
    assert controller.history[0]["content"] == "Hello Agent"

    # Check if worker was signaled
    # Note: controller.sig_generate is connected to worker.generate_from_messages
    # We can't easily check signal emission without a slot, but we can
    # check if internal logic ran.
    # Since _generate_response calls sig_generate.emit, and we can't mock
    # the signal itself easily on the instance,
    # we can trust the logic flow or use qtbot.waitSignal if we really need to.


def test_tool_execution_loop(controller):
    """Test the ReAct loop: Tool Call -> Execution -> History Update -> Loop."""

    # 1. Simulate LLM response with tool call
    tool_json = """
    ```json
    {
        "command": "load_data",
        "parameters": {"paths": ["test.gdf"]}
    }
    ```
    """
    controller.current_response = tool_json

    # Mock _generate_response to verify loop and prevent infinite recursion
    controller._generate_response = MagicMock()

    # 2. Trigger finish
    controller._on_generation_finished()

    # 3. Verify
    # Tool execution should happen (synchronously now)
    last_msg = controller.history[-1]
    assert (
        last_msg["role"] == "user"
    )  # Tool output is treated as user role (observation)
    assert "Tool Output" in last_msg["content"]

    # Verify loop continued
    controller._generate_response.assert_called_once()


def test_sliding_window(controller, qtbot):
    # Add 20 messages
    for i in range(20):
        controller.history.append({"role": "user", "content": f"msg {i}"})

    # Call generate response
    controller._generate_response()

    # Process events to allow signal to reach the slot (if threaded)
    qtbot.wait(100)

    # Verify that worker.generate_from_messages was called with the correct window
    # The signal connects to worker.generate_from_messages
    assert controller.worker.generate_from_messages.called

    # Get the arguments passed to the worker
    args = controller.worker.generate_from_messages.call_args[0][
        0
    ]  # The 'messages' list

    # 1 System prompt + 10 recent history = 11 messages (logic: history[-10:])
    # Note: If sliding window implementation changed, we need to align.
    # Assuming logic is: system_prompt + history[-10:]

    assert len(args) == 11
    assert args[0]["role"] == "system"
    assert args[1]["content"] == "msg 10"  # Should start from index 10
    assert args[-1]["content"] == "msg 19"

def test_loop_detection(controller):
    """Test that repeated tool calls trigger a loop intervention."""
    controller._on_generation_finished = MagicMock() # Prevent real recursion
    controller._execute_tool_no_loop = MagicMock(return_value=(True, "Success"))

    cmd = "test_tool"
    params = {"p": 1}

    # 1. Simulate 2 allowed calls
    for _ in range(2):
        controller._recent_tool_calls.append((cmd, str(params)))
        assert not controller._detect_loop((cmd, str(params)))

    # 2. Add 3rd call -> Loop detected
    controller._recent_tool_calls.append((cmd, str(params)))
    assert controller._detect_loop((cmd, str(params)))

def test_json_retry(controller):
    """Test that invalid JSON triggers retry."""
    controller._generate_response = MagicMock()

    # 1. Invalid JSON
    controller.current_response = "```json {invalid syntax} ```"
    controller._on_generation_finished()

    # Should trigger retry
    assert controller._retry_count == 1
    assert "Invalid JSON" in controller.history[-1]["content"] # Error message to user
    controller._generate_response.assert_called()
