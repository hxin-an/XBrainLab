import contextlib
from unittest.mock import MagicMock

from PyQt6.QtWidgets import QWidget

from XBrainLab.ui.dashboard_panel.preprocess import PreprocessPanel


def test_slider_debouncing(qtbot):
    """Test that slider changes are debounced."""
    # Mock parent and study
    mock_parent = MagicMock()
    # Mock parent and study
    mock_parent = QWidget()
    mock_parent.study = MagicMock()
    mock_ctrl = MagicMock()
    mock_ctrl.get_preprocessed_data_list.return_value = []
    mock_parent.study.get_controller.return_value = mock_ctrl

    panel = PreprocessPanel(mock_parent)
    qtbot.addWidget(panel)

    # Mock the plot method and reconnect signal
    panel.plot_sample_data = MagicMock()
    with contextlib.suppress(TypeError):
        panel.plot_timer.timeout.disconnect()
    panel.plot_timer.timeout.connect(panel.plot_sample_data)

    # Simulate rapid slider changes
    panel.on_time_slider_changed(10)
    panel.on_time_slider_changed(20)
    panel.on_time_slider_changed(30)

    # Verify plot NOT called immediately
    assert panel.plot_sample_data.call_count == 0

    # Wait for timer (50ms + buffer)
    qtbot.wait(100)

    # Verify plot called ONCE
    assert panel.plot_sample_data.call_count == 1


def test_spinbox_debouncing(qtbot):
    """Test that spinbox changes are debounced."""
    mock_parent = QWidget()
    mock_parent.study = MagicMock()
    mock_ctrl = MagicMock()
    mock_ctrl.get_preprocessed_data_list.return_value = []
    mock_parent.study.get_controller.return_value = mock_ctrl

    panel = PreprocessPanel(mock_parent)

    panel.plot_sample_data = MagicMock()
    with contextlib.suppress(TypeError):
        panel.plot_timer.timeout.disconnect()
    panel.plot_timer.timeout.connect(panel.plot_sample_data)

    panel.on_time_spin_changed(1.0)
    panel.on_time_spin_changed(2.0)

    assert panel.plot_sample_data.call_count == 0
    qtbot.wait(100)
    assert panel.plot_sample_data.call_count == 1
