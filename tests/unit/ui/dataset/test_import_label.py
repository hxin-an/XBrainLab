from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog

from XBrainLab.backend.application.commands import PreviewLabelImportCommand
from XBrainLab.ui.dialogs.dataset import (
    EventFilterDialog,
    ImportLabelDialog,
    LabelMappingDialog,
)


def _preview_summary(
    paths: list[str],
    unique_labels: list[object],
    *,
    mode: str = "sequence",
    target_count: int | None = 3,
    total_count: int | None = None,
) -> dict[str, object]:
    return {
        "preview_id": "label-preview-test",
        "label_paths": paths,
        "label_configs": {
            path: {
                "label_field": None,
                "anchor": None,
                "duration_field": None,
                "sequence_only": False,
            }
            for path in paths
        },
        "mode": mode,
        "target_count": target_count,
        "total_label_count": total_count if total_count is not None else target_count,
        "mapping_cardinality_limit": 256,
        "unique_labels": unique_labels,
    }


def _complete_preview(monkeypatch, summary: dict[str, object]):
    commands: list[PreviewLabelImportCommand] = []

    def _execute(_context, command, *, on_result, **_kwargs):
        commands.append(command)
        on_result(
            SimpleNamespace(
                failed=False,
                diagnostics={"label_preview": summary},
            )
        )
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.dialogs.dataset.import_label_dialog."
        "execute_application_command_async",
        _execute,
    )
    return commands


def test_import_label_dialog_init(qtbot):
    """Test initialization of ImportLabelDialog."""
    dialog = ImportLabelDialog()
    qtbot.addWidget(dialog)

    assert dialog.file_list.count() == 0
    assert dialog.map_table.rowCount() == 0


def test_import_label_dialog_shows_target_context(qtbot):
    """The post-load label dialog should show where labels will be applied."""
    target = type(
        "Target",
        (),
        {
            "get_filepath": lambda self: "/tmp/sub-01_task-mi_raw.fif",
        },
    )()
    dialog = ImportLabelDialog(target_files=[target])
    qtbot.addWidget(dialog)

    assert "Apply labels to 1 loaded EEG file" in dialog.target_summary_label.text()
    assert "sub-01_task-mi_raw.fif" in dialog.target_summary_label.text()
    assert "updates the current import recipe trace" in dialog.recipe_note_label.text()


def test_import_label_dialog_load_file_uses_typed_async_preview(
    qtbot, tmp_path, monkeypatch
):
    dialog = ImportLabelDialog()
    qtbot.addWidget(dialog)

    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2 1\n", encoding="utf-8")
    commands = _complete_preview(
        monkeypatch,
        _preview_summary([str(label_path)], [1, 2], total_count=3),
    )
    dialog.load_file(str(label_path))

    assert dialog.file_list.count() == 1
    assert dialog.label_paths == [str(label_path)]
    assert dialog.unique_labels == [1, 2]
    assert dialog.map_table.rowCount() == 2
    assert len(commands) == 1
    assert isinstance(commands[0], PreviewLabelImportCommand)
    assert commands[0].label_paths == [str(label_path)]


def test_import_label_dialog_binds_preview_to_reviewed_generation(
    qtbot,
    tmp_path,
    monkeypatch,
):
    observed_generations: list[int | None] = []

    def _execute(
        _context,
        _command,
        *,
        on_result,
        expected_publication_generation=None,
        **_kwargs,
    ):
        observed_generations.append(expected_publication_generation)
        on_result(
            SimpleNamespace(
                failed=False,
                diagnostics={
                    "label_preview": _preview_summary(
                        [str(label_path)],
                        [1, 2],
                        total_count=3,
                    ),
                },
            )
        )
        return True

    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2 1\n", encoding="utf-8")
    monkeypatch.setattr(
        "XBrainLab.ui.dialogs.dataset.import_label_dialog."
        "execute_application_command_async",
        _execute,
    )
    dialog = ImportLabelDialog(expected_publication_generation=73)
    qtbot.addWidget(dialog)

    dialog.load_file(str(label_path))

    assert observed_generations == [73]
    assert dialog.preview_summary["preview_id"] == "label-preview-test"


def test_import_label_dialog_worker_failure_does_not_expose_private_path(
    qtbot,
    tmp_path,
    monkeypatch,
):
    private_path = r"C:\Users\Alice Smith\Clinical Data\sub-P001.edf"

    def _execute(_context, _command, *, on_error, **_kwargs):
        on_error(
            (
                RuntimeError,
                RuntimeError(f"Could not inspect {private_path}"),
                f"Traceback:\nRuntimeError: Could not inspect {private_path}",
            )
        )
        return True

    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2 1\n", encoding="utf-8")
    monkeypatch.setattr(
        "XBrainLab.ui.dialogs.dataset.import_label_dialog."
        "execute_application_command_async",
        _execute,
    )
    dialog = ImportLabelDialog()
    qtbot.addWidget(dialog)

    with patch(
        "XBrainLab.ui.dialogs.dataset.import_label_dialog.QMessageBox.critical"
    ) as critical:
        dialog.load_file(str(label_path))

    critical.assert_called_once_with(
        dialog,
        "Label preview failed",
        (
            "XBrainLab could not inspect the selected label files. "
            "Review the files and try again."
        ),
    )
    assert private_path not in critical.call_args.args[2]


def test_import_label_dialog_presents_stale_preview_as_review_again(
    qtbot,
    tmp_path,
    monkeypatch,
):
    def _execute(_context, _command, *, on_result, **_kwargs):
        on_result(
            SimpleNamespace(
                failed=True,
                diagnostics={"stale_publication": True},
                error_type=None,
                message="The reviewed dataset changed.",
            )
        )
        return True

    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2 1\n", encoding="utf-8")
    monkeypatch.setattr(
        "XBrainLab.ui.dialogs.dataset.import_label_dialog."
        "execute_application_command_async",
        _execute,
    )
    dialog = ImportLabelDialog(expected_publication_generation=73)
    qtbot.addWidget(dialog)

    with patch(
        "XBrainLab.ui.dialogs.dataset.import_label_dialog.QMessageBox.warning"
    ) as warning:
        dialog.load_file(str(label_path))

    warning.assert_called_once_with(
        dialog,
        "Review Label Import Again",
        "The reviewed dataset changed.",
    )
    assert dialog.preview_summary == {}


def test_import_label_dialog_accept_success(qtbot):
    """Test accepting the dialog returns correct results."""
    dialog = ImportLabelDialog()
    qtbot.addWidget(dialog)

    dialog._apply_preview_summary(
        _preview_summary(["file1.txt"], [1, 2], total_count=2)
    )

    # Set mapping names
    dialog.map_table.item(0, 1).setText("Event A")  # Code 1
    dialog.map_table.item(1, 1).setText("Event B")  # Code 2

    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted

    selection, mapping = dialog.get_result()
    assert selection is not None
    assert selection.preview_id == "label-preview-test"
    assert selection.label_paths == ("file1.txt",)
    assert selection.mode == "sequence"
    assert mapping == {1: "Event A", 2: "Event B"}


def test_import_label_dialog_supports_string_sequence_labels(qtbot):
    """String sequence labels should remain usable through the mapping table."""
    dialog = ImportLabelDialog()
    qtbot.addWidget(dialog)

    dialog._apply_preview_summary(
        _preview_summary(
            ["labels.csv"],
            ["left", "right"],
            total_count=3,
        )
    )

    assert dialog.unique_labels == ["left", "right"]
    assert dialog.map_table.item(0, 0).text() == "left"
    assert dialog.map_table.item(1, 0).text() == "right"

    dialog.map_table.item(0, 1).setText("Left Hand")
    dialog.map_table.item(1, 1).setText("Right Hand")

    selection, mapping = dialog.get_result()
    assert selection is not None
    assert mapping == {"left": "Left Hand", "right": "Right Hand"}


def test_import_label_dialog_rejects_summary_above_backend_mapping_limit(qtbot):
    dialog = ImportLabelDialog()
    qtbot.addWidget(dialog)
    summary = _preview_summary(["labels.csv"], [1, 2, 3], total_count=3)
    summary["mapping_cardinality_limit"] = 2

    with pytest.raises(ValueError, match="incomplete"):
        dialog._apply_preview_summary(summary)

    assert dialog.map_table.rowCount() == 0


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


def test_event_filter_dialog_defaults_to_all_when_history_has_no_overlap(qtbot):
    """A stale saved selection should not uncheck every event in a new dataset."""
    with patch(
        "XBrainLab.ui.dialogs.dataset.event_filter_dialog.QSettings"
    ) as mock_settings:
        mock_settings.return_value.value.return_value = ["OldEvent"]
        dialog = EventFilterDialog(None, ["Event1", "Event2"])
        qtbot.addWidget(dialog)

    assert dialog.list_widget.item(0).checkState() == Qt.CheckState.Checked
    assert dialog.list_widget.item(1).checkState() == Qt.CheckState.Checked


@patch("XBrainLab.ui.dialogs.dataset.event_filter_dialog.QMessageBox.warning")
def test_event_filter_dialog_rejects_empty_selection(mock_warning, qtbot):
    """The dialog should not accept an empty keep-list."""
    with patch(
        "XBrainLab.ui.dialogs.dataset.event_filter_dialog.QSettings"
    ) as mock_settings:
        mock_settings.return_value.value.return_value = []
        dialog = EventFilterDialog(None, ["Event1", "Event2"])
        qtbot.addWidget(dialog)

    dialog.set_all_checked(False)
    dialog.accept()

    mock_warning.assert_called_once()
    assert dialog.result() != QDialog.DialogCode.Accepted


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


def test_label_mapping_dialog_avoids_ambiguous_substring_match(qtbot):
    """Auto-sort should prefer exact subject keys over substring containment."""
    data_files = ["/path/sub01.set", "/path/sub010.set"]
    label_files = ["/path/sub010_labels.txt", "/path/sub01_labels.txt"]

    dialog = LabelMappingDialog(None, data_files, label_files)
    qtbot.addWidget(dialog)

    assert (
        dialog.label_list.item(0).data(Qt.ItemDataRole.UserRole)
        == "/path/sub01_labels.txt"
    )
    assert (
        dialog.label_list.item(1).data(Qt.ItemDataRole.UserRole)
        == "/path/sub010_labels.txt"
    )


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
            patch.object(dialog, "_request_preview") as request_preview,
        ):
            mock_fd.getOpenFileNames.return_value = (["/tmp/labels.txt"], "")
            dialog.browse_files()
        request_preview.assert_called_once_with()
        assert dialog.file_list.count() == 1
        assert (
            dialog.file_list.item(0).data(Qt.ItemDataRole.UserRole) == "/tmp/labels.txt"
        )

    def test_browse_files_skips_duplicate(self, qtbot):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)
        dialog._add_label_path("/tmp/labels.txt")
        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.import_label_dialog.QFileDialog"
            ) as mock_fd,
            patch.object(dialog, "_request_preview") as request_preview,
        ):
            mock_fd.getOpenFileNames.return_value = (["/tmp/labels.txt"], "")
            dialog.browse_files()
        request_preview.assert_not_called()
        assert dialog.file_list.count() == 1
        assert dialog.label_paths == ["/tmp/labels.txt"]

    def test_browse_files_allows_same_basename_from_different_dirs(self, qtbot):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)
        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.import_label_dialog.QFileDialog"
            ) as mock_fd,
            patch.object(dialog, "_request_preview"),
        ):
            mock_fd.getOpenFileNames.return_value = (
                ["/tmp/sub01/labels.txt", "/tmp/sub02/labels.txt"],
                "",
            )
            dialog.browse_files()

        assert dialog.file_list.count() == 2
        assert (
            dialog.file_list.item(0).data(Qt.ItemDataRole.UserRole)
            == "/tmp/sub01/labels.txt"
        )
        assert (
            dialog.file_list.item(1).data(Qt.ItemDataRole.UserRole)
            == "/tmp/sub02/labels.txt"
        )

    def test_browse_files_handles_backend_preview_error(self, qtbot, monkeypatch):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)

        def _execute(_context, _command, *, on_result, **_kwargs):
            on_result(
                SimpleNamespace(
                    failed=True,
                    diagnostics={},
                    error_type=None,
                    message="The label file is corrupt.",
                )
            )
            return True

        monkeypatch.setattr(
            "XBrainLab.ui.dialogs.dataset.import_label_dialog."
            "execute_application_command_async",
            _execute,
        )
        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.import_label_dialog.QFileDialog"
            ) as mock_fd,
            patch(
                "XBrainLab.ui.dialogs.dataset.import_label_dialog.QMessageBox"
            ) as mock_mb,
        ):
            mock_fd.getOpenFileNames.return_value = (["/tmp/bad.txt"], "")
            dialog.browse_files()
        mock_mb.critical.assert_called_once()
        assert dialog.preview_summary == {}

    def test_remove_files(self, qtbot):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)
        dialog._add_label_path("a.txt")
        dialog.file_list.item(0).setSelected(True)
        dialog.remove_files()
        assert dialog.file_list.count() == 0
        assert dialog.label_paths == []
        assert dialog.preview_summary == {}

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
        dialog._apply_preview_summary(
            _preview_summary(
                ["ts.txt"],
                [10, 20],
                mode="timestamp",
                target_count=None,
                total_count=3,
            )
        )
        assert dialog.unique_labels == [10, 20]
        assert dialog.map_table.rowCount() == 2

    def test_update_unique_labels_empty(self, qtbot):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)
        dialog.update_unique_labels()
        assert dialog.unique_labels == []
        assert "No labels" in dialog.info_label.text()

    def test_update_unique_labels_preserves_mapping(self, qtbot):
        dialog = ImportLabelDialog()
        qtbot.addWidget(dialog)
        dialog._apply_preview_summary(
            _preview_summary(["a.txt"], [1, 2], total_count=2)
        )
        # Set custom name
        dialog.map_table.item(0, 1).setText("MyEvent")
        # Re-update — should preserve "MyEvent" for code 1
        dialog._apply_preview_summary(
            _preview_summary(["a.txt", "b.txt"], [1, 2, 3], total_count=4)
        )
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
        dialog._apply_preview_summary(
            _preview_summary(["f.txt"], [1], target_count=1, total_count=1)
        )
        # Clear the event name so mapping is empty
        dialog.map_table.item(0, 1).setText("")
        with patch(
            "XBrainLab.ui.dialogs.dataset.import_label_dialog.QMessageBox.warning"
        ):
            dialog.accept()
        assert dialog.result() != QDialog.DialogCode.Accepted
