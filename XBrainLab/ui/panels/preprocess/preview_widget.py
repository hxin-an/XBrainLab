"""Signal preview widget with time-domain and frequency-domain plots.

Uses PyQtGraph for high-performance interactive visualization with
crosshair cursors and debounced navigation controls.
"""

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme

# Set Global Config for PyQtGraph to match Theme
pg.setConfigOption("background", Theme.BACKGROUND_MID)
pg.setConfigOption("foreground", Theme.TEXT_MUTED)
pg.setConfigOption("antialias", True)

PREVIEW_RENDER_FAILED_MESSAGE = (
    "The current signal could not be displayed. Reopen Preprocess to retry. "
    "If the issue continues, reload the EEG data."
)


class PreviewWidget(QWidget):
    """Widget for signal visualization (time and frequency domains).

    Provides interactive PyQtGraph plots with crosshair cursors,
    channel selection, Y-scale control, and time/epoch navigation.

    Attributes:
        request_plot_update: Signal emitted when plot parameters change
            and a redraw is needed.
        plot_time: ``pg.PlotWidget`` for the time-domain view.
        plot_freq: ``pg.PlotWidget`` for the frequency-domain (PSD) view.
        chan_combo: ``QComboBox`` for selecting the displayed channel.
        yscale_spin: ``QDoubleSpinBox`` for manual Y-axis scaling.
        time_slider: ``QSlider`` for scrubbing through time or epochs.
        time_spin: ``QDoubleSpinBox`` for precise time/epoch entry.
        plot_timer: ``QTimer`` used for debouncing parameter changes.

    """

    # Signal to request a plot update from the controller/plotter
    request_plot_update = pyqtSignal()
    MAX_EVENT_MARKERS = 32

    def __init__(self, parent=None):
        """Initialize the preview widget.

        Args:
            parent: Optional parent widget.

        """
        super().__init__(parent)
        self._native_plot_shutdown = False
        self.init_ui()
        self.setup_timer()

    def init_ui(self):
        """Build layout: tabbed plots, channel/Y-scale controls, and navigation."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 1. Plot Area
        self.plot_group = QGroupBox("SIGNAL PREVIEW")
        plot_layout = QVBoxLayout()
        plot_layout.setContentsMargins(10, 20, 10, 10)
        self.preview_stack = QStackedWidget()
        self.plot_content = QWidget()
        plot_content_layout = QVBoxLayout(self.plot_content)
        plot_content_layout.setContentsMargins(0, 0, 0, 0)
        plot_content_layout.setSpacing(10)

        # Tabs for Time/Freq
        self.plot_tabs = QTabWidget()
        self.plot_tabs.setStyleSheet(Stylesheets.TAB_WIDGET_CLEAN)

        # Tab 1: Time Domain
        self.tab_time = QWidget()
        time_layout = QVBoxLayout(self.tab_time)

        self.plot_time = pg.PlotWidget()
        self.plot_time.setLabel("left", "Amplitude", units="uV")
        self.plot_time.setLabel("bottom", "Time", units="s")
        self.plot_time.showGrid(x=True, y=True, alpha=0.3)
        self.plot_time.getAxis("left").setPen(Theme.BORDER)
        self.plot_time.getAxis("bottom").setPen(Theme.BORDER)
        # Disable properties menu and Mouse Interaction (Zoom/Pan)
        self.plot_time.setMenuEnabled(False)
        self.plot_time.setMouseEnabled(x=False, y=False)
        self.plot_time.getPlotItem().vb.setMouseEnabled(x=False, y=False)
        self.plot_time.getPlotItem().buttonsHidden = True
        self.plot_time.hideButtons()
        self.time_event_markers = []
        self.time_original_curve = self.plot_time.plot(
            [],
            [],
            pen=pg.mkPen(
                Theme.CHART_ORIGINAL_DATA,
                width=1,
                style=Qt.PenStyle.DashLine,
            ),
            name="Original",
        )
        self.time_current_curve = self.plot_time.plot(
            [],
            [],
            pen=pg.mkPen(Theme.CHART_PRIMARY, width=1.5),
            name="Current",
        )
        self.time_current_curve.sigPlotChanged.connect(
            self._on_current_curve_data_changed
        )

        # Monkey-patch leaveEvent to hide crosshair when mouse leaves the widget
        self._orig_leave_time = self.plot_time.leaveEvent

        def on_leave_time(e):
            self.v_line_time.hide()
            self.h_line_time.hide()
            self.label_time.hide()
            if self._orig_leave_time:
                self._orig_leave_time(e)

        self.plot_time.leaveEvent = on_leave_time

        # Crosshair Time
        self.v_line_time = pg.InfiniteLine(
            angle=90,
            movable=False,
            pen=pg.mkPen(Theme.ACCENT_WARNING, width=1, style=Qt.PenStyle.DashLine),
        )
        self.h_line_time = pg.InfiniteLine(
            angle=0,
            movable=False,
            pen=pg.mkPen(Theme.ACCENT_WARNING, width=1, style=Qt.PenStyle.DashLine),
        )
        self.label_time = pg.TextItem(
            anchor=(0, 1),
            color=Theme.ACCENT_WARNING,
            fill=(30, 30, 30, 200),  # Semi-transparent dark background
        )
        self.v_line_time.setZValue(1000)
        self.h_line_time.setZValue(1000)
        self.label_time.setZValue(1000)
        self.plot_time.addItem(self.v_line_time, ignoreBounds=True)
        self.plot_time.addItem(self.h_line_time, ignoreBounds=True)
        self.plot_time.addItem(self.label_time, ignoreBounds=True)
        self.proxy_time = pg.SignalProxy(
            self.plot_time.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._mouse_moved_time,
        )

        time_layout.addWidget(self.plot_time)
        self.plot_tabs.addTab(self.tab_time, "Time Domain")

        # Tab 2: Frequency Domain (PSD)
        self.tab_freq = QWidget()
        freq_layout = QVBoxLayout(self.tab_freq)

        self.plot_freq = pg.PlotWidget()
        self.plot_freq.setLabel("left", "Power", units="dB/Hz")
        self.plot_freq.setLabel("bottom", "Frequency", units="Hz")
        self.plot_freq.showGrid(x=True, y=True, alpha=0.3)
        self.plot_freq.getAxis("left").setPen(Theme.BORDER)
        self.plot_freq.getAxis("bottom").setPen(Theme.BORDER)
        # Disable properties menu and Mouse Interaction (Zoom/Pan)
        self.plot_freq.setMenuEnabled(False)
        self.plot_freq.setMouseEnabled(x=False, y=False)
        self.plot_freq.getPlotItem().vb.setMouseEnabled(x=False, y=False)
        self.plot_freq.getPlotItem().buttonsHidden = True
        self.plot_freq.hideButtons()
        self.freq_original_curve = self.plot_freq.plot(
            [],
            [],
            pen=pg.mkPen(
                Theme.CHART_ORIGINAL_DATA,
                width=1,
                style=Qt.PenStyle.DashLine,
            ),
            name="Original",
        )
        self.freq_current_curve = self.plot_freq.plot(
            [],
            [],
            pen=pg.mkPen(Theme.CHART_PRIMARY, width=1.5),
            name="Current",
        )

        # Monkey-patch leaveEvent to hide crosshair when mouse leaves the widget
        self._orig_leave_freq = self.plot_freq.leaveEvent

        def on_leave_freq(e):
            self.v_line_freq.hide()
            self.h_line_freq.hide()
            self.label_freq.hide()
            if self._orig_leave_freq:
                self._orig_leave_freq(e)

        self.plot_freq.leaveEvent = on_leave_freq

        # Crosshair Freq
        self.v_line_freq = pg.InfiniteLine(
            angle=90,
            movable=False,
            pen=pg.mkPen(Theme.ACCENT_WARNING, width=1, style=Qt.PenStyle.DashLine),
        )
        self.h_line_freq = pg.InfiniteLine(
            angle=0,
            movable=False,
            pen=pg.mkPen(Theme.ACCENT_WARNING, width=1, style=Qt.PenStyle.DashLine),
        )
        self.label_freq = pg.TextItem(
            anchor=(0, 1),
            color=Theme.ACCENT_WARNING,
            fill=(30, 30, 30, 200),  # Semi-transparent dark background
        )
        self.v_line_freq.setZValue(1000)
        self.h_line_freq.setZValue(1000)
        self.label_freq.setZValue(1000)
        self.plot_freq.addItem(self.v_line_freq, ignoreBounds=True)
        self.plot_freq.addItem(self.h_line_freq, ignoreBounds=True)
        self.plot_freq.addItem(self.label_freq, ignoreBounds=True)
        self.proxy_freq = pg.SignalProxy(
            self.plot_freq.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._mouse_moved_freq,
        )

        freq_layout.addWidget(self.plot_freq)
        self.plot_tabs.addTab(self.tab_freq, "Frequency (PSD)")
        self.plot_tabs.currentChanged.connect(self._on_plot_param_changed)

        plot_content_layout.addWidget(self.plot_tabs)

        # 2. Controls (Channel, Y-Scale)
        ctrl_layout = QHBoxLayout()
        self.channel_label = QLabel("Channel:")
        ctrl_layout.addWidget(self.channel_label)
        self.chan_combo = QComboBox()
        self.chan_combo.setMinimumWidth(100)
        self.chan_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.chan_combo.currentIndexChanged.connect(self._on_plot_param_changed)
        channel_model = self.chan_combo.model()
        if channel_model is not None:
            channel_model.rowsInserted.connect(self._on_channels_inserted)
        ctrl_layout.addWidget(self.chan_combo)

        ctrl_layout.addSpacing(20)
        self.yscale_label = QLabel("Y-Scale (uV):")
        ctrl_layout.addWidget(self.yscale_label)
        self.yscale_spin = QDoubleSpinBox()
        self.yscale_spin.setRange(0, 5000)
        self.yscale_spin.setValue(0)  # 0 = Auto
        self.yscale_spin.setSpecialValueText("Auto")
        self.yscale_spin.setSingleStep(10)
        self.yscale_spin.valueChanged.connect(self._on_plot_param_changed)
        ctrl_layout.addWidget(self.yscale_spin)

        ctrl_layout.addStretch()
        plot_content_layout.addLayout(ctrl_layout)

        # 3. Time Navigation
        time_nav_layout = QHBoxLayout()
        self.time_label = QLabel("Time / Epoch:")
        time_nav_layout.addWidget(self.time_label)

        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 100)
        self.time_slider.valueChanged.connect(self._on_time_slider_changed)
        time_nav_layout.addWidget(self.time_slider)

        self.time_spin = QDoubleSpinBox()
        self.time_spin.setRange(0, 10000)
        self.time_spin.setSingleStep(1.0)
        self.time_spin.valueChanged.connect(self._on_time_spin_changed)
        time_nav_layout.addWidget(self.time_spin)

        plot_content_layout.addLayout(time_nav_layout)
        self.preview_stack.addWidget(self.plot_content)

        (
            self.empty_state,
            self.empty_state_title,
            self.empty_state_detail,
        ) = self._preview_state_widget(
            "No EEG data loaded",
            "Load EEG data to preview signals.",
        )
        self.preview_stack.addWidget(self.empty_state)
        (
            self.locked_state,
            self.locked_state_title,
            self.locked_state_detail,
        ) = self._preview_state_widget(
            "Preprocessing locked",
            (
                "The data has already been epoched. Preprocessing operations "
                "cannot be changed at this stage."
            ),
        )
        self.preview_stack.addWidget(self.locked_state)
        (
            self.unavailable_state,
            self.unavailable_state_title,
            self.unavailable_state_detail,
        ) = self._preview_state_widget(
            "Signal preview unavailable",
            PREVIEW_RENDER_FAILED_MESSAGE,
        )
        self.preview_stack.addWidget(self.unavailable_state)
        # Compatibility alias for older tests and callers.
        self.locked_status_label = self.locked_state_detail
        plot_layout.addWidget(self.preview_stack)
        self.plot_group.setLayout(plot_layout)

        layout.addWidget(self.plot_group)
        self._set_preview_interactive(
            False,
            state="empty",
        )

    @staticmethod
    def _preview_state_widget(
        title: str,
        detail: str,
    ) -> tuple[QWidget, QLabel, QLabel]:
        state = QWidget()
        state.setObjectName("PreprocessPreviewState")
        layout = QVBoxLayout(state)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        layout.addStretch()
        title_label = QLabel(title)
        title_label.setObjectName("PreprocessPreviewStateTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_label = QLabel(detail)
        detail_label.setObjectName("PreprocessPreviewStateDetail")
        detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(detail_label)
        layout.addStretch()
        state.setStyleSheet(
            f"""
            QWidget#PreprocessPreviewState {{
                background-color: {Theme.BACKGROUND_MID};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
            }}
            QLabel#PreprocessPreviewStateTitle {{
                background: transparent;
                border: none;
                color: {Theme.TEXT_PRIMARY};
                font-size: 15px;
                font-weight: 700;
            }}
            QLabel#PreprocessPreviewStateDetail {{
                background: transparent;
                border: none;
                color: {Theme.TEXT_SECONDARY};
                font-size: 12px;
            }}
            """
        )
        return state, title_label, detail_label

    def setup_timer(self):
        """Create a single-shot debounce timer for plot-parameter changes."""
        self.plot_timer = QTimer(self)
        self.plot_timer.setSingleShot(True)
        self.plot_timer.timeout.connect(self._emit_plot_update)

    def prepare_for_shutdown(self) -> None:
        """Stop deferred PyQtGraph work before Qt destroys native plot objects."""
        if self._native_plot_shutdown:
            return
        self._native_plot_shutdown = True
        self.plot_timer.stop()
        for proxy_name in ("proxy_time", "proxy_freq"):
            proxy = getattr(self, proxy_name, None)
            disconnect = getattr(proxy, "disconnect", None)
            if callable(disconnect):
                disconnect()
        for plot_name in ("plot_time", "plot_freq"):
            plot = getattr(self, plot_name, None)
            if plot is None:
                continue
            plot.setUpdatesEnabled(False)
            viewport = plot.viewport()
            if viewport is not None:
                viewport.setUpdatesEnabled(False)
            plot.close()

    def closeEvent(self, event) -> None:  # noqa: N802
        """Release deferred plot callbacks before the widget hierarchy closes."""
        self.prepare_for_shutdown()
        super().closeEvent(event)

    @pyqtSlot()
    def _emit_plot_update(self) -> None:
        """Forward the owned timer callback through the widget signal."""
        self.request_plot_update.emit()

    def _on_plot_param_changed(self):
        """Start the debounce timer when a plot parameter changes."""
        if self._native_plot_shutdown:
            return
        self.plot_timer.start(50)  # Debounce

    def _on_time_slider_changed(self, value):
        """Synchronize the spin box when the time slider moves.

        Args:
            value: New slider position (integer, 10x the time in seconds).

        """
        self.time_spin.blockSignals(True)
        self.time_spin.setValue(value / 10.0)
        self.time_spin.blockSignals(False)
        if self._native_plot_shutdown:
            return
        self.plot_timer.start(50)

    def _on_time_spin_changed(self, value):
        """Synchronize the slider when the time spin box changes.

        Args:
            value: New time value in seconds (float).

        """
        self.time_slider.blockSignals(True)
        self.time_slider.setValue(int(value * 10))
        self.time_slider.blockSignals(False)
        if self._native_plot_shutdown:
            return
        self.plot_timer.start(50)

    def _mouse_moved_time(self, evt):
        """Handle mouse movement over the time-domain plot.

        Args:
            evt: Mouse event tuple from ``pg.SignalProxy``.

        """
        self._update_crosshair(
            evt,
            self.plot_time,
            self.v_line_time,
            self.h_line_time,
            self.label_time,
        )

    def _mouse_moved_freq(self, evt):
        """Handle mouse movement over the frequency-domain plot.

        Args:
            evt: Mouse event tuple from ``pg.SignalProxy``.

        """
        self._update_crosshair(
            evt,
            self.plot_freq,
            self.v_line_freq,
            self.h_line_freq,
            self.label_freq,
        )

    def _update_crosshair(self, evt, plot, v_line, h_line, label):
        """Update crosshair lines and label for a given plot widget.

        Snaps the crosshair to the nearest point on the *Current* data
        curve when available.

        Args:
            evt: Mouse event tuple from ``pg.SignalProxy``.
            plot: The ``pg.PlotWidget`` to map coordinates in.
            v_line: Vertical ``pg.InfiniteLine`` crosshair.
            h_line: Horizontal ``pg.InfiniteLine`` crosshair.
            label: ``pg.TextItem`` displaying coordinate values.

        """
        pos = evt[0]
        if plot.sceneBoundingRect().contains(pos):
            mouse_point = plot.plotItem.vb.mapSceneToView(pos)
            x_mouse = mouse_point.x()

            # Find closest point on "Current" curve if available
            target_curve = None
            for item in plot.listDataItems():
                if item.name() == "Current":
                    target_curve = item
                    break

            snapped = False
            if target_curve:
                x_data = target_curve.xData
                y_data = target_curve.yData

                if x_data is not None and y_data is not None and len(x_data) > 0:
                    # Find closest index
                    # Note: x_data is typically sorted for time/freq plots
                    idx = np.searchsorted(x_data, x_mouse)

                    # Handle boundaries and check closest neighbor
                    if idx >= len(x_data):
                        idx = len(x_data) - 1
                    elif idx > 0 and abs(x_mouse - x_data[idx - 1]) < abs(
                        x_mouse - x_data[idx],
                    ):
                        idx = idx - 1

                    x_snap = x_data[idx]
                    y_snap = y_data[idx]

                    v_line.setPos(x_snap)
                    h_line.setPos(y_snap)
                    label.setText(f"X={x_snap:.3f}, Y={y_snap:.2f}")
                    label.setPos(x_snap, y_snap)
                    snapped = True

            if not snapped:
                # Fallback to mouse position if no data or curve not found
                v_line.setPos(x_mouse)
                h_line.setPos(mouse_point.y())
                label.setText(f"X={x_mouse:.2f}, Y={mouse_point.y():.2f}")
                label.setPos(x_mouse, mouse_point.y())

            v_line.show()
            h_line.show()
            label.show()
        else:
            v_line.hide()
            h_line.hide()
            label.hide()

    def reset_view(self):
        """Clear plots and replace the canvas with an intentional empty state."""
        self.plot_timer.stop()
        self.clear_plot_data()
        self.plot_time.setTitle("")
        self.plot_freq.setTitle("")
        self._set_preview_interactive(False, state="empty")

    def show_locked_message(self, message: str):
        """Display a locked state and remove misleading interaction affordances."""
        self.plot_timer.stop()
        self.clear_plot_data()
        self.plot_time.setTitle("")
        self.plot_freq.setTitle("")
        detail = str(message).strip()
        if not detail or detail.casefold() == "preprocessing locked":
            detail = (
                "The data has already been epoched. Preprocessing operations "
                "cannot be changed at this stage."
            )
        self.locked_state_detail.setText(detail)
        self._set_preview_interactive(False, state="locked")

    def show_unavailable_message(self, message: str) -> None:
        """Display an actionable preview failure without implying epoching."""
        self.plot_timer.stop()
        self.clear_plot_data()
        self.plot_time.setTitle("")
        self.plot_freq.setTitle("")
        detail = str(message).strip()
        self.unavailable_state_detail.setText(detail or PREVIEW_RENDER_FAILED_MESSAGE)
        self._set_preview_interactive(False, state="unavailable")

    def _on_channels_inserted(self, *_args) -> None:
        """Restore preview controls when a new raw dataset publishes channels."""
        if self.chan_combo.count() <= 0:
            return
        self.plot_time.setTitle("")
        self.plot_freq.setTitle("")
        self._set_preview_interactive(True, state="loaded")

    def _on_current_curve_data_changed(self, *_args) -> None:
        """Restore controls when a reset-to-raw path publishes signal data."""
        x_data = self.time_current_curve.xData
        if x_data is None or len(x_data) == 0:
            return
        self._set_preview_interactive(True, state="loaded")

    def _set_preview_interactive(
        self,
        enabled: bool,
        *,
        state: str,
    ) -> None:
        """Keep plot and navigation affordances aligned with preview availability."""
        controls = (
            self.plot_tabs,
            self.channel_label,
            self.chan_combo,
            self.yscale_label,
            self.yscale_spin,
            self.time_label,
            self.time_slider,
            self.time_spin,
        )
        for control in controls:
            control.setEnabled(enabled)
        target = {
            "loaded": self.plot_content,
            "empty": self.empty_state,
            "locked": self.locked_state,
            "unavailable": self.unavailable_state,
        }.get(state, self.empty_state)
        self.preview_stack.setCurrentWidget(target)
        self.locked_status_label.setVisible(state == "locked")

    def clear_plot_data(self):
        """Clear plotted data without deleting PyQtGraph graphics items."""
        for curve_name in (
            "time_original_curve",
            "time_current_curve",
            "freq_original_curve",
            "freq_current_curve",
        ):
            curve = getattr(self, curve_name, None)
            if curve is not None:
                curve.setData([], [])
        for item_name in (
            "v_line_time",
            "h_line_time",
            "label_time",
            "v_line_freq",
            "h_line_freq",
            "label_freq",
        ):
            item = getattr(self, item_name, None)
            if item is not None:
                item.hide()
        self.clear_time_event_markers()

    def clear_time_event_markers(self) -> None:
        """Hide reusable event markers without removing their Qt graphics items."""
        for marker in getattr(self, "time_event_markers", []):
            marker.hide()

    def show_time_event_markers(self, events: list[tuple[float, str]]) -> None:
        """Show visible EEG event markers using a bounded reusable item pool."""
        visible_events = events[: self.MAX_EVENT_MARKERS]
        self._ensure_time_event_marker_pool(len(visible_events))
        self.clear_time_event_markers()

        for marker, (onset, description) in zip(
            self.time_event_markers,
            visible_events,
            strict=False,
        ):
            marker.setPos(onset)
            label = getattr(marker, "label", None)
            if label is not None:
                label.setFormat(str(description))
            marker.show()

    def _ensure_time_event_marker_pool(self, count: int) -> None:
        while len(self.time_event_markers) < count:
            marker = pg.InfiniteLine(
                pos=0,
                angle=90,
                movable=False,
                pen=pg.mkPen(color=(Theme.ACCENT_SUCCESS + "80"), width=1),
                label="",
                labelOpts={
                    "position": 0.98,
                    "color": Theme.TEXT_PRIMARY,
                    "fill": (20, 20, 20, 200),
                    "anchor": (0, 0),
                },
            )
            marker.setZValue(500)
            marker.hide()
            self.plot_time.addItem(marker)
            self.time_event_markers.append(marker)
