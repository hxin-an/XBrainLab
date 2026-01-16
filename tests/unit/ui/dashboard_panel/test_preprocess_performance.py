
from unittest.mock import MagicMock

from XBrainLab.ui.dashboard_panel.preprocess import PreprocessPanel


def test_slider_debouncing(qtbot):
    """Test that slider changes are debounced."""
    # Mock parent and study
    mock_parent = MagicMock()
    mock_parent.study = MagicMock()

    panel = PreprocessPanel(None)
    panel.main_window = mock_parent
    qtbot.addWidget(panel)

    # Mock the plot method and reconnect signal
    panel.plot_sample_data = MagicMock()
    try:
        panel.plot_timer.timeout.disconnect()
    except TypeError:
        pass # Signal might not be connected if init failed (unlikely here)
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
    mock_parent = MagicMock()
    mock_parent.study = MagicMock()

    panel = PreprocessPanel(None)
    panel.main_window = mock_parent
    qtbot.addWidget(panel)

    panel.plot_sample_data = MagicMock()
    try:
        panel.plot_timer.timeout.disconnect()
    except TypeError:
        pass
    panel.plot_timer.timeout.connect(panel.plot_sample_data)

    panel.on_time_spin_changed(1.0)
    panel.on_time_spin_changed(2.0)

    assert panel.plot_sample_data.call_count == 0
    qtbot.wait(100)
    assert panel.plot_sample_data.call_count == 1
