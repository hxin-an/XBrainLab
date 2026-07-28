"""Low-mock regressions for workflow re-admission after delayed RAG.

The retriever is the only delayed test seam.  Controller admission, the
ApplicationService publication, capability policy, prompt assembler, Qt signals,
and pending-interaction owner are production implementations.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from threading import Event

import pytest

from tests.qt_lifecycle import close_controller_and_wait
from XBrainLab.backend.application import ApplicationService, get_application_service
from XBrainLab.backend.application.commands import CommandName
from XBrainLab.backend.application.state import (
    ActiveDatasetSnapshot,
    ApplicationStateSnapshot,
    InterpretationStateSnapshot,
    RawStateSnapshot,
)
from XBrainLab.backend.application.view_publication import (
    ApplicationViewPublication,
    ApplicationViewStore,
)
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.rag_lifecycle import RAGRetrieverLifecycle
from XBrainLab.llm.agent.response_presentation import (
    AssistantPanelTarget,
    AssistantResponseKind,
    AssistantResponsePresentation,
)
from XBrainLab.llm.agent.turn import (
    AssistantGenerationRequest,
    AssistantTurnCorrelation,
    AssistantTurnRequest,
)
from XBrainLab.llm.agent.ui_handoff import WorkflowUiHandoffRequest

_STALE_RAG_CONTEXT = "STALE_RAG_CONTEXT_MUST_NOT_REACH_GENERATION"


class _DelayedRetriever:
    """Hold one real lifecycle retrieval until the test changes publication."""

    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.finished = Event()
        self.queries: list[tuple[str, frozenset[str] | None]] = []

    def initialize(self) -> None:
        return None

    def get_similar_examples(
        self,
        query: str,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> str:
        self.queries.append((query, allowed_tool_names))
        self.started.set()
        if not self.release.wait(timeout=5.0):
            raise TimeoutError("Test did not release delayed RAG retrieval")
        self.finished.set()
        return _STALE_RAG_CONTEXT

    def close(self) -> None:
        self.release.set()


@dataclass(slots=True)
class _RAGReadmissionHarness:
    controller: LLMController
    service: ApplicationService
    view_store: ApplicationViewStore
    retriever: _DelayedRetriever
    lifecycle: RAGRetrieverLifecycle
    generation_requests: list[AssistantGenerationRequest]
    presentations: list[AssistantResponsePresentation]
    handoffs: list[WorkflowUiHandoffRequest]

    def publish(
        self,
        state: ApplicationStateSnapshot,
    ) -> ApplicationViewPublication:
        """Publish through the same atomic store used by ApplicationService."""
        current = self.view_store.read()
        return self.view_store.publish(state, current.training_boundary)


@pytest.fixture
def rag_readmission_harness(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_RAGReadmissionHarness]:
    study = Study()
    service = get_application_service(study)
    initial_publication = service.get_view_publication()
    view_store = ApplicationViewStore(
        initial_publication.state,
        initial_publication.training_boundary,
    )
    monkeypatch.setattr(service, "get_view_publication", view_store.read)
    retriever = _DelayedRetriever()
    lifecycle = RAGRetrieverLifecycle(retriever, shutdown_wait_seconds=1.0)
    controller = LLMController(study, rag_lifecycle=lifecycle)

    generation_requests: list[AssistantGenerationRequest] = []
    presentations: list[AssistantResponsePresentation] = []
    handoffs: list[WorkflowUiHandoffRequest] = []

    worker = controller.worker
    assert worker is not None
    controller._sig_dispatch_generation.disconnect(worker.generate_from_messages)
    controller.sig_generate.connect(generation_requests.append)
    controller.response_presentation_ready.connect(presentations.append)
    controller.workflow_ui_handoff_requested.connect(handoffs.append)

    harness = _RAGReadmissionHarness(
        controller=controller,
        service=service,
        view_store=view_store,
        retriever=retriever,
        lifecycle=lifecycle,
        generation_requests=generation_requests,
        presentations=presentations,
        handoffs=handoffs,
    )
    yield harness

    retriever.release.set()
    if lifecycle.is_retrieving:
        qtbot.waitUntil(lambda: not lifecycle.is_retrieving, timeout=2_000)
    close_controller_and_wait(controller, qtbot)


def _selected_source_state(path: str) -> ApplicationStateSnapshot:
    return replace(
        ApplicationStateSnapshot.empty(),
        interpretation=InterpretationStateSnapshot(
            source_path=path,
            source_kind="file",
        ),
    )


def _loaded_state() -> ApplicationStateSnapshot:
    return replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="data_loaded",
        raw=RawStateSnapshot(
            loaded=True,
            count=1,
            files=["/data/A01T.gdf"],
            formats=[".gdf"],
        ),
        active_dataset=ActiveDatasetSnapshot(has_raw_data=True),
    )


def _wait_for_delayed_retrieval(harness: _RAGReadmissionHarness) -> None:
    assert harness.retriever.started.wait(timeout=2.0)
    assert harness.controller.is_processing
    assert harness.controller._waiting_for_rag
    assert harness.generation_requests == []
    assert harness.controller._tool_execution_count == 0


def _release_retrieval(harness: _RAGReadmissionHarness) -> None:
    harness.retriever.release.set()
    assert harness.retriever.finished.wait(timeout=2.0)


def _submit_user_turn(
    harness: _RAGReadmissionHarness,
    text: str,
) -> None:
    harness.controller.handle_user_turn(
        AssistantTurnRequest.single_action(
            correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
            text=text,
        )
    )


def test_delayed_rag_generate_becomes_typed_ui_handoff(
    rag_readmission_harness: _RAGReadmissionHarness,
    qtbot,
) -> None:
    """A source removed during RAG must reopen the existing import surface."""
    harness = rag_readmission_harness
    admitted = harness.publish(_selected_source_state("/data/selected.edf"))

    _submit_user_turn(harness, "Load the selected EEG files.")
    _wait_for_delayed_retrieval(harness)
    assert harness.controller._admitted_command_name == CommandName.SCAN_SOURCE.value
    assert harness.controller._admitted_publication_generation == admitted.generation

    current = harness.publish(ApplicationStateSnapshot.empty())
    assert current.generation > admitted.generation
    _release_retrieval(harness)
    qtbot.waitUntil(lambda: len(harness.handoffs) == 1, timeout=2_000)

    request = harness.handoffs[0]
    assert isinstance(request, WorkflowUiHandoffRequest)
    assert request.command is CommandName.SCAN_SOURCE
    assert request.decision_fields == ("source_path",)
    assert harness.controller.pending_interactions.workflow_handoff == request
    assert harness.controller.is_processing
    assert harness.generation_requests == []
    assert harness.controller._tool_execution_count == 0
    assert _STALE_RAG_CONTEXT not in harness.controller.assembler.context_notes


def test_delayed_rag_generate_becomes_recoverable_blocked_result(
    rag_readmission_harness: _RAGReadmissionHarness,
    qtbot,
) -> None:
    """A lost precondition during RAG must publish a useful blocked result."""
    harness = rag_readmission_harness
    admitted = harness.publish(_loaded_state())

    _submit_user_turn(
        harness,
        "Apply the standard preprocessing defaults.",
    )
    _wait_for_delayed_retrieval(harness)
    assert harness.controller._admitted_command_name == CommandName.PREPROCESS.value
    assert harness.controller._admitted_publication_generation == admitted.generation

    current = harness.publish(ApplicationStateSnapshot.empty())
    assert current.generation > admitted.generation
    _release_retrieval(harness)
    qtbot.waitUntil(
        lambda: bool(harness.presentations) and not harness.controller.is_processing,
        timeout=2_000,
    )

    presentation = harness.presentations[-1]
    assert presentation.kind is AssistantResponseKind.BLOCKED
    assert "Load raw data before preprocessing" in presentation.text
    assert len(presentation.actions) == 1
    assert presentation.actions[0].panel is AssistantPanelTarget.PREPROCESS
    assert harness.generation_requests == []
    assert harness.handoffs == []
    assert harness.controller._tool_execution_count == 0
    assert _STALE_RAG_CONTEXT not in harness.controller.assembler.context_notes


def test_delayed_rag_same_command_uses_current_publication_without_stale_context(
    rag_readmission_harness: _RAGReadmissionHarness,
    qtbot,
) -> None:
    """A still-generative request must bind its prompt to the new publication."""
    harness = rag_readmission_harness
    admitted = harness.service.get_view_publication()

    _submit_user_turn(harness, "Load /data/A01T.gdf")
    _wait_for_delayed_retrieval(harness)
    assert harness.controller._admitted_command_name == CommandName.SCAN_SOURCE.value
    assert harness.controller._admitted_publication_generation == admitted.generation

    current = harness.publish(_selected_source_state("/data/other.edf"))
    assert current.generation > admitted.generation
    _release_retrieval(harness)
    qtbot.waitUntil(
        lambda: len(harness.generation_requests) == 1,
        timeout=2_000,
    )

    generation = harness.generation_requests[0]
    prompt_text = "\n".join(
        str(message["content"]) for message in generation.to_model_messages()
    )
    assert generation.generation_id > 0
    assert harness.controller._active_generation_id == generation.generation_id
    assert harness.controller._admitted_command_name == CommandName.SCAN_SOURCE.value
    assert harness.controller._admitted_publication_generation == current.generation
    assert harness.controller._active_tool_publication.backend_generation == (
        current.generation
    )
    assert harness.controller.assembler.latest_tool_publication.backend_generation == (
        current.generation
    )
    assert _STALE_RAG_CONTEXT not in prompt_text
    assert _STALE_RAG_CONTEXT not in harness.controller.assembler.context_notes
    assert harness.handoffs == []
    assert harness.presentations == []
    assert harness.controller._tool_execution_count == 0
