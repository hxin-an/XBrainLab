from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import mne
import numpy as np
import pytest
from PyQt6.QtWidgets import QLabel, QPushButton, QWidget

from XBrainLab.backend.application import ApplyMontageCommand, QueryStateCommand
from XBrainLab.ui.panels.dataset.sidebar import (
    _ACTION_TEXT_HORIZONTAL_PADDING,
    _DATASET_SIDEBAR_BUTTON_STYLE,
    DatasetSidebar,
)
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
    assert sidebar.import_btn.text() == "Import Data"
    assert not hasattr(sidebar, "import_folder_btn")
    assert not hasattr(sidebar, "import_bids_btn")
    assert isinstance(sidebar.reload_recipe_btn, QPushButton)
    assert isinstance(sidebar.import_label_btn, QPushButton)
    assert isinstance(sidebar.smart_parse_btn, QPushButton)
    assert isinstance(sidebar.chan_select_btn, QPushButton)
    assert isinstance(sidebar.electrode_layout_btn, QPushButton)
    assert not hasattr(sidebar, "electrode_layout_status")
    assert sidebar.electrode_layout_btn.toolTip() == (
        "No electrode layout configured. Load EEG data to review positions."
    )
    assert sidebar.electrode_layout_btn.accessibleDescription() == (
        "No electrode layout configured. Load EEG data to review positions."
    )
    assert not hasattr(sidebar, "clear_btn")
    assert not sidebar.findChildren(QPushButton, "ResetSessionButton")
    assert all(
        button.text() != "Reset Session" for button in sidebar.findChildren(QPushButton)
    )


@pytest.mark.parametrize("status", ["ready", "limited"])
def test_bids_layout_opens_the_same_dialog_summary_without_dispatching_apply(
    sidebar, monkeypatch, status
):
    dispatched = []
    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar.get_command_capability",
        lambda *_: SimpleNamespace(enabled=True),
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar.execute_application_command",
        lambda _widget, command, **_kwargs: (
            dispatched.append(command)
            or SimpleNamespace(
                failed=False,
                diagnostics={
                    "state": {
                        "electrode_layout": {
                            "source": "bids",
                            "status": status,
                            "positioned_channel_count": 3,
                            "channel_count": 4,
                            "coordinate_summary": "head",
                            "channel_names": ["C3"],
                            "electrode_names": ["C3"],
                        },
                        "interpretation": {"source_kind": "bids"},
                        "raw": {"channels": ["C3", "C4", "P3", "P4"]},
                        "active_training": {"has_trainer": False},
                    }
                },
            )
        ),
    )
    opened = []

    class SummaryDialog:
        def __init__(self, *_args, **kwargs):
            opened.append(kwargs)

        @staticmethod
        def exec():
            return False

    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar._electrode_layout_dialog_class",
        lambda: SummaryDialog,
    )

    outcome = sidebar.open_electrode_layout()

    assert outcome.status.value == "cancelled"
    assert opened == [
        {
            "current_layout": {
                "source": "bids",
                "status": status,
                "positioned_channel_count": 3,
                "channel_count": 4,
                "coordinate_summary": "head",
                "name": None,
                "bids_restore_available": False,
                "channel_names": ["C3"],
                "electrode_names": ["C3"],
                "preparation_state": None,
                "preparation_reason": None,
            },
            "is_bids_source": True,
            "layout_changes_allowed": True,
        }
    ]
    assert len(dispatched) == 1
    assert isinstance(dispatched[0], QueryStateCommand)
    assert sidebar._active_electrode_layout_dialog is None


def test_bids_layout_restore_dispatches_only_the_restore_command(sidebar, monkeypatch):
    dispatched = []
    state = {
        "electrode_layout": {
            "source": "manual",
            "status": "ready",
            "bids_restore_available": True,
        },
        "interpretation": {"source_kind": "bids"},
        "raw": {"channels": ["C3"]},
        "active_training": {"has_trainer": False},
    }
    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar.get_command_capability",
        lambda *_: SimpleNamespace(enabled=True),
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar.execute_application_command",
        lambda _widget, command, **_kwargs: (
            dispatched.append(command)
            or SimpleNamespace(failed=False, diagnostics={"state": state})
        ),
    )

    class RestoreDialog:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def exec():
            return True

        @staticmethod
        def restore_bids_requested():
            return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar._electrode_layout_dialog_class",
        lambda: RestoreDialog,
    )

    outcome = sidebar.open_electrode_layout()

    assert outcome.is_completed is True
    assert isinstance(dispatched[0], QueryStateCommand)
    assert dispatched[1].restore_bids is True
    assert dispatched[1].channels == []
    assert dispatched[1].positions == []


@pytest.mark.parametrize("restore_bids", [False, True])
def test_electrode_layout_review_is_generation_fenced_before_replace_or_restore(
    sidebar, monkeypatch, restore_bids
):
    """A changed dataset rejects either reviewed layout submission for re-review."""
    reviewed_generation = 41
    state = {
        "electrode_layout": {},
        "interpretation": {"source_kind": "bids"},
        "raw": {"channels": ["C3"]},
        "active_training": {"has_trainer": False},
    }
    calls = []
    warnings = []
    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar.get_application_view_publication",
        lambda *_: SimpleNamespace(generation=reviewed_generation),
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar.get_command_capability",
        lambda *_: SimpleNamespace(enabled=True),
    )

    def execute(_widget, command, **kwargs):
        calls.append((command, kwargs))
        if isinstance(command, QueryStateCommand):
            return SimpleNamespace(failed=False, diagnostics={"state": state})
        return SimpleNamespace(
            failed=True,
            message="Nothing was applied. Review the latest dataset and try again.",
            diagnostics={"stale_publication": True},
        )

    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar.execute_application_command", execute
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar.show_warning",
        lambda *_args: warnings.append(_args[1:]),
    )

    class ReviewedDialog:
        def __init__(self, *_args, **_kwargs):
            self.montage_combo = None

        @staticmethod
        def exec():
            return True

        @staticmethod
        def restore_bids_requested():
            return restore_bids

        @staticmethod
        def get_result():
            return ["C3"], [(0.0, 0.0, 0.08)]

        @staticmethod
        def get_electrode_names():
            return ["C3"]

    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar._electrode_layout_dialog_class",
        lambda: ReviewedDialog,
    )

    outcome = sidebar.open_electrode_layout()

    assert outcome.status.value == "blocked"
    assert [
        kwargs["expected_publication_generation"] for _command, kwargs in calls
    ] == [reviewed_generation, reviewed_generation]
    assert isinstance(calls[0][0], QueryStateCommand)
    assert isinstance(calls[1][0], ApplyMontageCommand)
    assert calls[1][0].restore_bids is restore_bids
    assert warnings == [
        (
            "Review Electrode Layout Again",
            "Nothing was applied. Review the latest dataset and try again.",
        )
    ]


def test_replace_layout_accepts_numpy_positions_from_the_real_picker(
    sidebar, qtbot, monkeypatch
):
    """A reviewed picker result reaches the command spine instead of truth-testing ndarray."""
    from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import (
        PickMontageDialog,
    )

    montage_positions = {
        "C3": (0.0, 0.0, 0.08),
        "C4": (0.04, 0.0, 0.08),
    }
    with (
        patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_builtin_montages",
            return_value=["standard_1020"],
        ),
        patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_positions",
            return_value={"ch_pos": montage_positions},
        ),
        patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_channel_positions",
            return_value=np.asarray(list(montage_positions.values())),
        ),
    ):
        dialog = PickMontageDialog(
            sidebar,
            ["C3", "C4"],
            is_bids_source=True,
            current_layout={"source": "bids", "status": "ready"},
        )
    qtbot.addWidget(dialog)
    dialog.show_mapping_page()
    for row in range(dialog.table.rowCount()):
        combo = dialog.table.cellWidget(row, 1)
        assert combo is not None
        combo.setCurrentIndex(row + 1)
    with patch(
        "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_channel_positions",
        return_value=np.asarray(list(montage_positions.values())),
    ):
        dialog.accept()
    assert isinstance(dialog.get_result()[1], np.ndarray)
    monkeypatch.setattr(dialog, "exec", lambda: True)
    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar._electrode_layout_dialog_class",
        lambda: lambda *_args, **_kwargs: dialog,
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar.get_command_capability",
        lambda *_: SimpleNamespace(enabled=True),
    )
    dispatched = []
    state = {
        "electrode_layout": {},
        "interpretation": {"source_kind": "bids"},
        "raw": {"channels": ["C3", "C4"]},
        "active_training": {"has_trainer": False},
    }

    def execute(_widget, command, **_kwargs):
        dispatched.append(command)
        if isinstance(command, QueryStateCommand):
            return SimpleNamespace(failed=False, diagnostics={"state": state})
        return SimpleNamespace(failed=False)

    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar.execute_application_command", execute
    )

    outcome = sidebar.open_electrode_layout()

    assert outcome.is_completed is True
    assert isinstance(dispatched[0], QueryStateCommand)
    applied = dispatched[1]
    assert isinstance(applied, ApplyMontageCommand)
    assert applied.channels == ["C3", "C4"]
    assert applied.positions == [(0.0, 0.0, 0.08), (0.04, 0.0, 0.08)]


def test_bids_layout_publication_keeps_tooltip_and_notifies_once(sidebar, monkeypatch):
    layout = SimpleNamespace(
        status="ready",
        source="bids",
        positioned_channel_count=4,
        channel_count=4,
    )
    publication = SimpleNamespace(
        effective_capabilities={},
        state=SimpleNamespace(electrode_layout=layout),
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar.get_application_view_publication",
        lambda *_: publication,
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar.has_real_application_context",
        lambda *_: False,
    )
    status = MagicMock()
    monkeypatch.setattr(sidebar, "_show_status", status)

    sidebar.update_sidebar()
    sidebar.update_sidebar()

    assert sidebar.electrode_layout_btn.toolTip() == (
        "BIDS layout ready · 4 of 4 EEG channels positioned"
    )
    assert sidebar.electrode_layout_btn.accessibleDescription() == (
        "BIDS layout ready · 4 of 4 EEG channels positioned"
    )
    status.assert_called_once()


def test_layout_status_projects_loading_and_manual_partial_states(sidebar, monkeypatch):
    layout = SimpleNamespace(
        status="pending",
        source=None,
        positioned_channel_count=0,
        channel_count=22,
    )
    publication = SimpleNamespace(
        effective_capabilities={},
        state=SimpleNamespace(electrode_layout=layout),
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar.get_application_view_publication",
        lambda *_: publication,
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar.has_real_application_context",
        lambda *_: False,
    )

    sidebar.update_sidebar()
    assert sidebar.electrode_layout_btn.toolTip() == "Preparing BIDS electrode layout"

    layout.status = "limited"
    layout.source = "manual"
    layout.positioned_channel_count = 18
    sidebar.update_sidebar()
    assert sidebar.electrode_layout_btn.toolTip() == (
        "Manual layout limited · 18 of 22 EEG channels positioned"
    )

    layout.status = "failed"
    layout.source = "bids"
    sidebar.update_sidebar()
    assert sidebar.electrode_layout_btn.toolTip() == "BIDS electrode layout unavailable"


def test_publication_refreshes_only_an_active_pending_electrode_summary(
    sidebar, qtbot, monkeypatch
):
    from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import (
        PickMontageDialog,
    )

    positions = {"C3": (0.0, 0.0, 0.08), "C4": (0.04, 0.0, 0.08)}
    with (
        patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_builtin_montages",
            return_value=["standard_1020"],
        ),
        patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_positions",
            return_value={"ch_pos": positions},
        ),
        patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_channel_positions",
            return_value=positions,
        ),
    ):
        dialog = PickMontageDialog(
            None,
            ["C3", "C4"],
            is_bids_source=True,
            current_layout={"source": None, "status": "pending"},
        )
    qtbot.addWidget(dialog)
    sidebar._active_electrode_layout_dialog = dialog
    layout = SimpleNamespace(
        status="ready",
        source="bids",
        positioned_channel_count=4,
        channel_count=4,
        name=None,
    )
    publication = SimpleNamespace(
        effective_capabilities={},
        state=SimpleNamespace(
            electrode_layout=layout,
            visualization=SimpleNamespace(
                montage_preparation_state="ready",
                montage_preparation_reason=None,
            ),
        ),
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar.get_application_view_publication",
        lambda *_: publication,
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.dataset.sidebar.has_real_application_context",
        lambda *_: False,
    )

    sidebar.update_sidebar()

    title = dialog.findChild(QLabel, "ElectrodeLayoutSummaryTitle")
    assert title is not None
    assert title.text() == "Dataset electrode coordinates"
    dialog.show_mapping_page()
    sidebar.update_sidebar()
    assert dialog.mapping_page.isHidden() is False


def test_add_labels_compatibility_button_stays_hidden(sidebar):
    assert sidebar.import_label_btn.isHidden() is True
    assert sidebar.import_label_btn.text() == "Add labels"
    assert sidebar.smart_parse_btn.isHidden()


def test_channel_selection_uses_neutral_action_style(sidebar):
    style = sidebar.chan_select_btn.styleSheet()

    assert style == _DATASET_SIDEBAR_BUTTON_STYLE
    assert Stylesheets.SIDEBAR_BTN in style
    assert f"padding-left: {_ACTION_TEXT_HORIZONTAL_PADDING // 2}px" in style
    assert f"padding-right: {_ACTION_TEXT_HORIZONTAL_PADDING // 2}px" in style
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
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.show_warning",
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


def test_channel_selection_binds_reviewed_publication_without_false_warning(
    qtbot,
):
    from XBrainLab.backend.application import (
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
    success_result = MagicMock(failed=False)

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
        boundary = kwargs["reviewed_preprocess_boundary"]
        assert boundary.publication_generation == publication.generation
        assert boundary.publication_revision == publication.revision
        assert boundary.state == publication.state
        return success_result

    with (
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.ChannelSelectionDialog",
        ) as dialog,
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.execute_application_command",
            side_effect=execute,
        ),
        patch("XBrainLab.ui.panels.dataset.sidebar.show_warning") as warning,
        patch("XBrainLab.ui.panels.dataset.sidebar.show_error") as critical,
        patch.object(widget, "_show_status") as show_status,
    ):
        dialog.return_value.exec.return_value = True
        dialog.return_value.get_result.return_value = ["C3", "C4"]
        widget.open_channel_selection()

    warning.assert_not_called()
    critical.assert_not_called()
    show_status.assert_called_once_with("Channel selection applied")
    panel.update_panel.assert_not_called()


def test_channel_selection_uses_captured_channels_when_montage_settles(
    qtbot,
):
    from XBrainLab.backend.application import get_application_service
    from XBrainLab.backend.application.bids_montage_preparation import (
        MontagePreparationSnapshot,
    )
    from XBrainLab.backend.load_data.raw import Raw
    from XBrainLab.backend.study import Study

    study = Study()
    raw = Raw(
        "channels.fif",
        mne.io.RawArray(
            np.zeros((2, 500)),
            mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
            verbose="ERROR",
        ),
    )
    study.set_loaded_data_list([raw], force_update=True)
    panel = MagicMock()
    panel.action_handler = MagicMock()
    panel.controller = MagicMock()
    panel.main_window = QWidget()
    panel.main_window.study = study
    widget = DatasetSidebar(panel, parent=None)
    qtbot.addWidget(widget)
    service = get_application_service(study)
    montage_status = [
        MontagePreparationSnapshot.pending(
            generation=1,
            recording_paths=("channels.fif",),
        )
    ]
    service.state_snapshot.montage_snapshot_provider = lambda: montage_status[0]
    reviewed = service._view_coordinator.refresh_opportunistic()

    def capture_then_settle(_context):
        montage_status[0] = MontagePreparationSnapshot(
            state="ready",
            generation=1,
            requested_recording_paths=("channels.fif",),
        )
        current = service._view_coordinator.refresh_opportunistic()
        assert current.generation > reviewed.generation
        return reviewed

    with (
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.get_application_view_publication",
            side_effect=capture_then_settle,
        ),
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.ChannelSelectionDialog",
        ) as dialog,
        patch("XBrainLab.ui.panels.dataset.sidebar.show_warning") as warning,
    ):
        dialog.return_value.exec.return_value = False
        widget.open_channel_selection()

    dialog.assert_called_once_with(widget, ["C3", "C4"])
    warning.assert_not_called()


@pytest.mark.parametrize(
    "stale_diagnostic",
    ["stale_publication", "stale_prepared_preprocess"],
)
def test_channel_selection_metadata_change_uses_dataset_warning(
    qtbot,
    stale_diagnostic,
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
        message="generic backend stale message",
        state=publication.state,
        changed_state=ChangedState(),
        error_type=ErrorType.PRECONDITION,
        recoverable=True,
        diagnostics={stale_diagnostic: True},
    )

    def execute(_context, command, **kwargs):
        if isinstance(command, QueryStateCommand):
            return MagicMock(
                failed=False,
                diagnostics={"loaded_data_list": [raw]},
                runtime={},
            )
        assert isinstance(command, PreprocessCommand)
        return stale_result

    with (
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.ChannelSelectionDialog",
        ) as dialog,
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.execute_application_command",
            side_effect=execute,
        ),
        patch("XBrainLab.ui.panels.dataset.sidebar.show_warning") as warning,
        patch("XBrainLab.ui.panels.dataset.sidebar.show_error") as critical,
        patch.object(widget, "_show_status") as show_status,
    ):
        dialog.return_value.exec.return_value = True
        dialog.return_value.get_result.return_value = ["C3", "C4"]
        widget.open_channel_selection()

    warning.assert_called_once_with(
        widget,
        "Dataset Changed",
        "Nothing was applied. Review the latest dataset and try again.",
    )
    critical.assert_not_called()
    show_status.assert_not_called()


@pytest.mark.parametrize("raw_change", ["channels", "source"])
def test_channel_selection_raw_change_uses_channels_warning(qtbot, raw_change):
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
    changed_raw = (
        replace(publication.state.raw, channels=["C3"])
        if raw_change == "channels"
        else replace(publication.state.raw, files=["sub-02_task-mi_raw.fif"])
    )
    stale_result = CommandResult.failure_result(
        command_name=CommandName.PREPROCESS.value,
        message="generic backend stale message",
        state=replace(publication.state, raw=changed_raw),
        changed_state=ChangedState(),
        error_type=ErrorType.PRECONDITION,
        recoverable=True,
        diagnostics={"stale_publication": True},
    )

    def execute(_context, command, **kwargs):
        if isinstance(command, QueryStateCommand):
            return MagicMock(
                failed=False,
                diagnostics={"loaded_data_list": [raw]},
                runtime={},
            )
        assert isinstance(command, PreprocessCommand)
        return stale_result

    with (
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.ChannelSelectionDialog",
        ) as dialog,
        patch(
            "XBrainLab.ui.panels.dataset.sidebar.execute_application_command",
            side_effect=execute,
        ),
        patch("XBrainLab.ui.panels.dataset.sidebar.show_warning") as warning,
        patch("XBrainLab.ui.panels.dataset.sidebar.show_error") as critical,
    ):
        dialog.return_value.exec.return_value = True
        dialog.return_value.get_result.return_value = ["C3", "C4"]
        widget.open_channel_selection()

    warning.assert_called_once_with(
        widget,
        "Channels Changed",
        "Nothing was applied. Review the latest channels and try again.",
    )
    critical.assert_not_called()


def test_button_connections(sidebar):
    # Verify connections call action handler
    sidebar.import_btn.click()
    sidebar.panel.action_handler.import_data.assert_called_once()

    sidebar.reload_recipe_btn.click()
    sidebar.panel.action_handler.reload_interpretation_recipe.assert_called_once()

    sidebar.smart_parse_btn.click()
    sidebar.panel.action_handler.open_smart_parser.assert_called_once()
