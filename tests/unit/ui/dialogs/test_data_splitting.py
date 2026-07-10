"""Coverage tests for DataSplittingDialog - 218 uncovered lines."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QTreeWidgetItem, QWidget

from XBrainLab.backend.study import Study


@pytest.fixture
def epoch_data():
    """Mock epoch data for DataSplittingDialog."""
    ed = MagicMock()
    ed.get_data_length.return_value = 100
    ed.subject_map = {"S01": [0, 1, 2], "S02": [3, 4, 5]}
    ed.session_map = {"sess1": [0, 1, 2, 3, 4, 5]}
    ed.label_map = {"left": 0, "right": 1}
    ed.data = MagicMock()
    ed.get_subject_map.return_value = ed.subject_map
    ed.get_session_map.return_value = ed.session_map
    return ed


@pytest.fixture
def controller(epoch_data):
    ctrl = MagicMock()
    ctrl.get_epoch_data.return_value = epoch_data
    ctrl.get_dataset_generator.return_value = None
    return ctrl


class TestDrawRegion:
    def test_init(self):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import DrawRegion

        r = DrawRegion(100, 50)
        assert r.w == 100
        assert r.h == 50

    def test_reset(self):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import DrawRegion

        r = DrawRegion(100, 50)
        r.from_canvas[0, 0] = 1
        r.reset()
        assert r.from_canvas[0, 0] == 0

    def test_set_from(self):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import DrawRegion

        r = DrawRegion(100, 50)
        r.set_from(10, 20)
        assert r.from_x == 10
        assert r.from_y == 20

    def test_set_to(self):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import DrawRegion

        r = DrawRegion(100, 50)
        r.set_to(30, 40, 0, 100)

    def test_change_to(self):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import DrawRegion

        r = DrawRegion(100, 50)
        r.set_from(0, 0)
        r.change_to(50, 50)

    def test_mask(self):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import DrawRegion

        r1 = DrawRegion(100, 50)
        r2 = DrawRegion(100, 50)
        r1.from_canvas = np.ones((50, 100), dtype=bool)
        r2.from_canvas = np.ones((50, 100), dtype=bool)
        r1.mask(r2)

    def test_copy(self):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import DrawRegion

        r1 = DrawRegion(100, 50)
        r2 = DrawRegion(100, 50)
        r1.copy(r2)

    def test_decrease_w_tail(self):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import DrawRegion

        r = DrawRegion(100, 50)
        r.decrease_w_tail(10)

    def test_decrease_w_head(self):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import DrawRegion

        r = DrawRegion(100, 50)
        r.decrease_w_head(10)


class TestPreviewCanvas:
    def test_creates(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            PreviewCanvas,
        )

        canvas = PreviewCanvas(None)
        qtbot.addWidget(canvas)
        assert isinstance(canvas, PreviewCanvas)

    def test_set_regions(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DrawColor,
            DrawRegion,
            PreviewCanvas,
        )

        canvas = PreviewCanvas(None)
        qtbot.addWidget(canvas)
        regions = [(DrawRegion(100, 50), DrawColor.TRAIN)]
        canvas.set_regions(regions)
        assert len(canvas.regions) == 1

    def test_adjacent_color_blocks_do_not_leave_background_gaps(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DrawColor,
            DrawRegion,
            PreviewCanvas,
        )

        canvas = PreviewCanvas(None)
        qtbot.addWidget(canvas)
        canvas.subject_num = 1
        canvas.session_num = 1
        canvas.resize(463, 280)

        regions = []
        for start, end, color in (
            (0.0, 0.333, DrawColor.TRAIN),
            (0.333, 0.667, DrawColor.VAL),
            (0.667, 1.0, DrawColor.TEST),
        ):
            region = DrawRegion(1, 1)
            region.set_from(0, 0)
            region.set_to(1, 1, start, end)
            regions.append((region, color))

        canvas.set_regions(regions)
        canvas.show()
        qtbot.wait(10)
        image = canvas.grab().toImage()
        expected_colors = {color.value.name() for color in DrawColor}
        row_colors = {
            image.pixelColor(x, 30).name() for x in range(51, canvas.width() - 51)
        }

        assert not image.isNull()
        assert row_colors <= expected_colors


class TestDataSplittingDialog:
    def test_creates(self, qtbot, controller):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, controller)
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Data Splitting Setting"

    @pytest.mark.parametrize("available_width", [752, 760])
    def test_narrow_geometry_reflows_and_keeps_confirm_visible(
        self,
        qtbot,
        controller,
        available_width,
    ):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, controller)
        qtbot.addWidget(dlg)
        dlg.resize(available_width, 700)
        dlg.show()
        qtbot.wait(10)

        preview = dlg.findChild(QFrame, "DataSplitPreviewGroup")
        settings = dlg.findChild(QFrame, "DataSplitOptionsGroup")
        assert preview is not None
        assert settings is not None
        assert dlg.btn_confirm is not None
        assert dlg.minimumSizeHint().width() <= available_width
        assert settings.geometry().top() >= preview.geometry().bottom()
        assert dlg.btn_confirm.isVisible()

        confirm_bottom_right = dlg.btn_confirm.mapTo(
            dlg,
            dlg.btn_confirm.rect().bottomRight(),
        )
        assert confirm_bottom_right.x() < dlg.width()
        assert confirm_bottom_right.y() < dlg.height()

        image = dlg.grab().toImage()
        confirm_center = dlg.btn_confirm.mapTo(dlg, dlg.btn_confirm.rect().center())
        assert not image.isNull()
        assert image.pixelColor(confirm_center).name() != "#1b1b1d"

    def test_real_study_requires_explicit_service_context(self, qtbot, controller):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        class RealStudyParent(QWidget):
            def __init__(self) -> None:
                super().__init__()
                self.study = Study()

        parent = RealStudyParent()
        qtbot.addWidget(parent)
        controller.get_epoch_data.side_effect = AssertionError("stale controller read")
        controller.get_dataset_generator.side_effect = AssertionError(
            "stale controller read"
        )

        dlg = DataSplittingDialog(parent, controller)
        qtbot.addWidget(dlg)

        assert dlg.epoch_data is None
        assert dlg.dataset_generator is None
        assert dlg.btn_confirm is not None
        assert not dlg.btn_confirm.isEnabled()
        assert dlg.blocked_label is not None
        assert "Create epochs" in dlg.blocked_label.text()
        controller.get_epoch_data.assert_not_called()
        controller.get_dataset_generator.assert_not_called()

    def test_confirm_without_epoch_data_does_not_open_preview(
        self,
        qtbot,
        controller,
    ):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, controller, epoch_data=None)
        qtbot.addWidget(dlg)

        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_dialog."
            "DataSplittingPreviewDialog"
        ) as MockPreview:
            dlg.confirm()

        MockPreview.assert_not_called()
        assert dlg.get_result() is None

    def test_preview_dialog_rejects_missing_epoch_data(self, qtbot):
        from XBrainLab.backend.dataset import DataSplittingConfig, TrainingType
        from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
            DataSplittingPreviewDialog,
        )

        config = DataSplittingConfig(
            train_type=TrainingType.FULL,
            is_cross_validation=False,
            val_splitter_list=[],
            test_splitter_list=[],
        )

        with pytest.raises(ValueError, match="Create epochs"):
            DataSplittingPreviewDialog(None, "Data Splitting Step 2", None, config)

    def test_preview_dialog_uses_frameless_summary_cards(self, qtbot, epoch_data):
        from XBrainLab.backend.dataset import (
            DataSplittingConfig,
            SplitByType,
            TrainingType,
            ValSplitByType,
        )
        from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
            DataSplitterHolder,
            DataSplittingPreviewDialog,
        )

        config = DataSplittingConfig(
            train_type=TrainingType.FULL,
            is_cross_validation=True,
            val_splitter_list=[DataSplitterHolder(True, ValSplitByType.TRIAL)],
            test_splitter_list=[DataSplitterHolder(True, SplitByType.TRIAL)],
        )

        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog."
                "DatasetGenerator"
            ),
            patch("threading.Thread") as mock_thread,
        ):
            mock_thread.return_value.is_alive.return_value = False
            dlg = DataSplittingPreviewDialog(
                None,
                "Data Splitting Step 2",
                epoch_data,
                config,
            )

        qtbot.addWidget(dlg)
        if dlg.timer is not None:
            dlg.timer.stop()
        if dlg.preview_debounce_timer is not None:
            dlg.preview_debounce_timer.stop()

        summary_panels = [
            frame
            for frame in dlg.findChildren(QFrame)
            if frame.objectName() == "SplitPreviewSummaryPanel"
        ]
        assert len(summary_panels) == 3
        assert all(
            panel.frameShape() == QFrame.Shape.NoFrame for panel in summary_panels
        )
        assert dlg.tree is not None
        assert dlg.tree.frameShape() == QFrame.Shape.NoFrame
        results_panel = dlg.findChild(QFrame, "SplitPreviewPanel")
        assert results_panel is not None
        assert results_panel.frameShape() == QFrame.Shape.NoFrame
        assert "QFrame#SplitPreviewSummaryPanel" in dlg.styleSheet()
        assert "QFrame#SplitPreviewPanel" in dlg.styleSheet()
        split_panel_style = dlg.styleSheet().split("QFrame#SplitPreviewPanel", 1)[1]
        split_panel_style = split_panel_style.split("}", 1)[0]
        assert "border: none;" in split_panel_style
        assert "border: none;" in dlg.styleSheet()

        dlg.tree.clear()
        rows = []
        for name in ("Fold_0", "Fold_1"):
            row = QTreeWidgetItem(dlg.tree)
            row.setText(0, name)
            rows.append(row)
        dlg._resize_tree_to_rows()
        dlg.show()
        qtbot.wait(10)

        last_row = dlg.tree.visualItemRect(rows[-1])
        unused_viewport_height = dlg.tree.viewport().height() - last_row.bottom()
        assert unused_viewport_height <= 12
        assert (
            dlg.tree.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert "gridline-color: transparent;" in dlg.tree.styleSheet()

    def test_data_splitting_cards_do_not_draw_internal_vertical_frame_lines(
        self,
        qtbot,
        controller,
    ):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, controller)
        qtbot.addWidget(dlg)

        for object_name in ("DataSplitPreviewGroup", "DataSplitOptionsGroup"):
            frame = dlg.findChild(QFrame, object_name)
            assert frame is not None
            assert frame.frameShape() == QFrame.Shape.NoFrame
        assert (
            "QFrame#DataSplitPreviewGroup,\n        QFrame#DataSplitOptionsGroup"
            in (dlg.styleSheet())
        )
        assert "border: none;" in dlg.styleSheet()

    def test_data_splitting_buttons_do_not_render_enter_glyphs(
        self,
        qtbot,
        controller,
        epoch_data,
    ):
        from XBrainLab.backend.dataset import (
            DataSplittingConfig,
            SplitByType,
            TrainingType,
            ValSplitByType,
        )
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )
        from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
            DataSplitterHolder,
            DataSplittingPreviewDialog,
        )

        dialog = DataSplittingDialog(None, controller)
        qtbot.addWidget(dialog)

        config = DataSplittingConfig(
            train_type=TrainingType.FULL,
            is_cross_validation=True,
            val_splitter_list=[DataSplitterHolder(True, ValSplitByType.TRIAL)],
            test_splitter_list=[DataSplitterHolder(True, SplitByType.TRIAL)],
        )
        with (
            patch(
                "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog."
                "DatasetGenerator"
            ),
            patch("threading.Thread") as mock_thread,
        ):
            mock_thread.return_value.is_alive.return_value = False
            preview = DataSplittingPreviewDialog(
                None,
                "Data Splitting Step 2",
                epoch_data,
                config,
            )
        qtbot.addWidget(preview)
        if preview.timer is not None:
            preview.timer.stop()
        if preview.preview_debounce_timer is not None:
            preview.preview_debounce_timer.stop()

        for button in (dialog.btn_confirm, preview.btn_confirm):
            assert button is not None
            assert button.text() == "Confirm"
            assert not button.autoDefault()
            assert not button.isDefault()
            assert button.icon().isNull()

    def test_default_split_config_uses_trainable_trial_splits(
        self,
        qtbot,
        controller,
    ):
        from XBrainLab.backend.dataset import SplitByType, ValSplitByType
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, controller)
        qtbot.addWidget(dlg)

        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_dialog."
            "DataSplittingPreviewDialog"
        ) as MockPreview:
            MockPreview.return_value.exec.return_value = False

            dlg.confirm()

        config = MockPreview.call_args.args[3]
        assert config.test_splitter_list[0].split_type == SplitByType.TRIAL
        assert config.val_splitter_list[0].split_type == ValSplitByType.TRIAL

    def test_update_preview(self, qtbot, controller):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, controller)
        qtbot.addWidget(dlg)
        dlg.update_preview()

    def test_handle_testing(self, qtbot, controller):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, controller)
        qtbot.addWidget(dlg)
        dlg.handle_testing()

    def test_handle_validation(self, qtbot, controller):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, controller)
        qtbot.addWidget(dlg)
        dlg.handle_validation()

    def test_get_result_default(self, qtbot, controller):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, controller)
        qtbot.addWidget(dlg)
        assert dlg.get_result() is None


class TestDataSplittingDialogSplitTypes:
    """Tests for each split type combo value in update_preview."""

    def _make_dialog(self, qtbot, controller) -> Any:
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, controller)
        qtbot.addWidget(dlg)
        return dlg

    def test_ind_training_type(self, qtbot, controller):
        from XBrainLab.backend.dataset import TrainingType

        dlg = self._make_dialog(qtbot, controller)
        dlg.train_type_combo.setCurrentText(TrainingType.IND.value)
        dlg.update_preview()

    def test_test_session_ind(self, qtbot, controller):
        from XBrainLab.backend.dataset import SplitByType

        dlg = self._make_dialog(qtbot, controller)
        dlg.test_combo.setCurrentText(SplitByType.SESSION_IND.value)
        dlg.update_preview()

    def test_test_trial(self, qtbot, controller):
        from XBrainLab.backend.dataset import SplitByType

        dlg = self._make_dialog(qtbot, controller)
        dlg.test_combo.setCurrentText(SplitByType.TRIAL.value)
        dlg.update_preview()

    def test_test_trial_ind(self, qtbot, controller):
        from XBrainLab.backend.dataset import SplitByType

        dlg = self._make_dialog(qtbot, controller)
        dlg.test_combo.setCurrentText(SplitByType.TRIAL_IND.value)
        dlg.update_preview()

    def test_test_subject(self, qtbot, controller):
        from XBrainLab.backend.dataset import SplitByType

        dlg = self._make_dialog(qtbot, controller)
        dlg.test_combo.setCurrentText(SplitByType.SUBJECT.value)
        dlg.update_preview()

    def test_test_subject_ind(self, qtbot, controller):
        from XBrainLab.backend.dataset import SplitByType

        dlg = self._make_dialog(qtbot, controller)
        dlg.test_combo.setCurrentText(SplitByType.SUBJECT_IND.value)
        dlg.update_preview()

    def test_val_session(self, qtbot, controller):
        from XBrainLab.backend.dataset import ValSplitByType

        dlg = self._make_dialog(qtbot, controller)
        dlg.val_combo.setCurrentText(ValSplitByType.SESSION.value)
        dlg.update_preview()

    def test_val_trial(self, qtbot, controller):
        from XBrainLab.backend.dataset import ValSplitByType

        dlg = self._make_dialog(qtbot, controller)
        dlg.val_combo.setCurrentText(ValSplitByType.TRIAL.value)
        dlg.update_preview()

    def test_val_subject(self, qtbot, controller):
        from XBrainLab.backend.dataset import ValSplitByType

        dlg = self._make_dialog(qtbot, controller)
        dlg.val_combo.setCurrentText(ValSplitByType.SUBJECT.value)
        dlg.update_preview()

    def test_confirm_opens_step2(self, qtbot, controller):
        from unittest.mock import patch

        dlg = self._make_dialog(qtbot, controller)
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_dialog.DataSplittingPreviewDialog"
        ) as MockPreview:
            MockPreview.return_value.exec.return_value = False
            dlg.confirm()
            MockPreview.assert_called_once()

    def test_confirm_accepts_on_step2_ok(self, qtbot, controller):
        from unittest.mock import MagicMock, patch

        dlg = self._make_dialog(qtbot, controller)
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_dialog.DataSplittingPreviewDialog"
        ) as MockPreview:
            MockPreview.return_value.exec.return_value = True
            MockPreview.return_value.get_result.return_value = MagicMock()
            dlg.confirm()
            assert dlg.split_result is not None


class TestPreviewCanvasPaintEvent:
    def test_paint_event(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DrawColor,
            DrawRegion,
            PreviewCanvas,
        )

        canvas = PreviewCanvas(None)
        qtbot.addWidget(canvas)

        r = DrawRegion(5, 5)
        r.set_from(0, 0)
        r.set_to(5, 5, 0, 1)
        canvas.set_regions([(r, DrawColor.TRAIN)])
        canvas.repaint()  # triggers paintEvent
