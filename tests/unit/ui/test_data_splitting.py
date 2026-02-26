"""Deep coverage tests for DataSplittingDialog, DrawRegion, PreviewCanvas, and more."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

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
        assert c is not None

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


class TestDataSplittingDialog:
    @pytest.fixture
    def dlg(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        ctrl = MagicMock()
        epoch = MagicMock()
        epoch.get_data_length.return_value = 100
        epoch.subject_map = {"S01": list(range(50)), "S02": list(range(50, 100))}
        epoch.session_map = {"sess1": list(range(100))}
        ctrl.get_epoch_data.return_value = epoch
        ctrl.get_dataset_generator.return_value = MagicMock()

        d = DataSplittingDialog(None, ctrl)
        qtbot.addWidget(d)
        return d

    def test_creates(self, dlg):
        assert dlg is not None

    def test_has_canvas(self, dlg):
        assert dlg.canvas is not None

    def test_has_combos(self, dlg):
        assert dlg.train_type_combo is not None
        assert dlg.test_combo is not None
        assert dlg.val_combo is not None

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

    def test_confirm_accepted(self, dlg):
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_dialog.DataSplittingPreviewDialog"
        ) as MockDlg:
            MockDlg.return_value.exec.return_value = True
            MockDlg.return_value.get_result.return_value = MagicMock()
            dlg.confirm()

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
        assert dlg is not None

    def test_get_result(self, dlg):
        result = dlg.get_result()
        # Before preview runs, result should be the generator (or None)
        assert result is None or hasattr(result, "__iter__")
