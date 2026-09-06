"""Coverage tests for DataSplittingDialog - 218 uncovered lines."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import numpy as np
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QTreeWidgetItem, QWidget

from tests.unit.ui.data_split_test_support import (
    dialog_context_kwargs,
    split_context,
)
from XBrainLab.backend.study import Study


class FakeEpochData:
    def __init__(self) -> None:
        self.subject_map = {"S01": [0, 1, 2], "S02": [3, 4, 5]}
        self.session_map = {"sess1": [0, 1, 2, 3, 4, 5]}
        self.label_map = {"left": 0, "right": 1}
        self.data = list(range(100))

    def get_data_length(self) -> int:
        return 100

    def get_subject_map(self) -> dict[str, list[int]]:
        return self.subject_map

    def get_session_map(self) -> dict[str, list[int]]:
        return self.session_map


class FakeDataSplittingController:
    def __init__(self, epoch_data: FakeEpochData) -> None:
        self.epoch_data = epoch_data
        self.dataset_generator = None
        self.epoch_reads = 0
        self.generator_reads = 0
        self.fail_on_read = False

    def get_epoch_data(self) -> FakeEpochData:
        self.epoch_reads += 1
        if self.fail_on_read:
            raise AssertionError("stale controller read")
        return self.epoch_data

    def get_dataset_generator(self) -> object | None:
        self.generator_reads += 1
        if self.fail_on_read:
            raise AssertionError("stale controller read")
        return self.dataset_generator


@pytest.fixture
def epoch_data() -> FakeEpochData:
    """Return contract-valid epoch data for DataSplittingDialog."""
    return FakeEpochData()


@pytest.fixture
def controller(epoch_data: FakeEpochData) -> FakeDataSplittingController:
    return FakeDataSplittingController(epoch_data)


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

    def test_set_to_accepts_partial_ratio(self):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import DrawRegion

        region = DrawRegion(5, 5)
        region.set_from(0, 0)
        region.set_to(3, 3, 0.2, 0.8)

        assert region.to_canvas.sum() > 0

    def test_set_to_ref_uses_existing_region(self):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import DrawRegion

        reference = DrawRegion(5, 5)
        reference.set_from(0, 0)
        reference.set_to(5, 5, 0, 1)
        region = DrawRegion(5, 5)
        region.set_from(0, 0)

        region.set_to_ref(3, 3, reference)

        assert region.to_canvas.sum() > 0

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

    def test_large_grid_thins_lines_without_changing_exact_dimensions(self, qtbot):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import PreviewCanvas

        canvas = PreviewCanvas(None)
        qtbot.addWidget(canvas)
        canvas.subject_num = 40
        canvas.session_num = 30
        canvas.show()
        qtbot.wait(10)

        assert len(canvas._grid_line_indices(canvas.subject_num)) <= 12
        assert len(canvas._grid_line_indices(canvas.session_num)) <= 12
        assert canvas.subject_num == 40
        assert canvas.session_num == 30
        assert not canvas.grab().toImage().isNull()


class TestDataSplittingDialog:
    def test_creates(self, qtbot, controller):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, **dialog_context_kwargs())
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Data Splitting Setting"

    @pytest.mark.parametrize(
        ("subject_count", "session_count"),
        [(1, 1), (3, 2), (5, 3), (15, 4)],
    )
    def test_step_one_uses_the_published_grid_dimensions_and_title(
        self,
        qtbot,
        controller,
        subject_count,
        session_count,
    ):
        """The illustration must not invent a fixed five-by-five cohort."""
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dialog = DataSplittingDialog(
            None,
            **dialog_context_kwargs(
                context=split_context(
                    subject_count=subject_count,
                    session_count=session_count,
                )
            ),
        )
        qtbot.addWidget(dialog)

        assert dialog.subject_num == subject_count
        assert dialog.session_num == session_count
        assert dialog.train_region.from_canvas.shape == (session_count, subject_count)
        assert dialog.canvas is not None
        assert dialog.canvas.subject_num == subject_count
        assert dialog.canvas.session_num == session_count
        dialog.show()
        qtbot.wait(10)
        assert not dialog.canvas.grab().toImage().isNull()
        title = dialog.findChild(QLabel, "DataSplitSectionTitle")
        assert title is not None
        assert title.text() == "Split strategy illustration"

    def test_step_one_projects_only_supported_strategies_for_individual_training(
        self,
        qtbot,
        controller,
    ):
        """A user cannot select retired Independent/Subject test modes."""
        from XBrainLab.backend.dataset import TrainingType
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dialog = DataSplittingDialog(None, **dialog_context_kwargs())
        qtbot.addWidget(dialog)
        dialog.train_type_combo.setCurrentText(TrainingType.IND.value)

        assert {
            dialog.test_combo.itemText(index)
            for index in range(dialog.test_combo.count())
        } == {"By Trial", "By Session"}
        assert {
            dialog.val_combo.itemText(index)
            for index in range(dialog.val_combo.count())
        } == {"Disable", "By Trial", "By Session"}

    def test_step_one_projects_backend_strategies_after_training_mode_toggle(
        self,
        qtbot,
        controller,
    ):
        from XBrainLab.backend.dataset import TrainingType
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        context = split_context()
        dialog = DataSplittingDialog(
            None,
            **dialog_context_kwargs(context=context),
        )
        qtbot.addWidget(dialog)

        assert [
            dialog.test_combo.itemText(index)
            for index in range(dialog.test_combo.count())
        ] == list(context.full_test_strategies)
        assert [
            dialog.val_combo.itemText(index)
            for index in range(dialog.val_combo.count())
        ] == list(context.full_validation_strategies)

        dialog.train_type_combo.setCurrentText(TrainingType.IND.value)

        assert [
            dialog.test_combo.itemText(index)
            for index in range(dialog.test_combo.count())
        ] == list(context.individual_test_strategies)
        assert [
            dialog.val_combo.itemText(index)
            for index in range(dialog.val_combo.count())
        ] == list(context.individual_validation_strategies)
        assert dialog.test_combo.currentText() in context.individual_test_strategies
        assert (
            dialog.val_combo.currentText() in context.individual_validation_strategies
        )

    def test_reopen_restores_saved_step_one_strategies_into_step_two_payload(
        self,
        qtbot,
        controller,
    ):
        from XBrainLab.backend.application.dataset_split_preview import (
            DatasetSplitSpecification,
        )
        from XBrainLab.backend.dataset import SplitByType, ValSplitByType
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        specification = DatasetSplitSpecification.from_payload(
            {
                "train_type": "Full Data",
                "is_cross_validation": False,
                "val_splitters": [
                    {
                        "split_type": "By Subject",
                        "split_unit": "Ratio",
                        "value": "0.2",
                        "is_option": True,
                    }
                ],
                "test_splitters": [
                    {
                        "split_type": "By Session",
                        "split_unit": "Ratio",
                        "value": "0.3",
                        "is_option": True,
                    }
                ],
            }
        )
        dialog = DataSplittingDialog(
            None,
            initial_specification=specification,
            **dialog_context_kwargs(),
        )
        qtbot.addWidget(dialog)

        assert dialog.test_combo.currentText() == "By Session"
        assert dialog.val_combo.currentText() == "By Subject"
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_dialog."
            "DataSplittingPreviewDialog"
        ) as preview_dialog:
            preview_dialog.return_value.exec.return_value = False
            dialog.confirm()

        config = preview_dialog.call_args.kwargs["config"]
        assert config.test_splitter_list[0].split_type == SplitByType.SESSION
        assert config.val_splitter_list[0].split_type == ValSplitByType.SUBJECT

    def test_reopen_keeps_saved_split_over_conflicting_assistant_hints(
        self,
        qtbot,
        controller,
    ):
        """Application-owned state wins when a dialog is reopened from a draft."""
        from XBrainLab.backend.application.dataset_split_preview import (
            DatasetSplitSpecification,
        )
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        specification = DatasetSplitSpecification.from_payload(
            {
                "train_type": "Full Data",
                "is_cross_validation": False,
                "val_splitters": [
                    {
                        "split_type": "By Subject",
                        "split_unit": "Ratio",
                        "value": "0.2",
                        "is_option": True,
                    }
                ],
                "test_splitters": [
                    {
                        "split_type": "By Session",
                        "split_unit": "Ratio",
                        "value": "0.3",
                        "is_option": True,
                    }
                ],
            }
        )
        dialog = DataSplittingDialog(
            None,
            initial_specification=specification,
            initial_values={
                "training_mode": "individual",
                "split_strategy": "subject",
                "test_ratio": "0.9",
            },
            **dialog_context_kwargs(),
        )
        qtbot.addWidget(dialog)

        assert dialog.train_type_combo.currentText() == "Full Data"
        assert dialog.test_combo.currentText() == "By Session"
        assert dialog.val_combo.currentText() == "By Subject"

        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_dialog."
            "DataSplittingPreviewDialog"
        ) as preview_dialog:
            preview_dialog.return_value.exec.return_value = False
            dialog.confirm()

        step_two = preview_dialog.call_args.kwargs["initial_specification"]
        assert step_two is specification
        assert step_two.test_splitters[0].value == "0.3"
        assert step_two.val_splitters[0].value == "0.2"

    def test_back_preserves_the_unconfirmed_step_two_draft(self, qtbot, controller):
        from XBrainLab.backend.application.dataset_split_preview import (
            DatasetSplitSpecification,
        )
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        original = DatasetSplitSpecification.from_payload(
            {
                "train_type": "Full Data",
                "is_cross_validation": False,
                "val_splitters": [
                    {"split_type": "By Trial", "split_unit": "Ratio", "value": "0.2"}
                ],
                "test_splitters": [
                    {"split_type": "By Trial", "split_unit": "Ratio", "value": "0.2"}
                ],
            }
        )
        revised = DatasetSplitSpecification.from_payload(
            {
                **original.to_payload(),
                "test_splitters": [
                    {"split_type": "By Trial", "split_unit": "Ratio", "value": "0.3"}
                ],
            }
        )
        dialog = DataSplittingDialog(
            None,
            initial_specification=original,
            **dialog_context_kwargs(),
        )
        qtbot.addWidget(dialog)

        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_dialog.DataSplittingPreviewDialog"
        ) as preview_dialog:
            preview_dialog.return_value.exec.return_value = False
            preview_dialog.return_value.get_current_specification.return_value = revised
            dialog.confirm()

        assert dialog.initial_specification is revised

    def test_assistant_handoff_prefills_explicit_split_choices(
        self,
        qtbot,
        controller,
    ):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dialog = DataSplittingDialog(
            None,
            **dialog_context_kwargs(),
            initial_values={
                "training_mode": "individual",
                "split_strategy": "subject",
                "test_ratio": "0.3",
            },
        )
        qtbot.addWidget(dialog)

        assert dialog.train_type_combo.currentText() == "Individual"
        assert dialog.test_combo.currentText() == "By Trial"
        assert dialog.val_combo.currentText() == "Disable"
        assert dialog.initial_values["test_ratio"] == "0.3"

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

        dlg = DataSplittingDialog(None, **dialog_context_kwargs())
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
        assert abs(settings.geometry().left() - preview.geometry().left()) <= 2
        assert settings.geometry().width() >= preview.geometry().width() - 4
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
        controller.fail_on_read = True

        dlg = DataSplittingDialog(parent)
        qtbot.addWidget(dlg)

        assert dlg.split_context is None
        assert not hasattr(dlg, "epoch_data")
        assert not hasattr(dlg, "dataset_generator")
        assert dlg.btn_confirm is not None
        assert not dlg.btn_confirm.isEnabled()
        assert dlg.blocked_label is not None
        assert "context is unavailable" in dlg.blocked_label.text()
        assert controller.epoch_reads == 0
        assert controller.generator_reads == 0

    def test_confirm_without_epoch_data_does_not_open_preview(
        self,
        qtbot,
        controller,
    ):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(
            None,
            **dialog_context_kwargs(context=split_context(epoch_available=False)),
        )
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

        kwargs = dialog_context_kwargs(
            context=split_context(epoch_available=False),
        )
        with pytest.raises(ValueError, match="Create EEG epochs"):
            DataSplittingPreviewDialog(
                None,
                "Data Splitting Step 2",
                config=config,
                **kwargs,
            )

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

        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.is_alive.return_value = False
            dlg = DataSplittingPreviewDialog(
                None,
                "Data Splitting Step 2",
                config=config,
                **dialog_context_kwargs(),
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
        assert "QFrame#SplitPreviewSummaryPanel QLabel" in dlg.styleSheet()
        summary_label_style = dlg.styleSheet().split(
            "QFrame#SplitPreviewSummaryPanel QLabel",
            1,
        )[1]
        summary_label_style = summary_label_style.split("}", 1)[0]
        assert "background: transparent;" in summary_label_style
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
        viewport = dlg.tree.viewport()
        assert viewport is not None
        unused_viewport_height = viewport.height() - last_row.bottom()
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

        dlg = DataSplittingDialog(None, **dialog_context_kwargs())
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

        dialog = DataSplittingDialog(None, **dialog_context_kwargs())
        qtbot.addWidget(dialog)

        config = DataSplittingConfig(
            train_type=TrainingType.FULL,
            is_cross_validation=True,
            val_splitter_list=[DataSplitterHolder(True, ValSplitByType.TRIAL)],
            test_splitter_list=[DataSplitterHolder(True, SplitByType.TRIAL)],
        )
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.is_alive.return_value = False
            preview = DataSplittingPreviewDialog(
                None,
                "Data Splitting Step 2",
                config=config,
                **dialog_context_kwargs(),
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

    def test_default_split_config_uses_trainable_trial_test_and_disabled_validation(
        self,
        qtbot,
        controller,
    ):
        from XBrainLab.backend.dataset import SplitByType
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, **dialog_context_kwargs())
        qtbot.addWidget(dlg)

        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_dialog."
            "DataSplittingPreviewDialog"
        ) as MockPreview:
            MockPreview.return_value.exec.return_value = False

            dlg.confirm()

        config = MockPreview.call_args.kwargs["config"]
        assert config.test_splitter_list[0].split_type == SplitByType.TRIAL
        assert config.val_splitter_list == []

    def test_validation_disable_passes_an_empty_validation_rule_to_step_two(
        self,
        qtbot,
        controller,
    ):
        """Disable is canonical absence, not a truthy disabled splitter."""
        from XBrainLab.backend.dataset import ValSplitByType
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dialog = DataSplittingDialog(None, **dialog_context_kwargs())
        qtbot.addWidget(dialog)
        dialog.val_combo.setCurrentText(ValSplitByType.DISABLE.value)

        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_dialog."
            "DataSplittingPreviewDialog"
        ) as preview_dialog:
            preview_dialog.return_value.exec.return_value = False
            dialog.confirm()

        config = preview_dialog.call_args.kwargs["config"]
        assert config.val_splitter_list == []

    def test_update_preview(self, qtbot, controller):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, **dialog_context_kwargs())
        qtbot.addWidget(dlg)
        dlg.update_preview()

    def test_handle_testing(self, qtbot, controller):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, **dialog_context_kwargs())
        qtbot.addWidget(dlg)
        dlg.handle_testing()

    def test_handle_validation(self, qtbot, controller):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, **dialog_context_kwargs())
        qtbot.addWidget(dlg)
        dlg.handle_validation()

    def test_get_result_default(self, qtbot, controller):
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, **dialog_context_kwargs())
        qtbot.addWidget(dlg)
        assert dlg.get_result() is None


class TestDataSplittingDialogSplitTypes:
    """Tests for each split type combo value in update_preview."""

    def _make_dialog(self, qtbot, controller) -> Any:
        from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import (
            DataSplittingDialog,
        )

        dlg = DataSplittingDialog(None, **dialog_context_kwargs())
        qtbot.addWidget(dlg)
        return dlg

    def test_ind_training_type(self, qtbot, controller):
        from XBrainLab.backend.dataset import TrainingType

        dlg = self._make_dialog(qtbot, controller)
        dlg.train_type_combo.setCurrentText(TrainingType.IND.value)
        dlg.update_preview()

    def test_test_trial(self, qtbot, controller):
        from XBrainLab.backend.dataset import SplitByType

        dlg = self._make_dialog(qtbot, controller)
        dlg.test_combo.setCurrentText(SplitByType.TRIAL.value)
        dlg.update_preview()

    def test_test_subject(self, qtbot, controller):
        from XBrainLab.backend.dataset import SplitByType

        dlg = self._make_dialog(qtbot, controller)
        dlg.test_combo.setCurrentText(SplitByType.SUBJECT.value)
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
        dlg = self._make_dialog(qtbot, controller)
        with patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_dialog.DataSplittingPreviewDialog"
        ) as MockPreview:
            MockPreview.return_value.exec.return_value = True
            MockPreview.return_value.get_result.return_value = object()
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
