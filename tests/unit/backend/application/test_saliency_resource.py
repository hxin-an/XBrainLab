"""Focused contracts for saliency resource admission."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from XBrainLab.backend.application import saliency_resource
from XBrainLab.backend.application.saliency_policy import (
    baseline_saliency_params,
    normalize_saliency_params,
)


class _ArrayLike:
    def __init__(self, shape: tuple[int, ...], *, item_bytes: int) -> None:
        self.shape = shape
        elements = 1
        for dimension in shape:
            elements *= dimension
        self.nbytes = elements * item_bytes


class _EpochData:
    def __init__(self, shape: tuple[int, int, int]) -> None:
        self.data: Any = _ArrayLike(shape, item_bytes=4)

    def get_data(self) -> Any:
        return self.data

    def get_model_args(self) -> dict[str, int]:
        return {"n_channels": 8, "n_times": 128, "n_classes": 2}


class _Dataset:
    def __init__(
        self,
        shape: tuple[int, int, int],
        *,
        test_count: int,
    ) -> None:
        epoch_count = shape[0]
        self.epoch_data = _EpochData(shape)
        self.train_mask = [False] * epoch_count
        self.val_mask = [False] * epoch_count
        self.test_mask = [index < test_count for index in range(epoch_count)]

    def get_epoch_data(self) -> _EpochData:
        return self.epoch_data


class _Parameter:
    @staticmethod
    def numel() -> int:
        return 1_000

    @staticmethod
    def element_size() -> int:
        return 4


class _Model:
    @staticmethod
    def parameters() -> list[_Parameter]:
        return [_Parameter()]

    def cpu(self) -> None:
        return None


class _ModelHolder:
    target_model = type("EEGNet", (), {})

    @staticmethod
    def get_model(_args: dict[str, Any]) -> _Model:
        return _Model()


def _option(
    *,
    batch_size: int = 4,
    repeat_count: int = 1,
    use_cpu: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        bs=batch_size,
        repeat_num=repeat_count,
        use_cpu=use_cpu,
        gpu_idx=None if use_cpu else 0,
    )


def test_estimate_uses_shape_batch_methods_and_noise_partition() -> None:
    dataset = _Dataset((32, 8, 128), test_count=16)
    automatic_params, _method = normalize_saliency_params(
        "SmoothGrad",
        {"nt_samples": 16},
    )
    partitioned_params, _method = normalize_saliency_params(
        "SmoothGrad",
        {"nt_samples": 16, "nt_samples_batch_size": 2},
    )

    automatic = saliency_resource.estimate_saliency_resources(
        [dataset],
        _option(batch_size=8, repeat_count=2),
        _ModelHolder(),
        automatic_params,
    )
    partitioned = saliency_resource.estimate_saliency_resources(
        [dataset],
        _option(batch_size=8, repeat_count=2),
        _ModelHolder(),
        partitioned_params,
    )

    assert automatic["datasets"][0]["epoch_shape"] == [32, 8, 128]
    assert automatic["datasets"][0]["evaluation_batch_size"] == 8
    assert automatic["selected_methods"] == ["SmoothGrad"]
    assert automatic["peak_noise_partition"] == 16
    assert partitioned["peak_noise_partition"] == 2
    assert automatic["expanded_batch_bytes"] == (
        partitioned["expanded_batch_bytes"] * 8
    )
    assert automatic["retained_attribution_bytes"] == 16 * 8 * 128 * 4 * 2


def test_preflight_allows_normal_recommended_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        saliency_resource.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 2 * 1024**3,
                "total_bytes": 4 * 1024**3,
                "used_bytes": 2 * 1024**3,
            }
        ),
    )
    params, _method = normalize_saliency_params(None, baseline_saliency_params())

    result = saliency_resource.check_saliency_resource_preflight(
        [_Dataset((32, 8, 128), test_count=8)],
        _option(batch_size=4),
        _ModelHolder(),
        params,
    )

    assert not result.blocking
    assert result.risk_level.value == "safe"
    assert result.diagnostics["selected_methods"] == [
        "Gradient",
        "Gradient * Input",
    ]
    assert result.diagnostics["peak_noise_partition"] == 1


def test_preflight_marks_near_capacity_saliency_as_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = _Dataset((32, 8, 128), test_count=8)
    option = _option(batch_size=4)
    params, _method = normalize_saliency_params(None, baseline_saliency_params())
    estimate = saliency_resource.estimate_saliency_resources(
        [dataset],
        option,
        _ModelHolder(),
        params,
    )
    required = estimate["estimated_ram_working_set_bytes"]
    available = required * 10 // 7
    monkeypatch.setattr(
        saliency_resource.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": available,
                "total_bytes": available * 2,
                "used_bytes": available,
            }
        ),
    )

    result = saliency_resource.check_saliency_resource_preflight(
        [dataset],
        option,
        _ModelHolder(),
        params,
    )

    assert result.risk_level.value == "warning"
    assert result.requires_confirmation
    assert not result.blocking


def test_preflight_fails_closed_when_epoch_shape_is_unavailable() -> None:
    dataset = _Dataset((8, 2, 16), test_count=4)
    dataset.epoch_data.data = object()
    params, _method = normalize_saliency_params(None, baseline_saliency_params())

    result = saliency_resource.check_saliency_resource_preflight(
        [dataset],
        _option(),
        _ModelHolder(),
        params,
    )

    assert result.blocking
    assert "epoch shape" in result.message
    assert result.diagnostics["reason"] == "resource_context_unavailable"


def test_preflight_requires_confirmation_when_available_ram_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        saliency_resource.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": None,
                "total_bytes": None,
                "used_bytes": None,
            }
        ),
    )
    params, _method = normalize_saliency_params(None, baseline_saliency_params())

    result = saliency_resource.check_saliency_resource_preflight(
        [_Dataset((8, 2, 16), test_count=4)],
        _option(),
        _ModelHolder(),
        params,
    )

    assert not result.blocking
    assert result.requires_confirmation
    assert result.risk_level.value == "unknown"
    assert "available RAM" in result.message
    assert result.diagnostics["ram_risk_level"] == "unknown"
