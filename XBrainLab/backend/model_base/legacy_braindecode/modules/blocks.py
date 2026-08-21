# License: BSD-3-Clause
"""Baseline multi-branch block adapted from Braindecode 1.6.1."""

import torch
from torch import nn


class InceptionBlock(nn.Module):
    """Apply convolutional branches and concatenate their channel outputs."""

    def __init__(self, branches):
        super().__init__()
        self.branches = nn.ModuleList(branches)

    def forward(self, x):
        return torch.cat([branch(x) for branch in self.branches], 1)
