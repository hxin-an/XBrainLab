from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.application import (
    AttachLabelsCommand,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    EvaluateCommand,
    GenerateDatasetCommand,
    LoadDataCommand,
    PreprocessCommand,
    PreprocessOperation,
    QueryStateCommand,
    ResetSessionCommand,
    SaliencyCommand,
    TrainCommand,
    VisualizeCommand,
)
from XBrainLab.llm.tools.real.analysis_real import (
    RealEvaluateTool,
    RealSaliencyTool,
    RealVisualizeTool,
)
from XBrainLab.llm.tools.real.dataset_real import (
    RealAttachLabelsTool,
    RealClearDatasetTool,
    RealGenerateDatasetTool,
    RealGetDatasetInfoTool,
    RealListFilesTool,
    RealLoadDataTool,
)
from XBrainLab.llm.tools.real.preprocess_real import (
    RealBandPassFilterTool,
    RealChannelSelectionTool,
    RealEpochDataTool,
    RealNormalizeTool,
    RealNotchFilterTool,
    RealRereferenceTool,
    RealResampleTool,
    RealSetMontageTool,
    RealStandardPreprocessTool,
)
from XBrainLab.llm.tools.real.training_real import (
    RealConfigureTrainingTool,
    RealSetModelTool,
    RealStartTrainingTool,
)
from XBrainLab.llm.tools.real.ui_control_real import RealSwitchPanelTool


@pytest.fixture
def mock_study():
    study = MagicMock()
    study.loaded_data_list = []
    study.output_dir = "./mock_output"
    return study


def _command_result(
    message: str = "ok",
    diagnostics: dict | None = None,
    *,
    failed: bool = False,
):
    result = MagicMock()
    result.message = message
    result.diagnostics = diagnostics or {}
    result.failed = failed
    result.ok = not failed
    return result


def _service(*results):
    service = MagicMock()
    service.preprocess.batch_notifications.return_value = nullcontext()
    if len(results) == 1:
        service.execute.return_value = results[0]
    elif results:
        service.execute.side_effect = list(results)
    else:
        service.execute.return_value = _command_result()
    return service


class TestRealTrainingTools:
    def test_set_model_success(self, mock_study):
        tool = RealSetModelTool()
        service = _service(_command_result())
        with patch(
            "XBrainLab.llm.tools.real.training_real.get_application_service",
            return_value=service,
        ):
            result = tool.execute(mock_study, model_name="EEGNet")

            assert "successfully set to EEGNet" in result
            command = service.execute.call_args.args[0]
            assert isinstance(command, ConfigureTrainingCommand)
            assert command.model_name == "EEGNet"

    def test_set_model_unknown(self, mock_study):
        tool = RealSetModelTool()
        service = _service(_command_result("Unknown model", failed=True))
        with patch(
            "XBrainLab.llm.tools.real.training_real.get_application_service",
            return_value=service,
        ):
            result = tool.execute(mock_study, model_name="UnknownModel")
            assert "Failed to set model" in result

    def test_configure_and_start_training(self, mock_study):
        config_tool = RealConfigureTrainingTool()
        start_tool = RealStartTrainingTool()
        service = _service(_command_result())

        with patch(
            "XBrainLab.llm.tools.real.training_real.get_application_service",
            return_value=service,
        ):
            # Configure
            res1 = config_tool.execute(
                mock_study,
                epoch=10,
                batch_size=32,
                learning_rate=0.001,
                optimizer="sgd",
                save_checkpoints_every=5,
                output_dir="/tmp/xbrainlab-training-output",
            )
            assert "Training configured" in res1
            command = service.execute.call_args.args[0]
            assert isinstance(command, ConfigureTrainingCommand)
            assert command.optimizer == "sgd"
            assert command.save_checkpoints_every == 5
            assert command.output_dir == "/tmp/xbrainlab-training-output"

            # Start
            res2 = start_tool.execute(mock_study)
            assert "started successfully" in res2
            train_command = service.execute.call_args.args[0]
            assert isinstance(train_command, TrainCommand)
            assert train_command.append is True
            assert train_command.interactive is True

            res3 = start_tool.execute(
                mock_study,
                confirmed=True,
                append=False,
                interactive=False,
            )
            assert "started successfully" in res3
            train_command = service.execute.call_args.args[0]
            assert isinstance(train_command, TrainCommand)
            assert train_command.confirmed is True
            assert train_command.append is False
            assert train_command.interactive is False


class TestRealAnalysisTools:
    def test_evaluate_visualize_and_saliency_route_to_service(self, mock_study):
        evaluate = RealEvaluateTool()
        visualize = RealVisualizeTool()
        saliency = RealSaliencyTool()
        service = _service(
            _command_result("Evaluation summary ready."),
            _command_result("Visualization summary ready."),
            _command_result("Saliency summary ready."),
        )

        with patch(
            "XBrainLab.llm.tools.real.analysis_real.get_application_service",
            return_value=service,
        ):
            assert "Evaluation" in evaluate.execute(mock_study, target="latest")
            assert "Visualization" in visualize.execute(mock_study, view="summary")
            assert "Saliency" in saliency.execute(
                mock_study,
                method="Gradient",
                params={"absolute": True},
            )

            evaluate_command = service.execute.call_args_list[0].args[0]
            visualize_command = service.execute.call_args_list[1].args[0]
            saliency_command = service.execute.call_args_list[2].args[0]
            assert isinstance(evaluate_command, EvaluateCommand)
            assert isinstance(visualize_command, VisualizeCommand)
            assert isinstance(saliency_command, SaliencyCommand)
            assert evaluate_command.target == "latest"
            assert visualize_command.view == "summary"
            assert saliency_command.method == "Gradient"
            assert saliency_command.params == {"absolute": True}


class TestRealDatasetTools:
    def test_list_files(self, mock_study):
        tool = RealListFilesTool()
        with (
            patch("os.listdir", return_value=["A.gdf", "B.txt"]),
            patch("os.path.isdir", return_value=True),
        ):
            res = tool.execute(mock_study, directory="/mock_dir", pattern="*.gdf")
            assert "A.gdf" in res
            assert "B.txt" not in res

    def test_load_data(self, mock_study):
        tool = RealLoadDataTool()
        service = _service(_command_result(diagnostics={"success_count": 1}))
        with patch(
            "XBrainLab.llm.tools.real.dataset_real.get_application_service",
            return_value=service,
        ):
            res = tool.execute(mock_study, paths=["/data/A.gdf"])

            assert "Successfully loaded 1 files" in res
            command = service.execute.call_args.args[0]
            assert isinstance(command, LoadDataCommand)
            assert command.paths == ["/data/A.gdf"]

    def test_attach_labels(self, mock_study):
        tool = RealAttachLabelsTool()
        service = _service(_command_result(diagnostics={"success_count": 1}))
        with patch(
            "XBrainLab.llm.tools.real.dataset_real.get_application_service",
            return_value=service,
        ):
            res = tool.execute(mock_study, mapping={"A.gdf": "/labels/A.mat"})
            assert "Attached labels to 1 files" in res
            command = service.execute.call_args.args[0]
            assert isinstance(command, AttachLabelsCommand)
            assert command.mapping == {"A.gdf": "/labels/A.mat"}

    def test_clear_dataset(self, mock_study):
        tool = RealClearDatasetTool()
        service = _service(_command_result())
        with patch(
            "XBrainLab.llm.tools.real.dataset_real.get_application_service",
            return_value=service,
        ):
            res = tool.execute(mock_study)
            assert "Dataset cleared" in res
            command = service.execute.call_args.args[0]
            assert isinstance(command, ResetSessionCommand)
            assert command.confirmed is True

    def test_get_dataset_info(self, mock_study):
        tool = RealGetDatasetInfoTool()
        service = _service(
            _command_result(
                diagnostics={
                    "count": 1,
                    "files": ["A.gdf"],
                    "total": 100,
                    "unique_count": 2,
                    "unique_labels": ["769", "770"],
                    "gdf_duplicate_channel_details": [
                        {
                            "file": "A.gdf",
                            "generated_bases": ["EEG"],
                            "generated_channels": ["EEG-0", "EEG-1"],
                            "message": "detail message",
                        },
                    ],
                },
            ),
        )
        with patch(
            "XBrainLab.llm.tools.real.dataset_real.get_application_service",
            return_value=service,
        ):
            res = tool.execute(mock_study)
            assert "Loaded 1 files" in res
            assert "Events: 100" in res
            assert "Diagnostics:" in res
            assert "GDF duplicate-channel ambiguity: A.gdf (bases: EEG)" in res
            command = service.execute.call_args.args[0]
            assert isinstance(command, QueryStateCommand)
            assert command.query == "data_summary"

    def test_generate_dataset(self, mock_study):
        tool = RealGenerateDatasetTool()
        service = _service(_command_result(diagnostics={"dataset_count": 2}))

        with patch(
            "XBrainLab.llm.tools.real.dataset_real.get_application_service",
            return_value=service,
        ):
            res = tool.execute(mock_study, test_ratio=0.1, val_ratio=0.1)

            assert "Dataset successfully generated" in res
            assert "Count: 2" in res
            command = service.execute.call_args.args[0]
            assert isinstance(command, GenerateDatasetCommand)
            assert command.test_ratio == 0.1
            assert command.val_ratio == 0.1


class TestRealPreprocessTools:
    def test_bandpass_filter(self, mock_study):
        tool = RealBandPassFilterTool()
        service = _service(_command_result())
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.get_application_service",
            return_value=service,
        ):
            res = tool.execute(mock_study, low_freq=1, high_freq=30)

            assert "Applied Bandpass Filter" in res
            command = service.execute.call_args.args[0]
            assert isinstance(command, PreprocessCommand)
            assert command.operation == PreprocessOperation.BANDPASS
            assert command.low_freq == 1
            assert command.high_freq == 30

    def test_standard_preprocess(self, mock_study):
        tool = RealStandardPreprocessTool()
        service = _service(_command_result())
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.get_application_service",
            return_value=service,
        ):
            res = tool.execute(mock_study, l_freq=4, h_freq=40)

            assert "Standard preprocessing applied" in res
            operations = [
                call.args[0].operation
                for call in service.execute.call_args_list
                if isinstance(call.args[0], PreprocessCommand)
            ]
            assert PreprocessOperation.BANDPASS in operations
            assert PreprocessOperation.NOTCH in operations

    def test_notch_filter(self, mock_study):
        tool = RealNotchFilterTool()
        service = _service(_command_result())
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.get_application_service",
            return_value=service,
        ):
            res = tool.execute(mock_study, freq=50)
            assert "Applied Notch Filter" in res
            command = service.execute.call_args.args[0]
            assert isinstance(command, PreprocessCommand)
            assert command.operation == PreprocessOperation.NOTCH
            assert command.notch_freq == 50

    def test_resample(self, mock_study):
        tool = RealResampleTool()
        service = _service(_command_result())
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.get_application_service",
            return_value=service,
        ):
            res = tool.execute(mock_study, rate=128)
            assert "Resampled" in res
            command = service.execute.call_args.args[0]
            assert isinstance(command, PreprocessCommand)
            assert command.operation == PreprocessOperation.RESAMPLE
            assert command.rate == 128

    def test_normalize(self, mock_study):
        tool = RealNormalizeTool()
        service = _service(_command_result())
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.get_application_service",
            return_value=service,
        ):
            res = tool.execute(mock_study, method="z-score")
            assert "Normalized" in res
            command = service.execute.call_args.args[0]
            assert isinstance(command, PreprocessCommand)
            assert command.operation == PreprocessOperation.NORMALIZE
            assert command.method == "z-score"

    def test_rereference(self, mock_study):
        tool = RealRereferenceTool()
        service = _service(_command_result())
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.get_application_service",
            return_value=service,
        ):
            res = tool.execute(mock_study, method="CAR")
            assert "Applied reference" in res
            command = service.execute.call_args_list[0].args[0]
            assert isinstance(command, PreprocessCommand)
            assert command.operation == PreprocessOperation.REREFERENCE
            assert command.method == "CAR"

    def test_channel_selection(self, mock_study):
        tool = RealChannelSelectionTool()
        service = _service(_command_result())
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.get_application_service",
            return_value=service,
        ):
            res = tool.execute(mock_study, channels=["C3", "C4"])
            assert "Selected 2 channels" in res
            command = service.execute.call_args_list[0].args[0]
            assert isinstance(command, PreprocessCommand)
            assert command.operation == PreprocessOperation.SELECT_CHANNELS
            assert command.channels == ["C3", "C4"]

    def test_channel_selection_surfaces_gdf_ambiguity(self, mock_study):
        tool = RealChannelSelectionTool()
        service = _service(
            _command_result(),
            _command_result(
                diagnostics={
                    "gdf_duplicate_channel_details": [
                        {
                            "file": "A01T.gdf",
                            "generated_bases": ["EEG"],
                            "generated_channels": ["EEG-0", "EEG-1"],
                        },
                    ],
                },
            ),
        )
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.get_application_service",
            return_value=service,
        ):
            res = tool.execute(mock_study, channels=["C3", "C4"])

            assert "Selected 2 channels" in res
            assert "GDF duplicate-channel ambiguity remains for A01T.gdf" in res

    def test_epoch_data(self, mock_study):
        tool = RealEpochDataTool()
        service = _service(_command_result())
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.get_application_service",
            return_value=service,
        ):
            res = tool.execute(mock_study, t_min=0, t_max=4, event_id=None)
            assert "Data epoched" in res
            command = service.execute.call_args.args[0]
            assert isinstance(command, CreateEpochCommand)
            assert command.t_min == 0
            assert command.t_max == 4

    def test_set_montage(self, mock_study):
        tool = RealSetMontageTool()
        # Note: RealSetMontageTool now returns a confirmation request (human-in-the-loop)
        # instead of auto-applying

        service = _service(_command_result())
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.get_application_service",
            return_value=service,
        ):
            res = tool.execute(mock_study, montage_name="standard_1020")

        # Verify the confirmation request format
        assert "confirm_montage 'standard_1020'" in res
        command = service.execute.call_args.args[0]
        assert isinstance(command, QueryStateCommand)
        assert command.query == "preprocess_diagnostics"

    def test_set_montage_surfaces_gdf_ambiguity(self, mock_study):
        tool = RealSetMontageTool()
        service = _service(
            _command_result(
                diagnostics={
                    "gdf_duplicate_channel_details": [
                        {
                            "file": "A01T.gdf",
                            "generated_bases": ["EEG"],
                            "generated_channels": ["EEG-0", "EEG-1"],
                        },
                    ],
                },
            ),
        )
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.get_application_service",
            return_value=service,
        ):
            res = tool.execute(mock_study, montage_name="standard_1020")

            assert "confirm_montage 'standard_1020'" in res
            assert "GDF duplicate-channel ambiguity remains for A01T.gdf" in res


class TestRealUIControlTools:
    def test_switch_panel(self, mock_study):
        tool = RealSwitchPanelTool()
        res = tool.execute(mock_study, panel_name="Training")
        assert res == "Request: Switch UI to 'Training'"
