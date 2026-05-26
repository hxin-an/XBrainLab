import contextlib
import os
import subprocess
import sys

import pyvistaqt
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.styles.theme import Theme

from .plot_3d_head import Saliency3D

_INTERACTIVE_3D_PROBE_TIMEOUT_SECONDS = 10
_INTERACTIVE_3D_PROBE_CODE = r"""
import sys

from PyQt6.QtWidgets import QApplication
import pyvista as pv
import pyvistaqt

app = QApplication([])
plotter = pyvistaqt.QtInteractor()
plotter.add_mesh(pv.Sphere(radius=0.25), color="white")
plotter.show()
for _ in range(10):
    app.processEvents()
print(f"plotter_created={plotter is not None}")
plotter.close()
app.quit()
sys.exit(0)
"""

_INTERACTIVE_3D_PROBE_CACHE: dict[tuple[str, str, str, str], tuple[bool, str]] = {}


class Saliency3DPlotWidget(QWidget):
    """Widget for visualizing 3D Brain Saliency Maps using PyVista.
    Embeds a QtInteractor for interactive 3D rendering.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Plot Area
        self.plot_container = QWidget()
        self.plot_layout = QVBoxLayout(self.plot_container)
        self.plot_layout.setContentsMargins(0, 0, 0, 0)

        # Initial Placeholder
        lbl = QLabel("Select a plan and method to visualize")
        lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 14px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_layout.addWidget(lbl)

        layout.addWidget(self.plot_container, stretch=1)

        self.plotter_widget = None

    def show_error(self, msg):
        self.clear_plot()
        lbl = QLabel(f"Error: {msg}")
        lbl.setStyleSheet(
            f"color: {Theme.ACCENT_ERROR}; font-size: 14px; font-weight: bold;",
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_layout.addWidget(lbl)

    def show_message(self, msg):
        self.clear_plot()
        lbl = QLabel(msg)
        lbl.setStyleSheet(
            f"color: {Theme.WARNING}; font-size: 16px; font-weight: bold;",
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_layout.addWidget(lbl)

    def clear_plot(self):
        plotter = self.plotter_widget

        # Remove existing widgets
        for i in reversed(range(self.plot_layout.count())):
            item = self.plot_layout.itemAt(i)
            if item:
                w = item.widget()
                if w:
                    w.setParent(None)
                    if w is not plotter:
                        w.deleteLater()

        # Clean up plotter if exists
        if plotter:
            close_plotter = getattr(plotter, "close", None)
            if callable(close_plotter):
                with contextlib.suppress(Exception):
                    close_plotter()
            delete_later = getattr(plotter, "deleteLater", None)
            if callable(delete_later):
                delete_later()
            self.plotter_widget = None

    def update_plot(self, plan, trainer, method, absolute, eval_record):
        try:
            self.clear_plot()

            # Get Data
            if eval_record is None:
                eval_record = plan.get_eval_record()

            if not eval_record:
                raise ValueError("No evaluation record found.")  # noqa: TRY301

            epoch_data = trainer.get_dataset().get_epoch_data()

            # Montage Check
            positions = epoch_data.get_montage_position()
            if positions is None or len(positions) == 0:
                self.show_message(
                    "Please Set Montage First\n(Go to Configuration -> Set Montage)",
                )
                return

            # Event Selection (Default to first event for now, or add event selector to
            # Select the first event by default for visualization.
            # Future enhancement: Add a combo box to allow selecting specific event
            # types.
            events = list(epoch_data.event_id.keys())
            if not events:
                self.show_error("No events found in dataset.")
                return
            selected_event = events[0]

            available, reason = self._interactive_3d_runtime_available()
            if not available:
                self.show_message(reason)
                return

            # Instantiate QtInteractor for 3D plotting.
            self.plotter_widget = pyvistaqt.QtInteractor(self.plot_container)
            self.plot_layout.addWidget(self.plotter_widget)

            # Force initialization of the interactor to prevent _FakeEventHandler error
            if hasattr(self.plotter_widget, "interactor"):
                self.plotter_widget.interactor.Initialize()

            # Defer the actual plotting to ensure the widget is ready and interactor is
            # initialized
            QTimer.singleShot(
                100,
                lambda: self._do_3d_plot(eval_record, epoch_data, selected_event),
            )

        except Exception as e:
            logger.error("Error initializing 3D plot: %s", e, exc_info=True)
            self.show_error(str(e))

    def _do_3d_plot(self, eval_record, epoch_data, selected_event):
        try:
            if not self.plotter_widget:
                return

            saliency = Saliency3D(
                eval_record,
                epoch_data,
                selected_event,
                plotter=self.plotter_widget,
            )
            init_error = getattr(saliency, "init_error", "")
            if init_error:
                self.show_error(init_error)
                return
            if getattr(saliency, "engine", None) is None:
                self.show_error("3D saliency engine could not initialize.")
                return
            saliency.get_3d_head_plot()
        except Exception as e:
            logger.error("Error executing 3D plot: %s", e, exc_info=True)
            self.show_error(f"Error during plotting: {e}")

    @staticmethod
    def _interactive_3d_runtime_available() -> tuple[bool, str]:
        """Return whether an interactive OpenGL Qt runtime is available."""
        qt_platform = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
        pyvista_offscreen = os.environ.get("PYVISTA_OFF_SCREEN", "").strip().lower()
        if qt_platform in {"offscreen", "minimal"} or pyvista_offscreen in {
            "1",
            "true",
            "yes",
        }:
            return (
                False,
                "3D rendering requires an interactive OpenGL desktop session. "
                "Use the desktop launcher, or switch to Saliency Map, Spectrogram, "
                "or Topographic Map in this headless environment.",
            )
        if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
            return (
                False,
                "3D rendering requires an interactive Linux display with OpenGL. "
                "Use WSLg or a desktop session, or switch to a 2D saliency view.",
            )
        if sys.platform.startswith("linux"):
            return Saliency3DPlotWidget._probe_interactive_3d_runtime()
        return True, ""

    @staticmethod
    def _probe_interactive_3d_runtime() -> tuple[bool, str]:
        """Probe PyVistaQt in a child process before touching the live UI."""
        env = dict(os.environ)
        cache_key = (
            env.get("QT_QPA_PLATFORM", ""),
            env.get("DISPLAY", ""),
            env.get("WAYLAND_DISPLAY", ""),
            env.get("XDG_SESSION_TYPE", ""),
        )
        cached = _INTERACTIVE_3D_PROBE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        try:
            completed = subprocess.run(  # noqa: S603
                [sys.executable, "-c", _INTERACTIVE_3D_PROBE_CODE],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_INTERACTIVE_3D_PROBE_TIMEOUT_SECONDS,
                env=env,
            )
        except subprocess.TimeoutExpired:
            result = (
                False,
                "3D rendering did not start within the runtime probe timeout. "
                "Use a native desktop/OpenGL session or a 2D saliency view.",
            )
            _INTERACTIVE_3D_PROBE_CACHE[cache_key] = result
            return result

        if completed.returncode == 0 and "plotter_created=True" in completed.stdout:
            result = (True, "")
        else:
            detail = (
                completed.stderr.strip()
                or completed.stdout.strip()
                or f"probe exited with code {completed.returncode}"
            )
            first_line = detail.splitlines()[0]
            result = (
                False,
                "3D rendering is blocked by the current desktop OpenGL runtime "
                f"({first_line}). Use a native desktop/X11 session or a 2D "
                "saliency view.",
            )
        _INTERACTIVE_3D_PROBE_CACHE[cache_key] = result
        return result
