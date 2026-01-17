import sys
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication, QDialog

from XBrainLab.backend.dataset.option import SplitByType, SplitUnit
from XBrainLab.ui.dataset.data_splitting import DataSplitterHolder, DataSplittingWindow

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)


def test_data_splitter_holder_validation():
    """
    Test that DataSplitterHolder correctly validates input
    and returns the correct value.
    """
    # Instantiate Holder (is_option=True, split_type=SplitByType.TRIAL)
    holder = DataSplitterHolder(True, SplitByType.TRIAL)

    # 1. Test Initial State (Empty)
    holder.set_entry_var("")
    holder.set_split_unit_var(None)

    assert not holder.is_valid()

    # 2. Test Valid Ratio
    holder.set_split_unit_var(SplitUnit.RATIO.value)  # "Ratio"
    holder.set_entry_var("0.8")

    assert holder.is_valid()
    assert holder.get_value() == 0.8

    # 3. Test Invalid Ratio (> 1)
    holder.set_entry_var("1.2")
    assert not holder.is_valid()

    # 4. Test Invalid Ratio (Non-numeric)
    holder.set_entry_var("abc")
    assert not holder.is_valid()

    # 5. Switch to Number mode
    holder.set_split_unit_var(SplitUnit.NUMBER.value)  # "Number"

    # 6. Test Valid Number
    holder.set_entry_var("10")
    assert holder.is_valid()
    assert holder.get_value() == 10.0

    # 7. Test Invalid Number (Float string)
    holder.set_entry_var("10.5")
    assert not holder.is_valid()

    # 8. Test Invalid Number (Negative)
    holder.set_entry_var("-5")
    assert not holder.is_valid()


def test_data_splitting_window_init(qtbot):
    """Test initialization of DataSplittingWindow."""
    mock_epoch = MagicMock()
    mock_epoch.subject_map = {}
    mock_epoch.session_map = {}
    mock_epoch.label_map = {}
    mock_epoch.data = []

    mock_config = MagicMock()
    mock_config.train_type.value = "TrainType"
    mock_config.get_splitter_option.return_value = ([], [])
    mock_config.is_cross_validation = False

    # Mock threading to prevent auto-preview
    with (
        patch("threading.Thread"),
        patch("XBrainLab.ui.dataset.data_splitting.DatasetGenerator"),
    ):
        window = DataSplittingWindow(None, "Test Window", mock_epoch, mock_config)
        qtbot.addWidget(window)

        assert window.windowTitle() == "Test Window"
        assert window.tree.columnCount() > 0


def test_data_splitting_window_preview(qtbot):
    """Test preview logic."""
    mock_epoch = MagicMock()
    mock_epoch.subject_map = {}
    mock_epoch.session_map = {}
    mock_epoch.label_map = {}
    mock_epoch.data = []

    mock_config = MagicMock()
    mock_config.train_type.value = "TrainType"
    mock_config.get_splitter_option.return_value = ([], [])
    mock_config.is_cross_validation = False

    with (
        patch("XBrainLab.ui.dataset.data_splitting.DatasetGenerator") as MockGen,
        patch("threading.Thread") as MockThread,
    ):
        window = DataSplittingWindow(None, "Test Window", mock_epoch, mock_config)
        qtbot.addWidget(window)

        # Check if generator was created and thread started
        MockGen.assert_called()
        MockThread.return_value.start.assert_called()

        # Check tree initial state
        assert window.tree.topLevelItemCount() == 1
        assert window.tree.topLevelItem(0).text(1) == "calculating"


def test_data_splitting_window_update_table(qtbot):
    """Test table update from generated datasets."""
    mock_epoch = MagicMock()
    mock_epoch.subject_map = {}
    mock_epoch.session_map = {}
    mock_epoch.label_map = {}
    mock_epoch.data = []

    mock_config = MagicMock()
    mock_config.train_type.value = "TrainType"
    mock_config.get_splitter_option.return_value = ([], [])
    mock_config.is_cross_validation = False

    with (
        patch("threading.Thread"),
        patch("XBrainLab.ui.dataset.data_splitting.DatasetGenerator"),
    ):
        window = DataSplittingWindow(None, "Test Window", mock_epoch, mock_config)
        qtbot.addWidget(window)

        # Simulate datasets generated
        mock_dataset = MagicMock()
        mock_dataset.get_treeview_row_info.return_value = [
            "True",
            "Dataset1",
            "100",
            "20",
            "20",
        ]
        window.datasets = [mock_dataset]

        # Ensure preview_failed is False
        window.dataset_generator.preview_failed = False

        window.update_table()

        assert window.tree.topLevelItemCount() == 1
        assert window.tree.topLevelItem(0).text(1) == "Dataset1"


def test_data_splitting_window_confirm(qtbot):
    """Test confirm logic."""
    mock_epoch = MagicMock()
    mock_epoch.subject_map = {}
    mock_epoch.session_map = {}
    mock_epoch.label_map = {}
    mock_epoch.data = []

    mock_config = MagicMock()
    mock_config.train_type.value = "TrainType"
    mock_config.get_splitter_option.return_value = ([], [])
    mock_config.is_cross_validation = False

    with (
        patch("threading.Thread"),
        patch("XBrainLab.ui.dataset.data_splitting.DatasetGenerator"),
    ):
        window = DataSplittingWindow(None, "Test Window", mock_epoch, mock_config)
        qtbot.addWidget(window)

        # Mock generator
        window.dataset_generator = MagicMock()
        window.preview_worker = MagicMock()
        window.preview_worker.is_alive.return_value = False

        with patch.object(QDialog, "accept") as mock_accept:
            window.confirm()

            # Typo in code: prepare_reuslt
            window.dataset_generator.prepare_reuslt.assert_called_once()
            mock_accept.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
