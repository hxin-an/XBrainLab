"""Base visualizer module for generating matplotlib figures from evaluation records."""

import contextlib

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
        created_figure = self.fig is None
        if self.fig is None:
            self.fig = Figure(figsize=self.figsize, dpi=self.dpi)
        try:
            self.fig.clf()
            return self._get_plt(*args, **kwargs)
        except Exception:
            if created_figure and self.fig is not None:
                plt.close(self.fig)
                self.fig = None
            raise

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
        saliency_store = self._saliency_store(saliency_name)
        resolved_key = self._resolve_saliency_key(
            saliency_store,
            label_index,
            label_index,
            label_index,
        )
        if resolved_key is None:
            available = self._available_saliency_keys(saliency_store)
            raise KeyError(
                f"Cannot map label {label_index!r} to saliency results. "
                f"Available saliency keys: {available}.",
            )
        return saliency_store[resolved_key]

    def iter_saliency_by_label(
        self,
        saliency_name: str,
    ) -> list[tuple[object, str, np.ndarray]]:
        """Return available saliency arrays paired with display labels.

        Training results may be keyed by model class indices (``0..n-1``),
        original event codes (for example ``769``), or stringified keys after
        loading older records.  The visualizers should display what exists
        instead of assuming a zero-based range from the epoch label count.
        """
        saliency_store = self._saliency_store(saliency_name)
        label_map = getattr(self.epoch_data, "label_map", {}) or {}
        mapped: list[tuple[object, str, np.ndarray]] = []
        saliency_keys = self._iter_saliency_keys(saliency_store)
        for order_index, resolved_key in enumerate(saliency_keys):
            saliency = saliency_store[resolved_key]
            if not self._has_saliency_data(saliency):
                continue
            label_name = self._label_name_for_key(
                resolved_key,
                order_index,
                label_map,
                class_count=len(saliency_keys),
            )
            mapped.append((resolved_key, label_name, saliency))
        return mapped

    def _saliency_store(self, saliency_name: str):
        if saliency_name is None:
            raise ValueError("Saliency name not provided")
        if saliency_name == "Gradient":
            return self.eval_record.gradient
        if saliency_name == "Gradient * Input":
            return self.eval_record.gradient_input
        if saliency_name == "SmoothGrad":
            return self.eval_record.smoothgrad
        if saliency_name == "SmoothGrad_Squared":
            return self.eval_record.smoothgrad_sq
        if saliency_name == "VarGrad":
            return self.eval_record.vargrad
        raise NotImplementedError

    @staticmethod
    def _resolve_saliency_key(
        saliency_store,
        label_key: object,
        label_name: object,
        order_index: int,
    ) -> object | None:
        candidates: list[object] = [label_key, label_name]
        for value in (label_key, label_name):
            if not isinstance(value, (str, bytes, int, np.integer)):
                continue
            with contextlib.suppress(TypeError, ValueError):
                candidates.append(int(value))
        candidates.append(order_index)

        if isinstance(saliency_store, dict):
            for candidate in candidates:
                if candidate in saliency_store:
                    return candidate
                for available_key in saliency_store:
                    if str(available_key) == str(candidate):
                        return available_key
            return None

        try:
            store_len = len(saliency_store)
        except TypeError:
            return None
        for candidate in candidates:
            if (
                isinstance(candidate, (int, np.integer))
                and 0 <= int(candidate) < store_len
            ):
                return int(candidate)
        return None

    @staticmethod
    def _has_saliency_data(saliency) -> bool:
        try:
            return len(saliency) > 0
        except TypeError:
            return False

    @staticmethod
    def _iter_saliency_keys(saliency_store) -> list[object]:
        if isinstance(saliency_store, dict):
            return list(saliency_store.keys())
        try:
            return list(range(len(saliency_store)))
        except TypeError:
            return []

    @staticmethod
    def _available_saliency_keys(saliency_store) -> str:
        keys = Visualizer._iter_saliency_keys(saliency_store)
        if not keys:
            return "none"
        return ", ".join(map(str, keys))

    @staticmethod
    def _label_name_for_key(
        saliency_key: object,
        order_index: int,
        label_map: object,
        class_count: int | None = None,
    ) -> str:
        if isinstance(label_map, dict):
            if saliency_key in label_map:
                return str(label_map[saliency_key])
            for label_key, label_name in label_map.items():
                if str(label_key) == str(saliency_key):
                    return str(label_name)
            label_names = list(label_map.values())
            if (
                class_count is not None
                and len(label_names) == class_count
                and 0 <= order_index < len(label_names)
            ):
                return str(label_names[order_index])
        return str(saliency_key)
