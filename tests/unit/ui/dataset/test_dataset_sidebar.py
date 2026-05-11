from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QMessageBox, QPushButton, QWidget

from XBrainLab.ui.panels.dataset.sidebar import DatasetSidebar
from XBrainLab.ui.styles.stylesheets import Stylesheets


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
    assert isinstance(sidebar.import_btn, QPushButton)
    assert isinstance(sidebar.import_folder_btn, QPushButton)
    assert isinstance(sidebar.reload_recipe_btn, QPushButton)
    assert isinstance(sidebar.import_label_btn, QPushButton)
    assert isinstance(sidebar.smart_parse_btn, QPushButton)
    assert isinstance(sidebar.chan_select_btn, QPushButton)
    assert isinstance(sidebar.clear_btn, QPushButton)


def test_channel_selection_uses_neutral_action_style(sidebar):
    assert sidebar.chan_select_btn.styleSheet() == Stylesheets.SIDEBAR_BTN
    assert sidebar.chan_select_btn.styleSheet() != Stylesheets.BTN_SUCCESS


def test_update_sidebar_locked(sidebar):
    # Case: Locked (processing downstream)
    sidebar.controller.is_locked.return_value = True
    sidebar.update_sidebar()

    # Logic: Button remains enabled but action is blocked. Tooltip updates.
    assert sidebar.chan_select_btn.isEnabled() is True
    assert "Dataset is locked" in sidebar.chan_select_btn.toolTip()
    assert sidebar.import_label_btn.isEnabled() is False
    assert "locked" in sidebar.import_label_btn.toolTip().lower()


def test_update_sidebar_unlocked(sidebar):
    # Case: Unlocked
    sidebar.controller.is_locked.return_value = False
    sidebar.controller.has_data.return_value = True

    sidebar.update_sidebar()

    assert sidebar.chan_select_btn.isEnabled() is True
    assert sidebar.chan_select_btn.toolTip() == "Select specific channels to keep"
    assert sidebar.import_label_btn.isEnabled() is True
    assert "recipe trace" in sidebar.import_label_btn.toolTip()


def test_update_sidebar_without_data_guides_to_interpret_source(sidebar):
    sidebar.controller.is_locked.return_value = False
    sidebar.controller.has_data.return_value = False

    sidebar.update_sidebar()

    assert sidebar.import_label_btn.isEnabled() is False
    assert "Interpret a data source" in sidebar.import_label_btn.toolTip()


def test_update_sidebar_disables_clear_dataset_for_empty_backend_state(qtbot):
    from XBrainLab.backend.study import Study

    panel_mock = MagicMock()
    panel_mock.action_handler = MagicMock()
    panel_mock.controller = MagicMock()
    panel_mock.main_window = QWidget()
    panel_mock.main_window.study = Study()

    widget = DatasetSidebar(panel_mock, parent=None)
    qtbot.addWidget(widget)

    widget.update_sidebar()

    assert widget.clear_btn.isEnabled() is False
    assert "No dataset to clear" in widget.clear_btn.toolTip()


def test_update_sidebar_refuses_real_study_clear_availability_fallback(qtbot):
    from XBrainLab.backend.study import Study

    panel_mock = MagicMock()
    panel_mock.action_handler = MagicMock()
    panel_mock.controller = MagicMock()
    panel_mock.controller.has_data.side_effect = AssertionError(
        "stale controller state should not decide clear availability",
    )
    panel_mock.main_window = QWidget()
    panel_mock.main_window.study = Study()

    widget = DatasetSidebar(panel_mock, parent=None)
    qtbot.addWidget(widget)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "XBrainLab.ui.panels.dataset.sidebar.execute_application_command",
            lambda *_, **__: None,
        )
        widget.update_sidebar()

    panel_mock.controller.has_data.assert_not_called()
    assert widget.clear_btn.isEnabled() is False
    assert "state is unavailable" in widget.clear_btn.toolTip()


def test_update_sidebar_refuses_real_study_no_capability_lock_data_fallback(qtbot):
    from types import SimpleNamespace

    from XBrainLab.backend.application import QueryStateCommand
    from XBrainLab.backend.study import Study

    panel_mock = MagicMock()
    panel_mock.action_handler = MagicMock()
    panel_mock.controller = MagicMock()
    panel_mock.controller.is_locked.side_effect = AssertionError(
        "stale lock state should not be read",
    )
    panel_mock.controller.has_data.side_effect = AssertionError(
        "stale loaded-data state should not be read",
    )
    panel_mock.main_window = QWidget()
    panel_mock.main_window.study = Study()

    widget = DatasetSidebar(panel_mock, parent=None)
    qtbot.addWidget(widget)

    def execute_for(_, command, refresh=True):
        if isinstance(command, QueryStateCommand):
            return SimpleNamespace(failed=False, diagnostics={"state": {}})
        return None

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "XBrainLab.ui.panels.dataset.sidebar.get_command_capability",
            lambda *_: None,
        )
        monkeypatch.setattr(
            "XBrainLab.ui.panels.dataset.sidebar.execute_application_command",
            execute_for,
        )
        widget.update_sidebar()

    panel_mock.controller.is_locked.assert_not_called()
    panel_mock.controller.has_data.assert_not_called()
    assert widget.import_btn.isEnabled() is False
    assert "unavailable" in widget.import_btn.toolTip()
    assert widget.import_label_btn.isEnabled() is False
    assert "unavailable" in widget.import_label_btn.toolTip()


def test_open_channel_selection_refuses_real_study_preflight_fallback(qtbot):
    from XBrainLab.backend.study import Study

    panel_mock = MagicMock()
    panel_mock.action_handler = MagicMock()
    panel_mock.controller = MagicMock()
    panel_mock.controller.has_data.side_effect = AssertionError(
        "stale loaded-data state should not be read",
    )
    panel_mock.controller.is_locked.side_effect = AssertionError(
        "stale lock state should not be read",
    )
    panel_mock.main_window = QWidget()
    panel_mock.main_window.study = Study()

    widget = DatasetSidebar(panel_mock, parent=None)
    qtbot.addWidget(widget)

    warning_calls = []
    with (
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.get_command_capability",
            return_value=None,
        ),
        patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *args: warning_calls.append(args),
        ),
    ):
        widget.open_channel_selection()

    panel_mock.controller.has_data.assert_not_called()
    panel_mock.controller.is_locked.assert_not_called()
    assert len(warning_calls) == 1
    assert warning_calls[0][1] == "Channel Selection Blocked"
    assert "could not safely complete" in warning_calls[0][2]


def test_button_connections(sidebar):
    # Verify connections call action handler
    sidebar.import_btn.click()
    sidebar.panel.action_handler.import_data.assert_called_once()

    sidebar.import_folder_btn.click()
    sidebar.panel.action_handler.import_folder_source.assert_called_once()

    sidebar.reload_recipe_btn.click()
    sidebar.panel.action_handler.reload_interpretation_recipe.assert_called_once()

    sidebar.smart_parse_btn.click()
    sidebar.panel.action_handler.open_smart_parser.assert_called_once()
