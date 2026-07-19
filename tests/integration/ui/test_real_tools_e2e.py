import mne
import numpy as np
import pytest

from XBrainLab.backend.application import (
    CommandResult,
    ErrorType,
    QueryStateCommand,
    get_application_service,
)
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
from XBrainLab.llm.tools.result_contract import ToolResult, UiRequest, UiRequestKind


def _query_result(study, query: str, *, include_objects: bool = False):
    result = get_application_service(study).execute(
        QueryStateCommand(query=query, include_objects=include_objects),
    )
    assert isinstance(result, CommandResult)
    assert result.ok, result.message
    return result


def _state(study):
    return _query_result(study, "state").diagnostics["state"]


def _data_lists(study):
    return _query_result(study, "data_lists", include_objects=True)


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


def _assert_tool_result(result, *, ok: bool = True) -> ToolResult:
    assert isinstance(result, ToolResult)
    assert result.ok is ok
    if ok:
        assert result.error_type == ErrorType.NONE.value
    else:
        assert result.error_type != ErrorType.NONE.value
    return result


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
    res_list = _assert_tool_result(res_list)
    assert res_list.message == "Found 1 file(s)."
    assert res_list.payload == ["test_data_raw.fif"]

    # Load Data
    tool_load = RealLoadDataTool()
    res_load = tool_load.execute(study, paths=[dummy_file])
    res_load = _assert_tool_result(res_load)
    assert res_load.message == "Loaded 1 file(s)."
    assert res_load.payload["diagnostics"]["success_count"] == 1
    assert res_load.payload["diagnostics"]["errors"] == []
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
    res_info = _assert_tool_result(res_info)
    assert res_info.message == "\n".join(
        [
            "Loaded 1 files:",
            "test_data_raw.fif",
            "Events: 0 (Unique: 0)",
        ],
    )

    # 2. Preprocess Tools
    # Standard preprocessing transforms continuous raw data. Epoch creation is
    # intentionally a separate workflow step.

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
    res_prep = _assert_tool_result(res_prep)
    assert res_prep.message == (
        "Standard preprocessing applied. Normalization using z-score is queued "
        "for per-epoch application during epoch creation."
    )

    data_lists_result = _data_lists(study)
    assert data_lists_result.diagnostics == {
        "raw_count": 1,
        "preprocessed_count": 1,
        "raw_files": ["test_data_raw.fif"],
        "preprocessed_files": ["test_data_raw.fif"],
    }
    raw_wrapper = data_lists_result.runtime["preprocessed_data_list"][0]

    raw = raw_wrapper.get_mne() if hasattr(raw_wrapper, "get_mne") else raw_wrapper

    # Note: 1Hz filter might result in something close to 1.0 depending on method (IIR/FIR)
    # Using approx just in case
    assert raw.info["highpass"] == pytest.approx(1.0, 0.1)
    assert raw.info["lowpass"] == pytest.approx(40.0, 0.1)

    # 3. Training Setup
    # Set Model
    tool_model = RealSetModelTool()
    res_model = tool_model.execute(study, model_name="EEGNet")
    res_model = _assert_tool_result(res_model)
    assert res_model.message == "Model configured: EEGNet."
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
    res_config = _assert_tool_result(res_config)
    assert res_config.message == "Training configured."
    assert res_config.payload["diagnostics"]["training_option"]["epoch"] == 5
    assert res_config.payload["diagnostics"]["training_option"]["batch_size"] == 4
    assert res_config.payload["diagnostics"]["training_option"]["learning_rate"] == 0.01

    training_state = _state(study)["training"]
    assert training_state["has_training_option"] is True
    assert training_state["training_option"] == {
        "epoch": 5,
        "batch_size": 4,
        "learning_rate": 0.01,
        "repeat": 1,
        "device": "cpu",
        "optimizer": "Adam",
        "optimizer_params": {},
        "checkpoint_epoch": 0,
        "evaluation_option": "Last Epoch",
        "output_dir": "./output",
    }
    assert training_state["missing_requirements"] == ["Data Splitting"]

    # 4. UI Control
    tool_ui = RealSwitchPanelTool()
    res_ui = tool_ui.execute(study, panel_name="Training")
    assert isinstance(res_ui, UiRequest)
    assert res_ui.kind is UiRequestKind.SWITCH_PANEL
    assert res_ui.params == {"panel": "Training", "view_mode": None}
