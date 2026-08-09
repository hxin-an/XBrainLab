"""Unit tests for LLM mock tools — verify correct mock responses."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from XBrainLab.llm.tools.mock.analysis_mock import (
    MockEvaluateTool,
    MockSaliencyTool,
    MockVisualizeTool,
)
from XBrainLab.llm.tools.mock.dataset_mock import (
    MockApplyInterpretationTool,
    MockAttachLabelsTool,
    MockClearDatasetTool,
    MockGenerateDatasetTool,
    MockGetDatasetInfoTool,
    MockListFilesTool,
    MockLoadDataTool,
    MockPreviewInterpretationTool,
    MockQueryStateTool,
    MockReloadInterpretationRecipeTool,
    MockSaveInterpretationRecipeTool,
    MockScanSourceTool,
    MockValidateInterpretationTool,
)
from XBrainLab.llm.tools.mock.preprocess_mock import (
    MockBandPassFilterTool,
    MockChannelSelectionTool,
    MockEpochDataTool,
    MockNormalizeTool,
    MockNotchFilterTool,
    MockRereferenceTool,
    MockResampleTool,
    MockResetPreprocessTool,
    MockSetMontageTool,
    MockStandardPreprocessTool,
)
from XBrainLab.llm.tools.mock.state import MockWorkflowState
from XBrainLab.llm.tools.mock.training_mock import (
    MockConfigureTrainingTool,
    MockSetModelTool,
    MockStartTrainingTool,
    MockStopTrainingTool,
)
from XBrainLab.llm.tools.mock.ui_control_mock import MockSwitchPanelTool
from XBrainLab.llm.tools.result_contract import ToolResult, UiRequest


def _assert_tool_result(
    result: object,
    *,
    ok: bool,
    message: str,
    payload: object | None = None,
    error_type: str = "none",
    recoverable: bool = True,
) -> None:
    assert isinstance(result, ToolResult)
    assert result.ok is ok
    assert result.message == message
    assert result.payload == payload
    assert result.error_type == error_type
    assert result.recoverable is recoverable


def _require_tool_result(result: object) -> ToolResult:
    assert isinstance(result, ToolResult)
    return result


@pytest.fixture
def study():
    return MagicMock()


class TestDatasetMocks:
    def test_list_files(self, study):
        result = MockListFilesTool().execute(study, directory="/data")
        _assert_tool_result(
            result,
            ok=True,
            message="Found 2 file(s) matching *.",
            payload=["A01T.gdf", "A02T.gdf"],
        )

        missing_directory = MockListFilesTool().execute(study)
        _assert_tool_result(
            missing_directory,
            ok=False,
            message="A folder path is required.",
            error_type="input",
        )

    def test_load_data(self, study):
        state = MockWorkflowState(
            data_loaded=True,
            epochs_ready=True,
            dataset_generated=True,
        )
        result = MockLoadDataTool(state).execute(study, paths=["/data/f.gdf"])
        assert isinstance(result, ToolResult)
        assert result.ok is True
        assert "Successfully loaded data from 1 sources" in result.message
        assert "f.gdf" in result.message
        assert "/data/f.gdf" in result.message
        assert result.payload is None
        assert result.error_type == "none"
        assert result.recoverable is True
        assert state.data_loaded is True
        assert state.epochs_ready is False
        assert state.dataset_generated is False

        missing_paths = MockLoadDataTool(state).execute(study)
        _assert_tool_result(
            missing_paths,
            ok=False,
            message="Error: paths list is required",
            error_type="input",
        )

    def test_data_interpretation_tools(self, study):
        state = MockWorkflowState(
            epochs_ready=True,
            dataset_generated=True,
        )
        scan_result = MockScanSourceTool().execute(study, source_path="/data")
        assert isinstance(scan_result, ToolResult)
        assert scan_result.ok is True
        assert "Scanned /data" in scan_result.message
        assert "as auto; found 1 EEG file." in scan_result.message
        assert "/data" in scan_result.message
        assert scan_result.payload is None
        assert scan_result.error_type == "none"
        assert scan_result.recoverable is True
        _assert_tool_result(
            MockScanSourceTool().execute(study),
            ok=False,
            message="Error: source_path is required",
            error_type="input",
        )
        _assert_tool_result(
            MockPreviewInterpretationTool().execute(study),
            ok=True,
            message="Interpretation preview ready for latest scan.",
        )
        _assert_tool_result(
            MockValidateInterpretationTool().execute(study),
            ok=True,
            message="Interpretation validation for latest candidate: safe.",
        )
        _assert_tool_result(
            MockApplyInterpretationTool(state).execute(study, confirmed=True),
            ok=True,
            message=("Applied interpretation for latest candidate with confirmation."),
        )
        assert state.data_loaded is True
        assert state.epochs_ready is False
        assert state.dataset_generated is False
        saved = MockSaveInterpretationRecipeTool().execute(
            study,
            recipe_path="/tmp/import.json",
        )
        reloaded = MockReloadInterpretationRecipeTool().execute(
            study,
            recipe_path="/tmp/import.json",
        )
        for result, action in ((saved, "saved to"), (reloaded, "reloaded from")):
            assert isinstance(result, ToolResult)
            assert result.ok is True
            assert f"Interpretation recipe {action}" in result.message
            assert "import.json" in result.message
            assert "/tmp/import.json" in result.message
            assert result.payload is None
            assert result.error_type == "none"
            assert result.recoverable is True
        _assert_tool_result(
            MockReloadInterpretationRecipeTool().execute(study),
            ok=False,
            message="Error: recipe_path is required",
            error_type="input",
        )

    def test_attach_labels(self, study):
        result = MockAttachLabelsTool().execute(
            study, mapping={"file.gdf": "/labels.mat"}
        )
        _assert_tool_result(
            result,
            ok=True,
            message="Attached labels to 1 files.",
        )

        missing_mapping = MockAttachLabelsTool().execute(study)
        _assert_tool_result(
            missing_mapping,
            ok=False,
            message="Error: mapping is required",
            error_type="input",
        )

    def test_clear_dataset(self, study):
        state = MockWorkflowState(
            data_loaded=True,
            epochs_ready=True,
            dataset_generated=True,
            model_name="EEGNet",
            training_options_configured=True,
        )

        unconfirmed = MockClearDatasetTool(state).execute(study)

        assert unconfirmed.ok is False
        assert unconfirmed.error_type == "confirmation_required"
        assert state.data_loaded is True
        assert state.dataset_generated is True

        result = MockClearDatasetTool(state).execute(study, confirmed=True)
        _assert_tool_result(result, ok=True, message="Dataset cleared.")
        assert state.data_loaded is False
        assert state.epochs_ready is False
        assert state.dataset_generated is False
        assert state.model_name is None
        assert state.training_options_configured is False

    def test_clear_dataset_rejects_non_boolean_confirmation(self, study):
        state = MockWorkflowState(data_loaded=True)

        result = MockClearDatasetTool(state).execute(study, confirmed="true")

        assert result.ok is False
        assert result.error_type == "input"
        assert "must be a boolean" in result.message
        assert state.data_loaded is True

    def test_get_dataset_info(self, study):
        result = MockGetDatasetInfoTool().execute(study)
        _assert_tool_result(
            result,
            ok=True,
            message="Dataset Info: 2 files loaded, 250Hz, 22 channels.",
            payload={
                "count": 2,
                "sampling_rate": 250,
                "channels": 22,
            },
        )

    def test_query_state(self, study):
        result = MockQueryStateTool().execute(study)
        _assert_tool_result(
            result,
            ok=True,
            message="No data loaded. Next: Scan data source.",
        )

    def test_generate_dataset(self, study):
        state = MockWorkflowState(epochs_ready=True)
        result = MockGenerateDatasetTool(state).execute(
            study, split_strategy="trial", training_mode="group"
        )
        _assert_tool_result(
            result,
            ok=True,
            message="Generated dataset (Split: trial, Mode: group).",
        )
        assert state.dataset_generated is True

    def test_generate_dataset_requires_epochs(self, study):
        state = MockWorkflowState(data_loaded=True)

        result = MockGenerateDatasetTool(state).execute(study)

        assert result.ok is False
        assert result.error_type == "precondition"
        assert result.recoverable is True
        assert state.dataset_generated is False


class TestPreprocessMocks:
    def test_reset_preprocess_preserves_loaded_raw_state(self, study):
        state = MockWorkflowState(
            data_loaded=True,
            epochs_ready=True,
            dataset_generated=True,
            model_name="EEGNet",
            training_options_configured=True,
        )

        result = MockResetPreprocessTool(state).execute(study, confirmed=True)

        assert result.ok is True
        assert state.data_loaded is True
        assert state.epochs_ready is False
        assert state.dataset_generated is False
        assert state.model_name is None
        assert state.training_options_configured is False

    @pytest.mark.parametrize(
        ("tool_type", "params"),
        [
            (MockStandardPreprocessTool, {}),
            (MockBandPassFilterTool, {"low_freq": 1, "high_freq": 40}),
            (MockNotchFilterTool, {"freq": 50}),
            (MockResampleTool, {"rate": 128}),
            (MockNormalizeTool, {"method": "z-score"}),
            (MockRereferenceTool, {"method": "average"}),
            (MockChannelSelectionTool, {"channels": ["C3", "C4"]}),
            (MockSetMontageTool, {"montage_name": "standard_1020"}),
        ],
    )
    def test_preprocess_requires_loaded_data(self, study, tool_type, params):
        state = MockWorkflowState()

        result = tool_type(state).execute(study, **params)

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
            (MockChannelSelectionTool, "Error: channels list is required"),
            (MockSetMontageTool, "Error: montage_name is required"),
        ],
    )
    def test_preprocess_missing_parameters_return_typed_input_failure(
        self,
        tool_type,
        message,
    ):
        result = tool_type(MockWorkflowState(data_loaded=True)).execute(object())

        _assert_tool_result(
            result,
            ok=False,
            message=message,
            error_type="input",
        )

    def test_standard_preprocess(self, study):
        result = MockStandardPreprocessTool(
            MockWorkflowState(data_loaded=True)
        ).execute(study)
        _assert_tool_result(
            result,
            ok=True,
            message=(
                "Applied standard preprocessing pipeline (BP: 4.0-40.0Hz, "
                "Notch: 50.0Hz)."
            ),
        )

    def test_bandpass(self, study):
        result = MockBandPassFilterTool(MockWorkflowState(data_loaded=True)).execute(
            study, low_freq=1, high_freq=40
        )
        _assert_tool_result(
            result,
            ok=True,
            message="Applied bandpass filter (1-40 Hz).",
        )

    def test_notch(self, study):
        result = MockNotchFilterTool(MockWorkflowState(data_loaded=True)).execute(
            study,
            freq=50,
        )
        _assert_tool_result(
            result,
            ok=True,
            message="Applied notch filter at 50 Hz.",
        )

    def test_resample(self, study):
        result = MockResampleTool(MockWorkflowState(data_loaded=True)).execute(
            study,
            rate=128,
        )
        _assert_tool_result(result, ok=True, message="Resampled data to 128 Hz.")

    def test_normalize(self, study):
        result = MockNormalizeTool(MockWorkflowState(data_loaded=True)).execute(
            study,
            method="z-score",
        )
        _assert_tool_result(
            result,
            ok=True,
            message="Normalized data using z-score method.",
        )

    def test_rereference(self, study):
        result = MockRereferenceTool(MockWorkflowState(data_loaded=True)).execute(
            study,
            method="average",
        )
        _assert_tool_result(
            result,
            ok=True,
            message="Re-referenced data to average.",
        )

    def test_channel_selection(self, study):
        result = MockChannelSelectionTool(MockWorkflowState(data_loaded=True)).execute(
            study, channels=["Cz", "Fz"]
        )
        _assert_tool_result(result, ok=True, message="Selected 2 channels.")

    def test_set_montage(self, study):
        result = MockSetMontageTool(MockWorkflowState(data_loaded=True)).execute(
            study,
            montage_name="standard_1020",
        )
        _assert_tool_result(
            result,
            ok=True,
            message="Set montage to standard_1020.",
        )

    def test_epoch_data(self, study):
        state = MockWorkflowState(data_loaded=True, dataset_generated=True)
        result = MockEpochDataTool(state).execute(study, t_min=-0.5, t_max=1.0)
        _assert_tool_result(
            result,
            ok=True,
            message="Created EEG epochs from -0.5s to 1.0s.",
        )
        assert state.epochs_ready is True
        assert state.dataset_generated is False

    def test_epoch_data_requires_loaded_data(self, study):
        state = MockWorkflowState()

        result = MockEpochDataTool(state).execute(study, t_min=-0.5, t_max=1.0)

        assert result.ok is False
        assert result.error_type == "precondition"
        assert result.recoverable is True
        assert state.epochs_ready is False


class TestTrainingMocks:
    def test_stop_training_only_stops_an_active_mock_run(self, study):
        state = MockWorkflowState(training_running=True)

        result = MockStopTrainingTool(state).execute(study)

        assert result.ok is True
        assert state.training_running is False
        blocked = MockStopTrainingTool(state).execute(study)
        assert blocked.ok is False
        assert blocked.error_type == "precondition"

    def test_set_model(self, study):
        state = MockWorkflowState()
        result = MockSetModelTool(state).execute(study, model_name="EEGNet")
        _assert_tool_result(result, ok=True, message="Model set to EEGNet.")
        assert state.model_name == "EEGNet"

        missing_model = MockSetModelTool(state).execute(study)
        _assert_tool_result(
            missing_model,
            ok=False,
            message="Error: model_name is required",
            error_type="input",
        )

        unsupported_model = MockSetModelTool(state).execute(
            study,
            model_name="UnsupportedNet",
        )
        assert unsupported_model.ok is False
        assert unsupported_model.error_type == "input"
        assert state.model_name == "EEGNet"

    def test_training_choices_match_real_case_insensitive_contract(self, study):
        state = MockWorkflowState()

        model_result = MockSetModelTool(state).execute(study, model_name="eegnet")
        configure_result = MockConfigureTrainingTool(state).execute(
            study,
            epoch=10,
            batch_size=32,
            learning_rate=0.001,
            device="CPU",
            optimizer="AdamW",
            evaluation_option="VAL_AUC",
        )

        assert model_result.ok is True
        assert configure_result.ok is True
        assert state.model_name == "EEGNet"
        assert state.training_options_configured is True

    def test_configure_training(self, study):
        state = MockWorkflowState()
        result = MockConfigureTrainingTool(state).execute(
            study,
            model_name="EEGNet",
            epoch=100,
            batch_size=32,
            learning_rate=0.001,
            evaluation_option="last_epoch",
        )
        _assert_tool_result(
            result,
            ok=True,
            message=(
                "Training configured (Training epochs: 100, LR: 0.001, Device: cpu, "
                "Optim: adam, Ckt: 0)."
            ),
        )
        assert state.model_name == "EEGNet"
        assert state.training_options_configured is True

        missing_options = MockConfigureTrainingTool(state).execute(study)
        _assert_tool_result(
            missing_options,
            ok=False,
            message=(
                "Missing required training parameter(s): epoch, batch_size, "
                "learning_rate."
            ),
            error_type="input",
        )

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("device", "tpu"),
            ("optimizer", "rmsprop"),
            ("evaluation_option", "test_accuracy"),
        ],
    )
    def test_configure_training_rejects_unsupported_choices_atomically(
        self,
        study,
        field: str,
        value: str,
    ) -> None:
        state = MockWorkflowState(
            model_name="SCCNet",
            training_options_configured=False,
        )
        params: dict[str, Any] = {
            "model_name": "EEGNet",
            "epoch": 10,
            "batch_size": 32,
            "learning_rate": 0.001,
            field: value,
        }

        result = MockConfigureTrainingTool(state).execute(study, **params)

        assert result.ok is False
        assert result.error_type == "input"
        assert field in result.message
        assert state.model_name == "SCCNet"
        assert state.training_options_configured is False

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("repeat", 0),
            ("repeat", 1.75),
            ("save_checkpoints_every", -1),
            ("save_checkpoints_every", 2.9),
        ],
    )
    def test_configure_training_rejects_invalid_optional_integers(
        self,
        study,
        field: str,
        value: object,
    ) -> None:
        params: dict[str, Any] = {
            "epoch": 10,
            "batch_size": 32,
            "learning_rate": 0.001,
            field: value,
        }

        state = MockWorkflowState()
        result = MockConfigureTrainingTool(state).execute(study, **params)

        assert result.ok is False
        assert result.error_type == "input"
        assert field in result.message
        assert state.training_options_configured is False

    def test_start_training(self, study):
        blocked_state = MockWorkflowState()
        blocked = MockStartTrainingTool(blocked_state).execute(study)
        assert blocked.ok is False
        assert blocked.error_type == "precondition"
        assert blocked.recoverable is True
        assert "dataset" in blocked.message.lower()
        assert "model" in blocked.message.lower()
        assert "training" in blocked.message.lower()

        ready_state = MockWorkflowState(
            dataset_generated=True,
            model_name="EEGNet",
            training_options_configured=True,
        )
        unconfirmed = MockStartTrainingTool(ready_state).execute(study)
        assert unconfirmed.ok is False
        assert unconfirmed.error_type == "confirmation_required"

        invalid_confirmation = MockStartTrainingTool(ready_state).execute(
            study,
            confirmed="true",
        )
        assert invalid_confirmation.ok is False
        assert invalid_confirmation.error_type == "input"

        result = MockStartTrainingTool(ready_state).execute(study, confirmed=True)
        _assert_tool_result(
            result,
            ok=True,
            message="Training started. (Mock: Training completed successfully.)",
        )

    def test_get_all_mock_tools_share_one_workflow_state(self, study):
        from XBrainLab.llm.tools import get_all_tools

        tools = {tool.name: tool for tool in get_all_tools(mode="mock")}

        assert _require_tool_result(tools["start_training"].execute(study)).ok is False
        assert _require_tool_result(
            tools["scan_source"].execute(study, source_path="/data/A01T.gdf")
        ).ok
        assert _require_tool_result(tools["preview_interpretation"].execute(study)).ok
        assert _require_tool_result(tools["validate_interpretation"].execute(study)).ok
        assert _require_tool_result(
            tools["apply_interpretation"].execute(study, confirmed=True)
        ).ok
        assert _require_tool_result(
            tools["epoch_data"].execute(study, t_min=-0.5, t_max=1.0)
        ).ok
        assert _require_tool_result(tools["generate_dataset"].execute(study)).ok
        assert _require_tool_result(
            tools["set_model"].execute(study, model_name="EEGNet")
        ).ok
        assert _require_tool_result(
            tools["configure_training"].execute(
                study,
                epoch=10,
                batch_size=32,
                learning_rate=0.001,
            )
        ).ok
        assert _require_tool_result(
            tools["start_training"].execute(study, confirmed=True)
        ).ok
        assert _require_tool_result(
            tools["clear_dataset"].execute(study, confirmed=True)
        ).ok
        cleared_start = _require_tool_result(tools["start_training"].execute(study))
        assert cleared_start.ok is False
        assert cleared_start.error_type == "precondition"


class TestAnalysisMocks:
    def test_evaluate(self, study):
        result = MockEvaluateTool().execute(study)
        _assert_tool_result(
            result,
            ok=True,
            message="Evaluation summary ready.",
        )

    def test_visualize(self, study):
        result = MockVisualizeTool().execute(study, view="summary")
        _assert_tool_result(
            result,
            ok=True,
            message="Visualization summary ready: summary.",
        )

    def test_saliency(self, study):
        _assert_tool_result(
            MockSaliencyTool().execute(study, method="Gradient"),
            ok=True,
            message="Saliency readiness checked with Gradient.",
        )
        _assert_tool_result(
            MockSaliencyTool().execute(study, nt_samples=8),
            ok=True,
            message="Saliency readiness checked with custom parameters.",
        )
        _assert_tool_result(
            MockSaliencyTool().execute(study),
            ok=True,
            message="Saliency readiness summary ready.",
        )


class TestUIControlMock:
    def test_switch_panel_basic(self, study):
        result = MockSwitchPanelTool().execute(study, panel_name="training")
        assert isinstance(result, UiRequest)
        assert result.kind.value == "switch_panel"
        assert result.params == {"panel": "training", "view_mode": None}

    def test_switch_panel_with_view_mode(self, study):
        result = MockSwitchPanelTool().execute(
            study, panel_name="visualization", view_mode="saliency_map"
        )
        assert isinstance(result, UiRequest)
        assert result.kind.value == "switch_panel"
        assert result.params == {
            "panel": "visualization",
            "view_mode": "saliency_map",
        }
