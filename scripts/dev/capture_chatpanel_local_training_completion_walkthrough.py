#!/usr/bin/env python3
"""Capture a true local-model ChatPanel tiny training completion walkthrough."""

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

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from scripts.dev.bounded_qt_shutdown import BoundedQtShutdown
from scripts.dev.capture_chatpanel_local_pipeline_chain_walkthrough import (
    assistant_surface_ready,
)
from scripts.dev.capture_chatpanel_local_tool_chain_walkthrough import (
    _capture_current_window,
    _clear_saved_main_window_geometry,
    _force_offline_hf_runtime,
    _runtime_summary,
    _set_baseline_window_geometry,
)
from scripts.dev.capture_chatpanel_local_walkthrough import (
    collect_executed_tools,
    collect_visible_messages,
    has_raw_debug_text,
)
from scripts.dev.capture_chatpanel_local_workflow_walkthrough import (
    _has_runtime_error_text,
)
from scripts.dev.chatpanel_confirmation_driver import (
    describe_visible_confirmation_card,
    resolve_visible_confirmation_card,
)
from scripts.dev.chatpanel_training_fixture import write_training_ready_raw_fif
from scripts.dev.inspect_local_assistant_runtime import classify_runtime
from scripts.dev.local_assistant_capture_runtime import (
    collect_capture_source_identity,
    collect_runtime_input_evidence,
    finalize_strict_capture_evidence,
    isolated_assistant_runtime_config,
    validate_strict_capture_evidence,
)
from XBrainLab.backend.application import (
    ApplyInterpretationCommand,
    ConfigureTrainingCommand,
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
DEFAULT_OUTPUT_DIR = (
    ROOT / "build" / "dev-artifacts" / "chatpanel-local-training-completion"
)
TEMP_ROOT = Path(tempfile.gettempdir())
TRAINING_OUTPUT_DIR = TEMP_ROOT / "xbrainlab-chatpanel-training-completion-output"
SOURCE_DIR = TEMP_ROOT / "xbrainlab_chatpanel_training_completion"
SOURCE_PATH = SOURCE_DIR / "training_completion_raw.fif"
READY_SCREENSHOT = "chatpanel-training-completion-ready.png"
TRAINED_SCREENSHOT = "chatpanel-training-completion-trained.png"
JSON_ARTIFACT = "chatpanel-local-training-completion-walkthrough.json"
MD_ARTIFACT = "chatpanel-local-training-completion-walkthrough.md"
TRAINING_TERMINAL_TEXT = "Training completed. Results are ready in Evaluation."
EXPECTED_SALIENCY_METHOD = "SmoothGrad"
EXPECTED_SALIENCY_PARAMS = {
    "nt_samples": 2,
    "nt_samples_batch_size": 1,
    "stdevs": 1.0,
}
_RUNTIME_INPUT_NAME = "training_eeg_fixture"
_RUNTIME_INPUT_KIND = "deterministic-eeg-fixture"

TURN_SPECS: list[dict[str, str]] = [
    {
        "kind": "tool",
        "expected_tool": "set_model",
        "prompt_template": (
            "Use EEGNet for the active dataset. Reply with one short result sentence."
        ),
    },
    {
        "kind": "tool",
        "expected_tool": "configure_training",
        "prompt_template": (
            "Configure training for 1 epoch, batch size 2, learning rate 0.001, "
            "and device cpu. Reply with one short result sentence."
        ),
    },
    {
        "kind": "confirmation",
        "expected_tool": "start_training",
        "prompt_template": (
            "Start training now with the current settings. If the app asks for "
            "confirmation, wait for that confirmation."
        ),
    },
    {
        "kind": "tool",
        "expected_tool": "evaluate",
        "prompt_template": (
            "Evaluate the completed training results and summarize the metrics in "
            "one short user-facing sentence."
        ),
    },
    {
        "kind": "tool",
        "expected_tool": "saliency",
        "prompt_template": (
            "Configure SmoothGrad saliency with nt_samples 2, "
            "nt_samples_batch_size 1, and stdevs 1.0. Reply with one short "
            "result sentence."
        ),
    },
    {
        "kind": "tool",
        "expected_tool": "visualize",
        "prompt_template": (
            "Use visualize for a post-training visualization summary. Reply with "
            "one short result sentence."
        ),
    },
    {
        "kind": "tool",
        "expected_tool": "saliency",
        "prompt_template": (
            "Query saliency readiness for the trained model. Reply with one short "
            "result sentence."
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
        default=900,
        help="Maximum time for the training-completion walkthrough.",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Optional approved local model id to prefer for this process.",
    )
    parser.add_argument(
        "--training-output-dir",
        default=str(TRAINING_OUTPUT_DIR),
        help="Temporary directory for tiny training outputs.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    training_output_dir = Path(args.training_output_dir)
    if training_output_dir.exists():
        shutil.rmtree(training_output_dir)
    training_output_dir.mkdir(parents=True, exist_ok=True)

    _force_offline_hf_runtime()
    model_id = args.model or LLMConfig.default_local_model_id()
    source_identity_at_start = collect_capture_source_identity(refresh=True)
    with isolated_assistant_runtime_config(
        model_id,
        parent_dir=output_dir,
    ) as config:
        runtime = classify_runtime(config)
        source_path = write_synthetic_training_raw_fif()
        runtime_input_paths = {_RUNTIME_INPUT_NAME: source_path}
        runtime_input_kinds = {_RUNTIME_INPUT_NAME: _RUNTIME_INPUT_KIND}
        runtime_input_evidence_at_start = collect_runtime_input_evidence(
            runtime_input_paths,
            kinds=runtime_input_kinds,
            retained=False,
        )
        if runtime["classification"] not in {"gpu-ready", "cpu-fallback"}:
            payload = _blocked_payload(args, runtime, source_path, training_output_dir)
            finalize_strict_capture_evidence(
                payload,
                requested_model_id=model_id,
                runtime_snapshot=None,
                cache_dir=config.cache_dir,
                artifact_root=output_dir,
                source_identity_at_start=source_identity_at_start,
                host_actions=("prepared deterministic training dataset state",),
                runtime_input_paths=runtime_input_paths,
                runtime_input_kinds=runtime_input_kinds,
                runtime_input_evidence_at_start=runtime_input_evidence_at_start,
            )
            _write_artifacts(output_dir, payload)
            print(payload["status"])
            return 2

        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        app.setProperty("model_override", model_id)
        payload = run_training_completion_walkthrough(
            app,
            output_dir,
            source_path,
            training_output_dir,
            args.timeout_seconds,
        )
        runtime_snapshot = payload.pop("_runtime_snapshot", None)
        strict_ok, strict_reason = finalize_strict_capture_evidence(
            payload,
            requested_model_id=model_id,
            runtime_snapshot=(
                runtime_snapshot if isinstance(runtime_snapshot, dict) else None
            ),
            cache_dir=config.cache_dir,
            artifact_root=output_dir,
            source_identity_at_start=source_identity_at_start,
            host_actions=(
                "prepared deterministic training dataset state",
                "approved the visible training confirmation card",
                "waited for terminal training completion",
            ),
            runtime_input_paths=runtime_input_paths,
            runtime_input_kinds=runtime_input_kinds,
            runtime_input_evidence_at_start=runtime_input_evidence_at_start,
        )
        if payload.get("status") == "passed" and not strict_ok:
            payload["status"] = "failed"
            payload["failure_reason"] = strict_reason
    _write_artifacts(output_dir, payload)
    print(f"Wrote {output_dir / JSON_ARTIFACT}")
    print(f"Wrote {output_dir / MD_ARTIFACT}")
    return 0 if payload["status"] == "passed" else 1


def write_synthetic_training_raw_fif() -> Path:
    """Write a deterministic EEG fixture with epoch duration suitable for EEGNet."""
    if SOURCE_DIR.exists():
        shutil.rmtree(SOURCE_DIR)
    return write_training_ready_raw_fif(SOURCE_PATH)


def build_prompts() -> list[str]:
    """Return visible user prompts for the training-completion walkthrough."""
    return [turn["prompt_template"] for turn in TURN_SPECS]


def prepare_training_dataset_ready_state(
    study: Any,
    source_path: Path,
    training_output_dir: Path,
) -> dict[str, Any]:
    """Prepare dataset-ready state with epoch duration suitable for EEGNet."""
    service = get_application_service(study)
    commands = [
        ScanSourceCommand(source_path=str(source_path)),
        PreviewInterpretationCommand(choices={"label_carrier": "embedded_events"}),
        ValidateInterpretationCommand(),
        ApplyInterpretationCommand(confirmed=True),
        PreprocessCommand(
            operation=PreprocessOperation.STANDARD,
            low_freq=4.0,
            high_freq=40.0,
            method="z-score",
        ),
        CreateEpochCommand(t_min=0.0, t_max=1.5, event_ids=["left", "right"]),
        GenerateDatasetCommand(
            test_ratio=0.25,
            val_ratio=0.25,
            split_strategy="trial",
            training_mode="individual",
        ),
        ConfigureTrainingCommand(
            epoch=1,
            batch_size=2,
            learning_rate=0.001,
            device="cpu",
            output_dir=str(training_output_dir),
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
            },
        )
        if result.failed:
            break
    return {
        "ok": bool(results) and all(item["ok"] for item in results),
        "commands": results,
        "state": service.get_state().to_dict(),
    }


def run_training_completion_walkthrough(
    app: QApplication,
    output_dir: Path,
    source_path: Path,
    training_output_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run dataset-ready -> training completion -> analysis through ChatPanel."""
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.main_window import MainWindow

    _clear_saved_main_window_geometry()
    study = Study()
    dataset_preparation = prepare_training_dataset_ready_state(
        study,
        source_path,
        training_output_dir,
    )
    window = MainWindow(study)
    _set_baseline_window_geometry(window)
    window.show()

    started_at = time.monotonic()
    prompts = build_prompts()
    state: dict[str, Any] = {
        "status": "running",
        "failure_reason": "",
        "source_path": str(source_path),
        "training_output_dir": str(training_output_dir),
        "dataset_preparation": dataset_preparation,
        "ready_screenshot": "",
        "trained_screenshot": "",
        "turns": [],
        "visible_messages": [],
        "executed_tools": [],
        "confirmation_events": [],
        "training_completion": {},
        "final_state": {},
        "send_button_text": "",
        "send_button_enabled": False,
        "input_enabled": False,
        "chat_processing": True,
        "controller_processing": True,
        "shutdown": {"status": "pending", "detail": ""},
        "runtime_snapshot": {},
        "terminal_started": False,
        "elapsed_seconds": 0.0,
    }
    handled_confirmation_ids: set[str] = set()
    shutdown = BoundedQtShutdown(
        app=app,
        window=window,
        manager_provider=lambda: window.agent_manager,
        state=state,
        schedule=QTimer.singleShot,
        now=time.monotonic,
    )

    def fail(reason: str) -> None:
        state["status"] = "failed"
        state["failure_reason"] = reason
        finish()

    def approve_confirmation_cards() -> None:
        manager = window.agent_manager
        panel = manager.chat_panel if manager is not None else None
        event = (
            describe_visible_confirmation_card(panel, approved=True)
            if panel is not None
            else None
        )
        if event is not None and event["request_id"] not in handled_confirmation_ids:
            request_id = str(event["request_id"])
            handled_confirmation_ids.add(request_id)
            screenshot_path = output_dir / "chatpanel-training-confirmation-approve.png"
            if _capture_current_window(window, screenshot_path) != 0:
                fail("Training confirmation card screenshot could not be saved.")
                return
            event["screenshot"] = str(screenshot_path)
            state["confirmation_events"].append(event)
            if not resolve_visible_confirmation_card(
                panel,
                request_id=request_id,
                expected_command_name="start_training",
                approved=True,
            ):
                fail("Training confirmation card changed before approval.")
                return
        if state["status"] == "running":
            QTimer.singleShot(250, approve_confirmation_cards)

    def finish() -> None:
        if state["terminal_started"]:
            return
        state["terminal_started"] = True
        state["elapsed_seconds"] = round(time.monotonic() - started_at, 3)
        manager = window.agent_manager
        panel = manager.chat_panel if manager is not None else None
        controller = manager.agent_controller if manager is not None else None
        if panel is not None:
            state["visible_messages"] = [
                message.__dict__ for message in collect_visible_messages(panel)
            ]
            state["send_button_text"] = panel.send_btn.text()
            state["send_button_enabled"] = panel.send_btn.isEnabled()
            state["input_enabled"] = panel.input_field.isEnabled()
        if controller is not None:
            state["executed_tools"] = collect_executed_tools(controller.metrics)
        lifecycle = getattr(manager, "assistant_runtime", None)
        current_runtime = getattr(lifecycle, "current", None)
        if current_runtime is not None and hasattr(current_runtime, "to_dict"):
            state["runtime_snapshot"] = current_runtime.to_dict()
        try:
            state["final_state"] = get_application_service(study).get_state().to_dict()
        except Exception:
            state["final_state"] = {}
        state["chat_processing"] = bool(
            manager is not None and manager.chat_controller.is_processing
        )
        state["controller_processing"] = bool(
            controller and getattr(controller, "is_processing", False)
        )
        if state["status"] == "running":
            ok, reason = validate_training_completion_payload(state, strict=False)
            state["status"] = "passed" if ok else "failed"
            state["failure_reason"] = "" if ok else reason
        shutdown.start()

    def open_assistant() -> None:
        if not dataset_preparation.get("ok"):
            fail("Dataset preparation failed before ChatPanel opened.")
            return
        window.ai_btn.click()
        QTimer.singleShot(250, wait_for_assistant_ready)

    def wait_for_assistant_ready() -> None:
        if time.monotonic() - started_at > timeout_seconds:
            fail(f"Timed out waiting for assistant readiness after {timeout_seconds}s.")
            return
        manager = window.agent_manager
        if manager is None:
            fail("Assistant manager was not initialized.")
            return
        ready, _reason = assistant_surface_ready(manager)
        if not ready:
            QTimer.singleShot(250, wait_for_assistant_ready)
            return
        capture_ready()

    def capture_ready() -> None:
        manager = window.agent_manager
        if manager is None:
            fail("Assistant manager disappeared before ready capture.")
            return
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
        if manager is None:
            fail(
                "Assistant manager disappeared during training-completion walkthrough."
            )
            return
        panel = manager.chat_panel
        if panel is None:
            fail("ChatPanel disappeared during training-completion walkthrough.")
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
        if manager is None:
            fail(
                "Assistant manager disappeared during training-completion walkthrough."
            )
            return
        panel = manager.chat_panel
        controller = manager.agent_controller
        if panel is None:
            fail("ChatPanel disappeared during training-completion walkthrough.")
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
            screenshot_name = f"chatpanel-training-completion-turn-{index + 1}.png"
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
                },
            )
            if TURN_SPECS[index]["expected_tool"] == "start_training":
                QTimer.singleShot(500, lambda: wait_for_training_completion(index))
                return
            if index + 1 < len(prompts):
                QTimer.singleShot(500, lambda: send_prompt(index + 1))
            else:
                finish()
            return

        QTimer.singleShot(
            1000,
            lambda: wait_for_turn(index, prompt, before_messages, before_tools),
        )

    def wait_for_training_completion(index: int) -> None:
        if time.monotonic() - started_at > timeout_seconds:
            fail(f"Timed out after {timeout_seconds} seconds waiting for training.")
            return
        manager = window.agent_manager
        panel = manager.chat_panel if manager is not None else None
        if panel is None:
            fail("ChatPanel disappeared while waiting for training completion.")
            return
        backend_state = get_application_service(study).get_state().to_dict()
        training = _section(backend_state, "training")
        evaluation = _section(backend_state, "evaluation")
        if training.get("has_trainer") and not training.get("is_running"):
            visible_messages = collect_visible_messages(panel)
            terminal_text = next(
                (
                    message.text.strip()
                    for message in reversed(visible_messages)
                    if message.sender == "assistant"
                    and TRAINING_TERMINAL_TEXT in message.text
                ),
                "",
            )
            if not terminal_text:
                QTimer.singleShot(250, lambda: wait_for_training_completion(index))
                return
            state["training_completion"] = {
                "state": backend_state,
                "finished_run_count": training.get("finished_run_count"),
                "metrics_available": evaluation.get("metrics_available"),
                "assistant_terminal_text": terminal_text,
            }
            if int(training.get("finished_run_count") or 0) < 1:
                fail("Training stopped without a completed run.")
                return
            if not state["turns"]:
                fail("Training completed before a turn screenshot was captured.")
                return
            trained_path = output_dir / TRAINED_SCREENSHOT
            if _capture_current_window(window, trained_path) != 0:
                fail("Training terminal screenshot was blank or could not be saved.")
                return
            state["trained_screenshot"] = str(trained_path)
            if index + 1 < len(prompts):
                QTimer.singleShot(500, lambda: send_prompt(index + 1))
            else:
                finish()
            return
        QTimer.singleShot(500, lambda: wait_for_training_completion(index))

    QTimer.singleShot(250, approve_confirmation_cards)
    QTimer.singleShot(1500, open_assistant)
    app.exec()
    shutdown.reconcile_after_event_loop()

    config = LLMConfig.load_from_file() or LLMConfig()
    runtime = classify_runtime(config)
    return {
        "status": state["status"],
        "failure_reason": state["failure_reason"],
        "source_path": state["source_path"],
        "training_output_dir": state["training_output_dir"],
        "prompts": prompts,
        "turn_specs": TURN_SPECS,
        "dataset_preparation": state["dataset_preparation"],
        "runtime": _runtime_summary(runtime),
        "hf_offline": {
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
            "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
        },
        "screenshots": {
            "ready": state["ready_screenshot"],
            "trained": state["trained_screenshot"],
        },
        "turns": state["turns"],
        "visible_messages": state["visible_messages"],
        "executed_tools": state["executed_tools"],
        "confirmation_events": state["confirmation_events"],
        "training_completion": state["training_completion"],
        "final_state": state["final_state"],
        "shutdown": state["shutdown"],
        "_runtime_snapshot": state["runtime_snapshot"],
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
        if not state.get("confirmation_events"):
            return False, "Training confirmation card was not observed."
        if not any(event.get("approved") for event in state["confirmation_events"]):
            return False, "Training confirmation was not approved."
        if not any(_successful_tool(tool, "start_training") for tool in new_tools):
            return False, "Training did not start after confirmation approval."
        return True, ""
    if not any(_successful_tool(tool, expected_tool) for tool in new_tools):
        return (
            False,
            f"Turn {index + 1} did not execute expected tool {expected_tool}; "
            f"new tools: {[tool.get('name') for tool in new_tools]}.",
        )
    if expected_tool == "evaluate" and "evaluat" not in assistant_text.lower():
        return False, "Evaluate turn did not summarize evaluation."
    if expected_tool == "visualize" and "visual" not in assistant_text.lower():
        return False, "Visualize turn did not summarize visualization readiness."
    if expected_tool == "saliency" and "saliency" not in assistant_text.lower():
        return False, "Saliency turn did not summarize saliency readiness."
    return True, ""


def validate_training_completion_payload(
    payload: dict[str, Any],
    *,
    strict: bool = True,
) -> tuple[bool, str]:
    """Validate dataset-ready -> tiny training completion -> analysis evidence."""
    if not payload.get("dataset_preparation", {}).get("ok"):
        return False, "Dataset preparation failed."
    if len(payload.get("turns", [])) != len(TURN_SPECS):
        return False, "Not all training-completion turns completed."
    if not payload.get("confirmation_events"):
        return False, "Training confirmation card was not observed."
    if not any(
        event.get("approved") for event in payload.get("confirmation_events", [])
    ):
        return False, "Training confirmation was not approved."

    tools = payload.get("executed_tools", [])
    for name in (
        "set_model",
        "configure_training",
        "start_training",
        "evaluate",
        "visualize",
        "saliency",
    ):
        if not any(_successful_tool(tool, name) for tool in tools):
            return False, f"Expected successful tool {name} was not recorded."

    final_state = payload.get("final_state") or {}
    dataset = _section(final_state, "dataset")
    training = _section(final_state, "training")
    evaluation = _section(final_state, "evaluation")
    visualization = _section(final_state, "visualization")
    if not dataset.get("available"):
        return False, "Final state does not have a generated dataset."
    if not training.get("has_model"):
        return False, "Final state does not have selected model."
    if not training.get("has_training_option"):
        return False, "Final state does not have training options."
    if not training.get("has_trainer"):
        return False, "Final state does not have trainer after training."
    if training.get("is_running"):
        return False, "Training was still running at artifact capture."
    if int(training.get("finished_run_count") or 0) < 1:
        return False, "Final state does not have a completed training run."
    option = training.get("training_option") or {}
    if option.get("output_dir") != payload.get("training_output_dir"):
        return False, "Training output_dir did not match requested artifact path."
    if not evaluation.get("available") or not evaluation.get("metrics_available"):
        return False, "Evaluation metrics were not available after training."
    if not visualization.get("saliency_configured"):
        return False, "Saliency was not configured after training."
    if not visualization.get("saliency_available"):
        return False, "Saliency was not available after configuration."
    saliency_params = visualization.get("saliency_params")
    if not isinstance(saliency_params, dict):
        return False, "Authoritative saliency_params were not published."
    methods = saliency_params.get("_methods")
    if methods != [EXPECTED_SALIENCY_METHOD]:
        return (
            False,
            f"Saliency _methods did not match {[EXPECTED_SALIENCY_METHOD]!r}.",
        )
    method_params = saliency_params.get(EXPECTED_SALIENCY_METHOD)
    if not isinstance(method_params, dict):
        return False, f"{EXPECTED_SALIENCY_METHOD} parameters were not published."
    for field, expected in EXPECTED_SALIENCY_PARAMS.items():
        actual = method_params.get(field)
        if type(actual) is not type(expected) or actual != expected:
            return (
                False,
                f"{EXPECTED_SALIENCY_METHOD}.{field} did not match {expected!r}.",
            )
    if set(method_params) != set(EXPECTED_SALIENCY_PARAMS):
        return False, f"{EXPECTED_SALIENCY_METHOD} params were not exact."

    completion = payload.get("training_completion") or {}
    if int(completion.get("finished_run_count") or 0) < 1:
        return False, "Training completion checkpoint did not record a finished run."
    terminal_text = str(completion.get("assistant_terminal_text") or "")
    if TRAINING_TERMINAL_TEXT not in terminal_text:
        return False, "Assistant training terminal result was not visible."
    visible_terminal = any(
        message.get("sender") == "assistant"
        and TRAINING_TERMINAL_TEXT in str(message.get("text") or "")
        for message in payload.get("visible_messages", [])
        if isinstance(message, dict)
    )
    if not visible_terminal:
        return False, "Assistant training terminal result was not retained in history."

    ui = payload.get("ui_state") or {}
    if ui.get("chat_processing") or ui.get("controller_processing"):
        return False, "ChatPanel did not return to idle."
    if strict:
        return validate_strict_capture_evidence(
            payload,
            required_runtime_inputs=(_RUNTIME_INPUT_NAME,),
        )
    return True, ""


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a compact training-completion walkthrough summary."""
    final_state = payload.get("final_state") or {}
    dataset = _section(final_state, "dataset")
    training = _section(final_state, "training")
    evaluation = _section(final_state, "evaluation")
    visualization = _section(final_state, "visualization")
    lines = [
        "# ChatPanel Local Training Completion Walkthrough",
        "",
        f"- status: `{payload['status']}`",
        f"- failure reason: {payload.get('failure_reason') or 'none'}",
        f"- dataset fixture: `{_runtime_input_display_name(payload)}`",
        f"- dataset fixture SHA-256: `{_runtime_input_sha256(payload)}`",
        f"- training output dir: `{payload.get('training_output_dir', '')}`",
        f"- dataset preparation ok: `{payload['dataset_preparation']['ok']}`",
        f"- runtime classification: `{payload['runtime']['classification']}`",
        f"- requested model: `{payload['runtime'].get('requested_model_id', '')}`",
        f"- loaded model: `{payload['runtime'].get('loaded_model_id', '')}`",
        f"- loaded revision: `{(payload['runtime'].get('model_identity') or {}).get('loaded_revision', '')}`",
        f"- cache usage: `{payload['runtime']['cache_usage']}`",
        f"- HF offline: `{payload['hf_offline']['HF_HUB_OFFLINE']}`",
        f"- Transformers offline: `{payload['hf_offline']['TRANSFORMERS_OFFLINE']}`",
        f"- ready screenshot: `{payload['screenshots']['ready']}`",
        f"- trained screenshot: `{payload['screenshots']['trained']}`",
        f"- training confirmation cards observed: `{len(payload.get('confirmation_events', []))}`",
        f"- confirmation approved: `{any(event.get('approved') for event in payload.get('confirmation_events', []))}`",
        f"- finished runs: `{training.get('finished_run_count')}`",
        f"- evaluation metrics available: `{evaluation.get('metrics_available')}`",
        f"- saliency configured: `{visualization.get('saliency_configured')}`",
        f"- saliency available: `{visualization.get('saliency_available')}`",
        f"- saliency methods: `{(visualization.get('saliency_params') or {}).get('_methods')}`",
        f"- {EXPECTED_SALIENCY_METHOD} params: `{(visualization.get('saliency_params') or {}).get(EXPECTED_SALIENCY_METHOD)}`",
        f"- shutdown: `{(payload.get('shutdown') or {}).get('status', 'unknown')}`",
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
            ],
        )

    lines.extend(["## Executed Tools", ""])
    tools = payload.get("executed_tools", [])
    if tools:
        for tool in tools:
            status = "ok" if tool.get("success") else "failed"
            lines.append(
                f"- `{tool.get('name', '')}`: `{status}` "
                f"({tool.get('duration_ms', 0)} ms)",
            )
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Final State",
            "",
            f"- dataset available: `{dataset.get('available')}`",
            f"- selected model: `{training.get('model_name')}`",
            f"- has training option: `{training.get('has_training_option')}`",
            f"- output dir: `{(training.get('training_option') or {}).get('output_dir')}`",
            f"- has trainer: `{training.get('has_trainer')}`",
            f"- training running: `{training.get('is_running')}`",
            f"- finished runs: `{training.get('finished_run_count')}`",
            f"- evaluation available: `{evaluation.get('available')}`",
            f"- evaluation metrics available: `{evaluation.get('metrics_available')}`",
            f"- saliency configured: `{visualization.get('saliency_configured')}`",
            f"- saliency available: `{visualization.get('saliency_available')}`",
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


def _successful_tool(tool: dict[str, Any], name: str) -> bool:
    return str(tool.get("name") or "") == name and bool(tool.get("success"))


def _section(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _runtime_input_record(payload: dict[str, Any]) -> dict[str, Any]:
    evidence = _section(payload, "runtime_input_artifacts")
    artifacts = _section(evidence, "artifacts")
    return _section(artifacts, _RUNTIME_INPUT_NAME)


def _runtime_input_display_name(payload: dict[str, Any]) -> str:
    return str(_runtime_input_record(payload).get("display_name") or "")


def _runtime_input_sha256(payload: dict[str, Any]) -> str:
    return str(_runtime_input_record(payload).get("sha256") or "")


def _blocked_payload(
    args: argparse.Namespace,
    runtime: dict[str, object],
    source_path: Path,
    training_output_dir: Path,
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "failure_reason": str(runtime.get("message") or "Local runtime not ready."),
        "source_path": str(source_path),
        "training_output_dir": str(training_output_dir),
        "prompts": build_prompts(),
        "turn_specs": TURN_SPECS,
        "dataset_preparation": {"ok": False, "commands": [], "state": {}},
        "runtime": _runtime_summary(runtime),
        "hf_offline": {
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
            "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
        },
        "screenshots": {"ready": "", "trained": ""},
        "turns": [],
        "visible_messages": [],
        "executed_tools": [],
        "confirmation_events": [],
        "training_completion": {},
        "final_state": {},
        "shutdown": {"status": "not_started", "detail": ""},
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
    if payload.get("status") == "passed":
        ok, reason = validate_training_completion_payload(payload)
        if not ok:
            raise ValueError(f"Refusing to write invalid strict evidence: {reason}")
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
