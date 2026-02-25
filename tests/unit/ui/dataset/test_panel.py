from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QMainWindow, QMessageBox

from XBrainLab.ui.panels.dataset.panel import DatasetPanel


@pytest.fixture
def mock_main_window(qtbot):
    # Use a real QMainWindow so QWidget parenting works
    window = QMainWindow()
    qtbot.addWidget(window)

    # Mock the study attribute and its methods
    window.study = MagicMock()
    window.study.loaded_data_list = []

    # Add custom methods not in QMainWindow spec
    window.refresh_panels = MagicMock()

    yield window
    window.close()


@pytest.fixture
def mock_controller(mock_main_window):
    controller = MagicMock()
    controller.is_locked.return_value = False
    controller.has_data.return_value = False
    controller.get_loaded_data_list.return_value = []

    # Configure Study to return this controller
    mock_main_window.study.get_controller.return_value = controller
    return controller


def test_dataset_panel_init_controller(mock_main_window, mock_controller, qtbot):
    """Test initialization creates controller."""
    # Create a REAL QMainWindow to serve as parent
    real_window = QMainWindow()
    # Attach the mock study from our fixture to this real window
    # Note: DatasetPanel accesses self.main_window.study if passed main_window
    # or parent().study if passed parent.
    # Let's verify standard pattern: usually parent() -> main_window

    real_window.study = mock_main_window.study

    panel = DatasetPanel(parent=real_window)
    qtbot.addWidget(panel)

    # Check if controller was instantiated and is our mock
    assert hasattr(panel, "controller")
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
    assert panel.table.item(0, 0).text() == "test.set"


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
        item.setText("NewSub")

        # Verify controller called
        mock_controller.update_metadata.assert_called()


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
