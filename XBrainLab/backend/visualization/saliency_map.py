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
        duration = self.epoch_data.get_epoch_duration()
        rows = 1 if visible_label_number <= self.MIN_LABEL_NUMBER_FOR_MULTI_ROW else 2
        cols = int(np.ceil(visible_label_number / rows))
        for plot_index, (label_index, raw_saliency) in enumerate(saliency_by_label):
            plt.subplot(rows, cols, plot_index + 1)

            if absolute:
                saliency = np.abs(raw_saliency).mean(axis=0)
                cmap = "Reds"
            else:
                saliency = raw_saliency.mean(axis=0)
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
