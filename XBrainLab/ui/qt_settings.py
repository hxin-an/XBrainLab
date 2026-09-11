"""Construct Qt preferences within the application's existing config boundary."""

import os

from PyQt6.QtCore import QSettings

from XBrainLab.platform_paths import CONFIG_DIR_ENV, user_config_dir


def application_settings(application: str = "XBrainLab") -> QSettings:
    """Honor an explicit config root; otherwise keep the native user store."""
    if os.environ.get(CONFIG_DIR_ENV, "").strip():
        path = user_config_dir() / "qt-settings" / f"{application}.ini"
        return QSettings(str(path), QSettings.Format.IniFormat)
    return QSettings("XBrainLab", application)
