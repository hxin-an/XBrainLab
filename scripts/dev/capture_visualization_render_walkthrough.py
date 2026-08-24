#!/usr/bin/env python3
"""Capture a true MainWindow visualization canvas render walkthrough."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import math
import os
import random
import shutil
import sys
import tempfile
import time
import traceback
from contextlib import suppress
from io import BytesIO
from pathlib import Path
from typing import Any, cast

from XBrainLab.ui.qt_runtime import (
    configure_qt_platform_for_runtime,
    drain_qt_runtime_after_event_loop,
)

configure_qt_platform_for_runtime()

from PyQt6.QtCore import QBuffer, QEventLoop, QIODevice, QTimer
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox, QScrollArea, QWidget

from scripts.dev.capture_chatpanel_local_tool_chain_walkthrough import (
    _clear_saved_main_window_geometry,
    _set_baseline_window_geometry,
)
from scripts.dev.capture_chatpanel_local_walkthrough import is_nearly_black
from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
    validate_source_identity,
)
from scripts.dev.training_evidence_fixture import (
    prepare_training_dataset_ready_state,
    write_synthetic_training_raw_fif,
)
from scripts.dev.ui_navigation import open_workflow_panel
from XBrainLab.backend.application import (
    ApplyMontageCommand,
    ConfigureTrainingCommand,
    EvaluateCommand,
    SaliencyCommand,
    TrainCommand,
    VisualizeCommand,
    get_application_service,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "dev-artifacts" / "visualization-render"
TEMP_ROOT = Path(tempfile.gettempdir())
TRAINING_OUTPUT_DIR = TEMP_ROOT / "xbrainlab-visualization-render-output"
JSON_ARTIFACT = "visualization-render-walkthrough.json"
MD_ARTIFACT = "visualization-render-walkthrough.md"
RENDER_TAB_SPECS: list[dict[str, str]] = [
    {
        "tab": "Saliency Map",
        "screenshot": "visualization-render-saliency-map.png",
        "expected_context": "True class · Mean over EEG epochs",
    },
    {
        "tab": "Spectrogram",
        "screenshot": "visualization-render-spectrogram.png",
        "expected_context": (
            "True class · Mean magnitude over EEG epochs and channels"
        ),
    },
    {
        "tab": "Topographic Map",
        "screenshot": "visualization-render-topographic-map.png",
        "expected_context": "True class · Mean over EEG epochs and time",
    },
]
THREE_D_TAB_SPECS: list[dict[str, str]] = [
    {
        "tab": "3D Plot",
        "screenshot": "visualization-render-3d-blocked.png",
        "interactive_screenshot": "visualization-render-3d-interactive.png",
        "expected_reason": "Set a 3D montage before opening the 3D plot.",
    },
]
UNCAUGHT_EXCEPTIONS: list[str] = []
DETERMINISTIC_CAPTURE_SEED = 1729
_RUNTIME_DEPENDENT = "<runtime-dependent>"
SHUTDOWN_TIMEOUT_MS = 20_000
_UNPAINTED_CAPTURE_SENTINEL = QColor(255, 0, 255)
SALIENCY_RENDER_TIMEOUT_MS = 15_000
THREE_D_CAPTURE_TIMEOUT_MS = 12_000
TOPOGRAPHIC_COLORBAR_MIN_MARGIN_PX = 6.0
LOGGER = logging.getLogger(__name__)


def _three_d_runtime_contract(
    *,
    platform_name: str | None = None,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Describe the 3-D outcome this Qt runtime must prove."""
    source = os.environ if environment is None else environment
    configured_platform = str(source.get("QT_QPA_PLATFORM", "")).strip().lower()
    if platform_name is None:
        app = QApplication.instance()
        platform_name = (
            str(cast(QApplication, app).platformName()) if app is not None else ""
        )
    active_platform = str(platform_name or configured_platform).strip().lower()
    pyvista_off_screen = str(source.get("PYVISTA_OFF_SCREEN", "")).strip().lower()
    off_screen_requested = pyvista_off_screen in {"1", "true", "yes", "on"}
    noninteractive_platform = active_platform in {"offscreen", "minimal"}
    expected_outcome = (
        "blocked" if noninteractive_platform or off_screen_requested else "rendered"
    )
    return {
        "qt_platform": active_platform or "unknown",
        "configured_qt_platform": configured_platform,
        "pyvista_off_screen": off_screen_requested,
        "display": str(source.get("DISPLAY", "")),
        "interactive_display": expected_outcome == "rendered",
        "expected_outcome": expected_outcome,
        "capture_method": (
            "vtk_framebuffer_composite"
            if expected_outcome == "rendered"
            else "qt_widget_render"
        ),
    }


def _artifact_metadata_for_runtime(contract: dict[str, Any]) -> dict[str, str]:
    platform = str(contract.get("qt_platform") or "unknown")
    if contract.get("expected_outcome") == "rendered":
        return {
            "status": "current release-candidate visualization evidence",
            "generator": "scripts/dev/capture_visualization_render_walkthrough.py",
            "environment": f"Qt {platform} interactive VisualizationPanel capture",
            "supports": (
                "MainWindow VisualizationPanel 2D saliency renders and an "
                f"interactive 3D render under Qt {platform}"
            ),
            "does_not_support": "human Windows click-through acceptance",
            "next_human_or_runtime_gate": (
                "manual desktop visualization click-through on the target Windows PC"
            ),
        }
    return {
        "status": "current release-candidate visualization evidence",
        "generator": "scripts/dev/capture_visualization_render_walkthrough.py",
        "environment": f"Qt {platform} noninteractive VisualizationPanel capture",
        "supports": (
            "MainWindow VisualizationPanel 2D saliency renders and the user-facing "
            "3D blocked state"
        ),
        "does_not_support": "interactive 3D render or human Windows click-through acceptance",
        "next_human_or_runtime_gate": (
            "repeat this walkthrough in an interactive XCB/OpenGL runtime"
        ),
    }


def _claim_boundary_for_runtime(contract: dict[str, Any]) -> dict[str, list[str]]:
    if contract.get("expected_outcome") == "rendered":
        return {
            "supports": [
                "true MainWindow VisualizationPanel Matplotlib saliency renders",
                "interactive 3D rendering with visible framebuffer evidence in the current XCB/OpenGL runtime",
            ],
            "does_not_support": ["Windows human click-through"],
        }
    return {
        "supports": [
            "true MainWindow VisualizationPanel Matplotlib saliency renders",
            "user-facing 3D blocked reason in headless/offscreen runtime",
        ],
        "does_not_support": [
            "interactive 3D render",
            "Windows human click-through",
        ],
    }


def _install_uncaught_exception_capture() -> None:
    """Capture Qt slot exceptions so walkthrough payloads cannot pass silently."""

    def _record_exception(exctype, value, tb):
        formatted = "".join(traceback.format_exception(exctype, value, tb))
        UNCAUGHT_EXCEPTIONS.append(formatted)
        sys.__excepthook__(exctype, value, tb)

    sys.excepthook = _record_exception


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for visualization screenshots and transcript artifacts.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=420,
        help="Maximum time for tiny training and render capture.",
    )
    parser.add_argument(
        "--training-output-dir",
        default=str(TRAINING_OUTPUT_DIR),
        help="Temporary directory for tiny training outputs.",
    )
    args = parser.parse_args()
    _install_uncaught_exception_capture()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    training_output_dir = Path(args.training_output_dir)
    if training_output_dir.exists():
        shutil.rmtree(training_output_dir)
    training_output_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    payload = run_visualization_render_walkthrough(
        app,
        output_dir,
        training_output_dir,
        args.timeout_seconds,
    )
    _write_artifacts(output_dir, payload)
    print(f"Wrote {output_dir / JSON_ARTIFACT}")
    print(f"Wrote {output_dir / MD_ARTIFACT}")
    return 0 if payload["status"] == "passed" else 1


def run_visualization_render_walkthrough(
    app: QApplication,
    output_dir: Path,
    training_output_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Prepare a tiny trained state and capture real VisualizationPanel renders."""
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.main_window import MainWindow

    UNCAUGHT_EXCEPTIONS.clear()
    _remove_previous_visualization_screenshots(output_dir)
    _install_uncaught_exception_capture()
    _set_deterministic_capture_seed()
    started_at = time.monotonic()
    source_identity_at_start = collect_source_identity(ROOT, refresh=True)
    _clear_saved_main_window_geometry()
    source_path = write_synthetic_training_raw_fif()
    study = Study()
    service = get_application_service(study)
    dataset_preparation = prepare_training_dataset_ready_state(
        study,
        source_path,
        training_output_dir,
    )
    three_d_runtime = _three_d_runtime_contract()
    payload: dict[str, Any] = {
        "status": "running",
        "failure_reason": "",
        "source_identity_at_start": source_identity_at_start,
        "source_identity_at_completion": {},
        "source_identity": {},
        "source_capture": {},
        "artifact_metadata": _artifact_metadata_for_runtime(three_d_runtime),
        "source_path": str(source_path),
        "training_output_dir": str(training_output_dir),
        "dataset_preparation": dataset_preparation,
        "training": {
            "commands": [],
            "finished_run_count": 0,
            "metrics_available": False,
            "saliency_available": False,
        },
        "application_evaluate": {},
        "application_visualize": {},
        "saliency_compute": {},
        "three_d_runtime": three_d_runtime,
        "renders": [],
        "blocked_renders": [],
        "interactive_renders": [],
        "claim_boundary": _claim_boundary_for_runtime(three_d_runtime),
        "dismissed_dialogs": [],
        "screenshots": {"ready": ""},
        "final_state": {},
        "shutdown": {},
        "ui_state": {},
        "elapsed_seconds": 0.0,
        "uncaught_exceptions": [],
    }

    if not dataset_preparation.get("ok"):
        return _finish_payload(
            payload,
            service,
            started_at,
            "Dataset preparation failed.",
        )

    training_ok = _prepare_tiny_trained_state(
        app,
        service,
        training_output_dir,
        timeout_seconds,
        started_at,
        payload,
    )
    if not training_ok:
        return _finish_payload(
            payload,
            service,
            started_at,
            payload.get("failure_reason") or "Tiny training did not complete.",
        )

    window = MainWindow(study)
    _set_baseline_window_geometry(window)
    _schedule_message_box_dismissal(payload)
    window.show()
    _process_events(app, 300)
    panel = cast(
        Any,
        open_workflow_panel(window, 4, timeout_ms=int(timeout_seconds * 1_000)),
    )
    _process_events(app, 800)
    panel.normalize_check.setChecked(True)
    _process_events(app, 150)

    payload["saliency_compute"] = _compute_saliency_for_capture(
        app,
        panel,
        service,
        timeout_seconds=timeout_seconds,
    )
    payload["training"]["saliency_available"] = bool(
        payload["saliency_compute"].get("saliency_available")
    )
    _process_events(app, 300)

    payload["ui_state"] = {
        "current_panel": "Visualization",
        "plan": panel.plan_combo.currentText(),
        "run": panel.run_combo.currentText(),
        "method": panel.method_combo.currentText(),
        "normalize": panel.normalize_check.isChecked(),
        "control_layout": _control_layout_evidence(panel),
    }
    payload["application_evaluate"] = _command_payload(
        service.execute(EvaluateCommand()),
    )
    payload["application_visualize"] = _command_payload(
        service.execute(VisualizeCommand(view="Saliency Map")),
    )

    for spec in RENDER_TAB_SPECS:
        render = _capture_render_tab(app, window, output_dir, spec)
        payload["renders"].append(render)
        if not render["ok"]:
            break
    if payload["renders"]:
        payload["screenshots"]["ready"] = payload["renders"][0]["screenshot"]
    if all(render.get("ok") for render in payload["renders"]):
        for spec in THREE_D_TAB_SPECS:
            if three_d_runtime["expected_outcome"] == "blocked":
                payload["blocked_renders"].append(
                    _capture_blocked_tab(app, window, output_dir, spec),
                )
            else:
                payload["interactive_renders"].append(
                    _capture_interactive_tab(app, window, output_dir, spec),
                )

    payload["final_state"] = service.get_state().to_dict()
    payload["shutdown"] = _close_window_for_capture(app, window)
    payload["uncaught_exceptions"] = list(UNCAUGHT_EXCEPTIONS)
    _seal_source_identity(payload)
    ok, reason = validate_visualization_render_payload(payload)
    payload["status"] = "passed" if ok else "failed"
    payload["failure_reason"] = "" if ok else reason
    payload["elapsed_seconds"] = round(time.monotonic() - started_at, 3)
    return payload


def _shutdown_snapshot_is_clean(snapshot: object) -> bool:
    if not isinstance(snapshot, dict):
        return False
    return (
        snapshot.get("application_closed") is True
        and snapshot.get("pre_close_application_idle") is True
        and snapshot.get("pre_close_remaining_workers") == 0
        and snapshot.get("pre_close_remaining_subprocesses") == 0
        and isinstance(snapshot.get("close_attempt_id"), str)
        and bool(str(snapshot["close_attempt_id"]).strip())
    )


def _close_window_for_capture(app: QApplication, window: Any) -> dict[str, Any]:
    """Observe clean MainWindow shutdown before native wrappers are finalized."""
    snapshots: list[dict[str, Any]] = []
    shutdown_loop = QEventLoop()
    shutdown_timer = QTimer()
    shutdown_timer.setSingleShot(True)

    def _finish_shutdown(snapshot: object) -> None:
        if isinstance(snapshot, dict):
            snapshots.append(dict(snapshot))
        if shutdown_loop.isRunning():
            shutdown_loop.quit()

    app.setQuitOnLastWindowClosed(False)
    window.shutdown_completed.connect(_finish_shutdown)
    shutdown_timer.timeout.connect(shutdown_loop.quit)
    shutdown_timer.start(SHUTDOWN_TIMEOUT_MS)
    QTimer.singleShot(0, window.close)
    shutdown_loop.exec()
    timed_out = not snapshots and not shutdown_timer.isActive()
    shutdown_timer.stop()
    app.processEvents()

    snapshot = snapshots[-1] if snapshots else None
    try:
        window_visible = bool(window.isVisible())
    except RuntimeError:
        window_visible = False
    clean = _shutdown_snapshot_is_clean(snapshot) and not window_visible
    if clean:
        with suppress(RuntimeError):
            window.deleteLater()
    drain_qt_runtime_after_event_loop(app)
    app.quit()
    return {
        "ok": clean,
        "timed_out": timed_out,
        "window_visible": window_visible,
        "snapshot": snapshot or {},
    }


def _prepare_tiny_trained_state(
    app: QApplication,
    service: Any,
    training_output_dir: Path,
    timeout_seconds: int,
    started_at: float,
    payload: dict[str, Any],
) -> bool:
    commands = [
        ConfigureTrainingCommand(model_name="EEGNet"),
        ConfigureTrainingCommand(
            epoch=1,
            batch_size=2,
            learning_rate=0.001,
            device="cpu",
            output_dir=str(training_output_dir),
        ),
        SaliencyCommand(method="Gradient", params={}),
        ApplyMontageCommand(
            channels=["C3", "C4", "Cz", "Pz"],
            positions=[
                (-0.06, 0.0, 0.0),
                (0.06, 0.0, 0.0),
                (0.0, 0.04, 0.0),
                (0.0, -0.08, 0.0),
            ],
            montage_name="synthetic-4ch",
        ),
        TrainCommand(confirmed=True, interactive=False),
    ]
    for command in commands:
        result = service.execute(command)
        payload["training"]["commands"].append(_command_payload(result))
        if result.failed:
            payload["failure_reason"] = result.message
            return False

    while time.monotonic() - started_at < timeout_seconds:
        state = service.get_state().to_dict()
        training = _section(state, "training")
        evaluation = _section(state, "evaluation")
        visualization = _section(state, "visualization")
        if training.get("has_trainer") and not training.get("is_running"):
            payload["training"].update(
                {
                    "finished_run_count": training.get("finished_run_count"),
                    "metrics_available": evaluation.get("metrics_available"),
                    "saliency_available": visualization.get("saliency_available"),
                },
            )
            return int(training.get("finished_run_count") or 0) >= 1
        app.processEvents()
        time.sleep(0.5)
    payload["failure_reason"] = f"Timed out after {timeout_seconds} seconds."
    return False


def _capture_render_tab(
    app: QApplication,
    window: Any,
    output_dir: Path,
    spec: dict[str, str],
) -> dict[str, Any]:
    panel = window.visualization_panel
    tab_name = spec["tab"]
    tab_index = _find_tab_index(panel, tab_name)
    if tab_index < 0:
        return {
            "tab": tab_name,
            "screenshot": "",
            "ok": False,
            "failure_reason": f"Tab not found: {tab_name}",
            "error_visible": False,
            "error_text": "",
            "axes_count": 0,
            "image_count": 0,
            "canvas_visible": False,
        }

    widget = panel.tabs.widget(tab_index)
    previous_generation = int(getattr(widget, "_plot_generation", 0) or 0)
    tabs_were_blocked = panel.tabs.blockSignals(True)
    panel.tabs.setCurrentIndex(tab_index)
    panel.tabs.blockSignals(tabs_were_blocked)
    method_was_blocked = panel.method_combo.blockSignals(True)
    panel.method_combo.setCurrentText("Gradient")
    panel.method_combo.blockSignals(method_was_blocked)
    _process_events(app, 50)
    panel.on_tab_changed(tab_index)
    render_settled = _wait_for_saliency_render(
        app,
        widget,
        minimum_generation=previous_generation + 1,
        require_visible_result=True,
    )
    canvas = getattr(widget, "canvas", None)
    draw = getattr(canvas, "draw", None)
    if callable(draw):
        draw()
        _process_events(app, 100)
    # Processing the draw can deliver a newer queued render publication. Use
    # the canvas that is currently owned by the view, not a deleted predecessor.
    canvas = getattr(widget, "canvas", None)
    evidence = _render_evidence(widget, window)
    explanation_context = _explanation_context_from_panel(panel)
    expected_context = spec["expected_context"]
    screenshot_path = output_dir / spec["screenshot"]
    capture_code = _capture_matplotlib_window(
        window,
        canvas,
        screenshot_path,
        canvas_geometry=evidence["canvas_geometry"],
    )
    screenshot_sha256 = ""
    if capture_code == 0:
        screenshot_path, screenshot_sha256 = _content_addressed_screenshot_path(
            screenshot_path
        )
    screenshot_region = _screenshot_region_evidence(
        screenshot_path,
        evidence["canvas_geometry"],
        window_size=evidence["window_size"],
        require_chromatic_content=True,
    )
    render_evidence = {
        **evidence,
        "render_settled": render_settled,
        "screenshot_region": screenshot_region,
    }
    colorbar_margin_ok = (
        tab_name != "Topographic Map"
        or float(evidence["artist_layout"].get("right_margin_pixels") or 0.0)
        >= TOPOGRAPHIC_COLORBAR_MIN_MARGIN_PX
    )
    render_evidence["colorbar_margin_ok"] = colorbar_margin_ok
    ok = (
        capture_code == 0
        and render_settled
        and not evidence["error_visible"]
        and evidence["canvas_visible"]
        and evidence["canvas_geometry"]["ok"]
        and evidence["artist_layout"]["ok"]
        and colorbar_margin_ok
        and evidence["axes_count"] > 0
        and evidence["image_count"] > 0
        and screenshot_region["ok"]
        and _provenance_context_matches(explanation_context, expected_context)
    )
    return {
        "tab": tab_name,
        "transform_controls": _transform_control_evidence(panel),
        "screenshot": _artifact_path(screenshot_path),
        "screenshot_sha256": screenshot_sha256,
        "ok": ok,
        "failure_reason": ""
        if ok
        else _render_failure_reason(tab_name, render_evidence),
        "render_settled": render_settled,
        "colorbar_margin_ok": colorbar_margin_ok,
        "screenshot_region": screenshot_region,
        "explanation_context": explanation_context,
        **evidence,
    }


def _explanation_context_from_panel(panel: Any) -> str:
    """Read aggregation semantics from the explanation tabs tooltip."""
    tabs = getattr(panel, "tabs", None)
    text = getattr(tabs, "toolTip", None)
    if not callable(text):
        raise RuntimeError("Visualization aggregation information is unavailable.")
    context = str(text()).strip()
    if not context:
        raise RuntimeError("Visualization aggregation information is empty.")
    return context


def _provenance_context_matches(context: str, expected_aggregation: str) -> bool:
    """Require dataset, fold/model and run identity before aggregation text."""
    suffix = expected_aggregation.strip()
    text = context.strip()
    if not suffix or not text.endswith(suffix):
        return False
    identity_text = text[: -len(suffix)].rstrip(" ·")
    identity = [part.strip() for part in identity_text.split(" · ") if part.strip()]
    if len(identity) != 3:
        return False
    dataset_label, plan_label, run_label = identity
    fold_number = plan_label.removeprefix("Fold ")
    return (
        bool(dataset_label)
        and fold_number.isdigit()
        and int(fold_number) > 0
        and bool(run_label)
    )


def _wait_for_saliency_render(
    app: QApplication,
    widget: Any,
    *,
    timeout_ms: int = SALIENCY_RENDER_TIMEOUT_MS,
    minimum_generation: int | None = None,
    require_visible_result: bool = False,
) -> bool:
    """Wait for the observable render job instead of assuming a fixed delay."""
    deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
    while time.monotonic() <= deadline:
        app.processEvents()
        workers = getattr(widget, "_render_workers", None)
        label = getattr(widget, "error_label", None)
        label_text = label.text() if isinstance(label, QLabel) else ""
        loading_message_visible = bool(
            isinstance(label, QLabel)
            and not label.isHidden()
            and label_text == "Rendering saliency..."
        )
        generation_ready = (
            minimum_generation is None
            or int(getattr(widget, "_plot_generation", 0) or 0) >= minimum_generation
        )
        canvas = getattr(widget, "canvas", None)
        canvas_visible = bool(canvas is not None and canvas.isVisible())
        terminal_message_visible = bool(
            isinstance(label, QLabel)
            and label.isVisible()
            and label_text
            and not loading_message_visible
        )
        result_visible = (
            not require_visible_result or canvas_visible or terminal_message_visible
        )
        if (
            generation_ready
            and not workers
            and not loading_message_visible
            and result_visible
        ):
            return True
        time.sleep(0.01)
    return False


def _compute_saliency_for_capture(
    app: QApplication,
    panel: Any,
    service: Any,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Exercise the visible Compute Saliency action and await its publication."""
    outcome = panel.compute_saliency()
    action_status = str(getattr(getattr(outcome, "status", None), "value", ""))
    action_message = str(getattr(outcome, "message", "") or "")
    button = panel.compute_saliency_btn
    evidence = {
        "ok": False,
        "action_status": action_status,
        "action_message": action_message,
        "operation_phase": str(button.property("operationPhase") or ""),
        "saliency_available": False,
    }
    if action_status not in {"accepted", "completed"}:
        return evidence

    deadline = time.monotonic() + max(0, timeout_seconds)
    while time.monotonic() <= deadline:
        app.processEvents()
        state = service.get_state().to_dict()
        saliency_available = bool(
            _section(state, "visualization").get("saliency_available")
        )
        operation_phase = str(button.property("operationPhase") or "")
        evidence.update(
            {
                "operation_phase": operation_phase,
                "saliency_available": saliency_available,
            }
        )
        if operation_phase in {"cancelled", "failed"}:
            return evidence
        if operation_phase == "completed" and saliency_available:
            evidence["ok"] = True
            return evidence
        time.sleep(0.01)
    return evidence


def _wait_for_3d_capture_terminal_state(
    app: QApplication,
    widget: Any,
    *,
    expected_outcome: str,
    expected_reason: str,
    window: Any | None = None,
    timeout_ms: int = THREE_D_CAPTURE_TIMEOUT_MS,
) -> dict[str, Any]:
    """Wait for the runtime probe or 3-D engine to publish a terminal UI state."""
    deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
    last_render_evidence: dict[str, Any] = {}
    while time.monotonic() <= deadline:
        app.processEvents()
        probe_pending = getattr(widget, "_runtime_probe_worker", None) is not None
        engine_pending = getattr(widget, "_engine_worker", None) is not None
        blocked_reason_visible = bool(_visible_label_text(widget, expected_reason))
        if window is not None:
            last_render_evidence = _interactive_3d_render_evidence(widget, window)
        if not probe_pending and not engine_pending:
            if expected_outcome == "blocked" and blocked_reason_visible:
                return {
                    "settled": True,
                    "outcome": "blocked",
                    "render_evidence": last_render_evidence,
                }
            if expected_outcome == "rendered" and last_render_evidence.get("ok"):
                return {
                    "settled": True,
                    "outcome": "rendered",
                    "render_evidence": last_render_evidence,
                }
        time.sleep(0.01)
    return {
        "settled": False,
        "outcome": "timeout",
        "render_evidence": last_render_evidence,
    }


def _interactive_3d_render_evidence(widget: Any, window: Any) -> dict[str, Any]:
    """Read observable VTK and Qt facts without treating allocation as a render."""
    plotter = getattr(widget, "plotter_widget", None)
    if plotter is None:
        return {
            "ok": False,
            "reason": "PyVista plotter was not created",
            "plotter_created": False,
            "plotter_visible": False,
            "plotter_geometry": {"ok": False, "reason": "plotter is missing"},
            "render_window_rendered": False,
            "render_window_size": {"width": 0, "height": 0},
            "actor_count": 0,
            "last_render_seconds": 0.0,
        }

    geometry = _widget_geometry(plotter, window)
    render_window = getattr(plotter, "render_window", None)
    renderer = getattr(plotter, "renderer", None)
    never_rendered = _safe_call(render_window, "GetNeverRendered", default=1)
    render_size = _safe_call(render_window, "GetSize", default=(0, 0))
    if not isinstance(render_size, (tuple, list)) or len(render_size) < 2:
        render_size = (0, 0)
    actors = _safe_call(renderer, "GetActors", default=None)
    actor_count = int(_safe_call(actors, "GetNumberOfItems", default=0) or 0)
    if actor_count <= 0:
        renderer_actors = getattr(renderer, "actors", None)
        if isinstance(renderer_actors, dict):
            actor_count = len(renderer_actors)
    last_render_seconds = float(
        _safe_call(renderer, "GetLastRenderTimeInSeconds", default=0.0) or 0.0
    )
    render_window_rendered = bool(
        render_window is not None
        and int(never_rendered or 0) == 0
        and int(render_size[0]) > 0
        and int(render_size[1]) > 0
        and last_render_seconds > 0.0
    )
    error_text = _visible_label_text(widget, "Error:")
    ok = bool(
        plotter.isVisible()
        and geometry.get("ok")
        and render_window_rendered
        and actor_count > 0
        and not error_text
    )
    if error_text:
        reason = error_text
    elif not geometry.get("ok"):
        reason = str(geometry.get("reason") or "plotter geometry is invalid")
    elif not render_window_rendered:
        reason = "VTK render window has not completed a visible render"
    elif actor_count <= 0:
        reason = "VTK renderer has no visible actors"
    else:
        reason = ""
    return {
        "ok": ok,
        "reason": reason,
        "plotter_created": True,
        "plotter_visible": bool(plotter.isVisible()),
        "plotter_geometry": geometry,
        "render_window_rendered": render_window_rendered,
        "render_window_size": {
            "width": int(render_size[0]),
            "height": int(render_size[1]),
        },
        "actor_count": actor_count,
        "last_render_seconds": last_render_seconds,
        "error_text": error_text,
    }


def _safe_call(target: Any, method_name: str, *, default: Any) -> Any:
    method = getattr(target, method_name, None)
    if not callable(method):
        return default
    try:
        return method()
    except Exception:
        return default


def _capture_blocked_tab(
    app: QApplication,
    window: Any,
    output_dir: Path,
    spec: dict[str, str],
) -> dict[str, Any]:
    panel = window.visualization_panel
    tab_name = spec["tab"]
    tab_index = _find_tab_index(panel, tab_name)
    if tab_index < 0:
        return {
            "tab": tab_name,
            "screenshot": "",
            "ok": False,
            "failure_reason": f"Tab not found: {tab_name}",
            "blocked_reason": "",
            "plotter_created": False,
        }
    panel.tabs.setCurrentIndex(tab_index)
    _process_events(app, 50)
    widget = panel.tabs.currentWidget()
    expected_reason = spec["expected_reason"]
    terminal_settled = _wait_for_3d_capture_terminal_state(
        app,
        widget,
        expected_outcome="blocked",
        expected_reason=expected_reason,
    )
    blocked_reason = _visible_label_text(widget, expected_reason)
    message_evidence = _blocked_message_evidence(widget, expected_reason)
    message_geometry = _visible_label_geometry(widget, window, expected_reason)
    plotter_created = bool(getattr(widget, "plotter_widget", None))
    screenshot_path = output_dir / spec["screenshot"]
    capture_code = _capture_fully_rendered_window(
        window,
        screenshot_path,
        capture_method="qt_widget_grab",
    )
    screenshot_sha256 = ""
    if capture_code == 0:
        screenshot_path, screenshot_sha256 = _content_addressed_screenshot_path(
            screenshot_path
        )
    screenshot_region = _screenshot_region_evidence(
        screenshot_path,
        message_geometry,
        window_size={"width": int(window.width()), "height": int(window.height())},
        require_chromatic_content=True,
        allow_sparse_foreground=True,
    )
    ok = (
        capture_code == 0
        and terminal_settled["settled"]
        and terminal_settled["outcome"] == "blocked"
        and expected_reason in blocked_reason
        and not plotter_created
        and message_evidence["ok"]
        and message_geometry["ok"]
        and screenshot_region["ok"]
    )
    return {
        "tab": tab_name,
        "screenshot": _artifact_path(screenshot_path),
        "screenshot_sha256": screenshot_sha256,
        "ok": ok,
        "failure_reason": ""
        if ok
        else (f"{tab_name} did not settle on an unclipped expected blocked reason."),
        "terminal_settled": terminal_settled["settled"],
        "outcome": terminal_settled["outcome"],
        "blocked_reason": blocked_reason,
        "message_evidence": message_evidence,
        "message_geometry": message_geometry,
        "screenshot_region": screenshot_region,
        "plotter_created": plotter_created,
    }


def _capture_interactive_tab(
    app: QApplication,
    window: Any,
    output_dir: Path,
    spec: dict[str, str],
) -> dict[str, Any]:
    panel = window.visualization_panel
    tab_name = spec["tab"]
    tab_index = _find_tab_index(panel, tab_name)
    if tab_index < 0:
        return {
            "tab": tab_name,
            "screenshot": "",
            "ok": False,
            "failure_reason": f"Tab not found: {tab_name}",
            "outcome": "missing",
            "terminal_settled": False,
            "plotter_created": False,
        }
    panel.tabs.setCurrentIndex(tab_index)
    _process_events(app, 50)
    widget = panel.tabs.currentWidget()
    terminal = _wait_for_3d_capture_terminal_state(
        app,
        widget,
        window=window,
        expected_outcome="rendered",
        expected_reason=spec["expected_reason"],
    )
    plotter = getattr(widget, "plotter_widget", None)
    if terminal["settled"] and plotter is not None:
        render = getattr(plotter, "render", None)
        if callable(render):
            render()
        plotter.update()
        plotter.repaint()
        _process_events(app, 150)
        terminal = _wait_for_3d_capture_terminal_state(
            app,
            widget,
            window=window,
            expected_outcome="rendered",
            expected_reason=spec["expected_reason"],
            timeout_ms=1000,
        )

    render_evidence = terminal.get("render_evidence") or {}
    plotter_geometry = render_evidence.get("plotter_geometry") or {
        "ok": False,
        "reason": "plotter geometry is missing",
    }
    screenshot_path = output_dir / spec["interactive_screenshot"]
    runtime_contract = _three_d_runtime_contract()
    capture_method = str(runtime_contract["capture_method"])
    if capture_method == "vtk_framebuffer_composite":
        capture_code = _capture_interactive_3d_window(
            window,
            plotter,
            screenshot_path,
            plotter_geometry=plotter_geometry,
        )
    else:
        capture_code = _capture_fully_rendered_window(
            window,
            screenshot_path,
            capture_method=capture_method,
        )
    screenshot_sha256 = ""
    if capture_code == 0:
        screenshot_path, screenshot_sha256 = _content_addressed_screenshot_path(
            screenshot_path
        )
    screenshot_region = _screenshot_region_evidence(
        screenshot_path,
        plotter_geometry,
        window_size={"width": int(window.width()), "height": int(window.height())},
        require_chromatic_content=True,
    )
    ok = bool(
        capture_code == 0
        and terminal["settled"]
        and terminal["outcome"] == "rendered"
        and render_evidence.get("ok")
        and screenshot_region.get("ok")
        and not UNCAUGHT_EXCEPTIONS
    )
    failure_reason = ""
    if not ok:
        failure_reason = _interactive_3d_failure_reason(
            terminal,
            screenshot_region,
            capture_code,
        )
    return {
        "tab": tab_name,
        "screenshot": _artifact_path(screenshot_path),
        "screenshot_sha256": screenshot_sha256,
        "ok": ok,
        "failure_reason": failure_reason,
        "outcome": terminal["outcome"],
        "terminal_settled": terminal["settled"],
        "plotter_created": bool(render_evidence.get("plotter_created")),
        "plotter_visible": bool(render_evidence.get("plotter_visible")),
        "plotter_geometry": plotter_geometry,
        "render_evidence": render_evidence,
        "screenshot_region": screenshot_region,
        "capture_method": capture_method,
    }


def _interactive_3d_failure_reason(
    terminal: dict[str, Any],
    screenshot_region: dict[str, Any],
    capture_code: int,
) -> str:
    if not terminal.get("settled"):
        evidence = terminal.get("render_evidence") or {}
        detail = evidence.get("reason") or "render did not reach a terminal state"
        return f"3D Plot timed out: {detail}."
    evidence = terminal.get("render_evidence") or {}
    if not evidence.get("ok"):
        return f"3D Plot render evidence failed: {evidence.get('reason') or 'unknown'}"
    if capture_code != 0:
        return "3D Plot native-window screenshot capture failed."
    if not screenshot_region.get("ok"):
        detail = screenshot_region.get("reason") or "framebuffer paint evidence failed"
        return f"3D Plot {detail}."
    if UNCAUGHT_EXCEPTIONS:
        return "3D Plot emitted an uncaught Qt/runtime exception."
    return "3D Plot render validation failed."


def _render_evidence(widget: Any, window: Any) -> dict[str, Any]:
    fig = getattr(widget, "fig", None)
    axes = list(getattr(fig, "axes", []) or [])
    image_count = sum(
        len(getattr(axis, "images", []) or [])
        + len(getattr(axis, "collections", []) or [])
        for axis in axes
    )
    error_label = getattr(widget, "error_label", None)
    canvas = getattr(widget, "canvas", None)
    canvas_geometry = _widget_geometry(canvas, window)
    artist_layout = _matplotlib_layout_evidence(fig, canvas)
    return {
        "error_visible": bool(error_label and error_label.isVisible()),
        "error_text": str(error_label.text()) if error_label else "",
        "axes_count": len(axes),
        "image_count": image_count,
        "canvas_visible": bool(canvas and canvas.isVisible()),
        "canvas_geometry": canvas_geometry,
        "artist_layout": artist_layout,
        "window_size": {
            "width": int(window.width()),
            "height": int(window.height()),
        },
    }


def _matplotlib_layout_evidence(fig: Any, canvas: Any) -> dict[str, Any]:
    """Report Matplotlib artists that extend outside the visible canvas."""
    if fig is None or canvas is None:
        return {
            "ok": False,
            "reason": "Matplotlib figure or canvas is missing",
            "clipped_axes": [],
            "axes_bounds": [],
            "canvas_size": {"width": 0, "height": 0},
            "right_margin_pixels": 0.0,
        }
    draw = getattr(canvas, "draw", None)
    get_renderer = getattr(canvas, "get_renderer", None)
    get_width_height = getattr(canvas, "get_width_height", None)
    if (
        not callable(draw)
        or not callable(get_renderer)
        or not callable(get_width_height)
    ):
        return {
            "ok": False,
            "reason": "Matplotlib canvas cannot provide render geometry",
            "clipped_axes": [],
            "axes_bounds": [],
            "canvas_size": {"width": 0, "height": 0},
            "right_margin_pixels": 0.0,
        }

    draw()
    renderer = get_renderer()
    width, height = cast(tuple[int, int], get_width_height())
    tolerance = 2.0
    axes_bounds: list[dict[str, float | int | bool]] = []
    clipped_axes: list[int] = []
    for index, axis in enumerate(list(getattr(fig, "axes", []) or [])):
        bounds = axis.get_tightbbox(renderer)
        if bounds is None:
            continue
        clipped = bool(
            bounds.x0 < -tolerance
            or bounds.y0 < -tolerance
            or bounds.x1 > float(width) + tolerance
            or bounds.y1 > float(height) + tolerance
        )
        axes_bounds.append(
            {
                "axis": index,
                "x0": round(float(bounds.x0), 3),
                "y0": round(float(bounds.y0), 3),
                "x1": round(float(bounds.x1), 3),
                "y1": round(float(bounds.y1), 3),
                "clipped": clipped,
            }
        )
        if clipped:
            clipped_axes.append(index)
    reason = (
        f"axes {', '.join(str(index) for index in clipped_axes)} extend beyond the canvas"
        if clipped_axes
        else ""
    )
    return {
        "ok": not clipped_axes,
        "reason": reason,
        "clipped_axes": clipped_axes,
        "axes_bounds": axes_bounds,
        "canvas_size": {"width": int(width), "height": int(height)},
        "right_margin_pixels": round(
            float(width)
            - max(
                (float(bounds["x1"]) for bounds in axes_bounds),
                default=float(width),
            ),
            3,
        ),
    }


def _widget_geometry(widget: Any, window: Any) -> dict[str, Any]:
    if widget is None:
        return {
            "ok": False,
            "reason": "widget is missing",
            "x": 0,
            "y": 0,
            "width": 0,
            "height": 0,
        }
    rect = widget.rect()
    top_left = widget.mapTo(window, rect.topLeft())
    geometry: dict[str, Any] = {
        "x": int(top_left.x()),
        "y": int(top_left.y()),
        "width": int(rect.width()),
        "height": int(rect.height()),
    }
    in_bounds = (
        geometry["x"] >= 0
        and geometry["y"] >= 0
        and geometry["x"] + geometry["width"] <= int(window.width())
        and geometry["y"] + geometry["height"] <= int(window.height())
    )
    large_enough = geometry["width"] >= 160 and geometry["height"] >= 160
    geometry.update(
        {
            "ok": bool(widget.isVisible() and in_bounds and large_enough),
            "reason": ""
            if widget.isVisible() and in_bounds and large_enough
            else "widget is hidden, clipped, or too small",
        }
    )
    return geometry


def _visible_label_geometry(
    widget: Any,
    window: Any,
    expected_text: str,
) -> dict[str, Any]:
    labels = [
        label
        for label in widget.findChildren(QLabel)
        if not label.isHidden() and expected_text in label.text()
    ]
    if not labels:
        return {
            "ok": False,
            "reason": "expected label is missing",
            "x": 0,
            "y": 0,
            "width": 0,
            "height": 0,
        }
    label = labels[0]
    rect = label.rect()
    top_left = label.mapTo(window, rect.topLeft())
    geometry: dict[str, Any] = {
        "x": int(top_left.x()),
        "y": int(top_left.y()),
        "width": int(rect.width()),
        "height": int(rect.height()),
    }
    in_bounds = (
        geometry["x"] >= 0
        and geometry["y"] >= 0
        and geometry["x"] + geometry["width"] <= int(window.width())
        and geometry["y"] + geometry["height"] <= int(window.height())
    )
    geometry.update(
        {
            "ok": bool(label.isVisible() and in_bounds and label.height() >= 20),
            "reason": ""
            if label.isVisible() and in_bounds and label.height() >= 20
            else "message label is hidden or clipped",
        }
    )
    return geometry


def _visible_label_text(widget: Any, expected_text: str) -> str:
    labels = [
        label.text()
        for label in widget.findChildren(QLabel)
        if not label.isHidden() and expected_text in label.text()
    ]
    return labels[0] if labels else ""


def _control_layout_evidence(panel: Any) -> dict[str, Any]:
    widgets = {
        "plan": getattr(panel, "plan_combo", None),
        "run": getattr(panel, "run_combo", None),
        "method": getattr(panel, "method_combo", None),
        "absolute": getattr(panel, "abs_check", None),
        "normalize": getattr(panel, "normalize_check", None),
    }
    rects = {
        name: _global_widget_rect(widget) for name, widget in widgets.items() if widget
    }
    hidden = [
        name
        for name, widget in widgets.items()
        if not widget
        or not widget.isVisible()
        or widget.width() <= 0
        or widget.height() <= 0
    ]
    overlaps: list[str] = []
    names = list(rects)
    for left_index, left_name in enumerate(names):
        for right_name in names[left_index + 1 :]:
            if _rects_intersect(rects[left_name], rects[right_name]):
                overlaps.append(f"{left_name}/{right_name}")
    label_rects = _control_label_rects(panel)
    pair_gaps, distant_pairs = _control_label_pair_gaps(
        rects,
        label_rects,
        {
            "plan": "Fold:",
            "run": "Run:",
            "method": "Method:",
        },
    )
    missing_labels = [
        f"{name}_label"
        for name, label_text in {
            "plan": "Fold:",
            "run": "Run:",
            "method": "Method:",
        }.items()
        if label_text not in label_rects
    ]
    return {
        "ok": not hidden and not overlaps and not distant_pairs and not missing_labels,
        "hidden_or_empty": [*hidden, *missing_labels],
        "overlaps": overlaps,
        "distant_pairs": distant_pairs,
        "pair_gaps": pair_gaps,
        "rects": rects,
        "label_rects": label_rects,
    }


def _transform_control_evidence(panel: Any) -> dict[str, Any]:
    """Record tab-specific transform semantics and stable selector geometry."""
    layout = getattr(panel, "ctrl_layout", None)
    absolute = getattr(panel, "abs_check", None)
    normalize = getattr(panel, "normalize_check", None)
    tabs = getattr(panel, "tabs", None)
    if layout is None or absolute is None or normalize is None or tabs is None:
        return {"ok": False, "reason": "transform controls are incomplete"}

    def control_state(widget: Any) -> dict[str, Any]:
        index = layout.indexOf(widget)
        grid_position: list[int] = []
        if index >= 0:
            row, column, row_span, column_span = layout.getItemPosition(index)
            grid_position = [row, column, row_span, column_span]
        return {
            "visible": bool(widget.isVisibleTo(panel)),
            "enabled": bool(widget.isEnabled()),
            "checked": bool(widget.isChecked()),
            "grid_position": grid_position,
        }

    return {
        "ok": True,
        "tab": tabs.tabText(tabs.currentIndex()),
        "absolute": control_state(absolute),
        "normalize": control_state(normalize),
        "selector_geometry": {
            name: _widget_rect_relative_to(
                getattr(panel, f"{name}_combo"),
                panel.ctrl_bar,
            )
            for name in ("plan", "run", "method")
        },
        "control_bar_size": [panel.ctrl_bar.width(), panel.ctrl_bar.height()],
    }


def _widget_rect_relative_to(widget: Any, ancestor: Any) -> list[int]:
    top_left = widget.mapTo(ancestor, widget.rect().topLeft())
    return [
        int(top_left.x()),
        int(top_left.y()),
        int(widget.width()),
        int(widget.height()),
    ]


def _global_widget_rect(widget: Any) -> dict[str, int]:
    rect = widget.rect()
    top_left = widget.mapToGlobal(rect.topLeft())
    return {
        "x": int(top_left.x()),
        "y": int(top_left.y()),
        "width": int(rect.width()),
        "height": int(rect.height()),
    }


def _rects_intersect(left: dict[str, int], right: dict[str, int]) -> bool:
    return not (
        left["x"] + left["width"] <= right["x"]
        or right["x"] + right["width"] <= left["x"]
        or left["y"] + left["height"] <= right["y"]
        or right["y"] + right["height"] <= left["y"]
    )


def _control_label_rects(panel: Any) -> dict[str, dict[str, int]]:
    labels = {}
    for label in panel.findChildren(QLabel):
        text = label.text().strip()
        if text in {"Fold:", "Run:", "Method:"} and label.isVisible():
            labels[text] = _global_widget_rect(label)
    return labels


def _control_label_pair_gaps(
    rects: dict[str, dict[str, int]],
    label_rects: dict[str, dict[str, int]],
    label_by_control: dict[str, str],
) -> tuple[dict[str, dict[str, int]], list[str]]:
    pair_gaps: dict[str, dict[str, int]] = {}
    distant_pairs: list[str] = []
    for control_name, label_text in label_by_control.items():
        control_rect = rects.get(control_name)
        label_rect = label_rects.get(label_text)
        if not control_rect or not label_rect:
            continue
        horizontal_gap = control_rect["x"] - (label_rect["x"] + label_rect["width"])
        label_center_y = label_rect["y"] + label_rect["height"] // 2
        control_center_y = control_rect["y"] + control_rect["height"] // 2
        row_delta = abs(control_center_y - label_center_y)
        pair_gaps[control_name] = {
            "horizontal_gap": int(horizontal_gap),
            "row_delta": int(row_delta),
        }
        if horizontal_gap < -2 or horizontal_gap > 48 or row_delta > 12:
            distant_pairs.append(control_name)
    return pair_gaps, distant_pairs


def _blocked_message_evidence(widget: Any, expected_reason: str) -> dict[str, Any]:
    labels = [
        label
        for label in widget.findChildren(QLabel)
        if not label.isHidden() and expected_reason in label.text()
    ]
    if not labels:
        return {"ok": False, "reason": "expected label not visible"}
    label = labels[0]
    rect = label.rect()
    top_left = label.mapTo(widget, rect.topLeft())
    label_rect = {
        "x": int(top_left.x()),
        "y": int(top_left.y()),
        "width": int(rect.width()),
        "height": int(rect.height()),
    }
    size_hint = label.sizeHint()
    clipped_by_bounds = (
        label_rect["x"] < 0
        or label_rect["y"] < 0
        or label_rect["x"] + label_rect["width"] > widget.width()
        or label_rect["y"] + label_rect["height"] > widget.height()
    )
    clipped_by_hint = size_hint.height() > label.height() + 2
    return {
        "ok": not clipped_by_bounds and not clipped_by_hint,
        "reason": "",
        "label_rect": label_rect,
        "container_size": {
            "width": int(widget.width()),
            "height": int(widget.height()),
        },
        "size_hint": {
            "width": int(size_hint.width()),
            "height": int(size_hint.height()),
        },
        "clipped_by_bounds": clipped_by_bounds,
        "clipped_by_hint": clipped_by_hint,
    }


def validate_visualization_render_payload(
    payload: dict[str, Any],
) -> tuple[bool, str]:
    """Validate source -> tiny train -> real VisualizationPanel render evidence."""
    source_ok, source_reason = _validate_exact_source_capture(payload)
    if not source_ok:
        return False, source_reason
    if not payload.get("dataset_preparation", {}).get("ok"):
        return False, "Dataset preparation failed."
    if payload.get("uncaught_exceptions"):
        first = str(payload["uncaught_exceptions"][0]).splitlines()[-1]
        return False, f"Uncaught Qt/runtime exception during capture: {first}"

    shutdown = payload.get("shutdown") or {}
    if (
        shutdown.get("ok") is not True
        or shutdown.get("timed_out") is not False
        or shutdown.get("window_visible") is not False
        or not _shutdown_snapshot_is_clean(shutdown.get("snapshot"))
    ):
        return False, "MainWindow did not publish a clean terminal shutdown."

    training = payload.get("training") or {}
    if int(training.get("finished_run_count") or 0) < 1:
        return False, "No completed tiny training run was captured."
    if not training.get("metrics_available"):
        return False, "Evaluation metrics were not available after tiny training."
    # Training now finishes with metric-only evaluation. The walkthrough must
    # exercise the same explicit Compute Saliency action as the visible panel.
    saliency_compute = payload.get("saliency_compute") or {}
    if not saliency_compute.get("ok"):
        return False, "The visible Compute Saliency action did not complete."

    app_visualize = payload.get("application_visualize") or {}
    if not app_visualize.get("ok"):
        return False, "ApplicationService visualize command did not succeed."
    available_views = set(
        app_visualize.get("diagnostics", {}).get("available_views", []),
    )
    if "saliency map" not in available_views:
        return False, "ApplicationService did not report saliency map availability."

    control_layout = (payload.get("ui_state") or {}).get("control_layout") or {}
    if not control_layout:
        return False, "Visualization control layout evidence is missing."
    if not control_layout.get("ok"):
        overlaps = ", ".join(control_layout.get("overlaps") or [])
        hidden = ", ".join(control_layout.get("hidden_or_empty") or [])
        distant = ", ".join(control_layout.get("distant_pairs") or [])
        detail = overlaps or hidden or distant or "unknown layout issue"
        return False, f"Visualization controls are not cleanly laid out: {detail}."

    final_state = payload.get("final_state") or {}
    if final_state:
        dataset = _section(final_state, "dataset")
        final_training = _section(final_state, "training")
        evaluation = _section(final_state, "evaluation")
        visualization = _section(final_state, "visualization")
        if not dataset.get("available"):
            return False, "Final state does not have a generated dataset."
        if final_training.get("is_running"):
            return False, "Training was still running at render capture."
        if int(final_training.get("finished_run_count") or 0) < 1:
            return False, "Final state does not have a completed training run."
        if not evaluation.get("metrics_available"):
            return False, "Final state does not have evaluation metrics."
        if not visualization.get("saliency_available"):
            return False, "Final state does not have saliency available."
        if not visualization.get("montage_available"):
            return False, "Final state does not have montage for topographic render."

    renders = {item.get("tab"): item for item in payload.get("renders", [])}
    transform_ok, transform_reason = _validate_transform_control_evidence(renders)
    if not transform_ok:
        return False, transform_reason
    screenshot_digests: dict[str, str] = {}
    for spec in RENDER_TAB_SPECS:
        tab = spec["tab"]
        render = renders.get(tab)
        if not render:
            return False, f"Missing render evidence for {tab}."
        if not render.get("ok"):
            return False, render.get("failure_reason") or f"{tab} render failed."
        if render.get("error_visible"):
            return False, f"{tab} showed an error instead of a render."
        if not render.get("canvas_visible"):
            return False, f"{tab} canvas was not visible."
        if not _provenance_context_matches(
            str(render.get("explanation_context") or ""),
            spec["expected_context"],
        ):
            return False, f"{tab} scientific context is stale or incorrect."
        if int(render.get("image_count") or 0) < 1:
            return False, f"{tab} did not contain a rendered image artist."
        canvas_geometry = render.get("canvas_geometry") or {}
        if not canvas_geometry.get("ok"):
            detail = canvas_geometry.get("reason") or "canvas geometry is invalid"
            return False, f"{tab} {detail}."
        artist_layout = render.get("artist_layout") or {}
        if not artist_layout.get("ok"):
            detail = artist_layout.get("reason") or "plot labels are clipped"
            return False, f"{tab} {detail}."
        if (
            tab == "Topographic Map"
            and float(artist_layout.get("right_margin_pixels") or 0.0)
            < TOPOGRAPHIC_COLORBAR_MIN_MARGIN_PX
        ):
            return (
                False,
                "Topographic Map colorbar does not leave a readable right margin.",
            )
        screenshot_region = render.get("screenshot_region") or {}
        if not screenshot_region.get("ok"):
            detail = screenshot_region.get("reason") or "plot region is invalid"
            return False, f"{tab} {detail}."
        screenshot_ok, screenshot_reason = _validate_screenshot(
            render.get("screenshot"),
            f"{tab} screenshot",
        )
        if not screenshot_ok:
            return False, screenshot_reason
        digest_ok, digest_reason = _validate_screenshot_digest(
            render.get("screenshot"),
            render.get("screenshot_sha256"),
            f"{tab} screenshot",
        )
        if not digest_ok:
            return False, digest_reason
        digest = str(render.get("screenshot_sha256") or "")
        duplicate_tab = screenshot_digests.get(digest)
        if duplicate_tab is not None:
            return (
                False,
                f"{duplicate_tab} and {tab} have an identical screenshot; "
                "the tab capture did not publish distinct render evidence.",
            )
        screenshot_digests[digest] = tab

    runtime = payload.get("three_d_runtime") or {}
    expected_outcome = str(runtime.get("expected_outcome") or "")
    if expected_outcome == "blocked":
        if payload.get("interactive_renders"):
            return False, "Interactive 3D evidence was recorded in a blocked runtime."
        ok, reason = _validate_blocked_3d_evidence(payload)
        if not ok:
            return False, reason
    elif expected_outcome == "rendered":
        if payload.get("blocked_renders"):
            return False, "3D was treated as blocked in an interactive runtime."
        ok, reason = _validate_interactive_3d_evidence(payload)
        if not ok:
            return False, reason
    else:
        return False, "3D runtime contract is missing or invalid."
    return True, ""


def _validate_exact_source_capture(payload: dict[str, Any]) -> tuple[bool, str]:
    start = payload.get("source_identity_at_start")
    completion = payload.get("source_identity_at_completion")
    recorded = payload.get("source_identity")
    if not isinstance(start, dict) or not isinstance(completion, dict):
        return False, "Visualization source identity is missing."
    if not isinstance(recorded, dict) or recorded != completion:
        return False, "Visualization source identity does not match completion."
    if start.get("source_digest") != completion.get("source_digest"):
        return False, "Visualization source changed during capture."
    start_ok, start_reason = validate_source_identity(
        start,
        expected_repo_root=ROOT,
        refresh=False,
        current_identity=completion,
        artifact_name="Visualization walkthrough",
    )
    if not start_ok:
        return False, start_reason
    completion_ok, completion_reason = validate_source_identity(
        completion,
        expected_repo_root=ROOT,
        refresh=False,
        current_identity=completion,
        artifact_name="Visualization walkthrough completion",
    )
    if not completion_ok:
        return False, completion_reason
    source_capture = payload.get("source_capture")
    if not isinstance(source_capture, dict):
        return False, "Visualization source capture summary is missing."
    expected_summary = {
        "branch": completion.get("branch"),
        "commit_sha": completion.get("commit_sha"),
        "head_tree_sha": completion.get("head_tree_sha"),
        "dirty": bool(completion.get("dirty")),
        "dirty_digest": completion.get("dirty_digest"),
        "source_content_digest": completion.get("source_content_digest"),
        "source_digest_at_start": start.get("source_digest"),
        "source_digest_at_completion": completion.get("source_digest"),
    }
    if source_capture != expected_summary:
        return False, "Visualization source capture summary is inconsistent."
    return True, ""


def _validate_transform_control_evidence(
    renders: dict[object, dict[str, Any]],
) -> tuple[bool, str]:
    states: dict[str, dict[str, Any]] = {}
    for tab in ("Saliency Map", "Spectrogram", "Topographic Map"):
        render = renders.get(tab)
        state = render.get("transform_controls") if isinstance(render, dict) else None
        if not isinstance(state, dict) or not state.get("ok"):
            return False, f"{tab} transform control evidence is missing."
        if state.get("tab") != tab:
            return False, f"{tab} transform control evidence names the wrong tab."
        states[tab] = state

    spectrogram = states["Spectrogram"]
    if bool((spectrogram.get("absolute") or {}).get("visible")):
        return False, "Spectrogram must keep Absolute hidden."
    if not bool((spectrogram.get("normalize") or {}).get("visible")):
        return False, "Spectrogram must keep Normalize visible."
    if bool((spectrogram.get("absolute") or {}).get("enabled")):
        return False, "Spectrogram must keep Absolute unavailable."

    for tab in ("Saliency Map", "Topographic Map"):
        if not bool((states[tab].get("absolute") or {}).get("visible")):
            return False, f"{tab} Absolute was not restored after Spectrogram."
        if not bool((states[tab].get("normalize") or {}).get("visible")):
            return False, f"{tab} did not keep Normalize visible."

    baseline = states["Saliency Map"]
    baseline_selectors = baseline.get("selector_geometry")
    baseline_absolute_slot = (baseline.get("absolute") or {}).get("grid_position")
    baseline_normalize_slot = (baseline.get("normalize") or {}).get("grid_position")
    for tab, state in states.items():
        if state.get("selector_geometry") != baseline_selectors:
            return False, f"{tab} selector geometry jumped across tab changes."
        if (state.get("normalize") or {}).get(
            "grid_position"
        ) != baseline_normalize_slot:
            return False, f"{tab} changed the Normalize control slot."
        absolute_slot = (state.get("absolute") or {}).get("grid_position")
        if tab == "Spectrogram":
            if absolute_slot:
                return False, "Spectrogram retained an empty Absolute control slot."
            continue
        if absolute_slot != baseline_absolute_slot:
            return False, f"{tab} changed the Absolute control slot."
        if not baseline_normalize_slot or not absolute_slot:
            return False, f"{tab} transform control positions are incomplete."
        if tuple(baseline_normalize_slot[:2]) >= tuple(absolute_slot[:2]):
            return False, f"{tab} must place Normalize before Absolute."
    return True, ""


def _validate_blocked_3d_evidence(payload: dict[str, Any]) -> tuple[bool, str]:
    blocked = {item.get("tab"): item for item in payload.get("blocked_renders", [])}
    for spec in THREE_D_TAB_SPECS:
        tab = spec["tab"]
        render = blocked.get(tab)
        if not render:
            return False, f"Missing blocked evidence for {tab}."
        if not render.get("ok"):
            return False, render.get("failure_reason") or f"{tab} blocked check failed."
        if render.get("terminal_settled") is not True:
            return False, f"{tab} did not reach a terminal capture state."
        if render.get("outcome") not in {None, "blocked"}:
            return False, f"{tab} did not settle as blocked."
        if render.get("plotter_created"):
            return False, f"{tab} created a PyVista plotter in a blocked runtime."
        if spec["expected_reason"] not in str(render.get("blocked_reason", "")):
            return False, f"{tab} did not show a user-facing blocked reason."
        if not (render.get("message_evidence") or {}).get("ok"):
            return False, f"{tab} blocked reason appears clipped or hidden."
        screenshot_region = render.get("screenshot_region") or {}
        if not screenshot_region.get("ok"):
            detail = (
                screenshot_region.get("reason")
                or "blocked message region was not painted"
            )
            return False, f"{tab} {detail}."
        screenshot_ok, screenshot_reason = _validate_screenshot(
            render.get("screenshot"),
            f"{tab} blocked screenshot",
        )
        if not screenshot_ok:
            return False, screenshot_reason
        digest_ok, digest_reason = _validate_screenshot_digest(
            render.get("screenshot"),
            render.get("screenshot_sha256"),
            f"{tab} blocked screenshot",
        )
        if not digest_ok:
            return False, digest_reason
    return True, ""


def _validate_interactive_3d_evidence(
    payload: dict[str, Any],
) -> tuple[bool, str]:
    rendered = {
        item.get("tab"): item for item in payload.get("interactive_renders", [])
    }
    for spec in THREE_D_TAB_SPECS:
        tab = spec["tab"]
        render = rendered.get(tab)
        if not render:
            return False, f"Missing interactive render evidence for {tab}."
        if not render.get("ok"):
            return False, render.get("failure_reason") or f"{tab} render failed."
        if render.get("terminal_settled") is not True:
            return False, f"{tab} did not reach a terminal render state."
        if render.get("outcome") != "rendered":
            return False, f"{tab} did not settle as an interactive render."
        if not render.get("plotter_created") or not render.get("plotter_visible"):
            return False, f"{tab} PyVista plotter was not visible."
        if not (render.get("plotter_geometry") or {}).get("ok"):
            return False, f"{tab} plotter geometry was hidden, clipped, or too small."
        evidence = render.get("render_evidence") or {}
        if not evidence.get("ok"):
            detail = evidence.get("reason") or "render evidence is incomplete"
            return False, f"{tab} {detail}."
        if not evidence.get("render_window_rendered"):
            return False, f"{tab} VTK render window did not complete a render."
        if int(evidence.get("actor_count") or 0) < 1:
            return False, f"{tab} VTK renderer did not contain visible actors."
        if float(evidence.get("last_render_seconds") or 0.0) <= 0.0:
            return False, f"{tab} did not record VTK render timing evidence."
        runtime = payload.get("three_d_runtime") or {}
        expected_capture_method = str(runtime.get("capture_method") or "")
        if render.get("capture_method") != expected_capture_method:
            return False, f"{tab} did not capture the expected native framebuffer."
        screenshot_region = render.get("screenshot_region") or {}
        if not screenshot_region.get("ok"):
            detail = screenshot_region.get("reason") or "framebuffer was not painted"
            return False, f"{tab} {detail}."
        if float(screenshot_region.get("sentinel_fraction") or 0.0) > 0.001:
            return False, f"{tab} contains unpainted capture pixels."
        screenshot_ok, screenshot_reason = _validate_screenshot(
            render.get("screenshot"),
            f"{tab} interactive screenshot",
        )
        if not screenshot_ok:
            return False, screenshot_reason
        digest_ok, digest_reason = _validate_screenshot_digest(
            render.get("screenshot"),
            render.get("screenshot_sha256"),
            f"{tab} interactive screenshot",
        )
        if not digest_ok:
            return False, digest_reason
    return True, ""


def _validate_screenshot(path: Any, label: str) -> tuple[bool, str]:
    screenshot = Path(str(path or "").strip())
    if not str(screenshot):
        return False, f"{label} path was not recorded."
    if not screenshot.is_file():
        return False, f"{label} file was not found: {screenshot}."
    if is_nearly_black(screenshot):
        return False, f"{label} was nearly all black: {screenshot}."
    shell_ok, missing_regions = _main_window_shell_repaint_evidence(screenshot)
    if not shell_ok:
        return (
            False,
            f"{label} did not repaint the complete main window shell "
            f"({', '.join(missing_regions)}): {screenshot}.",
        )
    return True, ""


def _validate_screenshot_digest(
    path: Any,
    expected_digest: Any,
    label: str,
) -> tuple[bool, str]:
    screenshot = Path(str(path or "").strip())
    digest = str(expected_digest or "").strip().lower()
    if len(digest) != 64:
        return False, f"{label} did not record a complete SHA-256 digest."
    if not screenshot.is_file():
        return False, f"{label} file was not found: {screenshot}."
    actual = hashlib.sha256(screenshot.read_bytes()).hexdigest()
    if actual != digest:
        return False, f"{label} SHA-256 did not match the captured artifact."
    return True, ""


def _capture_fully_rendered_window(
    window: Any,
    output_path: Path,
    *,
    capture_method: str = "qt_widget_render",
    validate_complete: bool = True,
) -> int:
    """Capture the complete widget tree, including native OpenGL children."""
    window.ensurePolished()
    window.update()
    window.repaint()
    QApplication.sendPostedEvents()
    QApplication.processEvents()

    if capture_method in {"screen_grab", "xcb_screen_grab"}:
        screen = window.screen() or QApplication.primaryScreen()
        if screen is None:
            print(
                "No Qt screen is available for native-window capture.", file=sys.stderr
            )
            return 3
        window.raise_()
        window.activateWindow()
        QApplication.processEvents()
        pixmap = screen.grabWindow(window.winId())
    elif capture_method == "qt_widget_grab":
        pixmap = window.grab()
    else:
        ratio = max(float(window.devicePixelRatioF()), 1.0)
        pixel_width = max(1, round(window.width() * ratio))
        pixel_height = max(1, round(window.height() * ratio))
        pixmap = QPixmap(pixel_width, pixel_height)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(_UNPAINTED_CAPTURE_SENTINEL)
        window.render(pixmap)
    if pixmap.isNull():
        print("Failed to render the main window pixmap.", file=sys.stderr)
        return 3
    if not pixmap.save(str(output_path)):
        print("Failed to save the rendered main window pixmap.", file=sys.stderr)
        return 4
    try:
        _normalize_png_artifact(output_path)
    except Exception as exc:
        print(f"Failed to normalize screenshot PNG: {exc}", file=sys.stderr)
        return 5
    if validate_complete:
        screenshot_ok, reason = _validate_screenshot(output_path, output_path.name)
        if not screenshot_ok:
            print(reason, file=sys.stderr)
            return 2
    print(f"Saved screenshot to {output_path}")
    return 0


def _capture_matplotlib_window(
    window: Any,
    canvas: Any,
    output_path: Path,
    *,
    canvas_geometry: dict[str, Any],
    validate_complete: bool = True,
) -> int:
    """Compose a real Matplotlib framebuffer into a complete Qt shell capture.

    WSLg can return an all-black native-window framebuffer, while QTAgg child
    painting can escape its widget geometry during recursive QWidget capture.
    Replacing the canvas with a same-size placeholder prevents that child paint
    from obscuring the surrounding application shell.
    """
    if canvas is None or canvas_geometry.get("ok") is False:
        print("Matplotlib canvas geometry is unavailable.", file=sys.stderr)
        return 3
    draw = getattr(canvas, "draw", None)
    buffer_rgba = getattr(canvas, "buffer_rgba", None)
    if not callable(draw) or not callable(buffer_rgba):
        print("Matplotlib canvas cannot provide its framebuffer.", file=sys.stderr)
        return 3

    try:
        import numpy as np

        draw()
        framebuffer = np.asarray(buffer_rgba()).copy()
    except Exception as matplotlib_error:
        try:
            framebuffer = _capture_qt_canvas_framebuffer(canvas)
        except Exception as qt_error:
            print(
                "Failed to read the Matplotlib framebuffer "
                f"({matplotlib_error}); Qt canvas fallback also failed: {qt_error}",
                file=sys.stderr,
            )
            return 3

    parent = canvas.parentWidget()
    layout = parent.layout() if parent is not None else None
    scroll_area = parent.parentWidget() if parent is not None else None
    scroll_owned = (
        isinstance(scroll_area, QScrollArea) and scroll_area.widget() is canvas
    )
    layout_owned = layout is not None and layout.indexOf(canvas) >= 0
    if parent is None or not (layout_owned or scroll_owned):
        print("Matplotlib canvas is not owned by a visible Qt layout.", file=sys.stderr)
        return 3

    capture_geometry = canvas_geometry
    if scroll_owned:
        viewport = scroll_area.viewport()
        viewport_geometry = _widget_geometry(viewport, window)
        if viewport_geometry.get("ok") is False:
            print(
                "Scrollable Matplotlib viewport geometry is unavailable.",
                file=sys.stderr,
            )
            return 3
        array = np.asarray(framebuffer)
        canvas_width = max(int(canvas.width()), 1)
        canvas_height = max(int(canvas.height()), 1)
        x_offset = int(scroll_area.horizontalScrollBar().value())
        y_offset = int(scroll_area.verticalScrollBar().value())
        visible_width = min(int(viewport.width()), canvas_width - x_offset)
        visible_height = min(int(viewport.height()), canvas_height - y_offset)
        if visible_width <= 0 or visible_height <= 0:
            print(
                "Scrollable Matplotlib canvas has no visible region.", file=sys.stderr
            )
            return 3
        x_scale = array.shape[1] / canvas_width
        y_scale = array.shape[0] / canvas_height
        x0 = max(0, round(x_offset * x_scale))
        y0 = max(0, round(y_offset * y_scale))
        x1 = min(array.shape[1], round((x_offset + visible_width) * x_scale))
        y1 = min(array.shape[0], round((y_offset + visible_height) * y_scale))
        framebuffer = array[y0:y1, x0:x1].copy()
        capture_geometry = viewport_geometry

    placeholder = QWidget(scroll_area if scroll_owned else parent)
    placeholder.setObjectName("VisualizationCaptureCanvasPlaceholder")
    placeholder.setFixedSize(canvas.size())
    placeholder.setStyleSheet("background: transparent; border: none;")
    if scroll_owned:
        detached_canvas = scroll_area.takeWidget()
        if detached_canvas is not canvas:
            placeholder.deleteLater()
            print(
                "Failed to isolate the scrollable Matplotlib canvas.", file=sys.stderr
            )
            return 3
        scroll_area.setWidget(placeholder)
    else:
        replaced_item = layout.replaceWidget(canvas, placeholder)
        if replaced_item is None:
            placeholder.deleteLater()
            print(
                "Failed to isolate the Matplotlib canvas for capture.", file=sys.stderr
            )
            return 3

    capture_code = 3
    try:
        canvas.hide()
        placeholder.show()
        if layout is not None:
            layout.activate()
        QApplication.sendPostedEvents()
        QApplication.processEvents()
        capture_code = _capture_fully_rendered_window(
            window,
            output_path,
            capture_method="qt_widget_grab",
            validate_complete=False,
        )
    finally:
        if scroll_owned:
            scroll_area.takeWidget()
            scroll_area.setWidget(canvas)
        else:
            layout.replaceWidget(placeholder, canvas)
        placeholder.hide()
        canvas.show()
        if layout is not None:
            layout.activate()
        placeholder.deleteLater()
        QApplication.sendPostedEvents()
        QApplication.processEvents()

    if capture_code != 0:
        return capture_code
    try:
        _compose_native_framebuffer(
            output_path,
            framebuffer,
            region_geometry=capture_geometry,
            window_size={"width": int(window.width()), "height": int(window.height())},
        )
        _normalize_png_artifact(output_path)
    except Exception as exc:
        print(f"Failed to compose the Matplotlib framebuffer: {exc}", file=sys.stderr)
        return 3
    if validate_complete:
        screenshot_ok, reason = _validate_screenshot(output_path, output_path.name)
        if not screenshot_ok:
            print(reason, file=sys.stderr)
            return 2
    return 0


def _capture_qt_canvas_framebuffer(canvas: QWidget) -> Any:
    """Read only the visible canvas when QTAgg has lost its Agg renderer.

    A completed Qt canvas can remain correctly painted after Matplotlib has
    released the renderer used by ``buffer_rgba``. Capturing the child widget
    itself preserves that visible product evidence without accepting an
    all-black whole-window framebuffer from WSLg.
    """
    import numpy as np
    from PIL import Image

    pixmap = canvas.grab()
    if pixmap.isNull():
        raise RuntimeError("the Qt canvas pixmap is empty")
    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("the Qt canvas image buffer could not be opened")
    try:
        if not pixmap.save(buffer, "PNG"):
            raise RuntimeError("the Qt canvas pixmap could not be encoded")
        payload = bytes(buffer.data())
    finally:
        buffer.close()
    with Image.open(BytesIO(payload)) as source:
        source.load()
        return np.asarray(source.convert("RGBA")).copy()


def _capture_interactive_3d_window(
    window: Any,
    plotter: Any,
    output_path: Path,
    *,
    plotter_geometry: dict[str, Any],
) -> int:
    """Compose the VTK framebuffer into a complete Qt window screenshot."""
    capture_code = _capture_fully_rendered_window(
        window,
        output_path,
        capture_method="qt_widget_grab",
        validate_complete=False,
    )
    if capture_code != 0:
        return capture_code
    screenshot = getattr(plotter, "screenshot", None)
    if not callable(screenshot):
        print("The 3D plotter cannot capture its framebuffer.", file=sys.stderr)
        return 3
    try:
        framebuffer = screenshot(return_img=True)
        _compose_native_framebuffer(
            output_path,
            framebuffer,
            region_geometry=plotter_geometry,
            window_size={"width": int(window.width()), "height": int(window.height())},
        )
        _normalize_png_artifact(output_path)
    except Exception as exc:
        print(f"Failed to capture the VTK framebuffer: {exc}", file=sys.stderr)
        return 3
    screenshot_ok, reason = _validate_screenshot(output_path, output_path.name)
    if not screenshot_ok:
        print(reason, file=sys.stderr)
        return 2
    return 0


def _compose_native_framebuffer(
    output_path: Path,
    framebuffer: Any,
    *,
    region_geometry: dict[str, Any],
    window_size: dict[str, int],
) -> None:
    """Place one native RGB(A) framebuffer at its logical Qt geometry."""
    import numpy as np
    from PIL import Image

    array = np.asarray(framebuffer)
    if array.ndim != 3 or array.shape[2] not in {3, 4} or array.size == 0:
        raise ValueError("VTK framebuffer does not contain an RGB image.")
    if array.dtype != np.uint8:
        array = np.clip(array, 0, 255).astype(np.uint8)

    with Image.open(output_path) as source:
        window_image = source.convert("RGB")
    logical_width = int(window_size.get("width") or 0)
    logical_height = int(window_size.get("height") or 0)
    if logical_width <= 0 or logical_height <= 0:
        raise ValueError("Qt window geometry is invalid.")
    scale_x = window_image.width / logical_width
    scale_y = window_image.height / logical_height
    left = round(int(region_geometry["x"]) * scale_x)
    top = round(int(region_geometry["y"]) * scale_y)
    width = round(int(region_geometry["width"]) * scale_x)
    height = round(int(region_geometry["height"]) * scale_y)
    if left < 0 or top < 0 or width <= 0 or height <= 0:
        raise ValueError("3D plotter geometry is invalid.")
    if left + width > window_image.width or top + height > window_image.height:
        raise ValueError("3D plotter geometry extends outside the Qt window.")

    vtk_image = Image.fromarray(array).convert("RGB")
    vtk_image = vtk_image.resize((width, height), Image.Resampling.LANCZOS)
    window_image.paste(vtk_image, (left, top))
    window_image.save(output_path, format="PNG", optimize=False, compress_level=6)


def _normalize_png_artifact(path: Path) -> dict[str, Any]:
    """Re-encode Qt PNG output as a portable opaque RGB artifact.

    A full RGB re-encode removes encoder-specific ambiguity. The capture then
    receives a content-addressed filename so artifact viewers cannot serve an
    older frame from a path-only cache after a rerun.
    """
    from PIL import Image

    temporary_path = path.with_name(f".{path.stem}.normalized.png")
    with Image.open(path) as source:
        source.load()
        normalized = source.convert("RGB")
        width, height = normalized.size
        normalized.save(
            temporary_path,
            format="PNG",
            optimize=False,
            compress_level=6,
        )
    temporary_path.replace(path)
    return {
        "format": "PNG",
        "mode": "RGB",
        "width": int(width),
        "height": int(height),
    }


def _content_addressed_screenshot_path(path: Path) -> tuple[Path, str]:
    """Rename a screenshot with a digest so changed evidence gets a new URL."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    destination = path.with_name(f"{path.stem}-{digest[:12]}{path.suffix}")
    path.replace(destination)
    return destination, digest


def _remove_previous_visualization_screenshots(output_dir: Path) -> None:
    """Keep the generated artifact directory limited to the current capture."""
    for path in output_dir.glob("visualization-render-*.png"):
        path.unlink()


def _screenshot_region_evidence(
    path: Path,
    logical_rect: dict[str, Any],
    *,
    window_size: dict[str, int],
    require_chromatic_content: bool,
    allow_sparse_foreground: bool = False,
) -> dict[str, Any]:
    """Measure whether a widget's screenshot region contains visible content."""
    from collections import Counter

    from PIL import Image

    if not path.is_file():
        return {
            "ok": False,
            "reason": "screenshot file is missing",
            "unique_color_count": 0,
            "dominant_color_fraction": 1.0,
            "chromatic_fraction": 0.0,
            "near_black_fraction": 1.0,
            "sentinel_fraction": 0.0,
        }
    logical_width = int(window_size.get("width") or 0)
    logical_height = int(window_size.get("height") or 0)
    if logical_width <= 0 or logical_height <= 0 or logical_rect.get("ok") is False:
        return {
            "ok": False,
            "reason": logical_rect.get("reason") or "region geometry is invalid",
            "unique_color_count": 0,
            "dominant_color_fraction": 1.0,
            "chromatic_fraction": 0.0,
            "near_black_fraction": 1.0,
            "sentinel_fraction": 0.0,
        }

    with Image.open(path) as source:
        image = source.convert("RGB")
        scale_x = image.width / logical_width
        scale_y = image.height / logical_height
        left = max(0, round(int(logical_rect["x"]) * scale_x))
        top = max(0, round(int(logical_rect["y"]) * scale_y))
        right = min(
            image.width,
            round((int(logical_rect["x"]) + int(logical_rect["width"])) * scale_x),
        )
        bottom = min(
            image.height,
            round((int(logical_rect["y"]) + int(logical_rect["height"])) * scale_y),
        )
        if right <= left or bottom <= top:
            return {
                "ok": False,
                "reason": "region falls outside the captured window",
                "unique_color_count": 0,
                "dominant_color_fraction": 1.0,
                "chromatic_fraction": 0.0,
                "near_black_fraction": 1.0,
                "sentinel_fraction": 0.0,
            }
        crop = image.crop((left, top, right, bottom))
        pixels = cast(
            list[tuple[int, int, int]],
            list(crop.get_flattened_data()),
        )

    colors = Counter(pixels)
    pixel_count = len(pixels)
    unique_color_count = len(colors)
    dominant_color_fraction = max(colors.values(), default=pixel_count) / pixel_count
    chromatic_fraction = (
        sum(
            1
            for red, green, blue in pixels
            if max(red, green, blue) - min(red, green, blue) >= 12
        )
        / pixel_count
    )
    near_black_fraction = (
        sum(1 for red, green, blue in pixels if max(red, green, blue) <= 8)
        / pixel_count
    )
    sentinel_fraction = (
        sum(
            1
            for red, green, blue in pixels
            if red >= 250 and green <= 5 and blue >= 250
        )
        / pixel_count
    )
    minimum_unique_colors = 2 if allow_sparse_foreground else 16
    visually_empty = (
        unique_color_count < minimum_unique_colors
        or (dominant_color_fraction >= 0.98 and not allow_sparse_foreground)
        or near_black_fraction >= 0.85
    )
    missing_chromatic_content = require_chromatic_content and chromatic_fraction < 0.005
    unpainted_capture = sentinel_fraction > 0.001
    ok = not visually_empty and not missing_chromatic_content and not unpainted_capture
    if unpainted_capture:
        reason = "plot region contains unpainted capture pixels"
    elif visually_empty:
        reason = "plot region is visually empty"
    elif missing_chromatic_content:
        reason = "plot region has no visible foreground content"
    else:
        reason = ""
    return {
        "ok": ok,
        "reason": reason,
        "pixel_rect": {
            "x": left,
            "y": top,
            "width": right - left,
            "height": bottom - top,
        },
        "pixel_count": pixel_count,
        "unique_color_count": unique_color_count,
        "dominant_color_fraction": round(dominant_color_fraction, 6),
        "chromatic_fraction": round(chromatic_fraction, 6),
        "near_black_fraction": round(near_black_fraction, 6),
        "sentinel_fraction": round(sentinel_fraction, 6),
    }


def _main_window_shell_repaint_evidence(path: Path) -> tuple[bool, list[str]]:
    """Detect offscreen captures where only the newly selected tab repainted."""
    from PIL import Image

    with Image.open(path) as source:
        image = source.convert("RGB")
        width, height = image.size
        if width <= 0 or height <= 0:
            return False, ["empty image"]

        top_height = max(1, min(height, round(height * 0.08)))
        content_top = min(top_height, height - 1)
        regions = {
            "top navigation": (0, 0, width, top_height),
            "right sidebar": (
                min(width - 1, round(width * 0.68)),
                content_top,
                width,
                height,
            ),
        }
        failed = []
        for name, box in regions.items():
            metrics = _shell_region_metrics(image.crop(box))
            if (
                metrics["near_black_fraction"] >= 0.75
                or metrics["entropy_bits"] < 0.03
                or metrics["contrast_fraction"] < 0.002
                or metrics["luminance_range"] < 12.0
            ):
                failed.append(name)
        if _sentinel_fraction(image) > 0.001:
            failed.append("unpainted capture pixels")
        return not failed, failed


def _shell_region_metrics(image: Any) -> dict[str, float]:
    """Measure whether a dark-theme shell region contains painted controls/text."""
    from collections import Counter

    pixels = list(image.get_flattened_data())
    if not pixels:
        return {
            "near_black_fraction": 1.0,
            "entropy_bits": 0.0,
            "contrast_fraction": 0.0,
            "luminance_range": 0.0,
        }
    colors = Counter(pixels)
    pixel_count = len(pixels)
    dominant_color, _ = colors.most_common(1)[0]
    entropy_bits = -sum(
        (count / pixel_count) * math.log2(count / pixel_count)
        for count in colors.values()
    )
    contrast_fraction = (
        sum(
            1
            for pixel in pixels
            if max(
                abs(channel - base)
                for channel, base in zip(pixel, dominant_color, strict=True)
            )
            >= 12
        )
        / pixel_count
    )
    luminances = [
        0.2126 * red + 0.7152 * green + 0.0722 * blue for red, green, blue in pixels
    ]
    return {
        "near_black_fraction": _near_black_fraction(image),
        "entropy_bits": entropy_bits,
        "contrast_fraction": contrast_fraction,
        "luminance_range": max(luminances) - min(luminances),
    }


def _near_black_fraction(image: Any) -> float:
    pixels = list(image.get_flattened_data())
    if not pixels:
        return 1.0
    count = sum(1 for red, green, blue in pixels if max(red, green, blue) <= 8)
    return count / len(pixels)


def _sentinel_fraction(image: Any) -> float:
    pixels = list(image.get_flattened_data())
    if not pixels:
        return 1.0
    count = sum(
        1 for red, green, blue in pixels if red >= 250 and green <= 5 and blue >= 250
    )
    return count / len(pixels)


def _artifact_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _set_deterministic_capture_seed() -> None:
    """Keep tracked visualization screenshots stable across capture reruns."""
    random.seed(DETERMINISTIC_CAPTURE_SEED)
    try:
        import numpy as np

        np.random.seed(DETERMINISTIC_CAPTURE_SEED)
    except Exception:
        LOGGER.debug("NumPy capture seeding is unavailable", exc_info=True)
    try:
        import torch

        torch.manual_seed(DETERMINISTIC_CAPTURE_SEED)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(DETERMINISTIC_CAPTURE_SEED)
    except Exception:
        LOGGER.debug("PyTorch capture seeding is unavailable", exc_info=True)


def stable_artifact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove runtime-only values from the persisted visualization artifact."""
    stable = copy.deepcopy(payload)
    stable["elapsed_seconds"] = _RUNTIME_DEPENDENT
    _mask_runtime_values(stable)
    return stable


def _mask_runtime_values(value: Any) -> None:
    if isinstance(value, dict):
        for key in list(value):
            if key in {
                "available_ram_bytes",
                "available_vram_bytes",
                "close_attempt_id",
            }:
                value[key] = _RUNTIME_DEPENDENT
            elif key == "metrics" and isinstance(value[key], dict):
                value[key] = {"status": "available"}
            else:
                _mask_runtime_values(value[key])
    elif isinstance(value, list):
        for item in value:
            _mask_runtime_values(item)


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a compact visualization render summary."""
    metadata = payload.get("artifact_metadata") or {}
    lines = [
        "# Visualization Render Walkthrough",
        "",
        f"- artifact status: `{metadata.get('status', 'current visualization evidence')}`",
        f"- generator: `{metadata.get('generator', 'scripts/dev/capture_visualization_render_walkthrough.py')}`",
        f"- environment: {metadata.get('environment', '')}",
        f"- supports: {metadata.get('supports', '')}",
        f"- does_not_support: {metadata.get('does_not_support', '')}",
        f"- next_human_or_runtime_gate: {metadata.get('next_human_or_runtime_gate', '')}",
        f"- Qt platform: `{(payload.get('three_d_runtime') or {}).get('qt_platform', '')}`",
        f"- expected 3D outcome: `{(payload.get('three_d_runtime') or {}).get('expected_outcome', '')}`",
        "",
        f"- status: `{payload['status']}`",
        f"- failure reason: {payload.get('failure_reason') or 'none'}",
        f"- source path: `{payload.get('source_path', '')}`",
        f"- training output dir: `{payload.get('training_output_dir', '')}`",
        f"- dataset preparation ok: `{payload['dataset_preparation']['ok']}`",
        f"- finished runs: `{payload.get('training', {}).get('finished_run_count')}`",
        f"- metrics available: `{payload.get('training', {}).get('metrics_available')}`",
        f"- Compute Saliency action: `{(payload.get('saliency_compute') or {}).get('action_status', '')}`",
        f"- Compute Saliency terminal: `{(payload.get('saliency_compute') or {}).get('operation_phase', '')}`",
        f"- saliency available: `{payload.get('training', {}).get('saliency_available')}`",
        f"- ready screenshot: `{payload.get('screenshots', {}).get('ready', '')}`",
        f"- elapsed seconds: `{payload['elapsed_seconds']}`",
        f"- uncaught exceptions: `{len(payload.get('uncaught_exceptions') or [])}`",
        f"- clean shutdown: `{bool((payload.get('shutdown') or {}).get('ok'))}`",
        "",
        "## Rendered Tabs",
        "",
    ]
    for render in payload.get("renders", []):
        lines.extend(
            [
                f"### {render.get('tab', '')}",
                "",
                f"- status: `{'ok' if render.get('ok') else 'failed'}`",
                f"- screenshot: `{render.get('screenshot', '')}`",
                f"- screenshot SHA-256: `{render.get('screenshot_sha256', '')}`",
                f"- axes count: `{render.get('axes_count')}`",
                f"- image count: `{render.get('image_count')}`",
                f"- scientific context: {render.get('explanation_context', '')}",
                f"- error visible: `{render.get('error_visible')}`",
                f"- canvas visible: `{render.get('canvas_visible')}`",
                f"- artist layout: `{'inside canvas' if (render.get('artist_layout') or {}).get('ok') else 'invalid'}`",
                f"- canvas color count: `{(render.get('screenshot_region') or {}).get('unique_color_count')}`",
                f"- canvas chromatic fraction: `{(render.get('screenshot_region') or {}).get('chromatic_fraction')}`",
                "",
            ],
        )

    if payload.get("blocked_renders"):
        lines.extend(["## Blocked Tabs", ""])
        for render in payload.get("blocked_renders", []):
            lines.extend(
                [
                    f"### {render.get('tab', '')}",
                    "",
                    f"- status: `{'ok' if render.get('ok') else 'failed'}`",
                    f"- screenshot: `{render.get('screenshot', '')}`",
                    f"- screenshot SHA-256: `{render.get('screenshot_sha256', '')}`",
                    f"- plotter created: `{render.get('plotter_created')}`",
                    f"- terminal outcome: `{render.get('outcome')}`",
                    f"- blocked reason: {render.get('blocked_reason', '')}",
                    f"- message chromatic fraction: `{(render.get('screenshot_region') or {}).get('chromatic_fraction')}`",
                    "",
                ],
            )

    if payload.get("interactive_renders"):
        lines.extend(["## Interactive 3D Renders", ""])
        for render in payload.get("interactive_renders", []):
            evidence = render.get("render_evidence") or {}
            region = render.get("screenshot_region") or {}
            lines.extend(
                [
                    f"### {render.get('tab', '')}",
                    "",
                    f"- status: `{'ok' if render.get('ok') else 'failed'}`",
                    f"- screenshot: `{render.get('screenshot', '')}`",
                    f"- screenshot SHA-256: `{render.get('screenshot_sha256', '')}`",
                    f"- capture method: `{render.get('capture_method', '')}`",
                    f"- terminal outcome: `{render.get('outcome')}`",
                    f"- plotter visible: `{render.get('plotter_visible')}`",
                    f"- VTK render completed: `{evidence.get('render_window_rendered')}`",
                    f"- actor count: `{evidence.get('actor_count')}`",
                    f"- render time seconds: `{evidence.get('last_render_seconds')}`",
                    f"- framebuffer color count: `{region.get('unique_color_count')}`",
                    f"- framebuffer chromatic fraction: `{region.get('chromatic_fraction')}`",
                    f"- unpainted pixel fraction: `{region.get('sentinel_fraction')}`",
                    "",
                ]
            )

    final_state = payload.get("final_state") or {}
    visualization = _section(final_state, "visualization")
    ui = payload.get("ui_state") or {}
    lines.extend(
        [
            "## UI State",
            "",
            f"- current panel: `{ui.get('current_panel', '')}`",
            f"- plan: `{ui.get('plan', '')}`",
            f"- run: `{ui.get('run', '')}`",
            f"- method: `{ui.get('method', '')}`",
            f"- montage available: `{visualization.get('montage_available')}`",
            "",
            "## Claim Boundary",
            "",
        ],
    )
    boundary = payload.get("claim_boundary") or {}
    for item in boundary.get("supports") or []:
        lines.append(f"- Supports {item}.")
    for item in boundary.get("does_not_support") or []:
        lines.append(f"- Does not support {item}.")
    return "\n".join(lines).rstrip() + "\n"


def _find_tab_index(panel: Any, tab_name: str) -> int:
    for index in range(panel.tabs.count()):
        if panel.tabs.tabText(index) == tab_name:
            return index
    return -1


def _render_failure_reason(tab_name: str, evidence: dict[str, Any]) -> str:
    if evidence.get("render_settled") is False:
        return f"{tab_name} render did not finish before the capture timeout."
    if evidence["error_visible"]:
        return f"{tab_name} showed error: {evidence['error_text']}"
    if not evidence["canvas_visible"]:
        return f"{tab_name} canvas was not visible."
    if evidence["axes_count"] < 1:
        return f"{tab_name} did not contain rendered axes."
    if evidence["image_count"] < 1:
        return f"{tab_name} did not contain a rendered image artist."
    geometry = evidence.get("canvas_geometry") or {}
    if not geometry.get("ok"):
        return f"{tab_name} {geometry.get('reason') or 'canvas geometry is invalid'}."
    artist_layout = evidence.get("artist_layout") or {}
    if not artist_layout.get("ok"):
        return f"{tab_name} {artist_layout.get('reason') or 'plot labels are clipped'}."
    if evidence.get("colorbar_margin_ok") is False:
        return f"{tab_name} colorbar does not leave a readable right margin."
    region = evidence.get("screenshot_region") or {}
    if not region.get("ok"):
        return f"{tab_name} {region.get('reason') or 'plot region is invalid'}."
    return f"{tab_name} screenshot capture failed."


def _schedule_message_box_dismissal(payload: dict[str, Any]) -> None:
    def dismiss() -> None:
        for widget in QApplication.topLevelWidgets():
            if not isinstance(widget, QMessageBox) or not widget.isVisible():
                continue
            payload["dismissed_dialogs"].append(
                {
                    "title": widget.windowTitle(),
                    "text": widget.text(),
                },
            )
            ok_button = widget.button(QMessageBox.StandardButton.Ok)
            if ok_button is not None:
                ok_button.click()
            else:
                widget.done(int(QMessageBox.StandardButton.Ok))
        if payload.get("status") == "running":
            QTimer.singleShot(100, dismiss)

    QTimer.singleShot(0, dismiss)


def _process_events(app: QApplication, milliseconds: int) -> None:
    deadline = time.monotonic() + milliseconds / 1000
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.05)


def _finish_payload(
    payload: dict[str, Any],
    service: Any,
    started_at: float,
    reason: str,
) -> dict[str, Any]:
    payload["status"] = "failed"
    payload["failure_reason"] = reason
    payload["elapsed_seconds"] = round(time.monotonic() - started_at, 3)
    payload["uncaught_exceptions"] = list(UNCAUGHT_EXCEPTIONS)
    try:
        payload["final_state"] = service.get_state().to_dict()
    except Exception:
        payload["final_state"] = {}
    _seal_source_identity(payload)
    return payload


def _seal_source_identity(payload: dict[str, Any]) -> None:
    completion = collect_source_identity(ROOT, refresh=True)
    start = payload.get("source_identity_at_start")
    start_identity = start if isinstance(start, dict) else {}
    payload["source_identity_at_completion"] = completion
    payload["source_identity"] = completion
    payload["source_capture"] = {
        "branch": completion.get("branch"),
        "commit_sha": completion.get("commit_sha"),
        "head_tree_sha": completion.get("head_tree_sha"),
        "dirty": bool(completion.get("dirty")),
        "dirty_digest": completion.get("dirty_digest"),
        "source_content_digest": completion.get("source_content_digest"),
        "source_digest_at_start": start_identity.get("source_digest"),
        "source_digest_at_completion": completion.get("source_digest"),
    }


def _command_payload(result: Any) -> dict[str, Any]:
    return {
        "command": str(getattr(result, "command_name", "")),
        "ok": result.ok,
        "message": result.message,
        "error_type": result.error_type.value if result.failed else None,
        "diagnostics": result.diagnostics,
    }


def _section(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _write_artifacts(output_dir: Path, payload: dict[str, Any]) -> None:
    payload = stable_artifact_payload(payload)
    (output_dir / JSON_ARTIFACT).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / MD_ARTIFACT).write_text(render_markdown(payload), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
