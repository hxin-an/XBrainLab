import mne
import numpy as np
import pytest

from XBrainLab.backend.application import QueryStateCommand, get_application_service
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


def _query_diagnostics(study, query: str, *, include_objects: bool = False):
    result = get_application_service(study).execute(
        QueryStateCommand(query=query, include_objects=include_objects),
    )
    assert result.ok, result.message
    return result.diagnostics


def _state(study):
    return _query_diagnostics(study, "state")["state"]


def _data_lists(study):
    return _query_diagnostics(study, "data_lists", include_objects=True)


def create_dummy_eeg_file(tmp_path):
    """Helper to create a dummy GDF/EDF file for testing."""
    # Create dummy data using MNE
    sfreq = 100
    ch_names = ["C3", "C4", "Cz"]
    info = mne.create_info(ch_names, sfreq, ch_types="eeg")
    rng = np.random.default_rng(0)
    data = rng.standard_normal((3, 1000))  # 10 seconds of deterministic data
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
    assert res_list == "['test_data_raw.fif']"

    # Load Data
    tool_load = RealLoadDataTool()
    res_load = tool_load.execute(study, paths=[dummy_file])
    assert res_load == "Successfully loaded 1 files."
    raw_state = _state(study)["raw"]
    assert raw_state == {
        "loaded": True,
        "count": 1,
        "files": ["test_data_raw.fif"],
        "formats": [".fif"],
        "channels": ["C3", "C4", "Cz"],
        "metadata": [
            {
                "index": "0",
                "file": "test_data_raw.fif",
                "subject": "0",
                "session": "0",
            },
        ],
        "event_total": 0,
        "unique_events": [],
        "locked": False,
        "diagnostics": {
            "runtime_signals": [],
            "gdf_duplicate_channel_files": [],
            "gdf_duplicate_channel_details": [],
        },
    }

    # Get Info
    tool_info = RealGetDatasetInfoTool()
    res_info = tool_info.execute(study)
    assert res_info == "\n".join(
        [
            "Loaded 1 files:",
            "test_data_raw.fif",
            "Events: 0 (Unique: 0)",
        ],
    )

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
        notch_freq=0.0,
        resample_rate=None,
        normalize_method="z-score",
    )
    assert res_prep == "Standard preprocessing applied successfully."

    data_lists = _data_lists(study)
    assert {
        key: value for key, value in data_lists.items() if not key.endswith("_list")
    } == {
        "raw_count": 1,
        "preprocessed_count": 1,
        "raw_files": ["test_data_raw.fif"],
        "preprocessed_files": ["test_data_raw.fif"],
    }
    if data_lists["preprocessed_count"] > 0:
        raw_wrapper = data_lists["preprocessed_data_list"][0]
    else:
        assert data_lists["loaded_count"] == 1
        raw_wrapper = data_lists["loaded_data_list"][0]

    raw = raw_wrapper.get_mne() if hasattr(raw_wrapper, "get_mne") else raw_wrapper

    # Note: 1Hz filter might result in something close to 1.0 depending on method (IIR/FIR)
    # Using approx just in case
    assert raw.info["highpass"] == pytest.approx(1.0, 0.1)
    assert raw.info["lowpass"] == pytest.approx(40.0, 0.1)

    # 3. Training Setup
    # Set Model
    tool_model = RealSetModelTool()
    res_model = tool_model.execute(study, model_name="EEGNet")
    assert res_model == "Model successfully set to EEGNet."
    training_state = _state(study)["training"]
    assert training_state["has_model"] is True
    assert training_state["model_name"] == "EEGNet"
    assert training_state["has_training_option"] is False
    assert training_state["training_option"] == {}
    assert training_state["missing_requirements"] == [
        "Data Splitting",
        "Training Settings",
    ]

    # Configure
    tool_config = RealConfigureTrainingTool()
    res_config = tool_config.execute(
        study, epoch=5, batch_size=4, optimizer="adam", learning_rate=0.01
    )
    assert (
        res_config == "Training configured: adam on cpu, Epochs: 5, Batch: 4, LR: 0.01"
    )

    training_state = _state(study)["training"]
    assert training_state["has_training_option"] is True
    assert training_state["training_option"] == {
        "epoch": 5,
        "batch_size": 4,
        "learning_rate": 0.01,
        "repeat": 1,
        "device": "cpu",
        "optimizer": "Adam",
        "checkpoint_epoch": 0,
        "output_dir": "./output",
    }
    assert training_state["missing_requirements"] == ["Data Splitting"]

    # 4. UI Control
    tool_ui = RealSwitchPanelTool()
    res_ui = tool_ui.execute(study, panel_name="Training")
    assert res_ui == "Request: Switch UI to 'Training'"
