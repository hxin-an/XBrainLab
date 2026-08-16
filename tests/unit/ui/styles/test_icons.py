"""Unit tests for Icons enum."""

from unittest.mock import patch

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon

from XBrainLab.ui.styles.icons import Icons


def _visible_icon_pixels(icon: QIcon) -> list[tuple[int, int, int, int, int]]:
    image = icon.pixmap(QSize(16, 16)).toImage()
    return [
        (x, y, color.red(), color.green(), color.blue())
        for y in range(image.height())
        for x in range(image.width())
        if (color := image.pixelColor(x, y)).alpha() >= 32
    ]


class TestIconsEnum:
    def test_members_exist(self):
        assert Icons.LOGO.value == "logo.png"
        assert Icons.PLAY.value == "play.svg"
        assert Icons.STOP.value == "stop.svg"
        assert Icons.SETTINGS.value == "settings.svg"
        assert Icons.FLOAT.value == "float.svg"
        assert Icons.DOCK.value == "dock.svg"
        assert Icons.REFRESH.value == "refresh.svg"
        assert Icons.SAVE.value == "save.svg"
        assert Icons.TRASH.value == "trash.svg"

    def test_path_property(self):
        with patch(
            "XBrainLab.config.AppConfig.get_icon_path",
            side_effect=lambda name: f"/icons/{name}",
        ):
            assert Icons.LOGO.path == "/icons/logo.png"
            assert Icons.PLAY.path == "/icons/play.svg"

    def test_get_static_method(self):
        with patch(
            "XBrainLab.config.AppConfig.get_icon_path",
            side_effect=lambda name: f"/mock/{name}",
        ):
            result = Icons.get(Icons.TRASH)
            assert result == "/mock/trash.svg"

    def test_all_members_are_strings(self):
        for icon in Icons:
            assert isinstance(icon.value, str)

    def test_settings_icon_is_padded_and_balanced_at_toolbar_size(self, qapp):
        del qapp
        pixels = _visible_icon_pixels(QIcon(Icons.SETTINGS.path))
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

    def test_float_and_dock_icons_match_settings_enabled_brightness(self, qapp):
        del qapp

        def average_luminance(icon: QIcon) -> float:
            pixels = _visible_icon_pixels(icon)
            assert pixels
            return sum(
                (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
                for _x, _y, red, green, blue in pixels
            ) / len(pixels)

        settings_luminance = average_luminance(QIcon(Icons.SETTINGS.path))
        for candidate in (Icons.FLOAT, Icons.DOCK):
            assert average_luminance(QIcon(candidate.path)) >= settings_luminance * 0.9
