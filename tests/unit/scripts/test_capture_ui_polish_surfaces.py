from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from PIL import Image, ImageDraw
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QAbstractButton, QApplication

from scripts.dev.app_polish_capture_contract import (
    APP_POLISH_SURFACES,
    _validate_training_history_visual_pair,
    build_app_polish_evidence,
    validate_app_polish_evidence,
)
from scripts.dev.capture_ui_polish_surfaces import (
    BIDS_EPOCH_SCREENSHOT,
    DEFAULT_OUTPUT_DIR,
    INTERNAL_EPOCH_SCREENSHOT,
    _apply_capture_application_theme,
    _assert_capture_geometry,
    _assert_surface_pixels,
    _assert_training_history_reference_pixels,
    _assistant_active_turn_narrow,
    _assistant_failed_standard,
    _assistant_loading_standard,
    _assistant_recovery_standard,
    _assistant_setup_required_narrow,
    _capture,
    _data_splitting_preview_dialog,
    _data_splitting_preview_semantics,
    _epoching_bids_interval_duration_dialog,
    _epoching_internal_events_dialog,
    _evaluation_controls_panel,
    _publish_capture,
    _settle_capture_widget,
    _surface_contract,
    _training_history_few_rows,
    _training_history_many_rows,
    _training_history_semantics,
    _write_readme,
)
from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
)
from scripts.dev.human_like_walkthrough.evidence import (
    assistant_composer_placeholder_evidence,
)
from scripts.dev.human_like_walkthrough.readiness import (
    assert_consecutive_complete_frames,
)
from XBrainLab.ui.styles.stylesheets import Stylesheets


def test_data_splitting_preview_capture_uses_current_worker_lifecycle(qtbot) -> None:
    dialog = _data_splitting_preview_dialog()
    qtbot.addWidget(dialog)

    assert dialog.preview_worker is not None
    assert not dialog.preview_worker.is_alive()
    assert dialog.tree is not None
    assert dialog.tree.topLevelItemCount() == 5
    dialog.show()
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    _settle_capture_widget(app, dialog)
    _assert_capture_geometry("data-splitting-preview-dialog.png", dialog)
    semantics = _data_splitting_preview_semantics(dialog)
    assert semantics["split_unit"] == "K Fold"
    assert semantics["k_fold_count"] == 5
    assert [row["name"] for row in semantics["dataset_rows"]] == [
        "Fold_0",
        "Fold_1",
        "Fold_2",
        "Fold_3",
        "Fold_4",
    ]


def test_data_splitting_preview_rejects_k_fold_row_mismatch(qtbot) -> None:
    dialog = _data_splitting_preview_dialog()
    qtbot.addWidget(dialog)
    _combo, entry = dialog.test_widgets[0]
    entry.blockSignals(True)
    entry.setText("2")

    with pytest.raises(RuntimeError, match="row count are inconsistent"):
        _data_splitting_preview_semantics(dialog)


@pytest.mark.parametrize(
    ("factory", "filename", "scenario"),
    [
        (
            _epoching_internal_events_dialog,
            INTERNAL_EPOCH_SCREENSHOT,
            "internal_events",
        ),
        (
            _epoching_bids_interval_duration_dialog,
            BIDS_EPOCH_SCREENSHOT,
            "bids_interval_duration",
        ),
    ],
)
def test_epoch_capture_contract_requires_complete_visible_controls(
    qtbot,
    factory,
    filename,
    scenario,
) -> None:
    dialog = factory()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(20)

    _assert_capture_geometry(filename, dialog)
    contract = _surface_contract(filename, dialog)

    assert contract["scenario"] == scenario
    assert contract["selected_event_count"] > 0
    assert contract["primary_action"] == "Create EEG Epochs"
    assert contract["cancel_action"] == "Cancel"
    assert "Create EEG Epochs" in contract["verified_controls"]
    assert "Cancel" in contract["verified_controls"]
    if scenario == "internal_events":
        assert contract["placement_method"] == "internal_events"
        assert contract["window_mode"] == "event_locked"
    else:
        assert contract["placement_method"] == "interval"
        assert contract["label_field"] == "trial_type"
        assert contract["window_mode"] == "duration"


def test_bids_epoch_capture_rejects_missing_primary_action(qtbot) -> None:
    dialog = _epoching_bids_interval_duration_dialog()
    qtbot.addWidget(dialog)
    dialog.show()
    primary = dialog.findChild(QAbstractButton, "EpochPrimaryButton")
    assert primary is not None
    primary.hide()

    with pytest.raises(RuntimeError, match="Create EEG Epochs"):
        _assert_capture_geometry(BIDS_EPOCH_SCREENSHOT, dialog)


def test_assistant_setup_capture_is_a_valid_320px_state(qtbot) -> None:
    panel = _assistant_setup_required_narrow()
    qtbot.addWidget(panel)
    panel.show()
    _settle_capture_widget(QApplication.instance(), panel)

    _assert_capture_geometry("assistant-setup-required-narrow.png", panel)

    assert panel.width() == 320
    assert panel._runtime_phase.value == "idle"
    assert panel.is_processing is False
    assert not hasattr(panel, "mode_selector_widget")
    assert panel.setup_btn.isVisible()
    assert panel.send_btn.text() == "Send"
    assert panel.send_btn.isEnabled() is False


def test_assistant_setup_pixel_gate_accepts_transparent_composer_input(
    qtbot,
    tmp_path,
) -> None:
    panel = _assistant_setup_required_narrow()
    qtbot.addWidget(panel)
    panel.show()

    evidence = _capture(panel, tmp_path / "assistant-setup.png")

    assert evidence["capture_method"] == "QWidget.grab"
    assert evidence["reference_validated"] is True
    assert "Assistant input" in evidence["required_regions"]
    assert "Assistant runtime title" in evidence["required_regions"]
    assert "Assistant runtime detail" in evidence["required_regions"]
    assert any(
        str(region).endswith("Open Assistant Settings")
        for region in evidence["required_regions"]
    )
    assert "Assistant runtime feedback" not in evidence["required_regions"]


def test_assistant_active_turn_capture_is_ready_before_processing(qtbot) -> None:
    panel = _assistant_active_turn_narrow()
    qtbot.addWidget(panel)
    panel.show()

    assert panel.width() == 420
    assert panel._runtime_phase.value == "ready"
    assert panel.is_processing is True
    assert not hasattr(panel, "mode_selector_widget")
    assert panel._turn_presentation.phase.value == "working"
    assert panel._turn_presentation.cancelability.value == "cancellable"
    assert not panel.turn_activity_widget.isHidden()
    assert panel.turn_activity_title.text() == "Preparing your request"
    assert panel.send_btn.text() == "Stop"
    assert panel.send_btn.isEnabled() is True
    assert panel.input_field.isEnabled() is False
    assert panel.setup_btn.isHidden()
    assert panel.scroll_area is not None
    scrollbar = panel.scroll_area.horizontalScrollBar()
    assert scrollbar is not None
    assert scrollbar.maximum() == 0
    placeholder = assistant_composer_placeholder_evidence(panel)
    assert placeholder["visible"] is True
    assert placeholder["text"] == "Ask about EEG..."
    assert placeholder["available_width"] > 0
    assert placeholder["available_height"] > 0


@pytest.mark.parametrize(
    ("factory", "filename", "expected_title"),
    [
        (
            _assistant_loading_standard,
            "assistant-loading.png",
            "Loading local assistant",
        ),
        (_assistant_failed_standard, "assistant-failed.png", "Assistant unavailable"),
        (
            _assistant_recovery_standard,
            "assistant-recovery-loading.png",
            "Retrying local assistant",
        ),
    ],
)
def test_assistant_standard_runtime_captures_are_semantically_valid(
    qtbot,
    factory,
    filename,
    expected_title,
) -> None:
    panel = factory()
    qtbot.addWidget(panel)
    panel.show()
    _settle_capture_widget(QApplication.instance(), panel)

    _assert_capture_geometry(filename, panel)

    assert panel.width() == 420
    assert panel.runtime_state_title.text() == expected_title


def test_assistant_capture_rejects_setup_required_with_stop(qtbot) -> None:
    panel = _assistant_setup_required_narrow()
    qtbot.addWidget(panel)
    panel.is_processing = True
    panel.send_btn.setText("Stop")

    with pytest.raises(RuntimeError, match=r"setup-required.*Stop"):
        _assert_capture_geometry("assistant-impossible.png", panel)


def test_assistant_capture_rejects_missing_setup_action(qtbot) -> None:
    panel = _assistant_setup_required_narrow()
    qtbot.addWidget(panel)
    panel.show()
    panel.setup_btn.hide()

    with pytest.raises(RuntimeError, match="Open Assistant Settings"):
        _assert_capture_geometry("assistant-missing-action.png", panel)


def test_assistant_pixel_gate_rejects_same_theme_erased_activity_and_stop(
    qtbot,
    tmp_path,
) -> None:
    panel = _assistant_active_turn_narrow()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.wait(20)
    screenshot = tmp_path / "assistant-erased.png"
    assert panel.grab().save(str(screenshot))
    with Image.open(screenshot) as captured:
        damaged = captured.convert("RGB")
    draw = ImageDraw.Draw(damaged)
    for control in (
        panel.turn_activity_widget,
        panel.send_btn,
    ):
        top_left = control.mapTo(panel, QPoint(0, 0))
        draw.rectangle(
            (
                top_left.x(),
                top_left.y(),
                top_left.x() + control.width() - 1,
                top_left.y() + control.height() - 1,
            ),
            fill="#1e1e1e",
        )
    damaged.save(screenshot)

    with pytest.raises(RuntimeError, match="reference render"):
        _assert_surface_pixels(panel, screenshot)


def test_evaluation_controls_capture_can_render_its_model_summary(qtbot) -> None:
    panel = _evaluation_controls_panel()
    qtbot.addWidget(panel)

    panel.show()
    qtbot.waitUntil(panel.isVisible)

    assert isinstance(cast(Any, panel).summary_text.toPlainText(), str)


def test_evaluation_controls_cleanup_quiesces_matplotlib_canvases(qtbot) -> None:
    panel = _evaluation_controls_panel()
    qtbot.addWidget(panel)
    assert panel.matrix_widget.canvas is not None
    assert panel.bar_chart.canvas is not None

    panel.cleanup()
    panel.cleanup()

    assert panel.matrix_widget.canvas is None
    assert panel.matrix_widget.fig is None
    assert panel.bar_chart.canvas is None
    assert panel.bar_chart.fig is None


@pytest.mark.parametrize(
    ("factory", "filename", "row_count", "running"),
    [
        (
            _training_history_few_rows,
            "training-history-few-rows.png",
            2,
            False,
        ),
        (
            _training_history_many_rows,
            "training-history-many-rows.png",
            9,
            True,
        ),
    ],
)
def test_training_history_capture_contract_is_coherent_and_readable(
    qtbot,
    factory,
    filename,
    row_count,
    running,
) -> None:
    panel = factory()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.wait(20)

    _assert_capture_geometry(filename, panel)
    semantics = _training_history_semantics(panel)

    assert semantics["row_count"] == row_count
    assert semantics["running"] is running
    assert semantics["start_enabled"] is (not running)
    assert semantics["stop_enabled"] is running
    assert semantics["summary_has_data"] is True
    if running:
        assert "Running" in semantics["statuses"]
    else:
        assert set(semantics["statuses"]) == {"Completed"}
    assert semantics["key_columns_fit"] is True


def test_training_history_pixel_gate_rejects_erased_chrome_and_row_cells(
    qtbot,
    tmp_path,
) -> None:
    panel = _training_history_many_rows()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.wait(20)
    screenshot = tmp_path / "training-history-many-rows-erased.png"
    canonical = DEFAULT_OUTPUT_DIR / "training-history-many-rows.png"
    assert screenshot.resolve().is_relative_to(tmp_path.resolve())
    assert screenshot.resolve() != canonical.resolve()
    assert panel.grab().save(str(screenshot))

    with Image.open(screenshot) as captured:
        damaged = captured.convert("RGB")
    draw = ImageDraw.Draw(damaged)
    for title_surface in (panel.plots_group, panel.history_title):
        top_left = title_surface.mapTo(panel, QPoint(0, 0))
        draw.rectangle(
            (
                top_left.x(),
                top_left.y(),
                top_left.x() + title_surface.width() - 1,
                top_left.y() + title_surface.height() - 1,
            ),
            fill="#f0f0f0",
        )
    assert panel.tabs is not None
    tab_bar = panel.tabs.tabBar()
    assert tab_bar is not None
    top_left = tab_bar.mapTo(panel, QPoint(0, 0))
    draw.rectangle(
        (
            top_left.x(),
            top_left.y(),
            top_left.x() + tab_bar.width() - 1,
            top_left.y() + tab_bar.height() - 1,
        ),
        fill="#f0f0f0",
    )
    assert panel.history_table is not None
    viewport = panel.history_table.viewport()
    assert viewport is not None
    model = panel.history_table.model()
    assert model is not None
    for row in (4, 5):
        for column in range(7):
            index = model.index(row, column)
            rect = panel.history_table.visualRect(index)
            top_left = viewport.mapTo(panel, rect.topLeft())
            draw.rectangle(
                (
                    top_left.x(),
                    top_left.y(),
                    top_left.x() + rect.width() - 1,
                    top_left.y() + rect.height() - 1,
                ),
                fill="#1e1e1e",
            )
    damaged.save(screenshot)
    second_screenshot = tmp_path / "training-history-many-rows-erased-2.png"
    damaged.save(second_screenshot)

    assert assert_consecutive_complete_frames(screenshot, second_screenshot) == 0.0
    with pytest.raises(RuntimeError, match=r"Training History (chrome|cell)"):
        _assert_training_history_reference_pixels(panel, screenshot)


def test_app_polish_validator_requires_many_row_cell_pixel_evidence(
    qtbot,
    tmp_path,
) -> None:
    filename = "training-history-many-rows.png"
    panel = _training_history_many_rows()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.wait(20)
    frame_readiness = _capture(panel, tmp_path / filename)
    with Image.open(tmp_path / filename) as captured:
        assert captured.mode == "RGB"
        assert "dpi" not in captured.info
    identity = collect_source_identity()
    generated_at = datetime.now(UTC)
    payload = build_app_polish_evidence(
        tmp_path,
        expected_surfaces=[filename],
        selected_surfaces=[filename],
        surface_contracts={
            filename: _surface_contract(
                filename,
                panel,
                frame_readiness=frame_readiness,
            )
        },
        generated_at=generated_at,
        source_identity=identity,
        qt_platform="offscreen",
    )
    ok, reason = _validate_test_evidence(
        payload,
        tmp_path,
        identity,
        now=generated_at,
        expected_surfaces=(filename,),
    )
    assert ok is True, reason

    frame = payload["surface_contracts"][filename]["frame_readiness"]
    removed_prefixes = (
        "Training History cell row 1:",
        "Training History cell row 2:",
    )
    frame["required_regions"] = [
        name
        for name in frame["required_regions"]
        if not name.startswith(removed_prefixes)
    ]
    frame["reference_regions"] = [
        region
        for region in frame["reference_regions"]
        if not region["surface_name"].startswith(removed_prefixes)
    ]
    frame["reference_comparison_count"] = len(frame["reference_regions"])
    frame["minimum_reference_edge_recall"] = round(
        min(region["edge_recall"] for region in frame["reference_regions"]),
        6,
    )
    frame["maximum_reference_changed_pixel_ratio"] = round(
        max(region["changed_pixel_ratio"] for region in frame["reference_regions"]),
        6,
    )

    ok, reason = _validate_test_evidence(
        payload,
        tmp_path,
        identity,
        now=generated_at,
        expected_surfaces=(filename,),
    )
    assert ok is False
    assert "cell evidence is incomplete" in reason


def test_capture_readme_can_be_written_outside_tracked_artifacts(tmp_path) -> None:
    _write_readme(tmp_path)

    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "App Polish Screenshots" in readme
    assert "human desktop acceptance" in readme


def test_capture_publish_replaces_manifest_only_after_screenshot_and_readme(
    monkeypatch,
    tmp_path,
) -> None:
    staging_dir = tmp_path / "staging"
    output_dir = tmp_path / "canonical"
    staging_dir.mkdir()
    Image.new("RGB", (20, 12), (40, 80, 120)).save(staging_dir / "surface-a.png")
    (staging_dir / "README.md").write_text("review", encoding="utf-8")
    (staging_dir / "app-polish-evidence.json").write_text(
        '{"complete": true}\n',
        encoding="utf-8",
    )
    replaced: list[str] = []
    original_replace = type(staging_dir).replace

    def tracking_replace(source, target):
        if source.name == "app-polish-evidence.json":
            assert (output_dir / "surface-a.png").is_file()
            assert (output_dir / "README.md").read_text(encoding="utf-8") == "review"
        replaced.append(source.name)
        return original_replace(source, target)

    monkeypatch.setattr(type(staging_dir), "replace", tracking_replace)

    _publish_capture(
        staging_dir,
        output_dir,
        selected_surfaces=["surface-a.png"],
    )

    assert replaced == [
        "surface-a.png",
        "README.md",
        "app-polish-evidence.json",
    ]
    assert (output_dir / "surface-a.png").is_file()
    assert (output_dir / "app-polish-evidence.json").is_file()


def test_capture_application_theme_matches_formal_main_window_theme(qapp) -> None:
    app = qapp
    previous_stylesheet = app.styleSheet()
    previous_capture_style = app.property("xbrainlab_capture_qt_style")
    try:
        _apply_capture_application_theme(app)

        assert app.property("xbrainlab_capture_qt_style") == "Fusion"
        assert app.styleSheet() == Stylesheets.MAIN_WINDOW
    finally:
        app.setStyleSheet(previous_stylesheet)
        app.setStyle("Fusion")
        app.setProperty("xbrainlab_capture_qt_style", previous_capture_style)


def test_training_history_visual_pair_rejects_blue_disabled_start() -> None:
    blue = {
        "mean_rgb": [75.0, 115.0, 175.0],
        "luminance": 110.0,
        "color_span": 100.0,
    }
    gray = {
        "mean_rgb": [55.0, 55.0, 55.0],
        "luminance": 55.0,
        "color_span": 0.0,
    }
    orange = {
        "mean_rgb": [185.0, 70.0, 25.0],
        "luminance": 91.0,
        "color_span": 160.0,
    }

    ok, reason = _validate_training_history_visual_pair(
        {
            "training-history-few-rows.png": {
                "start_visual": blue,
                "stop_visual": gray,
            },
            "training-history-many-rows.png": {
                "start_visual": blue,
                "stop_visual": orange,
            },
        }
    )

    assert ok is False
    assert "disabled Start is not visually distinct" in reason


def test_training_history_real_button_pixels_distinguish_disabled_start(
    qtbot,
) -> None:
    few = _training_history_few_rows()
    many = _training_history_many_rows()
    qtbot.addWidget(few)
    qtbot.addWidget(many)
    few.show()
    many.show()
    qtbot.wait(20)

    few_semantics = _training_history_semantics(few)
    many_semantics = _training_history_semantics(many)
    ok, reason = _validate_training_history_visual_pair(
        {
            "training-history-few-rows.png": few_semantics,
            "training-history-many-rows.png": many_semantics,
        }
    )

    assert ok is True, reason
    assert few_semantics["start_visual"] != many_semantics["start_visual"]


def _evidence_payload(tmp_path, *, generated_at: datetime) -> tuple[dict, dict]:
    filenames = ["surface-a.png", "surface-b.png"]
    for index, filename in enumerate(filenames):
        Image.new("RGB", (20 + index, 12), (40, 80 + index, 120)).save(
            tmp_path / filename
        )
    identity = collect_source_identity()
    payload = build_app_polish_evidence(
        tmp_path,
        expected_surfaces=filenames,
        selected_surfaces=filenames,
        surface_contracts={
            filename: {
                "contract_version": 1,
                "kind": "test_surface",
                "passed": True,
                "verified_controls": ["Primary action"],
                "frame_readiness": {
                    "consecutive_complete_frames": 2,
                    "stable": True,
                    "max_changed_pixel_ratio": 0.0,
                    "required_regions": ["Primary action"],
                    "reference_validated": True,
                    "reference_comparison_count": 1,
                    "minimum_reference_edge_recall": 1.0,
                    "maximum_reference_changed_pixel_ratio": 0.0,
                    "reference_regions": [
                        {
                            "surface_name": "Primary action",
                            "bounds": [0, 0, 12, 10],
                            "minimum_required_edge_recall": 0.42,
                            "maximum_allowed_changed_pixel_ratio": 0.55,
                            "maximum_allowed_missing_detail_tile_ratio": 0.35,
                            "minimum_reference_edge_pixels": 4,
                            "edge_recall": 1.0,
                            "changed_pixel_ratio": 0.0,
                            "reference_edge_pixels": 12,
                            "detail_tile_count": 1,
                            "missing_detail_tile_ratio": 0.0,
                        }
                    ],
                    "capture_method": "QWidget.grab",
                },
            }
            for filename in filenames
        },
        generated_at=generated_at,
        source_identity=identity,
        qt_platform="offscreen",
    )
    return payload, identity


def _validate_test_evidence(
    payload: dict,
    tmp_path,
    identity: dict,
    *,
    now: datetime,
    expected_surfaces: tuple[str, ...] = ("surface-a.png", "surface-b.png"),
) -> tuple[bool, str]:
    return validate_app_polish_evidence(
        payload,
        output_dir=tmp_path,
        expected_surfaces=expected_surfaces,
        now=now,
        refresh_source_identity=False,
        current_source_identity=identity,
    )


def _single_surface_payload(
    tmp_path,
    *,
    filename: str,
    widget,
    generated_at: datetime,
) -> tuple[dict, dict]:
    widget.show()
    assert widget.grab().save(str(tmp_path / filename))
    identity = collect_source_identity()
    payload = build_app_polish_evidence(
        tmp_path,
        expected_surfaces=[filename],
        selected_surfaces=[filename],
        surface_contracts={
            filename: _surface_contract(
                filename,
                widget,
                frame_readiness={
                    "consecutive_complete_frames": 2,
                    "stable": True,
                    "max_changed_pixel_ratio": 0.0,
                    "required_regions": ["test surface"],
                    "reference_validated": True,
                    "reference_comparison_count": 1,
                    "minimum_reference_edge_recall": 1.0,
                    "maximum_reference_changed_pixel_ratio": 0.0,
                    "reference_regions": [
                        {
                            "surface_name": "test surface",
                            "bounds": [0, 0, 12, 10],
                            "minimum_required_edge_recall": 0.42,
                            "maximum_allowed_changed_pixel_ratio": 0.55,
                            "maximum_allowed_missing_detail_tile_ratio": 0.35,
                            "minimum_reference_edge_pixels": 4,
                            "edge_recall": 1.0,
                            "changed_pixel_ratio": 0.0,
                            "reference_edge_pixels": 12,
                            "detail_tile_count": 1,
                            "missing_detail_tile_ratio": 0.0,
                        }
                    ],
                    "capture_method": "QWidget.grab",
                },
            )
        },
        generated_at=generated_at,
        source_identity=identity,
        qt_platform="offscreen",
    )
    return payload, identity


def test_app_polish_validator_rejects_machine_pass_without_stable_frames(
    tmp_path,
) -> None:
    now = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    payload, identity = _evidence_payload(tmp_path, generated_at=now)
    payload["surface_contracts"]["surface-a.png"]["frame_readiness"] = {
        "consecutive_complete_frames": 1,
        "stable": False,
        "max_changed_pixel_ratio": 0.6,
        "required_regions": [],
    }

    ok, reason = _validate_test_evidence(
        payload,
        tmp_path,
        identity,
        now=now,
    )

    assert ok is False
    assert "frame readiness" in reason.lower()


def test_app_polish_validator_rejects_incomplete_epoch_control_contract(
    qtbot,
    tmp_path,
) -> None:
    now = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    dialog = _epoching_internal_events_dialog()
    qtbot.addWidget(dialog)
    payload, identity = _single_surface_payload(
        tmp_path,
        filename=INTERNAL_EPOCH_SCREENSHOT,
        widget=dialog,
        generated_at=now,
    )
    payload["surface_contracts"][INTERNAL_EPOCH_SCREENSHOT]["verified_controls"].remove(
        "Cancel"
    )

    ok, reason = _validate_test_evidence(
        payload,
        tmp_path,
        identity,
        now=now,
        expected_surfaces=(INTERNAL_EPOCH_SCREENSHOT,),
    )

    assert ok is False
    assert "visible-control contract is incomplete" in reason


def test_app_polish_validator_rejects_k_fold_manifest_row_mismatch(
    qtbot,
    tmp_path,
) -> None:
    now = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    dialog = _data_splitting_preview_dialog()
    qtbot.addWidget(dialog)
    payload, identity = _single_surface_payload(
        tmp_path,
        filename="data-splitting-preview-dialog.png",
        widget=dialog,
        generated_at=now,
    )
    payload["surface_contracts"]["data-splitting-preview-dialog.png"][
        "k_fold_count"
    ] = 2

    ok, reason = _validate_test_evidence(
        payload,
        tmp_path,
        identity,
        now=now,
        expected_surfaces=("data-splitting-preview-dialog.png",),
    )

    assert ok is False
    assert "count and result rows disagree" in reason


def test_app_polish_manifest_records_current_source_and_screenshot_integrity(
    tmp_path,
) -> None:
    now = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    payload, identity = _evidence_payload(tmp_path, generated_at=now)

    ok, reason = _validate_test_evidence(
        payload,
        tmp_path,
        identity,
        now=now,
    )

    assert ok is True, reason
    assert payload["generated_at_utc"] == "2026-07-16T08:00:00+00:00"
    assert payload["source_identity"]["commit_sha"]
    assert payload["source_identity"]["head_tree_sha"]
    assert payload["capture_session"]["source_identity_stable"] is True
    assert (
        payload["capture_session"]["source_digest_at_completion"]
        == payload["source_identity"]["source_digest"]
    )
    for metadata in payload["screenshots"].values():
        assert metadata["dimensions"]
        assert metadata["byte_size"] > 0
        assert len(metadata["sha256"]) == 64


def test_app_polish_validator_rejects_partial_capture_as_complete(tmp_path) -> None:
    now = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    payload, identity = _evidence_payload(tmp_path, generated_at=now)
    payload["capture_scope"]["selected_surfaces"] = ["surface-a.png"]
    payload["capture_scope"]["complete"] = False
    payload["screenshots"].pop("surface-b.png")
    payload["surface_contracts"].pop("surface-b.png")

    ok, reason = _validate_test_evidence(
        payload,
        tmp_path,
        identity,
        now=now,
    )

    assert ok is False
    assert "partial capture" in reason.lower()


def test_app_polish_validator_rejects_narrowed_expected_surface_denominator(
    tmp_path,
) -> None:
    now = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    payload, identity = _evidence_payload(tmp_path, generated_at=now)
    payload["capture_scope"]["expected_surfaces"] = ["surface-a.png"]
    payload["capture_scope"]["selected_surfaces"] = ["surface-a.png"]
    payload["capture_scope"]["complete"] = True
    payload["screenshots"].pop("surface-b.png")
    payload["surface_contracts"].pop("surface-b.png")

    ok, reason = _validate_test_evidence(
        payload,
        tmp_path,
        identity,
        now=now,
    )

    assert ok is False
    assert "canonical surface inventory" in reason.lower()


def test_app_polish_validator_rejects_completion_source_digest_mutation(
    tmp_path,
) -> None:
    now = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    payload, identity = _evidence_payload(tmp_path, generated_at=now)
    payload["capture_session"]["source_digest_at_completion"] = "0" * 64

    ok, reason = _validate_test_evidence(
        payload,
        tmp_path,
        identity,
        now=now,
    )

    assert ok is False
    assert "capture completion" in reason.lower()


def test_app_polish_surface_inventory_includes_training_history_extremes() -> None:
    assert "training-history-few-rows.png" in APP_POLISH_SURFACES
    assert "training-history-many-rows.png" in APP_POLISH_SURFACES


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        (lambda payload: payload.pop("schema_version"), "schema version"),
        (
            lambda payload: payload["screenshots"]["surface-a.png"].pop("sha256"),
            "incomplete",
        ),
        (
            lambda payload: payload["source_identity"].pop("head_tree_sha"),
            "missing fields",
        ),
    ],
)
def test_app_polish_validator_rejects_missing_contract_fields(
    tmp_path,
    mutation,
    expected_reason,
) -> None:
    now = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    payload, identity = _evidence_payload(tmp_path, generated_at=now)
    mutation(payload)

    ok, reason = _validate_test_evidence(
        payload,
        tmp_path,
        identity,
        now=now,
    )

    assert ok is False
    assert expected_reason in reason.lower()


def test_app_polish_validator_rejects_stale_timestamp(tmp_path) -> None:
    generated = datetime(2026, 7, 14, 8, 0, tzinfo=UTC)
    payload, identity = _evidence_payload(tmp_path, generated_at=generated)

    ok, reason = _validate_test_evidence(
        payload,
        tmp_path,
        identity,
        now=generated + timedelta(days=2),
    )

    assert ok is False
    assert "timestamp is stale" in reason.lower()


def test_app_polish_validator_accepts_new_commit_with_identical_source_content(
    tmp_path,
) -> None:
    now = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    payload, identity = _evidence_payload(tmp_path, generated_at=now)
    current = deepcopy(identity)
    current["branch"] = f"{identity['branch']}-different"
    current["commit_sha"] = "a" * 40
    current["head_tree_sha"] = "b" * 40
    current["dirty"] = not bool(identity["dirty"])
    current["dirty_digest"] = "c" * 64
    current["source_digest"] = "d" * 64

    ok, reason = _validate_test_evidence(
        payload,
        tmp_path,
        current,
        now=now,
    )

    assert ok is True, reason


def test_app_polish_validator_rejects_stale_source_content(tmp_path) -> None:
    now = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    payload, identity = _evidence_payload(tmp_path, generated_at=now)
    current = deepcopy(identity)
    current["source_content_digest"] = "0" * 64

    ok, reason = _validate_test_evidence(
        payload,
        tmp_path,
        current,
        now=now,
    )

    assert ok is False
    assert "stale (source_content_digest)" in reason.lower()


def test_app_polish_validator_rejects_tampered_screenshot_bytes(tmp_path) -> None:
    now = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    payload, identity = _evidence_payload(tmp_path, generated_at=now)
    Image.new("RGB", (20, 12), (255, 0, 0)).save(tmp_path / "surface-a.png")

    ok, reason = _validate_test_evidence(
        payload,
        tmp_path,
        identity,
        now=now,
    )

    assert ok is False
    assert "metadata/hash mismatch" in reason.lower()
