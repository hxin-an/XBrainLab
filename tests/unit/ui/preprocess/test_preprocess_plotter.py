import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from scipy.signal import welch

from XBrainLab.ui.panels.preprocess.data_query import (
    PreprocessRenderDataUnavailableError,
)
from XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter import PreprocessPlotter


def _plot_controller_data(plotter, controller) -> None:
    plotter.plot_sample_data(
        data_list=controller.get_preprocessed_data_list(),
        original_data_list=[],
    )


@pytest.fixture
def mock_widget():
    widget = MagicMock()

    # Mock PyQtGraph items
    widget.plot_time = MagicMock()
    widget.plot_freq = MagicMock()
    widget.plot_tabs = MagicMock()
    widget.plot_tabs.currentIndex.return_value = 0
    widget.clear_plot_data = MagicMock()
    widget.show_time_event_markers = MagicMock()
    widget.time_original_curve = MagicMock()
    widget.time_current_curve = MagicMock()
    widget.freq_original_curve = MagicMock()
    widget.freq_current_curve = MagicMock()

    # Mock Crosshair items
    widget.v_line_time = MagicMock()
    widget.h_line_time = MagicMock()
    widget.label_time = MagicMock()
    widget.v_line_freq = MagicMock()
    widget.h_line_freq = MagicMock()
    widget.label_freq = MagicMock()

    # Mock Controls
    widget.chan_combo = MagicMock()
    widget.chan_combo.currentIndex.return_value = 0
    widget.chan_combo.currentText.return_value = "ch1"

    widget.time_spin = MagicMock()
    widget.time_spin.value.return_value = 0.0

    widget.yscale_spin = MagicMock()
    widget.yscale_spin.value.return_value = 0.0

    return widget


@pytest.fixture
def mock_controller():
    ctrl = MagicMock()
    ctrl.has_data.return_value = True

    # Mock MNE Object
    raw = MagicMock()
    raw.is_raw.return_value = True
    raw.get_sfreq.return_value = 100.0

    # Create fake data (2 channels, 1000 samples)
    data = np.random.rand(2, 1000)
    raw.get_mne.return_value.get_data.return_value = data
    raw.get_mne.return_value.times = np.arange(1000) / 100.0

    ctrl.get_preprocessed_data_list.return_value = [raw]

    # Mock Study
    ctrl.study = MagicMock()
    ctrl.study.loaded_data_list = []

    return ctrl


def test_plotter_init(mock_widget, mock_controller):
    plotter = PreprocessPlotter(mock_widget, mock_controller)
    assert plotter.widget == mock_widget
    assert plotter.controller == mock_controller


def test_plot_sample_data_time_domain(mock_widget, mock_controller):
    plotter = PreprocessPlotter(mock_widget, mock_controller)

    _plot_controller_data(plotter, mock_controller)

    mock_widget.clear_plot_data.assert_called_once()

    mock_widget.time_current_curve.setData.assert_called_once()

    # Check title set
    mock_widget.plot_time.setTitle.assert_called_with("ch1 (Time)")


def test_plot_sample_data_calculates_psd_on_ui_thread(mock_widget, mock_controller):
    plotter = PreprocessPlotter(mock_widget, mock_controller)
    mock_widget.plot_tabs.currentIndex.return_value = 1

    with patch.object(plotter, "_calc_psd_task", wraps=plotter._calc_psd_task) as calc:
        _plot_controller_data(plotter, mock_controller)

    calc.assert_called_once()
    mock_widget.freq_current_curve.setData.assert_called_once()
    mock_widget.plot_freq.setTitle.assert_called_with("ch1 (PSD)")


def test_stale_psd_result_does_not_update_latest_plot(mock_widget, mock_controller):
    plotter = PreprocessPlotter(mock_widget, mock_controller)
    psd_result = (np.array([1.0]), np.array([1.0]), None, None)
    plotter._plot_generation = 2

    plotter._apply_psd_result(psd_result, "ch1", plot_generation=1)
    mock_widget.freq_current_curve.setData.assert_not_called()

    plotter._apply_psd_result(psd_result, "ch1", plot_generation=2)
    mock_widget.freq_current_curve.setData.assert_called_once()
    mock_widget.plot_freq.setTitle.assert_called_with("ch1 (PSD)")


def test_plot_sample_data_defers_psd_until_frequency_tab(mock_widget, mock_controller):
    plotter = PreprocessPlotter(mock_widget, mock_controller)
    mock_widget.plot_tabs.currentIndex.return_value = 0

    with patch.object(plotter, "_calc_psd_task") as calc:
        _plot_controller_data(plotter, mock_controller)

    mock_widget.time_current_curve.setData.assert_called_once()
    calc.assert_not_called()


def test_plot_sample_data_does_not_create_psd_workers(
    mock_widget,
    mock_controller,
):
    plotter = PreprocessPlotter(mock_widget, mock_controller)
    mock_widget.plot_tabs.currentIndex.return_value = 1

    with patch(
        "XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter.welch",
        wraps=welch,
    ) as wrapped_welch:
        _plot_controller_data(plotter, mock_controller)

    assert wrapped_welch.called


def test_plot_sample_data_ignores_reentrant_refresh(mock_widget, mock_controller):
    plotter = PreprocessPlotter(mock_widget, mock_controller)
    calls = 0

    def reenter_once():
        nonlocal calls
        calls += 1
        plotter.plot_sample_data()

    mock_widget.clear_plot_data.side_effect = reenter_once

    _plot_controller_data(plotter, mock_controller)

    assert calls == 1
    mock_widget.clear_plot_data.assert_called_once()
    mock_widget.time_current_curve.setData.assert_called_once()


def test_plot_no_data(mock_widget, mock_controller):
    mock_controller.has_data.side_effect = AssertionError("controller fallback used")
    mock_controller.get_preprocessed_data_list.side_effect = AssertionError(
        "controller fallback used"
    )
    plotter = PreprocessPlotter(mock_widget, mock_controller)

    with patch(
        "XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter.query_preprocess_render_lists",
        return_value=([], []),
    ) as query:
        plotter.plot_sample_data()

    # Should clear transient data but not plot
    query.assert_called_once_with(plotter, require_available=True)
    mock_widget.clear_plot_data.assert_called_once()
    mock_widget.show_locked_message.assert_not_called()
    mock_widget.time_current_curve.setData.assert_not_called()


def test_plot_sample_data_uses_service_query_before_controller(
    mock_widget,
    mock_controller,
):
    """Service-backed render data should win over potentially stale controller reads."""
    raw_obj = mock_controller.get_preprocessed_data_list()[0]
    mock_controller.has_data.side_effect = AssertionError("stale controller read")
    mock_controller.get_preprocessed_data_list.side_effect = AssertionError(
        "stale controller read"
    )
    plotter = PreprocessPlotter(mock_widget, mock_controller)

    with patch(
        "XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter.query_preprocess_render_lists",
        return_value=([raw_obj], []),
    ) as execute:
        plotter.plot_sample_data()

    execute.assert_called_once_with(plotter, require_available=True)
    mock_controller.has_data.assert_not_called()
    mock_widget.time_current_curve.setData.assert_called_once()


def test_plot_sample_data_refuses_real_study_query_none_controller_fallback(
    mock_widget,
    mock_controller,
):
    from XBrainLab.backend.study import Study

    mock_controller.study = Study()
    mock_controller.has_data.side_effect = AssertionError(
        "stale controller readiness should not be read",
    )
    mock_controller.get_preprocessed_data_list.side_effect = AssertionError(
        "stale controller list should not be read",
    )
    plotter = PreprocessPlotter(mock_widget, mock_controller)

    with patch(
        "XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter.query_preprocess_render_lists",
        return_value=None,
    ) as query:
        plotter.plot_sample_data()

    query.assert_called_once_with(plotter, require_available=True)
    mock_controller.has_data.assert_not_called()
    mock_controller.get_preprocessed_data_list.assert_not_called()
    mock_widget.time_current_curve.setData.assert_not_called()
    mock_widget.show_unavailable_message.assert_called_once_with(
        "Preprocess preview is unavailable because application state could not be read."
    )


def test_plot_sample_data_surfaces_application_query_failure(
    mock_widget,
    mock_controller,
):
    mock_controller.has_data.side_effect = AssertionError("controller fallback used")
    mock_controller.get_preprocessed_data_list.side_effect = AssertionError(
        "controller fallback used"
    )
    plotter = PreprocessPlotter(mock_widget, mock_controller)

    with patch(
        "XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter.query_preprocess_render_lists",
        side_effect=PreprocessRenderDataUnavailableError(
            "Published preprocess objects are stale."
        ),
    ) as query:
        plotter.plot_sample_data()

    query.assert_called_once_with(plotter, require_available=True)
    mock_controller.has_data.assert_not_called()
    mock_controller.get_preprocessed_data_list.assert_not_called()
    mock_widget.time_current_curve.setData.assert_not_called()
    mock_widget.show_unavailable_message.assert_called_once_with(
        "Published preprocess objects are stale."
    )


def test_plot_sample_data_with_supplied_data_uses_query_for_original_overlay(
    mock_widget,
    mock_controller,
):
    """Supplied current data should still get original overlay from query truth."""
    from XBrainLab.backend.study import Study

    current = mock_controller.get_preprocessed_data_list()[0]
    stale_original = MagicMock()
    stale_original.get_sfreq.side_effect = AssertionError(
        "stale Study loaded_data_list should not be read",
    )
    mock_controller.study = Study()
    mock_controller.study.loaded_data_list = [stale_original]
    plotter = PreprocessPlotter(mock_widget, mock_controller)

    with patch(
        "XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter.query_preprocess_render_lists",
        return_value=([current], [current]),
    ) as query:
        plotter.plot_sample_data(data_list=[current])

    query.assert_called_once_with(plotter, require_available=True)
    stale_original.get_sfreq.assert_not_called()
    mock_widget.time_current_curve.setData.assert_called_once()


class TestGetChanData:
    """Tests for _get_chan_data covering raw and epoch paths."""

    def test_raw_returns_data(self, mock_widget, mock_controller):
        plotter = PreprocessPlotter(mock_widget, mock_controller)
        raw_obj = mock_controller.get_preprocessed_data_list()[0]
        raw_obj.is_raw.return_value = True
        raw_obj.get_sfreq.return_value = 100.0

        mne = raw_obj.get_mne()
        data = np.random.rand(1, 500)
        mne.get_data.return_value = data
        mne.times = MagicMock(shape=(1000,))

        x, y = plotter._get_chan_data(raw_obj, ch_idx=0, start_time=0, duration=5)
        assert x is not None
        assert y is not None
        assert len(y) == 500

    def test_raw_start_beyond_data(self, mock_widget, mock_controller):
        plotter = PreprocessPlotter(mock_widget, mock_controller)
        raw_obj = mock_controller.get_preprocessed_data_list()[0]
        raw_obj.is_raw.return_value = True
        raw_obj.get_sfreq.return_value = 100.0

        mne = raw_obj.get_mne()
        mne.times = MagicMock(shape=(100,))  # Only 100 samples

        x, y = plotter._get_chan_data(
            raw_obj,
            ch_idx=0,
            start_time=999,
            duration=5,
        )
        assert x is None and y is None

    def test_raw_empty_data(self, mock_widget, mock_controller):
        plotter = PreprocessPlotter(mock_widget, mock_controller)
        raw_obj = mock_controller.get_preprocessed_data_list()[0]
        raw_obj.is_raw.return_value = True
        raw_obj.get_sfreq.return_value = 100.0

        mne = raw_obj.get_mne()
        mne.times = MagicMock(shape=(1000,))
        mne.get_data.return_value = np.array([])

        x, y = plotter._get_chan_data(raw_obj, ch_idx=0, start_time=0)
        assert x is None and y is None

    def test_epochs_returns_data(self, mock_widget, mock_controller):
        plotter = PreprocessPlotter(mock_widget, mock_controller)
        epoch_obj = MagicMock()
        epoch_obj.is_raw.return_value = False
        epoch_obj.get_sfreq.return_value = 100.0

        mne = epoch_obj.get_mne()
        # 3D data: (n_epochs, n_channels, n_times)
        data = np.random.rand(3, 2, 200)
        mne.get_data.return_value = data
        mne.times = np.arange(200) / 100.0

        x, y = plotter._get_chan_data(epoch_obj, ch_idx=0, start_time=1)
        assert x is not None
        assert y is not None
        assert len(y) == 200

    def test_epochs_bad_ndim(self, mock_widget, mock_controller):
        plotter = PreprocessPlotter(mock_widget, mock_controller)
        epoch_obj = MagicMock()
        epoch_obj.is_raw.return_value = False
        epoch_obj.get_sfreq.return_value = 100.0

        mne = epoch_obj.get_mne()
        mne.get_data.return_value = np.random.rand(10)  # 1D

        x, y = plotter._get_chan_data(epoch_obj, ch_idx=0, start_time=0)
        assert x is None and y is None

    def test_epochs_clamps_index(self, mock_widget, mock_controller):
        plotter = PreprocessPlotter(mock_widget, mock_controller)
        epoch_obj = MagicMock()
        epoch_obj.is_raw.return_value = False
        epoch_obj.get_sfreq.return_value = 100.0

        mne = epoch_obj.get_mne()
        data = np.random.rand(3, 2, 100)
        mne.get_data.return_value = data
        mne.times = np.arange(100) / 100.0

        # start_time=999 → clamped to last epoch
        _x, y = plotter._get_chan_data(epoch_obj, ch_idx=0, start_time=999)
        assert y is not None

        # start_time=-5 → clamped to 0
        _x, y = plotter._get_chan_data(epoch_obj, ch_idx=0, start_time=-5)
        assert y is not None


class TestPlotEvents:
    """Tests for _plot_events."""

    def test_raw_with_annotations(self, mock_widget, mock_controller):
        plotter = PreprocessPlotter(mock_widget, mock_controller)
        raw_obj = MagicMock()
        raw_obj.is_raw.return_value = True
        mne = raw_obj.get_mne()
        mne.annotations = [
            {"onset": 1.0, "description": "stim"},
            {"onset": 5.0, "description": "out_of_range"},
        ]

        events = plotter._plot_events(raw_obj, start_time=0.0, end_time=3.0)
        assert events == [(1.0, "stim")]
        mock_widget.plot_time.addItem.assert_not_called()
        mock_widget.show_time_event_markers.assert_called_once_with([(1.0, "stim")])

    def test_raw_no_annotations(self, mock_widget, mock_controller):
        plotter = PreprocessPlotter(mock_widget, mock_controller)
        raw_obj = MagicMock()
        raw_obj.is_raw.return_value = True
        mne = raw_obj.get_mne()
        mne.annotations = None

        events = plotter._plot_events(raw_obj, start_time=0.0, end_time=10.0)
        assert events == []
        mock_widget.plot_time.addItem.assert_not_called()
        mock_widget.show_time_event_markers.assert_called_once_with([])

    def test_epochs_no_events_plotted(self, mock_widget, mock_controller):
        plotter = PreprocessPlotter(mock_widget, mock_controller)
        epoch_obj = MagicMock()
        epoch_obj.is_raw.return_value = False

        events = plotter._plot_events(epoch_obj, start_time=0.0, end_time=10.0)
        assert events == []
        mock_widget.plot_time.addItem.assert_not_called()
        mock_widget.show_time_event_markers.assert_called_once_with([])


class TestCalcPsdTask:
    """Tests for _calc_psd_task."""

    def test_psd_without_original(self, mock_widget, mock_controller):
        plotter = PreprocessPlotter(mock_widget, mock_controller)
        sig = np.random.rand(500)

        f, pxx, f_orig, pxx_orig = plotter._calc_psd_task(sig, sfreq=100.0)
        assert len(f) > 0
        assert len(pxx) == len(f)
        assert f_orig is None
        assert pxx_orig is None

    def test_psd_with_original(self, mock_widget, mock_controller):
        plotter = PreprocessPlotter(mock_widget, mock_controller)
        sig = np.random.rand(500)
        sig_orig = np.random.rand(500)

        _f, _pxx, f_orig, pxx_orig = plotter._calc_psd_task(
            sig,
            sfreq=100.0,
            sig_orig=sig_orig,
        )
        assert f_orig is not None
        assert pxx_orig is not None
        assert len(f_orig) == len(pxx_orig)


class TestPlotSampleDataEdgeCases:
    """Edge cases in plot_sample_data."""

    def test_no_controller(self, mock_widget):
        plotter = PreprocessPlotter(mock_widget, None)
        with patch(
            "XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter.query_preprocess_render_lists",
            side_effect=PreprocessRenderDataUnavailableError(
                "Preprocess application state is unavailable."
            ),
        ):
            plotter.plot_sample_data()
        mock_widget.time_current_curve.setData.assert_not_called()
        mock_widget.show_unavailable_message.assert_called_once_with(
            "Preprocess application state is unavailable."
        )

    def test_empty_data_list(self, mock_widget, mock_controller):
        mock_controller.get_preprocessed_data_list.return_value = []
        plotter = PreprocessPlotter(mock_widget, mock_controller)
        plotter.plot_sample_data(data_list=[], original_data_list=[])
        mock_widget.time_current_curve.setData.assert_not_called()

    def test_negative_chan_idx(self, mock_widget, mock_controller):
        mock_widget.chan_combo.currentIndex.return_value = -1
        plotter = PreprocessPlotter(mock_widget, mock_controller)

        _plot_controller_data(plotter, mock_controller)
        # Should return early since chan_idx < 0
        mock_widget.time_current_curve.setData.assert_not_called()

    def test_yscale_auto(self, mock_widget, mock_controller):
        """yscale_spin == 0 triggers enableAutoRange."""
        mock_widget.yscale_spin.value.return_value = 0.0
        plotter = PreprocessPlotter(mock_widget, mock_controller)

        raw_obj = mock_controller.get_preprocessed_data_list()[0]
        raw_obj.is_raw.return_value = True
        raw_obj.get_sfreq.return_value = 100.0
        mne = raw_obj.get_mne()
        mne.times = MagicMock(shape=(1000,))
        data = np.random.rand(1, 500)
        mne.get_data.return_value = data

        _plot_controller_data(plotter, mock_controller)
        mock_widget.plot_time.enableAutoRange.assert_called_once()

    def test_plot_exception(self, mock_widget, mock_controller):
        """Plotting exceptions switch to the product unavailable state."""
        raw_obj = mock_controller.get_preprocessed_data_list()[0]
        raw_obj.get_sfreq.side_effect = RuntimeError("broken")
        plotter = PreprocessPlotter(mock_widget, mock_controller)

        _plot_controller_data(plotter, mock_controller)
        mock_widget.show_unavailable_message.assert_called_once_with(
            "The current signal could not be displayed. Try refreshing the panel."
        )
        assert ("Plot Error",) not in {
            call.args for call in mock_widget.plot_time.setTitle.call_args_list
        }


def test_preprocess_plotter_has_no_direct_study_or_controller_data_reads() -> None:
    source_path = (
        Path(__file__).parents[4]
        / "XBrainLab"
        / "ui"
        / "panels"
        / "preprocess"
        / "plotters"
        / "preprocess_plotter.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

    forbidden_attributes = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr
        in {
            "study",
            "loaded_data_list",
            "get_preprocessed_data_list",
            "has_data",
        }
    }

    assert forbidden_attributes == set()
