"""Coverage tests for PreviewWidget - 65 uncovered lines."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QComboBox, QWidget


@pytest.fixture
def preview(qtbot):
    from XBrainLab.ui.panels.preprocess.preview_widget import PreviewWidget

    w = PreviewWidget()
    qtbot.addWidget(w)
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


class TestPreviewWidgetMethods:
    def test_reset_view(self, preview):
        preview.reset_view()

    def test_show_locked_message(self, preview):
        preview.show_locked_message("Data locked")

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
