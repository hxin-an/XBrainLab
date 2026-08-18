"""Approved Stable-v2 GUI handoff and exact runtime surface contracts."""

from __future__ import annotations

import pytest

from XBrainLab.backend.application.commands import CommandName
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.result_contract import UiRequest, UiRequestKind

_TARGET_GUI_HANDOFFS = {
    "import_eeg_data": (CommandName.SCAN_SOURCE, ()),
    "select_channels": (CommandName.PREPROCESS, ("channels",)),
    "set_montage": (CommandName.APPLY_MONTAGE, ()),
    "create_epochs": (CommandName.CREATE_EPOCH, ()),
    "configure_dataset_split": (CommandName.CONFIGURE_DATASET_SPLIT, ()),
    "select_model": (CommandName.CONFIGURE_TRAINING, ("model",)),
    "configure_training": (
        CommandName.CONFIGURE_TRAINING,
        ("training_options",),
    ),
    "compute_saliency": (CommandName.SALIENCY, ()),
}


@pytest.mark.parametrize("mode", ("mock", "real"))
def test_target_gui_tools_are_zero_parameter_typed_handoffs(
    mode: str,
) -> None:
    tools = {tool.name: tool for tool in get_all_tools(mode)}

    for tool_name, (command, decision_fields) in _TARGET_GUI_HANDOFFS.items():
        tool = tools[tool_name]
        assert tool.parameters == {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
        result = tool.execute(object())
        assert result == UiRequest(
            kind=UiRequestKind.WORKFLOW_HANDOFF,
            params={
                "tool_name": tool_name,
                "command": command.value,
                "decision_fields": decision_fields,
            },
        )


def test_target_runtime_and_model_projection_are_the_approved_eighteen() -> None:
    approved = frozenset(
        {
            *_TARGET_GUI_HANDOFFS,
            "apply_bandpass_filter",
            "apply_notch_filter",
            "resample_data",
            "set_reference",
            "normalize_data",
            "start_training",
            "stop_training",
            "reset_preprocessing",
            "clear_training_history",
            "switch_panel",
        }
    )

    assert AGENT_ACTION_CONTRACTS.tool_names() == approved
    assert AGENT_ACTION_CONTRACTS.model_tool_names() == approved
    for mode in ("mock", "real"):
        assert {tool.name for tool in get_all_tools(mode)} == approved
