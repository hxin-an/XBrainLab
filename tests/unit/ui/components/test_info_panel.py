from unittest.mock import MagicMock

import pytest

from XBrainLab.ui.components.info_panel import AggregateInfoPanel


@pytest.fixture
def mock_main_window():
    window = MagicMock()
    window.study = MagicMock()
    # Defaults
    window.study.loaded_data_list = []
    window.study.preprocessed_data_list = []
    window.study.epoch_data = None
    return window


@pytest.fixture
def panel(qtbot, mock_main_window):
    panel = AggregateInfoPanel(None)
    qtbot.addWidget(panel)
    return panel


def test_init(panel):
    assert panel.title() == "Data Summary"
    assert panel.table.rowCount() == 13  # 13 keys


def test_info_panel_rows_fit_without_vertical_clipping(qtbot):
    panel = AggregateInfoPanel(None)
    qtbot.addWidget(panel)
    data = MagicMock()
    data.get_subject_name.return_value = "Sub1"
    data.get_session_name.return_value = "Ses1"
    data.get_epochs_length.return_value = 10
    data.is_raw.return_value = False
    data.get_tmin.return_value = -0.2
    data.get_epoch_duration.return_value = 100
    data.get_nchan.return_value = 8
    data.get_sfreq.return_value = 100
    data.get_filter_range.return_value = (0.5, 40)
    data.get_event_list.return_value = (None, {"left": 1, "right": 2})
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


def test_info_panel_key_column_preserves_all_labels_at_sidebar_width(qtbot):
    panel = AggregateInfoPanel(None)
    qtbot.addWidget(panel)

    panel.resize(240, 340)
    panel.show()
    qtbot.wait(0)

    key_items = [panel.table.item(row, 0) for row in range(panel.table.rowCount())]
    assert all(item is not None for item in key_items)
    required_text_width = max(
        panel.table.fontMetrics().horizontalAdvance(item.text())
        for item in key_items
        if item is not None
    )
    assert panel.table.columnWidth(0) >= required_text_width + 16


def test_info_panel_visible_value_is_not_clipped_by_hidden_long_keys(qtbot):
    panel = AggregateInfoPanel(None)
    qtbot.addWidget(panel)
    data = MagicMock()
    data.get_subject_name.return_value = "Sub1"
    data.get_session_name.return_value = "Ses1"
    data.get_epochs_length.return_value = 0
    data.is_raw.return_value = True
    data.get_nchan.return_value = 4
    data.get_sfreq.return_value = 128
    data.get_filter_range.return_value = (0, 64)
    data.get_event_summary.return_value = {
        "available": True,
        "count": 10,
        "labels": ["left", "right"],
    }

    panel.resize(240, 340)
    panel.update_info(loaded_data_list=[data])
    panel.show()
    qtbot.wait(0)

    row = panel.row_map["Type"]
    item = panel.table.item(row, 1)
    assert item is not None
    visual_rect = panel.table.visualItemRect(item)
    text_width = panel.table.fontMetrics().horizontalAdvance(item.text())
    assert visual_rect.width() >= text_width + 16


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


def test_update_info_no_data(panel, mock_main_window, qtbot):
    with qtbot.waitSignal(panel.presentation_changed, timeout=100):
        panel.update_info(loaded_data_list=[], preprocessed_data_list=[])
    assert not panel.empty_label.isHidden()
    assert panel.has_data is False
    assert all(panel.table.isRowHidden(row) for row in range(panel.table.rowCount()))


def test_update_info_loaded_data(panel, mock_main_window, qtbot):
    # Setup Data
    d1 = MagicMock()
    d1.get_subject_name.return_value = "Sub1"
    d1.get_session_name.return_value = "Ses1"
    d1.get_epochs_length.return_value = 0
    d1.is_raw.return_value = True
    d1.get_nchan.return_value = 32
    d1.get_sfreq.return_value = 250.0
    d1.get_filter_range.return_value = (0.5, 40.0)
    d1.get_event_list.return_value = (None, {"EventA": 1})

    mock_main_window.study.loaded_data_list = [d1]

    with qtbot.waitSignal(panel.presentation_changed, timeout=100):
        panel.update_info(loaded_data_list=mock_main_window.study.loaded_data_list)

    # Checks
    assert panel.table.item(panel.row_map["Type"], 1).text() == "Continuous EEG"
    assert panel.table.item(panel.row_map["EEG files"], 1).text() == "1"
    assert panel.table.item(panel.row_map["Subjects"], 1).text() == "1"
    assert panel.table.item(panel.row_map["Sampling rate"], 1).text() == "250 Hz"
    assert panel.table.isRowHidden(panel.row_map["EEG epochs"])
    assert panel.has_data is True


def test_update_info_uses_cached_event_summary(panel, mock_main_window):
    d1 = MagicMock()
    d1.get_subject_name.return_value = "Sub1"
    d1.get_session_name.return_value = "Ses1"
    d1.get_epochs_length.return_value = 0
    d1.is_raw.return_value = True
    d1.get_nchan.return_value = 32
    d1.get_sfreq.return_value = 250.0
    d1.get_filter_range.return_value = (0.5, 40.0)
    d1.get_event_summary.return_value = {
        "available": True,
        "count": 7,
        "labels": ["EventA", "EventB"],
        "source": "detected_events",
        "scanned": True,
    }
    d1.get_event_list.side_effect = AssertionError(
        "aggregate info should not scan raw events during render"
    )

    panel.update_info(loaded_data_list=[d1])

    assert panel.table.item(panel.row_map["EEG events"], 1).text() == "7"
    assert panel.table.item(panel.row_map["Training classes"], 1).text() == "2"


def test_update_info_preprocessed_priority(panel, mock_main_window):
    # Loaded data exists but we should use preprocessed
    d_load = MagicMock()
    mock_main_window.study.loaded_data_list = [d_load]

    d_pre = MagicMock()
    d_pre.get_subject_name.return_value = "Sub1"
    d_pre.get_session_name.return_value = "Ses1"
    d_pre.is_raw.return_value = False  # Epoched
    d_pre.get_tmin.return_value = -0.2
    d_pre.get_epoch_duration.return_value = 1.0  # sec
    d_pre.get_sfreq.return_value = 100.0
    d_pre.get_nchan.return_value = 16
    d_pre.get_filter_range.return_value = (1.0, 50.0)
    d_pre.get_event_list.return_value = (None, {"EventB": 2})
    d_pre.get_epochs_length.return_value = 100

    mock_main_window.study.preprocessed_data_list = [d_pre]

    panel.update_info(
        loaded_data_list=mock_main_window.study.loaded_data_list,
        preprocessed_data_list=mock_main_window.study.preprocessed_data_list,
    )

    assert panel.table.item(panel.row_map["Type"], 1).text() == "Epochs"
    assert panel.table.item(panel.row_map["Channels"], 1).text() == "16"
    assert panel.table.item(panel.row_map["EEG epochs"], 1).text() == "100"
    assert not panel.table.isRowHidden(panel.row_map["EEG epoch start"])
    assert not panel.table.isRowHidden(panel.row_map["EEG epoch duration"])


def test_update_info_fallback(panel, mock_main_window):
    # Preprocessed empty, Epoch data exists, fallback to loaded
    mock_main_window.study.preprocessed_data_list = []
    mock_main_window.study.epoch_data = MagicMock()  # Exists

    d_load = MagicMock()
    d_load.is_raw.return_value = True
    d_load.get_subject_name.return_value = "SubFallback"

    # Configure so checks don't crash
    d_load.get_session_name.return_value = ""
    d_load.get_epochs_length.return_value = 0
    d_load.get_nchan.return_value = 1
    d_load.get_sfreq.return_value = 1
    d_load.get_filter_range.return_value = (0, 0)
    d_load.get_event_list.return_value = (None, {})

    mock_main_window.study.loaded_data_list = [d_load]

    panel.update_info(
        loaded_data_list=mock_main_window.study.loaded_data_list,
        preprocessed_data_list=mock_main_window.study.preprocessed_data_list,
    )

    # Should show loaded data info
    assert panel.table.item(panel.row_map["Subjects"], 1).text() == "1"


def test_update_info_duration_calc_error(panel, mock_main_window):
    d1 = MagicMock()
    d1.is_raw.return_value = False
    d1.get_epoch_duration.side_effect = Exception("Calc Error")
    # Need other mocks to pass
    d1.get_subject_name.return_value = ""
    d1.get_session_name.return_value = ""
    d1.get_epochs_length.return_value = 0
    d1.get_nchan.return_value = 0
    d1.get_sfreq.return_value = 1
    d1.get_filter_range.return_value = (0, 0)
    d1.get_event_list.return_value = (None, {})

    mock_main_window.study.preprocessed_data_list = [d1]

    panel.update_info(
        preprocessed_data_list=mock_main_window.study.preprocessed_data_list
    )
    assert panel.table.isRowHidden(panel.row_map["EEG epoch duration"])
