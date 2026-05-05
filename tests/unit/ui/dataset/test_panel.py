from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHeaderView, QMainWindow, QMessageBox, QTableWidgetItem

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
    """Test successful data import delegates to controller."""
    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)

    # Patch the name imported in the module
    with patch(
        "XBrainLab.ui.panels.dataset.actions.QFileDialog.getOpenFileNames",
        return_value=(["/path/to/file.set"], "Filter"),
    ):
        # Controller returns success
        mock_controller.import_files.return_value = (1, [])

        with patch(
            "XBrainLab.ui.panels.dataset.actions.QMessageBox.information"
        ) as mock_info:
            panel.action_handler.import_data()
            mock_controller.import_files.assert_called_once_with(["/path/to/file.set"])
            # No success message provided for clean import
            mock_info.assert_not_called()


def test_dataset_panel_clear_dataset(mock_main_window, mock_controller, qtbot):
    """Test clearing the dataset."""

    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)

    with (
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ),
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.QMessageBox.information"
        ) as mock_info,
    ):
        panel.sidebar.clear_dataset()
        mock_controller.clean_dataset.assert_called_once()
        mock_info.assert_called_once()


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


def test_dataset_panel_table_columns_fill_available_width(
    mock_main_window,
    mock_controller,
    qtbot,
):
    panel = DatasetPanel(controller=mock_controller, parent=mock_main_window)
    qtbot.addWidget(panel)
    panel.resize(1280, 480)
    panel.show()
    qtbot.wait(0)
    panel._fit_table_columns_to_viewport()

    header = panel.table.horizontalHeader()
    viewport = panel.table.viewport()
    assert header is not None
    assert viewport is not None

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
    qtbot.wait(0)
    panel._fit_table_columns_to_viewport()

    header = panel.table.horizontalHeader()
    viewport = panel.table.viewport()
    assert header is not None
    assert viewport is not None

    assert abs(header.length() - viewport.width()) <= 2
    assert (
        max(panel.table.columnWidth(column) for column in range(7))
        < (DatasetPanel._TABLE_BASE_WIDTHS[0])
    )


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
    assert warnings[0][1] == "Interpret Data Source"
    assert "Data Interpretation workflow" in warnings[0][2]


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
    with patch.object(panel, "update_panel"):
        # Simulate editing Subject (Column 1)
        item = panel.table.item(0, 1)  # Subject
        assert item is not None
        item.setText("NewSub")

        # Verify controller called
        mock_controller.update_metadata.assert_called()


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

        with patch("XBrainLab.ui.panels.dataset.actions.QMessageBox.information"):
            panel.action_handler.open_smart_parser()
            mock_controller.apply_smart_parse.assert_called_with(
                {"/path/file.set": ("sub", "ses")}
            )
