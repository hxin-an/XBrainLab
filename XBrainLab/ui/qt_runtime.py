"""Qt runtime environment helpers used before creating QApplication."""

from __future__ import annotations

import gc
import os
from collections.abc import MutableMapping
from typing import Any

QT_PLATFORM_ENV = "QT_QPA_PLATFORM"
XBRAINLAB_QT_PLATFORM_ENV = "XBRAINLAB_QT_PLATFORM"


def drain_qt_runtime_after_event_loop(app: Any, *, cycles: int = 3) -> None:
    """Release deferred Qt wrappers before Python interpreter teardown.

    Qt shutdown can queue additional ``DeferredDelete`` events while child
    widgets, threads, and native-backed canvases are being released.  Draining
    those events while ``QApplication`` is still alive prevents their wrappers
    from being finalized later in an undefined interpreter-shutdown order.
    """
    if cycles < 1:
        raise ValueError("Qt cleanup requires at least one drain cycle.")

    # Import only after the platform environment has been configured.  This
    # module is intentionally imported before PyQt by the desktop entry point.
    from PyQt6.QtCore import QEvent  # noqa: PLC0415 - platform must be configured first

    for _ in range(cycles):
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        gc.collect()


def run_qt_event_loop(app: Any) -> int:
    """Run the desktop event loop and drain native wrappers before returning."""
    exit_code = int(app.exec())
    drain_qt_runtime_after_event_loop(app)
    return exit_code


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
