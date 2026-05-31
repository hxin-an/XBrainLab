"""Topographic saliency map visualiser using MNE topomap routines."""

from typing import Any

import mne
import numpy as np

from .base import Visualizer


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
        saliency_by_label = self.iter_saliency_by_label(method)
        if not saliency_by_label:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "No saliency data for this run.", ha="center")
            ax.set_axis_off()
            return fig

        visible_label_number = len(saliency_by_label)
        rows = 1 if visible_label_number <= self.MIN_LABEL_NUMBER_FOR_MULTI_ROW else 2
        cols = int(np.ceil(visible_label_number / rows))

        for plot_index, (_label_key, label_name, raw_saliency) in enumerate(
            saliency_by_label,
        ):
            ax = fig.add_subplot(rows, cols, plot_index + 1)
            kwargs = {
                "pos": pos_array[:, 0:2],
                "ch_type": "eeg",
                "sensors": False,
                "names": chs,
                "axes": ax,
                "show": False,
                "extrapolate": "local",
                "outlines": "head",
                "sphere": (0.0, -0.02, 0.0, 0.12),
            }

            if absolute:
                saliency = np.abs(raw_saliency).mean(axis=0)
                cmap = "Reds"
            else:
                saliency = raw_saliency.mean(axis=0)
                cmap = "coolwarm"

            # average over time
            data = saliency.mean(axis=1)

            # Handle constant data to prevent RuntimeWarning in MNE
            if np.std(data) < 1e-10:
                data += np.random.normal(0, 1e-10, data.shape)

            im, _ = mne.viz.plot_topomap(data=data, cmap=cmap, **kwargs)
            cbar = fig.colorbar(im, ax=ax, orientation="vertical")
            cbar.ax.get_yaxis().set_ticks([])
            ax.set_title(f"Saliency Map of class {label_name}", color="white")
        fig.tight_layout()
        return fig
