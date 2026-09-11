"""Bundled icon paths and release metadata for XBrainLab."""

import sys
from pathlib import Path


class AppConfig:
    """Resolve bundled icons in development and frozen applications."""

    VERSION = "0.8.0"

    # Determine base path (handle frozen executable vs. development script)
    if getattr(sys, "frozen", False):
        BASE_DIR = Path(sys.executable).parent
    else:
        # __file__ resides in XBrainLab/, so the project root is one level up.
        BASE_DIR = Path(__file__).resolve().parent.parent

    RESOURCES_DIR = BASE_DIR / "XBrainLab" / "resources"
    ICONS_DIR = RESOURCES_DIR / "icons"

    @classmethod
    def get_icon_path(cls, icon_name: str) -> str:
        """Return the absolute path for a named icon asset.

        Args:
            icon_name: Filename of the icon (e.g. ``"settings.svg"``).

        Returns:
            Absolute filesystem path to the icon.

        """
        return str(cls.ICONS_DIR / icon_name)
