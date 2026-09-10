from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from scipy.signal import welch

from XBrainLab.backend.application.preprocess_render import (
    PreprocessRenderData,
    PreprocessRenderPublication,
    PreprocessRenderRequest,
    PreprocessSignalState,
    SignalEvent,
    SignalSeries,
)
from XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter import PreprocessPlotter
from XBrainLab.ui.panels.preprocess.preview_widget import (
    PREVIEW_RENDER_FAILED_MESSAGE,
    PreviewWidget,
)


@pytest.fixture
def mock_widget():
    widget = MagicMock()
    widget.plot_time = MagicMock()
    widget.plot_freq = MagicMock()
    widget.plot_tabs = MagicMock()
    widget.plot_tabs.currentIndex.return_value = 0
    widget.clear_plot_data = MagicMock()
    widget.show_time_event_markers = MagicMock()
    widget.show_unavailable_message = MagicMock()
    widget.time_original_curve = MagicMock()
    widget.time_current_curve = MagicMock()
    widget.freq_original_curve = MagicMock()
    widget.freq_current_curve = MagicMock()
    widget.yscale_spin = MagicMock()
    widget.yscale_spin.value.return_value = 0.0
    return widget


def _series(
    *,
    sampling_frequency: float = 100.0,
    start: float = 0.0,
    samples: int = 500,
    scale: float = 1.0,
) -> SignalSeries:
    times = start + np.arange(samples) / sampling_frequency
    values = np.linspace(-scale, scale, samples, dtype=np.float64) / 1e6
    return SignalSeries(
        time_seconds=times,
        values_volts=values,
        sampling_frequency=sampling_frequency,
    )


def _publication(
    *,
    current: SignalSeries | None = None,
    original: SignalSeries | None = None,
    events: tuple[SignalEvent, ...] = (),
    state: PreprocessSignalState = PreprocessSignalState.RAW,
) -> PreprocessRenderPublication:
    request = PreprocessRenderRequest(publication_generation=3)
    data = (
        PreprocessRenderData(state=state)
        if state is PreprocessSignalState.NO_DATA
        else PreprocessRenderData(
            state=state,
            channels=("C3",),
            sampling_frequency=100.0,
            cursor_max_seconds=5.0,
            selected_channel_index=0 if state is PreprocessSignalState.RAW else None,
            selected_channel_name="C3" if state is PreprocessSignalState.RAW else None,
            current=current if state is PreprocessSignalState.RAW else None,
            original=original if state is PreprocessSignalState.RAW else None,
            events=events if state is PreprocessSignalState.RAW else (),
        )
    )
    return PreprocessRenderPublication(
        request=request,
        generation=3,
        data=data,
    )


def test_plotter_init_has_no_backend_controller(mock_widget) -> None:
    plotter = PreprocessPlotter(mock_widget)

    assert plotter.widget is mock_widget
    assert not hasattr(plotter, "controller")


@pytest.mark.parametrize("frequency_tab", [False, True], ids=["time", "psd"])
@pytest.mark.parametrize("with_original", [False, True], ids=["current", "overlay"])
def test_native_curves_render_detached_signals_at_each_sampling_rate(
    qtbot, frequency_tab: bool, with_original: bool
) -> None:
    widget = PreviewWidget()
    qtbot.addWidget(
        widget, before_close_func=lambda owned: owned.prepare_for_shutdown()
    )
    widget.chan_combo.addItem("C3")
    widget.plot_tabs.setCurrentIndex(int(frequency_tab))
    current = _series(start=1.0)
    original = (
        _series(sampling_frequency=50.0, start=1.0, samples=250)
        if with_original
        else None
    )
    current_before = current.values_volts.copy()
    original_before = original.values_volts.copy() if original is not None else None

    plotter = PreprocessPlotter(widget)
    plotter.plot_sample_data(
        _publication(
            current=current,
            original=original,
            events=(SignalEvent(1.5, "cue", 0.2),),
        )
    )

    for series, curve in (
        (current, widget.time_current_curve),
        (original, widget.time_original_curve),
    ):
        x_values, y_values = curve.getData()
        if series is None:
            assert x_values is None or len(x_values) == 0
        else:
            np.testing.assert_array_equal(x_values, series.time_seconds)
            np.testing.assert_allclose(y_values, series.values_volts * 1e6, atol=1e-12)
    assert widget.time_event_markers[0].value() == 1.5
    assert widget.time_event_markers[0].toolTip() == "cue (0.2 s)"
    assert widget.plot_time.getPlotItem().titleLabel.text == "C3 (Time)"
    assert widget.plot_time.getPlotItem().viewRange()[0] == pytest.approx([1.0, 5.99])
    for series, curve in (
        (current, widget.freq_current_curve),
        (original, widget.freq_original_curve),
    ):
        frequencies, power = curve.getData()
        if not frequency_tab or series is None:
            assert frequencies is None or len(frequencies) == 0
        else:
            expected_frequencies, expected_power = welch(
                series.values_volts * 1e6,
                fs=series.sampling_frequency,
                nperseg=min(len(series.values_volts), 1024),
            )
            np.testing.assert_array_equal(frequencies, expected_frequencies)
            np.testing.assert_allclose(
                power,
                10 * np.log10(np.maximum(expected_power, np.finfo(float).tiny)),
            )
    if frequency_tab:
        assert widget.plot_freq.getPlotItem().titleLabel.text == "C3 (PSD)"
    np.testing.assert_array_equal(current.values_volts, current_before)
    if original is not None:
        np.testing.assert_array_equal(original.values_volts, original_before)

    plotter.plot_sample_data(_publication(state=PreprocessSignalState.NO_DATA))

    for curve in (
        widget.time_current_curve,
        widget.time_original_curve,
        widget.freq_current_curve,
        widget.freq_original_curve,
    ):
        x_values, _y_values = curve.getData()
        assert x_values is None or len(x_values) == 0
    assert not widget.time_event_markers[0].isVisible()


def test_time_domain_aligns_raw_baseline_without_changing_filtered_signal(
    mock_widget,
) -> None:
    """A large recording offset must not flatten the filtered preview."""
    current = _series(scale=20.0)
    raw_offset_microvolts = 250_000.0
    original = SignalSeries(
        time_seconds=current.time_seconds,
        values_volts=current.values_volts + raw_offset_microvolts / 1e6,
        sampling_frequency=current.sampling_frequency,
    )
    publication = _publication(current=current, original=original)
    plotter = PreprocessPlotter(mock_widget)

    plotter.plot_sample_data(publication)

    _, plotted_raw = mock_widget.time_original_curve.setData.call_args.args
    _, plotted_current = mock_widget.time_current_curve.setData.call_args.args
    assert np.median(plotted_raw) == pytest.approx(
        np.median(plotted_current),
        abs=1e-9,
    )
    assert np.ptp(plotted_raw) == pytest.approx(np.ptp(original.values_volts * 1e6))
    assert plotted_current == pytest.approx(current.values_volts * 1e6)
    assert np.median(original.values_volts * 1e6) == pytest.approx(
        raw_offset_microvolts
    )


def test_time_tab_defers_psd_work(mock_widget) -> None:
    plotter = PreprocessPlotter(mock_widget)

    with patch.object(plotter, "_calc_psd_task") as calculate:
        plotter.plot_sample_data(_publication(current=_series()))

    calculate.assert_not_called()
    mock_widget.freq_current_curve.setData.assert_not_called()


def test_reentrant_refresh_is_ignored(mock_widget) -> None:
    plotter = PreprocessPlotter(mock_widget)
    publication = _publication(current=_series())

    mock_widget.clear_plot_data.side_effect = lambda: plotter.plot_sample_data(
        publication
    )
    plotter.plot_sample_data(publication)

    mock_widget.clear_plot_data.assert_called_once()
    mock_widget.time_current_curve.setData.assert_called_once()


def test_render_failure_surfaces_product_message(mock_widget) -> None:
    plotter = PreprocessPlotter(mock_widget)
    mock_widget.time_current_curve.setData.side_effect = RuntimeError("native error")

    plotter.plot_sample_data(_publication(current=_series()))

    mock_widget.show_unavailable_message.assert_called_once_with(
        PREVIEW_RENDER_FAILED_MESSAGE
    )


def test_plotter_source_has_no_mutable_eeg_object_accessors() -> None:
    source = Path(
        "XBrainLab/ui/panels/preprocess/plotters/preprocess_plotter.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        ".get_mne(",
        ".get_sfreq(",
        ".is_raw(",
        "get_preprocessed_data_list",
        "query_preprocess_render_lists",
        "local_result_payload",
    ):
        assert forbidden not in source
