from __future__ import annotations

import inspect
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image
from PyQt6.QtCore import QPoint, QRect, QSize
from PyQt6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QLabel,
    QProxyStyle,
    QStyle,
    QWidget,
)

import scripts.dev.capture_ui_reviewer_fixes as capture_script
from XBrainLab.backend.application.preprocess_render import (
    PreprocessRenderPublication,
    PreprocessSignalState,
)

FIXTURE = Path("tests/fixtures/data/A01T.gdf").resolve()


def _settle(qapp: QApplication, widget) -> None:
    widget.show()
    for _ in range(3):
        layout = widget.layout()
        if layout is not None:
            layout.activate()
        qapp.processEvents()


def _dispose(qapp: QApplication, widget) -> None:
    prepare_for_shutdown = getattr(widget, "prepare_for_shutdown", None)
    if callable(prepare_for_shutdown):
        prepare_for_shutdown()
    widget.close()
    widget.deleteLater()
    qapp.processEvents()


def _identity() -> dict[str, object]:
    return {
        "version": 3,
        "repo_root": str(capture_script.ROOT),
        "branch": "test-branch",
        "commit_sha": "a" * 40,
        "head_tree_sha": "b" * 40,
        "dirty": True,
        "dirty_digest": "c" * 64,
        "source_content_digest": "d" * 64,
        "source_digest": "e" * 64,
        "untracked_source_count": 1,
        "excluded_generated_prefixes": ["artifacts/"],
        "excluded_local_paths": ["settings.json"],
        "included_file_policy": "all-non-generated-tracked-and-untracked-files",
        "error": "",
    }


def test_dispose_widget_tolerates_an_already_deleted_qt_wrapper(qapp) -> None:
    class DeletedWidget:
        def close(self) -> None:
            raise RuntimeError("wrapped C/C++ object of type QWidget has been deleted")

    capture_script._dispose_widget(qapp, DeletedWidget())  # type: ignore[arg-type]


def test_surface_capture_can_skip_scroll_clipped_child_references(
    qapp,
    tmp_path,
) -> None:
    surface = QWidget()
    surface.resize(200, 100)
    QLabel("Training Settings", surface).move(12, 12)
    clipped_child = QLabel("Patience", surface)
    clipped_child.setGeometry(12, 90, 100, 24)
    screenshot = tmp_path / "surface.png"
    try:
        _settle(qapp, surface)
        capture_script._save_capture(surface, screenshot)

        with pytest.raises(RuntimeError, match="clipped outside"):
            capture_script._assert_reviewer_surface_pixels(surface, screenshot)

        capture_script._assert_reviewer_surface_pixels(
            surface,
            screenshot,
            compare_child_references=False,
        )
    finally:
        _dispose(qapp, surface)


def test_surface_inventory_preserves_existing_artifacts_and_adds_review_states() -> (
    None
):
    assert len(capture_script.LEGACY_REVIEWER_FIX_SURFACES) == 29
    assert "preprocess-filtering-toggled.png" in (
        capture_script.LEGACY_REVIEWER_FIX_SURFACES
    )
    assert capture_script.REVIEWER_FIX_SURFACES[:29] == (
        capture_script.LEGACY_REVIEWER_FIX_SURFACES
    )
    assert capture_script.REVIEWER_FIX_SURFACES[29:] == (
        "saliency-setting-empty.png",
        "saliency-setting-single-method.png",
        "saliency-setting-multi-method.png",
        "data-splitting-step-2-ratio.png",
        "data-splitting-step-2-cross-validation.png",
    )


def test_preprocess_dialog_capture_records_both_filter_toggle_states(
    qapp,
    tmp_path,
) -> None:
    capture_script._capture_preprocess_dialogs(qapp, tmp_path)

    initial = tmp_path / "preprocess-filtering-dialog.png"
    toggled = tmp_path / "preprocess-filtering-toggled.png"
    assert initial.is_file()
    assert toggled.is_file()
    assert initial.read_bytes() != toggled.read_bytes()


@pytest.mark.parametrize(
    ("selected_methods", "expected_title", "ok_enabled"),
    [
        ((), "Method parameters", False),
        (("SmoothGrad",), "SmoothGrad parameters", True),
        (
            ("SmoothGrad", "SmoothGrad_Squared", "VarGrad"),
            "Method parameters",
            True,
        ),
    ],
)
def test_saliency_capture_factory_builds_requested_full_content_state(
    qapp,
    selected_methods,
    expected_title,
    ok_enabled,
) -> None:
    dialog = capture_script._saliency_setting_dialog(selected_methods)
    try:
        _settle(qapp, dialog)
        selected = {
            method
            for method, checkbox in dialog.method_checks.items()
            if checkbox.isChecked()
        }
        buttons = dialog.findChild(QDialogButtonBox)
        assert buttons is not None
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        assert ok_button is not None
        assert selected == set(selected_methods)
        assert dialog.params_title.text() == expected_title
        assert ok_button.isEnabled() is ok_enabled
        assert dialog.rect().contains(
            buttons.mapTo(dialog, buttons.rect().bottomRight())
        )
    finally:
        _dispose(qapp, dialog)


@pytest.mark.parametrize(
    ("cross_validation", "expected_split_labels", "expected_test_unit"),
    [
        (False, ["Holdout"], "Ratio"),
        (True, [f"Fold {index}" for index in range(1, 6)], "K Fold"),
    ],
)
def test_data_splitting_step_two_capture_factory_builds_representative_states(
    qapp,
    cross_validation,
    expected_split_labels,
    expected_test_unit,
) -> None:
    dialog = capture_script._data_splitting_step_two_dialog(
        cross_validation=cross_validation
    )
    try:
        _settle(qapp, dialog)
        assert dialog.tree is not None
        assert [
            dialog.tree.topLevelItem(row).text(0)
            for row in range(dialog.tree.topLevelItemCount())
        ] == expected_split_labels
        assert dialog.test_widgets[0][0].currentText() == expected_test_unit
        assert dialog.btn_confirm is not None and dialog.btn_confirm.isEnabled()
        assert dialog.rect().contains(
            dialog.btn_confirm.mapTo(
                dialog,
                dialog.btn_confirm.rect().bottomRight(),
            )
        )
    finally:
        _dispose(qapp, dialog)


def test_extended_review_capture_writes_all_full_content_frames(qapp, tmp_path) -> None:
    original_stylesheet = qapp.styleSheet()
    try:
        qapp.setStyleSheet(capture_script.Stylesheets.MAIN_WINDOW)
        capture_script._capture_extended_review_surfaces(qapp, tmp_path)
    finally:
        qapp.setStyleSheet(original_stylesheet)

    for filename in capture_script.EXTENDED_REVIEW_SURFACES:
        screenshot = tmp_path / filename
        assert screenshot.is_file()
        with Image.open(screenshot) as image:
            assert image.width >= 400
            assert image.height >= 200
            assert image.getbbox() is not None


def test_training_setting_capture_writes_top_and_resource_preview_frames(
    qapp,
    tmp_path,
) -> None:
    checks = capture_script._capture_training_setting_surfaces(qapp, tmp_path)

    assert len(checks) == len(capture_script.TRAINING_FONT_SCALES)
    assert all(check["passed"] is True for check in checks)
    for filename in (
        *capture_script.TRAINING_SETTING_SURFACES.values(),
        *capture_script.TRAINING_SETTING_RESOURCE_PREVIEW_SURFACES.values(),
    ):
        assert (tmp_path / filename).is_file()


def test_real_fixture_preview_populates_time_and_psd_curves(qapp) -> None:
    preview, fixture_evidence = capture_script._real_fixture_preview(FIXTURE)
    try:
        checks = capture_script._observe_loaded_preview_plots(preview)
    finally:
        _dispose(qapp, preview)

    assert fixture_evidence["path"] == "tests/fixtures/data/A01T.gdf"
    assert (
        fixture_evidence["sha256"]
        == "74d900ce83a115509f663c0ac45bd36d56f05be528064743c49b0c2efb5088a3"
    )
    assert fixture_evidence["byte_size"] == FIXTURE.stat().st_size
    assert fixture_evidence["sampling_rate_hz"] == 250.0
    assert fixture_evidence["channel_count"] == 25
    assert fixture_evidence["selected_channel"] == "EEG-C3"
    assert {check["curve"] for check in checks} == {
        "time_original",
        "time_current",
        "psd_original",
        "psd_current",
    }
    assert all(check["passed"] for check in checks)
    assert all(check["point_count"] > 2 for check in checks)
    assert all(check["y_range"] > 0 for check in checks)
    json.dumps({"fixture": fixture_evidence, "plot_checks": checks})


def test_real_fixture_preview_passes_detached_publication_to_plotter(
    qapp,
    monkeypatch,
) -> None:
    observed: dict[str, object] = {}

    class RecordingPlotter:
        def __init__(self, widget) -> None:
            observed["widget"] = widget

        def plot_sample_data(
            self,
            publication: PreprocessRenderPublication,
        ) -> None:
            observed["publication"] = publication

    monkeypatch.setattr(capture_script, "PreprocessPlotter", RecordingPlotter)

    preview, _fixture_evidence = capture_script._real_fixture_preview(FIXTURE)
    try:
        publication = observed["publication"]
        assert observed["widget"] is preview
        assert isinstance(publication, PreprocessRenderPublication)
        assert publication.generation == publication.request.publication_generation
        assert publication.data.state is PreprocessSignalState.RAW
        assert publication.data.selected_channel_name == "EEG-C3"
        assert publication.data.selected_channel_index == (
            publication.data.channels.index("EEG-C3")
        )
        assert publication.data.sampling_frequency == 250.0
        assert publication.data.current is not None
        assert publication.data.original is not None
        assert publication.data.current.values_volts.flags.writeable is False
        assert publication.data.original.values_volts.flags.writeable is False
    finally:
        _dispose(qapp, preview)


def test_real_fixture_preview_uses_only_detached_plotter_api() -> None:
    source = inspect.getsource(capture_script._real_fixture_preview)

    for removed_api in ("controller=", "data_list=", "original_data_list="):
        assert removed_api not in source


def test_loaded_preview_plot_guard_rejects_a_blank_curve(qapp) -> None:
    preview, _fixture_evidence = capture_script._real_fixture_preview(FIXTURE)
    try:
        preview.freq_current_curve.setData([], [])
        with pytest.raises(RuntimeError, match=r"blank plot.*psd_current"):
            capture_script._observe_loaded_preview_plots(preview)
    finally:
        _dispose(qapp, preview)


def test_loaded_capture_path_has_no_synthetic_signal_fallback() -> None:
    source = inspect.getsource(capture_script._capture_preprocess_states)

    assert "_real_fixture_preview" in source
    assert "preprocess-loaded-psd.png" in source
    assert "np.sin" not in source
    assert "np.linspace" not in source


def test_preprocess_dialog_capture_uses_channel_name_rereference_api(
    qapp,
    tmp_path,
) -> None:
    original_stylesheet = qapp.styleSheet()
    try:
        qapp.setStyleSheet(capture_script.Stylesheets.MAIN_WINDOW)
        capture_script._capture_preprocess_dialogs(qapp, tmp_path)
    finally:
        qapp.setStyleSheet(original_stylesheet)

    for filename in (
        "preprocess-rereference-average.png",
        "preprocess-rereference-selected.png",
        "preprocess-rereference-selection-required.png",
    ):
        screenshot = tmp_path / filename
        assert screenshot.is_file()
        with Image.open(screenshot) as image:
            assert image.width > 0
            assert image.height > 0
            assert image.getbbox() is not None


@pytest.mark.parametrize("font_scale", capture_script.TRAINING_FONT_SCALES)
def test_training_setting_geometry_is_observed_at_supported_font_scales(
    qapp,
    font_scale: float,
) -> None:
    app = qapp
    original_stylesheet = app.styleSheet()
    dialog = None
    try:
        app.setStyleSheet(capture_script.Stylesheets.MAIN_WINDOW)
        dialog = capture_script._training_setting_dialog()
        assert dialog.bs_entry is not None
        assert dialog.resource_preview_note is not None
        assert dialog.bs_entry.text() == "32"
        assert dialog.resource_preview_note.isHidden()
        capture_script._apply_training_setting_font_scale(dialog, font_scale)
        _settle(app, dialog)

        check = capture_script._observe_training_setting_geometry(
            dialog,
            font_scale=font_scale,
        )
    finally:
        if dialog is not None:
            _dispose(app, dialog)
        app.setStyleSheet(original_stylesheet)

    assert check["font_scale_percent"] == round(font_scale * 100)
    assert check["passed"] is True
    assert check["dialog_size"][0] >= 664
    assert check["overlap_count"] == 0
    assert check["clipped_text_count"] == 0
    assert len(check["rows"]) == 13
    assert any(row["label"] == "Class loss weighting" for row in check["rows"])
    assert {row["label"] for row in check["rows"]} >= {
        "Early stopping",
        "Patience",
        "Minimum improvement",
    }
    assert check["set_button_count"] == 3
    assert check["footer"]["passed"] is True
    assert check["scrollbar"]["right_gap_px"] <= 1
    assert all(gap >= 30 for gap in check["scrollbar"]["set_horizontal_gaps_px"])
    assert check["scrollbar"]["passed"] is True
    assert check["resource_preview"]["passed"] is True
    assert check["resource_preview"]["visible"] is True
    assert check["resource_preview"]["contained_in_viewport"] is True
    assert check["resource_preview"]["text_complete"] is True
    assert check["resource_preview"]["batch_visible_with_note"] is True
    assert "adjusted to 8" in check["resource_preview"]["text"]
    assert check["font_point_size"] == pytest.approx(
        check["base_font_point_size"] * font_scale
    )
    assert all(row["horizontal_gap_px"] >= 0 for row in check["rows"])
    assert all(row["label_text_clipped"] is False for row in check["rows"])
    assert all(row["overlap"] is False for row in check["rows"])
    assert all(
        row.get("set_button", {}).get("passed", True) is True for row in check["rows"]
    )


@pytest.mark.parametrize("font_scale", capture_script.TRAINING_FONT_SCALES)
@pytest.mark.parametrize("scrollbar_width", [None, 28])
def test_training_setting_scrollbar_clearance_survives_wide_native_scrollbar(
    qapp,
    font_scale: float,
    scrollbar_width: int | None,
) -> None:
    dialog = capture_script._training_setting_dialog()
    try:
        assert dialog.content_scroll is not None
        scroll_bar = dialog.content_scroll.verticalScrollBar()
        assert scroll_bar is not None
        if scrollbar_width is not None:
            scroll_bar.setFixedWidth(scrollbar_width)
        capture_script._apply_training_setting_font_scale(dialog, font_scale)
        _settle(qapp, dialog)
        if scrollbar_width is not None:
            assert scroll_bar.width() == scrollbar_width

        check = capture_script._observe_training_setting_geometry(
            dialog,
            font_scale=font_scale,
        )

        if scrollbar_width is None:
            dialog_layout = dialog.layout()
            assert dialog_layout is not None
            dialog_layout.setContentsMargins(18, 16, 18, 14)
            dialog._fit_dialog_to_content()
            _settle(qapp, dialog)
            with pytest.raises(RuntimeError, match="scrollbar clearance"):
                capture_script._observe_training_setting_geometry(
                    dialog,
                    font_scale=font_scale,
                )
    finally:
        _dispose(qapp, dialog)

    assert check["scrollbar"]["right_gap_px"] <= 1
    assert all(gap >= 30 for gap in check["scrollbar"]["set_horizontal_gaps_px"])
    if scrollbar_width is not None:
        assert check["scrollbar"]["geometry"][2] == scrollbar_width


def test_training_setting_bounds_inflated_native_combo_size_hint(qapp) -> None:
    dialog = capture_script._training_setting_dialog()
    try:
        assert dialog.evaluation_combo is not None
        dialog.evaluation_combo.sizeHint = lambda: QSize(1200, 36)
        dialog._fit_dialog_to_content()
        _settle(qapp, dialog)
        dialog.resize(dialog.width() + 32, dialog.height())
        qapp.processEvents()

        check = capture_script._observe_training_setting_geometry(
            dialog,
            font_scale=1.5,
        )
    finally:
        _dispose(qapp, dialog)

    evaluation = next(row for row in check["rows"] if row["label"] == "Evaluation")
    assert evaluation["contained_in_dialog"] is True
    assert evaluation["input_text_clipped"] is False


def test_training_setting_reserves_native_combo_edit_field_chrome(qapp) -> None:
    class NarrowEditFieldStyle(QProxyStyle):
        def subControlRect(self, control, option, sub_control, widget=None):
            rect = super().subControlRect(control, option, sub_control, widget)
            if (
                control == QStyle.ComplexControl.CC_ComboBox
                and sub_control == QStyle.SubControl.SC_ComboBoxEditField
            ):
                rect.setWidth(max(rect.width() - 190, 0))
            return rect

    dialog = capture_script._training_setting_dialog()
    try:
        assert dialog.evaluation_combo is not None
        native_style = NarrowEditFieldStyle()
        native_style.setParent(dialog.evaluation_combo)
        dialog.evaluation_combo.setStyle(native_style)
        dialog._fit_dialog_to_content()
        _settle(qapp, dialog)

        check = capture_script._observe_training_setting_geometry(
            dialog,
            font_scale=1.5,
        )
    finally:
        _dispose(qapp, dialog)

    evaluation = next(row for row in check["rows"] if row["label"] == "Evaluation")
    assert evaluation["input_text_clipped"] is False


def test_training_setting_reserves_stylesheet_combo_chrome(qapp) -> None:
    dialog = capture_script._training_setting_dialog()
    try:
        assert dialog.evaluation_combo is not None
        capture_script._apply_training_setting_font_scale(dialog, 1.5)
        _settle(qapp, dialog)

        widest = max(
            dialog.evaluation_combo.fontMetrics().horizontalAdvance(
                dialog.evaluation_combo.itemText(index)
            )
            for index in range(dialog.evaluation_combo.count())
        )
        assert dialog.evaluation_combo.width() >= (
            widest + dialog._COMBO_HORIZONTAL_CHROME_FALLBACK
        )
        check = capture_script._observe_training_setting_geometry(
            dialog,
            font_scale=1.5,
        )
    finally:
        _dispose(qapp, dialog)

    evaluation = next(row for row in check["rows"] if row["label"] == "Evaluation")
    assert evaluation["input_text_clipped"] is False


def test_training_setting_geometry_guard_rejects_overlap(qapp) -> None:
    dialog = capture_script._training_setting_dialog()
    try:
        _settle(qapp, dialog)
        checkpoint_label = next(
            label
            for label in dialog.findChildren(QLabel, "TrainingSettingLabel")
            if label.text() == "Checkpoint interval (training epochs)"
        )
        input_top_left = dialog.checkpoint_entry.mapTo(dialog, QPoint(0, 0))
        checkpoint_label.setGeometry(
            QRect(
                input_top_left.x() - 8,
                input_top_left.y(),
                24,
                dialog.checkpoint_entry.height(),
            )
        )

        with pytest.raises(RuntimeError, match=r"overlap.*Checkpoint interval"):
            capture_script._observe_training_setting_geometry(
                dialog,
                font_scale=1.5,
            )
    finally:
        _dispose(qapp, dialog)


def test_training_setting_geometry_guard_rejects_clipped_label(qapp) -> None:
    dialog = capture_script._training_setting_dialog()
    try:
        _settle(qapp, dialog)
        checkpoint_label = next(
            label
            for label in dialog.findChildren(QLabel, "TrainingSettingLabel")
            if label.text() == "Checkpoint interval (training epochs)"
        )
        checkpoint_label.setWordWrap(False)
        checkpoint_label.setFixedWidth(30)

        with pytest.raises(RuntimeError, match=r"clipped text.*Checkpoint interval"):
            capture_script._observe_training_setting_geometry(
                dialog,
                font_scale=1.0,
            )
    finally:
        _dispose(qapp, dialog)


def test_training_setting_geometry_guard_rejects_set_button_overlap(qapp) -> None:
    dialog = capture_script._training_setting_dialog()
    try:
        capture_script._apply_training_setting_font_scale(dialog, 1.5)
        _settle(qapp, dialog)
        assert dialog.opt_btn is not None
        assert dialog.opt_label is not None
        dialog.opt_btn.setGeometry(dialog.opt_label.geometry())

        with pytest.raises(RuntimeError, match="Set-button column"):
            capture_script._observe_training_setting_geometry(
                dialog,
                font_scale=1.5,
            )
    finally:
        _dispose(qapp, dialog)


def test_training_setting_geometry_guard_rejects_hidden_footer(qapp) -> None:
    dialog = capture_script._training_setting_dialog()
    try:
        capture_script._apply_training_setting_font_scale(dialog, 1.5)
        _settle(qapp, dialog)
        button_box = dialog.findChild(QDialogButtonBox)
        assert button_box is not None
        button_box.hide()

        with pytest.raises(RuntimeError, match="footer geometry"):
            capture_script._observe_training_setting_geometry(
                dialog,
                font_scale=1.5,
            )
    finally:
        _dispose(qapp, dialog)


def test_manifest_records_fixture_source_qt_and_observed_checks(tmp_path) -> None:
    for filename in capture_script.REVIEWER_FIX_SURFACES:
        Image.new("RGB", (80, 60), (35, 70, 105)).save(tmp_path / filename)
    fixture_evidence = capture_script._fixture_evidence(FIXTURE)
    geometry_checks = [
        {
            "font_scale_percent": percent,
            "passed": True,
            "overlap_count": 0,
            "clipped_text_count": 0,
            "rows": [],
        }
        for percent in (100, 125, 150)
    ]
    plot_checks = [
        {
            "surface": "preprocess-loaded.png",
            "plot": "time",
            "passed": True,
            "curve_color_pixel_count": 20,
        },
        {
            "surface": "preprocess-loaded-psd.png",
            "plot": "psd",
            "passed": True,
            "curve_color_pixel_count": 20,
        },
    ]
    started = _identity()
    completed = deepcopy(started)
    generated_at = datetime(2026, 7, 30, 10, 30, tzinfo=UTC)

    capture_script._write_evidence_manifest(
        output_dir=tmp_path,
        source_identity_at_start=started,
        source_identity_at_end=completed,
        fixture_evidence=fixture_evidence,
        geometry_checks=geometry_checks,
        plot_checks=plot_checks,
        generated_at=generated_at,
        qt_platform="xcb",
    )

    payload = json.loads(
        (tmp_path / capture_script.EVIDENCE_FILENAME).read_text(encoding="utf-8")
    )
    assert payload["generated_at"] == generated_at.isoformat()
    assert payload["qt_platform"] == "xcb"
    assert payload["source_capture"] == {
        "source_digest_at_start": "e" * 64,
        "source_digest_at_end": "e" * 64,
        "commit_sha": "a" * 40,
        "head_tree_sha": "b" * 40,
    }
    assert payload["fixture"] == fixture_evidence
    assert payload["observed_geometry_checks"]["training_setting"] == geometry_checks
    assert payload["observed_plot_checks"] == plot_checks
    assert payload["passed"] is True


def test_manifest_rejects_failed_geometry_or_changed_source(tmp_path) -> None:
    for filename in capture_script.REVIEWER_FIX_SURFACES:
        Image.new("RGB", (80, 60), (35, 70, 105)).save(tmp_path / filename)
    started = _identity()
    completed = deepcopy(started)
    failed_geometry = [
        {
            "font_scale_percent": 150,
            "passed": False,
            "overlap_count": 1,
            "clipped_text_count": 0,
            "rows": [],
        }
    ]
    kwargs = {
        "output_dir": tmp_path,
        "source_identity_at_start": started,
        "source_identity_at_end": completed,
        "fixture_evidence": capture_script._fixture_evidence(FIXTURE),
        "geometry_checks": failed_geometry,
        "plot_checks": [{"surface": "loaded", "passed": True}],
        "generated_at": datetime(2026, 7, 30, 10, 30, tzinfo=UTC),
        "qt_platform": "xcb",
    }

    with pytest.raises(RuntimeError, match="geometry check failed"):
        capture_script._write_evidence_manifest(**kwargs)

    kwargs["geometry_checks"] = [
        {
            "font_scale_percent": 150,
            "passed": True,
            "overlap_count": 0,
            "clipped_text_count": 0,
            "rows": [],
        }
    ]
    changed = deepcopy(completed)
    changed["source_digest"] = "f" * 64
    kwargs["source_identity_at_end"] = changed
    with pytest.raises(RuntimeError, match="source changed"):
        capture_script._write_evidence_manifest(**kwargs)


def test_manifest_rejects_failed_plot_check(tmp_path) -> None:
    for filename in capture_script.REVIEWER_FIX_SURFACES:
        Image.new("RGB", (80, 60), (35, 70, 105)).save(tmp_path / filename)
    identity = _identity()

    with pytest.raises(RuntimeError, match="plot check failed"):
        capture_script._write_evidence_manifest(
            output_dir=tmp_path,
            source_identity_at_start=identity,
            source_identity_at_end=deepcopy(identity),
            fixture_evidence=capture_script._fixture_evidence(FIXTURE),
            geometry_checks=[
                {
                    "font_scale_percent": percent,
                    "passed": True,
                    "overlap_count": 0,
                    "clipped_text_count": 0,
                    "rows": [],
                }
                for percent in (100, 125, 150)
            ],
            plot_checks=[
                {
                    "surface": "preprocess-loaded.png",
                    "plot": "time",
                    "passed": False,
                    "curve_color_pixel_count": 0,
                },
                {
                    "surface": "preprocess-loaded-psd.png",
                    "plot": "psd",
                    "passed": True,
                    "curve_color_pixel_count": 20,
                },
            ],
            generated_at=datetime(2026, 7, 30, 10, 30, tzinfo=UTC),
            qt_platform="xcb",
        )
