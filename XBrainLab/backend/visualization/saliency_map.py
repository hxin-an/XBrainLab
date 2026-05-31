"""Channel-by-time saliency map visualiser."""

from typing import Any

import numpy as np

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
        if self.fig is None:
            raise RuntimeError("Visualizer figure was not initialized")
        fig = self.fig
        saliency_by_label = self.iter_saliency_by_label(method)
        if not saliency_by_label:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "No saliency data for this run.", ha="center")
            ax.set_axis_off()
            return fig
        visible_label_number = len(saliency_by_label)
        duration = self.epoch_data.get_epoch_duration()
        rows = 1 if visible_label_number <= self.MIN_LABEL_NUMBER_FOR_MULTI_ROW else 2
        cols = int(np.ceil(visible_label_number / rows))
        for plot_index, (_label_key, label_name, raw_saliency) in enumerate(
            saliency_by_label,
        ):
            ax = fig.add_subplot(rows, cols, plot_index + 1)

            if absolute:
                saliency = np.abs(raw_saliency).mean(axis=0)
                cmap = "Reds"
            else:
                saliency = raw_saliency.mean(axis=0)
                cmap = "coolwarm"

            im = ax.imshow(
                saliency,
                aspect="auto",
                cmap=cmap,
                vmin=saliency.min(),
                vmax=saliency.max(),
                interpolation="none",
            )

            ax.set_xlabel("time")
            ax.set_ylabel("channel")
            ch_names = self.epoch_data.get_channel_names()
            ax.set_yticks(ticks=range(len(ch_names)), labels=ch_names, fontsize=6)
            ax.set_xticks(
                ticks=np.linspace(0, saliency.shape[-1], 5),
                labels=np.round(np.linspace(0, duration, 5), 2),
            )
            fig.colorbar(im, ax=ax, orientation="vertical")
            ax.set_title(f"Saliency Map of class {label_name}")
        fig.tight_layout()
        return fig
