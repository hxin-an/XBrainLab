"""Shared scientific display semantics for saliency visualizations."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

NONNEGATIVE_SALIENCY_METHODS = frozenset({"SmoothGrad_Squared", "VarGrad"})


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
    return ("Reds" if nonnegative else "coolwarm"), color_min, color_max
