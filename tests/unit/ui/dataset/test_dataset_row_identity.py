"""Dataset-table actions remain bound to the rendered file identities."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QMainWindow

from XBrainLab.backend.application.capabilities import CommandCapability
from XBrainLab.backend.application.commands import (
    QueryStateCommand,
    RemoveFilesCommand,
    UpdateMetadataCommand,
)
from XBrainLab.backend.study import Study
from XBrainLab.ui.application_capabilities import CommandReviewContext
from XBrainLab.ui.panels.dataset import actions
from XBrainLab.ui.panels.dataset import panel as panel_module
from XBrainLab.ui.panels.dataset.panel import DatasetPanel


def _loaded_data(path: str) -> MagicMock:
    data = MagicMock()
    data.configure_mock(
        **{
            "get_filepath.return_value": path,
            "get_filename.return_value": path.rsplit("/", 1)[-1],
            "get_subject_name.return_value": "S01",
            "get_session_name.return_value": "session-01",
            "get_nchan.return_value": 4,
            "get_sfreq.return_value": 128.0,
            "get_epochs_length.return_value": 1,
            "get_event_summary.return_value": {
                "available": False,
                "count": 0,
                "labels": [],
                "source": "none",
                "scanned": True,
            },
            "is_labels_imported.return_value": False,
        }
    )
    return data


def _result(
    *,
    data_list: list[Any] | None = None,
    stale: bool = False,
) -> SimpleNamespace:
    files = [str(data.get_filepath()) for data in list(data_list or [])]
    rows = [
        {
            "filepath": str(data.get_filepath()),
            "filename": str(data.get_filename()),
            "subject": str(data.get_subject_name()),
            "session": str(data.get_session_name()),
            "n_channels": int(data.get_nchan()),
            "sampling_frequency": float(data.get_sfreq()),
            "epochs_length": int(data.get_epochs_length()),
            "is_raw": True,
            "labels_imported": False,
            "channels": [],
            "event": dict(data.get_event_summary(allow_scan=False)),
        }
        for data in list(data_list or [])
    ]
    return SimpleNamespace(
        failed=stale,
        recoverable=stale,
        message=(
            "The reviewed dataset changed."
            if stale
            else "Dataset state was read successfully."
        ),
        diagnostics=(
            {"stale_publication": True}
            if stale
            else {
                "raw_files": files,
                "raw_rows": rows,
                "preprocessed_rows": [],
            }
        ),
    )


class _Capabilities:
    def get(self, command_name) -> CommandCapability:
        value = getattr(command_name, "value", command_name)
        return CommandCapability(command_name=str(value), enabled=True)


def _publication(generation: int) -> SimpleNamespace:
    return SimpleNamespace(
        generation=generation,
        effective_capabilities=_Capabilities(),
    )


@pytest.fixture
def rendered_dataset(qtbot, monkeypatch):
    window = QMainWindow()
    qtbot.addWidget(window)
    cast(Any, window).study = MagicMock()
    controller = MagicMock()
    controller.is_locked.return_value = False
    controller.has_data.return_value = True
    first = _loaded_data("/data/sub-01_task-mi_run-01_raw.fif")
    second = _loaded_data("/data/sub-01_task-mi_run-02_raw.fif")
    current = {"generation": 11, "data": [first, second]}
    mutations: list[tuple[Any, int | None]] = []

    def get_publication(_context):
        return _publication(current["generation"])

    def get_review_context(_context, command_name):
        capability = _Capabilities().get(command_name)
        return CommandReviewContext(
            capability=capability,
            publication_generation=current["generation"],
        )

    def execute(_context, command, **kwargs):
        expected = kwargs.get("expected_publication_generation")
        if isinstance(command, QueryStateCommand):
            if expected is not None and expected != current["generation"]:
                return _result(stale=True)
            return _result(data_list=current["data"])
        if isinstance(command, (UpdateMetadataCommand, RemoveFilesCommand)):
            mutations.append((command, expected))
            return _result()
        raise AssertionError(f"Unexpected command: {command!r}")

    monkeypatch.setattr(
        panel_module,
        "get_application_view_publication",
        get_publication,
        raising=False,
    )
    monkeypatch.setattr(
        panel_module,
        "get_command_capability",
        lambda _context, command_name: _Capabilities().get(command_name),
    )
    monkeypatch.setattr(panel_module, "execute_application_command", execute)
    monkeypatch.setattr(actions, "get_application_view_publication", get_publication)
    monkeypatch.setattr(actions, "get_command_review_context", get_review_context)
    monkeypatch.setattr(actions, "execute_application_command", execute)

    panel = DatasetPanel(controller=controller, parent=window)
    qtbot.addWidget(panel)
    panel.update_panel()
    return panel, current, mutations


def test_dataset_table_stores_detached_identity_not_live_raw(rendered_dataset) -> None:
    panel, current, _mutations = rendered_dataset
    name_item = panel.table.item(0, 0)

    assert name_item is not None
    assert name_item.data(Qt.ItemDataRole.UserRole) is None
    identity = name_item.data(panel._ROW_IDENTITY_ROLE)
    assert isinstance(identity, actions.DatasetTableRowIdentity)
    assert identity.canonical_filepath.endswith("sub-01_task-mi_run-01_raw.fif")
    assert current["data"][0] is not identity


def test_inline_metadata_edit_rejects_replaced_rendered_row(
    rendered_dataset,
    monkeypatch,
):
    panel, current, mutations = rendered_dataset
    warnings: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        panel_module,
        "show_warning",
        lambda *args: warnings.append(args),
    )
    subject_item = panel.table.item(0, 1)
    assert subject_item is not None

    current["generation"] = 12
    current["data"] = list(reversed(current["data"]))
    subject_item.setText("S99")

    assert mutations == []
    assert warnings
    assert warnings[0][1] == "Refresh Dataset and Edit Again"


def test_batch_metadata_update_uses_product_runtime_without_controller(
    rendered_dataset,
    monkeypatch,
) -> None:
    panel, _current, mutations = rendered_dataset
    panel.controller = None
    selection = panel.capture_table_selection([0])
    assert selection is not None
    monkeypatch.setattr(
        actions.QInputDialog,
        "getText",
        lambda *_args, **_kwargs: ("participant-07", True),
    )

    panel.action_handler._batch_set(selection, "Subject")

    assert len(mutations) == 1
    command, expected_generation = mutations[0]
    assert isinstance(command, UpdateMetadataCommand)
    assert command.updates[0].index == 0
    assert command.updates[0].subject == "participant-07"
    assert expected_generation == selection.publication_generation


@pytest.mark.parametrize(
    ("selected_action", "expected_title"),
    [
        ("subject", "Review Metadata Again"),
        ("remove", "Review File Removal Again"),
    ],
)
def test_context_menu_rejects_rows_reordered_while_menu_is_open(
    rendered_dataset,
    monkeypatch,
    selected_action,
    expected_title,
):
    panel, current, mutations = rendered_dataset
    panel.table.selectRow(0)
    warnings: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        actions,
        "show_warning",
        lambda *args: warnings.append(args),
    )
    monkeypatch.setattr(
        panel_module,
        "show_warning",
        lambda *args: warnings.append(args),
    )
    monkeypatch.setattr(
        actions,
        "ask_confirmation",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        actions.QInputDialog,
        "getText",
        lambda *_args, **_kwargs: ("S99", True),
    )

    menu = MagicMock()
    subject_action = object()
    session_action = object()
    remove_action = object()
    menu.addAction.side_effect = [subject_action, session_action, remove_action]

    def execute_menu(_pos):
        current["generation"] = 12
        current["data"] = list(reversed(current["data"]))
        return subject_action if selected_action == "subject" else remove_action

    menu.exec.side_effect = execute_menu
    monkeypatch.setattr(actions, "QMenu", MagicMock(return_value=menu))

    panel.action_handler.show_context_menu(QPoint(0, 0))

    assert mutations == []
    assert warnings
    assert warnings[0][1] == expected_title


@pytest.mark.parametrize("action_name", ["metadata", "remove"])
def test_table_mutations_fail_before_prompt_without_product_review(
    qtbot,
    monkeypatch,
    action_name,
):
    panel = QMainWindow()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).controller = MagicMock()
    handler = actions.DatasetActionHandler(panel)
    selection = actions.DatasetTableSelection(
        publication_generation=17,
        rows=(
            actions.DatasetTableRowIdentity(
                canonical_filepath="/data/sub-01_raw.fif",
                rendered_row=0,
            ),
        ),
    )
    input_dialog = MagicMock(return_value=("", False))
    confirmation = MagicMock(return_value=False)
    warning = MagicMock()
    monkeypatch.setattr(actions, "get_command_review_context", lambda *_args: None)
    monkeypatch.setattr(actions.QInputDialog, "getText", input_dialog)
    monkeypatch.setattr(actions, "ask_confirmation", confirmation)
    monkeypatch.setattr(actions, "show_warning", warning)

    if action_name == "metadata":
        handler._batch_set(selection, "Subject")
    else:
        handler._remove_files(selection)

    input_dialog.assert_not_called()
    confirmation.assert_not_called()
    warning.assert_called_once()
