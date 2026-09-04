"""Layout regressions for the second data-splitting step."""

from __future__ import annotations

import threading

import pytest
from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QBoxLayout, QLabel

from tests.unit.ui.data_split_test_support import dialog_context_kwargs
from XBrainLab.backend.application.dataset_split_preview import (
    DATASET_SPLIT_PREVIEW_ROW_LIMIT,
    DatasetSplitPreviewPublication,
    DatasetSplitPreviewRequest,
    DatasetSplitPreviewRow,
)
from XBrainLab.backend.dataset import (
    DataSplittingConfig,
    SplitByType,
    TrainingType,
    ValSplitByType,
)
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
    PREVIEW_STATUS_SUCCEEDED,
    DataSplitterHolder,
    DataSplittingPreviewDialog,
)


class _VisibleResizeRecorder(QObject):
    def __init__(self, target) -> None:
        super().__init__(target)
        self.target = target
        self.armed = False
        self.sizes: list[tuple[int, int]] = []

    def eventFilter(self, watched, event) -> bool:
        if (
            self.armed
            and watched is self.target
            and event.type() is QEvent.Type.Resize
            and self.target.isVisible()
        ):
            size = event.size()
            self.sizes.append((size.width(), size.height()))
        return super().eventFilter(watched, event)


def _preview_rows(count: int) -> tuple[DatasetSplitPreviewRow, ...]:
    return tuple(
        DatasetSplitPreviewRow(
            name=f"Fold_{index}",
            train_count=80,
            validation_count=10,
            test_count=10,
        )
        for index in range(count)
    )


def _preview_config() -> DataSplittingConfig:
    return DataSplittingConfig(
        train_type=TrainingType.FULL,
        is_cross_validation=True,
        val_splitter_list=[DataSplitterHolder(True, ValSplitByType.TRIAL)],
        test_splitter_list=[DataSplitterHolder(True, SplitByType.TRIAL)],
    )


def _async_preview_provider(
    rows: tuple[DatasetSplitPreviewRow, ...],
    release: threading.Event,
):
    def provide(
        request: DatasetSplitPreviewRequest,
    ) -> DatasetSplitPreviewPublication:
        if not release.wait(timeout=2):
            raise TimeoutError("Test did not release the split preview provider")
        visible_rows = rows[:DATASET_SPLIT_PREVIEW_ROW_LIMIT]
        return DatasetSplitPreviewPublication(
            request=request,
            generation=request.publication_generation,
            rows=visible_rows,
            total_count=len(rows),
            truncated_count=max(0, len(rows) - len(visible_rows)),
            train_count=sum(row.train_count for row in rows),
            validation_count=sum(row.validation_count for row in rows),
            test_count=sum(row.test_count for row in rows),
        )

    return provide


def _make_dialog(qtbot, *, row_count: int):
    release = threading.Event()
    dialog = DataSplittingPreviewDialog(
        None,
        "Data Splitting Step 2",
        config=_preview_config(),
        **dialog_context_kwargs(
            preview_provider=_async_preview_provider(
                _preview_rows(row_count),
                release,
            )
        ),
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(10)
    center_before = dialog.geometry().center()
    release.set()
    qtbot.waitUntil(
        lambda: dialog._preview_state()[0] == PREVIEW_STATUS_SUCCEEDED,
        timeout=3000,
    )
    dialog.update_table()
    qtbot.waitUntil(
        lambda: dialog.tree is not None
        and dialog.tree.topLevelItemCount()
        == min(row_count, DATASET_SPLIT_PREVIEW_ROW_LIMIT),
        timeout=1000,
    )
    qtbot.wait(10)
    return dialog, center_before


def test_five_fold_success_refits_content_and_uses_primary_confirm(qtbot):
    dialog, center_before = _make_dialog(qtbot, row_count=5)

    assert dialog.tree is not None
    assert dialog.content_scroll is not None
    assert dialog.btn_confirm is not None
    assert dialog.content_scroll.verticalScrollBar().maximum() == 0
    assert dialog.btn_confirm.objectName() == "PrimaryConfirmButton"
    assert dialog.btn_confirm.isEnabled()
    assert dialog.btn_confirm.isVisible()
    assert dialog.tree.verticalScrollBar().maximum() == 0
    assert dialog.screen() is not None
    available = dialog.screen().availableGeometry().adjusted(24, 24, -24, -24)
    assert (dialog.geometry().center() - available.center()).manhattanLength() <= 2
    assert (dialog.geometry().center() - center_before).manhattanLength() <= 4

    confirm_bottom_right = dialog.btn_confirm.mapTo(
        dialog,
        dialog.btn_confirm.rect().bottomRight(),
    )
    assert confirm_bottom_right.x() < dialog.width()
    assert confirm_bottom_right.y() < dialog.height()


@pytest.mark.parametrize("width", (752, 760))
def test_summary_rows_keep_the_count_table_horizontal_at_compact_widths(qtbot, width):
    dialog, _center_before = _make_dialog(qtbot, row_count=5)

    dialog.resize(width, dialog.height())
    qtbot.wait(10)

    assert dialog.content_layout is not None
    assert dialog.tree is not None
    assert dialog.content_layout.direction() == QBoxLayout.Direction.LeftToRight
    assert dialog.tree.horizontalScrollBar().maximum() == 0


def test_narrow_success_keeps_vertical_flow_and_footer_visible(qtbot):
    dialog, _center_before = _make_dialog(qtbot, row_count=5)
    dialog.resize(719, dialog.height())
    qtbot.wait(10)

    assert dialog.content_layout is not None
    assert dialog.btn_confirm is not None
    assert dialog.content_layout.direction() == QBoxLayout.Direction.TopToBottom
    assert dialog.screen() is not None
    assert dialog.height() <= dialog.screen().availableGeometry().height() - 48

    confirm_bottom_right = dialog.btn_confirm.mapTo(
        dialog,
        dialog.btn_confirm.rect().bottomRight(),
    )
    assert confirm_bottom_right.x() < dialog.width()
    assert confirm_bottom_right.y() < dialog.height()


def test_more_than_eight_rows_keeps_dialog_bounded_and_scrolls_tree(qtbot):
    dialog, _center_before = _make_dialog(qtbot, row_count=12)

    assert dialog.tree is not None
    assert dialog.btn_confirm is not None
    assert dialog.tree.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert dialog.tree.verticalScrollBar().maximum() > 0
    assert dialog.screen() is not None
    assert dialog.height() <= dialog.screen().availableGeometry().height() - 48

    confirm_bottom_right = dialog.btn_confirm.mapTo(
        dialog,
        dialog.btn_confirm.rect().bottomRight(),
    )
    assert confirm_bottom_right.x() < dialog.width()
    assert confirm_bottom_right.y() < dialog.height()


def test_more_than_fifty_rows_is_truthfully_capped_with_a_total_label(qtbot):
    dialog, _center_before = _make_dialog(qtbot, row_count=51)

    assert dialog.tree is not None
    assert dialog.tree.topLevelItemCount() == 50
    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert "Showing first 50 of 51" in labels


def test_each_preview_row_exposes_split_evidence_without_changing_count_columns(qtbot):
    release = threading.Event()
    row = DatasetSplitPreviewRow(
        name="Fold_0",
        train_count=80,
        validation_count=10,
        test_count=10,
        test_scope_group_count=5,
        test_selected_group_count=1,
        test_requested_unit="Ratio",
        test_requested_value="0.2",
        validation_scope_group_count=4,
        validation_selected_group_count=1,
        validation_requested_unit="Number",
        validation_requested_value="1",
        test_missing_class_names=("12 Hz",),
        validation_missing_class_names=(),
        saliency_source="validation",
    )
    dialog = DataSplittingPreviewDialog(
        None,
        "Data Splitting Step 2",
        config=_preview_config(),
        **dialog_context_kwargs(
            preview_provider=_async_preview_provider((row,), release)
        ),
    )
    qtbot.addWidget(dialog)
    dialog.show()
    release.set()
    qtbot.waitUntil(
        lambda: dialog._preview_state()[0] == PREVIEW_STATUS_SUCCEEDED,
        timeout=3000,
    )
    dialog.update_table()

    assert dialog.tree is not None
    item = dialog.tree.topLevelItem(0)
    assert [item.text(column) for column in range(4)] == ["Fold 1", "80", "10", "10"]
    titles = dialog.findChildren(QLabel, "SplitPreviewSectionTitle")
    assert any(
        "Hover a split row for allocation and class details." in label.text()
        and label.isVisible()
        for label in titles
    )
    evidence = item.toolTip(0)
    assert "Test: Ratio 0.2 · groups 5 → 1 · missing class: 12 Hz" in evidence
    assert "Validation: Number 1 · groups 4 → 1 · all classes covered" in evidence
    assert "Saliency: validation" in evidence
    assert item.data(0, Qt.ItemDataRole.AccessibleTextRole) == evidence
    assert item.data(0, Qt.ItemDataRole.AccessibleDescriptionRole) == evidence


def test_disabled_validation_evidence_does_not_claim_missing_classes(qtbot):
    release = threading.Event()
    row = DatasetSplitPreviewRow(
        name="Fold_0",
        train_count=80,
        validation_count=0,
        test_count=20,
        test_scope_group_count=5,
        test_selected_group_count=1,
        test_requested_unit="Number",
        test_requested_value="1",
        test_missing_class_names=(),
        saliency_source="test",
    )
    dialog = DataSplittingPreviewDialog(
        None,
        "Data Splitting Step 2",
        config=_preview_config(),
        **dialog_context_kwargs(
            preview_provider=_async_preview_provider((row,), release)
        ),
    )
    qtbot.addWidget(dialog)
    dialog.show()
    release.set()
    qtbot.waitUntil(
        lambda: dialog._preview_state()[0] == PREVIEW_STATUS_SUCCEEDED,
        timeout=3000,
    )
    dialog.update_table()

    assert dialog.tree is not None
    evidence = dialog.tree.topLevelItem(0).toolTip(0)
    assert "Validation: Disabled" in evidence
    assert "Validation: Disabled ·" not in evidence


def test_success_rows_schedule_one_refit_not_one_per_poll(qtbot, monkeypatch):
    release = threading.Event()
    dialog = DataSplittingPreviewDialog(
        None,
        "Data Splitting Step 2",
        config=_preview_config(),
        **dialog_context_kwargs(
            preview_provider=_async_preview_provider(_preview_rows(5), release)
        ),
    )
    qtbot.addWidget(dialog)
    dialog.show()

    refit_calls = 0
    original_refit = dialog._refit_to_current_content

    def counted_refit() -> None:
        nonlocal refit_calls
        refit_calls += 1
        original_refit()

    monkeypatch.setattr(dialog, "_refit_to_current_content", counted_refit)
    release.set()
    qtbot.waitUntil(
        lambda: dialog._preview_state()[0] == PREVIEW_STATUS_SUCCEEDED,
        timeout=3000,
    )

    dialog.update_table()
    dialog.update_table()
    qtbot.waitUntil(lambda: refit_calls == 1, timeout=1000)
    dialog.update_table()
    qtbot.wait(10)

    assert refit_calls == 1


def test_success_rows_do_not_resize_the_visible_wide_dialog(qtbot, monkeypatch):
    monkeypatch.setattr(BaseDialog, "_fit_to_available_screen", lambda self: None)
    monkeypatch.setattr(
        BaseDialog,
        "resize_preserving_center",
        lambda self, size: self.resize(size),
    )
    release = threading.Event()
    dialog = DataSplittingPreviewDialog(
        None,
        "Data Splitting Step 2",
        config=_preview_config(),
        **dialog_context_kwargs(
            preview_provider=_async_preview_provider(_preview_rows(5), release)
        ),
    )
    qtbot.addWidget(dialog)
    recorder = _VisibleResizeRecorder(dialog)
    dialog.installEventFilter(recorder)
    dialog.show()
    qtbot.waitUntil(lambda: dialog.isVisible())
    initial_size = (dialog.width(), dialog.height())
    initial_center = dialog.geometry().center()
    recorder.armed = True

    release.set()
    qtbot.waitUntil(
        lambda: dialog._preview_state()[0] == PREVIEW_STATUS_SUCCEEDED,
        timeout=3000,
    )
    dialog.update_table()
    qtbot.waitUntil(
        lambda: dialog.tree is not None
        and dialog.tree.topLevelItemCount() == 5
        and not dialog._content_refit_pending,
        timeout=1000,
    )

    assert (dialog.width(), dialog.height()) == initial_size
    assert dialog.geometry().center() == initial_center
    assert all(size == initial_size for size in recorder.sizes)


def test_wide_resize_refits_all_header_sections_into_viewport(qtbot):
    dialog, _center_before = _make_dialog(qtbot, row_count=5)

    dialog.resize(980, 520)
    qtbot.wait(10)

    assert dialog.tree is not None
    header = dialog.tree.header()
    viewport = dialog.tree.viewport()
    assert header is not None
    assert viewport is not None
    test_column = 3
    test_section_right = header.sectionViewportPosition(
        test_column
    ) + header.sectionSize(test_column)
    minimum_test_width = dialog.tree.fontMetrics().horizontalAdvance("Test") + 24

    assert header.length() <= viewport.width() + 2
    assert test_section_right <= viewport.width() + 2
    assert header.sectionSize(test_column) >= minimum_test_width
    assert dialog.tree.horizontalScrollBar().maximum() == 0
