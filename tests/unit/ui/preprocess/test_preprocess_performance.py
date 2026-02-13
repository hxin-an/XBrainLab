import contextlib
from unittest.mock import MagicMock

from PyQt6.QtWidgets import QWidget

from XBrainLab.ui.panels.preprocess.panel import PreprocessPanel


def test_slider_debouncing(qtbot):
    """Test that slider changes are debounced via PreviewWidget."""
    mock_parent = QWidget()
    mock_parent.study = MagicMock()
    mock_ctrl = MagicMock()
    mock_ctrl.get_preprocessed_data_list.return_value = []
    mock_parent.study.get_controller.return_value = mock_ctrl

    panel = PreprocessPanel(parent=mock_parent)
    qtbot.addWidget(panel)

    # Access timer via preview_widget
    preview = panel.preview_widget

    # Mock the plotter method
    panel.plotter.plot_sample_data = MagicMock()

    # Disconnect and reconnect to mock
    with contextlib.suppress(TypeError):
        preview.plot_timer.timeout.disconnect()
    preview.plot_timer.timeout.connect(panel.plotter.plot_sample_data)

    # Simulate rapid slider changes via preview_widget
    preview._on_time_slider_changed(10)
    preview._on_time_slider_changed(20)
    preview._on_time_slider_changed(30)

    # Verify plot NOT called immediately
    assert panel.plotter.plot_sample_data.call_count == 0

    # Wait for timer (50ms + buffer)
    qtbot.wait(100)

    # Verify plot called ONCE (debounced)
    assert panel.plotter.plot_sample_data.call_count == 1


def test_spinbox_debouncing(qtbot):
    """Test that spinbox changes are debounced via PreviewWidget."""
    mock_parent = QWidget()
    mock_parent.study = MagicMock()
    mock_ctrl = MagicMock()
    mock_ctrl.get_preprocessed_data_list.return_value = []
    mock_parent.study.get_controller.return_value = mock_ctrl

    panel = PreprocessPanel(parent=mock_parent)
    qtbot.addWidget(panel)

    preview = panel.preview_widget

    panel.plotter.plot_sample_data = MagicMock()
    with contextlib.suppress(TypeError):
        preview.plot_timer.timeout.disconnect()
    preview.plot_timer.timeout.connect(panel.plotter.plot_sample_data)

    preview._on_time_spin_changed(1.0)
    preview._on_time_spin_changed(2.0)

    assert panel.plotter.plot_sample_data.call_count == 0
    qtbot.wait(100)
    assert panel.plotter.plot_sample_data.call_count == 1
