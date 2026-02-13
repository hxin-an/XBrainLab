from enum import Enum

from XBrainLab.config import AppConfig


class Icons(Enum):
    """
    Centralized registry of icon paths.
    Usage: Icons.LOGO.path
    """

    # Define Icon Keys
    LOGO = "logo.png"
    PLAY = "play.svg"
    STOP = "stop.svg"
    SETTINGS = "settings.svg"
    REFRESH = "refresh.svg"
    SAVE = "save.svg"
    TRASH = "trash.svg"

    # ... add more as needed

    @property
    def path(self) -> str:
        """ """
        return AppConfig.get_icon_path(self.value)

    @staticmethod
    def get(icon_enum):
        """Helper to get path directly."""
        return icon_enum.path
