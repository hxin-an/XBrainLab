"""Behavior contracts for the Stable v2 Assistant mock registry."""

from unittest.mock import MagicMock

import pytest

from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.mock.preprocess_mock import (
    MockBandPassFilterTool,
    MockNormalizeTool,
    MockNotchFilterTool,
    MockRereferenceTool,
    MockResampleTool,
)
from XBrainLab.llm.tools.mock.state import MockWorkflowState
from XBrainLab.llm.tools.mock.training_mock import (
    MockStartTrainingTool,
    MockStopTrainingTool,
)
from XBrainLab.llm.tools.result_contract import ToolResult, UiRequest


@pytest.fixture
def study():
    return MagicMock()


@pytest.mark.parametrize(
    ("tool_type", "params"),
    [
        (MockBandPassFilterTool, {"low_freq": 1, "high_freq": 40}),
        (MockNotchFilterTool, {"freq": 50}),
        (MockResampleTool, {"rate": 128}),
        (MockNormalizeTool, {"method": "z-score"}),
        (MockRereferenceTool, {"method": "average"}),
    ],
)
def test_direct_preprocess_requires_loaded_data(study, tool_type, params) -> None:
    result = tool_type(MockWorkflowState()).execute(study, **params)

    assert result.ok is False
    assert result.error_type == "precondition"
    assert result.message == "Load EEG data before preprocessing."


@pytest.mark.parametrize(
    ("tool_type", "message"),
    [
        (MockBandPassFilterTool, "Error: frequencies are required"),
        (MockNotchFilterTool, "Error: frequency is required"),
        (MockResampleTool, "Error: rate is required"),
        (MockNormalizeTool, "Error: method is required"),
        (MockRereferenceTool, "Error: method is required"),
    ],
)
def test_direct_preprocess_missing_params_are_typed(study, tool_type, message) -> None:
    result = tool_type(MockWorkflowState(data_loaded=True)).execute(study)

    assert isinstance(result, ToolResult)
    assert result.ok is False
    assert result.error_type == "input"
    assert result.message == message


@pytest.mark.parametrize(
    ("tool_type", "params", "message"),
    [
        (
            MockBandPassFilterTool,
            {"low_freq": 1, "high_freq": 40},
            "Applied bandpass filter (1-40 Hz).",
        ),
        (MockNotchFilterTool, {"freq": 50}, "Applied notch filter at 50 Hz."),
        (MockResampleTool, {"rate": 128}, "Resampled data to 128 Hz."),
        (
            MockNormalizeTool,
            {"method": "z-score"},
            "Normalized data using z-score method.",
        ),
        (
            MockRereferenceTool,
            {"method": "average"},
            "Re-referenced data to average.",
        ),
    ],
)
def test_direct_preprocess_success(study, tool_type, params, message) -> None:
    result = tool_type(MockWorkflowState(data_loaded=True)).execute(study, **params)

    assert result.ok is True
    assert result.message == message


def test_stop_training_only_stops_active_run(study) -> None:
    state = MockWorkflowState(training_running=True)

    assert MockStopTrainingTool(state).execute(study).ok is True
    blocked = MockStopTrainingTool(state).execute(study)
    assert blocked.ok is False
    assert blocked.error_type == "precondition"


def test_start_training_requires_ready_state_and_confirmation(study) -> None:
    blocked = MockStartTrainingTool(MockWorkflowState()).execute(study)
    assert blocked.ok is False
    assert blocked.error_type == "precondition"

    ready = MockWorkflowState(
        split_spec_saved=True,
        model_name="EEGNet",
        training_options_configured=True,
    )
    unconfirmed = MockStartTrainingTool(ready).execute(study)
    assert unconfirmed.error_type == "confirmation_required"
    invalid = MockStartTrainingTool(ready).execute(study, confirmed="true")
    assert invalid.error_type == "input"
    assert MockStartTrainingTool(ready).execute(study, confirmed=True).ok is True


def test_mock_registry_is_exact_target_surface_and_shares_state(study) -> None:
    tools = {tool.name: tool for tool in get_all_tools(mode="mock")}

    assert set(tools) == set(AGENT_ACTION_CONTRACTS.model_tool_names())
    assert len(tools) == 18
    assert tools["start_training"].execute(study).ok is False
    for tool_name in (
        "import_eeg_data",
        "select_channels",
        "set_montage",
        "create_epochs",
        "configure_dataset_split",
        "select_model",
        "configure_training",
    ):
        result = tools[tool_name].execute(study)
        assert isinstance(result, UiRequest)
        assert result.kind.value == "workflow_handoff"


def test_switch_panel_mock_routes_target_view(study) -> None:
    tools = {tool.name: tool for tool in get_all_tools(mode="mock")}

    result = tools["switch_panel"].execute(
        study,
        panel_name="visualization",
        view_mode="saliency_map",
    )

    assert isinstance(result, UiRequest)
    assert result.kind.value == "switch_panel"
    assert result.params == {
        "panel": "visualization",
        "view_mode": "saliency_map",
    }
