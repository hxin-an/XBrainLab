from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from PyQt6.QtCore import QPoint, QSize

import scripts.dev.capture_data_import_wizard_steps as capture_script
from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
)
from scripts.dev.data_import_capture_contract import (
    build_data_import_capture_manifest,
)


def test_default_data_import_evidence_uses_dev_artifact_namespace() -> None:
    expected = (
        capture_script.ROOT / "build" / "dev-artifacts" / "data-import-wizard-steps"
    )

    assert expected == capture_script.DEFAULT_OUTPUT_DIR
    assert "HISTORICAL_CHECKPOINT_OUTPUT_DIR" not in vars(capture_script)


def test_compact_wizard_step_contract_matches_current_visible_labels() -> None:
    assert capture_script.WIZARD_COMPACT_STEP_TEXT == (
        "1. EEG",
        "2. Labels",
        "3. Details",
        "4. Match",
        "5. Review",
    )


def test_nested_placement_capture_keeps_full_logical_artifact_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = capture_script._placement_mode_capture_specs()[0]
    logical_names: list[str | None] = []

    monkeypatch.setattr(
        capture_script, "_settle_window_for_capture", lambda _widget: None
    )
    monkeypatch.setattr(capture_script, "_grab_window", lambda _widget: object())
    monkeypatch.setattr(
        capture_script,
        "_save_window_capture",
        lambda _pixmap, _path: None,
    )
    monkeypatch.setattr(
        capture_script,
        "_assert_complete_capture_frame",
        lambda _widget, _path, _spec, *, logical_name=None: logical_names.append(
            logical_name
        ),
    )
    monkeypatch.setattr(
        capture_script,
        "_assert_consecutive_complete_frames",
        lambda _first, _second: 0.0,
    )

    capture_script._capture(object(), tmp_path / spec.filename, spec)

    assert logical_names == [spec.filename, spec.filename]


def test_placement_mode_states_are_bound_in_the_root_manifest(tmp_path: Path) -> None:
    specs = capture_script._canonical_capture_specs()
    placement_specs = capture_script._placement_mode_capture_specs()
    for index, spec in enumerate((*specs, *placement_specs)):
        path = tmp_path / spec.filename
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (80 + index, 60), (35, 70, 105)).save(path)
    identity = collect_source_identity(capture_script.ROOT)
    captured_at = datetime.now(UTC)
    manifest = build_data_import_capture_manifest(
        tmp_path,
        expected_surfaces=[spec.filename for spec in specs],
        selected_surfaces=[spec.filename for spec in specs],
        source_identity=identity,
        source_identity_at_start=identity,
        capture_started_at=captured_at,
        generated_at=captured_at,
        qt_platform="xcb",
        session_id="placement-contract",
    )

    capture_script._bind_generator_manifest(
        manifest,
        output_dir=tmp_path,
        canonical_specs=specs,
        placement_specs=placement_specs,
        qt_platform="xcb",
    )

    assert manifest["generator"] == ("scripts/dev/capture_data_import_wizard_steps.py")
    assert manifest["source_identity"]["commit_sha"]
    assert manifest["source_identity"]["head_tree_sha"]
    assert manifest["source_identity"]["source_digest"]
    assert isinstance(manifest["source_identity"]["dirty"], bool)
    assert manifest["claims"]
    assert manifest["limitations"]
    assert manifest["capture_environment"]["virtual_screen"] == [1600, 1400]
    assert manifest["capture_environment"]["scale_factor"]
    assert set(manifest["placement_mode_screenshots"]) == {
        "eeg_event",
        "time_field",
        "interval",
        "event_code",
    }
    assert all(
        item["path"].startswith("match-label-placement-modes/")
        for item in manifest["placement_mode_screenshots"].values()
    )
    assert all(
        item["sha256"] for item in manifest["placement_mode_screenshots"].values()
    )

    ok, reason = capture_script._validate_generator_manifest(
        manifest,
        output_dir=tmp_path,
        canonical_specs=specs,
        placement_specs=placement_specs,
        refresh_source_identity=False,
        current_source_identity=identity,
    )
    assert ok is True, reason

    placement_path = tmp_path / placement_specs[0].filename
    placement_path.write_bytes(b"tampered")
    ok, reason = capture_script._validate_generator_manifest(
        manifest,
        output_dir=tmp_path,
        canonical_specs=specs,
        placement_specs=placement_specs,
        refresh_source_identity=False,
        current_source_identity=identity,
    )
    assert ok is False
    assert "placement screenshot metadata/hash mismatch" in reason


def test_canonical_capture_specs_define_unique_complete_inventory():
    specs = capture_script._canonical_capture_specs()
    specified_names = {spec.filename for spec in specs}

    assert len(specs) == len(specified_names)
    assert len(specs) >= 10
    assert [spec.filename for spec in specs if not spec.has_wizard_chrome] == [
        "04-match-labels-conversion-table-format-dialog.png"
    ]


def test_capture_specs_cover_responsive_and_semantic_review_evidence():
    specs = capture_script._canonical_capture_specs()
    wizard_specs = [spec for spec in specs if spec.has_wizard_chrome]

    assert {760, 1040, 1220} <= {spec.expected_size[0] for spec in wizard_specs}
    assert any(spec.label_carrier_count >= 12 for spec in wizard_specs)
    assert any(spec.bids_events for spec in wizard_specs)
    assert any(spec.expanded_report for spec in wizard_specs)
    advanced = [spec for spec in wizard_specs if spec.expanded_advanced_details]
    assert [(spec.filename, spec.expected_size) for spec in advanced] == [
        ("04-match-labels-internal-advanced-760px.png", (760, 900))
    ]
    assert {
        spec.filename: spec.expected_size
        for spec in wizard_specs
        if spec.step_title == "Review and Import"
    } == {
        "05-review-and-import-report.png": capture_script.REVIEW_REPORT_SIZE,
        "05-review-and-import.png": capture_script.REVIEW_COMPACT_SIZE,
    }
    assert all(
        f"{spec.expected_size[0]}px" in spec.filename
        for spec in wizard_specs
        if spec.expected_size[0] != 1220
    )


def test_required_region_guard_rejects_large_black_unpainted_block(tmp_path):
    screenshot = tmp_path / "partial-repaint.png"
    image = Image.new("RGB", (760, 520), "#242424")
    ImageDraw.Draw(image).rectangle((180, 100, 700, 430), fill="#000000")
    image.save(screenshot)

    with pytest.raises(RuntimeError, match="unpainted block"):
        capture_script._assert_region_has_no_unpainted_block(
            screenshot,
            (120, 70, 730, 470),
            surface_name="Wizard content",
        )


def test_consecutive_frame_guard_rejects_partial_repaint_transition(tmp_path):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (320, 240), "#2b3440").save(first)
    changed = Image.new("RGB", (320, 240), "#2b3440")
    ImageDraw.Draw(changed).rectangle((120, 30, 319, 239), fill="#000000")
    changed.save(second)

    with pytest.raises(RuntimeError, match="consecutive complete frames"):
        capture_script._assert_consecutive_complete_frames(first, second)


def test_reference_crop_guard_rejects_two_identical_same_theme_damaged_frames(
    tmp_path,
):
    reference = Image.new("RGB", (260, 80), "#1e1e1e")
    draw = ImageDraw.Draw(reference)
    draw.rectangle((8, 8, 251, 71), outline="#5b7db1", width=2)
    for left, width in ((24, 18), (50, 30), (88, 22), (120, 34), (164, 20)):
        draw.rectangle((left, 30, left + width, 45), fill="#f2f2f2")
    screenshot = Image.new("RGB", (320, 140), "#1e1e1e")
    screenshot.paste(reference, (30, 30))
    first = tmp_path / "damaged-first.png"
    second = tmp_path / "damaged-second.png"
    damaged = screenshot.copy()
    ImageDraw.Draw(damaged).rectangle((30, 30, 289, 109), fill="#1e1e1e")
    damaged.save(first)
    damaged.save(second)

    assert capture_script._assert_consecutive_complete_frames(first, second) == 0.0
    for frame in (first, second):
        with pytest.raises(RuntimeError, match="reference render"):
            capture_script._assert_region_matches_reference(
                frame,
                (30, 30, 290, 110),
                reference,
                surface_name="Required action text",
            )


def test_data_import_capture_script_only_targets_canonical_step_folder():
    source = inspect.getsource(capture_script.main)

    assert "review-import-states" not in source
    assert "bids-preset" not in source
    assert "REVIEW_STATES_DIR" not in vars(capture_script)
    assert "BIDS_PRESET_DIR" not in vars(capture_script)


def test_data_import_capture_uses_xcb_window_surface():
    source = inspect.getsource(capture_script._capture) + inspect.getsource(
        capture_script._assert_complete_capture_frame
    )
    grab_source = inspect.getsource(capture_script._grab_window)
    save_source = inspect.getsource(capture_script._save_window_capture)

    assert "grabWindow" in grab_source
    assert "root_window = cast(Any, 0)" in grab_source
    assert "mapToGlobal" in grab_source
    assert "widget.grab()" not in source
    assert "widget.grab()" not in grab_source
    assert "_settle_window_for_capture" in source
    assert "_assert_review_surface_rendered" in source
    assert "_normalize_png_for_artifact" in save_source


def test_data_import_capture_flushes_deferred_dialog_deletes_between_specs():
    source = inspect.getsource(capture_script._capture_specs_in_process)

    assert "QCoreApplication.sendPostedEvents" in source
    assert "QEvent.Type.DeferredDelete" in source


def test_complete_capture_stages_each_spec_in_an_isolated_child_process(
    monkeypatch,
    tmp_path,
):
    specs = capture_script._canonical_capture_specs()[:2]
    calls: list[list[str]] = []
    server_commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        (tmp_path / command[-1]).write_bytes(b"png")
        return type("Completed", (), {"returncode": 0})()

    class FakeServer:
        def poll(self):
            return 0

        def terminate(self):
            return None

        def wait(self, *, timeout=None):
            return 0

    def fake_start_xvfb(executable):
        server_commands.append([executable])
        return FakeServer(), ":99"

    monkeypatch.setattr(capture_script.shutil, "which", lambda _name: "/usr/bin/Xvfb")
    monkeypatch.setattr(capture_script, "_start_xvfb", fake_start_xvfb)
    monkeypatch.setattr(
        capture_script.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("isolated capture must use _start_xvfb"),
    )
    monkeypatch.setattr(capture_script.subprocess, "run", fake_run)

    capture_script._capture_specs_in_isolated_processes(specs, tmp_path)

    assert [command[-1] for command in calls] == [spec.filename for spec in specs]
    assert all("--only" in command for command in calls)
    assert all(command[0] == capture_script.sys.executable for command in calls)
    assert len(server_commands) == len(specs)
    assert server_commands == [["/usr/bin/Xvfb"]] * len(specs)


def test_data_import_capture_rejects_non_xcb_platforms():
    capture_script._require_xcb_capture("xcb")

    with pytest.raises(RuntimeError, match="xcb"):
        capture_script._require_xcb_capture("offscreen")


def test_capture_png_normalization_writes_plain_rgb(tmp_path):
    screenshot = tmp_path / "qt-capture.png"
    Image.new("RGBA", (12, 8), (12, 34, 56, 120)).save(
        screenshot,
        dpi=(96, 96),
    )

    capture_script._normalize_png_for_artifact(screenshot)

    with Image.open(screenshot) as normalized:
        assert normalized.mode == "RGB"
        assert normalized.size == (12, 8)
        assert "dpi" not in normalized.info

    normalization_source = inspect.getsource(capture_script._normalize_png_for_artifact)
    assert "optimize=True" in normalization_source


def test_review_import_capture_has_no_unresolved_primary_decision(qtbot, tmp_path):
    dialog = capture_script._review_import_dialog()
    qtbot.addWidget(dialog)
    dialog.resize(capture_script.WINDOW_SIZE)
    dialog.show()
    dialog.resize(capture_script.WINDOW_SIZE)
    dialog._go_to_step(dialog._step_titles.index("Review and Import"))
    qtbot.wait(1)

    review_specs = {
        spec.primary_action
        for spec in capture_script._canonical_capture_specs()
        if spec.step_title == "Review and Import"
    }
    assert review_specs == {dialog.apply_button.text()} == {"Confirm and Import"}
    assert dialog.apply_button.isEnabled()
    assert dialog.apply_button.isVisibleTo(dialog)
    assert not dialog.review_actions_panel.isVisibleTo(dialog)
    vertical = dialog.scroll_area.verticalScrollBar()
    assert vertical is not None
    assert vertical.maximum() == 0
    assert vertical.isVisible() is False
    capture_script._assert_single_vertical_scroll_owner(
        dialog,
        tmp_path / "test-review.png",
    )
    assert (
        dialog._review_summary_value_labels["Resource check"].text()
        == "Estimated RAM 2.0 GB / Available RAM 24.0 GB"
    )
    assert not dialog.review_tree.isVisibleTo(dialog)
    dialog.import_report_toggle.click()
    qtbot.wait(1)
    assert dialog.review_tree.isVisibleTo(dialog)
    assert dialog.review_tree.topLevelItemCount() > 0
    report_steps: set[str] = set()
    report_issues: set[str] = set()
    for index in range(dialog.review_tree.topLevelItemCount()):
        item = dialog.review_tree.topLevelItem(index)
        assert item is not None
        report_steps.add(item.text(0))
        report_issues.add(item.text(1))
    assert "Match Labels" not in report_steps
    assert report_issues == {"Optional session values were inferred"}


def test_review_import_releases_stale_conservative_summary_row_height(qtbot):
    dialog = capture_script._review_import_dialog()
    qtbot.addWidget(dialog)
    dialog.resize(capture_script.WINDOW_SIZE)
    dialog.show()
    dialog._go_to_step(dialog._step_titles.index("Review and Import"))
    qtbot.wait(20)

    summary = dialog._review_summary_value_labels["Resource check"]
    layout = dialog._review_import_rows_layout
    summary_item = next(
        layout.itemAt(index)
        for index in range(layout.count())
        if layout.itemAt(index).widget() is summary
    )
    row, _column, _row_span, _column_span = layout.getItemPosition(
        layout.indexOf(summary_item.widget())
    )
    stale_height = summary.minimumHeight() + 40
    summary.setMinimumHeight(stale_height)
    layout.setRowMinimumHeight(row, stale_height)

    dialog._sync_review_import_row_heights()

    assert summary.minimumHeight() < stale_height
    assert layout.rowMinimumHeight(row) == summary.minimumHeight()


def test_capture_step_navigation_resets_hidden_horizontal_scroll(qtbot, tmp_path):
    dialog = capture_script._review_import_dialog()
    qtbot.addWidget(dialog)
    dialog.resize(capture_script.WINDOW_SIZE)
    dialog.show()
    qtbot.waitExposed(dialog)

    horizontal = dialog.scroll_area.horizontalScrollBar()
    assert horizontal is not None
    horizontal.setValue(horizontal.maximum())
    dialog._go_to_step(dialog._step_titles.index("Review and Import"))
    qtbot.wait(1)

    assert horizontal.value() == horizontal.minimum()
    capture_script._assert_step_navigation_visible(
        dialog,
        tmp_path / "test-review.png",
    )


def test_capture_pixel_guard_rejects_styled_but_unpainted_step_navigation(
    qtbot,
    tmp_path,
):
    dialog = capture_script._review_import_dialog()
    qtbot.addWidget(dialog)
    dialog.resize(capture_script.WINDOW_SIZE)
    dialog.show()
    qtbot.wait(1)
    screenshot = tmp_path / "missing-step-labels.png"
    image = Image.new(
        "RGB",
        (dialog.width(), dialog.height()),
        "#1e1e1e",
    )
    draw = ImageDraw.Draw(image)
    for label in dialog.step_labels:
        top_left = label.mapTo(dialog, QPoint(0, 0))
        draw.rectangle(
            (
                top_left.x(),
                top_left.y(),
                top_left.x() + label.width() - 1,
                top_left.y() + label.height() - 1,
            ),
            fill="#23303a",
            outline="#5b7db1",
        )
    image.save(screenshot)

    with pytest.raises(RuntimeError, match=r"reference render|not fully rendered"):
        capture_script._assert_key_text_rendered(dialog, screenshot)


def test_required_region_guard_rejects_large_same_theme_content_erasure(
    qtbot,
    tmp_path,
):
    dialog = capture_script._review_import_dialog()
    qtbot.addWidget(dialog)
    dialog.resize(capture_script.WINDOW_SIZE)
    dialog.show()
    dialog._go_to_step(dialog._step_titles.index("Review and Import"))
    qtbot.wait(20)
    screenshot = tmp_path / "erased-content.png"
    assert dialog.grab().save(str(screenshot))
    capture_script._normalize_png_for_artifact(screenshot)
    with Image.open(screenshot) as captured:
        damaged = captured.convert("RGB")
    top_left = dialog.scroll_area.mapTo(dialog, QPoint(0, 0))
    ImageDraw.Draw(damaged).rectangle(
        (
            top_left.x(),
            top_left.y(),
            top_left.x() + dialog.scroll_area.width() - 1,
            top_left.y() + dialog.scroll_area.height() - 1,
        ),
        fill="#1e1e1e",
    )
    damaged.save(screenshot)

    with pytest.raises(RuntimeError, match="reference render"):
        capture_script._assert_required_capture_regions(dialog, screenshot)


def test_review_import_live_action_matches_current_platform_control(qtbot, tmp_path):
    spec = next(
        spec
        for spec in capture_script._canonical_capture_specs()
        if spec.filename == "05-review-and-import.png"
    )
    dialog = capture_script._review_import_dialog()
    qtbot.addWidget(dialog)
    expected_size = QSize(*spec.expected_size)
    dialog.resize(expected_size)
    dialog.show()
    dialog.resize(expected_size)
    dialog._go_to_step(dialog._step_titles.index("Review and Import"))
    qtbot.wait(20)

    live_capture = tmp_path / spec.filename
    assert dialog.grab().save(str(live_capture))
    capture_script._normalize_png_for_artifact(live_capture)
    capture_script._assert_text_controls_rendered(
        dialog,
        live_capture,
        [dialog.apply_button],
        surface_name="Review primary action",
    )


def test_expanded_report_guard_rejects_blank_review_header(qtbot, tmp_path):
    spec = next(
        spec
        for spec in capture_script._canonical_capture_specs()
        if spec.filename == "05-review-and-import-report.png"
    )
    dialog = capture_script._review_import_dialog()
    qtbot.addWidget(dialog)
    dialog.resize(QSize(*spec.expected_size))
    dialog.show()
    dialog._go_to_step(dialog._step_titles.index("Review and Import"))
    dialog.import_report_toggle.click()
    qtbot.wait(1)

    screenshot = tmp_path / "blank-review-header.png"
    image = Image.new(
        "RGB",
        (dialog.width(), dialog.height()),
        "#1e1e1e",
    )
    draw = ImageDraw.Draw(image)
    for widget in (dialog.import_report_toggle, dialog.review_tree):
        top_left = widget.mapTo(dialog, QPoint(0, 0))
        draw.rectangle(
            (
                top_left.x(),
                top_left.y(),
                top_left.x() + widget.width() - 1,
                top_left.y() + widget.height() - 1,
            ),
            fill="#242424",
            outline="#5b7db1",
        )
    draw.text(
        (
            dialog.import_report_toggle.mapTo(dialog, QPoint(0, 0)).x() + 8,
            dialog.import_report_toggle.mapTo(dialog, QPoint(0, 0)).y() + 8,
        ),
        "Hide import report",
        fill="#ffffff",
    )
    image.save(screenshot)

    with pytest.raises(
        RuntimeError,
        match=r"Review header.*(reference render|not fully rendered)",
    ):
        capture_script._assert_review_surface_rendered(dialog, screenshot)


@pytest.mark.parametrize(
    "filename",
    [
        "05-review-and-import.png",
        "05-review-and-import-report.png",
    ],
)
def test_canonical_review_artifacts_have_full_review_header(qtbot, tmp_path, filename):
    spec = next(
        spec
        for spec in capture_script._canonical_capture_specs()
        if spec.filename == filename
    )
    dialog = spec.dialog_factory()
    qtbot.addWidget(dialog)
    expected_size = QSize(*spec.expected_size)
    dialog.resize(expected_size)
    dialog.show()
    dialog.resize(expected_size)
    dialog._go_to_step(dialog._step_titles.index("Review and Import"))
    if spec.expanded_report:
        dialog.import_report_toggle.click()
    qtbot.wait(20)

    screenshot = tmp_path / filename
    assert dialog.grab().save(str(screenshot))
    capture_script._normalize_png_for_artifact(screenshot)
    capture_script._assert_canonical_review_artifact(screenshot)


def test_review_artifact_guard_rejects_qt_dpi_metadata(tmp_path):
    screenshot = tmp_path / "qt-encoded-report.png"
    Image.new("RGB", (1220, 926), "#eeeeee").save(screenshot, dpi=(96, 96))

    with pytest.raises(RuntimeError, match="DPI metadata"):
        capture_script._assert_canonical_review_artifact(screenshot)
