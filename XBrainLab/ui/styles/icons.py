"""Centralized icon path registry for XBrainLab UI."""

from enum import Enum

from XBrainLab.config import AppConfig


class Icons(Enum):
    """Centralized registry of icon paths.

    Each member maps a logical icon name to its filename. Use the
    ``path`` property to resolve the full filesystem path via
    ``AppConfig``.

    Example:
        >>> icon_path = Icons.LOGO.path

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
        """Resolve the full filesystem path for this icon.

        Returns:
            Absolute path string to the icon file.

        """
        return AppConfig.get_icon_path(self.value)

    @staticmethod
    def get(icon_enum):
        """Get the full path for an icon enum member.

        Args:
            icon_enum: An ``Icons`` enum member.

        Returns:
            Absolute path string to the icon file.

        """
        return icon_enum.path
