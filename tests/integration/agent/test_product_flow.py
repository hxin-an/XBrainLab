"""Product-facing agent flow regressions.

These tests exercise the path from user intent through controller-visible
transcript messages. They intentionally assert user language, not internal tool
payload shape, while still checking structured diagnostics remain available to
the agent history.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from XBrainLab.backend.controller.chat_controller import ChatController
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.controller import LLMController


class _NoopWorker(QObject):
    chunk_received = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.generation_thread = None

    def initialize_agent(self) -> None:
        return None

    def generate_from_messages(self, _messages: list[dict]) -> None:
        return None

    def reinitialize_agent(self, _mode: str) -> None:
        return None


class _NoopRag:
    def initialize(self) -> None:
        return None

    def get_similar_examples(self, _text: str) -> list:
        return []

    def close(self) -> None:
        return None


@dataclass
class ProductHarness:
    controller: LLMController
    chat: ChatController
    statuses: list[str]

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
        self.chat.add_user_message(user_text)
        self.controller.handle_user_input(user_text)
        if model_text is not None:
            self.controller.current_response = model_text
            self.controller._on_generation_finished()


@pytest.fixture
def product_harness(qtbot) -> Iterator[ProductHarness]:
    statuses: list[str] = []
    with (
        patch("XBrainLab.llm.agent.controller.AgentWorker", _NoopWorker),
        patch("XBrainLab.llm.agent.controller.RAGRetriever", _NoopRag),
        patch("XBrainLab.llm.agent.controller.threading.Thread") as MockThread,
    ):
        MockThread.return_value.start = MagicMock()
        controller = LLMController(Study())
        chat = ChatController()

        controller.response_ready.connect(
            lambda _sender, text: chat.add_agent_message(text)
        )
        controller.chunk_received.connect(lambda text: chat.add_agent_message(text))
        controller.generation_started.connect(lambda: chat.set_processing(True))
        controller.processing_finished.connect(lambda: chat.set_processing(False))
        controller.status_update.connect(statuses.append)

        yield ProductHarness(controller=controller, chat=chat, statuses=statuses)

        controller.close()


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
        "show files",
        _tool_json("list_files", {"directory": str(tmp_path)}),
    )

    visible = product_harness.visible_assistant_text
    assert "did not find files" in visible
    assert "import EEG data" in visible
    _assert_no_raw_tool_language(visible)


def test_state_gated_command_flow_uses_backend_reason(product_harness):
    product_harness.send("start training", _tool_json("start_training", {}))

    visible = product_harness.visible_assistant_text
    assert "Training is not available yet" in visible
    assert "Generate datasets before training" in visible
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


def test_local_runtime_disabled_flow_is_user_visible(qtbot):
    from PyQt6.QtWidgets import QMainWindow

    from XBrainLab.llm.core.config import LLMConfig
    from XBrainLab.ui.components.agent_manager import AgentManager

    main_window = QMainWindow()
    main_window.ai_btn = MagicMock()
    qtbot.addWidget(main_window)

    manager = AgentManager(main_window, Study())
    manager.init_ui()
    config = LLMConfig()
    config.local_model_enabled = False
    config.local_runtime_notice_acknowledged = True

    with (
        patch.object(manager, "_load_runtime_config", return_value=config),
        patch.object(manager, "_needs_local_runtime_first_run", return_value=False),
    ):
        manager.toggle()

    visible = "\n".join(
        str(message["content"])
        for message in manager.chat_controller.messages
        if message["role"] == "assistant"
    )
    assert "Assistant unavailable" in visible
    assert "disabled" in visible
    _assert_no_raw_tool_language(visible)
