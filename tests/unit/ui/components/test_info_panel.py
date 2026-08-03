import ast
from pathlib import Path

import pytest
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from XBrainLab.ui.components.info_panel import (
    INFO_KEY_COLUMN_PADDING,
    AggregateInfoPanel,
    SidebarScrollArea,
)
from XBrainLab.ui.styles.theme import Theme


def test_sidebar_scroll_surface_keeps_the_shared_sidebar_background(qtbot):
    area = SidebarScrollArea()
    qtbot.addWidget(area)

    expected = Theme.BACKGROUND_MID.lower()
    assert expected in area.viewport().styleSheet().lower()
    assert expected in area.content.styleSheet().lower()


def _detached_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "subject": "Sub1",
        "session": "Ses1",
        "epochs_length": 0,
        "is_raw": True,
        "event": {"labels": ["EventA"], "count": 7},
        "n_channels": 32,
        "sampling_frequency": 250.0,
        "epoch_duration_samples": None,
        "tmin": None,
        "highpass": 0.5,
        "lowpass": 40.0,
    }
    row.update(overrides)
    return row


@pytest.fixture
def panel(qtbot):
    panel = AggregateInfoPanel(None)
    qtbot.addWidget(panel)
    return panel


def test_init(panel):
    assert panel.title() == "Data Summary"
    assert panel.table.rowCount() == 13  # 13 keys
    assert panel.table.isHidden() is False
    assert all(
        panel.table.item(row, 1).text() == "-" for row in range(panel.table.rowCount())
    )
    assert panel.table.textElideMode() is Qt.TextElideMode.ElideNone
    assert panel.table.wordWrap() is True
    assert [
        panel.table.item(row, 0).text() for row in range(panel.table.rowCount())
    ] == [
        "Type",
        "EEG files",
        "Subjects",
        "Sessions",
        "Epochs",
        "Events",
        "Channels",
        "Sample rate",
        "Epoch start",
        "Epoch length",
        "High pass",
        "Low pass",
        "Classes",
    ]


def test_empty_summary_keeps_fixed_table_skeleton_at_compact_high_dpi_width(qtbot):
    panel = AggregateInfoPanel(None)
    qtbot.addWidget(panel)
    font = panel.font()
    font.setPointSize(max(14, font.pointSize() + 4))
    panel.setFont(font)
    panel.resize(220, 180)
    panel.show()
    qtbot.wait(0)

    assert panel.table.isVisibleTo(panel)
    assert all(
        not panel.table.isRowHidden(row) for row in range(panel.table.rowCount())
    )
    vertical_scrollbar = panel.table.verticalScrollBar()
    assert vertical_scrollbar is not None
    assert vertical_scrollbar.maximum() == 0


def test_info_panel_rows_fit_without_vertical_clipping(qtbot):
    panel = AggregateInfoPanel(None)
    qtbot.addWidget(panel)
    data = _detached_row(
        epochs_length=10,
        is_raw=False,
        event={"labels": ["left", "right"], "count": 10},
        n_channels=8,
        sampling_frequency=100.0,
        epoch_duration_samples=100,
        tmin=-0.2,
    )
    panel.update_info(preprocessed_data_list=[data])

    panel.resize(240, 340)
    panel.show()
    qtbot.wait(0)

    scrollbar = panel.table.verticalScrollBar()
    assert scrollbar is not None
    assert scrollbar.maximum() == 0
    last_row = panel.row_map["Training classes"]
    item = panel.table.item(last_row, 0)
    assert item is not None
    viewport = panel.table.viewport()
    assert viewport is not None
    assert panel.table.visualItemRect(item).bottom() <= viewport.height()


def test_info_panel_balances_key_and_value_columns_at_sidebar_width(qtbot):
    panel = AggregateInfoPanel(None)
    qtbot.addWidget(panel)
    panel.update_info(
        preprocessed_data_list=[
            {
                "subject": "subject-01",
                "session": "session-01",
                "epochs_length": 288,
                "is_raw": False,
                "event": {"labels": ["left", "right"], "count": 288},
                "n_channels": 22,
                "sampling_frequency": 250.0,
                "epoch_duration_samples": 300,
                "tmin": -0.2,
                "highpass": 1.0,
                "lowpass": 40.0,
            }
        ]
    )

    panel.resize(240, 340)
    panel.show()
    qtbot.wait(0)

    key_items = [panel.table.item(row, 0) for row in range(panel.table.rowCount())]
    assert all(item is not None for item in key_items)
    minimum_value_width = max(
        panel.table.fontMetrics().horizontalAdvance(item.text())
        for row in range(panel.table.rowCount())
        if not panel.table.isRowHidden(row)
        and (item := panel.table.item(row, 1)) is not None
    )
    minimum_value_width += 16
    viewport = panel.table.viewport()
    assert viewport is not None
    assert panel.table.columnWidth(0) <= viewport.width() - minimum_value_width
    assert all(item is not None and item.toolTip() == item.text() for item in key_items)
    epoch_length_item = panel.table.item(panel.row_map["EEG epoch duration"], 0)
    assert epoch_length_item is not None
    epoch_length_width = (
        panel.table.fontMetrics().boundingRect(epoch_length_item.text()).width()
    )
    assert panel.table.visualItemRect(epoch_length_item).width() >= (
        epoch_length_width + 8
    )


def test_info_panel_prioritizes_readable_keys_when_both_columns_fit(qtbot):
    panel = AggregateInfoPanel(None)
    qtbot.addWidget(panel)
    font = panel.font()
    font.setPointSize(10)
    panel.setFont(font)
    panel.table.setFont(font)
    panel.update_info(
        preprocessed_data_list=[
            {
                "subject": "subject-01",
                "session": "session-01",
                "epochs_length": 10,
                "is_raw": False,
                "event": {"labels": ["left", "right"], "count": 10},
                "n_channels": 4,
                "sampling_frequency": 128.0,
                "epoch_duration_samples": 66,
                "tmin": 0.0,
                "highpass": 4.0,
                "lowpass": 40.0,
            }
        ]
    )
    panel.resize(197, 340)
    panel.show()
    qtbot.wait(0)

    row = panel.row_map["EEG epoch duration"]
    key_item = panel.table.item(row, 0)
    value_item = panel.table.item(row, 1)
    assert key_item is not None
    assert value_item is not None
    metrics = panel.table.fontMetrics()
    assert panel.table.visualItemRect(key_item).width() >= (
        metrics.horizontalAdvance(key_item.text()) + 8
    )
    assert panel.table.visualItemRect(value_item).width() >= (
        metrics.horizontalAdvance(value_item.text()) + 8
    )


def test_info_panel_uses_exact_key_padding_at_fixed_sidebar_high_dpi(qtbot):
    panel = AggregateInfoPanel(None)
    qtbot.addWidget(panel)
    font = panel.font()
    font.setPointSizeF(15.0)
    panel.setFont(font)
    panel.table.setFont(font)
    panel.update_info(
        preprocessed_data_list=[
            _detached_row(
                epochs_length=120,
                is_raw=False,
                event={"labels": ["left", "right"], "count": 120},
                n_channels=64,
                sampling_frequency=250.0,
                epoch_duration_samples=250,
                tmin=-0.2,
            )
        ]
    )
    panel.resize(230, 520)
    panel.show()
    qtbot.wait(0)

    viewport = panel.table.viewport()
    assert viewport is not None
    metrics = panel.table.fontMetrics()
    key_items = [panel.table.item(row, 0) for row in range(panel.table.rowCount())]
    assert all(item is not None for item in key_items)
    required_key_width = (
        max(
            metrics.horizontalAdvance(item.text())
            for item in key_items
            if item is not None
        )
        + INFO_KEY_COLUMN_PADDING
    )
    assert panel.table.columnWidth(0) == required_key_width
    assert panel.table.columnWidth(1) >= metrics.horizontalAdvance("Epochs") + 8
    assert panel.table.columnWidth(0) + panel.table.columnWidth(1) == viewport.width()


def test_info_panel_recomputes_columns_when_a_hidden_page_is_shown_again(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(260, 720)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(10, 10, 10, 10)

    panel = AggregateInfoPanel(host)
    layout.addWidget(panel)
    host.show()
    qtbot.wait(0)

    host.hide()
    panel.table.setColumnWidth(0, 20)
    host.show()
    qtbot.waitUntil(lambda: panel.table.columnWidth(0) > 20, timeout=1_000)

    key_items = [panel.table.item(row, 0) for row in range(panel.table.rowCount())]
    assert all(item is not None for item in key_items)
    longest_label = max(item.text() for item in key_items if item is not None)
    required_width = panel.table.fontMetrics().horizontalAdvance(longest_label) + 8
    assert panel.table.columnWidth(0) >= required_width


@pytest.mark.parametrize("host_kind", ["direct", "scroll"])
@pytest.mark.parametrize("sidebar_width", [250, 260, 320])
@pytest.mark.parametrize("font_scale", [1.0, 1.25, 1.5])
def test_info_panel_text_fits_shared_narrow_sidebar_layouts(
    qtbot,
    host_kind,
    sidebar_width,
    font_scale,
):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(sidebar_width, 720)
    host_layout = QVBoxLayout(host)
    host_layout.setContentsMargins(0, 0, 0, 0)

    panel = AggregateInfoPanel(None)
    font = panel.font()
    font.setPointSizeF(font.pointSizeF() * font_scale)
    panel.setFont(font)
    panel.table.setFont(font)

    scroll_area = None
    if host_kind == "scroll":
        scroll_area = SidebarScrollArea(host)
        scroll_area.content_layout.setContentsMargins(10, 10, 10, 10)
        scroll_area.content_layout.addWidget(panel)
        host_layout.addWidget(scroll_area)
    else:
        host_layout.setContentsMargins(10, 10, 10, 10)
        host_layout.addWidget(panel)

    panel.update_info(
        preprocessed_data_list=[
            {
                "subject": "subject-01",
                "session": None,
                "epochs_length": 288,
                "is_raw": False,
                "event": {"labels": ["left", "right"], "count": 288},
                "n_channels": 22,
                "sampling_frequency": 250.0,
                "epoch_duration_samples": 300,
                "tmin": -0.2,
                "highpass": 1.0,
                "lowpass": 40.0,
            }
        ]
    )
    host.show()
    qtbot.wait(0)

    assert not panel.table.isRowHidden(panel.row_map["Sessions"])
    session_value_item = panel.table.item(panel.row_map["Sessions"], 1)
    assert session_value_item is not None
    assert session_value_item.text() == "-"
    table_scrollbar = panel.table.horizontalScrollBar()
    assert table_scrollbar is not None
    assert table_scrollbar.maximum() == 0
    if scroll_area is not None:
        sidebar_scrollbar = scroll_area.horizontalScrollBar()
        assert sidebar_scrollbar is not None
        assert sidebar_scrollbar.maximum() == 0

    viewport = panel.table.viewport()
    assert viewport is not None
    metrics = panel.table.fontMetrics()
    wrap_flags = (
        int(Qt.AlignmentFlag.AlignLeft)
        | int(Qt.AlignmentFlag.AlignTop)
        | int(Qt.TextFlag.TextWordWrap)
    )
    for row in range(panel.table.rowCount()):
        if panel.table.isRowHidden(row):
            continue
        for column in range(panel.table.columnCount()):
            item = panel.table.item(row, column)
            assert item is not None
            cell_rect = panel.table.visualItemRect(item)
            assert cell_rect.left() >= 0
            assert cell_rect.right() < viewport.width()
            text_rect = metrics.boundingRect(
                QRect(0, 0, max(1, cell_rect.width() - 8), 10_000),
                wrap_flags,
                item.text(),
            )
            assert text_rect.width() <= max(1, cell_rect.width() - 8)
            assert cell_rect.height() >= text_rect.height() + 2


def test_info_panel_visible_value_is_not_clipped_by_hidden_long_keys(qtbot):
    panel = AggregateInfoPanel(None)
    qtbot.addWidget(panel)
    data = _detached_row(
        event={"labels": ["left", "right"], "count": 10},
        n_channels=4,
        sampling_frequency=128.0,
        highpass=0.0,
        lowpass=64.0,
    )

    panel.resize(240, 340)
    panel.update_info(loaded_data_list=[data])
    panel.show()
    qtbot.wait(0)

    row = panel.row_map["Type"]
    item = panel.table.item(row, 1)
    assert item is not None
    visual_rect = panel.table.visualItemRect(item)
    text_width = panel.table.fontMetrics().horizontalAdvance(item.text())
    assert visual_rect.width() >= text_width + 8


def test_info_panel_row_height_tracks_larger_application_font(qtbot):
    panel = AggregateInfoPanel(None)
    qtbot.addWidget(panel)
    font = panel.font()
    font.setPointSize(max(font.pointSize() + 6, 16))

    panel.table.setRowHidden(0, False)
    panel.table.setFont(font)
    panel.show()
    qtbot.wait(0)

    required_height = panel.table.fontMetrics().height() + 2
    assert panel.table.rowHeight(0) >= required_height


def test_update_info_no_data(panel, qtbot):
    with qtbot.waitSignal(panel.presentation_changed, timeout=100):
        panel.update_info(loaded_data_list=[], preprocessed_data_list=[])
    assert panel.has_data is False
    assert panel.table.isHidden() is False
    assert all(
        not panel.table.isRowHidden(row) for row in range(panel.table.rowCount())
    )
    assert all(
        panel.table.item(row, 1).text() == "-" for row in range(panel.table.rowCount())
    )


def test_update_info_fails_closed_for_live_domain_objects_without_scanning(panel):
    class LiveEegDomainObject:
        def __getattr__(self, name):
            raise AssertionError(f"live EEG domain access is forbidden: {name}")

    panel.update_info(
        loaded_data_list=[
            {
                "subject": "subject-01",
                "is_raw": True,
                "n_channels": 22,
                "sampling_frequency": 250.0,
            }
        ]
    )
    assert panel.has_data is True

    panel.update_info(loaded_data_list=[LiveEegDomainObject()])

    assert panel.has_data is False
    assert all(
        panel.table.item(row, 1).text() == "-" for row in range(panel.table.rowCount())
    )


def test_product_info_panel_has_no_live_eeg_domain_reader_calls():
    source_path = (
        Path(__file__).resolve().parents[4] / "XBrainLab/ui/components/info_panel.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    panel_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "AggregateInfoPanel"
    )
    forbidden_readers = {
        "get_epoch_duration",
        "get_epochs_length",
        "get_event_list",
        "get_event_summary",
        "get_filter_range",
        "get_nchan",
        "get_session_name",
        "get_sfreq",
        "get_subject_name",
        "get_tmin",
        "is_raw",
    }
    attribute_calls = {
        node.func.attr
        for node in ast.walk(panel_class)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    dynamic_getattr_names = {
        node.args[1].value
        for node in ast.walk(panel_class)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    }

    assert forbidden_readers.isdisjoint(attribute_calls | dynamic_getattr_names)


def test_update_info_loaded_rows(panel, qtbot):
    row = _detached_row()
    with qtbot.waitSignal(panel.presentation_changed, timeout=100):
        panel.update_info(loaded_data_list=[row])

    assert panel.table.item(panel.row_map["Type"], 1).text() == "Continuous EEG"
    assert panel.table.item(panel.row_map["EEG files"], 1).text() == "1"
    assert panel.table.item(panel.row_map["Subjects"], 1).text() == "1"
    assert panel.table.item(panel.row_map["Sampling rate"], 1).text() == "250 Hz"
    assert panel.table.item(panel.row_map["EEG epochs"], 1).text() == "-"
    assert panel.has_data is True


def test_update_info_uses_detached_event_summary(panel):
    row = _detached_row(
        event={"count": 7, "labels": ["EventA", "EventB"]},
    )

    panel.update_info(loaded_data_list=[row])

    assert panel.table.item(panel.row_map["EEG events"], 1).text() == "7"
    assert panel.table.item(panel.row_map["Training classes"], 1).text() == "2"


def test_update_info_preprocessed_row_priority(panel):
    loaded_row = _detached_row(subject="Loaded", n_channels=8)
    preprocessed_row = _detached_row(
        subject="Preprocessed",
        is_raw=False,
        epochs_length=100,
        event={"labels": ["EventB"], "count": 100},
        n_channels=16,
        sampling_frequency=100.0,
        epoch_duration_samples=100,
        tmin=-0.2,
        highpass=1.0,
        lowpass=50.0,
    )
    panel.update_info(
        loaded_data_list=[loaded_row],
        preprocessed_data_list=[preprocessed_row],
    )

    assert panel.table.item(panel.row_map["Type"], 1).text() == "Epochs"
    assert panel.table.item(panel.row_map["Channels"], 1).text() == "16"
    assert panel.table.item(panel.row_map["EEG epochs"], 1).text() == "100"
    assert not panel.table.isRowHidden(panel.row_map["EEG epoch start"])
    assert not panel.table.isRowHidden(panel.row_map["EEG epoch duration"])


def test_update_info_uses_loaded_rows_when_preprocessed_rows_are_empty(panel):
    loaded_row = _detached_row(
        subject="SubFallback",
        session="",
        event={"labels": [], "count": 0},
        n_channels=1,
        sampling_frequency=1.0,
        highpass=0.0,
        lowpass=0.0,
    )
    panel.update_info(
        loaded_data_list=[loaded_row],
        preprocessed_data_list=[],
    )

    assert panel.table.item(panel.row_map["Subjects"], 1).text() == "1"


def test_update_info_missing_detached_duration_inputs_show_placeholder(panel):
    row = _detached_row(
        subject="",
        session="",
        epochs_length=0,
        is_raw=False,
        event={"labels": [], "count": 0},
        n_channels=0,
        sampling_frequency=1.0,
        epoch_duration_samples=None,
        highpass=0.0,
        lowpass=0.0,
    )

    panel.update_info(preprocessed_data_list=[row])

    assert panel.table.item(panel.row_map["EEG epoch duration"], 1).text() == "-"
