#!/usr/bin/env python3
"""Capture a true local-model multi-turn ChatPanel workflow artifact."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from PIL import Image
from PyQt6.QtCore import QPoint, QSettings, QSize, QTimer
from PyQt6.QtWidgets import QApplication

from scripts.dev.capture_chatpanel_local_walkthrough import (
    collect_executed_tools,
    collect_visible_messages,
    has_raw_debug_text,
    is_nearly_black,
)
from scripts.dev.inspect_local_assistant_runtime import classify_runtime
from XBrainLab.llm.core.config import LLMConfig

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "dev-artifacts" / "chatpanel-local-workflow"
READY_SCREENSHOT = "chatpanel-workflow-ready.png"
JSON_ARTIFACT = "chatpanel-local-workflow-walkthrough.json"
MD_ARTIFACT = "chatpanel-local-workflow-walkthrough.md"
BASELINE_WINDOW_SIZE = QSize(1280, 800)
DEFAULT_PROMPTS = [
    (
        "Check what is ready in the current XBrainLab workflow. Use the state "
        "query tool if needed, then answer in one short sentence."
    ),
    ("Explain in one short sentence what EEG preprocessing prepares data for."),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for screenshots and transcript artifacts.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=420,
        help="Maximum time for the full multi-turn walkthrough.",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Optional approved local model id to prefer for this process.",
    )
    parser.add_argument(
        "--exercise-deactivation",
        action="store_true",
        help="Unload and re-enable Assistant before the two-turn workflow.",
    )
    parser.add_argument(
        "--isolated-settings-path",
        default="",
        help="Required temp settings path when exercising deactivation.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.exercise_deactivation:
        if not args.isolated_settings_path:
            parser.error("--exercise-deactivation requires --isolated-settings-path")
        _prepare_isolated_settings(
            Path(args.isolated_settings_path),
            model_id=args.model,
        )

    _force_offline_hf_runtime()
    config = _load_capture_config(args.model)
    runtime = classify_runtime(config)
    if runtime["classification"] not in {"gpu-ready", "cpu-fallback"}:
        payload = _blocked_payload(args, runtime)
        _write_artifacts(output_dir, payload)
        print(payload["status"])
        return 2

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    if args.model:
        app.setProperty("model_override", args.model)

    payload = run_workflow(
        app,
        output_dir,
        args.timeout_seconds,
        exercise_deactivation=bool(args.exercise_deactivation),
    )
    _write_artifacts(output_dir, payload)
    print(f"Wrote {output_dir / JSON_ARTIFACT}")
    print(f"Wrote {output_dir / MD_ARTIFACT}")
    return 0 if payload["status"] == "passed" else 1


def run_workflow(
    app: QApplication,
    output_dir: Path,
    timeout_seconds: int,
    *,
    exercise_deactivation: bool = False,
) -> dict[str, Any]:
    """Run a two-turn ChatPanel workflow and return the artifact payload."""
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.main_window import MainWindow

    _clear_saved_main_window_geometry()
    study = Study()
    window = MainWindow(study)
    _set_baseline_window_geometry(window)
    window.show()
    manager_ref: Any | None = None
    runtime_ref: Any | None = None
    cleanup_events: list[dict[str, Any]] = []

    started_at = time.monotonic()
    state: dict[str, Any] = {
        "status": "running",
        "failure_reason": "",
        "ready_screenshot": "",
        "turns": [],
        "visible_messages": [],
        "executed_tools": [],
        "send_button_text": "",
        "send_button_enabled": False,
        "input_enabled": False,
        "chat_processing": True,
        "controller_processing": True,
        "deactivation": {
            "requested": False,
            "terminal_ok": False,
            "controller_released": False,
            "conversation_cleared": False,
            "cache_retained": False,
            "reenabled": False,
        },
        "elapsed_seconds": 0.0,
    }

    def fail(reason: str) -> None:
        state["status"] = "failed"
        state["failure_reason"] = reason
        finish()

    def finish() -> None:
        state["elapsed_seconds"] = round(time.monotonic() - started_at, 3)
        manager = window.agent_manager
        if manager is not None:
            panel = manager.chat_panel
            controller = manager.agent_controller
            if panel is not None:
                state["visible_messages"] = [
                    message.__dict__ for message in collect_visible_messages(panel)
                ]
                state["send_button_text"] = panel.send_btn.text()
                state["send_button_enabled"] = panel.send_btn.isEnabled()
                state["input_enabled"] = panel.input_field.isEnabled()
            if controller is not None:
                state["executed_tools"] = collect_executed_tools(controller.metrics)
            state["chat_processing"] = bool(manager.chat_controller.is_processing)
            state["controller_processing"] = bool(
                controller and getattr(controller, "is_processing", False)
            )
        # MainWindow owns assistant teardown and keeps the event loop alive while
        # its bounded shutdown retries release Qt/model resources.
        window.close()

    def open_assistant() -> None:
        nonlocal manager_ref, runtime_ref
        window.init_agent()
        manager = window.agent_manager
        if manager is None:
            fail("Assistant manager was not initialized.")
            return
        manager_ref = manager
        runtime = manager.assistant_runtime
        runtime_ref = runtime
        runtime.cleanup_finished.connect(
            lambda ok, message: cleanup_events.append(
                {"ok": bool(ok), "message": str(message or "")}
            )
        )
        _disable_first_run_dialog_for_unattended_capture(window)
        window.ai_btn.click()
        QTimer.singleShot(250, wait_for_assistant_ready)

    def wait_for_assistant_ready() -> None:
        if time.monotonic() - started_at > timeout_seconds:
            fail(f"Assistant did not become ready within {timeout_seconds} seconds.")
            return
        manager = window.agent_manager
        if manager is None:
            fail("Assistant manager disappeared during startup.")
            return
        if not _assistant_is_ready(manager):
            QTimer.singleShot(250, wait_for_assistant_ready)
            return
        if exercise_deactivation and not state["deactivation"]["requested"]:
            begin_deactivation(manager)
            return
        capture_ready()

    def begin_deactivation(manager: Any) -> None:
        config = LLMConfig.load_from_file() or LLMConfig()
        cache_ready_before = config.has_local_model_cache(config.model_name)
        state["deactivation"]["requested"] = True

        def on_terminal(ok: bool, message: str) -> None:
            signal = manager.assistant_deactivation_finished
            with suppress(RuntimeError, TypeError):
                signal.disconnect(on_terminal)
            if not ok:
                fail(message or "Assistant deactivation did not complete.")
                return
            state["deactivation"].update(
                {
                    "terminal_ok": True,
                    "controller_released": manager.agent_controller is None,
                    "conversation_cleared": not manager.chat_controller.messages,
                    "cache_retained": (
                        cache_ready_before
                        and config.has_local_model_cache(config.model_name)
                    ),
                }
            )
            if not all(
                state["deactivation"][name]
                for name in (
                    "controller_released",
                    "conversation_cleared",
                    "cache_retained",
                )
            ):
                fail("Assistant deactivation did not preserve its product boundary.")
                return
            config.local_model_enabled = True
            config.local_runtime_notice_acknowledged = True
            if not config.save_to_file():
                fail("Isolated Assistant settings could not be re-enabled.")
                return
            activation = manager.assistant_runtime.activate(config)
            if not activation.available:
                fail(activation.message or "Assistant could not be re-enabled.")
                return
            QTimer.singleShot(250, wait_for_reenabled)

        manager.assistant_deactivation_finished.connect(on_terminal)
        admission = manager.request_assistant_deactivation(config)
        if not admission.accepted:
            with suppress(RuntimeError, TypeError):
                manager.assistant_deactivation_finished.disconnect(on_terminal)
            fail(admission.message or "Assistant deactivation was rejected.")

    def wait_for_reenabled() -> None:
        if time.monotonic() - started_at > timeout_seconds:
            fail(f"Assistant did not re-enable within {timeout_seconds} seconds.")
            return
        manager = window.agent_manager
        if manager is None or not _assistant_is_ready(manager):
            QTimer.singleShot(250, wait_for_reenabled)
            return
        state["deactivation"]["reenabled"] = True
        capture_ready()

    def capture_ready() -> None:
        manager = window.agent_manager
        if manager is None or manager.chat_panel is None:
            fail("Assistant was not available for the ready capture.")
            return
        ready_path = output_dir / READY_SCREENSHOT
        if _capture_current_window(window, ready_path) != 0:
            fail("Ready screenshot was blank or could not be saved.")
            return
        state["ready_screenshot"] = str(ready_path)
        send_prompt(0)

    def send_prompt(index: int) -> None:
        manager = window.agent_manager
        if manager is None:
            fail("Assistant manager disappeared during workflow.")
            return
        panel = manager.chat_panel
        if panel is None:
            fail("ChatPanel disappeared during workflow.")
            return
        if not _assistant_is_ready(manager):
            fail("Assistant controls were not ready before sending a prompt.")
            return
        before_messages = len(collect_visible_messages(panel))
        before_tools = len(
            collect_executed_tools(manager.agent_controller.metrics)
            if manager.agent_controller is not None
            else []
        )
        prompt = DEFAULT_PROMPTS[index]
        panel.input_field.setText(prompt)
        panel.send_btn.click()
        QTimer.singleShot(
            1000,
            lambda: wait_for_turn(index, prompt, before_messages, before_tools),
        )

    def wait_for_turn(
        index: int,
        prompt: str,
        before_messages: int,
        before_tools: int,
    ) -> None:
        if time.monotonic() - started_at > timeout_seconds:
            fail(f"Timed out after {timeout_seconds} seconds.")
            return

        manager = window.agent_manager
        if manager is None:
            fail("Assistant manager disappeared during workflow.")
            return
        panel = manager.chat_panel
        controller = manager.agent_controller
        if panel is None:
            fail("ChatPanel disappeared during workflow.")
            return

        app.processEvents()
        messages = collect_visible_messages(panel)
        assistant_texts = [
            message.text.strip()
            for message in messages[before_messages:]
            if message.sender == "assistant" and message.text.strip()
        ]
        has_user = any(
            message.sender == "user" and message.text.strip() == prompt
            for message in messages[before_messages:]
        )
        still_processing = manager.chat_controller.is_processing or bool(
            controller and getattr(controller, "is_processing", False)
        )

        if has_user and assistant_texts and not still_processing:
            if has_raw_debug_text(assistant_texts):
                fail("Visible assistant text exposed debug syntax.")
                return
            if _has_runtime_error_text(assistant_texts):
                fail("Visible assistant text reported a local runtime error.")
                return
            executed_tools = (
                collect_executed_tools(controller.metrics)
                if controller is not None
                else []
            )
            new_tools = executed_tools[before_tools:]
            contract_failure = _turn_contract_failure(
                index,
                assistant_texts[-1],
                new_tools,
            )
            if contract_failure is not None:
                fail(contract_failure)
                return
            QTimer.singleShot(
                350,
                lambda: capture_completed_turn(
                    index,
                    prompt,
                    assistant_texts[-1],
                    new_tools,
                ),
            )
            return

        QTimer.singleShot(
            1000,
            lambda: wait_for_turn(index, prompt, before_messages, before_tools),
        )

    def capture_completed_turn(
        index: int,
        prompt: str,
        assistant_text: str,
        new_tools: list[dict[str, Any]],
    ) -> None:
        window.update()
        window.repaint()
        app.processEvents()
        screenshot_name = f"chatpanel-workflow-turn-{index + 1}.png"
        screenshot_path = output_dir / screenshot_name
        if _capture_current_window(window, screenshot_path) != 0:
            fail("Turn screenshot was blank or could not be saved.")
            return
        if _has_unpainted_main_surface(screenshot_path):
            fail("Turn screenshot contained a large unpainted main-window region.")
            return
        state["turns"].append(
            {
                "index": index + 1,
                "prompt": prompt,
                "assistant_text": assistant_text,
                "new_tool_count": len(new_tools),
                "screenshot": str(screenshot_path),
            }
        )
        if index + 1 < len(DEFAULT_PROMPTS):
            QTimer.singleShot(500, lambda: send_prompt(index + 1))
        else:
            state["status"] = "passed"
            finish()

    QTimer.singleShot(1500, open_assistant)
    app.exec()

    state["elapsed_seconds"] = round(time.monotonic() - started_at, 3)
    post_close = _capture_post_close_evidence(
        manager=manager_ref,
        runtime=runtime_ref,
        window=window,
        cleanup_events=cleanup_events,
    )
    if state["status"] == "passed" and not post_close["passed"]:
        state["status"] = "failed"
        state["failure_reason"] = _post_close_failure_reason(post_close)

    config = LLMConfig.load_from_file() or LLMConfig()
    runtime = classify_runtime(config)
    state["deactivation"]["config_final_enabled"] = bool(config.local_model_enabled)
    if (
        exercise_deactivation
        and state["status"] == "passed"
        and not all(
            state["deactivation"].get(name) is True
            for name in (
                "terminal_ok",
                "controller_released",
                "conversation_cleared",
                "cache_retained",
                "reenabled",
                "config_final_enabled",
            )
        )
    ):
        state["status"] = "failed"
        state["failure_reason"] = (
            "Assistant deactivation/re-enable evidence was incomplete."
        )
    return {
        "status": state["status"],
        "failure_reason": state["failure_reason"],
        "prompts": DEFAULT_PROMPTS,
        "runtime": _runtime_summary(runtime),
        "capture_first_run_policy": (
            "isolated_temp_settings_deactivation"
            if exercise_deactivation
            else "bypassed_without_persisting_settings"
        ),
        "hf_offline": {
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
            "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
        },
        "screenshots": {"ready": state["ready_screenshot"]},
        "turns": state["turns"],
        "visible_messages": state["visible_messages"],
        "executed_tools": state["executed_tools"],
        "ui_state": {
            "send_button_text": state["send_button_text"],
            "send_button_enabled": state["send_button_enabled"],
            "input_enabled": state["input_enabled"],
            "chat_processing": state["chat_processing"],
            "controller_processing": state["controller_processing"],
        },
        "post_close": post_close,
        "deactivation": state["deactivation"],
        "elapsed_seconds": state["elapsed_seconds"],
    }


def _prepare_isolated_settings(path: Path, *, model_id: str) -> None:
    """Bind mutable capture settings to an explicit OS temp path."""
    resolved = path.expanduser().resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    if resolved == temp_root or temp_root not in resolved.parents:
        raise ValueError(
            "Isolated settings must be a file below the OS temp directory."
        )
    LLMConfig._default_settings_path = staticmethod(  # type: ignore[method-assign]
        lambda: str(resolved)
    )
    config = LLMConfig(model_name=model_id or LLMConfig.default_local_model_id())
    config.local_model_enabled = True
    config.local_runtime_notice_acknowledged = True
    config.apply_runtime_selection(
        "local",
        model_id=config.model_name,
        ui_active_mode="local",
    )
    if not config.save_to_file(str(resolved)):
        raise RuntimeError("Could not create isolated Assistant settings.")


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a compact workflow walkthrough summary."""
    lines = [
        "# ChatPanel Local Workflow Walkthrough",
        "",
        f"- status: `{payload['status']}`",
        f"- failure reason: {payload.get('failure_reason') or 'none'}",
        f"- runtime classification: `{payload['runtime']['classification']}`",
        f"- model: `{payload['runtime']['model_id']}`",
        f"- cache usage: `{payload['runtime']['cache_usage']}`",
        "- first-run policy: "
        f"`{payload.get('capture_first_run_policy', 'not recorded')}`",
        f"- HF offline: `{payload['hf_offline']['HF_HUB_OFFLINE']}`",
        f"- Transformers offline: `{payload['hf_offline']['TRANSFORMERS_OFFLINE']}`",
        f"- ready screenshot: `{payload['screenshots']['ready']}`",
        f"- elapsed seconds: `{payload['elapsed_seconds']}`",
        f"- deactivation/re-enable: `{payload.get('deactivation', {})}`",
        "",
        "## Turns",
        "",
    ]
    for turn in payload["turns"]:
        lines.extend(
            [
                f"### Turn {turn['index']}",
                "",
                f"- prompt: {turn['prompt']}",
                f"- assistant: {turn['assistant_text']}",
                f"- new tool count: `{turn['new_tool_count']}`",
                f"- screenshot: `{turn['screenshot']}`",
                "",
            ]
        )
    lines.extend(["## Executed Tools", ""])
    tools = payload.get("executed_tools", [])
    if tools:
        for tool in tools:
            status = "ok" if tool.get("success") else "failed"
            lines.append(
                f"- `{tool.get('name', '')}`: `{status}` "
                f"({tool.get('duration_ms', 0)} ms)"
            )
    else:
        lines.append("- none")
    ui = payload["ui_state"]
    post_close = payload.get("post_close", {})
    lines.extend(
        [
            "",
            "## UI State",
            "",
            f"- send button: `{ui['send_button_text']}`",
            f"- send button enabled: `{ui['send_button_enabled']}`",
            f"- input enabled: `{ui['input_enabled']}`",
            f"- chat processing: `{ui['chat_processing']}`",
            f"- controller processing: `{ui['controller_processing']}`",
            "",
            "## Post-close Lifecycle",
            "",
            f"- passed: `{post_close.get('passed', False)}`",
            f"- runtime state: `{post_close.get('runtime_state', 'not reached')}`",
            "- dispatcher state: "
            f"`{post_close.get('dispatcher_state', 'not reached')}`",
            f"- controller released: `{post_close.get('controller_released', False)}`",
            "- cleanup signal observed: "
            f"`{post_close.get('cleanup_signal_observed', False)}`",
            "- registered generation threads: "
            f"`{post_close.get('registered_generation_thread_count', 0)}`",
            "- running generation threads: "
            f"`{post_close.get('running_generation_thread_count', 0)}`",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _has_runtime_error_text(texts: list[str]) -> bool:
    """Return whether the visible answer is an error, not a workflow response."""
    markers = (
        "generation timed out",
        "local llm is too slow",
        "assistant returned an empty response",
        "error:",
        "traceback",
    )
    return any(marker in text.lower() for marker in markers for text in texts)


def _blocked_payload(
    args: argparse.Namespace,
    runtime: dict[str, object],
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "failure_reason": str(runtime.get("message") or "Local runtime not ready."),
        "prompts": DEFAULT_PROMPTS,
        "runtime": _runtime_summary(runtime),
        "capture_first_run_policy": "not_reached",
        "hf_offline": {
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
            "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
        },
        "screenshots": {"ready": ""},
        "turns": [],
        "visible_messages": [],
        "executed_tools": [],
        "ui_state": {
            "send_button_text": "",
            "send_button_enabled": False,
            "input_enabled": False,
            "chat_processing": False,
            "controller_processing": False,
        },
        "post_close": {
            "passed": False,
            "not_reached": True,
            "checks": {},
        },
        "elapsed_seconds": 0.0,
    }


def _runtime_summary(runtime: dict[str, object]) -> dict[str, object]:
    return {
        "classification": runtime.get("classification"),
        "model_id": runtime.get("current_model_id"),
        "message": runtime.get("message"),
        "cache_dir": runtime.get("cache_dir"),
        "cache_usage": runtime.get("cache_usage"),
        "cache_usage_bytes": runtime.get("cache_usage_bytes"),
        "has_local_cache": runtime.get("has_local_cache"),
        "gpu_fallback_reason": runtime.get("gpu_fallback_reason"),
    }


def _write_artifacts(output_dir: Path, payload: dict[str, Any]) -> None:
    (output_dir / JSON_ARTIFACT).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / MD_ARTIFACT).write_text(
        render_markdown(payload),
        encoding="utf-8",
    )


def _capture_current_window(window: Any, output_path: Path) -> int:
    window.update()
    window.repaint()
    QApplication.processEvents()
    pixmap = window.grab()
    if pixmap.isNull():
        print("Failed to grab the main window pixmap.", file=sys.stderr)
        return 3
    if not pixmap.save(str(output_path)):
        print("Failed to save the grabbed main window pixmap.", file=sys.stderr)
        return 4
    if is_nearly_black(output_path):
        print(
            f"Captured screenshot is nearly all black: {output_path.name}",
            file=sys.stderr,
        )
        return 2
    print(f"Saved screenshot to {output_path}")
    return 0


def _has_unpainted_main_surface(path: Path) -> bool:
    """Detect the X11 capture failure that paints most of the main area black."""
    with Image.open(path).convert("RGB") as image:
        left_surface = image.crop((0, 0, max(1, int(image.width * 0.7)), image.height))
        histogram = left_surface.convert("L").histogram()
        pixel_count = left_surface.width * left_surface.height
    if pixel_count == 0:
        return True
    return sum(histogram[:8]) / pixel_count > 0.9


def _load_capture_config(model_id: str) -> LLMConfig:
    config = LLMConfig.load_from_file() or LLMConfig()
    if model_id:
        config.apply_runtime_selection(
            "local",
            model_id=model_id,
            ui_active_mode="local",
        )
    return config


def _clear_saved_main_window_geometry() -> None:
    settings = QSettings("XBrainLab", "XBrainLab")
    settings.remove("main_window/geometry")
    settings.sync()


def _set_baseline_window_geometry(window: Any) -> None:
    screen = window.screen() or QApplication.primaryScreen()
    if screen is not None:
        window.move(screen.availableGeometry().topLeft())
    else:
        window.move(QPoint(0, 0))
    window.resize(BASELINE_WINDOW_SIZE)


def _disable_first_run_dialog_for_unattended_capture(window: Any) -> None:
    """Bypass only the modal consent prompt without persisting user settings."""
    manager = getattr(window, "agent_manager", None)
    if manager is None:
        raise RuntimeError("Assistant manager must be initialized before capture setup")
    runtime = manager._assistant_runtime
    runtime.needs_first_run = lambda _config: False


def _assistant_is_ready(manager: Any) -> bool:
    panel = getattr(manager, "chat_panel", None)
    dock = getattr(manager, "chat_dock", None)
    chat_controller = getattr(manager, "chat_controller", None)
    controller = getattr(manager, "agent_controller", None)
    return bool(
        panel is not None
        and dock is not None
        and dock.isVisible()
        and panel.input_field.isEnabled()
        and not bool(
            chat_controller and getattr(chat_controller, "is_processing", False)
        )
        and not bool(controller and getattr(controller, "is_processing", False))
    )


def _capture_post_close_evidence(
    *,
    manager: Any | None,
    runtime: Any | None,
    window: Any,
    cleanup_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Capture terminal ownership facts after the main Qt event loop exits."""
    from XBrainLab.llm.agent.worker import ACTIVE_GENERATION_THREADS

    registered_threads = list(ACTIVE_GENERATION_THREADS)
    running_threads = 0
    for thread in registered_threads:
        try:
            running_threads += int(bool(thread.isRunning()))
        except RuntimeError:
            running_threads += 1

    runtime_state = _enum_value(getattr(runtime, "state", None))
    dispatcher = getattr(runtime, "dispatcher", None)
    dispatcher_state = _enum_value(getattr(dispatcher, "state", None))
    controller_released = bool(
        manager is not None and getattr(manager, "agent_controller", None) is None
    )
    try:
        window_visible = bool(window.isVisible())
    except RuntimeError:
        window_visible = False

    return _build_post_close_evidence(
        cleanup_events=cleanup_events,
        runtime_state=runtime_state,
        dispatcher_state=dispatcher_state,
        controller_released=controller_released,
        window_visible=window_visible,
        registered_generation_thread_count=len(registered_threads),
        running_generation_thread_count=running_threads,
    )


def _build_post_close_evidence(
    *,
    cleanup_events: list[dict[str, Any]],
    runtime_state: str,
    dispatcher_state: str,
    controller_released: bool,
    window_visible: bool,
    registered_generation_thread_count: int,
    running_generation_thread_count: int,
) -> dict[str, Any]:
    """Build the machine-checkable assistant teardown contract."""
    cleanup_result = cleanup_events[-1] if cleanup_events else {}
    cleanup_succeeded = bool(
        cleanup_result.get("ok") is True
        or (not cleanup_events and runtime_state == "closed")
    )
    checks = {
        "window_closed": not window_visible,
        "runtime_cleanup_succeeded": cleanup_succeeded,
        "runtime_closed": runtime_state == "closed",
        "dispatcher_closed": dispatcher_state == "closed",
        "controller_released": controller_released,
        "no_registered_generation_threads": registered_generation_thread_count == 0,
        "no_running_generation_threads": running_generation_thread_count == 0,
    }
    return {
        "cleanup_signal_observed": bool(cleanup_events),
        "cleanup_events": cleanup_events,
        "runtime_state": runtime_state,
        "dispatcher_state": dispatcher_state,
        "controller_released": controller_released,
        "window_visible": window_visible,
        "registered_generation_thread_count": registered_generation_thread_count,
        "running_generation_thread_count": running_generation_thread_count,
        "checks": checks,
        "passed": all(checks.values()),
    }


def _post_close_failure_reason(evidence: dict[str, Any]) -> str:
    failures = [
        name
        for name, passed in evidence.get("checks", {}).items()
        if passed is not True
    ]
    detail = ", ".join(failures) if failures else "unknown teardown state"
    return f"Assistant teardown contract failed after window close: {detail}."


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _turn_contract_failure(
    index: int,
    assistant_text: str,
    new_tools: list[dict[str, Any]],
) -> str | None:
    if index == 0:
        state_calls = [tool for tool in new_tools if tool.get("name") == "query_state"]
        if not state_calls:
            return (
                "Turn 1 did not execute query_state for a workflow readiness request."
            )
        if len(state_calls) != 1:
            return "Turn 1 must execute query_state exactly once."
        if len(new_tools) != 1:
            return "Turn 1 must not call other tools for a state-only request."
        if not any(tool.get("success") is True for tool in state_calls):
            return "Turn 1 query_state execution did not succeed."
        return None

    if index == 1:
        if new_tools:
            return "Turn 2 explanatory question must not call a workflow tool."
        normalized = assistant_text.lower()
        if "no workflow action is needed" in normalized:
            return "Turn 2 returned the generic refusal instead of an EEG explanation."
        if any(
            marker in normalized
            for marker in (
                "workflow status",
                "state query tool",
                "current xbrainlab workflow",
            )
        ):
            return "Turn 2 repeated the previous workflow request instead of answering."
        sentence_endings = re.findall(r"[.!?](?=\s|$)", assistant_text.strip())
        if len(sentence_endings) > 1 or "\n\n" in assistant_text:
            return "Turn 2 did not follow the requested one short sentence format."
        explanatory_terms = (
            "eeg",
            "signal",
            "data",
            "noise",
            "artifact",
            "epoch",
            "training",
            "analysis",
            "filter",
            "clean",
        )
        if not any(term in normalized for term in explanatory_terms):
            return "Turn 2 response did not contain a recognizable EEG explanation."
    return None


def _force_offline_hf_runtime() -> None:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


if __name__ == "__main__":
    raise SystemExit(main())
