"""Frequency-by-time saliency spectrogram visualiser."""

from typing import Any

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.ticker import FuncFormatter
from scipy import signal

from .base import Visualizer


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
        sfreq = self.epoch_data.get_model_args()["sfreq"]
        fig = plt.gcf()
        saliency_by_label = self.iter_saliency_by_label(method)
        if not saliency_by_label:
            ax = fig.gca()
            ax.text(0.5, 0.5, "No saliency data for this run.", ha="center")
            ax.set_axis_off()
            return fig
        visible_label_number = len(saliency_by_label)
        rows = 1 if visible_label_number <= self.MIN_LABEL_NUMBER_FOR_MULTI_ROW else 2
        cols = int(np.ceil(visible_label_number / rows))
        fig.subplots_adjust(
            left=0.08,
            right=0.90,
            bottom=0.12,
            top=0.90,
            wspace=0.55,
            hspace=0.55,
        )
        for plot_index, (_label_key, label_name, raw_saliency) in enumerate(
            saliency_by_label,
        ):
            ax = fig.add_subplot(rows, cols, plot_index + 1)

            freqs, timestamps, stft_saliency = signal.stft(
                raw_saliency,
                fs=sfreq,
                axis=-1,
                nperseg=int(sfreq),
                noverlap=int(sfreq) // 2,
            )
            # [:saliency.shape[0]//2,:]
            saliency = np.mean(np.mean(abs(stft_saliency), axis=0), axis=0)
            cmap = "coolwarm"
            im = ax.imshow(
                saliency,
                interpolation="gaussian",
                aspect="auto",
                cmap=cmap,
                vmin=saliency.min(),
                vmax=saliency.max(),
            )
            tick_interval = 0.5
            tick_label = np.round(np.arange(0, timestamps[-1], tick_interval), 1)
            ticks = np.linspace(0, saliency.shape[1], len(tick_label))
            ticks = ticks - tick_interval
            ax.set_xlabel("time")
            ax.set_ylabel("frequency")
            ax.set_xticks(ticks=ticks, labels=[str(label) for label in tick_label])
            ax.tick_params(axis="x", labelsize=6)
            ax.set_yticks(freqs[np.where(freqs % 10 == 0)])

            colorbar = fig.colorbar(
                im,
                ax=ax,
                orientation="vertical",
                fraction=0.046,
                pad=0.04,
                format=FuncFormatter(_compact_colorbar_tick),
            )
            colorbar.ax.tick_params(labelsize=7, pad=1)
            ax.set_title(f"Saliency spectrogram of class {label_name}")
        return fig
