import os
import sys


class AppConfig:
    """
    Global Application Configuration.
    Centralizes paths, constants, and environment defaults.
    """

    APP_NAME = "XBrainLab"
    VERSION = "0.5.2"

    # Paths
    # Determine base path (handle frozen executable vs script)
    if getattr(sys, "frozen", False):
        BASE_DIR = os.path.dirname(sys.executable)
    else:
        # Assuming constants.py is in XBrainLab/
        BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    RESOURCES_DIR = os.path.join(BASE_DIR, "XBrainLab", "resources")
    ICONS_DIR = os.path.join(RESOURCES_DIR, "icons")

    # 3D Models
    MODELS_3D_DIR = os.path.join(
        BASE_DIR, "XBrainLab", "backend", "visualization", "3Dmodel"
    )

    # Defaults
    DEFAULT_FONT = "Segoe UI"
    DEFAULT_FONT_SIZE = 10

    # Regex Patterns (Common)
    REGEX_SESSION = r"(ses-[a-zA-Z0-9]+)"
    REGEX_SUBJECT = r"(sub-[a-zA-Z0-9]+)"

    @classmethod
    def get_icon_path(cls, icon_name: str) -> str:
        """Get absolute path for an icon."""
        return os.path.join(cls.ICONS_DIR, icon_name)
