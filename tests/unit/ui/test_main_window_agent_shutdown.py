"""Qt lifecycle regressions for main-window assistant shutdown."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

from PyQt6 import sip
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtGui import QCloseEvent

from XBrainLab.ui.main_window import (
    ASSISTANT_SHUTDOWN_MAX_ATTEMPTS,
    MainWindow,
    global_exception_handler,
)


class _ThreadOwningAgentManager(QObject):
    """Small AgentManager stand-in with real Qt thread ownership."""

    def __init__(self, parent: QObject, *, failures_before_success: int | None):
        super().__init__(parent)
        self.close_calls = 0
        self._failures_before_success = failures_before_success
        self.command_thread = QThread(self)
        self.command_thread.start()

    def close(self) -> bool:
        self.close_calls += 1
        if not self.command_thread.isRunning():
            return True
        if self._failures_before_success is None:
            return False
        if self.close_calls <= self._failures_before_success:
            return False
        self.command_thread.quit()
        return self.command_thread.wait(1_000)

    def stop_for_test_cleanup(self) -> None:
        if self.command_thread.isRunning():
            self.command_thread.quit()
            self.command_thread.wait(1_000)


class _SignalDrivenAssistantRuntime(QObject):
    cleanup_finished = pyqtSignal(bool, str)

    def close(self) -> bool:
        return True


class _SignalDrivenAgentManager(QObject):
    """Assistant stand-in whose terminal cleanup arrives asynchronously."""

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.assistant_runtime = _SignalDrivenAssistantRuntime(self)
        self.close_calls = 0
        self.closed = False

    def close(self) -> bool:
        self.close_calls += 1
        return self.closed

    def complete(self) -> None:
        self.closed = True
        self.assistant_runtime.cleanup_finished.emit(True, "")


class _DownloadLifecycle(QObject):
    terminal = pyqtSignal(bool, str)

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.idle = False
        self.shutdown_requests = 0

    def request_shutdown(self) -> bool:
        self.shutdown_requests += 1
        return self.idle

    def complete(self) -> None:
        self.idle = True
        self.terminal.emit(False, "Cancelled by user")


class _PublicationBridge:
    def __init__(self):
        self.cleanup_requests = 0

    def cleanup(self) -> None:
        self.cleanup_requests += 1


class _DownloadOwningAgentManager(QObject):
    """Exercise the real AgentManager close method with focused dependencies."""

    def __init__(
        self,
        parent: QObject,
        *,
        publication_bridge: _PublicationBridge | None = None,
    ):
        super().__init__(parent)
        self.assistant_runtime = _SignalDrivenAssistantRuntime(self)
        self._assistant_runtime = self.assistant_runtime
        self.model_download_lifecycle = _DownloadLifecycle(self)
        self._model_download_lifecycle = self.model_download_lifecycle
        if publication_bridge is not None:
            self._application_publication_bridge = publication_bridge
        self._workflow_ui_handoff_host = MagicMock()
        self._assistant_turn_state = MagicMock()
        self._assistant_turn_state.shutdown_terminal.return_value = None
        self.close_calls = 0

    def close(self) -> bool:
        from XBrainLab.ui.components.agent_manager import AgentManager

        self.close_calls += 1
        return AgentManager.close(cast(AgentManager, self))


def _make_window(qtbot) -> MainWindow:
    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
    ):
        window = MainWindow(MagicMock())
    qtbot.addWidget(window)
    window._force_shutdown_requested = True
    window.show()
    qtbot.waitUntil(window.isVisible, timeout=1_000)
    return window


def test_forced_close_retries_failed_assistant_teardown_before_accepting(qtbot):
    window = _make_window(qtbot)
    manager = _ThreadOwningAgentManager(window, failures_before_success=3)
    window.agent_manager = manager

    try:
        assert window.close() is False
        assert window.isVisible() is True
        assert manager.command_thread.isRunning() is True
        assert sip.isdeleted(manager) is False

        qtbot.waitUntil(lambda: manager.close_calls == 4, timeout=2_000)
        qtbot.waitUntil(lambda: not window.isVisible(), timeout=1_000)

        assert manager.command_thread.isRunning() is False
    finally:
        manager.stop_for_test_cleanup()
        window.close()


def test_deferred_close_logs_user_shutdown_intent_once(qtbot):
    window = _make_window(qtbot)
    manager = _ThreadOwningAgentManager(window, failures_before_success=3)
    window.agent_manager = manager

    try:
        with patch("XBrainLab.ui.main_window.logger.info") as info:
            assert window.close() is False
            qtbot.waitUntil(lambda: manager.close_calls == 4, timeout=2_000)
            qtbot.waitUntil(lambda: not window.isVisible(), timeout=1_000)

        closing_messages = [
            call
            for call in info.call_args_list
            if call.args and call.args[0] == "Closing application..."
        ]
        assert len(closing_messages) == 1
    finally:
        manager.stop_for_test_cleanup()
        window.close()


def test_render_shutdown_pauses_and_cancelled_close_resumes_publication_renderer(
    qtbot,
):
    window = _make_window(qtbot)
    renderer = MagicMock()
    window._application_publication_renderer = renderer

    window._begin_close_attempt()
    renderer.pause_for_shutdown.assert_not_called()
    window._begin_desktop_render_shutdown()

    renderer.pause_for_shutdown.assert_called_once_with()

    window._restore_close_interaction()

    renderer.resume_after_cancelled_shutdown.assert_called_once_with()


def test_close_keeps_interaction_disabled_until_late_assistant_teardown_succeeds(
    qtbot,
    monkeypatch,
):
    monkeypatch.setattr(
        "XBrainLab.ui.main_window.ASSISTANT_SHUTDOWN_MAX_ATTEMPTS",
        2,
    )
    window = _make_window(qtbot)
    window._force_shutdown_requested = False
    manager = _ThreadOwningAgentManager(window, failures_before_success=3)
    window.agent_manager = manager

    try:
        assert window.close() is False
        qtbot.waitUntil(lambda: manager.close_calls >= 2, timeout=2_000)

        assert window._closing_in_progress is True
        assert window._shutdown_fence_active is False
        central_widget = window.centralWidget()
        assert central_widget is not None
        assert central_widget.isEnabled() is False

        qtbot.waitUntil(lambda: manager.close_calls == 4, timeout=2_000)
        qtbot.waitUntil(lambda: not window.isVisible(), timeout=1_000)
        assert manager.command_thread.isRunning() is False
    finally:
        manager.stop_for_test_cleanup()
        window.close()


def test_geometry_persistence_ignores_deleted_qt_window(qtbot):
    window = _make_window(qtbot)

    try:
        with (
            patch.object(
                window,
                "isMaximized",
                side_effect=RuntimeError(
                    "wrapped C/C++ object of type MainWindow has been deleted"
                ),
            ),
            patch(
                "XBrainLab.ui.window_geometry_lifecycle.sip.isdeleted",
                side_effect=[False, False, True],
            ),
        ):
            assert window.window_geometry.persist_before_close() is False
    finally:
        window.close()


def test_geometry_persistence_runs_after_every_shutdown_gate(qtbot):
    window = _make_window(qtbot)
    window._force_shutdown_requested = False
    call_order: list[str] = []
    event = QCloseEvent()

    with (
        patch.object(
            window,
            "_ensure_shutdown_fence_for_close",
            side_effect=lambda: call_order.append("fence") or True,
        ),
        patch.object(
            window,
            "_stop_training_for_close",
            side_effect=lambda: call_order.append("training") or True,
        ),
        patch.object(
            window,
            "_owned_ui_background_work_idle",
            side_effect=lambda: call_order.append("owned-workers") or True,
        ),
        patch.object(
            window,
            "_close_assistant_for_shutdown",
            side_effect=lambda: call_order.append("assistant") or True,
        ),
        patch.object(
            window.window_geometry,
            "persist_before_close",
            side_effect=lambda: call_order.append("geometry") or True,
        ),
        patch.object(
            window,
            "_delegate_close_event_if_alive",
            side_effect=lambda _event: call_order.append("qt-close") or True,
        ),
    ):
        window.closeEvent(event)

    assert call_order == [
        "fence",
        "training",
        "assistant",
        "owned-workers",
        "geometry",
        "qt-close",
    ]


def test_forced_close_releases_assistant_before_global_idle_gate(qtbot):
    window = _make_window(qtbot)
    call_order: list[str] = []
    event = QCloseEvent()

    with (
        patch.object(
            window,
            "_close_assistant_for_shutdown",
            side_effect=lambda: call_order.append("assistant") or True,
        ),
        patch.object(
            window,
            "_owned_ui_background_work_idle",
            side_effect=lambda: call_order.append("owned-workers") or False,
        ),
        patch.object(window, "_schedule_close_retry"),
    ):
        window.closeEvent(event)

    assert call_order == ["assistant", "owned-workers"]
    assert event.isAccepted() is False


def test_close_uses_watchdog_while_waiting_for_assistant_terminal_signal(qtbot):
    window = _make_window(qtbot)
    manager = _SignalDrivenAgentManager(window)
    window.agent_manager = manager

    assert window.close() is False
    assert window.isVisible() is True
    assert manager.close_calls == 1

    qtbot.waitUntil(lambda: manager.close_calls >= 2, timeout=1_000)

    manager.complete()

    qtbot.waitUntil(lambda: not window.isVisible(), timeout=1_000)
    assert manager.close_calls >= 2


def test_signal_driven_assistant_shutdown_logs_pending_once_while_watchdog_probes(
    qtbot,
):
    window = _make_window(qtbot)
    manager = _SignalDrivenAgentManager(window)
    window.agent_manager = manager

    try:
        with (
            patch("XBrainLab.ui.main_window.logger.info") as info,
            patch("XBrainLab.ui.main_window.logger.warning") as warning,
        ):
            assert window.close() is False
            qtbot.waitUntil(lambda: manager.close_calls >= 4, timeout=2_000)

            pending_messages = [
                call
                for call in info.call_args_list
                if call.args
                and call.args[0]
                == "Assistant teardown is pending; waiting for terminal cleanup."
            ]
            assert len(pending_messages) == 1
            assert not any(
                call.args and str(call.args[0]).startswith("Assistant teardown")
                for call in warning.call_args_list
            )

            manager.complete()
            qtbot.waitUntil(lambda: not window.isVisible(), timeout=1_000)
    finally:
        manager.complete()
        window.close()


def test_app_close_waits_for_active_model_download_terminal(qtbot):
    window = _make_window(qtbot)
    manager = _DownloadOwningAgentManager(window)
    window.agent_manager = manager

    assert not hasattr(manager, "_application_publication_bridge")
    assert window.close() is False
    assert window.isVisible() is True
    assert manager.model_download_lifecycle.shutdown_requests == 1

    manager.model_download_lifecycle.complete()

    qtbot.waitUntil(lambda: not window.isVisible(), timeout=1_000)
    assert manager.close_calls >= 2


def test_app_close_cleans_publication_bridge_while_stopping_download(qtbot):
    window = _make_window(qtbot)
    publication_bridge = _PublicationBridge()
    manager = _DownloadOwningAgentManager(
        window,
        publication_bridge=publication_bridge,
    )
    window.agent_manager = manager

    assert window.close() is False
    assert window.isVisible() is True
    assert publication_bridge.cleanup_requests == 1
    assert manager.model_download_lifecycle.shutdown_requests == 1

    manager.model_download_lifecycle.complete()

    qtbot.waitUntil(lambda: not window.isVisible(), timeout=1_000)
    assert manager.close_calls >= 2


def test_shutdown_attempt_counter_saturates_in_noninteractive_recovery(qtbot):
    window = _make_window(qtbot)
    window._assistant_shutdown_attempts = ASSISTANT_SHUTDOWN_MAX_ATTEMPTS
    event = MagicMock()

    with (
        patch.object(window, "_schedule_close_retry") as schedule_retry,
        patch("XBrainLab.ui.main_window.logger.warning") as warning,
    ):
        for _ in range(3):
            window._handle_assistant_shutdown_failure(event)

    assert event.ignore.call_count == 3
    assert window._assistant_shutdown_attempts == ASSISTANT_SHUTDOWN_MAX_ATTEMPTS
    assert window._shutdown_only_mode is True
    assert schedule_retry.call_count == 3
    warning.assert_called_once_with(
        "Assistant teardown exceeded the %sms shutdown watchdog; "
        "continuing safe cleanup.",
        12_000,
    )


def test_global_exception_handler_uses_safe_central_presenter(qtbot):
    del qtbot
    sensitive = (
        r"PermissionError C:\Users\alice\.cache "
        r"\\server\private token=hf_super_secret"
    )
    error = RuntimeError(sensitive)

    with (
        patch(
            "XBrainLab.ui.main_window.present_unexpected_error",
            create=True,
        ) as present,
        patch("XBrainLab.ui.main_window.QMessageBox"),
    ):
        global_exception_handler(RuntimeError, error, None)

    present.assert_called_once()
    context = present.call_args.args[1]
    assert sensitive not in context.value.message
    assert present.call_args.kwargs["error_info"] == (RuntimeError, error, None)
