"""Application-wide configuration for XBrainLab.

Defines paths, UI defaults, and regex patterns used throughout the project.
All settings are exposed as class-level attributes on :class:`AppConfig`.
"""

import platform
import sys
from pathlib import Path
from typing import ClassVar


class AppConfig:
    """Global application configuration.

    Centralizes base paths, resource directories, UI defaults, and common
    regex patterns so that every module can reference a single source of
    truth.

    Attributes:
        APP_NAME: Human-readable application name.
        VERSION: Semantic version string.
        BASE_DIR: Project root directory (handles frozen executables).
        RESOURCES_DIR: Path to bundled resource files.
        ICONS_DIR: Path to icon assets.
        MODELS_3D_DIR: Path to 3-D head-model files.
        DEFAULT_FONT: Default UI font family (platform-aware).
        DEFAULT_FONT_SIZE: Default UI font size in points.
        REGEX_SESSION: Pattern for BIDS session identifiers.
        REGEX_SUBJECT: Pattern for BIDS subject identifiers.

    """

    APP_NAME = "XBrainLab"
    VERSION = "0.5.3"

    # Determine base path (handle frozen executable vs. development script)
    if getattr(sys, "frozen", False):
        BASE_DIR = Path(sys.executable).parent
    else:
        # __file__ resides in XBrainLab/, so the project root is one level up.
        BASE_DIR = Path(__file__).resolve().parent.parent

    RESOURCES_DIR = BASE_DIR / "XBrainLab" / "resources"
    ICONS_DIR = RESOURCES_DIR / "icons"

    # 3D Models
    MODELS_3D_DIR = BASE_DIR / "XBrainLab" / "backend" / "visualization" / "3Dmodel"

    # Defaults — pick a font available on each OS
    _PLATFORM_FONTS: ClassVar[dict[str, str]] = {
        "Windows": "Segoe UI",
        "Darwin": "SF Pro Text",
        "Linux": "Noto Sans",
    }
    DEFAULT_FONT = _PLATFORM_FONTS.get(platform.system(), "sans-serif")
    DEFAULT_FONT_SIZE = 10

    # Regex Patterns (Common)
    REGEX_SESSION = r"(ses-[a-zA-Z0-9]+)"
    REGEX_SUBJECT = r"(sub-[a-zA-Z0-9]+)"

    @classmethod
    def get_icon_path(cls, icon_name: str) -> str:
        """Return the absolute path for a named icon asset.

        Args:
            icon_name: Filename of the icon (e.g. ``"app.png"``).

        Returns:
            Absolute filesystem path to the icon.

        """
        return str(cls.ICONS_DIR / icon_name)
