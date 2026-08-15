"""Delivery-result regression tests for assistant runtime lifecycle commands."""

from __future__ import annotations

from typing import Any, cast

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from XBrainLab.backend.application import CommandName
from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
)
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.agent.turn import (
    AssistantDebugToolRequest,
    AssistantTurnCorrelation,
    AssistantTurnDeliveryAcknowledgement,
    AssistantTurnDeliveryPhase,
    AssistantTurnRequest,
    AssistantTurnScope,
    AssistantTurnTerminal,
)
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeBackend,
    AssistantRuntimeLaunchResolution,
    AssistantRuntimeLaunchSpec,
    AssistantRuntimeSelectionOutcome,
    AssistantRuntimeSettingsSnapshot,
)
from XBrainLab.ui.components.assistant_runtime_lifecycle import (
    AssistantRuntimeLifecycle,
    RuntimeActivationStatus,
    RuntimeCommandAdmissionStatus,
)


def _launch_spec(model_id: str) -> AssistantRuntimeLaunchSpec:
    config = LLMConfig(model_name=model_id)
    return AssistantRuntimeLaunchSpec(
        backend=AssistantRuntimeBackend.LOCAL,
        requested_backend_id="local",
        requested_model_id=model_id,
        model_id=model_id,
        outcome=AssistantRuntimeSelectionOutcome.EXACT,
        selection_detail=f"Selected {model_id}.",
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


class _LifecycleController(QObject):
    runtime_state_changed = pyqtSignal(object)
    turn_finished = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.closed = False
        self.pending_confirmation_id: str | None = None

    def close(self) -> bool:
        self.closed = True
        return True


class _TerminalFallbackController(_LifecycleController):
    def __init__(self) -> None:
        super().__init__()
        self.active_turn: AssistantTurnCorrelation | None = None
        self.handoff_resolutions: list[WorkflowUiHandoffResolution] = []

    def on_workflow_ui_handoff_resolved(self, payload: object) -> None:
        assert isinstance(payload, WorkflowUiHandoffResolution)
        self.handoff_resolutions.append(payload)
        if self.active_turn is not None:
            self.turn_finished.emit(
                AssistantTurnTerminal(
                    correlation=self.active_turn,
                    outcome="handoff_failed",
                )
            )
            self.active_turn = None


class _DeliveryDispatcher:
    def __init__(self) -> None:
        self.controller: _LifecycleController | None = None
        self.outcomes: dict[str, bool | None] = {}
        self.calls: list[str] = []
        self.turn_requests: list[AssistantTurnRequest] = []
        self.debug_requests: list[AssistantDebugToolRequest] = []

    def _deliver(self, command_name: str) -> bool | None:
        self.calls.append(command_name)
        return self.outcomes.get(command_name, True)

    def bind(self, controller: object) -> None:
        self.controller = cast(_LifecycleController, controller)

    def initialize(self, _launch_spec: AssistantRuntimeLaunchSpec) -> bool | None:
        return self._deliver("initialize")

    def submit(self, request: AssistantTurnRequest) -> bool | None:
        self.turn_requests.append(request)
        return self._deliver("submit")

    def stop(self) -> bool | None:
        return self._deliver("stop")

    def set_model(self, _launch_spec: AssistantRuntimeLaunchSpec) -> bool | None:
        return self._deliver("set_model")

    def reset(self) -> bool | None:
        return self._deliver("reset")

    def confirm(
        self,
        _resolution: AgentConfirmationResolution,
    ) -> bool | None:
        delivered = self._deliver("confirm")
        if delivered is True and self.controller is not None:
            self.controller.pending_confirmation_id = None
        return delivered

    def resolve_ui_handoff(
        self,
        _resolution: WorkflowUiHandoffResolution,
    ) -> bool | None:
        return self._deliver("resolve_ui_handoff")

    def debug(self, request: AssistantDebugToolRequest) -> bool | None:
        self.debug_requests.append(request)
        return self._deliver("debug")

    def close(self) -> bool:
        if self.controller is not None:
            self.controller.close()
        return True


class _AcknowledgingDeliveryDispatcher(QObject, _DeliveryDispatcher):
    turn_delivery_acknowledged = pyqtSignal(object)

    def __init__(self) -> None:
        QObject.__init__(self)
        _DeliveryDispatcher.__init__(self)


class _LaunchResolver:
    def resolve(
        self,
        config: LLMConfig,
        *,
        requested_backend_id: str | None = None,
        requested_model_id: str | None = None,
    ) -> AssistantRuntimeLaunchResolution:
        del requested_backend_id
        model_id = requested_model_id or config.model_name
        return AssistantRuntimeLaunchResolution(launch_spec=_launch_spec(model_id))


def _ready_lifecycle(
    dispatcher: _DeliveryDispatcher,
    *,
    model_id: str = "test/local-primary",
    resolver: object | None = None,
) -> tuple[AssistantRuntimeLifecycle, _LifecycleController]:
    controller = _LifecycleController()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=cast(Any, dispatcher),
        config_loader=lambda: LLMConfig(model_name=model_id),
        resolver=cast(Any, resolver) if resolver is not None else None,
    )
    assert lifecycle.start(launch_spec=_launch_spec(model_id)) is True
    activation_id = lifecycle.expected_activation_id
    assert activation_id is not None
    lifecycle.accept_runtime_snapshot(
        AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=model_id,
            activation_id=activation_id,
        )
    )
    return lifecycle, controller


@pytest.mark.parametrize(
    "command_name",
    ["stop", "reset", "confirm", "resolve_ui_handoff", "debug"],
)
def test_lifecycle_never_accepts_none_delivery(command_name: str) -> None:
    dispatcher = _DeliveryDispatcher()
    lifecycle, _controller = _ready_lifecycle(dispatcher)
    dispatcher.outcomes[command_name] = None

    if command_name == "stop":
        assert lifecycle.submit("active request").accepted
        result = lifecycle.stop_generation()
    elif command_name == "reset":
        result = lifecycle.reset_conversation()
    elif command_name == "confirm":
        result = lifecycle.confirm(_confirmation())
    elif command_name == "resolve_ui_handoff":
        result = lifecycle.resolve_ui_handoff(_handoff())
    else:
        result = lifecycle.debug("inspect_state", {})

    assert result.status is RuntimeCommandAdmissionStatus.REJECTED
    assert "restart" in result.message.lower()


def test_rejected_submit_releases_the_reserved_turn() -> None:
    dispatcher = _DeliveryDispatcher()
    lifecycle, _controller = _ready_lifecycle(dispatcher)
    dispatcher.outcomes["submit"] = None

    result = lifecycle.submit("inspect current state")

    assert result.status is RuntimeCommandAdmissionStatus.REJECTED
    assert result.turn_id is None
    assert lifecycle.turn_in_flight is False


def test_submit_resolves_one_immutable_scope_from_each_natural_request() -> None:
    dispatcher = _DeliveryDispatcher()
    lifecycle, controller = _ready_lifecycle(dispatcher)

    single = lifecycle.submit("Explain the current workflow status.")

    assert single.accepted is True
    [single_request] = dispatcher.turn_requests
    assert single_request.scope is AssistantTurnScope.SINGLE_ACTION
    assert single_request.terminal_command is None
    controller.turn_finished.emit(
        AssistantTurnTerminal(
            correlation=single_request.correlation,
            outcome="completed",
        )
    )

    guided = lifecycle.submit("Load this EEG file, preprocess it, and create epochs.")

    assert guided.accepted is True
    assert guided.scope is AssistantTurnScope.GUIDED_WORKFLOW
    assert guided.terminal_command == "create_epoch"
    assert guided.excluded_commands == ()
    guided_request = dispatcher.turn_requests[-1]
    assert guided_request.scope is AssistantTurnScope.GUIDED_WORKFLOW
    assert guided_request.terminal_command == "create_epoch"


def test_submit_does_not_grant_an_excluded_preprocess_endpoint() -> None:
    dispatcher = _DeliveryDispatcher()
    lifecycle, _controller = _ready_lifecycle(dispatcher)

    result = lifecycle.submit("Load the data but not preprocess it.")

    assert result.accepted is True
    assert result.scope is AssistantTurnScope.SINGLE_ACTION
    assert result.terminal_command is None
    assert result.excluded_commands == (CommandName.PREPROCESS,)
    [request] = dispatcher.turn_requests
    assert request.scope is AssistantTurnScope.SINGLE_ACTION
    assert request.terminal_command is None
    assert request.excluded_commands == (CommandName.PREPROCESS,)


def test_delivery_error_releases_only_its_correlated_turn() -> None:
    dispatcher = _AcknowledgingDeliveryDispatcher()
    lifecycle, controller = _ready_lifecycle(dispatcher)
    terminals: list[AssistantTurnTerminal] = []
    lifecycle.turn_finished.connect(terminals.append)

    first = lifecycle.submit("first request")
    first_correlation = first.correlation
    assert first_correlation is not None
    dispatcher.turn_delivery_acknowledged.emit(
        AssistantTurnDeliveryAcknowledgement(
            correlation=first_correlation,
            phase=AssistantTurnDeliveryPhase.ERROR,
            message="queued controller setup failed",
        )
    )

    assert lifecycle.turn_in_flight is False
    assert [terminal.outcome for terminal in terminals] == ["delivery_error"]

    second = lifecycle.submit("second request")
    second_correlation = second.correlation
    assert second_correlation is not None
    dispatcher.turn_delivery_acknowledged.emit(
        AssistantTurnDeliveryAcknowledgement(
            correlation=first_correlation,
            phase=AssistantTurnDeliveryPhase.ERROR,
            message="late duplicate",
        )
    )
    dispatcher.turn_delivery_acknowledged.emit(
        AssistantTurnDeliveryAcknowledgement(
            correlation=second_correlation,
            phase=AssistantTurnDeliveryPhase.ACCEPTED,
        )
    )

    assert lifecycle.turn_in_flight is True
    assert len(terminals) == 1

    controller.turn_finished.emit(
        AssistantTurnTerminal(
            correlation=second_correlation,
            outcome="completed",
        )
    )
    assert lifecycle.turn_in_flight is False
    assert [terminal.outcome for terminal in terminals] == [
        "delivery_error",
        "completed",
    ]


def test_terminal_before_delivery_ack_is_not_reported_as_stale(
    caplog: pytest.LogCaptureFixture,
) -> None:
    dispatcher = _AcknowledgingDeliveryDispatcher()
    lifecycle, controller = _ready_lifecycle(dispatcher)

    admission = lifecycle.submit("request resolved synchronously")
    correlation = admission.correlation
    assert correlation is not None
    controller.turn_finished.emit(
        AssistantTurnTerminal(
            correlation=correlation,
            outcome="blocked",
        )
    )

    with caplog.at_level("WARNING"):
        dispatcher.turn_delivery_acknowledged.emit(
            AssistantTurnDeliveryAcknowledgement(
                correlation=correlation,
                phase=AssistantTurnDeliveryPhase.ACCEPTED,
            )
        )

    assert lifecycle.turn_in_flight is False
    assert "Ignored stale assistant turn delivery" not in caplog.text


def test_delivery_timeout_fences_retry_until_correlated_terminal() -> None:
    dispatcher = _AcknowledgingDeliveryDispatcher()
    lifecycle, controller = _ready_lifecycle(dispatcher)
    terminals: list[AssistantTurnTerminal] = []
    lifecycle.turn_finished.connect(terminals.append)

    admission = lifecycle.submit("request with a lost delivery acknowledgement")
    correlation = admission.correlation
    assert correlation is not None

    lifecycle._on_turn_delivery_timeout(correlation)

    assert lifecycle.turn_in_flight is True
    assert lifecycle._stop_requested_for == correlation
    assert terminals == []
    assert dispatcher.calls[-1] == "stop"
    retry = lifecycle.submit("do not execute this duplicate request")
    assert retry.status is RuntimeCommandAdmissionStatus.BUSY

    controller.turn_finished.emit(
        AssistantTurnTerminal(
            correlation=correlation,
            outcome="cancelled",
        )
    )

    assert lifecycle.turn_in_flight is False
    assert terminals == [
        AssistantTurnTerminal(correlation=correlation, outcome="delivery_timeout")
    ]
    assert lifecycle.submit("new request after terminal").accepted is True


def test_async_close_disarms_delivery_watchdog_until_shutdown_terminal() -> None:
    dispatcher = _AcknowledgingDeliveryDispatcher()
    lifecycle, _controller = _ready_lifecycle(dispatcher)
    terminals: list[AssistantTurnTerminal] = []
    lifecycle.turn_finished.connect(terminals.append)
    dispatcher.close = lambda: False

    admission = lifecycle.submit("request still waiting for delivery acknowledgement")
    correlation = admission.correlation
    assert correlation is not None
    assert lifecycle._turn_delivery_watchdog is not None

    assert lifecycle.close() is False
    assert lifecycle._turn_delivery_watchdog is None
    lifecycle._on_turn_delivery_timeout(correlation)

    assert lifecycle.turn_in_flight is True
    assert terminals == []

    lifecycle._complete_close()

    assert lifecycle.turn_in_flight is False
    assert terminals == [
        AssistantTurnTerminal(
            correlation=correlation,
            outcome="shutdown_cancelled",
        )
    ]


def test_rejected_confirmation_delivery_preserves_pending_interaction() -> None:
    dispatcher = _DeliveryDispatcher()
    lifecycle, controller = _ready_lifecycle(dispatcher)
    resolution = _confirmation()
    controller.pending_confirmation_id = resolution.request_id
    dispatcher.outcomes["confirm"] = False

    result = lifecycle.confirm(resolution)

    assert result.status is RuntimeCommandAdmissionStatus.REJECTED
    assert controller.pending_confirmation_id == resolution.request_id
    assert "restart" in result.message.lower()


def test_rejected_terminal_handoff_delivery_finalizes_one_correlated_turn() -> None:
    dispatcher = _DeliveryDispatcher()
    controller = _TerminalFallbackController()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=cast(Any, dispatcher),
        config_loader=lambda: LLMConfig(model_name="test/local-primary"),
    )
    assert lifecycle.start(launch_spec=_launch_spec("test/local-primary")) is True
    activation_id = lifecycle.expected_activation_id
    assert activation_id is not None
    lifecycle.accept_runtime_snapshot(
        AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id="test/local-primary",
            activation_id=activation_id,
        )
    )
    admitted = lifecycle.submit("open epoch settings")
    assert admitted.turn_id is not None
    controller.active_turn = admitted.correlation
    dispatcher.outcomes["resolve_ui_handoff"] = False
    resolution = _handoff()

    result = lifecycle.resolve_ui_handoff(resolution)

    assert result.status is RuntimeCommandAdmissionStatus.ACCEPTED
    assert result.turn_id == admitted.turn_id
    assert lifecycle.turn_in_flight is False
    assert len(controller.handoff_resolutions) == 1
    failed = controller.handoff_resolutions[0]
    assert failed.request_id == resolution.request_id
    assert failed.status is WorkflowUiHandoffResolutionStatus.FAILED


@pytest.mark.parametrize("delivery_result", [False, None])
def test_start_rolls_back_when_initial_command_delivery_is_rejected(
    delivery_result: bool | None,
) -> None:
    dispatcher = _DeliveryDispatcher()
    dispatcher.outcomes["initialize"] = delivery_result
    controller = _LifecycleController()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=cast(Any, dispatcher),
    )

    assert lifecycle.start(launch_spec=_launch_spec("test/local-primary")) is False
    assert lifecycle.initialized is False
    assert lifecycle.controller is None
    assert controller.closed is True
    assert lifecycle.current.phase is AssistantRuntimePhase.FAILED


def test_rejected_model_switch_enters_observable_recovery_state() -> None:
    dispatcher = _DeliveryDispatcher()
    lifecycle, _controller = _ready_lifecycle(
        dispatcher,
        resolver=_LaunchResolver(),
    )
    dispatcher.outcomes["set_model"] = None

    result = lifecycle.switch_model("test/local-secondary")

    assert result.status is RuntimeActivationStatus.UNAVAILABLE
    assert lifecycle.current.phase is AssistantRuntimePhase.FAILED
    assert lifecycle.current.initialized is True
    assert lifecycle.current.model_id == "test/local-primary"
    assert lifecycle.expected_activation_id is None
    assert "restart" in result.message.lower()


def test_debug_dispatch_reserves_and_reports_exact_turn_correlation() -> None:
    dispatcher = _DeliveryDispatcher()
    lifecycle, _controller = _ready_lifecycle(dispatcher)

    result = lifecycle.debug("inspect_state", {}, generation=37)

    assert result.status is RuntimeCommandAdmissionStatus.ACCEPTED
    assert result.generation == 37
    assert result.turn_id is not None
    assert lifecycle.turn_in_flight is True
    assert dispatcher.calls[-1] == "debug"
    [request] = dispatcher.debug_requests
    assert request.correlation == result.correlation
    assert request.tool_name == "inspect_state"
    assert request.to_params() == {}

    second = lifecycle.debug("inspect_state", {}, generation=38)

    assert second.status is RuntimeCommandAdmissionStatus.BUSY
    assert dispatcher.calls.count("debug") == 1
