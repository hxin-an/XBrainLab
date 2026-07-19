"""Channel-by-time saliency map visualiser."""

from typing import Any

import numpy as np

from .base import Visualizer
from .saliency_semantics import saliency_color_scale


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
        rows = 1 if visible_label_number <= self.MIN_LABEL_NUMBER_FOR_MULTI_ROW else 2
        cols = int(np.ceil(visible_label_number / rows))
        display_by_label = []
        for label_key, label_name, raw_saliency in saliency_by_label:
            if absolute:
                saliency = np.abs(raw_saliency).mean(axis=0)
            else:
                saliency = raw_saliency.mean(axis=0)
            display_by_label.append((label_key, label_name, saliency))

        cmap, color_min, color_max = saliency_color_scale(
            method,
            [saliency for _label_key, _label_name, saliency in display_by_label],
            absolute=absolute,
        )
        plot_axes = []
        image = None
        for plot_index, (_label_key, label_name, saliency) in enumerate(
            display_by_label,
        ):
            ax = fig.add_subplot(rows, cols, plot_index + 1)
            plot_axes.append(ax)

            image = ax.imshow(
                saliency,
                aspect="auto",
                cmap=cmap,
                vmin=color_min,
                vmax=color_max,
                interpolation="none",
            )

            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Channel")
            ch_names = self.epoch_data.get_channel_names()
            ax.set_yticks(ticks=range(len(ch_names)), labels=ch_names, fontsize=6)
            sample_count = int(saliency.shape[-1])
            sfreq = float(self.epoch_data.get_model_args()["sfreq"])
            if sfreq <= 0:
                raise ValueError(
                    "Sampling frequency must be positive for a saliency map."
                )
            epoch_start = float(getattr(self.epoch_data, "tmin", 0.0))
            epoch_end = epoch_start + (sample_count - 1) / sfreq
            tick_count = min(4, sample_count)
            ax.set_xticks(
                ticks=np.linspace(0, sample_count - 1, tick_count),
                labels=np.round(
                    np.linspace(epoch_start, epoch_end, tick_count),
                    2,
                ),
            )
            ax.tick_params(axis="x", labelsize=7)
            # The view already names the plot type. Repeating it on every
            # subplot makes class titles overlap in the desktop panel.
            ax.set_title(str(label_name))
        if image is not None:
            colorbar = fig.colorbar(
                image,
                ax=plot_axes,
                orientation="vertical",
                fraction=0.035,
                pad=0.04,
            )
            colorbar.ax.tick_params(labelsize=7, pad=1)
        fig.subplots_adjust(
            left=0.10,
            right=0.88,
            bottom=0.12,
            top=0.88,
            wspace=0.38,
            hspace=0.45,
        )
        return fig
