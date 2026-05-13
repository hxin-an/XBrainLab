import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.application import QueryStateCommand, get_application_service
from XBrainLab.backend.study import Study
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


def _query_diagnostics(study, query: str, *, include_objects: bool = False):
    result = get_application_service(study).execute(
        QueryStateCommand(query=query, include_objects=include_objects),
    )
    assert result.ok, result.message
    return result.diagnostics


def _state(study):
    return _query_diagnostics(study, "state")["state"]


def _first_preprocessed_data(study):
    diagnostics = _query_diagnostics(study, "data_lists", include_objects=True)
    assert diagnostics["preprocessed_count"] == 1
    return diagnostics["preprocessed_data_list"][0]


def _command_result(
    *,
    failed: bool = False,
    diagnostics: dict[str, object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        failed=failed,
        ok=not failed,
        message="ok",
        diagnostics=diagnostics or {},
    )


def test_epoch_data_tool_execution():
    """Verify RealEpochDataTool passes event names to the command spine."""
    tool = RealEpochDataTool()
    mock_study = MagicMock()

    service = MagicMock()
    service.execute.return_value = _command_result()

    with patch(
        "XBrainLab.llm.tools.real.preprocess_real.get_application_service",
        return_value=service,
    ):
        # Execute tool with list of strings
        result = tool.execute(
            mock_study, t_min=-0.1, t_max=0.5, event_id=["Target", "Standard"]
        )

        command = service.execute.call_args.args[0]
        assert command.t_min == -0.1
        assert command.t_max == 0.5
        assert command.baseline is None
        assert command.event_ids == ["Target", "Standard"]
        assert "Data epoched" in result


def test_load_data_tool_execution():
    """Verify RealLoadDataTool calls LoadDataCommand."""
    tool = RealLoadDataTool()
    mock_study = MagicMock()

    service = MagicMock()
    service.execute.return_value = _command_result(
        diagnostics={"success_count": 1, "errors": []},
    )

    with patch(
        "XBrainLab.llm.tools.real.dataset_real.get_application_service",
        return_value=service,
    ):
        result = tool.execute(mock_study, paths=["C:/data/test.edf"])

        command = service.execute.call_args.args[0]
        assert command.paths == ["C:/data/test.edf"]
        assert "Successfully loaded 1 files" in result


# Integration Tests with Real Backend (No Mocks)
# Locate test data (relative to project root)
TEST_DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../fixtures/data")
)
GDF_FILE = os.path.join(TEST_DATA_DIR, "A01T.gdf")


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

        assert "Successfully loaded 1 files" in res_load
        assert _state(study)["raw"]["count"] == 1

        # 2. Filter Data (8-12Hz)
        filter_tool = RealBandPassFilterTool()
        res_filter = filter_tool.execute(study, low_freq=8, high_freq=12)

        assert "Applied Bandpass Filter" in res_filter

        hist = _first_preprocessed_data(study).get_preprocess_history()
        assert any("Filtering" in h for h in hist)

        # 2.3 Epoch Data (Required for Dataset Generation)
        epoch_tool = RealEpochDataTool()
        res_epoch = epoch_tool.execute(study, t_min=0, t_max=2.0, event_id=None)
        assert "Data epoched" in res_epoch
        assert _state(study)["epoch"]["exists"] is True

        # 2.5 Generate Dataset (Required for Training)
        gen_tool = RealGenerateDatasetTool()
        res_gen = gen_tool.execute(
            study, split_strategy="trial"
        )  # trial strategy default
        assert "Dataset successfully generated" in res_gen or "Count:" in res_gen
        state = _state(study)
        assert state["dataset"]["count"] > 0
        assert state["active_dataset"]["has_datasets"] is True

        # 3. Configure & Start Training
        # Set Model (Optional default is often set, but let's be explicit)
        model_tool = RealSetModelTool()
        res_model = model_tool.execute(study, model_name="EEGNet")
        assert "successfully set" in res_model
        assert _state(study)["training"]["model_name"] == "EEGNet"

        # Configure
        config_tool = RealConfigureTrainingTool()
        res_config = config_tool.execute(study, epoch=1, batch_size=4)
        assert "Training configured" in res_config
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

        assert "started success" in res_start
        training_state = _state(study)["training"]
        assert training_state["has_trainer"] is True
        assert training_state["plan_count"] >= 1

    def test_tool_error_handling(self, study):
        """Verify tools return user-friendly error messages on failure."""
        load_tool = RealLoadDataTool()

        # Try loading non-existent file
        res = load_tool.execute(study, paths=["non_existent.gdf"])
        assert "Failed" in res or "Error" in res
        assert _state(study)["raw"]["count"] == 0
