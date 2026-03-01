"""Coverage tests for mock tools — execute() success paths."""

from XBrainLab.llm.tools.mock.dataset_mock import (
    MockAttachLabelsTool,
    MockListFilesTool,
    MockLoadDataTool,
)
from XBrainLab.llm.tools.mock.preprocess_mock import (
    MockBandPassFilterTool,
    MockChannelSelectionTool,
    MockNormalizeTool,
    MockNotchFilterTool,
    MockRereferenceTool,
    MockResampleTool,
    MockSetMontageTool,
)
from XBrainLab.llm.tools.mock.training_mock import (
    MockConfigureTrainingTool,
    MockSetModelTool,
)
from XBrainLab.llm.tools.mock.ui_control_mock import MockSwitchPanelTool


class TestMockPreprocessSuccess:
    """Test mock preprocess tools succeed with valid params."""

    def test_bandpass_success(self):
        tool = MockBandPassFilterTool()
        result = tool.execute(study=None, low_freq=4.0, high_freq=40.0)
        assert "Applied bandpass filter" in result
        assert "4.0-40.0" in result

    def test_notch_success(self):
        tool = MockNotchFilterTool()
        result = tool.execute(study=None, freq=50.0)
        assert "Applied notch filter at 50.0 Hz" in result

    def test_resample_success(self):
        tool = MockResampleTool()
        result = tool.execute(study=None, rate=256)
        assert "Resampled data to 256 Hz" in result

    def test_normalize_success(self):
        tool = MockNormalizeTool()
        result = tool.execute(study=None, method="z-score")
        assert "Normalized data using z-score" in result

    def test_rereference_success(self):
        tool = MockRereferenceTool()
        result = tool.execute(study=None, method="average")
        assert "Re-referenced data to average" in result

    def test_channel_selection_success(self):
        tool = MockChannelSelectionTool()
        result = tool.execute(study=None, channels=["C3", "C4", "Cz"])
        assert "Selected 3 channels" in result

    def test_set_montage_success(self):
        tool = MockSetMontageTool()
        result = tool.execute(study=None, montage_name="standard_1020")
        assert "Set montage to standard_1020" in result


class TestMockDatasetSuccess:
    """Test mock dataset tools succeed with valid params."""

    def test_list_files_success(self):
        tool = MockListFilesTool()
        result = tool.execute(study=None, directory="/data", pattern="*.gdf")
        assert "found in /data" in result

    def test_load_data_success(self):
        tool = MockLoadDataTool()
        result = tool.execute(study=None, paths=["/data/A01T.gdf"])
        assert "Successfully loaded" in result

    def test_attach_labels_success(self):
        tool = MockAttachLabelsTool()
        result = tool.execute(study=None, mapping={"A01T.gdf": "A01T_labels.csv"})
        assert "Attached labels to 1 files" in result


class TestMockTrainingSuccess:
    """Test mock training tools succeed with valid params."""

    def test_set_model_success(self):
        tool = MockSetModelTool()
        result = tool.execute(study=None, model_name="EEGNet")
        assert "Model set to EEGNet" in result

    def test_configure_training_success(self):
        tool = MockConfigureTrainingTool()
        result = tool.execute(study=None, epoch=100, learning_rate=0.001, batch_size=32)
        assert "Training configured" in result
        assert "Epochs: 100" in result


class TestMockUIControlSuccess:
    """Test mock UI control tool paths."""

    def test_switch_panel_no_view_mode(self):
        tool = MockSwitchPanelTool()
        result = tool.execute(study=None, panel_name="training", view_mode=None)
        assert "Switched UI view to training panel" in result
