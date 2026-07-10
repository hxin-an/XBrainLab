"""Focused tests for RAM/VRAM resource safety checks."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from XBrainLab.backend.application import resource_guard


class _ArrayLike:
    def __init__(
        self,
        *,
        nbytes: int,
        shape: tuple[int, ...],
        dtype: Any | None = None,
    ) -> None:
        self.nbytes = nbytes
        self.shape = shape
        if dtype is not None:
            self.dtype = dtype


class _EpochData:
    def __init__(self, data: Any, labels: Any) -> None:
        self.data = data
        self.labels = labels

    def get_data(self) -> Any:
        return self.data

    def get_label_list(self) -> Any:
        return self.labels

    def get_model_args(self) -> dict[str, int]:
        return {"n_channels": 22, "n_times": 301, "n_classes": 4}


class _Dataset:
    def __init__(self, epoch_data: _EpochData) -> None:
        self.epoch_data = epoch_data
        self.train_mask = [True] * 20
        self.val_mask = [True] * 4
        self.test_mask = [True] * 4

    def get_epoch_data(self) -> _EpochData:
        return self.epoch_data


def test_dataset_ram_check_blocks_large_file_size_fallback(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "large.unknown"
    path.write_bytes(b"0" * 100)
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {"available_bytes": 400, "total_bytes": 1_000, "used_bytes": 600}
        ),
    )

    result = resource_guard.ResourceChecker.check_dataset_load_safe([str(path)])

    assert result.risk_level == resource_guard.RISK_BLOCKING
    assert result.required_memory_bytes is not None
    assert result.required_memory_bytes > int(400 * resource_guard.RAM_BLOCKING_RATIO)
    assert "lazy" not in result.message.lower()
    assert "memory mapping" not in result.message.lower()


def test_dataset_ram_check_warns_without_blocking(tmp_path, monkeypatch) -> None:
    path = tmp_path / "warning.unknown"
    path.write_bytes(b"0" * 100)
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 2_000_000,
                "total_bytes": 4_000_000,
                "used_bytes": 2_000_000,
            }
        ),
    )

    preflight = resource_guard.check_import_resource_preflight([str(path)])

    assert preflight.ok is True
    assert preflight.warnings
    assert preflight.diagnostics["risk_level"] == resource_guard.RISK_WARNING


def test_training_vram_check_uses_peak_batch_not_fold_sum(monkeypatch) -> None:
    data = _ArrayLike(nbytes=40_000, shape=(10, 1_000))
    labels = _ArrayLike(nbytes=80, shape=(10,))
    datasets = [_Dataset(_EpochData(data, labels)), _Dataset(_EpochData(data, labels))]
    option = SimpleNamespace(use_cpu=False, gpu_idx=0, bs=5, optim=object)
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_gpu_vram_status",
        staticmethod(
            lambda _gpu_idx=None: {
                "available_bytes": 170_000,
                "total_bytes": 200_000,
                "used_bytes": 30_000,
                "allocated_bytes": 0,
                "reserved_bytes": 0,
                "gpu_name": "Test GPU",
            },
        ),
    )
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 10_000_000,
                "total_bytes": 20_000_000,
                "used_bytes": 10_000_000,
            },
        ),
    )

    result = resource_guard.ResourceChecker.check_training_config_safe(
        datasets,
        option,
    )

    assert result.risk_level == resource_guard.RISK_WARNING
    assert result.details["dataset_count"] == 2
    assert result.details["peak_input_batch_bytes"] < 40_000


def test_training_vram_check_unknown_when_cuda_memory_unavailable(monkeypatch) -> None:
    option = SimpleNamespace(use_cpu=False, gpu_idx=0, bs=32, optim=object)
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_gpu_vram_status",
        staticmethod(lambda _gpu_idx=None: {"available_bytes": None, "gpu_name": None}),
    )

    result = resource_guard.ResourceChecker.check_training_config_safe([], option)

    assert result.risk_level == resource_guard.RISK_UNKNOWN
    assert "Unable to estimate GPU memory" in result.message


def test_cuda_oom_detection_matches_common_runtime_errors(monkeypatch) -> None:
    calls: list[str] = []
    cuda = SimpleNamespace(
        is_available=lambda: True,
        empty_cache=lambda: calls.append("empty"),
    )
    monkeypatch.setattr(
        resource_guard,
        "_torch_module",
        lambda: SimpleNamespace(cuda=cuda),
    )

    assert resource_guard.is_cuda_oom_error(RuntimeError("CUDA out of memory")) is True
    assert (
        resource_guard.is_cuda_oom_error(RuntimeError("CUBLAS_STATUS_ALLOC_FAILED"))
        is True
    )

    resource_guard.release_cuda_cache()

    assert calls == ["empty"]
