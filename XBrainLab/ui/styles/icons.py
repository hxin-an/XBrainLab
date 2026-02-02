import os
from enum import Enum


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
        """
        Resolves the absolute path to the icon file.
        Assumes icons are stored in XBrainLab/resources/icons or similar.
        Adjust base path logic as per project structure.
        """
        # Base path resolution logic roughly matching where main.py/app.py usually runs
        # or relative to this file.
        # Current file is in ui/styles/
        # Icons usually in resources/icons at project root or package root.

        # Hypothetical path: XBrainLab/resources/icons/
        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        # base_dir -> XBrainLab/

        icon_path = os.path.join(base_dir, "resources", "icons", self.value)

        # Fallback or check existence could be added here
        return icon_path

    @staticmethod
    def get(icon_enum):
        """Helper to get path directly."""
        return icon_enum.path
