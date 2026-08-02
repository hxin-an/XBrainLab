"""Coverage tests for PreviewWidget - 65 uncovered lines."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QComboBox, QWidget


@pytest.fixture
def preview(qtbot):
    from XBrainLab.ui.panels.preprocess.preview_widget import PreviewWidget

    w = PreviewWidget()
    qtbot.addWidget(
        w,
        before_close_func=lambda owned: owned.prepare_for_shutdown(),
    )
    yield w


class TestPreviewWidgetInit:
    def test_creates_widget(self, preview):
        assert isinstance(preview, QWidget)

    def test_has_chan_combo(self, preview):
        assert isinstance(preview.chan_combo, QComboBox)

    def test_has_plot_time(self, preview):
        assert isinstance(preview.plot_time, QWidget)

    def test_has_plot_freq(self, preview):
        assert isinstance(preview.plot_freq, QWidget)

    def test_debounce_timer_is_owned_by_preview_widget(self, preview):
        assert preview.plot_timer.parent() is preview


class TestPreviewWidgetMethods:
    def test_reset_view(self, preview):
        preview.reset_view()

    def test_show_locked_message(self, preview):
        preview.show_locked_message("Data locked")

        assert preview.locked_status_label.text() == "Data locked"
        assert not preview.locked_status_label.isHidden()
        assert not preview.plot_tabs.isEnabled()
        assert not preview.chan_combo.isEnabled()
        assert not preview.yscale_spin.isEnabled()
        assert not preview.time_slider.isEnabled()
        assert not preview.time_spin.isEnabled()

    def test_new_channel_options_restore_preview_after_locked_state(
        self,
        preview,
        qtbot,
    ):
        preview.show()
        preview.show_locked_message("Data is Epoched - Preprocessing Locked")
        qtbot.wait(0)

        assert preview.locked_status_label.isVisibleTo(preview)
        assert not preview.chan_combo.isEnabled()

        preview.chan_combo.clear()
        preview.chan_combo.addItems(["C3", "C4"])
        qtbot.wait(0)

        assert preview.plot_tabs.isEnabled()
        assert preview.chan_combo.isEnabled()
        assert preview.yscale_spin.isEnabled()
        assert preview.time_slider.isEnabled()
        assert preview.time_spin.isEnabled()
        assert not preview.locked_status_label.isVisibleTo(preview)

    def test_new_curve_data_restores_preview_without_repopulating_channels(
        self,
        preview,
    ):
        preview.chan_combo.addItem("C3")
        preview.show_locked_message("Data is Epoched - Preprocessing Locked")

        preview.time_current_curve.setData([0.0, 0.1], [1.0, 2.0])

        assert preview.plot_tabs.isEnabled()
        assert preview.chan_combo.isEnabled()
        assert preview.time_slider.isEnabled()
        assert preview.locked_status_label.isHidden()

    def test_clear_plot_data_keeps_persistent_items(self, preview):
        preview.time_current_curve.setData([0, 1], [0, 1])
        preview.freq_current_curve.setData([0, 1], [0, 1])
        preview.show_time_event_markers([(0.5, "stim")])
        event_marker = preview.time_event_markers[0]

        preview.clear_plot_data()

        time_items = preview.plot_time.getPlotItem().items
        freq_items = preview.plot_freq.getPlotItem().items
        assert preview.time_current_curve in time_items
        assert preview.freq_current_curve in freq_items
        assert event_marker in time_items
        assert not event_marker.isVisible()
        assert preview.time_current_curve.xData is None or (
            len(preview.time_current_curve.xData) == 0
        )
        assert preview.freq_current_curve.xData is None or (
            len(preview.freq_current_curve.xData) == 0
        )
        assert preview.v_line_time in time_items
        assert preview.h_line_time in time_items
        assert preview.label_time in time_items

    def test_on_plot_param_changed(self, preview):
        preview._on_plot_param_changed()

    def test_on_time_slider_changed(self, preview):
        preview._on_time_slider_changed(50)

    def test_on_time_spin_changed(self, preview):
        preview._on_time_spin_changed(1.0)

    def test_mouse_moved_time_no_data(self, preview):
        """Exercise _mouse_moved_time fallback (no data curves)."""

        # Create a fake event at a point inside the plot
        pos = preview.plot_time.plotItem.vb.mapViewToScene(
            preview.plot_time.plotItem.vb.viewRect().center()
        )
        preview._mouse_moved_time((pos,))

    def test_mouse_moved_freq_no_data(self, preview):
        """Exercise _mouse_moved_freq fallback."""
        pos = preview.plot_freq.plotItem.vb.mapViewToScene(
            preview.plot_freq.plotItem.vb.viewRect().center()
        )
        preview._mouse_moved_freq((pos,))

    def test_mouse_moved_time_with_curve(self, preview):
        """Exercise crosshair snapping to a 'Current' data curve."""
        import numpy as np
        import pyqtgraph as pg

        x = np.linspace(0, 1, 100)
        y = np.sin(2 * np.pi * x)
        curve = pg.PlotDataItem(x, y, name="Current")
        preview.plot_time.addItem(curve)

        pos = preview.plot_time.plotItem.vb.mapViewToScene(
            preview.plot_time.plotItem.vb.viewRect().center()
        )
        preview._mouse_moved_time((pos,))

    def test_mouse_moved_outside_plot(self, preview):
        """Exercise crosshair hide when mouse is outside plot bounds."""
        from PyQt6.QtCore import QPointF

        far_away = QPointF(-9999, -9999)
        preview._mouse_moved_time((far_away,))

    def test_leave_event_hides_crosshairs(self, preview):
        """Exercise the monkey-patched leaveEvent."""
        from unittest.mock import MagicMock

        preview.v_line_time.show()
        preview.h_line_time.show()
        preview.label_time.show()
        # Use a mock event to avoid pyqtgraph GraphicsScene crash
        mock_event = MagicMock()
        preview.plot_time.leaveEvent(mock_event)
        assert not preview.v_line_time.isVisible()
        assert not preview.h_line_time.isVisible()

    def test_leave_event_freq_hides_crosshairs(self, preview):
        from unittest.mock import MagicMock

        preview.v_line_freq.show()
        preview.h_line_freq.show()
        preview.label_freq.show()
        mock_event = MagicMock()
        preview.plot_freq.leaveEvent(mock_event)
        assert not preview.v_line_freq.isVisible()
        assert not preview.h_line_freq.isVisible()
