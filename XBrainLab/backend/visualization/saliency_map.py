"""Channel-by-time saliency map visualiser."""

from typing import Any

import numpy as np
from matplotlib import pyplot as plt

from .base import Visualizer


class SaliencyMapViz(Visualizer):
    """Visualizer that generates a channel-by-time saliency heatmap.

    One subplot is created per class label.  Saliency values are averaged
    across trials and displayed as an image with channels on the y-axis and
    time on the x-axis.
    """

    def _get_plt(self, method, absolute: bool) -> Any:
        """Render the saliency map figure.

        Args:
            method: Name of the saliency method (e.g. ``"Gradient"``).
            absolute: If ``True``, use absolute saliency values with a
                ``"Reds"`` colour map; otherwise use signed values with
                ``"coolwarm"``.

        Returns:
            matplotlib.figure.Figure: The rendered saliency map figure.

        """
        label_number = self.epoch_data.get_label_number()
        # row and col of subplot
        duration = self.epoch_data.get_epoch_duration()
        rows = 1 if label_number <= self.MIN_LABEL_NUMBER_FOR_MULTI_ROW else 2
        cols = int(np.ceil(label_number / rows))
        # draw
        for label_index in range(label_number):
            plt.subplot(rows, cols, label_index + 1)
            saliency = self.get_saliency(method, label_index)
            # no test data for this label
            if len(saliency) == 0:
                continue

            if absolute:
                saliency = np.abs(saliency).mean(axis=0)
                cmap = "Reds"
            else:
                saliency = saliency.mean(axis=0)
                cmap = "coolwarm"

            im = plt.imshow(
                saliency,
                aspect="auto",
                cmap=cmap,
                vmin=saliency.min(),
                vmax=saliency.max(),
                interpolation="none",
            )

            plt.xlabel("time")
            plt.ylabel("channel")
            ch_names = self.epoch_data.get_channel_names()
            plt.yticks(ticks=range(len(ch_names)), labels=ch_names, fontsize=6)
            plt.xticks(
                ticks=np.linspace(0, saliency.shape[-1], 5),
                labels=np.round(np.linspace(0, duration, 5), 2),
            )
            plt.colorbar(im, orientation="vertical")
            plt.title(f"Saliency Map of class {self.epoch_data.label_map[label_index]}")
        plt.tight_layout()
        return plt.gcf()
