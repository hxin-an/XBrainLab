"""Scripted product integration for strict tool-envelope recovery.

The generator is deterministic, but the controller parser, retry policy,
proposal path, and execution coordinator are production implementations.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from tests.qt_lifecycle import close_controller_and_wait
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.tool_execution_coordinator import (
    ToolExecutionCoordinator,
)
from XBrainLab.llm.agent.turn import (
    AssistantGenerationDispatchAcknowledgement,
    AssistantGenerationDispatchPhase,
    AssistantGenerationRequest,
    AssistantGenerationStopAcknowledgement,
    AssistantGenerationStopRequest,
    AssistantTurnCorrelation,
    AssistantTurnRequest,
)
from XBrainLab.llm.core.generation import GenerationProfile


class _ScriptedWorker(QObject):
    """Qt worker seam that emits complete scripted generations."""

    generation_finished = pyqtSignal(int, list)
    generation_chunk_received = pyqtSignal(int, str)
    generation_error = pyqtSignal(int, str)
    generation_dispatch_acknowledged = pyqtSignal(object)
    error = pyqtSignal(str)
    log = pyqtSignal(str)
    generation_stop_finished = pyqtSignal(object)
    shutdown_finished = pyqtSignal(bool)
    runtime_snapshot_changed = pyqtSignal(object)

    def __init__(self, outputs: list[str]) -> None:
        super().__init__()
        self._outputs = deque(outputs)
        self.messages: list[list[dict[str, Any]]] = []
        self.profiles: list[GenerationProfile] = []

    @property
    def generation_count(self) -> int:
        return len(self.messages)

    @pyqtSlot(object)
    def initialize_agent(self, _launch_spec: object) -> None:
        return None

    @pyqtSlot(object)
    def generate_from_messages(self, request: AssistantGenerationRequest) -> None:
        assert isinstance(request, AssistantGenerationRequest)
        self.generation_dispatch_acknowledged.emit(
            AssistantGenerationDispatchAcknowledgement(
                generation_id=request.generation_id,
                phase=AssistantGenerationDispatchPhase.ACCEPTED,
            )
        )
        self.generation_dispatch_acknowledged.emit(
            AssistantGenerationDispatchAcknowledgement(
                generation_id=request.generation_id,
                phase=AssistantGenerationDispatchPhase.STARTED,
            )
        )
        messages = request.to_model_messages()
        self.messages.append([dict(message) for message in messages])
        self.profiles.append(request.generation_profile)
        if not self._outputs:
            self.generation_error.emit(
                request.generation_id,
                "Scripted generator was exhausted.",
            )
            return
        self.generation_chunk_received.emit(
            request.generation_id,
            self._outputs.popleft(),
        )
        self.generation_finished.emit(request.generation_id, [])

    @pyqtSlot(object)
    def reinitialize_agent(self, _launch_spec: object) -> None:
        return None

    @pyqtSlot(object)
    def cancel_generation(self, request: AssistantGenerationStopRequest) -> None:
        self.generation_stop_finished.emit(
            AssistantGenerationStopAcknowledgement(
                generation_id=request.generation_id,
                stopped=True,
            )
        )

    @pyqtSlot()
    def shutdown(self, wait_ms: int = 0) -> bool:
        del wait_ms
        self.shutdown_finished.emit(True)
        return True


class _NoopRag:
    def initialize(self) -> None:
        return None

    def get_similar_examples(
        self,
        _text: str,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> str:
        del allowed_tool_names
        return ""

    def close(self) -> None:
        return None


class _ImmediateRagLifecycle:
    """Deliver an empty retrieval result through the controller callback."""

    def __init__(self, retriever: _NoopRag | None = None) -> None:
        self.retriever = retriever or _NoopRag()

    def start(self) -> bool:
        self.retriever.initialize()
        return True

    def retrieve(
        self,
        turn_id: int,
        query: str,
        callback: Callable[[int, str, str, str], None],
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> bool:
        del allowed_tool_names
        callback(turn_id, query, "", "")
        return True

    def close(self) -> bool:
        self.retriever.close()
        return True


class _RecordingExecutionCoordinator(ToolExecutionCoordinator):
    """Real coordinator with an observable execute boundary."""

    def __init__(self, controller: LLMController) -> None:
        super().__init__(
            controller,
            block_policy=controller._tool_attempt_coordinator,
        )
        self.commands: list[str] = []

    def execute(
        self,
        command_name: str,
        params: dict[str, Any],
        *,
        context,
        application_runtime=None,
    ):
        self.commands.append(command_name)
        return super().execute(
            command_name,
            params,
            context=context,
            application_runtime=application_runtime,
        )


def _controller_with_script(
    outputs: list[str],
) -> tuple[LLMController, _ScriptedWorker, _RecordingExecutionCoordinator]:
    worker = _ScriptedWorker(outputs)
    with (
        patch(
            "XBrainLab.llm.agent.controller.AgentWorker",
            new=lambda: worker,
        ),
        patch(
            "XBrainLab.llm.agent.controller.ProcessRAGRetrieverLifecycle",
            new=_ImmediateRagLifecycle,
        ),
    ):
        controller = LLMController(Study())
    coordinator = _RecordingExecutionCoordinator(controller)
    controller._tool_execution_coordinator = coordinator
    return controller, worker, coordinator


def _submit_user_turn(controller: LLMController, text: str) -> None:
    controller.handle_user_turn(
        AssistantTurnRequest.single_action(
            correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
            text=text,
        )
    )


def test_malformed_tool_envelopes_stop_after_one_retry_without_execution(
    qtbot,
    tmp_path,
):
    source = tmp_path / "sample.edf"
    source.write_bytes(b"fixture")
    malformed = (
        '```json\n{"tool_name":"scan_source","parameters":'
        f'{{"source_path":"{source}"}}}}\n```'
    )
    controller, worker, coordinator = _controller_with_script([malformed] * 2)
    statuses: list[str] = []
    responses: list[str] = []
    controller.status_update.connect(statuses.append)
    controller.response_presentation_ready.connect(
        lambda presentation: responses.append(presentation.text)
    )

    try:
        _submit_user_turn(controller, f"Scan data source {source}")
        qtbot.waitUntil(lambda: not controller.is_processing, timeout=3_000)

        assert worker.generation_count == 2
        assert worker.profiles == [GenerationProfile.STRUCTURED_DECISION] * 2
        assert controller._tool_attempt_session.retry_count == 1
        assert controller._tool_attempt_session.execution_count == 0
        assert coordinator.commands == []
        assert statuses.count("Invalid assistant action, retrying...") == 1
        assert statuses[-1] == "Invalid assistant action"
        assert responses == [
            "The assistant could not produce a valid assistant action. Try again "
            "or describe one workflow step more specifically."
        ]
        assert all(
            "Return exactly one DECISION ENVELOPE" in messages[0]["content"]
            and "Never use a Markdown code fence" in messages[0]["content"]
            for messages in worker.messages[1:]
        )
        assert "FORMAT CORRECTION REQUIRED" in worker.messages[1][1]["content"]
        assert "one JSON object" in worker.messages[1][1]["content"]
    finally:
        close_controller_and_wait(controller, qtbot)


def test_recovered_valid_envelope_reaches_real_execution_coordinator(
    qtbot,
    tmp_path,
):
    source = tmp_path / "sample.edf"
    source.write_bytes(b"fixture")
    malformed = (
        '```json\n{"tool_name":"scan_source","parameters":'
        f'{{"source_path":"{source}"}}}}\n```'
    )
    valid = f'{{"tool_name":"scan_source","parameters":{{"source_path":"{source}"}}}}'
    controller, worker, coordinator = _controller_with_script([malformed, valid])

    try:
        _submit_user_turn(controller, f"Scan data source {source}")
        qtbot.waitUntil(lambda: not controller.is_processing, timeout=3_000)

        assert worker.generation_count == 2
        assert worker.profiles == [GenerationProfile.STRUCTURED_DECISION] * 2
        assert controller._tool_attempt_session.execution_count == 1
        assert coordinator.commands == ["scan_source"]
    finally:
        close_controller_and_wait(controller, qtbot)
