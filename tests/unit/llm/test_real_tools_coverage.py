"""Focused coverage for the approved real Assistant adapters."""

import pytest

from XBrainLab.backend.study import Study
from XBrainLab.debug.tool_executor import ToolExecutor
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.application_surface import ToolCommandResult
from XBrainLab.llm.tools.result_contract import UiRequest, UiRequestKind


def test_real_registry_is_exactly_the_approved_target_surface() -> None:
    tools = get_all_tools("real")

    assert len(tools) == 17
    assert {tool.name for tool in tools} == AGENT_ACTION_CONTRACTS.tool_names()


@pytest.mark.parametrize(
    ("tool_name", "params"),
    (
        ("apply_bandpass_filter", {"low_freq": 4, "high_freq": 38}),
        ("apply_notch_filter", {"freq": 60}),
        ("resample_data", {"rate": 128}),
        ("set_reference", {"method": "average"}),
        ("normalize_data", {"method": "z-score"}),
    ),
)
def test_direct_preprocess_adapters_use_backend_preconditions(
    tool_name: str,
    params: dict[str, object],
) -> None:
    result = ToolExecutor(Study()).execute(tool_name, params)

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "precondition"
    assert "Load raw data" in result.message


def test_gui_handoff_and_navigation_adapters_return_typed_requests() -> None:
    executor = ToolExecutor(Study())

    handoff = executor.execute("import_eeg_data", {})
    navigation = executor.execute("switch_panel", {"panel_name": "dataset"})

    assert isinstance(handoff, UiRequest)
    assert handoff.kind is UiRequestKind.WORKFLOW_HANDOFF
    assert isinstance(navigation, UiRequest)
    assert navigation.kind is UiRequestKind.SWITCH_PANEL
