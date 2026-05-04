#!/usr/bin/env python3
"""Capture a true local-model ChatPanel walkthrough artifact.

The walkthrough uses the real MainWindow, ChatPanel, AgentManager,
LLMController, AgentWorker, and LLMEngine local backend. It intentionally runs
Hugging Face in offline mode so this check cannot download model files.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image
from PyQt6.QtCore import QPoint, QSettings, QSize, QTimer
from PyQt6.QtWidgets import QApplication

from scripts.dev.inspect_local_assistant_runtime import classify_runtime
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.ui.chat.message_bubble import MessageBubble

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ui"
READY_SCREENSHOT = "chatpanel-local-ready.png"
RESPONSE_SCREENSHOT = "chatpanel-local-response.png"
JSON_ARTIFACT = "chatpanel-local-walkthrough.json"
MD_ARTIFACT = "chatpanel-local-walkthrough.md"
BASELINE_WINDOW_SIZE = QSize(1280, 800)
DEFAULT_PROMPT = (
    "In one short user-facing sentence, explain what EEG preprocessing does. "
    "Do not use tools."
)


@dataclass(frozen=True)
class VisibleMessage:
    """A user-visible chat bubble captured from ChatPanel."""

    sender: str
    text: str


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for screenshots and transcript artifacts.",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="Prompt sent through the ChatPanel composer.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=300,
        help="Maximum time to wait for local model load and response.",
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

    payload = run_walkthrough(app, output_dir, args.prompt, args.timeout_seconds)
    _write_artifacts(output_dir, payload)
    print(f"Wrote {output_dir / JSON_ARTIFACT}")
    print(f"Wrote {output_dir / MD_ARTIFACT}")
    return 0 if payload["status"] == "passed" else 1


def run_walkthrough(
    app: QApplication,
    output_dir: Path,
    prompt: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run the UI walkthrough and return the artifact payload."""
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
        "response_screenshot": "",
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
                asdict(message) for message in collect_visible_messages(panel)
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
        if not state.get("response_screenshot") and panel is not None:
            response_path = output_dir / RESPONSE_SCREENSHOT
            if _capture_current_window(window, response_path) == 0:
                state["response_screenshot"] = str(response_path)
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
        panel.input_field.setText(prompt)
        panel.send_btn.click()
        QTimer.singleShot(1000, wait_for_response)

    def wait_for_response() -> None:
        if time.monotonic() - started_at > timeout_seconds:
            fail(f"Timed out after {timeout_seconds} seconds.")
            return

        manager = window.agent_manager
        panel = manager.chat_panel
        controller = manager.agent_controller
        if panel is None:
            fail("ChatPanel disappeared during walkthrough.")
            return

        app.processEvents()
        messages = collect_visible_messages(panel)
        has_user = any(
            message.sender == "user" and prompt in message.text for message in messages
        )
        assistant_texts = [
            message.text.strip()
            for message in messages
            if message.sender == "assistant" and message.text.strip()
        ]
        still_processing = manager.chat_controller.is_processing or bool(
            controller and getattr(controller, "is_processing", False)
        )

        if has_user and assistant_texts and not still_processing:
            state["status"] = (
                "failed" if has_raw_debug_text(assistant_texts) else "passed"
            )
            if state["status"] == "failed":
                state["failure_reason"] = "Visible assistant text exposed debug syntax."
            response_path = output_dir / RESPONSE_SCREENSHOT
            if _capture_current_window(window, response_path) != 0:
                fail("Response screenshot was blank or could not be saved.")
                return
            state["response_screenshot"] = str(response_path)
            finish()
            return

        QTimer.singleShot(1000, wait_for_response)

    QTimer.singleShot(1500, open_assistant)
    app.exec()

    config = LLMConfig.load_from_file() or LLMConfig()
    runtime = classify_runtime(config)
    payload: dict[str, Any] = {
        "status": state["status"],
        "failure_reason": state["failure_reason"],
        "prompt": prompt,
        "runtime": _runtime_summary(runtime),
        "hf_offline": {
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
            "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
        },
        "screenshots": {
            "ready": state["ready_screenshot"],
            "response": state["response_screenshot"],
        },
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
    return payload


def collect_executed_tools(metrics: Any) -> list[dict[str, Any]]:
    """Collect completed tool executions from the controller metrics tracker."""
    tools: list[dict[str, Any]] = []
    for turn in getattr(metrics, "_completed_turns", []) or []:
        for execution in getattr(turn, "tool_executions", []) or []:
            tools.append(
                {
                    "name": str(getattr(execution, "name", "")),
                    "success": bool(getattr(execution, "success", False)),
                    "duration_ms": round(
                        float(getattr(execution, "duration_ms", 0.0)),
                        3,
                    ),
                    "error": getattr(execution, "error", None),
                }
            )
    return tools


def collect_visible_messages(panel: Any) -> list[VisibleMessage]:
    """Collect visible chat bubbles in display order."""
    messages: list[VisibleMessage] = []
    layout = getattr(panel, "chat_layout", None)
    if layout is None:
        return messages

    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget() if item is not None else None
        if not isinstance(widget, MessageBubble) or not widget.isVisible():
            continue
        text = widget.get_text().strip()
        if not text:
            continue
        messages.append(
            VisibleMessage(
                sender="user" if widget.is_user else "assistant",
                text=text,
            )
        )
    return messages


def has_raw_debug_text(texts: list[str]) -> bool:
    """Return whether user-visible assistant text leaks internal syntax."""
    markers = (
        "```json",
        "tool_name",
        "tool call",
        "traceback",
        "ApplicationService",
        "BackendFacade",
    )
    for text in texts:
        lowered = text.lower()
        if any(marker.lower() in lowered for marker in markers):
            return True
    return False


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a compact walkthrough summary."""
    lines = [
        "# ChatPanel Local Model Walkthrough",
        "",
        f"- status: `{payload['status']}`",
        f"- failure reason: {payload.get('failure_reason') or 'none'}",
        f"- prompt: {payload['prompt']}",
        f"- runtime classification: `{payload['runtime']['classification']}`",
        f"- model: `{payload['runtime']['model_id']}`",
        f"- cache usage: `{payload['runtime']['cache_usage']}`",
        f"- HF offline: `{payload['hf_offline']['HF_HUB_OFFLINE']}`",
        f"- Transformers offline: `{payload['hf_offline']['TRANSFORMERS_OFFLINE']}`",
        f"- ready screenshot: `{payload['screenshots']['ready']}`",
        f"- response screenshot: `{payload['screenshots']['response']}`",
        f"- elapsed seconds: `{payload['elapsed_seconds']}`",
        "",
        "## Visible Transcript",
        "",
    ]
    for message in payload["visible_messages"]:
        lines.extend(
            [
                f"### {message['sender']}",
                "",
                message["text"],
                "",
            ]
        )
    tools = payload.get("executed_tools", [])
    lines.extend(["## Executed Tools", ""])
    if tools:
        for tool in tools:
            status = "ok" if tool.get("success") else "failed"
            line = (
                f"- `{tool.get('name', '')}`: `{status}` "
                f"({tool.get('duration_ms', 0)} ms)"
            )
            if tool.get("error"):
                line += f" - {tool['error']}"
            lines.append(line)
    else:
        lines.append("- none")
    lines.append("")
    ui = payload["ui_state"]
    lines.extend(
        [
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


def is_nearly_black(path: Path) -> bool:
    """Return True when the captured image contains almost no visible content."""
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        histogram = rgb.histogram()

    bright_pixels = 0
    total_pixels = sum(histogram[:256])
    for value in range(16, 256):
        bright_pixels += histogram[value]
        bright_pixels += histogram[256 + value]
        bright_pixels += histogram[512 + value]

    return total_pixels == 0 or bright_pixels < total_pixels * 0.01


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


def _write_artifacts(output_dir: Path, payload: dict[str, Any]) -> None:
    json_path = output_dir / JSON_ARTIFACT
    md_path = output_dir / MD_ARTIFACT
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    md_path.write_text(render_markdown(payload), encoding="utf-8")


def _blocked_payload(
    args: argparse.Namespace, runtime: dict[str, object]
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "failure_reason": str(runtime.get("message") or "Local runtime not ready."),
        "prompt": args.prompt,
        "runtime": _runtime_summary(runtime),
        "hf_offline": {
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
            "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
        },
        "screenshots": {"ready": "", "response": ""},
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


def _load_capture_config(model_id: str) -> LLMConfig:
    config = LLMConfig.load_from_file() or LLMConfig()
    if model_id:
        config.apply_runtime_selection(
            "local", model_id=model_id, ui_active_mode="local"
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
