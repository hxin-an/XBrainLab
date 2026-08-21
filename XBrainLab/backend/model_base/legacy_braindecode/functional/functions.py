# Authors: Robin Schirrmeister <robintibor@gmail.com>
#          Bruno Aristimunha <b.aristimunha@gmail.com>
#
# License: BSD (3-clause)
"""Baseline activation functions adapted from Braindecode 1.6.1."""

import torch


def square(x):
    return x * x


def safe_log(x, eps: float = 1e-6) -> torch.Tensor:
    """Prevent ``log(0)`` by clamping the input to ``eps``."""
    return torch.log(torch.clamp(x, min=eps))
