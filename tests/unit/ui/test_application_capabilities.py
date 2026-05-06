"""Tests for UI reads of ApplicationService command capabilities."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.application import (
    ChangedState,
    CommandName,
    CommandResult,
    QueryStateCommand,
)
from XBrainLab.backend.facade import BackendFacade
from XBrainLab.backend.study import Study
from XBrainLab.ui import application_capabilities
from XBrainLab.ui.application_capabilities import (
    execute_application_command,
    get_command_capability,
    run_legacy_controller_fallback,
)


def test_ui_capability_helper_returns_application_policy(qtbot):
    study = Study()
    widget = QWidget()
    main_window = MagicMock()
    main_window.study = study
    cast(Any, widget).main_window = main_window
    qtbot.addWidget(widget)

    ui_capability = get_command_capability(widget, CommandName.TRAIN)
    backend_capability = (
        BackendFacade(study)
        .get_capabilities()
        .get(
            CommandName.TRAIN,
        )
    )

    assert ui_capability is not None
    assert ui_capability.enabled == backend_capability.enabled
    assert ui_capability.reasons == backend_capability.reasons


def test_ui_capability_helper_ignores_mock_study(qtbot):
    widget = QWidget()
    main_window = MagicMock()
    main_window.study = MagicMock()
    cast(Any, widget).main_window = main_window
    qtbot.addWidget(widget)

    assert get_command_capability(widget, CommandName.TRAIN) is None


def test_execute_application_command_triggers_changed_state_refresh(
    qtbot,
    monkeypatch,
):
    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    result = CommandResult.success_result(
        command_name="query_state",
        message="ok",
        state=None,
        changed_state=ChangedState(raw_changed=True),
    )
    refresh_calls = []

    class _Service:
        def execute(self, command):
            assert isinstance(command, QueryStateCommand)
            return result

    class _Facade:
        def __init__(self, provided_study):
            assert provided_study is study
            self.service = _Service()

    monkeypatch.setattr(application_capabilities, "BackendFacade", _Facade)
    monkeypatch.setattr(
        application_capabilities,
        "refresh_after_command",
        lambda context, command_result: refresh_calls.append(
            (context, command_result),
        ),
    )

    command_result = execute_application_command(widget, QueryStateCommand())

    assert command_result is result
    assert refresh_calls == [(widget, result)]


def test_execute_application_command_can_skip_refresh(qtbot, monkeypatch):
    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    result = CommandResult.success_result(
        command_name="query_state",
        message="ok",
        state=None,
        changed_state=ChangedState(raw_changed=True),
    )
    refresh_calls = []

    class _Service:
        def execute(self, command):
            assert isinstance(command, QueryStateCommand)
            return result

    class _Facade:
        def __init__(self, provided_study):
            assert provided_study is study
            self.service = _Service()

    monkeypatch.setattr(application_capabilities, "BackendFacade", _Facade)
    monkeypatch.setattr(
        application_capabilities,
        "refresh_after_command",
        lambda context, command_result: refresh_calls.append(
            (context, command_result),
        ),
    )

    command_result = execute_application_command(
        widget,
        QueryStateCommand(),
        refresh=False,
    )

    assert command_result is result
    assert refresh_calls == []


def test_legacy_controller_fallback_refuses_real_study(qtbot):
    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    fallback = MagicMock()

    with pytest.raises(RuntimeError, match="could not safely complete"):
        run_legacy_controller_fallback(widget, fallback)

    fallback.assert_not_called()


def test_legacy_controller_fallback_refuses_real_controller_study(qtbot):
    study = Study()
    widget = QWidget()
    cast(Any, widget).controller = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    fallback = MagicMock()

    with pytest.raises(RuntimeError, match="could not safely complete"):
        run_legacy_controller_fallback(widget, fallback)

    fallback.assert_not_called()


def test_named_controller_context_uses_application_service(qtbot):
    study = Study()
    widget = QWidget()
    cast(Any, widget).preprocess_controller = SimpleNamespace(study=study)
    qtbot.addWidget(widget)

    ui_capability = get_command_capability(widget, CommandName.TRAIN)

    assert ui_capability is not None


def test_legacy_controller_fallback_refuses_named_real_controller(qtbot):
    study = Study()
    widget = QWidget()
    cast(Any, widget).preprocess_controller = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    fallback = MagicMock()

    with pytest.raises(RuntimeError, match="could not safely complete"):
        run_legacy_controller_fallback(widget, fallback)

    fallback.assert_not_called()
