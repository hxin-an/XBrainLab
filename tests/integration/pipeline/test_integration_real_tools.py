import os
from unittest.mock import MagicMock

import pytest

from XBrainLab.backend.application import (
    ChangedState,
    CommandName,
    CommandResult,
    ErrorType,
    QueryStateCommand,
    get_application_service,
)
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.study import Study
from XBrainLab.llm.tools import application_surface
from XBrainLab.llm.tools.application_surface import (
    ToolAvailability,
    ToolAvailabilityContext,
)
from XBrainLab.llm.tools.real.dataset_real import (
    RealGenerateDatasetTool,
    RealLoadDataTool,
)
from XBrainLab.llm.tools.real.preprocess_real import (
    RealBandPassFilterTool,
    RealEpochDataTool,
)
from XBrainLab.llm.tools.real.training_real import (
    RealConfigureTrainingTool,
    RealSetModelTool,
    RealStartTrainingTool,
)
from XBrainLab.llm.tools.result_contract import ToolResult


def _query_result(study, query: str, *, include_objects: bool = False):
    result = get_application_service(study).execute(
        QueryStateCommand(query=query, include_objects=include_objects),
    )
    assert isinstance(result, CommandResult)
    assert result.ok, result.message
    return result


def _query_diagnostics(study, query: str):
    return _query_result(study, query).diagnostics


def _state(study):
    return _query_diagnostics(study, "state")["state"]


def _first_preprocessed_data(study):
    result = _query_result(study, "data_lists", include_objects=True)
    assert result.diagnostics["preprocessed_count"] == 1
    return result.runtime["preprocessed_data_list"][0]


def _command_result(
    *,
    command_name: str = CommandName.QUERY_STATE.value,
    failed: bool = False,
    message: str = "ok",
    diagnostics: dict[str, object] | None = None,
) -> CommandResult:
    state = ApplicationStateSnapshot.empty()
    if failed:
        return CommandResult.failure_result(
            command_name=command_name,
            message=message,
            state=state,
            changed_state=ChangedState(),
            error_type=ErrorType.RUNTIME,
            recoverable=True,
            diagnostics=diagnostics or {},
        )
    return CommandResult.success_result(
        command_name=command_name,
        message=message,
        state=state,
        changed_state=ChangedState(),
        diagnostics=diagnostics or {},
    )


def _assert_tool_result(result, *, ok: bool = True) -> ToolResult:
    assert isinstance(result, ToolResult)
    assert result.ok is ok
    if ok:
        assert result.error_type == ErrorType.NONE.value
    else:
        assert result.error_type != ErrorType.NONE.value
    return result


def _install_canonical_runtime(
    monkeypatch,
    tool_name: str,
    result: CommandResult,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    availability = ToolAvailability(
        tool_name=tool_name,
        enabled=True,
        command_name=application_surface.TOOL_TO_COMMAND[tool_name].value,
    )
    context = ToolAvailabilityContext(
        availability=availability,
        state={"canonical_snapshot": True},
        generation=17,
    )
    get_context = MagicMock(return_value=context)
    runtime = MagicMock()
    runtime.execute.return_value = result
    runtime_provider = MagicMock(return_value=runtime)
    monkeypatch.setattr(application_surface, "get_application_context", get_context)
    monkeypatch.setattr(
        application_surface,
        "application_tool_runtime",
        runtime_provider,
    )
    return runtime, get_context, runtime_provider


def test_epoch_data_tool_execution(monkeypatch):
    """Verify the Real tool reaches canonical epoch command translation."""
    command_result = _command_result(
        command_name=CommandName.CREATE_EPOCH.value,
        message="Created epochs from -0.1s to 0.5s.",
    )
    runtime, get_context, runtime_provider = _install_canonical_runtime(
        monkeypatch,
        "epoch_data",
        command_result,
    )
    study = object()

    result = RealEpochDataTool().execute(
        study,
        t_min=-0.1,
        t_max=0.5,
        event_id=["Target", "Standard"],
    )

    command = runtime.execute.call_args.args[0]
    assert command.t_min == -0.1
    assert command.t_max == 0.5
    assert command.baseline is None
    assert command.event_ids == ["Target", "Standard"]
    assert result.ok is True
    assert result.message == "Created epochs from -0.1s to 0.5s."
    assert result.payload["status"] == "ok"
    assert result.payload["command_name"] == CommandName.CREATE_EPOCH.value
    assert isinstance(result.payload["state"], dict)
    assert isinstance(result.payload["changed_state"], dict)
    assert result.payload["diagnostics"] == {}
    assert result.error_type == "none"
    assert result.recoverable is True
    assert result.command_name == CommandName.CREATE_EPOCH.value
    assert result.capability is not None
    assert result.capability["tool_name"] == "epoch_data"
    assert isinstance(result.changed_state, dict)
    get_context.assert_called_once_with(study, "epoch_data", runtime=runtime)
    runtime_provider.assert_called_once_with(study)


def test_load_data_tool_execution(monkeypatch):
    """Verify the Real tool reaches canonical load-data command translation."""
    command_result = _command_result(
        command_name=CommandName.LOAD_DATA.value,
        message="Loaded 1 file(s).",
        diagnostics={"success_count": 1, "errors": []},
    )
    runtime, get_context, runtime_provider = _install_canonical_runtime(
        monkeypatch,
        "load_data",
        command_result,
    )
    study = object()

    result = RealLoadDataTool().execute(study, paths=["C:/data/test.edf"])

    command = runtime.execute.call_args.args[0]
    assert command.paths == ["C:/data/test.edf"]
    assert command.allow_append is True
    assert result.ok is True
    assert result.message == "Loaded 1 file(s)."
    assert result.payload["status"] == "ok"
    assert result.payload["command_name"] == CommandName.LOAD_DATA.value
    assert isinstance(result.payload["state"], dict)
    assert isinstance(result.payload["changed_state"], dict)
    assert result.payload["diagnostics"] == {"success_count": 1, "errors": []}
    assert result.error_type == "none"
    assert result.recoverable is True
    assert result.command_name == CommandName.LOAD_DATA.value
    assert result.capability is not None
    assert result.capability["tool_name"] == "load_data"
    assert result.diagnostics == {"success_count": 1, "errors": []}
    assert isinstance(result.changed_state, dict)
    get_context.assert_called_once_with(study, "load_data", runtime=runtime)
    runtime_provider.assert_called_once_with(study)


# Integration Tests with Real Backend (No Mocks)
# Locate test data (relative to project root)
TEST_DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../fixtures/data")
)
GDF_FILE = os.path.join(TEST_DATA_DIR, "A01T.gdf")
EXPECTED_A01T_REAL_TOOL_EPOCH_EVENT_IDS = {
    "769": 0,
    "770": 1,
    "771": 2,
    "772": 3,
}
EXPECTED_A01T_REAL_TOOL_SPLIT_SUMMARY = {
    "count": 1,
    "train_count": 185,
    "val_count": 46,
    "test_count": 57,
    "audit": {"ok": True, "dataset_count": 1, "issues": []},
}


class TestRealToolChain:
    """End-to-end integration tests for LLM Tools -> ApplicationService."""

    @pytest.fixture
    def study(self):
        return Study()

    def test_load_preprocess_train_chain(self, study):
        """Test sequence: Load -> Filter -> Train (via Tools)."""
        if not os.path.exists(GDF_FILE):
            pytest.skip("Test data not found")

        # 1. Load Data
        load_tool = RealLoadDataTool()
        res_load = load_tool.execute(study, paths=[GDF_FILE])

        res_load = _assert_tool_result(res_load)
        assert res_load.message == "Loaded 1 file(s)."
        assert res_load.payload["status"] == "ok"
        assert res_load.payload["command_name"] == CommandName.LOAD_DATA.value
        assert res_load.payload["diagnostics"]["success_count"] == 1
        assert res_load.payload["diagnostics"]["errors"] == []
        assert _state(study)["raw"]["count"] == 1

        # 2. Filter Data (8-12Hz)
        filter_tool = RealBandPassFilterTool()
        res_filter = filter_tool.execute(study, low_freq=8, high_freq=12)

        res_filter = _assert_tool_result(res_filter)
        assert res_filter.message == "Applied bandpass filter (8.0-12.0 Hz)."

        hist = _first_preprocessed_data(study).get_preprocess_history()
        assert any("Filtering" in h for h in hist)

        # 2.3 Epoch Data (Required for Dataset Generation)
        epoch_tool = RealEpochDataTool()
        res_epoch = epoch_tool.execute(
            study,
            t_min=0,
            t_max=2.0,
            event_id=["769", "770", "771", "772"],
        )
        res_epoch = _assert_tool_result(res_epoch)
        assert res_epoch.message == "Created epochs from 0.0s to 2.0s."
        epoch_state = _state(study)["epoch"]
        assert epoch_state["exists"] is True
        assert epoch_state["epoch_count"] == 288
        assert epoch_state["n_channels"] == 25
        assert epoch_state["n_times"] == 501
        assert epoch_state["event_ids"] == EXPECTED_A01T_REAL_TOOL_EPOCH_EVENT_IDS

        # 2.5 Generate Dataset (Required for Training)
        gen_tool = RealGenerateDatasetTool()
        res_gen = gen_tool.execute(
            study, split_strategy="trial"
        )  # trial strategy default
        res_gen = _assert_tool_result(res_gen)
        assert res_gen.message == "Generated 1 dataset(s)."
        assert res_gen.payload["diagnostics"]["dataset_count"] == 1
        state = _state(study)
        assert (
            state["dataset"]["count"] == EXPECTED_A01T_REAL_TOOL_SPLIT_SUMMARY["count"]
        )
        assert (
            state["dataset"]["split_summary"] == EXPECTED_A01T_REAL_TOOL_SPLIT_SUMMARY
        )
        assert state["active_dataset"]["has_datasets"] is True

        # 3. Configure & Start Training
        # Set Model (Optional default is often set, but let's be explicit)
        model_tool = RealSetModelTool()
        res_model = model_tool.execute(study, model_name="EEGNet")
        res_model = _assert_tool_result(res_model)
        assert res_model.message == "Model configured: EEGNet."
        assert _state(study)["training"]["model_name"] == "EEGNet"

        # Configure
        config_tool = RealConfigureTrainingTool()
        res_config = config_tool.execute(
            study,
            epoch=1,
            batch_size=4,
            learning_rate=0.001,
        )
        res_config = _assert_tool_result(res_config)
        assert res_config.message == "Training configured."
        assert res_config.payload["diagnostics"]["training_option"]["epoch"] == 1
        assert res_config.payload["diagnostics"]["training_option"]["batch_size"] == 4
        training_state = _state(study)["training"]
        assert training_state["training_option"]["epoch"] == 1
        assert training_state["training_option"]["batch_size"] == 4

        # Start Training
        start_tool = RealStartTrainingTool()
        res_start = start_tool.execute(
            study,
            confirmed=True,
            append=False,
            interactive=False,
        )

        res_start = _assert_tool_result(res_start)
        assert res_start.message == "Training completed."
        assert res_start.payload["diagnostics"]["append"] is False
        assert res_start.payload["diagnostics"]["interactive"] is False
        training_state = _state(study)["training"]
        assert training_state["has_trainer"] is True
        assert training_state["plan_count"] == 1
        assert training_state["run_count"] == 1
        assert training_state["finished_run_count"] == 1

    def test_tool_error_handling(self, study):
        """Verify tools return user-friendly error messages on failure."""
        load_tool = RealLoadDataTool()

        # Try loading non-existent file
        res = load_tool.execute(study, paths=["non_existent.gdf"])
        res = _assert_tool_result(res, ok=False)
        assert "Failed" in res.message or "Error" in res.message
        assert _state(study)["raw"]["count"] == 0
