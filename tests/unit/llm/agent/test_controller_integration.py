import json
from collections.abc import Iterator
from contextlib import suppress
from copy import deepcopy
from threading import Event
from unittest.mock import MagicMock

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from XBrainLab.llm.agent.assembler import ContextAssembler, PromptToolPublication
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.rag_lifecycle import RAGRetrieverLifecycle
from XBrainLab.llm.agent.turn import (
    AssistantGenerationRequest,
    AssistantGenerationStopAcknowledgement,
    AssistantTurnCorrelation,
    AssistantTurnDeliveryPhase,
    AssistantTurnRequest,
)
from XBrainLab.llm.agent.verifier import ToolSchemaValidator, VerificationLayer
from XBrainLab.llm.agent.worker import AgentWorker
from XBrainLab.llm.tools.application_surface import (
    ToolAvailability,
    ToolAvailabilityContext,
)
from XBrainLab.llm.tools.tool_registry import ToolRegistry

EXPECTED_CONTROLLER_TOOL_NAMES = (
    "import_eeg_data",
    "select_channels",
    "set_montage",
    "create_epochs",
    "configure_dataset_split",
    "select_model",
    "configure_training",
    "apply_bandpass_filter",
    "apply_notch_filter",
    "resample_data",
    "set_reference",
    "normalize_data",
    "start_training",
    "stop_training",
    "reset_preprocessing",
    "clear_training_history",
    "switch_panel",
)


class _NoopRetriever:
    """Retriever double with no background work or external resources."""

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


class _LateGenerationEmitter(QThread):
    """Publish one stale generation terminal from a native Qt thread."""

    chunk = pyqtSignal(int, str)
    generation_finished = pyqtSignal(int, list)
    generation_error = pyqtSignal(int, str)

    def __init__(self, generation_id: int, release: Event) -> None:
        super().__init__()
        self._generation_id = generation_id
        self._release = release

    def run(self) -> None:
        self._release.wait(timeout=2.0)
        self.chunk.emit(
            self._generation_id,
            '{"tool_name":"query_state","parameters":{"query":"state"}}',
        )
        self.generation_finished.emit(self._generation_id, [])
        self.generation_error.emit(self._generation_id, "late turn A failure")


class _DelayedStopAcknowledgementEmitter(QThread):
    """Publish delayed typed acknowledgements from a native Qt thread."""

    acknowledgement = pyqtSignal(object)

    def __init__(
        self,
        acknowledgement: AssistantGenerationStopAcknowledgement,
        release: Event,
        *,
        count: int = 1,
    ) -> None:
        super().__init__()
        self._acknowledgement = acknowledgement
        self._release = release
        self._count = count

    def run(self) -> None:
        self._release.wait(timeout=2.0)
        for _index in range(self._count):
            self.acknowledgement.emit(self._acknowledgement)


@pytest.fixture
def controller(qtbot) -> Iterator[LLMController]:
    """Run integration assertions against the real QObject worker lifecycle."""
    lifecycle = RAGRetrieverLifecycle(_NoopRetriever())
    instance = LLMController(MagicMock(), rag_lifecycle=lifecycle)
    worker = instance.worker
    worker_thread = instance.worker_thread

    assert isinstance(worker, AgentWorker)
    assert isinstance(worker, QObject)
    assert worker.thread() is worker_thread
    assert worker_thread.isRunning()

    yield instance

    shutdown_terminals: list[tuple[bool, str]] = []
    instance.shutdown_finished.connect(
        lambda ok, message: shutdown_terminals.append((ok, message))
    )
    assert instance.close() is False
    qtbot.waitUntil(lambda: bool(shutdown_terminals), timeout=2_000)
    assert shutdown_terminals[0][0] is True
    qtbot.waitUntil(lambda: sip.isdeleted(worker), timeout=2_000)
    assert worker_thread.isRunning() is False
    assert instance.worker is None
    assert instance.close() is True


def test_controller_initialization(controller: LLMController) -> None:
    assert isinstance(controller.registry, ToolRegistry)
    assert isinstance(controller.assembler, ContextAssembler)
    assert isinstance(controller.verifier, VerificationLayer)
    assert controller.assembler.registry is controller.registry
    assert controller.assembler.study_state is controller.study
    assert isinstance(controller.worker, AgentWorker)
    assert controller.worker.thread() is controller.worker_thread

    tools = controller.registry.get_all_tools()
    tool_names = tuple(tool.name for tool in tools)
    assert tool_names == EXPECTED_CONTROLLER_TOOL_NAMES
    schema_validator = controller.verifier.validators[0]
    assert isinstance(schema_validator, ToolSchemaValidator)
    assert tuple(schema_validator.tool_schemas) == EXPECTED_CONTROLLER_TOOL_NAMES
    assert schema_validator.tool_schemas["import_eeg_data"]["properties"] == {}
    assert (
        schema_validator.tool_schemas["import_eeg_data"]["additionalProperties"]
        is False
    )


def test_controller_prompt_generation(controller: LLMController) -> None:
    controller._append_history("user", "Hello")

    msgs = controller.assembler.get_messages(controller.history)
    assert len(msgs) == 3
    assert (
        "Action Contract Catalog (input definitions, never an output array):"
        in msgs[0]["content"]
    )
    context = json.loads(msgs[1]["content"])
    assert context["schema"] == "xbrainlab.untrusted_context.v1"
    assert context["trust"] == "untrusted"
    assert msgs[2] == {"role": "user", "content": "Hello"}


def test_direct_uncorrelated_user_input_fails_closed(
    controller: LLMController,
    qtbot,
) -> None:
    """Only the desktop host may admit and correlate a user turn."""
    generation_requests = []
    controller.sig_generate.connect(generation_requests.append)
    history_before = deepcopy(controller.history)
    worker = controller.worker

    controller.handle_user_input("Explain alpha and beta EEG rhythms.")
    qtbot.wait(25)

    assert controller.history == history_before
    assert controller._turn_orchestrator.host_turn_id is None
    assert controller._turn_orchestrator.host_turn_generation is None
    assert controller._turn_orchestrator.active_generation_id is None
    assert controller._turn_orchestrator.active_rag_turn_id is None
    assert controller.is_processing is False
    assert generation_requests == []
    assert controller.worker is worker


def test_generation_diagnostic_observer_cannot_reenter_dispatch(
    controller: LLMController,
) -> None:
    """A diagnostic callback cannot create a second generation for one turn."""
    controller._sig_dispatch_generation.disconnect()
    controller._turn_orchestrator.host_turn_generation = 1
    controller._turn_orchestrator.host_turn_id = 1
    controller.is_processing = True
    controller.metrics.start_turn()
    dispatched = []
    diagnostic_generations = []
    reentry_results = []

    controller._sig_dispatch_generation.connect(dispatched.append)

    def _reenter_once(request: object) -> None:
        assert isinstance(request, AssistantGenerationRequest)
        diagnostic_generations.append(request.generation_id)
        if len(diagnostic_generations) == 1:
            reentry_results.append(controller._generate_response())

    controller.sig_generate.connect(_reenter_once)

    assert controller._generate_response() is True

    assert [request.generation_id for request in dispatched] == [1]
    assert diagnostic_generations == [1]
    assert reentry_results == [False]
    assert controller._turn_orchestrator.generation_sequence == 1
    assert controller._turn_orchestrator.active_generation_id == 1


def test_delivery_setup_fault_unwinds_all_controller_turn_state(
    controller: LLMController,
    monkeypatch,
) -> None:
    """Outer setup faults leave no state that can reject the next host turn."""
    attempts = 0

    def _fault_then_complete(_text: str) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            controller.is_processing = True
            controller.metrics.start_turn()
            controller._begin_rag_turn()
            controller.assembler.add_context("stale RAG context")
            controller.assembler.set_turn_authorized_command("load_data")
            controller._turn_orchestrator.admitted_command_name = "load_data"
            controller._turn_orchestrator.admitted_publication_generation = 12
            controller._turn_orchestrator.active_generation_id = 91
            controller._turn_orchestrator.dispatch_phase = MagicMock()
            controller.pending_interactions._workflow_handoff = MagicMock()
            raise RuntimeError("fault injection after setup side effects")
        controller._emit_processing_finished()

    monkeypatch.setattr(
        controller,
        "_handle_admitted_user_input",
        _fault_then_complete,
    )
    first = AssistantTurnRequest.single_action(
        correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
        text="first request",
    )

    acknowledgement = controller.handle_user_turn(first)

    assert acknowledgement.phase is AssistantTurnDeliveryPhase.ERROR
    assert controller.metrics.current_turn is None
    assert controller.pending_interactions.has_pending is False
    assert controller._turn_orchestrator.waiting_for_rag is False
    assert controller._turn_orchestrator.active_rag_turn_id is None
    assert controller.assembler.context_notes == []
    assert controller.assembler._turn_authorized_command is None
    assert controller._turn_orchestrator.admitted_command_name is None
    assert controller._turn_orchestrator.admitted_publication_generation is None
    assert controller._turn_orchestrator.active_generation_id is None
    assert controller._turn_orchestrator.dispatch_phase is None
    assert controller._turn_orchestrator.host_turn_id is None
    assert controller._turn_orchestrator.host_turn_generation is None
    assert controller._turn_orchestrator.scope is None
    assert controller._turn_orchestrator.terminal_command is None
    assert controller.is_processing is False

    second = controller.handle_user_turn(
        AssistantTurnRequest.single_action(
            correlation=AssistantTurnCorrelation(generation=2, turn_id=2),
            text="second request",
        )
    )

    assert second.phase is AssistantTurnDeliveryPhase.ACCEPTED
    assert attempts == 2
    assert controller._turn_orchestrator.host_turn_id is None
    assert controller._turn_orchestrator.host_turn_generation is None


def test_internal_setup_fault_unwinds_pending_metrics_and_rag_context(
    controller: LLMController,
    monkeypatch,
) -> None:
    """Faults caught inside admitted setup use the same complete rollback."""

    def _fail_after_side_effects(_text: str) -> frozenset[str]:
        controller.assembler.add_context("partial RAG context")
        controller.pending_interactions._workflow_handoff = MagicMock()
        raise RuntimeError("fault injection inside request setup")

    monkeypatch.setattr(
        controller.assembler,
        "rag_allowed_tool_names",
        _fail_after_side_effects,
    )
    terminals = []
    controller.turn_finished.connect(terminals.append)

    acknowledgement = controller.handle_user_turn(
        AssistantTurnRequest.single_action(
            correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
            text="request with setup fault",
        )
    )

    assert acknowledgement.phase is AssistantTurnDeliveryPhase.ACCEPTED
    assert [terminal.outcome for terminal in terminals] == ["failed_to_start"]
    assert controller.metrics.current_turn is None
    assert controller.pending_interactions.has_pending is False
    assert controller._turn_orchestrator.waiting_for_rag is False
    assert controller._turn_orchestrator.active_rag_turn_id is None
    assert controller.assembler.context_notes == []
    assert controller.assembler._turn_authorized_command is None
    assert controller._turn_orchestrator.host_turn_id is None
    assert controller._turn_orchestrator.host_turn_generation is None
    assert controller._turn_orchestrator.scope is None
    assert controller._turn_orchestrator.terminal_command is None
    assert controller.is_processing is False


def test_guided_turn_scope_is_owned_by_the_admitted_request(
    controller: LLMController,
    monkeypatch,
) -> None:
    observed: list[tuple[str, str | None]] = []

    def _inspect_active_scope(_text: str) -> None:
        observed.append(
            (
                controller._active_policy_mode(),
                controller._turn_orchestrator.terminal_command,
            )
        )
        assert not hasattr(controller, "set_execution_mode")
        controller._emit_processing_finished()

    monkeypatch.setattr(
        controller,
        "_handle_admitted_user_input",
        _inspect_active_scope,
    )

    acknowledgement = controller.handle_user_turn(
        AssistantTurnRequest.guided_workflow(
            correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
            text="Load the recording and create epochs.",
            terminal_command="create_epoch",
        )
    )

    assert acknowledgement.phase is AssistantTurnDeliveryPhase.ACCEPTED
    assert observed == [("multi", "create_epoch")]
    assert controller._turn_orchestrator.scope is None
    assert controller._turn_orchestrator.terminal_command is None


def test_controller_verification_flow_rejection(controller: LLMController) -> None:
    """Test that if Verifier rejects, the tool is not executed and error is logged."""
    status_mock = MagicMock()
    controller.status_update.connect(status_mock)
    controller._turn_orchestrator.host_turn_generation = 1
    controller._turn_orchestrator.host_turn_id = 1

    mock_result = MagicMock()
    mock_result.is_valid = False
    mock_result.error_message = "Safety Violation"
    controller.verifier.verify_tool_call = MagicMock(return_value=mock_result)
    controller._turn_orchestrator.active_publication = PromptToolPublication(
        tool_names=frozenset({"SomeTool"}),
        backend_generation=1,
    )
    context_source = MagicMock()
    context_source.get_context.return_value = ToolAvailabilityContext(
        availability=ToolAvailability(tool_name="SomeTool", enabled=True),
        state={"pipeline_stage": "empty"},
        generation=1,
    )
    controller._tool_attempt_coordinator._context_source = context_source

    command = ("SomeTool", {"param": 1})
    response_text = '{"tool_name":"SomeTool","parameters":{"param":1}}'
    controller._process_tool_calls([command], response_text)

    assert any(
        "Blocked:" in str(call.args[0]) and "Safety Violation" in str(call.args[0])
        for call in status_mock.call_args_list
    )
    last_msg = controller.history[-1]
    assert last_msg["role"] == "user"
    assert "Tool Output:" in last_msg["content"]
    assert "Safety Violation" in last_msg["content"]


def test_late_generation_events_cannot_mutate_the_next_host_turn(
    controller: LLMController,
    qtbot,
) -> None:
    """A queued native turn-A terminal cannot attach itself to active turn B."""
    controller._sig_dispatch_generation.disconnect()
    generation_requests = []
    controller.sig_generate.connect(generation_requests.append)
    terminals = []
    controller.turn_finished.connect(terminals.append)

    controller.handle_user_turn(
        AssistantTurnRequest.single_action(
            correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
            text="summarize the current dataset",
        )
    )
    qtbot.waitUntil(lambda: len(generation_requests) == 1, timeout=2_000)
    generation_a = generation_requests[-1].generation_id

    release_late_a = Event()
    emitter = _LateGenerationEmitter(generation_a, release_late_a)
    worker = controller.worker
    assert worker is not None
    emitter.chunk.connect(worker.generation_chunk_received)
    emitter.generation_finished.connect(worker.generation_finished)
    emitter.generation_error.connect(worker.generation_error)
    emitter.start()

    try:
        controller.stop_generation()
        qtbot.waitUntil(lambda: not controller.is_processing, timeout=2_000)
        assert [(item.turn_id, item.outcome) for item in terminals] == [
            (1, "cancelled")
        ]

        controller.handle_user_turn(
            AssistantTurnRequest.single_action(
                correlation=AssistantTurnCorrelation(generation=2, turn_id=2),
                text="Compare alpha and beta EEG rhythms",
            )
        )
        qtbot.waitUntil(lambda: len(generation_requests) == 2, timeout=2_000)
        generation_b = generation_requests[-1].generation_id
        assert generation_b > generation_a

        before_buffer = controller.current_response
        before_history = deepcopy(controller.history)
        before_tool_count = controller._tool_attempt_session.execution_count

        release_late_a.set()
        qtbot.waitUntil(lambda: not emitter.isRunning(), timeout=2_000)
        qtbot.wait(50)

        assert controller.current_response == before_buffer
        assert controller.history == before_history
        assert controller._tool_attempt_session.execution_count == before_tool_count
        assert controller.pending_interactions.has_pending is False
        assert controller.is_processing is True
        assert controller._turn_orchestrator.host_turn_id == 2
        assert controller._turn_orchestrator.active_generation_id == generation_b
        assert [(item.turn_id, item.outcome) for item in terminals] == [
            (1, "cancelled")
        ]
    finally:
        release_late_a.set()
        emitter.wait(2_000)
        if controller.is_processing:
            controller.stop_generation()
            qtbot.waitUntil(lambda: not controller.is_processing, timeout=2_000)


def test_delayed_duplicate_stop_ack_for_a_cannot_affect_active_or_stopping_b(
    controller: LLMController,
    qtbot,
) -> None:
    """Exercise A/B stop correlation through real QObject/QThread signal routing."""
    controller._sig_dispatch_generation.disconnect()
    generation_requests = []
    controller.sig_generate.connect(generation_requests.append)
    terminals = []
    controller.turn_finished.connect(terminals.append)

    controller.handle_user_turn(
        AssistantTurnRequest.single_action(
            correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
            text="Compare alpha and beta EEG rhythms",
        )
    )
    qtbot.waitUntil(lambda: len(generation_requests) == 1, timeout=2_000)
    generation_a = generation_requests[-1].generation_id

    controller.stop_generation()
    qtbot.waitUntil(lambda: len(terminals) == 1, timeout=2_000)
    assert [(item.turn_id, item.outcome) for item in terminals] == [(1, "cancelled")]

    controller.handle_user_turn(
        AssistantTurnRequest.single_action(
            correlation=AssistantTurnCorrelation(generation=2, turn_id=2),
            text="Explain event-related potentials",
        )
    )
    qtbot.waitUntil(lambda: len(generation_requests) == 2, timeout=2_000)
    generation_b = generation_requests[-1].generation_id
    assert generation_b > generation_a

    stale_ack = AssistantGenerationStopAcknowledgement(
        generation_id=generation_a,
        stopped=True,
    )
    active_release = Event()
    active_emitter = _DelayedStopAcknowledgementEmitter(
        stale_ack,
        active_release,
        count=2,
    )
    active_emitter.acknowledgement.connect(controller._on_generation_stop_finished)
    active_emitter.start()
    delayed_emitters = [(active_emitter, active_release)]

    delayed_b_acks = []
    worker = controller.worker
    assert worker is not None
    worker.generation_stop_finished.disconnect(controller._on_generation_stop_finished)
    worker.generation_stop_finished.connect(delayed_b_acks.append)

    try:
        active_release.set()
        qtbot.waitUntil(lambda: not active_emitter.isRunning(), timeout=2_000)
        qtbot.wait(25)

        assert controller.is_processing is True
        assert controller._turn_orchestrator.host_turn_id == 2
        assert controller._turn_orchestrator.active_generation_id == generation_b
        assert len(terminals) == 1

        controller.stop_generation()
        qtbot.waitUntil(lambda: len(delayed_b_acks) == 1, timeout=2_000)
        assert delayed_b_acks == [
            AssistantGenerationStopAcknowledgement(
                generation_id=generation_b,
                stopped=True,
            )
        ]
        assert controller.is_processing is True

        stopping_release = Event()
        stopping_emitter = _DelayedStopAcknowledgementEmitter(
            stale_ack,
            stopping_release,
            count=2,
        )
        stopping_emitter.acknowledgement.connect(
            controller._on_generation_stop_finished
        )
        stopping_emitter.start()
        delayed_emitters.append((stopping_emitter, stopping_release))
        stopping_release.set()
        qtbot.waitUntil(
            lambda: not stopping_emitter.isRunning(),
            timeout=2_000,
        )
        qtbot.wait(25)

        assert controller.is_processing is True
        assert controller._turn_orchestrator.host_turn_id == 2
        assert controller._turn_orchestrator.active_generation_id == generation_b
        assert [(item.turn_id, item.outcome) for item in terminals] == [
            (1, "cancelled")
        ]

        completion_release = Event()
        completion_emitter = _DelayedStopAcknowledgementEmitter(
            delayed_b_acks[0],
            completion_release,
        )
        completion_emitter.acknowledgement.connect(
            controller._on_generation_stop_finished
        )
        completion_emitter.start()
        delayed_emitters.append((completion_emitter, completion_release))
        completion_release.set()
        qtbot.waitUntil(
            lambda: not completion_emitter.isRunning(),
            timeout=2_000,
        )
        qtbot.waitUntil(lambda: len(terminals) == 2, timeout=2_000)

        assert [(item.turn_id, item.outcome) for item in terminals] == [
            (1, "cancelled"),
            (2, "cancelled"),
        ]
        assert controller.is_processing is False
    finally:
        for emitter, release in delayed_emitters:
            release.set()
            emitter.wait(2_000)
        with suppress(TypeError, RuntimeError):
            worker.generation_stop_finished.disconnect(delayed_b_acks.append)
        with suppress(TypeError, RuntimeError):
            worker.generation_stop_finished.connect(
                controller._on_generation_stop_finished
            )
        if controller.is_processing:
            controller._on_generation_stop_finished(
                AssistantGenerationStopAcknowledgement(
                    generation_id=generation_b,
                    stopped=True,
                )
            )
