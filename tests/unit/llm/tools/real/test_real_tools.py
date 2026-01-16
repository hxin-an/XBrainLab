from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.model_base.EEGNet import EEGNet
from XBrainLab.backend.preprocessor.channel_selection import ChannelSelection
from XBrainLab.backend.preprocessor.filtering import Filtering
from XBrainLab.backend.preprocessor.normalize import Normalize
from XBrainLab.backend.preprocessor.rereference import Rereference
from XBrainLab.backend.preprocessor.resample import Resample
from XBrainLab.backend.preprocessor.time_epoch import TimeEpoch
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
    # Mock list attributes to act like empty lists initially
    study.loaded_data_list = []
    # Mock output_dir for config tool
    study.output_dir = "./mock_output"
    return study


class TestRealTrainingTools:
    def test_set_model_success(self, mock_study):
        tool = RealSetModelTool()
        result = tool.execute(mock_study, model_name="EEGNet")

        assert "successfully set to EEGNet" in result
        mock_study.set_model_holder.assert_called_once()
        # Verify call args
        args, _ = mock_study.set_model_holder.call_args
        holder = args[0]
        assert holder.target_model == EEGNet

    def test_set_model_unknown(self, mock_study):
        tool = RealSetModelTool()
        result = tool.execute(mock_study, model_name="UnknownModel")
        assert "Unknown model" in result
        mock_study.set_model_holder.assert_not_called()

    def test_configure_and_start_training(self, mock_study):
        config_tool = RealConfigureTrainingTool()
        start_tool = RealStartTrainingTool()

        # Configure
        res1 = config_tool.execute(
            mock_study, epoch=10, batch_size=32, learning_rate=0.001
        )
        assert "Training configured" in res1
        mock_study.set_training_option.assert_called_once()

        # Start
        res2 = start_tool.execute(mock_study)
        assert "started successfully" in res2
        mock_study.generate_plan.assert_called_once_with(force_update=True)
        # Verify interactive mode is used
        mock_study.train.assert_called_once_with(interact=True)


class TestRealDatasetTools:
    def test_list_files(self, mock_study):
        tool = RealListFilesTool()
        # Use temp dir or mock os
        with (
            patch("os.listdir", return_value=["A.gdf", "B.txt"]),
            patch("os.path.exists", return_value=True),
        ):
            res = tool.execute(mock_study, directory="/tmp", pattern="*.gdf")
            assert "A.gdf" in res
            assert "B.txt" not in res

    def test_load_data(self, mock_study):
        tool = RealLoadDataTool()
        with patch(
            "XBrainLab.llm.tools.real.dataset_real.RawDataLoaderFactory.load"
        ) as mock_load:
            mock_raw = MagicMock()
            mock_load.return_value = mock_raw

            res = tool.execute(mock_study, paths=["/data/A.gdf"])

            assert "Successfully loaded 1 files" in res
            mock_study.set_loaded_data_list.assert_called_once()
            args, _ = mock_study.set_loaded_data_list.call_args
            assert args[0] == [mock_raw]  # Check list content

    def test_attach_labels(self, mock_study):
        tool = RealAttachLabelsTool()
        mock_raw = MagicMock()
        mock_raw.filepath = "/data/A.gdf"
        mock_study.loaded_data_list = [mock_raw]

        with patch(
            "XBrainLab.backend.load_data.label_loader.load_label_file",
            return_value=[[1, 0, 1]],
        ):
            res = tool.execute(mock_study, mapping={"A.gdf": "/labels/A.mat"})
            assert "Attached labels to 1 files" in res
            assert mock_raw.events == [[1, 0, 1]]

    def test_clear_dataset(self, mock_study):
        tool = RealClearDatasetTool()
        res = tool.execute(mock_study)
        assert "Dataset cleared" in res
        mock_study.clean_raw_data.assert_called_once_with(force_update=True)

    def test_get_dataset_info(self, mock_study):
        tool = RealGetDatasetInfoTool()
        # Mock loaded data
        mock_raw = MagicMock()
        mock_raw.raw.info = {"sfreq": 250, "ch_names": ["C3", "C4"]}
        mock_study.loaded_data_list = [mock_raw]

        res = tool.execute(mock_study)
        assert "Loaded 1 files" in res
        assert "Sample Rate: 250" in res

    def test_generate_dataset(self, mock_study):
        tool = RealGenerateDatasetTool()
        mock_gen = MagicMock()
        mock_gen.generate.return_value = ["ds1", "ds2"]
        mock_study.get_datasets_generator.return_value = mock_gen

        res = tool.execute(mock_study, test_ratio=0.1, val_ratio=0.1)

        assert "Dataset successfully generated" in res
        assert "Count: 2" in res
        mock_study.get_datasets_generator.assert_called_once()
        mock_gen.generate.assert_called_once()
        mock_study.set_datasets.assert_called_once_with(["ds1", "ds2"])


class TestRealPreprocessTools:
    def test_bandpass_filter(self, mock_study):
        tool = RealBandPassFilterTool()
        res = tool.execute(mock_study, low_freq=1, high_freq=30)

        assert "Applied Bandpass Filter" in res
        # Check calling Filtering class
        mock_study.preprocess.assert_called_with(Filtering, l_freq=1, h_freq=30)

    def test_standard_preprocess(self, mock_study):
        tool = RealStandardPreprocessTool()
        res = tool.execute(mock_study, l_freq=4, h_freq=40)

        assert "Standard preprocessing applied" in res

        calls = mock_study.preprocess.mock_calls
        # Check first call is Filtering with correct args
        assert len(calls) >= 1
        assert calls[0].args[0] == Filtering
        assert calls[0].kwargs["l_freq"] == 4
        assert calls[0].kwargs["h_freq"] == 40
        assert calls[0].kwargs["h_freq"] == 40

    def test_notch_filter(self, mock_study):
        tool = RealNotchFilterTool()
        res = tool.execute(mock_study, freq=50)
        assert "Applied Notch Filter" in res
        mock_study.preprocess.assert_called_with(Filtering, notch_freqs=50)

    def test_resample(self, mock_study):
        tool = RealResampleTool()
        res = tool.execute(mock_study, rate=128)
        assert "Resampled" in res
        mock_study.preprocess.assert_called_with(Resample, rate=128)

    def test_normalize(self, mock_study):
        tool = RealNormalizeTool()
        res = tool.execute(mock_study, method="z-score")
        assert "Normalized" in res
        mock_study.preprocess.assert_called_with(Normalize, method="z-score")

    def test_rereference(self, mock_study):
        tool = RealRereferenceTool()
        res = tool.execute(mock_study, method="CAR")
        assert "Applied reference" in res
        mock_study.preprocess.assert_called_with(Rereference, method="CAR")

    def test_channel_selection(self, mock_study):
        tool = RealChannelSelectionTool()
        res = tool.execute(mock_study, channels=["C3", "C4"])
        assert "Selected 2 channels" in res
        mock_study.preprocess.assert_called_with(
            ChannelSelection, channels=["C3", "C4"]
        )

    def test_epoch_data(self, mock_study):
        tool = RealEpochDataTool()
        # Mock preprocessed data for event discovery logic
        mock_d = MagicMock()
        mock_d.get_event_list.return_value = (None, {"769": 1, "770": 2})
        mock_study.preprocessed_data_list = [mock_d]

        res = tool.execute(
            mock_study, t_min=0, t_max=4, event_id=None
        )  # Test 'all events' logic
        assert "Data epoched" in res

        mock_study.preprocess.assert_called()
        args, kwargs = mock_study.preprocess.call_args
        assert args[0] == TimeEpoch
        assert kwargs["tmin"] == 0
        assert kwargs["tmax"] == 4
        # Verify events were collected
        assert set(kwargs["selected_event_names"]) == {"769", "770"}


class TestRealUIControlTools:
    def test_switch_panel(self, mock_study):
        tool = RealSwitchPanelTool()
        res = tool.execute(mock_study, panel_name="Training")
        assert res == "Request: Switch UI to 'Training'"
