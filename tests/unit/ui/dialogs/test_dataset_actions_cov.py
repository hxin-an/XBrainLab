"""Coverage tests for DatasetActionHandler - 130 uncovered lines."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def panel():
    p = MagicMock()
    p.controller = MagicMock()
    p.main_window = MagicMock()
    p.table = MagicMock()
    p.update_panel = MagicMock()
    return p


@pytest.fixture
def handler(panel):
    from XBrainLab.ui.panels.dataset.actions import DatasetActionHandler

    return DatasetActionHandler(panel)


class TestDatasetActionHandlerInit:
    def test_creates_handler(self, handler, panel):
        assert handler.panel is panel
        assert handler.controller is panel.controller
        assert handler.main_window is panel.main_window


class TestImportData:
    def test_import_data_no_files(self, handler):
        with patch(
            "PyQt6.QtWidgets.QFileDialog.getOpenFileNames",
            return_value=([], ""),
        ):
            handler.import_data()

    def test_import_data_with_files(self, handler):
        with patch(
            "PyQt6.QtWidgets.QFileDialog.getOpenFileNames",
            return_value=(["file1.set", "file2.set"], ""),
        ):
            handler.controller.is_locked.return_value = False
            handler.import_data()
            handler.controller.import_files.assert_called()

    def test_on_import_finished_success(self, handler):
        handler.on_import_finished(2, [])
        handler.panel.update_panel.assert_called()

    def test_on_import_finished_with_errors(self, handler):
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            handler.on_import_finished(1, ["Error loading file2.set"])


class TestSmartParser:
    def test_open_smart_parser_locked(self, handler):
        handler.controller.is_locked.return_value = True
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            handler.open_smart_parser()

    def test_open_smart_parser_no_data(self, handler):
        handler.controller.is_locked.return_value = False
        handler.controller.has_data.return_value = False
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            handler.open_smart_parser()

    def test_open_smart_parser_success(self, handler):
        handler.controller.is_locked.return_value = False
        handler.controller.has_data.return_value = True
        with patch("XBrainLab.ui.panels.dataset.actions.SmartParserDialog") as MockDlg:
            from PyQt6.QtWidgets import QDialog

            MockDlg.return_value.exec.return_value = QDialog.DialogCode.Accepted
            MockDlg.return_value.get_result.return_value = {"rule": "test"}
            handler.open_smart_parser()
            handler.controller.apply_smart_parse.assert_called()


class TestImportLabel:
    def test_import_label_locked(self, handler):
        handler.controller.is_locked.return_value = True
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            handler.import_label()

    def test_import_label_no_data(self, handler):
        handler.controller.is_locked.return_value = False
        handler.controller.has_data.return_value = False
        with patch("PyQt6.QtWidgets.QMessageBox.warning"):
            handler.import_label()


class TestContextMenu:
    def test_show_context_menu(self, handler):
        from PyQt6.QtCore import QPoint

        handler.panel.table.selectedIndexes.return_value = []
        with patch("XBrainLab.ui.panels.dataset.actions.QMenu") as MockMenu:
            mock_menu = MockMenu.return_value
            mock_menu.exec.return_value = None
            handler.show_context_menu(QPoint(0, 0))


class TestBatchOperations:
    def test_remove_files(self, handler):
        handler.controller.is_locked.return_value = False
        with patch("PyQt6.QtWidgets.QMessageBox.question") as mock_q:
            from PyQt6.QtWidgets import QMessageBox

            mock_q.return_value = QMessageBox.StandardButton.Yes
            handler._remove_files([0, 1])
            handler.controller.remove_files.assert_called()

    def test_batch_set(self, handler):
        handler.controller.is_locked.return_value = False
        handler.controller.get_loaded_data_list.return_value = [
            MagicMock(),
            MagicMock(),
        ]
        with patch("PyQt6.QtWidgets.QInputDialog.getText") as mock_input:
            mock_input.return_value = ("subject_1", True)
            handler._batch_set([0, 1], "subject")
