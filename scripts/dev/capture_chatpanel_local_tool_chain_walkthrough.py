#!/usr/bin/env python3
"""Capture a true local-model ChatPanel Data Interpretation tool chain.

The walkthrough opens the real MainWindow and ChatPanel, forces Hugging Face
offline mode, creates a deterministic synthetic FIF file, and asks the local
assistant to run scan -> preview -> validate through the visible composer.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import mne
import numpy as np
from PyQt6.QtCore import QPoint, QSettings, QSize, QTimer
from PyQt6.QtWidgets import QApplication

from scripts.dev.capture_chatpanel_local_walkthrough import (
    collect_executed_tools,
    collect_visible_messages,
    has_raw_debug_text,
    is_nearly_black,
)
from scripts.dev.capture_chatpanel_local_workflow_walkthrough import (
    _has_runtime_error_text,
)
from scripts.dev.inspect_local_assistant_runtime import classify_runtime
from XBrainLab.llm.core.config import LLMConfig

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ui" / "chatpanel-local-tool-chain"
SOURCE_DIR = Path(tempfile.gettempdir()) / "xbrainlab_chatpanel_tool_chain"
SOURCE_PATH = SOURCE_DIR / "chatpanel_chain_raw.fif"
READY_SCREENSHOT = "chatpanel-tool-chain-ready.png"
JSON_ARTIFACT = "chatpanel-local-tool-chain-walkthrough.json"
MD_ARTIFACT = "chatpanel-local-tool-chain-walkthrough.md"
BASELINE_WINDOW_SIZE = QSize(1280, 800)
EXPECTED_TOOLS = [
    "scan_source",
    "preview_interpretation",
    "validate_interpretation",
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
        default=520,
        help="Maximum time for the full tool-chain walkthrough.",
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

    source_path = write_synthetic_raw_fif()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    if args.model:
        app.setProperty("model_override", args.model)

    payload = run_tool_chain(
        app,
        output_dir,
        source_path,
        args.timeout_seconds,
    )
    _write_artifacts(output_dir, payload)
    print(f"Wrote {output_dir / JSON_ARTIFACT}")
    print(f"Wrote {output_dir / MD_ARTIFACT}")
    return 0 if payload["status"] == "passed" else 1


def write_synthetic_raw_fif() -> Path:
    """Write a deterministic synthetic EEG source for the ChatPanel chain."""
    if SOURCE_DIR.exists():
        shutil.rmtree(SOURCE_DIR)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    sfreq = 128
    ch_names = ["C3", "C4", "Cz", "Pz"]
    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    data = np.random.default_rng(41).normal(size=(len(ch_names), sfreq * 6))
    raw = mne.io.RawArray(data, info)
    events = np.array(
        [
            [128, 0, 1],
            [256, 0, 2],
            [384, 0, 1],
            [512, 0, 2],
            [640, 0, 1],
            [704, 0, 2],
        ],
    )
    raw.set_annotations(
        mne.annotations_from_events(
            events,
            sfreq=sfreq,
            event_desc={1: "left", 2: "right"},
        ),
    )
    raw.save(SOURCE_PATH, overwrite=True)
    return SOURCE_PATH


def build_prompts(source_path: Path) -> list[str]:
    """Return user-facing prompts for the local assistant tool chain."""
    return [
        (
            "Scan this EEG source with the Data Interpretation scan step: "
            f"{source_path}. Reply with one short result sentence."
        ),
        (
            "Preview the latest Data Interpretation candidate. Reply with one "
            "short result sentence."
        ),
        (
            "Validate the latest Data Interpretation candidate. Reply with one "
            "short result sentence and stop."
        ),
    ]


def run_tool_chain(
    app: QApplication,
    output_dir: Path,
    source_path: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run scan -> preview -> validate through the visible ChatPanel."""
    from XBrainLab.backend.facade import BackendFacade
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.main_window import MainWindow

    prompts = build_prompts(source_path)
    _clear_saved_main_window_geometry()
    study = Study()
    window = MainWindow(study)
    _set_baseline_window_geometry(window)
    window.show()

    started_at = time.monotonic()
    state: dict[str, Any] = {
        "status": "running",
        "failure_reason": "",
        "source_path": str(source_path),
        "ready_screenshot": "",
        "turns": [],
        "visible_messages": [],
        "executed_tools": [],
        "expected_tools": list(EXPECTED_TOOLS),
        "final_interpretation_state": {},
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
            controller.close()
        try:
            app_state = BackendFacade(study).get_state().to_dict()
            interpretation = app_state.get("interpretation")
            state["final_interpretation_state"] = (
                dict(interpretation) if isinstance(interpretation, dict) else {}
            )
        except Exception:
            state["final_interpretation_state"] = {}
        state["chat_processing"] = bool(manager.chat_controller.is_processing)
        state["controller_processing"] = bool(
            controller and getattr(controller, "is_processing", False)
        )
        if state["status"] == "running":
            ok, reason = tool_chain_status(
                state["executed_tools"],
                state["expected_tools"],
            )
            state["status"] = "passed" if ok else "failed"
            state["failure_reason"] = "" if ok else reason
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
            fail("ChatPanel disappeared during tool-chain walkthrough.")
            return
        before_messages = len(collect_visible_messages(panel))
        before_tools = len(
            collect_executed_tools(manager.agent_controller.metrics)
            if manager.agent_controller is not None
            else []
        )
        prompt = prompts[index]
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
            fail("ChatPanel disappeared during tool-chain walkthrough.")
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
            expected_tool = EXPECTED_TOOLS[index]
            if not _turn_has_expected_tool(new_tools, expected_tool):
                fail(
                    f"Turn {index + 1} did not execute expected tool "
                    f"{expected_tool}; new tools: {[tool.get('name') for tool in new_tools]}."
                )
                return
            screenshot_name = f"chatpanel-tool-chain-turn-{index + 1}.png"
            screenshot_path = output_dir / screenshot_name
            if _capture_current_window(window, screenshot_path) != 0:
                fail("Turn screenshot was blank or could not be saved.")
                return
            state["turns"].append(
                {
                    "index": index + 1,
                    "prompt": prompt,
                    "expected_tool": expected_tool,
                    "assistant_text": assistant_texts[-1],
                    "new_tools": [dict(tool) for tool in new_tools],
                    "screenshot": str(screenshot_path),
                },
            )
            if index + 1 < len(prompts):
                QTimer.singleShot(500, lambda: send_prompt(index + 1))
            else:
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
        "source_path": state["source_path"],
        "prompts": prompts,
        "expected_tools": state["expected_tools"],
        "runtime": _runtime_summary(runtime),
        "hf_offline": {
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
            "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
        },
        "screenshots": {"ready": state["ready_screenshot"]},
        "turns": state["turns"],
        "visible_messages": state["visible_messages"],
        "executed_tools": state["executed_tools"],
        "final_interpretation_state": state["final_interpretation_state"],
        "ui_state": {
            "send_button_text": state["send_button_text"],
            "send_button_enabled": state["send_button_enabled"],
            "input_enabled": state["input_enabled"],
            "chat_processing": state["chat_processing"],
            "controller_processing": state["controller_processing"],
        },
        "elapsed_seconds": state["elapsed_seconds"],
    }


def tool_chain_status(
    executed_tools: list[dict[str, Any]],
    expected_tools: list[str],
) -> tuple[bool, str]:
    """Return whether the expected successful tool sequence appears in order."""
    cursor = 0
    failed: list[str] = []
    for tool in executed_tools:
        name = str(tool.get("name") or "")
        if not bool(tool.get("success")):
            failed.append(name or "<unknown>")
            continue
        if cursor < len(expected_tools) and name == expected_tools[cursor]:
            cursor += 1
    if failed:
        return False, f"Tool execution failed: {', '.join(failed)}."
    if cursor != len(expected_tools):
        seen = [str(tool.get("name") or "") for tool in executed_tools]
        return False, f"Expected tool sequence {expected_tools}, saw {seen}."
    return True, ""


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a compact tool-chain walkthrough summary."""
    lines = [
        "# ChatPanel Local Tool-Chain Walkthrough",
        "",
        f"- status: `{payload['status']}`",
        f"- failure reason: {payload.get('failure_reason') or 'none'}",
        f"- source path: `{payload.get('source_path', '')}`",
        f"- runtime classification: `{payload['runtime']['classification']}`",
        f"- model: `{payload['runtime']['model_id']}`",
        f"- cache usage: `{payload['runtime']['cache_usage']}`",
        f"- HF offline: `{payload['hf_offline']['HF_HUB_OFFLINE']}`",
        f"- Transformers offline: `{payload['hf_offline']['TRANSFORMERS_OFFLINE']}`",
        f"- ready screenshot: `{payload['screenshots']['ready']}`",
        f"- expected tools: `{', '.join(payload.get('expected_tools', []))}`",
        f"- elapsed seconds: `{payload['elapsed_seconds']}`",
        "",
        "## Turns",
        "",
    ]
    for turn in payload["turns"]:
        tool_names = ", ".join(
            str(tool.get("name", "")) for tool in turn.get("new_tools", [])
        )
        lines.extend(
            [
                f"### Turn {turn['index']}",
                "",
                f"- prompt: {turn['prompt']}",
                f"- expected tool: `{turn['expected_tool']}`",
                f"- assistant: {turn['assistant_text']}",
                f"- new tools: `{tool_names}`",
                f"- screenshot: `{turn['screenshot']}`",
                "",
            ],
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

    interpretation = payload.get("final_interpretation_state") or {}
    lines.extend(
        [
            "",
            "## Final Interpretation State",
            "",
            f"- has scan result: `{interpretation.get('has_scan_result')}`",
            f"- has candidate: `{interpretation.get('has_candidate')}`",
            f"- has preview: `{interpretation.get('has_preview')}`",
            f"- has validation decision: `{interpretation.get('has_validation_decision')}`",
            f"- validation decision: `{interpretation.get('validation_decision')}`",
            f"- pending confirmation: `{interpretation.get('pending_confirmation')}`",
        ],
    )

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
        ],
    )
    return "\n".join(lines).rstrip() + "\n"


def _turn_has_expected_tool(
    tools: list[dict[str, Any]],
    expected_tool: str,
) -> bool:
    return any(
        str(tool.get("name") or "") == expected_tool and bool(tool.get("success"))
        for tool in tools
    )


def _blocked_payload(
    args: argparse.Namespace,
    runtime: dict[str, object],
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "failure_reason": str(runtime.get("message") or "Local runtime not ready."),
        "source_path": str(SOURCE_PATH),
        "prompts": build_prompts(SOURCE_PATH),
        "expected_tools": list(EXPECTED_TOOLS),
        "runtime": _runtime_summary(runtime),
        "hf_offline": {
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
            "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
        },
        "screenshots": {"ready": ""},
        "turns": [],
        "visible_messages": [],
        "executed_tools": [],
        "final_interpretation_state": {},
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


def _clear_saved_main_window_geometry() -> None:
    settings = QSettings("XBrainLab", "XBrainLab")
    settings.remove("geometry")
    settings.remove("windowState")
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
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _load_capture_config(model_override: str) -> LLMConfig:
    config = LLMConfig.load_from_file() or LLMConfig()
    if model_override:
        config.apply_runtime_selection(
            "local",
            model_id=model_override,
            ui_active_mode="local",
        )
    return config


if __name__ == "__main__":
    raise SystemExit(main())
