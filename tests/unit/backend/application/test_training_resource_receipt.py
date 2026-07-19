"""Bounded freshness tests for training resource admission receipts."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from XBrainLab.backend.application import training_resource_receipt as receipt_module
from XBrainLab.backend.application.commands import TrainCommand
from XBrainLab.backend.application.resource_guard import (
    ResourceConfirmationRequiredError,
    ResourcePreflightResult,
)


class _ExplodingBytesArray:
    """Virtual array that proves admission never materializes all bytes."""

    def __init__(
        self,
        *,
        size: int = 1_000_000_000,
        dtype: str = "int64",
    ) -> None:
        self.shape = (size,)
        self.size = size
        self.dtype = dtype
        self.nbytes = size * 8
        self.flat = self
        self.sample_reads = 0
        self.tobytes_calls = 0
        self._overrides: dict[int, Any] = {}
        self._resource_fingerprint_revision = 0

    def __getitem__(self, index: int) -> Any:
        self.sample_reads += 1
        return self._overrides.get(index, index % 7)

    def tobytes(self) -> bytes:
        self.tobytes_calls += 1
        raise AssertionError("training admission must not materialize array bytes")

    def mutate(self, index: int, value: Any, *, tracked: bool = False) -> None:
        self._overrides[index] = value
        if tracked:
            self._resource_fingerprint_revision += 1


class _EpochData:
    def __init__(self) -> None:
        self.data = _ExplodingBytesArray(dtype="float32")
        self.labels = _ExplodingBytesArray(dtype="int64")

    def get_data(self) -> _ExplodingBytesArray:
        return self.data

    def get_label_list(self) -> _ExplodingBytesArray:
        return self.labels


class _Dataset:
    def __init__(self) -> None:
        self.dataset_id = 7
        self.name = "dataset-7"
        self.is_selected = True
        self.epoch_data = _EpochData()
        self.train_mask = _ExplodingBytesArray(dtype="bool")
        self.val_mask = _ExplodingBytesArray(dtype="bool")
        self.test_mask = _ExplodingBytesArray(dtype="bool")
        self._resource_fingerprint_revision = 0

    def get_epoch_data(self) -> _EpochData:
        return self.epoch_data

    def get_name(self) -> str:
        return self.name


def _context() -> tuple[dict[str, Any], _Dataset]:
    dataset = _Dataset()
    return (
        {
            "datasets": [dataset],
            "training_option": SimpleNamespace(
                use_cpu=True,
                bs=8,
                epoch=2,
                lr=0.001,
                repeat_num=1,
                optim_params={},
                checkpoint_epoch=0,
                output_dir="./output",
                evaluation_option="last_epoch",
                get_device=lambda: "cpu",
                get_optim_name=lambda: "Adam",
            ),
            "model_holder": SimpleNamespace(
                target_model=type("EEGNet", (), {}),
                model_params_map={"input_size": 256, "num_classes": 2},
                pretrained_weight_path=None,
            ),
        },
        dataset,
    )


def _warning_preflight() -> ResourcePreflightResult:
    return ResourcePreflightResult(
        issues=(),
        warnings=("Training may use most available memory.",),
        diagnostics={"uses_cpu": True},
    )


def _fingerprint(context: dict[str, Any]) -> str:
    annotated = receipt_module.TrainingResourceReceiptAuthority().annotate(
        TrainCommand(),
        context,
        _warning_preflight(),
    )
    return str(annotated.diagnostics["configuration_fingerprint"])


def test_training_fingerprint_never_materializes_array_bytes_and_is_bounded() -> None:
    context, dataset = _context()
    arrays = (
        dataset.epoch_data.data,
        dataset.epoch_data.labels,
        dataset.train_mask,
        dataset.val_mask,
        dataset.test_mask,
    )

    fingerprint = _fingerprint(context)

    assert len(fingerprint) == 64
    assert sum(array.tobytes_calls for array in arrays) == 0
    assert all(
        array.sample_reads <= receipt_module.ARRAY_FINGERPRINT_MAX_SAMPLES
        for array in arrays
    )


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(
            lambda dataset: dataset.epoch_data.labels.mutate(0, 99),
            id="label-content",
        ),
        pytest.param(
            lambda dataset: dataset.train_mask.mutate(0, True),
            id="train-mask-content",
        ),
        pytest.param(
            lambda dataset: dataset.val_mask.mutate(0, True),
            id="validation-mask-content",
        ),
        pytest.param(
            lambda dataset: dataset.test_mask.mutate(0, True),
            id="test-mask-content",
        ),
        pytest.param(
            lambda dataset: setattr(
                dataset.epoch_data.labels,
                "shape",
                (dataset.epoch_data.labels.shape[0] + 1,),
            ),
            id="shape",
        ),
        pytest.param(
            lambda dataset: setattr(
                dataset.epoch_data.labels,
                "dtype",
                "int32",
            ),
            id="dtype",
        ),
        pytest.param(
            lambda dataset: setattr(
                dataset.epoch_data.labels,
                "size",
                dataset.epoch_data.labels.size + 1,
            ),
            id="count",
        ),
        pytest.param(
            lambda dataset: setattr(dataset, "is_selected", False),
            id="dataset-selection",
        ),
    ],
)
def test_training_fingerprint_invalidates_after_training_scope_mutation(
    mutation,
) -> None:
    context, dataset = _context()
    before = _fingerprint(context)

    mutation(dataset)

    assert _fingerprint(context) != before


def test_training_fingerprint_revision_catches_unsampled_tracked_mutation() -> None:
    context, dataset = _context()
    before = _fingerprint(context)

    dataset.train_mask.mutate(123_456_789, True, tracked=True)

    assert _fingerprint(context) != before


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda dataset: dataset.epoch_data.labels.mutate(0, 99),
            id="labels",
        ),
        pytest.param(
            lambda dataset: dataset.train_mask.mutate(0, True),
            id="split-mask",
        ),
        pytest.param(
            lambda dataset: setattr(
                dataset,
                "_resource_fingerprint_revision",
                dataset._resource_fingerprint_revision + 1,
            ),
            id="dataset-revision",
        ),
    ],
)
def test_changed_training_scope_cannot_reuse_warning_receipt(mutate) -> None:
    context, dataset = _context()
    authority = receipt_module.TrainingResourceReceiptAuthority()
    initial = authority.annotate(TrainCommand(), context, _warning_preflight())
    with pytest.raises(ResourceConfirmationRequiredError) as issued:
        authority.authorize(TrainCommand(), initial)
    old_challenge = issued.value.diagnostics["resource_preflight"]

    mutate(dataset)
    confirmed = TrainCommand(
        resource_preflight_confirmed=True,
        resource_preflight_token=old_challenge["confirmation_token"],
    )
    changed = authority.annotate(confirmed, context, _warning_preflight())

    with pytest.raises(ResourceConfirmationRequiredError) as refreshed:
        authority.authorize(confirmed, changed)

    new_challenge = refreshed.value.diagnostics["resource_preflight"]
    assert new_challenge["confirmation_token"] != old_challenge["confirmation_token"]
    assert new_challenge["scope_fingerprint"] != old_challenge["scope_fingerprint"]
