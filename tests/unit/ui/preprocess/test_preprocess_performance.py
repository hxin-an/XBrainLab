"""Real preview controls coalesce updates without replacing product signal wiring."""

import pytest
from PyQt6.QtTest import QSignalSpy

from XBrainLab.ui.panels.preprocess.preview_widget import PreviewWidget


@pytest.mark.parametrize("control_name", ["slider", "spin"])
def test_time_controls_debounce_real_plot_requests_and_stop_on_shutdown(
    qtbot, control_name
):
    preview = PreviewWidget()
    qtbot.addWidget(
        preview, before_close_func=lambda owned: owned.prepare_for_shutdown()
    )
    requests = QSignalSpy(preview.request_plot_update)
    control = preview.time_slider if control_name == "slider" else preview.time_spin
    scale = 10 if control_name == "slider" else 1

    for seconds in (1, 2, 3):
        control.setValue(seconds * scale)

    assert preview.time_slider.value() == 30
    assert preview.time_spin.value() == 3.0
    assert len(requests) == 0
    qtbot.waitUntil(lambda: len(requests) == 1, timeout=1_000)
    assert not preview.plot_timer.isActive()

    control.setValue(4 * scale)
    assert preview.plot_timer.isActive()
    preview.prepare_for_shutdown()
    assert not preview.plot_timer.isActive()
    control.setValue(5 * scale)
    assert not preview.plot_timer.isActive()
    assert len(requests) == 1
