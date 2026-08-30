"""Delivery-contract tests for the assistant command dispatcher."""

from __future__ import annotations

from typing import Any

import pytest
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
)
from XBrainLab.llm.agent.turn import (
    AssistantDebugToolRequest,
    AssistantTurnCorrelation,
    AssistantTurnDeliveryAcknowledgement,
    AssistantTurnDeliveryPhase,
    AssistantTurnRequest,
)
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeBackend,
    AssistantRuntimeLaunchSpec,
    AssistantRuntimeSelectionOutcome,
    AssistantRuntimeSettingsSnapshot,
)
from XBrainLab.ui.components.assistant_command_dispatcher import (
    AssistantCommandDispatcher,
    AssistantCommandDispatcherState,
)


def _launch_spec() -> AssistantRuntimeLaunchSpec:
    model_id = LLMConfig.default_local_model_id()
    config = LLMConfig(model_name=model_id)
    return AssistantRuntimeLaunchSpec(
        backend=AssistantRuntimeBackend.LOCAL,
        requested_backend_id="local",
        requested_model_id=model_id,
        model_id=model_id,
        outcome=AssistantRuntimeSelectionOutcome.EXACT,
        selection_detail="Exact local runtime selected.",
        settings=AssistantRuntimeSettingsSnapshot.from_config(config),
    )


def _confirmation() -> AgentConfirmationResolution:
    request = AgentConfirmationRequest.for_action(
        command_name="reset_preprocess",
        params={},
        action_label="Clear dataset",
        description="Clear the current dataset.",
        destructive=True,
        publication_generation=1,
    )
    return AgentConfirmationResolution.for_request(
        request,
        status=AgentConfirmationResolutionStatus.CANCELLED,
    )


def _handoff() -> WorkflowUiHandoffResolution:
    request = WorkflowUiHandoffRequest.for_decision("create_epoch")
    return WorkflowUiHandoffResolution.for_request(
        request,
        status=WorkflowUiHandoffResolutionStatus.CANCELLED,
    )


def _debug_request() -> AssistantDebugToolRequest:
    return AssistantDebugToolRequest.from_params(
        correlation=AssistantTurnCorrelation(generation=2, turn_id=2),
        tool_name="inspect_state",
        params={},
    )


class _DirectController:
    def __init__(
        self,
        delivery_result: bool | None,
        *,
        close_result: bool = True,
    ) -> None:
        self.delivery_result = delivery_result
        self.close_result = close_result
        self.calls: list[str] = []

    def _deliver(self, command_name: str) -> bool | None:
        self.calls.append(command_name)
        return self.delivery_result

    def initialize(self, _launch_spec: AssistantRuntimeLaunchSpec) -> bool | None:
        return self._deliver("initialize")

    def handle_user_turn(self, _request: AssistantTurnRequest) -> bool | None:
        return self._deliver("submit")

    def stop_generation(self) -> bool | None:
        return self._deliver("stop")

    def set_model(self, _launch_spec: AssistantRuntimeLaunchSpec) -> bool | None:
        return self._deliver("set_model")

    def reset_conversation(self) -> bool | None:
        return self._deliver("reset")

    def on_user_confirmation_resolved(
        self,
        _resolution: AgentConfirmationResolution,
    ) -> bool | None:
        return self._deliver("confirm")

    def on_workflow_ui_handoff_resolved(
        self,
        _resolution: WorkflowUiHandoffResolution,
    ) -> bool | None:
        return self._deliver("resolve_ui_handoff")

    def execute_debug_tool(
        self,
        _request: AssistantDebugToolRequest,
    ) -> bool | None:
        return self._deliver("debug")

    def close(self) -> bool:
        self.calls.append("close")
        return self.close_result


class _QueuedController(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.worker_thread = QThread()
        self.calls: list[str] = []

    def initialize(self, _launch_spec: AssistantRuntimeLaunchSpec) -> None:
        self.calls.append("initialize")

    def handle_user_turn(self, _request: AssistantTurnRequest) -> None:
        self.calls.append("submit")

    def stop_generation(self) -> None:
        self.calls.append("stop")

    def set_model(self, _launch_spec: AssistantRuntimeLaunchSpec) -> None:
        self.calls.append("set_model")

    def reset_conversation(self) -> None:
        self.calls.append("reset")

    def on_user_confirmation_resolved(
        self,
        _resolution: AgentConfirmationResolution,
    ) -> None:
        self.calls.append("confirm")

    def on_workflow_ui_handoff_resolved(
        self,
        _resolution: WorkflowUiHandoffResolution,
    ) -> None:
        self.calls.append("resolve_ui_handoff")

    def execute_debug_tool(
        self,
        _request: AssistantDebugToolRequest,
    ) -> None:
        self.calls.append("debug")

    def close(self) -> bool:
        self.worker_thread.quit()
        return True


class _FailingQueuedController(_QueuedController):
    def __init__(self) -> None:
        super().__init__()
        self.delivery_attempts = 0

    def handle_user_turn(
        self,
        request: AssistantTurnRequest,
    ) -> AssistantTurnDeliveryAcknowledgement:
        self.delivery_attempts += 1
        if self.delivery_attempts == 1:
            raise RuntimeError("fault injection: queued controller slot failed")
        self.calls.append("submit")
        return AssistantTurnDeliveryAcknowledgement(
            correlation=request.correlation,
            phase=AssistantTurnDeliveryPhase.ACCEPTED,
        )


class _HostileExceptionMeta(type):
    def __getattribute__(cls, name: str) -> object:
        if name == "__name__":
            raise AssertionError("hostile exception metaclass name access executed")
        return super().__getattribute__(name)


class _HostileDeliveryError(Exception, metaclass=_HostileExceptionMeta):
    def __str__(self) -> str:
        raise AssertionError("hostile exception string protocol executed")


class _HostileFailingQueuedController(_QueuedController):
    def handle_user_turn(self, _request: AssistantTurnRequest) -> None:
        raise _HostileDeliveryError("/srv/Clinical Records/Mary Example")


class _AsyncClosingQueuedController(_QueuedController):
    shutdown_finished = pyqtSignal(bool, str)

    def close(self) -> bool:
        self.calls.append("close")
        self.worker_thread.quit()
        QTimer.singleShot(10, lambda: self.shutdown_finished.emit(True, ""))
        return False


class _InlineAsyncClosingQueuedController(_QueuedController):
    """Expose affinity migration that happens inside the shutdown callback."""

    shutdown_finished = pyqtSignal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self.affinity_changed_before_close_returned = False

    def close(self) -> bool:
        self.calls.append("close")
        command_thread = QThread.currentThread()
        self.worker_thread.quit()
        self.shutdown_finished.emit(True, "")
        self.affinity_changed_before_close_returned = (
            self.thread() is not command_thread
        )
        return False


class _RetryingAsyncClosingQueuedController(_QueuedController):
    shutdown_finished = pyqtSignal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self._attempt = 0

    def close(self) -> bool:
        self.calls.append("close")
        self._attempt += 1
        if self._attempt == 1:
            QTimer.singleShot(
                10,
                lambda: self.shutdown_finished.emit(
                    False,
                    "Assistant cleanup is still pending.",
                ),
            )
        else:
            QTimer.singleShot(10, lambda: self.shutdown_finished.emit(True, ""))
        return False


def _dispatch_all(dispatcher: AssistantCommandDispatcher) -> dict[str, bool]:
    launch_spec = _launch_spec()
    return {
        "initialize": dispatcher.initialize(launch_spec),
        "submit": dispatcher.submit(
            AssistantTurnRequest(
                correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
                text="inspect state",
            )
        ),
        "stop": dispatcher.stop(),
        "set_model": dispatcher.set_model(launch_spec),
        "reset": dispatcher.reset(),
        "confirm": dispatcher.confirm(_confirmation()),
        "resolve_ui_handoff": dispatcher.resolve_ui_handoff(_handoff()),
        "debug": dispatcher.debug(_debug_request()),
    }


def _finish_queued_close(qtbot: Any, dispatcher: AssistantCommandDispatcher) -> None:
    dispatcher.close()
    qtbot.waitUntil(
        lambda: dispatcher.state is AssistantCommandDispatcherState.CLOSED,
        timeout=2_000,
    )


@pytest.mark.parametrize("callback_result", [None, True])
def test_direct_dispatch_treats_none_or_true_callbacks_as_delivered(
    callback_result: bool | None,
) -> None:
    controller = _DirectController(callback_result)
    dispatcher = AssistantCommandDispatcher()
    dispatcher.bind(controller)

    assert _dispatch_all(dispatcher) == dict.fromkeys(
        (
            "initialize",
            "submit",
            "stop",
            "set_model",
            "reset",
            "confirm",
            "resolve_ui_handoff",
            "debug",
        ),
        True,
    )


def test_direct_dispatch_operations_propagate_callback_rejection() -> None:
    controller = _DirectController(False)
    dispatcher = AssistantCommandDispatcher()
    dispatcher.bind(controller)

    assert set(_dispatch_all(dispatcher).values()) == {False}


def test_dispatch_operations_reject_missing_controller() -> None:
    dispatcher = AssistantCommandDispatcher()

    assert set(_dispatch_all(dispatcher).values()) == {False}


def test_dispatch_operations_reject_after_closing_starts() -> None:
    controller = _DirectController(True, close_result=False)
    dispatcher = AssistantCommandDispatcher()
    dispatcher.bind(controller)
    assert dispatcher.close() is False
    assert dispatcher.state is AssistantCommandDispatcherState.CLOSING

    assert set(_dispatch_all(dispatcher).values()) == {False}
    assert controller.calls == ["close"]


def test_queued_dispatch_rejects_a_missing_signal_receiver(qtbot: Any) -> None:
    controller = _QueuedController()
    dispatcher = AssistantCommandDispatcher()
    dispatcher.bind(controller)
    dispatcher.stop_requested.disconnect(controller.stop_generation)

    try:
        assert dispatcher.stop() is False
        qtbot.wait(20)
        assert controller.calls == []
    finally:
        _finish_queued_close(qtbot, dispatcher)


def test_queued_dispatch_reports_delivery_to_a_live_receiver(qtbot: Any) -> None:
    controller = _QueuedController()
    dispatcher = AssistantCommandDispatcher()
    dispatcher.bind(controller)

    try:
        assert dispatcher.stop() is True
        qtbot.waitUntil(lambda: controller.calls == ["stop"], timeout=2_000)
    finally:
        _finish_queued_close(qtbot, dispatcher)


def test_queued_dispatch_waits_for_async_controller_shutdown(qtbot: Any) -> None:
    controller = _AsyncClosingQueuedController()
    dispatcher = AssistantCommandDispatcher()
    terminals: list[tuple[bool, str]] = []
    dispatcher.cleanup_finished.connect(
        lambda ok, message: terminals.append((ok, message))
    )
    dispatcher.bind(controller)

    assert dispatcher.close() is False
    assert dispatcher.state is AssistantCommandDispatcherState.CLOSING
    qtbot.waitUntil(
        lambda: dispatcher.state is AssistantCommandDispatcherState.CLOSED,
        timeout=2_000,
    )

    assert terminals == [(True, "")]
    assert controller.calls == ["close"]


def test_queued_shutdown_does_not_move_controller_inside_its_signal_stack(
    qtbot: Any,
) -> None:
    controller = _InlineAsyncClosingQueuedController()
    dispatcher = AssistantCommandDispatcher()
    dispatcher.bind(controller)

    assert dispatcher.close() is False
    qtbot.waitUntil(
        lambda: dispatcher.state is AssistantCommandDispatcherState.CLOSED,
        timeout=2_000,
    )

    assert controller.affinity_changed_before_close_returned is False
    assert controller.calls == ["close"]


def test_queued_dispatch_can_retry_async_controller_shutdown(qtbot: Any) -> None:
    controller = _RetryingAsyncClosingQueuedController()
    dispatcher = AssistantCommandDispatcher()
    terminals: list[tuple[bool, str]] = []
    dispatcher.cleanup_finished.connect(
        lambda ok, message: terminals.append((ok, message))
    )
    dispatcher.bind(controller)

    assert dispatcher.close() is False
    qtbot.waitUntil(lambda: len(terminals) == 1, timeout=2_000)
    assert dispatcher.state is AssistantCommandDispatcherState.CLOSING
    assert terminals == [(False, "Assistant cleanup is still pending.")]

    assert dispatcher.close() is False
    qtbot.waitUntil(
        lambda: dispatcher.state is AssistantCommandDispatcherState.CLOSED,
        timeout=2_000,
    )

    assert terminals == [
        (False, "Assistant cleanup is still pending."),
        (True, ""),
    ]
    assert controller.calls == ["close", "close"]


def test_queued_submit_exception_is_acknowledged_without_sys_excepthook(
    qtbot: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    controller = _FailingQueuedController()
    dispatcher = AssistantCommandDispatcher()
    acknowledgements: list[AssistantTurnDeliveryAcknowledgement] = []
    uncaught: list[BaseException] = []
    dispatcher.turn_delivery_acknowledged.connect(acknowledgements.append)
    monkeypatch.setattr(
        sys,
        "excepthook",
        lambda _type, value, _traceback: uncaught.append(value),
    )
    dispatcher.bind(controller)
    first = AssistantTurnRequest(
        correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
        text="first",
    )
    second = AssistantTurnRequest(
        correlation=AssistantTurnCorrelation(generation=2, turn_id=2),
        text="second",
    )

    try:
        assert dispatcher.submit(first) is True
        qtbot.waitUntil(lambda: len(acknowledgements) == 1, timeout=2_000)
        assert acknowledgements[0].correlation == first.correlation
        assert acknowledgements[0].phase is AssistantTurnDeliveryPhase.ERROR
        assert uncaught == []

        assert dispatcher.submit(second) is True
        qtbot.waitUntil(lambda: len(acknowledgements) == 2, timeout=2_000)
        assert acknowledgements[1].correlation == second.correlation
        assert acknowledgements[1].phase is AssistantTurnDeliveryPhase.ACCEPTED
        assert controller.calls == ["submit"]
    finally:
        _finish_queued_close(qtbot, dispatcher)


def test_queued_submit_contains_hostile_exception_at_public_boundary(
    qtbot: Any,
) -> None:
    controller = _HostileFailingQueuedController()
    dispatcher = AssistantCommandDispatcher()
    acknowledgements: list[AssistantTurnDeliveryAcknowledgement] = []
    dispatcher.turn_delivery_acknowledged.connect(acknowledgements.append)
    dispatcher.bind(controller)
    request = AssistantTurnRequest(
        correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
        text="inspect state",
    )

    try:
        assert dispatcher.submit(request) is True
        qtbot.waitUntil(lambda: len(acknowledgements) == 1, timeout=2_000)

        acknowledgement = acknowledgements[0]
        assert acknowledgement.phase is AssistantTurnDeliveryPhase.ERROR
        assert acknowledgement.message == (
            "Assistant controller could not complete the queued request."
        )
        assert "Mary Example" not in acknowledgement.message
    finally:
        _finish_queued_close(qtbot, dispatcher)


def test_queued_dispatch_rejects_a_stopped_command_thread(qtbot: Any) -> None:
    controller = _QueuedController()
    dispatcher = AssistantCommandDispatcher()
    dispatcher.bind(controller)
    command_thread = dispatcher.command_thread
    assert command_thread is not None
    command_thread.quit()
    assert command_thread.wait(1_000)

    try:
        assert dispatcher.stop() is False
        qtbot.wait(20)
        assert controller.calls == []
    finally:
        command_thread.start()
        _finish_queued_close(qtbot, dispatcher)


def test_bind_rejects_missing_ui_handoff_handler() -> None:
    controller = _DirectController(True)
    controller.on_workflow_ui_handoff_resolved = None  # type: ignore[method-assign]
    dispatcher = AssistantCommandDispatcher()

    with pytest.raises(TypeError, match="on_workflow_ui_handoff_resolved"):
        dispatcher.bind(controller)
