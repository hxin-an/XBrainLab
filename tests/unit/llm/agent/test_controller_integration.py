from unittest.mock import MagicMock, patch

from XBrainLab.llm.agent.assembler import ContextAssembler
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.verifier import ToolSchemaValidator, VerificationLayer
from XBrainLab.llm.tools.tool_registry import ToolRegistry

EXPECTED_CONTROLLER_TOOL_NAMES = (
    "list_files",
    "scan_source",
    "preview_interpretation",
    "validate_interpretation",
    "apply_interpretation",
    "save_interpretation_recipe",
    "reload_interpretation_recipe",
    "load_data",
    "attach_labels",
    "clear_dataset",
    "query_state",
    "get_dataset_info",
    "generate_dataset",
    "evaluate",
    "visualize",
    "saliency",
    "apply_standard_preprocess",
    "apply_bandpass_filter",
    "apply_notch_filter",
    "resample_data",
    "normalize_data",
    "set_reference",
    "select_channels",
    "set_montage",
    "epoch_data",
    "set_model",
    "configure_training",
    "start_training",
    "switch_panel",
)

# Mock QApp fixture implies pytest-qt is installed
# If not, we can rely on standard unit test logic for non-UI parts,
# but LLMController inherits QObject, so we need QApplication.
# Assuming `qapp` fixture is available from conftest.py or pytest-qt.


def test_controller_initialization(qapp):
    mock_study = MagicMock()

    with patch("XBrainLab.llm.agent.controller.AgentWorker"):
        controller = LLMController(mock_study)

        assert isinstance(controller.registry, ToolRegistry)
        assert isinstance(controller.assembler, ContextAssembler)
        assert isinstance(controller.verifier, VerificationLayer)
        assert controller.assembler.registry is controller.registry
        assert controller.assembler.study_state is mock_study

        tools = controller.registry.get_all_tools()
        tool_names = tuple(tool.name for tool in tools)
        assert tool_names == EXPECTED_CONTROLLER_TOOL_NAMES
        schema_validator = controller.verifier.validators[0]
        assert isinstance(schema_validator, ToolSchemaValidator)
        assert tuple(schema_validator.tool_schemas) == EXPECTED_CONTROLLER_TOOL_NAMES
        assert schema_validator.tool_schemas["query_state"]["properties"] == {
            "query": {
                "type": "string",
                "enum": [
                    "state",
                    "data_lists",
                    "data_summary",
                    "preprocess_diagnostics",
                    "smart_filter_suggestions",
                ],
                "default": "state",
            }
        }

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
        # 1. Status updated with a user-facing blocked message.
        assert any(
            "Blocked:" in str(call.args[0]) and "Safety Violation" in str(call.args[0])
            for call in status_mock.call_args_list
        )

        # 2. History updated with structured tool-output feedback
        last_msg = controller.history[-1]
        assert (
            last_msg["role"] == "user"
        )  # Feedback is user role (System message simulation)
        assert "Tool Output:" in last_msg["content"]
        assert "Safety Violation" in last_msg["content"]

        controller.close()
