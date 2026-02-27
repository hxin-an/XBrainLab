from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter import PreprocessPlotter


@pytest.fixture
def mock_widget():
    widget = MagicMock()

    # Mock PyQtGraph items
    widget.plot_time = MagicMock()
    widget.plot_freq = MagicMock()

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

    # Patch Worker to avoid actual threading
    with patch(
        "XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter.Worker"
    ) as MockWorker:
        plotter.plot_sample_data()

        # Check clears
        mock_widget.plot_time.clear.assert_called_once()
        mock_widget.plot_freq.clear.assert_called_once()

        # Check re-adding crosshairs
        mock_widget.plot_time.addItem.assert_called()

        # Check plot called
        assert mock_widget.plot_time.plot.call_count >= 1

        # Check title set
        mock_widget.plot_time.setTitle.assert_called_with("ch1 (Time)")


def test_plot_sample_data_async_psd(mock_widget, mock_controller):
    plotter = PreprocessPlotter(mock_widget, mock_controller)

    # Mock ThreadPool to run synchronous for test or just check start call
    plotter.threadpool = MagicMock()

    with patch(
        "XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter.Worker"
    ) as MockWorker:
        plotter.plot_sample_data()

        # Verify loading title
        mock_widget.plot_freq.setTitle.assert_called_with("Calculating PSD...")

        # Verify Worker created
        MockWorker.assert_called_once()

        # Verify ThreadPool started
        plotter.threadpool.start.assert_called_once()


def test_plot_no_data(mock_widget, mock_controller):
    mock_controller.has_data.return_value = False
    plotter = PreprocessPlotter(mock_widget, mock_controller)

    plotter.plot_sample_data()

    # Should clear but not plot
    mock_widget.plot_time.clear.assert_called_once()
    mock_widget.plot_time.plot.assert_not_called()


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

        with patch("XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter.pg"):
            plotter._plot_events(raw_obj, start_time=0.0, end_time=3.0)
            # Only one event should be plotted (onset=1.0 is in range)
            assert mock_widget.plot_time.addItem.call_count == 1

    def test_raw_no_annotations(self, mock_widget, mock_controller):
        plotter = PreprocessPlotter(mock_widget, mock_controller)
        raw_obj = MagicMock()
        raw_obj.is_raw.return_value = True
        mne = raw_obj.get_mne()
        mne.annotations = None

        plotter._plot_events(raw_obj, start_time=0.0, end_time=10.0)
        # No crash, no addItem called
        mock_widget.plot_time.addItem.assert_not_called()

    def test_epochs_no_events_plotted(self, mock_widget, mock_controller):
        plotter = PreprocessPlotter(mock_widget, mock_controller)
        epoch_obj = MagicMock()
        epoch_obj.is_raw.return_value = False

        plotter._plot_events(epoch_obj, start_time=0.0, end_time=10.0)
        mock_widget.plot_time.addItem.assert_not_called()


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
        plotter.plot_sample_data()
        mock_widget.plot_time.plot.assert_not_called()

    def test_empty_data_list(self, mock_widget, mock_controller):
        mock_controller.get_preprocessed_data_list.return_value = []
        plotter = PreprocessPlotter(mock_widget, mock_controller)
        plotter.plot_sample_data()
        mock_widget.plot_time.plot.assert_not_called()

    def test_negative_chan_idx(self, mock_widget, mock_controller):
        mock_widget.chan_combo.currentIndex.return_value = -1
        plotter = PreprocessPlotter(mock_widget, mock_controller)

        with patch("XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter.Worker"):
            plotter.plot_sample_data()
            # Should return early since chan_idx < 0
            mock_widget.plot_time.plot.assert_not_called()

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

        with (
            patch("XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter.Worker"),
            patch("XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter.pg"),
        ):
            plotter.plot_sample_data()
            mock_widget.plot_time.enableAutoRange.assert_called_once()

    def test_plot_exception(self, mock_widget, mock_controller):
        """Plotting exception is caught and reported."""
        raw_obj = mock_controller.get_preprocessed_data_list()[0]
        raw_obj.get_sfreq.side_effect = RuntimeError("broken")
        plotter = PreprocessPlotter(mock_widget, mock_controller)

        plotter.plot_sample_data()
        mock_widget.plot_time.setTitle.assert_called_with("Plot Error")
