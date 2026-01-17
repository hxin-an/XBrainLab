import sys
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from XBrainLab.backend.load_data import Raw
from XBrainLab.ui.dashboard_panel.dataset import (
    ChannelSelectionDialog,
    SmartParserDialog,
)
from XBrainLab.ui.dashboard_panel.preprocess import EpochingDialog

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)


def test_channel_selection_dialog(qtbot):
    """Test ChannelSelectionDialog initialization and selection."""
    # Mock data list
    mock_data = MagicMock()
    mock_data.get_mne.return_value.ch_names = ["C3", "C4", "Cz"]
    data_list = [mock_data]

    # Mock Preprocessor
    with patch("XBrainLab.backend.preprocessor.ChannelSelection"):
        dialog = ChannelSelectionDialog(None, data_list)
        qtbot.addWidget(dialog)

        # Check list items
        assert dialog.list_widget.count() == 3
        items = [dialog.list_widget.item(i).text() for i in range(3)]
        assert items == ["C3", "C4", "Cz"]

        # Test Accept
        # Select all first
        for i in range(3):
            dialog.list_widget.item(i).setCheckState(Qt.CheckState.Checked)

        dialog.accept()
        # Should populate selected_channels
        assert dialog.selected_channels == ["C3", "C4", "Cz"]


def test_smart_parser_dialog(qtbot):
    """Test SmartParserDialog regex logic."""
    filepaths = ["/data/sub-01_ses-01_eeg.set", "/data/sub-02_ses-01_eeg.set"]
    dialog = SmartParserDialog(filepaths, None)
    qtbot.addWidget(dialog)

    # Set regex pattern manually to ensure test stability
    dialog.radio_regex.setChecked(True)
    dialog.regex_preset_combo.setCurrentIndex(0)
    # Pattern: sub-(\d+)_ses-(\d+)
    dialog.regex_input.setText(r"sub-(\d+)_ses-(\d+)")
    dialog.regex_sub_idx.setValue(1)
    dialog.regex_sess_idx.setValue(2)

    # Trigger preview (usually connected to textChanged)
    dialog.update_preview()

    assert dialog.table.rowCount() == 2

    # Row 0
    item_sub = dialog.table.item(0, 1)  # Subject
    item_ses = dialog.table.item(0, 2)  # Session
    assert item_sub.text() == "01"
    assert item_ses.text() == "01"


def test_epoching_dialog_init(qtbot):
    """
    Test EpochingDialog initialization and basic flow.
    """
    # Mock Raw object with spec to pass validation
    mock_data = MagicMock(spec=Raw)
    mock_data.get_raw_event_list.return_value = (MagicMock(), {"Event1": 1})
    mock_data.get_event_list.return_value = (MagicMock(), {"Event1": 1})
    mock_data.is_raw.return_value = True

    # Patch validate_list_type to bypass strict type checking if spec
    # doesn't work perfectly
    with patch("XBrainLab.backend.preprocessor.base.validate_list_type"):
        dialog = EpochingDialog(None, [mock_data])
        qtbot.addWidget(dialog)

        # Check if event list is populated
        assert dialog.event_list.count() > 0
        assert dialog.event_list.item(0).text() == "Event1"

        # Verify new UI elements exist (added for epoch duration validation)
        assert hasattr(dialog, "duration_label")
        assert hasattr(dialog, "warning_label")
        assert hasattr(dialog, "update_duration_info")

        # Select event
        dialog.event_list.item(0).setSelected(True)

        # Accept
        dialog.accept()

        # Verify get_params
        params = dialog.get_params()
        # (baseline, selected_events, tmin, tmax)
        # Default baseline check is False ? Let's Assume default config or
        # check UI state
        # But we just verified get_params returns what accepts sets.

        assert params is not None
        assert params[1] == ["Event1"]
        assert isinstance(params[2], float)  # tmin
        assert isinstance(params[3], float)  # tmax


if __name__ == "__main__":
    pytest.main([__file__])
