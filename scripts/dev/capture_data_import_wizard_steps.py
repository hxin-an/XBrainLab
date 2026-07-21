#!/usr/bin/env python3
"""Capture canonical Data Import wizard screenshots."""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

from PIL import Image
from PyQt6.QtCore import (
    QBuffer,
    QCoreApplication,
    QEvent,
    QEventLoop,
    QIODevice,
    QPoint,
    QSize,
    QTimer,
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QLabel,
    QPushButton,
    QWidget,
)

from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
)
from scripts.dev.data_import_capture_contract import (
    MANIFEST_NAME,
    build_data_import_capture_manifest,
    load_data_import_capture_manifest,
    validate_data_import_capture_manifest,
    write_data_import_capture_manifest,
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
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
    _ConvertedLabelTableDialog,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(
    os.environ.get(
        "XBRAINLAB_UI_CAPTURE_DIR",
        str(ROOT / "artifacts" / "ui" / "data-import-wizard-steps"),
    )
)
WINDOW_SIZE = QSize(1220, 1320)
WIZARD_STEP_TEXT = (
    "1. Choose EEG Data",
    "2. Load Labels",
    "3. Review Metadata",
    "4. Match Labels",
    "5. Review and Import",
)
WIZARD_COMPACT_STEP_TEXT = (
    "1. EEG Data",
    "2. Labels",
    "3. Metadata",
    "4. Match",
    "5. Review",
)


@dataclass(frozen=True)
class CanonicalCaptureSpec:
    filename: str
    dialog_factory: Callable[[], QWidget]
    title: str
    primary_action: str
    summary: str | None = None
    step_title: str | None = None
    expanded_report: bool = False
    expected_size: tuple[int, int] = (1220, 1320)
    label_carrier_count: int = 0
    bids_events: bool = False

    @property
    def has_wizard_chrome(self) -> bool:
        return self.step_title is not None


def main(argv: list[str] | None = None) -> int:
    specs = _canonical_capture_specs()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory for canonical PNG evidence.",
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=[spec.filename for spec in specs],
        help="Capture only this artifact; repeat for multiple artifacts.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the existing complete manifest without capturing.",
    )
    args = parser.parse_args(argv)
    expected_surfaces = [spec.filename for spec in specs]
    selected_set = set(args.only or expected_surfaces)
    output_dir = args.output_dir.expanduser().resolve()
    if args.validate_only:
        if args.only:
            parser.error("--validate-only cannot be combined with --only")
        payload = load_data_import_capture_manifest(output_dir)
        ok, reason = validate_data_import_capture_manifest(
            payload,
            output_dir=output_dir,
            expected_surfaces=expected_surfaces,
        )
        if not ok:
            print(f"Data Import capture rejected: {reason}", file=sys.stderr)
            return 1
        print(f"Validated {output_dir / MANIFEST_NAME}")
        return 0
    if args.only and output_dir == OUTPUT_DIR:
        parser.error("--only requires a non-canonical --output-dir")

    selected_specs = [spec for spec in specs if spec.filename in selected_set]
    capture_started_at = datetime.now(UTC)
    source_identity_at_start = collect_source_identity(ROOT, refresh=True)
    session_id = _new_capture_session_id()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{output_dir.name}-capture-",
        dir=output_dir.parent,
    ) as staging_name:
        staging_dir = Path(staging_name)
        if args.only:
            _capture_specs_in_process(selected_specs, staging_dir)
        else:
            _capture_specs_in_isolated_processes(selected_specs, staging_dir)
        source_identity_at_completion = collect_source_identity(ROOT, refresh=True)
        manifest = build_data_import_capture_manifest(
            staging_dir,
            expected_surfaces=expected_surfaces,
            selected_surfaces=[spec.filename for spec in selected_specs],
            source_identity=source_identity_at_completion,
            source_identity_at_start=source_identity_at_start,
            capture_started_at=capture_started_at,
            generated_at=datetime.now(UTC),
            qt_platform=QApplication.platformName() if args.only else "xcb",
            session_id=session_id,
        )
        ok, reason = validate_data_import_capture_manifest(
            manifest,
            output_dir=staging_dir,
            expected_surfaces=expected_surfaces,
            require_complete=not bool(args.only),
        )
        if not ok:
            raise RuntimeError(f"Data Import capture contract failed: {reason}")
        write_data_import_capture_manifest(staging_dir, manifest)
        _publish_capture(
            staging_dir,
            output_dir,
            selected_surfaces=[spec.filename for spec in selected_specs],
        )
    return 0


def _new_capture_session_id() -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"


def _publish_capture(
    staging_dir: Path,
    output_dir: Path,
    *,
    selected_surfaces: list[str],
) -> None:
    """Publish settled PNGs first, then atomically replace the manifest last."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in selected_surfaces:
        (staging_dir / filename).replace(output_dir / filename)
    (staging_dir / MANIFEST_NAME).replace(output_dir / MANIFEST_NAME)


def _capture_specs_in_isolated_processes(
    specs: Sequence[CanonicalCaptureSpec],
    staging_dir: Path,
) -> None:
    """Capture every canonical frame in a fresh Qt process and Xvfb display."""
    script = Path(__file__).resolve()
    xvfb = shutil.which("Xvfb")
    if xvfb is None:
        raise RuntimeError("Complete Data Import capture requires Xvfb.")
    child_environment = dict(os.environ)
    child_environment["QT_QPA_PLATFORM"] = "xcb"
    for spec in specs:
        server, display = _start_xvfb(xvfb)
        child_environment["DISPLAY"] = display
        try:
            completed = subprocess.run(  # noqa: S603 - current Python executable.
                [
                    sys.executable,
                    str(script),
                    "--output-dir",
                    str(staging_dir),
                    "--only",
                    spec.filename,
                ],
                cwd=ROOT,
                check=False,
                env=child_environment,
            )
        finally:
            _stop_xvfb(server)
        if completed.returncode != 0:
            raise RuntimeError(
                f"Data Import child capture failed: {spec.filename} "
                f"(exit {completed.returncode})."
            )
        if not (staging_dir / spec.filename).is_file():
            raise RuntimeError(
                f"Data Import child capture did not publish: {spec.filename}."
            )


def _start_xvfb(executable: str) -> tuple[subprocess.Popen[str], str]:
    display_number = _allocate_xvfb_display_number()
    server = subprocess.Popen(  # noqa: S603 - resolved local Xvfb executable.
        [
            executable,
            f":{display_number}",
            "-screen",
            "0",
            "1600x1400x24",
            "-listen",
            "tcp",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    for _ in range(100):
        if server.poll() is not None:
            break
        if _xvfb_tcp_ready(display_number):
            return server, f"localhost:{display_number}"
        time.sleep(0.05)
    _stop_xvfb(server)
    raise RuntimeError("Xvfb did not become ready within 5 seconds.")


def _allocate_xvfb_display_number() -> int:
    for _ in range(64):
        # Keep the X11 TCP port (6000 + display number) below 65535.
        number = 10_000 + int(uuid.uuid4().hex[:8], 16) % 40_000
        if not _xvfb_tcp_ready(number):
            return number
    raise RuntimeError("Could not allocate an unused Xvfb TCP display number.")


def _xvfb_tcp_ready(display_number: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 6000 + display_number), 0.1):
            return True
    except OSError:
        return False


def _stop_xvfb(server: subprocess.Popen[str]) -> None:
    if server.poll() is not None:
        return
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=10)


def _capture_specs_in_process(
    specs: Sequence[CanonicalCaptureSpec],
    staging_dir: Path,
) -> None:
    """Capture a targeted noncanonical subset in one lightweight Qt process."""
    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication(sys.argv)
    app.setStyle("Fusion")
    for spec in specs:
        dialog = spec.dialog_factory()
        try:
            _prepare_capture(dialog, spec, app)
            _capture(dialog, staging_dir / spec.filename, spec)
        finally:
            dialog.close()
            dialog.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()


def _canonical_capture_specs() -> tuple[CanonicalCaptureSpec, ...]:
    common_summary = "Found 3 EEG file(s) and 3 label/event carrier(s)."
    one_file_summary = "Found 1 EEG file(s) and 1 label/event carrier(s)."
    return (
        CanonicalCaptureSpec(
            filename="01-choose-eeg-data-760px.png",
            dialog_factory=_main_dialog,
            step_title="Choose EEG Data",
            title="Choose EEG Data",
            summary=common_summary,
            primary_action="Next: Load Labels",
            expected_size=(760, 900),
            label_carrier_count=3,
        ),
        CanonicalCaptureSpec(
            filename="01-choose-eeg-data.png",
            dialog_factory=_main_dialog,
            step_title="Choose EEG Data",
            title="Choose EEG Data",
            summary=common_summary,
            primary_action="Next: Load Labels",
            label_carrier_count=3,
        ),
        CanonicalCaptureSpec(
            filename="02-load-labels-many-1040px.png",
            dialog_factory=_many_labels_dialog,
            step_title="Load Labels",
            title="Load Labels",
            summary="Found 3 EEG file(s) and 12 label/event carrier(s).",
            primary_action="Next: Review Metadata",
            expected_size=(1040, 1100),
            label_carrier_count=12,
        ),
        CanonicalCaptureSpec(
            filename="02-load-labels-many.png",
            dialog_factory=_many_labels_dialog,
            step_title="Load Labels",
            title="Load Labels",
            summary="Found 3 EEG file(s) and 12 label/event carrier(s).",
            primary_action="Next: Review Metadata",
            label_carrier_count=12,
        ),
        CanonicalCaptureSpec(
            filename="03-review-metadata.png",
            dialog_factory=_main_dialog,
            step_title="Review Metadata",
            title="Review Metadata",
            summary=common_summary,
            primary_action="Next: Match Labels",
            label_carrier_count=3,
        ),
        CanonicalCaptureSpec(
            filename="04-match-labels-bids-events.png",
            dialog_factory=_bids_events_dialog,
            step_title="Match Labels",
            title="Match Labels",
            summary=one_file_summary,
            primary_action="Next: Review and Import",
            label_carrier_count=1,
            bids_events=True,
        ),
        CanonicalCaptureSpec(
            filename="04-match-labels-conversion-fallback.png",
            dialog_factory=_conversion_fallback_dialog,
            step_title="Match Labels",
            title="Match Labels",
            summary=one_file_summary,
            primary_action="Next: Review and Import",
            label_carrier_count=1,
        ),
        CanonicalCaptureSpec(
            filename="04-match-labels-conversion-table-format-dialog.png",
            dialog_factory=_converted_label_table_dialog,
            title="XBrainLab label table",
            primary_action="Close",
            expected_size=(900, 720),
        ),
        CanonicalCaptureSpec(
            filename="04-match-labels-final-loaded-label-files.png",
            dialog_factory=_loaded_label_files_dialog,
            step_title="Match Labels",
            title="Match Labels",
            summary=one_file_summary,
            primary_action="Next: Review and Import",
            label_carrier_count=1,
        ),
        CanonicalCaptureSpec(
            filename="04-match-labels-internal-suggested-events-full.png",
            dialog_factory=_internal_events_dialog,
            step_title="Match Labels",
            title="Match Labels",
            summary="Found 3 EEG file(s).",
            primary_action="Next: Review and Import",
        ),
        CanonicalCaptureSpec(
            filename="05-review-and-import-report.png",
            dialog_factory=_review_import_dialog,
            step_title="Review and Import",
            title="Review and Import",
            summary=common_summary,
            primary_action="Confirm and Import",
            expanded_report=True,
            label_carrier_count=3,
        ),
        CanonicalCaptureSpec(
            filename="05-review-and-import.png",
            dialog_factory=_review_import_dialog,
            step_title="Review and Import",
            title="Review and Import",
            summary=common_summary,
            primary_action="Confirm and Import",
            label_carrier_count=3,
        ),
    )


def _prepare_capture(
    widget: QWidget,
    spec: CanonicalCaptureSpec,
    app: QApplication,
) -> None:
    if spec.has_wizard_chrome:
        if not isinstance(widget, DataInterpretationPreviewDialog):
            raise RuntimeError(f"Wizard capture has an invalid dialog: {spec.filename}")
        if spec.step_title is None:
            raise RuntimeError(f"Wizard capture has no step title: {spec.filename}")
        _show_step(widget, spec.step_title, spec, app)
        if spec.expanded_report:
            _expand_report_for_capture(widget, app)
            _assert_report_row_visible(widget)
        return

    widget.resize(QSize(*spec.expected_size))
    widget.show()
    app.processEvents()
    _assert_capture_size(widget, spec)
    _wait_for_paint(50)


def _assert_capture_size(widget: QWidget, spec: CanonicalCaptureSpec) -> None:
    expected = QSize(*spec.expected_size)
    if widget.size() != expected:
        raise RuntimeError(
            f"{spec.filename} needs a {expected.width()}x{expected.height()} "
            "virtual screen. Run it with QT_QPA_PLATFORM=xcb xvfb-run -a -s "
            "'-screen 0 1600x1400x24'."
        )


def _show_step(
    dialog: DataInterpretationPreviewDialog,
    step_title: str,
    spec: CanonicalCaptureSpec,
    app: QApplication,
) -> None:
    expected_size = QSize(*spec.expected_size)
    dialog.resize(expected_size)
    dialog.show()
    app.processEvents()
    # Native window decoration/layout startup can transiently restore the
    # dialog's construction width. Reapply the evidence viewport after show.
    dialog.resize(expected_size)
    app.processEvents()
    if dialog.size() != expected_size:
        raise RuntimeError(
            f"Data Import capture needs a {expected_size.width()}x"
            f"{expected_size.height()} virtual screen. "
            "Run it with QT_QPA_PLATFORM=xcb xvfb-run -a -s "
            "'-screen 0 1600x1400x24'."
        )
    _wait_for_paint(50)
    dialog._go_to_step(dialog._step_titles.index(step_title))
    app.processEvents()
    dialog.repaint()
    _wait_for_paint(50)


def _assert_report_row_visible(dialog: DataInterpretationPreviewDialog) -> None:
    tree = dialog.review_tree
    first = tree.topLevelItem(0)
    if first is None:
        raise RuntimeError("Import report contains no review rows.")
    row_rect = tree.visualItemRect(first)
    viewport = tree.viewport()
    if viewport is None or not row_rect.intersects(viewport.rect()):
        raise RuntimeError("Import report does not show a review row in the viewport.")


def _expand_report_for_capture(
    dialog: DataInterpretationPreviewDialog,
    app: QApplication,
) -> None:
    dialog.import_report_toggle.click()
    app.processEvents()
    _settle_window_for_capture(dialog)


def _capture(
    widget: QWidget,
    output_path: Path,
    spec: CanonicalCaptureSpec,
) -> None:
    last_error: RuntimeError | None = None
    first_frame = output_path.with_name(f".{output_path.stem}-frame-1.png")
    for _attempt in range(3):
        try:
            _settle_window_for_capture(widget)
            _save_window_capture(_grab_window(widget), first_frame)
            _assert_complete_capture_frame(
                widget,
                first_frame,
                spec,
                logical_name=output_path.name,
            )
            _settle_window_for_capture(widget)
            _save_window_capture(_grab_window(widget), output_path)
            _assert_complete_capture_frame(
                widget,
                output_path,
                spec,
                logical_name=output_path.name,
            )
            _assert_consecutive_complete_frames(first_frame, output_path)
        except RuntimeError as exc:
            last_error = exc
            widget.update()
            continue
        finally:
            first_frame.unlink(missing_ok=True)
        return
    raise RuntimeError(
        f"Window capture did not fully repaint after 3 attempts: {output_path.name}"
    ) from last_error


def _assert_complete_capture_frame(
    widget: QWidget,
    screenshot: Path,
    spec: CanonicalCaptureSpec,
    *,
    logical_name: str,
) -> None:
    _assert_step_navigation_visible(widget, screenshot)
    _assert_key_text_rendered(widget, screenshot)
    _assert_review_surface_rendered(
        widget,
        screenshot,
        logical_name=logical_name,
    )
    _assert_canonical_capture_artifact(
        widget,
        screenshot,
        spec,
        logical_name=logical_name,
    )
    _assert_no_clipped_inline_actions(widget, screenshot)
    _assert_single_vertical_scroll_owner(widget, screenshot)
    _assert_required_capture_regions(widget, screenshot)


def _save_window_capture(pixmap: QPixmap, output_path: Path) -> None:
    if pixmap.isNull():
        raise RuntimeError(f"Could not grab {output_path}.")
    if not pixmap.save(str(output_path)):
        raise RuntimeError(f"Could not save {output_path}.")
    _normalize_png_for_artifact(output_path)
    if _is_nearly_black(output_path):
        raise RuntimeError(f"Screenshot is nearly black: {output_path}.")


def _normalize_png_for_artifact(output_path: Path) -> None:
    """Re-encode Qt captures as decoder-compatible RGB PNG artifacts."""
    with Image.open(output_path) as captured:
        normalized = captured.convert("RGB")
        normalized.load()
    normalized.save(output_path, format="PNG", optimize=True)


def _grab_window(widget: QWidget) -> QPixmap:
    """Capture the real xcb window surface used by the canonical artifact run."""
    _require_xcb_capture(QApplication.platformName())
    screen = widget.screen() or QApplication.primaryScreen()
    if screen is None:
        raise RuntimeError("xcb window capture requires an available screen.")
    top_left = widget.mapToGlobal(widget.rect().topLeft())
    root_window = cast(Any, 0)
    return screen.grabWindow(
        root_window,
        top_left.x(),
        top_left.y(),
        widget.width(),
        widget.height(),
    )


def _require_xcb_capture(platform_name: str) -> None:
    if platform_name.strip().casefold() != "xcb":
        raise RuntimeError(
            "Canonical Data Import captures require the xcb platform under Xvfb."
        )


def _wait_for_paint(milliseconds: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def _settle_window_for_capture(widget: QWidget) -> None:
    """Flush layout and paint work before reading the native xcb surface."""
    widget.ensurePolished()
    widget.updateGeometry()
    layout = widget.layout()
    if layout is not None:
        layout.invalidate()
        layout.activate()
    visible_children = [
        child for child in widget.findChildren(QWidget) if child.isVisibleTo(widget)
    ]
    for child in visible_children:
        child.ensurePolished()
        child.updateGeometry()
        child.update()
    widget.update()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.UpdateRequest)
    app = QApplication.instance()
    if isinstance(app, QApplication):
        app.processEvents()
    widget.repaint()
    for child in visible_children:
        child.repaint()
    if isinstance(app, QApplication):
        app.processEvents()
    _wait_for_paint(150)


def _assert_step_navigation_visible(widget: QWidget, output_path: Path) -> None:
    step_labels = getattr(widget, "step_labels", [])
    for label in step_labels:
        top_left = widget.mapFromGlobal(label.mapToGlobal(label.rect().topLeft()))
        bottom_right = widget.mapFromGlobal(
            label.mapToGlobal(label.rect().bottomRight())
        )
        if (
            top_left.x() < 0
            or top_left.y() < 0
            or bottom_right.x() >= widget.width()
            or bottom_right.y() >= widget.height()
        ):
            raise RuntimeError(
                "Step navigation appears clipped in "
                f"{output_path.name}: {label.text()} at "
                f"({top_left.x()}, {top_left.y()})-"
                f"({bottom_right.x()}, {bottom_right.y()})"
            )


def _assert_key_text_rendered(widget: QWidget, screenshot: Path) -> None:
    """Reject captures where visible wizard navigation or footer text was not painted."""
    step_labels = getattr(widget, "step_labels", [])
    controls: list[QWidget] = [
        label
        for label in step_labels
        if isinstance(label, QLabel) and label.isVisible()
    ]
    for name in ("summary_label", "cancel_button", "next_button", "apply_button"):
        control = getattr(widget, name, None)
        if isinstance(control, QWidget) and control.isVisible():
            controls.append(control)
    _assert_text_controls_rendered(
        widget,
        screenshot,
        controls,
        surface_name="Wizard key text",
    )


def _assert_review_surface_rendered(
    widget: QWidget,
    screenshot: Path,
    *,
    logical_name: str | None = None,
) -> None:
    """Reject expanded-report captures whose review header was not painted."""
    review_summaries = getattr(widget, "_review_summary_value_labels", None)
    if not isinstance(review_summaries, dict) or not review_summaries:
        return
    controls: list[QWidget] = [
        label
        for label in getattr(widget, "step_labels", [])
        if isinstance(label, QLabel) and label.isVisible()
    ]
    summary = getattr(widget, "summary_label", None)
    if isinstance(summary, QLabel) and summary.isVisible():
        controls.append(summary)
    controls.extend(
        label
        for label in widget.findChildren(QLabel)
        if label.isVisible()
        and (
            label.objectName().startswith("DataImportReview")
            or label.text().strip() in {"Review and Import", "Import review"}
        )
    )
    for name in ("save_recipe_check", "import_report_toggle"):
        control = getattr(widget, name, None)
        if isinstance(control, QWidget) and control.isVisible():
            controls.append(control)
    _assert_text_controls_rendered(
        widget,
        screenshot,
        controls,
        surface_name="Review header",
    )
    if (logical_name or screenshot.name).startswith("05-review-and-import"):
        _assert_canonical_review_artifact(screenshot)


def _assert_canonical_capture_artifact(
    widget: QWidget,
    screenshot: Path,
    spec: CanonicalCaptureSpec,
    *,
    logical_name: str | None = None,
) -> None:
    """Validate the semantic and painted text contract for one canonical PNG."""
    if (logical_name or screenshot.name) != spec.filename:
        raise RuntimeError(
            f"Capture spec {spec.filename} does not match {screenshot.name}."
        )
    _assert_canonical_png_artifact(screenshot, spec)

    controls, summary_label = _canonical_text_controls(widget, spec)
    _assert_text_controls_rendered(
        widget,
        screenshot,
        controls,
        surface_name="Canonical capture text",
    )
    if summary_label is not None:
        if spec.summary is None:
            raise RuntimeError(f"Wizard capture has no summary: {spec.filename}")
        _assert_line_tokens_rendered(widget, screenshot, summary_label, spec.summary)


def _assert_canonical_png_artifact(
    screenshot: Path,
    spec: CanonicalCaptureSpec,
) -> None:
    """Validate canonical encoding and fixed text coverage without Qt geometry."""
    with Image.open(screenshot) as captured:
        if captured.mode != "RGB" or captured.size != spec.expected_size:
            raise RuntimeError(
                f"Canonical artifact must be a {spec.expected_size[0]}x"
                f"{spec.expected_size[1]} RGB PNG: {screenshot.name}"
            )
        if "dpi" in captured.info:
            raise RuntimeError(
                "Canonical artifact retains Qt DPI metadata that can render "
                f"unpainted regions: {screenshot.name}"
            )
        grayscale = captured.convert("L")

    if not spec.has_wizard_chrome:
        _assert_bright_region(
            grayscale,
            (20, 24, 180, 49),
            minimum_bright_pixels=100,
            description=f"title {spec.title!r}",
            screenshot=screenshot,
        )
        _assert_bright_region(
            grayscale,
            (815, 670, 880, 700),
            minimum_bright_pixels=50,
            description=f"primary action {spec.primary_action!r}",
            screenshot=screenshot,
        )
        return

    step_width = max((spec.expected_size[0] - 40 - 32) // 5, 1)
    for index, expected_text in enumerate(WIZARD_STEP_TEXT):
        left = 20 + index * (step_width + 8)
        _assert_bright_region(
            grayscale,
            (left + 4, 24, min(left + step_width - 4, spec.expected_size[0]), 47),
            minimum_bright_pixels=35,
            description=f"step label {expected_text!r}",
            screenshot=screenshot,
        )

    if spec.summary is None:
        raise RuntimeError(f"Wizard capture has no summary: {spec.filename}")
    for description, bounds, minimum in _summary_text_probes(spec.summary):
        _assert_bright_region(
            grayscale,
            bounds,
            minimum_bright_pixels=minimum,
            description=description,
            screenshot=screenshot,
        )
    _assert_bright_region(
        grayscale,
        (20, 98, 450, 123),
        minimum_bright_pixels=100,
        description=f"title {spec.title!r}",
        screenshot=screenshot,
    )
    _assert_bright_region(
        grayscale,
        (25, spec.expected_size[1] - 45, 96, spec.expected_size[1] - 14),
        minimum_bright_pixels=50,
        description="Cancel action",
        screenshot=screenshot,
    )
    _assert_bright_region(
        grayscale,
        (
            max(spec.expected_size[0] - 280, 0),
            spec.expected_size[1] - 45,
            spec.expected_size[0] - 20,
            spec.expected_size[1] - 12,
        ),
        minimum_bright_pixels=180,
        description=f"primary action {spec.primary_action!r}",
        screenshot=screenshot,
    )


def _summary_text_probes(
    summary: str,
) -> tuple[tuple[str, tuple[int, int, int, int], int], ...]:
    common = (
        (f"summary prefix in {summary!r}", (20, 68, 80, 86), 100),
        (f"summary middle in {summary!r}", (80, 68, 140, 86), 100),
    )
    if summary == "Found 3 EEG file(s).":
        return (*common, (f"summary tail in {summary!r}", (140, 68, 175, 86), 50))
    return (*common, (f"summary tail in {summary!r}", (330, 68, 390, 86), 100))


def _assert_bright_region(
    grayscale: Image.Image,
    bounds: tuple[int, int, int, int],
    *,
    minimum_bright_pixels: int,
    description: str,
    screenshot: Path,
) -> None:
    histogram = grayscale.crop(bounds).histogram()
    if sum(histogram[110:]) < minimum_bright_pixels:
        raise RuntimeError(
            f"Canonical artifact did not render {description}: {screenshot.name}"
        )


def _canonical_text_controls(
    widget: QWidget,
    spec: CanonicalCaptureSpec,
) -> tuple[list[QWidget], QLabel | None]:
    title_label = _visible_label_with_text(widget, spec.title)
    controls: list[QWidget] = [title_label]
    if not spec.has_wizard_chrome:
        close_button = getattr(widget, "close_button", None)
        if not isinstance(close_button, QPushButton):
            raise RuntimeError(f"Missing Close action for {spec.filename}.")
        if close_button.text() != spec.primary_action or not close_button.isVisibleTo(
            widget
        ):
            raise RuntimeError(f"Close action contract changed for {spec.filename}.")
        controls.append(close_button)
        return controls, None

    step_labels = getattr(widget, "step_labels", None)
    if not isinstance(step_labels, list):
        raise RuntimeError(f"Missing wizard steps for {spec.filename}.")
    actual_steps = tuple(
        label.text() for label in step_labels if isinstance(label, QLabel)
    )
    if actual_steps not in {WIZARD_STEP_TEXT, WIZARD_COMPACT_STEP_TEXT} or len(
        actual_steps
    ) != len(step_labels):
        raise RuntimeError(f"Wizard step text contract changed for {spec.filename}.")
    if actual_steps == WIZARD_COMPACT_STEP_TEXT and any(
        label.toolTip() != full_text.removeprefix(f"{index}. ")
        for index, (label, full_text) in enumerate(
            zip(step_labels, WIZARD_STEP_TEXT, strict=True),
            start=1,
        )
    ):
        raise RuntimeError(
            f"Compact wizard steps lose their full names in {spec.filename}."
        )
    if not all(label.isVisibleTo(widget) for label in step_labels):
        raise RuntimeError(f"Wizard steps are hidden in {spec.filename}.")
    controls.extend(step_labels)

    summary_label = getattr(widget, "summary_label", None)
    if not isinstance(summary_label, QLabel) or spec.summary is None:
        raise RuntimeError(f"Missing wizard summary for {spec.filename}.")
    if summary_label.text() != spec.summary or not summary_label.isVisibleTo(widget):
        raise RuntimeError(f"Wizard summary contract changed for {spec.filename}.")
    controls.append(summary_label)

    cancel_button = getattr(widget, "cancel_button", None)
    if (
        not isinstance(cancel_button, QPushButton)
        or cancel_button.text() != "Cancel"
        or not cancel_button.isVisibleTo(widget)
    ):
        raise RuntimeError(f"Cancel action contract changed for {spec.filename}.")
    controls.append(cancel_button)

    primary_name = (
        "apply_button" if spec.step_title == "Review and Import" else "next_button"
    )
    primary_button = getattr(widget, primary_name, None)
    if (
        not isinstance(primary_button, QPushButton)
        or primary_button.text() != spec.primary_action
        or not primary_button.isVisibleTo(widget)
    ):
        raise RuntimeError(f"Primary action contract changed for {spec.filename}.")
    controls.append(primary_button)
    return controls, summary_label


def _visible_label_with_text(widget: QWidget, expected_text: str) -> QLabel:
    matches = [
        label
        for label in widget.findChildren(QLabel)
        if label.text() == expected_text and label.isVisibleTo(widget)
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one visible title {expected_text!r}, found {len(matches)}."
        )
    return matches[0]


def _assert_line_tokens_rendered(
    widget: QWidget,
    screenshot: Path,
    label: QLabel,
    expected_text: str,
) -> None:
    """Check every summary token at its expected painted x-position."""
    top_left = label.mapTo(widget, QPoint(0, 0))
    metrics = label.fontMetrics()
    cursor = 0
    with Image.open(screenshot) as captured:
        grayscale = captured.convert("L")
        for token in expected_text.split():
            start = expected_text.index(token, cursor)
            end = start + len(token)
            cursor = end
            left = top_left.x() + metrics.horizontalAdvance(expected_text[:start]) - 1
            right = top_left.x() + metrics.horizontalAdvance(expected_text[:end]) + 1
            bounds = (
                max(left, 0),
                max(top_left.y(), 0),
                min(right, grayscale.width),
                min(top_left.y() + label.height(), grayscale.height),
            )
            histogram = grayscale.crop(bounds).histogram()
            if sum(histogram[110:]) < 3:
                raise RuntimeError(
                    f"Canonical summary token {token!r} was not rendered in "
                    f"{screenshot.name}."
                )


def _assert_canonical_review_artifact(screenshot: Path) -> None:
    """Reject decoder-incompatible or visibly blank canonical review artifacts."""
    with Image.open(screenshot) as captured:
        expected_size = (WINDOW_SIZE.width(), WINDOW_SIZE.height())
        if captured.mode != "RGB" or captured.size != expected_size:
            raise RuntimeError(
                "Canonical review artifact must be a 1220x1320 RGB PNG: "
                f"{screenshot.name}"
            )
        if "dpi" in captured.info:
            raise RuntimeError(
                "Canonical review artifact retains Qt DPI metadata that can render "
                f"as a blank header: {screenshot.name}"
            )
        grayscale = captured.convert("L")

    for name, bounds, minimum_bright_pixels in (
        ("navigation and title", (0, 0, 1220, 150), 5_000),
        ("import review rows", (0, 150, 1220, 410), 5_000),
    ):
        histogram = grayscale.crop(bounds).histogram()
        bright_pixels = sum(histogram[110:])
        if bright_pixels < minimum_bright_pixels:
            raise RuntimeError(
                f"Canonical review artifact has a blank {name} band: {screenshot.name}"
            )


def _assert_text_controls_rendered(
    widget: QWidget,
    screenshot: Path,
    controls: list[QWidget],
    *,
    surface_name: str,
) -> None:
    with Image.open(screenshot) as captured:
        rgb = captured.convert("RGB")
        for control in controls:
            top_left = control.mapTo(widget, QPoint(0, 0))
            bounds = (
                max(top_left.x(), 0),
                max(top_left.y(), 0),
                min(top_left.x() + control.width(), rgb.width),
                min(top_left.y() + control.height(), rgb.height),
            )
            region = rgb.crop(bounds)
            _assert_region_has_no_unpainted_block(
                screenshot,
                bounds,
                surface_name=f"{surface_name}: {_control_name(control)}",
            )
            _assert_region_matches_reference(
                screenshot,
                bounds,
                _pixmap_image(control.grab()),
                surface_name=f"{surface_name}: {_control_name(control)}",
                minimum_edge_recall=0.70,
                maximum_changed_pixel_ratio=1.0,
            )
            border_margin = min(4, region.width // 4, region.height // 4)
            if border_margin:
                region = region.crop(
                    (
                        border_margin,
                        border_margin,
                        region.width - border_margin,
                        region.height - border_margin,
                    )
                )
            histogram = region.convert("L").histogram()
            pixel_count = sum(histogram)
            glyph_pixels = sum(histogram[110:])
            if not pixel_count or glyph_pixels < pixel_count * 0.01:
                text_getter = getattr(control, "text", None)
                text = (
                    str(text_getter())
                    if callable(text_getter)
                    else control.objectName()
                )
                raise RuntimeError(
                    f"{surface_name} was not fully rendered in "
                    f"{screenshot.name}: {text}"
                )


def _assert_single_vertical_scroll_owner(
    widget: QWidget,
    screenshot: Path,
) -> None:
    """Reject nested vertical scrolling inside the wizard's content scroller."""
    if not isinstance(widget, DataInterpretationPreviewDialog):
        return
    active: list[QAbstractScrollArea] = []
    for area in [widget.scroll_area, *widget.findChildren(QAbstractScrollArea)]:
        if area in active or not area.isVisibleTo(widget):
            continue
        scrollbar = area.verticalScrollBar()
        if scrollbar is not None and scrollbar.maximum() > 0 and scrollbar.isVisible():
            active.append(area)
    nested = [area for area in active if area is not widget.scroll_area]
    if nested:
        names = [area.objectName() or type(area).__name__ for area in nested]
        raise RuntimeError(
            f"Wizard has nested vertical scroll owners in {screenshot.name}: {names}."
        )
    horizontal = widget.scroll_area.horizontalScrollBar()
    if horizontal is not None and horizontal.maximum() > 0:
        raise RuntimeError(
            f"Wizard content requires horizontal scrolling in {screenshot.name}."
        )


def _assert_required_capture_regions(widget: QWidget, screenshot: Path) -> None:
    if not isinstance(widget, DataInterpretationPreviewDialog):
        return
    required: dict[str, QWidget] = {
        "Wizard summary": widget.summary_label,
        "Wizard content": widget.scroll_area,
        "Wizard Cancel": widget.cancel_button,
    }
    primary = (
        widget.apply_button if widget.apply_button.isVisible() else widget.next_button
    )
    required["Wizard primary action"] = primary
    for index, label in enumerate(widget.step_labels, start=1):
        required[f"Wizard step {index}"] = label
    for surface_name, control in required.items():
        rect = _widget_bounds(widget, control)
        _assert_region_has_no_unpainted_block(
            screenshot,
            (rect.left(), rect.top(), rect.right() + 1, rect.bottom() + 1),
            surface_name=surface_name,
        )
        _assert_region_matches_reference(
            screenshot,
            (rect.left(), rect.top(), rect.right() + 1, rect.bottom() + 1),
            _pixmap_image(control.grab()),
            surface_name=surface_name,
            minimum_edge_recall=0.42 if control is widget.scroll_area else 0.70,
            maximum_changed_pixel_ratio=(
                0.55 if control is widget.scroll_area else 1.0
            ),
        )


def _widget_bounds(root: QWidget, control: QWidget):
    top_left = control.mapTo(root, QPoint(0, 0))
    return control.rect().translated(top_left)


def _pixmap_image(pixmap: QPixmap) -> Image.Image:
    if pixmap.isNull():
        raise RuntimeError("Could not create a settled live control reference.")
    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("Could not open the live control reference buffer.")
    if not pixmap.save(buffer, "PNG"):
        raise RuntimeError("Could not encode the live control reference.")
    data = bytes(cast(Any, buffer.data()))
    buffer.close()
    with Image.open(BytesIO(data)) as source:
        image = source.convert("RGB")
        image.load()
    return image


def _control_name(control: QWidget) -> str:
    text_getter = getattr(control, "text", None)
    if callable(text_getter):
        text = " ".join(str(text_getter()).split())
        if text:
            return text
    return control.objectName() or type(control).__name__


def _assert_no_clipped_inline_actions(widget: QWidget, output_path: Path) -> None:
    for button in widget.findChildren(QPushButton):
        if button.objectName() != "DataImportInlineAction" or not button.isVisible():
            continue
        text_width = button.fontMetrics().horizontalAdvance(button.text()) + 18
        if button.width() < text_width:
            raise RuntimeError(
                "Inline action appears clipped in "
                f"{output_path.name}: {button.text()} width={button.width()} "
                f"needed={text_width}"
            )


def _is_nearly_black(path: Path) -> bool:
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


def _base_scan() -> dict[str, Any]:
    return {
        "source_path": "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data",
        "source_kind": "file",
        "eeg_files": [
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/A01T.gdf",
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/A02T.gdf",
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/A03T.gdf",
        ],
        "label_carriers": [
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/A01T.mat",
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/A02T.mat",
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/A03T.mat",
        ],
        "label_carrier_sources": {
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/A01T.mat": (
                "auto"
            ),
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/A02T.mat": (
                "auto"
            ),
            "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/A03T.mat": (
                "auto"
            ),
        },
        "bids": {"is_bids": False, "events_files": []},
    }


def _converted_label_table_dialog() -> _ConvertedLabelTableDialog:
    style_source = _main_dialog()
    dialog = _ConvertedLabelTableDialog()
    dialog.setStyleSheet(style_source.styleSheet())
    style_source.close()
    style_source.deleteLater()
    return dialog


def _main_dialog() -> DataInterpretationPreviewDialog:
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result=_base_scan(),
        preview={
            "summary": "Found 3 EEG file(s) and 3 label/event carrier(s).",
            "source_selection": "3 selected file(s)",
            "metadata_preview": _metadata_rows(),
            "label_carrier_preview": _label_carriers(),
            "confirmation_items": [
                "Confirm session metadata for A01T.gdf.",
                "Confirm label placement for A01T.mat: 6 selected EEG events have no label.",
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )


def _many_labels_dialog() -> DataInterpretationPreviewDialog:
    scan = _base_scan()
    carriers = []
    paths = []
    for index in range(1, 13):
        path = f"/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/A{index:02d}T.mat"
        paths.append(path)
        carriers.append(
            {
                "path": path,
                "name": Path(path).name,
                "format": "MAT",
                "source_kind": "auto_discovered" if index <= 6 else "user_added",
                "source_location": (
                    ""
                    if index <= 6
                    else "/mnt/d/workspace_v2/projects/lab/XBrainLab/external-labels"
                ),
                "selected_label_field": "classlabel",
                "selected_anchor": "trial order",
                "time_model": "trial_order",
                "granularity": "trial",
                "placement_method": "eeg_event",
            }
        )
    scan["label_carriers"] = paths
    scan["label_carrier_sources"] = {
        path: "auto" if index <= 6 else "/external-labels"
        for index, path in enumerate(paths, start=1)
    }
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result=scan,
        preview={
            "summary": "Found 3 EEG file(s) and 12 label/event carrier(s).",
            "source_selection": "3 selected file(s)",
            "metadata_preview": _metadata_rows(),
            "label_carrier_preview": carriers,
        },
        validation_decision={"decision": "needs_confirmation"},
    )


def _internal_events_dialog() -> DataInterpretationPreviewDialog:
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result={**_base_scan(), "label_carriers": []},
        preview={
            "summary": "Found 3 EEG file(s).",
            "source_selection": "3 selected file(s)",
            "metadata_preview": _metadata_rows(),
            "internal_event_preview": {
                "pattern_status": "Shared event pattern detected",
                "candidate_label_events": [
                    _event("769", "Class label", 216, "Repeats once per trial"),
                    _event("770", "Class label", 216, "Repeats once per trial"),
                    _event("771", "Class label", 216, "Repeats once per trial"),
                    _event(
                        "772",
                        "Class label",
                        144,
                        "Missing in A03T.gdf",
                        coverage="2/3 files",
                    ),
                ],
                "not_used_events": [
                    _event("768", "Trial timing", 864, "Trial start marker"),
                    _event("1023", "Exclude bad trials", 18, "Rejected trial marker"),
                    _event("32766", "Ignore", 3, "System / boundary marker"),
                ],
            },
        },
        validation_decision={"decision": "needs_confirmation"},
    )


def _loaded_label_files_dialog() -> DataInterpretationPreviewDialog:
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            **_base_scan(),
            "eeg_files": [
                "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/A01T.gdf",
            ],
            "label_carriers": [
                "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/A01T.mat",
            ],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "source_selection": "1 selected file",
            "metadata_preview": [_metadata_rows()[0]],
            "label_carrier_preview": [_label_carriers()[0]],
            "internal_event_preview": _external_target_event_preview(),
        },
        validation_decision={"decision": "needs_confirmation"},
    )


def _bids_events_dialog() -> DataInterpretationPreviewDialog:
    events_path = (
        "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/bids/"
        "sub-01_task-mi_run-01_events.tsv"
    )
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/bids",
            "source_kind": "bids",
            "eeg_files": [
                "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/bids/"
                "sub-01_task-mi_run-01_raw.fif",
            ],
            "label_carriers": [events_path],
            "bids": {
                "is_bids": True,
                "subjects": ["01"],
                "sessions": [],
                "tasks": ["mi"],
                "runs": ["01"],
                "events_files": [events_path],
                "has_participants_tsv": False,
            },
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "source_selection": "BIDS folder",
            "metadata_preview": [_metadata_rows()[0]],
            "label_carrier_preview": [
                {
                    "path": events_path,
                    "name": "sub-01_task-mi_run-01_events.tsv",
                    "format": "BIDS events",
                    "bids_event_columns": ["onset", "duration", "trial_type"],
                    "label_candidates": ["trial_type"],
                    "anchor_candidates": ["onset"],
                    "time_field_candidates": ["onset"],
                    "duration_candidates": ["duration"],
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "selected_duration_field": "duration",
                    "time_model": "seconds",
                    "placement_method": "interval",
                    "granularity": "trial",
                    "label_value_counts": {
                        "left_hand": 72,
                        "right_hand": 72,
                        "feet": 72,
                        "tongue": 72,
                    },
                    "value_decisions": {
                        value: {
                            "role": "unknown",
                            "keep_event": None,
                            "use_as_class": None,
                            "suggested_name": name,
                            "decision": "unresolved",
                            "decision_source": "unresolved",
                            "provenance": "observed:BIDS events:trial_type",
                            "count": 72,
                        }
                        for value, name in {
                            "left_hand": "Left hand",
                            "right_hand": "Right hand",
                            "feet": "Feet",
                            "tongue": "Tongue",
                        }.items()
                    },
                    "placement_review": {
                        "method": "interval",
                        "status": "ready",
                        "label_field": "trial_type",
                        "time_field": "onset",
                        "duration_field": "duration",
                        "label_rows": 288,
                        "numeric_rows": 288,
                        "duration_numeric_rows": 288,
                        "summary": (
                            "288 labels have onset and duration fields from events.tsv."
                        ),
                    },
                    "warnings": [
                        "events.json sidecar is missing; class names need review."
                    ],
                },
            ],
            "action_items": [
                {
                    "target_step": "Match Labels",
                    "issue": "Confirm BIDS class names.",
                    "impact": (
                        "events.json was not found, so class descriptions come "
                        "from raw trial_type values."
                    ),
                    "next_action": "Confirm class names in Match Labels.",
                }
            ],
        },
        validation_decision={"decision": "needs_confirmation"},
    )


def _conversion_fallback_dialog() -> DataInterpretationPreviewDialog:
    label_path = (
        "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/custom_labels.mat"
    )
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            **_base_scan(),
            "eeg_files": [
                "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/A01T.gdf",
            ],
            "label_carriers": [label_path],
        },
        preview={
            "summary": "Found 1 EEG file(s) and 1 label/event carrier(s).",
            "source_selection": "1 selected file",
            "metadata_preview": [_metadata_rows()[0]],
            "label_carrier_preview": [
                {
                    "path": label_path,
                    "name": "custom_labels.mat",
                    "format": "MAT",
                    "label_candidates": [],
                    "anchor_candidates": [],
                    "selected_label_field": "",
                    "selected_anchor": "",
                    "time_model": "",
                    "granularity": "",
                    "placement_method": "eeg_event",
                    "role": "external labels",
                }
            ],
        },
        validation_decision={"decision": "blocked"},
    )


def _review_import_dialog() -> DataInterpretationPreviewDialog:
    metadata_rows = _metadata_rows()
    for row in metadata_rows:
        row["task"] = {"value": "", "decision": "needs_confirmation"}
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result=_base_scan(),
        preview={
            "summary": "Found 3 EEG file(s) and 3 label/event carrier(s).",
            "source_selection": "3 selected file(s)",
            "metadata_preview": metadata_rows,
            "label_carrier_preview": _label_carriers(),
            "resource_preflight": {
                "risk_level": "safe",
                "requires_confirmation": False,
                "issues": [],
                "warnings": [],
                "unknowns": [],
                "message": "Resource check: Safe",
                "required_memory_bytes": 2 * 1024**3,
                "available_memory_bytes": 24 * 1024**3,
            },
            "action_items": [
                {
                    "target_step": "Review and Import",
                    "issue": "Optional session values were inferred",
                    "impact": (
                        "Session T was inferred from the selected file names for "
                        "A01T.gdf, A02T.gdf, and A03T.gdf."
                    ),
                    "next_action": (
                        "No action is required unless the import summary is unexpected."
                    ),
                    "severity": "warning",
                },
            ],
        },
        validation_decision={"decision": "safe"},
    )


def _review_import_state_dialog(state: str) -> DataInterpretationPreviewDialog:
    preview: dict[str, Any] = {
        "summary": "Found 3 EEG file(s) and 3 label/event carrier(s).",
        "source_selection": "3 selected file(s)",
        "metadata_preview": _metadata_rows(),
        "label_carrier_preview": _label_carriers(),
    }
    validation_decision: dict[str, Any] = {"decision": "safe"}
    if state == "confirm":
        preview["action_items"] = [
            {
                "target_step": "Review Metadata",
                "issue": "Confirm subject metadata.",
                "impact": "Subject was inferred from filenames for 3 files.",
                "next_action": "Review metadata if the subject is wrong.",
            }
        ]
        validation_decision = {"decision": "needs_confirmation"}
    elif state == "review":
        preview["action_items"] = [
            {
                "target_step": "Match Labels",
                "issue": "Label count needs review.",
                "impact": "A03T.mat has 282 labels and 288 selected EEG events.",
                "next_action": "Check target EEG events in Match Labels.",
            }
        ]
    elif state == "both":
        preview["action_items"] = [
            {
                "target_step": "Review Metadata",
                "issue": "Confirm subject metadata.",
                "impact": "Subject was inferred from filenames for 3 files.",
                "next_action": "Review metadata if the subject is wrong.",
            },
            {
                "target_step": "Match Labels",
                "issue": "Label count needs review.",
                "impact": "A03T.mat has 282 labels and 288 selected EEG events.",
                "next_action": "Check target EEG events in Match Labels.",
            },
        ]
        validation_decision = {"decision": "needs_confirmation"}

    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result=_base_scan(),
        preview=preview,
        validation_decision=validation_decision,
    )


def _metadata_rows() -> list[dict[str, Any]]:
    return [
        {
            "file": "A01T.gdf",
            "subject": {"value": "A01", "decision": "safe"},
            "session": {"value": "T", "decision": "needs_confirmation"},
            "task": {"value": "motor-imagery", "decision": "safe"},
            "run": {"value": "01", "decision": "safe"},
        },
        {
            "file": "A02T.gdf",
            "subject": {"value": "A02", "decision": "safe"},
            "session": {"value": "T", "decision": "needs_confirmation"},
            "task": {"value": "motor-imagery", "decision": "safe"},
            "run": {"value": "01", "decision": "safe"},
        },
        {
            "file": "A03T.gdf",
            "subject": {"value": "A03", "decision": "safe"},
            "session": {"value": "T", "decision": "needs_confirmation"},
            "task": {"value": "motor-imagery", "decision": "safe"},
            "run": {"value": "01", "decision": "safe"},
        },
    ]


def _label_carriers() -> list[dict[str, Any]]:
    carriers = []
    for name, target in (
        ("A01T.mat", "A01T.gdf"),
        ("A02T.mat", "A02T.gdf"),
        ("A03T.mat", "A03T.gdf"),
    ):
        carriers.append(
            {
                "path": (
                    "/mnt/d/workspace_v2/projects/lab/XBrainLab/tests/data/label/"
                    f"{name}"
                ),
                "name": name,
                "format": "MAT",
                "target_file": target,
                "label_candidates": ["classlabel"],
                "anchor_candidates": ["trial order"],
                "event_code_candidates": ["event_code"],
                "selected_label_field": "classlabel",
                "selected_anchor": "trial order",
                "selected_target_event_codes": ["769", "770", "771", "772"],
                "label_row_count": 282,
                "label_value_counts": {"1": 72, "2": 70, "3": 70, "4": 70},
                "time_model": "trial_order",
                "granularity": "trial",
                "placement_method": "eeg_event",
                "role": "external labels",
                "placement_review": {
                    "method": "eeg_event",
                    "status": "ready",
                    "label_field": "classlabel",
                    "label_rows": 282,
                    "selected_eeg_events": 282,
                    "matched": 282,
                    "summary": "282 label rows match 282 selected EEG events.",
                },
            }
        )
    return carriers


def _external_target_event_preview() -> dict[str, Any]:
    return {
        "pattern_status": "Event pattern ready for review",
        "candidate_label_events": [
            _event("769", "Class label", 72, "Repeated count + timing"),
            _event("770", "Class label", 70, "Repeated count + timing"),
            _event("771", "Class label", 70, "Repeated count + timing"),
            _event("772", "Class label", 70, "Repeated count + timing"),
        ],
        "not_used_events": [
            _event("768", "Trial timing", 288, "Matches class total"),
            _event("1023", "Artifact", 6, "Artifact text"),
        ],
    }


def _event(
    event_code: str,
    use_as: str,
    event_count: int,
    evidence: str,
    *,
    coverage: str = "3/3 files",
) -> dict[str, Any]:
    return {
        "event_code": event_code,
        "use_as": use_as,
        "event_count": event_count,
        "coverage": coverage,
        "evidence": evidence,
    }


if __name__ == "__main__":
    raise SystemExit(main())
