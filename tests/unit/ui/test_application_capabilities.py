"""Tests for UI reads of ApplicationService command capabilities."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from PyQt6 import sip
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.application import (
    ChangedState,
    CommandName,
    CommandResult,
    QueryStateCommand,
    get_application_service,
)
from XBrainLab.backend.study import Study
from XBrainLab.ui import application_capabilities
from XBrainLab.ui.application_capabilities import (
    execute_application_command,
    execute_application_command_async,
    get_command_capability,
    run_legacy_controller_fallback,
)
from XBrainLab.ui.refresh_coordinator import refresh_after_observer


def test_ui_capability_helper_returns_application_policy(qtbot):
    study = Study()
    widget = QWidget()
    main_window = MagicMock()
    main_window.study = study
    cast(Any, widget).main_window = main_window
    qtbot.addWidget(widget)

    ui_capability = get_command_capability(widget, CommandName.TRAIN)
    backend_capability = (
        get_application_service(study)
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

    def _service_for(provided_study):
        assert provided_study is study
        return _Service()

    monkeypatch.setattr(
        application_capabilities,
        "get_application_service",
        _service_for,
    )
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


def test_execute_application_command_suppresses_observer_refresh_until_result_refresh(
    qtbot,
    monkeypatch,
):
    study = Study()
    widget = QWidget()
    qtbot.addWidget(widget)

    class _PanelSpy:
        def __init__(self) -> None:
            self.update_calls = 0

        def update_panel(self) -> None:
            self.update_calls += 1

    class _AgentSpy:
        def __init__(self) -> None:
            self.refresh_calls = 0

        def refresh_backend_status(self) -> None:
            self.refresh_calls += 1

    main_window = SimpleNamespace(
        study=study,
        dataset_panel=_PanelSpy(),
        preprocess_panel=_PanelSpy(),
        training_panel=_PanelSpy(),
        evaluation_panel=_PanelSpy(),
        visualization_panel=_PanelSpy(),
        agent_manager=_AgentSpy(),
        update_info_calls=0,
    )

    def update_info_panel() -> None:
        main_window.update_info_calls += 1

    main_window.update_info_panel = update_info_panel
    cast(Any, widget).main_window = main_window

    result = CommandResult.success_result(
        command_name="load_data",
        message="ok",
        state=None,
        changed_state=ChangedState(raw_changed=True),
    )

    class _Service:
        def execute(self, command):
            assert isinstance(command, QueryStateCommand)
            assert refresh_after_observer(widget, event_name="data_changed") is False
            return result

    monkeypatch.setattr(
        application_capabilities,
        "get_application_service",
        lambda provided_study: _Service(),
    )

    command_result = execute_application_command(widget, QueryStateCommand())

    assert command_result is result
    assert main_window.dataset_panel.update_calls == 1
    assert main_window.preprocess_panel.update_calls == 1
    assert main_window.training_panel.update_calls == 1
    assert main_window.evaluation_panel.update_calls == 0
    assert main_window.visualization_panel.update_calls == 0
    assert main_window.update_info_calls == 1
    assert main_window.agent_manager.refresh_calls == 1


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

    def _service_for(provided_study):
        assert provided_study is study
        return _Service()

    monkeypatch.setattr(
        application_capabilities,
        "get_application_service",
        _service_for,
    )
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


def test_execute_application_command_async_runs_service_off_gui_call_stack(
    qtbot,
    monkeypatch,
):
    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    qtbot.addWidget(widget)
    busy_states: list[bool] = []
    cast(Any, widget).set_busy = lambda busy: busy_states.append(bool(busy))
    result = CommandResult.success_result(
        command_name="query_state",
        message="ok",
        state=None,
        changed_state=ChangedState(raw_changed=True),
    )
    executed: list[QueryStateCommand] = []
    callbacks: list[CommandResult] = []
    refresh_calls: list[tuple[Any, CommandResult]] = []
    started_workers = []

    class _Service:
        def execute(self, command):
            assert isinstance(command, QueryStateCommand)
            executed.append(command)
            return result

    class _ThreadPool:
        def start(self, worker):
            started_workers.append(worker)

    monkeypatch.setattr(
        application_capabilities,
        "get_application_service",
        lambda provided_study: _Service(),
    )
    monkeypatch.setattr(
        application_capabilities.QThreadPool,
        "globalInstance",
        lambda: _ThreadPool(),
    )
    monkeypatch.setattr(
        application_capabilities,
        "refresh_after_command",
        lambda context, command_result: refresh_calls.append(
            (context, command_result),
        ),
    )

    started = execute_application_command_async(
        widget,
        QueryStateCommand(),
        on_result=callbacks.append,
    )

    assert started is True
    assert busy_states == [True]
    assert executed == []
    assert len(started_workers) == 1
    assert cast(Any, widget)._xbrainlab_active_application_workers == started_workers

    started_workers[0].run()

    assert len(executed) == 1
    assert callbacks == [result]
    assert refresh_calls == [(widget, result)]
    assert busy_states == [True, False]
    assert cast(Any, widget)._xbrainlab_active_application_workers == []


def test_execute_application_command_async_ignores_result_after_widget_deleted(
    qtbot,
    monkeypatch,
):
    study = Study()
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=study)
    busy_states: list[bool] = []
    cast(Any, widget).set_busy = lambda busy: busy_states.append(bool(busy))
    result = CommandResult.success_result(
        command_name="query_state",
        message="ok",
        state=None,
        changed_state=ChangedState(raw_changed=True),
    )
    callbacks: list[CommandResult] = []
    refresh_calls: list[tuple[Any, CommandResult]] = []
    started_workers = []

    class _Service:
        def execute(self, command):
            assert isinstance(command, QueryStateCommand)
            return result

    class _ThreadPool:
        def start(self, worker):
            started_workers.append(worker)

    monkeypatch.setattr(
        application_capabilities,
        "get_application_service",
        lambda provided_study: _Service(),
    )
    monkeypatch.setattr(
        application_capabilities.QThreadPool,
        "globalInstance",
        lambda: _ThreadPool(),
    )
    monkeypatch.setattr(
        application_capabilities,
        "refresh_after_command",
        lambda context, command_result: refresh_calls.append(
            (context, command_result),
        ),
    )

    started = execute_application_command_async(
        widget,
        QueryStateCommand(),
        on_result=callbacks.append,
    )
    assert started is True

    widget.deleteLater()
    qtbot.waitUntil(lambda: sip.isdeleted(widget), timeout=1_000)
    started_workers[0].run()

    assert busy_states == [True]
    assert callbacks == []
    assert refresh_calls == []
    assert cast(Any, widget)._xbrainlab_active_application_workers == []


def test_execute_application_command_async_returns_false_for_mock_study(
    qtbot,
    monkeypatch,
):
    widget = QWidget()
    cast(Any, widget).main_window = SimpleNamespace(study=MagicMock())
    qtbot.addWidget(widget)
    started_workers = []

    class _ThreadPool:
        def start(self, worker):
            started_workers.append(worker)

    monkeypatch.setattr(
        application_capabilities.QThreadPool,
        "globalInstance",
        lambda: _ThreadPool(),
    )

    started = execute_application_command_async(
        widget,
        QueryStateCommand(),
        on_result=lambda _result: None,
    )

    assert started is False
    assert started_workers == []


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


def test_legacy_controller_fallback_allows_plain_non_study_context():
    fallback = MagicMock(return_value="legacy-ok")

    result = run_legacy_controller_fallback(object(), fallback)

    assert result == "legacy-ok"
    fallback.assert_called_once_with()
