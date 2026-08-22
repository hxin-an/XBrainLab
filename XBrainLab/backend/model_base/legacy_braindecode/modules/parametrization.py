# License: BSD-3-Clause
"""Baseline max-norm parametrization adapted from Braindecode 1.6.1."""

import torch
from torch import nn


class MaxNorm(nn.Module):
    """Constrain column norms while preserving parametrization invertibility."""

    def __init__(self, max_norm_val: float = 2.0, eps: float = 1e-5):
        super().__init__()
        self.max_norm_val = max_norm_val
        self.eps = eps

    def forward(self, weights: torch.Tensor) -> torch.Tensor:
        norm = weights.norm(2, dim=0, keepdim=True)
        denominator = norm.clamp(min=self.max_norm_val / 2)
        numerator = denominator.clamp(max=self.max_norm_val)
        return weights * (numerator / (denominator + self.eps))

    def right_inverse(self, weights: torch.Tensor) -> torch.Tensor:
        norm = weights.norm(2, dim=0, keepdim=True)
        denominator = norm.clamp(min=self.max_norm_val / 2)
        numerator = denominator.clamp(max=self.max_norm_val)
        scale = numerator / (denominator + self.eps)
        return weights / scale


class MaxNormParametrize(nn.Module):
    """Constrain rows of a weight tensor to a maximum L2 norm."""

    def __init__(self, max_norm: float = 1.0):
        super().__init__()
        self.max_norm = max_norm

    def forward(self, weights: torch.Tensor) -> torch.Tensor:
        return weights.renorm(p=2, dim=0, maxnorm=self.max_norm)
