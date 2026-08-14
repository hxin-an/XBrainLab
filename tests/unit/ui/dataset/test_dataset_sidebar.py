from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QMessageBox, QPushButton, QWidget

from XBrainLab.ui.panels.dataset.sidebar import DatasetSidebar
from XBrainLab.ui.styles.stylesheets import Stylesheets


class FakeDatasetActionHandler:
    def import_data(self) -> None:
        pass

    def import_folder_source(self) -> None:
        pass

    def import_bids_source(self) -> None:
        pass

    def reload_interpretation_recipe(self) -> None:
        pass

    def open_smart_parser(self) -> None:
        pass

    def import_label(self) -> None:
        pass


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
    assert isinstance(sidebar.import_bids_btn, QPushButton)
    assert isinstance(sidebar.reload_recipe_btn, QPushButton)
    assert isinstance(sidebar.import_label_btn, QPushButton)
    assert isinstance(sidebar.smart_parse_btn, QPushButton)
    assert isinstance(sidebar.chan_select_btn, QPushButton)
    assert not hasattr(sidebar, "clear_btn")
    assert not sidebar.findChildren(QPushButton, "ResetSessionButton")
    assert all(
        button.text() != "Reset Session" for button in sidebar.findChildren(QPushButton)
    )


def test_add_labels_compatibility_button_stays_hidden(sidebar):
    assert sidebar.import_label_btn.isHidden() is True
    assert sidebar.import_label_btn.text() == "Add labels"
    assert sidebar.smart_parse_btn.isHidden()


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


def test_update_sidebar_reads_one_atomic_capability_publication(qtbot):
    from XBrainLab.backend.application import get_application_service
    from XBrainLab.backend.study import Study

    panel = MagicMock()
    panel.action_handler = MagicMock()
    panel.controller = MagicMock()
    panel.main_window = QWidget()
    panel.main_window.study = Study()
    publication = get_application_service(
        panel.main_window.study,
    ).get_view_publication()

    class Runtime:
        def __init__(self) -> None:
            self.publication_reads = 0

        def get_view_publication(self):
            self.publication_reads += 1
            return publication

    runtime = Runtime()
    widget = DatasetSidebar(panel, parent=None)
    qtbot.addWidget(widget)

    with patch(
        "XBrainLab.ui.application_capabilities.application_ui_runtime",
        return_value=runtime,
    ):
        widget.update_sidebar()

    assert runtime.publication_reads == 1


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
            "XBrainLab.ui.panels.dataset.sidebar.get_application_view_publication",
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


def test_update_sidebar_real_study_missing_publication_skips_compatibility_state(
    qtbot,
):
    from XBrainLab.backend.study import Study

    panel = MagicMock()
    panel.action_handler = MagicMock()
    panel.controller = MagicMock()
    panel.main_window = QWidget()
    panel.main_window.study = Study()
    widget = DatasetSidebar(panel, parent=None)
    qtbot.addWidget(widget)

    with (
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.get_application_view_publication",
            return_value=None,
        ),
        patch.object(
            widget,
            "_compatibility_sidebar_state",
            side_effect=AssertionError(
                "real product state must not consult controller compatibility"
            ),
        ) as compatibility_state,
        patch.object(
            widget,
            "_compatibility_controller_value",
            side_effect=AssertionError(
                "real product reset state must not consult controller compatibility"
            ),
        ) as compatibility_value,
    ):
        widget.update_sidebar()

    compatibility_state.assert_not_called()
    compatibility_value.assert_not_called()
    expected = {
        widget.import_btn: "Data interpretation availability is unavailable right now.",
        widget.import_folder_btn: (
            "Data interpretation availability is unavailable right now."
        ),
        widget.import_bids_btn: (
            "Data interpretation availability is unavailable right now."
        ),
        widget.reload_recipe_btn: (
            "Recipe reload availability is unavailable right now."
        ),
        widget.chan_select_btn: (
            "Channel selection availability is unavailable right now."
        ),
        widget.smart_parse_btn: "Smart parse availability is unavailable right now.",
        widget.import_label_btn: (
            "Label import availability is unavailable right now."
        ),
    }
    for button, tooltip in expected.items():
        assert button.isEnabled() is False
        assert button.toolTip() == tooltip


def test_deferred_startup_real_study_missing_publication_fails_closed(qtbot):
    from XBrainLab.backend.study import Study

    panel = MagicMock()
    panel.action_handler = MagicMock()
    panel.controller = MagicMock()
    panel.main_window = QWidget()
    panel.main_window.study = Study()
    widget = DatasetSidebar(panel, parent=None)
    qtbot.addWidget(widget)

    with patch.object(widget, "_uses_startup_bootstrap_state", return_value=True):
        widget.update_sidebar()

    expected = {
        widget.import_btn: "Data interpretation availability is unavailable right now.",
        widget.import_folder_btn: (
            "Data interpretation availability is unavailable right now."
        ),
        widget.import_bids_btn: (
            "Data interpretation availability is unavailable right now."
        ),
        widget.reload_recipe_btn: (
            "Recipe reload availability is unavailable right now."
        ),
        widget.chan_select_btn: (
            "Channel selection availability is unavailable right now."
        ),
        widget.smart_parse_btn: "Smart parse availability is unavailable right now.",
        widget.import_label_btn: (
            "Label import availability is unavailable right now."
        ),
    }
    for button, tooltip in expected.items():
        assert button.isEnabled() is False
        assert button.toolTip() == tooltip


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
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.get_application_view_publication",
            return_value=None,
        ),
        patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *args: warning_calls.append(args),
        ),
        patch.object(
            widget,
            "_compatibility_controller_value",
            side_effect=AssertionError(
                "real product actions must not consult controller compatibility"
            ),
        ) as compatibility_value,
    ):
        widget.open_channel_selection()

    compatibility_value.assert_not_called()
    panel_mock.controller.has_data.assert_not_called()
    panel_mock.controller.is_locked.assert_not_called()
    assert len(warning_calls) == 1
    assert warning_calls[0][1] == "Channel Selection Blocked"
    assert warning_calls[0][2] == (
        "Channel selection availability is unavailable right now."
    )


def test_channel_selection_binds_reviewed_publication_and_skips_stale_success(
    qtbot,
):
    from XBrainLab.backend.application import (
        ChangedState,
        CommandName,
        CommandResult,
        ErrorType,
        PreprocessCommand,
        QueryStateCommand,
        get_application_service,
    )
    from XBrainLab.backend.study import Study

    study = Study()
    raw = MagicMock()
    raw.get_filename.return_value = "sub-01_task-mi_raw.fif"
    study.data_manager.loaded_data_list = [raw]
    panel = MagicMock()
    panel.action_handler = MagicMock()
    panel.controller = MagicMock()
    panel.main_window = QWidget()
    panel.main_window.study = study
    widget = DatasetSidebar(panel, parent=None)
    qtbot.addWidget(widget)
    publication = get_application_service(study).get_view_publication()
    stale_result = CommandResult.failure_result(
        command_name=CommandName.PREPROCESS.value,
        message=(
            "Workflow state changed while this confirmed action was pending. "
            "Review the action again before continuing."
        ),
        state=publication.state,
        changed_state=ChangedState(),
        error_type=ErrorType.PRECONDITION,
        recoverable=True,
        diagnostics={"stale_publication": True},
    )

    def execute(_context, command, **kwargs):
        if isinstance(command, QueryStateCommand):
            assert kwargs["expected_publication_generation"] == publication.generation
            return MagicMock(
                failed=False,
                diagnostics={"loaded_data_list": [raw]},
                runtime={},
            )
        assert isinstance(command, PreprocessCommand)
        assert kwargs["expected_publication_generation"] == publication.generation
        return stale_result

    with (
        patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.Yes,
        ),
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.ChannelSelectionDialog",
        ) as dialog,
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.execute_application_command",
            side_effect=execute,
        ),
        patch.object(QMessageBox, "warning") as warning,
        patch.object(QMessageBox, "critical") as critical,
        patch.object(widget, "_show_status") as show_status,
    ):
        dialog.return_value.exec.return_value = True
        dialog.return_value.get_result.return_value = ["C3", "C4"]
        widget.open_channel_selection()

    warning.assert_called_once_with(
        widget,
        "Review Channel Selection Again",
        stale_result.message,
    )
    critical.assert_not_called()
    show_status.assert_not_called()
    panel.update_panel.assert_not_called()


def test_button_connections(sidebar):
    # Verify connections call action handler
    sidebar.import_btn.click()
    sidebar.panel.action_handler.import_data.assert_called_once()

    sidebar.import_folder_btn.click()
    sidebar.panel.action_handler.import_folder_source.assert_called_once()

    sidebar.import_bids_btn.click()
    sidebar.panel.action_handler.import_bids_source.assert_called_once()

    sidebar.reload_recipe_btn.click()
    sidebar.panel.action_handler.reload_interpretation_recipe.assert_called_once()

    sidebar.smart_parse_btn.click()
    sidebar.panel.action_handler.open_smart_parser.assert_called_once()
