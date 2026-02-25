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
