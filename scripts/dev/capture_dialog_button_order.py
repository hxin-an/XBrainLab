#!/usr/bin/env python3
"""Capture standard and narrow contact sheets for standard dialog action order."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import torch
from PIL import Image, ImageDraw
from PyQt6.QtCore import QBuffer, QIODevice, QPoint
from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QWidget

from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
    inspect_screenshot_artifact,
)
from XBrainLab.ui.dialogs.dataset.bids_subject_selection_dialog import (
    BidsSubjectSelectionDialog,
)
from XBrainLab.ui.dialogs.dataset.channel_selection_dialog import (
    ChannelSelectionDialog,
)
from XBrainLab.ui.dialogs.dataset.event_filter_dialog import EventFilterDialog
from XBrainLab.ui.dialogs.dataset.import_label_dialog import ImportLabelDialog
from XBrainLab.ui.dialogs.dataset.label_mapping_dialog import LabelMappingDialog
from XBrainLab.ui.dialogs.dataset.manual_split_dialog import ManualSplitDialog
from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog
from XBrainLab.ui.dialogs.preprocess.filtering_dialog import FilteringDialog
from XBrainLab.ui.dialogs.preprocess.normalize_dialog import NormalizeDialog
from XBrainLab.ui.dialogs.preprocess.rereference_dialog import RereferenceDialog
from XBrainLab.ui.dialogs.preprocess.resampling_dialog import ResampleDialog
from XBrainLab.ui.dialogs.training.device_setting_dialog import DeviceSettingDialog
from XBrainLab.ui.dialogs.training.optimizer_setting_dialog import (
    OptimizerSettingDialog,
)
from XBrainLab.ui.dialogs.training.training_setting_dialog import TrainingSettingDialog
from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import PickMontageDialog
from XBrainLab.ui.dialogs.visualization.saliency_setting_dialog import (
    SaliencySettingDialog,
)
from XBrainLab.ui.panels.training.test_only_setting import TestOnlySettingWindow

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = (
    ROOT / "build" / "dev-artifacts" / "manual-ui-saliency-followup-v3" / "dialog-order"
)
_TILE_WIDTH = 540
_TILE_HEIGHT = 138
_COLUMNS = 2
EVIDENCE_FILENAME = "dialog-order-evidence.json"
_VARIANTS = ("standard", "narrow")


def _device_dialog() -> QWidget:
    with patch(
        "XBrainLab.ui.dialogs.training.device_setting_dialog.get_device_count",
        return_value=0,
    ):
        return DeviceSettingDialog(None)


def _optimizer_dialog() -> QWidget:
    with patch(
        "XBrainLab.ui.dialogs.training.optimizer_setting_dialog.get_optimizer_classes",
        return_value={},
    ):
        return OptimizerSettingDialog(None)


def _training_dialog() -> QWidget:
    controller = MagicMock()
    controller.get_training_option.return_value = None
    with patch(
        "XBrainLab.ui.dialogs.training.training_setting_dialog.get_optimizer_classes",
        return_value={"Adam": torch.optim.Adam},
    ):
        return TrainingSettingDialog(None, controller)


def _montage_dialog() -> QWidget:
    with (
        patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_builtin_montages",
            return_value=["standard_1020"],
        ),
        patch.object(PickMontageDialog, "on_montage_select", return_value=None),
    ):
        return PickMontageDialog(None, ["C3", "C4"])


def _bids_dialog() -> QWidget:
    return BidsSubjectSelectionDialog(
        None,
        catalog={
            "root": "/synthetic/bids",
            "subject_count": 1,
            "eeg_file_count": 1,
            "subjects": [
                {
                    "subject": "01",
                    "label": "sub-01",
                    "eeg_file_count": 1,
                    "sessions": [],
                    "tasks": ["mi"],
                    "runs": ["1"],
                }
            ],
            "warnings": [],
        },
    )


def _epoch_dialog() -> QWidget:
    return EpochingDialog(
        None,
        epoch_context={
            "available_events": [{"name": "left", "count": 2}],
            "has_import_hint": False,
        },
    )


def _dialog_factories() -> list[tuple[str, Callable[[], QWidget]]]:
    return [
        ("Device Setting", _device_dialog),
        ("Optimizer Setting", _optimizer_dialog),
        ("Training Setting", _training_dialog),
        ("Saliency Setting", lambda: SaliencySettingDialog(None)),
        ("Set Montage", _montage_dialog),
        ("Filtering", lambda: FilteringDialog(None, sampling_rate_hz=250.0)),
        ("Resample", lambda: ResampleDialog(None)),
        ("Re-reference", lambda: RereferenceDialog(None, ["C3", "C4"])),
        ("Normalize", lambda: NormalizeDialog(None)),
        ("Time Epoching (single OK)", _epoch_dialog),
        ("Event Filter", lambda: EventFilterDialog(None, ["left", "right"])),
        ("Import Labels", lambda: ImportLabelDialog(None, [])),
        (
            "Label Mapping",
            lambda: LabelMappingDialog(None, ["data.edf"], ["labels.csv"]),
        ),
        ("Manual Split", lambda: ManualSplitDialog(None, ["subject-01"])),
        ("BIDS Subject Selection", _bids_dialog),
        ("Channel Selection", lambda: ChannelSelectionDialog(None, ["C3", "C4"])),
        ("Test Only Setting (unrouted)", lambda: TestOnlySettingWindow(None)),
    ]


def _grab_dialog(dialog: QWidget) -> Image.Image:
    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("Could not open screenshot buffer.")
    if not dialog.grab().save(buffer, "PNG"):
        raise RuntimeError("Could not encode dialog screenshot.")
    return Image.open(BytesIO(bytes(buffer.data()))).convert("RGB")


def _point_in_dialog(widget: QWidget, point: QPoint, dialog: QWidget) -> QPoint:
    return widget.mapTo(dialog, point)


def _capture_variant(
    app: QApplication,
    *,
    variant: str,
) -> tuple[Image.Image, list[dict[str, object]]]:
    tiles: list[tuple[str, Image.Image]] = []
    evidence: list[dict[str, object]] = []
    for title, factory in _dialog_factories():
        dialog = factory()
        try:
            if variant == "narrow":
                target_width = max(dialog.minimumSizeHint().width(), 420)
                dialog.resize(target_width, dialog.height())
            dialog.show()
            app.processEvents()

            button_box = next(
                (
                    candidate
                    for candidate in dialog.findChildren(QDialogButtonBox)
                    if candidate.button(QDialogButtonBox.StandardButton.Ok) is not None
                ),
                None,
            )
            if button_box is None:
                raise RuntimeError(f"{title} has no standard primary button box.")
            primary = button_box.button(QDialogButtonBox.StandardButton.Ok)
            if primary is None:
                raise RuntimeError(f"{title} has no standard primary button.")
            cancel = button_box.button(QDialogButtonBox.StandardButton.Cancel)

            image = _grab_dialog(dialog)
            box_top = _point_in_dialog(button_box, QPoint(0, 0), dialog).y()
            crop_top = max(box_top - 22, 0)
            crop = image.crop((0, crop_top, image.width, image.height))
            crop.thumbnail((_TILE_WIDTH - 24, _TILE_HEIGHT - 42))
            tiles.append((title, crop))

            primary_left = _point_in_dialog(primary, QPoint(0, 0), dialog).x()
            primary_right = _point_in_dialog(
                primary,
                primary.rect().bottomRight(),
                dialog,
            ).x()
            cancel_right = None
            cancel_left = None
            order = "single-primary"
            if cancel is not None:
                cancel_left = _point_in_dialog(cancel, QPoint(0, 0), dialog).x()
                cancel_right = _point_in_dialog(
                    cancel,
                    cancel.rect().bottomRight(),
                    dialog,
                ).x()
                order = (
                    "cancel-primary"
                    if cancel_right < primary_left
                    else "primary-cancel"
                )
            evidence.append(
                {
                    "dialog": title,
                    "variant": variant,
                    "dialog_width": dialog.width(),
                    "layout_direction": button_box.layoutDirection().name,
                    "primary_text": primary.text(),
                    "primary_enabled": primary.isEnabled(),
                    "primary_left": primary_left,
                    "primary_right": primary_right,
                    "cancel_left": cancel_left,
                    "cancel_right": cancel_right,
                    "order": order,
                }
            )
        finally:
            dialog.close()
            dialog.deleteLater()
            app.processEvents()

    rows = (len(tiles) + _COLUMNS - 1) // _COLUMNS
    sheet = Image.new(
        "RGB",
        (_TILE_WIDTH * _COLUMNS, _TILE_HEIGHT * rows),
        "#111820",
    )
    draw = ImageDraw.Draw(sheet)
    for index, (title, crop) in enumerate(tiles):
        x = (index % _COLUMNS) * _TILE_WIDTH
        y = (index // _COLUMNS) * _TILE_HEIGHT
        draw.rectangle(
            (x + 4, y + 4, x + _TILE_WIDTH - 4, y + _TILE_HEIGHT - 4),
            outline="#53687a",
            width=1,
        )
        draw.text((x + 12, y + 10), title, fill="#eef4fb")
        sheet.paste(crop, (x + _TILE_WIDTH - crop.width - 12, y + 34))
    return sheet, evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = args.output_dir / EVIDENCE_FILENAME
    evidence_path.unlink(missing_ok=True)

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    source_identity_at_start = collect_source_identity(ROOT, refresh=True)
    all_evidence: list[dict[str, object]] = []
    screenshots: dict[str, dict[str, Any]] = {}
    for variant in _VARIANTS:
        sheet, evidence = _capture_variant(app, variant=variant)
        filename = f"dialog-order-{variant}.png"
        screenshot_path = args.output_dir / filename
        sheet.save(screenshot_path)
        screenshot = inspect_screenshot_artifact(screenshot_path)
        screenshot["path"] = filename
        screenshots[variant] = screenshot
        all_evidence.extend(evidence)

    expected_observations = {
        (title, variant)
        for title, _factory in _dialog_factories()
        for variant in _VARIANTS
    }
    observed = {
        (str(row.get("dialog")), str(row.get("variant"))) for row in all_evidence
    }
    failures = [
        row
        for row in all_evidence
        if row["layout_direction"] != "LeftToRight"
        or row["order"] not in {"cancel-primary", "single-primary"}
    ]
    if observed != expected_observations:
        failures.append(
            {
                "reason": "capture_matrix_incomplete",
                "missing": sorted(expected_observations - observed),
                "unexpected": sorted(observed - expected_observations),
            }
        )
    unreadable_screenshots = [
        variant
        for variant, screenshot in screenshots.items()
        if not screenshot.get("readable") or not screenshot.get("sha256")
    ]
    if unreadable_screenshots:
        failures.append(
            {
                "reason": "screenshot_unreadable",
                "variants": unreadable_screenshots,
            }
        )

    source_identity_at_end = collect_source_identity(ROOT, refresh=True)
    source_capture = _source_capture_payload(
        source_identity_at_start,
        source_identity_at_end,
    )
    evidence_payload = {
        "schema_version": 1,
        "artifact_type": "xbrainlab.dialog_button_order",
        "generator": "scripts/dev/capture_dialog_button_order.py",
        "contract": "physical LTR Cancel-left / primary-rightmost",
        "capture_environment": {
            "qt_platform": app.platformName(),
            "qt_style": "Fusion",
        },
        "source_capture": source_capture,
        "source_identity_at_start": source_identity_at_start,
        "source_identity_at_end": source_identity_at_end,
        "screenshots": screenshots,
        "failures": failures,
        "observations": all_evidence,
        "passed": not failures,
    }
    temporary = args.output_dir / f".{EVIDENCE_FILENAME}.tmp"
    temporary.write_text(
        json.dumps(evidence_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(evidence_path)
    if failures:
        raise RuntimeError(f"Dialog order evidence failed: {failures[0]}")
    return 0


def _source_capture_payload(
    start: dict[str, Any],
    end: dict[str, Any],
) -> dict[str, object]:
    required = (
        "branch",
        "commit_sha",
        "head_tree_sha",
        "dirty_digest",
        "source_content_digest",
        "source_digest",
        "untracked_source_count",
    )
    for phase, identity in (("start", start), ("end", end)):
        missing = [field for field in required if identity.get(field) in {None, ""}]
        if missing or identity.get("error"):
            detail = identity.get("error") or f"missing fields: {missing}"
            raise RuntimeError(
                f"Dialog capture source identity at {phase} failed: {detail}"
            )
    if start["source_digest"] != end["source_digest"]:
        raise RuntimeError("Product source changed during dialog capture.")
    return {
        "branch_at_start": start["branch"],
        "branch_at_end": end["branch"],
        "commit_sha_at_start": start["commit_sha"],
        "commit_sha_at_end": end["commit_sha"],
        "head_tree_sha_at_start": start["head_tree_sha"],
        "head_tree_sha_at_end": end["head_tree_sha"],
        "dirty_at_start": bool(start.get("dirty")),
        "dirty_at_end": bool(end.get("dirty")),
        "dirty_digest_at_start": start["dirty_digest"],
        "dirty_digest_at_end": end["dirty_digest"],
        "source_content_digest_at_start": start["source_content_digest"],
        "source_content_digest_at_end": end["source_content_digest"],
        "source_digest_at_start": start["source_digest"],
        "source_digest_at_end": end["source_digest"],
        "untracked_source_count_at_start": start["untracked_source_count"],
        "untracked_source_count_at_end": end["untracked_source_count"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
