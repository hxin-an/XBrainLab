from unittest.mock import MagicMock, patch

from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.assembler import ContextAssembler
from XBrainLab.llm.pipeline_state import PipelineStage
from XBrainLab.llm.tools.base import BaseTool
from XBrainLab.llm.tools.tool_registry import ToolRegistry


# Mock Tools
class ValidTool(BaseTool):
    @property
    def name(self):
        return "valid_tool"

    @property
    def description(self):
        return "Valid description"

    @property
    def parameters(self):
        return {"p": "v"}

    def is_valid(self, study):
        return True

    def execute(self, study, **kwargs):
        return ""


class InvalidTool(BaseTool):
    @property
    def name(self):
        return "invalid_tool"

    @property
    def description(self):
        return "Invalid description"

    @property
    def parameters(self):
        return {}

    def is_valid(self, study):
        return False

    def execute(self, study, **kwargs):
        return ""


def test_assembler_filtering():
    """Test that Assembler includes only tools allowed by the stage config."""

    # 1. Setup Registry
    registry = ToolRegistry()
    registry.register(ValidTool())
    registry.register(InvalidTool())

    # 2. Setup Mock Study
    mock_study = MagicMock(spec=Study)

    # 3. Patch pipeline stage to a config that allows only valid_tool
    with (
        patch(
            "XBrainLab.llm.agent.assembler.compute_pipeline_stage",
            return_value=PipelineStage.EMPTY,
        ),
        patch(
            "XBrainLab.llm.agent.assembler.STAGE_CONFIG",
            {
                PipelineStage.EMPTY: {
                    "tools": ["valid_tool"],
                    "guidance": "test guidance",
                }
            },
        ),
    ):
        assembler = ContextAssembler(registry, mock_study)
        system_prompt = assembler.build_system_prompt()

    # 4. Verify Content
    assert "valid_tool" in system_prompt
    assert "Valid description" in system_prompt
    assert "invalid_tool" not in system_prompt
    assert "Invalid description" not in system_prompt


def test_assembler_context_and_history():
    """Test standard features: RAG context and History assembly."""
    registry = ToolRegistry()
    mock_study = MagicMock(spec=Study)

    with patch(
        "XBrainLab.llm.agent.assembler.compute_pipeline_stage",
        return_value=PipelineStage.EMPTY,
    ):
        assembler = ContextAssembler(registry, mock_study)

        # Add RAG context
        assembler.add_context("Important RAG Info")

        # Get Messages with History
        history = [{"role": "user", "content": "Hello"}]
        messages = assembler.get_messages(history)

    # Verify System Message index 0
    sys_msg = messages[0]["content"]
    assert "Important RAG Info" in sys_msg
    assert "You are XBrainLab Assistant" in sys_msg  # Standard header

    # Verify History
    assert messages[1] == {"role": "user", "content": "Hello"}
