"""Deep coverage tests for DataSplittingDialog, DrawRegion, PreviewCanvas, and more."""

from __future__ import annotations

import threading
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from tests.unit.ui.data_split_test_support import (
    dialog_context_kwargs,
    split_context,
    successful_preview,
)
from XBrainLab.backend.application.dataset_split_preview import (
    DatasetSplitPreviewRow,
)

_REAL_THREAD_CLASS = threading.Thread


class _HostileExceptionMeta(type):
    def __getattribute__(cls, name: str) -> object:
        if name == "__name__":
            raise AssertionError("hostile exception metaclass name access executed")
        return super().__getattribute__(name)


class _HostileSplitError(Exception, metaclass=_HostileExceptionMeta):
    def __str__(self) -> str:
        raise AssertionError("hostile exception string protocol executed")


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


# DataSplittingDialog unit behavior is owned by dialogs/test_data_splitting.py.
# This module retains the detached preview and worker-lifecycle contracts.


class TestDataSplittingPreviewDialogDeep:
    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.backend.dataset import TrainingType

        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.is_alive.return_value = False
            from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
                DataSplittingPreviewDialog,
            )

            config = MagicMock()
            config.train_type = TrainingType.FULL
            config.is_cross_validation = False
            config.get_splitter_option.return_value = ([], [])

            d = DataSplittingPreviewDialog(
                None,
                "Preview",
                config=config,
                **dialog_context_kwargs(),
            )
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

    def test_full_data_result_after_successful_preview(self, dlg):
        dlg._set_preview_state(
            dlg._preview_generation_id,
            "succeeded",
            rows=(
                DatasetSplitPreviewRow(
                    name="Fold_0",
                    train_count=80,
                    validation_count=10,
                    test_count=10,
                ),
            ),
        )

        assert dlg.get_result() == {
            "train_type": "Full Data",
            "is_cross_validation": False,
            "val_splitters": [],
            "test_splitters": [],
        }

    def test_obsolete_show_split_button_is_not_rendered(self, dlg):
        assert dlg.btn_info is None

        dlg._set_preview_state(
            dlg._preview_generation_id,
            "succeeded",
            rows=(
                DatasetSplitPreviewRow(
                    name="Split A",
                    train_count=8,
                    validation_count=1,
                    test_count=1,
                ),
            ),
        )
        dlg.update_table()

        button_texts = [button.text() for button in dlg.findChildren(QPushButton)]
        assert not any("show" in text.lower() for text in button_texts)


# ============ DataSplittingPreviewDialog with splitter options ============


class TestDataSplittingPreviewDialogSplitters:
    """Exercise init_ui widget creation + methods with is_option splitters."""

    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.backend.dataset import SplitByType, TrainingType, ValSplitByType

        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.is_alive.return_value = False
            from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
                DataSplitterHolder,
                DataSplittingPreviewDialog,
            )

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
            d = DataSplittingPreviewDialog(
                None,
                "Preview",
                config=config,
                **dialog_context_kwargs(),
            )
            qtbot.addWidget(d)
            if hasattr(d, "timer"):
                d.timer.stop()
            yield d

    def test_creates_with_option_splitters(self, dlg):
        assert isinstance(dlg, QDialog)
        dialog = cast(Any, dlg)
        assert len(dialog.val_widgets) >= 1
        assert len(dialog.test_widgets) >= 1
        assert not hasattr(dialog, "epoch_data")
        assert not hasattr(dialog, "dataset_generator")
        assert not hasattr(dialog, "datasets")

    def test_preview_worker_renders_detached_application_rows(self, dlg):
        dlg.preview_provider = successful_preview
        dlg.preview_worker = None
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.threading.Thread",
            _REAL_THREAD_CLASS,
        ):
            dlg.preview()
            worker = dlg.preview_worker
            assert worker is not None
            worker.join(timeout=1.0)

        assert worker.is_alive() is False
        dlg.update_table()
        assert dlg._preview_status == "succeeded"
        assert dlg.tree.topLevelItem(0).text(0) == "Fold 1"
        assert dlg.tree.topLevelItem(0).text(1) == "80"
        assert dlg.tree.topLevelItem(0).text(2) == "10"
        assert dlg.tree.topLevelItem(0).text(3) == "10"
        assert dlg.tree.columnCount() == 4

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

        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.is_alive.return_value = False
            from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
                DataSplitterHolder,
                DataSplittingPreviewDialog,
            )

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
            dialog = DataSplittingPreviewDialog(
                None,
                "Preview",
                config=config,
                **dialog_context_kwargs(context=split_context(subject_count=1)),
            )
            qtbot.addWidget(dialog)
            if hasattr(dialog, "timer"):
                dialog.timer.stop()

        test_combo, test_entry = dialog.test_widgets[0]
        val_combo, val_entry = dialog.val_widgets[0]

        assert test_combo.currentText() == "K Fold"
        assert test_entry.text() == "5"
        assert val_combo.currentText() == "Ratio"
        assert val_entry.text() == "0.2"

        dialog._set_preview_state(
            dialog._preview_generation_id,
            "succeeded",
            rows=(
                DatasetSplitPreviewRow(
                    name="Fold_0",
                    train_count=80,
                    validation_count=10,
                    test_count=10,
                ),
            ),
        )
        payload = dialog.get_result()
        assert payload is not None
        assert payload["is_cross_validation"] is True
        assert payload["test_splitters"][0]["split_unit"] == "K Fold"
        assert payload["test_splitters"][0]["value"] == "5"
        assert payload["val_splitters"][0]["split_unit"] == "Ratio"

    def test_step2_layout_fits_available_screen_without_footer_stretch(self, dlg):
        assert dlg.layout().sizeConstraint().name != "SetDefaultConstraint"
        assert dlg.minimumHeight() < 500
        assert dlg.screen() is not None
        available = dlg.screen().availableGeometry()
        assert dlg.height() <= available.height() - 48
        assert dlg.tree.height() <= 84
        assert dlg.btn_confirm is not None
        confirm_bounds = QRect(
            dlg.btn_confirm.mapTo(dlg, QPoint(0, 0)),
            dlg.btn_confirm.size(),
        )
        assert dlg.rect().contains(confirm_bounds)

        right_panel_heights = [
            panel.sizePolicy().verticalPolicy()
            for panel in dlg.findChildren(QWidget)
            if panel.objectName() == "SplitPreviewPanel"
        ]
        assert QSizePolicy.Policy.Maximum in right_panel_heights

    def test_step2_results_table_keeps_full_headers_with_one_scroll_owner(
        self,
        dlg,
        qtbot,
    ):
        rows = tuple(
            DatasetSplitPreviewRow(
                name=f"Fold_{index}",
                train_count=80 - index,
                validation_count=10,
                test_count=10 + index,
            )
            for index in range(5)
        )
        dlg._set_preview_state(dlg._preview_generation_id, "succeeded", rows=rows)
        dlg.update_table()
        dlg.show()
        qtbot.waitUntil(
            lambda: dlg.tree.verticalScrollBar().maximum() == 0,
            timeout=1_000,
        )

        assert dlg.tree.topLevelItemCount() == 5
        assert dlg.tree.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
        assert (
            dlg.tree.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert dlg.tree.verticalScrollBar().maximum() == 0
        viewport = dlg.tree.viewport()
        header = dlg.tree.header()
        assert viewport is not None
        assert header is not None
        horizontal_scrollbar = dlg.tree.horizontalScrollBar()
        assert horizontal_scrollbar is not None
        if header.length() > viewport.width():
            assert horizontal_scrollbar.maximum() > 0
        else:
            assert abs(header.length() - viewport.width()) <= 2
            assert horizontal_scrollbar.maximum() == 0
        header_item = dlg.tree.headerItem()
        assert header_item is not None
        assert [header_item.text(column) for column in range(4)] == [
            "Split",
            "Train",
            "Validation",
            "Test",
        ]
        assert [header_item.toolTip(column) for column in range(4)] == [
            "Split",
            "Training rows",
            "Validation rows",
            "Test rows",
        ]

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

    def test_update_table_with_detached_rows(self, dlg):
        dlg._set_preview_state(
            dlg._preview_generation_id,
            "succeeded",
            rows=(
                DatasetSplitPreviewRow(
                    name="ds1",
                    train_count=80,
                    validation_count=10,
                    test_count=10,
                ),
            ),
        )
        dlg.update_table()
        assert dlg.tree.topLevelItem(0).text(0) == "ds1"

    def test_update_table_preview_failed(self, dlg):
        dlg._set_preview_state(
            dlg._preview_generation_id,
            "failed",
            "Preview failed safely.",
        )
        dlg.update_table()
        assert dlg.tree.topLevelItem(0).text(0) == "Preview failed"

    def test_debounce_clears_rows_that_no_longer_match_controls(self, dlg):
        dlg._set_preview_state(
            dlg._preview_generation_id,
            "succeeded",
            rows=(
                DatasetSplitPreviewRow(
                    name="stale split",
                    train_count=80,
                    validation_count=10,
                    test_count=10,
                ),
            ),
        )
        dlg.update_table()
        assert dlg.tree.topLevelItem(0).text(0) == "stale split"

        dlg.on_entry_change(dlg.val_splitter_list[0], "0.4")

        visible_rows = [
            dlg.tree.topLevelItem(index).text(0)
            for index in range(dlg.tree.topLevelItemCount())
        ]
        assert "stale split" not in visible_rows
        assert visible_rows == ["Updating preview"]
        assert dlg.preview_debounce_timer.isActive()
        dlg.preview_debounce_timer.stop()

    def test_preview_failure_shows_reason_and_continuously_available_back_action(
        self,
        dlg,
        qtbot,
    ):
        dlg._set_preview_state(
            dlg._preview_generation_id,
            "failed",
            "The requested validation ratio leaves no training rows.",
        )
        dlg.show()
        dlg.update_table()
        qtbot.wait(0)

        assert dlg.preview_status_label is not None
        assert dlg.preview_status_label.isVisibleTo(dlg)
        assert dlg.preview_status_label.text() == (
            "The requested validation ratio leaves no training rows."
        )
        assert dlg.btn_back is not None
        assert dlg.btn_back.text() == "Back"
        assert dlg.btn_back.isVisibleTo(dlg)
        assert dlg.btn_back.isEnabled()
        assert dlg.btn_back.minimumWidth() == dlg.btn_confirm.minimumWidth()
        assert dlg.btn_confirm.isEnabled() is False

        dlg.btn_back.click()
        qtbot.waitUntil(lambda: not dlg.isVisible(), timeout=1000)

    def test_obsolete_show_info_action_is_removed(self, dlg):
        assert not hasattr(dlg, "show_info")

    def test_confirm_worker_alive(self, dlg):
        dlg.preview_worker = MagicMock()
        dlg.preview_worker.is_alive.return_value = True
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.show_warning"
        ):
            dlg.confirm()

    def test_confirm_success(self, dlg):
        dlg.preview_worker = MagicMock()
        dlg.preview_worker.is_alive.return_value = False
        dlg.timer = MagicMock()
        dlg.preview_debounce_timer = MagicMock()
        dlg._set_preview_state(
            dlg._preview_generation_id,
            "succeeded",
            rows=(
                DatasetSplitPreviewRow(
                    name="Fold_0",
                    train_count=80,
                    validation_count=10,
                    test_count=10,
                ),
            ),
        )
        with patch.object(type(dlg), "accept"):
            dlg.confirm()
            dlg.timer.stop.assert_called_once()
            dlg.preview_debounce_timer.stop.assert_called_once()

    def test_confirm_without_successful_preview_is_blocked(self, dlg):
        dlg.preview_worker = MagicMock()
        dlg.preview_worker.is_alive.return_value = False
        dlg._set_preview_state(dlg._preview_generation_id, "idle")
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.show_error"
        ) as message:
            dlg.confirm()
        message.assert_called_once_with(
            dlg,
            "Data splitting failed",
            "The split preview failed. Adjust the split settings and try again.",
        )

    def test_unexpected_preview_exception_is_visible_and_confirm_does_not_retry(
        self,
        dlg,
    ):
        provider = MagicMock(side_effect=RuntimeError("split backend failed"))
        dlg.preview_provider = provider
        dlg.preview_worker = None

        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.threading.Thread",
            _REAL_THREAD_CLASS,
        ):
            dlg.preview()
            worker = dlg.preview_worker
            assert worker is not None
            worker.join(timeout=1.0)

        assert worker.is_alive() is False
        provider.assert_called_once()
        dlg.update_table()

        assert dlg._preview_status == "failed"
        assert dlg._preview_error.endswith("split backend failed")
        assert dlg.tree.topLevelItem(0).text(0) == "Preview failed"
        assert dlg.btn_confirm.isEnabled() is False

        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.show_error"
        ) as message:
            dlg.confirm()

        assert "split backend failed" in message.call_args.args[2]

    def test_preview_contains_hostile_exception_at_public_boundary(self, dlg):
        def hostile_provider(_request):
            raise _HostileSplitError("/srv/Clinical Records/Mary Example")

        dlg.preview_provider = hostile_provider
        dlg.preview_worker = None
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.threading.Thread",
            _REAL_THREAD_CLASS,
        ):
            dlg.preview()
            worker = dlg.preview_worker
            assert worker is not None
            worker.join(timeout=1.0)

        assert dlg._preview_status == "failed"
        assert dlg._preview_error == (
            "The split preview failed. Adjust the split settings and try again."
        )
        assert "Mary Example" not in dlg._preview_error

    def test_confirm_does_not_regenerate_domain_datasets(self, dlg):
        dlg.preview_worker = MagicMock()
        dlg.preview_worker.is_alive.return_value = False
        provider = MagicMock()
        dlg.preview_provider = provider
        dlg._set_preview_state(
            dlg._preview_generation_id,
            "succeeded",
            rows=(
                DatasetSplitPreviewRow(
                    name="Fold_0",
                    train_count=80,
                    validation_count=10,
                    test_count=10,
                ),
            ),
        )

        with patch.object(type(dlg), "accept"):
            dlg.confirm()

        provider.assert_not_called()

    def test_expected_preview_precondition_is_visible_without_error_traceback(
        self,
        dlg,
    ):
        from XBrainLab.backend.application.errors import PreconditionError

        dlg.preview_provider = MagicMock(
            side_effect=PreconditionError(
                "Dataset split preview is infeasible: one subject cannot be split by subject."
            )
        )
        dlg.preview_worker = None

        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.threading.Thread",
                _REAL_THREAD_CLASS,
            ),
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.logger.exception"
            ) as logged,
        ):
            dlg.preview()
            worker = dlg.preview_worker
            assert worker is not None
            worker.join(timeout=1.0)

        assert worker.is_alive() is False
        assert dlg._preview_status == "failed"
        assert "one subject cannot be split" in dlg._preview_error
        logged.assert_not_called()

    def test_close_stops_timer_after_worker_exits(self, dlg):
        from PyQt6.QtGui import QCloseEvent

        dlg.timer = MagicMock()
        dlg.preview_canceller = MagicMock()
        dlg.preview_worker = MagicMock()
        dlg.preview_worker.is_alive.return_value = False
        event = QCloseEvent()
        dlg.closeEvent(event)
        dlg.timer.stop.assert_called_once()
        dlg.preview_canceller.assert_not_called()
        dlg.preview_worker.join.assert_not_called()
        assert event.isAccepted() is True

    def test_preview_does_not_replace_worker_that_is_still_alive(self, dlg):
        old_worker = MagicMock()
        old_worker.is_alive.return_value = True
        new_worker = MagicMock()
        dlg.preview_worker = old_worker
        dlg.preview_canceller = MagicMock(return_value=True)
        dlg._active_preview_request = (9, "active-preview")

        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.threading.Thread",
            return_value=new_worker,
        ):
            dlg.preview()

        dlg.preview_canceller.assert_called_once_with("active-preview")
        old_worker.join.assert_not_called()
        new_worker.start.assert_not_called()
        assert dlg.preview_worker is old_worker
        assert dlg.preview_debounce_timer.isActive()
        dlg.preview_debounce_timer.stop()
        old_worker.is_alive.return_value = False

    def test_edit_cancels_running_preview_before_debouncing_replacement(self, dlg):
        worker = MagicMock()
        worker.is_alive.return_value = True
        dlg.preview_worker = worker
        dlg.preview_canceller = MagicMock(return_value=True)
        dlg._active_preview_request = (1, "active-preview")

        dlg.schedule_preview()

        dlg.preview_canceller.assert_called_once_with("active-preview")
        assert dlg.preview_debounce_timer.isActive()
        dlg.preview_debounce_timer.stop()

    def test_preview_restarts_after_previous_worker_exits(self, dlg):
        old_worker = MagicMock()
        old_worker.is_alive.return_value = True
        new_worker = MagicMock()
        new_worker.is_alive.return_value = False
        dlg.preview_worker = old_worker
        dlg.preview_canceller = MagicMock(return_value=True)
        dlg._active_preview_request = (9, "active-preview")

        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.threading.Thread",
            return_value=new_worker,
        ):
            dlg.preview()

            assert new_worker.start.call_count == 0
            assert dlg.preview_debounce_timer.isActive()
            dlg.preview_debounce_timer.stop()
            old_worker.is_alive.return_value = False
            dlg.preview()

        dlg.preview_canceller.assert_called_once_with("active-preview")
        old_worker.join.assert_not_called()
        new_worker.start.assert_called_once()
        assert dlg.preview_worker is new_worker

    def test_close_waits_for_preview_worker_ownership_release(self, dlg):
        from PyQt6.QtGui import QCloseEvent

        dlg.timer = MagicMock()
        dlg.preview_canceller = MagicMock(return_value=True)
        dlg.preview_worker = MagicMock()
        dlg.preview_worker.is_alive.return_value = True
        dlg._active_preview_request = (9, "active-preview")
        event = QCloseEvent()

        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.QTimer.singleShot"
        ) as retry:
            dlg.closeEvent(event)
            dlg.closeEvent(QCloseEvent())

        assert event.isAccepted() is False
        assert dlg.preview_worker is not None
        dlg.preview_canceller.assert_called()
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
        dlg.preview_canceller = MagicMock(return_value=True)
        dlg._active_preview_request = (9, "active-preview")
        dlg.preview_worker = worker
        dlg.show()

        callbacks = []
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.QTimer.singleShot",
            side_effect=lambda _delay, callback: callbacks.append(callback),
        ):
            qtbot.keyClick(dlg, Qt.Key.Key_Escape)

        assert dlg.isVisible() is True
        dlg.preview_canceller.assert_called_once_with("active-preview")
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
        dlg.preview_canceller = MagicMock(return_value=True)
        dlg._active_preview_request = (9, "active-preview")
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
        dlg.preview_canceller = MagicMock(return_value=True)
        dlg._active_preview_request = (9, "active-preview")
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
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.show_warning"
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
