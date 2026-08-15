from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import cast

import numpy as np
import pytest

from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.saliency_render import (
    SaliencyCrossFoldIdentity,
    SaliencyPlanIdentity,
    SaliencyRenderData,
    SaliencyRenderPublication,
    SaliencyRenderPublisher,
    SaliencyRenderRequest,
    SaliencyRunIdentity,
    _normalize_saliency_store,
    build_saliency_cross_fold_choices,
    normalized_saliency_render_publication,
)
from XBrainLab.backend.application.training_runtime import TrainingRuntimePort
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
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


class _EpochDataWithPartialBidsGeometry(_EpochData):
    def get_channel_names(self) -> list[str]:
        return ["C3", "C4", "Cz", "EOG"]

    def get_montage_position(self) -> list[tuple[float, float, float]]:
        return []


class _EpochDataWithManualGeometry(_EpochData):
    def __init__(
        self,
        positions: tuple[tuple[float, float, float], ...],
    ) -> None:
        super().__init__()
        self._positions = positions

    def get_channel_names(self) -> list[str]:
        return ["C3", "C4", "Cz", "Pz"]

    def get_montage_position(self) -> list[tuple[float, float, float]]:
        return list(self._positions)


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
        self.validation_calls = 0

    def validate_saliency_context(
        self,
        _epoch_data: object,
        *,
        producer_identity: object,
    ) -> object:
        self.validation_calls += 1
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
        cross_validation_cohort_id: str = "cohort-1",
        training_round_id: str | None = None,
    ) -> None:
        self.dataset = SimpleNamespace(
            epoch_data=epoch_data,
            config=config,
            cross_validation_cohort_id=cross_validation_cohort_id,
            get_epoch_data=lambda: epoch_data,
            test_mask=np.asarray(test_mask),
        )
        self._run = run
        run.dataset = self.dataset
        self._plan_index = plan_index
        if training_round_id is not None:
            self.training_round_id = training_round_id

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


def _manual_geometry_publisher(
    positions: tuple[tuple[float, float, float], ...],
) -> tuple[SaliencyRenderPublisher, SaliencyRunIdentity]:
    epoch_data = _EpochDataWithManualGeometry(positions)
    record = _Record(
        (
            np.ones((1, 4, 4), dtype=np.float32),
            np.full((1, 4, 4), 2.0, dtype=np.float32),
        )
    )
    holder = _Holder(
        epoch_data,
        SimpleNamespace(is_cross_validation=False),
        _Run(record),
        plan_index=0,
        test_mask=(True,),
    )
    boundary = TrainingReadBoundary.no_trainer()
    publication = cast(
        ApplicationViewPublication,
        SimpleNamespace(
            generation=4,
            usable=True,
            training_boundary=boundary,
        ),
    )
    publisher = SaliencyRenderPublisher(
        training_runtime=cast(
            TrainingRuntimePort,
            SimpleNamespace(
                has_trainer=lambda: True,
                training_plan_holders=lambda: (holder,),
            ),
        ),
        get_publication=lambda: publication,
        capture_training_boundary=lambda: boundary,
    )
    return publisher, SaliencyRunIdentity(SaliencyPlanIdentity(0), 0)


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


def test_cross_fold_saliency_keeps_appended_training_rounds_separate() -> None:
    first_round = _fold_holders()
    for holder in first_round:
        holder.training_round_id = "training-round-1"

    second_round = _fold_holders()
    for second, first in zip(second_round, first_round, strict=True):
        second.dataset.epoch_data = first.dataset.epoch_data
        second.dataset.config = first.dataset.config
        second.dataset.cross_validation_cohort_id = (
            first.dataset.cross_validation_cohort_id
        )
        second.training_round_id = "training-round-2"

    choices = build_saliency_cross_fold_choices((*first_round, *second_round))

    assert [choice.display_name for choice in choices] == [
        "Fold Set 1",
        "Fold Set 2",
    ]
    assert [
        tuple(member.plan.plan_index for member in choice.identity.members)
        for choice in choices
    ] == [(0, 1), (2, 3)]


def test_bids_geometry_subsets_only_position_dependent_render_views() -> None:
    epoch_data = _EpochDataWithPartialBidsGeometry()
    record = _Record(
        (
            np.ones((1, 4, 4), dtype=np.float32),
            np.full((1, 4, 4), 2.0, dtype=np.float32),
        )
    )
    holder = _Holder(
        epoch_data,
        SimpleNamespace(is_cross_validation=False),
        _Run(record),
        plan_index=0,
        test_mask=(True,),
    )
    boundary = TrainingReadBoundary.no_trainer()
    publication = cast(
        ApplicationViewPublication,
        SimpleNamespace(
            generation=4,
            usable=True,
            training_boundary=boundary,
        ),
    )
    publisher = SaliencyRenderPublisher(
        training_runtime=cast(
            TrainingRuntimePort,
            SimpleNamespace(
                has_trainer=lambda: True,
                training_plan_holders=lambda: (holder,),
            ),
        ),
        get_publication=lambda: publication,
        capture_training_boundary=lambda: boundary,
        effective_montage_provider=lambda: SimpleNamespace(
            source="bids",
            channel_names=("C3", "C4", "Cz"),
            positions_m=(
                (-0.04, 0.0, 0.08),
                (0.04, 0.0, 0.08),
                (0.0, 0.04, 0.09),
            ),
            supports_topographic=True,
            supports_three_dimensional=False,
        ),
    )
    identity = SaliencyRunIdentity(SaliencyPlanIdentity(0), 0)

    map_render = publisher.publish(
        SaliencyRenderRequest(
            publication_generation=4,
            run=identity,
            method="Gradient",
            view="channel_time",
        )
    )
    topographic_render = publisher.publish(
        SaliencyRenderRequest(
            publication_generation=4,
            run=identity,
            method="Gradient",
            view="topographic_map",
        )
    )

    assert map_render.data.channel_names == ("C3", "C4", "Cz", "EOG")
    assert map_render.data.channel_positions == ()
    assert map_render.data.saliency_by_class[0].shape == (1, 4, 4)
    assert topographic_render.data.channel_names == ("C3", "C4", "Cz")
    assert topographic_render.data.channel_positions == (
        (-0.04, 0.0, 0.08),
        (0.04, 0.0, 0.08),
        (0.0, 0.04, 0.09),
    )
    assert topographic_render.data.saliency_by_class[0].shape == (1, 3, 4)


@pytest.mark.parametrize(
    "positions",
    [
        (
            (-0.04, -0.04, 0.0),
            (0.04, -0.04, 0.0),
            (-0.04, 0.04, 0.0),
            (0.04, 0.04, 0.0),
        ),
        (
            (-0.04, 0.0, 0.0),
            (-0.01, 0.0, 0.0),
            (0.01, 0.0, 0.0),
            (0.04, 0.0, 0.0),
        ),
    ],
    ids=("planar", "degenerate"),
)
def test_direct_render_query_blocks_non_3d_manual_geometry(
    positions: tuple[tuple[float, float, float], ...],
) -> None:
    publisher, identity = _manual_geometry_publisher(positions)

    with pytest.raises(PreconditionError) as exc_info:
        publisher.publish(
            SaliencyRenderRequest(
                publication_generation=4,
                run=identity,
                method="Gradient",
                view="three_dimensional",
            )
        )

    assert str(exc_info.value) == (
        "The selected visualization requires compatible electrode positions."
    )
    assert exc_info.value.diagnostics == {
        "retryable": True,
        "view": "three_dimensional",
    }


def test_direct_render_query_allows_valid_2d_manual_geometry() -> None:
    positions = (
        (-0.04, -0.04, 0.0),
        (0.04, -0.04, 0.0),
        (-0.04, 0.04, 0.0),
        (0.04, 0.04, 0.0),
    )
    publisher, identity = _manual_geometry_publisher(positions)

    render = publisher.publish(
        SaliencyRenderRequest(
            publication_generation=4,
            run=identity,
            method="Gradient",
            view="topographic_map",
        )
    )

    assert render.data.channel_positions == positions


def test_direct_render_query_allows_true_3d_manual_geometry() -> None:
    positions = (
        (0.0, 0.0, 0.0),
        (0.04, 0.0, 0.0),
        (0.0, 0.04, 0.0),
        (0.0, 0.0, 0.04),
    )
    publisher, identity = _manual_geometry_publisher(positions)

    render = publisher.publish(
        SaliencyRenderRequest(
            publication_generation=4,
            run=identity,
            method="Gradient",
            view="three_dimensional",
        )
    )

    assert render.data.channel_positions == positions


def test_cross_fold_choices_reject_distinct_subject_cohorts() -> None:
    first, second = _fold_holders()
    first.dataset.cross_validation_cohort_id = "subject-1"
    second.dataset.cross_validation_cohort_id = "subject-2"

    assert build_saliency_cross_fold_choices((first, second)) == ()


def test_cross_fold_render_pools_out_of_fold_epochs_and_normalizes_shared() -> None:
    holders = _fold_holders()
    choice = build_saliency_cross_fold_choices(holders)[0]
    boundary = TrainingReadBoundary.no_trainer()
    publication = cast(
        ApplicationViewPublication,
        SimpleNamespace(
            generation=4,
            usable=True,
            training_boundary=boundary,
        ),
    )
    runtime = cast(
        TrainingRuntimePort,
        SimpleNamespace(
            has_trainer=lambda: True,
            training_plan_holders=lambda: holders,
        ),
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
    assert {values.dtype for values in normalized.data.saliency_by_class.values()} == {
        np.dtype(np.float64)
    }
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


def test_cross_fold_render_validates_each_selected_fold_once() -> None:
    holders = _fold_holders()
    choice = build_saliency_cross_fold_choices(holders)[0]
    for holder in holders:
        holder._run.record.validation_calls = 0
    boundary = TrainingReadBoundary.no_trainer()
    publication = cast(
        ApplicationViewPublication,
        SimpleNamespace(
            generation=4,
            usable=True,
            training_boundary=boundary,
        ),
    )
    publisher = SaliencyRenderPublisher(
        training_runtime=cast(
            TrainingRuntimePort,
            SimpleNamespace(
                has_trainer=lambda: True,
                training_plan_holders=lambda: holders,
            ),
        ),
        get_publication=lambda: publication,
        capture_training_boundary=lambda: boundary,
    )

    publisher.publish(
        SaliencyRenderRequest(
            publication_generation=4,
            run=choice.identity,
            method="Gradient",
        )
    )

    assert [holder._run.record.validation_calls for holder in holders] == [1, 1]


def test_cross_fold_render_does_not_recopy_owned_pooled_arrays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    holders = _fold_holders()
    choice = build_saliency_cross_fold_choices(holders)[0]
    boundary = TrainingReadBoundary.no_trainer()
    publication = cast(
        ApplicationViewPublication,
        SimpleNamespace(
            generation=4,
            usable=True,
            training_boundary=boundary,
        ),
    )
    publisher = SaliencyRenderPublisher(
        training_runtime=cast(
            TrainingRuntimePort,
            SimpleNamespace(
                has_trainer=lambda: True,
                training_plan_holders=lambda: holders,
            ),
        ),
        get_publication=lambda: publication,
        capture_training_boundary=lambda: boundary,
    )
    copy_calls = 0

    def _count_copy(value: object) -> np.ndarray:
        nonlocal copy_calls
        copy_calls += 1
        copied = np.array(value, copy=True)
        copied.setflags(write=False)
        return copied

    monkeypatch.setattr(
        "XBrainLab.backend.application.saliency_render._copy_array_readonly",
        _count_copy,
    )

    render = publisher.publish(
        SaliencyRenderRequest(
            publication_generation=4,
            run=choice.identity,
            method="Gradient",
        )
    )

    assert copy_calls == 0
    assert all(
        values.flags.owndata and not values.flags.writeable
        for values in render.data.saliency_by_class.values()
    )


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
    source: dict[object, np.ndarray] = {0: np.zeros((2, 3, 4), dtype=np.float32)}

    normalized = _normalize_saliency_store(source)

    assert normalized[0] is not source[0]
    assert np.isfinite(normalized[0]).all()
    np.testing.assert_array_equal(normalized[0], source[0])


def test_normalize_saliency_store_preserves_float32_storage() -> None:
    source: dict[object, np.ndarray] = {
        0: np.array([[[-2.0, 1.0]]], dtype=np.float32),
        1: np.array([[[4.0, -1.0]]], dtype=np.float32),
    }

    normalized = _normalize_saliency_store(source)

    assert {values.dtype for values in normalized.values()} == {np.dtype(np.float32)}
    np.testing.assert_allclose(normalized[0], [[[-0.5, 0.25]]])
    np.testing.assert_allclose(normalized[1], [[[1.0, -0.25]]])


def test_normalized_render_publication_preserves_source_and_global_scale() -> None:
    request = SaliencyRenderRequest(
        publication_generation=4,
        run=SaliencyRunIdentity(SaliencyPlanIdentity(0), 0),
        method="Gradient",
    )
    source = SaliencyRenderPublication(
        request=request,
        generation=4,
        training_generation=9,
        data=SaliencyRenderData(
            method="Gradient",
            saliency_by_class={
                0: np.array([[[-2.0, 1.0]]], dtype=np.float32),
                1: np.array([[[4.0, -1.0]]], dtype=np.float32),
            },
            class_map=((769, "Left"), (770, "Right")),
            event_ids={"Left": 769, "Right": 770},
            channel_names=("C3",),
            channel_positions=((-0.04, 0.0, 0.08),),
            sfreq=128.0,
            tmin=-0.2,
            source_split="test",
            aggregation="per-epoch",
            fold_count=1,
        ),
    )

    normalized = normalized_saliency_render_publication(source)

    assert normalized.request == replace(request, normalize=True)
    assert normalized.generation == source.generation
    assert normalized.training_generation == source.training_generation
    assert normalized.data.normalized is True
    assert normalized.data.source_split == source.data.source_split
    assert normalized.data.aggregation == source.data.aggregation
    np.testing.assert_allclose(
        normalized.data.saliency_by_class[0],
        [[[-0.5, 0.25]]],
    )
    np.testing.assert_allclose(
        normalized.data.saliency_by_class[1],
        [[[1.0, -0.25]]],
    )
    np.testing.assert_array_equal(
        source.data.saliency_by_class[0],
        [[[-2.0, 1.0]]],
    )
