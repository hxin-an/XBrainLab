from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

from XBrainLab.ui.panels.training.history_table import TrainingHistoryTable


@pytest.fixture
def history_table(qtbot):
    widget = TrainingHistoryTable()
    qtbot.addWidget(widget)
    return widget


def test_init_ui(history_table):
    assert history_table.columnCount() == 11
    assert history_table.selectionMode() == QTableWidget.SelectionMode.SingleSelection


def test_metric_headers_fit_without_clipping(history_table):
    header = history_table.horizontalHeader()
    assert header is not None
    metrics = header.fontMetrics()
    for column in range(history_table.columnCount()):
        item = history_table.horizontalHeaderItem(column)
        assert item is not None
        assert history_table.columnWidth(column) >= (
            metrics.horizontalAdvance(item.text()) + 28
        )


def test_update_history_empty(history_table):
    history_table.update_history([])
    assert history_table.rowCount() == 0


def test_update_history_populates_rows(history_table):
    # Mock data structure
    mock_plan = MagicMock()
    mock_plan.option.epoch = 10

    mock_record = MagicMock()
    mock_record.get_epoch.return_value = 5
    mock_record.is_finished.return_value = False
    mock_record.epoch = 5
    mock_record.train = {"loss": [0.5], "accuracy": [0.8], "lr": [0.001]}
    mock_record.val = {"loss": [0.6], "accuracy": [0.75]}

    data = [
        {
            "plan": mock_plan,
            "record": mock_record,
            "group_name": "G1",
            "run_name": "R1",
            "model_name": "M1",
            "is_current_run": True,
        }
    ]

    history_table.update_history(data)

    assert history_table.rowCount() == 1
    assert history_table.item(0, 0).text() == "G1"
    assert history_table.item(0, 1).text() == "R1"
    assert history_table.item(0, 3).text() == "Running"
    assert history_table.item(0, 5).text() == "0.5000"  # Train Loss
    assert history_table.item(0, 6).text() == "0.80%"  # Train Acc


def test_finished_history_uses_completed_product_status(history_table):
    mock_plan = MagicMock()
    mock_plan.option.epoch = 10
    mock_record = MagicMock()
    mock_record.get_epoch.return_value = 10
    mock_record.is_finished.return_value = True
    mock_record.epoch = 10
    mock_record.train = {"loss": [0.2], "accuracy": [0.9], "lr": [0.001]}
    mock_record.val = {"loss": [0.3], "accuracy": [0.85]}

    history_table.update_history(
        [
            {
                "plan": mock_plan,
                "record": mock_record,
                "group_name": "Group 01",
                "run_name": "Run 01",
                "model_name": "EEGNet",
                "is_current_run": False,
            }
        ]
    )

    assert history_table.item(0, 3).text() == "Completed"


def test_key_columns_expand_for_group_run_model_and_status_text(
    history_table,
    qtbot,
):
    mock_plan = MagicMock()
    mock_plan.option.epoch = 12
    mock_record = MagicMock()
    mock_record.get_epoch.return_value = 12
    mock_record.is_finished.return_value = True
    mock_record.epoch = 12
    mock_record.train = {"loss": [0.2], "accuracy": [0.9], "lr": [0.001]}
    mock_record.val = {"loss": [0.3], "accuracy": [0.85]}
    history_table.resize(640, 320)
    history_table.show()

    history_table.update_history(
        [
            {
                "plan": mock_plan,
                "record": mock_record,
                "group_name": "Motor imagery group 01",
                "run_name": "Repeated run 12",
                "model_name": "ShallowConvNet",
                "is_current_run": False,
            }
        ]
    )
    qtbot.wait(0)

    for column in (0, 1, 2, 3):
        item = history_table.item(0, column)
        assert item is not None
        required_width = (
            history_table.fontMetrics().horizontalAdvance(item.text())
            + history_table.KEY_COLUMN_PADDING
        )
        assert history_table.columnWidth(column) >= required_width
    assert history_table.horizontalScrollBar().maximum() > 0


def test_empty_history_is_compact_and_has_an_intentional_empty_state(
    history_table,
    qtbot,
):
    history_table.resize(980, 420)
    history_table.show()
    history_table.update_history([])
    qtbot.wait(0)

    assert history_table.empty_state_label.isVisibleTo(history_table)
    assert history_table.empty_state_label.text() == "No training runs yet"
    assert history_table.height() == history_table.preferred_content_height()
    assert history_table.height() < 140
    assert (
        history_table.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )


def test_small_history_fits_rows_without_large_empty_viewport(
    history_table,
    qtbot,
):
    mock_plan = MagicMock()
    mock_plan.option.epoch = 10
    mock_record = MagicMock()
    mock_record.get_epoch.return_value = 1
    mock_record.is_finished.return_value = False
    mock_record.epoch = 1
    mock_record.train = {"loss": [0.5], "accuracy": [0.8], "lr": [0.001]}
    mock_record.val = {"loss": [0.6], "accuracy": [0.75]}
    row = {
        "plan": mock_plan,
        "record": mock_record,
        "group_name": "G1",
        "run_name": "R1",
        "model_name": "M1",
        "is_current_run": True,
    }
    history_table.resize(980, 420)
    history_table.show()

    history_table.update_history([row, {**row, "run_name": "R2"}])
    qtbot.wait(0)

    last_item = history_table.item(1, 0)
    viewport = history_table.viewport()
    assert last_item is not None
    assert viewport is not None
    assert not history_table.empty_state_label.isVisibleTo(history_table)
    assert history_table.visualItemRect(last_item).bottom() >= viewport.height() - 24
    assert history_table.height() == history_table.preferred_content_height()
    assert (
        history_table.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )


def test_large_history_caps_height_and_enables_row_scrolling(history_table, qtbot):
    mock_plan = MagicMock()
    mock_plan.option.epoch = 10
    mock_record = MagicMock()
    mock_record.get_epoch.return_value = 1
    mock_record.is_finished.return_value = False
    mock_record.epoch = 1
    mock_record.train = {"loss": [0.5], "accuracy": [0.8], "lr": [0.001]}
    mock_record.val = {"loss": [0.6], "accuracy": [0.75]}
    rows = [
        {
            "plan": mock_plan,
            "record": mock_record,
            "group_name": "G1",
            "run_name": f"R{index + 1}",
            "model_name": "M1",
            "is_current_run": index == 0,
        }
        for index in range(history_table.MAX_VISIBLE_ROWS + 3)
    ]
    history_table.resize(980, 520)
    history_table.show()

    history_table.update_history(rows)
    qtbot.wait(0)

    assert history_table.rowCount() == history_table.MAX_VISIBLE_ROWS + 3
    assert history_table.height() == history_table.preferred_content_height()
    assert (
        history_table.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )
    assert history_table.verticalScrollBar().maximum() > 0


def test_selection_emit(history_table, qtbot):
    # Setup mock row with an item so selection works
    mock_record = MagicMock()
    history_table.row_map[0] = (None, mock_record)
    history_table.setRowCount(1)
    history_table.setColumnCount(1)

    # Must explicitly set an item for QTableWidget to consider it "selectable" via items?
    # Actually, verify: does selecting a row without items return empty selectedItems()? Yes.
    history_table.setItem(0, 0, QTableWidgetItem("Test"))

    with qtbot.waitSignal(history_table.selection_changed_record) as blocker:
        history_table.selectRow(0)

    assert blocker.args[0] == mock_record


def test_clear_history(history_table):
    history_table.row_map[0] = ("plan", "record")
    history_table.setRowCount(1)

    history_table.clear_history()

    assert history_table.rowCount() == 0
    assert len(history_table.row_map) == 0
