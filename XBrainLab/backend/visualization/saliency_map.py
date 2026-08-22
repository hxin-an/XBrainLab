"""Channel-by-time saliency map visualiser."""

from typing import Any, cast

import numpy as np

from .base import Visualizer
from .saliency_semantics import (
    attribution_colormap,
    mean_saliency_over_trials,
    saliency_color_scale,
    style_attribution_colorbar,
)


class SaliencyMapViz(Visualizer):
    """Visualizer that generates a channel-by-time saliency heatmap.

    One subplot is created per class label.  Saliency values are averaged
    across trials and displayed as an image with channels on the y-axis and
    time on the x-axis.
    """

    def _get_plt(
        self,
        method,
        absolute: bool,
        *,
        selected_label_key: object | None = None,
        display_mode: str = "all",
    ) -> Any:
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
        display_by_label = []
        for label_key, label_name, raw_saliency in saliency_by_label:
            saliency = mean_saliency_over_trials(
                raw_saliency,
                absolute=absolute,
            )
            display_by_label.append((label_key, label_name, saliency))

        if display_mode not in {"all", "single"}:
            raise ValueError("display_mode must be 'all' or 'single'")
        plotted_by_label = display_by_label
        if display_mode == "single":
            plotted_by_label = [
                item for item in display_by_label if item[0] == selected_label_key
            ]
            if not plotted_by_label:
                raise ValueError("Selected saliency class is not available.")

        cmap, color_min, color_max = saliency_color_scale(
            method,
            [saliency for _label_key, _label_name, saliency in display_by_label],
            absolute=absolute,
            normalized=bool(getattr(self.epoch_data, "normalized", False)),
        )
        display_cmap = attribution_colormap(cmap)
        visible_label_number = len(plotted_by_label)
        if display_mode == "single":
            rows, cols = 1, 1
        else:
            cols = min(3, max(1, int(np.ceil(np.sqrt(visible_label_number)))))
            rows = int(np.ceil(visible_label_number / cols))
            cast(Any, fig)._xbrainlab_min_canvas_height = max(420, rows * 240)
        # Reserving this column prevents the colorbar from competing with the
        # final data axes when a compact desktop canvas is fitted later.
        grid = fig.add_gridspec(
            rows,
            cols + 1,
            width_ratios=[1.0] * cols + [0.075],
            wspace=0.38,
            hspace=0.45,
        )
        plot_axes = []
        image = None
        for plot_index, (label_key, label_name, saliency) in enumerate(
            plotted_by_label,
        ):
            ax = fig.add_subplot(grid[plot_index // cols, plot_index % cols])
            ax.set_gid(f"saliency-class:{label_key!r}")
            cast(Any, ax)._xbrainlab_class_key = label_key
            plot_axes.append(ax)

            image = ax.imshow(
                saliency,
                aspect="auto",
                cmap=display_cmap,
                vmin=color_min,
                vmax=color_max,
                interpolation="none",
            )

            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Channel")
            ch_names = self.epoch_data.get_channel_names()
            if display_mode == "single" and len(ch_names) > 12:
                tick_indices = np.unique(
                    np.linspace(0, len(ch_names) - 1, 12, dtype=int),
                )
            elif display_mode == "all" and len(ch_names) > 8:
                tick_indices = np.unique(
                    np.linspace(0, len(ch_names) - 1, 8, dtype=int),
                )
            else:
                tick_indices = np.arange(len(ch_names))
            ax.set_yticks(
                ticks=tick_indices,
                labels=[ch_names[index] for index in tick_indices],
                fontsize=6,
            )
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
            ax.set_title(str(label_name), fontsize=9 if display_mode == "all" else 11)
        if image is not None:
            colorbar_axis = fig.add_subplot(grid[:, -1])
            colorbar = fig.colorbar(
                image,
                cax=colorbar_axis,
                orientation="vertical",
            )
            style_attribution_colorbar(colorbar)
        fig.subplots_adjust(
            left=0.10,
            right=0.94,
            bottom=0.12,
            top=0.88,
        )
        return fig
