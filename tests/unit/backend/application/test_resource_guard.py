"""Tests for application resource preflight helpers."""

from XBrainLab.backend.application import resource_guard


class _Array:
    def __init__(self, *, nbytes: int, shape: tuple[int, ...]) -> None:
        self.nbytes = nbytes
        self.shape = shape


class _EpochData:
    def __init__(self, *, data: _Array, labels: _Array) -> None:
        self._data = data
        self._labels = labels

    def get_data(self):
        return self._data

    def get_label_list(self):
        return self._labels


class _Dataset:
    def __init__(self, epoch_data: _EpochData) -> None:
        self._epoch_data = epoch_data

    def get_epoch_data(self):
        return self._epoch_data


class _Option:
    bs = 4
    use_cpu = True
    gpu_idx = 0


def test_training_preflight_uses_explicit_dataset_context(monkeypatch):
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 10_000)
    epoch_data = _EpochData(
        data=_Array(nbytes=800, shape=(8, 2, 10)),
        labels=_Array(nbytes=80, shape=(8,)),
    )

    result = resource_guard.check_training_resource_preflight(
        [_Dataset(epoch_data)],
        _Option(),
    )

    assert result.ok
    assert result.diagnostics["dataset_bytes"] == 880
    assert result.diagnostics["estimated_gpu_batch_working_set_bytes"] == 3200


def test_training_preflight_blocks_explicit_context_when_ram_is_too_small(
    monkeypatch,
):
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 100)
    epoch_data = _EpochData(
        data=_Array(nbytes=800, shape=(8, 2, 10)),
        labels=_Array(nbytes=80, shape=(8,)),
    )

    result = resource_guard.check_training_resource_preflight(
        [_Dataset(epoch_data)],
        _Option(),
    )

    assert not result.ok
    assert "Training dataset is too large" in result.message
