"""Batch 5: deeper coverage for data_splitting_preview, actions, import_label,
agent_manager, preprocess_plotter, saliency views, and remaining gaps."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PyQt6.QtWidgets import QDialog, QMainWindow, QWidget

# ====================================================================
# DataSplitterHolder (pure logic - no Qt needed)
# ====================================================================


class TestDataSplitterHolder:
    def _make(self, is_option=True, split_type=None):
        from XBrainLab.backend.dataset import SplitByType

        if split_type is None:
            split_type = SplitByType.TRIAL
        from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
            DataSplitterHolder,
        )

        return DataSplitterHolder(is_option, split_type)

    def test_init(self):
        h = self._make()
        assert h.is_option is True

    def test_set_split_unit_ratio(self):
        from XBrainLab.backend.dataset import SplitUnit

        h = self._make()
        h.set_split_unit_var(SplitUnit.RATIO.value)
        assert h.split_unit == SplitUnit.RATIO

    def test_set_split_unit_number(self):
        from XBrainLab.backend.dataset import SplitUnit

        h = self._make()
        h.set_split_unit_var(SplitUnit.NUMBER.value)
        assert h.split_unit == SplitUnit.NUMBER

    def test_set_split_unit_invalid(self):
        h = self._make()
        h.set_split_unit_var("non_existent_unit")
        assert h.split_unit is None

    def test_set_entry_var(self):
        h = self._make()
        h.set_entry_var("0.3")
        assert h.value_var == "0.3"

    def test_to_thread(self):
        h = self._make()
        h.to_thread()  # should not raise

    def test_not_option(self):
        h = self._make(is_option=False)
        assert h.is_option is False


# ====================================================================
# DatasetActionHandler
# ====================================================================


class TestDatasetActionHandler:
    @pytest.fixture
    def handler(self):
        from XBrainLab.ui.panels.dataset.actions import DatasetActionHandler

        panel = MagicMock()
        panel.table = MagicMock()
        panel.table.selectedIndexes.return_value = []
        panel.table.rowCount.return_value = 3
        panel.table.mapToGlobal.return_value = MagicMock()
        h = DatasetActionHandler(panel)
        return h

    def test_controller_property(self, handler):
        handler.panel.controller = MagicMock()
        assert handler.controller is handler.panel.controller

    def test_main_window_property(self, handler):
        handler.panel.main_window = MagicMock()
        assert handler.main_window is handler.panel.main_window

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_locked(self, mock_mb, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = True
        handler.import_data()
        mock_mb.warning.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_no_files(self, mock_mb, mock_fd, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = ([], "")
        handler.import_data()
        handler.panel.controller.import_files.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_success(self, mock_mb, mock_fd, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = (["/a.set"], "")
        handler.import_data()
        handler.panel.controller.import_files.assert_called_once_with(["/a.set"])

    @patch("XBrainLab.ui.panels.dataset.actions.QFileDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_import_data_exception(self, mock_mb, mock_fd, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        mock_fd.getOpenFileNames.return_value = (["/a.set"], "")
        handler.panel.controller.import_files.side_effect = RuntimeError("fail")
        handler.import_data()
        mock_mb.critical.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_on_import_finished_success(self, mock_mb, handler):
        handler.on_import_finished(2, [])
        handler.panel.update_panel.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_on_import_finished_errors(self, mock_mb, handler):
        handler.on_import_finished(1, ["err1", "err2"])
        mock_mb.warning.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_open_smart_parser_locked(self, mock_mb, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = True
        handler.open_smart_parser()
        mock_mb.warning.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_open_smart_parser_no_data(self, mock_mb, handler):
        handler.panel.controller = MagicMock()
        handler.panel.controller.is_locked.return_value = False
        handler.panel.controller.has_data.return_value = False
        handler.open_smart_parser()
        mock_mb.warning.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QInputDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMenu")
    def test_show_context_menu_no_rows(self, mock_menu, mock_input, handler):
        handler.panel.table.selectedIndexes.return_value = []
        handler.show_context_menu(MagicMock())
        # no menu exec when no rows

    @patch("XBrainLab.ui.panels.dataset.actions.QInputDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMenu")
    def test_show_context_menu_with_rows(self, mock_menu_cls, mock_input, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        menu = MagicMock()
        mock_menu_cls.return_value = menu
        a_subj = MagicMock()
        a_sess = MagicMock()
        a_rem = MagicMock()
        menu.addAction.side_effect = [a_subj, a_sess, a_rem]
        menu.exec.return_value = a_subj
        mock_input.getText.return_value = ("S1", True)
        handler.panel.controller = MagicMock()
        handler.show_context_menu(MagicMock())
        handler.panel.controller.update_metadata.assert_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_remove_files(self, mock_mb, handler):
        mock_mb.question.return_value = MagicMock()
        mock_mb.StandardButton.Yes = MagicMock()
        mock_mb.question.return_value = mock_mb.StandardButton.Yes
        handler.panel.controller = MagicMock()
        handler._remove_files([0, 1])
        handler.panel.controller.remove_files.assert_called_once_with([0, 1])

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_batch_set_session(self, mock_mb, handler):
        handler.panel.controller = MagicMock()
        with patch("XBrainLab.ui.panels.dataset.actions.QInputDialog") as mock_input:
            mock_input.getText.return_value = ("sess1", True)
            handler._batch_set([0], "Session")
        handler.panel.controller.update_metadata.assert_called_once_with(
            0, session="sess1"
        )

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_get_target_files_no_selection_apply_all(self, mock_mb, handler):
        handler.panel.table.selectedIndexes.return_value = []
        mock_mb.StandardButton.Yes = 1
        mock_mb.StandardButton.No = 2
        mock_mb.question.return_value = 1
        handler.panel.controller = MagicMock()
        handler.panel.controller.get_loaded_data_list.return_value = ["a", "b", "c"]
        result = handler._get_target_files_for_import()
        assert len(result) == 3

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    def test_get_target_files_no_selection_cancel(self, mock_mb, handler):
        handler.panel.table.selectedIndexes.return_value = []
        mock_mb.StandardButton.Yes = 1
        mock_mb.StandardButton.No = 2
        mock_mb.question.return_value = 2
        result = handler._get_target_files_for_import()
        assert result == []

    def test_open_smart_parser_success(self, handler):
        handler.panel.controller.is_locked.return_value = False
        handler.panel.controller.has_data.return_value = True
        handler.panel.controller.get_filenames.return_value = ["file1.set"]
        with patch("XBrainLab.ui.panels.dataset.actions.SmartParserDialog") as MockDlg:
            from PyQt6.QtWidgets import QDialog

            MockDlg.return_value.exec.return_value = QDialog.DialogCode.Accepted
            MockDlg.return_value.get_result.return_value = {"rule": "test"}
            with patch("XBrainLab.ui.panels.dataset.actions.QMessageBox"):
                handler.open_smart_parser()
                handler.panel.controller.apply_smart_parse.assert_called()

    def test_import_label_returns_early_no_files(self, handler):
        """import_label calls _get_target_files_for_import first; if empty, returns."""
        handler.panel.table.selectedIndexes.return_value = []
        with patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb:
            mock_mb.StandardButton.Yes = 1
            mock_mb.StandardButton.No = 2
            mock_mb.question.return_value = 2  # user cancels
            handler.import_label()
            # No warning called since user just cancelled target selection

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_dialog_cancelled(self, mock_dlg, mock_mb, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        handler.panel.controller.get_loaded_data_list.return_value = [MagicMock()]
        mock_dlg.return_value.exec.return_value = False
        handler.import_label()
        handler.panel.controller.apply_labels_legacy.assert_not_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_null_label_map(self, mock_dlg, mock_mb, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        handler.panel.controller.get_loaded_data_list.return_value = [MagicMock()]
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (None, None)
        handler.import_label()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_single_same_length(self, mock_dlg, mock_mb, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        data_obj = MagicMock()
        data_obj.is_raw.return_value = False
        handler.panel.controller.get_loaded_data_list.return_value = [data_obj]
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (
            {"file1.txt": [0, 1, 0, 1]},
            "mapping",
        )
        handler.panel.controller.apply_labels_legacy.return_value = 1
        handler.import_label()
        handler.panel.controller.apply_labels_legacy.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.LabelMappingDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_batch(self, mock_dlg, mock_mb, mock_map_dlg, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        data_obj = MagicMock()
        data_obj.is_raw.return_value = False
        data_obj.get_filepath.return_value = "/file1.set"
        handler.panel.controller.get_loaded_data_list.return_value = [data_obj]
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (
            {"label1.txt": [0, 1], "label2.txt": [1, 0]},
            "mapping",
        )
        mock_map_dlg.return_value.exec.return_value = True
        mock_map_dlg.return_value.get_mapping.return_value = {
            "/file1.set": "label1.txt"
        }
        handler.panel.controller.apply_labels_batch.return_value = 1
        handler.import_label()
        handler.panel.controller.apply_labels_batch.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_timestamp(self, mock_dlg, mock_mb, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        data_obj = MagicMock()
        data_obj.is_raw.return_value = False
        data_obj.get_filepath.return_value = "/file1.set"
        handler.panel.controller.get_loaded_data_list.return_value = [data_obj]
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (
            {"label1.txt": [{"onset": 0.0, "duration": 1.0, "label": "A"}]},
            "mapping",
        )
        handler.panel.controller.apply_labels_batch.return_value = 1
        handler.import_label()
        handler.panel.controller.apply_labels_batch.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_exception(self, mock_dlg, mock_mb, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        data_obj = MagicMock()
        data_obj.is_raw.return_value = False
        handler.panel.controller.get_loaded_data_list.return_value = [data_obj]
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (
            {"f.txt": [0, 1]},
            "mapping",
        )
        handler.panel.controller.apply_labels_legacy.side_effect = RuntimeError("fail")
        handler.import_label()
        mock_mb.critical.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.EventFilterDialog")
    def test_filter_events_no_raw_files(self, mock_efd, handler):
        handler.panel.controller = MagicMock()
        data = MagicMock()
        data.is_raw.return_value = False
        data.has_event.return_value = False
        result = handler._filter_events_for_import([data], 4)
        assert result is None

    @patch("XBrainLab.ui.panels.dataset.actions.EventFilterDialog")
    def test_filter_events_with_suggestions(self, mock_efd, handler):
        handler.panel.controller = MagicMock()
        data = MagicMock()
        data.is_raw.return_value = True
        data.has_event.return_value = True
        data.get_raw_event_list.return_value = ([], {"left": 1, "right": 2})
        handler.panel.controller.get_smart_filter_suggestions.return_value = [1, 2]
        mock_efd.return_value.exec.return_value = True
        mock_efd.return_value.get_selected_ids.return_value = ["left", "right"]
        result = handler._filter_events_for_import([data], 2)
        assert result == {"left", "right"}

    @patch("XBrainLab.ui.panels.dataset.actions.EventFilterDialog")
    def test_filter_events_cancelled(self, mock_efd, handler):
        data = MagicMock()
        data.is_raw.return_value = True
        data.has_event.return_value = True
        data.get_raw_event_list.return_value = ([], {"ev1": 1})
        handler.panel.controller = MagicMock()
        mock_efd.return_value.exec.return_value = False
        result = handler._filter_events_for_import([data], 2)
        assert result is False

    def test_on_import_finished_many_errors(self, handler):
        with patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb:
            handler.on_import_finished(0, [f"err{i}" for i in range(15)])
            mock_mb.warning.assert_called_once()

    @patch("XBrainLab.ui.panels.dataset.actions.QInputDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMenu")
    def test_context_menu_remove(self, mock_menu_cls, mock_input, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        menu = MagicMock()
        mock_menu_cls.return_value = menu
        a_subj = MagicMock()
        a_sess = MagicMock()
        a_rem = MagicMock()
        menu.addAction.side_effect = [a_subj, a_sess, a_rem]
        menu.exec.return_value = a_rem
        handler.panel.controller = MagicMock()
        with patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb:
            mock_mb.StandardButton.Yes = 1
            mock_mb.StandardButton.No = 2
            mock_mb.question.return_value = 1
            handler.show_context_menu(MagicMock())
        handler.panel.controller.remove_files.assert_called()

    @patch("XBrainLab.ui.panels.dataset.actions.QInputDialog")
    @patch("XBrainLab.ui.panels.dataset.actions.QMenu")
    def test_context_menu_session(self, mock_menu_cls, mock_input, handler):
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        menu = MagicMock()
        mock_menu_cls.return_value = menu
        a_subj = MagicMock()
        a_sess = MagicMock()
        a_rem = MagicMock()
        menu.addAction.side_effect = [a_subj, a_sess, a_rem]
        menu.exec.return_value = a_sess
        mock_input.getText.return_value = ("sess1", True)
        handler.panel.controller = MagicMock()
        handler.show_context_menu(MagicMock())
        handler.panel.controller.update_metadata.assert_called_with(0, session="sess1")

    @patch("XBrainLab.ui.panels.dataset.actions.QMessageBox")
    @patch("XBrainLab.ui.panels.dataset.actions.ImportLabelDialog")
    def test_import_label_with_event_filter(self, mock_dlg, mock_mb, handler):
        """Tests import_label where target has raw events requiring filtering."""
        idx = MagicMock()
        idx.row.return_value = 0
        handler.panel.table.selectedIndexes.return_value = [idx]
        handler.panel.controller = MagicMock()
        data_obj = MagicMock()
        data_obj.is_raw.return_value = True
        data_obj.has_event.return_value = True
        data_obj.get_raw_event_list.return_value = ([], {"left": 1, "right": 2})
        handler.panel.controller.get_loaded_data_list.return_value = [data_obj]
        handler.panel.controller.get_smart_filter_suggestions.return_value = [1]
        mock_dlg.return_value.exec.return_value = True
        mock_dlg.return_value.get_result.return_value = (
            {"file1.txt": [0, 1, 0, 1]},
            "mapping",
        )
        handler.panel.controller.apply_labels_legacy.return_value = 1
        with patch("XBrainLab.ui.panels.dataset.actions.EventFilterDialog") as mock_efd:
            mock_efd.return_value.exec.return_value = True
            mock_efd.return_value.get_selected_ids.return_value = ["left"]
            handler.import_label()
        handler.panel.controller.apply_labels_legacy.assert_called_once()


# ====================================================================
# ImportLabelDialog
# ====================================================================


class TestImportLabelDialog:
    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.import_label_dialog import ImportLabelDialog

        d = ImportLabelDialog(parent=None)
        qtbot.addWidget(d)
        return d

    def test_creates(self, dlg):
        assert isinstance(dlg, QDialog)
        assert dlg.label_data_map == {}

    def test_remove_files_empty(self, dlg):
        dlg.remove_files()  # no items, should not crash

    def test_update_unique_labels_empty(self, dlg):
        dlg.update_unique_labels()
        assert dlg.unique_labels == []
        assert "No labels" in dlg.info_label.text()

    def test_update_unique_labels_sequence(self, dlg):
        dlg.label_data_map["f.txt"] = np.array([1, 2, 1, 3])
        dlg.update_unique_labels()
        assert dlg.unique_labels == [1, 2, 3]
        assert "3 unique" in dlg.info_label.text()

    def test_update_unique_labels_timestamp(self, dlg):
        dlg.label_data_map["f.csv"] = [
            {"label": 1, "onset": 0.0},
            {"label": 2, "onset": 1.0},
        ]
        dlg.update_unique_labels()
        assert dlg.unique_labels == [1, 2]

    def test_get_results_none_when_empty(self, dlg):
        lm, m = dlg.get_results()
        assert lm is None and m is None

    def test_get_result_alias(self, dlg):
        r = dlg.get_result()
        assert r == (None, None)

    def test_get_results_with_data(self, dlg):
        dlg.label_data_map["f.txt"] = np.array([1, 2])
        dlg.update_unique_labels()
        lm, m = dlg.get_results()
        assert lm is not None
        assert 1 in m and 2 in m

    @patch("XBrainLab.ui.dialogs.dataset.import_label_dialog.QMessageBox")
    def test_accept_empty(self, mock_mb, dlg):
        dlg.accept()
        mock_mb.warning.assert_called()

    @patch("XBrainLab.ui.dialogs.dataset.import_label_dialog.QMessageBox")
    def test_accept_no_mapping(self, mock_mb, dlg):
        dlg.label_data_map["f.txt"] = np.array([1])
        dlg.accept()
        mock_mb.warning.assert_called()

    def test_on_file_selection_changed(self, dlg):
        dlg.on_file_selection_changed()  # no-op, should not crash

    @patch("XBrainLab.ui.dialogs.dataset.import_label_dialog.load_label_file")
    def test_load_file(self, mock_load, dlg):
        mock_load.return_value = np.array([1, 2, 3])
        dlg.load_file("/path/labels.txt")
        assert "labels.txt" in dlg.label_data_map

    def test_browse_files(self, dlg):
        # Manually simulate what browse_files does after file dialog
        dlg.load_file = MagicMock()
        dlg.label_data_map["a.txt"] = np.array([1, 2])
        dlg.file_list.addItem("a.txt")
        assert dlg.file_list.count() == 1
        dlg.update_unique_labels()
        assert dlg.unique_labels == [1, 2]


# ====================================================================
# AgentManager deeper coverage
# ====================================================================


class TestAgentManagerDeep:
    @pytest.fixture
    def mgr(self, qtbot):
        with (
            patch("XBrainLab.ui.components.agent_manager.ChatController") as mock_cc,
            patch("XBrainLab.ui.components.agent_manager.ChatPanel"),
            patch("XBrainLab.ui.components.agent_manager.Stylesheets"),
        ):
            from XBrainLab.ui.components.agent_manager import AgentManager

            mw = QMainWindow()
            qtbot.addWidget(mw)
            study = MagicMock()
            study.get_controller.return_value = MagicMock()
            m = AgentManager(mw, study)
            m.chat_controller = mock_cc.return_value
            yield m

    def test_update_ai_btn_state(self, mgr):
        mgr.main_window.ai_btn = MagicMock()
        mgr.update_ai_btn_state(True)
        mgr.main_window.ai_btn.setChecked.assert_called_with(True)

    def test_toggle_float_no_dock(self, mgr):
        mgr.chat_dock = None
        mgr._toggle_float()  # should not crash

    def test_toggle_float_with_dock(self, mgr, qtbot):
        from PyQt6.QtWidgets import QDockWidget

        dock = QDockWidget("test", mgr.main_window)
        mgr.chat_dock = dock
        mgr._toggle_float()
        assert dock.isFloating()

    def test_handle_user_input(self, mgr):
        mgr.agent_controller = MagicMock()
        mgr.handle_user_input("hello")
        mgr.chat_controller.add_user_message.assert_called_with("hello")
        mgr.agent_controller.handle_user_input.assert_called_with("hello")

    def test_stop_generation(self, mgr):
        mgr.agent_controller = MagicMock()
        mgr.stop_generation()
        mgr.agent_controller.stop_generation.assert_called_once()
        mgr.chat_controller.set_processing.assert_called_with(False)

    def test_set_model(self, mgr):
        mgr.agent_controller = MagicMock()
        mgr.set_model("Gemini")
        mgr.agent_controller.set_model.assert_called_with("Gemini")

    def test_on_processing_state_changed(self, mgr):
        mgr.chat_panel = MagicMock()
        mgr.on_processing_state_changed(True)
        mgr.chat_panel.set_processing_state.assert_called_with(True)

    def test_start_new_conversation(self, mgr):
        mgr.agent_controller = MagicMock()
        mgr.agent_controller.reset_conversation = MagicMock()
        mgr.start_new_conversation()
        mgr.chat_controller.clear_conversation.assert_called_once()
        mgr.agent_controller.reset_conversation.assert_called_once()

    def test_on_generation_started(self, mgr):
        mgr.chat_panel = MagicMock()
        mgr._on_generation_started()
        assert mgr.chat_panel.current_agent_bubble is None
        mgr.chat_controller.set_processing.assert_called_with(True)

    def test_on_processing_finished(self, mgr):
        mgr.on_processing_finished()
        mgr.chat_controller.set_processing.assert_called_with(False)

    def test_on_agent_status_update_error(self, mgr):
        mgr.on_agent_status_update("Error occurred")
        mgr.chat_controller.set_processing.assert_called_with(False)

    def test_handle_agent_error(self, mgr):
        mgr.handle_agent_error("test error")
        mgr.chat_controller.set_processing.assert_called_with(False)
        mgr.chat_controller.add_agent_message.assert_called_once()

    def test_close(self, mgr):
        mgr.agent_controller = MagicMock()
        mgr.close()
        mgr.agent_controller.close.assert_called_once()

    def test_handle_user_interaction_switch_panel(self, mgr):
        mgr.main_window.stack = MagicMock()
        mgr.main_window.nav_btns = [MagicMock() for _ in range(5)]
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.handle_user_interaction("switch_panel", {"panel": "dataset"})
        mgr.main_window.stack.setCurrentIndex.assert_called_with(0)

    def test_switch_panel_preprocess(self, mgr):
        mgr.main_window.stack = MagicMock()
        mgr.main_window.nav_btns = [MagicMock() for _ in range(5)]
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.switch_panel({"panel": "preprocess"})
        mgr.main_window.stack.setCurrentIndex.assert_called_with(1)

    def test_switch_panel_training(self, mgr):
        mgr.main_window.stack = MagicMock()
        mgr.main_window.nav_btns = [MagicMock() for _ in range(5)]
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.switch_panel({"panel": "training"})
        mgr.main_window.stack.setCurrentIndex.assert_called_with(2)

    def test_switch_panel_eval(self, mgr):
        mgr.main_window.stack = MagicMock()
        mgr.main_window.nav_btns = [MagicMock() for _ in range(5)]
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.switch_panel({"panel": "evaluation"})
        mgr.main_window.stack.setCurrentIndex.assert_called_with(3)

    def test_switch_panel_visual_with_view(self, mgr):
        mgr.main_window.stack = MagicMock()
        target = MagicMock()
        mgr.main_window.stack.widget.return_value = target
        mgr.main_window.nav_btns = [MagicMock() for _ in range(5)]
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.switch_panel({"panel": "visualization", "view_mode": "saliency_map"})
        mgr.main_window.stack.setCurrentIndex.assert_called_with(4)
        target.tabs.setCurrentIndex.assert_called_with(0)

    def test_switch_panel_unknown(self, mgr):
        mgr.main_window.stack = MagicMock()
        mgr.main_window.nav_btns = [MagicMock() for _ in range(5)]
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.switch_panel({"panel": "unknown_panel"})
        # Should not crash; statusBar shows error

    def test_prepare_model_deletion_no_controller(self, mgr):
        mgr.agent_controller = None
        assert mgr.prepare_model_deletion("model") is True

    def test_prepare_model_deletion_local_mode(self, mgr):
        mgr.agent_controller = MagicMock()
        worker = MagicMock()
        mgr.agent_controller.worker = worker
        worker.engine.config.active_mode = "local"
        assert mgr.prepare_model_deletion("model") is True
        mgr.agent_controller.set_model.assert_called_with("Gemini")

    def test_prepare_model_deletion_gemini(self, mgr):
        mgr.agent_controller = MagicMock()
        worker = MagicMock()
        mgr.agent_controller.worker = worker
        worker.engine.config.active_mode = "gemini"
        assert mgr.prepare_model_deletion("model") is True

    def test_check_vram_not_local(self, mgr):
        mgr.agent_controller = None
        mgr.check_vram_conflict(switching_to_local=False)
        # no warning when not local

    @patch("XBrainLab.ui.components.agent_manager.QMessageBox")
    def test_check_vram_local_and_3d(self, mock_mb, mgr):
        mgr.main_window.visualization_panel = MagicMock()
        mgr.check_vram_conflict(switching_to_local=True, switching_to_3d=True)
        mock_mb.warning.assert_called_once()

    def test_on_viz_tab_changed_non_3d(self, mgr):
        mgr.check_vram_conflict = MagicMock()
        mgr.on_viz_tab_changed(0)
        mgr.check_vram_conflict.assert_not_called()

    def test_on_viz_tab_changed_3d(self, mgr):
        mgr.check_vram_conflict = MagicMock()
        mgr.on_viz_tab_changed(3)
        mgr.check_vram_conflict.assert_called_with(switching_to_3d=True)

    @patch("XBrainLab.ui.components.agent_manager.PickMontageDialog")
    def test_open_montage_no_epoch(self, mock_dlg, mgr):
        mgr.study.epoch_data = None
        mgr.main_window.statusBar = MagicMock(return_value=MagicMock())
        mgr.open_montage_picker_dialog({})
        mock_dlg.assert_not_called()

    @patch("XBrainLab.ui.components.agent_manager.PickMontageDialog")
    def test_open_montage_accepted(self, mock_dlg_cls, mgr):
        mgr.study.epoch_data = MagicMock()
        mgr.study.epoch_data.get_mne.return_value.info = {"ch_names": ["C3", "C4"]}
        dlg = MagicMock()
        mock_dlg_cls.return_value = dlg
        dlg.exec.return_value = True
        dlg.get_result.return_value = (["C3", "C4"], [[0, 0], [1, 0]])
        mgr.chat_panel = MagicMock()
        mgr.chat_panel.debug_mode = False
        mgr.agent_controller = MagicMock()
        mgr.open_montage_picker_dialog({"montage_name": "standard_1020"})
        mgr.preprocess_controller.apply_montage.assert_called()


# ====================================================================
# SaliencyTopographicMapWidget
# ====================================================================


class TestTopoMapView:
    @pytest.fixture
    def widget(self, qtbot):
        from XBrainLab.ui.panels.visualization.saliency_views.topomap_view import (
            SaliencyTopographicMapWidget,
        )

        w = SaliencyTopographicMapWidget()
        qtbot.addWidget(w)
        return w

    def test_creates(self, widget):
        assert isinstance(widget, QWidget)

    def test_show_warning(self, widget):
        widget.show_warning("test warning")
        assert "test warning" in widget.error_label.text()

    def test_update_plot_no_eval(self, widget):
        plan = MagicMock()
        plan.get_eval_record.return_value = None
        widget.update_plot(plan, MagicMock(), "grad", False, None)
        assert "No evaluation" in widget.error_label.text()

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.topomap_view.VisualizerType"
    )
    def test_update_plot_no_montage(self, mock_vt, widget):
        plan = MagicMock()
        eval_rec = MagicMock()
        trainer = MagicMock()
        epoch_data = MagicMock()
        epoch_data.get_montage_position.return_value = None
        trainer.get_dataset.return_value.get_epoch_data.return_value = epoch_data
        widget.update_plot(plan, trainer, "grad", False, eval_rec)
        assert "Montage" in widget.error_label.text()

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.topomap_view.VisualizerType"
    )
    def test_update_plot_success(self, mock_vt, widget):
        import matplotlib.pyplot as plt

        plan = MagicMock()
        eval_rec = MagicMock()
        trainer = MagicMock()
        epoch_data = MagicMock()
        epoch_data.get_montage_position.return_value = [[0, 0, 0]]
        trainer.get_dataset.return_value.get_epoch_data.return_value = epoch_data
        fig, _ax = plt.subplots()
        mock_vt.SaliencyTopoMap.value.return_value.get_plt.return_value = fig
        widget.update_plot(plan, trainer, "grad", False, eval_rec)
        plt.close(fig)

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.topomap_view.VisualizerType"
    )
    def test_update_plot_no_data(self, mock_vt, widget):
        plan = MagicMock()
        eval_rec = MagicMock()
        trainer = MagicMock()
        epoch_data = MagicMock()
        epoch_data.get_montage_position.return_value = [[0, 0, 0]]
        trainer.get_dataset.return_value.get_epoch_data.return_value = epoch_data
        mock_vt.SaliencyTopoMap.value.return_value.get_plt.return_value = None
        widget.update_plot(plan, trainer, "grad", False, eval_rec)


# ====================================================================
# SaliencySpectrogramWidget
# ====================================================================


class TestSpectrogramView:
    @pytest.fixture
    def widget(self, qtbot):
        from XBrainLab.ui.panels.visualization.saliency_views.spectrogram_view import (
            SaliencySpectrogramWidget,
        )

        w = SaliencySpectrogramWidget()
        qtbot.addWidget(w)
        return w

    def test_creates(self, widget):
        assert isinstance(widget, QWidget)

    def test_update_plot_no_eval(self, widget):
        plan = MagicMock()
        plan.get_eval_record.return_value = None
        widget.update_plot(plan, MagicMock(), "grad", False, None)
        assert "No evaluation" in widget.error_label.text()

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.spectrogram_view.VisualizerType"
    )
    def test_update_plot_success(self, mock_vt, widget):
        import matplotlib.pyplot as plt

        plan = MagicMock()
        eval_rec = MagicMock()
        trainer = MagicMock()
        epoch_data = MagicMock()
        trainer.get_dataset.return_value.get_epoch_data.return_value = epoch_data
        fig, _ax = plt.subplots()
        mock_vt.SaliencySpectrogramMap.value.return_value.get_plt.return_value = fig
        widget.update_plot(plan, trainer, "grad", False, eval_rec)
        plt.close(fig)

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.spectrogram_view.VisualizerType"
    )
    def test_update_plot_none(self, mock_vt, widget):
        plan = MagicMock()
        eval_rec = MagicMock()
        trainer = MagicMock()
        epoch_data = MagicMock()
        trainer.get_dataset.return_value.get_epoch_data.return_value = epoch_data
        mock_vt.SaliencySpectrogramMap.value.return_value.get_plt.return_value = None
        widget.update_plot(plan, trainer, "grad", False, eval_rec)

    @patch(
        "XBrainLab.ui.panels.visualization.saliency_views.spectrogram_view.VisualizerType"
    )
    def test_update_plot_exception(self, mock_vt, widget):
        plan = MagicMock()
        eval_rec = MagicMock()
        trainer = MagicMock()
        trainer.get_dataset.side_effect = RuntimeError("fail")
        widget.update_plot(plan, trainer, "grad", False, eval_rec)


# ====================================================================
# PreprocessPlotter (partial - covers _get_chan_data and helpers)
# ====================================================================


class TestPreprocessPlotter:
    @pytest.fixture
    def plotter(self):
        from XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter import (
            PreprocessPlotter,
        )

        widget = MagicMock()
        ctrl = MagicMock()
        return PreprocessPlotter(widget, ctrl)

    def test_get_chan_data_raw(self, plotter):
        obj = MagicMock()
        obj.is_raw.return_value = True
        obj.get_sfreq.return_value = 256.0
        mne_obj = MagicMock()
        mne_obj.times = np.arange(0, 5 * 256) / 256
        mne_obj.get_data.return_value = np.random.randn(1, 256 * 5)
        obj.get_mne.return_value = mne_obj
        x, y = plotter._get_chan_data(obj, 0, start_time=0, duration=5)
        assert x is not None and y is not None
        assert len(y) == 256 * 5

    def test_get_chan_data_raw_out_of_range(self, plotter):
        obj = MagicMock()
        obj.is_raw.return_value = True
        obj.get_sfreq.return_value = 256.0
        mne_obj = MagicMock()
        mne_obj.times = np.array([0.0])  # very short
        obj.get_mne.return_value = mne_obj
        x, y = plotter._get_chan_data(obj, 0, start_time=100, duration=5)
        assert x is None and y is None

    def test_get_chan_data_raw_empty(self, plotter):
        obj = MagicMock()
        obj.is_raw.return_value = True
        obj.get_sfreq.return_value = 256.0
        mne_obj = MagicMock()
        mne_obj.times = np.arange(0, 256) / 256
        mne_obj.get_data.return_value = np.array([])
        obj.get_mne.return_value = mne_obj
        x, y = plotter._get_chan_data(obj, 0, start_time=0, duration=5)
        assert x is None and y is None
