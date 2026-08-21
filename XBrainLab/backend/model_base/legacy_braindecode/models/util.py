# Authors: Robin Schirrmeister <robintibor@gmail.com>
#          Hubert Banville <hubert.jbanville@gmail.com>
#
# License: BSD (3-clause)
"""Model-only utility subset adapted from Braindecode 1.6.1."""

import inspect
from functools import wraps

from torch import nn

_BATCH_NORM_MODULES = (
    nn.BatchNorm1d,
    nn.BatchNorm2d,
    nn.BatchNorm3d,
    nn.SyncBatchNorm,
)


def _disable_batch_norm_training_if_batch_size_one(forward):
    """Temporarily put BatchNorm layers in eval mode for batch size one."""
    forward_signature = inspect.signature(forward)

    @wraps(forward)
    def wrapped(self, *args, **kwargs):
        bound = forward_signature.bind(self, *args, **kwargs)
        inputs = next(
            value for name, value in bound.arguments.items() if name != "self"
        )
        batch_norms = []
        if self.training and inputs.shape[0] == 1:
            batch_norms = [
                layer
                for layer in self.modules()
                if isinstance(layer, _BATCH_NORM_MODULES) and layer.training
            ]
            for batch_norm in batch_norms:
                batch_norm.train(False)
        try:
            return forward(self, *args, **kwargs)
        finally:
            for batch_norm in batch_norms:
                batch_norm.train(True)

    return wrapped
