# License: BSD-3-Clause
"""Baseline expression wrapper adapted from Braindecode 1.6.1."""

import torch
from torch import nn


class Expression(nn.Module):
    """Compute a supplied expression during the forward pass."""

    def __init__(self, expression_fn):
        super().__init__()
        self.expression_fn = expression_fn

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.expression_fn(x)

    def __repr__(self):
        if hasattr(self.expression_fn, "func") and hasattr(
            self.expression_fn, "kwargs"
        ):
            expression_str = (
                f"{self.expression_fn.func.__name__} {self.expression_fn.kwargs!s}"
            )
        elif hasattr(self.expression_fn, "__name__"):
            expression_str = self.expression_fn.__name__
        else:
            expression_str = repr(self.expression_fn)
        return f"{self.__class__.__name__}(expression={expression_str}) "
