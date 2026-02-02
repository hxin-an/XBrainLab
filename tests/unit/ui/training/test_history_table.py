from unittest.mock import MagicMock

import pytest

from XBrainLab.ui.panels.training.history_table import TrainingHistoryTable


@pytest.fixture
def history_table(qtbot):
    table = TrainingHistoryTable()
    qtbot.addWidget(table)
    return table


def test_history_table_init(history_table):
    assert history_table.columnCount() == 11
    assert history_table.rowCount() == 0


def test_history_table_update_history(history_table):
    # Mock data
    mock_plan = MagicMock()
    mock_plan.option.epoch = 10

    mock_record = MagicMock()
    mock_record.get_epoch.return_value = 1
    mock_record.is_finished.return_value = False
    mock_record.train = {"loss": [0.5], "accuracy": [0.1], "lr": [0.01]}
    mock_record.val = {"loss": [0.6], "accuracy": [0.1]}
    mock_record.start_timestamp = 1000
    mock_record.end_timestamp = 1060  # 1 min

    data = [
        {
            "plan": mock_plan,
            "record": mock_record,
            "group_name": "Group1",
            "run_name": "Run1",
            "model_name": "Model1",
            "is_current_run": False,
        }
    ]

    history_table.update_history(data)

    assert history_table.rowCount() == 1
    assert history_table.item(0, 0).text() == "Group1"
    assert history_table.item(0, 1).text() == "Run1"
    assert history_table.item(0, 4).text() == "1/10"
    assert history_table.item(0, 10).text() != "-"


def test_history_table_selection_signal(history_table, qtbot):
    # Populate
    mock_record = MagicMock()
    data = [
        {
            "plan": MagicMock(),
            "record": mock_record,
            "group_name": "G",
            "run_name": "R",
            "model_name": "M",
        }
    ]
    history_table.update_history(data)

    # Watch signal
    with qtbot.waitSignal(history_table.selection_changed_record) as blocker:
        history_table.selectRow(0)

    assert blocker.args[0] == mock_record
