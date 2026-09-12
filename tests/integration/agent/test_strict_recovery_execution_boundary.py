"""Scripted product integration for strict tool-envelope recovery.

The generator is deterministic, but the controller parser, retry policy,
proposal path, and execution coordinator are production implementations.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from tests.qt_lifecycle import close_controller_and_wait
from XBrainLab.backend.application import CommandName
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
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
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
            controller.study,
            controller.registry,
            controller.metrics,
            block_policy=controller._tool_attempt_coordinator,
            emit_status=controller.status_update.emit,
            emit_application_command_started=controller.application_command_started.emit,
            emit_application_command_completed=controller.application_command_completed.emit,
        )
        self.commands: list[str] = []

    def execute(
        self,
        command_name: str,
        params: dict[str, Any],
        *,
        context,
        expected_publication_generation=None,
    ):
        self.commands.append(command_name)
        return super().execute(
            command_name,
            params,
            context=context,
            expected_publication_generation=expected_publication_generation,
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


def _submit_user_turn(
    controller: LLMController,
    text: str,
    *,
    generation: int = 1,
) -> None:
    controller.handle_user_turn(
        AssistantTurnRequest(
            correlation=AssistantTurnCorrelation(
                generation=generation,
                turn_id=generation,
            ),
            text=text,
        )
    )


def test_malformed_tool_envelopes_stop_after_two_retries_without_execution(
    qtbot,
):
    malformed = '```json\n{"tool_name":"import_eeg_data","parameters":{}}\n```'
    controller, worker, coordinator = _controller_with_script([malformed] * 3)
    statuses: list[str] = []
    responses: list[str] = []
    controller.status_update.connect(statuses.append)
    controller.response_presentation_ready.connect(
        lambda presentation: responses.append(presentation.text)
    )

    try:
        _submit_user_turn(controller, "Import EEG data.")
        qtbot.waitUntil(lambda: not controller.is_processing, timeout=3_000)

        assert worker.generation_count == 3
        assert worker.profiles == [GenerationProfile.STRUCTURED_DECISION] * 3
        assert controller._tool_attempt_session.retry_count == 2
        assert controller._tool_attempt_session.execution_count == 0
        assert coordinator.commands == []
        assert statuses.count("Invalid assistant action, retrying...") == 2
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
        assert "FORMAT CORRECTION REQUIRED" not in worker.messages[0][0]["content"]
        assert all(
            messages[0]["content"].count("FORMAT CORRECTION REQUIRED") == 1
            and "FORMAT CORRECTION REQUIRED" not in messages[1]["content"]
            for messages in worker.messages[1:]
        )
        assert "one JSON object" in worker.messages[1][0]["content"]
    finally:
        close_controller_and_wait(controller, qtbot)


def test_recovered_valid_envelope_reaches_real_execution_coordinator(
    qtbot,
):
    malformed = '```json\n{"tool_name":"import_eeg_data","parameters":{}}\n```'
    valid = '{"workflow_stage":"empty","tool_name":"import_eeg_data","parameters":{}}'
    controller, worker, coordinator = _controller_with_script([malformed, valid])

    try:
        _submit_user_turn(controller, "Import EEG data.")
        qtbot.waitUntil(
            lambda: controller._tool_attempt_session.execution_count == 1,
            timeout=3_000,
        )

        assert worker.generation_count == 2
        assert worker.profiles == [GenerationProfile.STRUCTURED_DECISION] * 2
        assert controller._tool_attempt_session.execution_count == 1
        assert coordinator.commands == ["import_eeg_data"]
        handoff = controller.pending_interactions.workflow_handoff
        assert handoff is not None
        assert handoff.command is CommandName.SCAN_SOURCE
        assert controller.is_processing is True
    finally:
        close_controller_and_wait(controller, qtbot)


@pytest.mark.parametrize("malformed_count", (0, 2))
def test_parsed_import_handoff_executes_once_despite_recovery_or_duplicate_finish(
    qtbot,
    malformed_count: int,
) -> None:
    """One parsed proposal cannot become a second tool execution in one turn."""
    malformed = '```json\n{"tool_name":"import_eeg_data","parameters":{}}\n```'
    valid = '{"workflow_stage":"empty","tool_name":"import_eeg_data","parameters":{}}'
    controller, worker, coordinator = _controller_with_script(
        [malformed] * malformed_count + [valid]
    )
    terminals = []
    controller.turn_finished.connect(terminals.append)

    try:
        _submit_user_turn(controller, "Import EEG data.")
        qtbot.waitUntil(
            lambda: controller.pending_interactions.workflow_handoff is not None,
            timeout=3_000,
        )
        handoff = controller.pending_interactions.workflow_handoff
        assert handoff is not None
        assert worker.generation_count == malformed_count + 1
        assert coordinator.commands == ["import_eeg_data"]
        assert controller._tool_attempt_session.execution_count == 1

        # This is the real worker signal, replayed after its generation already
        # reached a pending UI handoff. It must not parse or execute again.
        worker.generation_finished.emit(malformed_count + 1, [])
        qtbot.wait(20)
        assert controller.pending_interactions.workflow_handoff is handoff
        assert coordinator.commands == ["import_eeg_data"]
        assert controller._tool_attempt_session.execution_count == 1
        assert len(terminals) == 0

        controller.on_workflow_ui_handoff_resolved(
            WorkflowUiHandoffResolution.for_request(
                handoff,
                status=WorkflowUiHandoffResolutionStatus.CANCELLED,
                message="Import was cancelled in the existing UI.",
            )
        )
        qtbot.waitUntil(lambda: not controller.is_processing, timeout=3_000)
        assert len(terminals) == 1
        assert controller.pending_interactions.workflow_handoff is None
        assert coordinator.commands == ["import_eeg_data"]
    finally:
        close_controller_and_wait(controller, qtbot)


def test_same_import_action_in_three_fresh_turns_never_accumulates_a_loop(
    qtbot,
) -> None:
    """Repeat across user turns is legal; each fresh turn still owns one action."""
    valid = '{"workflow_stage":"empty","tool_name":"import_eeg_data","parameters":{}}'
    controller, worker, coordinator = _controller_with_script([valid, valid, valid])
    terminals = []
    controller.turn_finished.connect(terminals.append)

    try:
        for generation in range(1, 4):
            _submit_user_turn(
                controller,
                "Import EEG data.",
                generation=generation,
            )
            qtbot.waitUntil(
                lambda: controller.pending_interactions.workflow_handoff is not None,
                timeout=3_000,
            )
            handoff = controller.pending_interactions.workflow_handoff
            assert handoff is not None
            assert coordinator.commands == ["import_eeg_data"] * generation
            assert controller._tool_attempt_session.execution_count == 1

            controller.on_workflow_ui_handoff_resolved(
                WorkflowUiHandoffResolution.for_request(
                    handoff,
                    status=WorkflowUiHandoffResolutionStatus.CANCELLED,
                    message="Import was cancelled in the existing UI.",
                )
            )
            qtbot.waitUntil(lambda: not controller.is_processing, timeout=3_000)
            assert len(terminals) == generation

        assert worker.generation_count == 3
        assert coordinator.commands == ["import_eeg_data"] * 3
    finally:
        close_controller_and_wait(controller, qtbot)
