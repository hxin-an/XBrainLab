#!/usr/bin/env python3
"""Capture an automated human-like product walkthrough artifact.

This replay uses the real Qt MainWindow, Data Interpretation dialog, ChatPanel,
and ApplicationService command spine. It is UI-observable automation evidence,
not human Windows desktop acceptance.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any, cast

from PIL import Image, ImageStat
from PyQt6.QtCore import (
    QBuffer,
    QIODevice,
    QPoint,
    QRect,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
)
from PyQt6.QtGui import QPixmap, QTextLayout, QTextOption
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QDockWidget,
    QLabel,
    QLineEdit,
    QMainWindow,
    QTextBrowser,
    QToolButton,
    QWidget,
)

from scripts.dev.capture_data_interpretation_replay import (
    LABEL_PATH,
    SOURCE_DIR,
    SOURCE_PATH,
    apply_replay_review_choices,
    pairing_rows,
    pairing_rows_state,
    show_dialog_step,
    table_state,
    tree_rows,
    tree_state,
    write_synthetic_raw_fif,
)
from scripts.dev.human_like_walkthrough import capture as assistant_capture
from scripts.dev.human_like_walkthrough.capture import AssistantCaptureDependencies
from scripts.dev.human_like_walkthrough.contract import (
    ASSISTANT_BLOCKED_REQUEST,
    ASSISTANT_CLARIFICATION_REQUEST,
    ASSISTANT_ERROR_REQUEST,
    ASSISTANT_EVIDENCE_CONTRACT_VERSION,
    ASSISTANT_NARROW_DOCK_WIDTH,
    ASSISTANT_NORMAL_REQUEST,
    ASSISTANT_PROCESSING_REQUEST,
    ASSISTANT_RAW_TRACEBACK,
    ASSISTANT_RECOVERY_REQUEST,
    ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS,
    ASSISTANT_REQUIRED_PHASES,
    ASSISTANT_REQUIRED_SCREENSHOTS,
    ASSISTANT_SCREENSHOT_NAMES,
    ASSISTANT_STANDARD_DOCK_WIDTH,
    ASSISTANT_SUCCESS_REQUEST,
    build_artifact_contract,
    walkthrough_source_fingerprint,
)
from scripts.dev.human_like_walkthrough.driver import (
    append_chat_transcript,
    drive_assistant_request,
    install_walkthrough_assistant,
)
from scripts.dev.human_like_walkthrough.evidence import (
    chat_panel_geometry,
    icon_only_control_contrast_evidence,
)
from scripts.dev.human_like_walkthrough.readiness import (
    assert_consecutive_complete_frames as _assert_consecutive_complete_frames,
)
from scripts.dev.human_like_walkthrough.readiness import (
    assert_region_has_no_unpainted_block as _assert_region_has_no_unpainted_block,
)
from scripts.dev.human_like_walkthrough.readiness import (
    assert_region_matches_reference as _assert_region_matches_reference,
)
from scripts.dev.human_like_walkthrough.readiness import (
    frame_readiness_payload,
)
from scripts.dev.human_like_walkthrough.validation import (
    ASSISTANT_REVIEW_KEYS,
    assistant_contract_findings,
    build_assistant_claim_contract_review,
    build_assistant_contract_reviews,
    build_assistant_dock_contract_review,
    build_assistant_error_contract_review,
    build_assistant_full_window_contract_review,
    build_assistant_interaction_contract_review,
    build_assistant_notice_contract_review,
    build_assistant_processing_contract_review,
    build_assistant_runtime_contract_review,
    build_assistant_settings_recovery_review,
    build_assistant_signal_path_review,
    build_assistant_stage_copy_review,
    build_chat_geometry_review,
    required_assistant_screenshot_failures,
    validate_assistant_payload,
    validate_recorded_assistant_reviews,
)
from scripts.dev.ui_navigation import open_workflow_panel
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
    ReloadInterpretationRecipeCommand,
    SaliencyCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    TrainCommand,
    ValidateInterpretationCommand,
    VisualizeCommand,
    get_application_service,
)
from XBrainLab.backend.application.results import CommandResult
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.study import Study
from XBrainLab.ui.application_capabilities import local_result_payload
from XBrainLab.ui.chat.message_bubble import MessageBubble
from XBrainLab.ui.chat.presentation import (
    ChatTurnCancelability,
    ChatTurnPresentationPhase,
)
from XBrainLab.ui.chat.suggestion_card import AssistantSuggestionCard
from XBrainLab.ui.dialogs.dataset import DataInterpretationPreviewDialog
from XBrainLab.ui.main_window import MainWindow

__all__ = (
    "ASSISTANT_BLOCKED_REQUEST",
    "ASSISTANT_CLARIFICATION_REQUEST",
    "ASSISTANT_ERROR_REQUEST",
    "ASSISTANT_EVIDENCE_CONTRACT_VERSION",
    "ASSISTANT_NARROW_DOCK_WIDTH",
    "ASSISTANT_NORMAL_REQUEST",
    "ASSISTANT_PROCESSING_REQUEST",
    "ASSISTANT_RAW_TRACEBACK",
    "ASSISTANT_RECOVERY_REQUEST",
    "ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS",
    "ASSISTANT_REQUIRED_SCREENSHOTS",
    "ASSISTANT_STANDARD_DOCK_WIDTH",
    "ASSISTANT_SUCCESS_REQUEST",
    "build_assistant_claim_contract_review",
    "build_assistant_dock_contract_review",
    "build_assistant_error_contract_review",
    "build_assistant_full_window_contract_review",
    "build_assistant_interaction_contract_review",
    "build_assistant_notice_contract_review",
    "build_assistant_processing_contract_review",
    "build_assistant_runtime_contract_review",
    "build_assistant_settings_recovery_review",
    "build_assistant_signal_path_review",
    "build_assistant_stage_copy_review",
    "chat_panel_geometry",
    "install_walkthrough_assistant",
    "walkthrough_source_fingerprint",
)

try:
    import resource
except ModuleNotFoundError:  # pragma: no cover - exercised on Windows CI
    resource = None

try:
    import psutil
except ModuleNotFoundError:  # pragma: no cover - psutil is optional in script envs
    psutil = None

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = (
    ROOT / "artifacts" / "ui" / "human-like-walkthrough-runs" / "current"
)
WINDOW_SIZE = QSize(1280, 800)
# Match MainWindow.MINIMUM_SIZE so responsive evidence exercises the narrowest
# product surface we claim to support, not a comfortable surrogate.
NARROW_WINDOW_SIZE = QSize(760, 520)
JSON_ARTIFACT = "human-like-walkthrough.json"
MD_ARTIFACT = "human-like-walkthrough.md"
RECIPE_ARTIFACT = "walkthrough-import.recipe.json"

SCREENSHOT_NAMES: dict[str, str] = {
    "main_initial": "01-main-initial.png",
    "dataset_page": "02-dataset-page.png",
    "source_selection": "02-dataset-page.png",
    "wizard_preview": "04-interpretation-preview.png",
    "wizard_metadata": "05-interpretation-metadata.png",
    "wizard_confirm": "05-interpretation-match-labels.png",
    "wizard_review": "05-interpretation-review-import.png",
    "applied": "06-interpretation-applied.png",
    "recipe_reloaded": "07-recipe-reloaded.png",
    "recipe_reapplied": "07-recipe-reapplied.png",
    "preprocess_loaded": "08a-preprocessing-loaded.png",
    "preprocess": "08-preprocessing.png",
    "preprocess_locked": "08b-preprocessing-locked.png",
    "dataset_ready": "09-dataset-ready.png",
    "training_readiness": "10-training-readiness.png",
    "analysis_readiness": "11-analysis-readiness.png",
    "visualization_readiness": "11b-visualization-readiness.png",
    **ASSISTANT_SCREENSHOT_NAMES,
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
    "data_interpretation_review_and_import",
    "data_interpretation_decisions",
    "data_interpretation_confirm_metadata_labels",
    "data_interpretation_apply",
    "data_interpretation_save_recipe",
    "data_interpretation_reload_recipe",
    "data_interpretation_reapply_recipe",
    "preprocessing_loaded",
    "preprocessing",
    "preprocessing_locked",
    "epoch_creation",
    "dataset_generation",
    "training_readiness",
    "evaluation_visualization_saliency_readiness",
    "visualization_readiness",
    *ASSISTANT_REQUIRED_PHASES,
    "reset_new_session_boundary",
    "error_recovery",
    "eval_dashboard_report",
)

VISIBLE_FORBIDDEN = (
    "tool_name",
    "Tool Output:",
    "Tool Call:",
    "```json",
    "command_name",
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

DATA_IMPORT_STEP_TITLES = (
    "Choose EEG Data",
    "Load Labels",
    "Review Metadata",
    "Match Labels",
    "Review and Import",
)
DATA_IMPORT_COMPACT_STEP_TITLES = (
    "EEG Data",
    "Labels",
    "Metadata",
    "Match",
    "Review",
)
MAIN_NAVIGATION_TITLES = (
    "Dataset",
    "Preprocess",
    "Training",
    "Evaluation",
    "Visualization",
)

RESOURCE_THREAD_TOLERANCE = 1
RESOURCE_RSS_SMOKE_LIMIT_KB = 1_200_000
GEOMETRY_WIDTH_TOLERANCE_PX = 8
WALKTHROUGH_EVENT_ROWS = tuple(
    f"{0.1 + index * 0.55:.2f}\t0.2\t{'left' if index % 2 == 0 else 'right'}"
    for index in range(10)
)
_CAPTURE_FRAME_READINESS: dict[str, dict[str, object]] = {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for screenshots and walkthrough artifacts.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    run_id = _new_artifact_run_id()
    staging_dir = _artifact_staging_dir(output_dir, run_id)
    staging_dir.mkdir(parents=True, exist_ok=False)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    payload = capture_walkthrough(app, staging_dir)
    published_dir = publish_artifact_run(
        staging_dir=staging_dir,
        output_dir=output_dir,
        payload=payload,
        run_id=run_id,
    )
    print(f"Wrote {published_dir / JSON_ARTIFACT}")
    print(f"Wrote {published_dir / MD_ARTIFACT}")
    return 0 if payload["status"] == "passed" else 1


def _new_artifact_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


def _artifact_staging_dir(output_dir: Path, run_id: str) -> Path:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    return output_dir.parent / f".{output_dir.name}-staging-{run_id}"


def publish_artifact_run(
    *,
    staging_dir: Path,
    output_dir: Path,
    payload: dict[str, Any],
    run_id: str,
) -> Path:
    """Publish one internally consistent walkthrough run.

    Failed runs are retained separately and never overwrite the last successful
    product evidence. A successful run replaces the whole latest directory, so
    screenshots and reports cannot come from different executions.
    """
    passed = payload.get("status") == "passed"
    destination = output_dir if passed else _failed_artifact_run_dir(output_dir, run_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    relocated = _relocate_artifact_payload(payload, staging_dir, destination)
    relocated["artifact_run"] = _build_artifact_run_manifest(
        relocated,
        staging_dir=staging_dir,
        run_id=run_id,
    )
    payload.clear()
    payload.update(relocated)
    write_artifacts(staging_dir, payload)
    if passed:
        _replace_artifact_directory(staging_dir, destination, run_id=run_id)
    else:
        if destination.exists():
            shutil.rmtree(destination)
        staging_dir.replace(destination)
    return destination


def _failed_artifact_run_dir(output_dir: Path, run_id: str) -> Path:
    if output_dir.name == "current" and output_dir.parent.name.endswith("-runs"):
        return output_dir.parent / run_id
    return output_dir.parent / f"{output_dir.name}-runs" / run_id


def _relocate_artifact_payload(
    payload: dict[str, Any],
    source_dir: Path,
    destination_dir: Path,
) -> dict[str, Any]:
    source_prefix = str(source_dir)
    destination_prefix = str(destination_dir)

    def relocate(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: relocate(item) for key, item in value.items()}
        if isinstance(value, list):
            return [relocate(item) for item in value]
        if isinstance(value, tuple):
            return [relocate(item) for item in value]
        if isinstance(value, str) and value.startswith(source_prefix):
            return destination_prefix + value[len(source_prefix) :]
        return value

    relocated = relocate(payload)
    return cast(dict[str, Any], relocated)


def _build_artifact_run_manifest(
    payload: dict[str, Any],
    *,
    staging_dir: Path,
    run_id: str,
) -> dict[str, Any]:
    hashes: dict[str, str] = {}
    for key, path_value in payload.get("screenshots", {}).items():
        candidate = staging_dir / Path(str(path_value)).name
        if candidate.is_file():
            hashes[str(key)] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    return {
        "run_id": run_id,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": payload.get("status"),
        "source_fingerprint": walkthrough_source_fingerprint(),
        "git_revision": _git_revision(),
        "working_tree_dirty": _git_worktree_dirty(),
        "screenshot_sha256": hashes,
    }


def _replace_artifact_directory(
    staging_dir: Path,
    destination: Path,
    *,
    run_id: str,
) -> None:
    backup = destination.parent / f".{destination.name}-backup-{run_id}"
    if backup.exists():
        shutil.rmtree(backup)
    if destination.exists():
        destination.replace(backup)
    try:
        staging_dir.replace(destination)
    except Exception:
        if backup.exists() and not destination.exists():
            backup.replace(destination)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _git_revision() -> str:
    git_executable = shutil.which("git")
    if git_executable is None:
        return "unknown"
    completed = subprocess.run(  # noqa: S603 - executable resolved from PATH
        [git_executable, "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _git_worktree_dirty() -> bool | None:
    git_executable = shutil.which("git")
    if git_executable is None:
        return None
    completed = subprocess.run(  # noqa: S603 - executable resolved from PATH
        [git_executable, "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    return bool(completed.stdout.strip()) if completed.returncode == 0 else None


def capture_walkthrough(app: QApplication, output_dir: Path) -> dict[str, Any]:
    """Run the walkthrough and return the artifact payload."""
    started_at = time.monotonic()
    source_fingerprint_at_start = walkthrough_source_fingerprint()
    result: dict[str, Any] = {"payload": None}

    def run() -> None:
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
            try:
                for widget in tuple(app.topLevelWidgets()):
                    try:
                        # MainWindow teardown closes owned PyQtGraph widgets.
                        # Qt may retain those wrappers in this snapshot briefly;
                        # PlotWidget.close() is not idempotent after plotItem=None.
                        if (
                            hasattr(widget, "plotItem")
                            and getattr(widget, "plotItem", None) is None
                        ):
                            continue
                        widget.close()
                    except RuntimeError:
                        # A parent window may already have deleted the wrapper.
                        continue
            finally:
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
    payload = _record_capture_source_stability(
        payload,
        started=source_fingerprint_at_start,
        completed=walkthrough_source_fingerprint(),
    )
    return finalize_walkthrough_after_close(app, payload, started_at=started_at)


def _record_capture_source_stability(
    payload: dict[str, Any],
    *,
    started: str,
    completed: str,
) -> dict[str, Any]:
    """Fail a run whose loaded capture sources changed during Qt replay."""
    payload["capture_source"] = {
        "fingerprint_at_start": started,
        "fingerprint_at_completion": completed,
        "stable": bool(started and started == completed),
    }
    if started and started == completed:
        return payload
    reason = "Product source changed during human-like capture; discard this run."
    payload["status"] = "failed"
    payload["failure_reason"] = reason
    summary = dict(payload.get("pass_fail_summary", {}))
    failed_checks = [str(item) for item in summary.get("failed_checks", [])]
    summary["passed"] = False
    summary["failed_checks"] = [reason, *failed_checks]
    payload["pass_fail_summary"] = summary
    return payload


def finalize_walkthrough_after_close(
    app: QApplication,
    payload: dict[str, Any],
    *,
    started_at: float,
) -> dict[str, Any]:
    """Finalize resource evidence after walkthrough-owned Qt objects are released."""
    root_failure = (
        str(payload.get("failure_reason") or "").strip()
        if payload.get("status") == "failed"
        else ""
    )
    for _ in range(3):
        app.sendPostedEvents()
        app.processEvents()
        gc.collect()
    resource_notes = list(payload.get("resource_notes", []))
    resource_notes.append(
        {
            **resource_snapshot("after_close"),
            "measurement_boundary": "after_walkthrough_return_and_qt_cleanup",
        }
    )
    phases = list(payload.get("phases", []))
    screenshots = dict(payload.get("screenshots", {}))
    pass_fail_summary = build_pass_fail_summary(
        phases,
        screenshots,
        resource_notes=resource_notes,
    )
    ui_quality_review = payload.get("ui_quality_review")
    if not isinstance(ui_quality_review, dict):
        ui_quality_review = build_ui_quality_review(phases, screenshots)
    pass_fail_summary = merge_ui_quality_into_pass_fail_summary(
        pass_fail_summary,
        ui_quality_review,
    )
    if root_failure:
        failed_checks = list(pass_fail_summary.get("failed_checks", []))
        pass_fail_summary["failed_checks"] = [
            root_failure,
            *(item for item in failed_checks if item != root_failure),
        ]
        pass_fail_summary["passed"] = False
    status = "passed" if pass_fail_summary["passed"] else "failed"
    return {
        **payload,
        "status": status,
        "failure_reason": (
            ""
            if status == "passed"
            else root_failure or "; ".join(pass_fail_summary["failed_checks"])
        ),
        "resource_notes": resource_notes,
        "ui_quality_review": ui_quality_review,
        "pass_fail_summary": pass_fail_summary,
        "elapsed_seconds": round(time.monotonic() - started_at, 3),
    }


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
    LABEL_PATH.write_text(
        "onset\tduration\ttrial_type\n" + "\n".join(WALKTHROUGH_EVENT_ROWS) + "\n",
        encoding="utf-8",
    )
    study = Study()
    service = get_application_service(study)
    window = cast(Any, MainWindow(study))
    set_window_geometry(window, WINDOW_SIZE)
    window.show()
    settle_window_geometry_for_capture(app, window, WINDOW_SIZE)

    def capture_step(
        phase: str,
        screenshot_key: str,
        *,
        widget: QWidget | None = None,
        notes: dict[str, Any] | Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        target = widget or window
        screenshot_path = output_dir / SCREENSHOT_NAMES[screenshot_key]
        settle_widget_for_capture(app, target)
        capture_widget(target, screenshot_path)
        resolved_notes = notes() if callable(notes) else notes
        screenshots[screenshot_key] = str(screenshot_path)
        phases.append(
            {
                "phase": phase,
                "screenshot": str(screenshot_path),
                "visible_text": visible_text_snapshot(target),
                "button_state": button_state_snapshot(target),
                "workflow_state": compact_state(service.get_state()),
                "notes": resolved_notes or {},
            }
        )

    capture_step(
        "app_startup",
        "main_initial",
        notes={"window_title": window.windowTitle(), "startup": "MainWindow shown"},
    )
    open_workflow_panel(window, 0)
    app.processEvents()
    capture_step(
        "main_window_initial_state",
        "dataset_page",
        notes=lambda: {
            "current_panel": "Dataset",
            "ui_geometry": dataset_page_geometry(window),
        },
    )
    capture_step(
        "data_source_selection",
        "source_selection",
        notes=lambda: {
            "selected_source": sanitize_path(str(source_path)),
            "input_mode": "file",
            "source_button": window.dataset_panel.sidebar.import_btn.text(),
        },
    )
    append_phase_alias(
        phases,
        "data_interpretation_select_source",
        screenshots["source_selection"],
        window.dataset_panel,
        service,
        {"selected_source": sanitize_path(str(source_path))},
    )

    scan = execute_recorded(
        service,
        ScanSourceCommand(source_path=str(source_path), source_hint="file"),
        command_results,
    )
    preview = execute_recorded(service, PreviewInterpretationCommand(), command_results)
    validation = execute_recorded(
        service,
        ValidateInterpretationCommand(),
        command_results,
    )
    scan_payload = _required_command_payload(
        scan,
        expected_payload_type="scan_result",
        required_fields=("scan_result",),
    )
    preview_payload = _required_command_payload(
        preview,
        expected_payload_type="interpretation_preview",
        required_fields=("preview",),
    )
    validation_payload = _required_command_payload(
        validation,
        expected_payload_type="validation_decision",
        required_fields=("validation_decision",),
    )
    tool_transcript.extend(
        command_summary(item) for item in [scan, preview, validation]
    )

    dialog = DataInterpretationPreviewDialog(
        window.dataset_panel,
        scan_result=scan_payload["scan_result"],
        preview=preview_payload["preview"],
        validation_decision=validation_payload["validation_decision"],
    )
    dialog.show()
    app.processEvents()
    capture_step(
        "data_interpretation_scan_result",
        "wizard_preview",
        widget=dialog,
        notes=lambda: {
            "active_step": active_dialog_step(dialog),
            "decision": validation_payload["validation_decision"]["decision"],
            "eeg_files": len(scan_payload["scan_result"]["eeg_files"]),
            "label_carriers": len(scan_payload["scan_result"]["label_carriers"]),
            "ui_geometry": sanitize(interpretation_dialog_geometry(dialog)),
        },
    )

    apply_review_choices(dialog)
    app.processEvents()
    dialog_result = dialog.get_result()
    review_choices = dialog_result.get("choices", {})
    show_dialog_step(dialog, "Review Metadata", app)
    app.processEvents()
    capture_step(
        "data_interpretation_preview",
        "wizard_metadata",
        widget=dialog,
        notes=lambda: {
            "active_step": active_dialog_step(dialog),
            "review_choices": sanitize(review_choices),
            "metadata_rows": tree_rows(dialog.file_tree),
            "ui_geometry": sanitize(interpretation_dialog_geometry(dialog)),
        },
    )
    show_dialog_step(dialog, "Match Labels", app)
    app.processEvents()
    capture_step(
        "data_interpretation_confirm_metadata_labels",
        "wizard_confirm",
        widget=dialog,
        notes=lambda: {
            "active_step": active_dialog_step(dialog),
            "file_pairing_rows": pairing_rows(dialog),
            "ui_geometry": sanitize(interpretation_dialog_geometry(dialog)),
        },
    )
    show_dialog_step(dialog, "Review and Import", app)
    app.processEvents()
    capture_step(
        "data_interpretation_review_and_import",
        "wizard_review",
        widget=dialog,
        notes=lambda: {
            "active_step": active_dialog_step(dialog),
            "apply_enabled": dialog.apply_button.isEnabled(),
            "save_recipe_selected": dialog.save_recipe_check.isChecked(),
            "review_summary_rows": tree_rows(dialog.review_tree),
            "ui_geometry": sanitize(interpretation_dialog_geometry(dialog)),
        },
    )
    if dialog.save_recipe_check.isChecked():
        raise RuntimeError("Save recipe must remain optional by default.")
    dialog.save_recipe_check.click()
    recipe_requested = bool(dialog.get_result().get("save_recipe"))
    if not recipe_requested:
        raise RuntimeError("Step 5 did not preserve the explicit Save recipe choice.")
    dialog.close()

    safe_probe = data_interpretation_decision_probe(str(SOURCE_PATH), {})
    blocked_probe_path = SOURCE_DIR / "stream-export.xdf"
    blocked_probe_path.write_text("stream placeholder", encoding="utf-8")
    blocked_probe = data_interpretation_decision_probe(str(blocked_probe_path), {})

    reviewed_preview = execute_recorded(
        service,
        PreviewInterpretationCommand(
            scan_id=scan_payload["scan_result"]["scan_id"],
            choices=review_choices if isinstance(review_choices, dict) else {},
        ),
        command_results,
    )
    reviewed_validation = execute_recorded(
        service,
        ValidateInterpretationCommand(),
        command_results,
    )
    reviewed_validation_payload = _required_command_payload(
        reviewed_validation,
        expected_payload_type="validation_decision",
        required_fields=("validation_decision",),
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
    save_recipe = (
        execute_recorded(
            service,
            SaveInterpretationRecipeCommand(recipe_path=str(recipe_path)),
            command_results,
        )
        if recipe_requested
        else None
    )
    if save_recipe is None:
        raise RuntimeError("The explicit Save recipe choice was not executed.")
    reload_recipe = execute_recorded(
        service,
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
        command_results,
    )
    reload_apply = execute_recorded(
        service,
        ApplyInterpretationCommand(confirmed=True),
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
            reload_apply,
        ]
    )

    window.dataset_panel.update_panel()
    open_workflow_panel(window, 0)
    app.processEvents()
    capture_step(
        "data_interpretation_decisions",
        "applied",
        notes={
            "safe": safe_probe,
            "needs_confirmation": reviewed_validation_payload["validation_decision"],
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
    reload_payload = _required_command_payload(
        reload_recipe,
        expected_payload_type="recipe_reload_preview",
        required_fields=("scan_result", "preview", "validation_decision"),
    )
    reload_dialog = DataInterpretationPreviewDialog(
        window.dataset_panel,
        scan_result=reload_payload["scan_result"],
        preview=reload_payload["preview"],
        validation_decision=reload_payload["validation_decision"],
        initial_step="Review and Import",
    )
    reload_dialog.show()
    app.processEvents()
    capture_step(
        "data_interpretation_reload_recipe",
        "recipe_reloaded",
        widget=reload_dialog,
        notes=lambda: {
            "reload": command_summary(reload_recipe),
            "reapply": command_summary(reload_apply),
            "review_summary_rows": tree_rows(reload_dialog.review_tree),
            "ui_geometry": sanitize(interpretation_dialog_geometry(reload_dialog)),
        },
    )
    reload_dialog.close()
    app.processEvents()
    window.dataset_panel.update_panel()
    capture_step(
        "data_interpretation_reapply_recipe",
        "recipe_reapplied",
        notes={
            "reapply": command_summary(reload_apply),
            "ui_geometry": dataset_page_geometry(window),
        },
    )

    open_workflow_panel(window, 1)
    window.preprocess_panel.update_panel()
    app.processEvents()
    capture_step(
        "preprocessing_loaded",
        "preprocess_loaded",
        notes={
            "preview_state": "loaded",
            "channel_count": window.preprocess_panel.preview_widget.chan_combo.count(),
            "time_curve_samples": len(
                window.preprocess_panel.preview_widget.time_current_curve.xData
            )
            if window.preprocess_panel.preview_widget.time_current_curve.xData
            is not None
            else 0,
        },
    )

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
    tool_transcript.append(command_summary(preprocess))
    open_workflow_panel(window, 1)
    window.preprocess_panel.update_panel()
    app.processEvents()
    capture_step(
        "preprocessing",
        "preprocess",
        notes={"preprocess": command_summary(preprocess)},
    )

    epoch = execute_recorded(
        service,
        CreateEpochCommand(t_min=0.0, t_max=0.51, event_ids=None),
        command_results,
    )
    dataset = execute_recorded(
        service,
        GenerateDatasetCommand(
            test_ratio=0.25,
            val_ratio=0.25,
            split_strategy="trial",
            training_mode="individual",
        ),
        command_results,
    )
    tool_transcript.extend(command_summary(item) for item in [epoch, dataset])
    open_workflow_panel(window, 1)
    window.preprocess_panel.update_panel()
    app.processEvents()
    capture_step(
        "preprocessing_locked",
        "preprocess_locked",
        notes={
            "epoch": command_summary(epoch),
            "preview_state": "locked",
        },
    )
    open_workflow_panel(window, 2)
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
            model_name="SCCNet",
            epoch=1,
            batch_size=2,
            learning_rate=0.001,
            device="cpu",
            output_dir=str(output_dir / "training-smoke-output"),
        ),
        command_results,
    )
    train = execute_recorded(
        service,
        TrainCommand(confirmed=True, interactive=False),
        command_results,
    )
    training_wait = (
        wait_for_training_completion(app, service)
        if train.ok
        else {"completed": False, "reason": "training command failed"}
    )
    evaluate = execute_recorded(service, EvaluateCommand(), command_results)
    visualize = execute_recorded(service, VisualizeCommand(), command_results)
    saliency = execute_recorded(service, SaliencyCommand(), command_results)
    tool_transcript.extend(
        command_summary(item)
        for item in [configure_training, train, evaluate, visualize, saliency]
    )
    open_workflow_panel(window, 2)
    app.processEvents()
    capture_step(
        "training_readiness",
        "training_readiness",
        notes={
            "training": command_summary(configure_training),
            "train": command_summary(train),
            "training_wait": training_wait,
        },
    )
    open_workflow_panel(window, 3)
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
    open_workflow_panel(window, 4)
    app.processEvents()
    capture_step(
        "visualization_readiness",
        "visualization_readiness",
        notes={
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
    open_workflow_panel(window, 0)
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
    drive_assistant_request(
        app,
        window.agent_manager,
        ASSISTANT_RECOVERY_REQUEST,
    )
    app.processEvents()
    append_chat_transcript(
        user_transcript,
        window.agent_manager.chat_controller.messages,
    )
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
    return {
        # The after-close resource sample is collected by
        # ``finalize_walkthrough_after_close`` before a pass/fail claim is made.
        "status": "captured",
        "failure_reason": "",
        "claim_boundary": claim_boundary(),
        "artifact_contract": build_artifact_contract(),
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
    """Delegate assistant capture while this entry orchestrates the product flow."""
    dependencies = AssistantCaptureDependencies(
        capture_named,
        visible_text_snapshot,
        button_state_snapshot,
        compact_state,
        command_summary,
        set_window_geometry,
        settle_widget_for_capture,
        WINDOW_SIZE,
        NARROW_WINDOW_SIZE,
    )
    return assistant_capture.run_assistant_walkthrough(
        app,
        window,
        service,
        screenshots,
        phases,
        output_dir,
        user_transcript,
        tool_transcript,
        dependencies=dependencies,
    )


def apply_review_choices(dialog: DataInterpretationPreviewDialog) -> None:
    """Apply deterministic human-like review choices to the wizard."""
    apply_replay_review_choices(dialog)
    editor = dialog.event_value_editor
    if editor is not None and editor.has_rows():
        unresolved = set(editor.unresolved_values())
        expected_values = {"left", "right"}
        unexpected = sorted(unresolved - expected_values, key=str.casefold)
        if unexpected:
            raise RuntimeError(
                "Walkthrough fixture exposed unexpected unresolved label value(s): "
                + ", ".join(unexpected)
            )
        for raw_value in sorted(unresolved, key=str.casefold):
            editor.set_value_decision(
                raw_value,
                role="stimulus",
                use="class",
                class_name=raw_value,
            )
    dialog._refresh_pairing_status()


def active_dialog_step(dialog: DataInterpretationPreviewDialog) -> str:
    """Return the task step currently presented to the user."""
    index = dialog.step_stack.currentIndex()
    return dialog._step_titles[index] if 0 <= index < len(dialog._step_titles) else ""


def dataset_page_geometry(window: Any) -> dict[str, Any]:
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
        "metadata": tree_state_for_visible_dialog_step(
            dialog,
            "Review Metadata",
            dialog.file_tree,
        ),
        "file_pairing": pairing_rows_state_for_visible_dialog_step(
            dialog,
            "Match Labels",
        ),
        "events": tree_state_for_visible_dialog_step(
            dialog,
            "Match Labels",
            dialog.event_tree,
        ),
        "review_summary": tree_state_for_visible_dialog_step(
            dialog,
            "Review and Import",
            dialog.review_tree,
        ),
    }


def tree_state_for_visible_dialog_step(
    dialog: DataInterpretationPreviewDialog,
    step_title: str,
    tree,
) -> dict[str, Any]:
    """Measure wizard tree geometry while the owning step is visible."""
    app = QApplication.instance()
    current_index = dialog.step_stack.currentIndex()
    try:
        step_titles = getattr(dialog, "_step_titles", [])
        if step_title in step_titles:
            dialog._go_to_step(step_titles.index(step_title))
        if app is not None:
            app.processEvents()
        dialog._fit_all_tree_columns_to_viewport()
        if app is not None:
            app.processEvents()
        return tree_state(tree)
    finally:
        dialog._go_to_step(current_index)
        if app is not None:
            app.processEvents()


def pairing_rows_state_for_visible_dialog_step(
    dialog: DataInterpretationPreviewDialog,
    step_title: str,
) -> dict[str, Any]:
    """Measure the visible EEG-to-label pairing rows on their owning step."""
    app = QApplication.instance()
    current_index = dialog.step_stack.currentIndex()
    try:
        step_titles = getattr(dialog, "_step_titles", [])
        if step_title in step_titles:
            dialog._go_to_step(step_titles.index(step_title))
        if app is not None:
            app.processEvents()
        return pairing_rows_state(dialog)
    finally:
        dialog._go_to_step(current_index)
        if app is not None:
            app.processEvents()


def data_interpretation_decision_probe(
    source_path: str,
    choices: dict[str, Any],
) -> dict[str, Any]:
    """Probe one decision boundary on a separate service."""
    service = get_application_service(Study())
    scan = service.execute(ScanSourceCommand(source_path=source_path))
    preview = service.execute(PreviewInterpretationCommand(choices=choices))
    validation = service.execute(ValidateInterpretationCommand())
    validation_payload = _required_command_payload(
        validation,
        expected_payload_type="validation_decision",
        required_fields=("validation_decision",),
    )
    return {
        "scan": command_summary(scan),
        "preview": command_summary(preview),
        "validation": validation_payload["validation_decision"],
    }


def _required_command_payload(
    result: Any,
    *,
    expected_payload_type: str,
    required_fields: tuple[str, ...],
) -> dict[str, Any]:
    """Read and validate one command's serializable/local result payload."""
    payload = local_result_payload(result)
    command_name = str(getattr(result, "command_name", "command") or "command")
    if not bool(getattr(result, "success", False)):
        error_type = getattr(getattr(result, "error_type", None), "value", "unknown")
        message = str(
            getattr(result, "error_message", None) or getattr(result, "message", "")
        )
        raise RuntimeError(
            f"{command_name} failed ({error_type}) before walkthrough payload "
            f"'{expected_payload_type}' was available: {message}"
        )
    actual_payload_type = payload.get("payload_type")
    if actual_payload_type != expected_payload_type:
        raise RuntimeError(
            f"{command_name} expected payload_type '{expected_payload_type}', "
            f"received {actual_payload_type!r}; available fields: "
            f"{sorted(str(key) for key in payload)}"
        )
    missing = tuple(field for field in required_fields if field not in payload)
    if missing:
        raise RuntimeError(
            f"{command_name} payload '{expected_payload_type}' is missing required "
            f"field(s): {', '.join(missing)}; available fields: "
            f"{sorted(str(key) for key in payload)}"
        )
    return payload


def execute_recorded(
    service: ApplicationService,
    command: Any,
    command_results: list[dict[str, Any]],
) -> CommandResult:
    """Execute a command and append a sanitized CommandResult payload."""
    result = service.execute(command)
    command_results.append(sanitize(result.to_dict()))
    return result


def wait_for_training_completion(
    app: QApplication,
    service: ApplicationService,
    *,
    timeout_seconds: float = 90.0,
) -> dict[str, Any]:
    """Keep the UI responsive while the tiny training smoke finishes."""
    deadline = time.monotonic() + timeout_seconds
    last_state = service.get_state()
    while time.monotonic() < deadline:
        app.processEvents()
        last_state = service.get_state()
        if (
            not last_state.training.is_running
            and last_state.training.finished_run_count > 0
        ):
            return {
                "completed": True,
                "finished_run_count": last_state.training.finished_run_count,
            }
        time.sleep(0.02)
    return {
        "completed": False,
        "reason": "training did not finish before the walkthrough timeout",
        "is_running": last_state.training.is_running,
        "finished_run_count": last_state.training.finished_run_count,
    }


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
    app = QApplication.instance()
    if isinstance(app, QApplication):
        settle_widget_for_capture(app, window)
    capture_widget(window, path)
    return str(path)


def capture_widget(widget: QWidget, output_path: Path) -> None:
    """Capture a stable pair of complete widget frames and publish the second."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance()
    last_render_error: RuntimeError | None = None
    first_frame = output_path.with_name(f".{output_path.stem}-frame-1.png")
    for attempt in range(3):
        try:
            if isinstance(app, QApplication):
                settle_widget_for_capture(
                    app,
                    widget,
                    wait_ms=180 if attempt else 100,
                )
            _grab_widget_to_path(widget, first_frame)
            _assert_capture_frame_rendered(
                widget,
                first_frame,
                logical_name=output_path.name,
            )
            if isinstance(app, QApplication):
                settle_widget_for_capture(app, widget, wait_ms=80)
            _grab_widget_to_path(widget, output_path)
            _assert_capture_frame_rendered(
                widget,
                output_path,
                logical_name=output_path.name,
            )
            changed_ratio = _assert_consecutive_complete_frames(
                first_frame,
                output_path,
            )
        except RuntimeError as error:
            last_render_error = error
            continue
        finally:
            first_frame.unlink(missing_ok=True)
        _CAPTURE_FRAME_READINESS[str(output_path.resolve())] = frame_readiness_payload(
            changed_pixel_ratio=changed_ratio,
            required_regions=_required_capture_region_names(widget),
        )
        return
    if last_render_error is not None:
        raise last_render_error


def _assert_capture_frame_rendered(
    widget: QWidget,
    output_path: Path,
    *,
    logical_name: str | None = None,
) -> None:
    """Require one complete frame before it can count toward the two-frame gate."""
    if is_nearly_black(output_path):
        raise RuntimeError(f"Screenshot is nearly black: {output_path}.")
    _assert_step_navigation_rendered(widget, output_path)
    _assert_main_navigation_rendered(widget, output_path)
    _assert_right_panels_rendered(widget, output_path)
    _assert_assistant_dock_rendered(
        widget,
        output_path,
        logical_name=logical_name,
    )


def _required_capture_region_names(widget: QWidget) -> list[str]:
    regions: list[str] = []
    if getattr(widget, "step_labels", None):
        regions.extend(
            ["Import Review stepper", "Import Review summary", "Import footer"]
        )
    if getattr(widget, "nav_btns", None):
        regions.append("Main navigation")
    if widget.findChildren(QWidget, "RightPanel"):
        regions.append("Workflow sidebar")
    panel = (
        widget
        if widget.objectName() == "AssistantPanel"
        else widget.findChild(QWidget, "AssistantPanel")
    )
    if panel is not None:
        regions.extend(
            ["Assistant composer", "Assistant activity", "Assistant feedback"]
        )
    return regions or ["Complete widget"]


def _grab_widget_to_path(widget: QWidget, output_path: Path) -> None:
    """Write one widget frame without weakening the post-capture checks."""
    pixmap = _grab_docked_widget_from_composed_window(widget)
    if pixmap is None:
        screen = widget.screen() or QApplication.primaryScreen()
        platform_name = QApplication.platformName()
        if _use_native_window_capture(
            is_window=widget.isWindow(),
            platform_name=platform_name,
            screen_available=screen is not None,
        ):
            if screen is None:
                raise RuntimeError(
                    "Native widget capture requires an available screen."
                )
            pixmap = screen.grabWindow(
                widget.winId(),
                0,
                0,
                widget.width(),
                widget.height(),
            )
        else:
            pixmap = widget.grab()
    if pixmap.isNull():
        raise RuntimeError(f"Could not grab screenshot for {output_path.name}.")
    if not pixmap.save(str(output_path)):
        raise RuntimeError(f"Could not save screenshot {output_path}.")


def _pixmap_image(pixmap: QPixmap) -> Image.Image:
    """Convert one live Qt render into a detached PIL reference image."""
    if pixmap.isNull():
        raise RuntimeError("Could not create a live widget reference.")
    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("Could not open the live widget reference buffer.")
    if not pixmap.save(buffer, "PNG"):
        raise RuntimeError("Could not encode the live widget reference.")
    data = bytes(cast(Any, buffer.data()))
    buffer.close()
    with Image.open(BytesIO(data)) as source:
        image = source.convert("RGB")
        image.load()
    return image


def _grab_docked_widget_from_composed_window(widget: QWidget) -> QPixmap | None:
    """Crop a dock from its composed main-window frame when one is available.

    On Linux and offscreen Qt platforms, ``QDockWidget.grab()`` can expose an
    incomplete native backing store even though the owning ``QMainWindow`` is
    fully composed. Floating docks and invalid crop geometry deliberately fall
    back to the regular widget capture path.
    """
    if (
        not isinstance(widget, QDockWidget)
        or widget.isFloating()
        or not widget.isVisible()
    ):
        return None
    main_window = _owning_visible_main_window(widget)
    if main_window is None:
        return None
    try:
        composed = _grab_capture_surface(main_window)
    except RuntimeError:
        return None
    if composed.isNull():
        return None
    return _crop_composed_pixmap(
        composed,
        surface=main_window,
        target=widget,
    )


def _owning_visible_main_window(dock: QDockWidget) -> QMainWindow | None:
    candidate = dock.window()
    if isinstance(candidate, QMainWindow) and candidate.isVisible():
        return candidate
    parent = dock.parentWidget()
    while parent is not None:
        if isinstance(parent, QMainWindow) and parent.isVisible():
            return parent
        parent = parent.parentWidget()
    return None


def _grab_capture_surface(widget: QWidget) -> QPixmap:
    screen = widget.screen() or QApplication.primaryScreen()
    if _use_native_window_capture(
        is_window=widget.isWindow(),
        platform_name=QApplication.platformName(),
        screen_available=screen is not None,
    ):
        if screen is None:
            return QPixmap()
        return screen.grabWindow(
            widget.winId(),
            0,
            0,
            widget.width(),
            widget.height(),
        )
    return widget.grab()


def _crop_composed_pixmap(
    pixmap: QPixmap,
    *,
    surface: QWidget,
    target: QWidget,
) -> QPixmap | None:
    """Map a logical child rect into the composed pixmap's physical pixels."""
    if (
        pixmap.isNull()
        or surface.width() <= 0
        or surface.height() <= 0
        or target.width() <= 0
        or target.height() <= 0
    ):
        return None
    top_left = target.mapTo(surface, QPoint(0, 0))
    logical_rect = QRect(top_left, target.size())
    if not surface.rect().contains(logical_rect):
        return None

    # QPixmap dimensions are physical pixels. Deriving each scale from the
    # captured surface handles both high-DPI devicePixelRatio and platform
    # plugins that return a backing store with a backend-specific pixel size.
    scale_x = pixmap.width() / surface.width()
    scale_y = pixmap.height() / surface.height()
    left = round(logical_rect.left() * scale_x)
    top = round(logical_rect.top() * scale_y)
    right = round((logical_rect.left() + logical_rect.width()) * scale_x)
    bottom = round((logical_rect.top() + logical_rect.height()) * scale_y)
    physical_rect = QRect(left, top, right - left, bottom - top)
    if (
        physical_rect.width() <= 0
        or physical_rect.height() <= 0
        or not pixmap.rect().contains(physical_rect)
    ):
        return None
    cropped = pixmap.copy(physical_rect)
    return None if cropped.isNull() else cropped


def _use_native_window_capture(
    *,
    is_window: bool,
    platform_name: str,
    screen_available: bool,
) -> bool:
    """Use native capture only on desktop platforms with reliable composition."""
    if not is_window or not screen_available:
        return False
    # X11/Xvfb native grabs can let a native plotting child overpaint the
    # surrounding Qt backing store, producing a black or partially rendered
    # false-positive artifact. QWidget.grab() is deterministic for the Linux
    # product walkthrough while Windows/macOS benefit from native composition.
    return platform_name.strip().lower() in {"windows", "cocoa"}


def _assert_step_navigation_rendered(widget: QWidget, screenshot: Path) -> None:
    """Require the complete Import Review stepper and footer to be painted."""
    step_labels = getattr(widget, "step_labels", [])
    if not isinstance(step_labels, list) or not step_labels:
        if widget.objectName() == "DataImportWizardDialog":
            raise RuntimeError(
                "Import Review capture is missing its step navigation owner."
            )
        return
    if len(step_labels) != len(DATA_IMPORT_STEP_TITLES):
        raise RuntimeError(
            "Wizard step navigation contract requires all five Import Review labels."
        )
    for index, (label, full_title, compact_title) in enumerate(
        zip(
            step_labels,
            DATA_IMPORT_STEP_TITLES,
            DATA_IMPORT_COMPACT_STEP_TITLES,
            strict=True,
        ),
        start=1,
    ):
        if not isinstance(label, QLabel) or not label.isVisibleTo(widget):
            raise RuntimeError(
                f"Wizard step navigation is missing visible step {index}: {full_title}."
            )
        expected_labels = {f"{index}. {full_title}", f"{index}. {compact_title}"}
        actual_label = " ".join(label.text().split())
        if actual_label not in expected_labels:
            raise RuntimeError(
                f"Wizard step navigation has stale label {index}: {label.text()!r}."
            )
        if actual_label == f"{index}. {compact_title}" and compact_title != full_title:
            if label.toolTip() != full_title:
                raise RuntimeError(
                    f"Wizard compact step {index} does not preserve {full_title!r}."
                )

    cancel = getattr(widget, "cancel_button", None)
    next_button = getattr(widget, "next_button", None)
    apply_button = getattr(widget, "apply_button", None)
    if (
        not isinstance(cancel, QAbstractButton)
        or not cancel.isVisibleTo(widget)
        or cancel.text() != "Cancel"
    ):
        raise RuntimeError(
            "Import Review capture is missing the visible Cancel action."
        )
    primary_actions = [
        control
        for control in (next_button, apply_button)
        if isinstance(control, QAbstractButton) and control.isVisibleTo(widget)
    ]
    if len(primary_actions) != 1:
        raise RuntimeError(
            "Import Review capture must show exactly one visible primary action."
        )
    primary = primary_actions[0]
    allowed_primary = primary.text().startswith("Next: ") or primary.text() in {
        "Import EEG Data",
        "Confirm and Import",
        "Apply Remap",
    }
    if not allowed_primary or primary.objectName() != "DataImportPrimaryButton":
        raise RuntimeError(
            "Import Review capture has an invalid or stale primary action."
        )
    summary = getattr(widget, "summary_label", None)
    if (
        not isinstance(summary, QLabel)
        or not summary.isVisibleTo(widget)
        or not summary.text().strip()
    ):
        raise RuntimeError("Import Review capture is missing its visible summary.")
    _assert_text_controls_rendered(
        widget,
        screenshot,
        [*step_labels, summary, cancel, primary],
        surface_name="Import Review controls",
    )


def _assert_main_navigation_rendered(widget: QWidget, screenshot: Path) -> None:
    """Require every workflow destination or the compact selector to be painted."""
    nav_buttons = getattr(widget, "nav_btns", [])
    if not isinstance(nav_buttons, list) or not nav_buttons:
        if isinstance(widget, QMainWindow):
            raise RuntimeError("Main product capture is missing navigation controls.")
        return
    observed_titles = tuple(
        " ".join(button.text().split())
        for button in nav_buttons
        if isinstance(button, QAbstractButton)
    )
    if observed_titles != MAIN_NAVIGATION_TITLES:
        raise RuntimeError(
            "Main navigation does not expose the five workflow destinations."
        )
    visible_buttons = [
        button
        for button in nav_buttons
        if isinstance(button, QAbstractButton) and button.isVisibleTo(widget)
    ]
    compact = getattr(widget, "compact_nav_combo", None)
    compact_visible = isinstance(compact, QComboBox) and compact.isVisibleTo(widget)
    if visible_buttons:
        if len(visible_buttons) != len(MAIN_NAVIGATION_TITLES) or compact_visible:
            raise RuntimeError(
                "Main navigation mixes incomplete full and compact controls."
            )
        _assert_button_text_rendered(
            widget,
            screenshot,
            visible_buttons,
            surface_name="Main navigation",
        )
        return
    if not compact_visible or not isinstance(compact, QComboBox):
        raise RuntimeError("Main navigation has no visible workflow selector.")
    compact_items = tuple(compact.itemText(index) for index in range(compact.count()))
    if compact_items != MAIN_NAVIGATION_TITLES:
        raise RuntimeError("Compact navigation has a stale workflow destination list.")
    if compact.currentText() not in MAIN_NAVIGATION_TITLES:
        raise RuntimeError("Compact navigation has no current workflow destination.")
    _assert_combo_text_rendered(
        widget,
        screenshot,
        compact,
        surface_name="Compact main navigation",
    )


def _assert_button_text_rendered(
    root: QWidget,
    screenshot: Path,
    controls: Sequence[QWidget],
    *,
    surface_name: str,
) -> None:
    """Reject captures where a button painted only part of its visible text."""
    _assert_text_controls_rendered(
        root,
        screenshot,
        controls,
        surface_name=surface_name,
    )


def _assert_text_controls_rendered(
    root: QWidget,
    screenshot: Path,
    controls: Sequence[QWidget],
    *,
    surface_name: str,
) -> None:
    """Verify expected control text through geometry and glyph-pixel span."""
    if not controls:
        raise RuntimeError(f"{surface_name} has no expected visible controls.")
    with Image.open(screenshot) as captured:
        grayscale = captured.convert("L")
        for control in controls:
            if not isinstance(control, (QAbstractButton, QLabel)):
                raise RuntimeError(
                    f"{surface_name} includes a non-text capture control."
                )
            if not control.isVisibleTo(root):
                name = control.objectName() or control.__class__.__name__
                raise RuntimeError(f"{surface_name} control is hidden: {name}.")
            if (
                isinstance(control, QToolButton)
                and control.toolButtonStyle() is Qt.ToolButtonStyle.ToolButtonIconOnly
            ):
                if control.icon().isNull() or not control.accessibleName().strip():
                    name = control.objectName() or control.__class__.__name__
                    raise RuntimeError(
                        f"{surface_name} icon-only control is not perceivable: {name}."
                    )
                contrast = icon_only_control_contrast_evidence(
                    root,
                    screenshot,
                    control,
                )
                if not contrast["passed"]:
                    name = control.objectName() or control.__class__.__name__
                    raise RuntimeError(
                        f"{surface_name} icon-only control is not visibly painted: "
                        f"{name} ({contrast})."
                    )
                continue
            text = (
                control.text().replace("&&", "\0").replace("&", "").replace("\0", "&")
            )
            if not text:
                raise RuntimeError(f"{surface_name} includes an empty text control.")
            top_left = control.mapTo(root, QPoint(0, 0))
            if isinstance(control, QAbstractButton):
                # Sidebar and action buttons intentionally left-align their text.
                # Probe the interior text band instead of assuming centered copy.
                metrics = control.fontMetrics()
                expected_width = max(metrics.horizontalAdvance(text), 1)
                expected_height = max(metrics.height(), 1)
                local_left = 4
                probe_width = max(control.width() - 8, 1)
                local_top = max((control.height() - expected_height) // 2 - 3, 0)
                probes = [
                    (
                        QRect(local_left, local_top, probe_width, expected_height + 6),
                        expected_width,
                    )
                ]
            else:
                probes = _label_text_line_probes(
                    control, text, surface_name=surface_name
                )
            scale_x = grayscale.width / max(root.width(), 1)
            scale_y = grayscale.height / max(root.height(), 1)
            control_bounds = (
                max(round(top_left.x() * scale_x), 0),
                max(round(top_left.y() * scale_y), 0),
                min(round((top_left.x() + control.width()) * scale_x), grayscale.width),
                min(
                    round((top_left.y() + control.height()) * scale_y),
                    grayscale.height,
                ),
            )
            _assert_region_has_no_unpainted_block(
                screenshot,
                control_bounds,
                surface_name=surface_name,
            )
            for local_probe, expected_width in probes:
                bounds = _physical_text_probe_bounds(
                    root=root,
                    screenshot=grayscale,
                    top_left=top_left,
                    local_probe=local_probe,
                )
                if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
                    name = control.objectName() or control.__class__.__name__
                    raise RuntimeError(
                        f"{surface_name} control is outside {screenshot.name}: {name}."
                    )
                region = grayscale.crop(bounds)
                histogram = region.histogram()
                background = max(range(256), key=histogram.__getitem__)
                painted_columns = [
                    x
                    for x in range(region.width)
                    if any(
                        abs(cast(int, region.getpixel((x, y))) - background) >= 18
                        for y in range(region.height)
                    )
                ]
                painted_span = (
                    painted_columns[-1] - painted_columns[0] + 1
                    if painted_columns
                    else 0
                )
                expected_pixel_width = expected_width * scale_x
                minimum_span = max(int(expected_pixel_width * 0.55), 3)
                if painted_span < minimum_span:
                    ratio = painted_span / max(expected_pixel_width, 1)
                    name = control.objectName() or (
                        f"{control.__class__.__name__}({text!r})"
                    )
                    raise RuntimeError(
                        f"{surface_name} was not fully rendered in "
                        f"{screenshot.name}: {name} ({ratio:.1%} text width painted)"
                    )


def _label_text_line_probes(
    label: QLabel,
    text: str,
    *,
    surface_name: str,
) -> list[tuple[QRect, int]]:
    """Return one content-margin and alignment-aware probe for each label line."""
    content_rect = label.contentsRect()
    if content_rect.width() <= 0 or content_rect.height() <= 0:
        raise RuntimeError(f"{surface_name} label has no usable contents rectangle.")

    layout = QTextLayout(text, label.font())
    options = QTextOption()
    options.setWrapMode(
        QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere
        if label.wordWrap()
        else QTextOption.WrapMode.NoWrap
    )
    layout.setTextOption(options)
    layout.beginLayout()
    lines = []
    try:
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(float(content_rect.width()))
            lines.append(line)
    finally:
        layout.endLayout()
    if not lines:
        raise RuntimeError(f"{surface_name} label has no text layout lines.")

    metrics = label.fontMetrics()
    line_heights = [max(round(line.height()), metrics.height()) for line in lines]
    required_height = sum(line_heights)
    if label.wordWrap() and required_height > content_rect.height():
        name = label.objectName() or f"QLabel({text!r})"
        raise RuntimeError(
            f"{surface_name} label text is vertically clipped: {name} "
            f"needs {required_height}px, has {content_rect.height()}px."
        )

    horizontal_alignment = label.alignment() & Qt.AlignmentFlag.AlignHorizontal_Mask
    vertical_alignment = label.alignment() & Qt.AlignmentFlag.AlignVertical_Mask
    if vertical_alignment == Qt.AlignmentFlag.AlignBottom:
        local_y = content_rect.y() + content_rect.height() - required_height
    elif vertical_alignment == Qt.AlignmentFlag.AlignTop:
        local_y = content_rect.y()
    else:
        local_y = content_rect.y() + (content_rect.height() - required_height) // 2

    probes: list[tuple[QRect, int]] = []
    for line, line_height in zip(lines, line_heights, strict=True):
        text_width = max(round(line.naturalTextWidth()), 1)
        if not label.wordWrap() and text_width > content_rect.width():
            raise RuntimeError(f"{surface_name} label text is horizontally clipped.")
        if horizontal_alignment == Qt.AlignmentFlag.AlignRight:
            local_x = content_rect.x() + content_rect.width() - text_width
        elif horizontal_alignment == Qt.AlignmentFlag.AlignHCenter:
            local_x = content_rect.x() + (content_rect.width() - text_width) // 2
        else:
            # QLabel's default horizontal alignment is left when no explicit
            # horizontal flag is present.
            local_x = content_rect.x()
        probe = QRect(local_x - 3, local_y - 3, text_width + 6, line_height + 6)
        probes.append((probe.intersected(content_rect), text_width))
        local_y += line_height
    return probes


def _physical_text_probe_bounds(
    *,
    root: QWidget,
    screenshot: Image.Image,
    top_left: QPoint,
    local_probe: QRect,
) -> tuple[int, int, int, int]:
    scale_x = screenshot.width / max(root.width(), 1)
    scale_y = screenshot.height / max(root.height(), 1)
    return (
        max(round((top_left.x() + local_probe.x()) * scale_x), 0),
        max(round((top_left.y() + local_probe.y()) * scale_y), 0),
        min(
            round((top_left.x() + local_probe.x() + local_probe.width()) * scale_x),
            screenshot.width,
        ),
        min(
            round((top_left.y() + local_probe.y() + local_probe.height()) * scale_y),
            screenshot.height,
        ),
    )


def _assert_combo_text_rendered(
    root: QWidget,
    screenshot: Path,
    control: QComboBox,
    *,
    surface_name: str,
) -> None:
    """Verify a compact selector has nonuniform pixels across its current text."""
    if not control.isVisibleTo(root) or not control.currentText():
        raise RuntimeError(f"{surface_name} is hidden or empty.")
    with Image.open(screenshot) as captured:
        grayscale = captured.convert("L")
        scale_x = grayscale.width / max(root.width(), 1)
        scale_y = grayscale.height / max(root.height(), 1)
        expected_width = control.fontMetrics().horizontalAdvance(control.currentText())
        expected_height = control.fontMetrics().height()
        top_left = control.mapTo(root, QPoint(0, 0))
        bounds = (
            max(round((top_left.x() + 8) * scale_x), 0),
            max(
                round(
                    (top_left.y() + (control.height() - expected_height) / 2 - 3)
                    * scale_y
                ),
                0,
            ),
            min(round((top_left.x() + 14 + expected_width) * scale_x), grayscale.width),
            min(
                round(
                    (top_left.y() + (control.height() + expected_height) / 2 + 3)
                    * scale_y
                ),
                grayscale.height,
            ),
        )
        region = grayscale.crop(bounds)
        histogram = region.histogram()
        background = max(range(256), key=histogram.__getitem__)
        columns = [
            x
            for x in range(region.width)
            if any(
                abs(cast(int, region.getpixel((x, y))) - background) >= 18
                for y in range(region.height)
            )
        ]
        painted_span = columns[-1] - columns[0] + 1 if columns else 0
        if painted_span < max(int(expected_width * scale_x * 0.55), 3):
            raise RuntimeError(
                f"{surface_name} was not fully rendered in {screenshot.name}."
            )


def _assert_right_panels_rendered(widget: QWidget, screenshot: Path) -> None:
    """Require the current workflow sidebar and its visible actions to paint."""
    right_panels = [
        panel
        for panel in widget.findChildren(QWidget, "RightPanel")
        if panel.isVisibleTo(widget)
    ]
    is_main_window_capture = bool(
        getattr(widget, "nav_btns", None) and getattr(widget, "stack", None)
    )
    compact_navigation = getattr(widget, "compact_nav_combo", None)
    compact_layout_active = bool(
        isinstance(compact_navigation, QComboBox)
        and compact_navigation.isVisibleTo(widget)
    )
    if is_main_window_capture and not right_panels and not compact_layout_active:
        raise RuntimeError("Main product capture is missing its workflow sidebar.")
    if not right_panels:
        return
    visible_actions: list[QWidget] = []
    for panel in right_panels:
        declared_actions = [
            action
            for action in panel.findChildren(QAbstractButton)
            if action.text().strip() and _widget_inside_capture(widget, action)
        ]
        # Evaluation and other read-only pages reuse RightPanel for aggregate
        # information and intentionally declare no workflow actions.
        if not declared_actions:
            continue
        panel_actions = [
            action for action in declared_actions if action.isVisibleTo(widget)
        ]
        if not panel_actions:
            raise RuntimeError("Workflow sidebar has no visible action contract.")
        visible_actions.extend(panel_actions)
    for panel in right_panels:
        top_left = panel.mapTo(widget, QPoint(0, 0))
        bounds = (
            top_left.x(),
            top_left.y(),
            top_left.x() + panel.width(),
            top_left.y() + panel.height(),
        )
        _assert_region_matches_reference(
            screenshot,
            bounds,
            _pixmap_image(panel.grab()),
            surface_name="Right panel",
            minimum_edge_recall=0.70,
            maximum_changed_pixel_ratio=0.55,
            content_inset=2,
        )
    if visible_actions:
        _assert_text_controls_rendered(
            widget,
            screenshot,
            visible_actions,
            surface_name="Workflow sidebar actions",
        )


def _assert_assistant_dock_rendered(
    widget: QWidget,
    screenshot: Path,
    *,
    logical_name: str | None = None,
) -> None:
    """Require the current assistant composer and Send/Stop action to be painted."""
    panel = (
        widget
        if widget.objectName() == "AssistantPanel"
        else widget.findChild(QWidget, "AssistantPanel")
    )
    if panel is None:
        if isinstance(widget, QDockWidget):
            raise RuntimeError("Assistant dock capture is missing AssistantPanel.")
        return
    with Image.open(screenshot) as captured:
        top_left = panel.mapTo(widget, QPoint(0, 0))
        scale_x = captured.width / max(widget.width(), 1)
        scale_y = captured.height / max(widget.height(), 1)
        panel_bounds = (
            max(round(top_left.x() * scale_x), 0),
            max(round(top_left.y() * scale_y), 0),
            min(round((top_left.x() + panel.width()) * scale_x), captured.width),
            min(round((top_left.y() + panel.height()) * scale_y), captured.height),
        )
    _assert_region_foreground_content(
        screenshot,
        panel_bounds,
        surface_name="Assistant content",
    )
    _assert_region_has_no_unpainted_block(
        screenshot,
        panel_bounds,
        surface_name="Assistant content",
    )
    title = widget.findChild(QWidget, "AssistantDockTitle")
    control_panel = panel.findChild(QWidget, "ControlPanel")
    send_button = getattr(panel, "send_btn", None)
    input_field = getattr(panel, "input_field", None)
    if not isinstance(send_button, QAbstractButton) or not isinstance(
        input_field,
        QWidget,
    ):
        raise RuntimeError(
            "Assistant capture is missing its composer or Send/Stop action."
        )
    if any(
        hasattr(panel, name)
        for name in ("mode_selector_widget", "ask_mode_btn", "workflow_mode_btn")
    ):
        raise RuntimeError("Assistant capture still exposes the legacy mode selector.")
    is_processing = bool(getattr(panel, "is_processing", False))
    turn_presentation = getattr(panel, "_turn_presentation", None)
    phase = getattr(turn_presentation, "phase", None)
    cancelability = getattr(
        turn_presentation,
        "cancelability",
        ChatTurnCancelability.NONE,
    )
    if not is_processing:
        expected_action = "Send"
    elif phase is ChatTurnPresentationPhase.WAITING:
        expected_action = "Waiting"
    elif cancelability is ChatTurnCancelability.CANCELLABLE:
        expected_action = "Stop"
    elif cancelability is ChatTurnCancelability.STOPPING:
        expected_action = "Stopping"
    else:
        expected_action = "Working"
    if cast(QAbstractButton, send_button).text() != expected_action:
        raise RuntimeError(
            f"Assistant capture expected {expected_action}, got "
            f"{cast(QAbstractButton, send_button).text()!r}."
        )
    paint_controls = [cast(QWidget, send_button)]
    empty_action = getattr(panel, "empty_state_action_button", None)
    legacy_empty_action = (
        cast(QAbstractButton, empty_action)
        if isinstance(empty_action, QAbstractButton)
        else None
    )
    suggestion_cards = [
        card
        for card in getattr(panel, "suggestion_prompt_buttons", ())
        if isinstance(card, AssistantSuggestionCard) and card.isVisibleTo(widget)
    ]
    empty_action_visible = bool(suggestion_cards) or (
        legacy_empty_action is not None and legacy_empty_action.isVisibleTo(widget)
    )
    if (logical_name or screenshot.name) == SCREENSHOT_NAMES[
        "assistant_empty"
    ] and not empty_action_visible:
        raise RuntimeError(
            "Assistant empty-state capture is missing its visible action button."
        )
    if suggestion_cards:
        for card in suggestion_cards:
            action_text = " ".join(card.text().split())
            if (
                not action_text
                or card.accessibleName() != action_text
                or not card.subtitle().strip()
            ):
                raise RuntimeError(
                    "Assistant suggestion is visible without current action copy."
                )
            paint_controls.extend((card.title_label, card.subtitle_label))
    elif legacy_empty_action is not None and empty_action_visible:
        action_text = " ".join(legacy_empty_action.text().split())
        if not action_text or legacy_empty_action.accessibleName() != action_text:
            raise RuntimeError(
                "Assistant empty-state action is visible without current action copy."
            )
        paint_controls.append(legacy_empty_action)
    _assert_text_controls_rendered(
        widget,
        screenshot,
        paint_controls,
        surface_name="Assistant primary controls",
    )
    _assert_widget_regions_painted(
        widget,
        screenshot,
        [title] if title is not None else [],
        surface_name="Assistant title",
        brightness_threshold=80,
        minimum_ratio=0.02,
    )
    _assert_widget_regions_painted(
        widget,
        screenshot,
        [control_panel] if control_panel is not None else [],
        surface_name="Assistant composer",
        brightness_threshold=20,
        minimum_ratio=0.85,
    )
    _assert_widget_regions_painted(
        widget,
        screenshot,
        [send_button] if isinstance(send_button, QWidget) else [],
        surface_name="Assistant Send action",
        brightness_threshold=60,
        minimum_ratio=0.05,
    )
    input_field = getattr(panel, "input_field", None)
    if not isinstance(input_field, QWidget) or not input_field.isVisibleTo(widget):
        raise RuntimeError("Assistant capture is missing its visible composer input.")
    _assert_widget_regions_painted(
        widget,
        screenshot,
        [input_field],
        surface_name="Assistant composer input",
        brightness_threshold=20,
        minimum_ratio=0.65,
    )
    _assert_assistant_feedback_rendered(
        widget,
        panel,
        screenshot,
        logical_name=logical_name or screenshot.name,
    )


def _assert_assistant_feedback_rendered(
    root: QWidget,
    panel: QWidget,
    screenshot: Path,
    *,
    logical_name: str,
) -> None:
    """Require the state-specific activity, runtime, error, or result feedback."""
    required_widgets: list[QWidget] = []
    is_processing = bool(getattr(panel, "is_processing", False))
    activity = getattr(panel, "turn_activity_widget", None)
    confirmation_card = getattr(panel, "confirmation_card_widget", None)
    if is_processing:
        if isinstance(activity, QWidget) and activity.isVisibleTo(root):
            required_widgets.append(activity)
        elif isinstance(confirmation_card, QWidget) and confirmation_card.isVisibleTo(
            root
        ):
            required_widgets.append(confirmation_card)
        else:
            raise RuntimeError(
                "Assistant processing capture is missing activity or decision feedback."
            )

    runtime_phase = getattr(getattr(panel, "_runtime_phase", None), "value", "")
    runtime_state = getattr(panel, "runtime_state_widget", None)
    if runtime_phase in {"idle", "loading", "failed"}:
        if not isinstance(runtime_state, QWidget) or not runtime_state.isVisibleTo(
            root
        ):
            raise RuntimeError(
                f"Assistant {runtime_phase} capture is missing runtime feedback."
            )
        required_widgets.append(runtime_state)

    transcript_names = {
        SCREENSHOT_NAMES["assistant_success"],
        SCREENSHOT_NAMES["assistant_error"],
    }
    if logical_name in transcript_names:
        bubbles = [
            bubble
            for bubble in panel.findChildren(MessageBubble)
            if bubble.isVisibleTo(root) and not bubble.is_user
        ]
        if not bubbles:
            raise RuntimeError(
                "Assistant result/error capture is missing transcript feedback."
            )
        required_widgets.append(bubbles[-1])

    _assert_widget_regions_painted(
        root,
        screenshot,
        required_widgets,
        surface_name="Assistant feedback",
        brightness_threshold=35,
        minimum_ratio=0.015,
    )


def _widget_inside_capture(root: QWidget, control: QWidget) -> bool:
    top_left = control.mapTo(root, control.rect().topLeft())
    bottom_right = control.mapTo(root, control.rect().bottomRight())
    return root.rect().contains(top_left) and root.rect().contains(bottom_right)


def _assert_widget_regions_painted(
    root: QWidget,
    screenshot: Path,
    controls: list[QWidget],
    *,
    surface_name: str,
    brightness_threshold: int,
    minimum_ratio: float,
) -> None:
    if not controls:
        return
    with Image.open(screenshot) as captured:
        grayscale = captured.convert("L")
        scale_x = grayscale.width / max(root.width(), 1)
        scale_y = grayscale.height / max(root.height(), 1)
        for control in controls:
            if not control.isVisible():
                continue
            top_left = control.mapTo(root, QPoint(0, 0))
            bounds = (
                max(round(top_left.x() * scale_x), 0),
                max(round(top_left.y() * scale_y), 0),
                min(
                    round((top_left.x() + control.width()) * scale_x),
                    grayscale.width,
                ),
                min(
                    round((top_left.y() + control.height()) * scale_y),
                    grayscale.height,
                ),
            )
            _assert_region_has_no_unpainted_block(
                screenshot,
                bounds,
                surface_name=surface_name,
            )
            histogram = grayscale.crop(bounds).histogram()
            pixel_count = sum(histogram)
            painted = sum(histogram[brightness_threshold:])
            if not pixel_count or painted < pixel_count * minimum_ratio:
                name = control.objectName() or control.__class__.__name__
                ratio = painted / pixel_count if pixel_count else 0.0
                raise RuntimeError(
                    f"{surface_name} was not fully rendered in "
                    f"{screenshot.name}: {name} ({ratio:.1%} painted)"
                )


def _assert_region_foreground_content(
    screenshot: Path,
    bounds: tuple[int, int, int, int],
    *,
    surface_name: str,
    minimum_foreground_ratio: float = 0.012,
    minimum_component_count: int = 3,
) -> None:
    """Reject sparse line noise that does not resemble painted UI content."""
    _assert_region_has_no_unpainted_block(
        screenshot,
        bounds,
        surface_name=surface_name,
    )
    with Image.open(screenshot) as captured:
        grayscale = captured.convert("L")
        left, top, right, bottom = bounds
        left = max(left, 0)
        top = max(top, 0)
        right = min(right, grayscale.width)
        bottom = min(bottom, grayscale.height)
        if right <= left or bottom <= top:
            raise RuntimeError(f"{surface_name} region is outside the capture.")
        region = grayscale.crop((left, top, right, bottom))

    histogram = region.histogram()
    background = max(range(256), key=histogram.__getitem__)
    width, height = region.size
    foreground = bytearray(width * height)
    foreground_count = 0
    occupied_rows: set[int] = set()
    occupied_columns: set[int] = set()
    for y in range(height):
        for x in range(width):
            pixel = cast(int, region.getpixel((x, y)))
            if abs(pixel - background) < 18:
                continue
            index = y * width + x
            foreground[index] = 1
            foreground_count += 1
            occupied_rows.add(y)
            occupied_columns.add(x)

    pixel_count = max(width * height, 1)
    foreground_ratio = foreground_count / pixel_count
    if foreground_ratio < minimum_foreground_ratio:
        raise RuntimeError(
            f"{surface_name} foreground coverage is too sparse in "
            f"{screenshot.name}: {foreground_ratio:.2%}."
        )
    row_ratio = len(occupied_rows) / max(height, 1)
    column_ratio = len(occupied_columns) / max(width, 1)
    if row_ratio < 0.08 or column_ratio < 0.12:
        raise RuntimeError(
            f"{surface_name} glyph paint span is incomplete in {screenshot.name}: "
            f"rows={row_ratio:.1%}, columns={column_ratio:.1%}."
        )

    visited = bytearray(width * height)
    meaningful_components = 0
    meaningful_pixels = 0
    for start in range(width * height):
        if not foreground[start] or visited[start]:
            continue
        stack = [start]
        visited[start] = 1
        area = 0
        min_x = width
        max_x = 0
        min_y = height
        max_y = 0
        while stack:
            index = stack.pop()
            y, x = divmod(index, width)
            area += 1
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)
            for next_x, next_y in (
                (x - 1, y),
                (x + 1, y),
                (x, y - 1),
                (x, y + 1),
            ):
                if not (0 <= next_x < width and 0 <= next_y < height):
                    continue
                next_index = next_y * width + next_x
                if foreground[next_index] and not visited[next_index]:
                    visited[next_index] = 1
                    stack.append(next_index)
        component_width = max_x - min_x + 1
        component_height = max_y - min_y + 1
        if area >= 4 and component_width >= 2 and component_height >= 2:
            meaningful_components += 1
            meaningful_pixels += area

    component_ratio = meaningful_pixels / pixel_count
    if meaningful_components < minimum_component_count or component_ratio < 0.004:
        raise RuntimeError(
            f"{surface_name} component paint is incomplete in {screenshot.name}: "
            f"components={meaningful_components}, coverage={component_ratio:.2%}."
        )


def settle_widget_for_capture(
    app: QApplication,
    widget: QWidget,
    *,
    wait_ms: int = 120,
) -> None:
    """Flush deferred layouts and paints before recording UI evidence."""
    app.processEvents()
    widget.updateGeometry()
    widget.repaint()
    for child in widget.findChildren(QWidget):
        if child.isVisible():
            child.update()
    app.processEvents()
    deadline = time.monotonic() + max(wait_ms, 0) / 1000
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def is_nearly_black(path: Path) -> bool:
    """Return whether an image contains almost no visible UI content."""
    with Image.open(path) as image:
        grayscale = image.convert("L")
        histogram = grayscale.histogram()
        pixel_count = grayscale.width * grayscale.height
        contrast = float(ImageStat.Stat(grayscale).stddev[0])
    if pixel_count <= 0:
        return True
    visible_pixels = sum(histogram[90:])
    visible_ratio = visible_pixels / pixel_count
    return visible_ratio < 0.001 or contrast < 2.0


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
    assistant_reviews = build_assistant_contract_reviews(phases)
    failed.extend(assistant_contract_findings(assistant_reviews))
    failed.extend(required_assistant_screenshot_failures(screenshots))
    failed.extend(build_workflow_contract_failures(phases))
    failed.extend(_data_import_visual_evidence_failures(phases))
    resource_smoke = build_resource_smoke_summary(resource_notes)
    failed.extend(resource_smoke["failed_checks"])
    return {
        "passed": not failed,
        "failed_checks": failed,
        "required_phase_count": len(REQUIRED_PHASES),
        "observed_phase_count": len(phase_names),
        "screenshot_count": len(set(screenshots.values())),
        "human_desktop_acceptance": "not performed",
        "resource_smoke": resource_smoke,
        **{key: assistant_reviews[key] for key in ASSISTANT_REVIEW_KEYS},
    }


def build_workflow_contract_failures(phases: list[dict[str, Any]]) -> list[str]:
    """Validate that named happy-path phases changed the real backend state."""
    by_name = {str(phase.get("phase") or ""): phase for phase in phases}
    failures: list[str] = []

    def require_command(phase_name: str, note_name: str) -> None:
        phase = by_name.get(phase_name)
        if phase is None:
            return
        result = (phase.get("notes") or {}).get(note_name)
        if not isinstance(result, dict) or not bool(result.get("ok")):
            command_name = (
                str(result.get("command") or note_name)
                if isinstance(result, dict)
                else note_name
            )
            failures.append(f"{phase_name} command {command_name} did not succeed")

    def require_state(phase_name: str, path: tuple[str, ...], message: str) -> None:
        phase = by_name.get(phase_name)
        if phase is None:
            return
        value: Any = phase.get("workflow_state", {})
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if not value:
            failures.append(f"{phase_name} {message}")

    for phase_name, note_names in {
        "data_interpretation_apply": ("applied", "recipe"),
        "data_interpretation_reload_recipe": ("reload",),
        "data_interpretation_reapply_recipe": ("reapply",),
        "preprocessing": ("preprocess",),
        "epoch_creation": ("epoch",),
        "dataset_generation": ("dataset",),
        "training_readiness": ("training", "train"),
        "evaluation_visualization_saliency_readiness": (
            "evaluate",
            "visualize",
            "saliency",
        ),
        "visualization_readiness": ("visualize", "saliency"),
        "reset_new_session_boundary": ("confirmed",),
        "error_recovery": ("recovery_scan",),
    }.items():
        for note_name in note_names:
            require_command(phase_name, note_name)

    require_state(
        "preprocessing",
        ("preprocessed", "available"),
        "did not produce preprocessed data",
    )
    require_state("epoch_creation", ("epoch", "exists"), "did not produce epochs")
    require_state(
        "dataset_generation", ("dataset", "available"), "did not produce a dataset"
    )
    require_state(
        "training_readiness",
        ("training", "finished_run_count"),
        "did not finish a training run",
    )
    training_phase = by_name.get("training_readiness")
    training_wait = (
        (training_phase.get("notes") or {}).get("training_wait")
        if training_phase is not None
        else None
    )
    if not isinstance(training_wait, dict) or not bool(training_wait.get("completed")):
        failures.append("training_readiness did not observe training completion")
    require_state(
        "evaluation_visualization_saliency_readiness",
        ("evaluation", "available"),
        "did not produce evaluation results",
    )

    intentional_failures = {
        "data_interpretation_decisions": (
            "unconfirmed_apply",
            "confirmation_required",
        ),
        "reset_new_session_boundary": ("unconfirmed", "confirmation_required"),
        "error_recovery": ("blocked_preview", "precondition"),
    }
    for phase_name, (note_name, expected_error) in intentional_failures.items():
        phase = by_name.get(phase_name)
        if phase is None:
            continue
        result = (phase.get("notes") or {}).get(note_name)
        if (
            not isinstance(result, dict)
            or bool(result.get("ok"))
            or str(result.get("error_type") or "") != expected_error
        ):
            failures.append(
                f"{phase_name} did not preserve the expected {expected_error} boundary"
            )

    return failures


def _data_import_visual_evidence_failures(
    phases: list[dict[str, Any]],
) -> list[str]:
    expected_steps = {
        "data_interpretation_scan_result": "Choose EEG Data",
        "data_interpretation_preview": "Review Metadata",
        "data_interpretation_confirm_metadata_labels": "Match Labels",
        "data_interpretation_review_and_import": "Review and Import",
    }
    by_name = {str(phase.get("phase")): phase for phase in phases}
    failures: list[str] = []
    captured_paths: list[Path] = []
    for phase_name, expected_step in expected_steps.items():
        phase = by_name.get(phase_name)
        if phase is None:
            continue
        screenshot = Path(str(phase.get("screenshot") or ""))
        if not screenshot.is_file():
            continue
        active_step = str((phase.get("notes") or {}).get("active_step") or "")
        if active_step != expected_step:
            failures.append(
                f"{phase_name} captured {active_step or 'unknown step'}; "
                f"expected {expected_step}"
            )
        captured_paths.append(screenshot)
    digests = [hashlib.sha256(path.read_bytes()).hexdigest() for path in captured_paths]
    if len(digests) != len(set(digests)):
        failures.append("Data Import walkthrough step screenshots are duplicated")
    return failures


def build_resource_smoke_summary(
    resource_notes: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Check for obvious thread or RSS regressions in the automated replay."""
    boundary = (
        "Coarse process smoke only: current RSS catches large retained-memory "
        "regressions, while max RSS is recorded as a high-water diagnostic and "
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
    current_rss_growth_kb = _resource_int(
        after_close,
        "current_rss_kb",
    ) - _resource_int(start, "current_rss_kb")
    max_rss_growth_kb = _resource_int(after_close, "max_rss_kb") - _resource_int(
        start,
        "max_rss_kb",
    )

    if after_threads > start_threads + RESOURCE_THREAD_TOLERANCE:
        failed.append(
            "Python threads did not settle: "
            f"start {start_threads}, after_close {after_threads}."
        )
    if after_qt_threads > 0:
        failed.append(f"Qt thread pool still active after close: {after_qt_threads}.")
    if current_rss_growth_kb > RESOURCE_RSS_SMOKE_LIMIT_KB:
        failed.append(
            "RSS smoke delta exceeded "
            f"{RESOURCE_RSS_SMOKE_LIMIT_KB} KB: {current_rss_growth_kb} KB."
        )

    return {
        "checked": True,
        "passed": not failed,
        "failed_checks": failed,
        "start_python_threads": start_threads,
        "after_close_python_threads": after_threads,
        "python_thread_tolerance": RESOURCE_THREAD_TOLERANCE,
        "after_close_qt_active_threads": after_qt_threads,
        "rss_growth_kb": current_rss_growth_kb,
        "rss_metric": "current_rss_kb",
        "max_rss_growth_kb": max_rss_growth_kb,
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
    chat_geometry: dict[str, dict[str, Any]] = {}
    assistant_processing: dict[str, dict[str, Any]] = {}
    assistant_runtime: dict[str, dict[str, Any]] = {}
    assistant_dock: dict[str, dict[str, Any]] = {}
    assistant_main_window: dict[str, dict[str, Any]] = {}
    assistant_notice: dict[str, dict[str, Any]] = {}
    assistant_signal_path: dict[str, dict[str, Any]] = {}
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
        if isinstance(notes, dict) and isinstance(notes.get("chat_geometry"), dict):
            chat_geometry[name] = dict(notes["chat_geometry"])
        if isinstance(notes, dict) and isinstance(
            notes.get("assistant_processing"),
            dict,
        ):
            assistant_processing[name] = dict(notes["assistant_processing"])
        for note_name, destination in (
            ("assistant_runtime", assistant_runtime),
            ("assistant_dock", assistant_dock),
            ("assistant_main_window", assistant_main_window),
            ("assistant_notice", assistant_notice),
            ("assistant_signal_path", assistant_signal_path),
        ):
            if isinstance(notes, dict) and isinstance(notes.get(note_name), dict):
                destination[name] = dict(notes[note_name])
    return {
        "visible_text_snapshots": visible_text,
        "button_states": button_states,
        "workflow_states": workflow_states,
        "backend_state_snapshots": backend_snapshots,
        "phase_screenshots": phase_screenshots,
        "ui_geometry_snapshots": ui_geometry,
        "chat_geometry_snapshots": chat_geometry,
        "assistant_processing_snapshots": assistant_processing,
        "assistant_runtime_snapshots": assistant_runtime,
        "assistant_dock_snapshots": assistant_dock,
        "assistant_main_window_snapshots": assistant_main_window,
        "assistant_notice_snapshots": assistant_notice,
        "assistant_signal_path_snapshots": assistant_signal_path,
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
                "frame_readiness": _CAPTURE_FRAME_READINESS.get(
                    str(path.resolve()),
                    {},
                ),
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
    all_phases_have_snapshots = bool(phases) and all(
        "visible_text" in phase
        and "button_state" in phase
        and "workflow_state" in phase
        and phase.get("screenshot")
        for phase in phases
    )
    table_geometry_review = build_table_geometry_review(phases)
    chat_geometry_review = build_chat_geometry_review(phases)
    assistant_reviews = build_assistant_contract_reviews(phases)
    frame_readiness_coverage = bool(screenshot_rows) and all(
        row["frame_readiness"].get("consecutive_complete_frames") == 2
        and row["frame_readiness"].get("stable") is True
        and bool(row["frame_readiness"].get("required_regions"))
        for row in screenshot_rows
    )
    return {
        "automated_checks_passed": not forbidden_rows
        and all(row["nonblank"] for row in screenshot_rows)
        and all_phases_have_snapshots
        and frame_readiness_coverage
        and table_geometry_review["passed"]
        and chat_geometry_review["passed"]
        and all(review["passed"] for review in assistant_reviews.values()),
        "screenshot_review": screenshot_rows,
        "forbidden_visible_text": forbidden_rows,
        "phase_snapshot_coverage": all_phases_have_snapshots,
        "frame_readiness_coverage": frame_readiness_coverage,
        "table_geometry_review": table_geometry_review,
        "chat_geometry_review": chat_geometry_review,
        **assistant_reviews,
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
        if lowered.lstrip().startswith("request:"):
            offenders.append(normalized)
            continue
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
    """Validate the product artifact and delegate assistant contracts."""
    if payload.get("status") != "passed":
        return False, str(payload.get("failure_reason") or "status is not passed")
    summary = payload.get("pass_fail_summary", {})
    if not summary.get("passed"):
        return False, "; ".join(summary.get("failed_checks", []))
    phases = {phase.get("phase") for phase in payload.get("phases", [])}
    missing = [phase for phase in REQUIRED_PHASES if phase not in phases]
    if missing:
        return False, f"missing phases: {', '.join(missing)}"

    assistant_ok, assistant_reason = validate_assistant_payload(
        payload,
        forbidden_visible_text=forbidden_visible_text,
    )
    if not assistant_ok:
        return False, assistant_reason

    screenshots = payload.get("screenshots", {})
    if require_files:
        for path in screenshots.values():
            if not Path(path).exists():
                return False, f"missing screenshot file: {path}"
    if not payload.get("observable_evidence"):
        return False, "observable evidence summary is missing"
    ui_quality_review = payload.get("ui_quality_review")
    if not isinstance(ui_quality_review, dict):
        return False, "ui quality review is missing"
    if not ui_quality_review.get("automated_checks_passed"):
        return False, "ui quality review did not pass"
    recorded_ok, recorded_reason = validate_recorded_assistant_reviews(
        ui_quality_review
    )
    if not recorded_ok:
        return False, recorded_reason
    geometry_review = ui_quality_review.get("table_geometry_review", {})
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
    max_rss_kb = (
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if resource is not None
        else 0
    )
    current_rss_kb = (
        int(psutil.Process(os.getpid()).memory_info().rss / 1024)
        if psutil is not None
        else max_rss_kb
    )
    return {
        "label": label,
        "pid": os.getpid(),
        "python_threads": threading.active_count(),
        "thread_names": [thread.name for thread in threading.enumerate()[:12]],
        "qt_active_threads": pool.activeThreadCount() if pool is not None else 0,
        "max_rss_kb": max_rss_kb,
        "current_rss_kb": current_rss_kb,
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
        "acceptance. Assistant states use AgentManager and Qt signals with a "
        "deterministic controller, not direct ChatController injection. This is "
        "product-surface evidence, not local-model or tool-call correctness evidence. Windows "
        "launcher click-through, dual-monitor/DPI behavior, and long real local-model "
        "desktop sessions remain human verification."
    )


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a compact Markdown report."""
    contract = payload.get("artifact_contract", {})
    run = payload.get("artifact_run", {})
    if not isinstance(contract, dict):
        contract = {}
    if not isinstance(run, dict):
        run = {}
    source_fingerprint = contract.get("source_fingerprint") or run.get(
        "source_fingerprint",
        "",
    )
    lines = [
        "# Human-Like Product Walkthrough",
        "",
        f"- status: `{payload.get('status')}`",
        f"- run ID: `{run.get('run_id', '')}`",
        f"- generated at: `{run.get('generated_at_utc', '')}`",
        f"- Git revision: `{run.get('git_revision', '')}`",
        f"- working tree dirty: `{run.get('working_tree_dirty', '')}`",
        f"- screenshot hashes: `{len(run.get('screenshot_sha256', {}))}`",
        f"- failure reason: {payload.get('failure_reason') or 'none'}",
        f"- claim boundary: {payload.get('claim_boundary')}",
        f"- evidence contract: `{contract.get('version', '')}`",
        f"- assistant driver: `{contract.get('assistant_driver', '')}`",
        f"- source fingerprint: `{source_fingerprint}`",
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
                f"- current RSS growth: `{resource_smoke.get('rss_growth_kb', 'n/a')}` KB / limit `{resource_smoke.get('rss_limit_kb', 'n/a')}` KB",
                f"- max RSS high-water growth: `{resource_smoke.get('max_rss_growth_kb', 'n/a')}` KB",
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
    chat_geometry = quality.get("chat_geometry_review", {})
    if chat_geometry:
        lines.extend(
            [
                f"- chat geometry passed: `{chat_geometry.get('passed')}`",
                f"- checked ChatPanel phases: `{chat_geometry.get('checked_widgets')}`",
                f"- chat geometry findings: `{len(chat_geometry.get('findings', []))}`",
            ]
        )
    processing_review = quality.get("assistant_processing_contract_review", {})
    if processing_review:
        processing_evidence = processing_review.get("evidence", {})
        turn_activity = processing_evidence.get("turn_activity", {})
        primary_status = turn_activity.get("primary_status", {})
        stopping_state = processing_evidence.get("stopping_state", {})
        stopping_activity = stopping_state.get("turn_activity", {})
        stop_button = processing_evidence.get("stop_button", {})
        lines.extend(
            [
                f"- assistant processing contract passed: `{processing_review.get('passed')}`",
                f"- processing status: `{primary_status.get('text', '')}`; "
                f"visible `{primary_status.get('visible')}`; "
                f"fits `{primary_status.get('fits_height')}`",
                f"- processing action: `{stop_button.get('text', '')}`; visible `{stop_button.get('visible')}`; enabled `{stop_button.get('enabled')}`",
                f"- stopping state: `{stopping_activity.get('phase', '')}`; "
                f"cancelability `{stopping_activity.get('cancelability', '')}`",
                f"- composer enabled while processing: `{processing_evidence.get('composer_input_enabled')}`",
            ]
        )
    for label, key in (
        ("assistant runtime", "assistant_runtime_contract_review"),
        ("assistant full dock", "assistant_dock_contract_review"),
        ("assistant notices", "assistant_notice_contract_review"),
        ("assistant signal path", "assistant_signal_path_review"),
        ("assistant error sanitization", "assistant_error_contract_review"),
        ("assistant backend claims", "assistant_claim_contract_review"),
        ("assistant interactions", "assistant_interaction_contract_review"),
        ("assistant settings recovery", "assistant_settings_recovery_review"),
    ):
        review = quality.get(key, {})
        if review:
            lines.append(f"- {label} passed: `{review.get('passed')}`")
    lines.extend(["", "## Observable Evidence", ""])
    evidence = payload.get("observable_evidence", {})
    lines.extend(
        [
            f"- visible text snapshots: `{len(evidence.get('visible_text_snapshots', {}))}` phases",
            f"- button states: `{len(evidence.get('button_states', {}))}` phases",
            f"- workflow/backend snapshots: `{len(evidence.get('backend_state_snapshots', {}))}` phases",
            f"- UI geometry snapshots: `{len(evidence.get('ui_geometry_snapshots', {}))}` phases",
            f"- ChatPanel geometry snapshots: `{len(evidence.get('chat_geometry_snapshots', {}))}` phases",
            f"- assistant processing snapshots: `{len(evidence.get('assistant_processing_snapshots', {}))}` phases",
            f"- assistant runtime snapshots: `{len(evidence.get('assistant_runtime_snapshots', {}))}` phases",
            f"- assistant full-dock snapshots: `{len(evidence.get('assistant_dock_snapshots', {}))}` phases",
            f"- assistant signal-path snapshots: `{len(evidence.get('assistant_signal_path_snapshots', {}))}` phases",
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
            f"qt active `{note.get('qt_active_threads')}`, "
            f"current rss `{note.get('current_rss_kb')}` KB, "
            f"max rss `{note.get('max_rss_kb')}` KB"
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
