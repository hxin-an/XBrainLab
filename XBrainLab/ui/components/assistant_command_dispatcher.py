"""Thread-safe command dispatch for the in-app assistant controller."""

from __future__ import annotations

from contextlib import suppress
from typing import Any, cast

from PyQt6.QtCore import QEventLoop, QObject, QThread, QTimer, pyqtSignal

from XBrainLab.backend.utils.logger import logger


class _ControllerShutdownBridge(QObject):
    """Close a controller on its command thread, then return it to the GUI."""

    finished = pyqtSignal(bool, str)

    def __init__(self, controller: QObject, gui_thread: QThread):
        super().__init__()
        self._controller = controller
        self._gui_thread = gui_thread

    def shutdown(self) -> None:
        ok = True
        message = ""
        try:
            close = getattr(self._controller, "close", None)
            if callable(close):
                result = close()
                if result is False:
                    ok = False
                    message = "Assistant controller did not finish shutdown."
        except Exception as exc:
            ok = False
            message = str(exc)
            logger.exception("Assistant controller shutdown failed")

        if not ok:
            self.finished.emit(False, message)
            return
        self._controller.moveToThread(self._gui_thread)
        self.finished.emit(ok, message)
        self.moveToThread(self._gui_thread)


class AssistantCommandDispatcher(QObject):
    """Queue controller commands away from the GUI and own thread shutdown."""

    initialize_requested = pyqtSignal()
    input_requested = pyqtSignal(str)
    stop_requested = pyqtSignal()
    model_requested = pyqtSignal(str)
    mode_requested = pyqtSignal(str)
    reset_requested = pyqtSignal()
    confirmation_requested = pyqtSignal(bool)
    debug_requested = pyqtSignal(str, object)
    shutdown_requested = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller: Any | None = None
        self._command_thread: QThread | None = None
        self._shutdown_bridge: _ControllerShutdownBridge | None = None
        self._queued = False
        self._closed = False

    @property
    def command_thread(self) -> QThread | None:
        """Return the command thread for lifecycle tests and diagnostics."""
        return self._command_thread

    @property
    def is_queued(self) -> bool:
        return self._queued

    def bind(self, controller: Any) -> None:
        """Bind one controller and create a dedicated command thread when possible."""
        if self._controller is not None:
            raise RuntimeError("Assistant command dispatcher is already bound.")
        self._controller = controller
        self._closed = False

        runtime_thread = getattr(controller, "worker_thread", None)
        gui_thread = self.thread()
        if (
            not isinstance(controller, QObject)
            or not isinstance(runtime_thread, QThread)
            or gui_thread is None
        ):
            return

        command_thread = QThread(self)
        command_thread.setObjectName("AssistantCommandThread")
        command_thread.start()
        controller.moveToThread(command_thread)
        qt_controller = cast(Any, controller)

        shutdown_bridge = _ControllerShutdownBridge(controller, gui_thread)
        shutdown_bridge.moveToThread(command_thread)
        self.initialize_requested.connect(qt_controller.initialize)
        self.input_requested.connect(qt_controller.handle_user_input)
        self.stop_requested.connect(qt_controller.stop_generation)
        self.model_requested.connect(qt_controller.set_model)
        self.mode_requested.connect(qt_controller.set_execution_mode)
        self.reset_requested.connect(qt_controller.reset_conversation)
        self.confirmation_requested.connect(qt_controller.on_user_confirmed)
        self.debug_requested.connect(qt_controller.execute_debug_tool)
        self.shutdown_requested.connect(shutdown_bridge.shutdown)

        self._command_thread = command_thread
        self._shutdown_bridge = shutdown_bridge
        self._queued = True

    def initialize(self) -> None:
        self._emit_or_call(self.initialize_requested, "initialize")

    def submit(self, text: str) -> None:
        self._emit_or_call(self.input_requested, "handle_user_input", text)

    def stop(self) -> None:
        self._emit_or_call(self.stop_requested, "stop_generation")

    def set_model(self, model_name: str) -> None:
        self._emit_or_call(self.model_requested, "set_model", model_name)

    def set_mode(self, mode: str) -> None:
        self._emit_or_call(self.mode_requested, "set_execution_mode", mode)

    def reset(self) -> None:
        self._emit_or_call(self.reset_requested, "reset_conversation")

    def confirm(self, approved: bool) -> None:
        self._emit_or_call(
            self.confirmation_requested,
            "on_user_confirmed",
            approved,
        )

    def debug(self, tool_name: str, params: dict) -> None:
        self._emit_or_call(
            self.debug_requested,
            "execute_debug_tool",
            tool_name,
            dict(params),
        )

    def _emit_or_call(self, signal, method_name: str, *args: Any) -> None:
        if self._controller is None or self._closed:
            return
        if self._queued:
            signal.emit(*args)
            return
        method = getattr(self._controller, method_name, None)
        if callable(method):
            method(*args)

    def close(self) -> bool:
        """Stop controller resources and the command thread exactly once."""
        if self._closed:
            return True
        controller = self._controller
        if controller is None:
            self._closed = True
            return True
        if not self._queued:
            close = getattr(controller, "close", None)
            if callable(close) and close() is False:
                return False
            self._closed = True
            return True

        command_thread = self._command_thread
        shutdown_bridge = self._shutdown_bridge
        if command_thread is None or shutdown_bridge is None:
            raise RuntimeError("Assistant command thread is missing during shutdown.")

        completed = {"value": False, "ok": False}
        wait_loop = QEventLoop()

        def on_shutdown_finished(ok: bool, message: str) -> None:
            completed["value"] = True
            completed["ok"] = ok
            if not ok:
                logger.error("Assistant shutdown completed with errors: %s", message)
            wait_loop.quit()

        shutdown_bridge.finished.connect(on_shutdown_finished)
        QTimer.singleShot(6000, wait_loop.quit)
        self.shutdown_requested.emit()
        wait_loop.exec()
        with suppress(RuntimeError, TypeError):
            shutdown_bridge.finished.disconnect(on_shutdown_finished)

        if not completed["value"] or not completed["ok"]:
            logger.error("Assistant controller remains active after shutdown failure")
            return False

        command_thread.quit()
        stopped = command_thread.wait(3000)
        if not stopped:
            logger.error("Assistant command thread did not stop within timeout")
            return False

        self._queued = False
        self._command_thread = None
        self._shutdown_bridge = None
        self._closed = True
        return True
