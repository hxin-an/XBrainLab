from collections.abc import Callable
from typing import Any
from unittest.mock import patch

from scripts.dev.bounded_qt_shutdown import BoundedQtShutdown


class _App:
    def __init__(self) -> None:
        self.quit_on_last_window_closed = True
        self.quit_count = 0

    def setQuitOnLastWindowClosed(self, enabled: bool) -> None:
        self.quit_on_last_window_closed = enabled

    def quit(self) -> None:
        self.quit_count += 1

    def sendPostedEvents(self, _receiver, _event_type) -> None:
        pass

    def processEvents(self) -> None:
        pass


class _Window:
    def __init__(self) -> None:
        self.visible = True
        self.close_count = 0

    def isVisible(self) -> bool:
        return self.visible

    def close(self) -> None:
        self.close_count += 1


class _RuntimeState:
    def __init__(self, value: str) -> None:
        self.value = value


class _Runtime:
    def __init__(self, state: str) -> None:
        self.state = _RuntimeState(state)


class _Manager:
    def __init__(self, state: str = "cleanup_pending") -> None:
        self.assistant_runtime = _Runtime(state)
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


def test_bounded_shutdown_waits_for_window_and_runtime() -> None:
    now = [10.0]
    callbacks: list[Callable[[], None]] = []
    state: dict[str, Any] = {"status": "passed", "failure_reason": ""}
    app = _App()
    window = _Window()
    manager = _Manager()
    shutdown = BoundedQtShutdown(
        app=app,
        window=window,
        manager_provider=lambda: manager,
        state=state,
        schedule=lambda _delay, callback: callbacks.append(callback),
        now=lambda: now[0],
    )

    shutdown.start()

    assert app.quit_on_last_window_closed is False
    assert state["shutdown"] == {"status": "closing", "detail": ""}
    assert app.quit_count == 0
    callbacks.pop(0)()
    assert app.quit_count == 0

    manager.assistant_runtime.state.value = "closed"
    window.visible = False
    callbacks.pop(0)()

    assert state["shutdown"] == {"status": "completed", "detail": ""}
    assert app.quit_count == 1


def test_bounded_shutdown_timeout_fails_artifact_before_quit() -> None:
    now = [10.0]
    callbacks: list[Callable[[], None]] = []
    state: dict[str, Any] = {"status": "passed", "failure_reason": ""}
    app = _App()
    window = _Window()
    manager = _Manager()
    shutdown = BoundedQtShutdown(
        app=app,
        window=window,
        manager_provider=lambda: manager,
        state=state,
        schedule=lambda _delay, callback: callbacks.append(callback),
        now=lambda: now[0],
        grace_seconds=5.0,
    )

    shutdown.start()
    now[0] = 16.0
    callbacks.pop(0)()

    assert state["status"] == "failed"
    assert state["shutdown"]["status"] == "timed_out"
    assert "shutdown exceeded" in state["failure_reason"]
    assert manager.close_count == 1
    assert app.quit_count == 1


def test_event_loop_exit_before_terminal_shutdown_is_failure() -> None:
    state: dict[str, Any] = {"status": "passed", "failure_reason": ""}
    shutdown = BoundedQtShutdown(
        app=_App(),
        window=_Window(),
        manager_provider=lambda: _Manager(),
        state=state,
        schedule=lambda _delay, _callback: None,
        now=lambda: 10.0,
    )
    shutdown.start()

    shutdown.reconcile_after_event_loop()

    assert state["status"] == "failed"
    assert state["shutdown"]["status"] == "interrupted"


def test_event_loop_reconciliation_drains_deferred_qt_cleanup() -> None:
    app = _App()
    state: dict[str, Any] = {"status": "passed", "failure_reason": ""}
    shutdown = BoundedQtShutdown(
        app=app,
        window=_Window(),
        manager_provider=lambda: _Manager(state="closed"),
        state=state,
        schedule=lambda _delay, _callback: None,
        now=lambda: 10.0,
    )
    state["shutdown"] = {"status": "completed", "detail": ""}

    with patch(
        "scripts.dev.bounded_qt_shutdown.drain_qt_runtime_after_event_loop",
    ) as drain:
        shutdown.reconcile_after_event_loop()

    drain.assert_called_once_with(app)
