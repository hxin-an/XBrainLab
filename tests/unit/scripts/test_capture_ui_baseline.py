from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image

from scripts.dev.capture_ui_baseline import (
    AI_DOCK_STEP,
    EXPECTED_UI_ARTIFACTS,
    _prepare_capture_step,
    _shutdown_snapshot_is_clean,
    _validate_consecutive_frames,
    build_ui_baseline_evidence,
    is_nearly_black,
    validate_ui_baseline_evidence,
)
from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
)


@pytest.mark.parametrize("failure_phase", ["prepare", "first_frame", "stable_frame"])
def test_capture_callback_failure_closes_real_service(
    qapp, qtbot, tmp_path, monkeypatch, failure_phase
):
    from PyQt6.QtCore import QTimer

    from scripts.dev import capture_ui_baseline as capture
    from XBrainLab.backend.application import runtime

    services = []
    original_get_service = runtime.get_application_service

    def observe_service(study):
        service = original_get_service(study)
        services.append(service)
        return service

    monkeypatch.setattr(runtime, "get_application_service", observe_service)
    calls = []

    def frame(_window, _path, **_kwargs):
        calls.append("frame")
        if failure_phase == "first_frame" or len(calls) == 2:
            raise OSError("baseline frame readback unavailable")
        return 0

    def prepare(_window, _target):
        raise OSError("baseline panel preparation unavailable")

    if failure_phase == "prepare":
        monkeypatch.setattr(capture, "_prepare_capture_step", prepare)
    else:
        monkeypatch.setattr(capture, "_capture_window_frame", frame)
    fallback = QTimer()
    fallback.setSingleShot(True)
    fallback.timeout.connect(qapp.quit)
    fallback.start(6000)
    previous_quit_policy = qapp.quitOnLastWindowClosed()
    try:
        with qtbot.captureExceptions() as exceptions:
            code, shutdown = capture.capture_window(qapp, tmp_path / "baseline.png")
        assert code == 5
        assert shutdown["ok"], shutdown
        assert services and all(service.is_closed for service in services)
        assert exceptions == []
        assert fallback.isActive(), "capture only exited via the test safety timer"
    finally:
        fallback.stop()
        for widget in qapp.topLevelWidgets():
            if getattr(widget, "study", None) in [
                service.study for service in services
            ]:
                widget.close()
                widget.deleteLater()
        for service in services:
            service.close()
        qapp.setQuitOnLastWindowClosed(previous_quit_policy)


def test_default_baseline_covers_both_filter_section_states():
    from scripts.dev.run_app_polish_ui_dpi_gate import DPI_APP_POLISH_SURFACES

    assert {
        "preprocess-filtering-default.png",
        "preprocess-filtering-notch-only.png",
    } <= set(EXPECTED_UI_ARTIFACTS)
    assert {
        "preprocess-filtering-default.png",
        "preprocess-filtering-notch-only.png",
    } <= set(DPI_APP_POLISH_SURFACES)


def test_is_nearly_black_detects_empty_image(tmp_path):
    image_path = tmp_path / "black.png"
    Image.new("RGB", (20, 20), (0, 0, 0)).save(image_path)

    assert is_nearly_black(image_path) is True


def test_is_nearly_black_detects_visible_content(tmp_path):
    image_path = tmp_path / "visible.png"
    Image.new("RGB", (20, 20), (255, 255, 255)).save(image_path)

    assert is_nearly_black(image_path) is False


def test_consecutive_frame_gate_accepts_settled_frames(tmp_path):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (100, 100), (32, 32, 32)).save(first)
    Image.new("RGB", (100, 100), (32, 32, 32)).save(second)

    assert _validate_consecutive_frames(first, second) == 0


def test_consecutive_frame_gate_rejects_partial_repaint(tmp_path):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (100, 100), (0, 0, 0)).save(first)
    Image.new("RGB", (100, 100), (220, 220, 220)).save(second)

    assert _validate_consecutive_frames(first, second) == 5


def test_baseline_evidence_binds_candidate_references_and_source(tmp_path):
    candidate_dir = tmp_path / "candidate"
    reference_dir = tmp_path / "references"
    candidate_dir.mkdir()
    reference_dir.mkdir()
    for filename in EXPECTED_UI_ARTIFACTS:
        Image.new("RGB", (24, 16), (32, 48, 64)).save(candidate_dir / filename)
        Image.new("RGB", (24, 16), (32, 48, 64)).save(reference_dir / filename)
    source_identity = collect_source_identity(refresh=True)
    payload = build_ui_baseline_evidence(
        output_dir=candidate_dir,
        reference_dir=reference_dir,
        source_identity=source_identity,
        qt_platform="offscreen",
        qt_style="fusion",
        device_pixel_ratio=1.0,
        shutdown={
            "ok": True,
            "timed_out": False,
            "window_visible": False,
            "snapshot": {
                "application_closed": True,
                "pre_close_application_idle": True,
                "pre_close_remaining_workers": 0,
                "pre_close_remaining_subprocesses": 0,
                "close_attempt_id": "ui-baseline-close-attempt",
            },
        },
    )

    ok, reason = validate_ui_baseline_evidence(
        payload,
        output_dir=candidate_dir,
        reference_dir=reference_dir,
        current_source_identity=source_identity,
    )

    assert ok, reason
    assert payload["passed"] is True

    Image.new("RGB", (24, 16), (200, 20, 20)).save(
        reference_dir / EXPECTED_UI_ARTIFACTS[0]
    )
    ok, reason = validate_ui_baseline_evidence(
        payload,
        output_dir=candidate_dir,
        reference_dir=reference_dir,
        current_source_identity=source_identity,
    )
    assert not ok
    assert "references changed" in reason


def test_baseline_evidence_rejects_missing_clean_shutdown(tmp_path):
    candidate_dir = tmp_path / "candidate"
    reference_dir = tmp_path / "references"
    candidate_dir.mkdir()
    reference_dir.mkdir()
    for filename in EXPECTED_UI_ARTIFACTS:
        Image.new("RGB", (24, 16), (32, 48, 64)).save(candidate_dir / filename)
        Image.new("RGB", (24, 16), (32, 48, 64)).save(reference_dir / filename)
    source_identity = collect_source_identity(refresh=True)
    payload = build_ui_baseline_evidence(
        output_dir=candidate_dir,
        reference_dir=reference_dir,
        source_identity=source_identity,
        qt_platform="offscreen",
        qt_style="fusion",
        device_pixel_ratio=1.0,
        shutdown={},
    )

    ok, reason = validate_ui_baseline_evidence(
        payload,
        output_dir=candidate_dir,
        reference_dir=reference_dir,
        current_source_identity=source_identity,
    )

    assert ok is False
    assert reason == "UI baseline did not publish a clean terminal shutdown."


def test_shutdown_snapshot_requires_owned_work_to_be_idle():
    assert _shutdown_snapshot_is_clean(
        {
            "application_closed": True,
            "pre_close_application_idle": True,
            "pre_close_remaining_workers": 0,
            "pre_close_remaining_subprocesses": 0,
            "close_attempt_id": "ui-baseline-close-attempt",
        }
    )
    assert not _shutdown_snapshot_is_clean(
        {
            "application_closed": True,
            "pre_close_application_idle": True,
            "pre_close_remaining_workers": 1,
            "pre_close_remaining_subprocesses": 0,
            "close_attempt_id": "ui-baseline-close-attempt",
        }
    )


def _ready_switch_page(index, *, on_ready):
    on_ready(SimpleNamespace(index=index))
    return True


def test_prepare_capture_step_switches_panel(qapp):
    del qapp
    window = MagicMock()
    window.switch_page.side_effect = _ready_switch_page

    _prepare_capture_step(window, 4)

    window.switch_page.assert_called_once()
    assert window.switch_page.call_args.args == (4,)
    assert callable(window.switch_page.call_args.kwargs["on_ready"])


def test_prepare_capture_step_opens_ai_dock_on_dataset_page(qapp):
    del qapp
    chat_dock = MagicMock()
    agent_manager = SimpleNamespace(
        agent_initialized=False,
        chat_dock=chat_dock,
        update_ai_btn_state=MagicMock(),
    )
    switch_page = MagicMock(side_effect=_ready_switch_page)
    window = SimpleNamespace(
        switch_page=switch_page,
        agent_manager=agent_manager,
        ai_btn=MagicMock(),
    )

    _prepare_capture_step(window, AI_DOCK_STEP)

    switch_page.assert_called_once()
    assert switch_page.call_args.args == (0,)
    assert callable(switch_page.call_args.kwargs["on_ready"])
    assert window.agent_manager.agent_initialized is False
    chat_dock.show.assert_called_once_with()
    window.agent_manager.update_ai_btn_state.assert_called_once_with(True)
