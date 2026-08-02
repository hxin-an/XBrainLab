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
from XBrainLab.llm.tools.mock.state import MockWorkflowState
from XBrainLab.llm.tools.mock.training_mock import (
    MockConfigureTrainingTool,
    MockSetModelTool,
    MockStartTrainingTool,
)
from XBrainLab.llm.tools.mock.ui_control_mock import MockSwitchPanelTool
from XBrainLab.llm.tools.result_contract import ToolResult, UiRequest


def _assert_success(
    result: object,
    message: str,
    *,
    payload: object | None = None,
) -> None:
    assert isinstance(result, ToolResult)
    assert result.ok is True
    assert result.message == message
    assert result.payload == payload
    assert result.error_type == "none"
    assert result.recoverable is True


class TestMockPreprocessSuccess:
    """Test mock preprocess tools succeed with valid params."""

    def test_bandpass_success(self):
        tool = MockBandPassFilterTool(MockWorkflowState(data_loaded=True))
        result = tool.execute(study=None, low_freq=4.0, high_freq=40.0)
        _assert_success(result, "Applied bandpass filter (4.0-40.0 Hz).")

    def test_notch_success(self):
        tool = MockNotchFilterTool(MockWorkflowState(data_loaded=True))
        result = tool.execute(study=None, freq=50.0)
        _assert_success(result, "Applied notch filter at 50.0 Hz.")

    def test_resample_success(self):
        tool = MockResampleTool(MockWorkflowState(data_loaded=True))
        result = tool.execute(study=None, rate=256)
        _assert_success(result, "Resampled data to 256 Hz.")

    def test_normalize_success(self):
        tool = MockNormalizeTool(MockWorkflowState(data_loaded=True))
        result = tool.execute(study=None, method="z-score")
        _assert_success(result, "Normalized data using z-score method.")

    def test_rereference_success(self):
        tool = MockRereferenceTool(MockWorkflowState(data_loaded=True))
        result = tool.execute(study=None, method="average")
        _assert_success(result, "Re-referenced data to average.")

    def test_channel_selection_success(self):
        tool = MockChannelSelectionTool(MockWorkflowState(data_loaded=True))
        result = tool.execute(study=None, channels=["C3", "C4", "Cz"])
        _assert_success(result, "Selected 3 channels.")

    def test_set_montage_success(self):
        tool = MockSetMontageTool(MockWorkflowState(data_loaded=True))
        result = tool.execute(study=None, montage_name="standard_1020")
        _assert_success(result, "Set montage to standard_1020.")


class TestMockDatasetSuccess:
    """Test mock dataset tools succeed with valid params."""

    def test_list_files_success(self):
        tool = MockListFilesTool()
        result = tool.execute(study=None, directory="/data", pattern="*.gdf")
        _assert_success(
            result,
            "Found 2 file(s) matching *.gdf.",
            payload=["A01T.gdf", "A02T.gdf"],
        )

    def test_load_data_success(self):
        tool = MockLoadDataTool(MockWorkflowState())
        result = tool.execute(study=None, paths=["/data/A01T.gdf"])

        assert isinstance(result, ToolResult)
        assert result.ok is True
        assert "Successfully loaded data from 1 sources" in result.message
        assert "A01T.gdf" in result.message
        assert "/data/A01T.gdf" in result.message
        assert result.payload is None
        assert result.error_type == "none"
        assert result.recoverable is True

    def test_attach_labels_success(self):
        tool = MockAttachLabelsTool()
        result = tool.execute(study=None, mapping={"A01T.gdf": "A01T_labels.csv"})
        _assert_success(result, "Attached labels to 1 files.")


class TestMockTrainingSuccess:
    """Test mock training tools succeed with valid params."""

    def test_set_model_success(self):
        tool = MockSetModelTool(MockWorkflowState())
        result = tool.execute(study=None, model_name="EEGNet")
        _assert_success(result, "Model set to EEGNet.")

    def test_configure_training_success(self):
        tool = MockConfigureTrainingTool(MockWorkflowState())
        result = tool.execute(study=None, epoch=100, learning_rate=0.001, batch_size=32)
        _assert_success(
            result,
            (
                "Training configured (Training epochs: 100, LR: 0.001, Device: cpu, "
                "Optim: adam, Ckt: 0)."
            ),
        )

    def test_start_training_success_with_explicit_ready_state(self):
        state = MockWorkflowState(
            dataset_generated=True,
            model_name="EEGNet",
            training_options_configured=True,
        )

        result = MockStartTrainingTool(state).execute(study=None, confirmed=True)

        _assert_success(
            result,
            "Training started. (Mock: Training completed successfully.)",
        )


class TestMockUIControlSuccess:
    """Test mock UI control tool paths."""

    def test_switch_panel_no_view_mode(self):
        tool = MockSwitchPanelTool()
        result = tool.execute(study=None, panel_name="training", view_mode=None)
        assert isinstance(result, UiRequest)
        assert result.kind.value == "switch_panel"
        assert result.params == {"panel": "training", "view_mode": None}
