"""Unit tests for AppConfig."""

import tomllib
from pathlib import Path

from XBrainLab import FALLBACK_VERSION
from XBrainLab.config import AppConfig


class TestAppConfig:
    """AppConfig resolves a shipped icon and participates in release versioning."""

    def test_version_format(self):
        parts = AppConfig.VERSION.split(".")
        assert len(parts) == 3
        for p in parts:
            assert p.isdigit()

    def test_release_version_contract_is_single_sourced(self):
        pyproject = tomllib.loads(
            (AppConfig.BASE_DIR / "pyproject.toml").read_text(encoding="utf-8")
        )
        commitizen = pyproject["tool"]["commitizen"]

        assert AppConfig.VERSION == "0.8.0"
        assert FALLBACK_VERSION == AppConfig.VERSION
        assert pyproject["project"]["version"] == AppConfig.VERSION
        assert commitizen["version"] == AppConfig.VERSION
        assert commitizen["changelog_file"] == "CHANGELOG.md"
        assert "XBrainLab/__init__.py:FALLBACK_VERSION" in commitizen["version_files"]

    def test_get_icon_path(self):
        path = Path(AppConfig.get_icon_path("settings.svg"))
        expected = (
            Path(__file__).resolve().parents[2]
            / "XBrainLab"
            / "resources"
            / "icons"
            / "settings.svg"
        )
        assert path == expected
        assert path.is_file()
