"""Standalone debug execution follows the approved 17-action boundary."""

from XBrainLab.backend.study import Study
from XBrainLab.debug.tool_executor import ToolExecutor
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.application_surface import ToolCommandResult
from XBrainLab.llm.tools.result_contract import UiRequest, UiRequestKind


def test_debug_executor_surface_matches_canonical_real_tools() -> None:
    canonical = {tool.name for tool in get_all_tools("real")}

    assert canonical == AGENT_ACTION_CONTRACTS.model_tool_names()
    assert len(canonical) == 17
    assert set(ToolExecutor.TOOL_MAP) == canonical


def test_parameter_free_import_handoff_uses_real_ui_request_adapter() -> None:
    executor = ToolExecutor(Study())

    result = executor.execute("import_eeg_data", {})

    assert isinstance(result, UiRequest)
    assert result.kind is UiRequestKind.WORKFLOW_HANDOFF
    assert result.params["command"] == "scan_source"
    evidence = executor.last_execution_evidence
    assert evidence is not None
    assert evidence.dispatch_count == 1
    assert evidence.ui_adapter_invocation_count == 1
    assert evidence.runtime_command_invocation_count == 0


def test_parameter_free_training_setup_handoff_does_not_accept_model_settings() -> None:
    executor = ToolExecutor(Study())

    opened = executor.execute("configure_training", {})
    invented = executor.execute(
        "configure_training",
        {"epoch": 10, "batch_size": 8, "learning_rate": 0.001},
    )

    assert isinstance(opened, UiRequest)
    assert opened.kind is UiRequestKind.WORKFLOW_HANDOFF
    assert opened.params["command"] == "configure_training"
    assert isinstance(invented, ToolCommandResult)
    assert invented.ok is False
    assert invented.error_type == "input"


def test_switch_panel_remains_a_typed_navigation_request() -> None:
    result = ToolExecutor(Study()).execute(
        "switch_panel",
        {"panel_name": "visualization", "view_mode": "saliency_map"},
    )

    assert isinstance(result, UiRequest)
    assert result.kind is UiRequestKind.SWITCH_PANEL
    assert result.params == {
        "panel": "visualization",
        "view_mode": "saliency_map",
    }


def test_direct_preprocess_action_is_blocked_by_backend_state_when_empty() -> None:
    result = ToolExecutor(Study()).execute(
        "apply_bandpass_filter",
        {"low_freq": 4, "high_freq": 38},
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "precondition"
    assert "Load raw data" in result.message


def test_host_confirmation_cannot_be_smuggled_inside_parameters() -> None:
    result = ToolExecutor(Study()).execute(
        "reset_preprocessing",
        {"confirmed": True},
    )

    assert isinstance(result, ToolCommandResult)
    assert result.ok is False
    assert result.error_type == "input"
    assert result.diagnostics["policy"] == "host_confirmation_parameter"


def test_retired_and_unknown_tools_fail_before_execution() -> None:
    for tool_name in ("list_files", "query_state", "scan_source", "unknown_tool"):
        executor = ToolExecutor(Study())

        result = executor.execute(tool_name, {})

        assert isinstance(result, ToolCommandResult)
        assert result.ok is False
        assert result.error_type == "input"
        evidence = executor.last_execution_evidence
        assert evidence is not None
        assert evidence.runtime_command_invocation_count == 0
        assert evidence.adapter_invocation_count == 0
