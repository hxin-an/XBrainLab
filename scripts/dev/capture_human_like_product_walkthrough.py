#!/usr/bin/env python3
"""Capture an automated human-like product walkthrough artifact.

This replay uses the real Qt MainWindow, Data Interpretation dialog, ChatPanel,
and ApplicationService command spine. It is UI-observable automation evidence,
not human Windows desktop acceptance.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import re
import resource
import sys
import tempfile
import threading
import time
from html import escape
from pathlib import Path
from typing import Any

from PIL import Image
from PyQt6.QtCore import QPoint, QSize, Qt, QThreadPool, QTimer
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QTextBrowser,
    QWidget,
)

from scripts.dev.capture_chatpanel_local_walkthrough import collect_visible_messages
from scripts.dev.capture_data_interpretation_replay import (
    SOURCE_DIR,
    SOURCE_PATH,
    apply_replay_review_choices,
    table_state,
    tree_rows,
    tree_state,
    write_synthetic_raw_fif,
)
from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    EvaluateCommand,
    GenerateDatasetCommand,
    NewSessionCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ReloadInterpretationRecipeCommand,
    SaliencyCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
    VisualizeCommand,
)
from XBrainLab.backend.application.results import CommandResult
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.study import Study
from XBrainLab.ui.dialogs.dataset import DataInterpretationPreviewDialog
from XBrainLab.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ui" / "human-like-walkthrough"
WINDOW_SIZE = QSize(1280, 800)
NARROW_WINDOW_SIZE = QSize(900, 760)
JSON_ARTIFACT = "human-like-walkthrough.json"
MD_ARTIFACT = "human-like-walkthrough.md"
RECIPE_ARTIFACT = "walkthrough-import.recipe.json"

SCREENSHOT_NAMES: dict[str, str] = {
    "main_initial": "01-main-initial.png",
    "dataset_page": "02-dataset-page.png",
    "source_selection": "03-source-selection.png",
    "wizard_preview": "04-interpretation-preview.png",
    "wizard_confirm": "05-interpretation-confirm.png",
    "applied": "06-interpretation-applied.png",
    "recipe_reloaded": "07-recipe-reloaded.png",
    "preprocess": "08-preprocessing.png",
    "dataset_ready": "09-dataset-ready.png",
    "training_readiness": "10-training-readiness.png",
    "analysis_readiness": "11-analysis-readiness.png",
    "assistant_empty": "12-assistant-empty.png",
    "assistant_normal": "13-assistant-normal.png",
    "assistant_clarification": "14-assistant-clarification.png",
    "assistant_blocked": "15-assistant-blocked.png",
    "assistant_success": "16-assistant-success.png",
    "assistant_narrow": "17-assistant-narrow.png",
    "reset_boundary": "18-reset-boundary.png",
    "error_recovery": "19-error-recovery.png",
    "eval_dashboard": "20-eval-dashboard.png",
}

REQUIRED_PHASES = (
    "app_startup",
    "main_window_initial_state",
    "data_source_selection",
    "data_interpretation_select_source",
    "data_interpretation_scan_result",
    "data_interpretation_preview",
    "data_interpretation_decisions",
    "data_interpretation_confirm_metadata_labels",
    "data_interpretation_apply",
    "data_interpretation_save_recipe",
    "data_interpretation_reload_recipe",
    "preprocessing",
    "epoch_creation",
    "dataset_generation",
    "training_readiness",
    "evaluation_visualization_saliency_readiness",
    "assistant_empty_state",
    "assistant_normal_message",
    "assistant_missing_input_clarification",
    "assistant_blocked_command",
    "assistant_successful_tool_result",
    "assistant_repeated_open_close",
    "assistant_narrow_panel",
    "reset_new_session_boundary",
    "error_recovery",
    "eval_dashboard_report",
)

VISIBLE_FORBIDDEN = (
    "tool_name",
    "Tool Output:",
    "Tool Call:",
    "Traceback",
    "ApplicationService",
    "BackendFacade",
    "json_schema",
    "pipeline_stage",
    "scan_source",
    "preview_interpretation",
    "validate_interpretation",
    "apply_interpretation",
    "save_interpretation_recipe",
    "reload_interpretation_recipe",
    "configure_training",
    "generate_dataset",
    "create_epoch",
    "reset_session",
    "new_session",
    "query_state",
    "load_data",
    "attach_labels",
    "import_labels",
)
VISIBLE_TRACE_TOKEN_PATTERN = re.compile(
    r"\b(?:scan|candidate|metadata|metadata_override|choices|label_import|"
    r"label_carrier|class_map|recipe):[A-Za-z0-9_.<>/-]+",
)

RESOURCE_THREAD_TOLERANCE = 1
RESOURCE_RSS_SMOKE_LIMIT_KB = 600_000
GEOMETRY_WIDTH_TOLERANCE_PX = 8


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for screenshots and walkthrough artifacts.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    payload = capture_walkthrough(app, output_dir)
    write_artifacts(output_dir, payload)
    print(f"Wrote {output_dir / JSON_ARTIFACT}")
    print(f"Wrote {output_dir / MD_ARTIFACT}")
    return 0 if payload["status"] == "passed" else 1


def capture_walkthrough(app: QApplication, output_dir: Path) -> dict[str, Any]:
    """Run the walkthrough and return the artifact payload."""
    started_at = time.monotonic()
    result: dict[str, Any] = {"payload": None}

    def run() -> None:
        window: MainWindow | None = None
        try:
            result["payload"] = _run_walkthrough_steps(app, output_dir, started_at)
        except Exception as exc:  # pragma: no cover - artifact failure path
            result["payload"] = {
                "status": "failed",
                "failure_reason": str(exc),
                "claim_boundary": claim_boundary(),
                "phases": [],
                "screenshots": {},
                "pass_fail_summary": {
                    "passed": False,
                    "failed_checks": [str(exc)],
                },
            }
        finally:
            if window is not None:
                window.close()
            app.quit()

    QTimer.singleShot(1000, run)
    app.exec()
    payload = result["payload"]
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "failure_reason": "Walkthrough did not produce a payload.",
            "claim_boundary": claim_boundary(),
            "phases": [],
            "screenshots": {},
            "pass_fail_summary": {
                "passed": False,
                "failed_checks": ["payload missing"],
            },
        }
    return payload


def _run_walkthrough_steps(
    app: QApplication,
    output_dir: Path,
    started_at: float,
) -> dict[str, Any]:
    screenshots: dict[str, str] = {}
    phases: list[dict[str, Any]] = []
    command_results: list[dict[str, Any]] = []
    tool_transcript: list[dict[str, Any]] = []
    user_transcript: list[dict[str, str]] = []
    resource_notes: list[dict[str, Any]] = [resource_snapshot("start")]
    recipe_path = output_dir / RECIPE_ARTIFACT

    source_path = write_synthetic_raw_fif()
    study = Study()
    service = ApplicationService(study)
    window = MainWindow(study)
    set_window_geometry(window, WINDOW_SIZE)
    window.show()
    settle_window_geometry_for_capture(app, window, WINDOW_SIZE)

    def capture_step(
        phase: str,
        screenshot_key: str,
        *,
        widget: QWidget | None = None,
        notes: dict[str, Any] | None = None,
    ) -> None:
        target = widget or window
        screenshot_path = output_dir / SCREENSHOT_NAMES[screenshot_key]
        capture_widget(target, screenshot_path)
        screenshots[screenshot_key] = str(screenshot_path)
        phases.append(
            {
                "phase": phase,
                "screenshot": str(screenshot_path),
                "visible_text": visible_text_snapshot(target),
                "button_state": button_state_snapshot(target),
                "workflow_state": compact_state(service.get_state()),
                "notes": notes or {},
            }
        )

    capture_step(
        "app_startup",
        "main_initial",
        notes={"window_title": window.windowTitle(), "startup": "MainWindow shown"},
    )
    window.switch_page(0)
    app.processEvents()
    capture_step(
        "main_window_initial_state",
        "dataset_page",
        notes={
            "current_panel": "Dataset",
            "ui_geometry": dataset_page_geometry(window),
        },
    )
    capture_step(
        "data_source_selection",
        "source_selection",
        notes={
            "selected_source": sanitize_path(str(source_path.parent)),
            "input_mode": "folder",
            "source_button": window.dataset_panel.sidebar.import_btn.text(),
        },
    )
    append_phase_alias(
        phases,
        "data_interpretation_select_source",
        screenshots["source_selection"],
        window.dataset_panel,
        service,
        {"selected_source": sanitize_path(str(source_path.parent))},
    )

    scan = execute_recorded(
        service,
        ScanSourceCommand(source_path=str(source_path.parent)),
        command_results,
    )
    preview = execute_recorded(service, PreviewInterpretationCommand(), command_results)
    validation = execute_recorded(
        service,
        ValidateInterpretationCommand(),
        command_results,
    )
    tool_transcript.extend(
        command_summary(item) for item in [scan, preview, validation]
    )

    dialog = DataInterpretationPreviewDialog(
        window.dataset_panel,
        scan_result=scan.diagnostics["scan_result"],
        preview=preview.diagnostics["preview"],
        validation_decision=validation.diagnostics["validation_decision"],
    )
    dialog.show()
    app.processEvents()
    capture_step(
        "data_interpretation_scan_result",
        "wizard_preview",
        widget=dialog,
        notes={
            "decision": validation.diagnostics["validation_decision"]["decision"],
            "eeg_files": len(scan.diagnostics["scan_result"]["eeg_files"]),
            "label_carriers": len(scan.diagnostics["scan_result"]["label_carriers"]),
            "ui_geometry": sanitize(interpretation_dialog_geometry(dialog)),
        },
    )

    apply_review_choices(dialog)
    app.processEvents()
    dialog_result = dialog.get_result()
    review_choices = dialog_result.get("choices", {})
    capture_step(
        "data_interpretation_preview",
        "wizard_confirm",
        widget=dialog,
        notes={
            "review_choices": sanitize(review_choices),
            "metadata_rows": tree_rows(dialog.file_tree),
            "label_carrier_rows": tree_rows(dialog.label_carrier_tree),
            "ui_geometry": sanitize(interpretation_dialog_geometry(dialog)),
        },
    )
    append_phase_alias(
        phases,
        "data_interpretation_confirm_metadata_labels",
        screenshots["wizard_confirm"],
        dialog,
        service,
        {"review_choices": sanitize(review_choices)},
    )
    dialog.close()

    safe_probe = data_interpretation_decision_probe(str(SOURCE_PATH), {})
    blocked_probe_path = SOURCE_DIR / "stream-export.xdf"
    blocked_probe_path.write_text("stream placeholder", encoding="utf-8")
    blocked_probe = data_interpretation_decision_probe(str(blocked_probe_path), {})

    reviewed_preview = execute_recorded(
        service,
        PreviewInterpretationCommand(
            scan_id=scan.diagnostics["scan_result"]["scan_id"],
            choices=review_choices if isinstance(review_choices, dict) else {},
        ),
        command_results,
    )
    reviewed_validation = execute_recorded(
        service,
        ValidateInterpretationCommand(),
        command_results,
    )
    apply_without_confirmation = execute_recorded(
        service,
        ApplyInterpretationCommand(),
        command_results,
    )
    apply_confirmed = execute_recorded(
        service,
        ApplyInterpretationCommand(confirmed=True),
        command_results,
    )
    save_recipe = execute_recorded(
        service,
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path)),
        command_results,
    )
    reload_recipe = execute_recorded(
        service,
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
        command_results,
    )
    tool_transcript.extend(
        command_summary(item)
        for item in [
            reviewed_preview,
            reviewed_validation,
            apply_without_confirmation,
            apply_confirmed,
            save_recipe,
            reload_recipe,
        ]
    )

    window.dataset_panel.update_panel()
    window.switch_page(0)
    app.processEvents()
    capture_step(
        "data_interpretation_decisions",
        "applied",
        notes={
            "safe": safe_probe,
            "needs_confirmation": reviewed_validation.diagnostics[
                "validation_decision"
            ],
            "blocked": blocked_probe,
            "unconfirmed_apply": command_summary(apply_without_confirmation),
            "ui_geometry": dataset_page_geometry(window),
        },
    )
    capture_step(
        "data_interpretation_apply",
        "applied",
        notes={
            "applied": command_summary(apply_confirmed),
            "recipe": command_summary(save_recipe),
            "ui_geometry": dataset_page_geometry(window),
        },
    )
    append_phase_alias(
        phases,
        "data_interpretation_save_recipe",
        screenshots["applied"],
        window,
        service,
        {"recipe": command_summary(save_recipe)},
    )
    reload_dialog = DataInterpretationPreviewDialog(
        window.dataset_panel,
        scan_result=reload_recipe.diagnostics["scan_result"],
        preview=reload_recipe.diagnostics["preview"],
        validation_decision=reload_recipe.diagnostics["validation_decision"],
    )
    reload_dialog.show()
    app.processEvents()
    capture_step(
        "data_interpretation_reload_recipe",
        "recipe_reloaded",
        widget=reload_dialog,
        notes={
            "reload": command_summary(reload_recipe),
            "review_summary_rows": tree_rows(reload_dialog.review_tree),
            "ui_geometry": sanitize(interpretation_dialog_geometry(reload_dialog)),
        },
    )
    reload_dialog.close()

    preprocess = execute_recorded(
        service,
        PreprocessCommand(
            operation=PreprocessOperation.STANDARD,
            low_freq=4.0,
            high_freq=40.0,
            method="z-score",
        ),
        command_results,
    )
    epoch = execute_recorded(
        service,
        CreateEpochCommand(t_min=0.0, t_max=1.0, event_ids=["left", "right"]),
        command_results,
    )
    dataset = execute_recorded(
        service,
        GenerateDatasetCommand(
            test_ratio=0.25,
            val_ratio=0.25,
            split_strategy="trial",
            training_mode="group",
        ),
        command_results,
    )
    tool_transcript.extend(
        command_summary(item) for item in [preprocess, epoch, dataset]
    )

    window.switch_page(1)
    app.processEvents()
    capture_step(
        "preprocessing",
        "preprocess",
        notes={"preprocess": command_summary(preprocess)},
    )
    window.switch_page(2)
    app.processEvents()
    capture_step(
        "epoch_creation",
        "dataset_ready",
        notes={
            "epoch": command_summary(epoch),
            "dataset": command_summary(dataset),
        },
    )
    append_phase_alias(
        phases,
        "dataset_generation",
        screenshots["dataset_ready"],
        window.training_panel,
        service,
        {"dataset": command_summary(dataset)},
    )

    configure_training = execute_recorded(
        service,
        ConfigureTrainingCommand(
            model_name="EEGNet",
            epoch=1,
            batch_size=2,
            learning_rate=0.001,
            device="cpu",
            output_dir=str(output_dir / "training-smoke-output"),
        ),
        command_results,
    )
    evaluate = execute_recorded(service, EvaluateCommand(), command_results)
    visualize = execute_recorded(service, VisualizeCommand(), command_results)
    saliency = execute_recorded(service, SaliencyCommand(), command_results)
    tool_transcript.extend(
        command_summary(item)
        for item in [configure_training, evaluate, visualize, saliency]
    )
    window.switch_page(2)
    app.processEvents()
    capture_step(
        "training_readiness",
        "training_readiness",
        notes={"training": command_summary(configure_training)},
    )
    window.switch_page(3)
    app.processEvents()
    capture_step(
        "evaluation_visualization_saliency_readiness",
        "analysis_readiness",
        notes={
            "evaluate": command_summary(evaluate),
            "visualize": command_summary(visualize),
            "saliency": command_summary(saliency),
        },
    )

    chat_payload = run_chatpanel_walkthrough(
        app,
        window,
        service,
        screenshots,
        phases,
        output_dir,
        user_transcript,
        tool_transcript,
    )

    new_session_blocked = execute_recorded(
        service,
        NewSessionCommand(),
        command_results,
    )
    new_session_confirmed = execute_recorded(
        service,
        NewSessionCommand(confirmed=True),
        command_results,
    )
    tool_transcript.extend(
        command_summary(item) for item in [new_session_blocked, new_session_confirmed]
    )
    window.dataset_panel.update_panel()
    window.agent_manager.refresh_backend_status()
    window.switch_page(0)
    app.processEvents()
    capture_step(
        "reset_new_session_boundary",
        "reset_boundary",
        notes={
            "unconfirmed": command_summary(new_session_blocked),
            "confirmed": command_summary(new_session_confirmed),
        },
    )

    preview_missing_scan = execute_recorded(
        service,
        PreviewInterpretationCommand(),
        command_results,
    )
    recovery_scan = execute_recorded(
        service,
        ScanSourceCommand(source_path=str(source_path.parent)),
        command_results,
    )
    tool_transcript.extend(
        command_summary(item) for item in [preview_missing_scan, recovery_scan]
    )
    window.agent_manager.refresh_backend_status()
    add_chat_message(
        window,
        user_transcript,
        "user",
        "Preview the selected data again.",
    )
    add_chat_message(
        window,
        user_transcript,
        "assistant",
        "I need a source scan before previewing. I scanned the selected source again.",
    )
    app.processEvents()
    capture_step(
        "error_recovery",
        "error_recovery",
        notes={
            "blocked_preview": command_summary(preview_missing_scan),
            "recovery_scan": command_summary(recovery_scan),
        },
    )

    dashboard_shot = capture_eval_dashboard(output_dir)
    screenshots["eval_dashboard"] = str(dashboard_shot)
    phases.append(
        {
            "phase": "eval_dashboard_report",
            "screenshot": str(dashboard_shot),
            "visible_text": ["XBrainLab Evaluation Dashboard Report"],
            "button_state": [],
            "workflow_state": compact_state(service.get_state()),
            "notes": {
                "dashboard": "artifacts/agent_evals/dashboard.md",
                "claim_boundary": "Tool-call benchmark evidence only.",
            },
        }
    )

    resource_notes.append(resource_snapshot("before_close"))
    window.close()
    app.processEvents()
    gc.collect()
    resource_notes.append(resource_snapshot("after_close"))

    pass_fail_summary = build_pass_fail_summary(
        phases,
        screenshots,
        resource_notes=resource_notes,
    )
    observable_evidence = build_observable_evidence_summary(phases)
    ui_quality_review = build_ui_quality_review(phases, screenshots)
    pass_fail_summary = merge_ui_quality_into_pass_fail_summary(
        pass_fail_summary,
        ui_quality_review,
    )
    status = "passed" if pass_fail_summary["passed"] else "failed"
    return {
        "status": status,
        "failure_reason": ""
        if status == "passed"
        else "; ".join(pass_fail_summary["failed_checks"]),
        "claim_boundary": claim_boundary(),
        "source_path": sanitize_path(str(source_path.parent)),
        "recipe_path": str(recipe_path),
        "phases": phases,
        "screenshots": screenshots,
        "observable_evidence": observable_evidence,
        "command_results": command_results,
        "tool_transcript": tool_transcript,
        "user_facing_message_transcript": user_transcript,
        "chatpanel": chat_payload,
        "final_state": compact_state(service.get_state()),
        "resource_notes": resource_notes,
        "ui_quality_review": ui_quality_review,
        "pass_fail_summary": pass_fail_summary,
        "elapsed_seconds": round(time.monotonic() - started_at, 3),
    }


def run_chatpanel_walkthrough(
    app: QApplication,
    window: MainWindow,
    service: Any,
    screenshots: dict[str, str],
    phases: list[dict[str, Any]],
    output_dir: Path,
    user_transcript: list[dict[str, str]],
    tool_transcript: list[dict[str, Any]],
) -> dict[str, Any]:
    """Drive user-visible ChatPanel states without starting a local model."""
    manager = window.agent_manager
    panel = manager.chat_panel
    dock = manager.chat_dock
    if panel is None or dock is None:
        raise RuntimeError("ChatPanel was not initialized.")

    open_close_states: list[dict[str, Any]] = []
    dock.show()
    app.processEvents()
    for index in range(2):
        open_close_states.append(
            {"step": f"open-{index + 1}", "visible": dock.isVisible()}
        )
        dock.close()
        app.processEvents()
        open_close_states.append(
            {"step": f"close-{index + 1}", "visible": dock.isVisible()}
        )
        dock.show()
        app.processEvents()
    screenshots["assistant_empty"] = capture_named(
        panel,
        output_dir,
        "assistant_empty",
    )
    phases.append(
        chat_phase(
            "assistant_empty_state",
            screenshots["assistant_empty"],
            panel,
            service,
            {"open_close": open_close_states},
        )
    )
    phases.append(
        chat_phase(
            "assistant_repeated_open_close",
            screenshots["assistant_empty"],
            panel,
            service,
            {"open_close": open_close_states},
        )
    )

    add_chat_message(window, user_transcript, "user", "Hello.")
    add_chat_message(
        window,
        user_transcript,
        "assistant",
        "I can help interpret EEG data and prepare a training-ready dataset.",
    )
    app.processEvents()
    screenshots["assistant_normal"] = capture_named(
        panel,
        output_dir,
        "assistant_normal",
    )
    phases.append(
        chat_phase(
            "assistant_normal_message",
            screenshots["assistant_normal"],
            panel,
            service,
            {},
        )
    )

    add_chat_message(window, user_transcript, "user", "Load my brainwave data.")
    add_chat_message(
        window,
        user_transcript,
        "assistant",
        "Choose a file, folder, BIDS root, or saved recipe before I can scan it.",
    )
    app.processEvents()
    screenshots["assistant_clarification"] = capture_named(
        panel,
        output_dir,
        "assistant_clarification",
    )
    phases.append(
        chat_phase(
            "assistant_missing_input_clarification",
            screenshots["assistant_clarification"],
            panel,
            service,
            {"clarification": "missing source path"},
        )
    )

    add_chat_message(window, user_transcript, "user", "Train it now.")
    add_chat_message(
        window,
        user_transcript,
        "assistant",
        "Training is not ready until data, epochs, a dataset, a model, and settings are ready.",
    )
    app.processEvents()
    screenshots["assistant_blocked"] = capture_named(
        panel,
        output_dir,
        "assistant_blocked",
    )
    phases.append(
        chat_phase(
            "assistant_blocked_command",
            screenshots["assistant_blocked"],
            panel,
            service,
            {"blocked_reason": "training readiness boundary"},
        )
    )

    query_state = service.execute(QueryStateCommand())
    tool_transcript.append(command_summary(query_state))
    add_chat_message(window, user_transcript, "user", "What is ready now?")
    add_chat_message(
        window,
        user_transcript,
        "assistant",
        "The dataset and training settings are ready; evaluation needs a completed run.",
    )
    app.processEvents()
    screenshots["assistant_success"] = capture_named(
        panel,
        output_dir,
        "assistant_success",
    )
    phases.append(
        chat_phase(
            "assistant_successful_tool_result",
            screenshots["assistant_success"],
            panel,
            service,
            {"query_state": command_summary(query_state)},
        )
    )

    set_window_geometry(window, NARROW_WINDOW_SIZE)
    dock.setMinimumWidth(320)
    dock.resize(340, max(620, window.height() - 80))
    app.processEvents()
    screenshots["assistant_narrow"] = capture_named(
        panel,
        output_dir,
        "assistant_narrow",
    )
    phases.append(
        chat_phase(
            "assistant_narrow_panel",
            screenshots["assistant_narrow"],
            panel,
            service,
            {"width": window.width(), "dock_width": dock.width()},
        )
    )
    set_window_geometry(window, WINDOW_SIZE)
    app.processEvents()

    visible_messages = [message.__dict__ for message in collect_visible_messages(panel)]
    send_button_text = panel.send_btn.text()
    send_button_enabled = panel.send_btn.isEnabled()
    input_enabled = panel.input_field.isEnabled()
    processing = manager.chat_controller.is_processing

    manager.start_new_conversation()
    app.processEvents()
    return {
        "open_close_states": open_close_states,
        "visible_messages": visible_messages,
        "send_button_text": send_button_text,
        "send_button_enabled": send_button_enabled,
        "input_enabled": input_enabled,
        "processing": processing,
    }


def apply_review_choices(dialog: DataInterpretationPreviewDialog) -> None:
    """Apply deterministic human-like review choices to the wizard."""
    apply_replay_review_choices(dialog)


def dataset_page_geometry(window: MainWindow) -> dict[str, Any]:
    """Return geometry evidence for the Dataset page main table and sidebar summary."""
    return {
        "dataset_table": table_state(
            window.dataset_panel.table,
            panel=window.dataset_panel,
            right_boundary=window.dataset_panel.sidebar,
        ),
        "aggregate_info": table_state(
            window.dataset_panel.sidebar.info_panel.table,
            panel=window.dataset_panel.sidebar.info_panel,
        ),
    }


def interpretation_dialog_geometry(
    dialog: DataInterpretationPreviewDialog,
) -> dict[str, Any]:
    """Return table/tree geometry evidence for Data Interpretation review panes."""
    return {
        "metadata": tree_state(dialog.file_tree),
        "label_carriers": tree_state(dialog.label_carrier_tree),
        "events": tree_state(dialog.event_tree),
        "review_summary": tree_state(dialog.review_tree),
    }


def data_interpretation_decision_probe(
    source_path: str,
    choices: dict[str, Any],
) -> dict[str, Any]:
    """Probe one decision boundary on a separate service."""
    service = ApplicationService(Study())
    scan = service.execute(ScanSourceCommand(source_path=source_path))
    preview = service.execute(PreviewInterpretationCommand(choices=choices))
    validation = service.execute(ValidateInterpretationCommand())
    return {
        "scan": command_summary(scan),
        "preview": command_summary(preview),
        "validation": validation.diagnostics.get("validation_decision", {}),
    }


def execute_recorded(
    service: ApplicationService,
    command: Any,
    command_results: list[dict[str, Any]],
) -> CommandResult:
    """Execute a command and append a sanitized CommandResult payload."""
    result = service.execute(command)
    command_results.append(sanitize(result.to_dict()))
    return result


def command_summary(result: CommandResult) -> dict[str, Any]:
    """Return a compact command/tool transcript row."""
    return {
        "command": result.command_name,
        "ok": result.ok,
        "status": result.status.value,
        "message": result.message,
        "error_type": result.error_type.value,
        "error_message": result.error_message,
        "changed_state": result.changed_state.to_dict(),
        "diagnostics_keys": sorted(result.diagnostics.keys()),
    }


def add_chat_message(
    window: MainWindow,
    transcript: list[dict[str, str]],
    role: str,
    text: str,
) -> None:
    """Add a visible ChatPanel message through the real ChatController."""
    controller = window.agent_manager.chat_controller
    if role == "user":
        controller.add_user_message(text)
    else:
        controller.add_agent_message(text)
    transcript.append({"role": role, "text": text})


def chat_phase(
    phase: str,
    screenshot: str,
    panel: QWidget,
    service: ApplicationService,
    notes: dict[str, Any],
) -> dict[str, Any]:
    """Build a ChatPanel phase payload."""
    return {
        "phase": phase,
        "screenshot": screenshot,
        "visible_text": visible_text_snapshot(panel),
        "button_state": button_state_snapshot(panel),
        "workflow_state": compact_state(service.get_state()),
        "notes": notes,
    }


def append_phase_alias(
    phases: list[dict[str, Any]],
    phase: str,
    screenshot: str,
    widget: QWidget,
    service: ApplicationService,
    notes: dict[str, Any],
) -> None:
    """Append an additional acceptance phase backed by an existing screenshot."""
    phases.append(
        {
            "phase": phase,
            "screenshot": screenshot,
            "visible_text": visible_text_snapshot(widget),
            "button_state": button_state_snapshot(widget),
            "workflow_state": compact_state(service.get_state()),
            "notes": notes,
        }
    )


def capture_eval_dashboard(output_dir: Path) -> Path:
    """Render the eval dashboard into a product-style screenshot artifact."""
    dashboard_path = ROOT / "artifacts" / "agent_evals" / "dashboard.md"
    text = (
        dashboard_path.read_text(encoding="utf-8")
        if dashboard_path.exists()
        else "# XBrainLab Tool-Call Eval Dashboard\n\nDashboard artifact missing.\n"
    )
    widget = QTextBrowser()
    widget.setWindowTitle("XBrainLab Tool-Call Eval Dashboard")
    widget.setHtml(render_eval_dashboard_html(text[:12000]))
    widget.resize(1000, 760)
    widget.show()
    QApplication.processEvents()
    screenshot_path = output_dir / SCREENSHOT_NAMES["eval_dashboard"]
    capture_widget(widget, screenshot_path)
    widget.close()
    return screenshot_path


def render_eval_dashboard_html(markdown_text: str) -> str:
    """Convert the saved eval dashboard Markdown into compact review HTML."""
    lines = markdown_text.splitlines()
    claim_boundary = _extract_markdown_list_section(lines, "Thesis Claim Boundary")
    body: list[str] = []
    index = 0
    in_list = False
    claim_boundary_inserted = False
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.strip()
        if not line:
            if in_list:
                body.append("</ul>")
                in_list = False
            index += 1
            continue
        if (
            line.startswith("|")
            and index + 1 < len(lines)
            and _is_markdown_table_separator(lines[index + 1])
        ):
            if in_list:
                body.append("</ul>")
                in_list = False
            table_html, index = _render_markdown_table(lines, index)
            body.append(table_html)
            continue
        if line.startswith("#"):
            if in_list:
                body.append("</ul>")
                in_list = False
            level = min(max(len(line) - len(line.lstrip("#")), 1), 3)
            heading = line[level:].strip()
            if heading == "Thesis Claim Boundary" and claim_boundary:
                index = _skip_markdown_section(lines, index)
                continue
            body.append(f"<h{level}>{_format_inline_markdown(heading)}</h{level}>")
            if level == 1 and claim_boundary and not claim_boundary_inserted:
                body.append(_render_claim_boundary(claim_boundary))
                claim_boundary_inserted = True
            index += 1
            continue
        if line.startswith("- "):
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{_format_inline_markdown(line[2:].strip())}</li>")
            index += 1
            continue
        if in_list:
            body.append("</ul>")
            in_list = False
        body.append(f"<p>{_format_inline_markdown(line)}</p>")
        index += 1
    if in_list:
        body.append("</ul>")
    if claim_boundary and not claim_boundary_inserted:
        body.insert(0, _render_claim_boundary(claim_boundary))
    return f"""
    <html>
    <head>
      <style>
        body {{
          background: #181818;
          color: #d8dee9;
          font-family: "Segoe UI", "Inter", sans-serif;
          font-size: 13px;
          margin: 18px;
        }}
        h1 {{
          color: #f2f6fb;
          font-size: 22px;
          margin: 0 0 14px;
        }}
        h2 {{
          color: #f2f6fb;
          font-size: 16px;
          margin: 22px 0 8px;
          border-top: 1px solid #31363d;
          padding-top: 14px;
        }}
        h3 {{
          color: #d8dee9;
          font-size: 14px;
          margin: 16px 0 8px;
        }}
        p, li {{
          color: #c7d0da;
          line-height: 1.35;
        }}
        table {{
          border-collapse: collapse;
          width: 100%;
          margin: 8px 0 14px;
          background: #202020;
          border: 1px solid #353b43;
        }}
        th {{
          background: #2c3036;
          color: #b9c5d2;
          font-weight: 600;
          text-align: left;
          padding: 7px 8px;
          border-bottom: 1px solid #3d444e;
        }}
        td {{
          color: #e1e7ef;
          padding: 6px 8px;
          border-top: 1px solid #2a2f35;
        }}
        tr:nth-child(even) td {{
          background: #232323;
        }}
        code {{
          color: #d7e8ff;
          background: #26313a;
          padding: 1px 4px;
          border-radius: 3px;
        }}
        .claim-boundary {{
          background: #202020;
          border: 1px solid #44413a;
          border-left: 4px solid #c7a75a;
          margin: 10px 0 18px;
          padding: 10px 12px;
        }}
        .claim-boundary h2 {{
          border-top: 0;
          color: #f2f6fb;
          font-size: 15px;
          margin: 0 0 6px;
          padding-top: 0;
        }}
        .claim-boundary ul {{
          margin: 0;
          padding-left: 18px;
        }}
      </style>
    </head>
    <body>
      {"".join(body)}
    </body>
    </html>
    """


def _render_claim_boundary(items: list[str]) -> str:
    item_html = "".join(f"<li>{_format_inline_markdown(item)}</li>" for item in items)
    return f'<section class="claim-boundary"><h2>Claim Boundary</h2><ul>{item_html}</ul></section>'


def _extract_markdown_list_section(lines: list[str], heading: str) -> list[str]:
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        level = len(stripped) - len(stripped.lstrip("#"))
        if stripped[level:].strip() != heading:
            continue
        items: list[str] = []
        section_index = index + 1
        while section_index < len(lines):
            section_line = lines[section_index].strip()
            if section_line.startswith("#"):
                break
            if section_line.startswith("- "):
                items.append(section_line[2:].strip())
            section_index += 1
        return items
    return []


def _skip_markdown_section(lines: list[str], start_index: int) -> int:
    index = start_index + 1
    while index < len(lines):
        line = lines[index].strip()
        if line.startswith("#"):
            return index
        index += 1
    return index


def _render_markdown_table(lines: list[str], start_index: int) -> tuple[str, int]:
    headers = _split_markdown_table_row(lines[start_index])
    index = start_index + 2
    rows: list[list[str]] = []
    while index < len(lines) and lines[index].strip().startswith("|"):
        rows.append(_split_markdown_table_row(lines[index]))
        index += 1
    header_html = "".join(
        f"<th>{_format_inline_markdown(cell)}</th>" for cell in headers
    )
    row_html = "".join(
        "<tr>"
        + "".join(f"<td>{_format_inline_markdown(cell)}</td>" for cell in row)
        + "</tr>"
        for row in rows
    )
    return (
        f"<table><thead><tr>{header_html}</tr></thead>"
        f"<tbody>{row_html}</tbody></table>",
        index,
    )


def _split_markdown_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_markdown_table_separator(line: str) -> bool:
    cells = _split_markdown_table_row(line)
    return bool(cells) and all(
        set(cell.replace(" ", "")) <= {"-", ":"} for cell in cells
    )


def _format_inline_markdown(text: str) -> str:
    escaped = escape(text)
    parts = escaped.split("`")
    if len(parts) == 1:
        return escaped
    formatted: list[str] = []
    for index, part in enumerate(parts):
        if index % 2 == 1:
            formatted.append(f"<code>{part}</code>")
        else:
            formatted.append(part)
    return "".join(formatted)


def capture_named(window: QWidget, output_dir: Path, key: str) -> str:
    """Capture a named screenshot and return its path."""
    path = output_dir / SCREENSHOT_NAMES[key]
    capture_widget(window, path)
    return str(path)


def capture_widget(widget: QWidget, output_path: Path) -> None:
    """Capture a nonblank widget screenshot."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pixmap = widget.grab()
    if pixmap.isNull():
        raise RuntimeError(f"Could not grab screenshot for {output_path.name}.")
    if not pixmap.save(str(output_path)):
        raise RuntimeError(f"Could not save screenshot {output_path}.")
    if is_nearly_black(output_path):
        raise RuntimeError(f"Screenshot is nearly black: {output_path}.")


def is_nearly_black(path: Path) -> bool:
    """Return whether an image contains almost no visible content."""
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        histogram = rgb.histogram()
    total_pixels = sum(histogram[:256])
    bright_pixels = 0
    for value in range(16, 256):
        bright_pixels += histogram[value]
        bright_pixels += histogram[256 + value]
        bright_pixels += histogram[512 + value]
    return total_pixels == 0 or bright_pixels < total_pixels * 0.01


def visible_text_snapshot(widget: QWidget) -> list[str]:
    """Collect user-visible text from common widgets."""
    texts: list[str] = []
    for child in widget.findChildren(QWidget):
        if not child.isVisible():
            continue
        text = ""
        if isinstance(child, QLabel | QAbstractButton):
            text = child.text()
        elif isinstance(child, QLineEdit):
            text = child.text() or child.placeholderText()
        elif isinstance(child, QComboBox):
            text = child.currentText()
        elif isinstance(child, QTextBrowser):
            text = child.toPlainText()
        if text:
            normalized = " ".join(str(text).split())
            if normalized and normalized not in texts:
                texts.append(normalized)
    return texts[:160]


def button_state_snapshot(widget: QWidget) -> list[dict[str, Any]]:
    """Collect visible button labels and enabled states."""
    states: list[dict[str, Any]] = []
    for button in widget.findChildren(QAbstractButton):
        if not button.isVisible():
            continue
        text = " ".join(str(button.text() or button.toolTip() or "").split())
        if not text:
            continue
        states.append(
            {
                "text": text,
                "enabled": button.isEnabled(),
                "checked": button.isChecked() if button.isCheckable() else None,
                "tooltip": " ".join(str(button.toolTip()).split()),
            }
        )
    return states[:120]


def compact_state(state: ApplicationStateSnapshot) -> dict[str, Any]:
    """Return a compact workflow state snapshot."""
    data = state.to_dict()
    return {
        "pipeline_stage": data["pipeline_stage"],
        "raw": {
            "loaded": data["raw"]["loaded"],
            "count": data["raw"]["count"],
            "files": data["raw"]["files"],
        },
        "preprocessed": {
            "available": data["preprocessed"]["available"],
            "count": data["preprocessed"]["count"],
            "operations": data["preprocessed"]["operations"],
        },
        "epoch": {
            "exists": data["epoch"]["exists"],
            "epoch_count": data["epoch"]["epoch_count"],
            "event_names": data["epoch"]["event_names"],
        },
        "dataset": {
            "available": data["dataset"]["available"],
            "count": data["dataset"]["count"],
        },
        "training": {
            "has_model": data["training"]["has_model"],
            "model_name": data["training"]["model_name"],
            "has_training_option": data["training"]["has_training_option"],
            "has_trainer": data["training"]["has_trainer"],
            "is_running": data["training"]["is_running"],
            "finished_run_count": data["training"]["finished_run_count"],
        },
        "evaluation": data["evaluation"],
        "visualization": data["visualization"],
        "interpretation": {
            "has_scan_result": data["interpretation"]["has_scan_result"],
            "has_preview": data["interpretation"]["has_preview"],
            "has_validation_decision": data["interpretation"][
                "has_validation_decision"
            ],
            "has_applied_interpretation": data["interpretation"][
                "has_applied_interpretation"
            ],
            "has_recipe": data["interpretation"]["has_recipe"],
            "validation_decision": data["interpretation"]["validation_decision"],
            "pending_confirmation": data["interpretation"]["pending_confirmation"],
            "recipe_path": sanitize_path(str(data["interpretation"]["recipe_path"])),
        },
    }


def build_pass_fail_summary(
    phases: list[dict[str, Any]],
    screenshots: dict[str, str],
    *,
    resource_notes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate the artifact against the walkthrough acceptance checklist."""
    failed: list[str] = []
    phase_names = {phase.get("phase") for phase in phases}
    for required in REQUIRED_PHASES:
        if required not in phase_names:
            failed.append(f"missing phase: {required}")
    for key, path in screenshots.items():
        if not Path(path).exists():
            failed.append(f"missing screenshot: {key}")
            continue
        if is_nearly_black(Path(path)):
            failed.append(f"nearly black screenshot: {key}")
    for phase in phases:
        forbidden = forbidden_visible_text(phase.get("visible_text", []))
        if forbidden:
            failed.append(f"{phase.get('phase')} exposes internal text: {forbidden}")
        if "button_state" not in phase:
            failed.append(f"{phase.get('phase')} is missing button state")
        if "workflow_state" not in phase:
            failed.append(f"{phase.get('phase')} is missing workflow state")
    resource_smoke = build_resource_smoke_summary(resource_notes)
    failed.extend(resource_smoke["failed_checks"])
    return {
        "passed": not failed,
        "failed_checks": failed,
        "required_phase_count": len(REQUIRED_PHASES),
        "observed_phase_count": len(phase_names),
        "screenshot_count": len(screenshots),
        "human_desktop_acceptance": "not performed",
        "resource_smoke": resource_smoke,
    }


def build_resource_smoke_summary(
    resource_notes: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Check for obvious thread or RSS regressions in the automated replay."""
    boundary = (
        "Coarse process smoke only: RSS uses ru_maxrss high-water mark and this "
        "does not prove the absence of leaks."
    )
    if resource_notes is None:
        return {
            "checked": False,
            "passed": True,
            "failed_checks": [],
            "boundary": boundary,
        }

    start = _resource_note(resource_notes, "start")
    after_close = _resource_note(resource_notes, "after_close")
    failed: list[str] = []
    if start is None or after_close is None:
        failed.append("resource notes missing start/after_close snapshots")
        return {
            "checked": True,
            "passed": False,
            "failed_checks": failed,
            "boundary": boundary,
        }

    start_threads = _resource_int(start, "python_threads")
    after_threads = _resource_int(after_close, "python_threads")
    after_qt_threads = _resource_int(after_close, "qt_active_threads")
    rss_growth_kb = _resource_int(after_close, "max_rss_kb") - _resource_int(
        start, "max_rss_kb"
    )

    if after_threads > start_threads + RESOURCE_THREAD_TOLERANCE:
        failed.append(
            "Python threads did not settle: "
            f"start {start_threads}, after_close {after_threads}."
        )
    if after_qt_threads > 0:
        failed.append(f"Qt thread pool still active after close: {after_qt_threads}.")
    if rss_growth_kb > RESOURCE_RSS_SMOKE_LIMIT_KB:
        failed.append(
            "RSS smoke delta exceeded "
            f"{RESOURCE_RSS_SMOKE_LIMIT_KB} KB: {rss_growth_kb} KB."
        )

    return {
        "checked": True,
        "passed": not failed,
        "failed_checks": failed,
        "start_python_threads": start_threads,
        "after_close_python_threads": after_threads,
        "python_thread_tolerance": RESOURCE_THREAD_TOLERANCE,
        "after_close_qt_active_threads": after_qt_threads,
        "rss_growth_kb": rss_growth_kb,
        "rss_limit_kb": RESOURCE_RSS_SMOKE_LIMIT_KB,
        "boundary": boundary,
    }


def merge_ui_quality_into_pass_fail_summary(
    summary: dict[str, Any],
    ui_quality_review: dict[str, Any],
) -> dict[str, Any]:
    """Fold automated UI quality checks into the walkthrough status summary."""
    merged = dict(summary)
    failed_checks = list(merged.get("failed_checks", []))
    if not ui_quality_review.get("automated_checks_passed"):
        failed_checks.append("ui quality review did not pass")
    merged["failed_checks"] = failed_checks
    merged["passed"] = bool(merged.get("passed")) and not failed_checks
    return merged


def _resource_note(
    resource_notes: list[dict[str, Any]],
    label: str,
) -> dict[str, Any] | None:
    return next(
        (note for note in resource_notes if str(note.get("label", "")) == label),
        None,
    )


def _resource_int(note: dict[str, Any], key: str) -> int:
    try:
        return int(note.get(key, 0))
    except (TypeError, ValueError):
        return 0


def build_observable_evidence_summary(
    phases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Index per-phase UI evidence so reviewers do not need to mine raw phases."""
    visible_text: dict[str, list[str]] = {}
    button_states: dict[str, list[dict[str, Any]]] = {}
    workflow_states: dict[str, dict[str, Any]] = {}
    backend_snapshots: dict[str, dict[str, Any]] = {}
    phase_screenshots: dict[str, str] = {}
    ui_geometry: dict[str, dict[str, Any]] = {}
    for phase in phases:
        name = str(phase.get("phase", ""))
        if not name:
            continue
        visible_text[name] = list(phase.get("visible_text", []))
        button_states[name] = list(phase.get("button_state", []))
        workflow_state = dict(phase.get("workflow_state", {}))
        workflow_states[name] = workflow_state
        backend_snapshots[name] = workflow_state
        phase_screenshots[name] = str(phase.get("screenshot", ""))
        notes = phase.get("notes", {})
        if isinstance(notes, dict) and isinstance(notes.get("ui_geometry"), dict):
            ui_geometry[name] = dict(notes["ui_geometry"])
    return {
        "visible_text_snapshots": visible_text,
        "button_states": button_states,
        "workflow_states": workflow_states,
        "backend_state_snapshots": backend_snapshots,
        "phase_screenshots": phase_screenshots,
        "ui_geometry_snapshots": ui_geometry,
    }


def build_ui_quality_review(
    phases: list[dict[str, Any]],
    screenshots: dict[str, str],
) -> dict[str, Any]:
    """Return automated UI quality checks and explicit human-review boundary."""
    screenshot_rows: list[dict[str, Any]] = []
    for key, path_text in screenshots.items():
        path = Path(path_text)
        exists = path.exists()
        nearly_black = is_nearly_black(path) if exists else True
        screenshot_rows.append(
            {
                "screenshot": key,
                "path": path_text,
                "exists": exists,
                "nonblank": exists and not nearly_black,
                "automated_review": "nonblank"
                if exists and not nearly_black
                else "failed",
            }
        )
    forbidden_rows = [
        {
            "phase": phase.get("phase"),
            "offenders": forbidden_visible_text(phase.get("visible_text", [])),
        }
        for phase in phases
    ]
    forbidden_rows = [row for row in forbidden_rows if row["offenders"]]
    all_phases_have_snapshots = all(
        "visible_text" in phase
        and "button_state" in phase
        and "workflow_state" in phase
        and phase.get("screenshot")
        for phase in phases
    )
    table_geometry_review = build_table_geometry_review(phases)
    return {
        "automated_checks_passed": not forbidden_rows
        and all(row["nonblank"] for row in screenshot_rows)
        and all_phases_have_snapshots
        and table_geometry_review["passed"],
        "screenshot_review": screenshot_rows,
        "forbidden_visible_text": forbidden_rows,
        "phase_snapshot_coverage": all_phases_have_snapshots,
        "table_geometry_review": table_geometry_review,
        "visible_text_boundary": (
            "Checks visible widget text for raw tool syntax, schema, traceback, "
            "selected snake_case command leakage, and recipe trace tokens."
        ),
        "human_design_review_boundary": (
            "This is automated UI-observable evidence. It does not replace a "
            "human desktop review of Windows launcher, dual-monitor/DPI, or "
            "long local-model sessions."
        ),
    }


def build_table_geometry_review(phases: list[dict[str, Any]]) -> dict[str, Any]:
    """Check table/tree geometry evidence for obvious overflow or underfill."""
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for phase in phases:
        phase_name = str(phase.get("phase", ""))
        notes = phase.get("notes", {})
        if not isinstance(notes, dict):
            continue
        for widget_name, state in iter_geometry_states(notes.get("ui_geometry")):
            header_length = geometry_int(state, "header_length")
            viewport_width = geometry_int(state, "viewport_width")
            if header_length <= 0 or viewport_width <= 0:
                continue
            horizontal_scrollbar_max = geometry_int(state, "horizontal_scrollbar_max")
            width_gap = viewport_width - header_length
            has_right_boundary = "right_gap_to_boundary" in state
            right_gap_to_boundary = (
                geometry_int(state, "right_gap_to_boundary")
                if has_right_boundary
                else 0
            )
            partial_visible_rows = geometry_int_list(state, "partial_visible_rows")
            fits_panel = (
                header_length <= viewport_width + GEOMETRY_WIDTH_TOLERANCE_PX
                and horizontal_scrollbar_max == 0
            )
            fills_panel = width_gap <= GEOMETRY_WIDTH_TOLERANCE_PX
            fills_content_boundary = (
                not has_right_boundary
                or abs(right_gap_to_boundary) <= GEOMETRY_WIDTH_TOLERANCE_PX
            )
            shows_only_complete_rows = not partial_visible_rows
            row = {
                "phase": phase_name,
                "widget": widget_name,
                "headers": list(state.get("headers", [])),
                "row_count": len(state.get("rows", []))
                if isinstance(state.get("rows"), list)
                else 0,
                "header_length": header_length,
                "viewport_width": viewport_width,
                "width_gap": width_gap,
                "widget_width": geometry_int(state, "widget_width"),
                "panel_width": geometry_int(state, "panel_width"),
                "table_right_x": geometry_int(state, "table_right_x"),
                "right_boundary_x": geometry_int(state, "right_boundary_x"),
                "right_gap_to_boundary": right_gap_to_boundary,
                "horizontal_scrollbar_max": horizontal_scrollbar_max,
                "vertical_scrollbar_max": geometry_int(
                    state,
                    "vertical_scrollbar_max",
                ),
                "partial_visible_rows": partial_visible_rows,
                "fits_panel": fits_panel,
                "fills_panel": fills_panel,
                "fills_content_boundary": fills_content_boundary,
                "shows_only_complete_rows": shows_only_complete_rows,
                "resize_modes": list(state.get("resize_modes", [])),
                "column_widths": list(state.get("column_widths", [])),
                "text_elide_mode": state.get("text_elide_mode"),
                "alternating_row_colors": state.get("alternating_row_colors"),
            }
            rows.append(row)
            if (
                not fits_panel
                or not fills_panel
                or not fills_content_boundary
                or not shows_only_complete_rows
            ):
                findings.append(row)
    clipped_row_findings = [
        row for row in findings if not row.get("shows_only_complete_rows", True)
    ]
    return {
        "passed": bool(rows) and not findings,
        "checked_widgets": len(rows),
        "width_tolerance_px": GEOMETRY_WIDTH_TOLERANCE_PX,
        "findings": findings,
        "clipped_row_findings": clipped_row_findings,
        "rows": rows,
        "boundary": (
            "Automated geometry smoke checks header length, viewport width, "
            "horizontal scrollbar state, table-to-content-boundary gaps, and "
            "whether visible rows are clipped at the viewport edge. Human review "
            "still decides visual polish."
        ),
    }


def iter_geometry_states(
    value: Any,
    prefix: str = "",
) -> list[tuple[str, dict[str, Any]]]:
    """Flatten nested UI geometry maps into named widget states."""
    if not isinstance(value, dict):
        return []
    if "header_length" in value and "viewport_width" in value:
        return [(prefix or "widget", value)]
    rows: list[tuple[str, dict[str, Any]]] = []
    for key, item in value.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        rows.extend(iter_geometry_states(item, name))
    return rows


def geometry_int(state: dict[str, Any], key: str) -> int:
    """Read an integer geometry field from an artifact row."""
    try:
        return int(state.get(key, 0))
    except (TypeError, ValueError):
        return 0


def geometry_int_list(state: dict[str, Any], key: str) -> list[int]:
    """Read a list of integer geometry fields from an artifact row."""
    value = state.get(key, [])
    if not isinstance(value, list):
        return []
    rows: list[int] = []
    for item in value:
        try:
            rows.append(int(item))
        except (TypeError, ValueError):
            continue
    return rows


def forbidden_visible_text(texts: list[str]) -> list[str]:
    """Return visible text entries that expose raw internal syntax."""
    offenders: list[str] = []
    for text in texts:
        normalized = str(text)
        lowered = normalized.lower()
        if any(marker.lower() in lowered for marker in VISIBLE_FORBIDDEN):
            offenders.append(normalized)
            continue
        if VISIBLE_TRACE_TOKEN_PATTERN.search(normalized):
            offenders.append(normalized)
            continue
        if re.search(r"\b(tool|schema|traceback)\b", lowered):
            offenders.append(normalized)
    return offenders


def validate_walkthrough_payload(
    payload: dict[str, Any],
    *,
    require_files: bool = True,
) -> tuple[bool, str]:
    """Validate a human-like walkthrough payload."""
    if payload.get("status") != "passed":
        return False, str(payload.get("failure_reason") or "status is not passed")
    summary = payload.get("pass_fail_summary", {})
    if not summary.get("passed"):
        return False, "; ".join(summary.get("failed_checks", []))
    phases = {phase.get("phase") for phase in payload.get("phases", [])}
    missing = [phase for phase in REQUIRED_PHASES if phase not in phases]
    if missing:
        return False, f"missing phases: {', '.join(missing)}"
    if require_files:
        for path in payload.get("screenshots", {}).values():
            if not Path(path).exists():
                return False, f"missing screenshot file: {path}"
    if not payload.get("observable_evidence"):
        return False, "observable evidence summary is missing"
    if not payload.get("ui_quality_review"):
        return False, "ui quality review is missing"
    if not payload["ui_quality_review"].get("automated_checks_passed"):
        return False, "ui quality review did not pass"
    geometry_review = payload["ui_quality_review"].get("table_geometry_review", {})
    if not geometry_review.get("passed"):
        return False, "table geometry review did not pass"
    if "not human Windows desktop acceptance" not in payload.get(
        "claim_boundary",
        "",
    ):
        return False, "claim boundary does not distinguish human acceptance"
    return True, ""


def resource_snapshot(label: str) -> dict[str, Any]:
    """Return lightweight process/thread notes."""
    pool = QThreadPool.globalInstance()
    return {
        "label": label,
        "pid": os.getpid(),
        "python_threads": threading.active_count(),
        "thread_names": [thread.name for thread in threading.enumerate()[:12]],
        "qt_active_threads": pool.activeThreadCount() if pool is not None else 0,
        "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }


def set_window_geometry(window: QWidget, size: QSize) -> None:
    """Set deterministic capture geometry."""
    window.setWindowState(Qt.WindowState.WindowNoState)
    screen = window.screen() or QApplication.primaryScreen()
    if screen is not None:
        window.move(screen.availableGeometry().topLeft())
    else:
        window.move(QPoint(0, 0))
    window.resize(size)


def settle_window_geometry_for_capture(
    app: QApplication,
    window: QWidget,
    size: QSize,
    *,
    recovery_wait_ms: int = 320,
) -> None:
    """Let startup geometry timers run, then restore capture dimensions."""
    deadline = time.monotonic() + max(recovery_wait_ms, 0) / 1000
    app.processEvents()
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    set_window_geometry(window, size)
    app.processEvents()
    window.repaint()
    app.processEvents()


def sanitize(value: Any) -> Any:
    """Replace machine-local paths with stable tokens."""
    if isinstance(value, dict):
        return {str(sanitize(key)): sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return sanitize_path(value)
    return value


def sanitize_path(text: str) -> str:
    """Replace volatile local paths in a string."""
    replacements = {
        str(SOURCE_DIR): "<walkthrough_source>",
        str(tempfile.gettempdir()): "<tmp>",
        str(ROOT): "<repo>",
    }
    sanitized = text
    for source, replacement in replacements.items():
        sanitized = sanitized.replace(source, replacement)
    return sanitized


def claim_boundary() -> str:
    """Return the validation claim boundary."""
    return (
        "Automated UI-observable PyQt replay; not human Windows desktop "
        "acceptance. Windows launcher click-through, dual-monitor/DPI behavior, "
        "and long real local-model desktop sessions remain human verification."
    )


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a compact Markdown report."""
    lines = [
        "# Human-Like Product Walkthrough",
        "",
        f"- status: `{payload.get('status')}`",
        f"- failure reason: {payload.get('failure_reason') or 'none'}",
        f"- claim boundary: {payload.get('claim_boundary')}",
        f"- elapsed seconds: `{payload.get('elapsed_seconds', 0)}`",
        f"- source: `{payload.get('source_path', '')}`",
        f"- recipe: `{payload.get('recipe_path', '')}`",
        "",
        "## Pass / Fail",
        "",
    ]
    summary = payload.get("pass_fail_summary", {})
    lines.extend(
        [
            f"- passed: `{summary.get('passed')}`",
            f"- phases: `{summary.get('observed_phase_count')}` / `{summary.get('required_phase_count')}`",
            f"- screenshots: `{summary.get('screenshot_count')}`",
            f"- human desktop acceptance: `{summary.get('human_desktop_acceptance')}`",
        ]
    )
    resource_smoke = summary.get("resource_smoke", {})
    if resource_smoke:
        lines.extend(
            [
                f"- resource smoke passed: `{resource_smoke.get('passed')}`",
                f"- RSS growth: `{resource_smoke.get('rss_growth_kb', 'n/a')}` KB / limit `{resource_smoke.get('rss_limit_kb', 'n/a')}` KB",
            ]
        )
    failures = summary.get("failed_checks", [])
    if failures:
        lines.extend(["", "## Failed Checks", ""])
        lines.extend(f"- {failure}" for failure in failures)
    lines.extend(["", "## Screenshots", ""])
    for key, path in payload.get("screenshots", {}).items():
        lines.append(f"- {key}: `{path}`")
    quality = payload.get("ui_quality_review", {})
    lines.extend(["", "## UI Quality Review", ""])
    lines.extend(
        [
            f"- automated checks passed: `{quality.get('automated_checks_passed')}`",
            f"- phase snapshot coverage: `{quality.get('phase_snapshot_coverage')}`",
            f"- forbidden visible text findings: `{len(quality.get('forbidden_visible_text', []))}`",
            f"- human review boundary: {quality.get('human_design_review_boundary', '')}",
        ]
    )
    table_geometry = quality.get("table_geometry_review", {})
    if table_geometry:
        lines.extend(
            [
                f"- table geometry passed: `{table_geometry.get('passed')}`",
                f"- checked table/tree widgets: `{table_geometry.get('checked_widgets')}`",
                f"- table geometry findings: `{len(table_geometry.get('findings', []))}`",
                f"- clipped row findings: `{len(table_geometry.get('clipped_row_findings', []))}`",
            ]
        )
    lines.extend(["", "## Observable Evidence", ""])
    evidence = payload.get("observable_evidence", {})
    lines.extend(
        [
            f"- visible text snapshots: `{len(evidence.get('visible_text_snapshots', {}))}` phases",
            f"- button states: `{len(evidence.get('button_states', {}))}` phases",
            f"- workflow/backend snapshots: `{len(evidence.get('backend_state_snapshots', {}))}` phases",
            f"- UI geometry snapshots: `{len(evidence.get('ui_geometry_snapshots', {}))}` phases",
        ]
    )
    lines.extend(["", "## Phases", ""])
    for phase in payload.get("phases", []):
        lines.append(f"- `{phase.get('phase')}` -> `{phase.get('screenshot')}`")
    lines.extend(["", "## User-Facing Transcript", ""])
    for message in payload.get("user_facing_message_transcript", []):
        lines.append(f"- {message.get('role')}: {message.get('text')}")
    lines.extend(["", "## Command / Tool Transcript", ""])
    for item in payload.get("tool_transcript", []):
        status = "ok" if item.get("ok") else "failed"
        lines.append(f"- `{item.get('command')}`: `{status}` - {item.get('message')}")
    lines.extend(["", "## Resource Notes", ""])
    if resource_smoke:
        lines.extend(
            [
                f"- smoke checked: `{resource_smoke.get('checked')}`",
                f"- smoke passed: `{resource_smoke.get('passed')}`",
                f"- boundary: {resource_smoke.get('boundary', '')}",
            ]
        )
    for note in payload.get("resource_notes", []):
        lines.append(
            f"- {note.get('label')}: threads `{note.get('python_threads')}`, "
            f"qt active `{note.get('qt_active_threads')}`, rss `{note.get('max_rss_kb')}` KB"
        )
    lines.extend(
        [
            "",
            "## Remaining Human Verification",
            "",
            "- Windows desktop launcher click-through",
            "- dual-monitor and DPI behavior",
            "- long real local-model desktop session",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def write_artifacts(output_dir: Path, payload: dict[str, Any]) -> None:
    """Write JSON and Markdown artifacts."""
    (output_dir / JSON_ARTIFACT).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / MD_ARTIFACT).write_text(render_markdown(payload), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
