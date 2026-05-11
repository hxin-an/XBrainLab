#!/usr/bin/env python3
"""Capture a true local-model multi-turn ChatPanel workflow artifact."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

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
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ui" / "chatpanel-local-workflow"
READY_SCREENSHOT = "chatpanel-workflow-ready.png"
JSON_ARTIFACT = "chatpanel-local-workflow-walkthrough.json"
MD_ARTIFACT = "chatpanel-local-workflow-walkthrough.md"
BASELINE_WINDOW_SIZE = QSize(1280, 800)
DEFAULT_PROMPTS = [
    (
        "Check what is ready in the current XBrainLab workflow. Use the state "
        "query tool if needed, then answer in one short sentence."
    ),
    (
        "In one short sentence, explain what EEG preprocessing prepares for. "
        "Do not use tools."
    ),
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
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

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

    payload = run_workflow(app, output_dir, args.timeout_seconds)
    _write_artifacts(output_dir, payload)
    print(f"Wrote {output_dir / JSON_ARTIFACT}")
    print(f"Wrote {output_dir / MD_ARTIFACT}")
    return 0 if payload["status"] == "passed" else 1


def run_workflow(
    app: QApplication,
    output_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run a two-turn ChatPanel workflow and return the artifact payload."""
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.main_window import MainWindow

    _clear_saved_main_window_geometry()
    study = Study()
    window = MainWindow(study)
    _set_baseline_window_geometry(window)
    window.show()

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
        "elapsed_seconds": 0.0,
    }

    def fail(reason: str) -> None:
        state["status"] = "failed"
        state["failure_reason"] = reason
        finish()

    def finish() -> None:
        state["elapsed_seconds"] = round(time.monotonic() - started_at, 3)
        manager = window.agent_manager
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
        if controller is not None:
            controller.close()
        window.close()
        app.quit()

    def open_assistant() -> None:
        window.ai_btn.click()
        QTimer.singleShot(2500, capture_ready)

    def capture_ready() -> None:
        manager = window.agent_manager
        panel = manager.chat_panel
        if panel is None or not manager.chat_dock or not manager.chat_dock.isVisible():
            fail("Assistant dock did not open.")
            return
        ready_path = output_dir / READY_SCREENSHOT
        if _capture_current_window(window, ready_path) != 0:
            fail("Ready screenshot was blank or could not be saved.")
            return
        state["ready_screenshot"] = str(ready_path)
        send_prompt(0)

    def send_prompt(index: int) -> None:
        manager = window.agent_manager
        panel = manager.chat_panel
        if panel is None:
            fail("ChatPanel disappeared during workflow.")
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
            screenshot_name = f"chatpanel-workflow-turn-{index + 1}.png"
            screenshot_path = output_dir / screenshot_name
            if _capture_current_window(window, screenshot_path) != 0:
                fail("Turn screenshot was blank or could not be saved.")
                return
            executed_tools = (
                collect_executed_tools(controller.metrics)
                if controller is not None
                else []
            )
            state["turns"].append(
                {
                    "index": index + 1,
                    "prompt": prompt,
                    "assistant_text": assistant_texts[-1],
                    "new_tool_count": max(0, len(executed_tools) - before_tools),
                    "screenshot": str(screenshot_path),
                }
            )
            if index + 1 < len(DEFAULT_PROMPTS):
                QTimer.singleShot(500, lambda: send_prompt(index + 1))
            else:
                state["status"] = "passed"
                finish()
            return

        QTimer.singleShot(
            1000,
            lambda: wait_for_turn(index, prompt, before_messages, before_tools),
        )

    QTimer.singleShot(1500, open_assistant)
    app.exec()

    config = LLMConfig.load_from_file() or LLMConfig()
    runtime = classify_runtime(config)
    return {
        "status": state["status"],
        "failure_reason": state["failure_reason"],
        "prompts": DEFAULT_PROMPTS,
        "runtime": _runtime_summary(runtime),
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
        "elapsed_seconds": state["elapsed_seconds"],
    }


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
        f"- HF offline: `{payload['hf_offline']['HF_HUB_OFFLINE']}`",
        f"- Transformers offline: `{payload['hf_offline']['TRANSFORMERS_OFFLINE']}`",
        f"- ready screenshot: `{payload['screenshots']['ready']}`",
        f"- elapsed seconds: `{payload['elapsed_seconds']}`",
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


def _force_offline_hf_runtime() -> None:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


if __name__ == "__main__":
    raise SystemExit(main())
