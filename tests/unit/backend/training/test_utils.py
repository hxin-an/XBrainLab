"""Unit tests for training/utils — optimizer helpers and device queries."""

import pytest
import torch

from XBrainLab.backend.training.utils import (
    get_device_count,
    get_device_name,
    get_optimizer_classes,
    get_optimizer_params,
    instantiate_optimizer,
    parse_optimizer_param,
)


class TestGetOptimizerClasses:
    def test_returns_dict(self):
        result = get_optimizer_classes()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_contains_common_optimizers(self):
        result = get_optimizer_classes()
        assert "Adam" in result
        assert "SGD" in result
        assert "AdamW" in result

    def test_values_are_classes(self):
        result = get_optimizer_classes()
        for cls in result.values():
            assert isinstance(cls, type)


class TestGetOptimizerParams:
    def test_adam_params(self):
        params = get_optimizer_params(torch.optim.Adam)
        param_names = [p[0] for p in params]
        assert "betas" in param_names
        assert "eps" in param_names
        assert "weight_decay" in param_names
        # lr should be excluded
        for name, _ in params:
            assert "lr" not in name

    def test_sgd_params(self):
        params = get_optimizer_params(torch.optim.SGD)
        param_names = [p[0] for p in params]
        assert "momentum" in param_names

    def test_returns_list_of_tuples(self):
        params = get_optimizer_params(torch.optim.Adam)
        assert isinstance(params, list)
        for item in params:
            assert isinstance(item, tuple)
            assert len(item) == 2


class TestInstantiateOptimizer:
    def test_creates_optimizer(self):
        opt = instantiate_optimizer(torch.optim.Adam, {}, lr=0.001)
        assert isinstance(opt, torch.optim.Adam)

    def test_with_custom_params(self):
        opt = instantiate_optimizer(torch.optim.SGD, {"momentum": 0.9}, lr=0.01)
        assert isinstance(opt, torch.optim.SGD)


@pytest.mark.parametrize(
    ("optimizer", "parameter", "value", "expected"),
    [
        (torch.optim.SGD, "momentum", "0.9", 0.9),
        (torch.optim.SGD, "weight_decay", "0.0001", 0.0001),
        (torch.optim.Adam, "weight_decay", "0.0001", 0.0001),
    ],
)
def test_parse_optimizer_param_accepts_fractional_values_with_integer_defaults(
    optimizer,
    parameter,
    value,
    expected,
) -> None:
    assert parse_optimizer_param(optimizer, parameter, value) == pytest.approx(expected)


class TestGetDeviceCount:
    def test_returns_int(self):
        count = get_device_count()
        assert isinstance(count, int)
        assert count >= 0


class TestGetDeviceName:
    def test_returns_string_for_cuda_device(self, monkeypatch):
        monkeypatch.setattr(
            torch.cuda,
            "get_device_name",
            lambda index: "Test CUDA Device" if index == 0 else "Unexpected Device",
        )

        name = get_device_name(0)

        assert isinstance(name, str)
        assert name == "Test CUDA Device"

    def test_raises_on_invalid_index(self, monkeypatch):
        def raise_for_invalid_index(_index: int) -> str:
            raise AssertionError("Invalid device index")

        monkeypatch.setattr(torch.cuda, "get_device_name", raise_for_invalid_index)

        with pytest.raises((RuntimeError, AssertionError)):
            get_device_name(0)
