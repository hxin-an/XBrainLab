"""Thread-safe command dispatch for the in-app assistant controller."""

from __future__ import annotations

from enum import Enum
from typing import Any, cast

from PyQt6 import sip
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot

from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.public_diagnostics import (
    PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER,
    DiagnosticTextLayout,
    public_diagnostic_text,
)
from XBrainLab.llm.agent.confirmation import AgentConfirmationResolution
from XBrainLab.llm.agent.turn import (
    AssistantDebugToolRequest,
    AssistantTurnDeliveryAcknowledgement,
    AssistantTurnDeliveryPhase,
    AssistantTurnRequest,
)
from XBrainLab.llm.agent.ui_handoff import WorkflowUiHandoffResolution
from XBrainLab.llm.core.runtime_selection import AssistantRuntimeLaunchSpec

_QUEUED_CONTROLLER_FAILURE_MESSAGE = (
    "Assistant controller could not complete the queued request."
)
_CONTROLLER_SHUTDOWN_FAILURE_MESSAGE = (
    "Assistant controller could not complete shutdown."
)


class AssistantCommandDispatcherState(str, Enum):
    """Admission and cleanup state for one bound controller."""

    OPEN = "open"
    CLOSING = "closing"
    CONTROLLER_CLOSED = "controller_closed"
    CLOSED = "closed"


class _ControllerShutdownBridge(QObject):
    """Guard controller delivery/shutdown on its command thread."""

    finished = pyqtSignal(bool, str)
    turn_delivery_acknowledged = pyqtSignal(object)

    def __init__(self, controller: QObject, gui_thread: QThread):
        super().__init__()
        self._controller = controller
        self._gui_thread = gui_thread
        self._shutdown_pending = False
        self._shutdown_finished = False
        shutdown_signal = getattr(controller, "shutdown_finished", None)
        if shutdown_signal is not None and callable(
            getattr(shutdown_signal, "connect", None)
        ):
            shutdown_signal.connect(
                self._on_async_shutdown_finished,
                Qt.ConnectionType.QueuedConnection,
            )

    @pyqtSlot(object)
    def deliver_turn(self, payload: object) -> None:
        """Invoke the queued controller slot behind an exception boundary."""
        if not isinstance(payload, AssistantTurnRequest):
            logger.error("Ignored untyped queued assistant turn delivery: %r", payload)
            return
        try:
            result = self._invoke_turn_handler(payload)
        except Exception:
            logger.exception(
                "Assistant controller rejected queued turn %s during delivery",
                payload.turn_id,
            )
            acknowledgement = AssistantTurnDeliveryAcknowledgement(
                correlation=payload.correlation,
                phase=AssistantTurnDeliveryPhase.ERROR,
                message=_QUEUED_CONTROLLER_FAILURE_MESSAGE,
            )
        else:
            acknowledgement = self._normalize_turn_delivery(payload, result)
        self.turn_delivery_acknowledged.emit(acknowledgement)

    @pyqtSlot(object)
    def deliver_debug(self, payload: object) -> None:
        """Invoke one correlated diagnostic request on the controller thread."""
        if not isinstance(payload, AssistantDebugToolRequest):
            logger.error("Ignored untyped queued assistant debug delivery: %r", payload)
            return
        try:
            result = self._invoke_debug_handler(payload)
        except Exception:
            logger.exception(
                "Assistant controller rejected queued debug turn %s during delivery",
                payload.turn_id,
            )
            acknowledgement = AssistantTurnDeliveryAcknowledgement(
                correlation=payload.correlation,
                phase=AssistantTurnDeliveryPhase.ERROR,
                message=_QUEUED_CONTROLLER_FAILURE_MESSAGE,
            )
        else:
            acknowledgement = self._normalize_turn_delivery(payload, result)
        self.turn_delivery_acknowledged.emit(acknowledgement)

    def _invoke_turn_handler(self, request: AssistantTurnRequest) -> object:
        handler = getattr(self._controller, "handle_user_turn", None)
        if not callable(handler):
            raise RuntimeError("Assistant controller turn handler is unavailable.")
        return handler(request)

    def _invoke_debug_handler(self, request: AssistantDebugToolRequest) -> object:
        handler = getattr(self._controller, "execute_debug_tool", None)
        if not callable(handler):
            raise RuntimeError("Assistant controller debug handler is unavailable.")
        return handler(request)

    @staticmethod
    def _normalize_turn_delivery(
        request: AssistantTurnRequest | AssistantDebugToolRequest,
        result: object,
    ) -> AssistantTurnDeliveryAcknowledgement:
        if isinstance(result, AssistantTurnDeliveryAcknowledgement):
            if result.correlation == request.correlation:
                return result
            return AssistantTurnDeliveryAcknowledgement(
                correlation=request.correlation,
                phase=AssistantTurnDeliveryPhase.ERROR,
                message="Controller returned a mismatched turn acknowledgement.",
            )
        phase = (
            AssistantTurnDeliveryPhase.REJECTED
            if result is False
            else AssistantTurnDeliveryPhase.ACCEPTED
        )
        return AssistantTurnDeliveryAcknowledgement(
            correlation=request.correlation,
            phase=phase,
        )

    @pyqtSlot()
    def shutdown(self) -> None:
        if self._shutdown_pending or self._shutdown_finished:
            return
        try:
            close = getattr(self._controller, "close", None)
            result = close() if callable(close) else True
        except Exception:
            logger.exception("Assistant controller shutdown failed")
            self._finish(False, _CONTROLLER_SHUTDOWN_FAILURE_MESSAGE)
            return
        if result is False:
            if self._shutdown_finished:
                return
            shutdown_signal = getattr(self._controller, "shutdown_finished", None)
            if shutdown_signal is None:
                self._finish(
                    False,
                    "Assistant controller did not finish shutdown.",
                )
                return
            self._shutdown_pending = True
            return
        self._finish(True, "")

    @pyqtSlot(bool, str)
    def _on_async_shutdown_finished(self, ok: bool, message: str) -> None:
        """Complete a controller close that intentionally returned pending."""
        if self._shutdown_finished:
            return
        self._shutdown_pending = False
        self._finish(
            ok if type(ok) is bool else False,
            _public_dispatch_message(
                message,
                fallback=_CONTROLLER_SHUTDOWN_FAILURE_MESSAGE,
                allow_empty=ok is True,
            ),
        )

    def _finish(self, ok: bool, message: str) -> None:
        """Publish one terminal and restore GUI-thread ownership on success."""
        if self._shutdown_finished:
            return
        self._shutdown_pending = False
        safe_ok = ok if type(ok) is bool else False
        if safe_ok:
            self._shutdown_finished = True
            self._controller.moveToThread(self._gui_thread)
            self.moveToThread(self._gui_thread)
        safe_message = _public_dispatch_message(
            message,
            fallback=_CONTROLLER_SHUTDOWN_FAILURE_MESSAGE,
            allow_empty=safe_ok,
        )
        self.finished.emit(safe_ok, safe_message)


def _public_dispatch_message(
    value: object,
    *,
    fallback: str,
    allow_empty: bool,
) -> str:
    rendered = public_diagnostic_text(
        value,
        layout=DiagnosticTextLayout.SINGLE_LINE,
    )
    if rendered == PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER:
        return fallback
    if not rendered and not allow_empty:
        return fallback
    return rendered


class AssistantCommandDispatcher(QObject):
    """Queue controller commands away from the GUI and own thread shutdown."""

    _REQUIRED_CONTROLLER_METHODS = (
        "handle_user_turn",
        "initialize",
        "stop_generation",
        "set_model",
        "reset_conversation",
        "on_user_confirmation_resolved",
        "on_workflow_ui_handoff_resolved",
        "execute_debug_tool",
        "close",
    )

    initialize_requested = pyqtSignal(object)
    input_requested = pyqtSignal(object)
    stop_requested = pyqtSignal()
    model_requested = pyqtSignal(object)
    reset_requested = pyqtSignal()
    confirmation_requested = pyqtSignal(object)
    workflow_ui_handoff_resolved_requested = pyqtSignal(object)
    debug_requested = pyqtSignal(object)
    shutdown_requested = pyqtSignal()
    cleanup_finished = pyqtSignal(bool, str)
    turn_delivery_acknowledged = pyqtSignal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller: Any | None = None
        self._command_thread: QThread | None = None
        self._shutdown_bridge: _ControllerShutdownBridge | None = None
        self._queued = False
        self._state = AssistantCommandDispatcherState.OPEN
        self._shutdown_in_flight = False

    @property
    def command_thread(self) -> QThread | None:
        """Return the command thread for lifecycle tests and diagnostics."""
        return self._command_thread

    @property
    def is_queued(self) -> bool:
        return self._queued

    @property
    def state(self) -> AssistantCommandDispatcherState:
        return self._state

    @property
    def accepts_commands(self) -> bool:
        """Return transport availability, not assistant runtime readiness.

        ``AssistantRuntimeLifecycle`` owns the product admission decision. This
        lower-level guard only prevents delivery after transport shutdown starts.
        """
        return self._state is AssistantCommandDispatcherState.OPEN

    def bind(self, controller: Any) -> None:
        """Bind one controller and create a dedicated command thread when possible."""
        if self._controller is not None:
            raise RuntimeError("Assistant command dispatcher is already bound.")
        if self._state is not AssistantCommandDispatcherState.OPEN:
            raise RuntimeError("Closed assistant command dispatcher cannot be rebound.")
        self._validate_controller_contract(controller)
        self._controller = controller

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
        qt_controller = cast(Any, controller)

        shutdown_bridge = _ControllerShutdownBridge(controller, gui_thread)
        controller.moveToThread(command_thread)
        shutdown_bridge.moveToThread(command_thread)
        self.initialize_requested.connect(qt_controller.initialize)
        self.input_requested.connect(shutdown_bridge.deliver_turn)
        shutdown_bridge.turn_delivery_acknowledged.connect(
            self.turn_delivery_acknowledged.emit
        )
        self.stop_requested.connect(qt_controller.stop_generation)
        self.model_requested.connect(qt_controller.set_model)
        self.reset_requested.connect(qt_controller.reset_conversation)
        self.confirmation_requested.connect(qt_controller.on_user_confirmation_resolved)
        self.workflow_ui_handoff_resolved_requested.connect(
            qt_controller.on_workflow_ui_handoff_resolved
        )
        self.debug_requested.connect(shutdown_bridge.deliver_debug)
        self.shutdown_requested.connect(shutdown_bridge.shutdown)
        shutdown_bridge.finished.connect(self._on_controller_shutdown_finished)
        command_thread.finished.connect(self._on_command_thread_finished)

        self._command_thread = command_thread
        self._shutdown_bridge = shutdown_bridge
        self._queued = True
        command_thread.start()

    @classmethod
    def _validate_controller_contract(cls, controller: Any) -> None:
        """Reject incomplete controllers before allocating transport resources."""
        missing = [
            name
            for name in cls._REQUIRED_CONTROLLER_METHODS
            if not callable(getattr(controller, name, None))
        ]
        if missing:
            raise TypeError(
                "Assistant controller is missing required contract methods: "
                + ", ".join(missing)
            )

    def initialize(self, launch_spec: AssistantRuntimeLaunchSpec) -> bool:
        return self._emit_or_call(
            self.initialize_requested,
            "initialize",
            launch_spec,
        )

    def submit(self, request: AssistantTurnRequest) -> bool:
        """Queue an already-admitted turn; lifecycle owns busy state."""
        if not isinstance(request, AssistantTurnRequest):
            raise TypeError("Assistant submit requires a correlated turn request.")
        return self._emit_or_call(self.input_requested, "handle_user_turn", request)

    def stop(self) -> bool:
        return self._emit_or_call(self.stop_requested, "stop_generation")

    def set_model(self, launch_spec: AssistantRuntimeLaunchSpec) -> bool:
        return self._emit_or_call(self.model_requested, "set_model", launch_spec)

    def reset(self) -> bool:
        return self._emit_or_call(self.reset_requested, "reset_conversation")

    def confirm(self, resolution: AgentConfirmationResolution) -> bool:
        """Dispatch one correlated assistant action resolution."""
        if not isinstance(resolution, AgentConfirmationResolution):
            raise TypeError("Assistant confirmation resolution must be typed.")
        return self._emit_or_call(
            self.confirmation_requested,
            "on_user_confirmation_resolved",
            resolution,
        )

    def resolve_ui_handoff(
        self,
        resolution: WorkflowUiHandoffResolution,
    ) -> bool:
        """Dispatch one correlated product-surface resolution."""
        if not isinstance(resolution, WorkflowUiHandoffResolution):
            raise TypeError("Workflow UI handoff resolution must be typed.")
        return self._emit_or_call(
            self.workflow_ui_handoff_resolved_requested,
            "on_workflow_ui_handoff_resolved",
            resolution,
        )

    def debug(self, request: AssistantDebugToolRequest) -> bool:
        if not isinstance(request, AssistantDebugToolRequest):
            raise TypeError("Assistant debug dispatch requires a correlated request.")
        return self._emit_or_call(
            self.debug_requested,
            "execute_debug_tool",
            request,
        )

    def _emit_or_call(self, signal, method_name: str, *args: Any) -> bool:
        if self._controller is None:
            logger.warning(
                "Assistant command '%s' rejected without a bound controller",
                method_name,
            )
            return False
        if not self.accepts_commands:
            logger.warning(
                "Assistant command '%s' rejected while dispatcher is %s",
                method_name,
                self._state.value,
            )
            return False
        if self._queued:
            command_thread = self._command_thread
            if (
                command_thread is None
                or sip.isdeleted(command_thread)
                or not command_thread.isRunning()
            ):
                logger.error(
                    "Assistant command '%s' has no running transport thread",
                    method_name,
                )
                return False
            try:
                if self.receivers(signal) <= 0:
                    logger.error(
                        "Assistant command '%s' has no transport receiver",
                        method_name,
                    )
                    return False
                signal.emit(*args)
            except Exception:
                logger.exception(
                    "Assistant command '%s' transport delivery failed",
                    method_name,
                )
                return False
            return True
        method = getattr(self._controller, method_name, None)
        if not callable(method):
            logger.error(
                "Assistant controller handler '%s' is unavailable",
                method_name,
            )
            return False
        try:
            callback_result = method(*args)
        except Exception:
            logger.exception(
                "Assistant controller handler '%s' rejected delivery",
                method_name,
            )
            return False
        return callback_result is not False

    def close(self) -> bool:
        """Start cleanup without blocking the GUI and report terminal ownership."""
        if self._state is AssistantCommandDispatcherState.CLOSED:
            return True
        if self._state is AssistantCommandDispatcherState.OPEN:
            self._state = AssistantCommandDispatcherState.CLOSING
        controller = self._controller
        if controller is None:
            self._finish_close()
            return True
        if self._state is AssistantCommandDispatcherState.CONTROLLER_CLOSED:
            return self._finish_command_thread_cleanup()
        if not self._queued:
            close = getattr(controller, "close", None)
            if callable(close) and close() is False:
                return False
            self._state = AssistantCommandDispatcherState.CONTROLLER_CLOSED
            self._finish_close()
            return True

        command_thread = self._command_thread
        shutdown_bridge = self._shutdown_bridge
        if command_thread is None or shutdown_bridge is None:
            raise RuntimeError("Assistant command thread is missing during shutdown.")
        if sip.isdeleted(command_thread) or sip.isdeleted(shutdown_bridge):
            self._finish_close()
            return True

        if not command_thread.isRunning():
            logger.error(
                "Assistant command thread stopped before controller cleanup completed"
            )
            return False
        if not self._shutdown_in_flight:
            self._shutdown_in_flight = True
            self.shutdown_requested.emit()
        return False

    @pyqtSlot(bool, str)
    def _on_controller_shutdown_finished(self, ok: bool, message: str) -> None:
        """Advance cleanup only for the owned controller shutdown request."""
        if self._state is AssistantCommandDispatcherState.CLOSED:
            return
        self._shutdown_in_flight = False
        if not ok:
            detail = message or "Assistant controller did not finish shutdown."
            logger.error("Assistant shutdown completed with errors: %s", detail)
            self.cleanup_finished.emit(False, detail)
            return

        self._state = AssistantCommandDispatcherState.CONTROLLER_CLOSED
        if self._finish_command_thread_cleanup():
            self.cleanup_finished.emit(True, "")

    @pyqtSlot()
    def _on_command_thread_finished(self) -> None:
        """Release Qt ownership after the command event loop has stopped."""
        if self._state is not AssistantCommandDispatcherState.CONTROLLER_CLOSED:
            return
        self._finish_close()
        self.cleanup_finished.emit(True, "")

    def _finish_command_thread_cleanup(self) -> bool:
        """Request command-thread exit without waiting on the GUI thread."""
        command_thread = self._command_thread
        if (
            command_thread is None
            or sip.isdeleted(command_thread)
            or not command_thread.isRunning()
        ):
            self._finish_close()
            return True
        command_thread.quit()
        return self._state is AssistantCommandDispatcherState.CLOSED

    def _finish_close(self) -> None:
        """Release dispatcher ownership only after all cleanup has completed."""
        self._queued = False
        self._shutdown_in_flight = False
        self._command_thread = None
        self._shutdown_bridge = None
        self._controller = None
        self._state = AssistantCommandDispatcherState.CLOSED
