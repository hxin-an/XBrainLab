# License: BSD-3-Clause
"""Baseline constrained linear layer adapted from Braindecode 1.6.1."""

from torch import nn
from torch.nn.utils.parametrize import register_parametrization

from .parametrization import MaxNorm, MaxNormParametrize


class MaxNormLinear(nn.Linear):
    """Linear layer with max-norm parametrization."""

    def __init__(
        self,
        in_features,
        out_features,
        bias=True,
        max_norm_val: float = 2.0,
        eps: float = 1e-5,
        **kwargs,
    ):
        super().__init__(
            in_features=in_features,
            out_features=out_features,
            bias=bias,
            **kwargs,
        )
        self._max_norm_val = max_norm_val
        self._eps = eps
        register_parametrization(
            self,
            "weight",
            MaxNorm(self._max_norm_val, self._eps),
        )


class LinearWithConstraint(nn.Linear):
    """Linear layer with max-norm parametrization."""

    def __init__(self, *args, max_norm=1.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_norm = max_norm
        register_parametrization(self, "weight", MaxNormParametrize(self.max_norm))
