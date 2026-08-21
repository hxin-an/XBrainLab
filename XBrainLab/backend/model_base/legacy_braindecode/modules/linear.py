# License: BSD-3-Clause
"""Baseline constrained linear layer adapted from Braindecode 1.6.1."""

from torch import nn
from torch.nn.utils.parametrize import register_parametrization

from .parametrization import MaxNormParametrize


class LinearWithConstraint(nn.Linear):
    """Linear layer with max-norm parametrization."""

    def __init__(self, *args, max_norm=1.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_norm = max_norm
        register_parametrization(self, "weight", MaxNormParametrize(self.max_norm))
