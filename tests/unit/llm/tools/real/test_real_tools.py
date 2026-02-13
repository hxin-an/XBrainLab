from unittest.mock import MagicMock, patch

import pytest

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


class TestRealTrainingTools:
    def test_set_model_success(self, mock_study):
        tool = RealSetModelTool()
        with patch(
            "XBrainLab.llm.tools.real.training_real.BackendFacade"
        ) as MockFacade:
            mock_facade = MockFacade.return_value
            result = tool.execute(mock_study, model_name="EEGNet")

            assert "successfully set to EEGNet" in result
            mock_facade.set_model.assert_called_once_with("EEGNet")

    def test_set_model_unknown(self, mock_study):
        tool = RealSetModelTool()
        with patch(
            "XBrainLab.llm.tools.real.training_real.BackendFacade"
        ) as MockFacade:
            mock_facade = MockFacade.return_value
            mock_facade.set_model.side_effect = ValueError("Unknown model")
            result = tool.execute(mock_study, model_name="UnknownModel")
            assert "Failed to set model" in result

    def test_configure_and_start_training(self, mock_study):
        config_tool = RealConfigureTrainingTool()
        start_tool = RealStartTrainingTool()

        with patch(
            "XBrainLab.llm.tools.real.training_real.BackendFacade"
        ) as MockFacade:
            mock_facade = MockFacade.return_value

            # Configure
            res1 = config_tool.execute(
                mock_study,
                epoch=10,
                batch_size=32,
                learning_rate=0.001,
                optimizer="sgd",
                save_checkpoints_every=5,
            )
            assert "Training configured" in res1
            # Verify passed params
            mock_facade.configure_training.assert_called_once()
            call_args = mock_facade.configure_training.call_args[1]
            assert call_args["optimizer"] == "sgd"
            assert call_args["save_checkpoints_every"] == 5

            # Start
            res2 = start_tool.execute(mock_study)
            assert "started successfully" in res2
            mock_facade.run_training.assert_called()


class TestRealDatasetTools:
    def test_list_files(self, mock_study):
        tool = RealListFilesTool()
        with (
            patch("os.listdir", return_value=["A.gdf", "B.txt"]),
            patch("os.path.exists", return_value=True),
        ):
            res = tool.execute(mock_study, directory="/mock_dir", pattern="*.gdf")
            assert "A.gdf" in res
            assert "B.txt" not in res

    def test_load_data(self, mock_study):
        tool = RealLoadDataTool()
        with patch("XBrainLab.llm.tools.real.dataset_real.BackendFacade") as MockFacade:
            mock_facade = MockFacade.return_value
            mock_facade.load_data.return_value = (1, [])

            res = tool.execute(mock_study, paths=["/data/A.gdf"])

            assert "Successfully loaded 1 files" in res
            mock_facade.load_data.assert_called_once_with(["/data/A.gdf"])

    def test_attach_labels(self, mock_study):
        tool = RealAttachLabelsTool()
        with patch("XBrainLab.llm.tools.real.dataset_real.BackendFacade") as MockFacade:
            mock_facade = MockFacade.return_value
            mock_facade.attach_labels.return_value = 1

            res = tool.execute(mock_study, mapping={"A.gdf": "/labels/A.mat"})
            assert "Attached labels to 1 files" in res
            mock_facade.attach_labels.assert_called_once_with(
                {"A.gdf": "/labels/A.mat"}
            )

    def test_clear_dataset(self, mock_study):
        tool = RealClearDatasetTool()
        with patch("XBrainLab.llm.tools.real.dataset_real.BackendFacade") as MockFacade:
            mock_facade = MockFacade.return_value
            res = tool.execute(mock_study)
            assert "Dataset cleared" in res
            mock_facade.clear_data.assert_called_once()

    def test_get_dataset_info(self, mock_study):
        tool = RealGetDatasetInfoTool()
        with patch("XBrainLab.llm.tools.real.dataset_real.BackendFacade") as MockFacade:
            mock_facade = MockFacade.return_value
            mock_facade.get_data_summary.return_value = {
                "count": 1,
                "files": ["A.gdf"],
                "total": 100,
                "unique_count": 2,
                "unique_labels": ["769", "770"],
            }

            res = tool.execute(mock_study)
            assert "Loaded 1 files" in res
            assert "Events: 100" in res

    def test_generate_dataset(self, mock_study):
        tool = RealGenerateDatasetTool()
        mock_study.datasets = ["ds1", "ds2"]

        with patch("XBrainLab.llm.tools.real.dataset_real.BackendFacade") as MockFacade:
            mock_facade = MockFacade.return_value

            res = tool.execute(mock_study, test_ratio=0.1, val_ratio=0.1)

            assert "Dataset successfully generated" in res
            assert "Count: 2" in res
            mock_facade.generate_dataset.assert_called_once()


class TestRealPreprocessTools:
    def test_bandpass_filter(self, mock_study):
        tool = RealBandPassFilterTool()
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.BackendFacade"
        ) as MockFacade:
            mock_facade = MockFacade.return_value
            res = tool.execute(mock_study, low_freq=1, high_freq=30)

            assert "Applied Bandpass Filter" in res
            mock_facade.apply_filter.assert_called_once_with(1, 30)

    def test_standard_preprocess(self, mock_study):
        tool = RealStandardPreprocessTool()
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.BackendFacade"
        ) as MockFacade:
            mock_facade = MockFacade.return_value
            res = tool.execute(mock_study, l_freq=4, h_freq=40)

            assert "Standard preprocessing applied" in res
            # Verify sequence of facade calls
            mock_facade.apply_filter.assert_called()
            mock_facade.apply_notch_filter.assert_called()

    def test_notch_filter(self, mock_study):
        tool = RealNotchFilterTool()
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.BackendFacade"
        ) as MockFacade:
            mock_facade = MockFacade.return_value
            res = tool.execute(mock_study, freq=50)
            assert "Applied Notch Filter" in res
            mock_facade.apply_notch_filter.assert_called_once_with(50)

    def test_resample(self, mock_study):
        tool = RealResampleTool()
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.BackendFacade"
        ) as MockFacade:
            mock_facade = MockFacade.return_value
            res = tool.execute(mock_study, rate=128)
            assert "Resampled" in res
            mock_facade.resample_data.assert_called_once_with(128)

    def test_normalize(self, mock_study):
        tool = RealNormalizeTool()
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.BackendFacade"
        ) as MockFacade:
            mock_facade = MockFacade.return_value
            res = tool.execute(mock_study, method="z-score")
            assert "Normalized" in res
            mock_facade.normalize_data.assert_called_once_with("z-score")

    def test_rereference(self, mock_study):
        tool = RealRereferenceTool()
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.BackendFacade"
        ) as MockFacade:
            mock_facade = MockFacade.return_value
            res = tool.execute(mock_study, method="CAR")
            assert "Applied reference" in res
            mock_facade.set_reference.assert_called_once_with("CAR")

    def test_channel_selection(self, mock_study):
        tool = RealChannelSelectionTool()
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.BackendFacade"
        ) as MockFacade:
            mock_facade = MockFacade.return_value
            res = tool.execute(mock_study, channels=["C3", "C4"])
            assert "Selected 2 channels" in res
            mock_facade.select_channels.assert_called_once_with(["C3", "C4"])

    def test_epoch_data(self, mock_study):
        tool = RealEpochDataTool()
        with patch(
            "XBrainLab.llm.tools.real.preprocess_real.BackendFacade"
        ) as MockFacade:
            mock_facade = MockFacade.return_value
            res = tool.execute(mock_study, t_min=0, t_max=4, event_id=None)
            assert "Data epoched" in res
            mock_facade.epoch_data.assert_called_once()

    def test_set_montage(self, mock_study):
        tool = RealSetMontageTool()
        # Note: RealSetMontageTool now returns a confirmation request (human-in-the-loop)
        # instead of auto-applying

        res = tool.execute(mock_study, montage_name="standard_1020")

        # Verify the confirmation request format
        assert "confirm_montage 'standard_1020'" in res


class TestRealUIControlTools:
    def test_switch_panel(self, mock_study):
        tool = RealSwitchPanelTool()
        res = tool.execute(mock_study, panel_name="Training")
        assert res == "Request: Switch UI to 'Training'"
