#!/usr/bin/env python3
"""Capture a true local-model ChatPanel import-to-dataset tool chain."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from scripts.dev.capture_chatpanel_local_tool_chain_walkthrough import (
    _capture_current_window,
    _clear_saved_main_window_geometry,
    _force_offline_hf_runtime,
    _load_capture_config,
    _runtime_summary,
    _set_baseline_window_geometry,
    tool_chain_status,
    write_synthetic_raw_fif,
)
from scripts.dev.capture_chatpanel_local_walkthrough import (
    collect_executed_tools,
    collect_visible_messages,
    has_raw_debug_text,
)
from scripts.dev.capture_chatpanel_local_workflow_walkthrough import (
    _has_runtime_error_text,
)
from scripts.dev.inspect_local_assistant_runtime import classify_runtime
from XBrainLab.llm.core.config import LLMConfig

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ui" / "chatpanel-local-pipeline-chain"
READY_SCREENSHOT = "chatpanel-pipeline-chain-ready.png"
JSON_ARTIFACT = "chatpanel-local-pipeline-chain-walkthrough.json"
MD_ARTIFACT = "chatpanel-local-pipeline-chain-walkthrough.md"
EXPECTED_TOOLS = [
    "scan_source",
    "preview_interpretation",
    "validate_interpretation",
    "apply_interpretation",
    "apply_standard_preprocess",
    "epoch_data",
    "generate_dataset",
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
        default=760,
        help="Maximum time for the full pipeline-chain walkthrough.",
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

    payload = run_pipeline_chain(
        app,
        output_dir,
        source_path,
        args.timeout_seconds,
    )
    _write_artifacts(output_dir, payload)
    print(f"Wrote {output_dir / JSON_ARTIFACT}")
    print(f"Wrote {output_dir / MD_ARTIFACT}")
    return 0 if payload["status"] == "passed" else 1


def build_prompts(source_path: Path) -> list[str]:
    """Return the visible user prompts for the import-to-dataset chain."""
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
        (
            "Yes, apply the validated interpretation. I confirm this "
            "workspace-changing apply action if the app asks. Reply with one "
            "short result sentence."
        ),
        (
            "Apply standard preprocessing. Use apply_standard_preprocess with "
            "l_freq 4, h_freq 40, and normalize_method z-score. Reply with one "
            "short result sentence."
        ),
        (
            "Create epochs for events left and right from 0.0 to 0.25 seconds. Reply with "
            "one short result sentence."
        ),
        (
            "Generate an individual training dataset using a trial split. Reply "
            "with one short result sentence and stop before training."
        ),
    ]


def run_pipeline_chain(
    app: QApplication,
    output_dir: Path,
    source_path: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run import -> apply -> preprocess -> epoch -> dataset through ChatPanel."""
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
        "confirmation_dialogs": [],
        "final_state": {},
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

    def approve_confirmation_dialogs() -> None:
        for widget in QApplication.topLevelWidgets():
            if not isinstance(widget, QMessageBox) or not widget.isVisible():
                continue
            if widget.windowTitle() != "Confirm Action":
                continue
            state["confirmation_dialogs"].append(
                {
                    "title": widget.windowTitle(),
                    "text": widget.text(),
                    "informative_text": widget.informativeText(),
                },
            )
            yes_button = widget.button(QMessageBox.StandardButton.Yes)
            if yes_button is not None:
                yes_button.click()
            else:
                widget.done(int(QMessageBox.StandardButton.Yes))
        if state["status"] == "running":
            QTimer.singleShot(250, approve_confirmation_dialogs)

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
            state["final_state"] = BackendFacade(study).get_state().to_dict()
        except Exception:
            state["final_state"] = {}
        state["chat_processing"] = bool(manager.chat_controller.is_processing)
        state["controller_processing"] = bool(
            controller and getattr(controller, "is_processing", False)
        )
        if state["status"] == "running":
            ok, reason = validate_pipeline_payload(state)
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
            fail("ChatPanel disappeared during pipeline-chain walkthrough.")
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
            fail("ChatPanel disappeared during pipeline-chain walkthrough.")
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
            screenshot_name = f"chatpanel-pipeline-chain-turn-{index + 1}.png"
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

    QTimer.singleShot(250, approve_confirmation_dialogs)
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
        "confirmation_dialogs": state["confirmation_dialogs"],
        "final_state": state["final_state"],
        "ui_state": {
            "send_button_text": state["send_button_text"],
            "send_button_enabled": state["send_button_enabled"],
            "input_enabled": state["input_enabled"],
            "chat_processing": state["chat_processing"],
            "controller_processing": state["controller_processing"],
        },
        "elapsed_seconds": state["elapsed_seconds"],
    }


def validate_pipeline_payload(state: dict[str, Any]) -> tuple[bool, str]:
    """Validate the tool sequence and final backend state."""
    ok, reason = tool_chain_status(state["executed_tools"], state["expected_tools"])
    if not ok:
        return False, reason
    final_state = state.get("final_state") or {}
    raw = _section(final_state, "raw")
    epoch = _section(final_state, "epoch")
    dataset = _section(final_state, "dataset")
    interpretation = _section(final_state, "interpretation")
    if not raw.get("loaded"):
        return False, "Final state did not load interpreted raw data."
    if not interpretation.get("has_applied_interpretation"):
        return False, "Final state does not have an applied interpretation."
    if not epoch.get("available"):
        return False, "Final state does not have epoch data."
    if not dataset.get("available"):
        return False, "Final state does not have a generated dataset."
    if not state.get("confirmation_dialogs"):
        return False, "Apply confirmation dialog was not observed."
    return True, ""


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a compact import-to-dataset walkthrough summary."""
    lines = [
        "# ChatPanel Local Pipeline-Chain Walkthrough",
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
        f"- confirmation dialogs observed: `{len(payload.get('confirmation_dialogs', []))}`",
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

    final_state = payload.get("final_state") or {}
    interpretation = _section(final_state, "interpretation")
    epoch = _section(final_state, "epoch")
    dataset = _section(final_state, "dataset")
    lines.extend(
        [
            "",
            "## Final State",
            "",
            f"- applied interpretation: `{interpretation.get('has_applied_interpretation')}`",
            f"- validation decision: `{interpretation.get('validation_decision')}`",
            f"- epoch available: `{epoch.get('available')}`",
            f"- epoch count: `{epoch.get('epoch_count')}`",
            f"- dataset available: `{dataset.get('available')}`",
            f"- dataset count: `{dataset.get('count')}`",
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


def _section(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _blocked_payload(
    args: argparse.Namespace,
    runtime: dict[str, object],
) -> dict[str, Any]:
    source_path = write_synthetic_raw_fif()
    return {
        "status": "blocked",
        "failure_reason": str(runtime.get("message") or "Local runtime not ready."),
        "source_path": str(source_path),
        "prompts": build_prompts(source_path),
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
        "confirmation_dialogs": [],
        "final_state": {},
        "ui_state": {
            "send_button_text": "",
            "send_button_enabled": False,
            "input_enabled": False,
            "chat_processing": False,
            "controller_processing": False,
        },
        "elapsed_seconds": 0.0,
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


if __name__ == "__main__":
    raise SystemExit(main())
