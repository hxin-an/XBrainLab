# License: BSD-3-Clause
"""Baseline activation modules adapted from Braindecode 1.6.1."""

import torch
from torch import Tensor, nn

from .. import functional


class Square(nn.Module):
    """Element-wise square activation."""

    def forward(self, x) -> Tensor:
        return x * x


class SafeLog(nn.Module):
    """Clamp inputs before applying the natural logarithm."""

    def __init__(self, epsilon: float = 1e-6):
        super().__init__()
        self.epsilon = epsilon

    def forward(self, x) -> Tensor:
        return functional.safe_log(x=x, eps=self.epsilon)

    def extra_repr(self) -> str:
        return f"eps={self.epsilon}"


class LogActivation(nn.Module):
    """Apply the logarithm after adding a small positive epsilon."""

    def __init__(self, epsilon: float = 1e-6, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.epsilon = epsilon

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.log(x + self.epsilon)
