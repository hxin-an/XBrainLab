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
from XBrainLab.llm.agent.tool_attempt_coordinator import (
    ToolAttemptAction,
    ToolAttemptRequest,
)
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

    def __init__(self, retriever: _NoopRag) -> None:
        self.retriever = retriever

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
        self.controller.handle_user_turn(
            AssistantTurnRequest(
                correlation=AssistantTurnCorrelation(
                    generation=self.turn_sequence,
                    turn_id=self.turn_sequence,
                ),
                text=user_text,
            )
        )
        if model_text is not None:
            self.wait_for_generation_start()
            generation_id = self.controller._active_generation_id
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
        patch("XBrainLab.llm.agent.controller.RAGRetriever", _NoopRag),
        patch(
            "XBrainLab.llm.agent.controller.RAGRetrieverLifecycle",
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
                    controller._active_generation_dispatch_phase
                    is AssistantGenerationDispatchPhase.STARTED
                ),
                timeout=2_000,
            ),
        )

        close_controller_and_wait(controller, qtbot)


def _tool_json(name: str, parameters: dict) -> str:
    import json

    return json.dumps({"tool_name": name, "parameters": parameters})


def _assert_no_raw_tool_language(text: str) -> None:
    forbidden = [
        "Tool ",
        "Tool `",
        "Tool Output:",
        "completed (",
        "Error: directory is required",
        "command_name",
        "list_files",
        "start_training",
        "[]",
    ]
    for needle in forbidden:
        assert needle not in text
    assert re.search(r"\b[a-z]+_[a-z_]+\b", text) is None


def test_greeting_flow_is_friendly_and_does_not_call_tools(product_harness):
    product_harness.controller._generate_response = MagicMock()

    product_harness.send("hello")

    visible = product_harness.visible_assistant_text
    assert "Hello" in visible
    assert "import raw data" in visible
    product_harness.controller._generate_response.assert_not_called()
    _assert_no_raw_tool_language(visible)


def test_missing_argument_flow_asks_for_folder_without_schema_error(product_harness):
    product_harness.send("list files", _tool_json("list_files", {}))

    events = product_harness.generation_events
    assert len(events) == 2
    assert all(isinstance(event, AssistantGenerationEvent) for event in events)
    assert events[0].generation_id > 0
    assert events[1].generation_id == events[0].generation_id
    assert [event.phase for event in events] == [
        AssistantGenerationEventPhase.STARTED,
        AssistantGenerationEventPhase.FINISHED,
    ]

    visible = product_harness.visible_assistant_text
    assert "folder path" in visible
    assert "paste the path" in visible
    _assert_no_raw_tool_language(visible)

    history_text = "\n".join(
        str(message["content"]) for message in product_harness.controller.history
    )
    assert "Tool Output:" in history_text
    assert "directory is required" in history_text


def test_empty_tool_result_flow_uses_user_empty_state(
    tmp_path: Path,
    product_harness,
):
    product_harness.send(
        f"show files in {tmp_path}",
        _tool_json("list_files", {"directory": str(tmp_path)}),
    )

    visible = product_harness.visible_assistant_text
    assert "did not find files" in visible
    assert "import EEG data" in visible
    _assert_no_raw_tool_language(visible)


def test_model_invented_existing_path_is_rejected_before_file_access(
    tmp_path: Path,
    product_harness,
):
    not_selected = tmp_path / "not-selected"
    not_selected.mkdir()
    (not_selected / "private.txt").write_text("private", encoding="utf-8")

    product_harness.send(
        "Show my EEG files",
        _tool_json("list_files", {"directory": str(not_selected)}),
    )

    visible = product_harness.visible_assistant_text
    assert "Choose a file or folder in the app" in visible
    assert "private.txt" not in visible
    _assert_no_raw_tool_language(visible)


def test_qt_chat_wiring_rejects_prose_prefixed_tool_trace_without_execution(
    qtbot,
    tmp_path: Path,
):
    from XBrainLab.ui.chat.message_bubble import MessageBubble
    from XBrainLab.ui.chat.panel import ChatPanel

    with (
        patch("XBrainLab.llm.agent.controller.AgentWorker", _NoopWorker),
        patch("XBrainLab.llm.agent.controller.RAGRetriever", _NoopRag),
        patch(
            "XBrainLab.llm.agent.controller.RAGRetrieverLifecycle",
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
            AssistantTurnRequest(
                correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
                text=f"Show files in {tmp_path}",
            )
        )
        qtbot.waitUntil(
            lambda: (
                controller._active_generation_dispatch_phase
                is AssistantGenerationDispatchPhase.STARTED
            ),
            timeout=2_000,
        )
        controller._generate_response = MagicMock()
        controller._process_tool_calls = MagicMock()
        generation_id = controller._active_generation_id
        assert isinstance(generation_id, int)
        assert not isinstance(generation_id, bool)
        assert generation_id > 0
        controller._on_chunk_received(generation_id, "Sure, I will check.\n")
        controller._on_chunk_received(generation_id, '{"tool_name":"list_')
        controller._on_chunk_received(
            generation_id, f'files","parameters":{{"directory":"{tmp_path}"}}}}'
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
                text='{"tool_name":"list_',
            ),
            AssistantGenerationEvent(
                generation_id=generation_id,
                phase=AssistantGenerationEventPhase.CHUNK,
                text=f'files","parameters":{{"directory":"{tmp_path}"}}}}',
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
        assert "did not find files" not in visible_text
        _assert_no_raw_tool_language(visible_text)
        close_controller_and_wait(controller, qtbot)


def test_state_gated_command_flow_uses_backend_reason(product_harness):
    product_harness.send("start training")

    visible = product_harness.visible_assistant_text
    assert "Start training is not available yet" in visible
    assert "Generate datasets before training" in visible
    assert product_harness.generation_events == []
    _assert_no_raw_tool_language(visible)


def test_successful_command_result_summary_flow(product_harness):
    product_harness.send(
        "use eegnet",
        _tool_json("set_model", {"model_name": "eegnet"}),
    )

    visible = product_harness.visible_assistant_text
    assert "Model configured" in visible
    assert "eegnet" in visible
    _assert_no_raw_tool_language(visible)


def test_workflow_scan_continuation_authorizes_fresh_preview_candidate(
    product_harness,
):
    source = Path("tests/fixtures/data/A01T.gdf").resolve()
    request_text = f"Load {source} and continue until a decision is needed."
    product_harness.controller.set_execution_mode(LLMController.MODE_MULTI)

    product_harness.send(
        request_text,
        _tool_json("scan_source", {"source_path": str(source)}),
    )

    publication = product_harness.controller._active_tool_publication
    assert publication.authorized_command == "preview_interpretation"
    assert publication.tool_names == frozenset({"preview_interpretation"})
    decision = product_harness.controller._tool_attempt_coordinator.evaluate(
        ToolAttemptRequest(
            command_name="preview_interpretation",
            params={},
            confidence=0.9,
            publication=publication,
            latest_user_text=request_text,
        )
    )

    assert decision.action is ToolAttemptAction.EXECUTE


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
        assert manager.chat_controller.messages == []
        title = manager.chat_panel.runtime_state_title.text()
        detail = manager.chat_panel.runtime_state_detail.text()
        assert title == "Assistant setup required"
        assert "disabled" in detail
        _assert_no_raw_tool_language(f"{title}\n{detail}")
    finally:
        assert manager.close()
