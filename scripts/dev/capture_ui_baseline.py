#!/usr/bin/env python3
"""Capture a minimal UI baseline screenshot set for XBrainLab.

This helper launches the real application stack, waits for the main window to
settle, and captures the rendered main-window widget across the shell and the
five primary panels into transient ``build/dev-artifacts/ui-baseline/`` PNGs. Approved references
live in ``tests/baselines/ui/``.

Expected usage in WSL/headless environments:

    xvfb-run -a /home/administrator/.local/bin/poetry run -- python \
        scripts/dev/capture_ui_baseline.py
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from XBrainLab.ui.qt_runtime import configure_qt_platform_for_runtime

configure_qt_platform_for_runtime()

from PyQt6.QtCore import QPoint, QSettings, QSize, Qt, QTimer
from PyQt6.QtWidgets import QApplication

from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
    inspect_screenshot_artifact,
    validate_source_identity,
)
from scripts.dev.human_like_walkthrough.readiness import (
    assert_consecutive_complete_frames,
)
from scripts.dev.ui_navigation import open_workflow_panel

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = ROOT / "build" / "dev-artifacts" / "ui-baseline"
OUTPUT_PATH = ARTIFACTS_DIR / "main-window-initial.png"
REFERENCE_UI_DIR = ROOT / "tests" / "baselines" / "ui"
MANIFEST_NAME = "ui-baseline-evidence.json"
SCHEMA_VERSION = 1
ARTIFACT_TYPE = "xbrainlab.ui_visual_baseline"
GENERATOR = "scripts/dev/capture_ui_baseline.py"
AI_DOCK_STEP = "ai-dock"
BASELINE_WINDOW_SIZE = QSize(1280, 800)
# Lazy panel materialization, dock resizing, and the final Qt polish/repaint each
# use queued event-loop work. Capturing earlier can record a partially repainted
# frame even though the live widget geometry is already correct.
PANEL_PAINT_SETTLE_MS = 300
CONSECUTIVE_FRAME_SETTLE_MS = 80
MAX_CONSECUTIVE_FRAME_CHANGED_RATIO = 0.02
MAX_UI_MEAN_DIFF = 1.5
MAX_UI_CHANGED_RATIO = 0.02
PIXEL_DIFF_THRESHOLD = 12
CAPTURE_STEPS = [
    ("main-window-initial.png", None),
    ("panel-dataset.png", 0),
    ("panel-preprocess.png", 1),
    ("panel-training.png", 2),
    ("panel-evaluation.png", 3),
    ("panel-visualization.png", 4),
    ("ai-assistant-open.png", AI_DOCK_STEP),
]
EXPECTED_UI_ARTIFACTS = tuple(filename for filename, _target in CAPTURE_STEPS)


def compare_ui_images(
    reference_path: Path,
    candidate_path: Path,
) -> tuple[str, dict[str, float | str]]:
    """Compare one candidate frame with its explicitly approved reference."""
    with (
        Image.open(reference_path) as reference_image,
        Image.open(candidate_path) as candidate_image,
    ):
        reference_rgb = reference_image.convert("RGB")
        candidate_rgb = candidate_image.convert("RGB")
    if reference_rgb.size != candidate_rgb.size:
        return (
            "fail",
            {
                "reason": "size mismatch",
                "reference_size": str(reference_rgb.size),
                "candidate_size": str(candidate_rgb.size),
            },
        )
    diff = ImageChops.difference(reference_rgb, candidate_rgb)
    mean_diff = sum(ImageStat.Stat(diff).mean) / 3
    diff_mask = diff.convert("L").point(
        lambda value: 255 if value > PIXEL_DIFF_THRESHOLD else 0
    )
    histogram = diff_mask.histogram()
    total_pixels = sum(histogram)
    changed_pixels = total_pixels - histogram[0]
    changed_ratio = changed_pixels / total_pixels if total_pixels else 0.0
    status = (
        "pass"
        if mean_diff <= MAX_UI_MEAN_DIFF and changed_ratio <= MAX_UI_CHANGED_RATIO
        else "fail"
    )
    return status, {
        "mean_diff": round(mean_diff, 3),
        "changed_ratio": round(changed_ratio, 4),
    }


def validate_ui_artifacts(
    artifacts_dir: Path,
    *,
    reference_dir: Path = REFERENCE_UI_DIR,
) -> tuple[str, str]:
    """Fail closed on missing, unusable, or visually drifted baseline frames."""
    missing = [
        name for name in EXPECTED_UI_ARTIFACTS if not (artifacts_dir / name).is_file()
    ]
    if missing:
        return "fail", f"Missing UI artifacts: {', '.join(missing)}"
    unusable = [
        name for name in EXPECTED_UI_ARTIFACTS if is_nearly_black(artifacts_dir / name)
    ]
    if unusable:
        return "fail", f"Nearly black UI artifacts: {', '.join(unusable)}"
    missing_references = [
        name for name in EXPECTED_UI_ARTIFACTS if not (reference_dir / name).is_file()
    ]
    if missing_references:
        return "fail", f"Missing UI references: {', '.join(missing_references)}"

    mismatches: list[str] = []
    matched_metrics: list[tuple[float, float]] = []
    for filename in EXPECTED_UI_ARTIFACTS:
        status, metrics = compare_ui_images(
            reference_dir / filename,
            artifacts_dir / filename,
        )
        if status != "pass":
            if metrics.get("reason") == "size mismatch":
                mismatches.append(
                    f"{filename} (size {metrics['candidate_size']} vs ref "
                    f"{metrics['reference_size']})"
                )
            else:
                mismatches.append(
                    f"{filename} (mean diff {metrics['mean_diff']}, changed "
                    f"{float(metrics['changed_ratio']):.2%})"
                )
            continue
        matched_metrics.append(
            (float(metrics["mean_diff"]), float(metrics["changed_ratio"]))
        )
    if mismatches:
        return "fail", f"UI baseline drift: {', '.join(mismatches[:3])}"
    max_mean = max((mean for mean, _ratio in matched_metrics), default=0.0)
    max_changed = max((ratio for _mean, ratio in matched_metrics), default=0.0)
    return (
        "pass",
        f"{len(EXPECTED_UI_ARTIFACTS)} UI artifacts match approved references "
        f"(max mean diff {max_mean:.3f}, max changed {max_changed:.2%}).",
    )


def _artifact_manifest(root: Path) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for filename in EXPECTED_UI_ARTIFACTS:
        record = inspect_screenshot_artifact(root / filename)
        record["path"] = filename
        records[filename] = record
    return records


def build_ui_baseline_evidence(
    *,
    output_dir: Path,
    reference_dir: Path,
    source_identity: Mapping[str, object],
    qt_platform: str,
    qt_style: str,
    device_pixel_ratio: float,
) -> dict[str, object]:
    """Build exact-source evidence only after candidate/reference comparison passes."""
    comparisons: dict[str, dict[str, float | str]] = {}
    for filename in EXPECTED_UI_ARTIFACTS:
        status, metrics = compare_ui_images(
            reference_dir / filename,
            output_dir / filename,
        )
        comparisons[filename] = {"status": status, **metrics}
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_identity": dict(source_identity),
        "capture_environment": {
            "platform_system": platform.system(),
            "qt_platform": qt_platform,
            "qt_style": qt_style,
            "device_pixel_ratio": float(device_pixel_ratio),
        },
        "expected_artifacts": list(EXPECTED_UI_ARTIFACTS),
        "screenshots": _artifact_manifest(output_dir),
        "references": _artifact_manifest(reference_dir),
        "comparisons": comparisons,
        "passed": all(item.get("status") == "pass" for item in comparisons.values()),
        "claim_boundary": (
            "Automated default-scale Qt comparison; not Windows human acceptance."
        ),
    }


def _write_manifest(output_dir: Path, payload: Mapping[str, object]) -> Path:
    destination = output_dir / MANIFEST_NAME
    temporary = output_dir / f".{MANIFEST_NAME}.tmp"
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def validate_ui_baseline_evidence(
    payload: Mapping[str, object],
    *,
    output_dir: Path,
    reference_dir: Path = REFERENCE_UI_DIR,
    current_source_identity: Mapping[str, object] | None = None,
) -> tuple[bool, str]:
    """Reject stale source, changed references, tampered frames, or visual drift."""
    if payload.get("schema_version") != SCHEMA_VERSION:
        return False, "UI baseline schema version is missing or unsupported."
    if (
        payload.get("artifact_type") != ARTIFACT_TYPE
        or payload.get("generator") != GENERATOR
    ):
        return False, "Artifact is not canonical UI baseline evidence."
    ok, reason = validate_source_identity(
        payload.get("source_identity"),
        expected_repo_root=ROOT,
        refresh=current_source_identity is None,
        current_identity=current_source_identity,
        artifact_name="UI baseline",
    )
    if not ok:
        return ok, reason
    if payload.get("expected_artifacts") != list(EXPECTED_UI_ARTIFACTS):
        return False, "UI baseline artifact inventory is incomplete."
    for key, root in (("screenshots", output_dir), ("references", reference_dir)):
        records = payload.get(key)
        if not isinstance(records, Mapping) or set(records) != set(
            EXPECTED_UI_ARTIFACTS
        ):
            return False, f"UI baseline {key} inventory is incomplete."
        for filename in EXPECTED_UI_ARTIFACTS:
            recorded = records.get(filename)
            observed = inspect_screenshot_artifact(root / filename)
            if isinstance(recorded, Mapping):
                observed["path"] = filename
            if recorded != observed:
                return False, f"UI baseline {key} changed: {filename}."
    status, summary = validate_ui_artifacts(output_dir, reference_dir=reference_dir)
    if status != "pass":
        return False, summary
    comparisons = payload.get("comparisons")
    if not isinstance(comparisons, Mapping) or any(
        not isinstance(comparisons.get(filename), Mapping)
        or comparisons[filename].get("status") != "pass"
        for filename in EXPECTED_UI_ARTIFACTS
    ):
        return False, "UI baseline comparison receipt is incomplete."
    if payload.get("passed") is not True:
        return False, "UI baseline evidence is not marked passed."
    return True, summary


def _clear_saved_main_window_geometry() -> None:
    """Remove user/session geometry so capture remains deterministic."""
    settings = QSettings("XBrainLab", "XBrainLab")
    settings.remove("main_window/geometry")
    settings.sync()


def _set_baseline_window_geometry(window) -> None:
    """Force the screenshot window to the approved capture dimensions."""
    window.setWindowState(Qt.WindowState.WindowNoState)
    screen = window.screen() or QApplication.primaryScreen()
    target = BASELINE_WINDOW_SIZE
    if screen is not None:
        available = screen.availableGeometry()
        window.move(available.topLeft())
    else:
        window.move(QPoint(0, 0))
    window.resize(target)


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


def _capture_window_frame(
    window,
    output_path: Path,
    *,
    announce: bool = False,
) -> int:
    """Grab one rendered frame and reject unusable output."""
    pixmap = window.grab()
    if pixmap.isNull():
        print("Failed to grab the main window pixmap.", file=sys.stderr)
        return 3
    if not pixmap.save(str(output_path)):
        print("Failed to save the grabbed main window pixmap.", file=sys.stderr)
        return 4
    if is_nearly_black(output_path):
        print(
            f"Captured screenshot is nearly all black and unusable: {output_path.name}",
            file=sys.stderr,
        )
        return 2
    if announce:
        print(f"Saved baseline screenshot to {output_path}")
    return 0


def _validate_consecutive_frames(first_frame: Path, second_frame: Path) -> int:
    """Reject captures that still contain a visible repaint transition."""
    try:
        assert_consecutive_complete_frames(
            first_frame,
            second_frame,
            max_changed_pixel_ratio=MAX_CONSECUTIVE_FRAME_CHANGED_RATIO,
        )
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 5
    return 0


def _prepare_capture_step(window, step_target) -> None:
    """Move the UI into the state needed for the requested capture step."""
    if step_target is None:
        return

    if step_target == AI_DOCK_STEP:
        open_workflow_panel(window, 0)
        if window.agent_manager is None:
            window.init_agent()
        manager = window.agent_manager
        if manager is None:
            return
        if manager.chat_dock is not None:
            manager.chat_dock.show()
        if hasattr(manager, "update_ai_btn_state"):
            manager.update_ai_btn_state(True)
        elif hasattr(window, "ai_btn"):
            window.ai_btn.setChecked(True)
        return

    open_workflow_panel(window, step_target)


def capture_window(app: QApplication, output_path: Path) -> int:
    """Launch the main window and capture the shell plus all five panels."""
    from XBrainLab.backend.application.runtime import get_application_service
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.main_window import MainWindow

    result: dict[str, int] = {"code": 3}

    _clear_saved_main_window_geometry()
    study = Study()
    get_application_service(study)
    window = MainWindow(study)
    _set_baseline_window_geometry(window)
    window.show()

    def _run_step(step_index: int) -> None:
        _filename, step_target = CAPTURE_STEPS[step_index]
        _prepare_capture_step(window, step_target)
        _set_baseline_window_geometry(window)

        app.processEvents()
        current_widget = window.stack.currentWidget()
        if current_widget is not None:
            current_widget.ensurePolished()
            layout = current_widget.layout()
            if layout is not None:
                layout.activate()
            current_widget.updateGeometry()
            current_widget.update()
        window.update()
        QTimer.singleShot(
            PANEL_PAINT_SETTLE_MS,
            lambda: _capture_prepared_step(step_index),
        )

    def _capture_prepared_step(step_index: int) -> None:
        filename, _step_target = CAPTURE_STEPS[step_index]
        app.processEvents()
        current_widget = window.stack.currentWidget()
        if current_widget is not None:
            current_widget.repaint()
        window.repaint()
        app.processEvents()

        step_output = output_path.parent / filename
        first_frame = step_output.with_name(f".{step_output.stem}-frame-1.png")
        result["code"] = _capture_window_frame(window, first_frame)
        if result["code"] != 0:
            first_frame.unlink(missing_ok=True)
            window.close()
            app.quit()
            return

        QTimer.singleShot(
            CONSECUTIVE_FRAME_SETTLE_MS,
            lambda: _capture_stable_step(step_index, first_frame, step_output),
        )

    def _capture_stable_step(
        step_index: int,
        first_frame: Path,
        step_output: Path,
    ) -> None:
        app.processEvents()
        current_widget = window.stack.currentWidget()
        if current_widget is not None:
            current_widget.repaint()
        window.repaint()
        app.processEvents()

        result["code"] = _capture_window_frame(
            window,
            step_output,
            announce=True,
        )
        if result["code"] == 0:
            result["code"] = _validate_consecutive_frames(first_frame, step_output)
        first_frame.unlink(missing_ok=True)
        if result["code"] != 0:
            window.close()
            app.quit()
            return

        if step_index + 1 >= len(CAPTURE_STEPS):
            window.close()
            app.quit()
            return

        QTimer.singleShot(
            max(0, 500 - PANEL_PAINT_SETTLE_MS),
            lambda: _run_step(step_index + 1),
        )

    QTimer.singleShot(2500, lambda: _run_step(0))
    app.exec()
    return result["code"]


def main(argv: list[str] | None = None) -> int:
    """Capture or validate the canonical default-scale visual baseline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ARTIFACTS_DIR,
        help="Candidate screenshot and evidence directory.",
    )
    parser.add_argument(
        "--reference-dir",
        type=Path,
        default=REFERENCE_UI_DIR,
        help="Explicitly approved visual reference directory.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate existing exact-source evidence without capturing.",
    )
    args = parser.parse_args(argv)
    output_dir = args.output_dir.expanduser().resolve()
    reference_dir = args.reference_dir.expanduser().resolve()
    if args.validate_only:
        try:
            payload = json.loads(
                (output_dir / MANIFEST_NAME).read_text(encoding="utf-8")
            )
        except (OSError, ValueError, TypeError) as error:
            print(f"UI baseline evidence could not be read: {error}", file=sys.stderr)
            return 1
        if not isinstance(payload, Mapping):
            print("UI baseline evidence is not a JSON object.", file=sys.stderr)
            return 1
        ok, reason = validate_ui_baseline_evidence(
            payload,
            output_dir=output_dir,
            reference_dir=reference_dir,
        )
        print(reason, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / MANIFEST_NAME).unlink(missing_ok=True)
    source_at_start = collect_source_identity(ROOT, refresh=True)
    app = QApplication([sys.argv[0]])
    app.setStyle("Fusion")
    code = capture_window(app, output_dir / OUTPUT_PATH.name)
    if code != 0:
        return code
    source_at_end = collect_source_identity(ROOT, refresh=True)
    if source_at_start.get("source_digest") != source_at_end.get("source_digest"):
        print("Product source changed during UI baseline capture.", file=sys.stderr)
        return 6
    status, summary = validate_ui_artifacts(output_dir, reference_dir=reference_dir)
    if status != "pass":
        print(summary, file=sys.stderr)
        return 7
    screen = app.primaryScreen()
    evidence = build_ui_baseline_evidence(
        output_dir=output_dir,
        reference_dir=reference_dir,
        source_identity=source_at_end,
        qt_platform=QApplication.platformName(),
        qt_style=app.style().objectName(),
        device_pixel_ratio=(screen.devicePixelRatio() if screen is not None else 0.0),
    )
    _write_manifest(output_dir, evidence)
    ok, reason = validate_ui_baseline_evidence(
        evidence,
        output_dir=output_dir,
        reference_dir=reference_dir,
        current_source_identity=source_at_end,
    )
    print(reason, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 8


if __name__ == "__main__":
    raise SystemExit(main())
