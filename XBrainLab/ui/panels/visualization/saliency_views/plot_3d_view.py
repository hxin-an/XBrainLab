import contextlib
import os
import subprocess
import sys
from typing import Any, cast

import pyvistaqt
from PyQt6 import sip
from PyQt6.QtCore import Qt, QThreadPool, QTimer
from PyQt6.QtWidgets import QApplication, QLabel, QSizePolicy, QVBoxLayout, QWidget

from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.core.worker import Worker
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
        self._runtime_probe_worker = None
        self._pending_3d_request = None
        self._engine_worker = None
        self._engine_request_id = 0
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
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 14px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_layout.addWidget(lbl)

        layout.addWidget(self.plot_container, stretch=1)

        self.plotter_widget: Any = None

    def show_error(self, msg):
        self.clear_plot()
        lbl = self._message_label(f"Error: {msg}")
        lbl.setStyleSheet(
            f"color: {Theme.ACCENT_ERROR}; font-size: 14px; font-weight: bold;",
        )
        self.plot_layout.addWidget(lbl, stretch=1)

    def show_message(self, msg):
        self.clear_plot()
        lbl = self._message_label(msg)
        lbl.setStyleSheet(
            f"color: {Theme.WARNING}; font-size: 16px; font-weight: bold;",
        )
        self.plot_layout.addWidget(lbl, stretch=1)

    @staticmethod
    def _message_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setContentsMargins(16, 16, 16, 16)
        lbl.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        lbl.setMinimumWidth(0)
        lbl.setMinimumHeight(80)
        return lbl

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
            if available is None:
                self.show_message(reason)
                self._start_interactive_3d_runtime_probe(
                    plan,
                    trainer,
                    method,
                    absolute,
                    eval_record,
                )
                return
            if not available:
                self.show_message(reason)
                return

            self._start_3d_engine_worker(
                eval_record,
                epoch_data,
                selected_event,
                method=method,
                absolute=absolute,
            )

        except Exception as e:
            logger.error("Error initializing 3D plot: %s", e, exc_info=True)
            if not self._qt_object_deleted(self):
                self.show_error(str(e))

    def _start_3d_engine_worker(
        self,
        eval_record,
        epoch_data,
        selected_event,
        *,
        method="Gradient",
        absolute=False,
    ) -> None:
        self._engine_request_id += 1
        request_id = self._engine_request_id
        self.show_message("Preparing 3D view...")
        worker = Worker(
            Saliency3D.prepare_engine,
            eval_record,
            epoch_data,
            selected_event,
            method=method,
            absolute=absolute,
        )
        self._engine_worker = worker
        worker.signals.result.connect(
            lambda result, rid=request_id: self._on_3d_engine_ready(
                rid,
                result,
                eval_record,
                epoch_data,
                selected_event,
                method=method,
                absolute=absolute,
            ),
        )
        worker.signals.error.connect(
            lambda error, rid=request_id: self._on_3d_engine_error(rid, error),
        )
        thread_pool = QThreadPool.globalInstance()
        if thread_pool is None:
            self._engine_worker = None
            self.show_message("3D engine could not start. Use a 2D saliency view.")
            return
        thread_pool.start(worker)

    def _on_3d_engine_ready(
        self,
        request_id,
        result,
        eval_record,
        epoch_data,
        selected_event,
        *,
        method="Gradient",
        absolute=False,
    ) -> None:
        if self._qt_object_deleted(self) or request_id != self._engine_request_id:
            return
        self._engine_worker = None
        prepared_engine, prepared_channel_count = result
        app = QApplication.instance()
        if app is not None:
            with contextlib.suppress(Exception):
                prepared_engine.moveToThread(app.thread())
        self.clear_plot()
        self.plotter_widget = cast(
            QWidget,
            pyvistaqt.QtInteractor(self.plot_container),
        )
        self.plot_layout.addWidget(self.plotter_widget)
        interactor = getattr(self.plotter_widget, "interactor", None)
        if interactor is not None:
            interactor.Initialize()
        QTimer.singleShot(
            100,
            lambda: self._do_3d_plot_if_alive(
                eval_record,
                epoch_data,
                selected_event,
                method=method,
                absolute=absolute,
                prepared_engine=prepared_engine,
                prepared_channel_count=prepared_channel_count,
            ),
        )

    def _on_3d_engine_error(self, request_id, error: tuple) -> None:
        if self._qt_object_deleted(self) or request_id != self._engine_request_id:
            return
        self._engine_worker = None
        message = error[1] if len(error) > 1 else error
        self.show_error(str(message))

    def _do_3d_plot_if_alive(
        self,
        eval_record,
        epoch_data,
        selected_event,
        *,
        method="Gradient",
        absolute=False,
        prepared_engine=None,
        prepared_channel_count=None,
    ) -> None:
        """Run delayed 3D plotting only while the Qt widget still exists."""
        if self._qt_object_deleted(self) or self._qt_object_deleted(
            self.plotter_widget,
        ):
            return
        self._do_3d_plot(
            eval_record,
            epoch_data,
            selected_event,
            method=method,
            absolute=absolute,
            prepared_engine=prepared_engine,
            prepared_channel_count=prepared_channel_count,
        )

    def _do_3d_plot(
        self,
        eval_record,
        epoch_data,
        selected_event,
        *,
        method="Gradient",
        absolute=False,
        prepared_engine=None,
        prepared_channel_count=None,
    ):
        try:
            if self._qt_object_deleted(self) or self._qt_object_deleted(
                self.plotter_widget,
            ):
                return
            if not self.plotter_widget:
                return

            saliency = Saliency3D(
                eval_record,
                epoch_data,
                selected_event,
                method=method,
                absolute=absolute,
                plotter=self.plotter_widget,
                prepared_engine=prepared_engine,
                prepared_channel_count=prepared_channel_count,
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
            if not self._qt_object_deleted(self):
                self.show_error(f"Error during plotting: {e}")

    @staticmethod
    def _qt_object_deleted(obj) -> bool:
        if obj is None:
            return False
        try:
            return bool(sip.isdeleted(obj))
        except (AttributeError, TypeError, RuntimeError):
            return False

    @staticmethod
    def _interactive_3d_runtime_available() -> tuple[bool | None, str]:
        """Return whether an interactive OpenGL Qt runtime is available."""
        qt_platform = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
        active_qt_platform = Saliency3DPlotWidget._active_qt_platform_name()
        pyvista_offscreen = os.environ.get("PYVISTA_OFF_SCREEN", "").strip().lower()
        if (
            qt_platform in {"offscreen", "minimal"}
            or active_qt_platform in {"offscreen", "minimal"}
            or pyvista_offscreen in {"1", "true", "yes"}
        ):
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
            cache_key = Saliency3DPlotWidget._runtime_probe_cache_key()
            cached = _INTERACTIVE_3D_PROBE_CACHE.get(cache_key)
            if cached is not None:
                return cached
            return (
                None,
                "Checking 3D runtime... If this takes more than a few seconds, "
                "use a 2D saliency view.",
            )
        return True, ""

    def _start_interactive_3d_runtime_probe(
        self,
        plan,
        trainer,
        method,
        absolute,
        eval_record,
    ) -> None:
        self._pending_3d_request = (plan, trainer, method, absolute, eval_record)
        if self._runtime_probe_worker is not None:
            return
        worker = Worker(self._probe_interactive_3d_runtime)
        self._runtime_probe_worker = worker
        worker.signals.result.connect(self._on_interactive_3d_runtime_probe_result)
        worker.signals.error.connect(self._on_interactive_3d_runtime_probe_error)
        thread_pool = QThreadPool.globalInstance()
        if thread_pool is None:
            self._runtime_probe_worker = None
            self._pending_3d_request = None
            self.show_message(
                "3D runtime check could not start. Use a 2D saliency view.",
            )
            return
        thread_pool.start(worker)

    def _on_interactive_3d_runtime_probe_result(self, result) -> None:
        if self._qt_object_deleted(self):
            return
        self._runtime_probe_worker = None
        available, reason = result
        pending = self._pending_3d_request
        self._pending_3d_request = None
        if not available:
            self.show_message(str(reason))
            return
        if pending is not None:
            self.update_plot(*pending)

    def _on_interactive_3d_runtime_probe_error(self, error: tuple) -> None:
        if self._qt_object_deleted(self):
            return
        self._runtime_probe_worker = None
        self._pending_3d_request = None
        message = error[1] if len(error) > 1 else error
        self.show_message(
            "3D rendering could not be checked in the background "
            f"({message}). Use a 2D saliency view.",
        )

    @staticmethod
    def _active_qt_platform_name() -> str:
        """Return the actual QApplication platform if a Qt app exists."""
        app = QApplication.instance()
        if app is None:
            return ""
        platform_name = getattr(app, "platformName", None)
        if not callable(platform_name):
            return ""
        return str(platform_name()).strip().lower()

    @staticmethod
    def _probe_interactive_3d_runtime() -> tuple[bool, str]:
        """Probe PyVistaQt in a child process before touching the live UI."""
        env = dict(os.environ)
        cache_key = Saliency3DPlotWidget._runtime_probe_cache_key(env)
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

    @staticmethod
    def _runtime_probe_cache_key(
        env: dict[str, str] | None = None,
    ) -> tuple[str, str, str, str]:
        source = env if env is not None else os.environ
        return (
            source.get("QT_QPA_PLATFORM", ""),
            source.get("DISPLAY", ""),
            source.get("WAYLAND_DISPLAY", ""),
            source.get("XDG_SESSION_TYPE", ""),
        )
