import os
from pathlib import Path

import pytest

from tests.integration.data_interpretation_support import (
    GRAZ_2A_CLASS_MAP,
    import_recording_through_interpretation,
)
from XBrainLab.backend.application import QueryStateCommand, get_application_service
from XBrainLab.backend.study import Study
from XBrainLab.llm.tools.authorized_paths import authorize_existing_path
from XBrainLab.llm.tools.real.dataset_real import (
    RealAttachLabelsTool,
    RealClearDatasetTool,
    RealGetDatasetInfoTool,
    RealListFilesTool,
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
from XBrainLab.llm.tools.result_contract import ToolResult, UiRequest, UiRequestKind


def _successful_tool_result(result) -> ToolResult:
    assert isinstance(result, ToolResult)
    assert result.ok is True, result.message
    return result


def _query_result(study, query: str):
    result = get_application_service(study).execute(
        QueryStateCommand(query=query),
    )
    assert result.ok, result.message
    return result


def _state(study):
    result = get_application_service(study).query_published_state()
    assert result.ok, result.message
    return result.state.to_dict()


def _first_preprocessed_row(study):
    result = _query_result(study, "data_lists")
    assert result.diagnostics["preprocessed_count"] == 1
    return result.diagnostics["preprocessed_rows"][0]


# Locate test data
TEST_DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../fixtures/data")
)
GDF_FILE = os.path.join(TEST_DATA_DIR, "A01T.gdf")
LABEL_FILE = os.path.join(TEST_DATA_DIR, "label", "A01T.mat")


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

        import_recording_through_interpretation(
            study,
            GDF_FILE,
            class_map=GRAZ_2A_CLASS_MAP,
        )
        assert _state(study)["raw"]["count"] == 1
        return study

    # --- Dataset Tools ---

    def test_list_files_tool(self, study):
        """Test RealListFilesTool."""
        tool = RealListFilesTool()
        # List the data directory itself
        result = _successful_tool_result(
            tool.execute(
                study,
                directory=authorize_existing_path(
                    TEST_DATA_DIR,
                    authorized_root=TEST_DATA_DIR,
                    expected_kind="directory",
                ),
                pattern="*.gdf",
            )
        )
        expected_files = sorted(path.name for path in Path(TEST_DATA_DIR).glob("*.gdf"))
        assert result.message == f"Found {len(expected_files)} file(s)."
        assert result.payload == expected_files

    def test_get_dataset_info_tool(self, loaded_study):
        """Test RealGetDatasetInfoTool."""
        tool = RealGetDatasetInfoTool()
        result = _successful_tool_result(tool.execute(loaded_study))
        raw_state = _state(loaded_study)["raw"]
        assert result.message == (
            "Loaded 1 files:\n"
            "A01T.gdf\n"
            f"Events: {raw_state['event_total']} "
            f"(Unique: {len(raw_state['unique_events'])})"
        )

    def test_attach_labels_tool(self, loaded_study):
        """Attach the real A01T class labels to its 769-772 trial markers."""
        if not os.path.exists(LABEL_FILE):
            pytest.skip("Test label data A01T.mat not found")
        before = _query_result(loaded_study, "data_lists")
        source_event = before.diagnostics["raw_rows"][0]["event"]
        assert source_event == {
            "available": True,
            "count": 588,
            "labels": [
                "1072",
                "276",
                "277",
                "32766",
                "768",
                "769",
                "770",
                "771",
                "772",
            ],
            "source": "detected_events",
            "scanned": True,
        }

        tool = RealAttachLabelsTool()
        mapping = {"A01T.gdf": LABEL_FILE}

        result = _successful_tool_result(
            tool.execute(
                loaded_study,
                mapping=mapping,
                selected_event_names=["769", "770", "771", "772"],
            )
        )
        assert result.message == "Attached labels to 1 file(s)."
        assert result.payload["diagnostics"]["success_count"] == 1
        query_result = _query_result(loaded_study, "data_lists")
        data_row = query_result.diagnostics["raw_rows"][0]
        assert data_row["labels_imported"] is True
        assert data_row["event"] == {
            "available": True,
            "count": 288,
            "labels": ["1", "2", "3", "4"],
            "source": "attached_labels",
            "scanned": True,
        }

    def test_clear_dataset_tool(self, loaded_study):
        """Test RealClearDatasetTool."""
        assert _state(loaded_study)["raw"]["count"] == 1
        tool = RealClearDatasetTool()
        result = _successful_tool_result(tool.execute(loaded_study, confirmed=True))
        assert result.message == "Session reset."
        assert _state(loaded_study)["raw"]["count"] == 0

    # --- Preprocess Tools ---

    def test_notch_filter_tool(self, loaded_study):
        """Test RealNotchFilterTool."""
        tool = RealNotchFilterTool()
        result = _successful_tool_result(tool.execute(loaded_study, freq=50))
        assert result.message == "Applied notch filter (50.0 Hz)."

        hist = _state(loaded_study)["preprocessed"]["operations"]
        assert any("Notch" in h for h in hist)

    def test_resample_tool(self, loaded_study):
        """Test RealResampleTool."""
        tool = RealResampleTool()
        result = _successful_tool_result(tool.execute(loaded_study, rate=100))
        assert result.message == "Resampled data to 100 Hz."

        data_row = _first_preprocessed_row(loaded_study)
        assert data_row["sampling_frequency"] == 100

    def test_channel_selection_tool(self, loaded_study):
        """Test RealChannelSelectionTool."""
        tool = RealChannelSelectionTool()
        channels = _state(loaded_study)["preprocessed"]["channel_names"][:2]
        assert len(channels) == 2
        result = _successful_tool_result(tool.execute(loaded_study, channels=channels))
        assert result.message == "Selected 2 channel(s)."

        data_row = _first_preprocessed_row(loaded_study)
        assert len(data_row["channels"]) == 2

    def test_rereference_tool(self, loaded_study):
        """Test RealRereferenceTool (CAR)."""
        tool = RealRereferenceTool()
        result = _successful_tool_result(tool.execute(loaded_study, method="average"))
        assert result.message == "Applied reference: average."

        hist = _state(loaded_study)["preprocessed"]["operations"]
        assert any("reference" in h.lower() or "average" in h.lower() for h in hist)

    def test_normalize_tool(self, loaded_study):
        """Test RealNormalizeTool."""
        tool = RealNormalizeTool()
        result = _successful_tool_result(tool.execute(loaded_study, method="z-score"))
        assert result.message == (
            "Normalization using z-score is queued for per-EEG-epoch application "
            "during EEG epoch creation."
        )

        hist = _state(loaded_study)["preprocessed"]["operations"]
        assert any("normalization requested" in h for h in hist)

    def test_set_montage_tool(self, loaded_study):
        """Test RealSetMontageTool."""
        tool = RealSetMontageTool()
        # 'standard_1020' or 'china_1020' are supported?
        # Using 'standard_1020' is safest for MNE.
        result = tool.execute(loaded_study, montage_name="standard_1020")

        assert isinstance(result, UiRequest)
        assert result.kind is UiRequestKind.CONFIRM_MONTAGE
        assert result.params["montage_name"] == "standard_1020"
        assert "duplicate-channel ambiguity" not in result.params["warning"]
        assert _state(loaded_study)["raw"]["count"] == 1

    # --- UI Tools ---

    def test_switch_panel_tool(self, study):
        """Test RealSwitchPanelTool."""
        tool = RealSwitchPanelTool()
        result = tool.execute(study, panel_name="Training", view_mode="advanced")
        assert isinstance(result, UiRequest)
        assert result.kind is UiRequestKind.SWITCH_PANEL
        assert result.params == {"panel": "Training", "view_mode": "advanced"}
