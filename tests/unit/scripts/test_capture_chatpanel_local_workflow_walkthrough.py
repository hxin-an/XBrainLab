from __future__ import annotations

import heapq
from itertools import count
from types import SimpleNamespace

import pytest
from PIL import Image
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMainWindow, QPushButton

from scripts.dev import capture_chatpanel_local_workflow_walkthrough as workflow
from scripts.dev.capture_chatpanel_local_walkthrough import (
    VisibleMessage,
    _assistant_setup_required,
)
from scripts.dev.capture_chatpanel_local_workflow_walkthrough import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PROMPTS,
    ROOT,
    _assistant_is_ready,
    _build_post_close_evidence,
    _has_unpainted_main_surface,
    _prepare_isolated_settings,
    _record_latest_completed_tools,
    _runtime_summary,
    _turn_contract_failure,
    render_markdown,
)
from XBrainLab.llm.agent.metrics import AgentMetricsTracker
from XBrainLab.llm.agent.response_presentation import (
    AssistantResponseKind,
    AssistantResponsePresentation,
)
from XBrainLab.llm.agent.turn import (
    AssistantTurnCorrelation,
    AssistantTurnRequest,
    AssistantTurnTerminal,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.ui.chat.panel import ChatPanel


@pytest.fixture
def run_observed_workflow(monkeypatch, qtbot, tmp_path):
    """Run both real composer clicks while isolating model, clock and capture IO."""

    def run(*, fault=None, affected_turn=1, terminal_delay=0, response_delay=0):
        clock = [0.0]
        pending = []
        sequence = count()
        sent = []
        messages = []
        screenshots = []
        panel = ChatPanel()
        panel.set_runtime_state("ready")

        class Controller(QObject):
            response_presentation_ready = pyqtSignal(object)
            is_processing = False

            def __init__(self):
                super().__init__()
                self.metrics = AgentMetricsTracker()

            def runtime_snapshot(self):
                return SimpleNamespace(model_id="fixture-model")

        class Dispatcher(QObject):
            input_requested = pyqtSignal(object)
            state = "ready"

        class Runtime(QObject):
            turn_finished = pyqtSignal(object)
            cleanup_finished = pyqtSignal(bool, str)
            state = "ready"

        controller = Controller()
        runtime = Runtime()
        runtime.dispatcher = Dispatcher()
        manager = SimpleNamespace(
            chat_panel=panel,
            chat_dock=panel,
            agent_controller=controller,
            chat_controller=SimpleNamespace(is_processing=False),
            assistant_runtime=runtime,
        )

        class Window(QMainWindow):
            def init_agent(self):
                return None

            def closeEvent(self, event):
                runtime.state = "closed"
                runtime.dispatcher.state = "closed"
                manager.agent_controller = None
                runtime.cleanup_finished.emit(True, "")
                super().closeEvent(event)

        window = Window()
        window.setCentralWidget(panel)
        window.ai_btn = QPushButton(window)
        window.agent_manager = manager
        qtbot.addWidget(window)

        def schedule(milliseconds, callback):
            heapq.heappush(
                pending, (clock[0] + milliseconds / 1000, next(sequence), callback)
            )

        def respond(prompt):
            index = len(sent)
            sent.append((clock[0], prompt))
            panel.accept_composer_submission(prompt)
            current = AssistantTurnCorrelation(generation=index + 1, turn_id=index + 1)
            previous = AssistantTurnCorrelation(generation=1, turn_id=1)
            active_fault = fault if index == affected_turn else None
            runtime.dispatcher.input_requested.emit(
                AssistantTurnRequest(text=prompt, correlation=current)
            )
            text = (
                "The dataset is empty, so import EEG data first."
                if index == 0
                else "EEG preprocessing cleans signals before analysis."
            )
            messages.extend(
                [VisibleMessage("user", prompt), VisibleMessage("assistant", text)]
            )
            response = AssistantResponsePresentation(
                text=text,
                correlation=previous if active_fault == "stale_response" else current,
                kind=(
                    AssistantResponseKind.ERROR
                    if active_fault == "error_response"
                    else AssistantResponseKind.MESSAGE
                ),
            )
            schedule(
                (response_delay if index == affected_turn else 0) * 1000,
                lambda: controller.response_presentation_ready.emit(response),
            )
            if active_fault == "missing_terminal":
                return
            terminal = AssistantTurnTerminal(
                correlation=previous if active_fault == "stale_terminal" else current,
                outcome="failed" if active_fault == "failed_terminal" else "completed",
            )

            def finish_turn():
                runtime.turn_finished.emit(terminal)
                if active_fault == "duplicate_terminal":
                    runtime.turn_finished.emit(terminal)

            schedule(
                (terminal_delay if index == affected_turn else 0) * 1000, finish_turn
            )

        panel.send_message.connect(respond)

        def execute():
            while pending and window.isVisible():
                due, _sequence, callback = heapq.heappop(pending)
                assert due <= 13, "Workflow capture did not respect its deadline."
                clock[0] = due
                qtbot.wait(1)
                callback()

        def screenshot(_window, path):
            screenshots.append((clock[0], path.name))
            return 0

        monkeypatch.setattr(workflow, "QTimer", SimpleNamespace(singleShot=schedule))
        monkeypatch.setattr(
            workflow, "time", SimpleNamespace(monotonic=lambda: clock[0])
        )
        monkeypatch.setattr("XBrainLab.backend.study.Study", lambda: object())
        monkeypatch.setattr(
            "XBrainLab.ui.main_window.MainWindow", lambda _study: window
        )
        monkeypatch.setattr(workflow, "_capture_current_window", screenshot)
        monkeypatch.setattr(
            workflow, "_has_unpainted_main_surface", lambda _path: False
        )
        monkeypatch.setattr(
            workflow, "collect_visible_messages", lambda _panel: messages
        )
        monkeypatch.setattr(workflow.LLMConfig, "load_from_file", lambda: None)
        app = SimpleNamespace(exec=execute, processEvents=lambda: qtbot.wait(1))
        payload = workflow.run_workflow(
            app, tmp_path, 12, runtime_inspection={"current_model_id": "fixture-model"}
        )
        return payload, sent, screenshots

    return run


def test_workflow_observes_both_real_composer_submissions(run_observed_workflow):
    payload, sent, _screenshots = run_observed_workflow()
    assert payload["status"] == "passed", payload["failure_reason"]
    assert [text for _time, text in sent] == DEFAULT_PROMPTS
    assert len(payload["turns"]) == 2
    assert payload["post_close"]["passed"] is True


def test_workflow_stops_before_second_submission_if_first_turn_failed(
    run_observed_workflow,
):
    payload, sent, screenshots = run_observed_workflow(
        fault="failed_terminal", affected_turn=0
    )
    assert payload["status"] == "failed"
    assert [text for _time, text in sent] == DEFAULT_PROMPTS[:1]
    assert payload["turns"] == []
    assert not any("turn-" in name for _time, name in screenshots)


@pytest.mark.parametrize(
    "fault",
    [
        "missing_terminal",
        "failed_terminal",
        "duplicate_terminal",
        "stale_terminal",
        "stale_response",
        "error_response",
    ],
)
def test_workflow_never_credits_uncorrelated_or_unsuccessful_second_turn(
    run_observed_workflow, fault
):
    payload, sent, screenshots = run_observed_workflow(fault=fault)
    assert payload["status"] == "failed"
    assert len(sent) == 2
    assert len(payload["turns"]) == 1
    assert not any(
        name == "chatpanel-workflow-turn-2.png" for _time, name in screenshots
    )


@pytest.mark.parametrize("delayed_field", ["terminal_delay", "response_delay"])
def test_workflow_waits_for_typed_evidence_after_visible_text_and_idle(
    run_observed_workflow, delayed_field
):
    payload, sent, screenshots = run_observed_workflow(**{delayed_field: 3})
    assert payload["status"] == "passed", payload["failure_reason"]
    captured_at = next(
        time for time, name in screenshots if name == "chatpanel-workflow-turn-2.png"
    )
    assert captured_at >= sent[1][0] + 3


def test_default_output_uses_dev_artifact_namespace() -> None:
    assert DEFAULT_OUTPUT_DIR == (
        ROOT / "build" / "dev-artifacts" / "chatpanel-local-workflow"
    )


def test_terminal_tool_capture_keeps_two_turn_aggregate_and_failure_evidence() -> None:
    metrics = AgentMetricsTracker()
    state = {"executed_tools": [], "observed_turn_ids": set()}
    first = metrics.start_turn()
    first.record_tool("switch_panel", True, 1.0)
    metrics.finish_turn()
    assert _record_latest_completed_tools(state, metrics) == [
        {"name": "switch_panel", "success": True, "duration_ms": 1.0, "error": None}
    ]
    assert _record_latest_completed_tools(state, metrics) == []

    second = metrics.start_turn()
    second.record_tool("apply_bandpass_filter", False, 2.0, "blocked")
    assert _record_latest_completed_tools(state, metrics) == []
    metrics.finish_turn()
    captured = _record_latest_completed_tools(state, metrics)
    assert captured[0]["name"] == "apply_bandpass_filter"
    assert captured[0]["success"] is False
    assert [tool["name"] for tool in state["executed_tools"]] == [
        "switch_panel",
        "apply_bandpass_filter",
    ]


def test_unattended_capture_detects_setup_without_clicking_it() -> None:
    class FakeLabel:
        def text(self) -> str:
            return "Start XBrainLab Assistant"

    class FakeWidget:
        def isVisible(self) -> bool:
            return True

    class FakeButton:
        def __init__(self, text: str) -> None:
            self.label = text
            self.clicks = 0

        def text(self) -> str:
            return self.label

        def click(self) -> None:
            self.clicks += 1

    enable = FakeButton("Enable Assistant")
    panel = SimpleNamespace(
        runtime_state_title=FakeLabel(),
        runtime_state_widget=FakeWidget(),
        retry_runtime_btn=enable,
    )

    assert _assistant_setup_required(panel) is True
    assert enable.clicks == 0


def test_deactivation_capture_settings_are_isolated_below_temp(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "scripts.dev.capture_chatpanel_local_workflow_walkthrough.tempfile.gettempdir",
        lambda: str(tmp_path.parent),
    )
    monkeypatch.setattr(
        LLMConfig,
        "_default_settings_path",
        LLMConfig._default_settings_path,
    )
    settings_path = tmp_path / "capture" / "settings.json"

    _prepare_isolated_settings(settings_path)

    loaded = LLMConfig.load_from_file()
    assert settings_path.is_file()
    assert loaded is not None
    assert loaded.local_model_enabled is True
    assert loaded.local_runtime_notice_acknowledged is True


def test_deactivation_capture_rejects_repo_settings_path() -> None:
    with pytest.raises(ValueError, match="OS temp"):
        _prepare_isolated_settings(ROOT / "settings.json")


def test_assistant_ready_requires_visible_enabled_idle_controls() -> None:
    class FakeControl:
        def __init__(self, *, enabled: bool = True, visible: bool = True) -> None:
            self.enabled = enabled
            self.visible = visible

        def isEnabled(self) -> bool:
            return self.enabled

        def isVisible(self) -> bool:
            return self.visible

    class FakePanel:
        input_field = FakeControl()
        send_btn = FakeControl(enabled=False)

    class FakeController:
        is_processing = False

    class FakeManager:
        chat_panel = FakePanel()
        chat_dock = FakeControl()
        chat_controller = FakeController()
        agent_controller = FakeController()

    manager = FakeManager()
    assert _assistant_is_ready(manager) is True

    manager.chat_panel.input_field.enabled = False
    assert _assistant_is_ready(manager) is False

    manager.chat_panel.input_field.enabled = True
    manager.chat_controller.is_processing = True
    assert _assistant_is_ready(manager) is False


def test_walkthrough_contract_requires_two_no_tool_informational_answers() -> None:
    assert all("query_state" not in prompt for prompt in DEFAULT_PROMPTS)
    assert all("state query tool" not in prompt.lower() for prompt in DEFAULT_PROMPTS)
    assert (
        _turn_contract_failure(
            0,
            "The dataset is empty, so importing EEG data is the next available step.",
            [],
        )
        is None
    )
    assert "must not call" in (
        _turn_contract_failure(
            0,
            "Ready.",
            [{"name": "import_eeg_data", "success": True}],
        )
        or ""
    )
    assert "workflow readiness" in (
        _turn_contract_failure(0, "Everything is fine.", []) or ""
    )

    assert (
        _turn_contract_failure(
            1,
            "EEG preprocessing cleans signals before epoching and analysis.",
            [],
        )
        is None
    )
    assert "must not call" in (
        _turn_contract_failure(
            1,
            "EEG preprocessing prepares the signal.",
            [{"name": "import_eeg_data", "success": True}],
        )
        or ""
    )
    assert "generic refusal" in (
        _turn_contract_failure(
            1,
            "No workflow action is needed for that question. Ask for a concrete step.",
            [],
        )
        or ""
    )
    assert "previous workflow" in (
        _turn_contract_failure(
            1,
            (
                "The current XBrainLab workflow status is empty. "
                "EEG preprocessing prepares signals for analysis."
            ),
            [],
        )
        or ""
    )
    assert "one short sentence" in (
        _turn_contract_failure(
            1,
            (
                "EEG preprocessing prepares signals for analysis. "
                "It can also reduce noise before training."
            ),
            [],
        )
        or ""
    )


def test_runtime_summary_preserves_inspected_and_loaded_model_identity() -> None:
    runtime = {
        "classification": "gpu-ready",
        "current_model_id": "ibm-granite/granite-4.0-micro",
        "message": "Local runtime ready.",
        "cache_dir": "/redacted/cache",
        "cache_usage": "6.82 GB",
        "cache_usage_bytes": 6_820_000_000,
        "has_local_cache": True,
        "gpu_fallback_reason": None,
    }

    matched = _runtime_summary(
        runtime,
        loaded_model_id="ibm-granite/granite-4.0-micro",
    )
    mismatched = _runtime_summary(
        runtime,
        loaded_model_id="ibm-granite/granite-3.3-2b-instruct",
    )

    assert matched["model_id"] == "ibm-granite/granite-4.0-micro"
    assert matched["inspected_model_id"] == "ibm-granite/granite-4.0-micro"
    assert matched["model_identity_matches"] is True
    assert mismatched["model_id"] == "ibm-granite/granite-3.3-2b-instruct"
    assert mismatched["model_identity_matches"] is False


def test_walkthrough_capture_rejects_large_unpainted_left_surface(tmp_path) -> None:
    broken = tmp_path / "broken.png"
    painted = tmp_path / "painted.png"
    Image.new("RGB", (100, 60), (0, 0, 0)).save(broken)
    Image.new("RGB", (100, 60), (30, 30, 30)).save(painted)

    assert _has_unpainted_main_surface(broken) is True
    assert _has_unpainted_main_surface(painted) is False


def test_post_close_evidence_requires_terminal_runtime_and_no_generation_threads() -> (
    None
):
    evidence = _build_post_close_evidence(
        cleanup_events=[{"ok": True, "message": "closed"}],
        runtime_state="closed",
        dispatcher_state="closed",
        controller_released=True,
        window_visible=False,
        registered_generation_thread_count=0,
        running_generation_thread_count=0,
    )

    assert evidence["passed"] is True
    assert all(evidence["checks"].values())

    incomplete = _build_post_close_evidence(
        cleanup_events=[{"ok": False, "message": "still stopping"}],
        runtime_state="cleanup_pending",
        dispatcher_state="closing",
        controller_released=False,
        window_visible=True,
        registered_generation_thread_count=1,
        running_generation_thread_count=1,
    )

    assert incomplete["passed"] is False
    assert incomplete["checks"]["runtime_cleanup_succeeded"] is False
    assert incomplete["checks"]["runtime_closed"] is False
    assert incomplete["checks"]["no_registered_generation_threads"] is False


def test_render_markdown_lists_turns_and_tools() -> None:
    payload = {
        "status": "passed",
        "failure_reason": "",
        "runtime": {
            "classification": "gpu-ready",
            "model_id": "ibm-granite/granite-4.0-micro",
            "cache_usage": "19.62 GB",
        },
        "hf_offline": {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
        "screenshots": {"ready": "ready.png"},
        "elapsed_seconds": 42.0,
        "turns": [
            {
                "index": 1,
                "prompt": "Check state.",
                "assistant_text": "Application state snapshot ready.",
                "new_tool_count": 0,
                "screenshot": "turn-1.png",
            },
            {
                "index": 2,
                "prompt": "Create epochs.",
                "assistant_text": "Epoch creation is not available yet.",
                "new_tool_count": 0,
                "screenshot": "turn-2.png",
            },
        ],
        "executed_tools": [],
        "ui_state": {
            "send_button_text": "Send",
            "send_button_enabled": True,
            "input_enabled": True,
            "chat_processing": False,
            "controller_processing": False,
        },
        "post_close": _build_post_close_evidence(
            cleanup_events=[{"ok": True, "message": "closed"}],
            runtime_state="closed",
            dispatcher_state="closed",
            controller_released=True,
            window_visible=False,
            registered_generation_thread_count=0,
            running_generation_thread_count=0,
        ),
    }

    rendered = render_markdown(payload)

    assert "Turn 1" in rendered
    assert "Turn 2" in rendered
    assert "## Executed Tools" in rendered
    assert "- none" in rendered
    assert "Epoch creation is not available yet." in rendered
    assert "runtime state: `closed`" in rendered
    assert "registered generation threads: `0`" in rendered
