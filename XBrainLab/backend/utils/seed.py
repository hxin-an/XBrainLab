"""Random seed management for reproducible experiments (PyTorch, NumPy)."""

from __future__ import annotations

import random

import numpy as np
import torch
from numpy.random import MT19937, RandomState, SeedSequence


def set_seed(seed: int | None = None, deterministic: bool = False) -> int:
    """Set random seeds for reproducibility across all frameworks.

    Configures random seeds for Python's ``random`` module, PyTorch
    (CPU and CUDA), and NumPy.

    Args:
        seed: Random seed value. If ``None``, generated automatically
            via :func:`torch.seed`.
        deterministic: If ``True``, forces deterministic CUDA algorithms
            (may reduce performance).

    Returns:
        The seed value that was applied.

    """
    if seed is None:
        seed = torch.seed() & 0xFFFF_FFFF  # Mask to 32 bits for safe serialisation

    # random
    random.seed(seed)
    # torch
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        if deterministic:
            torch.backends.cudnn.benchmark = False
            torch.backends.cudnn.deterministic = True
        else:
            torch.backends.cudnn.benchmark = True
            torch.backends.cudnn.deterministic = False
    # numpy
    rs = RandomState(MT19937(SeedSequence(seed)))
    np.random.set_state(rs.get_state())

    return seed


def get_random_state() -> tuple:
    """Capture the current random state of PyTorch, Python, and NumPy.

    Returns:
        A tuple of ``(torch_rng_state, random_state, numpy_state,
        cuda_rng_states)``. ``cuda_rng_states`` is ``None`` when CUDA is not
        available.

    """
    cuda_rng_states = (
        torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None
    )
    return (
        torch.get_rng_state(),
        random.getstate(),
        np.random.get_state(),
        cuda_rng_states,
    )


def set_random_state(state: tuple) -> None:
    """Restore the random state of PyTorch, Python, and NumPy.

    Args:
        state: The four-part state returned by :func:`get_random_state`.

    """
    if not isinstance(state, tuple) or len(state) != 4:
        raise ValueError("Random state must include CPU, Python, NumPy, and CUDA state")
    torch_state, random_state, np_state, cuda_rng_states = state
    if cuda_rng_states is not None and not torch.cuda.is_available():
        raise RuntimeError("CUDA RNG state cannot be restored without CUDA")

    torch.set_rng_state(torch_state)
    random.setstate(random_state)
    np.random.set_state(np_state)
    if cuda_rng_states is not None:
        torch.cuda.set_rng_state_all(cuda_rng_states)
