"""Render detached Preprocess signal publications with PyQtGraph."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
from scipy.signal import welch

from XBrainLab.backend.application.preprocess_render import (
    PreprocessRenderPublication,
    PreprocessSignalState,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.panels.preprocess.preview_widget import (
    PREVIEW_RENDER_FAILED_MESSAGE,
)

if TYPE_CHECKING:
    from XBrainLab.ui.panels.preprocess.preview_widget import PreviewWidget


class PreprocessPlotter:
    """Draw immutable application publications without reading backend objects."""

    def __init__(self, widget: PreviewWidget) -> None:
        self.widget = widget
        self._plot_generation = 0
        self._is_plotting = False

    @staticmethod
    def _align_original_baseline_for_preview(
        original_microvolts: np.ndarray,
        current_microvolts: np.ndarray,
    ) -> np.ndarray:
        """Align the raw trace baseline for overlay without mutating signal data."""
        original_finite = original_microvolts[np.isfinite(original_microvolts)]
        current_finite = current_microvolts[np.isfinite(current_microvolts)]
        if original_finite.size == 0 or current_finite.size == 0:
            return original_microvolts
        return (
            original_microvolts
            - float(np.median(original_finite))
            + float(np.median(current_finite))
        )

    def _calc_psd_task(
        self,
        signal: np.ndarray,
        sampling_frequency: float,
        original_signal: np.ndarray | None = None,
        original_sampling_frequency: float | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray | None, np.ndarray | None]:
        """Calculate PSD for current and optional original signal windows."""
        frequencies, power = welch(
            signal,
            fs=sampling_frequency,
            nperseg=min(len(signal), 256 * 4),
        )
        original_frequencies: np.ndarray | None = None
        original_power: np.ndarray | None = None
        if original_signal is not None:
            original_frequencies, original_power = welch(
                original_signal,
                fs=(
                    original_sampling_frequency
                    if original_sampling_frequency is not None
                    else sampling_frequency
                ),
                nperseg=min(len(original_signal), 256 * 4),
            )
        return frequencies, power, original_frequencies, original_power

    def _frequency_tab_active(self) -> bool:
        tabs = getattr(self.widget, "plot_tabs", None)
        current_index = getattr(tabs, "currentIndex", None)
        if not callable(current_index):
            return False
        value = current_index()
        if not isinstance(value, (int, str)):
            return False
        return int(value) == 1

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
        publication: PreprocessRenderPublication | None,
    ) -> None:
        """Render one detached publication with a non-reentrant redraw guard."""
        if self._is_plotting:
            return
        self._is_plotting = True
        try:
            self._plot_sample_data_impl(publication)
        finally:
            self._is_plotting = False

    def _plot_sample_data_impl(
        self,
        publication: PreprocessRenderPublication | None,
    ) -> None:
        self._plot_generation += 1
        plot_generation = self._plot_generation
        self.widget.clear_plot_data()
        if publication is None:
            return
        data = publication.data
        if data.state is not PreprocessSignalState.RAW or data.current is None:
            return

        try:
            current = data.current
            original = data.original
            channel_name = data.selected_channel_name or "EEG"
            current_microvolts = current.values_volts * 1e6
            original_microvolts = (
                original.values_volts * 1e6 if original is not None else None
            )

            if original is not None and original_microvolts is not None:
                original_preview_microvolts = self._align_original_baseline_for_preview(
                    original_microvolts,
                    current_microvolts,
                )
                self.widget.time_original_curve.setData(
                    original.time_seconds,
                    original_preview_microvolts,
                )
            self.widget.time_current_curve.setData(
                current.time_seconds,
                current_microvolts,
            )
            self.widget.plot_time.setTitle(f"{channel_name} (Time)")
            plot_item: Any = self.widget.plot_time.getPlotItem()
            plot_item.setXRange(
                float(current.time_seconds[0]),
                float(current.time_seconds[-1]),
                padding=0,
            )

            y_scale = self.widget.yscale_spin.value()
            if y_scale > 0:
                self.widget.plot_time.setYRange(-y_scale, y_scale)
            else:
                self.widget.plot_time.enableAutoRange(axis="y")

            show_markers = getattr(self.widget, "show_time_event_markers", None)
            if callable(show_markers):
                show_markers(
                    [
                        (
                            event.onset_seconds,
                            event.label,
                            event.duration_seconds,
                        )
                        for event in data.events
                    ]
                )

            if self._frequency_tab_active():
                self.widget.plot_freq.setTitle("Calculating PSD...")
                result = self._calc_psd_task(
                    current_microvolts,
                    current.sampling_frequency,
                    original_microvolts,
                    (original.sampling_frequency if original is not None else None),
                )
                self._apply_psd_result(result, channel_name, plot_generation)
        except Exception as error:
            logger.error("Plotting failed: %s", error, exc_info=True)
            self._show_preview_unavailable(PREVIEW_RENDER_FAILED_MESSAGE)

    def _apply_psd_result(
        self,
        result: tuple[Any, Any, Any, Any],
        channel_name: str,
        plot_generation: int,
    ) -> None:
        """Apply PSD arrays to persistent PyQtGraph curves on the UI thread."""
        if plot_generation != self._plot_generation:
            return
        frequencies, power, original_frequencies, original_power = result
        if original_frequencies is not None and original_power is not None:
            self.widget.freq_original_curve.setData(
                original_frequencies,
                10 * np.log10(np.maximum(original_power, np.finfo(float).tiny)),
            )
        self.widget.freq_current_curve.setData(
            frequencies,
            10 * np.log10(np.maximum(power, np.finfo(float).tiny)),
        )
        self.widget.plot_freq.setTitle(f"{channel_name} (PSD)")
