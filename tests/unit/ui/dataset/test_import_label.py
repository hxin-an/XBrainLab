from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog

from XBrainLab.ui.dialogs.dataset import (
    EventFilterDialog,
    ImportLabelDialog,
    LabelMappingDialog,
)


def test_import_label_dialog_init(qtbot):
    """Test initialization of ImportLabelDialog."""
    dialog = ImportLabelDialog()
    qtbot.addWidget(dialog)

    assert dialog.file_list.count() == 0
    assert dialog.map_table.rowCount() == 0


def test_import_label_dialog_load_file(qtbot):
    """Test loading label files."""
    dialog = ImportLabelDialog()
    qtbot.addWidget(dialog)

    # Directly test the load_file method instead of browse_files
    with patch(
        "XBrainLab.ui.dialogs.dataset.import_label_dialog.load_label_file",
        return_value=[1, 2, 1],
    ):
        dialog.load_file("/path/to/labels.txt")
        dialog.file_list.addItem("labels.txt")
        dialog.update_unique_labels()

        assert dialog.file_list.count() == 1
        assert "labels.txt" in dialog.label_data_map
        assert dialog.label_data_map["labels.txt"] == [1, 2, 1]

        assert dialog.unique_labels == [1, 2]
        assert dialog.map_table.rowCount() == 2


def test_import_label_dialog_accept_success(qtbot):
    """Test accepting the dialog returns correct results."""
    dialog = ImportLabelDialog()
    qtbot.addWidget(dialog)

    # Manually populate data
    dialog.label_data_map = {"file1.txt": [1, 2]}
    dialog.update_unique_labels()

    # Set mapping names
    dialog.map_table.item(0, 1).setText("Event A")  # Code 1
    dialog.map_table.item(1, 1).setText("Event B")  # Code 2

    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted

    labels, mapping = dialog.get_result()
    assert labels == {"file1.txt": [1, 2]}
    assert mapping == {1: "Event A", 2: "Event B"}


def test_event_filter_dialog(qtbot):
    """Test EventFilterDialog logic."""
    events = ["Event1", "Event2", "Event3"]
    dialog = EventFilterDialog(None, events)
    qtbot.addWidget(dialog)

    # Check initial state (all checked by default if no settings)
    # We mocked QSettings in the class? No, it uses real QSettings.
    # Assume default behavior or check items.

    # Select only Event1
    dialog.set_all_checked(False)
    dialog.list_widget.item(0).setCheckState(Qt.CheckState.Checked)

    with patch.object(QDialog, "accept") as mock_accept:
        dialog.accept()
        mock_accept.assert_called_once()

    assert dialog.get_selected_ids() == ["Event1"]


def test_label_mapping_dialog(qtbot):
    """Test LabelMappingDialog auto-sort logic."""
    data_files = ["/path/sub01.set", "/path/sub02.set"]
    label_files = ["/path/sub02_labels.txt", "/path/sub01_labels.txt"]

    dialog = LabelMappingDialog(None, data_files, label_files)
    qtbot.addWidget(dialog)

    # Check auto-sort (should match sub01 with sub01)
    # Row 0: data=sub01, label should be sub01
    label_item_0 = dialog.label_list.item(0)
    assert "sub01_labels.txt" in label_item_0.text()

    # Row 1: data=sub02, label should be sub02
    label_item_1 = dialog.label_list.item(1)
    assert "sub02_labels.txt" in label_item_1.text()

    # Check mapping result
    with patch.object(QDialog, "accept"):
        dialog.accept()

    mapping = dialog.get_mapping()
    assert mapping["/path/sub01.set"] == "/path/sub01_labels.txt"
    assert mapping["/path/sub02.set"] == "/path/sub02_labels.txt"


# ---------------------------------------------------------------------------
# Additional coverage tests for ImportLabelDialog methods
# ---------------------------------------------------------------------------


class TestImportLabelDialogBrowse:
    """Tests for browse_files / remove_files / update_unique_labels / accept."""

    def test_browse_files_no_selection(self, qtbot):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)
        with patch(
            "XBrainLab.ui.dialogs.dataset.import_label_dialog.QFileDialog"
        ) as mock_fd:
            mock_fd.getOpenFileNames.return_value = ([], "")
            dialog.browse_files()
        assert dialog.file_list.count() == 0

    def test_browse_files_loads_file(self, qtbot):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)
        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.import_label_dialog.QFileDialog"
            ) as mock_fd,
            patch.object(dialog, "load_file"),
        ):
            mock_fd.getOpenFileNames.return_value = (["/tmp/labels.txt"], "")
            dialog.browse_files()
        assert dialog.file_list.count() == 1

    def test_browse_files_skips_duplicate(self, qtbot):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)
        dialog.label_data_map["labels.txt"] = [1]
        with patch(
            "XBrainLab.ui.dialogs.dataset.import_label_dialog.QFileDialog"
        ) as mock_fd:
            mock_fd.getOpenFileNames.return_value = (["/tmp/labels.txt"], "")
            dialog.browse_files()
        # Should not add a second entry
        assert dialog.file_list.count() == 0

    def test_browse_files_handles_error(self, qtbot):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)
        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.import_label_dialog.QFileDialog"
            ) as mock_fd,
            patch.object(
                dialog,
                "load_file",
                side_effect=ValueError("corrupt"),
            ),
            patch(
                "XBrainLab.ui.dialogs.dataset.import_label_dialog.QMessageBox"
            ) as mock_mb,
        ):
            mock_fd.getOpenFileNames.return_value = (["/tmp/bad.txt"], "")
            dialog.browse_files()
        mock_mb.warning.assert_called_once()

    def test_remove_files(self, qtbot):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)
        dialog.label_data_map["a.txt"] = [1]
        dialog.file_list.addItem("a.txt")
        dialog.file_list.item(0).setSelected(True)
        dialog.remove_files()
        assert dialog.file_list.count() == 0
        assert "a.txt" not in dialog.label_data_map

    def test_remove_files_no_selection(self, qtbot):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)
        dialog.file_list.addItem("a.txt")
        # nothing selected
        dialog.remove_files()
        assert dialog.file_list.count() == 1

    def test_update_unique_labels_timestamp_mode(self, qtbot):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)
        dialog.label_data_map["ts.txt"] = [
            {"label": 10, "onset": 0.0},
            {"label": 20, "onset": 1.0},
            {"label": 10, "onset": 2.0},
        ]
        dialog.update_unique_labels()
        assert dialog.unique_labels == [10, 20]
        assert dialog.map_table.rowCount() == 2

    def test_update_unique_labels_empty(self, qtbot):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)
        dialog.label_data_map.clear()
        dialog.update_unique_labels()
        assert dialog.unique_labels == []
        assert "No labels" in dialog.info_label.text()

    def test_update_unique_labels_preserves_mapping(self, qtbot):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)
        dialog.label_data_map["a.txt"] = [1, 2]
        dialog.update_unique_labels()
        # Set custom name
        dialog.map_table.item(0, 1).setText("MyEvent")
        # Re-update — should preserve "MyEvent" for code 1
        dialog.label_data_map["b.txt"] = [1, 3]
        dialog.update_unique_labels()
        assert dialog.map_table.item(0, 1).text() == "MyEvent"

    def test_get_results_empty(self, qtbot):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)
        result = dialog.get_results()
        assert result == (None, None)

    def test_accept_no_labels(self, qtbot):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)
        with patch(
            "XBrainLab.ui.dialogs.dataset.import_label_dialog.QMessageBox.warning"
        ):
            dialog.accept()
        assert dialog.result() != QDialog.DialogCode.Accepted

    def test_accept_no_mapping(self, qtbot):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)
        dialog.label_data_map["f.txt"] = [1]
        dialog.update_unique_labels()
        # Clear the event name so mapping is empty
        dialog.map_table.item(0, 1).setText("")
        with patch(
            "XBrainLab.ui.dialogs.dataset.import_label_dialog.QMessageBox.warning"
        ):
            dialog.accept()
        assert dialog.result() != QDialog.DialogCode.Accepted
