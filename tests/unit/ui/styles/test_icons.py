"""Unit tests for Icons enum."""

from unittest.mock import patch

from XBrainLab.ui.styles.icons import Icons


class TestIconsEnum:
    def test_members_exist(self):
        assert Icons.LOGO.value == "logo.png"
        assert Icons.PLAY.value == "play.svg"
        assert Icons.STOP.value == "stop.svg"
        assert Icons.SETTINGS.value == "settings.svg"
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
