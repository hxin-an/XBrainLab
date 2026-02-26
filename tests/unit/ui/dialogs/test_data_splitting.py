"""Coverage tests for DataSplittingDialog - 218 uncovered lines."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest


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


class TestDataSplittingDialog:
    def test_creates(self, qtbot, controller):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, controller)
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Data Splitting Setting"

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

    def _make_dialog(self, qtbot, controller):
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
