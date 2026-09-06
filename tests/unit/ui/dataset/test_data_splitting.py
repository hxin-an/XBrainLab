"""Dataset-splitting UI tests at the detached publication boundary."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QDialog, QLabel

from tests.unit.ui.data_split_test_support import (
    dialog_context_kwargs,
    successful_preview,
)
from XBrainLab.backend.application.dataset_split_preview import (
    DatasetSplitChoice,
    DatasetSplitContext,
    DatasetSplitPreviewRow,
    DatasetSplitSpecification,
)
from XBrainLab.backend.dataset import (
    DataSplittingConfig,
    SplitByType,
    SplitUnit,
    TrainingType,
    ValSplitByType,
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
        "Fold 1",
        "80",
        "10",
        "10",
    ]
    assert window.tree.selectedItems() == []
    assert window.tree.currentIndex().isValid() is False
    assert window.tree.height() <= 180


def test_step_two_shows_epoch_trials_atomic_groups_and_class_labels(qtbot) -> None:
    context = DatasetSplitContext(
        epoch_available=True,
        trial_count=12,
        trial_group_count=3,
        label_count=2,
        label_choices=(
            DatasetSplitChoice(value="7.50", label="7.50 Hz"),
            DatasetSplitChoice(value="10.00", label="10.00 Hz"),
        ),
    )
    window = DataSplittingPreviewDialog(
        None,
        "Test Window",
        config=_split_config(),
        **dialog_context_kwargs(context=context, preview_provider=successful_preview),
    )
    qtbot.addWidget(window)
    labels = [label.text() for label in window.findChildren(QLabel)]

    assert "Trials" in labels and "12" in labels
    assert "Atomic trial groups" in labels and "3" in labels
    assert "7.50 Hz, 10.00 Hz" in labels
    classes_value = next(
        label
        for label in window.findChildren(QLabel)
        if label.text() == "7.50 Hz, 10.00 Hz"
    )
    assert classes_value.wordWrap()
    assert classes_value.toolTip() == "7.50 Hz, 10.00 Hz"


@pytest.mark.parametrize(
    ("split_unit", "value"),
    [
        (SplitUnit.RATIO, "0.3"),
        (SplitUnit.NUMBER, "3"),
        (SplitUnit.MANUAL, "0 2"),
    ],
)
def test_step_two_rehydrates_saved_test_unit_and_value(
    qtbot,
    split_unit,
    value,
) -> None:
    specification = DatasetSplitSpecification.from_payload(
        {
            "train_type": "Full Data",
            "is_cross_validation": False,
            "val_splitters": [],
            "test_splitters": [
                {
                    "split_type": SplitByType.TRIAL.value,
                    "split_unit": split_unit.value,
                    "value": value,
                    "is_option": True,
                }
            ],
        }
    )
    config = DataSplittingConfig(
        train_type=TrainingType.FULL,
        is_cross_validation=False,
        val_splitter_list=[],
        test_splitter_list=[DataSplitterHolder(True, SplitByType.TRIAL)],
    )
    window = DataSplittingPreviewDialog(
        None,
        "Test Window",
        config=config,
        initial_specification=specification,
        **dialog_context_kwargs(preview_provider=successful_preview),
    )
    qtbot.addWidget(window)
    if window.preview_worker is not None:
        window.preview_worker.join(timeout=1)

    unit_combo, entry = window.test_widgets[0]
    assert unit_combo.currentText() == split_unit.value
    assert entry.text() == value


@pytest.mark.parametrize(
    ("split_unit", "value"),
    [(SplitUnit.RATIO, "0.25"), (SplitUnit.NUMBER, "2")],
)
def test_step_two_rehydrates_saved_validation_unit_value_and_payload(
    qtbot,
    split_unit,
    value,
) -> None:
    specification = DatasetSplitSpecification.from_payload(
        {
            "train_type": "Full Data",
            "is_cross_validation": False,
            "val_splitters": [
                {
                    "split_type": ValSplitByType.TRIAL.value,
                    "split_unit": split_unit.value,
                    "value": value,
                    "is_option": True,
                }
            ],
            "test_splitters": [
                {
                    "split_type": SplitByType.TRIAL.value,
                    "split_unit": "Ratio",
                    "value": "0.2",
                    "is_option": True,
                }
            ],
        }
    )
    config = DataSplittingConfig(
        train_type=TrainingType.FULL,
        is_cross_validation=False,
        val_splitter_list=[DataSplitterHolder(True, ValSplitByType.TRIAL)],
        test_splitter_list=[DataSplitterHolder(True, SplitByType.TRIAL)],
    )
    window = DataSplittingPreviewDialog(
        None,
        "Test Window",
        config=config,
        initial_specification=specification,
        **dialog_context_kwargs(preview_provider=successful_preview),
    )
    qtbot.addWidget(window)
    if window.preview_worker is not None:
        window.preview_worker.join(timeout=1)

    unit_combo, entry = window.val_widgets[0]
    assert unit_combo.currentText() == split_unit.value
    assert entry.text() == value
    assert window._split_config_payload()["val_splitters"][0]["value"] == value


@pytest.mark.parametrize(
    ("cross_validation", "expected_test_units", "expected_validation_units"),
    [
        (False, ("Ratio", "Number", "Manual"), ("Ratio", "Number", "Manual")),
        (True, ("K Fold",), ("Ratio", "Number")),
    ],
)
def test_step_two_projects_split_units_from_backend_context(
    qtbot,
    cross_validation,
    expected_test_units,
    expected_validation_units,
) -> None:
    config = DataSplittingConfig(
        train_type=TrainingType.FULL,
        is_cross_validation=cross_validation,
        val_splitter_list=[DataSplitterHolder(True, ValSplitByType.TRIAL)],
        test_splitter_list=[DataSplitterHolder(True, SplitByType.TRIAL)],
    )
    window = DataSplittingPreviewDialog(
        None,
        "Test Window",
        config=config,
        **dialog_context_kwargs(preview_provider=successful_preview),
    )
    qtbot.addWidget(window)
    if window.preview_worker is not None:
        window.preview_worker.join(timeout=1)

    val_combo, _val_entry = window.val_widgets[0]
    test_combo, _test_entry = window.test_widgets[0]
    assert [val_combo.itemText(index) for index in range(val_combo.count())] == list(
        expected_validation_units
    )
    assert [test_combo.itemText(index) for index in range(test_combo.count())] == list(
        expected_test_units
    )


def test_data_splitting_window_keeps_long_preview_complete_without_summary_noise(
    qtbot,
) -> None:
    """Long results stay available through the table's own scroll affordance."""
    rows = tuple(
        DatasetSplitPreviewRow(
            name=f"Fold_{index}",
            train_count=80,
            validation_count=10,
            test_count=10,
        )
        for index in range(51)
    )

    def preview(request):
        from XBrainLab.backend.application.dataset_split_preview import (
            DatasetSplitPreviewPublication,
        )

        return DatasetSplitPreviewPublication(
            request=request,
            generation=request.publication_generation,
            rows=rows,
            train_count=4000,
            validation_count=500,
            test_count=500,
            total_count=51,
            truncated_count=0,
        )

    window = DataSplittingPreviewDialog(
        None,
        "Test Window",
        config=_split_config(),
        **dialog_context_kwargs(preview_provider=preview),
    )
    qtbot.addWidget(window)
    if window.preview_worker is not None:
        window.preview_worker.join(timeout=1)
    window.update_table()

    assert window.tree.topLevelItemCount() == 51
    labels = [label.text() for label in window.findChildren(QLabel)]
    assert not any("Showing" in label for label in labels)
    assert not any(label.startswith("Train ") for label in labels)


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
