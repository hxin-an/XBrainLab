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
from XBrainLab.ui.panels.preprocess.preview_widget import PREVIEW_RENDER_FAILED_MESSAGE


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


def test_time_domain_renders_detached_signal_and_events(mock_widget) -> None:
    current = _series(start=1.0)
    original = _series(sampling_frequency=50.0, start=1.0, samples=250)
    publication = _publication(
        current=current,
        original=original,
        events=(SignalEvent(1.5, "cue", 0.2),),
    )
    plotter = PreprocessPlotter(mock_widget)

    plotter.plot_sample_data(publication)

    mock_widget.clear_plot_data.assert_called_once()
    mock_widget.time_current_curve.setData.assert_called_once()
    current_x, current_y = mock_widget.time_current_curve.setData.call_args.args
    assert current_x is current.time_seconds
    assert current_y[[0, -1]].tolist() == pytest.approx([-1.0, 1.0])
    mock_widget.time_original_curve.setData.assert_called_once()
    mock_widget.plot_time.setTitle.assert_called_once_with("C3 (Time)")
    mock_widget.plot_time.getPlotItem.return_value.setXRange.assert_called_once_with(
        1.0,
        pytest.approx(5.99),
        padding=0,
    )
    mock_widget.show_time_event_markers.assert_called_once_with([(1.5, "cue", 0.2)])


def test_frequency_domain_uses_each_series_sampling_frequency(mock_widget) -> None:
    current = _series(sampling_frequency=100.0)
    original = _series(sampling_frequency=50.0, samples=250)
    publication = _publication(current=current, original=original)
    plotter = PreprocessPlotter(mock_widget)
    mock_widget.plot_tabs.currentIndex.return_value = 1

    with patch.object(
        plotter,
        "_calc_psd_task",
        wraps=plotter._calc_psd_task,
    ) as calculate:
        plotter.plot_sample_data(publication)

    args = calculate.call_args.args
    assert args[1] == 100.0
    assert args[3] == 50.0
    mock_widget.freq_current_curve.setData.assert_called_once()
    mock_widget.freq_original_curve.setData.assert_called_once()
    mock_widget.plot_freq.setTitle.assert_called_with("C3 (PSD)")


def test_time_tab_defers_psd_work(mock_widget) -> None:
    plotter = PreprocessPlotter(mock_widget)

    with patch.object(plotter, "_calc_psd_task") as calculate:
        plotter.plot_sample_data(_publication(current=_series()))

    calculate.assert_not_called()
    mock_widget.freq_current_curve.setData.assert_not_called()


def test_frequency_render_uses_scipy_without_worker_creation(mock_widget) -> None:
    plotter = PreprocessPlotter(mock_widget)
    mock_widget.plot_tabs.currentIndex.return_value = 1

    with patch(
        "XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter.welch",
        wraps=welch,
    ) as wrapped_welch:
        plotter.plot_sample_data(_publication(current=_series()))

    assert wrapped_welch.called


def test_stale_psd_result_does_not_update_latest_plot(mock_widget) -> None:
    plotter = PreprocessPlotter(mock_widget)
    result = (np.array([1.0]), np.array([1.0]), None, None)
    plotter._plot_generation = 2

    plotter._apply_psd_result(result, "C3", plot_generation=1)
    mock_widget.freq_current_curve.setData.assert_not_called()

    plotter._apply_psd_result(result, "C3", plot_generation=2)
    mock_widget.freq_current_curve.setData.assert_called_once()


def test_reentrant_refresh_is_ignored(mock_widget) -> None:
    plotter = PreprocessPlotter(mock_widget)
    publication = _publication(current=_series())

    mock_widget.clear_plot_data.side_effect = lambda: plotter.plot_sample_data(
        publication
    )
    plotter.plot_sample_data(publication)

    mock_widget.clear_plot_data.assert_called_once()
    mock_widget.time_current_curve.setData.assert_called_once()


def test_no_data_publication_only_clears_transient_curves(mock_widget) -> None:
    plotter = PreprocessPlotter(mock_widget)

    plotter.plot_sample_data(_publication(state=PreprocessSignalState.NO_DATA))

    mock_widget.clear_plot_data.assert_called_once()
    mock_widget.time_current_curve.setData.assert_not_called()
    mock_widget.freq_current_curve.setData.assert_not_called()


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
