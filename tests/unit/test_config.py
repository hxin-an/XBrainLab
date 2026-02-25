"""Unit tests for AppConfig."""

import platform
import re
from pathlib import Path

from XBrainLab.config import AppConfig


class TestAppConfig:
    """AppConfig exposes paths, version, and regex patterns."""

    def test_app_name(self):
        assert AppConfig.APP_NAME == "XBrainLab"

    def test_version_format(self):
        parts = AppConfig.VERSION.split(".")
        assert len(parts) == 3
        for p in parts:
            assert p.isdigit()

    def test_base_dir_exists(self):
        assert isinstance(AppConfig.BASE_DIR, Path)
        assert AppConfig.BASE_DIR.exists()

    def test_resources_dir(self):
        assert AppConfig.RESOURCES_DIR == AppConfig.BASE_DIR / "XBrainLab" / "resources"

    def test_icons_dir(self):
        assert AppConfig.ICONS_DIR == AppConfig.RESOURCES_DIR / "icons"

    def test_models_3d_dir(self):
        expected = (
            AppConfig.BASE_DIR / "XBrainLab" / "backend" / "visualization" / "3Dmodel"
        )
        assert expected == AppConfig.MODELS_3D_DIR

    def test_default_font_matches_platform(self):
        expected = AppConfig._PLATFORM_FONTS.get(platform.system(), "sans-serif")
        assert expected == AppConfig.DEFAULT_FONT

    def test_default_font_size(self):
        assert AppConfig.DEFAULT_FONT_SIZE == 10

    def test_regex_session(self):
        assert re.search(AppConfig.REGEX_SESSION, "ses-abc123")
        assert re.search(AppConfig.REGEX_SESSION, "ses-A1b2C3")
        assert not re.search(AppConfig.REGEX_SESSION, "ses-")

    def test_regex_subject(self):
        assert re.search(AppConfig.REGEX_SUBJECT, "sub-01")
        assert re.search(AppConfig.REGEX_SUBJECT, "sub-ABC")
        assert not re.search(AppConfig.REGEX_SUBJECT, "sub-")

    def test_get_icon_path(self):
        path = AppConfig.get_icon_path("app.png")
        assert path.endswith("app.png")
        assert "icons" in path
