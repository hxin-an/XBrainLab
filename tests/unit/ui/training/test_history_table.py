from unittest.mock import MagicMock

import pytest
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
