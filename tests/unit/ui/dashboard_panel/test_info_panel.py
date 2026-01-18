from unittest.mock import MagicMock

import pytest

from XBrainLab.ui.dashboard_panel.info import AggregateInfoPanel


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
    panel.main_window = mock_main_window
    qtbot.addWidget(panel)
    return panel


def test_init(panel):
    assert panel.title() == "Aggregate Information"
    assert panel.table.rowCount() == 13  # 13 keys


def test_update_info_no_data(panel, mock_main_window):
    panel.update_info(loaded_data_list=[], preprocessed_data_list=[])
    # Check "Total Files" is "-"
    row = panel.row_map["Total Files"]
    assert panel.table.item(row, 1).text() == "-"


def test_update_info_loaded_data(panel, mock_main_window):
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

    panel.update_info(loaded_data_list=mock_main_window.study.loaded_data_list)

    # Checks
    assert panel.table.item(panel.row_map["Type"], 1).text() == "raw"
    assert panel.table.item(panel.row_map["Total Files"], 1).text() == "1"
    assert panel.table.item(panel.row_map["Subjects"], 1).text() == "1"
    assert panel.table.item(panel.row_map["Sample rate"], 1).text() == "250.0"


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

    assert panel.table.item(panel.row_map["Type"], 1).text() == "epochs"
    assert panel.table.item(panel.row_map["Channel"], 1).text() == "16"
    assert panel.table.item(panel.row_map["Total Epochs"], 1).text() == "100"


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
    assert panel.table.item(panel.row_map["duration (sec)"], 1).text() == "?"
