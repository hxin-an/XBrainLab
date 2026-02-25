"""Base visualizer module for generating matplotlib figures from evaluation records."""

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.figure import Figure

from ..dataset import Epochs
from ..training.record import EvalRecord


class Visualizer:
    """Base class for visualizer that generate figures from evaluation record

    Attributes:
        eval_record: evaluation record
        epoch_data: original epoch data for providing dataset information
        figsize: figure size
        dpi: figure dpi
        fig: figure to plot on. If None, a new figure will be created

    """

    MIN_LABEL_NUMBER_FOR_MULTI_ROW = 2

    def __init__(
        self,
        eval_record: EvalRecord,
        epoch_data: Epochs,
        figsize: tuple = (6.4, 4.8),
        dpi: int = 100,
        fig: Figure | None = None,
    ):
        """Initialise the visualizer.

        Args:
            eval_record: Evaluation record containing model outputs and gradients.
            epoch_data: Original epoch data providing dataset information.
            figsize: Width and height of the figure in inches.
            dpi: Dots per inch for the figure.
            fig: Existing matplotlib ``Figure`` to draw on.  If ``None``, a new
                figure is created on each call to :meth:`get_plt`.

        """
        self.eval_record = eval_record
        self.epoch_data = epoch_data
        self.figsize = figsize
        self.dpi = dpi
        self.fig = fig

    def _get_plt(self, *args, **kwargs):
        """Subclass hook that performs the actual plotting.

        Raises:
            NotImplementedError: Always; subclasses must override this method.

        """
        raise NotImplementedError

    def get_plt(self, *args, **kwargs):
        """Create (or clear) the figure and delegate to :meth:`_get_plt`.

        Args:
            *args: Positional arguments forwarded to :meth:`_get_plt`.
            **kwargs: Keyword arguments forwarded to :meth:`_get_plt`.

        Returns:
            matplotlib.figure.Figure: The rendered figure.

        """
        if self.fig is None:
            self.fig = plt.figure(figsize=self.figsize, dpi=self.dpi)
        plt.clf()
        return self._get_plt(*args, **kwargs)

    def get_saliency(self, saliency_name: str, label_index: int) -> np.ndarray:
        """Return the saliency (gradient-based) array for a given class.

        Args:
            saliency_name: Name of the saliency method.  Supported values are
                ``"Gradient"``, ``"Gradient * Input"``, ``"SmoothGrad"``,
                ``"SmoothGrad_Squared"``, and ``"VarGrad"``.
            label_index: Index of the target class label.

        Returns:
            np.ndarray: Saliency array computed by the requested method.

        Raises:
            NotImplementedError: If *saliency_name* is not a recognised method.
            ValueError: If *saliency_name* is ``None``.

        """
        if saliency_name is not None:
            if saliency_name == "Gradient":
                return self.eval_record.get_gradient(label_index)
            if saliency_name == "Gradient * Input":
                return self.eval_record.get_gradient_input(label_index)
            if saliency_name == "SmoothGrad":
                return self.eval_record.get_smoothgrad(label_index)
            if saliency_name == "SmoothGrad_Squared":
                return self.eval_record.get_smoothgrad_sq(label_index)
            if saliency_name == "VarGrad":
                return self.eval_record.get_vargrad(label_index)
            raise NotImplementedError
        raise ValueError("Saliency name not provided")
