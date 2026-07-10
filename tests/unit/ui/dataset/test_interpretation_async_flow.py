"""Lifecycle tests for non-blocking Data Interpretation command continuations."""

from __future__ import annotations

import threading
import time
from typing import Any, cast
from unittest.mock import MagicMock

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.application import (
    ChangedState,
    CommandResult,
    QueryStateCommand,
    ReloadInterpretationRecipeCommand,
    ReviewInterpretationCommand,
    SaveInterpretationRecipeCommand,
)
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.study import Study
from XBrainLab.ui import application_capabilities
from XBrainLab.ui.panels.dataset import actions
from XBrainLab.ui.panels.dataset.actions import DatasetActionHandler


def _success_result(command_name: str, **diagnostics: Any) -> CommandResult:
    return CommandResult.success_result(
        command_name=command_name,
        message="ok",
        state=ApplicationStateSnapshot.empty(),
        changed_state=ChangedState(),
        diagnostics=diagnostics,
    )


def test_real_study_command_returns_immediately_and_continues_on_result(
    qtbot,
    monkeypatch,
):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    busy_states: list[bool] = []
    cast(Any, panel).set_busy = lambda busy: busy_states.append(bool(busy))
    handler = DatasetActionHandler(panel)
    worker_started = threading.Event()
    worker_release = threading.Event()
    worker_threads: list[int] = []
    results: list[CommandResult] = []
    heartbeat: list[bool] = []
    expected = _success_result("query_state")

    class _Service:
        def execute(self, command):
            assert isinstance(command, QueryStateCommand)
            worker_threads.append(threading.get_ident())
            worker_started.set()
            assert worker_release.wait(timeout=2.0)
            return expected

    monkeypatch.setattr(
        application_capabilities,
        "get_application_service",
        lambda _study: _Service(),
    )
    monkeypatch.setattr(
        application_capabilities,
        "refresh_after_command",
        lambda *_args: None,
    )

    started_at = time.monotonic()
    started = handler._execute_interpretation_command_async(
        QueryStateCommand(),
        on_result=results.append,
        error_title="Review failed",
    )
    elapsed = time.monotonic() - started_at

    assert started is True
    assert elapsed < 0.1
    assert worker_started.wait(timeout=1.0)
    assert results == []
    QTimer.singleShot(0, lambda: heartbeat.append(True))
    qtbot.waitUntil(lambda: bool(heartbeat), timeout=1000)

    worker_release.set()
    qtbot.waitUntil(lambda: results == [expected], timeout=1000)

    assert worker_threads != [threading.get_ident()]
    assert busy_states == [True, False]
    assert getattr(panel, "_xbrainlab_active_application_workers", []) == []


def test_compatibility_context_continues_synchronously(qtbot, monkeypatch):
    panel = QWidget()
    qtbot.addWidget(panel)
    handler = DatasetActionHandler(panel)
    expected = _success_result("query_state")
    results = []

    monkeypatch.setattr(
        actions,
        "execute_application_command",
        lambda _panel, command: expected
        if isinstance(command, QueryStateCommand)
        else None,
    )

    started = handler._execute_interpretation_command_async(
        QueryStateCommand(),
        on_result=results.append,
        error_title="Review failed",
    )

    assert started is True
    assert results == [expected]


def test_worker_exception_cleans_up_and_reports_without_nested_wait(
    qtbot,
    monkeypatch,
):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = MagicMock()
    handler = DatasetActionHandler(panel)

    class _Service:
        def execute(self, _command):
            raise RuntimeError("scan failed")

    monkeypatch.setattr(
        application_capabilities,
        "get_application_service",
        lambda _study: _Service(),
    )
    critical = MagicMock()
    monkeypatch.setattr(actions.QMessageBox, "critical", critical)

    assert handler._execute_interpretation_command_async(
        QueryStateCommand(),
        on_result=MagicMock(),
        error_title="Review failed",
    )

    qtbot.waitUntil(lambda: critical.call_count == 1, timeout=1000)
    qtbot.waitUntil(
        lambda: not getattr(panel, "_xbrainlab_active_application_workers", []),
        timeout=1000,
    )
    assert "scan failed" in critical.call_args.args[2]
    assert cast(Any, panel).set_busy.call_args_list == [((True,),), ((False,),)]


def test_save_recipe_returns_before_worker_and_completes_via_callback(
    qtbot,
    monkeypatch,
):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    worker_started = threading.Event()
    worker_release = threading.Event()
    completions: list[str] = []
    heartbeat: list[bool] = []
    expected = _success_result("save_interpretation_recipe")

    class _Service:
        def execute(self, command):
            assert isinstance(command, SaveInterpretationRecipeCommand)
            worker_started.set()
            assert worker_release.wait(timeout=2.0)
            return expected

    monkeypatch.setattr(
        application_capabilities,
        "get_application_service",
        lambda _study: _Service(),
    )
    monkeypatch.setattr(
        application_capabilities,
        "refresh_after_command",
        lambda *_args: None,
    )
    monkeypatch.setattr(handler, "_recipe_save_block_reason", lambda: None)
    monkeypatch.setattr(
        actions.QFileDialog,
        "getSaveFileName",
        lambda *_args: ("/tmp/import_recipe.json", ""),
    )

    started_at = time.monotonic()
    started = handler._save_interpretation_recipe(on_complete=completions.append)
    elapsed = time.monotonic() - started_at

    assert started is True
    assert elapsed < 0.1
    assert worker_started.wait(timeout=1.0)
    assert completions == []
    QTimer.singleShot(0, lambda: heartbeat.append(True))
    qtbot.waitUntil(lambda: bool(heartbeat), timeout=1000)

    worker_release.set()
    qtbot.waitUntil(lambda: completions == ["Recipe saved."], timeout=1000)


def test_review_flow_uses_slow_worker_without_blocking_gui(qtbot, monkeypatch):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    continue_flow = MagicMock()
    monkeypatch.setattr(handler, "_continue_data_interpretation_import", continue_flow)
    worker_started = threading.Event()
    worker_release = threading.Event()
    heartbeat: list[bool] = []
    result = _success_result(
        "review_interpretation",
        scan_result={"scan_id": "scan-1"},
        preview={"summary": "ready"},
        candidate={"candidate_id": "candidate-1"},
        validation_decision={"candidate_id": "candidate-1", "decision": "safe"},
    )

    class _Service:
        def execute(self, command):
            assert isinstance(command, ReviewInterpretationCommand)
            worker_started.set()
            assert worker_release.wait(timeout=2.0)
            return result

    monkeypatch.setattr(
        application_capabilities,
        "get_application_service",
        lambda _study: _Service(),
    )
    monkeypatch.setattr(
        application_capabilities,
        "refresh_after_command",
        lambda *_args: None,
    )

    started_at = time.monotonic()
    started = handler._start_interpretation_review_async(
        "/tmp/sub-01_raw.fif",
        "auto",
        {},
        [],
    )
    elapsed = time.monotonic() - started_at

    assert started is True
    assert elapsed < 0.1
    assert worker_started.wait(timeout=1.0)
    QTimer.singleShot(0, lambda: heartbeat.append(True))
    qtbot.waitUntil(lambda: bool(heartbeat), timeout=1000)

    worker_release.set()
    qtbot.waitUntil(lambda: continue_flow.call_count == 1, timeout=1000)


def test_reload_recipe_uses_slow_worker_without_blocking_gui(qtbot, monkeypatch):
    panel = QWidget()
    qtbot.addWidget(panel)
    cast(Any, panel).study = Study()
    cast(Any, panel).set_busy = lambda _busy: None
    handler = DatasetActionHandler(panel)
    continue_reload = MagicMock()
    monkeypatch.setattr(
        handler,
        "_continue_reloaded_interpretation_recipe",
        continue_reload,
    )
    monkeypatch.setattr(
        handler, "_can_start_interpretation", lambda *_args, **_kw: True
    )
    monkeypatch.setattr(
        actions.QFileDialog,
        "getOpenFileName",
        lambda *_args: ("/tmp/import_recipe.json", ""),
    )
    worker_started = threading.Event()
    worker_release = threading.Event()
    heartbeat: list[bool] = []
    result = _success_result("reload_interpretation_recipe")

    class _Service:
        def execute(self, command):
            assert isinstance(command, ReloadInterpretationRecipeCommand)
            worker_started.set()
            assert worker_release.wait(timeout=2.0)
            return result

    monkeypatch.setattr(
        application_capabilities,
        "get_application_service",
        lambda _study: _Service(),
    )
    monkeypatch.setattr(
        application_capabilities,
        "refresh_after_command",
        lambda *_args: None,
    )

    started_at = time.monotonic()
    handler.reload_interpretation_recipe()
    elapsed = time.monotonic() - started_at

    assert elapsed < 0.1
    assert worker_started.wait(timeout=1.0)
    QTimer.singleShot(0, lambda: heartbeat.append(True))
    qtbot.waitUntil(lambda: bool(heartbeat), timeout=1000)

    worker_release.set()
    qtbot.waitUntil(lambda: continue_reload.call_count == 1, timeout=1000)
