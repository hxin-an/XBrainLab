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
