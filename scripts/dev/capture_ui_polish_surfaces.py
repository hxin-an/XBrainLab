#!/usr/bin/env python3
"""Capture focused UI surfaces that are not covered by the wizard screenshots."""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, TypeVar
from unittest.mock import MagicMock, patch

from PIL import Image, ImageStat
from PyQt6.QtCore import (
    QBuffer,
    QCoreApplication,
    QEvent,
    QIODevice,
    QPoint,
    QRect,
    QSize,
    Qt,
)
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QComboBox,
    QGroupBox,
    QLabel,
    QStyleOptionViewItem,
    QTableWidget,
    QWidget,
)

from scripts.dev.app_polish_capture_contract import (
    APP_POLISH_SURFACES,
    build_app_polish_evidence,
    load_app_polish_evidence,
    validate_app_polish_evidence,
    write_app_polish_evidence,
)
from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
)
from scripts.dev.human_like_walkthrough.readiness import (
    assert_consecutive_complete_frames,
    assert_region_has_no_unpainted_block,
    assert_region_matches_reference,
    frame_readiness_payload,
)
from XBrainLab.backend.application.dataset_split_preview import (
    DatasetSplitChoice,
    DatasetSplitContext,
    DatasetSplitPreviewPublication,
    DatasetSplitPreviewRequest,
    DatasetSplitPreviewRow,
)
from XBrainLab.backend.dataset import (
    DataSplittingConfig,
    SplitByType,
    TrainingType,
    ValSplitByType,
)
from XBrainLab.llm.agent.assistant_activity import (
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from XBrainLab.ui.chat.message_bubble import MessageBubble
from XBrainLab.ui.chat.panel import ChatPanel
from XBrainLab.ui.chat.presentation import present_assistant_activity
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
from XBrainLab.ui.panels.training.panel import TrainingPanel
from XBrainLab.ui.styles.stylesheets import Stylesheets

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "dev-artifacts" / "app-polish"
OUTPUT_DIR = DEFAULT_OUTPUT_DIR
INTERNAL_EPOCH_SCREENSHOT = "preprocess-epoching-internal-events-dialog.png"
BIDS_EPOCH_SCREENSHOT = "preprocess-epoching-bids-interval-duration-dialog.png"
_T = TypeVar("_T")


def _require_qt_value(value: _T | None, description: str) -> _T:
    if value is None:
        raise RuntimeError(f"{description} was not initialized.")
    return value


def main(argv: list[str] | None = None) -> int:
    captures = _capture_factories()
    capture_names = tuple(filename for filename, _factory in captures)
    if capture_names != APP_POLISH_SURFACES:
        raise RuntimeError(
            "App-polish capture factories do not match the canonical surface inventory."
        )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        action="append",
        choices=[filename for filename, _factory in captures],
        help="Capture only this filename; repeat for multiple surfaces.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for screenshots and the generated review README.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the existing complete evidence manifest without capturing.",
    )
    args = parser.parse_args(argv)
    output_dir = args.output_dir.expanduser().resolve()
    if args.validate_only:
        if args.only:
            parser.error("--validate-only cannot be combined with --only")
        payload = load_app_polish_evidence(output_dir)
        ok, reason = validate_app_polish_evidence(payload, output_dir=output_dir)
        if not ok:
            print(f"App-polish evidence rejected: {reason}", file=sys.stderr)
            return 1
        print(f"Validated {output_dir}")
        return 0

    expected_surfaces = list(APP_POLISH_SURFACES)
    selected_set = set(args.only or expected_surfaces)
    selected_surfaces = [
        filename for filename in expected_surfaces if filename in selected_set
    ]
    if args.only and output_dir == DEFAULT_OUTPUT_DIR:
        parser.error("--only requires a non-canonical --output-dir")
    surface_contracts: dict[str, dict[str, Any]] = {}
    capture_started_at = datetime.now(UTC)
    source_identity_at_start = collect_source_identity(ROOT, refresh=True)

    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication(sys.argv)
    _apply_capture_application_theme(app)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{output_dir.name}-capture-",
        dir=output_dir.parent,
    ) as staging_name:
        staging_dir = Path(staging_name)
        for filename, factory in captures:
            if filename not in selected_set:
                continue
            widget = factory()
            try:
                widget.show()
                for _ in range(3):
                    app.processEvents()
                    widget.repaint()
                    time.sleep(0.015)
                if isinstance(widget, ChatPanel):
                    _settle_chat_panel_capture(app, widget)
                _assert_capture_geometry(filename, widget)
                frame_readiness = _capture(widget, staging_dir / filename)
                surface_contracts[filename] = _surface_contract(
                    filename,
                    widget,
                    frame_readiness=frame_readiness,
                )
            finally:
                widget.close()
                widget.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                app.processEvents()
        _write_readme(staging_dir)
        source_identity_at_end = collect_source_identity(ROOT, refresh=True)
        if source_identity_at_start.get("source_digest") != source_identity_at_end.get(
            "source_digest"
        ):
            raise RuntimeError(
                "Product source changed during app-polish capture; discard this run."
            )
        evidence = build_app_polish_evidence(
            staging_dir,
            expected_surfaces=expected_surfaces,
            selected_surfaces=selected_surfaces,
            surface_contracts=surface_contracts,
            capture_started_at=capture_started_at,
            source_identity=source_identity_at_end,
            source_identity_at_start=source_identity_at_start,
            qt_platform=QApplication.platformName(),
        )
        ok, reason = validate_app_polish_evidence(
            evidence,
            output_dir=staging_dir,
            require_complete=not bool(args.only),
        )
        if not ok:
            raise RuntimeError(f"App-polish evidence contract failed: {reason}")
        write_app_polish_evidence(staging_dir, evidence)
        _publish_capture(
            staging_dir,
            output_dir,
            selected_surfaces=selected_surfaces,
        )
    return 0


def _apply_capture_application_theme(app: QApplication) -> None:
    """Mirror run.py's Fusion style and MainWindow descendant stylesheet."""
    app.setStyle("Fusion")
    app.setProperty("xbrainlab_capture_qt_style", "Fusion")
    app.setStyleSheet(Stylesheets.MAIN_WINDOW)


def _publish_capture(
    staging_dir: Path,
    output_dir: Path,
    *,
    selected_surfaces: list[str],
) -> None:
    """Atomically replace accepted screenshots, then publish the manifest last."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in selected_surfaces:
        (staging_dir / filename).replace(output_dir / filename)
    (staging_dir / "README.md").replace(output_dir / "README.md")
    (staging_dir / "app-polish-evidence.json").replace(
        output_dir / "app-polish-evidence.json"
    )


def _settle_chat_panel_capture(app: QApplication, panel: ChatPanel) -> None:
    """Flush deferred ChatPanel layout and child painting before capture."""
    containers = (panel, panel.chat_content_widget, panel.control_panel)
    for _ in range(4):
        for container in containers:
            layout = container.layout()
            if layout is not None:
                layout.activate()
        panel.repaint()
        app.processEvents()
        for child in panel.findChildren(QWidget):
            child.updateGeometry()
            child.repaint()
        app.processEvents()
        time.sleep(0.01)


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
    dialog = RereferenceDialog(None, ["Fz", "C3", "Cz", "C4", "Pz"])
    dialog.adjustSize()
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


def _epoching_internal_events_dialog() -> EpochingDialog:
    dialog = EpochingDialog(
        None,
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
            "placement_method": "internal_events",
            "placement_label": "Events inside EEG files",
            "window_mode": "event_locked",
            "window_evidence": "Suggested from the import label matching step.",
        },
    )
    dialog.resize(QSize(640, 740))
    return dialog


def _epoching_bids_interval_duration_dialog() -> EpochingDialog:
    dialog = EpochingDialog(
        None,
        epoch_context={
            "available_events": [
                {"name": "left", "count": 36},
                {"name": "right", "count": 36},
            ],
            "recommended_events": ["left", "right"],
            "suggested_t_min": 0.0,
            "suggested_t_max": 1.5,
            "suggested_baseline": None,
            "has_import_hint": True,
            "source": "BIDS events",
            "placement_method": "interval",
            "placement_label": "Label interval",
            "label_field": "trial_type",
            "time_field": "onset",
            "duration_field": "duration",
            "window_mode": "duration",
            "window_evidence": (
                "Uses the largest reviewed BIDS duration from Match Labels."
            ),
            "epoch_handoff": {
                "ready": True,
                "label_source": "bids_events",
                "placement_modes": ["interval"],
                "default_epoch_events": ["left", "right"],
                "supervised_blockers": [],
            },
        },
    )
    dialog.resize(QSize(700, 780))
    return dialog


def _epoching_dialog() -> EpochingDialog:
    """Compatibility alias for the internal-event capture fixture."""
    return _epoching_internal_events_dialog()


def _data_splitting_dialog() -> QWidget:
    dialog = DataSplittingDialog(
        None,
        split_context=_data_split_capture_context(),
        publication_generation=1,
        preview_provider=_data_split_capture_provider,
        preview_canceller=lambda _request_id: True,
    )
    dialog.resize(QSize(820, 470))
    return dialog


def _data_splitting_dialog_narrow() -> QWidget:
    dialog = _data_splitting_dialog()
    dialog.resize(QSize(752, 700))
    return dialog


def _data_splitting_preview_dialog() -> DataSplittingPreviewDialog:
    val_splitter = DataSplitterHolder(True, ValSplitByType.TRIAL)
    test_splitter = DataSplitterHolder(True, SplitByType.TRIAL)
    config = DataSplittingConfig(
        TrainingType.FULL,
        True,
        [val_splitter],
        [test_splitter],
    )
    dialog = DataSplittingPreviewDialog(
        None,
        "Data Splitting Step 2",
        split_context=_data_split_capture_context(),
        publication_generation=1,
        config=config,
        preview_provider=_data_split_capture_provider,
        preview_canceller=lambda _request_id: True,
    )
    if dialog.preview_worker is not None:
        dialog.preview_worker.join(timeout=2)
    dialog.update_table()
    if dialog.preview_debounce_timer is not None:
        dialog.preview_debounce_timer.stop()
    if dialog.timer is not None:
        dialog.timer.stop()
    if dialog.tree is None:
        raise RuntimeError("Data splitting preview tree was not initialized.")
    dialog._clear_tree_current_item()
    dialog._resize_tree_to_rows()
    dialog.adjustSize()
    dialog.resize(QSize(980, dialog.sizeHint().height()))
    return dialog


def _data_split_capture_context() -> DatasetSplitContext:
    return DatasetSplitContext(
        epoch_available=True,
        subject_count=2,
        session_count=1,
        label_count=2,
        trial_count=120,
        subject_choices=(
            DatasetSplitChoice(value="S01", label="S01"),
            DatasetSplitChoice(value="S02", label="S02"),
        ),
        session_choices=(DatasetSplitChoice(value="session", label="session"),),
    )


def _data_split_capture_provider(
    request: DatasetSplitPreviewRequest,
) -> DatasetSplitPreviewPublication:
    return DatasetSplitPreviewPublication(
        request=request,
        generation=request.publication_generation,
        rows=tuple(
            DatasetSplitPreviewRow(
                name=f"Fold_{index}",
                train_count=76,
                validation_count=20,
                test_count=24,
            )
            for index in range(5)
        ),
    )


def _assistant_setup_required_narrow() -> ChatPanel:
    panel = ChatPanel()
    panel.set_runtime_state("idle")
    panel.resize(QSize(320, 650))
    return panel


def _assistant_active_turn_narrow() -> ChatPanel:
    panel = ChatPanel()
    panel.set_runtime_state("ready")
    panel.resize(QSize(420, 650))
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
    panel.set_turn_activity(
        present_assistant_activity(
            AssistantTurnActivity(
                AssistantTurnActivityPhase.PREPARING,
                turn_id=1,
                generation=1,
            )
        )
    )
    if app is not None:
        app.processEvents()
    return panel


def _assistant_loading_standard() -> ChatPanel:
    panel = ChatPanel()
    panel.set_runtime_state("loading")
    panel.resize(QSize(420, 650))
    return panel


def _assistant_failed_standard() -> ChatPanel:
    panel = ChatPanel()
    panel.resize(QSize(420, 650))
    panel.show()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    panel.set_runtime_state("failed", "The selected local model could not start.")
    panel.show_runtime_notice(
        "**Assistant unavailable**: The selected local model could not start. "
        "Open Assistant Settings to review the installed model and runtime."
    )
    if app is not None:
        app.processEvents()
    return panel


def _assistant_recovery_standard() -> ChatPanel:
    panel = ChatPanel()
    panel.resize(QSize(420, 650))
    panel.show()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    panel.set_runtime_state("failed", "The selected local model could not start.")
    if app is not None:
        app.processEvents()
    panel.set_runtime_state("loading")
    if app is not None:
        app.processEvents()
    return panel


def _saliency_setting_dialog() -> QWidget:
    return SaliencySettingDialog(None, saliency_params=None)


def _saliency_setting_single_method() -> QWidget:
    dialog = SaliencySettingDialog(None, saliency_params=None)
    for method, check in dialog.method_checks.items():
        check.setChecked(method == "SmoothGrad")
    return dialog


def _saliency_setting_empty_state() -> QWidget:
    dialog = SaliencySettingDialog(None, saliency_params=None)
    for check in dialog.method_checks.values():
        check.setChecked(False)
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
    dialog.resize(QSize(760, dialog.height()))
    return dialog


def _evaluation_controls_panel() -> QWidget:
    panel = EvaluationPanel(parent=None)
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
    panel.plot_stack.setCurrentIndex(0)
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


def _training_history_few_rows() -> TrainingPanel:
    panel = _training_history_panel()
    panel.history_table.update_history(
        _training_history_rows(2, running=False),
    )
    panel.sidebar.btn_start.setEnabled(True)
    panel.sidebar.btn_stop.setEnabled(False)
    return panel


def _training_history_many_rows() -> TrainingPanel:
    panel = _training_history_panel()
    panel.history_table.update_history(
        _training_history_rows(9, running=True),
    )
    panel.sidebar.btn_start.setEnabled(False)
    panel.sidebar.btn_stop.setEnabled(True)
    return panel


def _training_history_panel() -> TrainingPanel:
    controller = MagicMock()
    controller.validate_ready.return_value = True
    controller.has_datasets.return_value = True
    controller.has_model.return_value = True
    controller.has_training_option.return_value = True
    controller.is_training.return_value = False
    controller.get_trainer.return_value = None
    panel = TrainingPanel(controller=controller, parent=None)
    dataset_row = {
        "filename": "sub-01_task-mi_run-01_eeg.fif",
        "subject": "01",
        "session": "01",
        "n_channels": 22,
        "sampling_frequency": 250.0,
        "epochs_length": 288,
        "is_raw": False,
        "tmin": -0.2,
        "epoch_duration_samples": 301,
        "highpass": 1.0,
        "lowpass": 40.0,
        "event": {
            "available": True,
            "count": 288,
            "labels": ["left", "right", "feet", "tongue"],
        },
    }
    panel.sidebar.info_panel.update_info(
        loaded_data_list=[dataset_row],
        preprocessed_data_list=[dataset_row],
    )
    panel.resize(QSize(1280, 760))
    return panel


def _training_history_rows(
    count: int,
    *,
    running: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(count):
        is_running = running and index == 0
        rows.append(
            {
                "identity": {
                    "plan_index": index // 3,
                    "run_index": index,
                },
                "group_name": f"Group {index // 3 + 1:02d}",
                "run_name": f"Run {index + 1:02d}",
                "model_name": "EEGNet" if index % 2 == 0 else "ShallowConvNet",
                "status": "Running" if is_running else "Completed",
                "epoch": 4 if is_running else 12,
                "max_epochs": 12,
                "is_active": is_running,
                "is_current_run": is_running,
                "start_timestamp": time.time() - 37.0 if is_running else 1_000.0,
                "end_timestamp": None if is_running else 1_062.0 + index,
                "metrics": {
                    "train": {
                        "loss": [0.42 - index * 0.01],
                        "accuracy": [82.1 + index * 0.2],
                        "auc": [],
                        "lr": [0.001],
                        "time": [],
                    },
                    "validation": {
                        "loss": [0.51 - index * 0.01],
                        "accuracy": [78.4 + index * 0.3],
                        "auc": [],
                    },
                },
            }
        )
    return rows


def _capture_factories() -> tuple[tuple[str, Callable[[], QWidget]], ...]:
    return (
        ("model-selection-dialog.png", _model_selection_dialog),
        ("training-setting-dialog.png", _training_setting_dialog),
        ("preprocess-rereference-dialog.png", _rereference_dialog),
        (INTERNAL_EPOCH_SCREENSHOT, _epoching_internal_events_dialog),
        (BIDS_EPOCH_SCREENSHOT, _epoching_bids_interval_duration_dialog),
        ("data-splitting-dialog.png", _data_splitting_dialog),
        ("data-splitting-dialog-narrow.png", _data_splitting_dialog_narrow),
        ("data-splitting-preview-dialog.png", _data_splitting_preview_dialog),
        ("assistant-setup-required-narrow.png", _assistant_setup_required_narrow),
        ("assistant-active-turn-narrow.png", _assistant_active_turn_narrow),
        ("assistant-loading.png", _assistant_loading_standard),
        ("assistant-failed.png", _assistant_failed_standard),
        ("assistant-recovery-loading.png", _assistant_recovery_standard),
        ("saliency-setting-dialog.png", _saliency_setting_dialog),
        ("saliency-setting-single-method.png", _saliency_setting_single_method),
        ("saliency-setting-empty-state.png", _saliency_setting_empty_state),
        ("set-montage-dialog.png", _set_montage_dialog),
        ("evaluation-controls-panel.png", _evaluation_controls_panel),
        ("evaluation-metrics-table.png", _metrics_table),
        ("training-history-few-rows.png", _training_history_few_rows),
        ("training-history-many-rows.png", _training_history_many_rows),
    )


def _capture(widget: QWidget, output_path: Path) -> dict[str, object]:
    """Publish only after two consecutive complete widget frames settle."""
    app = QApplication.instance()
    first_frame = output_path.with_name(f".{output_path.stem}-frame-1.png")
    last_error: RuntimeError | None = None
    for _attempt in range(3):
        try:
            _settle_capture_widget(app, widget)
            _save_widget_grab(widget, first_frame)
            required_regions, _first_matches = _assert_surface_pixels(
                widget,
                first_frame,
            )
            _settle_capture_widget(app, widget)
            _save_widget_grab(widget, output_path)
            required_regions, reference_matches = _assert_surface_pixels(
                widget,
                output_path,
            )
            changed_ratio = assert_consecutive_complete_frames(
                first_frame,
                output_path,
            )
        except RuntimeError as error:
            last_error = error
            continue
        finally:
            first_frame.unlink(missing_ok=True)
        payload = frame_readiness_payload(
            changed_pixel_ratio=changed_ratio,
            required_regions=required_regions,
            reference_matches=reference_matches,
        )
        payload["capture_method"] = "QWidget.grab"
        return payload
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Could not capture {output_path}.")


def _settle_capture_widget(app: object, widget: QWidget) -> None:
    if isinstance(app, QApplication):
        if isinstance(widget, ChatPanel):
            _settle_chat_panel_capture(app, widget)
        else:
            widget.ensurePolished()
            widget.updateGeometry()
            widget.repaint()
            app.processEvents()
            time.sleep(0.04)
            app.processEvents()


def _save_widget_grab(widget: QWidget, output_path: Path) -> None:
    pixmap = widget.grab()
    if pixmap.isNull():
        raise RuntimeError(f"Could not grab {output_path}.")
    if not pixmap.save(str(output_path)):
        raise RuntimeError(f"Could not save {output_path}.")
    with Image.open(output_path) as captured:
        normalized = captured.convert("RGB")
        normalized.load()
    normalized.save(output_path, format="PNG")
    if _is_nearly_black(output_path):
        raise RuntimeError(f"Screenshot is nearly black: {output_path}.")


def _assert_surface_pixels(
    widget: QWidget,
    screenshot: Path,
) -> tuple[list[str], list[dict[str, object]]]:
    required = _required_reference_controls(widget)
    with Image.open(screenshot) as captured:
        scale_x = captured.width / max(widget.width(), 1)
        scale_y = captured.height / max(widget.height(), 1)
    matches: list[dict[str, object]] = []
    for surface_name, control in required.items():
        if not control.isVisibleTo(widget):
            raise RuntimeError(f"{surface_name} is hidden in {screenshot.name}.")
        top_left = control.mapTo(widget, QPoint(0, 0))
        bounds = (
            round(top_left.x() * scale_x),
            round(top_left.y() * scale_y),
            round((top_left.x() + control.width()) * scale_x),
            round((top_left.y() + control.height()) * scale_y),
        )
        assert_region_has_no_unpainted_block(
            screenshot,
            bounds,
            surface_name=surface_name,
        )
        # The isolated editor grab omits the parent-composited fill; its edges and
        # detail tiles still prove that the full-frame control was painted in place.
        transparent_composer_input = bool(
            isinstance(widget, ChatPanel) and control is widget.input_field
        )
        matches.append(
            assert_region_matches_reference(
                screenshot,
                bounds,
                _pixmap_image(control.grab()),
                surface_name=surface_name,
                minimum_edge_recall=(
                    0.70
                    if isinstance(control, (QLabel, QAbstractButton, QComboBox))
                    else 0.42
                ),
                maximum_changed_pixel_ratio=(
                    1.0
                    if transparent_composer_input
                    or isinstance(control, (QLabel, QAbstractButton, QComboBox))
                    else 0.55
                ),
                content_inset=(
                    1
                    if transparent_composer_input
                    or isinstance(control, (QLabel, QAbstractButton, QComboBox))
                    else 3
                ),
            )
        )
    if isinstance(widget, TrainingPanel):
        training_matches = _assert_training_history_reference_pixels(
            widget,
            screenshot,
        )
        matches.extend(training_matches)
        required.update(
            {str(match["surface_name"]): widget for match in training_matches}
        )
    return list(required), matches


def _required_reference_controls(widget: QWidget) -> dict[str, QWidget]:
    required: dict[str, QWidget] = {
        f"{type(widget).__name__} complete surface": widget,
    }
    if isinstance(widget, ChatPanel):
        required.update(
            {
                "Assistant composer": widget.control_panel,
                "Assistant input": widget.input_field,
                "Assistant Send/Stop action": widget.send_btn,
            }
        )
        phase = widget._runtime_phase.value
        if phase in {"idle", "loading", "failed"}:
            # The runtime surface is intentionally transparent and inherits its
            # fill from the chat viewport.  Grabbing that container in isolation
            # therefore produces a different background from the composited
            # panel.  Validate its visible semantic children instead; the full
            # ChatPanel reference above still guards the complete surface.
            required["Assistant runtime title"] = widget.runtime_state_title
            required["Assistant runtime detail"] = widget.runtime_state_detail
            if widget.runtime_progress.isVisibleTo(widget):
                required["Assistant runtime progress"] = widget.runtime_progress
            for index, action in enumerate(
                widget.runtime_actions.findChildren(QAbstractButton)
            ):
                if not action.isVisibleTo(widget):
                    continue
                label = " ".join(action.text().split()) or type(action).__name__
                required[f"Assistant runtime action {index}: {label}"] = action
        if widget.is_processing:
            required["Assistant activity feedback"] = widget.turn_activity_widget
        if phase == "failed":
            required["Assistant error feedback"] = widget.runtime_state_detail
        return required

    if isinstance(widget, TrainingPanel):
        required.update(
            {
                "Training History table": widget.history_table,
                "Start Training action": widget.sidebar.btn_start,
                "Stop Training action": widget.sidebar.btn_stop,
            }
        )

    for index, control in enumerate(widget.findChildren(QAbstractItemView)):
        if not control.isVisibleTo(widget):
            continue
        top_left = control.mapTo(widget, QPoint(0, 0))
        if not widget.rect().contains(QRect(top_left, control.size())):
            # Scroll-area children can be intentionally clipped by their viewport;
            # comparing a full child grab with only its visible slice is invalid.
            continue
        name = control.objectName() or type(control).__name__
        required.setdefault(f"{name} content {index}", control)

    text_controls: list[QWidget] = [
        *widget.findChildren(QLabel),
        *widget.findChildren(QAbstractButton),
        *widget.findChildren(QComboBox),
    ]
    for index, control in enumerate(text_controls):
        text = _control_text(control)
        if not text or not control.isVisibleTo(widget):
            continue
        name = control.objectName() or type(control).__name__
        required.setdefault(f"{name} text {index}: {text[:48]}", control)
    return required


def _control_text(control: QWidget) -> str:
    text_getter = getattr(control, "text", None)
    if callable(text_getter):
        return " ".join(str(text_getter()).split())
    if isinstance(control, QComboBox):
        return " ".join(control.currentText().split())
    return ""


def _pixmap_image(pixmap) -> Image.Image:
    if pixmap.isNull():
        raise RuntimeError("Could not create a settled live widget reference.")
    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("Could not open the live widget reference buffer.")
    if not pixmap.save(buffer, "PNG"):
        raise RuntimeError("Could not encode the live widget reference.")
    data = buffer.data().data()
    buffer.close()
    with Image.open(BytesIO(data)) as source:
        image = source.convert("RGB")
        image.load()
    return image


def _qt_image_to_pil(qt_image: QImage) -> Image.Image:
    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("Could not open the live widget reference buffer.")
    if not qt_image.save(buffer, "PNG"):
        raise RuntimeError("Could not encode the live widget reference.")
    data = buffer.data().data()
    buffer.close()
    with Image.open(BytesIO(data)) as source:
        pil_image = source.convert("RGB")
        pil_image.load()
    return pil_image


def _assert_training_history_reference_pixels(
    panel: TrainingPanel,
    screenshot: Path,
) -> list[dict[str, object]]:
    """Validate title, tabs, and each fully visible non-empty history cell."""
    with Image.open(screenshot) as captured:
        scale_x = captured.width / max(panel.width(), 1)
        scale_y = captured.height / max(panel.height(), 1)
    matches: list[dict[str, object]] = []
    for surface_name, logical_bounds, reference in _training_history_reference_regions(
        panel
    ):
        left, top, right, bottom = logical_bounds
        bounds = (
            round(left * scale_x),
            round(top * scale_y),
            round(right * scale_x),
            round(bottom * scale_y),
        )
        assert_region_has_no_unpainted_block(
            screenshot,
            bounds,
            surface_name=surface_name,
        )
        matches.append(
            assert_region_matches_reference(
                screenshot,
                bounds,
                reference,
                surface_name=surface_name,
                minimum_edge_recall=0.55,
                maximum_changed_pixel_ratio=0.70,
                content_inset=1,
            )
        )
    return matches


def _training_history_reference_regions(
    panel: TrainingPanel,
) -> list[tuple[str, tuple[int, int, int, int], Image.Image]]:
    references: list[tuple[str, tuple[int, int, int, int], Image.Image]] = []
    for group in (panel.plots_group,):
        width = min(
            group.width(),
            group.fontMetrics().horizontalAdvance(group.title()) + 24,
        )
        height = min(group.height(), group.fontMetrics().height() + 8)
        top_left = group.mapTo(panel, QPoint(0, 0))
        rendered = _pixmap_image(group.grab())
        references.append(
            (
                f"Training History chrome title: {group.title()}",
                (
                    top_left.x(),
                    top_left.y(),
                    top_left.x() + width,
                    top_left.y() + height,
                ),
                rendered.crop((0, 0, width, height)),
            )
        )

    history_title = panel.history_title
    history_title_text = history_title.text()
    width = min(
        history_title.width(),
        history_title.fontMetrics().horizontalAdvance(history_title_text) + 8,
    )
    height = history_title.height()
    top_left = history_title.mapTo(panel, QPoint(0, 0))
    title_in_section = history_title.mapTo(panel.history_group, QPoint(0, 0))
    rendered = _pixmap_image(panel.history_group.grab())
    references.append(
        (
            f"Training History chrome title: {history_title_text}",
            (
                top_left.x(),
                top_left.y(),
                top_left.x() + width,
                top_left.y() + height,
            ),
            rendered.crop(
                (
                    title_in_section.x(),
                    title_in_section.y(),
                    title_in_section.x() + width,
                    title_in_section.y() + height,
                )
            ),
        )
    )

    tab_bar = _require_qt_value(panel.tabs.tabBar(), "Training History tab bar")
    rendered_tabs = _pixmap_image(tab_bar.grab())
    for index in range(tab_bar.count()):
        rect = tab_bar.tabRect(index)
        top_left = tab_bar.mapTo(panel, rect.topLeft())
        references.append(
            (
                f"Training History chrome tab: {tab_bar.tabText(index)}",
                (
                    top_left.x(),
                    top_left.y(),
                    top_left.x() + rect.width(),
                    top_left.y() + rect.height(),
                ),
                rendered_tabs.crop(
                    (
                        rect.x(),
                        rect.y(),
                        rect.x() + rect.width(),
                        rect.y() + rect.height(),
                    )
                ),
            )
        )

    table = panel.history_table
    viewport = _require_qt_value(table.viewport(), "Training History viewport")
    model = _require_qt_value(table.model(), "Training History table model")
    viewport_rect = viewport.rect()
    for row in range(table.rowCount()):
        for column in range(table.columnCount()):
            item = table.item(row, column)
            if item is None or not item.text().strip():
                continue
            index = model.index(row, column)
            rect = table.visualRect(index)
            if rect.isEmpty() or not viewport_rect.contains(rect):
                continue
            top_left = viewport.mapTo(panel, rect.topLeft())
            header = table.horizontalHeaderItem(column)
            column_name = header.text() if header is not None else str(column + 1)
            references.append(
                (
                    f"Training History cell row {row + 1}: {column_name}",
                    (
                        top_left.x(),
                        top_left.y(),
                        top_left.x() + rect.width(),
                        top_left.y() + rect.height(),
                    ),
                    _render_item_reference(table, index, rect),
                )
            )
    return references


def _render_item_reference(
    table: QTableWidget,
    index,
    rect: QRect,
) -> Image.Image:
    viewport = _require_qt_value(table.viewport(), "Training History viewport")
    delegate = _require_qt_value(
        table.itemDelegate(),
        "Training History item delegate",
    )
    image = QImage(
        QSize(rect.width(), rect.height()),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.fill(viewport.palette().base().color())
    option = QStyleOptionViewItem()
    option.initFrom(viewport)
    option.rect = QRect(0, 0, rect.width(), rect.height())
    painter = QPainter(image)
    try:
        delegate.paint(painter, option, index)
    finally:
        painter.end()
    return _qt_image_to_pil(image)


def _assert_capture_geometry(filename: str, widget: QWidget) -> None:
    if isinstance(widget, EpochingDialog):
        _assert_epoching_dialog_contract(filename, widget)

    if isinstance(widget, TrainingPanel):
        semantics = _training_history_semantics(widget)
        expected_running = filename == "training-history-many-rows.png"
        expected_rows = 9 if expected_running else 2
        if semantics["row_count"] != expected_rows:
            raise RuntimeError(f"{filename} has the wrong Training History row count.")
        if semantics["running"] is not expected_running:
            raise RuntimeError(f"{filename} has an inconsistent training lifecycle.")
        if semantics["start_enabled"] is expected_running:
            raise RuntimeError(f"{filename} has an inconsistent Start Training state.")
        if semantics["stop_enabled"] is not expected_running:
            raise RuntimeError(f"{filename} has an inconsistent Stop Training state.")
        if not semantics["summary_has_data"]:
            raise RuntimeError(f"{filename} has a contradictory empty Data Summary.")
        if not semantics["key_columns_fit"]:
            raise RuntimeError(f"{filename} clips Group, Run, Model, or Status text.")
        if semantics["horizontal_scroll_maximum"] != 0:
            raise RuntimeError(
                f"{filename} unnecessarily scrolls Training History horizontally."
            )
        expected_visible_rows = list(
            range(min(expected_rows, widget.history_table.MAX_VISIBLE_ROWS))
        )
        if semantics["fully_visible_rows"] != expected_visible_rows:
            raise RuntimeError(
                f"{filename} has the wrong fully visible Training History rows."
            )
        if semantics["partially_visible_rows"]:
            raise RuntimeError(f"{filename} clips a partial Training History row.")
        vertical_scroll = int(semantics["vertical_scroll_maximum"])
        if (expected_running and vertical_scroll <= 0) or (
            not expected_running and vertical_scroll != 0
        ):
            raise RuntimeError(f"{filename} has the wrong row scrolling behavior.")

    if isinstance(widget, DataSplittingDialog):
        if widget.minimumSizeHint().width() > widget.width():
            raise RuntimeError(f"{filename} minimum width exceeds its captured width.")
        button = widget.btn_confirm
        if button is None or not button.isVisible():
            raise RuntimeError(f"{filename} does not show its Confirm button.")
        bottom_right = button.mapTo(widget, button.rect().bottomRight())
        if bottom_right.x() >= widget.width() or bottom_right.y() >= widget.height():
            raise RuntimeError(f"{filename} clips its Confirm button.")
        for control in (
            widget.options_group,
            widget.train_type_combo,
            widget.test_combo,
            widget.val_combo,
        ):
            if control is None or not control.isVisibleTo(widget):
                raise RuntimeError(f"{filename} hides a core split setting.")

    if isinstance(widget, DataSplittingPreviewDialog) and widget.tree is not None:
        _data_splitting_preview_semantics(widget)
        tree = widget.tree
        last_row = tree.topLevelItem(tree.topLevelItemCount() - 1)
        if last_row is not None:
            row_rect = tree.visualItemRect(last_row)
            tree_viewport = tree.viewport()
            if tree_viewport is None:
                raise RuntimeError(f"{filename} has no results viewport.")
            unused_height = tree_viewport.height() - row_rect.bottom()
            if unused_height > 12:
                raise RuntimeError(f"{filename} leaves an empty results viewport.")

    if isinstance(widget, MetricsTableWidget) and widget.rowCount():
        last_item = widget.item(widget.rowCount() - 1, 0)
        table_viewport = widget.viewport()
        scroll_bar = widget.verticalScrollBar()
        if last_item is None or table_viewport is None or scroll_bar is None:
            raise RuntimeError(f"{filename} has incomplete metrics geometry.")
        last_row = widget.visualItemRect(last_item)
        if not last_row.isValid() or not table_viewport.rect().contains(last_row):
            raise RuntimeError(f"{filename} clips its final metrics row.")
        if widget.rowCount() <= widget.MAX_VISIBLE_ROWS and scroll_bar.isVisible():
            raise RuntimeError(f"{filename} scrolls a small metrics result.")
        unused_height = table_viewport.height() - last_row.bottom()
        if unused_height > 4:
            raise RuntimeError(f"{filename} leaves an empty metrics viewport.")

    if isinstance(widget, ChatPanel):
        phase = widget._runtime_phase.value
        setup_required = phase in {"idle", "failed"}
        if setup_required and widget.send_btn.text() == "Stop":
            raise RuntimeError(f"{filename} shows setup-required state with Stop.")
        if widget.is_processing and phase != "ready":
            raise RuntimeError(f"{filename} shows processing while runtime is {phase}.")
        if setup_required:
            if not widget.setup_btn.isVisible() or not widget.setup_btn.isEnabled():
                raise RuntimeError(
                    f"{filename} does not expose Open Assistant Settings."
                )
            if (
                widget.input_widget.isHidden()
                or widget.input_field.isEnabled()
                or widget.send_btn.isEnabled()
            ):
                raise RuntimeError(
                    f"{filename} does not keep the setup-required composer disabled."
                )
            failed = phase == "failed"
            if widget.retry_runtime_btn.isVisible() is not failed:
                raise RuntimeError(
                    f"{filename} exposes the runtime retry action in the wrong phase."
                )
            if widget.retry_runtime_btn.isEnabled() is not failed:
                raise RuntimeError(
                    f"{filename} enables the runtime retry action in the wrong phase."
                )
        elif widget.setup_btn.isVisible():
            raise RuntimeError(
                f"{filename} exposes Open Assistant Settings outside recovery."
            )
        if phase == "loading" and (
            widget.runtime_state_widget.isHidden()
            or widget.workflow_run_status_label.isVisible()
            or widget.runtime_progress.isHidden()
        ):
            raise RuntimeError(
                f"{filename} does not use one inline loading runtime state."
            )
        if phase == "ready" and widget.runtime_state_widget.isVisible():
            raise RuntimeError(
                f"{filename} leaves stale runtime copy visible when ready."
            )
        if phase != "loading" and widget.runtime_progress.isVisible():
            raise RuntimeError(
                f"{filename} leaves startup progress visible while runtime is {phase}."
            )
        if widget.is_processing and widget.send_btn.text() != "Stop":
            raise RuntimeError(f"{filename} processing state does not expose Stop.")
        if not widget.is_processing and widget.send_btn.text() == "Stop":
            raise RuntimeError(f"{filename} exposes Stop while not processing.")
        for control_name in (
            "input_field",
            "send_btn",
        ):
            control = getattr(widget, control_name)
            bottom_right = control.mapTo(
                widget.control_panel,
                control.rect().bottomRight(),
            )
            if (
                not control.isVisibleTo(widget)
                or bottom_right.x() >= widget.control_panel.width()
                or bottom_right.y() >= widget.control_panel.height()
            ):
                raise RuntimeError(
                    f"{filename} clips the assistant control {control_name}."
                )

        expected_widths = {
            "assistant-setup-required-narrow.png": 320,
            "assistant-active-turn-narrow.png": 420,
            "assistant-loading.png": 420,
            "assistant-failed.png": 420,
            "assistant-recovery-loading.png": 420,
        }
        expected_width = expected_widths.get(filename)
        if expected_width is not None and widget.width() != expected_width:
            raise RuntimeError(
                f"{filename} is {widget.width()}px, expected {expected_width}px."
            )
        expected_runtime_titles = {
            "assistant-setup-required-narrow.png": "Assistant setup required",
            "assistant-loading.png": "Loading local assistant",
            "assistant-failed.png": "Assistant unavailable",
            "assistant-recovery-loading.png": "Retrying local assistant",
        }
        expected_title = expected_runtime_titles.get(filename)
        if (
            expected_title is not None
            and widget.runtime_state_title.text() != expected_title
        ):
            raise RuntimeError(
                f"{filename} shows stale runtime copy instead of {expected_title}."
            )

        runtime_state = widget.runtime_state_widget
        if runtime_state.isVisible():
            state_bottom_right = runtime_state.mapTo(
                widget.chat_content_widget,
                runtime_state.rect().bottomRight(),
            )
            if (
                state_bottom_right.x() >= widget.chat_content_widget.width()
                or state_bottom_right.y() >= widget.chat_content_widget.height()
            ):
                raise RuntimeError(f"{filename} clips its inline runtime state.")
        if widget.setup_btn.isVisible():
            button_right = widget.setup_btn.mapTo(
                runtime_state,
                widget.setup_btn.rect().bottomRight(),
            )
            required_width = (
                widget.setup_btn.fontMetrics().horizontalAdvance(
                    widget.setup_btn.text()
                )
                + 24
            )
            if (
                button_right.x() >= runtime_state.width()
                or button_right.y() >= runtime_state.height()
                or required_width > widget.setup_btn.contentsRect().width()
            ):
                raise RuntimeError(
                    f"{filename} clips Open Assistant Settings at its target width."
                )
        if widget.retry_runtime_btn.isVisible():
            retry_right = widget.retry_runtime_btn.mapTo(
                runtime_state,
                widget.retry_runtime_btn.rect().bottomRight(),
            )
            if (
                retry_right.x() >= runtime_state.width()
                or retry_right.y() >= runtime_state.height()
            ):
                raise RuntimeError(f"{filename} clips Retry local assistant.")

        viewport = widget.scroll_area.viewport()
        if viewport is None:
            raise RuntimeError(f"{filename} has no conversation viewport.")
        for bubble in widget.findChildren(MessageBubble):
            if not bubble.isVisible():
                continue
            left = bubble.mapTo(viewport, bubble.rect().topLeft()).x()
            right = bubble.mapTo(viewport, bubble.rect().bottomRight()).x()
            if left < 0 or right >= viewport.width():
                raise RuntimeError(f"{filename} clips a conversation bubble.")


def _training_history_semantics(panel: TrainingPanel) -> dict[str, Any]:
    table = panel.history_table
    viewport = _require_qt_value(table.viewport(), "Training History viewport")
    viewport_rect = viewport.rect()
    visible_rows: list[int] = []
    partially_visible_rows: list[int] = []
    for row in range(table.rowCount()):
        item = table.item(row, 0)
        if item is None:
            continue
        row_rect = table.visualItemRect(item)
        if viewport_rect.contains(row_rect):
            visible_rows.append(row)
        elif row_rect.intersects(viewport_rect):
            partially_visible_rows.append(row)
    statuses = [
        item.text()
        for row in range(table.rowCount())
        if (item := table.item(row, 3)) is not None
    ]
    key_columns_fit = True
    all_visible_text_fits = True
    padding = table.KEY_COLUMN_PADDING
    header = _require_qt_value(
        table.horizontalHeader(),
        "Training History horizontal header",
    )
    horizontal_scroll = _require_qt_value(
        table.horizontalScrollBar(),
        "Training History horizontal scroll bar",
    )
    vertical_scroll = _require_qt_value(
        table.verticalScrollBar(),
        "Training History vertical scroll bar",
    )
    header_metrics = header.fontMetrics()
    for column in range(table.columnCount()):
        header_item = table.horizontalHeaderItem(column)
        if header_item is None or table.columnWidth(column) < (
            header_metrics.horizontalAdvance(header_item.text()) + table.HEADER_PADDING
        ):
            all_visible_text_fits = False
    for row in range(table.rowCount()):
        for column in range(table.columnCount()):
            item = table.item(row, column)
            if item is None:
                all_visible_text_fits = False
                if column in (0, 1, 2, 3):
                    key_columns_fit = False
                continue
            required_width = (
                table.fontMetrics().horizontalAdvance(item.text()) + padding
            )
            if table.columnWidth(column) < required_width:
                all_visible_text_fits = False
                if column in (0, 1, 2, 3):
                    key_columns_fit = False
    return {
        "row_count": table.rowCount(),
        "visible_row_capacity": table.MAX_VISIBLE_ROWS,
        "statuses": statuses,
        "running": "Running" in statuses,
        "start_enabled": panel.sidebar.btn_start.isEnabled(),
        "stop_enabled": panel.sidebar.btn_stop.isEnabled(),
        "summary_has_data": panel.sidebar.info_panel.has_data,
        "start_visual": _control_visual_signature(panel.sidebar.btn_start),
        "stop_visual": _control_visual_signature(panel.sidebar.btn_stop),
        "key_columns_fit": key_columns_fit,
        "all_visible_text_fits": all_visible_text_fits,
        "horizontal_scroll_maximum": horizontal_scroll.maximum(),
        "all_columns_visible_without_scroll": (
            horizontal_scroll.maximum() == 0 and header.length() <= viewport.width()
        ),
        "vertical_scroll_maximum": vertical_scroll.maximum(),
        "fully_visible_rows": visible_rows,
        "partially_visible_rows": partially_visible_rows,
    }


def _control_visual_signature(control: QWidget) -> dict[str, object]:
    """Summarize rendered button color so disabled state must look different."""
    image = _pixmap_image(control.grab()).convert("RGB")
    inset = min(5, max((image.width - 1) // 4, 0), max((image.height - 1) // 4, 0))
    if inset:
        image = image.crop((inset, inset, image.width - inset, image.height - inset))
    mean_rgb = [round(value, 3) for value in ImageStat.Stat(image).mean[:3]]
    luminance = mean_rgb[0] * 0.2126 + mean_rgb[1] * 0.7152 + mean_rgb[2] * 0.0722
    return {
        "mean_rgb": mean_rgb,
        "luminance": round(luminance, 3),
        "color_span": round(max(mean_rgb) - min(mean_rgb), 3),
    }


def _assert_epoching_dialog_contract(
    filename: str,
    dialog: EpochingDialog,
) -> None:
    expected_text = {
        INTERNAL_EPOCH_SCREENSHOT: (
            "Create EEG Epochs",
            "Suggested from import",
            "labels inside EEG files",
            "Events inside EEG files",
            "Events",
            "Time Window",
            "Apply baseline correction",
            "Cancel",
        ),
        BIDS_EPOCH_SCREENSHOT: (
            "Create EEG Epochs",
            "BIDS events from import",
            "BIDS events confirmed in Match Labels.",
            "Label interval",
            "trial_type",
            "onset + duration",
            "Use event duration.",
            "Events",
            "Time Window",
            "Apply baseline correction",
            "Cancel",
        ),
    }
    required = expected_text.get(filename)
    if required is None:
        raise RuntimeError(f"{filename} has no Epoch capture contract.")
    visible_text = "\n".join(_visible_control_text(dialog))
    missing = [text for text in required if text not in visible_text]
    if missing:
        raise RuntimeError(f"{filename} is missing visible Epoch controls: {missing}.")

    controls = (
        dialog.event_list,
        dialog.tmin_spin,
        dialog.tmax_spin,
        dialog.baseline_check,
        dialog.b_min_spin,
        dialog.b_max_spin,
    )
    for control in controls:
        if control is None or not control.isVisibleTo(dialog):
            raise RuntimeError(f"{filename} hides an Epoch configuration control.")
        top_left = control.mapTo(dialog, control.rect().topLeft())
        bottom_right = control.mapTo(dialog, control.rect().bottomRight())
        if not dialog.rect().contains(top_left) or not dialog.rect().contains(
            bottom_right
        ):
            raise RuntimeError(f"{filename} clips an Epoch configuration control.")

    buttons = {
        button.objectName(): button
        for button in dialog.findChildren(QAbstractButton)
        if button.isVisibleTo(dialog)
    }
    primary = buttons.get("EpochPrimaryButton")
    cancel = buttons.get("EpochSecondaryButton")
    if primary is None or primary.text() != "Create EEG Epochs":
        raise RuntimeError(f"{filename} does not expose Create EEG Epochs.")
    if cancel is None or cancel.text() != "Cancel":
        raise RuntimeError(f"{filename} does not expose Cancel.")

    event_list = dialog.event_list
    if event_list is None or event_list.rowCount() <= 0:
        raise RuntimeError(f"{filename} has no selectable Epoch events.")
    selected = _selected_epoch_event_count(event_list)
    if selected <= 0:
        raise RuntimeError(f"{filename} has no selected Epoch events.")


def _selected_epoch_event_count(event_list: QTableWidget | None) -> int:
    selected = 0
    if event_list is None:
        return selected
    for row in range(event_list.rowCount()):
        item = event_list.item(row, 0)
        if item is not None and item.checkState() == Qt.CheckState.Checked:
            selected += 1
    return selected


def _data_splitting_preview_semantics(
    dialog: DataSplittingPreviewDialog,
) -> dict[str, Any]:
    if dialog.tree is None or len(dialog.test_widgets) != 1:
        raise RuntimeError("Data splitting preview has no single K-fold control.")
    split_unit, split_value = dialog.test_widgets[0]
    try:
        fold_count = int(split_value.text())
    except ValueError as exc:
        raise RuntimeError("Data splitting K-fold count is not an integer.") from exc
    rows: list[dict[str, int | str]] = []
    for index in range(dialog.tree.topLevelItemCount()):
        item = dialog.tree.topLevelItem(index)
        if item is None:
            continue
        train = int(item.text(1))
        validation = int(item.text(2))
        test = int(item.text(3))
        rows.append(
            {
                "name": item.text(0),
                "train": train,
                "validation": validation,
                "test": test,
                "total": train + validation + test,
            }
        )
    expected_names = [f"Fold_{index}" for index in range(fold_count)]
    observed_names = [str(row["name"]) for row in rows]
    trial_count = int(dialog.split_context.trial_count)
    if split_unit.currentText() != "K Fold" or fold_count < 2:
        raise RuntimeError("Data splitting preview is not configured for K Fold.")
    if len(rows) != fold_count or observed_names != expected_names:
        raise RuntimeError(
            "Data splitting K-fold control and result row count are inconsistent."
        )
    if any(int(row["total"]) != trial_count for row in rows):
        raise RuntimeError("Data splitting result row totals are inconsistent.")
    return {
        "split_unit": split_unit.currentText(),
        "k_fold_count": fold_count,
        "trial_count": trial_count,
        "dataset_rows": rows,
    }


def _surface_contract(
    filename: str,
    widget: QWidget,
    *,
    frame_readiness: dict[str, object] | None = None,
) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "contract_version": 1,
        "kind": type(widget).__name__,
        "passed": frame_readiness is not None,
        "verified_controls": [text for text in _visible_control_text(widget) if text][
            :80
        ],
        "frame_readiness": dict(frame_readiness or {}),
    }
    if isinstance(widget, DataSplittingPreviewDialog):
        contract.update(
            {
                "kind": "data_splitting_preview",
                **_data_splitting_preview_semantics(widget),
            }
        )
    elif isinstance(widget, EpochingDialog):
        event_list = widget.event_list
        selected_event_count = _selected_epoch_event_count(event_list)
        context = widget.epoch_context
        contract.update(
            {
                "kind": "epoching_dialog",
                "scenario": (
                    "bids_interval_duration"
                    if filename == BIDS_EPOCH_SCREENSHOT
                    else "internal_events"
                ),
                "source": context.get("source"),
                "placement_method": context.get("placement_method"),
                "placement_label": context.get("placement_label"),
                "label_field": context.get("label_field"),
                "window_mode": context.get("window_mode"),
                "time_field": context.get("time_field"),
                "duration_field": context.get("duration_field"),
                "window_evidence": context.get("window_evidence"),
                "selected_event_count": selected_event_count,
                "primary_action": "Create EEG Epochs",
                "cancel_action": "Cancel",
            }
        )
    elif isinstance(widget, TrainingPanel):
        contract.update(
            {
                "kind": "training_history",
                "scenario": (
                    "many_rows_running"
                    if filename == "training-history-many-rows.png"
                    else "few_rows_completed"
                ),
                **_training_history_semantics(widget),
            }
        )
    return contract


def _visible_control_text(widget: QWidget) -> list[str]:
    controls = [
        *widget.findChildren(QLabel),
        *widget.findChildren(QAbstractButton),
    ]
    texts = [
        " ".join(control.text().split())
        for control in controls
        if control.isVisibleTo(widget) and control.text().strip()
    ]
    texts.extend(
        " ".join(combo.currentText().split())
        for combo in widget.findChildren(QComboBox)
        if combo.isVisibleTo(widget) and combo.currentText().strip()
    )
    texts.extend(
        " ".join(group.title().split())
        for group in widget.findChildren(QGroupBox)
        if group.isVisibleTo(widget) and group.title().strip()
    )
    tables = [*widget.findChildren(QTableWidget)]
    if isinstance(widget, QTableWidget):
        tables.append(widget)
    for table in tables:
        if not table.isVisibleTo(widget):
            continue
        texts.extend(
            item.text()
            for column in range(table.columnCount())
            if (item := table.horizontalHeaderItem(column)) is not None
            and item.text().strip()
        )
    return list(dict.fromkeys(texts))


def _write_readme(output_dir: Path = DEFAULT_OUTPUT_DIR) -> None:
    (output_dir / "README.md").write_text(
        "# App Polish Screenshots\n\n"
        "status: generated focused UI review evidence\n"
        "generator: `scripts/dev/capture_ui_polish_surfaces.py`\n"
        "environment: PyQt offscreen capture\n"
        "supports: current visual state for adaptive assistant setup, active-turn, "
        "and runtime recovery surfaces, plus model selection, data splitting, "
        "and evaluation metrics table polish\n"
        "does_not_support: end-to-end training quality, human desktop "
        "acceptance, or long-running runtime behavior\n"
        "next_human_or_runtime_gate: open the same dialogs in the Windows "
        "desktop app during manual acceptance\n\n"
        "Focused current screenshots for manual review of surfaces that are not "
        "fully represented by the Data Import wizard artifacts. Regenerate the "
        "complete set with:\n\n"
        "```bash\n"
        "QT_QPA_PLATFORM=offscreen poetry run -- python "
        "scripts/dev/capture_ui_polish_surfaces.py\n"
        "```\n\n"
        "Regenerate only the narrow assistant evidence with:\n\n"
        "```bash\n"
        "QT_QPA_PLATFORM=offscreen poetry run -- python "
        "scripts/dev/capture_ui_polish_surfaces.py "
        "--only assistant-setup-required-narrow.png "
        "--only assistant-active-turn-narrow.png "
        "--only assistant-loading.png "
        "--only assistant-failed.png "
        "--only assistant-recovery-loading.png\n"
        "```\n\n"
        "- `model-selection-dialog.png`\n"
        "- `training-setting-dialog.png`\n"
        "- `preprocess-rereference-dialog.png`\n"
        "- `preprocess-epoching-internal-events-dialog.png`\n"
        "- `preprocess-epoching-bids-interval-duration-dialog.png`\n"
        "- `data-splitting-dialog.png` (752 x 470 scroll fallback)\n"
        "- `data-splitting-dialog-narrow.png` (752 x 700 full reflow)\n"
        "- `data-splitting-preview-dialog.png`\n"
        "- `assistant-setup-required-narrow.png` (320 x 650, setup-required "
        "recovery)\n"
        "- `assistant-active-turn-narrow.png` (420 x 650, adaptive active-turn "
        "processing)\n"
        "- `assistant-loading.png` (420 x 650, inline runtime loading)\n"
        "- `assistant-failed.png` (420 x 650, unavailable recovery action)\n"
        "- `assistant-recovery-loading.png` (420 x 650, retry in progress)\n"
        "- `saliency-setting-dialog.png`\n"
        "- `saliency-setting-single-method.png`\n"
        "- `saliency-setting-empty-state.png`\n"
        "- `set-montage-dialog.png`\n"
        "- `evaluation-controls-panel.png`\n"
        "- `evaluation-metrics-table.png`\n"
        "- `training-history-few-rows.png` (completed runs; Start enabled)\n"
        "- `training-history-many-rows.png` (active run; Stop enabled)\n",
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
