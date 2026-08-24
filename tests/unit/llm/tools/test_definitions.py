"""Schema contracts for the Stable v2 Assistant tool definitions."""

from typing import Any

import pytest

from XBrainLab.llm.tools.definitions.preprocess_def import (
    BaseBandPassFilterTool,
    BaseNormalizeTool,
    BaseNotchFilterTool,
    BaseRereferenceTool,
    BaseResampleTool,
)
from XBrainLab.llm.tools.definitions.training_def import (
    BaseStartTrainingTool,
    BaseStopTrainingTool,
)
from XBrainLab.llm.tools.definitions.ui_control_def import (
    ApplicationCommandTool,
    BaseSwitchPanelTool,
    WorkflowHandoffTool,
)
from XBrainLab.llm.tools.schema_contract import tool_contract_for_llm


def _property_value(prop: property) -> Any:
    getter = prop.fget
    assert getter is not None
    return getter(None)


DIRECT_CONTRACTS = {
    BaseBandPassFilterTool: (
        "apply_bandpass_filter",
        ("low_freq", "high_freq"),
    ),
    BaseNotchFilterTool: ("apply_notch_filter", ("freq",)),
    BaseResampleTool: ("resample_data", ("rate",)),
    BaseNormalizeTool: ("normalize_data", ("method",)),
    BaseRereferenceTool: ("set_reference", ("method",)),
    BaseStartTrainingTool: ("start_training", ()),
    BaseStopTrainingTool: ("stop_training", ()),
}

DIRECT_PREPROCESS_TOOLS = (
    BaseBandPassFilterTool,
    BaseNotchFilterTool,
    BaseResampleTool,
    BaseNormalizeTool,
    BaseRereferenceTool,
)


@pytest.mark.parametrize(("tool_cls", "contract"), DIRECT_CONTRACTS.items())
def test_direct_definition_has_exact_schema(tool_cls, contract) -> None:
    expected_name, expected_required = contract
    tool = tool_cls()

    assert tool.name == expected_name
    assert tool.description.strip()
    assert tool.parameters["type"] == "object"
    assert tuple(tool.parameters.get("required", ())) == expected_required
    assert set(expected_required) <= set(tool.parameters["properties"])

    with pytest.raises(NotImplementedError):
        tool.execute(None)


def test_normalize_method_is_closed_to_target_choices() -> None:
    schema = BaseNormalizeTool().parameters

    assert schema["properties"]["method"]["enum"] == ["z-score", "min-max"]


@pytest.mark.parametrize("tool_cls", DIRECT_PREPROCESS_TOOLS)
def test_direct_preprocess_projection_requires_latest_user_values_without_defaults(
    tool_cls,
) -> None:
    tool = tool_cls()
    description = tool.description.lower()
    projected = tool_contract_for_llm(tool)

    assert "latest user request" in description
    assert "respond_to_user" in description
    assert "pending_action" in description
    assert "missing_inputs" in description
    for parameter_name in tool.parameters["required"]:
        parameter = tool.parameters["properties"][parameter_name]
        projected_parameter = projected["parameters"]["properties"][parameter_name]
        parameter_description = parameter["description"].lower()

        assert "latest user request" in parameter_description
        assert "no model or product default" in parameter_description
        assert "default" not in parameter
        assert projected_parameter["description"] == parameter["description"]


def test_start_training_requires_confirmation_and_stop_does_not() -> None:
    assert BaseStartTrainingTool().requires_confirmation is True
    assert BaseStopTrainingTool().requires_confirmation is False


def test_switch_panel_target_and_visualization_view_schema_are_closed() -> None:
    schema = BaseSwitchPanelTool().parameters

    assert schema["required"] == ["panel_name"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["panel_name"]["enum"] == [
        "dataset",
        "preprocess",
        "training",
        "visualization",
        "evaluation",
    ]
    assert schema["properties"]["view_mode"]["enum"] == [
        "saliency_map",
        "spectrogram",
        "topographic_map",
        "3d_plot",
    ]


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
def test_workflow_handoff_schema_is_parameter_free(tool_name: str) -> None:
    tool = WorkflowHandoffTool(tool_name, "Open the existing UI.")

    assert tool.name == tool_name
    assert tool.parameters == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


@pytest.mark.parametrize(
    "tool_name",
    ("reset_preprocessing", "clear_training_history"),
)
def test_lifecycle_adapter_schema_is_parameter_free(tool_name: str) -> None:
    tool = ApplicationCommandTool(tool_name, "Apply after confirmation.")

    assert tool.name == tool_name
    assert tool.parameters == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
