# License: BSD-3-Clause
"""Baseline initialization helper adapted from Braindecode 1.6.1."""

from torch import nn


def glorot_weight_zero_bias(model):
    """Apply upstream Xavier, batch-norm, and zero-bias initialization."""
    for module in model.modules():
        if hasattr(module, "weight") and "BatchNorm" in module.__class__.__name__:
            nn.init.constant_(module.weight, 1)
        if hasattr(module, "bias") and module.bias is not None:
            nn.init.constant_(module.bias, 0)
