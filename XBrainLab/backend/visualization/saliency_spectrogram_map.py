"""Frequency-by-time saliency spectrogram visualiser."""

from typing import Any

import numpy as np
from matplotlib.ticker import FuncFormatter
from scipy import signal

from .base import Visualizer
from .saliency_semantics import shared_color_limits


def _compact_colorbar_tick(value: float, _position: int) -> str:
    """Return readable colorbar text for tiny saliency magnitudes."""
    abs_value = abs(value)
    if abs_value == 0:
        return "0"
    if 0.01 <= abs_value < 100:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{value:.1e}"


class SaliencySpectrogramMapViz(Visualizer):
    """Visualizer that generates a frequency-by-time saliency spectrogram.

    The saliency is transformed via STFT and averaged across trials and
    channels, producing one subplot per class label.
    """

    def _get_plt(self, method, absolute: bool = False) -> Any:
        """Render the saliency spectrogram figure.

        Args:
            method: Name of the saliency method (e.g. ``"Gradient"``).
            absolute: Accepted for interface consistency with sibling
                visualisers but currently unused by this implementation.

        Returns:
            matplotlib.figure.Figure: The rendered spectrogram figure.

        """
        del absolute  # STFT magnitude is non-negative by definition.
        sfreq = float(self.epoch_data.get_model_args()["sfreq"])
        if sfreq <= 0:
            raise ValueError("Sampling frequency must be positive for a spectrogram.")
        if self.fig is None:
            raise RuntimeError("Visualizer figure was not initialized")
        fig = self.fig
        saliency_by_label = self.iter_saliency_by_label(method)
        if not saliency_by_label:
            ax = fig.gca()
            ax.text(0.5, 0.5, "No saliency data for this run.", ha="center")
            ax.set_axis_off()
            return fig
        visible_label_number = len(saliency_by_label)
        rows = 1 if visible_label_number <= self.MIN_LABEL_NUMBER_FOR_MULTI_ROW else 2
        cols = int(np.ceil(visible_label_number / rows))
        spectrogram_by_label = []
        for label_key, label_name, raw_saliency in saliency_by_label:
            sample_count = int(raw_saliency.shape[-1])
            if sample_count < 2:
                raise ValueError(
                    "At least two epoch samples are required for a spectrogram.",
                )
            segment_samples = min(max(2, round(sfreq)), sample_count)
            overlap_samples = min(segment_samples // 2, segment_samples - 1)
            # SciPy accepts ``None`` to disable boundary extension, but its
            # current type stub only advertises string modes.
            boundary_mode: Any = None

            freqs, timestamps, stft_saliency = signal.stft(
                raw_saliency,
                fs=sfreq,
                axis=-1,
                nperseg=segment_samples,
                noverlap=overlap_samples,
                boundary=boundary_mode,
                padded=False,
            )
            saliency = np.mean(np.mean(abs(stft_saliency), axis=0), axis=0)
            epoch_start = float(getattr(self.epoch_data, "tmin", 0.0))
            time_centers = epoch_start + timestamps
            if time_centers.size == 1:
                half_bin_width = segment_samples / (2 * sfreq)
                time_min = float(time_centers[0] - half_bin_width)
                time_max = float(time_centers[0] + half_bin_width)
            else:
                time_min = float(
                    time_centers[0] - (time_centers[1] - time_centers[0]) / 2,
                )
                time_max = float(
                    time_centers[-1] + (time_centers[-1] - time_centers[-2]) / 2,
                )
            spectrogram_by_label.append(
                (
                    label_key,
                    label_name,
                    saliency,
                    freqs,
                    time_centers,
                    time_min,
                    time_max,
                ),
            )

        _, color_max = shared_color_limits(
            [
                saliency
                for (
                    _label_key,
                    _label_name,
                    saliency,
                    _freqs,
                    _time_centers,
                    _time_min,
                    _time_max,
                ) in spectrogram_by_label
            ],
            nonnegative=True,
            value_name="Spectrogram magnitude",
        )
        fig.subplots_adjust(
            left=0.10,
            right=0.86,
            bottom=0.12,
            top=0.84,
            wspace=0.38,
            hspace=0.55,
        )
        fig.suptitle(
            "Attribution magnitude spectrogram",
            color="#cccccc",
            fontsize=10,
        )
        plot_axes = []
        image = None
        for plot_index, (
            _label_key,
            label_name,
            saliency,
            freqs,
            time_centers,
            time_min,
            time_max,
        ) in enumerate(
            spectrogram_by_label,
        ):
            ax = fig.add_subplot(rows, cols, plot_index + 1)
            plot_axes.append(ax)

            cmap = "magma"
            image = ax.imshow(
                saliency,
                origin="lower",
                interpolation="nearest",
                aspect="auto",
                cmap=cmap,
                vmin=0.0,
                vmax=color_max,
                extent=(
                    time_min,
                    time_max,
                    float(freqs[0]),
                    float(freqs[-1]),
                ),
            )
            tick_count = min(5, time_centers.size)
            tick_label = np.round(
                np.linspace(time_centers[0], time_centers[-1], tick_count),
                2,
            )
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Frequency (Hz)")
            ax.set_xticks(tick_label)
            ax.tick_params(axis="x", labelsize=6)
            ax.set_yticks(freqs[np.where(np.isclose(freqs % 10, 0))])

            ax.set_title(str(label_name))
        if image is not None:
            colorbar = fig.colorbar(
                image,
                ax=plot_axes,
                orientation="vertical",
                fraction=0.035,
                pad=0.04,
                format=FuncFormatter(_compact_colorbar_tick),
            )
            colorbar.ax.tick_params(labelsize=7, pad=1)
        return fig
