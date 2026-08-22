# Adapted from braindecode 1.6.1.
# License: BSD-3-Clause
"""Small tensor conversion helper required by the reviewed convolution code."""

import numpy as np
import torch


def np_to_th(array, requires_grad=False, dtype=None, pin_memory=False, **kwargs):
    """Convert a NumPy array to a torch tensor without changing values."""
    if not hasattr(array, "__len__"):
        array = [array]
    values = np.asarray(array)
    if dtype is not None:
        values = values.astype(dtype)
    tensor = torch.tensor(values, requires_grad=requires_grad, **kwargs)
    if pin_memory:
        tensor = tensor.pin_memory()
    return tensor
