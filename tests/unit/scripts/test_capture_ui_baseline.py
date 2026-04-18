from __future__ import annotations

from PIL import Image

from scripts.dev.capture_ui_baseline import is_nearly_black


def test_is_nearly_black_detects_empty_image(tmp_path):
    image_path = tmp_path / "black.png"
    Image.new("RGB", (20, 20), (0, 0, 0)).save(image_path)

    assert is_nearly_black(image_path) is True


def test_is_nearly_black_detects_visible_content(tmp_path):
    image_path = tmp_path / "visible.png"
    Image.new("RGB", (20, 20), (255, 255, 255)).save(image_path)

    assert is_nearly_black(image_path) is False
