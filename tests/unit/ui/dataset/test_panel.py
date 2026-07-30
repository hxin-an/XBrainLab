from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QHeaderView,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.study import Study
from XBrainLab.ui.panels.dataset.panel import DatasetPanel
from XBrainLab.ui.styles.theme import Theme


@pytest.fixture
def mock_main_window(qtbot):
    # Use a real QMainWindow so QWidget parenting works
    window = QMainWindow()
    qtbot.addWidget(window)

    # Mock the study attribute and its methods
    study = MagicMock()
    study.loaded_data_list = []
    cast(Any, window).study = study

    # Add custom methods not in QMainWindow spec
    cast(Any, window).refresh_panels = MagicMock()

    yield window
    window.close()


@pytest.fixture
def mock_controller(mock_main_window):
    controller = MagicMock()
    controller.is_locked.return_value = False
    controller.has_data.return_value = False
    controller.get_loaded_data_list.return_value = []

    # Configure Study to return this controller
    cast(Any, mock_main_window).study.get_controller.return_value = controller
    return controller


def loaded_data_stub(filename: str, *, labels_imported: bool = False) -> MagicMock:
    data = MagicMock()
    data.configure_mock(
        **{
            "get_filepath.return_value": f"/path/{filename}",
            "get_filename.return_value": filename,
            "get_subject_name.return_value": "S01",
            "get_session_name.return_value": "session-01",
            "get_nchan.return_value": 4,
            "get_sfreq.return_value": 128.0,
            "get_epochs_length.return_value": 1,
            "has_event.return_value": True,
            "is_raw.return_value": True,
            "is_labels_imported.return_value": labels_imported,
            "get_event_list.return_value": ([1, 2, 3, 4], {"left": 1}),
            "get_filter_range.return_value": (0.0, 64.0),
            "get_tmin.return_value": 0.0,
            "get_epoch_duration.return_value": 1.0,
        }
    )
    return data


def dataset_publication(
    *,
    generation: int,
    raw: bool = False,
    preprocessed: bool = False,
    epoched: bool = False,
    datasets: bool = False,
):
    return SimpleNamespace(
        usable=True,
        generation=generation,
        effective_capabilities={},
        state=SimpleNamespace(
            active_dataset=SimpleNamespace(
                has_raw_data=raw,
                has_preprocessed_data=preprocessed,
                has_epoch_data=epoched,
                has_datasets=datasets,
            )
        ),
    )


def dataset_shell_with_assistant(
    qtbot,
    *,
    shell_width: int = 760,
    shell_height: int = 800,
) -> tuple[QMainWindow, DatasetPanel, QDockWidget]:
    window = QMainWindow()
    cast(Any, window).study = MagicMock()
    controller = MagicMock()
    controller.is_locked.return_value = False
    controller.has_data.return_value = False
    controller.get_loaded_data_list.return_value = []

    central_widget = QWidget(window)
    central_layout = QVBoxLayout(central_widget)
    central_layout.setContentsMargins(0, 0, 0, 0)
    central_layout.setSpacing(0)
    top_bar = QWidget(central_widget)
    top_bar.setObjectName("TopBar")
    top_bar.setFixedHeight(50)
    central_layout.addWidget(top_bar)
    panel = DatasetPanel(controller=controller, parent=window)
    central_layout.addWidget(panel)
    window.setCentralWidget(central_widget)
    status_bar = window.statusBar()
    assert status_bar is not None
    status_bar.showMessage("Dataset")
    assistant_dock = QDockWidget("XBrainLab Assistant", window)
    assistant_dock.setWidget(QWidget(assistant_dock))
    assistant_dock.setFixedWidth(320)
    window.addDockWidget(
        Qt.DockWidgetArea.RightDockWidgetArea,
        assistant_dock,
    )
    window.setFixedSize(shell_width, shell_height)
    qtbot.addWidget(window)
    window.show()
    window.resizeDocks([assistant_dock], [320], Qt.Orientation.Horizontal)
    qtbot.wait(10)
    return window, panel, assistant_dock


def assert_widget_fits_panel(widget: QWidget, panel: DatasetPanel) -> None:
    top_left = widget.mapTo(panel, widget.rect().topLeft())
    bottom_right = widget.mapTo(panel, widget.rect().bottomRight())
    assert top_left.x() >= panel.contentsRect().left()
    assert top_left.y() >= panel.contentsRect().top()
    assert bottom_right.x() <= panel.contentsRect().right()
    assert bottom_right.y() <= panel.contentsRect().bottom()


def assert_dataset_horizontal_scroll_is_absent(panel: DatasetPanel) -> None:
    scroll_areas = (
        panel.table,
        panel.sidebar.scroll_area,
        panel.sidebar.info_panel.table,
        panel.summary_info_panel.table,
    )
    for area in scroll_areas:
        scrollbar = area.horizontalScrollBar()
        assert scrollbar is not None
        assert scrollbar.maximum() == 0


def assert_widget_fits_scroll_viewport(widget: QWidget, scroll_area) -> None:
    viewport = scroll_area.viewport()
    top_left = widget.mapTo(viewport, widget.rect().topLeft())
    bottom_right = widget.mapTo(viewport, widget.rect().bottomRight())
    assert top_left.x() >= viewport.contentsRect().left()
    assert top_left.y() >= viewport.contentsRect().top()
    assert bottom_right.x() <= viewport.contentsRect().right()
    assert bottom_right.y() <= viewport.contentsRect().bottom()


def assert_info_cells_fit(info_panel) -> None:
    for row in range(info_panel.table.rowCount()):
        if info_panel.table.isRowHidden(row):
            continue
        for column in range(info_panel.table.columnCount()):
            item = info_panel.table.item(row, column)
            assert item is not None
            item_rect = info_panel.table.visualItemRect(item)
            text_width = info_panel.table.fontMetrics().horizontalAdvance(item.text())
            assert text_width + 16 <= item_rect.width(), (
                item.text(),
                text_width,
                item_rect.width(),
            )


def test_dataset_panel_empty_state_fits_760_shell_with_320_assistant_dock(
    qtbot,
):
    _window, panel, assistant_dock = dataset_shell_with_assistant(qtbot)

    assert assistant_dock.isVisible()
    assert assistant_dock.width() == 320
    assert panel.data_surface.currentWidget() is panel.empty_state
    tab_bar = panel.content_tabs.tabBar()
    assert tab_bar is not None
    assert not tab_bar.isVisibleTo(panel)
    assert not panel.content_tabs.isTabVisible(1)
    assert not panel.sidebar.info_panel.isVisibleTo(panel)
    assert_widget_fits_panel(panel.content_column, panel)
    assert_widget_fits_panel(panel.sidebar, panel)
    assert_widget_fits_panel(panel.empty_state_title, panel)
    assert (
        panel.empty_state_title.fontMetrics().horizontalAdvance(
            panel.empty_state_title.text()
        )
        <= panel.empty_state_title.contentsRect().width()
    )
    for button in (
        panel.sidebar.import_btn,
        panel.sidebar.import_folder_btn,
        panel.sidebar.import_bids_btn,
        panel.sidebar.reload_recipe_btn,
        panel.sidebar.chan_select_btn,
        panel.sidebar.clear_btn,
    ):
        assert button.isVisibleTo(panel)
        assert_widget_fits_panel(button, panel)
    assert_dataset_horizontal_scroll_is_absent(panel)


def test_dataset_panel_loaded_summary_fits_760_shell_with_320_assistant_dock(
    qtbot,
):
    _window, panel, assistant_dock = dataset_shell_with_assistant(qtbot)
    data = loaded_data_stub("sub-01_task-mi_run-01_eeg.fif")
    data.is_raw.return_value = False
    data.get_epochs_length.return_value = 120
    data.get_epoch_duration.return_value = 250
    data.get_sfreq.return_value = 250
    data.get_event_summary.return_value = {
        "available": True,
        "count": 120,
        "labels": ["left", "right"],
    }
    panel.sidebar.info_panel.update_info(preprocessed_data_list=[data])
    panel.summary_info_panel.update_info(preprocessed_data_list=[data])
    panel.content_tabs.setCurrentIndex(1)
    qtbot.wait(10)

    assert assistant_dock.isVisible()
    assert assistant_dock.width() == 320
    assert panel.summary_info_panel.isVisibleTo(panel)
    assert_widget_fits_panel(panel.content_column, panel)
    assert_widget_fits_panel(panel.sidebar, panel)
    assert_widget_fits_panel(panel.summary_info_panel, panel)
    assert_info_cells_fit(panel.summary_info_panel)
    assert_dataset_horizontal_scroll_is_absent(panel)


@pytest.mark.parametrize("shell_width", [760, 820, 1280])
@pytest.mark.parametrize("logical_scale", [1.0, 1.25, 1.5])
def test_dataset_panel_empty_and_loaded_summary_scale_matrix(
    qtbot,
    shell_width,
    logical_scale,
):
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    original_font = QFont(app.font())
    scaled_font = QFont(original_font)
    scaled_font.setPointSizeF(original_font.pointSizeF() * logical_scale)
    app.setFont(scaled_font)
    window = None
    try:
        window, panel, assistant_dock = dataset_shell_with_assistant(
            qtbot,
            shell_width=shell_width,
        )
        assert assistant_dock.width() == 320
        assert_widget_fits_panel(panel.content_column, panel)
        assert_widget_fits_panel(panel.sidebar, panel)
        assert_widget_fits_panel(panel.empty_state_title, panel)
        assert (
            panel.empty_state_title.fontMetrics().horizontalAdvance(
                panel.empty_state_title.text()
            )
            <= panel.empty_state_title.contentsRect().width()
        )

        data = loaded_data_stub("sub-01_task-mi_run-01_eeg.fif")
        data.is_raw.return_value = False
        data.get_epochs_length.return_value = 120
        data.get_epoch_duration.return_value = 250
        data.get_sfreq.return_value = 250
        data.get_event_summary.return_value = {
            "available": True,
            "count": 120,
            "labels": ["left", "right"],
        }
        panel.sidebar.info_panel.update_info(preprocessed_data_list=[data])
        panel.summary_info_panel.update_info(preprocessed_data_list=[data])
        panel.table.setRowCount(1)
        for column, text in enumerate(
            (
                data.get_filename(),
                data.get_subject_name(),
                data.get_session_name(),
                str(data.get_nchan()),
                str(data.get_sfreq()),
                str(data.get_epochs_length()),
                "120",
            )
        ):
            panel.table.setItem(0, column, QTableWidgetItem(text))
        panel.data_surface.setCurrentWidget(panel.table)
        with patch(
            "XBrainLab.ui.panels.dataset.panel.get_application_view_publication",
            return_value=dataset_publication(
                generation=2,
                raw=True,
                preprocessed=True,
            ),
        ):
            panel.show_post_import_next_action()
        qtbot.wait(10)
        tab_bar = panel.content_tabs.tabBar()
        assert tab_bar is not None
        if tab_bar.isVisibleTo(panel):
            panel.content_tabs.setCurrentIndex(1)
            active_info_panel = panel.summary_info_panel
        else:
            panel.content_tabs.setCurrentIndex(0)
            active_info_panel = panel.sidebar.info_panel
        qtbot.wait(10)

        assert active_info_panel.isVisibleTo(panel)
        assert_widget_fits_panel(active_info_panel, panel)
        assert_info_cells_fit(active_info_panel)
        assert panel.post_import_action_button.isVisibleTo(panel)
        assert_widget_fits_panel(panel.post_import_action_button, panel)
        assert (
            panel.post_import_action_button.fontMetrics().horizontalAdvance(
                panel.post_import_action_button.text()
            )
            + 24
            <= panel.post_import_action_button.contentsRect().width()
        )
        for button in (
            panel.sidebar.import_btn,
            panel.sidebar.import_folder_btn,
            panel.sidebar.import_bids_btn,
            panel.sidebar.reload_recipe_btn,
            panel.sidebar.chan_select_btn,
            panel.sidebar.clear_btn,
        ):
            assert button.isVisibleTo(panel)
            assert_widget_fits_panel(button, panel)
            assert_widget_fits_scroll_viewport(button, panel.sidebar.scroll_area)
            assert (
                button.fontMetrics().horizontalAdvance(button.text()) + 30
                <= button.contentsRect().width()
            )
        assert_dataset_horizontal_scroll_is_absent(panel)
    finally:
        if window is not None:
            window.close()
        app.setFont(original_font)
        app.processEvents()


def test_update_panel_uses_query_data_list_before_stale_controller(qtbot):
    study = Study()
    data = loaded_data_stub("sub-01_task-mi_raw.fif")
    study.loaded_data_list = [data]

    controller = MagicMock()
    controller.study = study
    controller.is_locked.return_value = False
    controller.get_loaded_data_list.side_effect = AssertionError(
        "stale loaded list should not be read",
    )

    real_window = QMainWindow()
    cast(Any, real_window).study = study
    panel = DatasetPanel(controller=controller, parent=real_window)
    qtbot.addWidget(real_window)
    qtbot.addWidget(panel)

    panel.update_panel()

    controller.get_loaded_data_list.assert_not_called()
    assert panel.table.rowCount() == 1
    file_item = panel.table.item(0, 0)
    assert file_item is not None
    assert file_item.text() == "sub-01_task-mi_raw.fif"
    real_window.close()


def test_update_panel_refuses_real_study_query_none_controller_fallback(qtbot):
    study = Study()
    study.loaded_data_list = [loaded_data_stub("sub-01_task-mi_raw.fif")]

    controller = MagicMock()
    controller.study = study
    controller.is_locked.return_value = False
    controller.get_loaded_data_list.side_effect = AssertionError(
        "stale loaded list should not be read",
    )

    real_window = QMainWindow()
    cast(Any, real_window).study = study
    panel = DatasetPanel(controller=controller, parent=real_window)
    qtbot.addWidget(real_window)
    qtbot.addWidget(panel)

    with patch(
        "XBrainLab.ui.panels.dataset.panel.execute_application_command",
        return_value=None,
    ):
        panel.update_panel()

    controller.get_loaded_data_list.assert_not_called()
    assert panel.table.rowCount() == 0
    real_window.close()


def test_deferred_runtime_uses_actionable_empty_state(qtbot):
    real_window = QMainWindow()
    cast(Any, real_window).study = Study()
    controller = MagicMock()
    controller.study = cast(Any, real_window).study
    panel = DatasetPanel(controller=controller, parent=real_window)
    qtbot.addWidget(real_window)
    qtbot.addWidget(panel)
    panel.table.setRowCount(1)
    panel.data_surface.setCurrentWidget(panel.table)
    panel.empty_state_title.setText("Stale dataset state")
    panel.empty_state_detail.setText("Stale detail")

    with patch(
        "XBrainLab.ui.panels.dataset.panel.is_application_runtime_deferred",
        return_value=True,
    ):
        panel.update_panel()

    assert panel.table.rowCount() == 0
    assert panel.data_surface.currentWidget() is panel.empty_state
    assert panel.empty_state_title.text() == "No EEG data loaded"
    assert (
        panel.empty_state_detail.text()
        == "Import a file, folder, or BIDS folder to begin."
    )
    real_window.close()


def test_dataset_panel_init_controller(mock_main_window, mock_controller, qtbot):
    """Test initialization creates controller."""
    # Create a REAL QMainWindow to serve as parent
    real_window = QMainWindow()
    # Attach the mock study from our fixture to this real window
    # Note: DatasetPanel accesses self.main_window.study if passed main_window
    # or parent().study if passed parent.
    # Let's verify standard pattern: usually parent() -> main_window

    cast(Any, real_window).study = cast(Any, mock_main_window).study

    panel = DatasetPanel(parent=real_window)
    qtbot.addWidget(panel)

    # Check if controller was instantiated and is our mock
    assert panel.controller is not None
    assert panel.controller == mock_controller

    # Clean up
    panel.close()
    real_window.close()


def test_dataset_panel_import_data_success(mock_main_window, mock_controller, qtbot):
    """Import without command service should not mutate the controller."""
    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)

    # Patch the name imported in the module
    with (
        patch(
            "XBrainLab.ui.panels.dataset.actions.QFileDialog.getOpenFileNames",
            return_value=(["/path/to/file.set"], "Filter"),
        ),
        patch(
            "XBrainLab.ui.panels.dataset.actions.QMessageBox.information",
        ) as mock_info,
        patch(
            "XBrainLab.ui.panels.dataset.actions.QMessageBox.warning",
        ) as mock_warning,
    ):
        panel.action_handler.import_data()
        mock_controller.import_files.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Interpretation Blocked"
        mock_info.assert_not_called()


def test_dataset_panel_clear_dataset(mock_main_window, mock_controller, qtbot):
    """Test clearing the dataset."""

    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)
    mock_controller.has_data.return_value = True
    mock_controller.is_epoched.return_value = True

    with (
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ),
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.QMessageBox.information"
        ) as mock_info,
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.QMessageBox.warning"
        ) as mock_warning,
    ):
        panel.sidebar.clear_dataset()
        mock_controller.clean_dataset.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Reset Session Blocked"
        mock_info.assert_not_called()


def test_dataset_panel_update_table(mock_main_window, mock_controller, qtbot):
    """Test table update from controller data."""
    mock_data = MagicMock()
    mock_data.configure_mock(
        **{
            "get_filepath.return_value": "/path/test.set",
            "get_filename.return_value": "test.set",
            "get_subject_name.return_value": "Sub01",
            "get_session_name.return_value": "Sess01",
            "get_nchan.return_value": 32,
            "get_sfreq.return_value": 250,
            "get_epochs_length.return_value": 100,
            "has_event.return_value": False,
            "is_raw.return_value": False,
            "is_labels_imported.return_value": False,
            "get_event_list.return_value": ([], {}),
            "get_filter_range.return_value": (0.1, 40.0),
            "get_tmin.return_value": 0.0,
            "get_epoch_duration.return_value": 1.0,
        }
    )

    mock_controller.get_loaded_data_list.return_value = [mock_data]

    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)

    panel.update_panel()

    assert panel.table.rowCount() == 1
    file_item = panel.table.item(0, 0)
    assert file_item is not None
    assert file_item.text() == "test.set"


def test_dataset_panel_uses_product_empty_state_instead_of_blank_table(
    mock_main_window,
    mock_controller,
    qtbot,
):
    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)
    panel.resize(980, 520)
    panel.show()

    panel.update_panel()
    qtbot.wait(0)

    assert panel.table.rowCount() == 0
    assert panel.empty_state.isVisibleTo(panel)
    assert not panel.table.isVisibleTo(panel)
    assert panel.empty_state_title.text() == "No EEG data loaded"
    assert "Import a file, folder, or BIDS folder" in panel.empty_state_detail.text()


def test_dataset_panel_restores_table_when_rows_are_available(
    mock_main_window,
    mock_controller,
    qtbot,
):
    mock_controller.get_loaded_data_list.return_value = [
        loaded_data_stub("sub-01_task-mi_raw.fif")
    ]
    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)
    panel.resize(980, 520)
    panel.show()

    panel.update_panel()
    qtbot.wait(0)

    assert panel.table.rowCount() == 1
    assert panel.table.isVisibleTo(panel)
    assert not panel.empty_state.isVisibleTo(panel)


def test_dataset_panel_table_columns_fill_available_width(
    mock_main_window,
    mock_controller,
    qtbot,
):
    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)
    panel.resize(1280, 480)
    panel.show()

    header = panel.table.horizontalHeader()
    viewport = panel.table.viewport()
    assert header is not None
    assert viewport is not None
    qtbot.waitUntil(
        lambda: (
            abs(header.length() - viewport.width()) <= 2
            and all(
                not panel.table.isColumnHidden(column)
                and panel.table.columnWidth(column) > DatasetPanel._TABLE_MIN_WIDTH
                for column in range(panel.table.columnCount())
            )
        ),
        timeout=1_000,
    )

    assert not header.stretchLastSection()
    for column in range(panel.table.columnCount()):
        assert header.sectionResizeMode(column) == QHeaderView.ResizeMode.Interactive
    assert abs(header.length() - viewport.width()) <= 2
    assert all(
        panel.table.columnWidth(column) > DatasetPanel._TABLE_MIN_WIDTH
        for column in range(panel.table.columnCount())
    )
    assert panel.table.textElideMode() == Qt.TextElideMode.ElideRight


def test_dataset_panel_table_columns_shrink_to_fill_narrow_panel(
    mock_main_window,
    mock_controller,
    qtbot,
):
    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)
    panel.resize(620, 420)
    panel.show()

    header = panel.table.horizontalHeader()
    viewport = panel.table.viewport()
    assert header is not None
    assert viewport is not None
    qtbot.waitUntil(
        lambda: (
            tuple(
                column
                for column in range(panel.table.columnCount())
                if not panel.table.isColumnHidden(column)
            )
            == DatasetPanel._COMPACT_COLUMNS
            and abs(header.length() - viewport.width()) <= 2
        ),
        timeout=1_000,
    )

    assert abs(header.length() - viewport.width()) <= 2
    assert (
        tuple(
            column
            for column in range(panel.table.columnCount())
            if not panel.table.isColumnHidden(column)
        )
        == DatasetPanel._COMPACT_COLUMNS
    )
    scrollbar = panel.table.horizontalScrollBar()
    assert scrollbar is not None
    assert scrollbar.maximum() == 0


def test_dataset_panel_refits_table_after_loaded_rows_settle(
    mock_main_window,
    mock_controller,
    qtbot,
):
    mock_controller.get_loaded_data_list.return_value = [
        loaded_data_stub("sub-01_task-mi_run-1_raw.fif"),
        loaded_data_stub("sub-01_task-mi_run-2_raw.fif", labels_imported=True),
    ]
    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)
    panel.resize(760, 420)
    panel.show()

    panel.update_panel()
    qtbot.wait(10)

    header = panel.table.horizontalHeader()
    viewport = panel.table.viewport()
    scrollbar = panel.table.horizontalScrollBar()
    assert header is not None
    assert viewport is not None
    assert scrollbar is not None
    assert abs(header.length() - viewport.width()) <= 2
    assert scrollbar.maximum() == 0


def test_dataset_panel_uses_compact_columns_when_assistant_reduces_width(
    mock_main_window,
    mock_controller,
    qtbot,
):
    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)
    panel.resize(425, 420)
    panel.show()

    header = panel.table.horizontalHeader()
    viewport = panel.table.viewport()
    scrollbar = panel.table.horizontalScrollBar()
    assert header is not None
    assert viewport is not None
    assert scrollbar is not None
    qtbot.waitUntil(
        lambda: (
            tuple(
                column
                for column in range(panel.table.columnCount())
                if not panel.table.isColumnHidden(column)
            )
            == DatasetPanel._COMPACT_COLUMNS
            and abs(header.length() - viewport.width()) <= 2
        ),
        timeout=1_000,
    )
    assert not panel.table.isColumnHidden(0)
    assert (
        tuple(
            column
            for column in range(panel.table.columnCount())
            if not panel.table.isColumnHidden(column)
        )
        == DatasetPanel._COMPACT_COLUMNS
    )
    assert abs(header.length() - viewport.width()) <= 2
    assert scrollbar.maximum() == 0


def test_dataset_panel_moves_data_summary_into_tab_at_narrow_width(
    mock_main_window,
    mock_controller,
    qtbot,
):
    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    mock_main_window.setCentralWidget(panel)
    mock_main_window.resize(620, 520)
    mock_main_window.show()
    qtbot.wait(10)

    data = loaded_data_stub("sub-01_task-mi_run-01_eeg.fif")
    data.get_event_summary.return_value = {
        "available": True,
        "count": 4,
        "labels": ["left"],
    }
    panel.sidebar.info_panel.update_info(loaded_data_list=[data])
    panel.summary_info_panel.update_info(loaded_data_list=[data])
    qtbot.wait(10)

    tab_bar = panel.content_tabs.tabBar()
    assert tab_bar is not None
    typed_tab_bar = tab_bar
    assert tab_bar.isVisibleTo(panel)
    assert panel.content_tabs.isTabVisible(1)
    assert panel.content_tabs.tabText(0) == "EEG Files"
    assert panel.content_tabs.tabText(1) == "Data Summary"
    assert not panel.sidebar.info_panel.isVisibleTo(panel)

    panel.content_tabs.setCurrentIndex(1)
    assert panel.summary_info_panel.isVisibleTo(panel)

    mock_main_window.resize(1100, 520)
    qtbot.waitUntil(lambda: not typed_tab_bar.isVisibleTo(panel), timeout=1000)

    tab_bar = panel.content_tabs.tabBar()
    assert tab_bar is not None
    assert not tab_bar.isVisibleTo(panel)
    assert panel.content_tabs.currentIndex() == 0
    assert panel.sidebar.info_panel.isVisibleTo(panel)


def test_dataset_summary_uses_one_vertical_scroll_owner_at_short_high_dpi_shell(
    qtbot,
):
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    original_font = QFont(app.font())
    scaled_font = QFont(original_font)
    scaled_font.setPointSizeF(original_font.pointSizeF() * 1.5)
    app.setFont(scaled_font)
    window = None
    try:
        window, panel, _assistant_dock = dataset_shell_with_assistant(
            qtbot,
            shell_width=760,
            shell_height=520,
        )
        data = loaded_data_stub("sub-01_task-mi_run-01_eeg.fif")
        data.is_raw.return_value = False
        data.get_epochs_length.return_value = 120
        data.get_epoch_duration.return_value = 250
        data.get_sfreq.return_value = 250
        data.get_event_summary.return_value = {
            "available": True,
            "count": 120,
            "labels": ["left", "right"],
        }

        panel.sidebar.info_panel.update_info(preprocessed_data_list=[data])
        panel.summary_info_panel.update_info(preprocessed_data_list=[data])
        qtbot.wait(10)
        panel.content_tabs.setCurrentIndex(1)
        qtbot.wait(10)

        summary_vertical = panel.summary_page.verticalScrollBar()
        summary_horizontal = panel.summary_page.horizontalScrollBar()
        table_vertical = panel.summary_info_panel.table.verticalScrollBar()
        table_horizontal = panel.summary_info_panel.table.horizontalScrollBar()
        assert summary_vertical is not None
        assert summary_horizontal is not None
        assert table_vertical is not None
        assert table_horizontal is not None
        assert summary_vertical.maximum() > 0
        assert summary_horizontal.maximum() == 0
        assert table_vertical.maximum() == 0
        assert table_horizontal.maximum() == 0
        assert panel.summary_info_panel.isVisibleTo(panel)
        assert_info_cells_fit(panel.summary_info_panel)
    finally:
        if window is not None:
            window.close()
        app.setFont(original_font)


def test_dataset_panel_post_import_action_uses_one_contextual_destination(
    mock_main_window,
    mock_controller,
    qtbot,
):
    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)
    cast(Any, mock_main_window).switch_page = MagicMock(return_value=True)
    publication = SimpleNamespace(
        usable=True,
        state=SimpleNamespace(
            active_dataset=SimpleNamespace(
                has_raw_data=True,
                has_preprocessed_data=False,
                has_epoch_data=False,
                has_datasets=False,
            )
        ),
    )

    with patch(
        "XBrainLab.ui.panels.dataset.panel.get_application_view_publication",
        return_value=publication,
    ):
        panel.show_post_import_next_action()

    assert not panel.post_import_action_bar.isHidden()
    assert panel.post_import_action_button.text() == "Continue to Preprocess"
    assert len(panel.post_import_action_bar.findChildren(QPushButton)) == 1

    panel.post_import_action_button.click()

    cast(Any, mock_main_window).switch_page.assert_called_once_with(1)
    assert panel.post_import_action_bar.isHidden()


def test_dataset_panel_post_import_action_reflows_in_narrow_content(
    mock_main_window,
    mock_controller,
    qtbot,
):
    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)
    publication = dataset_publication(generation=2, raw=True)

    with patch(
        "XBrainLab.ui.panels.dataset.panel.get_application_view_publication",
        return_value=publication,
    ):
        panel.show_post_import_next_action()

    panel.resize(620, 520)
    panel.show()
    qtbot.wait(0)

    assert panel.post_import_action_button.text() == "Continue to Preprocess"
    assert panel.post_import_action_label.wordWrap()
    assert (
        panel.post_import_action_button.geometry().top()
        > panel.post_import_action_label.geometry().bottom()
    )
    assert (
        panel.post_import_action_button.geometry().right()
        <= panel.post_import_action_bar.contentsRect().right()
    )
    assert (
        panel.post_import_action_button.geometry().bottom()
        <= panel.post_import_action_bar.contentsRect().bottom()
    )


def test_dataset_panel_post_import_action_tracks_refresh_and_reset_publication(
    mock_main_window,
    mock_controller,
    qtbot,
):
    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)
    raw = dataset_publication(generation=2, raw=True)
    preprocessed = dataset_publication(generation=3, raw=True, preprocessed=True)
    reset = dataset_publication(generation=4)

    with (
        patch(
            "XBrainLab.ui.panels.dataset.panel.get_application_view_publication",
            side_effect=[raw, preprocessed, reset],
        ),
        patch(
            "XBrainLab.ui.panels.dataset.panel.is_application_runtime_deferred",
            return_value=False,
        ),
    ):
        panel.show_post_import_next_action()
        assert panel.post_import_action_button.text() == "Continue to Preprocess"

        panel.update_panel()
        assert panel.post_import_action_button.text() == "Create EEG epochs"
        assert not panel.post_import_action_bar.isHidden()

        panel.update_panel()

    assert panel.post_import_action_bar.isHidden()
    assert panel._post_import_target_index is None


def test_dataset_panel_apply_loader_refuses_real_study(
    qtbot,
    monkeypatch,
):
    window = QMainWindow()
    qtbot.addWidget(window)
    cast(Any, window).study = Study()
    warnings: list[tuple[Any, ...]] = []
    infos: list[tuple[Any, ...]] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args: infos.append(args),
    )
    panel = DatasetPanel(parent=window)
    qtbot.addWidget(panel)
    loader = MagicMock()

    panel.apply_loader(loader)

    loader.apply.assert_not_called()
    assert infos == []
    assert warnings
    assert warnings[0][1] == "Import EEG Data"
    assert "guided import workflow" in warnings[0][2]


def test_dataset_panel_events_column_uses_semantic_text_and_muted_color(
    mock_main_window,
    mock_controller,
    qtbot,
):
    internal_events = MagicMock()
    internal_events.configure_mock(
        **{
            "get_filename.return_value": "internal_events.set",
            "get_subject_name.return_value": "Sub01",
            "get_session_name.return_value": "Sess01",
            "get_nchan.return_value": 32,
            "get_sfreq.return_value": 250,
            "get_epochs_length.return_value": 0,
            "has_event.return_value": True,
            "is_raw.return_value": True,
            "is_labels_imported.return_value": False,
            "get_event_list.return_value": ([1, 2, 3], {}),
        }
    )
    imported_labels = MagicMock()
    imported_labels.configure_mock(
        **{
            "get_filename.return_value": "imported_labels.set",
            "get_subject_name.return_value": "Sub02",
            "get_session_name.return_value": "Sess02",
            "get_nchan.return_value": 32,
            "get_sfreq.return_value": 250,
            "get_epochs_length.return_value": 0,
            "has_event.return_value": True,
            "is_raw.return_value": True,
            "is_labels_imported.return_value": True,
            "get_event_list.return_value": ([1, 2], {}),
        }
    )
    mock_controller.get_loaded_data_list.return_value = [
        internal_events,
        imported_labels,
    ]

    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)
    panel.update_panel()

    internal_item = panel.table.item(0, 6)
    imported_item = panel.table.item(1, 6)
    assert internal_item is not None
    assert imported_item is not None

    assert internal_item.text() == "Events (3)"
    assert internal_item.toolTip() == "Events detected in the recording."
    assert imported_item.text() == "Labels (2)"
    assert imported_item.toolTip() == "External labels are attached to this recording."
    assert internal_item.foreground().color().name().lower() not in {
        Theme.ACCENT_SUCCESS.lower(),
        "#50fa7b",
    }
    assert imported_item.foreground().color().name().lower() == (
        Theme.TEXT_MUTED.lower()
    )


def test_update_panel_uses_cached_event_summary_without_scanning(
    mock_main_window,
    mock_controller,
    qtbot,
):
    data = loaded_data_stub("cached_events.set")
    data.get_event_summary.return_value = {
        "available": True,
        "count": 5,
        "labels": ["left", "right"],
        "source": "detected_events",
        "scanned": True,
    }
    data.get_event_list.side_effect = AssertionError(
        "dataset table should not scan raw events during render"
    )
    data.has_event.side_effect = AssertionError(
        "dataset table should use cached event summary first"
    )
    mock_controller.get_loaded_data_list.return_value = [data]

    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)
    panel.update_panel()

    event_item = panel.table.item(0, 6)
    assert event_item is not None
    assert event_item.text() == "Events (5)"


def test_dataset_panel_on_item_changed(mock_main_window, mock_controller, qtbot):
    """Test editing subject/session in table updates metadata via controller."""
    mock_data = MagicMock()
    mock_data.configure_mock(
        **{
            "get_filepath.return_value": "/path/test.set",
            "get_filename.return_value": "test.set",
            "get_subject_name.return_value": "Sub01",
            "get_session_name.return_value": "Sess01",
            "get_event_list.return_value": ([], {}),
            "get_epochs_length.return_value": 0,
            "get_nchan.return_value": 0,
            "get_sfreq.return_value": 100,
            "get_tmin.return_value": 0,
            "get_epoch_duration.return_value": 0,
            "is_raw.return_value": True,
            "get_filter_range.return_value": (0, 0),
        }
    )
    # Needed for _populate_table in update_panel
    mock_data.get_subject_name.return_value = "Sub01"

    mock_controller.get_loaded_data_list.return_value = [mock_data]

    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)
    panel.update_panel()

    # Mock update_panel to avoid clearing the table (which deletes the item
    # triggering the signal)
    with (
        patch.object(panel, "update_panel"),
        patch("XBrainLab.ui.panels.dataset.panel.QMessageBox.warning") as mock_warning,
    ):
        # Simulate editing Subject (Column 1)
        item = panel.table.item(0, 1)  # Subject
        assert item is not None
        item.setText("NewSub")

        mock_controller.update_metadata.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Metadata blocked"


def test_dataset_panel_metadata_service_success_uses_coordinator_refresh(
    mock_main_window,
    mock_controller,
    qtbot,
):
    """Service-backed inline metadata edits should not refresh locally."""
    from XBrainLab.backend.application import UpdateMetadataCommand

    mock_data = MagicMock()
    mock_controller.get_loaded_data_list.return_value = [mock_data]
    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)
    panel.table.blockSignals(True)
    panel.table.setRowCount(1)
    panel.table.setColumnCount(7)
    name_item = QTableWidgetItem("file.set")
    name_item.setData(Qt.ItemDataRole.UserRole, True)
    panel.table.setItem(0, 0, name_item)
    subject_item = QTableWidgetItem("S02")
    panel.table.setItem(0, 1, subject_item)
    panel.table.blockSignals(False)

    with (
        patch.object(panel, "update_panel") as mock_update,
        patch(
            "XBrainLab.ui.panels.dataset.panel.execute_application_command",
            return_value=MagicMock(failed=False),
        ) as mock_execute,
    ):
        panel.on_item_changed(subject_item)

    command = mock_execute.call_args.args[1]
    assert isinstance(command, UpdateMetadataCommand)
    assert command.subject == "S02"
    mock_controller.update_metadata.assert_not_called()
    mock_update.assert_not_called()


def test_dataset_panel_metadata_edit_refuses_real_study_controller_fallback(qtbot):
    """Inline metadata edits should block instead of falling back in real Study."""

    window = QMainWindow()
    qtbot.addWidget(window)
    study = Study()
    cast(Any, window).study = study
    controller = MagicMock()

    panel = DatasetPanel(controller=controller, parent=window)
    qtbot.addWidget(panel)
    panel.table.blockSignals(True)
    panel.table.setRowCount(1)
    panel.table.setColumnCount(7)
    name_item = QTableWidgetItem("file.set")
    name_item.setData(Qt.ItemDataRole.UserRole, True)
    panel.table.setItem(0, 0, name_item)
    subject_item = QTableWidgetItem("S02")
    panel.table.setItem(0, 1, subject_item)
    panel.table.blockSignals(False)

    with (
        patch.object(panel, "update_panel") as mock_update,
        patch(
            "XBrainLab.ui.panels.dataset.panel.get_command_capability",
            return_value=None,
        ),
        patch(
            "XBrainLab.ui.panels.dataset.panel.execute_application_command",
            return_value=None,
        ),
        patch.object(QMessageBox, "warning") as mock_warning,
    ):
        panel.on_item_changed(subject_item)

    controller.update_metadata.assert_not_called()
    mock_warning.assert_called_once()
    assert mock_warning.call_args.args[1] == "Refresh Dataset and Edit Again"
    assert "Refresh the Dataset table" in mock_warning.call_args.args[2]
    mock_update.assert_called_once()


def test_dataset_panel_metadata_cells_use_backend_update_capability(qtbot):
    """Locked real Study paths should show metadata as read-only."""
    from XBrainLab.backend.study import Study

    window = QMainWindow()
    qtbot.addWidget(window)
    study = Study()
    cast(Any, window).study = study
    mock_data = MagicMock()
    mock_data.configure_mock(
        **{
            "get_filepath.return_value": "/path/test.set",
            "get_filename.return_value": "test.set",
            "get_subject_name.return_value": "Sub01",
            "get_session_name.return_value": "Sess01",
            "get_event_list.return_value": ([], {}),
            "get_epochs_length.return_value": 0,
            "get_nchan.return_value": 0,
            "get_sfreq.return_value": 100,
            "is_raw.return_value": True,
            "has_event.return_value": False,
            "is_labels_imported.return_value": False,
        },
    )
    study.loaded_data_list = [mock_data]
    study.epoch_data = MagicMock()
    controller = MagicMock()
    controller.get_loaded_data_list.return_value = [mock_data]

    panel = DatasetPanel(controller=controller, parent=window)
    qtbot.addWidget(panel)
    panel.update_panel()

    subject_item = panel.table.item(0, 1)
    session_item = panel.table.item(0, 2)

    assert subject_item is not None
    assert session_item is not None
    assert not subject_item.flags() & Qt.ItemFlag.ItemIsEditable
    assert not session_item.flags() & Qt.ItemFlag.ItemIsEditable
    assert "Reset the session before changing raw files" in subject_item.toolTip()
    assert subject_item.toolTip() == session_item.toolTip()


def test_dataset_panel_smart_parse(mock_main_window, mock_controller, qtbot):
    """Test smart parser delegates to controller."""
    mock_controller.has_data.return_value = True
    mock_controller.get_filenames.return_value = ["/path/file.set"]

    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)

    with patch("XBrainLab.ui.panels.dataset.actions.SmartParserDialog") as MockDialog:
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_result.return_value = {"/path/file.set": ("sub", "ses")}

        mock_controller.apply_smart_parse.return_value = 1

        with patch("XBrainLab.ui.panels.dataset.actions.QMessageBox") as mock_mb:
            panel.action_handler.open_smart_parser()
            mock_controller.apply_smart_parse.assert_not_called()
            mock_mb.warning.assert_called_once()
            assert mock_mb.warning.call_args.args[1] == "Smart Parse Blocked"
