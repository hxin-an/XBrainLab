# License: BSD-3-Clause
"""Baseline initialization helper adapted from Braindecode 1.6.1."""

import math

from torch import nn


def glorot_weight_zero_bias(model):
    """Apply upstream Xavier, batch-norm, and zero-bias initialization."""
    for module in model.modules():
        if hasattr(module, "weight") and "BatchNorm" in module.__class__.__name__:
            nn.init.constant_(module.weight, 1)
        if hasattr(module, "bias") and module.bias is not None:
            nn.init.constant_(module.bias, 0)


def rescale_parameter(param, layer_id):
    """Rescale a transformer parameter by its one-based layer depth."""
    param.div_(math.sqrt(2.0 * layer_id))
