"""Topographic saliency map visualiser using MNE topomap routines."""

from typing import Any

import mne
import numpy as np
from matplotlib import pyplot as plt

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
        label_number = self.epoch_data.get_label_number()

        rows = 1 if label_number <= self.MIN_LABEL_NUMBER_FOR_MULTI_ROW else 2
        cols = int(np.ceil(label_number / rows))

        for label_index in range(label_number):
            ax = plt.subplot(rows, cols, label_index + 1)

            saliency = self.get_saliency(method, label_index)
            # no test data for this label
            if len(saliency) == 0:
                continue
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
                saliency = np.abs(saliency).mean(axis=0)
                cmap = "Reds"
            else:
                saliency = saliency.mean(axis=0)
                cmap = "coolwarm"

            # average over time
            data = saliency.mean(axis=1)

            # Handle constant data to prevent RuntimeWarning in MNE
            if np.std(data) < 1e-10:
                data += np.random.normal(0, 1e-10, data.shape)

            im, _ = mne.viz.plot_topomap(data=data, cmap=cmap, **kwargs)
            cbar = plt.colorbar(im, orientation="vertical")
            cbar.ax.get_yaxis().set_ticks([])
            plt.title(
                f"Saliency Map of class {self.epoch_data.label_map[label_index]}",
                color="white",
            )
        plt.tight_layout()
        return plt.gcf()
