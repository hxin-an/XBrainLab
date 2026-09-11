"""Actual experiment RNG replay; generated values are not cryptographic secrets."""

# ruff: noqa: S311

import random
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch

from XBrainLab.backend.utils import seed


@pytest.fixture
def cpu_rng_state():
    with patch(
        "XBrainLab.backend.utils.seed.torch.cuda.is_available", return_value=False
    ):
        original_state = seed.get_random_state()
        try:
            yield
        finally:
            seed.set_random_state(original_state)


def test_set_seed(cpu_rng_state):
    result = seed.set_seed()
    seed_target = 42
    assert isinstance(result, int)
    assert seed.set_seed(seed_target) == seed_target


def test_set_seed_replays_actual_python_numpy_and_torch_cpu_draws(
    cpu_rng_state,
) -> None:
    seed.set_seed(42)
    first_python = random.random()
    first_numpy = np.random.random(3)
    first_torch = torch.rand(3)

    seed.set_seed(42)
    assert random.random() == first_python
    assert np.array_equal(np.random.random(3), first_numpy)
    assert torch.equal(torch.rand(3), first_torch)


def test_set_seed_configures_cuda_determinism(cpu_rng_state) -> None:
    with patch("XBrainLab.backend.utils.seed.torch") as mock_torch:
        mock_torch.cuda.is_available.return_value = True
        mock_torch.backends.cudnn = MagicMock()

        assert seed.set_seed(42, deterministic=True) == 42

    mock_torch.cuda.manual_seed.assert_called_once_with(42)
    mock_torch.cuda.manual_seed_all.assert_called_once_with(42)
    assert mock_torch.backends.cudnn.benchmark is False
    assert mock_torch.backends.cudnn.deterministic is True


def test_set_seed_leaves_cuda_nondeterministic_when_requested(cpu_rng_state) -> None:
    with patch("XBrainLab.backend.utils.seed.torch") as mock_torch:
        mock_torch.cuda.is_available.return_value = True
        mock_torch.backends.cudnn = MagicMock()

        assert seed.set_seed(42, deterministic=False) == 42

    assert mock_torch.backends.cudnn.benchmark is True
    assert mock_torch.backends.cudnn.deterministic is False


def test_get_random_state():
    with patch(
        "XBrainLab.backend.utils.seed.torch.cuda.is_available", return_value=False
    ):
        result = seed.get_random_state()
    tuple_length = 4
    assert isinstance(result, tuple)
    assert len(result) == tuple_length
    assert isinstance(result[0], torch.ByteTensor)
    assert isinstance(result[1], tuple)
    assert isinstance(result[2], tuple)
    assert result[3] is None


def test_set_random_state_replays_advanced_python_numpy_and_torch_cpu_draws(
    cpu_rng_state,
) -> None:
    state = seed.get_random_state()
    expected_python = random.random()
    expected_numpy = np.random.random(3)
    expected_torch = torch.rand(3)

    random.random()
    np.random.random(3)
    torch.rand(3)

    seed.set_random_state(state)
    assert random.random() == expected_python
    assert np.array_equal(np.random.random(3), expected_numpy)
    assert torch.equal(torch.rand(3), expected_torch)


def test_set_random_state_rejects_malformed_state_without_cpu_mutation(
    cpu_rng_state,
) -> None:
    seed.set_seed(123)
    state = seed.get_random_state()

    with pytest.raises(ValueError, match="must include"):
        seed.set_random_state(("not a random state",))

    actual_python = random.random()
    actual_numpy = np.random.random(3)
    actual_torch = torch.rand(3)
    seed.set_random_state(state)
    assert random.random() == actual_python
    assert np.array_equal(np.random.random(3), actual_numpy)
    assert torch.equal(torch.rand(3), actual_torch)


def test_set_random_state_rejects_cuda_state_without_cpu_mutation(
    cpu_rng_state,
) -> None:
    seed.set_seed(123)
    requested_state = seed.get_random_state()
    seed.set_seed(456)
    current_state = seed.get_random_state()
    cuda_state = (*requested_state[:3], [torch.tensor([1, 2, 3], dtype=torch.uint8)])

    with pytest.raises(RuntimeError, match="without CUDA"):
        seed.set_random_state(cuda_state)

    actual_python = random.random()
    actual_numpy = np.random.random(3)
    actual_torch = torch.rand(3)
    seed.set_random_state(current_state)
    assert random.random() == actual_python
    assert np.array_equal(np.random.random(3), actual_numpy)
    assert torch.equal(torch.rand(3), actual_torch)


def test_random_state_round_trips_cuda_generators_when_available(cpu_rng_state):
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
