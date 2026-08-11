"""Topographic saliency map visualiser using MNE topomap routines."""

from typing import Any

import mne
import numpy as np
from matplotlib.ticker import MaxNLocator, ScalarFormatter

from .base import Visualizer
from .saliency_semantics import mean_saliency_over_trials, saliency_color_scale

SPARSE_INTERPOLATION_CHANNEL_LIMIT = 8
TOPOGRAPHIC_COLORBAR_RECT = (0.87, 0.20, 0.018, 0.60)


class SaliencyTopoMapViz(Visualizer):
    """Visualizer that generates topographic saliency maps.

    Saliency values are averaged across trials and time, then displayed on
    a 2-D scalp topographic map using :func:`mne.viz.plot_topomap`.  One
    subplot is created per class label.
    """

    def _get_plt(self, method, absolute: bool) -> Any:
        """Render the topographic saliency map figure.

        Args:
            method: Name of the saliency method (e.g. ``"Gradient"``).
            absolute: If ``True``, use absolute saliency values with a
                ``"Reds"`` colour map; otherwise use signed values with
                ``"coolwarm"``.

        Returns:
            matplotlib.figure.Figure: The rendered topomap figure.

        Raises:
            ValueError: If no montage positions are available.

        """
        if self.fig is None:
            raise RuntimeError("Visualizer figure was not initialized")
        fig = self.fig
        positions = self.epoch_data.get_montage_position()

        if positions is None or len(positions) == 0:
            raise ValueError("No montage positions found. Please set a montage first.")

        # Ensure numpy array
        pos_array = np.array(positions)

        # Ensure 2D array
        if pos_array.ndim == 1 and pos_array.size > 0:
            # Assuming single channel case, though rare for Topomap
            pos_array = pos_array.reshape(1, -1)

        chs = self.epoch_data.get_channel_names()
        if pos_array.ndim != 2 or pos_array.shape[1] < 2:
            raise ValueError(
                "Montage positions must contain one 2-D or 3-D coordinate per channel.",
            )
        if len(chs) != len(pos_array):
            raise ValueError(
                "The number of channel names and montage positions must match "
                f"({len(chs)} names, {len(pos_array)} positions).",
            )
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
            saliency = mean_saliency_over_trials(
                raw_saliency,
                absolute=absolute,
            )

            # average over time
            data = saliency.mean(axis=1, dtype=np.float64)
            data_channel_count = int(data.shape[0]) if data.ndim >= 1 else 0
            if data.ndim != 1 or data_channel_count != len(chs):
                raise ValueError(
                    "Saliency channels must match the configured montage "
                    f"({data_channel_count} saliency channels, "
                    f"{len(chs)} montage channels).",
                )

            display_by_label.append((label_key, label_name, data))

        cmap, color_min, color_max = saliency_color_scale(
            method,
            [data for _label_key, _label_name, data in display_by_label],
            absolute=absolute,
            normalized=bool(getattr(self.epoch_data, "normalized", False)),
        )
        plot_axes = []
        image = None
        for plot_index, (_label_key, label_name, data) in enumerate(
            display_by_label,
        ):
            ax = fig.add_subplot(rows, cols, plot_index + 1)
            plot_axes.append(ax)
            kwargs = {
                "pos": pos_array[:, 0:2],
                "ch_type": "eeg",
                "sensors": True,
                "names": (
                    chs if len(chs) <= SPARSE_INTERPOLATION_CHANNEL_LIMIT else None
                ),
                "axes": ax,
                "show": False,
                "extrapolate": "local",
                "outlines": "head",
                "sphere": (0.0, -0.02, 0.0, 0.12),
            }
            kwargs["vlim"] = (color_min, color_max)
            if float(np.ptp(data)) <= 1e-12:
                kwargs["contours"] = 0

            image, _ = mne.viz.plot_topomap(data=data, cmap=cmap, **kwargs)
            ax.set_title(str(label_name), color="white")
        if len(chs) <= SPARSE_INTERPOLATION_CHANNEL_LIMIT:
            fig.text(
                0.5,
                0.02,
                f"Sparse {len(chs)}-channel interpolation · sensor locations shown",
                color="#cccccc",
                ha="center",
                fontsize=8,
            )
        fig.subplots_adjust(
            left=0.08,
            right=0.83,
            bottom=0.10,
            top=0.90,
            wspace=0.30,
            hspace=0.40,
        )
        if image is not None:
            colorbar_axis = fig.add_axes(TOPOGRAPHIC_COLORBAR_RECT)
            colorbar = fig.colorbar(
                image,
                cax=colorbar_axis,
                orientation="vertical",
            )
            formatter = ScalarFormatter(useMathText=True, useOffset=False)
            formatter.set_scientific(True)
            formatter.set_powerlimits((-2, 2))
            colorbar.formatter = formatter
            colorbar.locator = MaxNLocator(nbins=5)
            colorbar.update_ticks()
            colorbar.ax.tick_params(labelsize=7, pad=1)
            colorbar.ax.yaxis.get_offset_text().set_fontsize(7)
        return fig
