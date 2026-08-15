from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from PIL import Image

from scripts.dev.capture_ui_baseline import (
    AI_DOCK_STEP,
    EXPECTED_UI_ARTIFACTS,
    _prepare_capture_step,
    _validate_consecutive_frames,
    build_ui_baseline_evidence,
    is_nearly_black,
    validate_ui_baseline_evidence,
)
from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
)


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
