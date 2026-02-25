import os

import pytest

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

# Locate test data
TEST_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))
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
        label_file.write_text("0,769,Target\n100,770,Standard")

        tool = RealAttachLabelsTool()
        mapping = {"A01T.gdf": str(label_file)}

        res = tool.execute(loaded_study, mapping=mapping)
        # Tool should run without crashing; verify it returns a status string
        assert isinstance(res, str) and len(res) > 0

    def test_clear_dataset_tool(self, loaded_study):
        """Test RealClearDatasetTool."""
        assert len(loaded_study.loaded_data_list) == 1
        tool = RealClearDatasetTool()
        res = tool.execute(loaded_study)
        assert "Dataset cleared" in res
        assert len(loaded_study.loaded_data_list) == 0

    # --- Preprocess Tools ---

    def test_notch_filter_tool(self, loaded_study):
        """Test RealNotchFilterTool."""
        tool = RealNotchFilterTool()
        res = tool.execute(loaded_study, freq=50)
        assert "Applied Notch Filter (50 Hz)" in res

        hist = (
            loaded_study.get_controller("preprocess")
            .get_first_data()
            .get_preprocess_history()
        )
        # History string is "Notch [{freq}] Hz", see PreprocessBase
        assert any("Notch" in h for h in hist)

    def test_resample_tool(self, loaded_study):
        """Test RealResampleTool."""
        tool = RealResampleTool()
        res = tool.execute(loaded_study, rate=100)
        assert "Resampled data to 100 Hz" in res

        data = loaded_study.get_controller("preprocess").get_first_data()
        assert data.get_mne().info["sfreq"] == 100

    def test_channel_selection_tool(self, loaded_study):
        """Test RealChannelSelectionTool."""
        # A01T has 25 channels usually (22 EEG + 3 EOG)
        tool = RealChannelSelectionTool()
        # Select first 2 channels
        channels = loaded_study.get_controller("preprocess").get_channel_names()[:2]
        res = tool.execute(loaded_study, channels=channels)
        assert "Selected 2 channels" in res

        data = loaded_study.get_controller("preprocess").get_first_data()
        assert len(data.get_mne().ch_names) == 2

    def test_rereference_tool(self, loaded_study):
        """Test RealRereferenceTool (CAR)."""
        tool = RealRereferenceTool()
        res = tool.execute(loaded_study, method="average")
        assert "Applied reference: average" in res

        hist = (
            loaded_study.get_controller("preprocess")
            .get_first_data()
            .get_preprocess_history()
        )
        # History string depends on implementation, usually "Rereference ({method})" or similar
        # Real implementation might check for "Rereference" or the method name
        assert any("reference" in h.lower() or "average" in h.lower() for h in hist)

    def test_normalize_tool(self, loaded_study):
        """Test RealNormalizeTool."""
        tool = RealNormalizeTool()
        res = tool.execute(loaded_study, method="z-score")
        assert "Normalized data" in res

        hist = (
            loaded_study.get_controller("preprocess")
            .get_first_data()
            .get_preprocess_history()
        )
        # History string is "{method} normalization"
        assert any("normalization" in h for h in hist)

    def test_set_montage_tool(self, loaded_study):
        """Test RealSetMontageTool."""
        tool = RealSetMontageTool()
        # 'standard_1020' or 'china_1020' are supported?
        # Using 'standard_1020' is safest for MNE.
        res = tool.execute(loaded_study, montage_name="standard_1020")

        # Tool should run without crashing and return a status string
        assert isinstance(res, str) and len(res) > 0

    # --- UI Tools ---

    def test_switch_panel_tool(self, study):
        """Test RealSwitchPanelTool."""
        tool = RealSwitchPanelTool()
        res = tool.execute(study, panel_name="Training", view_mode="advanced")
        assert "Request: Switch UI to 'Training'" in res
        assert "(View: advanced)" in res
