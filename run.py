"""Entry point for the XBrainLab desktop application.

Launches the PyQt6-based GUI, optionally accepting CLI arguments for
tool debugging and model selection.

Usage::

    python run.py
    python run.py --tool-debug path/to/script.json
    python run.py --model local
"""

import argparse
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from time import monotonic, sleep
from typing import Protocol

# hf-xet can stall indefinitely while reconstructing large model shards under
# WSLg. Hugging Face reads this switch at import time, so set it before any
# product module can import huggingface_hub. Standard HTTP still resumes files.
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")

# Ensure the project root is importable when running the script directly.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from XBrainLab.ui.qt_runtime import (
    configure_qt_platform_for_runtime,
    run_qt_event_loop,
)

configure_qt_platform_for_runtime()

_RUN_ROOT = Path(__file__).resolve().parent
_STARTUP_SMOKE_CLOSE_MS_ENV = "XBRAINLAB_STARTUP_SMOKE_CLOSE_MS"
_CONFIG_DIR_ENV = "XBRAINLAB_CONFIG_DIR"


def _resolve_tool_debug_script(value: str) -> str:
    """Resolve a walkthrough before deferred Qt construction can change context."""
    requested = Path(value).expanduser()
    candidates = (
        (requested,)
        if requested.is_absolute()
        else (Path.cwd() / requested, _RUN_ROOT / requested)
    )
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_file():
            return str(resolved)
    raise argparse.ArgumentTypeError(
        "Assistant walkthrough profile was not found. Pass an existing JSON file path."
    )


from PyQt6.QtCore import QSettings, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

from XBrainLab.ui.window_placement import (
    center_widget_on_screen,
    choose_screen_for_saved_geometry,
    remember_startup_screen,
    screen_geometry_diagnostic_lines,
    startup_geometry_diagnostics_enabled,
    startup_screen_hint,
    widget_geometry_diagnostic_line,
)


class _Splash(QWidget):
    """Branded startup window shown while the heavier UI stack imports."""

    def __init__(self, pixmap: QPixmap) -> None:
        super().__init__(
            None,
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self._pixmap = pixmap
        self.setObjectName("XBrainLabStartupSplash")
        self.setWindowTitle("XBrainLab")
        self.setFixedSize(pixmap.size())
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(False)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        _ = event
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.end()

    def finish(self, window: QWidget) -> None:
        """Match QSplashScreen.finish enough for the startup path."""
        _ = window
        self.hide()
        self.deleteLater()


class _SplashFinisher(Protocol):
    """Minimal splash contract needed when presenting the main window."""

    def finish(self, window: QWidget) -> None:
        """Release the splash after the product window is visible."""


def _create_splash_pixmap() -> QPixmap:
    """Create the splash pixmap without importing the heavier UI stack."""
    pixmap = QPixmap(QSize(420, 200))
    pixmap.fill(QColor("#22262b"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.fillRect(0, 0, pixmap.width(), 6, QColor("#0e7ac4"))
    painter.fillRect(0, pixmap.height() - 2, pixmap.width(), 2, QColor("#333942"))
    painter.setPen(QPen(QColor("#4a5664"), 1))
    painter.drawRect(pixmap.rect().adjusted(0, 0, -1, -1))

    painter.setPen(QColor("#f1f1f1"))
    painter.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
    painter.drawText(
        pixmap.rect().adjusted(0, -18, 0, -18),
        Qt.AlignmentFlag.AlignCenter,
        "XBrainLab",
    )
    painter.setPen(QColor("#a0a0a0"))
    painter.setFont(QFont("Segoe UI", 11))
    painter.drawText(
        pixmap.rect().adjusted(0, 118, 0, 0),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
        "Loading...",
    )
    painter.end()
    return pixmap


def _flush_splash_paint(
    app: QApplication,
    splash: _Splash,
    *,
    paint_wait_ms: int = 220,
) -> None:
    """Force early splash painting before imports block the Qt event loop."""
    splash.raise_()
    splash.activateWindow()
    splash.repaint()
    app.processEvents()
    deadline = monotonic() + max(0, paint_wait_ms) / 1000
    while monotonic() < deadline:
        splash.repaint()
        app.processEvents()
        sleep(0.01)


def _create_centered_splash(app: QApplication, saved_geometry=None) -> _Splash:
    """Create a splash centered on the same startup screen as MainWindow."""
    splash = _Splash(_create_splash_pixmap())
    target_screen = choose_screen_for_saved_geometry(saved_geometry)
    remember_startup_screen(target_screen)
    center_widget_on_screen(splash, target_screen)
    app.processEvents()
    return splash


def _show_centered_splash(
    app: QApplication,
    splash: _Splash,
    *,
    paint_wait_ms: int = 220,
) -> None:
    """Show the splash and recenter after the window manager assigns a frame."""
    splash.show()
    center_widget_on_screen(splash, startup_screen_hint() or app.primaryScreen())
    _flush_splash_paint(app, splash, paint_wait_ms=paint_wait_ms)


def _request_main_window_activation(
    app: QApplication,
    window: QWidget,
) -> None:
    """Bring the product window forward after the splash releases focus."""
    try:
        if window.isMinimized():
            window.showNormal()
        app.setActiveWindow(window)
        window.raise_()
        window.activateWindow()
    except RuntimeError:
        # The queued request may race with an immediate application shutdown.
        return


def _present_main_window(
    app: QApplication,
    splash: _SplashFinisher,
    window: QWidget,
) -> None:
    """Show and activate the main window reliably across WSLg and remote desktops."""
    window.show()
    app.processEvents()
    splash.finish(window)
    app.processEvents()
    _request_main_window_activation(app, window)

    # WSLg can ignore an activation request issued before the event loop starts.
    QTimer.singleShot(0, lambda: _request_main_window_activation(app, window))


def _configure_product_window_lifetime(window: QWidget) -> None:
    """Destroy native child resources before the interpreter tears down."""
    window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)


def _configure_application_identity(app: QApplication) -> None:
    """Give every native Qt surface the product identity, never ``run.py``."""
    app.setOrganizationName("XBrainLab")
    app.setApplicationName("XBrainLab")
    app.setApplicationDisplayName("XBrainLab")


def _configure_qt_application_attributes() -> None:
    """Keep dialogs inside Qt instead of spawning fragile WSL native surfaces."""
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_DontUseNativeDialogs,
        True,
    )


def _configure_startup_smoke_qsettings(
    environ: Mapping[str, str] = os.environ,
) -> Path | None:
    """Keep the explicit startup smoke out of the runner's native settings."""
    if not environ.get(_STARTUP_SMOKE_CLOSE_MS_ENV, "").strip():
        return None
    raw_path = environ.get(_CONFIG_DIR_ENV, "").strip()
    if not raw_path:
        raise ValueError("Startup smoke requires an isolated XBRAINLAB_CONFIG_DIR.")
    settings_root = Path(raw_path).expanduser()
    if not settings_root.is_absolute():
        raise ValueError("Startup smoke config path must be absolute.")
    settings_root.mkdir(parents=True, exist_ok=True)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(settings_root),
    )
    return settings_root.resolve()


def _startup_smoke_close_delay_ms(
    environ: Mapping[str, str] = os.environ,
) -> int | None:
    """Return the bounded developer-smoke close delay, if explicitly enabled."""
    raw_value = environ.get(_STARTUP_SMOKE_CLOSE_MS_ENV, "").strip()
    if not raw_value:
        return None
    try:
        delay_ms = int(raw_value)
    except ValueError as error:
        raise ValueError("Startup smoke close delay must be an integer.") from error
    if not 0 <= delay_ms <= 10_000:
        raise ValueError("Startup smoke close delay must be between 0 and 10000 ms.")
    return delay_ms


def _schedule_startup_smoke_close(window: QWidget) -> None:
    """Request normal product shutdown only for the explicit developer smoke."""
    delay_ms = _startup_smoke_close_delay_ms()
    if delay_ms is None:
        return

    print(
        f"XBrainLab startup smoke platform: {QApplication.platformName()}",
        flush=True,
    )

    def request_close() -> None:
        print("XBrainLab startup smoke close requested", flush=True)
        window.close()

    QTimer.singleShot(delay_ms, request_close)


def main() -> None:
    """Parse CLI arguments, create the application, and show the main window.

    The function initialises a :class:`~XBrainLab.backend.study.Study`,
    builds the :class:`~XBrainLab.ui.main_window.MainWindow`, and enters
    the Qt event loop.  It calls ``sys.exit`` when the window is closed.
    """
    parser = argparse.ArgumentParser(description="XBrainLab Application")
    parser.add_argument(
        "--tool-debug",
        type=_resolve_tool_debug_script,
        help="Path to tool debug script (JSON)",
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=["local"],
        help="Use the local-only assistant runtime for this session.",
    )
    args = parser.parse_args()

    _configure_qt_application_attributes()
    _configure_startup_smoke_qsettings()
    app = QApplication(sys.argv)
    _configure_application_identity(app)

    # --- Splash Screen (shown while heavy imports load) ---
    settings = QSettings("XBrainLab", "XBrainLab")
    splash = _create_centered_splash(app, settings.value("main_window/geometry", None))
    _show_centered_splash(app, splash)

    # --- Heavy imports deferred until after splash is visible ---
    from XBrainLab.backend.study import Study
    from XBrainLab.backend.utils.logger import logger
    from XBrainLab.ui.main_window import MainWindow

    logger.info("Starting XBrainLab (PyQt6)...")
    if startup_geometry_diagnostics_enabled():
        logger.info(
            "Startup geometry diagnostics enabled with XBRAINLAB_STARTUP_DIAGNOSTICS=1"
        )
        for line in screen_geometry_diagnostic_lines():
            logger.info(line)
        logger.info(widget_geometry_diagnostic_line("splash.after_show", splash))

    if args.tool_debug:
        logger.info("Tool Debug Mode enabled. Script: %s", args.tool_debug)
        app.setProperty("tool_debug_script", args.tool_debug)

    # ``local`` selects the local backend; model selection stays in persisted settings.
    if args.model:
        logger.info("CLI local backend compatibility mode requested")

    app.setStyle("Fusion")
    from XBrainLab.ui.dialog_button_policy import install_dialog_button_policy

    install_dialog_button_policy(app)

    study = Study()

    window = MainWindow(study)
    _configure_product_window_lifetime(window)
    _present_main_window(app, splash, window)
    _schedule_startup_smoke_close(window)
    if startup_geometry_diagnostics_enabled():
        logger.info(widget_geometry_diagnostic_line("main_window.after_show", window))

    raise SystemExit(run_qt_event_loop(app))


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()
