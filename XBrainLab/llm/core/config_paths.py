"""Platform-specific per-user paths for local assistant configuration."""

from __future__ import annotations

import os
import platform
from collections.abc import Mapping
from pathlib import Path

CONFIG_DIR_ENV = "XBRAINLAB_CONFIG_DIR"
SETTINGS_FILENAME = "settings.json"


def user_config_dir(
    *,
    environ: Mapping[str, str] | None = None,
    system_name: str | None = None,
    home: str | Path | None = None,
) -> Path:
    """Return XBrainLab's per-user config directory.

    Native Windows uses roaming AppData. Linux and WSL use the XDG config
    boundary, while macOS uses Application Support. ``XBRAINLAB_CONFIG_DIR``
    is an explicit override for tests and isolated deployments.
    """
    env = os.environ if environ is None else environ
    user_home = Path.home() if home is None else Path(home).expanduser()
    explicit_dir = str(env.get(CONFIG_DIR_ENV, "")).strip()
    if explicit_dir:
        explicit_path = Path(explicit_dir).expanduser()
        return (
            explicit_path if explicit_path.is_absolute() else user_home / explicit_path
        )

    current_system = system_name or platform.system()
    if current_system == "Windows":
        roaming = str(env.get("APPDATA", "")).strip()
        roaming_path = Path(roaming).expanduser()
        base_dir = (
            roaming_path
            if roaming and roaming_path.is_absolute()
            else user_home / "AppData" / "Roaming"
        )
        return base_dir / "XBrainLab"

    if current_system == "Darwin":
        return user_home / "Library" / "Application Support" / "XBrainLab"

    # WSL is a Linux process and deliberately keeps its config in the Linux
    # user's XDG boundary instead of writing through to a Windows profile.
    xdg_config_home = str(env.get("XDG_CONFIG_HOME", "")).strip()
    xdg_path = Path(xdg_config_home).expanduser()
    base_dir = (
        xdg_path
        if xdg_config_home and xdg_path.is_absolute()
        else user_home / ".config"
    )
    return base_dir / "xbrainlab"


def user_settings_path(
    *,
    environ: Mapping[str, str] | None = None,
    system_name: str | None = None,
    home: str | Path | None = None,
) -> Path:
    """Return the mutable local-assistant settings file for one OS user."""
    return (
        user_config_dir(
            environ=environ,
            system_name=system_name,
            home=home,
        )
        / SETTINGS_FILENAME
    )


def legacy_repo_settings_path(*, repo_root: str | Path | None = None) -> Path:
    """Return the old repo-root path used only as one-time migration input."""
    root = (
        Path(repo_root)
        if repo_root is not None
        else Path(__file__).resolve().parents[3]
    )
    return root / SETTINGS_FILENAME
