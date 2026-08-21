# Authors: Robin Schirrmeister <robintibor@gmail.com>
#
# License: BSD (3-clause)
"""Baseline shape layers adapted from Braindecode 1.6.1."""

import torch
from einops.layers.torch import Rearrange
from torch import nn

from ..functional import drop_path


class Ensure4d(nn.Module):
    """Append singleton dimensions until an input tensor is four-dimensional."""

    def forward(self, x):
        while len(x.shape) < 4:
            x = x.unsqueeze(-1)
        return x


class Chomp1d(nn.Module):
    """Remove a fixed number of samples from the end of a sequence."""

    def __init__(self, chomp_size):
        super().__init__()
        self.chomp_size = chomp_size

    def extra_repr(self):
        return f"chomp_size={self.chomp_size}"

    def forward(self, x):
        return x[:, :, : -self.chomp_size].contiguous()


class DropPath(nn.Module):
    """Drop residual paths per sample during training."""

    def __init__(self, drop_prob=None):
        super().__init__()
        self.drop_prob = drop_prob

    def forward(self, x):
        return drop_path(x, self.drop_prob, self.training)

    def extra_repr(self) -> str:
        return f"p={self.drop_prob}"


class SqueezeFinalOutput(nn.Module):
    """Remove the final feature dimension and a singleton time dimension."""

    def __init__(self):
        super().__init__()
        self.squeeze = Rearrange("b c t 1 -> b c t")

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.squeeze(x)
        if x.shape[-1] == 1:
            x = x.squeeze(-1)
        return x
