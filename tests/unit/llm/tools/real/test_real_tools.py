"""Real target-tool adapter contracts."""

import pytest

from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.result_contract import ToolResult, UiRequest, UiRequestKind


def _tool(name: str):
    return next(tool for tool in get_all_tools() if tool.name == name)


@pytest.mark.parametrize(
    "tool_name",
    (
        "import_eeg_data",
        "select_channels",
        "set_montage",
        "create_epochs",
        "configure_dataset_split",
        "select_model",
        "configure_training",
    ),
)
def test_gui_decision_tools_are_parameter_free_handoffs(tool_name: str) -> None:
    tool = _tool(tool_name)

    assert tool.parameters == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    result = tool.execute(object())
    assert isinstance(result, UiRequest)
    assert result.kind is UiRequestKind.WORKFLOW_HANDOFF
    assert result.params["tool_name"] == tool_name


def test_switch_panel_preserves_requested_visualization_subview() -> None:
    tool = next(tool for tool in get_all_tools() if tool.name == "switch_panel")
    result = tool.execute(
        object(),
        panel_name="visualization",
        view_mode="spectrogram",
    )

    assert isinstance(result, UiRequest)
    assert result.kind is UiRequestKind.SWITCH_PANEL
    assert result.params == {
        "panel": "visualization",
        "view_mode": "spectrogram",
    }


def test_switch_panel_without_a_panel_returns_input_failure() -> None:
    tool = next(tool for tool in get_all_tools() if tool.name == "switch_panel")

    result = tool.execute(object())

    assert isinstance(result, ToolResult)
    assert result.ok is False
    assert result.error_type == "input"
    assert result.message == "A panel name is required."


def test_normalization_schema_rejects_unsupported_method() -> None:
    assert _tool("normalize_data").parameters["properties"]["method"]["enum"] == [
        "z-score",
        "min-max",
    ]
