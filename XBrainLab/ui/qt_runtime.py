"""Qt runtime environment helpers used before creating QApplication."""

from __future__ import annotations

import os
from collections.abc import MutableMapping

QT_PLATFORM_ENV = "QT_QPA_PLATFORM"
XBRAINLAB_QT_PLATFORM_ENV = "XBRAINLAB_QT_PLATFORM"


def configure_qt_platform_for_runtime(
    env: MutableMapping[str, str] | None = None,
) -> str | None:
    """Set a stable Qt platform default for known desktop runtimes.

    The Windows WSL launcher already exports ``QT_QPA_PLATFORM=xcb`` because
    WSLg's Wayland path can crash VTK/PyVistaQt with a low-level ``BadWindow``.
    This helper gives the same protection to direct ``python run.py`` launches.

    Returns:
        The value that was applied, or ``None`` when the caller already supplied a
        platform or no runtime-specific default is needed.
    """
    target_env = env if env is not None else os.environ
    explicit_platform = target_env.get(QT_PLATFORM_ENV, "").strip()
    if explicit_platform:
        return None

    requested_platform = target_env.get(XBRAINLAB_QT_PLATFORM_ENV, "").strip()
    if requested_platform:
        target_env[QT_PLATFORM_ENV] = requested_platform
        return requested_platform

    if is_wslg_session(target_env):
        target_env[QT_PLATFORM_ENV] = "xcb"
        return "xcb"

    return None


def is_wslg_session(env: MutableMapping[str, str] | None = None) -> bool:
    """Return whether the current process looks like an interactive WSLg session."""
    target_env = env if env is not None else os.environ
    is_wsl = bool(
        target_env.get("WSL_DISTRO_NAME", "").strip()
        or target_env.get("WSL_INTEROP", "").strip()
    )
    has_wslg_display = bool(
        target_env.get("DISPLAY", "").strip()
        and target_env.get("WAYLAND_DISPLAY", "").strip()
    )
    return is_wsl and has_wslg_display
