from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from XBrainLab.backend.application.saliency_render import (
    SaliencyCrossFoldIdentity,
    SaliencyPlanIdentity,
    SaliencyRenderPublisher,
    SaliencyRenderRequest,
    SaliencyRunIdentity,
    _normalize_saliency_store,
    build_saliency_cross_fold_choices,
)
from XBrainLab.backend.training_state_contract import TrainingReadBoundary


class _EpochData:
    def __init__(self) -> None:
        self.label_map = {769: "Left", 770: "Right"}
        self.event_id = {"Left": 769, "Right": 770}
        self.tmin = -0.2

    def get_channel_names(self) -> list[str]:
        return ["C3", "C4"]

    def get_montage_position(self) -> list[tuple[float, float, float]]:
        return [(-0.04, 0.0, 0.08), (0.04, 0.0, 0.08)]

    def get_model_args(self) -> dict[str, float]:
        return {"sfreq": 128.0}


class _Record:
    def __init__(
        self,
        values: tuple[np.ndarray, np.ndarray],
        *,
        split: str = "test",
        labels: tuple[int, ...] = (0, 1),
    ) -> None:
        self.evaluation_split = split
        self.label = np.asarray(labels)
        self.output = np.ones((len(labels), 2), dtype=np.float32)
        self.gradient = {0: values[0], 1: values[1]}
        self.gradient_input = {}
        self.smoothgrad = {}
        self.smoothgrad_sq = {}
        self.vargrad = {}
        self._expected_producer: object | None = None

    def validate_saliency_context(
        self,
        _epoch_data: object,
        *,
        producer_identity: object,
    ) -> object:
        assert producer_identity == self._expected_producer
        return SimpleNamespace(
            class_map=((769, "Left"), (770, "Right")),
            channel_names=("C3", "C4"),
            sampling_frequency_hz=128.0,
            epoch_start_seconds=-0.2,
            epoch_end_seconds=0.8,
            epoch_sample_count=3,
            montage_fingerprint="montage",
            epoch_data_fingerprint="epoch-data",
        )


class _Run:
    def __init__(self, record: _Record, *, repeat: int = 0) -> None:
        self.record = record
        self.repeat = repeat
        self.eval_record = record
        self.evaluation_records = {record.evaluation_split: record}
        self.dataset: object | None = None

    def get_saliency_eval_record(self) -> _Record:
        return self.record

    def is_finished(self) -> bool:
        return True


class _Holder:
    def __init__(
        self,
        epoch_data: _EpochData,
        config: object,
        run: _Run,
        *,
        plan_index: int,
        test_mask: tuple[bool, ...],
    ) -> None:
        self.dataset = SimpleNamespace(
            epoch_data=epoch_data,
            config=config,
            get_epoch_data=lambda: epoch_data,
            test_mask=np.asarray(test_mask),
        )
        self._run = run
        run.dataset = self.dataset
        self._plan_index = plan_index

    def get_plans(self) -> list[_Run]:
        return [self._run]

    def get_dataset(self) -> object:
        return self.dataset

    def build_saliency_producer_identity(
        self,
        run: _Run,
        *,
        evaluation_split: str,
    ) -> tuple[int, int, str]:
        producer = (self._plan_index, run.repeat, evaluation_split)
        run.record._expected_producer = producer
        return producer


def _fold_holders(
    *,
    second_split: str = "test",
    second_repeat: int = 0,
) -> tuple[_Holder, _Holder]:
    epoch_data = _EpochData()
    config = SimpleNamespace(is_cross_validation=True)
    first = _Record(
        (
            np.array([[[1.0, 1.0, 1.0]], [[3.0, 3.0, 3.0]]]),
            np.array([[[4.0, 4.0, 4.0]]]),
        ),
        labels=(0, 0, 1),
    )
    second = _Record(
        (
            np.array([[[10.0, 10.0, 10.0]]]),
            np.array([[[20.0, 20.0, 20.0]]]),
        ),
        split=second_split,
        labels=(0, 1),
    )
    return (
        _Holder(
            epoch_data,
            config,
            _Run(first),
            plan_index=0,
            test_mask=(True, True, True, False, False),
        ),
        _Holder(
            epoch_data,
            config,
            _Run(second, repeat=second_repeat),
            plan_index=1,
            test_mask=(False, False, False, True, True),
        ),
    )


def test_cross_fold_choices_require_matching_verified_runs_and_split() -> None:
    choices = build_saliency_cross_fold_choices(_fold_holders())

    assert len(choices) == 1
    choice = choices[0]
    assert choice.display_name == "All Folds"
    assert choice.run_label == "Run 1 (Summary)"
    assert choice.source_split == "test"
    assert choice.methods == ("Gradient",)
    assert [item.display_name for item in choice.classes] == ["Left", "Right"]

    assert (
        build_saliency_cross_fold_choices(_fold_holders(second_split="validation"))
        == ()
    )
    assert build_saliency_cross_fold_choices(_fold_holders(second_repeat=1)) == ()


def test_cross_fold_render_pools_out_of_fold_epochs_and_normalizes_shared() -> None:
    holders = _fold_holders()
    choice = build_saliency_cross_fold_choices(holders)[0]
    boundary = TrainingReadBoundary.no_trainer()
    publication = SimpleNamespace(
        generation=4,
        usable=True,
        training_boundary=boundary,
    )
    runtime = SimpleNamespace(
        has_trainer=lambda: True,
        training_plan_holders=lambda: holders,
    )
    publisher = SaliencyRenderPublisher(
        training_runtime=runtime,
        get_publication=lambda: publication,
        capture_training_boundary=lambda: boundary,
    )

    request = SaliencyRenderRequest(
        publication_generation=4,
        run=choice.identity,
        method="Gradient",
    )
    render = publisher.publish(request)

    left = render.data.saliency_by_class[0]
    assert left.shape == (3, 1, 3)
    np.testing.assert_allclose(left[:, 0, 0], [1.0, 3.0, 10.0])
    assert float(left.mean()) == pytest.approx(14.0 / 3.0)
    assert render.data.aggregation == "pooled out-of-fold epochs"
    assert render.data.fold_count == 2
    assert render.data.source_split == "test"

    normalized = publisher.publish(
        SaliencyRenderRequest(
            publication_generation=4,
            run=choice.identity,
            method="Gradient",
            normalize=True,
        )
    )
    np.testing.assert_allclose(
        normalized.data.saliency_by_class[0][:, 0, 0],
        [0.05, 0.15, 0.5],
    )
    np.testing.assert_allclose(
        normalized.data.saliency_by_class[1][:, 0, 0],
        [0.2, 1.0],
    )
    assert normalized.data.normalized is True
    assert float(holders[1]._run.record.gradient[1].max()) == 20.0


def test_cross_fold_request_identity_requires_canonical_distinct_folds() -> None:
    identity = SaliencyCrossFoldIdentity(
        members=(
            SaliencyRunIdentity(SaliencyPlanIdentity(0), 0),
            SaliencyRunIdentity(SaliencyPlanIdentity(1), 0),
        )
    )

    assert identity.run_index == 0
    assert identity.to_dict() == {
        "members": [
            {"plan_index": 0, "run_index": 0},
            {"plan_index": 1, "run_index": 0},
        ]
    }


def test_normalize_saliency_store_keeps_all_zero_values_finite() -> None:
    source = {0: np.zeros((2, 3, 4), dtype=np.float32)}

    normalized = _normalize_saliency_store(source)

    assert normalized[0] is not source[0]
    assert np.isfinite(normalized[0]).all()
    np.testing.assert_array_equal(normalized[0], source[0])
