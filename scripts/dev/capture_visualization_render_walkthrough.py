#!/usr/bin/env python3
"""Capture a true MainWindow visualization canvas render walkthrough."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, cast

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox

from scripts.dev.capture_chatpanel_local_tool_chain_walkthrough import (
    _capture_current_window,
    _clear_saved_main_window_geometry,
    _set_baseline_window_geometry,
)
from scripts.dev.capture_chatpanel_local_training_completion_walkthrough import (
    prepare_training_dataset_ready_state,
    write_synthetic_training_raw_fif,
)
from scripts.dev.capture_chatpanel_local_walkthrough import is_nearly_black
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
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ui" / "visualization-render"
TEMP_ROOT = Path(tempfile.gettempdir())
TRAINING_OUTPUT_DIR = TEMP_ROOT / "xbrainlab-visualization-render-output"
JSON_ARTIFACT = "visualization-render-walkthrough.json"
MD_ARTIFACT = "visualization-render-walkthrough.md"
RENDER_TAB_SPECS: list[dict[str, str]] = [
    {
        "tab": "Saliency Map",
        "screenshot": "visualization-render-saliency-map.png",
    },
    {
        "tab": "Spectrogram",
        "screenshot": "visualization-render-spectrogram.png",
    },
    {
        "tab": "Topographic Map",
        "screenshot": "visualization-render-topographic-map.png",
    },
]
BLOCKED_TAB_SPECS: list[dict[str, str]] = [
    {
        "tab": "3D Plot",
        "screenshot": "visualization-render-3d-blocked.png",
        "expected_reason": "interactive OpenGL desktop session",
    },
]
UNCAUGHT_EXCEPTIONS: list[str] = []


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
    _install_uncaught_exception_capture()
    started_at = time.monotonic()
    _clear_saved_main_window_geometry()
    source_path = write_synthetic_training_raw_fif()
    study = Study()
    service = get_application_service(study)
    dataset_preparation = prepare_training_dataset_ready_state(study, source_path)
    payload: dict[str, Any] = {
        "status": "running",
        "failure_reason": "",
        "artifact_metadata": {
            "status": "current release-candidate visualization evidence",
            "generator": "scripts/dev/capture_visualization_render_walkthrough.py",
            "environment": "Qt offscreen VisualizationPanel capture with PYVISTA_OFF_SCREEN",
            "supports": "MainWindow VisualizationPanel 2D saliency renders and headless 3D blocked state",
            "does_not_support": "interactive 3D render or human Windows click-through acceptance",
            "next_human_or_runtime_gate": "manual desktop visualization click-through with an interactive OpenGL session",
        },
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
        "renders": [],
        "blocked_renders": [],
        "claim_boundary": {
            "supports": [
                "true MainWindow VisualizationPanel Matplotlib saliency renders",
                "user-facing 3D blocked reason in headless/offscreen runtime",
            ],
            "does_not_support": [
                "interactive 3D render",
                "Windows human click-through",
            ],
        },
        "dismissed_dialogs": [],
        "screenshots": {"ready": ""},
        "final_state": {},
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
    window.switch_page(4)
    _process_events(app, 800)

    panel = cast(Any, window).visualization_panel
    payload["ui_state"] = {
        "current_panel": "Visualization",
        "plan": panel.plan_combo.currentText(),
        "run": panel.run_combo.currentText(),
        "method": panel.method_combo.currentText(),
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
        for spec in BLOCKED_TAB_SPECS:
            payload["blocked_renders"].append(
                _capture_blocked_tab(app, window, output_dir, spec),
            )

    payload["final_state"] = service.get_state().to_dict()
    payload["uncaught_exceptions"] = list(UNCAUGHT_EXCEPTIONS)
    ok, reason = validate_visualization_render_payload(payload)
    payload["status"] = "passed" if ok else "failed"
    payload["failure_reason"] = "" if ok else reason
    payload["elapsed_seconds"] = round(time.monotonic() - started_at, 3)
    window.close()
    app.quit()
    return payload


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
        SaliencyCommand(
            method="Gradient",
            params={"nt_samples": 2, "nt_samples_batch_size": 1, "stdevs": 1.0},
        ),
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

    panel.tabs.setCurrentIndex(tab_index)
    panel.method_combo.setCurrentText("Gradient")
    panel.on_update()
    _process_events(app, 500)
    widget = panel.tabs.currentWidget()
    evidence = _render_evidence(widget)
    screenshot_path = output_dir / spec["screenshot"]
    capture_code = _capture_current_window(window, screenshot_path)
    ok = (
        capture_code == 0
        and not evidence["error_visible"]
        and evidence["canvas_visible"]
        and evidence["axes_count"] > 0
        and evidence["image_count"] > 0
    )
    return {
        "tab": tab_name,
        "screenshot": str(screenshot_path),
        "ok": ok,
        "failure_reason": "" if ok else _render_failure_reason(tab_name, evidence),
        **evidence,
    }


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
    panel.on_update()
    _process_events(app, 500)
    widget = panel.tabs.currentWidget()
    blocked_reason = _visible_label_text(widget)
    expected_reason = spec["expected_reason"]
    message_evidence = _blocked_message_evidence(widget, expected_reason)
    plotter_created = bool(getattr(widget, "plotter_widget", None))
    screenshot_path = output_dir / spec["screenshot"]
    capture_code = _capture_current_window(window, screenshot_path)
    ok = (
        capture_code == 0
        and expected_reason in blocked_reason
        and not plotter_created
        and message_evidence["ok"]
    )
    return {
        "tab": tab_name,
        "screenshot": str(screenshot_path),
        "ok": ok,
        "failure_reason": ""
        if ok
        else f"{tab_name} did not show an unclipped expected blocked reason.",
        "blocked_reason": blocked_reason,
        "message_evidence": message_evidence,
        "plotter_created": plotter_created,
    }


def _render_evidence(widget: Any) -> dict[str, Any]:
    fig = getattr(widget, "fig", None)
    axes = list(getattr(fig, "axes", []) or [])
    image_count = sum(
        len(getattr(axis, "images", []) or [])
        + len(getattr(axis, "collections", []) or [])
        for axis in axes
    )
    error_label = getattr(widget, "error_label", None)
    canvas = getattr(widget, "canvas", None)
    return {
        "error_visible": bool(error_label and error_label.isVisible()),
        "error_text": str(error_label.text()) if error_label else "",
        "axes_count": len(axes),
        "image_count": image_count,
        "canvas_visible": bool(canvas and canvas.isVisible()),
    }


def _visible_label_text(widget: Any) -> str:
    labels = [
        label.text()
        for label in widget.findChildren(QLabel)
        if not label.isHidden() and label.text()
    ]
    return " ".join(labels)


def _control_layout_evidence(panel: Any) -> dict[str, Any]:
    widgets = {
        "plan": getattr(panel, "plan_combo", None),
        "run": getattr(panel, "run_combo", None),
        "method": getattr(panel, "method_combo", None),
        "absolute": getattr(panel, "abs_check", None),
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
    return {
        "ok": not hidden and not overlaps,
        "hidden_or_empty": hidden,
        "overlaps": overlaps,
        "rects": rects,
    }


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
    if not payload.get("dataset_preparation", {}).get("ok"):
        return False, "Dataset preparation failed."
    if payload.get("uncaught_exceptions"):
        first = str(payload["uncaught_exceptions"][0]).splitlines()[-1]
        return False, f"Uncaught Qt/runtime exception during capture: {first}"

    training = payload.get("training") or {}
    if int(training.get("finished_run_count") or 0) < 1:
        return False, "No completed tiny training run was captured."
    if not training.get("metrics_available"):
        return False, "Evaluation metrics were not available after tiny training."
    if not training.get("saliency_available"):
        return False, "Saliency was not available after tiny training."

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
        detail = overlaps or hidden or "unknown layout issue"
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
        if int(render.get("image_count") or 0) < 1:
            return False, f"{tab} did not contain a rendered image artist."
        screenshot_ok, screenshot_reason = _validate_screenshot(
            render.get("screenshot"),
            f"{tab} screenshot",
        )
        if not screenshot_ok:
            return False, screenshot_reason

    blocked = {item.get("tab"): item for item in payload.get("blocked_renders", [])}
    for spec in BLOCKED_TAB_SPECS:
        tab = spec["tab"]
        render = blocked.get(tab)
        if not render:
            return False, f"Missing blocked evidence for {tab}."
        if not render.get("ok"):
            return False, render.get("failure_reason") or f"{tab} blocked check failed."
        if render.get("plotter_created"):
            return False, f"{tab} created a PyVista plotter in a blocked runtime."
        if spec["expected_reason"] not in str(render.get("blocked_reason", "")):
            return False, f"{tab} did not show a user-facing blocked reason."
        if not (render.get("message_evidence") or {}).get("ok"):
            return False, f"{tab} blocked reason appears clipped or hidden."
        screenshot_ok, screenshot_reason = _validate_screenshot(
            render.get("screenshot"),
            f"{tab} blocked screenshot",
        )
        if not screenshot_ok:
            return False, screenshot_reason
    return True, ""


def _validate_screenshot(path: Any, label: str) -> tuple[bool, str]:
    screenshot = Path(str(path or "").strip())
    if not str(screenshot):
        return False, f"{label} path was not recorded."
    if not screenshot.is_file():
        return False, f"{label} file was not found: {screenshot}."
    if is_nearly_black(screenshot):
        return False, f"{label} was nearly all black: {screenshot}."
    return True, ""


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
        "",
        f"- status: `{payload['status']}`",
        f"- failure reason: {payload.get('failure_reason') or 'none'}",
        f"- source path: `{payload.get('source_path', '')}`",
        f"- training output dir: `{payload.get('training_output_dir', '')}`",
        f"- dataset preparation ok: `{payload['dataset_preparation']['ok']}`",
        f"- finished runs: `{payload.get('training', {}).get('finished_run_count')}`",
        f"- metrics available: `{payload.get('training', {}).get('metrics_available')}`",
        f"- saliency available: `{payload.get('training', {}).get('saliency_available')}`",
        f"- ready screenshot: `{payload.get('screenshots', {}).get('ready', '')}`",
        f"- elapsed seconds: `{payload['elapsed_seconds']}`",
        f"- uncaught exceptions: `{len(payload.get('uncaught_exceptions') or [])}`",
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
                f"- axes count: `{render.get('axes_count')}`",
                f"- image count: `{render.get('image_count')}`",
                f"- error visible: `{render.get('error_visible')}`",
                f"- canvas visible: `{render.get('canvas_visible')}`",
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
                    f"- plotter created: `{render.get('plotter_created')}`",
                    f"- blocked reason: {render.get('blocked_reason', '')}",
                    "",
                ],
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
    if evidence["error_visible"]:
        return f"{tab_name} showed error: {evidence['error_text']}"
    if not evidence["canvas_visible"]:
        return f"{tab_name} canvas was not visible."
    if evidence["axes_count"] < 1:
        return f"{tab_name} did not contain rendered axes."
    if evidence["image_count"] < 1:
        return f"{tab_name} did not contain a rendered image artist."
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
    return payload


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
    (output_dir / JSON_ARTIFACT).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / MD_ARTIFACT).write_text(render_markdown(payload), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
