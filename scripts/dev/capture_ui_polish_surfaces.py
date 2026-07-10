#!/usr/bin/env python3
"""Capture focused UI surfaces that are not covered by the wizard screenshots."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image
from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication, QTreeWidgetItem, QWidget

from XBrainLab.backend.dataset import (
    DataSplittingConfig,
    SplitByType,
    TrainingType,
    ValSplitByType,
)
from XBrainLab.ui.chat.message_bubble import MessageBubble
from XBrainLab.ui.chat.panel import ChatPanel
from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import DataSplittingDialog
from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
    DataSplitterHolder,
    DataSplittingPreviewDialog,
)
from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog
from XBrainLab.ui.dialogs.preprocess.rereference_dialog import RereferenceDialog
from XBrainLab.ui.dialogs.training.model_selection_dialog import ModelSelectionDialog
from XBrainLab.ui.dialogs.training.training_setting_dialog import TrainingSettingDialog
from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import PickMontageDialog
from XBrainLab.ui.dialogs.visualization.saliency_setting_dialog import (
    SaliencySettingDialog,
)
from XBrainLab.ui.panels.evaluation.metrics_table import MetricsTableWidget
from XBrainLab.ui.panels.evaluation.panel import EvaluationPanel

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "artifacts" / "ui" / "app-polish"


def main(argv: list[str] | None = None) -> int:
    captures = _capture_factories()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        action="append",
        choices=[filename for filename, _factory in captures],
        help="Capture only this filename; repeat for multiple surfaces.",
    )
    args = parser.parse_args(argv)
    selected = set(args.only or [filename for filename, _factory in captures])

    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication(sys.argv)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, factory in captures:
        if filename not in selected:
            continue
        widget = factory()
        widget.show()
        app.processEvents()
        widget.repaint()
        app.processEvents()
        _assert_capture_geometry(filename, widget)
        _capture(widget, OUTPUT_DIR / filename)
        widget.close()
    _write_readme()
    return 0


def _model_selection_dialog() -> QWidget:
    dialog = ModelSelectionDialog(None, MagicMock())
    if dialog.model_combo is not None:
        index = dialog.model_combo.findText("EEGNet")
        if index >= 0:
            dialog.model_combo.setCurrentIndex(index)
    dialog.adjustSize()
    dialog.resize(QSize(680, max(dialog.sizeHint().height(), 440)))
    return dialog


def _rereference_dialog() -> QWidget:
    data = MagicMock()
    data.get_mne.return_value.ch_names = ["Fz", "C3", "Cz", "C4", "Pz"]
    dialog = RereferenceDialog(None, [data])
    dialog.resize(QSize(460, 340))
    return dialog


def _training_setting_dialog() -> QWidget:
    controller = MagicMock()
    controller.get_training_option.return_value = None
    with (
        patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog.get_optimizer_classes",
            return_value={"Adam": MagicMock(__name__="Adam")},
        ),
        patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog.get_device_count",
            return_value=0,
        ),
    ):
        dialog = TrainingSettingDialog(None, controller)
    dialog.resize(QSize(560, 420))
    return dialog


def _epoching_dialog() -> QWidget:
    data = MagicMock()
    data.get_event_list.return_value = (
        None,
        {"768": 1, "769": 2, "770": 3, "771": 4, "772": 5},
    )
    dialog = EpochingDialog(
        None,
        [data],
        epoch_context={
            "available_events": [
                {"name": "769", "count": 72},
                {"name": "770", "count": 72},
                {"name": "771", "count": 72},
                {"name": "772", "count": 72},
            ],
            "recommended_events": ["769", "770", "771", "772"],
            "suggested_t_min": -0.2,
            "suggested_t_max": 1.0,
            "suggested_baseline": (-0.2, 0.0),
            "has_import_hint": True,
            "source": "labels inside EEG files",
            "placement_label": "Events inside EEG files",
            "window_evidence": "Suggested from the import label matching step.",
        },
    )
    dialog.resize(QSize(640, 740))
    return dialog


def _data_splitting_dialog() -> QWidget:
    controller = MagicMock()
    controller.get_epoch_data.return_value = object()
    controller.get_dataset_generator.return_value = None
    dialog = DataSplittingDialog(None, controller)
    dialog.resize(QSize(820, 470))
    return dialog


def _data_splitting_dialog_narrow() -> QWidget:
    dialog = _data_splitting_dialog()
    dialog.resize(QSize(752, 700))
    return dialog


def _data_splitting_preview_dialog() -> QWidget:
    epoch = MagicMock()
    epoch.subject_map = {"S01": [0, 1, 2], "S02": [3, 4, 5]}
    epoch.session_map = {"session": [0, 1, 2, 3, 4, 5]}
    epoch.label_map = {"left": 0, "right": 1}
    epoch.data = list(range(120))
    epoch.get_data_length.return_value = 120
    val_splitter = DataSplitterHolder(True, ValSplitByType.TRIAL)
    test_splitter = DataSplitterHolder(True, SplitByType.TRIAL)
    config = DataSplittingConfig(
        TrainingType.FULL,
        True,
        [val_splitter],
        [test_splitter],
    )
    with (
        patch(
            "XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog.DatasetGenerator"
        ),
        patch("threading.Thread"),
    ):
        dialog = DataSplittingPreviewDialog(
            None, "Data Splitting Step 2", epoch, config
        )
    if dialog.preview_debounce_timer is not None:
        dialog.preview_debounce_timer.stop()
    if dialog.timer is not None:
        dialog.timer.stop()
    dialog._interrupt_preview_worker(0.2)
    if dialog.tree is None:
        raise RuntimeError("Data splitting preview tree was not initialized.")
    dialog.tree.clear()
    for name, train, val, test in (
        ("Fold_0", 76, 20, 24),
        ("Fold_1", 76, 20, 24),
    ):
        item = QTreeWidgetItem(dialog.tree)
        item.setText(0, name)
        item.setText(1, str(train))
        item.setText(2, str(val))
        item.setText(3, str(test))
    dialog._clear_tree_current_item()
    dialog._resize_tree_to_rows()
    dialog.adjustSize()
    dialog.resize(QSize(980, dialog.sizeHint().height()))
    return dialog


def _assistant_ask_narrow() -> QWidget:
    panel = ChatPanel()
    panel.set_execution_mode("single")
    panel.resize(QSize(340, 650))
    return panel


def _assistant_workflow_narrow() -> QWidget:
    panel = ChatPanel()
    panel.set_execution_mode("multi")
    panel.resize(QSize(340, 650))
    panel.show()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    panel.append_message("user", "Prepare the data for training.")
    panel.append_message(
        "assistant",
        "I checked the workflow and need one decision before continuing.",
    )
    panel.set_workflow_status("Complete the open XBrainLab dialog")
    panel.show_notice("A settings dialog is open. Complete it to continue.")
    panel.set_processing_state(True)
    if app is not None:
        app.processEvents()
    return panel


def _saliency_setting_dialog() -> QWidget:
    dialog = SaliencySettingDialog(None, saliency_params=None)
    dialog.adjustSize()
    dialog.resize(dialog.sizeHint())
    return dialog


def _saliency_setting_single_method() -> QWidget:
    dialog = SaliencySettingDialog(None, saliency_params=None)
    for method, check in dialog.method_checks.items():
        check.setChecked(method == "SmoothGrad")
    dialog.adjustSize()
    dialog.resize(dialog.sizeHint())
    return dialog


def _saliency_setting_empty_state() -> QWidget:
    dialog = SaliencySettingDialog(None, saliency_params=None)
    for check in dialog.method_checks.values():
        check.setChecked(False)
    dialog.adjustSize()
    dialog.resize(dialog.sizeHint())
    return dialog


def _set_montage_dialog() -> QWidget:
    positions = {
        "Fz": (0.0, 0.8, 0.0),
        "C3": (-0.4, 0.0, 0.0),
        "Cz": (0.0, 0.0, 0.0),
        "C4": (0.4, 0.0, 0.0),
        "Pz": (0.0, -0.7, 0.0),
    }
    with (
        patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_builtin_montages",
            return_value=["standard_1020", "biosemi64"],
        ),
        patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_positions",
            return_value={"ch_pos": positions},
        ),
        patch(
            "XBrainLab.ui.dialogs.visualization.montage_picker_dialog.get_montage_channel_positions",
            return_value=positions,
        ),
    ):
        dialog = PickMontageDialog(None, ["Fz", "C3", "Cz", "C4", "Pz"])
    dialog.resize(QSize(760, 420))
    return dialog


def _evaluation_controls_panel() -> QWidget:
    controller = MagicMock()
    panel = EvaluationPanel(controller=controller, parent=None)
    panel.model_combo.blockSignals(True)
    panel.run_combo.blockSignals(True)
    panel.model_combo.addItem(
        "Fold 1: EEGNet with a deliberately long model label for overflow review",
        object(),
    )
    panel.run_combo.addItem("Repeat 1 (Finished, best validation accuracy)", object())
    panel.model_combo.blockSignals(False)
    panel.run_combo.blockSignals(False)
    panel.chk_percentage.blockSignals(True)
    panel.chk_percentage.setChecked(True)
    panel.chk_percentage.blockSignals(False)
    panel.plot_stack.setCurrentIndex(1)
    panel.no_data_label.setText("Evaluation controls layout review")
    panel.resize(QSize(900, 520))
    return panel


def _metrics_table() -> QWidget:
    table = MetricsTableWidget()
    table.resize(QSize(780, 210))
    table.update_data(
        {
            0: {
                "precision": 0.4762,
                "recall": 0.2326,
                "f1-score": 0.3125,
                "support": 43,
            },
            1: {
                "precision": 0.3788,
                "recall": 0.5814,
                "f1-score": 0.4587,
                "support": 43,
            },
            2: {
                "precision": 0.5429,
                "recall": 0.4419,
                "f1-score": 0.4872,
                "support": 43,
            },
            3: {
                "precision": 0.6600,
                "recall": 0.7674,
                "f1-score": 0.7097,
                "support": 43,
            },
            "macro_avg": {
                "precision": 0.5145,
                "recall": 0.5058,
                "f1-score": 0.4920,
                "support": 172,
            },
        }
    )
    return table


def _capture_factories() -> tuple[tuple[str, Callable[[], QWidget]], ...]:
    return (
        ("model-selection-dialog.png", _model_selection_dialog),
        ("training-setting-dialog.png", _training_setting_dialog),
        ("preprocess-rereference-dialog.png", _rereference_dialog),
        ("preprocess-epoching-dialog.png", _epoching_dialog),
        ("data-splitting-dialog.png", _data_splitting_dialog),
        ("data-splitting-dialog-narrow.png", _data_splitting_dialog_narrow),
        ("data-splitting-preview-dialog.png", _data_splitting_preview_dialog),
        ("assistant-ask-narrow.png", _assistant_ask_narrow),
        ("assistant-workflow-narrow.png", _assistant_workflow_narrow),
        ("saliency-setting-dialog.png", _saliency_setting_dialog),
        ("saliency-setting-single-method.png", _saliency_setting_single_method),
        ("saliency-setting-empty-state.png", _saliency_setting_empty_state),
        ("set-montage-dialog.png", _set_montage_dialog),
        ("evaluation-controls-panel.png", _evaluation_controls_panel),
        ("evaluation-metrics-table.png", _metrics_table),
    )


def _capture(widget: QWidget, output_path: Path) -> None:
    pixmap = widget.grab()
    if pixmap.isNull():
        raise RuntimeError(f"Could not grab {output_path}.")
    if not pixmap.save(str(output_path)):
        raise RuntimeError(f"Could not save {output_path}.")
    if _is_nearly_black(output_path):
        raise RuntimeError(f"Screenshot is nearly black: {output_path}.")


def _assert_capture_geometry(filename: str, widget: QWidget) -> None:
    if isinstance(widget, DataSplittingDialog):
        if widget.minimumSizeHint().width() > widget.width():
            raise RuntimeError(f"{filename} minimum width exceeds its captured width.")
        button = widget.btn_confirm
        if button is None or not button.isVisible():
            raise RuntimeError(f"{filename} does not show its Confirm button.")
        bottom_right = button.mapTo(widget, button.rect().bottomRight())
        if bottom_right.x() >= widget.width() or bottom_right.y() >= widget.height():
            raise RuntimeError(f"{filename} clips its Confirm button.")

    if isinstance(widget, DataSplittingPreviewDialog) and widget.tree is not None:
        last_row = widget.tree.topLevelItem(widget.tree.topLevelItemCount() - 1)
        if last_row is not None:
            row_rect = widget.tree.visualItemRect(last_row)
            unused_height = widget.tree.viewport().height() - row_rect.bottom()
            if unused_height > 12:
                raise RuntimeError(f"{filename} leaves an empty results viewport.")

    if isinstance(widget, ChatPanel):
        viewport = widget.scroll_area.viewport()
        for bubble in widget.findChildren(MessageBubble):
            if not bubble.isVisible():
                continue
            left = bubble.mapTo(viewport, bubble.rect().topLeft()).x()
            right = bubble.mapTo(viewport, bubble.rect().bottomRight()).x()
            if left < 0 or right >= viewport.width():
                raise RuntimeError(f"{filename} clips a conversation bubble.")


def _write_readme() -> None:
    (OUTPUT_DIR / "README.md").write_text(
        "# App Polish Screenshots\n\n"
        "status: generated focused UI review evidence\n"
        "generator: `scripts/dev/capture_ui_polish_surfaces.py`\n"
        "environment: PyQt offscreen capture\n"
        "supports: current visual state for assistant single-step/Workflow narrow "
        "surfaces, model selection, data splitting, and evaluation metrics "
        "table polish\n"
        "does_not_support: end-to-end training quality, human desktop "
        "acceptance, or long-running runtime behavior\n"
        "next_human_or_runtime_gate: open the same dialogs in the Windows "
        "desktop app during manual acceptance\n\n"
        "Focused current screenshots for manual review of surfaces that are not "
        "fully represented by the Data Import wizard artifacts. Regenerate the "
        "complete set with:\n\n"
        "```bash\n"
        "QT_QPA_PLATFORM=offscreen poetry run python "
        "scripts/dev/capture_ui_polish_surfaces.py\n"
        "```\n\n"
        "Regenerate only the narrow assistant evidence with:\n\n"
        "```bash\n"
        "QT_QPA_PLATFORM=offscreen poetry run python "
        "scripts/dev/capture_ui_polish_surfaces.py "
        "--only assistant-ask-narrow.png "
        "--only assistant-workflow-narrow.png\n"
        "```\n\n"
        "- `model-selection-dialog.png`\n"
        "- `training-setting-dialog.png`\n"
        "- `preprocess-rereference-dialog.png`\n"
        "- `preprocess-epoching-dialog.png`\n"
        "- `data-splitting-dialog.png` (752 x 470 scroll fallback)\n"
        "- `data-splitting-dialog-narrow.png` (752 x 700 full reflow)\n"
        "- `data-splitting-preview-dialog.png`\n"
        "- `assistant-ask-narrow.png` (340 x 650, current single-step mode)\n"
        "- `assistant-workflow-narrow.png` (340 x 650)\n"
        "- `saliency-setting-dialog.png`\n"
        "- `saliency-setting-single-method.png`\n"
        "- `saliency-setting-empty-state.png`\n"
        "- `set-montage-dialog.png`\n"
        "- `evaluation-controls-panel.png`\n"
        "- `evaluation-metrics-table.png`\n",
        encoding="utf-8",
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


if __name__ == "__main__":
    raise SystemExit(main())
