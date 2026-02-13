from unittest.mock import MagicMock

import pytest

from XBrainLab.ui.panels.dataset.sidebar import DatasetSidebar


@pytest.fixture
def sidebar(qtbot):
    panel_mock = MagicMock()
    # Mock action handler on panel
    panel_mock.action_handler = MagicMock()
    # Mock controller on panel
    panel_mock.controller = MagicMock()
    # Mock main_window
    panel_mock.main_window = None

    widget = DatasetSidebar(panel_mock, parent=None)
    qtbot.addWidget(widget)
    return widget


def test_init_ui(sidebar):
    assert sidebar.import_btn is not None
    assert sidebar.import_label_btn is not None
    assert sidebar.smart_parse_btn is not None
    assert sidebar.chan_select_btn is not None
    assert sidebar.clear_btn is not None


def test_update_sidebar_locked(sidebar):
    # Case: Locked (processing downstream)
    sidebar.controller.is_locked.return_value = True
    sidebar.update_sidebar()

    # Logic: Button remains enabled but action is blocked. Tooltip updates.
    assert sidebar.chan_select_btn.isEnabled() is True
    assert "Dataset is locked" in sidebar.chan_select_btn.toolTip()


def test_update_sidebar_unlocked(sidebar):
    # Case: Unlocked
    sidebar.controller.is_locked.return_value = False
    sidebar.controller.has_data.return_value = True

    sidebar.update_sidebar()

    assert sidebar.chan_select_btn.isEnabled() is True
    assert sidebar.chan_select_btn.toolTip() == "Select specific channels to keep"


def test_button_connections(sidebar):
    # Verify connections call action handler
    sidebar.import_btn.click()
    sidebar.panel.action_handler.import_data.assert_called_once()

    sidebar.smart_parse_btn.click()
    sidebar.panel.action_handler.open_smart_parser.assert_called_once()
