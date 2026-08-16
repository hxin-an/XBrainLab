from __future__ import annotations

import pytest
from PIL import Image

from scripts.dev.capture_chatpanel_local_workflow_walkthrough import (
    DEFAULT_OUTPUT_DIR,
    ROOT,
    _assistant_is_ready,
    _build_post_close_evidence,
    _disable_first_run_dialog_for_unattended_capture,
    _has_unpainted_main_surface,
    _prepare_isolated_settings,
    _turn_contract_failure,
    render_markdown,
)
from XBrainLab.llm.core.config import LLMConfig


def test_default_output_uses_dev_artifact_namespace() -> None:
    assert DEFAULT_OUTPUT_DIR == (
        ROOT / "build" / "dev-artifacts" / "chatpanel-local-workflow"
    )


def test_unattended_capture_bypasses_first_run_without_persistence() -> None:
    class FakeRuntime:
        def needs_first_run(self, config: object) -> bool:
            return True

    class FakeManager:
        _assistant_runtime = FakeRuntime()

    class FakeWindow:
        agent_manager = FakeManager()

    window = FakeWindow()

    _disable_first_run_dialog_for_unattended_capture(window)

    assert window.agent_manager._assistant_runtime.needs_first_run(object()) is False


def test_unattended_capture_requires_initialized_assistant_manager() -> None:
    class FakeWindow:
        agent_manager = None

    with pytest.raises(RuntimeError, match="must be initialized"):
        _disable_first_run_dialog_for_unattended_capture(FakeWindow())


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

    _prepare_isolated_settings(
        settings_path,
        model_id=LLMConfig.default_local_model_id(),
    )

    loaded = LLMConfig.load_from_file()
    assert settings_path.is_file()
    assert loaded is not None
    assert loaded.local_model_enabled is True
    assert loaded.local_runtime_notice_acknowledged is True


def test_deactivation_capture_rejects_repo_settings_path() -> None:
    with pytest.raises(ValueError, match="OS temp"):
        _prepare_isolated_settings(
            ROOT / "settings.json",
            model_id=LLMConfig.default_local_model_id(),
        )


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


def test_walkthrough_contract_requires_state_tool_then_no_tool_explanation() -> None:
    assert (
        _turn_contract_failure(
            0,
            "The dataset is empty, so importing EEG data is the next available step.",
            [{"name": "query_state", "success": True}],
        )
        is None
    )
    assert "query_state" in (_turn_contract_failure(0, "Ready.", []) or "")
    assert "exactly once" in (
        _turn_contract_failure(
            0,
            "Ready.",
            [
                {"name": "query_state", "success": True},
                {"name": "query_state", "success": True},
            ],
        )
        or ""
    )
    assert "must not call other tools" in (
        _turn_contract_failure(
            0,
            "Ready.",
            [
                {"name": "query_state", "success": True},
                {"name": "preprocess", "success": True},
            ],
        )
        or ""
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
            [{"name": "query_state", "success": True}],
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
                "The current workflow status cannot be determined without the state "
                "query tool. EEG preprocessing prepares signals for analysis."
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
            "model_id": "microsoft/Phi-4-mini-instruct",
            "cache_usage": "15.34 GB",
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
                "new_tool_count": 1,
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
        "executed_tools": [
            {
                "name": "query_state",
                "success": True,
                "duration_ms": 1.0,
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
    assert "`query_state`: `ok`" in rendered
    assert "Epoch creation is not available yet." in rendered
    assert "runtime state: `closed`" in rendered
    assert "registered generation threads: `0`" in rendered
