from unittest.mock import MagicMock, patch

import numpy as np
import torch

from XBrainLab.backend.utils import seed


def test_set_seed():
    result = seed.set_seed()
    seed_target = 42
    assert isinstance(result, int)
    assert seed.set_seed(seed_target) == seed_target


def test_set_seed_configures_cuda_determinism() -> None:
    with patch("XBrainLab.backend.utils.seed.torch") as mock_torch:
        mock_torch.cuda.is_available.return_value = True
        mock_torch.backends.cudnn = MagicMock()

        assert seed.set_seed(42, deterministic=True) == 42

    mock_torch.cuda.manual_seed.assert_called_once_with(42)
    mock_torch.cuda.manual_seed_all.assert_called_once_with(42)
    assert mock_torch.backends.cudnn.benchmark is False
    assert mock_torch.backends.cudnn.deterministic is True


def test_set_seed_leaves_cuda_nondeterministic_when_requested() -> None:
    with patch("XBrainLab.backend.utils.seed.torch") as mock_torch:
        mock_torch.cuda.is_available.return_value = True
        mock_torch.backends.cudnn = MagicMock()

        assert seed.set_seed(42, deterministic=False) == 42

    assert mock_torch.backends.cudnn.benchmark is True
    assert mock_torch.backends.cudnn.deterministic is False


def test_get_random_state():
    result = seed.get_random_state()
    tuple_length = 4
    assert isinstance(result, tuple)
    assert len(result) == tuple_length
    assert isinstance(result[0], torch.ByteTensor)
    assert isinstance(result[1], tuple)
    assert isinstance(result[2], tuple)
    assert result[3] is None or isinstance(result[3], list)


def test_set_random_state():
    state = seed.get_random_state()
    seed.set_random_state(state)
    result = seed.get_random_state()
    # torch
    assert np.allclose(state[0], result[0])
    # random
    assert state[1] == result[1]
    # numpy
    for s, r in zip(state[2], result[2], strict=False):
        if isinstance(s, np.ndarray):
            assert (s == r).all()
        else:
            assert s == r


def test_random_state_round_trips_cuda_generators_when_available():
    cuda_state = [torch.tensor([1, 2, 3], dtype=torch.uint8)]

    with (
        patch("torch.cuda.is_available", return_value=True),
        patch("torch.cuda.get_rng_state_all", return_value=cuda_state),
        patch("torch.cuda.set_rng_state_all") as restore_cuda,
    ):
        state = seed.get_random_state()
        seed.set_random_state(state)

    assert state[3] == cuda_state
    restore_cuda.assert_called_once_with(cuda_state)
