"""Signal preview widget with time-domain and frequency-domain plots.

Uses PyQtGraph for high-performance interactive visualization with
crosshair cursors and debounced navigation controls.
"""

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSlider,
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

    def __init__(self, parent=None):
        """Initialize the preview widget.

        Args:
            parent: Optional parent widget.

        """
        super().__init__(parent)
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

        plot_layout.addWidget(self.plot_tabs)

        # 2. Controls (Channel, Y-Scale)
        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel("Channel:"))
        self.chan_combo = QComboBox()
        self.chan_combo.setMinimumWidth(100)
        self.chan_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.chan_combo.currentIndexChanged.connect(self._on_plot_param_changed)
        ctrl_layout.addWidget(self.chan_combo)

        ctrl_layout.addSpacing(20)
        ctrl_layout.addWidget(QLabel("Y-Scale (uV):"))
        self.yscale_spin = QDoubleSpinBox()
        self.yscale_spin.setRange(0, 5000)
        self.yscale_spin.setValue(0)  # 0 = Auto
        self.yscale_spin.setSpecialValueText("Auto")
        self.yscale_spin.setSingleStep(10)
        self.yscale_spin.valueChanged.connect(self._on_plot_param_changed)
        ctrl_layout.addWidget(self.yscale_spin)

        ctrl_layout.addStretch()
        plot_layout.addLayout(ctrl_layout)

        # 3. Time Navigation
        time_nav_layout = QHBoxLayout()
        time_nav_layout.addWidget(QLabel("Time / Epoch:"))

        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 100)
        self.time_slider.valueChanged.connect(self._on_time_slider_changed)
        time_nav_layout.addWidget(self.time_slider)

        self.time_spin = QDoubleSpinBox()
        self.time_spin.setRange(0, 10000)
        self.time_spin.setSingleStep(1.0)
        self.time_spin.valueChanged.connect(self._on_time_spin_changed)
        time_nav_layout.addWidget(self.time_spin)

        plot_layout.addLayout(time_nav_layout)
        self.plot_group.setLayout(plot_layout)

        layout.addWidget(self.plot_group)

    def setup_timer(self):
        """Create a single-shot debounce timer for plot-parameter changes."""
        self.plot_timer = QTimer()
        self.plot_timer.setSingleShot(True)
        self.plot_timer.timeout.connect(self.request_plot_update.emit)

    def _on_plot_param_changed(self):
        """Start the debounce timer when a plot parameter changes."""
        self.plot_timer.start(50)  # Debounce

    def _on_time_slider_changed(self, value):
        """Synchronize the spin box when the time slider moves.

        Args:
            value: New slider position (integer, 10x the time in seconds).

        """
        self.time_spin.blockSignals(True)
        self.time_spin.setValue(value / 10.0)
        self.time_spin.blockSignals(False)
        self.plot_timer.start(50)

    def _on_time_spin_changed(self, value):
        """Synchronize the slider when the time spin box changes.

        Args:
            value: New time value in seconds (float).

        """
        self.time_slider.blockSignals(True)
        self.time_slider.setValue(int(value * 10))
        self.time_slider.blockSignals(False)
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
        """Clear both plots and show a *No Data* title."""
        self.plot_time.clear()
        self.plot_freq.clear()
        self.plot_time.setTitle("No Data")
        self.plot_freq.setTitle("No Data")

    def show_locked_message(self, message: str):
        """Display a locked/status message on the plots."""
        self.plot_time.clear()
        self.plot_freq.clear()

        # Use simple titles for now as it's most robust
        self.plot_time.setTitle(message)
        self.plot_freq.setTitle(message)

        # Disable interaction cues if needed, or just clear content
        # Adding a centered text item would be nicer but requires ViewBox mapping
        # Title is sufficient for "Data is Epoched" status.
