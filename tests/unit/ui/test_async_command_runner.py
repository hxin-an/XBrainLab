"""Behavioral lifecycle tests for the Qt application command runner."""

from __future__ import annotations

import sys
import threading
from types import SimpleNamespace
from typing import Any, cast

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QObject, QRunnable, QThread
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.application import ChangedState, CommandResult, QueryStateCommand
from XBrainLab.ui import async_command_runner, refresh_coordinator
from XBrainLab.ui.async_command_runner import (
    AsyncCommandCleanup,
    AsyncCommandDelivery,
    AsyncCommandRegistry,
    QtApplicationCommandRunner,
)
from XBrainLab.ui.core.worker import WorkerSignals
from XBrainLab.ui.interaction_outcome import (
    InteractionCompletionSession,
    InteractionCompletionStatus,
)


class _Signal:
    def __init__(self, name: str, fail_stage: str) -> None:
        self.name = name
        self.fail_stage = fail_stage

    def connect(self, _slot) -> None:
        if self.name == self.fail_stage:
            raise RuntimeError(f"{self.name} connect failed")


class _FakeWorker:
    def __init__(self, fail_stage: str) -> None:
        self.signals = SimpleNamespace(
            result=_Signal("result_connect", fail_stage),
            error=_Signal("error_connect", fail_stage),
            finished=_Signal("finished_connect", fail_stage),
        )


class _FinishedOnlyWorker(QRunnable):
    """Malformed worker used to prove finished-without-outcome is terminal."""

    def __init__(self) -> None:
        super().__init__()
        self.signals = WorkerSignals()

    def run(self) -> None:
        self.signals.finished.emit()


class _FailingRegistry(AsyncCommandRegistry):
    def register(self, handle) -> None:
        raise RuntimeError("registry rejected command handle")


def _is_gui_thread() -> bool:
    application = QCoreApplication.instance()
    return application is not None and QThread.currentThread() == application.thread()


@pytest.mark.parametrize(
    "failure_stage",
    [
        "worker",
        "active_append",
        "delivery",
        "cleanup",
        "result_connect",
        "error_connect",
        "finished_connect",
        "pool_lookup",
        "pool_start",
    ],
)
def test_partial_setup_failure_rolls_back_every_acquired_resource(
    qtbot,
    failure_stage,
) -> None:
    context = QWidget()
    main_window = SimpleNamespace()
    cast(Any, context).main_window = main_window
    qtbot.addWidget(context)
    busy_states: list[bool] = []
    cast(Any, context).set_busy = lambda busy: busy_states.append(bool(busy))
    registry = (
        _FailingRegistry()
        if failure_stage == "active_append"
        else AsyncCommandRegistry()
    )
    receivers: list[QObject] = []

    def worker_factory(_execute):
        if failure_stage == "worker":
            raise RuntimeError("worker construction failed")
        return _FakeWorker(failure_stage)

    def delivery_factory(**kwargs):
        if failure_stage == "delivery":
            raise RuntimeError("delivery construction failed")
        receiver = AsyncCommandDelivery(**kwargs)
        receivers.append(receiver)
        return receiver

    def cleanup_factory(finish):
        if failure_stage == "cleanup":
            raise RuntimeError("cleanup construction failed")
        receiver = AsyncCommandCleanup(finish)
        receivers.append(receiver)
        return receiver

    class _Pool:
        def start(self, _worker) -> None:
            if failure_stage == "pool_start":
                raise RuntimeError("thread pool start failed")

    def thread_pool_factory():
        if failure_stage == "pool_lookup":
            raise RuntimeError("thread pool lookup failed")
        return _Pool()

    started = QtApplicationCommandRunner(
        context=context,
        command=QueryStateCommand(),
        execute=lambda: _result(),
        on_result=lambda _result: None,
        on_error=None,
        refresh=True,
        busy_target=None,
        allow_during_shutdown=False,
        delivery_factory=delivery_factory,
        cleanup_factory=cleanup_factory,
        thread_pool_factory=cast(Any, thread_pool_factory),
        worker_factory=cast(Any, worker_factory),
        registry=registry,
    ).start()

    assert started is False
    assert busy_states == [True, False]
    assert registry.active_count(context) == 0
    assert id(main_window) not in refresh_coordinator._COMMAND_EXECUTING_MAIN_WINDOWS
    if receivers:
        qtbot.waitUntil(
            lambda: all(sip.isdeleted(receiver) for receiver in receivers),
            timeout=1_000,
        )


@pytest.mark.parametrize("failure_stage", ["refresh", "result", "error"])
def test_real_threadpool_contains_callback_exceptions_and_cleans_up(
    qtbot,
    monkeypatch,
    failure_stage,
) -> None:
    context = QWidget()
    main_window = SimpleNamespace()
    cast(Any, context).main_window = main_window
    qtbot.addWidget(context)
    busy_states: list[bool] = []
    busy_threads: list[bool] = []

    def set_busy(busy: bool) -> None:
        busy_states.append(bool(busy))
        busy_threads.append(_is_gui_thread())

    cast(Any, context).set_busy = set_busy
    registry = AsyncCommandRegistry()
    worker_started = threading.Event()
    worker_release = threading.Event()
    receivers: list[QObject] = []
    uncaught: list[tuple[Any, ...]] = []
    callback_threads: list[bool] = []
    refresh_attempts: list[bool] = []
    result_attempts: list[CommandResult] = []
    error_attempts: list[tuple] = []
    monkeypatch.setattr(sys, "excepthook", lambda *args: uncaught.append(args))

    if failure_stage == "refresh":

        def fail_refresh(*_args) -> None:
            refresh_attempts.append(True)
            callback_threads.append(_is_gui_thread())
            raise RuntimeError("refresh failed")

        monkeypatch.setattr(
            async_command_runner,
            "refresh_after_command",
            fail_refresh,
        )

    def execute() -> CommandResult:
        worker_started.set()
        assert worker_release.wait(timeout=2.0)
        if failure_stage == "error":
            raise RuntimeError("worker failed")
        return _result()

    def on_result(result: CommandResult) -> None:
        result_attempts.append(result)
        callback_threads.append(_is_gui_thread())
        if failure_stage == "result":
            raise RuntimeError("result callback failed")

    def on_error(error: tuple) -> None:
        error_attempts.append(error)
        callback_threads.append(_is_gui_thread())
        if failure_stage == "error":
            raise RuntimeError("error callback failed")

    def delivery_factory(**kwargs):
        receiver = AsyncCommandDelivery(**kwargs)
        receivers.append(receiver)
        return receiver

    def cleanup_factory(finish):
        receiver = AsyncCommandCleanup(finish)
        receivers.append(receiver)
        return receiver

    runner = QtApplicationCommandRunner(
        context=context,
        command=QueryStateCommand(),
        execute=execute,
        on_result=on_result,
        on_error=on_error,
        refresh=failure_stage == "refresh",
        busy_target=None,
        allow_during_shutdown=False,
        delivery_factory=delivery_factory,
        cleanup_factory=cleanup_factory,
        registry=registry,
    )

    assert runner.start() is True
    assert worker_started.wait(timeout=1.0)
    assert registry.active_count(context) == 1
    worker_release.set()
    qtbot.waitUntil(lambda: registry.active_count(context) == 0, timeout=2_000)
    qtbot.waitUntil(
        lambda: all(sip.isdeleted(receiver) for receiver in receivers),
        timeout=2_000,
    )

    assert busy_states == [True, False]
    assert busy_threads == [True, True]
    assert uncaught == []
    assert callback_threads and all(callback_threads)
    assert refresh_attempts == ([True] if failure_stage == "refresh" else [])
    assert result_attempts == ([] if failure_stage == "error" else [_result()])
    assert len(error_attempts) == (1 if failure_stage == "error" else 0)
    assert id(main_window) not in refresh_coordinator._COMMAND_EXECUTING_MAIN_WINDOWS


def _result() -> CommandResult:
    return CommandResult.success_result(
        command_name="query_state",
        message="ok",
        state=None,
        changed_state=ChangedState(),
    )


def test_cleanup_defers_finished_during_reentrant_outcome_delivery(qtbot) -> None:
    context = QWidget()
    qtbot.addWidget(context)
    events: list[str] = []
    cleanup = AsyncCommandCleanup(lambda: events.append("finished"))

    def on_result(_result: CommandResult) -> None:
        events.append("result-start")
        cleanup.handle_finished()
        assert events == ["result-start"]
        events.append("result-end")

    delivery = AsyncCommandDelivery(
        context=context,
        command=QueryStateCommand(),
        on_result=on_result,
        on_error=None,
        refresh=False,
        allow_during_shutdown=False,
        parent=context,
    )
    cleanup.bind_delivery(delivery)

    cleanup.handle_result(_result())
    cleanup.handle_finished()

    assert events == ["result-start", "result-end", "finished"]


def test_finished_only_worker_fails_interaction_session_and_releases_ownership(
    qtbot,
) -> None:
    context = QWidget()
    cast(Any, context).main_window = SimpleNamespace()
    qtbot.addWidget(context)
    cast(Any, context).set_busy = lambda _busy: None
    terminal = []
    session = InteractionCompletionSession(
        request_id="request-finished-only",
        command_name="query_state",
        on_terminal=terminal.append,
    )
    callbacks = session.prepare_command(
        context=context,
        on_result=lambda _result: None,
        on_error=None,
    )
    registry = AsyncCommandRegistry()
    runner = QtApplicationCommandRunner(
        context=context,
        command=QueryStateCommand(),
        execute=_result,
        on_result=callbacks.on_result,
        on_error=callbacks.on_error,
        on_finished=callbacks.on_finished,
        refresh=False,
        busy_target=context,
        allow_during_shutdown=False,
        worker_factory=lambda _execute: _FinishedOnlyWorker(),
        registry=registry,
    )

    assert runner.start() is True
    callbacks.mark_started(True)
    qtbot.waitUntil(lambda: bool(terminal), timeout=2_000)
    qtbot.waitUntil(lambda: registry.active_count(context) == 0, timeout=2_000)

    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.FAILED
    assert terminal[0].message == (
        "The asynchronous UI command finished without returning a result."
    )


def test_chained_commands_keep_shared_busy_target_disabled_until_both_finish(
    qtbot,
) -> None:
    target = QWidget()
    cast(Any, target).main_window = SimpleNamespace()
    qtbot.addWidget(target)
    busy_states: list[bool] = []
    cast(Any, target).set_busy = lambda busy: busy_states.append(bool(busy))
    registry = AsyncCommandRegistry()
    started = [threading.Event(), threading.Event()]
    releases = [threading.Event(), threading.Event()]

    def execute(index: int) -> CommandResult:
        started[index].set()
        assert releases[index].wait(timeout=2.0)
        return _result()

    runners = [
        QtApplicationCommandRunner(
            context=target,
            command=QueryStateCommand(),
            execute=lambda index=index: execute(index),
            on_result=lambda _result: None,
            on_error=None,
            refresh=False,
            busy_target=target,
            allow_during_shutdown=False,
            registry=registry,
        )
        for index in range(2)
    ]

    assert all(runner.start() for runner in runners)
    assert all(event.wait(timeout=1.0) for event in started)
    assert busy_states == [True]

    releases[0].set()
    qtbot.waitUntil(lambda: registry.active_count(target) == 1, timeout=2_000)
    assert busy_states == [True]

    releases[1].set()
    qtbot.waitUntil(lambda: registry.active_count(target) == 0, timeout=2_000)
    assert busy_states == [True, False]


def test_deleted_owner_drops_result_but_releases_async_command_ownership(qtbot) -> None:
    context = QWidget()
    cast(Any, context).main_window = SimpleNamespace()
    qtbot.addWidget(context)
    cast(Any, context).set_busy = lambda _busy: None
    registry = AsyncCommandRegistry()
    worker_started = threading.Event()
    worker_release = threading.Event()
    delivered: list[CommandResult] = []
    terminal = []
    session = InteractionCompletionSession(
        request_id="request-deleted-owner",
        command_name="query_state",
        on_terminal=terminal.append,
    )
    callbacks = session.prepare_command(
        context=context,
        on_result=delivered.append,
        on_error=None,
    )

    def execute() -> CommandResult:
        worker_started.set()
        assert worker_release.wait(timeout=2.0)
        return _result()

    runner = QtApplicationCommandRunner(
        context=context,
        command=QueryStateCommand(),
        execute=execute,
        on_result=callbacks.on_result,
        on_error=callbacks.on_error,
        on_finished=callbacks.on_finished,
        refresh=False,
        busy_target=context,
        allow_during_shutdown=False,
        registry=registry,
    )

    assert runner.start() is True
    callbacks.mark_started(True)
    assert worker_started.wait(timeout=1.0)
    context.deleteLater()
    qtbot.waitUntil(lambda: sip.isdeleted(context), timeout=1_000)
    worker_release.set()
    qtbot.waitUntil(lambda: registry.active_count(context) == 0, timeout=2_000)

    assert delivered == []
    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.FAILED
    assert async_command_runner._ASYNC_BUSY_STATE.active_count(context) == 0


def test_shutdown_drops_result_and_still_clears_busy_state(qtbot) -> None:
    context = QWidget()
    main_window = SimpleNamespace(_closing_in_progress=False)
    cast(Any, context).main_window = main_window
    qtbot.addWidget(context)
    busy_states: list[bool] = []
    cast(Any, context).set_busy = lambda busy: busy_states.append(bool(busy))
    registry = AsyncCommandRegistry()
    worker_started = threading.Event()
    worker_release = threading.Event()
    delivered: list[CommandResult] = []

    def execute() -> CommandResult:
        worker_started.set()
        assert worker_release.wait(timeout=2.0)
        return _result()

    runner = QtApplicationCommandRunner(
        context=context,
        command=QueryStateCommand(),
        execute=execute,
        on_result=delivered.append,
        on_error=None,
        refresh=False,
        busy_target=context,
        allow_during_shutdown=False,
        registry=registry,
    )

    assert runner.start() is True
    assert worker_started.wait(timeout=1.0)
    main_window._closing_in_progress = True
    worker_release.set()
    qtbot.waitUntil(lambda: registry.active_count(context) == 0, timeout=2_000)

    assert delivered == []
    assert busy_states == [True, False]


def test_shutdown_drops_screen_callback_but_still_settles_interaction_session(
    qtbot,
) -> None:
    context = QWidget()
    main_window = SimpleNamespace(_closing_in_progress=False)
    cast(Any, context).main_window = main_window
    qtbot.addWidget(context)
    cast(Any, context).set_busy = lambda _busy: None
    registry = AsyncCommandRegistry()
    worker_started = threading.Event()
    worker_release = threading.Event()
    screen_results: list[CommandResult] = []
    terminal = []
    session = InteractionCompletionSession(
        request_id="request-shutdown",
        command_name="query_state",
        on_terminal=terminal.append,
    )
    callbacks = session.prepare_command(
        context=context,
        on_result=lambda result: screen_results.append(result),
        on_error=None,
    )

    def execute() -> CommandResult:
        worker_started.set()
        assert worker_release.wait(timeout=2.0)
        return _result()

    runner = QtApplicationCommandRunner(
        context=context,
        command=QueryStateCommand(),
        execute=execute,
        on_result=callbacks.on_result,
        on_error=callbacks.on_error,
        on_finished=callbacks.on_finished,
        refresh=False,
        busy_target=context,
        allow_during_shutdown=False,
        registry=registry,
    )

    assert runner.start() is True
    callbacks.mark_started(True)
    assert worker_started.wait(timeout=1.0)
    main_window._closing_in_progress = True
    worker_release.set()
    qtbot.waitUntil(lambda: bool(terminal), timeout=2_000)
    qtbot.waitUntil(lambda: registry.active_count(context) == 0, timeout=2_000)

    assert screen_results == []
    assert len(terminal) == 1
    assert terminal[0].status is InteractionCompletionStatus.FAILED
