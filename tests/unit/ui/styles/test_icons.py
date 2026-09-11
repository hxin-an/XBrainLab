"""Render checks for the actual Assistant settings icon."""

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon

from XBrainLab.config import AppConfig


def _visible_icon_pixels(icon: QIcon) -> list[tuple[int, int, int, int, int]]:
    image = icon.pixmap(QSize(16, 16)).toImage()
    return [
        (x, y, color.red(), color.green(), color.blue())
        for y in range(image.height())
        for x in range(image.width())
        if (color := image.pixelColor(x, y)).alpha() >= 32
    ]


class TestSettingsIcon:
    def test_settings_icon_is_padded_and_balanced_at_toolbar_size(self, qapp):
        del qapp
        pixels = _visible_icon_pixels(QIcon(AppConfig.get_icon_path("settings.svg")))
        assert pixels
        xs = [pixel[0] for pixel in pixels]
        ys = [pixel[1] for pixel in pixels]
        assert min(xs) >= 1
        assert max(xs) <= 14
        assert min(ys) >= 1
        assert max(ys) <= 14

        quadrants = [0, 0, 0, 0]
        for x, y, *_rgb in pixels:
            quadrants[(2 if y >= 8 else 0) + (1 if x >= 8 else 0)] += 1
        assert max(quadrants) / min(quadrants) <= 1.25
