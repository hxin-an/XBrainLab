import os

import pytest

from XBrainLab.backend.application import QueryStateCommand, get_application_service
from XBrainLab.backend.study import Study
from XBrainLab.llm.tools.real.dataset_real import (
    RealAttachLabelsTool,
    RealClearDatasetTool,
    RealGetDatasetInfoTool,
    RealListFilesTool,
    RealLoadDataTool,
)
from XBrainLab.llm.tools.real.preprocess_real import (
    RealChannelSelectionTool,
    RealNormalizeTool,
    RealNotchFilterTool,
    RealRereferenceTool,
    RealResampleTool,
    RealSetMontageTool,
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


def _first_preprocessed_data(study):
    diagnostics = _query_diagnostics(study, "data_lists", include_objects=True)
    assert diagnostics["preprocessed_count"] == 1
    return diagnostics["preprocessed_data_list"][0]


# Locate test data
TEST_DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../fixtures/data")
)
GDF_FILE = os.path.join(TEST_DATA_DIR, "A01T.gdf")


class TestAllRealTools:
    """
    Comprehensive functional verification for ALL Real Tools.
    Ensures every tool class can execute and interact with the backend correctly.
    """

    @pytest.fixture
    def study(self):
        s = Study()
        s.reset_preprocess(force_update=True)
        s.clean_raw_data(force_update=True)
        return s

    @pytest.fixture
    def loaded_study(self, study):
        """Pre-loaded study for tools that require data."""
        if not os.path.exists(GDF_FILE):
            pytest.skip("Test data A01T.gdf not found")

        load_tool = RealLoadDataTool()
        load_tool.execute(study, paths=[GDF_FILE])
        assert _state(study)["raw"]["count"] == 1
        return study

    # --- Dataset Tools ---

    def test_list_files_tool(self, study):
        """Test RealListFilesTool."""
        tool = RealListFilesTool()
        # List the data directory itself
        res = tool.execute(study, directory=TEST_DATA_DIR, pattern="*.gdf")
        assert "A01T.gdf" in res
        assert "Error" not in res

    def test_get_dataset_info_tool(self, loaded_study):
        """Test RealGetDatasetInfoTool."""
        tool = RealGetDatasetInfoTool()
        res = tool.execute(loaded_study)
        assert "Loaded 1 files" in res
        assert "A01T.gdf" in res

    def test_attach_labels_tool(self, loaded_study, tmp_path):
        """Test RealAttachLabelsTool using a dummy label file."""
        # Create dummy label file
        label_file = tmp_path / "labels.txt"
        label_file.write_text("769 770 769 770 769 770\n")

        tool = RealAttachLabelsTool()
        mapping = {"A01T.gdf": str(label_file)}

        res = tool.execute(loaded_study, mapping=mapping)
        assert "Attached labels to 1 files" in res
        data = _query_diagnostics(
            loaded_study,
            "data_lists",
            include_objects=True,
        )["loaded_data_list"][0]
        assert data.is_labels_imported()

    def test_clear_dataset_tool(self, loaded_study):
        """Test RealClearDatasetTool."""
        assert _state(loaded_study)["raw"]["count"] == 1
        tool = RealClearDatasetTool()
        res = tool.execute(loaded_study)
        assert "Dataset cleared" in res
        assert _state(loaded_study)["raw"]["count"] == 0

    # --- Preprocess Tools ---

    def test_notch_filter_tool(self, loaded_study):
        """Test RealNotchFilterTool."""
        tool = RealNotchFilterTool()
        res = tool.execute(loaded_study, freq=50)
        assert "Applied Notch Filter (50 Hz)" in res

        hist = _first_preprocessed_data(loaded_study).get_preprocess_history()
        assert any("Notch" in h for h in hist)

    def test_resample_tool(self, loaded_study):
        """Test RealResampleTool."""
        tool = RealResampleTool()
        res = tool.execute(loaded_study, rate=100)
        assert "Resampled data to 100 Hz" in res

        data = _first_preprocessed_data(loaded_study)
        assert data.get_mne().info["sfreq"] == 100

    def test_channel_selection_tool(self, loaded_study):
        """Test RealChannelSelectionTool."""
        tool = RealChannelSelectionTool()
        channels = _state(loaded_study)["preprocessed"]["channel_names"][:2]
        assert len(channels) == 2
        res = tool.execute(loaded_study, channels=channels)
        assert "Selected 2 channels" in res
        assert "duplicate-channel ambiguity" not in res

        data = _first_preprocessed_data(loaded_study)
        assert len(data.get_mne().ch_names) == 2

    def test_rereference_tool(self, loaded_study):
        """Test RealRereferenceTool (CAR)."""
        tool = RealRereferenceTool()
        res = tool.execute(loaded_study, method="average")
        assert "Applied reference: average" in res

        hist = _first_preprocessed_data(loaded_study).get_preprocess_history()
        assert any("reference" in h.lower() or "average" in h.lower() for h in hist)

    def test_normalize_tool(self, loaded_study):
        """Test RealNormalizeTool."""
        tool = RealNormalizeTool()
        res = tool.execute(loaded_study, method="z-score")
        assert "Normalized data" in res

        hist = _first_preprocessed_data(loaded_study).get_preprocess_history()
        assert any("normalization" in h for h in hist)

    def test_set_montage_tool(self, loaded_study):
        """Test RealSetMontageTool."""
        tool = RealSetMontageTool()
        # 'standard_1020' or 'china_1020' are supported?
        # Using 'standard_1020' is safest for MNE.
        res = tool.execute(loaded_study, montage_name="standard_1020")

        assert "confirm_montage 'standard_1020'" in res
        assert "duplicate-channel ambiguity" not in res
        assert _state(loaded_study)["raw"]["count"] == 1

    # --- UI Tools ---

    def test_switch_panel_tool(self, study):
        """Test RealSwitchPanelTool."""
        tool = RealSwitchPanelTool()
        res = tool.execute(study, panel_name="Training", view_mode="advanced")
        assert "Request: Switch UI to 'Training'" in res
        assert "(View: advanced)" in res
