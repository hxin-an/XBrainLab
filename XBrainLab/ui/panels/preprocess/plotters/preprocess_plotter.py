"""Plotting engine for the preprocessing panel.

Handles time-domain and frequency-domain (PSD) signal rendering
with support for original-vs-current overlays and event markers.
"""

from typing import TYPE_CHECKING

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QThreadPool
from scipy.signal import welch

from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.core.worker import Worker
from XBrainLab.ui.styles.theme import Theme

if TYPE_CHECKING:
    from XBrainLab.ui.panels.preprocess.preview_widget import PreviewWidget


class PreprocessPlotter:
    """Handles plotting logic for the PreprocessPanel using PyQtGraph.
    Now supports threading for heavy calculations (PSD).
    """

    def __init__(self, widget: "PreviewWidget", controller):
        """Initialize the plotter.

        Args:
            widget: The ``PreviewWidget`` containing the PyQtGraph plot
                widgets to draw into.
            controller: The ``PreprocessController`` providing data access.

        """
        self.widget = widget
        self.controller = controller
        self.threadpool = QThreadPool.globalInstance()

    def _get_chan_data(self, obj, ch_idx, start_time=0, duration=5):
        """Helper to retrieve channel data from a data object."""
        is_raw = obj.is_raw()
        obj_sfreq = obj.get_sfreq()
        mne_obj = obj.get_mne()

        if is_raw:
            start_sample = int(start_time * obj_sfreq)
            n_samples = int(duration * obj_sfreq)
            end_sample = start_sample + n_samples

            # Retrieve specific time segment using MNE's efficient slicing
            # This avoids loading the entire dataset into memory
            if start_sample >= mne_obj.times.shape[0]:
                return None, None

            # Efficiently load only the required segment
            data = mne_obj.get_data(start=start_sample, stop=end_sample, picks=[ch_idx])

            if data is None or data.size == 0:
                return None, None

            # With pick=[idx], get_data returns shape (1, n_times)
            y = data[0]
            # Generate time axis relative to the segment or absolute?
            # MNE get_data returns just values.
            # We usually plot absolute time.
            x = np.arange(start_sample, start_sample + len(y)) / obj_sfreq
            return x, y
        # For epochs, data is usually already loaded in memory
        # (unless on_demand? MNE Epochs default is preload=True usually)
        # But if it's large and not preloaded, get_data() full might still be slow.
        # Epochs.get_data() supports item slicing?
        # obj.get_mne() returns MNE Epochs object.
        # epoch_data = epochs[epoch_idx].get_data(picks=[ch_idx])

        # For Epochs, data is typically preloaded in memory.
        # However, we still use get_data() for consistency.
        data = mne_obj.get_data()
        if data.ndim != 3:
            return None, None

        # For epochs, start_time is the epoch index
        epoch_idx = int(start_time)
        epoch_idx = max(epoch_idx, 0)
        if epoch_idx >= data.shape[0]:
            epoch_idx = data.shape[0] - 1

        y = data[epoch_idx, ch_idx, :]
        x = mne_obj.times
        return x, y

    def _plot_events(self, obj, start_time, end_time):
        """Plot events or annotations on the time plot."""
        mne_obj = obj.get_mne()
        events = []

        # 1. Handle Raw Annotations
        if obj.is_raw():
            if mne_obj.annotations:
                for annot in mne_obj.annotations:
                    onset = annot["onset"]
                    desc = annot["description"]
                    # Filter visible
                    if start_time <= onset <= end_time:
                        events.append((onset, desc))

        # 2. Handle Epochs — events not plotted in epoch mode
        else:
            # For epochs, events are usually aligned to t=0.
            # Event markers are visualized primarily in Raw mode.
            pass

        # Draw Events
        for onset, desc in events:
            # Vertical Line
            # Use QColor with alpha for lower contrast
            # 50% Alpha (80 hex)
            pen = pg.mkPen(color=(Theme.ACCENT_SUCCESS + "80"), width=2)
            v_line = pg.InfiniteLine(
                pos=onset,
                angle=90,
                movable=False,
                pen=pen,
                label=str(desc),
                labelOpts={
                    "position": 0.98,
                    "color": Theme.TEXT_PRIMARY,
                    "fill": (20, 20, 20, 200),
                    "anchor": (0, 0),
                },
            )
            self.widget.plot_time.addItem(v_line)

    def _calc_psd_task(self, sig, sfreq, sig_orig=None):
        """Worker task to calculate PSD for current and optional original signal."""
        # Calc Current
        f, pxx = welch(sig, fs=sfreq, nperseg=min(len(sig), 256 * 4))

        # Calc Original (if exists)
        f_orig, pxx_orig = None, None
        if sig_orig is not None:
            f_orig, pxx_orig = welch(
                sig_orig,
                fs=sfreq,
                nperseg=min(len(sig_orig), 256 * 4),
            )

        return f, pxx, f_orig, pxx_orig

    def plot_sample_data(self):
        """Main plotting routine."""
        # 1. Clear previous plots
        self.widget.plot_time.clear()
        self.widget.plot_freq.clear()

        # Re-add crosshair items (clearing removes them)
        self.widget.plot_time.addItem(self.widget.v_line_time)
        self.widget.plot_time.addItem(self.widget.h_line_time)
        self.widget.plot_time.addItem(self.widget.label_time)

        self.widget.plot_freq.addItem(self.widget.v_line_freq)
        self.widget.plot_freq.addItem(self.widget.h_line_freq)
        self.widget.plot_freq.addItem(self.widget.label_freq)

        if not self.controller or not self.controller.has_data():
            return

        data_list = self.controller.get_preprocessed_data_list()
        orig_list = []
        if hasattr(self.controller, "study"):
            orig_list = self.controller.study.loaded_data_list

        if not data_list:
            return

        try:
            # Use first file
            raw_obj = data_list[0]
            orig_obj = orig_list[0] if orig_list else None

            chan_idx = self.widget.chan_combo.currentIndex()
            if chan_idx < 0:
                return  # No channel selected
            chan_name = self.widget.chan_combo.currentText()

            sfreq = raw_obj.get_sfreq()

            # Get Current Data
            start_t = self.widget.time_spin.value()
            x_curr, y_curr = self._get_chan_data(raw_obj, chan_idx, start_time=start_t)

            # Get Original Data (if available and compatible)
            x_orig, y_orig = None, None
            if orig_obj:
                x_orig, y_orig = self._get_chan_data(
                    orig_obj,
                    chan_idx,
                    start_time=start_t,
                )

            # --- Time Domain Plot (Immediate) ---
            if y_curr is not None:
                y_curr_uv = y_curr * 1e6
                y_orig_uv = y_orig * 1e6 if y_orig is not None else None

                if y_orig_uv is not None and x_orig is not None:
                    self.widget.plot_time.plot(
                        x_orig,
                        y_orig_uv,
                        pen=pg.mkPen(
                            Theme.CHART_ORIGINAL_DATA,
                            width=1,
                            style=pg.QtCore.Qt.PenStyle.DashLine,
                        ),
                        name="Original",
                    )

                self.widget.plot_time.plot(
                    x_curr,
                    y_curr_uv,
                    pen=pg.mkPen(Theme.CHART_PRIMARY, width=1.5),
                    name="Current",
                )

                if raw_obj.is_raw():
                    self.widget.plot_time.setTitle(f"{chan_name} (Time)")
                else:
                    self.widget.plot_time.setTitle(
                        f"{chan_name} (Epoch {int(start_t)})",
                    )

                # Ensure X-Axis follows the data (Link slider to view)
                if len(x_curr) > 0:
                    self.widget.plot_time.setXRange(x_curr[0], x_curr[-1], padding=0)

                # Apply Y-Scale
                y_scale = self.widget.yscale_spin.value()
                if y_scale > 0:
                    self.widget.plot_time.setYRange(-y_scale, y_scale)
                else:
                    self.widget.plot_time.enableAutoRange(axis="y")

                # Events / Annotations Visualization
                self._plot_events(raw_obj, x_curr[0], x_curr[-1])

            # --- Frequency Domain (Async) ---
            if y_curr is not None:
                # Show loading state
                self.widget.plot_freq.setTitle("Calculating PSD...")

                # Prepare args for worker
                worker = Worker(
                    self._calc_psd_task,
                    y_curr_uv,
                    sfreq,
                    sig_orig=y_orig_uv,
                )

                # Pass data needed for plotting via closure or args
                # We also need orig data if present

                def handle_psd_result(result):
                    f_curr, p_curr, f_orig, p_orig = result

                    # Plot Original (if available)
                    if f_orig is not None and p_orig is not None:
                        self.widget.plot_freq.plot(
                            f_orig,
                            10 * np.log10(p_orig),
                            pen=pg.mkPen(
                                Theme.CHART_ORIGINAL_DATA,
                                width=1,
                                style=pg.QtCore.Qt.PenStyle.DashLine,
                            ),
                            name="Original",
                        )

                    # Plot Current
                    self.widget.plot_freq.plot(
                        f_curr,
                        10 * np.log10(p_curr),
                        pen=pg.mkPen(Theme.CHART_PRIMARY, width=1.5),
                        name="Current",
                    )
                    self.widget.plot_freq.setTitle(f"{chan_name} (PSD)")

                worker.signals.result.connect(handle_psd_result)
                self.threadpool.start(worker)  # type: ignore[union-attr]

        except Exception as e:
            logger.error("Plotting failed: %s", e)
            self.widget.plot_time.setTitle("Plot Error")
