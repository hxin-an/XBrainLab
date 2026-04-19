from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from PIL import Image

from scripts.dev.capture_ui_baseline import (
    AI_DOCK_STEP,
    _prepare_capture_step,
    is_nearly_black,
)


def test_is_nearly_black_detects_empty_image(tmp_path):
    image_path = tmp_path / "black.png"
    Image.new("RGB", (20, 20), (0, 0, 0)).save(image_path)

    assert is_nearly_black(image_path) is True


def test_is_nearly_black_detects_visible_content(tmp_path):
    image_path = tmp_path / "visible.png"
    Image.new("RGB", (20, 20), (255, 255, 255)).save(image_path)

    assert is_nearly_black(image_path) is False


def test_prepare_capture_step_switches_panel():
    window = MagicMock()

    _prepare_capture_step(window, 4)

    window.switch_page.assert_called_once_with(4)


def test_prepare_capture_step_opens_ai_dock_on_dataset_page():
    chat_dock = MagicMock()
    agent_manager = SimpleNamespace(
        agent_initialized=False,
        chat_dock=chat_dock,
        update_ai_btn_state=MagicMock(),
    )
    window = SimpleNamespace(
        switch_page=MagicMock(),
        agent_manager=agent_manager,
        ai_btn=MagicMock(),
    )

    _prepare_capture_step(window, AI_DOCK_STEP)

    window.switch_page.assert_called_once_with(0)
    assert window.agent_manager.agent_initialized is True
    chat_dock.show.assert_called_once_with()
    window.agent_manager.update_ai_btn_state.assert_called_once_with(True)
