#!/usr/bin/env python3
"""Capture a true local-model ChatPanel training-readiness walkthrough."""

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
from XBrainLab.backend.application import (
    ApplyInterpretationCommand,
    CreateEpochCommand,
    GenerateDatasetCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
    get_application_service,
)
from XBrainLab.llm.core.config import LLMConfig

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ui" / "chatpanel-local-training-readiness"
READY_SCREENSHOT = "chatpanel-training-readiness-ready.png"
JSON_ARTIFACT = "chatpanel-local-training-readiness-walkthrough.json"
MD_ARTIFACT = "chatpanel-local-training-readiness-walkthrough.md"

TURN_SPECS: list[dict[str, str]] = [
    {
        "kind": "tool",
        "expected_tool": "set_model",
        "prompt": (
            "Use EEGNet for the active dataset. Reply with one short result sentence."
        ),
    },
    {
        "kind": "tool",
        "expected_tool": "configure_training",
        "prompt": (
            "Configure training for 1 epoch, batch size 2, learning rate 0.001, "
            "and device cpu. Reply with one short result sentence."
        ),
    },
    {
        "kind": "confirmation",
        "expected_tool": "start_training",
        "prompt": (
            "Start training now with the current settings. If the app asks for "
            "confirmation, wait for that confirmation."
        ),
    },
    {
        "kind": "tool",
        "expected_tool": "visualize",
        "prompt": (
            "Show visualization readiness for the active dataset. Use the "
            "visualization readiness tool and reply with one short result sentence."
        ),
    },
    {
        "kind": "tool",
        "expected_tool": "saliency",
        "prompt": (
            "Show saliency readiness for the active dataset. Use the saliency "
            "readiness tool and reply with one short result sentence."
        ),
    },
    {
        "kind": "blocked",
        "expected_tool": "evaluate",
        "prompt": (
            "Evaluate current training results. If evaluation is blocked, explain "
            "the blocked reason in one short user-facing sentence."
        ),
    },
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
        default=620,
        help="Maximum time for the training-readiness walkthrough.",
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
        source_path = write_synthetic_raw_fif()
        payload = _blocked_payload(args, runtime, source_path)
        _write_artifacts(output_dir, payload)
        print(payload["status"])
        return 2

    source_path = write_synthetic_raw_fif()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    if args.model:
        app.setProperty("model_override", args.model)

    payload = run_training_readiness_walkthrough(
        app,
        output_dir,
        source_path,
        args.timeout_seconds,
    )
    _write_artifacts(output_dir, payload)
    print(f"Wrote {output_dir / JSON_ARTIFACT}")
    print(f"Wrote {output_dir / MD_ARTIFACT}")
    return 0 if payload["status"] == "passed" else 1


def build_prompts() -> list[str]:
    """Return visible user prompts for the training-readiness walkthrough."""
    return [turn["prompt"] for turn in TURN_SPECS]


def prepare_dataset_ready_state(study: Any, source_path: Path) -> dict[str, Any]:
    """Prepare dataset-ready state through ApplicationService before UI prompts."""
    service = get_application_service(study)
    commands = [
        ScanSourceCommand(source_path=str(source_path)),
        PreviewInterpretationCommand(),
        ValidateInterpretationCommand(),
        ApplyInterpretationCommand(confirmed=True),
        PreprocessCommand(
            operation=PreprocessOperation.STANDARD,
            low_freq=4.0,
            high_freq=40.0,
            method="z-score",
        ),
        CreateEpochCommand(t_min=0.0, t_max=0.25, event_ids=["left", "right"]),
        GenerateDatasetCommand(
            test_ratio=0.25,
            val_ratio=0.25,
            split_strategy="trial",
            training_mode="individual",
        ),
    ]
    results: list[dict[str, Any]] = []
    for command in commands:
        result = service.execute(command)
        results.append(
            {
                "command": command.name.value,
                "ok": result.ok,
                "message": result.message,
                "error_type": result.error_type.value if result.failed else None,
                "diagnostics": result.diagnostics,
            }
        )
        if result.failed:
            break
    state = service.get_state().to_dict()
    return {
        "ok": bool(results) and all(item["ok"] for item in results),
        "commands": results,
        "state": state,
    }


def run_training_readiness_walkthrough(
    app: QApplication,
    output_dir: Path,
    source_path: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run dataset-ready -> training config -> analysis readiness through ChatPanel."""
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.main_window import MainWindow

    _clear_saved_main_window_geometry()
    study = Study()
    dataset_preparation = prepare_dataset_ready_state(study, source_path)
    window = MainWindow(study)
    _set_baseline_window_geometry(window)
    window.show()

    started_at = time.monotonic()
    prompts = build_prompts()
    state: dict[str, Any] = {
        "status": "running",
        "failure_reason": "",
        "source_path": str(source_path),
        "dataset_preparation": dataset_preparation,
        "ready_screenshot": "",
        "turns": [],
        "visible_messages": [],
        "executed_tools": [],
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

    def reject_confirmation_dialogs() -> None:
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
                    "approved": False,
                }
            )
            no_button = widget.button(QMessageBox.StandardButton.No)
            if no_button is not None:
                no_button.click()
            else:
                widget.done(int(QMessageBox.StandardButton.No))
        if state["status"] == "running":
            QTimer.singleShot(250, reject_confirmation_dialogs)

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
            state["final_state"] = get_application_service(study).get_state().to_dict()
        except Exception:
            state["final_state"] = {}
        state["chat_processing"] = bool(manager.chat_controller.is_processing)
        state["controller_processing"] = bool(
            controller and getattr(controller, "is_processing", False)
        )
        if state["status"] == "running":
            ok, reason = validate_training_readiness_payload(state)
            state["status"] = "passed" if ok else "failed"
            state["failure_reason"] = "" if ok else reason
        window.close()
        app.quit()

    def open_assistant() -> None:
        if not dataset_preparation.get("ok"):
            fail("Dataset preparation failed before ChatPanel opened.")
            return
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
            fail("ChatPanel disappeared during training-readiness walkthrough.")
            return
        controller = manager.agent_controller
        before_messages = len(collect_visible_messages(panel))
        before_tools = len(
            collect_executed_tools(controller.metrics) if controller is not None else []
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
            fail("ChatPanel disappeared during training-readiness walkthrough.")
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
            joined_assistant = " ".join(assistant_texts)
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
            ok, reason = validate_turn(index, joined_assistant, new_tools, state)
            if not ok:
                fail(reason)
                return
            screenshot_name = f"chatpanel-training-readiness-turn-{index + 1}.png"
            screenshot_path = output_dir / screenshot_name
            if _capture_current_window(window, screenshot_path) != 0:
                fail("Turn screenshot was blank or could not be saved.")
                return
            state["turns"].append(
                {
                    "index": index + 1,
                    "prompt": prompt,
                    "kind": TURN_SPECS[index]["kind"],
                    "expected_tool": TURN_SPECS[index]["expected_tool"],
                    "assistant_text": joined_assistant,
                    "new_tools": [dict(tool) for tool in new_tools],
                    "screenshot": str(screenshot_path),
                }
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

    QTimer.singleShot(250, reject_confirmation_dialogs)
    QTimer.singleShot(1500, open_assistant)
    app.exec()

    config = LLMConfig.load_from_file() or LLMConfig()
    runtime = classify_runtime(config)
    return {
        "status": state["status"],
        "failure_reason": state["failure_reason"],
        "source_path": state["source_path"],
        "prompts": prompts,
        "turn_specs": TURN_SPECS,
        "dataset_preparation": state["dataset_preparation"],
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


def validate_turn(
    index: int,
    assistant_text: str,
    new_tools: list[dict[str, Any]],
    state: dict[str, Any],
) -> tuple[bool, str]:
    """Validate one visible ChatPanel turn."""
    spec = TURN_SPECS[index]
    expected_tool = spec["expected_tool"]
    kind = spec["kind"]
    if kind == "confirmation":
        if not state.get("confirmation_dialogs"):
            return False, "Training confirmation dialog was not observed."
        if any(_successful_tool(tool, "start_training") for tool in new_tools):
            return False, "Training started even though confirmation was rejected."
        if "cancel" not in assistant_text.lower():
            return False, "Training confirmation rejection was not visible."
        return True, ""
    if kind == "blocked":
        successful_unexpected = [
            tool.get("name")
            for tool in new_tools
            if bool(tool.get("success")) and tool.get("name") != expected_tool
        ]
        if successful_unexpected:
            return (
                False,
                f"Blocked turn executed substitute tools: {successful_unexpected}",
            )
        lower_text = assistant_text.lower()
        if "evaluat" not in lower_text and "training plan" not in lower_text:
            return False, "Blocked evaluate turn did not explain evaluation readiness."
        return True, ""
    if not any(_successful_tool(tool, expected_tool) for tool in new_tools):
        return (
            False,
            f"Turn {index + 1} did not execute expected tool {expected_tool}; "
            f"new tools: {[tool.get('name') for tool in new_tools]}.",
        )
    return True, ""


def validate_training_readiness_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    """Validate dataset-ready -> training config -> analysis-readiness evidence."""
    if not payload.get("dataset_preparation", {}).get("ok"):
        return False, "Dataset preparation failed."
    if len(payload.get("turns", [])) != len(TURN_SPECS):
        return False, "Not all training-readiness turns completed."
    if not payload.get("confirmation_dialogs"):
        return False, "Training confirmation dialog was not observed."
    if any(
        dialog.get("approved") for dialog in payload.get("confirmation_dialogs", [])
    ):
        return False, "Training confirmation was approved; this artifact should stop."

    tools = payload.get("executed_tools", [])
    for name in ("set_model", "configure_training", "visualize", "saliency"):
        if not any(_successful_tool(tool, name) for tool in tools):
            return False, f"Expected successful tool {name} was not recorded."
    if any(_successful_tool(tool, "start_training") for tool in tools):
        return False, "Training started despite the boundary-only walkthrough."

    final_state = payload.get("final_state") or {}
    dataset = _section(final_state, "dataset")
    training = _section(final_state, "training")
    if not dataset.get("available"):
        return False, "Final state does not have a generated dataset."
    if not training.get("has_model"):
        return False, "Final state does not have selected model."
    if not training.get("has_training_option"):
        return False, "Final state does not have training options."
    if training.get("has_trainer") or training.get("is_running"):
        return False, "Training unexpectedly started."

    ui = payload.get("ui_state") or {}
    if ui.get("chat_processing") or ui.get("controller_processing"):
        return False, "ChatPanel did not return to idle."
    return True, ""


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a compact training-readiness walkthrough summary."""
    evaluate_blocked = not _section(payload.get("final_state") or {}, "evaluation").get(
        "available",
        False,
    )
    lines = [
        "# ChatPanel Local Training Readiness Walkthrough",
        "",
        f"- status: `{payload['status']}`",
        f"- failure reason: {payload.get('failure_reason') or 'none'}",
        f"- source path: `{payload.get('source_path', '')}`",
        f"- dataset preparation ok: `{payload['dataset_preparation']['ok']}`",
        f"- runtime classification: `{payload['runtime']['classification']}`",
        f"- model: `{payload['runtime']['model_id']}`",
        f"- cache usage: `{payload['runtime']['cache_usage']}`",
        f"- HF offline: `{payload['hf_offline']['HF_HUB_OFFLINE']}`",
        f"- Transformers offline: `{payload['hf_offline']['TRANSFORMERS_OFFLINE']}`",
        f"- ready screenshot: `{payload['screenshots']['ready']}`",
        f"- training confirmations observed: `{len(payload.get('confirmation_dialogs', []))}`",
        f"- evaluate blocked: `{evaluate_blocked}`",
        f"- elapsed seconds: `{payload['elapsed_seconds']}`",
        "",
        "## Dataset Preparation",
        "",
    ]
    for command in payload.get("dataset_preparation", {}).get("commands", []):
        lines.append(f"- `{command.get('command')}`: `{command.get('ok')}`")

    lines.extend(["", "## Turns", ""])
    for turn in payload["turns"]:
        tool_names = ", ".join(
            str(tool.get("name", "")) for tool in turn.get("new_tools", [])
        )
        lines.extend(
            [
                f"### Turn {turn['index']}",
                "",
                f"- kind: `{turn['kind']}`",
                f"- prompt: {turn['prompt']}",
                f"- expected tool: `{turn['expected_tool']}`",
                f"- assistant: {turn['assistant_text']}",
                f"- new tools: `{tool_names}`",
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

    final_state = payload.get("final_state") or {}
    dataset = _section(final_state, "dataset")
    training = _section(final_state, "training")
    evaluation = _section(final_state, "evaluation")
    lines.extend(
        [
            "",
            "## Final State",
            "",
            f"- dataset available: `{dataset.get('available')}`",
            f"- selected model: `{training.get('model_name')}`",
            f"- has training option: `{training.get('has_training_option')}`",
            f"- has trainer: `{training.get('has_trainer')}`",
            f"- training running: `{training.get('is_running')}`",
            f"- evaluation available: `{evaluation.get('available')}`",
            f"- evaluation plans: `{evaluation.get('total_plans')}`",
        ]
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
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _successful_tool(tool: dict[str, Any], name: str) -> bool:
    return str(tool.get("name") or "") == name and bool(tool.get("success"))


def _section(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _blocked_payload(
    args: argparse.Namespace,
    runtime: dict[str, object],
    source_path: Path,
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "failure_reason": str(runtime.get("message") or "Local runtime not ready."),
        "source_path": str(source_path),
        "prompts": build_prompts(),
        "turn_specs": TURN_SPECS,
        "dataset_preparation": {"ok": False, "commands": [], "state": {}},
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
