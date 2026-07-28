"""Focused tests for assistant runtime ownership outside ``AgentManager``."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QObject, pyqtSignal

from XBrainLab.chat_contract import MAX_CHAT_MESSAGE_CONTENT_LENGTH
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
    AssistantTurnTerminal,
)
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeLaunchSpec,
    AssistantRuntimeSelectionFailureCode,
)
from XBrainLab.ui.components.assistant_runtime_lifecycle import (
    AssistantRuntimeActivationRequest,
    AssistantRuntimeLifecycle,
    AssistantRuntimeLifecycleState,
    RuntimeActivationStatus,
    RuntimeCommandAdmissionResult,
    RuntimeCommandAdmissionStatus,
    RuntimeSetupAction,
)


def _terminal(
    admission: RuntimeCommandAdmissionResult,
    *,
    outcome: str = "completed",
) -> AssistantTurnTerminal:
    correlation = admission.correlation
    assert correlation is not None
    return AssistantTurnTerminal(correlation=correlation, outcome=outcome)


class _Controller(QObject):
    runtime_state_changed = pyqtSignal(object)
    processing_finished = pyqtSignal()
    turn_finished = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    def close(self) -> bool:
        self.closed = True
        return True


class _SignalDrivenShutdownController(_Controller):
    shutdown_finished = pyqtSignal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self.shutdown_in_progress = False

    def complete_shutdown(self) -> None:
        self.shutdown_in_progress = False
        self.closed = True
        self.shutdown_finished.emit(True, "")


class _ControllerMissingTerminalSignal(QObject):
    runtime_state_changed = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    def close(self) -> bool:
        self.closed = True
        return True


class _Dispatcher:
    def __init__(self) -> None:
        self.bound_controller: object | None = None
        self.bind_calls = 0
        self.initialized = False
        self.launch_specs: list[AssistantRuntimeLaunchSpec] = []
        self.models: list[AssistantRuntimeLaunchSpec] = []
        self.submissions: list[str] = []
        self.turn_requests: list[object] = []
        self.confirmation_resolutions: list[AgentConfirmationResolution] = []
        self.handoff_resolutions: list[WorkflowUiHandoffResolution] = []
        self.closed = False
        self.stop_calls = 0
        self.reset_calls = 0

    def bind(self, controller: object) -> None:
        self.bind_calls += 1
        self.bound_controller = controller

    def initialize(self, launch_spec: AssistantRuntimeLaunchSpec) -> bool:
        self.initialized = True
        self.launch_specs.append(launch_spec)
        return True

    def set_model(self, launch_spec: AssistantRuntimeLaunchSpec) -> bool:
        self.models.append(launch_spec)
        return True

    def submit(self, request: object) -> bool:
        self.turn_requests.append(request)
        self.submissions.append(str(getattr(request, "text", request)))
        return True

    def stop(self) -> bool:
        self.stop_calls += 1
        return True

    def reset(self) -> bool:
        self.reset_calls += 1
        return True

    def confirm(self, resolution: AgentConfirmationResolution) -> bool:
        self.confirmation_resolutions.append(resolution)
        return True

    def resolve_ui_handoff(
        self,
        resolution: WorkflowUiHandoffResolution,
    ) -> bool:
        self.handoff_resolutions.append(resolution)
        return True

    def debug(self, request: AssistantDebugToolRequest) -> bool:
        del request
        return True

    def close(self) -> bool:
        self.closed = True
        return True


class _FailingDispatcher(_Dispatcher):
    def __init__(self, failure: str) -> None:
        super().__init__()
        self.failure = failure

    def bind(self, controller: object) -> None:
        if self.failure == "bind":
            raise RuntimeError("bind failed")
        super().bind(controller)

    def initialize(self, launch_spec: AssistantRuntimeLaunchSpec) -> bool:
        if self.failure == "initialize":
            raise RuntimeError("initialize failed")
        return super().initialize(launch_spec)


class _RetryingCloseDispatcher(_FailingDispatcher):
    def __init__(self) -> None:
        super().__init__("initialize")
        self.close_attempts = 0

    def close(self) -> bool:
        self.close_attempts += 1
        self.closed = self.close_attempts >= 2
        return self.closed


class _CleanupPendingDispatcher(_Dispatcher):
    def __init__(self) -> None:
        super().__init__()
        self.close_attempts = 0

    def close(self) -> bool:
        self.close_attempts += 1
        self.closed = self.close_attempts >= 2
        return self.closed


class _SignalledCleanupDispatcher(QObject, _Dispatcher):
    cleanup_finished = pyqtSignal(bool, str)

    def __init__(self) -> None:
        QObject.__init__(self)
        _Dispatcher.__init__(self)

    def close(self) -> bool:
        return False


class _ControllerSignalCleanupDispatcher(QObject, _Dispatcher):
    cleanup_finished = pyqtSignal(bool, str)

    def __init__(self) -> None:
        QObject.__init__(self)
        _Dispatcher.__init__(self)
        self.close_attempts = 0

    def close(self) -> bool:
        self.close_attempts += 1
        if self.close_attempts == 1:
            controller = self.bound_controller
            assert isinstance(controller, _SignalDrivenShutdownController)
            controller.shutdown_in_progress = True
            self.cleanup_finished.emit(
                False,
                "Assistant controller did not finish shutdown.",
            )
            return False
        self.closed = True
        return True


class _ExceptionThenSuccessDispatcher(_Dispatcher):
    def __init__(self) -> None:
        super().__init__()
        self.close_attempts = 0

    def close(self) -> bool:
        self.close_attempts += 1
        if self.close_attempts == 1:
            raise RuntimeError("dispatcher cleanup failed")
        self.closed = True
        return True


class _RejectingSubmitDispatcher(_Dispatcher):
    def submit(self, request: object) -> bool:
        self.turn_requests.append(request)
        self.submissions.append(str(getattr(request, "text", request)))
        return False


@dataclass(frozen=True)
class _ActivationTransition(AssistantRuntimeSnapshot):
    activation_id: int = 0


def _ready_config(model_id: str | None = None) -> LLMConfig:
    model_id = model_id or LLMConfig.default_local_model_id()
    config = LLMConfig(model_name=model_id)
    config.local_runtime_notice_acknowledged = True
    config.local_backend_ready = (
        lambda candidate=None: (  # type: ignore[method-assign]
            candidate or model_id
        )
        == model_id
    )
    config.local_backend_status_message = (  # type: ignore[method-assign]
        lambda candidate=None: (
            "Local runtime ready."
            if (candidate or model_id) == model_id
            else f"Model cache not found for {candidate}."
        )
    )
    return config


def test_lifecycle_owns_start_snapshot_dispatch_and_shutdown(qtbot) -> None:
    del qtbot
    controller = _Controller()
    dispatcher = _Dispatcher()
    published: list[AssistantRuntimeSnapshot] = []
    created: list[object] = []
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    lifecycle.runtime_snapshot_changed.connect(published.append)
    lifecycle.controller_created.connect(created.append)

    assert lifecycle.start() is True
    assert lifecycle.initialized is True
    assert lifecycle.controller is controller
    assert lifecycle.current.phase is AssistantRuntimePhase.LOADING
    assert lifecycle.current.activation_id == lifecycle.expected_activation_id
    loading_admission = lifecycle.submit("too early")
    assert loading_admission.status is RuntimeCommandAdmissionStatus.REJECTED
    assert "loading" in loading_admission.message.lower()
    assert dispatcher.submissions == []
    assert created == [controller]
    assert dispatcher.bound_controller is controller
    assert dispatcher.initialized is True
    assert len(dispatcher.launch_specs) == 1
    launch_spec = dispatcher.launch_specs[0]
    assert launch_spec.model_id == LLMConfig.default_local_model_id()

    ready = _ActivationTransition(
        phase=AssistantRuntimePhase.READY,
        initialized=True,
        backend_mode="local",
        model_id=launch_spec.model_id,
        requested_model_id=launch_spec.requested_model_id,
        selection_outcome=launch_spec.outcome,
        selection_detail=launch_spec.selection_detail,
        activation_id=getattr(launch_spec, "activation_id", 0),
    )
    controller.runtime_state_changed.emit(ready)
    assert lifecycle.current == ready
    assert published[-1] == ready

    admission = lifecycle.submit("inspect this dataset")
    assert admission.status is RuntimeCommandAdmissionStatus.ACCEPTED
    assert dispatcher.submissions == ["inspect this dataset"]
    assert lifecycle.close() is True
    assert dispatcher.closed is True
    assert lifecycle.controller is None
    assert lifecycle.initialized is False


def test_start_fails_and_cleans_controller_without_terminal_signal() -> None:
    controller = _ControllerMissingTerminalSignal()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=_Dispatcher(),
        config_loader=_ready_config,
    )

    assert lifecycle.start() is False

    assert controller.closed is True
    assert lifecycle.controller is None
    assert lifecycle.initialized is False
    assert lifecycle.current.phase is AssistantRuntimePhase.FAILED


def test_submit_admission_is_owned_by_the_ready_runtime_phase() -> None:
    controller = _Controller()
    dispatcher = _Dispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )

    idle = lifecycle.submit("before startup")
    assert idle.status is RuntimeCommandAdmissionStatus.REJECTED
    assert dispatcher.submissions == []

    assert lifecycle.start() is True
    loading = lifecycle.submit("during startup")
    assert loading.status is RuntimeCommandAdmissionStatus.REJECTED
    assert dispatcher.submissions == []

    activation_id = lifecycle.expected_activation_id
    assert activation_id is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=LLMConfig.default_local_model_id(),
            activation_id=activation_id,
        )
    )
    ready = lifecycle.submit("when ready")
    assert ready.status is RuntimeCommandAdmissionStatus.ACCEPTED
    assert dispatcher.submissions == ["when ready"]

    lifecycle.mark_unavailable("runtime failed")
    failed = lifecycle.submit("after failure")
    assert failed.status is RuntimeCommandAdmissionStatus.REJECTED
    assert "failed" in failed.message.lower()
    assert dispatcher.submissions == ["when ready"]


def test_rapid_double_submit_reserves_one_turn_until_processing_finishes() -> None:
    controller = _Controller()
    dispatcher = _Dispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    assert lifecycle.start() is True
    activation_id = lifecycle.expected_activation_id
    assert activation_id is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=LLMConfig.default_local_model_id(),
            activation_id=activation_id,
        )
    )

    first = lifecycle.submit("first request")
    second = lifecycle.submit("second request")

    assert first.status is RuntimeCommandAdmissionStatus.ACCEPTED
    assert first.turn_id is not None
    assert second.status is RuntimeCommandAdmissionStatus.BUSY
    assert "previous request" in second.message.lower()
    assert dispatcher.submissions == ["first request"]

    controller.turn_finished.emit(_terminal(first))
    third = lifecycle.submit("third request")

    assert third.status is RuntimeCommandAdmissionStatus.ACCEPTED
    assert dispatcher.submissions == ["first request", "third request"]


def test_stale_terminal_cannot_release_a_newer_turn() -> None:
    controller = _Controller()
    dispatcher = _Dispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    assert lifecycle.start() is True
    activation_id = lifecycle.expected_activation_id
    assert activation_id is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=LLMConfig.default_local_model_id(),
            activation_id=activation_id,
        )
    )

    first = lifecycle.submit("first")
    assert first.turn_id is not None
    controller.turn_finished.emit(_terminal(first))
    second = lifecycle.submit("second")
    assert second.turn_id is not None

    controller.turn_finished.emit(_terminal(first))

    assert lifecycle.turn_in_flight is True
    assert lifecycle.submit("must stay blocked").status is (
        RuntimeCommandAdmissionStatus.BUSY
    )

    controller.turn_finished.emit(_terminal(second))
    assert lifecycle.turn_in_flight is False


def test_reset_is_rejected_until_active_turn_reaches_its_terminal_signal() -> None:
    controller = _Controller()
    dispatcher = _Dispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    assert lifecycle.start() is True
    activation_id = lifecycle.expected_activation_id
    assert activation_id is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=LLMConfig.default_local_model_id(),
            activation_id=activation_id,
        )
    )
    turn = lifecycle.submit("active")
    assert turn.turn_id is not None

    blocked = lifecycle.reset_conversation()

    assert blocked.status is RuntimeCommandAdmissionStatus.BUSY
    assert dispatcher.reset_calls == 0

    controller.turn_finished.emit(_terminal(turn))
    assert lifecycle.reset_conversation().accepted is True
    assert dispatcher.reset_calls == 1


def test_model_switch_is_rejected_while_a_turn_is_active() -> None:
    controller = _Controller()
    dispatcher = _Dispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    assert lifecycle.start() is True
    activation_id = lifecycle.expected_activation_id
    assert activation_id is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=LLMConfig.default_local_model_id(),
            activation_id=activation_id,
        )
    )
    turn = lifecycle.submit("active")
    assert turn.turn_id is not None

    blocked = lifecycle.switch_model(LLMConfig.fallback_local_model_id())

    assert blocked.status is RuntimeActivationStatus.BUSY
    assert blocked.available is False
    assert dispatcher.models == []


def test_blank_submit_is_rejected_without_reserving_a_turn() -> None:
    controller = _Controller()
    dispatcher = _Dispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    assert lifecycle.start() is True
    activation_id = lifecycle.expected_activation_id
    assert activation_id is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=LLMConfig.default_local_model_id(),
            activation_id=activation_id,
        )
    )

    admission = lifecycle.submit("   ")

    assert admission.status is RuntimeCommandAdmissionStatus.REJECTED
    assert admission.turn_id is None
    assert lifecycle.turn_in_flight is False
    assert dispatcher.turn_requests == []


def test_oversized_submit_is_rejected_before_turn_reservation_or_dispatch() -> None:
    controller = _Controller()
    dispatcher = _Dispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    assert lifecycle.start() is True
    activation_id = lifecycle.expected_activation_id
    assert activation_id is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=LLMConfig.default_local_model_id(),
            activation_id=activation_id,
        )
    )

    admission = lifecycle.submit("x" * (MAX_CHAT_MESSAGE_CONTENT_LENGTH + 1))

    assert admission.status is RuntimeCommandAdmissionStatus.REJECTED
    assert admission.turn_id is None
    assert lifecycle.turn_in_flight is False
    assert dispatcher.turn_requests == []


def test_cancel_keeps_turn_reserved_until_terminal_processing_finished() -> None:
    controller = _Controller()
    dispatcher = _Dispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    assert lifecycle.start() is True
    activation_id = lifecycle.expected_activation_id
    assert activation_id is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=LLMConfig.default_local_model_id(),
            activation_id=activation_id,
        )
    )

    turn = lifecycle.submit("cancel me")
    assert turn.accepted
    assert turn.turn_id is not None
    lifecycle.stop_generation()

    assert dispatcher.stop_calls == 1
    assert lifecycle.turn_in_flight is True
    assert lifecycle.submit("too soon").status is RuntimeCommandAdmissionStatus.BUSY

    controller.turn_finished.emit(_terminal(turn, outcome="cancelled"))

    assert lifecycle.turn_in_flight is False
    assert lifecycle.submit("after cancel").accepted


def test_stop_reaches_active_turn_after_runtime_phase_becomes_failed() -> None:
    controller = _Controller()
    dispatcher = _Dispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    assert lifecycle.start() is True
    activation_id = lifecycle.expected_activation_id
    assert activation_id is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=LLMConfig.default_local_model_id(),
            activation_id=activation_id,
        )
    )
    turn = lifecycle.submit("active request")
    assert turn.accepted
    assert turn.turn_id is not None
    lifecycle.mark_unavailable("runtime failed during the active turn")

    lifecycle.stop_generation()

    assert dispatcher.stop_calls == 1
    assert lifecycle.turn_in_flight is True
    controller.turn_finished.emit(_terminal(turn, outcome="cancelled"))
    assert lifecycle.turn_in_flight is False


def test_pending_interaction_resolutions_use_control_plane_after_runtime_failure() -> (
    None
):
    controller = _Controller()
    dispatcher = _Dispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    assert lifecycle.start() is True
    lifecycle.mark_unavailable("runtime failed while the dialog was open")

    confirmation_request = AgentConfirmationRequest.for_action(
        command_name="clear_dataset",
        params={},
        action_label="Clear dataset",
        description="Clear the current dataset.",
        destructive=True,
        publication_generation=1,
    )
    confirmation = AgentConfirmationResolution.for_request(
        confirmation_request,
        status=AgentConfirmationResolutionStatus.CANCELLED,
    )
    handoff_request = WorkflowUiHandoffRequest.for_decision("create_epoch")
    handoff = WorkflowUiHandoffResolution.for_request(
        handoff_request,
        status=WorkflowUiHandoffResolutionStatus.CANCELLED,
    )

    confirmation_result = lifecycle.confirm(confirmation)
    handoff_result = lifecycle.resolve_ui_handoff(handoff)

    assert confirmation_result.status is RuntimeCommandAdmissionStatus.ACCEPTED
    assert handoff_result.status is RuntimeCommandAdmissionStatus.ACCEPTED
    assert dispatcher.confirmation_resolutions == [confirmation]
    assert dispatcher.handoff_resolutions == [handoff]


def test_interaction_resolution_rejection_is_typed_after_runtime_close() -> None:
    controller = _Controller()
    dispatcher = _Dispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    assert lifecycle.start() is True
    assert lifecycle.close() is True
    request = WorkflowUiHandoffRequest.for_decision("create_epoch")
    resolution = WorkflowUiHandoffResolution.for_request(
        request,
        status=WorkflowUiHandoffResolutionStatus.CANCELLED,
    )

    result = lifecycle.resolve_ui_handoff(resolution)

    assert result.status is RuntimeCommandAdmissionStatus.REJECTED
    assert "closed" in result.message.lower()


def test_error_signal_waits_for_terminal_finish_before_releasing_turn() -> None:
    controller = _Controller()
    dispatcher = _Dispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    assert lifecycle.start() is True
    activation_id = lifecycle.expected_activation_id
    assert activation_id is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=LLMConfig.default_local_model_id(),
            activation_id=activation_id,
        )
    )

    turn = lifecycle.submit("failing request")
    assert turn.accepted
    assert turn.turn_id is not None
    controller.error_occurred.emit("generation failed")

    assert lifecycle.turn_in_flight is True
    assert lifecycle.submit("before terminal").status is (
        RuntimeCommandAdmissionStatus.BUSY
    )

    controller.turn_finished.emit(_terminal(turn, outcome="failed"))

    assert lifecycle.turn_in_flight is False
    assert lifecycle.submit("after error").accepted


def test_failed_transport_admission_releases_reserved_turn() -> None:
    controller = _Controller()
    dispatcher = _RejectingSubmitDispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    assert lifecycle.start() is True
    activation_id = lifecycle.expected_activation_id
    assert activation_id is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=LLMConfig.default_local_model_id(),
            activation_id=activation_id,
        )
    )

    admission = lifecycle.submit("cannot queue")

    assert admission.status is RuntimeCommandAdmissionStatus.REJECTED
    assert lifecycle.turn_in_flight is False


def test_close_preserves_turn_until_typed_shutdown_terminal() -> None:
    controller = _Controller()
    dispatcher = _CleanupPendingDispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    assert lifecycle.start() is True
    activation_id = lifecycle.expected_activation_id
    assert activation_id is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=LLMConfig.default_local_model_id(),
            activation_id=activation_id,
        )
    )
    admission = lifecycle.submit("active request")
    assert admission.accepted
    terminals: list[AssistantTurnTerminal] = []
    lifecycle.turn_finished.connect(terminals.append)

    assert lifecycle.close() is False

    assert lifecycle.turn_in_flight is True
    assert terminals == []
    assert lifecycle.state is AssistantRuntimeLifecycleState.CLEANUP_PENDING
    assert lifecycle.close() is True
    assert lifecycle.turn_in_flight is False
    assert terminals == [_terminal(admission, outcome="shutdown_cancelled")]


def test_async_cleanup_signal_completes_the_same_typed_shutdown_terminal() -> None:
    controller = _Controller()
    dispatcher = _SignalledCleanupDispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    assert lifecycle.start() is True
    activation_id = lifecycle.expected_activation_id
    assert activation_id is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=LLMConfig.default_local_model_id(),
            activation_id=activation_id,
        )
    )
    admission = lifecycle.submit("active request")
    assert admission.accepted
    terminals: list[AssistantTurnTerminal] = []
    cleanup_events: list[tuple[bool, str]] = []
    lifecycle.turn_finished.connect(terminals.append)
    lifecycle.cleanup_finished.connect(
        lambda ok, message: cleanup_events.append((ok, message))
    )

    assert lifecycle.close() is False
    assert lifecycle.turn_in_flight is True
    dispatcher.cleanup_finished.emit(True, "closed")

    assert lifecycle.state is AssistantRuntimeLifecycleState.CLOSED
    assert lifecycle.turn_in_flight is False
    assert terminals == [_terminal(admission, outcome="shutdown_cancelled")]
    assert cleanup_events == [(True, "closed")]

    dispatcher.cleanup_finished.emit(False, "late failure")
    dispatcher.cleanup_finished.emit(True, "late duplicate")

    assert lifecycle.state is AssistantRuntimeLifecycleState.CLOSED
    assert terminals == [_terminal(admission, outcome="shutdown_cancelled")]
    assert cleanup_events == [(True, "closed")]


def test_controller_terminal_signal_resumes_pending_dispatcher_cleanup() -> None:
    controller = _SignalDrivenShutdownController()
    dispatcher = _ControllerSignalCleanupDispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    assert lifecycle.start() is True
    cleanup_events: list[tuple[bool, str]] = []
    lifecycle.cleanup_finished.connect(
        lambda ok, message: cleanup_events.append((ok, message))
    )

    assert lifecycle.close() is False
    assert lifecycle.state is AssistantRuntimeLifecycleState.CLEANUP_PENDING
    assert cleanup_events == []

    controller.complete_shutdown()

    assert dispatcher.close_attempts == 2
    assert lifecycle.state is AssistantRuntimeLifecycleState.CLOSED
    assert cleanup_events == [(True, "")]


def test_lifecycle_activation_owns_readiness_start_and_model_switch() -> None:
    primary_model = LLMConfig.default_local_model_id()
    fallback_model = LLMConfig.fallback_local_model_id()
    controller = _Controller()
    dispatcher = _Dispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )

    started = lifecycle.activate(
        _ready_config(primary_model),
    )
    assert started.status is RuntimeActivationStatus.STARTED
    assert started.model_id == primary_model
    assert started.launch_spec is dispatcher.launch_specs[0]

    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=primary_model,
            activation_id=started.activation_id or 0,
        )
    )
    unchanged = lifecycle.activate(
        _ready_config(primary_model),
    )
    assert unchanged.status is RuntimeActivationStatus.ALREADY_READY
    assert dispatcher.models == []

    switched = lifecycle.activate(
        _ready_config(fallback_model),
    )
    assert switched.status is RuntimeActivationStatus.SWITCHING
    assert switched.launch_spec is dispatcher.models[0]
    assert dispatcher.models[0].model_id == fallback_model
    assert lifecycle.current.phase is AssistantRuntimePhase.LOADING
    assert lifecycle.current.model_id == fallback_model


def test_activation_does_not_fallback_to_a_ready_legacy_model() -> None:
    primary_model = LLMConfig.default_local_model_id()
    fallback_model = LLMConfig.fallback_local_model_id()
    config = LLMConfig(model_name=primary_model)
    config.local_runtime_notice_acknowledged = True
    config.local_backend_ready = lambda candidate=None: (  # type: ignore[method-assign]
        candidate == fallback_model
    )
    config.local_backend_status_message = (  # type: ignore[method-assign]
        lambda candidate=None: (
            "Local runtime ready."
            if candidate == fallback_model
            else f"Model cache not found for {candidate}."
        )
    )
    dispatcher = _Dispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: _Controller(),
        dispatcher=dispatcher,
        config_loader=lambda: config,
    )

    activation = lifecycle.activate(config)

    assert activation.status is RuntimeActivationStatus.UNAVAILABLE
    assert activation.launch_spec is None
    assert activation.failure is not None
    assert activation.failure.code is (
        AssistantRuntimeSelectionFailureCode.RUNTIME_UNAVAILABLE
    )
    assert primary_model in activation.message
    assert fallback_model not in activation.message
    assert dispatcher.launch_specs == []
    assert lifecycle.current.model_id == ""
    assert lifecycle.current.requested_model_id == primary_model
    assert lifecycle.current.phase is AssistantRuntimePhase.FAILED


def test_activation_typed_fails_unknown_ids_without_starting_or_switching() -> None:
    dispatcher = _Dispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: _Controller(),
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    unknown_backend = _ready_config()
    unknown_backend.inference_mode = "unknown-runtime"

    backend_result = lifecycle.activate(
        unknown_backend,
    )

    assert backend_result.status is RuntimeActivationStatus.UNAVAILABLE
    assert backend_result.failure is not None
    assert backend_result.failure.code is (
        AssistantRuntimeSelectionFailureCode.UNKNOWN_BACKEND
    )
    assert lifecycle.controller is None
    assert dispatcher.launch_specs == []

    unknown_model = _ready_config()
    unknown_model.model_name = "unknown/model"
    model_result = lifecycle.activate(unknown_model)

    assert model_result.status is RuntimeActivationStatus.UNAVAILABLE
    assert model_result.failure is not None
    assert model_result.failure.code is (
        AssistantRuntimeSelectionFailureCode.UNKNOWN_MODEL
    )
    assert lifecycle.controller is None
    assert dispatcher.launch_specs == []


def test_model_switch_resolves_once_and_dispatches_the_exact_spec() -> None:
    primary_model = LLMConfig.default_local_model_id()
    fallback_model = LLMConfig.fallback_local_model_id()
    dispatcher = _Dispatcher()
    config = _ready_config(primary_model)
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: _Controller(),
        dispatcher=dispatcher,
        config_loader=lambda: config,
    )
    started = lifecycle.activate(config)
    assert started.launch_spec is not None
    lifecycle.accept_runtime_snapshot(
        AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=primary_model,
        )
    )
    config.local_backend_ready = lambda candidate=None: (  # type: ignore[method-assign]
        candidate == fallback_model
    )
    config.local_backend_status_message = (  # type: ignore[method-assign]
        lambda candidate=None: (
            "Local runtime ready."
            if candidate == fallback_model
            else f"Model cache not found for {candidate}."
        )
    )

    switched = lifecycle.switch_model(fallback_model)

    assert switched.status is RuntimeActivationStatus.SWITCHING
    assert switched.launch_spec is dispatcher.models[0]
    assert switched.launch_spec is not None
    assert switched.launch_spec.model_id == fallback_model
    assert lifecycle.current.model_id == switched.launch_spec.model_id

    rejected = lifecycle.switch_model("unknown/model")

    assert rejected.status is RuntimeActivationStatus.UNAVAILABLE
    assert rejected.failure is not None
    assert rejected.failure.code is AssistantRuntimeSelectionFailureCode.UNKNOWN_MODEL
    assert dispatcher.models == [switched.launch_spec]


def test_model_switch_registers_expected_activation_before_dispatch() -> None:
    lifecycle: AssistantRuntimeLifecycle

    class _OrderingDispatcher(_Dispatcher):
        def set_model(self, launch_spec: AssistantRuntimeLaunchSpec) -> bool:
            assert lifecycle.current.phase is AssistantRuntimePhase.LOADING
            assert lifecycle.current.model_id == launch_spec.model_id
            assert isinstance(launch_spec, AssistantRuntimeActivationRequest)
            assert lifecycle.expected_activation_id == launch_spec.activation_id
            return super().set_model(launch_spec)

    primary_model = LLMConfig.default_local_model_id()
    fallback_model = LLMConfig.fallback_local_model_id()
    dispatcher = _OrderingDispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: _Controller(),
        dispatcher=dispatcher,
        config_loader=lambda: _ready_config(fallback_model),
    )
    started = lifecycle.activate(_ready_config(primary_model))
    assert started.launch_spec is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=primary_model,
            activation_id=started.activation_id or 0,
        )
    )

    switched = lifecycle.switch_model(fallback_model)

    assert switched.status is RuntimeActivationStatus.SWITCHING
    assert dispatcher.models == [switched.launch_spec]


def test_failed_activation_can_retry_without_rebuilding_controller() -> None:
    primary_model = LLMConfig.default_local_model_id()
    fallback_model = LLMConfig.fallback_local_model_id()
    dispatcher = _Dispatcher()
    controllers: list[_Controller] = []

    def factory(_study: object) -> _Controller:
        controller = _Controller()
        controllers.append(controller)
        return controller

    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=factory,
        dispatcher=dispatcher,
        config_loader=lambda: _ready_config(fallback_model),
    )
    started = lifecycle.activate(_ready_config(primary_model))
    assert started.launch_spec is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=primary_model,
            activation_id=started.activation_id or 0,
        )
    )

    failed = lifecycle.switch_model(fallback_model)
    assert failed.launch_spec is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.FAILED,
            initialized=False,
            backend_mode="local",
            model_id=primary_model,
            error="generation is active",
            activation_id=failed.activation_id or 0,
        )
    )
    assert lifecycle.current.phase is AssistantRuntimePhase.FAILED
    assert lifecycle.current.initialized is True
    assert lifecycle.current.model_id == primary_model
    assert lifecycle.active_local_runtime_blocks_model_deletion() is True

    retried = lifecycle.switch_model(fallback_model)
    assert retried.launch_spec is not None
    assert lifecycle.current.phase is AssistantRuntimePhase.LOADING
    assert retried.activation_id != failed.activation_id
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=fallback_model,
            activation_id=retried.activation_id or 0,
        )
    )

    assert lifecycle.current.phase is AssistantRuntimePhase.READY
    assert lifecycle.current.model_id == fallback_model
    assert len(controllers) == 1
    assert dispatcher.bind_calls == 1
    assert len(dispatcher.launch_specs) == 1
    assert len(dispatcher.models) == 2


def test_failed_reconfiguration_preserves_live_runtime_identity_and_delete_guard() -> (
    None
):
    model_id = LLMConfig.default_local_model_id()
    controller = _Controller()
    dispatcher = _Dispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=lambda: _ready_config(model_id),
    )
    started = lifecycle.activate(_ready_config(model_id))
    assert started.activation_id is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=model_id,
            activation_id=started.activation_id,
        )
    )
    invalid = _ready_config(model_id)
    invalid.inference_mode = "not-a-runtime"

    result = lifecycle.activate(invalid)

    assert result.status is RuntimeActivationStatus.UNAVAILABLE
    assert lifecycle.controller is controller
    assert lifecycle.current.phase is AssistantRuntimePhase.FAILED
    assert lifecycle.current.initialized is True
    assert lifecycle.current.backend_mode == "local"
    assert lifecycle.current.model_id == model_id
    assert lifecycle.active_local_runtime_blocks_model_deletion() is True
    admission = lifecycle.submit("must remain blocked until recovery")
    assert admission.status is RuntimeCommandAdmissionStatus.REJECTED
    assert dispatcher.submissions == []

    recovered = lifecycle.activate(
        _ready_config(model_id),
    )
    assert recovered.status is RuntimeActivationStatus.ALREADY_READY
    assert lifecycle.current.phase is AssistantRuntimePhase.READY
    assert lifecycle.current.model_id == model_id


def test_activation_watchdog_fails_and_retry_restores_ready(qtbot) -> None:
    model_id = LLMConfig.default_local_model_id()
    dispatcher = _Dispatcher()
    factory_calls = 0

    def factory(_study: object) -> _Controller:
        nonlocal factory_calls
        factory_calls += 1
        return _Controller()

    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=factory,
        dispatcher=dispatcher,
        config_loader=lambda: _ready_config(model_id),
        activation_timeout_ms=10,
    )

    started = lifecycle.activate(_ready_config(model_id))
    assert started.status is RuntimeActivationStatus.STARTED
    qtbot.waitUntil(
        lambda: lifecycle.current.phase is AssistantRuntimePhase.FAILED,
        timeout=1_000,
    )
    assert "timed out" in lifecycle.current.error.lower()

    retried = lifecycle.activate(_ready_config(model_id))
    assert retried.status is RuntimeActivationStatus.SWITCHING
    assert retried.launch_spec is not None
    assert lifecycle.current.phase is AssistantRuntimePhase.LOADING
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=model_id,
            activation_id=retried.activation_id or 0,
        )
    )

    assert lifecycle.current.phase is AssistantRuntimePhase.READY
    assert factory_calls == 1
    assert dispatcher.bind_calls == 1


def test_timed_out_activation_recovers_when_its_late_ready_arrives(qtbot) -> None:
    model_id = LLMConfig.default_local_model_id()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: _Controller(),
        dispatcher=_Dispatcher(),
        config_loader=lambda: _ready_config(model_id),
        activation_timeout_ms=10,
    )

    started = lifecycle.activate(_ready_config(model_id))
    assert started.activation_id is not None
    qtbot.waitUntil(
        lambda: lifecycle.current.phase is AssistantRuntimePhase.FAILED,
        timeout=1_000,
    )

    assert lifecycle.expected_activation_id == started.activation_id
    assert lifecycle.active_local_runtime_blocks_model_deletion() is True

    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=model_id,
            activation_id=started.activation_id,
        )
    )

    assert lifecycle.current.phase is AssistantRuntimePhase.READY
    assert lifecycle.current.initialized is True
    assert lifecycle.expected_activation_id is None


def test_stale_same_model_completion_does_not_finish_new_activation() -> None:
    primary_model = LLMConfig.default_local_model_id()
    fallback_model = LLMConfig.fallback_local_model_id()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: _Controller(),
        dispatcher=_Dispatcher(),
        config_loader=lambda: _ready_config(fallback_model),
    )
    started = lifecycle.activate(_ready_config(primary_model))
    assert started.launch_spec is not None
    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=primary_model,
            activation_id=started.activation_id or 0,
        )
    )
    first = lifecycle.switch_model(fallback_model)
    second = lifecycle.switch_model(fallback_model)
    assert first.launch_spec is not None
    assert second.launch_spec is not None

    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=fallback_model,
            activation_id=first.activation_id or 0,
        )
    )
    assert lifecycle.current.phase is AssistantRuntimePhase.LOADING
    assert lifecycle.expected_activation_id == second.activation_id

    lifecycle.accept_runtime_snapshot(
        _ActivationTransition(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=fallback_model,
            activation_id=second.activation_id or 0,
        )
    )
    assert lifecycle.current.phase is AssistantRuntimePhase.READY


def test_start_rolls_back_factory_failure_and_can_retry(qtbot) -> None:
    del qtbot
    controller = _Controller()
    dispatcher = _Dispatcher()
    attempts = 0
    created: list[object] = []

    def factory(_study: object) -> object:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("factory failed")
        return controller

    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=factory,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    lifecycle.controller_created.connect(created.append)

    assert lifecycle.start() is False
    assert lifecycle.current.phase is AssistantRuntimePhase.FAILED
    assert lifecycle.current.initialized is False
    assert lifecycle.current.model_id == ""
    assert lifecycle.controller is None
    assert lifecycle.initialized is False
    assert created == []

    assert lifecycle.start() is True
    assert lifecycle.controller is controller
    assert lifecycle.initialized is True
    assert created == [controller]


def test_start_rolls_back_bind_failure_without_publishing_controller(qtbot) -> None:
    del qtbot
    controller = _Controller()
    dispatcher = _FailingDispatcher("bind")
    created: list[object] = []
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    lifecycle.controller_created.connect(created.append)

    assert lifecycle.start() is False

    assert lifecycle.current.phase is AssistantRuntimePhase.FAILED
    assert lifecycle.controller is None
    assert lifecycle.initialized is False
    assert controller.closed is True
    assert dispatcher.closed is False
    assert created == []


def test_start_rolls_back_initialize_failure_and_closes_bound_dispatcher(
    qtbot,
) -> None:
    del qtbot
    controller = _Controller()
    dispatcher = _FailingDispatcher("initialize")
    created: list[object] = []
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    lifecycle.controller_created.connect(created.append)

    assert lifecycle.start() is False

    assert lifecycle.current.phase is AssistantRuntimePhase.FAILED
    assert lifecycle.controller is None
    assert lifecycle.initialized is False
    assert dispatcher.closed is True
    assert created == []


def test_failed_start_retains_controller_until_rollback_cleanup_succeeds(
    qtbot,
) -> None:
    del qtbot
    controller = _Controller()
    dispatcher = _RetryingCloseDispatcher()
    created: list[object] = []
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    lifecycle.controller_created.connect(created.append)

    assert lifecycle.start() is False

    assert dispatcher.close_attempts == 1
    assert lifecycle.controller is controller
    assert lifecycle.initialized is False
    assert created == []

    assert lifecycle.close() is True
    assert dispatcher.close_attempts == 2
    assert lifecycle.controller is None
    assert lifecycle.initialized is False


def test_failed_close_blocks_dispatch_and_late_ready_until_cleanup_succeeds() -> None:
    controller = _Controller()
    dispatcher = _CleanupPendingDispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    assert lifecycle.start() is True
    activation_id = lifecycle.expected_activation_id
    assert activation_id is not None
    ready = AssistantRuntimeSnapshot(
        phase=AssistantRuntimePhase.READY,
        initialized=True,
        backend_mode="local",
        model_id=LLMConfig.default_local_model_id(),
        activation_id=activation_id,
    )
    lifecycle.accept_runtime_snapshot(ready)
    assert lifecycle.current.phase is AssistantRuntimePhase.READY

    assert lifecycle.close() is False
    assert lifecycle.initialized is False
    assert lifecycle.state is AssistantRuntimeLifecycleState.CLEANUP_PENDING
    assert lifecycle.accepts_commands is False
    assert lifecycle.current.phase is AssistantRuntimePhase.FAILED
    assert lifecycle.active_local_runtime_blocks_model_deletion() is True

    admission = lifecycle.submit("after-close")
    lifecycle.accept_runtime_snapshot(ready)

    assert dispatcher.submissions == []
    assert admission.status is RuntimeCommandAdmissionStatus.REJECTED
    assert "shutdown" in admission.message.lower()
    assert lifecycle.current.phase is AssistantRuntimePhase.FAILED
    assert lifecycle.start() is False
    assert lifecycle.close() is True
    assert dispatcher.close_attempts == 2
    assert lifecycle.state is AssistantRuntimeLifecycleState.CLOSED
    assert lifecycle.controller is None
    assert lifecycle.active_local_runtime_blocks_model_deletion() is False


def test_close_exception_keeps_runtime_retryable_until_cleanup_succeeds() -> None:
    controller = _Controller()
    dispatcher = _ExceptionThenSuccessDispatcher()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: controller,
        dispatcher=dispatcher,
        config_loader=_ready_config,
    )
    assert lifecycle.start() is True

    assert lifecycle.close() is False

    assert dispatcher.close_attempts == 1
    assert lifecycle.state is AssistantRuntimeLifecycleState.CLEANUP_PENDING
    assert lifecycle.accepts_commands is False
    assert lifecycle.initialized is False
    assert lifecycle.controller is controller

    admission = lifecycle.submit("must remain blocked while cleanup is pending")
    assert dispatcher.submissions == []
    assert admission.status is RuntimeCommandAdmissionStatus.REJECTED
    assert "restart" in admission.message.lower()

    assert lifecycle.close() is True

    assert dispatcher.close_attempts == 2
    assert lifecycle.state is AssistantRuntimeLifecycleState.CLOSED
    assert lifecycle.controller is None

    assert lifecycle.close() is True
    assert dispatcher.close_attempts == 2


def test_activate_closed_lifecycle_reports_unavailable_instead_of_started() -> None:
    factory_calls = 0

    def factory(_study: object) -> object:
        nonlocal factory_calls
        factory_calls += 1
        return _Controller()

    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=factory,
        dispatcher=_Dispatcher(),
    )
    assert lifecycle.close() is True

    result = lifecycle.activate(_ready_config())

    assert result.status is RuntimeActivationStatus.UNAVAILABLE
    assert "closed" in result.message.lower()
    assert lifecycle.current.phase is AssistantRuntimePhase.FAILED
    assert lifecycle.controller is None
    assert lifecycle.initialized is False
    assert factory_calls == 0


def test_lifecycle_first_run_decision_persists_runtime_policy(monkeypatch) -> None:
    lifecycle = AssistantRuntimeLifecycle(
        study=object(),
        controller_factory=lambda _study: _Controller(),
        dispatcher=_Dispatcher(),
        config_loader=_ready_config,
    )
    config = LLMConfig()
    saves: list[LLMConfig] = []
    monkeypatch.setattr(
        config, "save_to_file", lambda filepath=None: saves.append(config)
    )

    disabled = lifecycle.apply_first_run_choice(config, "disable")
    assert disabled.action is RuntimeSetupAction.STOP
    assert "disabled" in disabled.message.lower()
    assert config.local_model_enabled is False
    assert config.local_runtime_notice_acknowledged is True
    assert saves == [config]

    deferred_config = LLMConfig()
    deferred = lifecycle.apply_first_run_choice(deferred_config, "later")
    assert deferred.action is RuntimeSetupAction.STOP
    assert "deferred" in deferred.message.lower()


def test_agent_manager_keeps_runtime_state_out_of_its_instance(qtbot) -> None:
    from unittest.mock import MagicMock

    from PyQt6.QtWidgets import QMainWindow

    from XBrainLab.ui.components.agent_manager import AgentManager

    main_window = QMainWindow()
    main_window.ai_btn = MagicMock()  # type: ignore[attr-defined]
    qtbot.addWidget(main_window)
    manager = AgentManager(main_window, MagicMock())

    assert "agent_controller" not in manager.__dict__
    assert "agent_initialized" not in manager.__dict__
    assert "_agent_dispatcher" not in manager.__dict__
    assert manager.agent_controller is manager.assistant_runtime.controller
    assert manager.agent_initialized is manager.assistant_runtime.initialized
