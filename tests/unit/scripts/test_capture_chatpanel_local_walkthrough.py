from __future__ import annotations

import heapq
from itertools import count
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QMainWindow, QPushButton

from scripts.dev import capture_chatpanel_local_walkthrough as capture
from scripts.dev.capture_chatpanel_local_walkthrough import (
    VisibleMessage,
    collect_executed_tools,
    has_raw_debug_text,
    render_markdown,
)
from XBrainLab.llm.agent.metrics import AgentMetricsTracker
from XBrainLab.ui.chat.panel import ChatPanel


@pytest.fixture
def capture_with_delayed_runtime(monkeypatch, qtbot, tmp_path):
    """Exercise real composer enablement with virtual time and no model load."""

    def run(*, ready_after, timeout=12, controller_after=None):
        clock = [0.0]
        pending = []
        sequence = count()
        sent = []
        messages = []
        screenshots = []
        panel = ChatPanel()
        panel.set_runtime_state("loading")
        window = QMainWindow()
        window.setCentralWidget(panel)
        window.ai_btn = QPushButton(window)
        controller = SimpleNamespace(is_processing=False, metrics=AgentMetricsTracker())
        manager = SimpleNamespace(
            chat_panel=panel,
            chat_dock=panel,
            agent_controller=None,
            chat_controller=SimpleNamespace(is_processing=False),
        )
        window.agent_manager = manager
        qtbot.addWidget(window)

        def schedule(milliseconds, callback):
            heapq.heappush(
                pending, (clock[0] + milliseconds / 1000, next(sequence), callback)
            )

        def publish_controller():
            manager.agent_controller = controller

        def activate():
            if ready_after is not None:
                schedule(ready_after * 1000, lambda: panel.set_runtime_state("ready"))
                schedule(
                    (controller_after if controller_after is not None else ready_after)
                    * 1000,
                    publish_controller,
                )

        window.ai_btn.clicked.connect(activate)

        def respond(prompt):
            sent.append((clock[0], prompt))
            messages.extend(
                [
                    VisibleMessage("user", prompt),
                    VisibleMessage(
                        "assistant", "Preprocessing prepares the EEG signal."
                    ),
                ]
            )

        panel.send_message.connect(respond)

        def execute():
            while pending and window.isVisible():
                due, _sequence, callback = heapq.heappop(pending)
                assert due <= timeout + 2, (
                    "Capture did not respect its original deadline."
                )
                clock[0] = due
                qtbot.wait(1)
                callback()

        def screenshot(_window, path):
            screenshots.append((clock[0], path.name, panel.input_field.isEnabled()))
            return 0

        monkeypatch.setattr(capture, "QTimer", SimpleNamespace(singleShot=schedule))
        monkeypatch.setattr(
            capture, "time", SimpleNamespace(monotonic=lambda: clock[0])
        )
        monkeypatch.setattr("XBrainLab.backend.study.Study", lambda: object())
        monkeypatch.setattr(
            "XBrainLab.ui.main_window.MainWindow", lambda _study: window
        )
        monkeypatch.setattr(capture, "_capture_current_window", screenshot)
        monkeypatch.setattr(
            capture, "collect_visible_messages", lambda _panel: messages
        )
        monkeypatch.setattr(capture.LLMConfig, "load_from_file", lambda: None)
        monkeypatch.setattr(capture, "classify_runtime", lambda _config: {})
        app = SimpleNamespace(exec=execute, processEvents=lambda: qtbot.wait(1))
        payload = capture.run_walkthrough(
            app, tmp_path, "Explain preprocessing.", timeout
        )
        return payload, sent, screenshots

    return run


@pytest.mark.parametrize("controller_after", [None, 9])
def test_capture_waits_for_runtime_and_controller_before_submitting(
    capture_with_delayed_runtime,
    controller_after,
) -> None:
    payload, sent, screenshots = capture_with_delayed_runtime(
        ready_after=6,
        controller_after=controller_after,
    )
    assert payload["status"] == "passed"
    assert len(sent) == 1
    assert sent[0][0] >= 1.5 + (controller_after or 6)
    ready = [shot for shot in screenshots if shot[1] == capture.READY_SCREENSHOT]
    assert len(ready) == 1
    assert ready[0][2] is True


def test_capture_never_ready_expires_without_submission_or_ready_screenshot(
    capture_with_delayed_runtime,
) -> None:
    payload, sent, screenshots = capture_with_delayed_runtime(
        ready_after=None, timeout=5
    )
    assert payload["status"] == "failed"
    assert "5 seconds" in payload["failure_reason"]
    assert sent == []
    assert all(shot[1] != capture.READY_SCREENSHOT for shot in screenshots)
    assert payload["elapsed_seconds"] <= 5.25


def test_has_raw_debug_text_flags_tool_syntax() -> None:
    assert has_raw_debug_text(['{"tool_name": "scan_source"}']) is True
    assert (
        has_raw_debug_text(["Preprocessing prepares EEG data for modeling."]) is False
    )


def test_has_raw_debug_text_flags_backend_status_tokens_in_visible_context() -> None:
    assert (
        has_raw_debug_text(["Interpretation validation: needs_confirmation."]) is True
    )
    assert has_raw_debug_text(['{"decision": "needs_confirmation"}']) is True
    assert has_raw_debug_text(["Workflow status = waiting_for_decision"]) is True


def test_has_raw_debug_text_allows_paths_and_general_snake_case_text() -> None:
    assert (
        has_raw_debug_text(
            ["Loaded /tmp/session_01/needs_confirmation.edf successfully."]
        )
        is False
    )
    assert (
        has_raw_debug_text(
            [r"Loaded C:\\EEG_Data\\subject_01\\recording_file.edf successfully."]
        )
        is False
    )
    assert has_raw_debug_text(["snake_case is a common naming convention."]) is False
    assert (
        has_raw_debug_text(
            ["The validation result is false_positive for this example."]
        )
        is False
    )


def test_render_markdown_includes_visible_transcript() -> None:
    payload = {
        "status": "passed",
        "failure_reason": "",
        "prompt": "Explain preprocessing.",
        "runtime": {
            "classification": "gpu-ready",
            "model_id": "microsoft/Phi-4-mini-instruct",
            "cache_usage": "15.34 GB",
        },
        "hf_offline": {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
        "screenshots": {
            "ready": "build/dev-artifacts/ui/chatpanel-local-ready.png",
            "response": "build/dev-artifacts/ui/chatpanel-local-response.png",
        },
        "elapsed_seconds": 12.3,
        "visible_messages": [
            VisibleMessage("user", "Explain preprocessing.").__dict__,
            VisibleMessage(
                "assistant",
                "Preprocessing prepares EEG data for modeling.",
            ).__dict__,
        ],
        "executed_tools": [
            {
                "name": "query_state",
                "success": True,
                "duration_ms": 1.2,
                "error": None,
            }
        ],
        "ui_state": {
            "send_button_text": "Send",
            "send_button_enabled": True,
            "input_enabled": True,
            "chat_processing": False,
            "controller_processing": False,
        },
    }

    rendered = render_markdown(payload)

    assert "ChatPanel Local Model Walkthrough" in rendered
    assert "Preprocessing prepares EEG data for modeling." in rendered
    assert "`query_state`: `ok`" in rendered
    assert "tool_name" not in rendered


def test_collect_executed_tools_reads_latest_completed_turn_metrics() -> None:
    metrics = AgentMetricsTracker()

    assert collect_executed_tools(metrics) == []

    unfinished = metrics.start_turn()
    unfinished.record_tool("ignored", True, 9.0)
    assert collect_executed_tools(metrics) == []

    completed = metrics.start_turn()
    completed.record_tool("resample_data", True, 1.23456)
    completed.record_tool("set_reference", False, 2.0, "invalid reference")
    metrics.finish_turn()

    assert collect_executed_tools(metrics) == [
        {
            "name": "resample_data",
            "success": True,
            "duration_ms": 1.235,
            "error": None,
        },
        {
            "name": "set_reference",
            "success": False,
            "duration_ms": 2.0,
            "error": "invalid reference",
        },
    ]

    metrics.reset()
    assert collect_executed_tools(metrics) == []
