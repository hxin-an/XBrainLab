"""Unit tests for LLM mock tools — verify correct mock responses."""

from unittest.mock import MagicMock

import pytest

from XBrainLab.llm.tools.mock.dataset_mock import (
    MockAttachLabelsTool,
    MockClearDatasetTool,
    MockGenerateDatasetTool,
    MockGetDatasetInfoTool,
    MockListFilesTool,
    MockLoadDataTool,
)
from XBrainLab.llm.tools.mock.preprocess_mock import (
    MockBandPassFilterTool,
    MockChannelSelectionTool,
    MockEpochDataTool,
    MockNormalizeTool,
    MockNotchFilterTool,
    MockRereferenceTool,
    MockResampleTool,
    MockSetMontageTool,
    MockStandardPreprocessTool,
)
from XBrainLab.llm.tools.mock.training_mock import (
    MockConfigureTrainingTool,
    MockSetModelTool,
    MockStartTrainingTool,
)
from XBrainLab.llm.tools.mock.ui_control_mock import MockSwitchPanelTool


@pytest.fixture
def study():
    return MagicMock()


class TestDatasetMocks:
    def test_list_files(self, study):
        result = MockListFilesTool().execute(study, directory="/data")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_load_data(self, study):
        result = MockLoadDataTool().execute(study, paths=["/data/f.gdf"])
        assert "loaded" in result.lower() or "success" in result.lower()

    def test_attach_labels(self, study):
        result = MockAttachLabelsTool().execute(
            study, mapping={"file.gdf": "/labels.mat"}
        )
        assert isinstance(result, str)

    def test_clear_dataset(self, study):
        result = MockClearDatasetTool().execute(study)
        assert isinstance(result, str)

    def test_get_dataset_info(self, study):
        result = MockGetDatasetInfoTool().execute(study)
        assert isinstance(result, str)

    def test_generate_dataset(self, study):
        result = MockGenerateDatasetTool().execute(
            study, split_strategy="trial", training_mode="group"
        )
        assert isinstance(result, str)


class TestPreprocessMocks:
    def test_standard_preprocess(self, study):
        result = MockStandardPreprocessTool().execute(study)
        assert isinstance(result, str)

    def test_bandpass(self, study):
        result = MockBandPassFilterTool().execute(study, low_freq=1, high_freq=40)
        assert isinstance(result, str)

    def test_notch(self, study):
        result = MockNotchFilterTool().execute(study, freq=50)
        assert isinstance(result, str)

    def test_resample(self, study):
        result = MockResampleTool().execute(study, rate=128)
        assert isinstance(result, str)

    def test_normalize(self, study):
        result = MockNormalizeTool().execute(study, method="z-score")
        assert isinstance(result, str)

    def test_rereference(self, study):
        result = MockRereferenceTool().execute(study, method="average")
        assert isinstance(result, str)

    def test_channel_selection(self, study):
        result = MockChannelSelectionTool().execute(study, channels=["Cz", "Fz"])
        assert isinstance(result, str)

    def test_set_montage(self, study):
        result = MockSetMontageTool().execute(study, montage_name="standard_1020")
        assert isinstance(result, str)

    def test_epoch_data(self, study):
        result = MockEpochDataTool().execute(study, t_min=-0.5, t_max=1.0)
        assert isinstance(result, str)


class TestTrainingMocks:
    def test_set_model(self, study):
        result = MockSetModelTool().execute(study, model_name="EEGNet")
        assert "EEGNet" in result

    def test_configure_training(self, study):
        result = MockConfigureTrainingTool().execute(
            study, epoch=100, batch_size=32, learning_rate=0.001
        )
        assert isinstance(result, str)

    def test_start_training(self, study):
        result = MockStartTrainingTool().execute(study)
        assert isinstance(result, str)


class TestUIControlMock:
    def test_switch_panel_basic(self, study):
        result = MockSwitchPanelTool().execute(study, panel_name="training")
        assert "training" in result.lower()

    def test_switch_panel_with_view_mode(self, study):
        result = MockSwitchPanelTool().execute(
            study, panel_name="visualization", view_mode="saliency_map"
        )
        assert "saliency_map" in result
