"""Signal preview widget with time-domain and frequency-domain plots.

Uses PyQtGraph for high-performance interactive visualization with
crosshair cursors and debounced navigation controls.
"""

from typing import Any

import numpy as np
import pyqtgraph as pg
from PyQt6 import sip
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
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
        self._plot_items_attached = False
        self.init_ui()
        self._plot_items_attached = True
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
        self.plot_time.setLabel(
            "left",
            "Amplitude",
            units="uV",
            color=Theme.TEXT_MUTED,
        )
        self.plot_time.setLabel(
            "bottom",
            "Time",
            units="s",
            color=Theme.TEXT_MUTED,
        )
        self.plot_time.showGrid(x=True, y=True, alpha=0.3)
        self.plot_time.getAxis("left").setPen(Theme.BORDER)
        self.plot_time.getAxis("bottom").setPen(Theme.BORDER)
        self.plot_time.getAxis("left").setTextPen(Theme.TEXT_MUTED)
        self.plot_time.getAxis("bottom").setTextPen(Theme.TEXT_MUTED)
        # Disable properties menu and Mouse Interaction (Zoom/Pan)
        self.plot_time.setMenuEnabled(False)
        self.plot_time.setMouseEnabled(x=False, y=False)
        self.plot_time.getPlotItem().vb.setMouseEnabled(x=False, y=False)
        self.plot_time.getPlotItem().buttonsHidden = True
        self.plot_time.hideButtons()
        self.time_event_markers = []
        self.time_excluded_regions = []
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
        self.proxy_time = self._create_mouse_proxy(
            self.plot_time,
            self._mouse_moved_time,
        )

        time_layout.addWidget(self.plot_time)
        self.plot_tabs.addTab(self.tab_time, "Time Domain")

        # Tab 2: Frequency Domain (PSD)
        self.tab_freq = QWidget()
        freq_layout = QVBoxLayout(self.tab_freq)

        self.plot_freq = pg.PlotWidget()
        self.plot_freq.setLabel(
            "left",
            "Power",
            units="dB/Hz",
            color=Theme.TEXT_MUTED,
        )
        self.plot_freq.setLabel(
            "bottom",
            "Frequency",
            units="Hz",
            color=Theme.TEXT_MUTED,
        )
        self.plot_freq.showGrid(x=True, y=True, alpha=0.3)
        self.plot_freq.getAxis("left").setPen(Theme.BORDER)
        self.plot_freq.getAxis("bottom").setPen(Theme.BORDER)
        self.plot_freq.getAxis("left").setTextPen(Theme.TEXT_MUTED)
        self.plot_freq.getAxis("bottom").setTextPen(Theme.TEXT_MUTED)
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
        self.proxy_freq = self._create_mouse_proxy(
            self.plot_freq,
            self._mouse_moved_freq,
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

        self.signal_legend = QWidget()
        self.signal_legend.setObjectName("PreprocessSignalLegend")
        signal_legend_layout = QGridLayout(self.signal_legend)
        signal_legend_layout.setContentsMargins(0, 0, 0, 0)
        signal_legend_layout.setHorizontalSpacing(20)
        signal_legend_layout.setVerticalSpacing(4)

        self.loaded_signal_legend = QWidget(self.signal_legend)
        loaded_legend_layout = QHBoxLayout(self.loaded_signal_legend)
        loaded_legend_layout.setContentsMargins(0, 0, 0, 0)
        loaded_legend_layout.setSpacing(6)
        loaded_swatch = QFrame()
        loaded_swatch.setObjectName("PreprocessLoadedLegendSwatch")
        loaded_swatch.setFixedSize(18, 8)
        loaded_swatch.setStyleSheet(
            "background: transparent; border: none; "
            f"border-top: 1px dashed {Theme.CHART_ORIGINAL_DATA};"
        )
        self.loaded_signal_legend_text = QLabel("Loaded EEG")
        self.loaded_signal_legend_text.setObjectName("PreprocessLoadedLegendText")
        loaded_legend_layout.addWidget(loaded_swatch)
        loaded_legend_layout.addWidget(self.loaded_signal_legend_text)

        self.current_signal_legend = QWidget(self.signal_legend)
        current_legend_layout = QHBoxLayout(self.current_signal_legend)
        current_legend_layout.setContentsMargins(0, 0, 0, 0)
        current_legend_layout.setSpacing(6)
        current_swatch = QFrame()
        current_swatch.setObjectName("PreprocessCurrentLegendSwatch")
        current_swatch.setFixedSize(18, 8)
        current_swatch.setStyleSheet(
            "background: transparent; border: none; "
            f"border-top: 2px solid {Theme.CHART_PRIMARY};"
        )
        self.current_signal_legend_text = QLabel("Current preview")
        self.current_signal_legend_text.setObjectName("PreprocessCurrentLegendText")
        current_legend_layout.addWidget(current_swatch)
        current_legend_layout.addWidget(self.current_signal_legend_text)

        self.event_legend = QWidget(self.signal_legend)
        self.event_legend.setObjectName("PreprocessEventLegend")
        event_legend_layout = QHBoxLayout(self.event_legend)
        event_legend_layout.setContentsMargins(0, 0, 0, 0)
        event_legend_layout.setSpacing(6)
        event_swatch = QFrame()
        event_swatch.setObjectName("PreprocessEventLegendSwatch")
        event_swatch.setFixedSize(10, 10)
        event_swatch.setStyleSheet(
            f"background-color: {Theme.ACCENT_SUCCESS}; border: none;"
        )
        self.event_legend_text = QLabel()
        self.event_legend_text.setObjectName("PreprocessEventLegendText")
        event_legend_layout.addWidget(event_swatch)
        event_legend_layout.addWidget(self.event_legend_text)
        self.event_legend.hide()

        self.excluded_legend = QWidget(self.signal_legend)
        self.excluded_legend.setObjectName("PreprocessExcludedLegend")
        excluded_legend_layout = QHBoxLayout(self.excluded_legend)
        excluded_legend_layout.setContentsMargins(0, 0, 0, 0)
        excluded_legend_layout.setSpacing(6)
        excluded_swatch = QFrame()
        excluded_swatch.setObjectName("PreprocessExcludedLegendSwatch")
        excluded_swatch.setFixedSize(10, 10)
        excluded_swatch.setStyleSheet(
            f"background-color: {Theme.ACCENT_ERROR}; border: none;"
        )
        self.excluded_legend_text = QLabel()
        self.excluded_legend_text.setObjectName("PreprocessExcludedLegendText")
        excluded_legend_layout.addWidget(excluded_swatch)
        excluded_legend_layout.addWidget(self.excluded_legend_text)
        self.excluded_legend.hide()
        signal_legend_layout.addWidget(self.loaded_signal_legend, 0, 0)
        signal_legend_layout.addWidget(self.current_signal_legend, 0, 1)
        signal_legend_layout.addWidget(self.event_legend, 1, 0)
        signal_legend_layout.addWidget(self.excluded_legend, 1, 1)
        signal_legend_layout.setColumnStretch(2, 1)
        self.signal_legend.hide()
        plot_content_layout.addWidget(self.signal_legend)

        # 3. Time Navigation
        time_nav_layout = QHBoxLayout()
        self.time_label = QLabel("Time / EEG epoch:")
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
                "EEG epochs have already been created. Preprocessing operations "
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

    @staticmethod
    def _create_mouse_proxy(plot: pg.PlotWidget, slot) -> pg.SignalProxy:
        """Connect one rate-limited crosshair callback to a plot scene."""
        scene = plot.scene()
        mouse_moved = getattr(scene, "sigMouseMoved", None)
        if mouse_moved is None:
            raise RuntimeError("PyQtGraph plot scene does not expose mouse movement")
        return pg.SignalProxy(
            mouse_moved,
            rateLimit=60,
            slot=slot,
        )

    def prepare_for_shutdown(self) -> None:
        """Quiesce callbacks and detach items before native ViewBox destruction."""
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
        self._detach_owned_plot_items()

    def resume_after_cancelled_shutdown(self) -> None:
        """Restore plot callbacks when an application close is cancelled."""
        if not self._native_plot_shutdown or not self._attach_owned_plot_items():
            return
        self.proxy_time = self._create_mouse_proxy(
            self.plot_time,
            self._mouse_moved_time,
        )
        self.proxy_freq = self._create_mouse_proxy(
            self.plot_freq,
            self._mouse_moved_freq,
        )
        for plot in (self.plot_time, self.plot_freq):
            plot.setUpdatesEnabled(True)
            viewport = plot.viewport()
            if viewport is not None:
                viewport.setUpdatesEnabled(True)
            plot.update()
        self._native_plot_shutdown = False
        self.update()

    def closeEvent(self, event) -> None:  # noqa: N802
        """Release deferred plot callbacks before the widget hierarchy closes."""
        self.prepare_for_shutdown()
        super().closeEvent(event)

    def _owned_plot_item_bindings(
        self,
    ) -> tuple[tuple[pg.PlotWidget, tuple[tuple[Any, bool], ...]], ...]:
        """Return every graphics root owned by each plot and its bounds policy."""
        time_items: tuple[tuple[Any, bool], ...] = (
            (self.time_original_curve, False),
            (self.time_current_curve, False),
            (self.v_line_time, True),
            (self.h_line_time, True),
            (self.label_time, True),
            *((marker, False) for marker in self.time_event_markers),
            *((region, False) for region in self.time_excluded_regions),
        )
        frequency_items: tuple[tuple[Any, bool], ...] = (
            (self.freq_original_curve, False),
            (self.freq_current_curve, False),
            (self.v_line_freq, True),
            (self.h_line_freq, True),
            (self.label_freq, True),
        )
        return (
            (self.plot_time, time_items),
            (self.plot_freq, frequency_items),
        )

    @staticmethod
    def _forget_graphics_item_views(root: Any) -> None:
        """Clear cached ViewBox references for one detached graphics item tree."""
        pending = [root]
        while pending:
            item = pending.pop()
            if sip.isdeleted(item):
                continue
            pending.extend(item.childItems())
            forget_view_box = getattr(item, "forgetViewBox", None)
            if callable(forget_view_box):
                forget_view_box()
            forget_view_widget = getattr(item, "forgetViewWidget", None)
            if callable(forget_view_widget):
                forget_view_widget()

    def _detach_owned_plot_items(self) -> None:
        """Transfer graphics roots out of each live ViewBox exactly once."""
        if not self._plot_items_attached:
            return
        for plot, bindings in self._owned_plot_item_bindings():
            if sip.isdeleted(plot):
                continue
            plot_item = plot.getPlotItem()
            if plot_item is None or sip.isdeleted(plot_item):
                continue
            plot_scene = plot.scene()
            for item, _ignore_bounds in bindings:
                if sip.isdeleted(item):
                    continue
                if item.scene() is plot_scene:
                    plot.removeItem(item)
                self._forget_graphics_item_views(item)
        self._plot_items_attached = False

    def _attach_owned_plot_items(self) -> bool:
        """Restore detached graphics roots only while every native owner is live."""
        if self._plot_items_attached:
            return True
        bindings_by_plot = self._owned_plot_item_bindings()
        for plot, bindings in bindings_by_plot:
            if sip.isdeleted(plot):
                return False
            plot_item = plot.getPlotItem()
            if plot_item is None or sip.isdeleted(plot_item):
                return False
            plot_scene = plot.scene()
            for item, _ignore_bounds in bindings:
                if sip.isdeleted(item):
                    return False
                item_scene = item.scene()
                if item_scene is not None and item_scene is not plot_scene:
                    return False

        for plot, bindings in bindings_by_plot:
            for item, ignore_bounds in bindings:
                item_scene = item.scene()
                if item_scene is None:
                    plot.addItem(item, ignore_bounds)
        self._plot_items_attached = True
        return True

    @pyqtSlot()
    def _emit_plot_update(self) -> None:
        """Forward the owned timer callback through the widget signal."""
        if self._native_plot_shutdown:
            return
        self.request_plot_update.emit()

    def _on_plot_param_changed(self):
        """Start the debounce timer when a plot parameter changes."""
        self._refresh_event_legend_visibility()
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
                "EEG epochs have already been created. Preprocessing operations "
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
        self._preview_state = state
        self.signal_legend.setVisible(state == "loaded")
        self._refresh_event_legend_visibility()
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
        for region in getattr(self, "time_excluded_regions", []):
            region.hide()
        self.event_legend_text.clear()
        self.event_legend.setToolTip("")
        self.excluded_legend_text.clear()
        self.excluded_legend.setToolTip("")
        self.event_legend.hide()
        self.excluded_legend.hide()

    def show_time_event_markers(
        self,
        events: list[tuple[float, str] | tuple[float, str, float]],
    ) -> None:
        """Show visible EEG event markers using a bounded reusable item pool."""
        visible_events = [
            self._event_marker_parts(event)
            for event in events[: self.MAX_EVENT_MARKERS]
        ]
        self._ensure_time_event_marker_pool(len(visible_events))
        excluded_region_count = sum(
            1
            for _onset, description, duration in visible_events
            if self._is_excluded_annotation(description) and duration > 0
        )
        self._ensure_time_excluded_region_pool(excluded_region_count)
        self.clear_time_event_markers()

        next_region = 0
        for marker, (onset, description, duration) in zip(
            self.time_event_markers,
            visible_events,
            strict=False,
        ):
            excluded = self._is_excluded_annotation(description)
            marker.setPos(onset)
            marker.setPen(
                pg.mkPen(
                    color=(
                        Theme.ACCENT_ERROR
                        if excluded
                        else (Theme.ACCENT_SUCCESS + "80")
                    ),
                    width=1,
                    style=(Qt.PenStyle.DashLine if excluded else Qt.PenStyle.SolidLine),
                )
            )
            marker.setToolTip(self._event_tooltip(description, duration))
            marker.show()
            if excluded and duration > 0:
                region = self.time_excluded_regions[next_region]
                next_region += 1
                region.setRegion((onset, onset + duration))
                region.setToolTip(self._event_tooltip(description, duration))
                region.show()
        self._show_event_legend(visible_events)

    def _show_event_legend(
        self,
        events: list[tuple[float, str, float]],
    ) -> None:
        event_descriptions = list(
            dict.fromkeys(
                str(description).strip()
                for _onset, description, _duration in events
                if not self._is_excluded_annotation(description)
                if str(description).strip()
            )
        )
        if not event_descriptions:
            self.event_legend_text.clear()
            self.event_legend.setToolTip("")
            self.event_legend.hide()
        else:
            self.event_legend_text.setText(
                f"EEG events: {len(event_descriptions)} "
                f"{'type' if len(event_descriptions) == 1 else 'types'}"
            )
            self.event_legend.setToolTip(", ".join(event_descriptions))

        excluded_events = [
            (description, duration)
            for _onset, description, duration in events
            if self._is_excluded_annotation(description)
        ]
        if not excluded_events:
            self.excluded_legend_text.clear()
            self.excluded_legend.setToolTip("")
            self.excluded_legend.hide()
        else:
            count = len(excluded_events)
            self.excluded_legend_text.setText(
                f"Excluded: {count} {'segment' if count == 1 else 'segments'}"
            )
            self.excluded_legend.setToolTip(
                ", ".join(
                    self._event_tooltip(description, duration)
                    for description, duration in excluded_events
                )
            )
        self._refresh_event_legend_visibility()

    def _refresh_event_legend_visibility(self) -> None:
        """Show time-only legend details only in an active time-domain preview."""
        if not hasattr(self, "event_legend"):
            return
        time_preview_active = (
            getattr(self, "_preview_state", "empty") == "loaded"
            and self.plot_tabs.currentIndex() == 0
        )
        self.event_legend.setVisible(
            time_preview_active and bool(self.event_legend_text.text().strip())
        )
        self.excluded_legend.setVisible(
            time_preview_active and bool(self.excluded_legend_text.text().strip())
        )

    @staticmethod
    def _event_marker_parts(
        event: tuple[float, str] | tuple[float, str, float],
    ) -> tuple[float, str, float]:
        onset = float(event[0])
        description = str(event[1])
        duration = max(float(event[2]), 0.0) if len(event) > 2 else 0.0
        return onset, description, duration

    @staticmethod
    def _is_excluded_annotation(description: str) -> bool:
        """Follow MNE's explicit BAD-prefix exclusion convention."""
        return str(description).strip().casefold().startswith("bad")

    @staticmethod
    def _event_tooltip(description: str, duration: float) -> str:
        detail = str(description).strip()
        return f"{detail} ({duration:g} s)" if duration > 0 else detail

    def _ensure_time_event_marker_pool(self, count: int) -> None:
        while len(self.time_event_markers) < count:
            marker = pg.InfiniteLine(
                pos=0,
                angle=90,
                movable=False,
                pen=pg.mkPen(color=(Theme.ACCENT_SUCCESS + "80"), width=1),
            )
            marker.setZValue(500)
            marker.hide()
            self.plot_time.addItem(marker)
            self.time_event_markers.append(marker)

    def _ensure_time_excluded_region_pool(self, count: int) -> None:
        while len(self.time_excluded_regions) < count:
            region = pg.LinearRegionItem(
                values=(0.0, 0.0),
                movable=False,
                brush=pg.mkBrush(255, 85, 85, 36),
                pen=pg.mkPen(Theme.ACCENT_ERROR, width=1),
            )
            region.setZValue(400)
            region.hide()
            self.plot_time.addItem(region)
            self.time_excluded_regions.append(region)
