"""Approved real adapters remain thin over existing owners."""

from typing import Any

import pytest

from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.real import preprocess_real, training_real
from XBrainLab.llm.tools.result_contract import ToolResult, UiRequest, UiRequestKind


@pytest.mark.parametrize(
    ("tool", "params", "expected_name"),
    (
        (
            preprocess_real.RealBandPassFilterTool(),
            {"low_freq": 4, "high_freq": 38},
            "apply_bandpass_filter",
        ),
        (preprocess_real.RealNotchFilterTool(), {"freq": 60}, "apply_notch_filter"),
        (preprocess_real.RealResampleTool(), {"rate": 128}, "resample_data"),
        (preprocess_real.RealRereferenceTool(), {"method": "average"}, "set_reference"),
        (preprocess_real.RealNormalizeTool(), {"method": "z-score"}, "normalize_data"),
        (training_real.RealStartTrainingTool(), {}, "start_training"),
        (training_real.RealStopTrainingTool(), {}, "stop_training"),
    ),
)
def test_direct_adapters_delegate_to_application_surface(
    monkeypatch,
    tool,
    params: dict[str, object],
    expected_name: str,
) -> None:
    calls: list[tuple[Any, str, dict[str, Any]]] = []

    def _delegate(study: Any, tool_name: str, values: dict[str, Any]) -> ToolResult:
        calls.append((study, tool_name, values))
        return ToolResult(True, "delegated")

    module = (
        training_real
        if expected_name in {"start_training", "stop_training"}
        else preprocess_real
    )
    monkeypatch.setattr(module, "execute_real_application_tool", _delegate)
    study = object()

    result = tool.execute(study, **params)

    assert result.ok is True
    assert calls[0][0] is study
    assert calls[0][1] == expected_name


def test_parameter_free_gui_handoff_adapter_has_no_command_owner() -> None:
    tool = next(tool for tool in get_all_tools("real") if tool.name == "select_model")

    result = tool.execute(object())

    assert isinstance(result, UiRequest)
    assert result.kind is UiRequestKind.WORKFLOW_HANDOFF
    assert result.params == {
        "command": "configure_training",
        "tool_name": "select_model",
        "decision_fields": ("model",),
    }
