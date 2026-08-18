"""Product-facing agent flow regressions.

These tests exercise the path from user intent through controller-visible
transcript messages. They intentionally assert user language, not internal tool
payload shape, while still checking structured diagnostics remain available to
the agent history.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from tests.qt_lifecycle import close_controller_and_wait
from XBrainLab.backend.controller.chat_controller import ChatController
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.turn import (
    AssistantGenerationDispatchAcknowledgement,
    AssistantGenerationDispatchPhase,
    AssistantGenerationEvent,
    AssistantGenerationEventPhase,
    AssistantGenerationRequest,
    AssistantGenerationStopAcknowledgement,
    AssistantGenerationStopRequest,
    AssistantTurnCorrelation,
    AssistantTurnRequest,
)
from XBrainLab.llm.agent.turn_scope import resolve_assistant_turn_scope
from XBrainLab.llm.agent.worker import AgentWorker


class _NoopWorker(AgentWorker):
    """Real worker contract with inference suppressed for product-language tests."""

    def initialize_agent(self) -> None:
        return None

    def generate_from_messages(self, _request: AssistantGenerationRequest) -> None:
        self.generation_dispatch_acknowledged.emit(
            AssistantGenerationDispatchAcknowledgement(
                generation_id=_request.generation_id,
                phase=AssistantGenerationDispatchPhase.ACCEPTED,
            )
        )
        self.generation_dispatch_acknowledged.emit(
            AssistantGenerationDispatchAcknowledgement(
                generation_id=_request.generation_id,
                phase=AssistantGenerationDispatchPhase.STARTED,
            )
        )

    def reinitialize_agent(self, _mode: str) -> None:
        return None

    def cancel_generation(self, request: AssistantGenerationStopRequest) -> None:
        self.generation_stop_finished.emit(
            AssistantGenerationStopAcknowledgement(
                generation_id=request.generation_id,
                stopped=True,
            )
        )

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
    """Deterministic lifecycle seam without bypassing controller RAG behavior."""

    def __init__(self, retriever: _NoopRag | None = None) -> None:
        self.retriever = retriever or _NoopRag()

    def start(self) -> bool:
        self.retriever.initialize()
        return True

    def retrieve(
        self,
        turn_id: int,
        query: str,
        callback,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> bool:
        callback(
            turn_id,
            query,
            self.retriever.get_similar_examples(
                query,
                allowed_tool_names=allowed_tool_names,
            ),
            "",
        )
        return True

    def close(self) -> bool:
        self.retriever.close()
        return True


@dataclass
class ProductHarness:
    controller: LLMController
    chat: ChatController
    statuses: list[str]
    generation_events: list[AssistantGenerationEvent]
    wait_for_generation_start: Callable[[], None]
    turn_sequence: int = 0

    @property
    def visible_transcript(self) -> list[str]:
        return [str(message["content"]) for message in self.chat.messages]

    @property
    def visible_assistant_text(self) -> str:
        return "\n".join(
            str(message["content"])
            for message in self.chat.messages
            if message["role"] == "assistant"
        )

    def send(self, user_text: str, model_text: str | None = None) -> None:
        self.turn_sequence += 1
        self.chat.add_user_message(user_text)
        scope = resolve_assistant_turn_scope(user_text)
        self.controller.handle_user_turn(
            AssistantTurnRequest(
                correlation=AssistantTurnCorrelation(
                    generation=self.turn_sequence,
                    turn_id=self.turn_sequence,
                ),
                text=user_text,
                scope=scope.scope,
                terminal_command=scope.terminal_command,
            )
        )
        if model_text is not None:
            self.wait_for_generation_start()
            generation_id = self.controller._turn_orchestrator.active_generation_id
            assert isinstance(generation_id, int)
            assert not isinstance(generation_id, bool)
            assert generation_id > 0
            self.controller.current_response = model_text
            self.controller._on_generation_finished(generation_id, [])


@pytest.fixture
def product_harness(qtbot) -> Iterator[ProductHarness]:
    statuses: list[str] = []
    generation_events: list[AssistantGenerationEvent] = []
    with (
        patch("XBrainLab.llm.agent.controller.AgentWorker", _NoopWorker),
        patch(
            "XBrainLab.llm.agent.controller.ProcessRAGRetrieverLifecycle",
            _ImmediateRagLifecycle,
        ),
    ):
        controller = LLMController(Study())
        chat = ChatController()

        controller.response_presentation_ready.connect(
            lambda presentation: chat.add_agent_message(presentation.text)
        )
        controller.generation_event.connect(generation_events.append)
        controller.generation_event.connect(
            lambda event: chat.set_processing(True)
            if isinstance(event, AssistantGenerationEvent)
            and event.phase is AssistantGenerationEventPhase.STARTED
            else None
        )
        controller.processing_finished.connect(lambda: chat.set_processing(False))
        controller.status_update.connect(statuses.append)

        yield ProductHarness(
            controller=controller,
            chat=chat,
            statuses=statuses,
            generation_events=generation_events,
            wait_for_generation_start=lambda: qtbot.waitUntil(
                lambda: (
                    controller._turn_orchestrator.dispatch_phase
                    is AssistantGenerationDispatchPhase.STARTED
                ),
                timeout=2_000,
            ),
        )

        close_controller_and_wait(controller, qtbot)


def _tool_json(name: str, parameters: dict) -> str:
    import json

    return json.dumps(
        {
            "workflow_stage": "empty",
            "tool_name": name,
            "parameters": parameters,
        }
    )


def _assert_no_raw_tool_language(text: str) -> None:
    forbidden = [
        "Tool ",
        "Tool `",
        "Tool Output:",
        "completed (",
        "Error: directory is required",
        "command_name",
        "start_training",
        "[]",
    ]
    for needle in forbidden:
        assert needle not in text
    assert re.search(r"\b[a-z]+_[a-z_]+\b", text) is None


def test_greeting_flow_is_friendly_and_does_not_call_tools(product_harness):
    product_harness.send(
        "hello",
        _tool_json(
            "respond_to_user",
            {"message": "Hello! I can help you work through your EEG workflow."},
        ),
    )

    visible = product_harness.visible_assistant_text
    assert "Hello" in visible
    assert "EEG workflow" in visible
    _assert_no_raw_tool_language(visible)


def test_qt_chat_wiring_rejects_prose_prefixed_target_action_without_execution(
    qtbot,
    tmp_path: Path,
):
    from XBrainLab.ui.chat.message_bubble import MessageBubble
    from XBrainLab.ui.chat.panel import ChatPanel

    with (
        patch("XBrainLab.llm.agent.controller.AgentWorker", _NoopWorker),
        patch(
            "XBrainLab.llm.agent.controller.ProcessRAGRetrieverLifecycle",
            _ImmediateRagLifecycle,
        ),
    ):
        controller = LLMController(Study())
        panel = ChatPanel()
        qtbot.addWidget(panel)
        controller.response_presentation_ready.connect(
            lambda presentation: panel.append_message(
                "assistant",
                presentation.text,
            )
        )
        generation_events: list[AssistantGenerationEvent] = []
        controller.generation_event.connect(generation_events.append)

        controller.handle_user_turn(
            AssistantTurnRequest.single_action(
                correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
                text="Import EEG data.",
            )
        )
        qtbot.waitUntil(
            lambda: (
                controller._turn_orchestrator.dispatch_phase
                is AssistantGenerationDispatchPhase.STARTED
            ),
            timeout=2_000,
        )
        controller._generate_response = MagicMock()
        controller._process_tool_calls = MagicMock()
        generation_id = controller._turn_orchestrator.active_generation_id
        assert isinstance(generation_id, int)
        assert not isinstance(generation_id, bool)
        assert generation_id > 0
        controller._on_chunk_received(generation_id, "Sure, I will check.\n")
        controller._on_chunk_received(
            generation_id,
            '{"workflow_stage":"empty","tool_name":"import_',
        )
        controller._on_chunk_received(
            generation_id,
            'eeg_data","parameters":{}}',
        )

        assert not any(
            bubble.isVisible() for bubble in panel.findChildren(MessageBubble)
        )

        controller._on_generation_finished(generation_id, [])
        assert generation_events == [
            AssistantGenerationEvent(
                generation_id=generation_id,
                phase=AssistantGenerationEventPhase.STARTED,
            ),
            AssistantGenerationEvent(
                generation_id=generation_id,
                phase=AssistantGenerationEventPhase.CHUNK,
                text="Sure, I will check.\n",
            ),
            AssistantGenerationEvent(
                generation_id=generation_id,
                phase=AssistantGenerationEventPhase.CHUNK,
                text='{"workflow_stage":"empty","tool_name":"import_',
            ),
            AssistantGenerationEvent(
                generation_id=generation_id,
                phase=AssistantGenerationEventPhase.CHUNK,
                text='eeg_data","parameters":{}}',
            ),
            AssistantGenerationEvent(
                generation_id=generation_id,
                phase=AssistantGenerationEventPhase.FINISHED,
            ),
        ]
        response_after_finish = controller.current_response
        controller._on_chunk_received(generation_id, "stale chunk")
        controller._on_generation_finished(generation_id, [])
        controller._on_generation_error(generation_id, "stale error")
        assert controller.current_response == response_after_finish
        assert len(generation_events) == 5
        bubbles = panel.findChildren(MessageBubble)
        visible_text = "\n".join(
            bubble.get_text() for bubble in bubbles if not bubble.isHidden()
        )

        controller._process_tool_calls.assert_not_called()
        controller._generate_response.assert_called_once_with()
        assert "Sure, I will check" not in visible_text
        _assert_no_raw_tool_language(visible_text)
        close_controller_and_wait(controller, qtbot)


def test_local_runtime_disabled_flow_is_user_visible(qtbot):
    from PyQt6.QtWidgets import QMainWindow

    from XBrainLab.llm.core.config import LLMConfig
    from XBrainLab.ui.components.agent_manager import AgentManager

    main_window = QMainWindow()
    cast(Any, main_window).ai_btn = MagicMock()
    qtbot.addWidget(main_window)

    manager = AgentManager(main_window, Study())
    manager.init_ui()
    config = LLMConfig()
    config.local_model_enabled = False
    config.local_runtime_notice_acknowledged = True

    with patch.object(
        manager.assistant_runtime,
        "load_config",
        return_value=config,
    ):
        manager.toggle()

    try:
        assert manager.chat_panel is not None
        assert manager.chat_controller.messages == []
        title = manager.chat_panel.runtime_state_title.text()
        detail = manager.chat_panel.runtime_state_detail.text()
        assert title == "Assistant setup required"
        assert "disabled" in detail
        _assert_no_raw_tool_language(f"{title}\n{detail}")
    finally:
        assert manager.close()
