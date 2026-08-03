"""Shared scientific display semantics for saliency visualizations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
from matplotlib import colormaps
from matplotlib.colors import Colormap
from matplotlib.ticker import FuncFormatter

NONNEGATIVE_SALIENCY_METHODS = frozenset({"SmoothGrad_Squared", "VarGrad"})
SALIENCY_RED_BLUE_CMAP = "coolwarm"
ATTRIBUTION_MASKED_COLOR = "#777777"
ATTRIBUTION_COLORBAR_TICK_SIZE = 7
ATTRIBUTION_COLORBAR_LABEL_SIZE = 8


def attribution_colormap(name: str) -> Colormap:
    """Return one isolated attribution palette with shared exceptional colors."""
    cmap = colormaps[name].copy()
    cmap.set_bad(ATTRIBUTION_MASKED_COLOR)
    cmap.set_under(cmap(0.0))
    cmap.set_over(cmap(1.0))
    return cmap


def compact_attribution_tick(value: float, _position: int) -> str:
    """Return readable colorbar text for small attribution magnitudes."""
    abs_value = abs(value)
    if abs_value == 0:
        return "0"
    if 0.01 <= abs_value < 100:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{value:.1e}"


def style_attribution_colorbar(
    colorbar: Any,
    *,
    label: str | None = None,
) -> None:
    """Apply shared attribution tick and label styling to a colorbar."""
    colorbar.formatter = FuncFormatter(compact_attribution_tick)
    colorbar.update_ticks()
    colorbar.ax.tick_params(labelsize=ATTRIBUTION_COLORBAR_TICK_SIZE, pad=1)
    if label:
        colorbar.set_label(label, fontsize=ATTRIBUTION_COLORBAR_LABEL_SIZE)


def shared_color_limits(
    values: np.ndarray | Iterable[np.ndarray],
    *,
    nonnegative: bool,
    value_name: str = "Display data",
) -> tuple[float, float]:
    """Return one color range shared by every supplied display array."""
    arrays = (
        (np.asarray(values),)
        if isinstance(values, np.ndarray)
        else tuple(np.asarray(value) for value in values)
    )
    if not arrays or any(array.size == 0 for array in arrays):
        raise ValueError(f"{value_name} values are empty.")

    epsilon = float(np.finfo(float).eps)
    if nonnegative:
        global_min = min(float(np.min(array)) for array in arrays)
        if global_min < -1e-12:
            raise ValueError(
                f"{value_name} produced negative values for a non-negative map.",
            )
        global_max = max(float(np.max(array)) for array in arrays)
        return 0.0, max(global_max, epsilon)

    global_abs_max = max(float(np.max(np.abs(array))) for array in arrays)
    color_max = max(global_abs_max, epsilon)
    return -color_max, color_max


def saliency_color_scale(
    method: str,
    values: np.ndarray | Iterable[np.ndarray],
    *,
    absolute: bool,
) -> tuple[str, float, float]:
    """Return a colormap and limits that preserve each method's sign semantics."""
    nonnegative = absolute or method in NONNEGATIVE_SALIENCY_METHODS
    color_min, color_max = shared_color_limits(
        values,
        nonnegative=nonnegative,
        value_name=method,
    )
    return ("Reds" if nonnegative else SALIENCY_RED_BLUE_CMAP), color_min, color_max
