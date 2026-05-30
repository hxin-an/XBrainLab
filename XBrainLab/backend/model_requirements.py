"""Lightweight model input requirements shared by UI/backend readiness checks."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelSampleRequirement:
    """Minimum epoch length required to instantiate a model."""

    model_name: str
    min_samples: int
    min_duration_seconds: float
    unsupported_reason: str = ""


def minimum_samples_for_model(
    model_name: str | None,
    *,
    sfreq: float | int | None,
    model_params: dict[str, Any] | None = None,
) -> ModelSampleRequirement | None:
    """Return minimum sample requirement for a supported model without torch."""
    if model_name is None or sfreq is None:
        return None
    try:
        sfreq_value = float(sfreq)
    except (TypeError, ValueError):
        return None
    if sfreq_value <= 0:
        return None

    normalized = str(model_name).strip().lower()
    params = dict(model_params or {})
    if normalized == "eegnet":
        half_sf = math.floor(sfreq_value / 2)
        separable_kernel = math.floor(half_sf / 4)
        pool_1 = _positive_int(params.get("pool_1"), default=4)
        pool_2 = _positive_int(params.get("pool_2"), default=8)
        if half_sf < 1 or separable_kernel < 1:
            return ModelSampleRequirement(
                model_name="EEGNet",
                min_samples=10**12,
                min_duration_seconds=math.inf,
                unsupported_reason=(
                    "EEGNet requires a sampling frequency high enough to form "
                    "positive temporal kernels."
                ),
            )
        min_samples = half_sf - 1 + pool_1 * (pool_2 + separable_kernel - 1)
        display_name = "EEGNet"
    elif normalized == "sccnet":
        min_samples = int(sfreq_value / 2) + 1
        display_name = "SCCNet"
    elif normalized == "shallowconvnet":
        pool_len = _positive_int(params.get("pool_len"), default=75)
        min_samples = math.ceil(sfreq_value * 0.1) + pool_len
        display_name = "ShallowConvNet"
    else:
        return None

    return ModelSampleRequirement(
        model_name=display_name,
        min_samples=int(min_samples),
        min_duration_seconds=float(min_samples) / sfreq_value,
    )


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
