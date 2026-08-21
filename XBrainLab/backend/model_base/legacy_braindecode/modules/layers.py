# Authors: Robin Schirrmeister <robintibor@gmail.com>
#
# License: BSD (3-clause)
"""Baseline shape layers adapted from Braindecode 1.6.1."""

import torch
from einops.layers.torch import Rearrange
from torch import nn


class Ensure4d(nn.Module):
    """Append singleton dimensions until an input tensor is four-dimensional."""

    def forward(self, x):
        while len(x.shape) < 4:
            x = x.unsqueeze(-1)
        return x


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
