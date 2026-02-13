from unittest.mock import MagicMock, patch

from XBrainLab.llm.agent.controller import LLMController

# Mock QApp fixture implies pytest-qt is installed
# If not, we can rely on standard unit test logic for non-UI parts,
# but LLMController inherits QObject, so we need QApplication.
# Assuming `qapp` fixture is available from conftest.py or pytest-qt.


def test_controller_initialization(qapp):
    mock_study = MagicMock()

    with patch("XBrainLab.llm.agent.controller.AgentWorker"):
        controller = LLMController(mock_study)

        assert controller.registry is not None
        assert controller.assembler is not None
        assert controller.verifier is not None

        # Verify tools are registered (Real tools from AVAILABLE_TOOLS)
        assert len(controller.registry.get_all_tools()) > 0

        controller.close()


def test_controller_prompt_generation(qapp):
    mock_study = MagicMock()
    with patch("XBrainLab.llm.agent.controller.AgentWorker"):
        controller = LLMController(mock_study)

        controller._append_history("user", "Hello")

        # Verify Assembler is used
        msgs = controller.assembler.get_messages(controller.history)
        assert len(msgs) == 2
        assert "Available Tools:" in msgs[0]["content"]

        controller.close()


def test_controller_verification_flow_rejection(qapp):
    """Test that if Verifier rejects, the tool is not executed and error is logged."""
    mock_study = MagicMock()
    with patch("XBrainLab.llm.agent.controller.AgentWorker"):
        controller = LLMController(mock_study)

        # Spy on signals
        status_mock = MagicMock()
        controller.status_update.connect(status_mock)

        # Mock Verifier to Reject
        mock_result = MagicMock()
        mock_result.is_valid = False
        mock_result.error_message = "Safety Violation"
        controller.verifier.verify_tool_call = MagicMock(return_value=mock_result)

        # Simulate LLM outputting a tool call
        command = ("SomeTool", {"param": 1})
        response_text = "Thinking... ```json ... ```"

        # Call process
        controller._process_tool_calls([command], response_text)

        # Assertions
        # 1. Status updated with Blocked message
        status_mock.assert_any_call("Blocked: Safety Violation")

        # 2. History updated with rejection feedback
        last_msg = controller.history[-1]
        assert (
            last_msg["role"] == "user"
        )  # Feedback is user role (System message simulation)
        assert "Tool call REJECTED: Safety Violation" in last_msg["content"]

        controller.close()
