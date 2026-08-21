# License: BSD-3-Clause
"""Baseline max-norm parametrization adapted from Braindecode 1.6.1."""

import torch
from torch import nn


class MaxNormParametrize(nn.Module):
    """Constrain rows of a weight tensor to a maximum L2 norm."""

    def __init__(self, max_norm: float = 1.0):
        super().__init__()
        self.max_norm = max_norm

    def forward(self, weights: torch.Tensor) -> torch.Tensor:
        return weights.renorm(p=2, dim=0, maxnorm=self.max_norm)
