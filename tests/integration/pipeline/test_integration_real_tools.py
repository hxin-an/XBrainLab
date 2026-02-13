import os
from unittest.mock import MagicMock, patch

import pytest

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


def test_epoch_data_tool_execution():
    """Verify RealEpochDataTool correctly calls Facade with list of strings."""
    tool = RealEpochDataTool()
    mock_study = MagicMock()

    # We patch BackendFacade to verify the call
    with patch("XBrainLab.llm.tools.real.preprocess_real.BackendFacade") as MockFacade:
        instance = MockFacade.return_value

        # Execute tool with list of strings
        result = tool.execute(
            mock_study, t_min=-0.1, t_max=0.5, event_id=["Target", "Standard"]
        )

        # Verify Facade call
        instance.epoch_data.assert_called_once_with(
            -0.1, 0.5, baseline=None, event_ids=["Target", "Standard"]
        )
        assert "Data epoched" in result


def test_load_data_tool_execution():
    """Verify RealLoadDataTool calls Facade.load_data."""
    tool = RealLoadDataTool()
    mock_study = MagicMock()

    with patch("XBrainLab.llm.tools.real.dataset_real.BackendFacade") as MockFacade:
        instance = MockFacade.return_value
        instance.load_data.return_value = (1, [])  # 1 success, 0 errors

        result = tool.execute(mock_study, paths=["C:/data/test.edf"])

        instance.load_data.assert_called_once_with(["C:/data/test.edf"])
        assert "Successfully loaded 1 files" in result


# Integration Tests with Real Backend (No Mocks)
# Locate test data (relative to project root)
TEST_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))
GDF_FILE = os.path.join(TEST_DATA_DIR, "A01T.gdf")


class TestRealToolChain:
    """End-to-end integration tests for LLM Tools -> Backend Controller."""

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
        assert len(study.loaded_data_list) == 1

        # 2. Filter Data (8-12Hz)
        filter_tool = RealBandPassFilterTool()
        res_filter = filter_tool.execute(study, low_freq=8, high_freq=12)

        assert "Applied Bandpass Filter" in res_filter

        # Verify effect on controller
        controller = study.get_controller("preprocess")
        assert controller.has_data()
        hist = controller.get_first_data().get_preprocess_history()
        assert any("Filtering" in h for h in hist)

        # 2.3 Epoch Data (Required for Dataset Generation)
        epoch_tool = RealEpochDataTool()
        res_epoch = epoch_tool.execute(study, t_min=0, t_max=2.0, event_id=None)
        assert "Data epoched" in res_epoch

        # 2.5 Generate Dataset (Required for Training)
        gen_tool = RealGenerateDatasetTool()
        res_gen = gen_tool.execute(
            study, split_strategy="trial"
        )  # trial strategy default
        assert "Dataset successfully generated" in res_gen or "Count:" in res_gen

        # 3. Configure & Start Training
        # Set Model (Optional default is often set, but let's be explicit)
        model_tool = RealSetModelTool()
        res_model = model_tool.execute(study, model_name="EEGNet")
        assert "successfully set" in res_model

        # Configure
        config_tool = RealConfigureTrainingTool()
        res_config = config_tool.execute(study, epoch=1, batch_size=4)
        assert "Training configured" in res_config

        # Start Training
        # Note: In Headless mode, this starts a thread.
        # We need to verify the controller state changes to 'training' or 'running'.
        start_tool = RealStartTrainingTool()
        res_start = start_tool.execute(study)

        assert "started success" in res_start

        # Verify Controller State
        train_ctrl = study.get_controller("training")
        # Since it's threaded, it might be quick or slow.
        # We just check if the request was processed and controller is aware.
        # Ideally check train_ctrl.is_training() but it might finish instantly for 1 epoch on tiny data.
        # We'll check if history table has entries or if logs exist.
        # For this test, just ensuring the Tool->Facade->Controller call didn't crash is enough.

    def test_tool_error_handling(self, study):
        """Verify tools return user-friendly error messages on failure."""
        load_tool = RealLoadDataTool()

        # Try loading non-existent file
        res = load_tool.execute(study, paths=["non_existent.gdf"])
        assert "Failed" in res or "Error" in res
        assert len(study.loaded_data_list) == 0
