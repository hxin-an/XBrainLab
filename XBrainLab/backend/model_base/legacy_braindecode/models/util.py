# Authors: Robin Schirrmeister <robintibor@gmail.com>
#          Hubert Banville <hubert.jbanville@gmail.com>
#
# License: BSD (3-clause)
"""Model-only utility subset adapted from Braindecode 1.6.1."""

# ruff: noqa: UP035, UP045

import inspect
from functools import wraps
from typing import Any, Optional, Sequence

import numpy as np
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


def extract_channel_locations_from_chs_info(
    chs_info: Optional[Sequence[dict[str, Any]]],
    num_channels: Optional[int] = None,
) -> Optional[np.ndarray]:
    """Extract valid 3-D channel locations from MNE-style channel metadata."""
    if chs_info is None:
        return None

    locations = []
    n_to_extract = num_channels if num_channels is not None else len(chs_info)
    for ch_info in chs_info[:n_to_extract]:
        if not isinstance(ch_info, dict):
            break
        loc = ch_info.get("loc")
        if loc is None:
            break
        try:
            loc_array = np.asarray(loc, dtype=np.float32)
        except (ValueError, TypeError):
            break
        if loc_array.ndim != 1 or loc_array.size < 3:
            break
        locations.append(loc_array[:3])

    if not locations:
        return None
    result = np.stack(locations, axis=0)
    if np.allclose(result, 0):
        return None
    return result
