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

    def _get_plt(self, method) -> Any:
        """Render the saliency spectrogram figure.

        Args:
            method: Name of the saliency method (e.g. ``"Gradient"``).

        Returns:
            matplotlib.figure.Figure: The rendered spectrogram figure.
        """
        sfreq = self.epoch_data.get_model_args()["sfreq"]
        label_number = self.epoch_data.get_label_number()
        # row and col of subplot
        rows = 1 if label_number <= self.MIN_LABEL_NUMBER_FOR_MULTI_ROW else 2
        cols = int(np.ceil(label_number / rows))
        # draw
        for label_index in range(label_number):
            plt.subplot(rows, cols, label_index + 1)
            saliency = self.get_saliency(method, label_index)
            # no test data for this label
            if len(saliency) == 0:
                continue

            freqs, timestamps, saliency = signal.stft(
                saliency,
                fs=sfreq,
                axis=-1,
                nperseg=int(sfreq),
                noverlap=int(sfreq) // 2,
            )
            # [:saliency.shape[0]//2,:]
            saliency = np.mean(np.mean(abs(saliency), axis=0), axis=0)
            cmap = "coolwarm"
            im = plt.imshow(
                saliency,
                interpolation="gaussian",
                aspect="auto",
                cmap=cmap,
                vmin=saliency.min(),
                vmax=saliency.max(),
            )
            tick_inteval = 0.5
            tick_label = np.round(np.arange(0, timestamps[-1], tick_inteval), 1)
            ticks = np.linspace(0, saliency.shape[1], len(tick_label))
            ticks = ticks - tick_inteval
            plt.xlabel("time")
            plt.ylabel("frequency")
            plt.xticks(
                ticks=ticks, labels=[str(label) for label in tick_label], fontsize=6
            )
            plt.yticks(ticks=freqs[np.where(freqs % 10 == 0)])

            plt.colorbar(im, orientation="vertical")
            plt.title(
                f"Saliency spectrogram of class "
                f"{self.epoch_data.label_map[label_index]}"
            )
        plt.tight_layout()
        return plt.gcf()
