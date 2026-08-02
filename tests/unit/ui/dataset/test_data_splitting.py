"""Dataset-splitting UI tests at the detached publication boundary."""

from __future__ import annotations

from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QDialog

from tests.unit.ui.data_split_test_support import (
    dialog_context_kwargs,
    successful_preview,
)
from XBrainLab.backend.application.dataset_split_preview import (
    DatasetSplitPreviewRow,
)
from XBrainLab.backend.dataset import (
    DataSplittingConfig,
    SplitByType,
    SplitUnit,
    TrainingType,
)
from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
    DataSplitterHolder,
    DataSplittingPreviewDialog,
)


def _split_config() -> DataSplittingConfig:
    return DataSplittingConfig(
        train_type=TrainingType.FULL,
        is_cross_validation=False,
        val_splitter_list=[],
        test_splitter_list=[],
    )


def _window(qtbot) -> DataSplittingPreviewDialog:
    window = DataSplittingPreviewDialog(
        None,
        "Test Window",
        config=_split_config(),
        **dialog_context_kwargs(preview_provider=successful_preview),
    )
    qtbot.addWidget(window)
    if window.preview_worker is not None:
        window.preview_worker.join(timeout=1)
    window.update_table()
    return window


def test_data_splitter_holder_validation() -> None:
    holder = DataSplitterHolder(True, SplitByType.TRIAL)
    holder.set_entry_var("")
    holder.set_split_unit_var(None)
    assert not holder.is_valid()

    holder.set_split_unit_var(SplitUnit.RATIO.value)
    holder.set_entry_var("0.8")
    assert holder.is_valid()
    assert holder.get_value() == 0.8

    holder.set_entry_var("1.2")
    assert not holder.is_valid()
    holder.set_entry_var("abc")
    assert not holder.is_valid()

    holder.set_split_unit_var(SplitUnit.NUMBER.value)
    holder.set_entry_var("10")
    assert holder.is_valid()
    assert holder.get_value() == 10.0
    holder.set_entry_var("10.5")
    assert not holder.is_valid()
    holder.set_entry_var("-5")
    assert not holder.is_valid()


def test_data_splitting_window_init_uses_detached_context(qtbot) -> None:
    window = _window(qtbot)

    assert window.windowTitle() == "Test Window"
    assert window.tree.columnCount() == 4
    assert [window.tree.headerItem().text(i) for i in range(4)] == [
        "Split",
        "Train",
        "Validation",
        "Test",
    ]
    assert window.tree.selectionMode() == QAbstractItemView.SelectionMode.NoSelection
    assert window.tree.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert "chevron-down.svg" in window.styleSheet()
    assert not hasattr(window, "epoch_data")
    assert not hasattr(window, "dataset_generator")
    assert not hasattr(window, "datasets")


def test_data_splitting_window_preview_renders_typed_rows(qtbot) -> None:
    window = _window(qtbot)

    assert window._preview_status == "succeeded"
    assert window.tree.topLevelItemCount() == 1
    item = window.tree.topLevelItem(0)
    assert [item.text(column) for column in range(4)] == [
        "Fold_0",
        "80",
        "10",
        "10",
    ]
    assert window.tree.selectedItems() == []
    assert window.tree.currentIndex().isValid() is False
    assert window.tree.height() <= 180


def test_data_splitting_window_update_table_replaces_calculating_row(qtbot) -> None:
    window = _window(qtbot)
    window.tree.clear()
    window._set_preview_state(
        window._preview_generation_id,
        "succeeded",
        rows=(
            DatasetSplitPreviewRow(
                name="Dataset1",
                train_count=100,
                validation_count=20,
                test_count=20,
            ),
        ),
    )

    window.update_table()

    assert window.tree.topLevelItemCount() == 1
    item = window.tree.topLevelItem(0)
    assert [item.text(column) for column in range(4)] == [
        "Dataset1",
        "100",
        "20",
        "20",
    ]


def test_data_splitting_window_confirm_accepts_only_successful_preview(qtbot) -> None:
    window = _window(qtbot)
    window.preview_worker = None

    with patch.object(QDialog, "accept") as accept:
        window.confirm()

    accept.assert_called_once()
