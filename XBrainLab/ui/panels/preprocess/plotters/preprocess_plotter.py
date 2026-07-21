"""Plotting engine for the preprocessing panel.

Handles time-domain and frequency-domain (PSD) signal rendering
with support for original-vs-current overlays and event markers.
"""

from typing import TYPE_CHECKING, Any

import numpy as np
from scipy.signal import welch

from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.panels.preprocess.data_query import (
    PREPROCESS_RENDER_DATA_UNAVAILABLE_MESSAGE,
    PreprocessRenderDataUnavailableError,
    query_preprocess_render_lists,
)

if TYPE_CHECKING:
    from XBrainLab.ui.panels.preprocess.preview_widget import PreviewWidget

PLOT_RENDER_FAILED_MESSAGE = (
    "The current signal could not be displayed. Try refreshing the panel."
)


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
        self._plot_generation = 0
        self._is_plotting = False

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

        # The widget owns a reusable marker pool. Redraws update existing
        # PyQtGraph items instead of deleting and recreating native objects.
        show_markers = getattr(self.widget, "show_time_event_markers", None)
        if callable(show_markers):
            show_markers(events)
        return events

    def _calc_psd_task(self, sig, sfreq, sig_orig=None):
        """Calculate PSD for current and optional original signal."""
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

    def _frequency_tab_active(self) -> bool:
        tabs = getattr(self.widget, "plot_tabs", None)
        current_index = getattr(tabs, "currentIndex", None)
        if not callable(current_index):
            return False
        value = current_index()
        if not isinstance(value, (int, str)):
            return False
        return int(value) == 1

    def _query_data_lists_for_render(self) -> tuple[list[Any], list[Any]] | None:
        """Read one authoritative object publication or expose unavailability."""
        try:
            queried_lists = query_preprocess_render_lists(
                self,
                require_available=True,
            )
        except PreprocessRenderDataUnavailableError as error:
            self._show_preview_unavailable(str(error))
            return None
        if queried_lists is None:
            self._show_preview_unavailable(
                PREPROCESS_RENDER_DATA_UNAVAILABLE_MESSAGE,
            )
        return queried_lists

    def _show_preview_unavailable(self, message: str) -> None:
        logger.warning("Preprocess preview data unavailable: %s", message)
        show_unavailable_message = getattr(
            self.widget,
            "show_unavailable_message",
            None,
        )
        if callable(show_unavailable_message):
            show_unavailable_message(message)
            return
        self.widget.plot_time.setTitle("Preview unavailable")
        self.widget.plot_freq.setTitle("Preview unavailable")

    def plot_sample_data(
        self,
        *,
        data_list: list[Any] | None = None,
        original_data_list: list[Any] | None = None,
    ):
        """Main plotting routine with a non-reentrant redraw guard."""
        if self._is_plotting:
            return
        self._is_plotting = True
        try:
            self._plot_sample_data_impl(
                data_list=data_list,
                original_data_list=original_data_list,
            )
        finally:
            self._is_plotting = False

    def _plot_sample_data_impl(
        self,
        *,
        data_list: list[Any] | None = None,
        original_data_list: list[Any] | None = None,
    ):
        self._plot_generation += 1
        plot_generation = self._plot_generation

        # 1. Clear previous data without deleting persistent crosshair items.
        self.widget.clear_plot_data()

        orig_list = original_data_list or []
        if data_list is None or original_data_list is None:
            queried_lists = self._query_data_lists_for_render()
            if queried_lists is None:
                return
            data_list, orig_list = queried_lists

        if not data_list:
            return

        try:
            # Use first file
            raw_obj = data_list[0]
            orig_obj = orig_list[0] if orig_list else None
            if orig_obj is raw_obj:
                orig_obj = None

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
                    self.widget.time_original_curve.setData(x_orig, y_orig_uv)
                self.widget.time_current_curve.setData(x_curr, y_curr_uv)

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

                self._plot_events(raw_obj, x_curr[0], x_curr[-1])

            # --- Frequency Domain ---
            if y_curr is not None and self._frequency_tab_active():
                self.widget.plot_freq.setTitle("Calculating PSD...")
                result = self._calc_psd_task(y_curr_uv, sfreq, sig_orig=y_orig_uv)
                self._apply_psd_result(result, chan_name, plot_generation)

        except Exception as error:
            logger.error("Plotting failed: %s", error, exc_info=True)
            self._show_preview_unavailable(PLOT_RENDER_FAILED_MESSAGE)

    def _apply_psd_result(
        self,
        result: tuple[Any, Any, Any, Any],
        chan_name: str,
        plot_generation: int,
    ) -> None:
        """Apply PSD arrays to persistent PyQtGraph curves on the UI thread."""
        if plot_generation != self._plot_generation:
            return
        f_curr, p_curr, f_orig, p_orig = result
        if f_orig is not None and p_orig is not None:
            self.widget.freq_original_curve.setData(
                f_orig,
                10 * np.log10(np.maximum(p_orig, np.finfo(float).tiny)),
            )
        self.widget.freq_current_curve.setData(
            f_curr,
            10 * np.log10(np.maximum(p_curr, np.finfo(float).tiny)),
        )
        self.widget.plot_freq.setTitle(f"{chan_name} (PSD)")
