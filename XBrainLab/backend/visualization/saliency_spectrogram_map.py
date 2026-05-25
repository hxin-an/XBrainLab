"""Frequency-by-time saliency spectrogram visualiser."""

from typing import Any

import numpy as np
from matplotlib import pyplot as plt
from scipy import signal

from .base import Visualizer


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
        label_number = self.epoch_data.get_label_number()
        saliency_by_label = [
            (label_index, self.get_saliency(method, label_index))
            for label_index in range(label_number)
        ]
        saliency_by_label = [
            (label_index, saliency)
            for label_index, saliency in saliency_by_label
            if len(saliency) > 0
        ]
        if not saliency_by_label:
            ax = plt.gca()
            ax.text(0.5, 0.5, "No saliency data for selected labels.", ha="center")
            ax.set_axis_off()
            return plt.gcf()
        visible_label_number = len(saliency_by_label)
        rows = 1 if visible_label_number <= self.MIN_LABEL_NUMBER_FOR_MULTI_ROW else 2
        cols = int(np.ceil(visible_label_number / rows))
        for plot_index, (label_index, raw_saliency) in enumerate(saliency_by_label):
            plt.subplot(rows, cols, plot_index + 1)

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
            im = plt.imshow(
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
            plt.xlabel("time")
            plt.ylabel("frequency")
            plt.xticks(
                ticks=ticks,
                labels=[str(label) for label in tick_label],
                fontsize=6,
            )
            plt.yticks(ticks=freqs[np.where(freqs % 10 == 0)])

            plt.colorbar(im, orientation="vertical")
            plt.title(
                f"Saliency spectrogram of class "
                f"{self.epoch_data.label_map[label_index]}",
            )
        plt.tight_layout()
        return plt.gcf()
