"""Focused coverage for the approved real Assistant adapters."""

from XBrainLab.backend.study import Study
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.result_contract import UiRequest, UiRequestKind


def test_real_registry_is_exactly_the_approved_target_surface() -> None:
    tools = get_all_tools("real")

    assert len(tools) == 18
    assert {tool.name for tool in tools} == AGENT_ACTION_CONTRACTS.tool_names()


def test_compute_saliency_is_zero_parameter_confirmed_ui_action() -> None:
    tool = next(
        tool for tool in get_all_tools("real") if tool.name == "compute_saliency"
    )

    assert tool.parameters == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    assert tool.requires_confirmation is True
    request = tool.execute(Study())
    assert isinstance(request, UiRequest)
    assert request.kind is UiRequestKind.WORKFLOW_HANDOFF
    assert request.params == {
        "tool_name": "compute_saliency",
        "command": "saliency",
        "decision_fields": (),
    }
