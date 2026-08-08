import mne
import numpy as np
import pytest

from tests.integration.data_interpretation_support import (
    import_recording_through_interpretation,
)
from XBrainLab.backend.application import (
    CommandResult,
    ErrorType,
    QueryStateCommand,
    get_application_service,
)
from XBrainLab.llm.tools.authorized_paths import authorize_existing_path
from XBrainLab.llm.tools.real.dataset_real import (
    RealGetDatasetInfoTool,
    RealListFilesTool,
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


def _query_result(study, query: str):
    result = get_application_service(study).execute(
        QueryStateCommand(query=query),
    )
    assert isinstance(result, CommandResult)
    assert result.ok, result.message
    return result


def _state(study):
    result = get_application_service(study).query_published_state()
    assert isinstance(result, CommandResult)
    assert result.ok, result.message
    return result.state.to_dict()


def _data_lists(study):
    return _query_result(study, "data_lists")


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
    res_list = tool_list.execute(
        study,
        directory=authorize_existing_path(
            dummy_dir,
            authorized_root=dummy_dir,
            expected_kind="directory",
        ),
        pattern="*.fif",
    )
    res_list = _assert_tool_result(res_list)
    assert res_list.message == "Found 1 file(s)."
    assert res_list.payload == ["test_data_raw.fif"]

    # Import through the supported Data Interpretation lifecycle.
    import_recording_through_interpretation(study, dummy_file)
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
        "for per-EEG-epoch application during EEG epoch creation."
    )

    data_lists_result = _data_lists(study)
    diagnostics = data_lists_result.diagnostics
    assert diagnostics["raw_count"] == 1
    assert diagnostics["preprocessed_count"] == 1
    assert diagnostics["raw_rows"][0]["filepath"] == dummy_file
    preprocessed_row = diagnostics["preprocessed_rows"][0]
    assert preprocessed_row["filepath"] == dummy_file
    assert preprocessed_row["filename"] == "test_data_raw.fif"
    assert preprocessed_row["channels"] == ["C3", "C4", "Cz"]

    # Note: 1Hz filter might result in something close to 1.0 depending on method (IIR/FIR)
    # Using approx just in case
    assert preprocessed_row["highpass"] == pytest.approx(1.0, 0.1)
    assert preprocessed_row["lowpass"] == pytest.approx(40.0, 0.1)

    # 3. Training Setup
    # Set Model
    tool_model = RealSetModelTool()
    res_model = tool_model.execute(study, model_name="EEGNet")
    res_model = _assert_tool_result(res_model)
    assert res_model.message == "Model configured: EEGNet."
    training_state = _state(study)["training"]
    assert training_state["has_model"] is True
    assert training_state["model_name"] == "EEGNet (XBrainLab)"
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
        "output_dir": "./output/runs",
    }
    assert training_state["missing_requirements"] == ["Data Splitting"]

    # 4. UI Control
    tool_ui = RealSwitchPanelTool()
    res_ui = tool_ui.execute(study, panel_name="Training")
    assert isinstance(res_ui, UiRequest)
    assert res_ui.kind is UiRequestKind.SWITCH_PANEL
    assert res_ui.params == {"panel": "Training", "view_mode": None}
