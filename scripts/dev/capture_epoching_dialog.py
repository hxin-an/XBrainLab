#!/usr/bin/env python3
"""Capture canonical Create EEG Epochs dialog screenshots and evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image
from PyQt6.QtCore import QElapsedTimer, QEventLoop, QPoint, QRect, QSize
from PyQt6.QtWidgets import QApplication, QPushButton, QScrollArea, QWidget

from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
)
from XBrainLab.backend.application.epoch_context import (
    EPOCH_HINT_KEY,
    build_epoching_context,
)
from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "dev-artifacts" / "epoching-dialog"
EVIDENCE_FILENAME = "epoching-dialog-evidence.json"


class _EpochData:
    def __init__(self, event_id: dict[str, int], hint: dict[str, Any]) -> None:
        self._event_id = event_id
        self._hint = hint

    def get_event_list(self):
        return None, self._event_id

    def get_runtime_detail(self, key: str) -> Any:
        return self._hint if key == EPOCH_HINT_KEY else None

    @property
    def hint(self) -> dict[str, Any]:
        return self._hint


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for epoching screenshots and evidence JSON.",
    )
    parser.add_argument(
        "--include-layout-variants",
        action="store_true",
        help="Also capture available-space and intentionally narrow layouts.",
    )
    args = parser.parse_args(argv)
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication(sys.argv)
    source_identity_at_start = collect_source_identity(ROOT, refresh=True)
    capture_specs = [
        (
            "interval-import",
            "epoching-interval-import.png",
            _interval_epoch_data,
            False,
            None,
            "production",
            False,
        ),
        (
            "internal-events",
            "epoching-internal-events.png",
            _internal_event_epoch_data,
            True,
            None,
            "production",
            False,
        ),
        (
            "baseline-enabled",
            "epoching-baseline-enabled.png",
            _internal_event_epoch_data,
            True,
            None,
            "production",
            False,
        ),
        (
            "baseline-disabled",
            "epoching-baseline-disabled.png",
            _internal_event_epoch_data,
            False,
            None,
            "production",
            False,
        ),
        (
            "baseline-order-invalid",
            "epoching-baseline-order-invalid.png",
            _internal_event_epoch_data,
            True,
            "baseline-order",
            "production",
            False,
        ),
        (
            "time-window-invalid",
            "epoching-time-window-invalid.png",
            _internal_event_epoch_data,
            False,
            "time-window",
            "production",
            False,
        ),
    ]
    if args.include_layout_variants:
        capture_specs.extend(
            (
                (
                    "available-space",
                    "epoching-available-space.png",
                    _available_space_epoch_data,
                    True,
                    None,
                    "production",
                    False,
                ),
                (
                    "bounded-overflow",
                    "epoching-bounded-overflow.png",
                    _many_event_epoch_data,
                    True,
                    None,
                    "narrow",
                    True,
                ),
            )
        )

    captures: list[dict[str, Any]] = []
    for (
        state,
        filename,
        data_factory,
        baseline_enabled,
        invalid_state,
        layout_mode,
        expected_vertical_scroll,
    ) in capture_specs:
        data = data_factory()
        dialog = EpochingDialog(
            None,
            epoch_context=build_epoching_context(
                [data],
                epoch_handoff=_epoch_handoff(data),
            ),
        )
        _configure_capture_state(
            dialog,
            baseline_enabled=baseline_enabled,
            invalid_state=invalid_state,
        )
        _settle_layout(app, dialog)
        if layout_mode == "narrow":
            dialog.resize(QSize(620, 520))
            _settle_layout(app, dialog)
            scroll = dialog.findChild(QScrollArea, "EpochDialogContentScroll")
            if scroll is None:
                raise RuntimeError("Epoch content scroll is unavailable for capture.")
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
            _settle_layout(app, dialog)

        screenshot = output_dir / filename
        screenshot_evidence = _capture(dialog, screenshot)
        baseline_surface = _baseline_surface_evidence(dialog, screenshot)
        semantic_checks = _semantic_evidence(
            dialog,
            expected_baseline_enabled=baseline_enabled,
            invalid_state=invalid_state,
        )
        geometry_checks = _geometry_evidence(
            dialog,
            expected_vertical_scroll=expected_vertical_scroll,
        )
        if not semantic_checks["passed"]:
            raise RuntimeError(f"Epoch semantic evidence failed for {state}.")
        if not geometry_checks["passed"]:
            raise RuntimeError(f"Epoch geometry evidence failed for {state}.")
        if not baseline_surface["passed"]:
            raise RuntimeError(f"Epoch baseline surface evidence failed for {state}.")
        captures.append(
            {
                "state": state,
                "layout_mode": layout_mode,
                "screenshot": filename,
                "screenshot_evidence": screenshot_evidence,
                "dpi": _dpi_evidence(dialog),
                "baseline_surface": baseline_surface,
                "geometry_checks": geometry_checks,
                "semantic_checks": semantic_checks,
            }
        )
        dialog.close()
        dialog.deleteLater()
        app.processEvents()

    source_identity_at_end = collect_source_identity(ROOT, refresh=True)
    _write_evidence_manifest(
        output_dir=output_dir,
        source_identity_at_start=source_identity_at_start,
        source_identity_at_end=source_identity_at_end,
        captures=captures,
        generated_at=datetime.now(UTC),
        qt_platform=QApplication.platformName(),
    )
    return 0


def _configure_capture_state(
    dialog: EpochingDialog,
    *,
    baseline_enabled: bool,
    invalid_state: str | None,
) -> None:
    if dialog.baseline_check is None:
        raise RuntimeError("Epoch baseline toggle is unavailable for capture.")
    dialog.baseline_check.setChecked(baseline_enabled)
    if invalid_state == "baseline-order":
        if dialog.b_min_spin is None or dialog.b_max_spin is None:
            raise RuntimeError("Epoch baseline inputs are unavailable for capture.")
        dialog.b_min_spin.setValue(0.5)
        dialog.b_max_spin.setValue(0.2)
    elif invalid_state == "time-window":
        if dialog.tmin_spin is None or dialog.tmax_spin is None:
            raise RuntimeError("Epoch time inputs are unavailable for capture.")
        dialog.tmin_spin.setValue(1.0)
        dialog.tmax_spin.setValue(0.5)


def _interval_epoch_data() -> _EpochData:
    return _EpochData(
        {"Left hand": 1, "Right hand": 2, "Artifact": 99},
        {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "label_field": "trial_type",
            "time_field": "onset",
            "duration_field": "duration",
            "duration_stats": {
                "numeric_count": 288,
                "row_count": 288,
                "min": 0.5,
                "max": 1.25,
            },
            "placement_event_count": 288,
            "unknown_duration_count": 0,
            "class_map": {"left": "Left hand", "right": "Right hand"},
        },
    )


def _internal_event_epoch_data() -> _EpochData:
    return _EpochData(
        {"769": 769, "770": 770, "771": 771, "772": 772, "1023": 1023},
        {
            "source": "Labels inside EEG files",
            "placement_method": "internal_events",
            "class_map": {
                "769": "769",
                "770": "770",
                "771": "771",
                "772": "772",
            },
        },
    )


def _available_space_epoch_data() -> _EpochData:
    return _internal_event_data(6)


def _many_event_epoch_data() -> _EpochData:
    return _internal_event_data(16)


def _internal_event_data(event_count: int) -> _EpochData:
    event_ids = {f"event_{index:02d}": index + 1 for index in range(event_count)}
    return _EpochData(
        event_ids,
        {
            "source": "Labels inside EEG files",
            "placement_method": "internal_events",
            "class_map": {
                name: name for name in list(event_ids)[: min(event_count, 4)]
            },
        },
    )


def _epoch_handoff(data: _EpochData) -> dict[str, Any]:
    placement_method = str(data.hint.get("placement_method") or "")
    source = str(data.hint.get("source") or "").casefold()
    label_source = "bids_events" if "bids" in source else "internal_events"
    selected_events = [str(value) for value in data.hint.get("class_map", {}).values()]
    return {
        "ready": True,
        "supervised_ready": True,
        "label_source": label_source,
        "placement_modes": [placement_method],
        "default_epoch_events": selected_events,
        "selected_event_names": selected_events,
        "supervised_blocker_codes": [],
        "supervised_blockers": [],
    }


def _settle_layout(
    app: QApplication,
    widget: QWidget,
    *,
    timeout_ms: int = 1000,
) -> None:
    """Wait for stable widget geometry without a fixed sleep."""
    widget.show()
    elapsed = QElapsedTimer()
    elapsed.start()
    stable_frames = 0
    previous: tuple[int, ...] | None = None
    while elapsed.elapsed() < timeout_ms and stable_frames < 3:
        layout = widget.layout()
        if layout is not None:
            layout.activate()
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
        widget.repaint()
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
        current = (
            widget.x(),
            widget.y(),
            widget.width(),
            widget.height(),
            int(widget.isVisible()),
        )
        stable_frames = stable_frames + 1 if current == previous else 0
        previous = current
    if stable_frames < 3:
        raise RuntimeError("Epoch dialog geometry did not settle before capture.")


def _capture(widget: QWidget, output_path: Path) -> dict[str, Any]:
    pixmap = widget.grab()
    if pixmap.isNull():
        raise RuntimeError(f"Could not grab {output_path}.")
    if not pixmap.save(str(output_path)):
        raise RuntimeError(f"Could not save {output_path}.")
    if _is_nearly_black(output_path):
        raise RuntimeError(f"Screenshot is nearly black: {output_path}.")
    with Image.open(output_path) as image:
        width, height = image.size
    return {
        "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "width": width,
        "height": height,
        "byte_size": output_path.stat().st_size,
    }


def _semantic_evidence(
    dialog: EpochingDialog,
    *,
    expected_baseline_enabled: bool,
    invalid_state: str | None,
) -> dict[str, Any]:
    if (
        dialog.baseline_check is None
        or dialog.baseline_help_label is None
        or dialog.baseline_content is None
        or dialog.baseline_error_label is None
        or dialog.warning_label is None
        or dialog.create_button is None
    ):
        raise RuntimeError("Epoch dialog semantic controls are incomplete.")
    baseline_error_visible = dialog.baseline_error_label.isVisibleTo(dialog)
    window_warning_visible = dialog.warning_label.isVisibleTo(dialog)
    invalid = invalid_state is not None
    expected_error_visible = (
        baseline_error_visible
        if invalid_state == "baseline-order"
        else window_warning_visible
    )
    checks: dict[str, Any] = {
        "baseline_enabled": dialog.baseline_check.isChecked(),
        "baseline_fields_enabled": dialog.baseline_content.isEnabled(),
        "baseline_help_conditional": dialog.baseline_help_label.text().startswith(
            "When enabled,"
        ),
        "create_enabled": dialog.create_button.isEnabled(),
        "invalid": invalid,
        "invalid_state": invalid_state or "",
        "baseline_error_visible": baseline_error_visible,
        "baseline_error": dialog.baseline_error_label.text(),
        "window_warning_visible": window_warning_visible,
        "window_warning": dialog.warning_label.text(),
    }
    checks["passed"] = bool(
        checks["baseline_enabled"] is expected_baseline_enabled
        and checks["baseline_fields_enabled"] is expected_baseline_enabled
        and checks["baseline_help_conditional"]
        and (not invalid or (not checks["create_enabled"] and expected_error_visible))
    )
    return checks


def _baseline_surface_evidence(
    dialog: EpochingDialog,
    screenshot: Path,
) -> dict[str, Any]:
    if (
        dialog.baseline_group is None
        or dialog.baseline_content is None
        or dialog.baseline_help_label is None
        or dialog.baseline_min_label is None
        or dialog.baseline_max_label is None
        or dialog.b_min_spin is None
        or dialog.b_max_spin is None
        or dialog.baseline_check is None
    ):
        raise RuntimeError("Epoch baseline surface controls are incomplete.")
    baseline_rect = _widget_rect_in(dialog, dialog.baseline_group)
    with Image.open(screenshot) as source:
        image = source.convert("RGB")
        scale_x = image.width / max(dialog.width(), 1)
        scale_y = image.height / max(dialog.height(), 1)
        bounds = (
            round(baseline_rect.left() * scale_x),
            round(baseline_rect.top() * scale_y),
            round((baseline_rect.right() + 1) * scale_x),
            round((baseline_rect.bottom() + 1) * scale_y),
        )
        region = image.crop(bounds)
        pixels = list(region.get_flattened_data())
    if not pixels:
        raise RuntimeError("Epoch baseline surface capture is empty.")
    dominant_color, dominant_count = Counter(pixels).most_common(1)[0]
    near_black_count = sum(max(pixel) < 16 for pixel in pixels)
    expected_color = (34, 36, 38) if dialog.baseline_check.isChecked() else (32, 33, 36)
    color_distance = max(
        abs(actual - expected)
        for actual, expected in zip(dominant_color, expected_color, strict=True)
    )
    labels = (
        dialog.baseline_help_label,
        dialog.baseline_min_label,
        dialog.baseline_max_label,
    )
    labels_not_clipped = all(_label_text_not_clipped(label) for label in labels)
    controls = (*labels, dialog.b_min_spin, dialog.b_max_spin)
    controls_visible = all(control.isVisibleTo(dialog) for control in controls)
    controls_contained = all(
        baseline_rect.contains(_widget_rect_in(dialog, control)) for control in controls
    )
    near_black_fraction = near_black_count / len(pixels)
    return {
        "passed": bool(
            color_distance <= 6
            and near_black_fraction < 0.01
            and labels_not_clipped
            and controls_visible
            and controls_contained
        ),
        "enabled": dialog.baseline_check.isChecked(),
        "bounds": list(bounds),
        "dominant_color": list(dominant_color),
        "dominant_color_fraction": dominant_count / len(pixels),
        "expected_surface_color": list(expected_color),
        "surface_color_distance": color_distance,
        "near_black_fraction": near_black_fraction,
        "labels_not_clipped": labels_not_clipped,
        "controls_visible": controls_visible,
        "controls_contained": controls_contained,
    }


def _label_text_not_clipped(label: Any) -> bool:
    required_height = (
        label.heightForWidth(label.width())
        if label.wordWrap()
        else label.fontMetrics().lineSpacing()
    )
    return required_height <= label.contentsRect().height()


def _geometry_evidence(
    dialog: EpochingDialog,
    *,
    expected_vertical_scroll: bool = False,
) -> dict[str, Any]:
    scroll = dialog.findChild(QScrollArea, "EpochDialogContentScroll")
    cancel = dialog.findChild(QPushButton, "EpochSecondaryButton")
    create = dialog.create_button
    if scroll is None or cancel is None or create is None:
        raise RuntimeError("Epoch dialog geometry controls are incomplete.")
    dialog_rect = dialog.rect()
    scroll_rect = _widget_rect_in(dialog, scroll)
    cancel_rect = _widget_rect_in(dialog, cancel)
    create_rect = _widget_rect_in(dialog, create)
    controls_contained = all(
        dialog_rect.contains(rect) for rect in (scroll_rect, cancel_rect, create_rect)
    )
    footer_below_content = min(cancel_rect.top(), create_rect.top()) > scroll_rect.top()
    footer_visible = cancel.isVisibleTo(dialog) and create.isVisibleTo(dialog)
    horizontal_scroll_hidden = not scroll.horizontalScrollBar().isVisibleTo(dialog)
    vertical_scroll_max = scroll.verticalScrollBar().maximum()
    vertical_scroll_matches = (vertical_scroll_max > 0) is expected_vertical_scroll
    screen = dialog.screen()
    available_height = screen.availableGeometry().height() if screen is not None else 0
    safe_max_height = max(available_height - 48, 0)
    return {
        "passed": bool(
            controls_contained
            and footer_below_content
            and footer_visible
            and horizontal_scroll_hidden
            and vertical_scroll_matches
        ),
        "dialog": _rect_payload(dialog_rect),
        "content_scroll": _rect_payload(scroll_rect),
        "cancel_button": _rect_payload(cancel_rect),
        "create_button": _rect_payload(create_rect),
        "controls_contained": controls_contained,
        "footer_below_content": footer_below_content,
        "footer_visible": footer_visible,
        "horizontal_scroll_hidden": horizontal_scroll_hidden,
        "expected_vertical_scroll": expected_vertical_scroll,
        "vertical_scroll_matches": vertical_scroll_matches,
        "vertical_scroll_max": vertical_scroll_max,
        "content_fully_expanded": vertical_scroll_max == 0,
        "available_height": available_height,
        "safe_max_height": safe_max_height,
        "unused_safe_height": max(safe_max_height - dialog.height(), 0),
    }


def _dpi_evidence(widget: QWidget) -> dict[str, float]:
    screen = widget.screen()
    return {
        "device_pixel_ratio": float(widget.devicePixelRatioF()),
        "logical_dpi_x": float(screen.logicalDotsPerInchX() if screen else 0.0),
        "logical_dpi_y": float(screen.logicalDotsPerInchY() if screen else 0.0),
    }


def _widget_rect_in(ancestor: QWidget, widget: QWidget) -> QRect:
    return QRect(widget.mapTo(ancestor, QPoint(0, 0)), widget.size())


def _rect_payload(rect: QRect) -> list[int]:
    return [rect.x(), rect.y(), rect.width(), rect.height()]


def _write_evidence_manifest(
    *,
    output_dir: Path,
    source_identity_at_start: dict[str, Any],
    source_identity_at_end: dict[str, Any],
    captures: list[dict[str, Any]],
    generated_at: datetime,
    qt_platform: str,
) -> None:
    start_digest = str(source_identity_at_start.get("source_digest") or "")
    end_digest = str(source_identity_at_end.get("source_digest") or "")
    if not start_digest or start_digest != end_digest:
        raise RuntimeError("Product source changed during epoch dialog capture.")
    required_identity = (
        "branch",
        "commit_sha",
        "head_tree_sha",
        "dirty_digest",
        "source_content_digest",
    )
    missing = [
        field for field in required_identity if not source_identity_at_end.get(field)
    ]
    if missing:
        raise RuntimeError(f"Epoch dialog source identity is missing: {missing}.")
    if not qt_platform:
        raise RuntimeError("Epoch dialog capture has no Qt platform identity.")
    payload = {
        "schema_version": 1,
        "artifact_type": "xbrainlab.epoching_dialog",
        "generator": "scripts/dev/capture_epoching_dialog.py",
        "generated_at": generated_at.isoformat(),
        "qt_platform": qt_platform,
        "source_capture": {
            "branch": source_identity_at_end["branch"],
            "commit_sha": source_identity_at_end["commit_sha"],
            "head_tree_sha": source_identity_at_end["head_tree_sha"],
            "dirty": bool(source_identity_at_end.get("dirty")),
            "dirty_digest": source_identity_at_end["dirty_digest"],
            "source_content_digest": source_identity_at_end["source_content_digest"],
            "source_digest_at_start": start_digest,
            "source_digest_at_end": end_digest,
        },
        "source_identity_at_start": source_identity_at_start,
        "source_identity_at_end": source_identity_at_end,
        "source_identity": source_identity_at_end,
        "captures": captures,
        "passed": bool(captures)
        and all(
            item.get("geometry_checks", {}).get("passed")
            and item.get("semantic_checks", {}).get("passed")
            and item.get("baseline_surface", {}).get("passed")
            for item in captures
        ),
    }
    temporary = output_dir / f".{EVIDENCE_FILENAME}.tmp"
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output_dir / EVIDENCE_FILENAME)


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


if __name__ == "__main__":
    raise SystemExit(main())
