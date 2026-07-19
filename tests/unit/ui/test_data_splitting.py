"""Deep coverage tests for DataSplittingDialog, DrawRegion, PreviewCanvas, and more."""

from __future__ import annotations

import threading
from typing import Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QPushButton,
    QSizePolicy,
    QWidget,
)

_REAL_THREAD_CLASS = threading.Thread


def _split_config_payload() -> dict[str, object]:
    return {
        "train_type": "Individual",
        "is_cross_validation": False,
        "val_splitters": [
            {"split_type": "By Trial", "split_unit": "Ratio", "value": "0.2"},
        ],
        "test_splitters": [
            {"split_type": "By Trial", "split_unit": "Ratio", "value": "0.2"},
        ],
    }


# ============ DrawRegion (pure logic, no Qt) ============


class TestDrawRegion:
    def _make(self, w=5, h=5):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import DrawRegion

        return DrawRegion(w, h)

    def test_create(self):
        dr = self._make()
        assert dr.w == 5 and dr.h == 5

    def test_reset(self):
        dr = self._make()
        dr.from_canvas[0, 0] = 1.0
        dr.reset()
        assert dr.from_canvas.sum() == 0.0

    def test_set_from(self):
        dr = self._make()
        dr.set_from(1, 2)
        assert dr.from_x == 1 and dr.from_y == 2

    def test_set_to(self):
        dr = self._make()
        dr.set_from(0, 0)
        dr.set_to(5, 5, 0, 1)
        assert dr.to_canvas.sum() > 0

    def test_set_to_partial(self):
        dr = self._make()
        dr.set_from(0, 0)
        dr.set_to(3, 3, 0.2, 0.8)
        assert dr.to_canvas.sum() > 0

    def test_change_to(self):
        dr = self._make()
        dr.set_from(0, 0)
        dr.set_to(5, 5, 0, 1)
        dr.change_to(3, 3)
        assert dr.to_x == 3 and dr.to_y == 3

    def test_mask(self):
        dr1 = self._make()
        dr2 = self._make()
        dr1.set_from(0, 0)
        dr1.set_to(5, 5, 0, 1)
        dr2.set_from(0, 0)
        dr2.set_to(2, 2, 0, 1)
        dr1.mask(dr2)

    def test_copy(self):
        dr1 = self._make()
        dr2 = self._make()
        dr1.set_from(0, 0)
        dr1.set_to(5, 5, 0, 1)
        dr2.copy(dr1)
        np.testing.assert_array_equal(dr2.from_canvas, dr1.from_canvas)

    def test_decrease_w_tail(self):
        dr = self._make()
        dr.set_from(0, 0)
        dr.set_to(5, 5, 0, 1)
        dr.decrease_w_tail(0.5)

    def test_decrease_w_head(self):
        dr = self._make()
        dr.set_from(0, 0)
        dr.set_to(5, 5, 0, 1)
        dr.decrease_w_head(0.5)

    def test_set_to_ref(self):
        dr1 = self._make()
        dr2 = self._make()
        dr1.set_from(0, 0)
        dr1.set_to(5, 5, 0, 1)
        dr2.set_from(0, 0)
        dr2.set_to_ref(3, 3, dr1)


# ============ PreviewCanvas ============


class TestPreviewCanvas:
    def test_creates(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import PreviewCanvas

        c = PreviewCanvas(None)
        qtbot.addWidget(c)
        assert isinstance(c, PreviewCanvas)

    def test_set_regions(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DrawColor,
            DrawRegion,
            PreviewCanvas,
        )

        c = PreviewCanvas(None)
        qtbot.addWidget(c)

        train = DrawRegion(5, 5)
        train.set_from(0, 0)
        train.set_to(5, 5, 0, 1)
        c.set_regions([(train, DrawColor.TRAIN)])

    def test_paint_event(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DrawColor,
            DrawRegion,
            PreviewCanvas,
        )

        c = PreviewCanvas(None)
        qtbot.addWidget(c)
        c.resize(400, 200)

        train = DrawRegion(5, 5)
        train.set_from(0, 0)
        train.set_to(5, 5, 0, 1)
        c.set_regions([(train, DrawColor.TRAIN)])

        # Trigger repaint
        c.repaint()


# ============ DataSplittingDialog ============


class FakeEpochData:
    def __init__(self) -> None:
        self.subject_map = {
            "S01": list(range(50)),
            "S02": list(range(50, 100)),
        }
        self.session_map = {"sess1": list(range(100))}

    def get_data_length(self) -> int:
        return 100


class FakeDataSplittingController:
    def __init__(self) -> None:
        self.epoch_data = FakeEpochData()
        self.dataset_generator = object()

    def get_epoch_data(self) -> FakeEpochData:
        return self.epoch_data

    def get_dataset_generator(self) -> object:
        return self.dataset_generator


class TestDataSplittingDialog:
    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        ctrl = FakeDataSplittingController()

        d = DataSplittingDialog(None, ctrl)
        qtbot.addWidget(d)
        return d

    def test_creates(self, dlg):
        assert isinstance(dlg, QDialog)

    def test_has_canvas(self, dlg):
        assert isinstance(dlg.canvas, QWidget)

    def test_has_combos(self, dlg):
        assert isinstance(dlg.train_type_combo, QComboBox)
        assert isinstance(dlg.test_combo, QComboBox)
        assert isinstance(dlg.val_combo, QComboBox)

    def test_update_preview_full(self, dlg):
        dlg.train_type_combo.setCurrentText("Full Data")
        dlg.update_preview()

    def test_update_preview_individual(self, dlg):
        dlg.train_type_combo.setCurrentText("Individual")
        dlg.update_preview()

    def test_handle_testing_by_session(self, dlg):
        dlg.test_combo.setCurrentText("By Session")
        dlg.update_preview()

    def test_handle_testing_by_trial(self, dlg):
        dlg.test_combo.setCurrentText("By Trial")
        dlg.update_preview()

    def test_handle_testing_by_subject(self, dlg):
        dlg.test_combo.setCurrentText("By Subject")
        dlg.update_preview()

    def test_handle_validation_by_session(self, dlg):
        dlg.val_combo.setCurrentText("By Session")
        dlg.update_preview()

    def test_handle_validation_by_trial(self, dlg):
        dlg.val_combo.setCurrentText("By Trial")
        dlg.update_preview()

    def test_handle_validation_by_subject(self, dlg):
        dlg.val_combo.setCurrentText("By Subject")
        dlg.update_preview()

    def test_confirm_accepts_preview_result(self, dlg):
        split_config = _split_config_payload()
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_dialog.DataSplittingPreviewDialog"
        ) as MockDlg:
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_result.return_value = split_config
            dlg.confirm()

        MockDlg.assert_called_once()
        assert dlg.get_result() == split_config

    def test_confirm_rejected(self, dlg):
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_dialog.DataSplittingPreviewDialog"
        ) as MockDlg:
            MockDlg.return_value.exec.return_value = False
            dlg.confirm()

    def test_get_result_none(self, dlg):
        assert dlg.get_result() is None

    def test_cv_check(self, dlg):
        dlg.cv_check.setChecked(True)
        assert dlg.cv_check.isChecked()

    def test_handle_testing_disable(self, dlg):
        dlg.test_combo.setCurrentText("Disable")
        dlg.update_preview()

    def test_handle_testing_session_ind(self, dlg):
        dlg.test_combo.setCurrentText("By Session (Independent)")
        dlg.update_preview()

    def test_handle_testing_trial_ind(self, dlg):
        dlg.test_combo.setCurrentText("By Trial (Independent)")
        dlg.update_preview()

    def test_handle_testing_subject_ind(self, dlg):
        dlg.test_combo.setCurrentText("By Subject (Independent)")
        dlg.update_preview()


# ============ DataSplittingPreviewDialog deeper tests ============


class TestDataSplittingPreviewDialogDeep:
    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.backend.dataset import TrainingType

        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.DatasetGenerator"
            ) as MockGen,
            patch("threading.Thread"),
        ):
            MockGen.return_value.preview_failed = None
            from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
                DataSplittingPreviewDialog,
            )

            epoch_data = MagicMock()
            epoch_data.get_data_length.return_value = 100
            epoch_data.subject_map = {
                "S01": list(range(50)),
                "S02": list(range(50, 100)),
            }
            epoch_data.session_map = {"sess1": list(range(100))}
            epoch_data.label_map = {"left": 0, "right": 1}
            epoch_data.get_subject_map.return_value = epoch_data.subject_map
            epoch_data.get_session_map.return_value = epoch_data.session_map

            config = MagicMock()
            config.train_type = TrainingType.FULL
            config.is_cross_validation = False
            config.get_splitter_option.return_value = ([], [])

            d = DataSplittingPreviewDialog(None, "Preview", epoch_data, config)
            qtbot.addWidget(d)
            if hasattr(d, "timer"):
                d.timer.stop()
            return d

    def test_creates(self, dlg):
        assert isinstance(dlg, QDialog)

    def test_get_result(self, dlg):
        result = dlg.get_result()
        # Before preview runs, result should be the generator (or None)
        assert result is None or hasattr(result, "__iter__")

    def test_obsolete_show_split_button_is_not_rendered(self, dlg):
        assert dlg.btn_info is None

        dataset = MagicMock()
        dataset.get_treeview_row_info.return_value = ["", "Split A", 8, 1, 1]
        dlg.datasets = [dataset]
        dlg.update_table()

        button_texts = [button.text() for button in dlg.findChildren(QPushButton)]
        assert not any("show" in text.lower() for text in button_texts)


# ============ DataSplittingPreviewDialog with splitter options ============


class TestDataSplittingPreviewDialogSplitters:
    """Exercise init_ui widget creation + methods with is_option splitters."""

    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.backend.dataset import SplitByType, TrainingType, ValSplitByType

        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.DatasetGenerator"
            ) as MockGen,
            patch("threading.Thread"),
        ):
            MockGen.return_value.preview_failed = None
            MockGen.return_value.generate = MagicMock()
            from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
                DataSplitterHolder,
                DataSplittingPreviewDialog,
            )

            epoch_data = MagicMock()
            epoch_data.get_data_length.return_value = 100
            epoch_data.subject_map = {
                "S01": list(range(50)),
                "S02": list(range(50, 100)),
            }
            epoch_data.session_map = {"sess1": list(range(100))}
            epoch_data.label_map = {"left": 0, "right": 1}
            epoch_data.data = list(range(100))
            epoch_data.get_subject_map.return_value = epoch_data.subject_map
            epoch_data.get_session_map.return_value = epoch_data.session_map

            val_splitters = [
                DataSplitterHolder(is_option=True, split_type=ValSplitByType.SESSION),
                DataSplitterHolder(is_option=False, split_type=ValSplitByType.SESSION),
            ]
            test_splitters = [
                DataSplitterHolder(is_option=True, split_type=SplitByType.SUBJECT),
            ]

            config = MagicMock()
            config.train_type = TrainingType.FULL
            config.is_cross_validation = False
            config.get_splitter_option.return_value = (
                val_splitters,
                test_splitters,
            )
            d = DataSplittingPreviewDialog(None, "Preview", epoch_data, config)
            qtbot.addWidget(d)
            if hasattr(d, "timer"):
                d.timer.stop()
            yield d

    def test_creates_with_option_splitters(self, dlg):
        assert isinstance(dlg, QDialog)
        dialog = cast(Any, dlg)
        assert len(dialog.val_widgets) >= 1
        assert len(dialog.test_widgets) >= 1

    def test_on_split_type_change(self, dlg):
        splitter = dlg.val_splitter_list[0]
        dlg.on_split_type_change(splitter, "By Ratio")

    def test_on_entry_change(self, dlg):
        splitter = dlg.val_splitter_list[0]
        dlg.on_entry_change(splitter, "0.3")

    def test_on_entry_change_debounces_preview_worker_restart(self, dlg):
        splitter = dlg.val_splitter_list[0]
        with patch.object(dlg, "preview") as preview:
            dlg.on_entry_change(splitter, "0.4")

        preview.assert_not_called()
        assert dlg.preview_debounce_timer is not None
        assert dlg.preview_debounce_timer.isActive()
        dlg.preview_debounce_timer.stop()

    def test_cross_validation_defaults_testing_to_kfold(self, qtbot):
        from XBrainLab.backend.dataset import SplitByType, TrainingType, ValSplitByType

        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.DatasetGenerator"
            ) as MockGen,
            patch("threading.Thread"),
        ):
            MockGen.return_value.preview_failed = None
            MockGen.return_value.generate = MagicMock()
            from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
                DataSplitterHolder,
                DataSplittingPreviewDialog,
            )

            epoch_data = MagicMock()
            epoch_data.get_data_length.return_value = 100
            epoch_data.subject_map = {"S01": list(range(100))}
            epoch_data.session_map = {"sess1": list(range(100))}
            epoch_data.label_map = {"left": 0, "right": 1}
            epoch_data.data = list(range(100))
            epoch_data.get_subject_map.return_value = epoch_data.subject_map
            epoch_data.get_session_map.return_value = epoch_data.session_map

            val_splitters = [
                DataSplitterHolder(is_option=True, split_type=ValSplitByType.TRIAL),
            ]
            test_splitters = [
                DataSplitterHolder(is_option=True, split_type=SplitByType.TRIAL),
            ]

            config = MagicMock()
            config.train_type = TrainingType.FULL
            config.is_cross_validation = True
            config.get_splitter_option.return_value = (
                val_splitters,
                test_splitters,
            )
            dialog = DataSplittingPreviewDialog(None, "Preview", epoch_data, config)
            qtbot.addWidget(dialog)
            if hasattr(dialog, "timer"):
                dialog.timer.stop()

        test_combo, test_entry = dialog.test_widgets[0]
        val_combo, val_entry = dialog.val_widgets[0]

        assert test_combo.currentText() == "K Fold"
        assert test_entry.text() == "5"
        assert val_combo.currentText() == "Ratio"
        assert val_entry.text() == "0.2"

        payload = dialog.get_result()
        assert payload is not None
        assert payload["is_cross_validation"] is True
        assert payload["test_splitters"][0]["split_unit"] == "K Fold"
        assert payload["test_splitters"][0]["value"] == "5"
        assert payload["val_splitters"][0]["split_unit"] == "Ratio"

    def test_step2_layout_shrinks_to_content_without_footer_stretch(self, dlg):
        assert dlg.layout().sizeConstraint().name != "SetDefaultConstraint"
        assert dlg.minimumHeight() < 500
        assert dlg.height() <= 520
        assert dlg.tree.height() <= 84

        right_panel_heights = [
            panel.sizePolicy().verticalPolicy()
            for panel in dlg.findChildren(QWidget)
            if panel.objectName() == "SplitPreviewPanel"
        ]
        assert QSizePolicy.Policy.Maximum in right_panel_heights

    def test_step2_results_table_uses_width_without_small_row_scrollbar(self, dlg):
        for i in range(5):
            dataset = MagicMock()
            dataset.get_treeview_row_info.return_value = [
                "",
                f"Fold_{i}",
                80 - i,
                10,
                10 + i,
            ]
            dlg.datasets.append(dataset)

        dlg.update_table()
        dlg.show()

        assert dlg.tree.topLevelItemCount() == 5
        assert dlg.tree.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
        assert (
            dlg.tree.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert dlg.tree.verticalScrollBar().maximum() == 0
        assert dlg.tree.width() >= int(dlg.contentsRect().width() * 0.45)

    def test_step2_cards_do_not_use_vertical_separator_frames(self, dlg):
        separators = [
            frame
            for frame in dlg.findChildren(QFrame)
            if frame.frameShape() == QFrame.Shape.VLine
            or "separator" in frame.objectName().lower()
            or "divider" in frame.objectName().lower()
        ]
        assert separators == []

    def test_on_split_type_manual(self, dlg):
        splitter = dlg.val_splitter_list[0]
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.ManualSplitDialog"
        ) as MockDlg:
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_result.return_value = [0, 1]
            dlg.on_split_type_change(splitter, "Manual")

    def test_handle_manual_split_session(self, dlg):
        splitter = dlg.val_splitter_list[0]
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.ManualSplitDialog"
        ) as MockDlg:
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_result.return_value = ["sess1"]
            dlg.handle_manual_split(splitter)

    def test_handle_manual_split_subject(self, dlg):
        splitter = dlg.test_splitter_list[0]
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.ManualSplitDialog"
        ) as MockDlg:
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_result.return_value = ["S01"]
            dlg.handle_manual_split(splitter)

    def test_update_table_with_datasets(self, dlg):
        mock_ds = MagicMock()
        mock_ds.get_treeview_row_info.return_value = ["", "ds1", "80", "10", "10"]
        dlg.datasets.append(mock_ds)
        dlg.update_table()

    def test_update_table_preview_failed(self, dlg):
        dlg.dataset_generator = MagicMock()
        dlg.dataset_generator.preview_failed = True
        dlg.update_table()

    def test_obsolete_show_info_action_is_removed(self, dlg):
        assert not hasattr(dlg, "show_info")

    def test_confirm_worker_alive(self, dlg):
        dlg.preview_worker = MagicMock()
        dlg.preview_worker.is_alive.return_value = True
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.QMessageBox"
        ):
            dlg.confirm()

    def test_confirm_success(self, dlg):
        dlg.preview_worker = MagicMock()
        dlg.preview_worker.is_alive.return_value = False
        dlg.dataset_generator = MagicMock()
        dlg.timer = MagicMock()
        dlg.preview_debounce_timer = MagicMock()
        dlg._preview_status = "succeeded"
        with patch.object(type(dlg), "accept"):
            dlg.confirm()
            dlg.dataset_generator.prepare_result.assert_called_once()
            dlg.timer.stop.assert_called_once()
            dlg.preview_debounce_timer.stop.assert_called_once()

    def test_confirm_error(self, dlg):
        dlg.preview_worker = MagicMock()
        dlg.preview_worker.is_alive.return_value = False
        dlg.dataset_generator = MagicMock()
        dlg.dataset_generator.prepare_result.side_effect = RuntimeError("fail")
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.QMessageBox"
        ):
            dlg.confirm()

    def test_unexpected_preview_exception_is_visible_and_confirm_does_not_retry(
        self,
        dlg,
    ):
        generator = MagicMock()
        generator.generate.side_effect = RuntimeError("split backend failed")
        generator.interrupted = False
        generator.preview_failed = False
        dlg.dataset_generator = None
        dlg.preview_worker = None

        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.DatasetGenerator",
                return_value=generator,
            ),
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.threading.Thread",
                _REAL_THREAD_CLASS,
            ),
        ):
            dlg.preview()
            worker = dlg.preview_worker
            assert worker is not None
            worker.join(timeout=1.0)

        assert worker.is_alive() is False
        generator.generate.assert_called_once_with()
        dlg.update_table()

        assert dlg._preview_status == "failed"
        assert dlg._preview_error == "split backend failed"
        assert dlg.tree.topLevelItem(0).text(0) == "Preview failed"
        assert dlg.btn_confirm.isEnabled() is False

        with patch.object(dlg, "_show_message_box") as message:
            dlg.confirm()

        generator.prepare_result.assert_not_called()
        assert "split backend failed" in message.call_args.args[2]

    def test_close_stops_timer_and_generator_after_worker_exits(self, dlg):
        from PyQt6.QtGui import QCloseEvent

        dlg.timer = MagicMock()
        dlg.dataset_generator = MagicMock()
        dlg.preview_worker = MagicMock()
        dlg.preview_worker.is_alive.return_value = False
        event = QCloseEvent()
        dlg.closeEvent(event)
        dlg.timer.stop.assert_called_once()
        dlg.dataset_generator.set_interrupt.assert_called_once()
        dlg.preview_worker.join.assert_not_called()
        assert event.isAccepted() is True

    def test_preview_does_not_replace_worker_that_is_still_alive(self, dlg):
        old_generator = MagicMock()
        old_worker = MagicMock()
        old_worker.is_alive.return_value = True
        new_worker = MagicMock()
        dlg.dataset_generator = old_generator
        dlg.preview_worker = old_worker

        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.DatasetGenerator"
            ) as mock_generator,
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.threading.Thread",
                return_value=new_worker,
            ),
        ):
            mock_generator.return_value.preview_failed = None
            dlg.preview()

        old_generator.set_interrupt.assert_called_once()
        old_worker.join.assert_not_called()
        new_worker.start.assert_not_called()
        assert dlg.dataset_generator is old_generator
        assert dlg.preview_worker is old_worker
        assert dlg.preview_debounce_timer.isActive()
        dlg.preview_debounce_timer.stop()
        old_worker.is_alive.return_value = False

    def test_preview_restarts_after_previous_worker_exits(self, dlg):
        old_generator = MagicMock()
        old_worker = MagicMock()
        old_worker.is_alive.return_value = True
        new_worker = MagicMock()
        new_worker.is_alive.return_value = False
        dlg.dataset_generator = old_generator
        dlg.preview_worker = old_worker

        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.DatasetGenerator"
            ) as mock_generator,
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.threading.Thread",
                return_value=new_worker,
            ),
        ):
            mock_generator.return_value.preview_failed = None
            dlg.preview()

            assert new_worker.start.call_count == 0
            assert dlg.preview_debounce_timer.isActive()
            dlg.preview_debounce_timer.stop()
            old_worker.is_alive.return_value = False
            dlg.preview()

        assert old_generator.set_interrupt.call_count == 2
        old_worker.join.assert_not_called()
        new_worker.start.assert_called_once()
        assert dlg.dataset_generator is mock_generator.return_value
        assert dlg.preview_worker is new_worker

    def test_close_waits_for_preview_worker_ownership_release(self, dlg):
        from PyQt6.QtGui import QCloseEvent

        dlg.timer = MagicMock()
        dlg.dataset_generator = MagicMock()
        dlg.preview_worker = MagicMock()
        dlg.preview_worker.is_alive.return_value = True
        event = QCloseEvent()

        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.QTimer.singleShot"
        ) as retry:
            dlg.closeEvent(event)
            dlg.closeEvent(QCloseEvent())

        assert event.isAccepted() is False
        assert dlg.dataset_generator is not None
        assert dlg.preview_worker is not None
        retry.assert_called_once()
        dlg.preview_worker.is_alive.return_value = False

    def test_close_retry_only_closes_after_preview_worker_exits(self, dlg):
        dlg.preview_worker = MagicMock()
        dlg.preview_worker.is_alive.return_value = True

        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.QTimer.singleShot"
            ) as retry,
            patch.object(dlg, "close") as close,
        ):
            dlg._close_when_preview_worker_stops()
            close.assert_not_called()
            retry.assert_called_once()

            dlg.preview_worker.is_alive.return_value = False
            dlg._close_when_preview_worker_stops()
            close.assert_called_once()

    def test_escape_waits_for_real_preview_worker_before_rejecting(self, dlg, qtbot):
        release_worker = threading.Event()
        worker = _REAL_THREAD_CLASS(target=release_worker.wait)
        worker.start()
        dlg.dataset_generator = MagicMock()
        dlg.preview_worker = worker
        dlg.show()

        callbacks = []
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.QTimer.singleShot",
            side_effect=lambda _delay, callback: callbacks.append(callback),
        ):
            qtbot.keyClick(dlg, Qt.Key.Key_Escape)

        assert dlg.isVisible() is True
        dlg.dataset_generator.set_interrupt.assert_called_once()
        assert len(callbacks) == 1
        assert dlg._preview_pending_close_action == "reject"

        release_worker.set()
        worker.join(timeout=1.0)
        assert worker.is_alive() is False
        callbacks[0]()
        assert dlg.result() == QDialog.DialogCode.Rejected
        assert dlg._preview_pending_close_action is None
        qtbot.waitUntil(lambda: not dlg.isVisible(), timeout=1000)

    def test_window_close_waits_for_real_preview_worker_and_clears_timers(
        self,
        dlg,
        qtbot,
    ):
        release_worker = threading.Event()
        worker = _REAL_THREAD_CLASS(target=release_worker.wait)
        worker.start()
        dlg.dataset_generator = MagicMock()
        dlg.preview_worker = worker
        dlg.show()
        callbacks = []

        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.QTimer.singleShot",
            side_effect=lambda _delay, callback: callbacks.append(callback),
        ):
            assert dlg.close() is False

        assert dlg.isVisible() is True
        assert len(callbacks) == 1
        assert dlg._preview_pending_close_action == "close"

        release_worker.set()
        worker.join(timeout=1.0)
        assert worker.is_alive() is False
        callbacks[0]()

        qtbot.waitUntil(lambda: not dlg.isVisible(), timeout=1000)
        assert dlg._preview_pending_close_action is None
        assert dlg._preview_close_retry_pending is False
        assert dlg.preview_debounce_timer.isActive() is False
        assert dlg.timer.isActive() is False

    def test_preview_close_retry_continues_safely_after_timeout(self, dlg):
        dlg.dataset_generator = MagicMock()
        dlg.preview_worker = MagicMock()
        dlg.preview_worker.is_alive.return_value = True
        dlg.show()

        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.time.monotonic",
                side_effect=[10.0, 16.0],
            ),
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.QTimer.singleShot"
            ) as retry,
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.QMessageBox.warning"
            ) as warning,
        ):
            dlg.reject()
            callback = retry.call_args.args[1]
            callback()
            final_callback = retry.call_args.args[1]

            warning.assert_called_once()
            assert retry.call_count == 2
            assert dlg.isVisible() is True
            assert dlg._preview_close_retry_pending is True
            assert dlg._preview_pending_close_action == "reject"

            dlg.preview_worker.is_alive.return_value = False
            final_callback()

        assert dlg.result() == QDialog.DialogCode.Rejected
        assert dlg._preview_close_retry_pending is False
        assert dlg._preview_pending_close_action is None

    def test_preview_close_callback_ignores_deleted_qt_wrapper(self, dlg):
        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.sip.isdeleted",
                return_value=True,
            ),
            patch.object(dlg, "close") as close,
        ):
            dlg._close_when_preview_worker_stops()

        close.assert_not_called()
