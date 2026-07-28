"""Full-topology regressions for assistant turn lifecycle failures."""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QMainWindow

from XBrainLab.backend.controller.chat_controller import ChatMessagePresentationKind
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.rag_lifecycle import RAGRetrieverLifecycle
from XBrainLab.llm.agent.response_presentation import AssistantResponseKind
from XBrainLab.llm.agent.runtime_state import AssistantRuntimePhase
from XBrainLab.llm.agent.turn import (
    AssistantGenerationDispatchAcknowledgement,
    AssistantGenerationDispatchPhase,
    AssistantGenerationEvent,
    AssistantGenerationEventPhase,
    AssistantGenerationRequest,
    AssistantTurnDeliveryAcknowledgement,
    AssistantTurnDeliveryPhase,
    AssistantTurnRequest,
    AssistantTurnTerminal,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeBackend,
    AssistantRuntimeLaunchSpec,
    AssistantRuntimeSelectionOutcome,
    AssistantRuntimeSettingsSnapshot,
)
from XBrainLab.ui.components.agent_manager import AgentManager
from XBrainLab.ui.components.assistant_runtime_lifecycle import (
    AssistantRuntimeLifecycle,
    AssistantRuntimeLifecycleState,
    RuntimeCommandAdmissionStatus,
)

_RAG_CONTEXT = "EEG band context from the retriever."


class _NoopRetriever:
    def initialize(self) -> None:
        return None

    def get_similar_examples(
        self,
        query: str,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> str:
        del query, allowed_tool_names
        return ""

    def close(self) -> None:
        return None


class _ContextRetriever(_NoopRetriever):
    def get_similar_examples(
        self,
        query: str,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> str:
        del query, allowed_tool_names
        return _RAG_CONTEXT


class _InMemoryEngine:
    """Avoid model IO while retaining the real AgentWorker generation thread."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def load_model(self) -> None:
        return None

    def generate_stream(self, _messages: list[dict[str, Any]], *, profile: Any):
        del profile
        yield "Recovered assistant response."

    def cancel_generation(self, wait_timeout: float = 0.25) -> bool:
        del wait_timeout
        return True

    def close(self) -> None:
        return None


def _launch_spec() -> AssistantRuntimeLaunchSpec:
    model_id = LLMConfig.default_local_model_id()
    config = LLMConfig(model_name=model_id)
    return AssistantRuntimeLaunchSpec(
        backend=AssistantRuntimeBackend.LOCAL,
        requested_backend_id="local",
        requested_model_id=model_id,
        model_id=model_id,
        outcome=AssistantRuntimeSelectionOutcome.EXACT,
        selection_detail="Local runtime ready.",
        settings=AssistantRuntimeSettingsSnapshot.from_config(config),
    )


@pytest.fixture
def lifecycle_harness(
    qtbot, monkeypatch
) -> Iterator[tuple[AssistantRuntimeLifecycle, LLMController]]:
    monkeypatch.setattr(
        "XBrainLab.llm.agent.worker.LLMEngine",
        _InMemoryEngine,
    )
    controllers: list[LLMController] = []

    def _controller_factory(study: object) -> LLMController:
        controller = LLMController(
            study,
            rag_lifecycle=RAGRetrieverLifecycle(_NoopRetriever()),
        )
        controllers.append(controller)
        return controller

    lifecycle = AssistantRuntimeLifecycle(
        Study(),
        controller_factory=_controller_factory,
    )
    assert lifecycle.start(launch_spec=_launch_spec()) is True
    qtbot.waitUntil(
        lambda: lifecycle.current.phase is AssistantRuntimePhase.READY,
        timeout=2_000,
    )
    controller = controllers[0]
    worker = controller.worker
    worker_thread = controller.worker_thread
    yield lifecycle, controller

    closed = lifecycle.close()
    if not closed:
        qtbot.waitUntil(
            lambda: lifecycle.state is AssistantRuntimeLifecycleState.CLOSED,
            timeout=5_000,
        )
    assert lifecycle.state is AssistantRuntimeLifecycleState.CLOSED
    assert worker_thread.isRunning() is False
    assert worker is not None
    qtbot.waitUntil(lambda: sip.isdeleted(worker), timeout=2_000)


@pytest.fixture
def manager_lifecycle_harness(qtbot, monkeypatch):
    monkeypatch.setattr(
        "XBrainLab.llm.agent.worker.LLMEngine",
        _InMemoryEngine,
    )
    controllers: list[LLMController] = []
    study = Study()

    def _controller_factory(controller_study: object) -> LLMController:
        controller = LLMController(
            controller_study,
            rag_lifecycle=RAGRetrieverLifecycle(_NoopRetriever()),
        )
        controllers.append(controller)
        return controller

    lifecycle = AssistantRuntimeLifecycle(
        study,
        controller_factory=_controller_factory,
    )
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    manager = AgentManager(
        main_window,
        study,
        runtime_lifecycle=lifecycle,
    )
    assert lifecycle.start(launch_spec=_launch_spec()) is True
    qtbot.waitUntil(
        lambda: lifecycle.current.phase is AssistantRuntimePhase.READY,
        timeout=2_000,
    )
    controller = controllers[0]
    worker = controller.worker
    worker_thread = controller.worker_thread
    yield manager, lifecycle, controller

    closed = manager.close()
    if not closed:
        qtbot.waitUntil(
            lambda: lifecycle.state is AssistantRuntimeLifecycleState.CLOSED,
            timeout=5_000,
        )
    assert lifecycle.state is AssistantRuntimeLifecycleState.CLOSED
    assert worker_thread.isRunning() is False
    assert worker is not None
    qtbot.waitUntil(lambda: sip.isdeleted(worker), timeout=2_000)


def test_manager_queued_controller_slot_exception_releases_and_next_turn_succeeds(
    manager_lifecycle_harness,
    qtbot,
    monkeypatch,
) -> None:
    manager, lifecycle, controller = manager_lifecycle_harness
    original_handler = controller.handle_user_turn
    attempts = 0
    delivery_threads: list[QThread] = []
    uncaught: list[BaseException] = []
    terminals: list[AssistantTurnTerminal] = []
    visible_errors: list[str] = []
    original_add_agent_message = manager.chat_controller.add_agent_message

    def _capture_agent_message(message: str, *args: Any, **kwargs: Any) -> object:
        visible_errors.append(message)
        return original_add_agent_message(message, *args, **kwargs)

    def _fail_first_delivery(payload: object):
        nonlocal attempts
        attempts += 1
        current_thread = QThread.currentThread()
        assert current_thread is not None
        delivery_threads.append(current_thread)
        if attempts == 1:
            raise RuntimeError("fault injection: queued controller slot failed")
        return original_handler(payload)

    monkeypatch.setattr(controller, "handle_user_turn", _fail_first_delivery)
    monkeypatch.setattr(
        sys,
        "excepthook",
        lambda _type, value, _traceback: uncaught.append(value),
    )
    monkeypatch.setattr(
        manager.chat_controller,
        "add_agent_message",
        _capture_agent_message,
    )
    lifecycle.turn_finished.connect(terminals.append)
    command_thread = lifecycle.dispatcher.command_thread
    assert command_thread is not None
    assert command_thread.objectName() == "AssistantCommandThread"
    assert command_thread.isRunning()

    manager.handle_user_input("first queued request")
    first_correlation = manager._assistant_turn_state.lease
    assert first_correlation is not None
    qtbot.waitUntil(lambda: len(terminals) == 1, timeout=2_000)

    assert terminals[0].correlation == first_correlation
    assert terminals[0].outcome == "delivery_error"
    assert delivery_threads == [command_thread]
    assert uncaught == []
    assert lifecycle.turn_in_flight is False
    assert manager._assistant_turn_state.lease is None
    assert manager.chat_controller.is_processing is False
    assert controller._active_host_turn_id is None
    assert controller._active_host_turn_generation is None
    assert controller._active_generation_id is None
    assert len(visible_errors) == 1
    assert "could not receive this request" in visible_errors[0].lower()
    assert "retry" in visible_errors[0].lower()
    assert (
        manager.chat_controller.get_typed_history()[-1].presentation_kind
        is ChatMessagePresentationKind.ERROR
    )

    manager.handle_user_input("Explain event-related potentials in one sentence.")
    second_correlation = manager._assistant_turn_state.lease
    assert second_correlation is not None
    assert second_correlation != first_correlation
    qtbot.waitUntil(lambda: len(terminals) == 2, timeout=2_000)

    assert terminals[1].correlation == second_correlation
    assert terminals[1].outcome == "completed"
    assert delivery_threads == [command_thread, command_thread]
    assert lifecycle.turn_in_flight is False
    assert manager._assistant_turn_state.lease is None
    assert manager.chat_controller.is_processing is False
    assert len(visible_errors) == 2


def test_manager_queued_controller_rejection_shows_recoverable_error(
    manager_lifecycle_harness,
    qtbot,
) -> None:
    """A controller-side rejection must not leave a user turn without a reply."""
    manager, lifecycle, controller = manager_lifecycle_harness
    terminals: list[AssistantTurnTerminal] = []
    controller.is_processing = True
    lifecycle.turn_finished.connect(terminals.append)

    manager.handle_user_input("Request while the controller is already busy.")
    correlation = manager._assistant_turn_state.lease
    assert correlation is not None

    qtbot.waitUntil(lambda: len(terminals) == 1, timeout=2_000)

    assert terminals == [
        AssistantTurnTerminal(
            correlation=correlation,
            outcome="rejected_busy",
        )
    ]
    assert lifecycle.turn_in_flight is False
    assert manager._assistant_turn_state.lease is None
    assert manager.chat_controller.is_processing is False
    response = manager.chat_controller.get_typed_history()[-1]
    assert response.presentation_kind is ChatMessagePresentationKind.ERROR
    assert "did not accept this request" in response.content.lower()
    assert "retry" in response.content.lower()


@pytest.mark.parametrize("fault_mode", ["ack_lost", "ack_handler_exception"])
def test_manager_delivery_watchdog_releases_lost_or_failed_ack_exactly_once(
    manager_lifecycle_harness,
    qtbot,
    monkeypatch,
    fault_mode: str,
) -> None:
    """The host lease cannot depend on one fallible queued Qt acknowledgement."""
    manager, lifecycle, controller = manager_lifecycle_harness
    original_handler = controller.handle_user_turn
    dispatcher = lifecycle.dispatcher
    bridge = dispatcher._shutdown_bridge
    assert bridge is not None
    lifecycle._turn_delivery_timeout_ms = 50
    terminals: list[AssistantTurnTerminal] = []
    visible_errors: list[str] = []
    uncaught: list[BaseException] = []
    original_add_agent_message = manager.chat_controller.add_agent_message

    def _capture_agent_message(message: str, *args: Any, **kwargs: Any) -> object:
        visible_errors.append(message)
        return original_add_agent_message(message, *args, **kwargs)

    def _accept_without_terminal(
        request: object,
    ) -> AssistantTurnDeliveryAcknowledgement:
        assert isinstance(request, AssistantTurnRequest)
        return AssistantTurnDeliveryAcknowledgement(
            correlation=request.correlation,
            phase=AssistantTurnDeliveryPhase.ACCEPTED,
        )

    def _raise_ack_handler(_payload: object) -> None:
        raise RuntimeError("fault injection: queued acknowledgement handler failed")

    monkeypatch.setattr(controller, "handle_user_turn", _accept_without_terminal)
    monkeypatch.setattr(
        manager.chat_controller,
        "add_agent_message",
        _capture_agent_message,
    )
    monkeypatch.setattr(
        sys,
        "excepthook",
        lambda _type, value, _traceback: uncaught.append(value),
    )
    lifecycle.turn_finished.connect(terminals.append)

    if fault_mode == "ack_lost":
        bridge.turn_delivery_acknowledged.disconnect()
    else:
        dispatcher.turn_delivery_acknowledged.disconnect(
            lifecycle._on_turn_delivery_acknowledged
        )
        dispatcher.turn_delivery_acknowledged.connect(_raise_ack_handler)

    manager.handle_user_input("Probe queued delivery acknowledgement.")
    correlation = manager._assistant_turn_state.lease
    assert correlation is not None
    assert lifecycle.turn_in_flight is True

    qtbot.waitUntil(lambda: len(terminals) == 1, timeout=2_000)
    qtbot.wait(100)

    assert terminals == [
        AssistantTurnTerminal(
            correlation=correlation,
            outcome="delivery_timeout",
        )
    ]
    assert lifecycle.turn_in_flight is False
    assert manager._assistant_turn_state.lease is None
    assert manager.chat_controller.is_processing is False
    assert len(visible_errors) == 1
    assert "did not acknowledge" in visible_errors[0].lower()
    assert "retry" in visible_errors[0].lower()
    if fault_mode == "ack_handler_exception":
        assert len(uncaught) == 1
        assert "acknowledgement handler failed" in str(uncaught[0])
        dispatcher.turn_delivery_acknowledged.disconnect(_raise_ack_handler)
        dispatcher.turn_delivery_acknowledged.connect(
            lifecycle._on_turn_delivery_acknowledged
        )
    else:
        assert uncaught == []
        bridge.turn_delivery_acknowledged.connect(
            dispatcher.turn_delivery_acknowledged.emit
        )

    worker = controller.worker
    assert worker is not None
    engine = worker.engine
    assert engine is not None

    def _valid_recovery_response(
        _messages: list[dict[str, Any]],
        *,
        profile: Any,
    ):
        del profile
        yield (
            '{"tool_name":"respond_to_user","parameters":'
            '{"decision":"answer","message":"Transport recovered."}}'
        )

    monkeypatch.setattr(engine, "generate_stream", _valid_recovery_response)
    monkeypatch.setattr(controller, "handle_user_turn", original_handler)
    lifecycle._turn_delivery_timeout_ms = lifecycle.DEFAULT_TURN_DELIVERY_TIMEOUT_MS
    manager.handle_user_input("Complete a request after transport recovery.")
    recovered_correlation = manager._assistant_turn_state.lease
    assert recovered_correlation is not None
    assert recovered_correlation != correlation
    qtbot.waitUntil(lambda: len(terminals) == 2, timeout=2_000)

    assert terminals[1] == AssistantTurnTerminal(
        correlation=recovered_correlation,
        outcome="completed",
    )
    assert lifecycle.turn_in_flight is False
    assert manager._assistant_turn_state.lease is None
    assert manager.chat_controller.is_processing is False
    assert len(visible_errors) == 2


def test_manager_controller_turn_setup_exception_releases_and_retries(
    manager_lifecycle_harness,
    qtbot,
    monkeypatch,
) -> None:
    manager, lifecycle, controller = manager_lifecycle_harness
    original_setup = controller._handle_admitted_user_input
    attempts = 0
    controller_terminals: list[AssistantTurnTerminal] = []
    runtime_terminals: list[AssistantTurnTerminal] = []

    def _fail_first_setup(text: str) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("fault injection: controller turn setup failed")
        original_setup(text)

    monkeypatch.setattr(
        controller,
        "_handle_admitted_user_input",
        _fail_first_setup,
    )
    controller.turn_finished.connect(controller_terminals.append)
    lifecycle.turn_finished.connect(runtime_terminals.append)

    manager.handle_user_input(
        "Explain the difference between alpha and beta EEG rhythms."
    )
    first_correlation = manager._assistant_turn_state.lease
    assert first_correlation is not None
    qtbot.waitUntil(lambda: len(runtime_terminals) == 1, timeout=2_000)
    qtbot.wait(25)

    assert controller_terminals == runtime_terminals
    assert runtime_terminals[0].correlation == first_correlation
    assert runtime_terminals[0].outcome == "delivery_error"
    assert lifecycle.turn_in_flight is False
    assert manager._assistant_turn_state.lease is None
    assert manager.chat_controller.is_processing is False
    assert controller.is_processing is False
    assert controller._active_host_turn_id is None
    assert controller._active_host_turn_generation is None
    assert controller._active_generation_id is None

    manager.handle_user_input("Explain event-related potentials in one sentence.")
    second_correlation = manager._assistant_turn_state.lease
    assert second_correlation is not None
    assert second_correlation != first_correlation
    qtbot.waitUntil(lambda: len(runtime_terminals) == 2, timeout=2_000)

    assert attempts == 2
    assert runtime_terminals[1].correlation == second_correlation
    assert runtime_terminals[1].outcome == "completed"
    assert lifecycle.turn_in_flight is False
    assert manager._assistant_turn_state.lease is None
    assert manager.chat_controller.is_processing is False


def test_slow_generation_diagnostic_observer_cannot_delay_worker_dispatch(
    manager_lifecycle_harness,
    qtbot,
) -> None:
    manager, lifecycle, controller = manager_lifecycle_harness
    dispatch_started = threading.Event()
    diagnostic_entered = threading.Event()
    terminals: list[AssistantTurnTerminal] = []

    def _observe_dispatch(_request: object) -> None:
        dispatch_started.set()

    def _slow_diagnostic(_request: object) -> None:
        diagnostic_entered.set()
        time.sleep(0.30)

    controller._sig_dispatch_generation.connect(_observe_dispatch)
    controller.sig_generate.connect(_slow_diagnostic)
    lifecycle.turn_finished.connect(terminals.append)

    manager.handle_user_input(
        "Explain the difference between alpha and beta EEG rhythms."
    )
    qtbot.waitUntil(diagnostic_entered.is_set, timeout=2_000)
    assert dispatch_started.is_set()
    qtbot.waitUntil(lambda: len(terminals) == 1, timeout=2_000)

    assert terminals[0].outcome == "completed"


def test_raising_generation_diagnostic_observer_is_isolated_from_dispatch(
    manager_lifecycle_harness,
    qtbot,
    monkeypatch,
) -> None:
    manager, lifecycle, controller = manager_lifecycle_harness
    uncaught: list[BaseException] = []
    dispatched: list[int] = []
    terminals: list[AssistantTurnTerminal] = []

    def _observe_dispatch(request: object) -> None:
        assert isinstance(request, AssistantGenerationRequest)
        dispatched.append(request.generation_id)

    def _raise_diagnostic(_request: object) -> None:
        raise RuntimeError("fault injection: diagnostic observer failed")

    monkeypatch.setattr(
        sys,
        "excepthook",
        lambda _type, value, _traceback: uncaught.append(value),
    )
    controller._sig_dispatch_generation.connect(_observe_dispatch)
    controller.sig_generate.connect(_raise_diagnostic)
    lifecycle.turn_finished.connect(terminals.append)

    manager.handle_user_input("Explain event-related potentials in one sentence.")
    qtbot.waitUntil(lambda: len(terminals) == 1, timeout=2_000)

    assert uncaught == []
    assert len(dispatched) == 1
    assert terminals[0].outcome == "completed"


def test_prompt_assembly_failure_emits_one_terminal_and_releases_runtime_lease(
    lifecycle_harness: tuple[AssistantRuntimeLifecycle, LLMController],
    qtbot,
    monkeypatch,
) -> None:
    lifecycle, controller = lifecycle_harness
    original_get_generation_request = controller.assembler.get_generation_request
    request_build_count = 0

    def _fail_once(history):
        nonlocal request_build_count
        request_build_count += 1
        if request_build_count == 1:
            raise RuntimeError("fault injection: prompt assembly failed")
        return original_get_generation_request(history)

    monkeypatch.setattr(
        controller.assembler,
        "get_generation_request",
        _fail_once,
    )
    controller_terminals: list[AssistantTurnTerminal] = []
    runtime_terminals: list[AssistantTurnTerminal] = []
    generation_events: list[AssistantGenerationEvent] = []
    presentations = []
    controller.turn_finished.connect(controller_terminals.append)
    lifecycle.turn_finished.connect(runtime_terminals.append)
    controller.generation_event.connect(generation_events.append)
    controller.response_presentation_ready.connect(presentations.append)

    first = lifecycle.submit(
        "Explain the difference between alpha and beta EEG rhythms.",
        generation=1,
    )
    assert first.status is RuntimeCommandAdmissionStatus.ACCEPTED
    assert lifecycle.turn_in_flight is True

    qtbot.waitUntil(lambda: len(runtime_terminals) == 1, timeout=2_000)
    qtbot.wait(50)

    assert controller_terminals == runtime_terminals
    assert len(runtime_terminals) == 1
    assert runtime_terminals[0].correlation == first.correlation
    assert runtime_terminals[0].outcome == "generation_request_failed"
    assert lifecycle.turn_in_flight is False
    assert controller.is_processing is False
    assert controller._waiting_for_rag is False
    assert controller._active_rag_turn_id is None
    assert controller._stopping_generation_id is None
    assert controller._active_generation_id is None
    assert controller._active_host_turn_id is None
    assert controller._active_host_turn_generation is None
    assert [
        event
        for event in generation_events
        if event.phase
        in {
            AssistantGenerationEventPhase.ERROR,
            AssistantGenerationEventPhase.FINISHED,
            AssistantGenerationEventPhase.CANCELLED,
        }
    ] == []
    assert presentations[-1].kind is AssistantResponseKind.ERROR

    second = lifecycle.submit(
        "Explain event-related potentials in one sentence.",
        generation=2,
    )
    assert second.status is RuntimeCommandAdmissionStatus.ACCEPTED
    assert lifecycle.turn_in_flight is True

    qtbot.waitUntil(lambda: len(runtime_terminals) == 2, timeout=2_000)

    assert request_build_count == 2
    assert runtime_terminals[1].correlation == second.correlation
    assert runtime_terminals[1].outcome == "completed"
    assert lifecycle.turn_in_flight is False
    assert controller.is_processing is False
    assert [event.phase for event in generation_events] == [
        AssistantGenerationEventPhase.STARTED,
        AssistantGenerationEventPhase.CHUNK,
        AssistantGenerationEventPhase.FINISHED,
    ]


def test_post_rag_context_failure_releases_full_topology_leases_and_next_turn(
    qtbot,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "XBrainLab.llm.agent.worker.LLMEngine",
        _InMemoryEngine,
    )
    controllers: list[LLMController] = []
    study = Study()

    def _controller_factory(controller_study: object) -> LLMController:
        controller = LLMController(
            controller_study,
            rag_lifecycle=RAGRetrieverLifecycle(_ContextRetriever()),
        )
        controllers.append(controller)
        return controller

    lifecycle = AssistantRuntimeLifecycle(
        study,
        controller_factory=_controller_factory,
    )
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    manager = AgentManager(
        main_window,
        study,
        runtime_lifecycle=lifecycle,
    )
    assert lifecycle.start(launch_spec=_launch_spec()) is True
    qtbot.waitUntil(
        lambda: lifecycle.current.phase is AssistantRuntimePhase.READY,
        timeout=2_000,
    )
    controller = controllers[0]
    worker = controller.worker
    worker_thread = controller.worker_thread
    original_add_context = controller.assembler.add_context
    context_injection_count = 0

    def _fail_once(features: str) -> None:
        nonlocal context_injection_count
        context_injection_count += 1
        assert features == _RAG_CONTEXT
        if context_injection_count == 1:
            raise RuntimeError("fault injection: RAG context injection failed")
        original_add_context(features)

    monkeypatch.setattr(controller.assembler, "add_context", _fail_once)
    controller_terminals: list[AssistantTurnTerminal] = []
    runtime_terminals: list[AssistantTurnTerminal] = []
    generation_events: list[AssistantGenerationEvent] = []
    controller.turn_finished.connect(controller_terminals.append)
    lifecycle.turn_finished.connect(runtime_terminals.append)
    controller.generation_event.connect(generation_events.append)

    try:
        manager.handle_user_input(
            "Explain the difference between alpha and beta EEG rhythms."
        )
        first_correlation = manager._assistant_turn_state.lease
        assert first_correlation is not None
        assert lifecycle.turn_in_flight is True

        qtbot.waitUntil(lambda: len(runtime_terminals) == 1, timeout=2_000)
        qtbot.wait(50)

        assert controller_terminals == runtime_terminals
        assert len(runtime_terminals) == 1
        assert runtime_terminals[0].correlation == first_correlation
        assert runtime_terminals[0].outcome == "generation_request_failed"
        assert lifecycle.turn_in_flight is False
        assert manager._assistant_turn_state.lease is None
        assert manager.chat_controller.is_processing is False
        assert controller.is_processing is False
        assert controller._waiting_for_rag is False
        assert controller._active_rag_turn_id is None
        assert controller._stopping_generation_id is None
        assert controller._active_generation_id is None
        assert controller._active_host_turn_id is None
        assert controller._active_host_turn_generation is None
        assert generation_events == []

        manager.handle_user_input("Explain event-related potentials in one sentence.")
        second_correlation = manager._assistant_turn_state.lease
        assert second_correlation is not None
        assert second_correlation != first_correlation
        assert lifecycle.turn_in_flight is True

        qtbot.waitUntil(lambda: len(runtime_terminals) == 2, timeout=2_000)

        assert context_injection_count == 2
        assert runtime_terminals[1].correlation == second_correlation
        assert runtime_terminals[1].outcome == "completed"
        assert lifecycle.turn_in_flight is False
        assert manager._assistant_turn_state.lease is None
        assert manager.chat_controller.is_processing is False
        assert controller.is_processing is False
        assert [event.phase for event in generation_events] == [
            AssistantGenerationEventPhase.STARTED,
            AssistantGenerationEventPhase.CHUNK,
            AssistantGenerationEventPhase.FINISHED,
        ]
    finally:
        closed = manager.close()
        if not closed:
            qtbot.waitUntil(
                lambda: lifecycle.state is AssistantRuntimeLifecycleState.CLOSED,
                timeout=5_000,
            )
        assert lifecycle.state is AssistantRuntimeLifecycleState.CLOSED
        assert worker_thread.isRunning() is False
        assert worker is not None
        qtbot.waitUntil(lambda: sip.isdeleted(worker), timeout=2_000)


def test_worker_dispatch_setup_and_model_faults_release_manager_turns(
    qtbot,
    monkeypatch,
) -> None:
    """Every worker-side fault reaches one manager terminal and permits retry."""
    from XBrainLab.llm.agent import worker as worker_module

    monkeypatch.setattr(
        worker_module,
        "LLMEngine",
        _InMemoryEngine,
    )
    controllers: list[LLMController] = []
    study = Study()

    def _controller_factory(controller_study: object) -> LLMController:
        controller = LLMController(
            controller_study,
            rag_lifecycle=RAGRetrieverLifecycle(_NoopRetriever()),
        )
        controllers.append(controller)
        return controller

    lifecycle = AssistantRuntimeLifecycle(
        study,
        controller_factory=_controller_factory,
    )
    main_window = QMainWindow()
    qtbot.addWidget(main_window)
    manager = AgentManager(
        main_window,
        study,
        runtime_lifecycle=lifecycle,
    )
    assert lifecycle.start(launch_spec=_launch_spec()) is True
    qtbot.waitUntil(
        lambda: lifecycle.current.phase is AssistantRuntimePhase.READY,
        timeout=2_000,
    )
    controller = controllers[0]
    worker = controller.worker
    worker_thread = controller.worker_thread
    assert worker is not None

    original_thread_type = worker_module.GenerationThread
    setup_attempts = 0

    def _fail_first_thread_setup(engine, request):
        nonlocal setup_attempts
        setup_attempts += 1
        if setup_attempts == 1:
            raise RuntimeError("fault injection: worker thread setup failed")
        return original_thread_type(engine, request)

    original_generate_stream = _InMemoryEngine.generate_stream
    model_invocations = 0

    def _fail_first_model_invocation(self, messages, *, profile):
        nonlocal model_invocations
        model_invocations += 1
        if model_invocations == 1:
            raise RuntimeError("fault injection: model invocation failed")
        yield from original_generate_stream(self, messages, profile=profile)

    monkeypatch.setattr(
        worker_module,
        "GenerationThread",
        _fail_first_thread_setup,
    )
    monkeypatch.setattr(
        _InMemoryEngine,
        "generate_stream",
        _fail_first_model_invocation,
    )

    runtime_terminals: list[AssistantTurnTerminal] = []
    generation_events: list[AssistantGenerationEvent] = []
    dispatch_events: list[AssistantGenerationDispatchAcknowledgement] = []
    lifecycle.turn_finished.connect(runtime_terminals.append)
    controller.generation_event.connect(generation_events.append)
    worker.generation_dispatch_acknowledged.connect(dispatch_events.append)

    def _assert_turn_ownership_released() -> None:
        qtbot.waitUntil(lambda: worker.generation_thread is None, timeout=2_000)
        assert lifecycle.turn_in_flight is False
        assert manager._assistant_turn_state.lease is None
        assert manager.chat_controller.is_processing is False
        assert controller.is_processing is False
        assert controller._active_generation_id is None
        assert controller._active_generation_dispatch_phase is None
        assert controller._stopping_generation_id is None
        assert controller._active_host_turn_id is None
        assert controller._active_host_turn_generation is None
        assert worker._active_generation_id is None
        assert worker._generation_thread_id is None

    try:
        manager.handle_user_input("Explain alpha EEG rhythms.")
        first_correlation = manager._assistant_turn_state.lease
        assert first_correlation is not None

        qtbot.waitUntil(lambda: len(runtime_terminals) == 1, timeout=2_000)

        assert runtime_terminals[0].correlation == first_correlation
        assert runtime_terminals[0].outcome == "generation_error"
        _assert_turn_ownership_released()
        assert [event.phase for event in dispatch_events] == [
            AssistantGenerationDispatchPhase.ACCEPTED
        ]
        assert [event.phase for event in generation_events] == [
            AssistantGenerationEventPhase.ERROR
        ]

        manager.handle_user_input("Explain beta EEG rhythms.")
        second_correlation = manager._assistant_turn_state.lease
        assert second_correlation is not None
        assert second_correlation != first_correlation

        qtbot.waitUntil(lambda: len(runtime_terminals) == 2, timeout=2_000)

        assert runtime_terminals[1].correlation == second_correlation
        assert runtime_terminals[1].outcome == "generation_error"
        _assert_turn_ownership_released()
        assert [event.phase for event in dispatch_events] == [
            AssistantGenerationDispatchPhase.ACCEPTED,
            AssistantGenerationDispatchPhase.ACCEPTED,
            AssistantGenerationDispatchPhase.STARTED,
        ]
        assert [event.phase for event in generation_events] == [
            AssistantGenerationEventPhase.ERROR,
            AssistantGenerationEventPhase.STARTED,
            AssistantGenerationEventPhase.ERROR,
        ]

        manager.handle_user_input("Explain event-related potentials.")
        third_correlation = manager._assistant_turn_state.lease
        assert third_correlation is not None
        assert third_correlation not in {first_correlation, second_correlation}

        qtbot.waitUntil(lambda: len(runtime_terminals) == 3, timeout=2_000)

        assert runtime_terminals[2].correlation == third_correlation
        assert runtime_terminals[2].outcome == "completed"
        _assert_turn_ownership_released()
        assert [event.phase for event in generation_events[-3:]] == [
            AssistantGenerationEventPhase.STARTED,
            AssistantGenerationEventPhase.CHUNK,
            AssistantGenerationEventPhase.FINISHED,
        ]
    finally:
        closed = manager.close()
        if not closed:
            qtbot.waitUntil(
                lambda: lifecycle.state is AssistantRuntimeLifecycleState.CLOSED,
                timeout=5_000,
            )
        assert lifecycle.state is AssistantRuntimeLifecycleState.CLOSED
        assert worker_thread.isRunning() is False
        qtbot.waitUntil(lambda: sip.isdeleted(worker), timeout=2_000)
