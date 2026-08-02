import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

from XBrainLab.ui.panels.training.history_table import TrainingHistoryTable


def _history_row(
    *,
    plan_index=0,
    run_index=0,
    group_name="G1",
    run_name="R1",
    model_name="M1",
    status="Running",
    epoch=1,
    max_epochs=10,
):
    return {
        "identity": {
            "plan_index": plan_index,
            "run_index": run_index,
        },
        "group_name": group_name,
        "run_name": run_name,
        "model_name": model_name,
        "status": status,
        "epoch": epoch,
        "max_epochs": max_epochs,
        "is_active": status == "Running",
        "is_current_run": status == "Running",
        "start_timestamp": None,
        "end_timestamp": None,
        "metrics": {
            "train": {
                "loss": [0.5],
                "accuracy": [0.8],
                "auc": [],
                "lr": [0.001],
                "time": [],
            },
            "validation": {
                "loss": [0.6],
                "accuracy": [0.75],
                "auc": [],
            },
        },
    }


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
    assert header.font().bold()
    metrics = header.fontMetrics()
    for column in range(history_table.columnCount()):
        item = history_table.horizontalHeaderItem(column)
        assert item is not None
        assert history_table.columnWidth(column) >= (
            metrics.horizontalAdvance(item.text()) + history_table.HEADER_PADDING
        )


def test_update_history_empty(history_table):
    history_table.update_history([])
    assert history_table.rowCount() == 0


def test_update_history_populates_rows(history_table):
    data = [_history_row(epoch=5)]

    history_table.update_history(data)

    assert history_table.rowCount() == 1
    assert history_table.item(0, 0).text() == "G1"
    assert history_table.item(0, 1).text() == "R1"
    assert history_table.item(0, 3).text() == "Running"
    assert history_table.item(0, 5).text() == "0.5000"  # Train Loss
    assert history_table.item(0, 6).text() == "0.80%"  # Train Acc


def test_finished_history_uses_completed_product_status(history_table):
    history_table.update_history(
        [
            _history_row(
                group_name="Group 01",
                run_name="Run 01",
                model_name="EEGNet",
                status="Completed",
                epoch=10,
            )
        ]
    )

    assert history_table.item(0, 3).text() == "Completed"


def test_key_columns_expand_for_group_run_model_and_status_text(
    history_table,
    qtbot,
):
    history_table.resize(640, 320)
    history_table.show()

    history_table.update_history(
        [
            _history_row(
                group_name="Motor imagery group 01",
                run_name="Repeated run 12",
                model_name="ShallowConvNet",
                status="Completed",
                epoch=12,
                max_epochs=12,
            )
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


def test_standard_history_width_fits_without_horizontal_scrolling(
    history_table,
    qtbot,
):
    history_table.resize(980, 320)
    history_table.show()
    history_table.update_history(
        [
            _history_row(
                group_name="Group 01",
                run_name="Run 01",
                model_name="ShallowConvNet",
                status="Completed",
                epoch=12,
                max_epochs=12,
            )
        ]
    )
    qtbot.wait(0)

    assert history_table.horizontalScrollBar().maximum() == 0
    assert history_table.horizontalHeader().length() <= history_table.viewport().width()


def test_empty_history_uses_the_stable_history_viewport(
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
    expected_height = (
        history_table.horizontalHeader().sizeHint().height()
        + (
            history_table.verticalHeader().defaultSectionSize()
            * history_table.MAX_VISIBLE_ROWS
        )
        + (2 * history_table.frameWidth())
    )
    assert history_table.preferred_content_height() == expected_height
    assert (
        history_table.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )


def test_small_history_does_not_resize_the_history_viewport(
    history_table,
    qtbot,
):
    row = _history_row()
    history_table.resize(980, 420)
    history_table.show()

    history_table.update_history([row, {**row, "run_name": "R2"}])
    qtbot.wait(0)

    last_item = history_table.item(1, 0)
    viewport = history_table.viewport()
    assert last_item is not None
    assert viewport is not None
    assert not history_table.empty_state_label.isVisibleTo(history_table)
    assert history_table.visualItemRect(last_item).bottom() < viewport.height()
    assert history_table.height() == history_table.preferred_content_height()
    assert (
        history_table.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )


def test_stable_history_geometry_skips_redundant_item_layout(
    history_table,
    qtbot,
    monkeypatch,
):
    history_table.resize(980, 420)
    history_table.show()
    history_table.update_history([])
    qtbot.wait(0)
    layout_calls = []
    monkeypatch.setattr(
        history_table,
        "doItemsLayout",
        lambda: layout_calls.append(True),
    )

    history_table._sync_content_height()

    assert layout_calls == []


def test_large_history_caps_height_and_enables_row_scrolling(history_table, qtbot):
    rows = [
        _history_row(
            run_index=index,
            run_name=f"R{index + 1}",
            status="Running" if index == 0 else "Pending",
        )
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
    assert history_table.horizontalScrollBar().maximum() == 0
    assert history_table.horizontalHeader().length() <= history_table.viewport().width()
    viewport = history_table.viewport()
    assert viewport is not None
    for row in range(history_table.MAX_VISIBLE_ROWS):
        assert viewport.rect().contains(
            history_table.visualItemRect(history_table.item(row, 0))
        )
    first_hidden = history_table.visualItemRect(
        history_table.item(history_table.MAX_VISIBLE_ROWS, 0)
    )
    assert not viewport.rect().intersects(first_hidden)


def test_wide_history_viewport_does_not_reveal_a_partial_fourth_row(
    history_table,
    qtbot,
):
    rows = [
        _history_row(
            run_index=index,
            run_name=f"R{index + 1}",
            status="Stopped",
        )
        for index in range(history_table.MAX_VISIBLE_ROWS + 1)
    ]
    history_table.resize(1800, 520)
    history_table.show()
    history_table.update_history(rows)
    qtbot.wait(0)

    viewport = history_table.viewport()
    fourth_row = history_table.visualItemRect(
        history_table.item(history_table.MAX_VISIBLE_ROWS, 0)
    )
    assert not viewport.rect().intersects(fourth_row)


def test_history_height_stays_fixed_when_vertical_scrollbar_appears(
    history_table,
    qtbot,
):
    row = _history_row(status="Stopped")
    header = history_table.horizontalHeader()
    assert header is not None
    just_fits_columns = header.length() + (2 * history_table.frameWidth()) + 2
    history_table.resize(just_fits_columns, 420)
    history_table.show()
    history_table.update_history([])
    qtbot.wait(0)
    empty_height = history_table.height()

    history_table.update_history(
        [
            {**row, "run_name": f"R{index + 1}"}
            for index in range(history_table.MAX_VISIBLE_ROWS + 2)
        ]
    )
    qtbot.wait(0)

    assert history_table.verticalScrollBar().maximum() > 0
    assert history_table.height() == empty_height
    first_hidden = history_table.visualItemRect(
        history_table.item(history_table.MAX_VISIBLE_ROWS, 0)
    )
    assert not history_table.viewport().rect().intersects(first_hidden)


def test_selection_emit(history_table, qtbot):
    identity = {"plan_index": 2, "run_index": 3}
    history_table.row_identity_by_index[0] = identity
    history_table.setRowCount(1)
    history_table.setColumnCount(1)
    history_table.setItem(0, 0, QTableWidgetItem("Test"))

    with qtbot.waitSignal(history_table.selection_changed_identity) as blocker:
        history_table.selectRow(0)

    assert blocker.args[0] == identity


def test_clear_history(history_table):
    history_table.row_identity_by_index[0] = {
        "plan_index": 0,
        "run_index": 0,
    }
    history_table.setRowCount(1)

    history_table.clear_history()

    assert history_table.rowCount() == 0
    assert len(history_table.row_identity_by_index) == 0
