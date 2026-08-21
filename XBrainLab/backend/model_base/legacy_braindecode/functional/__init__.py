"""Functional helpers used by reviewed legacy model implementations."""

from .functions import safe_log, square
from .initialization import glorot_weight_zero_bias

__all__ = [
    "glorot_weight_zero_bias",
    "safe_log",
    "square",
]
