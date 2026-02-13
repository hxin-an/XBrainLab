import mne
import numpy as np
import pytest

from XBrainLab.llm.tools.real.dataset_real import (
    RealGetDatasetInfoTool,
    RealListFilesTool,
    RealLoadDataTool,
)
from XBrainLab.llm.tools.real.preprocess_real import (
    RealStandardPreprocessTool,
)
from XBrainLab.llm.tools.real.training_real import (
    RealConfigureTrainingTool,
    RealSetModelTool,
)
from XBrainLab.llm.tools.real.ui_control_real import RealSwitchPanelTool


def create_dummy_eeg_file(tmp_path):
    """Helper to create a dummy GDF/EDF file for testing."""
    # Create dummy data using MNE
    sfreq = 100
    ch_names = ["C3", "C4", "Cz"]
    info = mne.create_info(ch_names, sfreq, ch_types="eeg")
    data = np.random.randn(3, 1000)  # 10 seconds of data
    raw = mne.io.RawArray(data, info)

    # Save as FIF (safest for generic MNE load) or EDF if supported
    # Using FIF for simplicity as XBrainLab supports it via MNE
    fpath = tmp_path / "test_data_raw.fif"
    raw.save(fpath, overwrite=True)
    return str(fpath)


def test_real_tools_e2e_flow(test_app, tmp_path):
    """
    End-to-End test using Real Tools against the Headless App.
    Flow: List -> Load -> Preprocess -> Configure Training -> Set Model
    """
    study = test_app.study

    # 0. Setup Dummy Data
    dummy_file = create_dummy_eeg_file(tmp_path)
    dummy_dir = str(tmp_path)

    # 1. Dataset Tools
    # List Files
    tool_list = RealListFilesTool()
    res_list = tool_list.execute(study, directory=dummy_dir, pattern="*.fif")
    assert "test_data_raw.fif" in res_list

    # Load Data
    tool_load = RealLoadDataTool()
    res_load = tool_load.execute(study, paths=[dummy_file])
    assert "Successfully loaded 1 files" in res_load
    assert len(study.loaded_data_list) == 1

    # Get Info
    tool_info = RealGetDatasetInfoTool()
    res_info = tool_info.execute(study)
    assert "Loaded 1 files" in res_info

    # 2. Preprocess Tools
    # Standard Preprocess (Filter + Epoch)
    # Note: Requires events? RawArray usually has empty annotations.
    # Let's add annotations if needed for epoching, or use fixed length epoching if tool supports it?
    # RealEpochDataTool usually splits by events.
    # Let's try simple filtering first which is safer.

    tool_prep = RealStandardPreprocessTool()
    # Apply filter 1-40Hz
    res_prep = tool_prep.execute(
        study,
        l_freq=1,
        h_freq=40,
        notch_freq=None,
        resample_rate=None,
        normalize_method="z-score",
    )
    assert "Standard preprocessing applied" in res_prep

    # Check that data was modified
    # Preprocessing usually creates a new dataset or updates preprocessed list
    # Let's check if preprocessed list has it
    if len(study.preprocessed_data_list) > 0:
        raw_wrapper = study.preprocessed_data_list[0]
    else:
        # Fallback if it modifies in place (unlikely for XBrainLab usually)
        raw_wrapper = study.loaded_data_list[0]

    # Check if get_mne exists (wrapper) or if it's raw

    raw = raw_wrapper.get_mne() if hasattr(raw_wrapper, "get_mne") else raw_wrapper

    # Note: 1Hz filter might result in something close to 1.0 depending on method (IIR/FIR)
    # Using approx just in case
    assert raw.info["highpass"] == pytest.approx(1.0, 0.1)
    assert raw.info["lowpass"] == pytest.approx(40.0, 0.1)

    # 3. Training Setup
    # Set Model
    tool_model = RealSetModelTool()
    res_model = tool_model.execute(study, model_name="EEGNet")
    assert "successfully set to EEGNet" in res_model
    assert study.model_holder.target_model.__name__ == "EEGNet"

    # Configure
    tool_config = RealConfigureTrainingTool()
    res_config = tool_config.execute(
        study, epoch=5, batch_size=4, optimizer="adam", learning_rate=0.01
    )
    assert "Training configured" in res_config

    # Verify Training Option
    # The tool sets it on the TrainingController -> Study.training_option
    # Trainer might be initialized later or lazily?
    # Let's check study directly as that's where controller sets it.
    assert study.training_option is not None
    assert study.training_option.epoch == 5
    assert study.training_option.bs == 4

    # 4. UI Control
    tool_ui = RealSwitchPanelTool()
    res_ui = tool_ui.execute(study, panel_name="Training")
    assert "Request: Switch UI" in res_ui
