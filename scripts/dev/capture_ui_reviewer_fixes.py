#!/usr/bin/env python3
"""Capture focused evidence for current import and preprocessing UI fixes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import numpy as np
from PIL import Image, ImageStat
from PyQt6.QtCore import (
    QBuffer,
    QCoreApplication,
    QEvent,
    QIODevice,
    QPoint,
    QRect,
    QSize,
)
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QComboBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_screenshot_artifacts,
    collect_source_identity,
)
from scripts.dev.human_like_walkthrough.readiness import (
    assert_consecutive_complete_frames,
    assert_region_has_no_unpainted_block,
    assert_region_matches_reference,
)
from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.dataset_split_preview import (
    DatasetSplitChoice,
    DatasetSplitContext,
    DatasetSplitPreviewPublication,
    DatasetSplitPreviewRequest,
    DatasetSplitPreviewRow,
)
from XBrainLab.backend.application.preprocess_render import (
    PreprocessRenderPublication,
    PreprocessRenderPublisher,
    PreprocessRenderRequest,
)
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.view_publication import (
    ApplicationViewPublication,
)
from XBrainLab.backend.dataset import (
    DataSplittingConfig,
    SplitByType,
    TrainingType,
    ValSplitByType,
)
from XBrainLab.backend.load_data.raw_data_loader import load_gdf_file
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)
from XBrainLab.ui.dialogs.dataset.data_splitting_preview_dialog import (
    DataSplitterHolder,
    DataSplittingPreviewDialog,
)
from XBrainLab.ui.dialogs.dataset.smart_parser_dialog import SmartParserDialog
from XBrainLab.ui.dialogs.preprocess.filtering_dialog import FilteringDialog
from XBrainLab.ui.dialogs.preprocess.normalize_dialog import NormalizeDialog
from XBrainLab.ui.dialogs.preprocess.rereference_dialog import RereferenceDialog
from XBrainLab.ui.dialogs.preprocess.resampling_dialog import ResampleDialog
from XBrainLab.ui.dialogs.training.training_setting_dialog import TrainingSettingDialog
from XBrainLab.ui.dialogs.visualization.saliency_setting_dialog import (
    SaliencySettingDialog,
)
from XBrainLab.ui.panels.preprocess.history_widget import HistoryWidget
from XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter import PreprocessPlotter
from XBrainLab.ui.panels.preprocess.preview_widget import (
    PREVIEW_RENDER_FAILED_MESSAGE,
    PreviewWidget,
)
from XBrainLab.ui.panels.training.history_table import TrainingHistoryTable
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "dev-artifacts" / "ui-review-fixes"
OUTPUT_DIR = DEFAULT_OUTPUT_DIR
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "data" / "A01T.gdf"
EVIDENCE_FILENAME = "ui-review-fixes-evidence.json"
TRAINING_FONT_SCALES = (1.0, 1.25, 1.5)
TRAINING_SETTING_SURFACES = {
    100: "training-setting-100-percent.png",
    125: "training-setting-125-percent.png",
    150: "training-setting-150-percent.png",
}
LEGACY_REVIEWER_FIX_SURFACES = (
    "preprocess-no-data.png",
    "preprocess-loaded.png",
    "preprocess-loaded-psd.png",
    "preprocess-locked.png",
    "preprocess-unavailable.png",
    "preprocessing-history-no-data.png",
    "preprocessing-history-locked.png",
    "preprocess-filtering-dialog.png",
    "preprocess-filtering-invalid.png",
    "preprocess-rereference-average.png",
    "preprocess-rereference-selected.png",
    "preprocess-rereference-selection-required.png",
    "preprocess-normalize-dialog.png",
    "preprocess-resample-dialog.png",
    "training-history-empty.png",
    *TRAINING_SETTING_SURFACES.values(),
    "smart-parser-simple.png",
    "smart-parser-regex.png",
    "smart-parser-folder.png",
    "smart-parser-fixed.png",
    "import-report-ready.png",
    "import-review-will-save.png",
    "import-review-loaded-recipe.png",
)
EXTENDED_REVIEW_SURFACES = (
    "saliency-setting-empty.png",
    "saliency-setting-single-method.png",
    "saliency-setting-multi-method.png",
    "data-splitting-step-2-ratio.png",
    "data-splitting-step-2-cross-validation.png",
)
REVIEWER_FIX_SURFACES = (
    *LEGACY_REVIEWER_FIX_SURFACES,
    *EXTENDED_REVIEW_SURFACES,
)


class _RealFixtureProjection:
    """Expose real fixture objects only to the application render publisher."""

    def __init__(self, *, current: Any, original: Any) -> None:
        self._current = current
        self._original = original

    def get_preprocessed_data_list(self) -> list[Any]:
        return [self._current]

    def get_loaded_data_list(self) -> list[Any]:
        return [self._original]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for the complete screenshot set and evidence manifest.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="Real EEG fixture used for the loaded time and PSD captures.",
    )
    args = parser.parse_args(argv)
    output_dir = args.output_dir.expanduser().resolve()
    fixture = args.fixture.expanduser().resolve()

    fixture_evidence_at_start = _fixture_evidence(fixture)
    source_identity_at_start = collect_source_identity(ROOT, refresh=True)
    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(Stylesheets.MAIN_WINDOW)
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(
        prefix=f".{output_dir.name}-capture-",
        dir=output_dir.parent,
    ) as staging_name:
        staging_dir = Path(staging_name)
        plot_checks, runtime_fixture_evidence = _capture_preprocess_states(
            app,
            staging_dir,
            fixture,
        )
        _capture_preprocess_dialogs(app, staging_dir)
        geometry_checks = _capture_training_setting_surfaces(app, staging_dir)
        _capture_smart_parser_modes(app, staging_dir)
        _capture_extended_review_surfaces(app, staging_dir)

        review = _ready_import_dialog()
        review.resize(QSize(1100, 800))
        review._go_to_step(review._step_titles.index("Review and Import"))
        review.import_report_toggle.click()
        _capture(app, review, "import-report-ready.png", output_dir=staging_dir)

        review = _ready_import_dialog()
        review.resize(QSize(1100, 800))
        review._go_to_step(review._step_titles.index("Review and Import"))
        review.save_recipe_check.setChecked(True)
        _capture(app, review, "import-review-will-save.png", output_dir=staging_dir)

        review = _ready_import_dialog(recipe_loaded=True)
        review.resize(QSize(1100, 800))
        review._go_to_step(review._step_titles.index("Review and Import"))
        _capture(
            app,
            review,
            "import-review-loaded-recipe.png",
            output_dir=staging_dir,
        )

        fixture_evidence_at_end = _fixture_evidence(fixture)
        if fixture_evidence_at_start != fixture_evidence_at_end:
            raise RuntimeError("The EEG fixture changed during focused UI capture.")
        fixture_evidence = {
            **fixture_evidence_at_start,
            **runtime_fixture_evidence,
        }
        source_identity_at_end = collect_source_identity(ROOT, refresh=True)
        _write_evidence_manifest(
            output_dir=staging_dir,
            source_identity_at_start=source_identity_at_start,
            source_identity_at_end=source_identity_at_end,
            fixture_evidence=fixture_evidence,
            geometry_checks=geometry_checks,
            plot_checks=plot_checks,
            generated_at=datetime.now(UTC),
            qt_platform=QApplication.platformName(),
        )
        _publish_capture(staging_dir, output_dir)
    return 0


def _capture_preprocess_states(
    app: QApplication,
    output_dir: Path,
    fixture: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    preview = PreviewWidget()
    preview.resize(QSize(920, 620))
    preview.reset_view()
    _capture(
        app,
        preview,
        "preprocess-no-data.png",
        output_dir=output_dir,
    )

    preview, fixture_evidence = _real_fixture_preview(fixture)
    curve_checks = _observe_loaded_preview_plots(preview)
    preview.plot_tabs.setCurrentIndex(0)
    time_pixels = _capture(
        app,
        preview,
        "preprocess-loaded.png",
        output_dir=output_dir,
        dispose=False,
        loaded_plot="time",
    )
    preview.plot_tabs.setCurrentIndex(1)
    psd_pixels = _capture(
        app,
        preview,
        "preprocess-loaded-psd.png",
        output_dir=output_dir,
        loaded_plot="psd",
    )
    plot_checks = [
        {
            "surface": "preprocess-loaded.png",
            "plot": "time",
            "curve_checks": [
                check for check in curve_checks if check["curve"].startswith("time_")
            ],
            **time_pixels,
        },
        {
            "surface": "preprocess-loaded-psd.png",
            "plot": "psd",
            "curve_checks": [
                check for check in curve_checks if check["curve"].startswith("psd_")
            ],
            **psd_pixels,
        },
    ]

    preview = PreviewWidget()
    preview.resize(QSize(920, 620))
    preview.show_locked_message("Preprocessing locked")
    _capture(
        app,
        preview,
        "preprocess-locked.png",
        output_dir=output_dir,
    )

    preview = PreviewWidget()
    preview.resize(QSize(920, 620))
    preview.show_unavailable_message(PREVIEW_RENDER_FAILED_MESSAGE)
    _capture(
        app,
        preview,
        "preprocess-unavailable.png",
        output_dir=output_dir,
    )

    history = HistoryWidget()
    history.resize(QSize(920, history.height()))
    history.show_no_data()
    _capture(
        app,
        history,
        "preprocessing-history-no-data.png",
        output_dir=output_dir,
    )

    history = HistoryWidget()
    history.resize(QSize(920, history.height()))
    history.update_history(
        [
            "Band-pass filter: 1-40 Hz",
            "Re-reference: average",
            "Normalize: Z-Score",
        ],
        is_epoched=True,
    )
    _capture(
        app,
        history,
        "preprocessing-history-locked.png",
        output_dir=output_dir,
    )
    return plot_checks, fixture_evidence


def _real_fixture_preview(
    fixture: Path,
) -> tuple[PreviewWidget, dict[str, Any]]:
    fixture = fixture.expanduser().resolve()
    fixture_evidence = _fixture_evidence(fixture)
    original = load_gdf_file(str(fixture))
    if original is None:
        raise RuntimeError(f"Could not load the real EEG fixture: {fixture}")
    current = original.copy()

    channel_names = [str(name) for name in current.get_mne().ch_names]
    selected_channel = "EEG-C3" if "EEG-C3" in channel_names else channel_names[0]
    publication = _real_fixture_render_publication(
        current=current,
        original=original,
        channel_index=channel_names.index(selected_channel),
    )
    render_data = publication.data
    if (
        render_data.sampling_frequency is None
        or render_data.current is None
        or render_data.original is None
    ):
        raise RuntimeError("The real EEG fixture did not publish both signal copies.")

    preview = PreviewWidget()
    preview.resize(QSize(920, 620))
    preview.chan_combo.addItems(list(render_data.channels))
    preview.chan_combo.setCurrentText(selected_channel)

    # Frequency must be active when the product plotter runs so both domains
    # are populated from the same real five-second source window.
    preview.plot_tabs.setCurrentIndex(1)
    plotter = PreprocessPlotter(preview)
    plotter.plot_sample_data(publication)
    preview.plot_tabs.setCurrentIndex(0)
    fixture_evidence.update(
        {
            "sampling_rate_hz": render_data.sampling_frequency,
            "channel_count": len(render_data.channels),
            "selected_channel": render_data.selected_channel_name,
            "sample_window_start_seconds": float(preview.time_spin.value()),
            "sample_window_duration_seconds": 5.0,
            "plot_data_origin": (
                "PreprocessPlotter rendering a detached application publication "
                "copied from the checked-in EEG fixture"
            ),
        }
    )
    return preview, fixture_evidence


def _real_fixture_render_publication(
    *,
    current: Any,
    original: Any,
    channel_index: int,
) -> PreprocessRenderPublication:
    state = ApplicationStateSnapshot.empty()
    view_publication = ApplicationViewPublication(
        generation=1,
        state=state,
        capabilities=build_capability_policy(state),
    )
    return PreprocessRenderPublisher(
        dataset=_RealFixtureProjection(current=current, original=original),
        get_publication=lambda: view_publication,
    ).publish(
        PreprocessRenderRequest(
            publication_generation=view_publication.generation,
            channel_index=channel_index,
            start_seconds=0.0,
            duration_seconds=5.0,
        )
    )


def _observe_loaded_preview_plots(
    preview: PreviewWidget,
) -> list[dict[str, Any]]:
    curves = (
        ("time_original", preview.time_original_curve),
        ("time_current", preview.time_current_curve),
        ("psd_original", preview.freq_original_curve),
        ("psd_current", preview.freq_current_curve),
    )
    checks: list[dict[str, Any]] = []
    for name, curve in curves:
        x_data, y_data = curve.getData()
        x = np.asarray(x_data if x_data is not None else [], dtype=float)
        y = np.asarray(y_data if y_data is not None else [], dtype=float)
        finite = bool(
            x.size == y.size
            and x.size >= 3
            and np.isfinite(x).all()
            and np.isfinite(y).all()
        )
        x_range = float(np.ptp(x)) if finite else 0.0
        y_range = float(np.ptp(y)) if finite else 0.0
        passed = bool(finite and x_range > 0.0 and y_range > np.finfo(float).eps)
        check = {
            "curve": name,
            "point_count": int(min(x.size, y.size)),
            "finite": finite,
            "x_range": x_range,
            "y_range": y_range,
            "passed": passed,
        }
        checks.append(check)
        if not passed:
            raise RuntimeError(
                f"Loaded preview has a blank plot curve: {name} "
                f"(points={check['point_count']}, y_range={y_range})."
            )
    return checks


def _capture_preprocess_dialogs(app: QApplication, output_dir: Path) -> None:
    filtering = FilteringDialog(None, sampling_rate_hz=250.0)
    _capture(
        app,
        filtering,
        "preprocess-filtering-dialog.png",
        output_dir=output_dir,
    )

    filtering = FilteringDialog(None, sampling_rate_hz=250.0)
    filtering.h_freq_spin.setValue(130.0)
    _capture(
        app,
        filtering,
        "preprocess-filtering-invalid.png",
        output_dir=output_dir,
    )

    channel_names = ["Fz", "C3", "Cz", "C4", "Pz"]
    rereference = RereferenceDialog(None, channel_names)
    _capture(
        app,
        rereference,
        "preprocess-rereference-average.png",
        output_dir=output_dir,
    )

    rereference = RereferenceDialog(None, channel_names)
    rereference.selected_channels_radio.setChecked(True)
    c3_item = rereference.chan_list.item(1)
    c4_item = rereference.chan_list.item(3)
    if c3_item is None or c4_item is None:
        raise RuntimeError("Re-reference capture channels are unavailable.")
    c3_item.setSelected(True)
    c4_item.setSelected(True)
    _capture(
        app,
        rereference,
        "preprocess-rereference-selected.png",
        output_dir=output_dir,
    )

    rereference = RereferenceDialog(None, channel_names)
    rereference.selected_channels_radio.setChecked(True)
    _capture(
        app,
        rereference,
        "preprocess-rereference-selection-required.png",
        output_dir=output_dir,
    )

    _capture(
        app,
        NormalizeDialog(None),
        "preprocess-normalize-dialog.png",
        output_dir=output_dir,
    )
    _capture(
        app,
        ResampleDialog(None),
        "preprocess-resample-dialog.png",
        output_dir=output_dir,
    )

    history_container = QWidget()
    history_layout = QVBoxLayout(history_container)
    history_layout.setContentsMargins(12, 12, 12, 12)
    history = TrainingHistoryTable(history_container)
    history_layout.addWidget(history)
    history_container.resize(QSize(1144, history.preferred_content_height() + 24))
    _capture(
        app,
        history_container,
        "training-history-empty.png",
        output_dir=output_dir,
    )


def _capture_training_setting_surfaces(
    app: QApplication,
    output_dir: Path,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    dialog: TrainingSettingDialog | None = None
    try:
        for scale in TRAINING_FONT_SCALES:
            dialog = _training_setting_dialog()
            _apply_training_setting_font_scale(dialog, scale)
            dialog.show()
            _settle_widget(app, dialog)
            checks.append(
                _observe_training_setting_geometry(
                    dialog,
                    font_scale=scale,
                )
            )
            filename = TRAINING_SETTING_SURFACES[round(scale * 100)]
            _capture(
                app,
                dialog,
                filename,
                output_dir=output_dir,
            )
            dialog = None
    finally:
        if dialog is not None:
            _dispose_widget(app, dialog)
    return checks


def _font_at_scale(font: QFont, scale: float) -> QFont:
    if scale <= 0:
        raise ValueError("Font scale must be positive.")
    scaled = QFont(font)
    if font.pointSizeF() > 0:
        scaled.setPointSizeF(font.pointSizeF() * scale)
    elif font.pixelSize() > 0:
        scaled.setPixelSize(max(round(font.pixelSize() * scale), 1))
    else:
        raise RuntimeError("The application font has no scalable size.")
    return scaled


def _training_setting_dialog() -> TrainingSettingDialog:
    return TrainingSettingDialog(
        None,
        None,
        initial_option={"device": "cpu"},
    )


def _apply_training_setting_font_scale(
    dialog: TrainingSettingDialog,
    scale: float,
) -> None:
    """Apply capture-only scaling after BaseDialog establishes its baseline font."""
    baseline = QFont(dialog.font())
    scaled = _font_at_scale(baseline, scale)
    dialog.setProperty("capture_base_font_point_size", baseline.pointSizeF())
    dialog.setProperty("capture_font_scale", float(scale))
    dialog.setFont(scaled)
    if scaled.pointSizeF() > 0:
        dialog.setStyleSheet(
            f"{dialog.styleSheet()}\n"
            "QDialog, QDialog QWidget { "
            f"font-size: {scaled.pointSizeF():.3f}pt; "
            "}"
        )
    dialog._fit_dialog_to_content()


def _observe_training_setting_geometry(
    dialog: TrainingSettingDialog,
    *,
    font_scale: float,
) -> dict[str, Any]:
    form_layout = dialog.form_layout
    rows: list[dict[str, Any]] = []
    for row_index in range(form_layout.rowCount()):
        label_item = form_layout.itemAtPosition(row_index, 0)
        input_item = form_layout.itemAtPosition(row_index, 1)
        label = label_item.widget() if label_item is not None else None
        input_widget = input_item.widget() if input_item is not None else None
        if not isinstance(label, QLabel) or input_widget is None:
            raise RuntimeError(
                f"Training Setting row {row_index} has incomplete form geometry."
            )

        label_rect = _widget_rect_in(dialog, label)
        input_rect = _widget_rect_in(dialog, input_widget)
        overlap = label_rect.intersects(input_rect)
        label_text_clipped = _control_text_is_clipped(label)
        input_text_clipped = _control_text_is_clipped(input_widget)
        contained = dialog.rect().contains(label_rect) and dialog.rect().contains(
            input_rect
        )
        horizontal_gap = input_rect.left() - label_rect.right() - 1
        rows.append(
            {
                "row": row_index,
                "label": " ".join(label.text().split()),
                "label_geometry": _rect_payload(label_rect),
                "input_type": type(input_widget).__name__,
                "input_geometry": _rect_payload(input_rect),
                "horizontal_gap_px": int(horizontal_gap),
                "overlap": overlap,
                "label_text_clipped": label_text_clipped,
                "input_text_clipped": input_text_clipped,
                "contained_in_dialog": contained,
                "passed": (
                    not overlap
                    and not label_text_clipped
                    and not input_text_clipped
                    and contained
                    and horizontal_gap >= 0
                ),
            }
        )

    overlap_rows = [
        row for row in rows if row["overlap"] or row["horizontal_gap_px"] < 0
    ]
    clipped_rows = [
        row for row in rows if row["label_text_clipped"] or row["input_text_clipped"]
    ]
    outside_rows = [row for row in rows if not row["contained_in_dialog"]]
    if overlap_rows:
        raise RuntimeError(
            "Training Setting overlap at "
            f"{round(font_scale * 100)}%: {overlap_rows[0]['label']}."
        )
    if clipped_rows:
        raise RuntimeError(
            "Training Setting clipped text at "
            f"{round(font_scale * 100)}%: {clipped_rows[0]['label']}."
        )
    if outside_rows:
        raise RuntimeError(
            "Training Setting control outside dialog at "
            f"{round(font_scale * 100)}%: {outside_rows[0]['label']}."
        )

    return {
        "font_scale": float(font_scale),
        "font_scale_percent": round(font_scale * 100),
        "base_font_point_size": float(
            dialog.property("capture_base_font_point_size")
            or dialog.font().pointSizeF()
        ),
        "font_point_size": float(dialog.font().pointSizeF()),
        "dialog_size": [dialog.width(), dialog.height()],
        "row_count": len(rows),
        "overlap_count": len(overlap_rows),
        "clipped_text_count": len(clipped_rows),
        "outside_dialog_count": len(outside_rows),
        "rows": rows,
        "passed": bool(rows) and all(bool(row["passed"]) for row in rows),
    }


def _widget_rect_in(ancestor: QWidget, widget: QWidget) -> QRect:
    top_left = widget.mapTo(ancestor, QPoint(0, 0))
    return QRect(top_left, widget.size())


def _rect_payload(rect: QRect) -> list[int]:
    return [rect.x(), rect.y(), rect.width(), rect.height()]


def _control_text_is_clipped(widget: QWidget) -> bool:
    text = _control_text(widget)
    if not text:
        return False
    contents = widget.contentsRect()
    metrics = widget.fontMetrics()
    if isinstance(widget, QLabel):
        margin = max(widget.margin(), 0)
        available_width = max(contents.width() - 2 * margin, 0)
        available_height = max(contents.height() - 2 * margin, 0)
        if widget.wordWrap():
            required_height = widget.heightForWidth(available_width)
            return required_height < 0 or required_height > available_height
        return (
            metrics.horizontalAdvance(text) > available_width
            or metrics.lineSpacing() > available_height
        )
    if isinstance(widget, QComboBox):
        available_width = max(contents.width() - 30, 0)
        return metrics.horizontalAdvance(text) > available_width
    if isinstance(widget, QLineEdit):
        available_width = max(contents.width() - 12, 0)
        return metrics.horizontalAdvance(text) > available_width
    if isinstance(widget, QAbstractButton):
        return widget.sizeHint().width() > widget.width()
    return False


def _capture_smart_parser_modes(app: QApplication, output_dir: Path) -> None:
    modes = (
        (
            "simple",
            "radio_split",
            ["Sub01_Ses01.gdf", "Sub02_Ses01.gdf", "Sub03_Ses02.gdf"],
        ),
        (
            "regex",
            "radio_regex",
            [
                "sub-01_ses-01_task-mi_run-01_eeg.gdf",
                "sub-02_ses-01_task-mi_run-02_eeg.gdf",
                "sub-03_ses-02_task-mi_run-01_eeg.gdf",
            ],
        ),
        (
            "folder",
            "radio_folder",
            [
                "/capture/Subject01/ses-01/eeg01.gdf",
                "/capture/Subject02/ses-01/eeg02.gdf",
                "/capture/Subject03/ses-02/eeg03.gdf",
            ],
        ),
        ("fixed", "radio_fixed", ["A01T.gdf", "A02E.gdf", "A03T.gdf"]),
    )
    for suffix, radio_name, filenames in modes:
        dialog = SmartParserDialog(filenames)
        getattr(dialog, radio_name).setChecked(True)
        if suffix == "simple":
            dialog.split_sep_combo.setCurrentIndex(0)
            dialog.split_sub_idx.setValue(1)
            dialog.split_sess_idx.setValue(2)
        dialog.update_preview()
        _capture(
            app,
            dialog,
            f"smart-parser-{suffix}.png",
            output_dir=output_dir,
        )


def _capture_extended_review_surfaces(
    app: QApplication,
    output_dir: Path,
) -> None:
    saliency_states = (
        ("saliency-setting-empty.png", ()),
        ("saliency-setting-single-method.png", ("SmoothGrad",)),
        (
            "saliency-setting-multi-method.png",
            ("SmoothGrad", "SmoothGrad_Squared", "VarGrad"),
        ),
    )
    for filename, selected_methods in saliency_states:
        _capture(
            app,
            _saliency_setting_dialog(selected_methods),
            filename,
            output_dir=output_dir,
        )

    for filename, cross_validation in (
        ("data-splitting-step-2-ratio.png", False),
        ("data-splitting-step-2-cross-validation.png", True),
    ):
        _capture(
            app,
            _data_splitting_step_two_dialog(
                cross_validation=cross_validation,
            ),
            filename,
            output_dir=output_dir,
            compare_child_references=False,
        )


def _saliency_setting_dialog(
    selected_methods: tuple[str, ...],
) -> SaliencySettingDialog:
    dialog = SaliencySettingDialog(None, saliency_params=None)
    unknown = set(selected_methods).difference(dialog.method_checks)
    if unknown:
        raise RuntimeError(f"Unknown saliency methods for capture: {sorted(unknown)}")
    for method, checkbox in dialog.method_checks.items():
        checkbox.setChecked(method in selected_methods)
    return dialog


def _data_splitting_step_two_dialog(
    *,
    cross_validation: bool,
) -> DataSplittingPreviewDialog:
    config = DataSplittingConfig(
        TrainingType.FULL,
        cross_validation,
        [DataSplitterHolder(True, ValSplitByType.TRIAL)],
        [DataSplitterHolder(True, SplitByType.TRIAL)],
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
    worker = dialog.preview_worker
    if worker is not None:
        worker.join(timeout=2)
        if worker.is_alive():
            raise RuntimeError("Data-splitting capture preview did not finish.")
    dialog.update_table()
    if dialog.preview_debounce_timer is not None:
        dialog.preview_debounce_timer.stop()
    if dialog.timer is not None:
        dialog.timer.stop()
    if dialog.tree is None:
        raise RuntimeError("Data-splitting capture tree is unavailable.")
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
    fold_count = 5 if request.specification.is_cross_validation else 1
    return DatasetSplitPreviewPublication(
        request=request,
        generation=request.publication_generation,
        rows=tuple(
            DatasetSplitPreviewRow(
                name=(f"Fold_{index + 1}" if fold_count > 1 else "Holdout"),
                train_count=76,
                validation_count=20,
                test_count=24,
            )
            for index in range(fold_count)
        ),
    )


def _ready_import_dialog(
    *,
    recipe_loaded: bool = False,
) -> DataInterpretationPreviewDialog:
    source_path = ROOT / "tests" / "fixtures" / "data"
    eeg_path = str(source_path / "sub-01_task-mi_raw.fif")
    preview = {
        "summary": "Found 1 EEG file(s).",
        "selected_eeg_files": [eeg_path],
        "source_selection": "Single file",
        "metadata_preview": [
            {
                "file": "sub-01_task-mi_raw.fif",
                "subject": {"value": "01", "decision": "safe"},
                "session": {"value": None, "decision": "safe"},
                "task": {"value": "mi", "decision": "safe"},
                "run": {"value": None, "decision": "safe"},
            }
        ],
        "class_map": {"left": "Left", "right": "Right"},
        "resource_preflight": {
            "risk_level": "safe",
            "required_memory_bytes": 512 * 1024**2,
            "available_memory_bytes": 8 * 1024**3,
        },
    }
    if recipe_loaded:
        preview["recipe_reload_summary"] = {
            "message": "Saved import choices were loaded and revalidated."
        }
    return DataInterpretationPreviewDialog(
        parent=None,
        scan_result={"source_path": str(source_path), "eeg_files": [eeg_path]},
        preview=preview,
        validation_decision={"decision": "safe"},
    )


def _write_evidence_manifest(
    *,
    output_dir: Path,
    source_identity_at_start: dict[str, Any],
    source_identity_at_end: dict[str, Any],
    fixture_evidence: dict[str, Any],
    geometry_checks: list[dict[str, Any]],
    plot_checks: list[dict[str, Any]],
    generated_at: datetime,
    qt_platform: str,
) -> None:
    source_digest_at_start = str(source_identity_at_start.get("source_digest") or "")
    source_digest_at_end = str(source_identity_at_end.get("source_digest") or "")
    if (
        not source_digest_at_start
        or not source_digest_at_end
        or source_digest_at_start != source_digest_at_end
    ):
        raise RuntimeError("Product source changed during focused UI capture.")
    commit_sha = str(source_identity_at_end.get("commit_sha") or "")
    head_tree_sha = str(source_identity_at_end.get("head_tree_sha") or "")
    if not commit_sha or not head_tree_sha:
        raise RuntimeError("Focused UI capture has no Git commit/tree identity.")
    if not qt_platform:
        raise RuntimeError("Focused UI capture has no Qt platform identity.")
    if generated_at.tzinfo is None:
        raise RuntimeError("Focused UI capture generated_at must be timezone-aware.")

    failed_geometry = [
        check for check in geometry_checks if not bool(check.get("passed"))
    ]
    if failed_geometry:
        raise RuntimeError(
            f"Observed Training Setting geometry check failed: {failed_geometry[0]}."
        )
    observed_scales = {
        int(check.get("font_scale_percent", 0)) for check in geometry_checks
    }
    expected_scales = {round(scale * 100) for scale in TRAINING_FONT_SCALES}
    if observed_scales != expected_scales:
        raise RuntimeError(
            "Training Setting geometry evidence does not cover "
            "100%, 125%, and 150% font scales."
        )

    failed_plots = [check for check in plot_checks if not bool(check.get("passed"))]
    if failed_plots:
        raise RuntimeError(
            f"Observed loaded preview plot check failed: {failed_plots[0]}."
        )
    observed_plot_surfaces = {str(check.get("surface") or "") for check in plot_checks}
    if observed_plot_surfaces != {
        "preprocess-loaded.png",
        "preprocess-loaded-psd.png",
    }:
        raise RuntimeError("Loaded preview evidence must cover time and PSD surfaces.")

    screenshots = collect_screenshot_artifacts(
        {filename: output_dir / filename for filename in REVIEWER_FIX_SURFACES}
    )
    missing = [
        filename
        for filename, metadata in screenshots.items()
        if not metadata.get("readable")
    ]
    if missing:
        raise RuntimeError(f"Focused UI captures are missing or unreadable: {missing}")
    for filename, metadata in screenshots.items():
        metadata["path"] = filename
    payload = {
        "schema_version": 2,
        "artifact_type": "xbrainlab.ui_reviewer_fixes",
        "generator": "scripts/dev/capture_ui_reviewer_fixes.py",
        "generated_at": generated_at.isoformat(),
        "qt_platform": qt_platform,
        "source_capture": {
            "source_digest_at_start": source_digest_at_start,
            "source_digest_at_end": source_digest_at_end,
            "commit_sha": commit_sha,
            "head_tree_sha": head_tree_sha,
        },
        "source_identity_at_start": source_identity_at_start,
        "source_identity_at_end": source_identity_at_end,
        "source_identity": source_identity_at_end,
        "fixture": fixture_evidence,
        "observed_geometry_checks": {
            "training_setting": geometry_checks,
        },
        "observed_plot_checks": plot_checks,
        "required_surfaces": list(REVIEWER_FIX_SURFACES),
        "screenshots": screenshots,
        "passed": True,
    }
    temporary = output_dir / f".{EVIDENCE_FILENAME}.tmp"
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output_dir / EVIDENCE_FILENAME)


def _fixture_evidence(fixture: Path) -> dict[str, Any]:
    fixture = fixture.expanduser().resolve()
    if not fixture.is_file():
        raise RuntimeError(f"Real EEG fixture is missing: {fixture}")
    byte_size = fixture.stat().st_size
    if byte_size <= 0:
        raise RuntimeError(f"Real EEG fixture is empty: {fixture}")
    digest = hashlib.sha256()
    with fixture.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    try:
        path = fixture.relative_to(ROOT).as_posix()
    except ValueError:
        path = str(fixture)
    return {
        "path": path,
        "sha256": digest.hexdigest(),
        "byte_size": byte_size,
    }


def _publish_capture(staging_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in REVIEWER_FIX_SURFACES:
        (staging_dir / filename).replace(output_dir / filename)
    (staging_dir / EVIDENCE_FILENAME).replace(output_dir / EVIDENCE_FILENAME)


def _capture(
    app: QApplication,
    widget: QWidget,
    filename: str,
    *,
    output_dir: Path,
    dispose: bool = True,
    loaded_plot: str | None = None,
    compare_child_references: bool = True,
) -> dict[str, Any]:
    _settle_widget(app, widget)
    output = output_dir / filename
    first = output.with_name(f".{output.stem}-frame-1.png")
    try:
        _save_capture(widget, first)
        _assert_reviewer_surface_pixels(
            widget,
            first,
            compare_child_references=compare_child_references,
        )
        if loaded_plot is not None:
            _observe_visible_plot_pixels(
                cast(PreviewWidget, widget),
                first,
                plot_name=loaded_plot,
                surface=filename,
            )
        app.processEvents()
        widget.repaint()
        time.sleep(0.04)
        app.processEvents()
        _save_capture(widget, output)
        _assert_reviewer_surface_pixels(
            widget,
            output,
            compare_child_references=compare_child_references,
        )
        plot_check = (
            _observe_visible_plot_pixels(
                cast(PreviewWidget, widget),
                output,
                plot_name=loaded_plot,
                surface=filename,
            )
            if loaded_plot is not None
            else {}
        )
        changed_ratio = assert_consecutive_complete_frames(first, output)
        if plot_check:
            plot_check["consecutive_frame_changed_pixel_ratio"] = float(changed_ratio)
        return plot_check
    finally:
        first.unlink(missing_ok=True)
        if dispose:
            _dispose_widget(app, widget)


def _settle_widget(app: QApplication, widget: QWidget) -> None:
    widget.show()
    for _ in range(4):
        layout = widget.layout()
        if layout is not None:
            layout.activate()
        app.processEvents()
        widget.repaint()
        time.sleep(0.01)


def _dispose_widget(app: QApplication, widget: QWidget) -> None:
    # PreviewWidget.closeEvent quiesces timers/proxies; Qt's parent tree owns
    # native PlotWidget and scene destruction.
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _observe_visible_plot_pixels(
    preview: PreviewWidget,
    screenshot: Path,
    *,
    plot_name: str,
    surface: str,
) -> dict[str, Any]:
    if plot_name == "time":
        plot = preview.plot_time
    elif plot_name == "psd":
        plot = preview.plot_freq
    else:
        raise ValueError(f"Unknown loaded preview plot: {plot_name}")

    viewport = plot.viewport()
    if viewport is None:
        raise RuntimeError(f"Loaded preview has no plot viewport: {plot_name}.")
    top_left = viewport.mapTo(preview, QPoint(0, 0))
    with Image.open(screenshot) as source:
        image = source.convert("RGB")
        scale_x = image.width / max(preview.width(), 1)
        scale_y = image.height / max(preview.height(), 1)
        bounds = (
            round(top_left.x() * scale_x),
            round(top_left.y() * scale_y),
            round((top_left.x() + viewport.width()) * scale_x),
            round((top_left.y() + viewport.height()) * scale_y),
        )
        region = image.crop(bounds)
    if region.width <= 0 or region.height <= 0:
        raise RuntimeError(f"Loaded preview has a blank plot region: {plot_name}.")

    targets = [
        QColor(Theme.CHART_PRIMARY).getRgb()[:3],
        QColor(Theme.CHART_ORIGINAL_DATA).getRgb()[:3],
    ]
    pixels = np.asarray(region, dtype=np.int16).reshape(-1, 3)
    target_values = np.asarray(targets, dtype=np.int16)
    target_distance = np.max(
        np.abs(pixels[:, np.newaxis, :] - target_values[np.newaxis, :, :]),
        axis=2,
    )
    curve_pixels = int(np.count_nonzero(np.any(target_distance <= 56, axis=1)))
    contrast = float(ImageStat.Stat(region.convert("L")).stddev[0])
    passed = contrast >= 2.0 and curve_pixels >= 8
    check = {
        "surface": surface,
        "plot": plot_name,
        "bounds": list(bounds),
        "contrast": contrast,
        "curve_color_pixel_count": int(curve_pixels),
        "passed": passed,
    }
    if not passed:
        raise RuntimeError(
            f"Loaded preview has a blank plot: {plot_name} "
            f"(contrast={contrast:.2f}, curve pixels={curve_pixels})."
        )
    return check


def _save_capture(widget: QWidget, output: Path) -> None:
    pixmap = widget.grab()
    if pixmap.isNull() or not pixmap.save(str(output)):
        raise RuntimeError(f"Could not capture {output}.")
    with Image.open(output) as captured:
        normalized = captured.convert("RGB")
        extrema = cast(tuple[float, float], normalized.convert("L").getextrema())
        if extrema[1] - extrema[0] < 12:
            raise RuntimeError(f"Capture is visually blank: {output}.")
        normalized.save(output, format="PNG", optimize=True)


def _assert_reviewer_surface_pixels(
    widget: QWidget,
    screenshot: Path,
    *,
    compare_child_references: bool = True,
) -> None:
    required: dict[str, QWidget] = {
        f"{type(widget).__name__} complete surface": widget,
    }
    controls: list[QWidget] = [
        *widget.findChildren(QLabel),
        *widget.findChildren(QAbstractButton),
        *widget.findChildren(QComboBox),
        *widget.findChildren(QAbstractItemView),
    ]
    for index, control in enumerate(controls):
        if not control.isVisibleTo(widget):
            continue
        if isinstance(control, QHeaderView):
            # A scrollable table header can be wider than its clipped viewport;
            # the owning table region below already verifies the painted result.
            continue
        text = _control_text(control)
        has_readable_text = bool(
            text and any(character.isalnum() for character in text)
        )
        if isinstance(control, QAbstractItemView) or has_readable_text:
            name = control.objectName() or type(control).__name__
            required[f"{name} {index}: {text[:48]}"] = control

    with Image.open(screenshot) as captured:
        scale_x = captured.width / max(widget.width(), 1)
        scale_y = captured.height / max(widget.height(), 1)
    for surface_name, control in required.items():
        top_left = control.mapTo(widget, QPoint(0, 0))
        bottom_right = control.mapTo(widget, control.rect().bottomRight())
        if not widget.rect().contains(top_left) or not widget.rect().contains(
            bottom_right
        ):
            raise RuntimeError(
                f"{surface_name} is clipped outside the captured widget."
            )
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
            max_black_ratio=0.20,
        )
        if control is not widget and not compare_child_references:
            continue
        is_text = isinstance(control, (QLabel, QAbstractButton, QComboBox))
        assert_region_matches_reference(
            screenshot,
            bounds,
            _pixmap_image(control.grab()),
            surface_name=surface_name,
            minimum_edge_recall=0.70 if is_text else 0.42,
            maximum_changed_pixel_ratio=1.0 if is_text else 0.55,
        )


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
    data = bytes(cast(Any, buffer.data()))
    buffer.close()
    with Image.open(BytesIO(data)) as source:
        image = source.convert("RGB")
        image.load()
    return image


if __name__ == "__main__":
    raise SystemExit(main())
