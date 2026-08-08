from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.evaluation_render import (
    EvaluationCrossFoldIdentity,
    EvaluationPlanIdentity,
    EvaluationRenderPublisher,
    EvaluationRenderRequest,
    EvaluationRunIdentity,
    EvaluationSummaryIdentity,
    build_evaluation_cross_fold_choices,
)
from XBrainLab.backend.training_state_contract import (
    TrainingReadBoundary,
    TrainingStateToken,
)


def _boundary(generation: int = 7) -> TrainingReadBoundary:
    return TrainingReadBoundary(
        trainer_identity="trainer-evaluation",
        token=TrainingStateToken(generation=generation, stable=True),
    )


class _EpochData:
    def __init__(self) -> None:
        self.label_map = {0: "Left", 1: "Right"}

    @staticmethod
    def get_model_args() -> dict[str, int]:
        return {}


class _Dataset:
    def __init__(
        self,
        *,
        epoch_data: _EpochData | None = None,
        config: Any | None = None,
        test_mask: np.ndarray | None = None,
    ) -> None:
        self.epoch_data = epoch_data or _EpochData()
        self.config = config or SimpleNamespace(is_cross_validation=False)
        self.test_mask = (
            np.asarray(test_mask, dtype=bool)
            if test_mask is not None
            else np.array([True, True])
        )

    def get_epoch_data(self) -> _EpochData:
        return self.epoch_data

    @staticmethod
    def get_training_data() -> tuple[np.ndarray, np.ndarray]:
        return np.zeros((2, 1, 2, 4)), np.array([0, 1])


class _EvalRecord:
    def __init__(
        self,
        labels: np.ndarray,
        outputs: np.ndarray,
        *,
        evaluation_split: str = "test",
    ) -> None:
        self.label = labels
        self.output = outputs
        self.evaluation_split = evaluation_split
        self.metrics = {
            0: {
                "precision": np.float64(1.0),
                "recall": np.float64(0.5),
                "f1-score": np.float64(2 / 3),
                "support": np.int64(1),
            },
            "macro_avg": {
                "precision": np.float64(0.75),
                "recall": np.float64(0.75),
                "f1-score": np.float64(0.75),
                "support": np.int64(2),
            },
        }

    def get_per_class_metrics(self) -> dict[Any, dict[str, Any]]:
        return self.metrics


class _Run:
    def __init__(
        self,
        labels: np.ndarray,
        outputs: np.ndarray,
        *,
        dataset: _Dataset | None = None,
    ) -> None:
        self.dataset = dataset or _Dataset()
        self.eval_record = _EvalRecord(labels, outputs)
        self.evaluation_records = {"test": self.eval_record}

    @staticmethod
    def is_finished() -> bool:
        return True

    @staticmethod
    def get_name() -> str:
        return "Repeat-0"


class _Plan:
    def __init__(
        self,
        runs: list[_Run],
        *,
        dataset: _Dataset | None = None,
    ) -> None:
        self.dataset = dataset or (runs[0].dataset if runs else _Dataset())
        self._runs = runs

    @staticmethod
    def get_name() -> str:
        return "EEGNet"

    def get_plans(self) -> list[_Run]:
        return self._runs


class _Runtime:
    def __init__(self, plans: list[_Plan]) -> None:
        self.plans = plans

    def training_plan_holders(self) -> tuple[Any, ...]:
        return tuple(self.plans)

    def resource_context(self) -> Any:
        raise AssertionError(
            "evaluation rendering must not read resource configuration"
        )

    def is_training(self) -> bool:
        return False

    def current_training_plan_index(self) -> int | None:
        return None


def _publisher(
    runtime: _Runtime,
    *,
    publication_generation: int = 3,
    boundaries: list[TrainingReadBoundary] | None = None,
) -> EvaluationRenderPublisher:
    boundary_values = iter(boundaries or [_boundary(), _boundary()])
    publication = SimpleNamespace(
        generation=publication_generation,
        usable=True,
        training_boundary=_boundary(),
    )
    return EvaluationRenderPublisher(
        training_runtime=runtime,  # type: ignore[arg-type]
        get_publication=lambda: publication,
        capture_training_boundary=lambda: next(boundary_values),
    )


def test_run_publication_is_detached_immutable_and_identity_bound() -> None:
    source_labels = np.array([0, 1])
    source_outputs = np.array([[0.9, 0.1], [0.2, 0.8]])
    run = _Run(source_labels, source_outputs)
    publisher = _publisher(_Runtime([_Plan([run])]))
    run_identity = EvaluationRunIdentity(
        plan=EvaluationPlanIdentity(plan_index=0),
        run_index=0,
    )
    request = EvaluationRenderRequest(
        publication_generation=3,
        selection=run_identity,
    )

    publication = publisher.publish(request)

    assert publication.request == request
    assert publication.generation == 3
    assert publication.training_boundary == _boundary()
    assert publication.data.summary_identity == EvaluationSummaryIdentity(
        plan=run_identity.plan,
        run=run_identity,
    )
    assert publication.data.evaluation_split == "test"
    assert publication.data.class_labels == {0: "Left", 1: "Right"}
    assert publication.data.labels.flags.writeable is False
    assert publication.data.outputs.flags.writeable is False
    assert publication.data.labels is not source_labels
    assert publication.data.outputs is not source_outputs
    assert publication.data.metrics[0]["precision"] == 1.0

    source_labels[0] = 1
    source_outputs[0, 0] = 0.0
    run.eval_record.metrics[0]["precision"] = 0.0
    run.dataset.get_epoch_data().label_map[0] = "Mutated"

    assert publication.data.labels.tolist() == [0, 1]
    assert publication.data.outputs[0, 0] == 0.9
    assert publication.data.metrics[0]["precision"] == 1.0
    assert publication.data.class_labels[0] == "Left"
    with pytest.raises(ValueError):
        publication.data.labels[0] = 1
    with pytest.raises(ValueError):
        publication.data.labels.setflags(write=True)
    with pytest.raises(ValueError):
        publication.data.outputs.setflags(write=True)
    with pytest.raises(TypeError):
        publication.data.metrics[0]["precision"] = 0.0
    with pytest.raises(TypeError):
        publication.data.class_labels[0] = "Changed"
    with pytest.raises(FrozenInstanceError):
        publication.generation = 4


def test_plan_publication_pools_only_finished_evaluation_arrays() -> None:
    first = _Run(np.array([0]), np.array([[0.8, 0.2]]))
    second = _Run(np.array([1]), np.array([[0.1, 0.9]]))
    publisher = _publisher(_Runtime([_Plan([first, second])]))
    plan_identity = EvaluationPlanIdentity(plan_index=0)

    publication = publisher.publish(
        EvaluationRenderRequest(
            publication_generation=3,
            selection=plan_identity,
        )
    )

    assert publication.data.summary_identity == EvaluationSummaryIdentity(
        plan=plan_identity
    )
    assert publication.data.labels.tolist() == [0, 1]
    assert publication.data.outputs.tolist() == [[0.8, 0.2], [0.1, 0.9]]
    assert publication.data.metrics["macro_avg"]["support"] == 2


def test_cross_fold_publication_pools_predictions_and_recomputes_metrics() -> None:
    epoch_data = _EpochData()
    config = SimpleNamespace(is_cross_validation=True)
    first_dataset = _Dataset(
        epoch_data=epoch_data,
        config=config,
        test_mask=np.array([True, True, False]),
    )
    second_dataset = _Dataset(
        epoch_data=epoch_data,
        config=config,
        test_mask=np.array([False, False, True]),
    )
    first_fold = _Plan(
        [
            _Run(
                np.array([0, 1]),
                np.array([[0.8, 0.2], [0.4, 0.6]]),
                dataset=first_dataset,
            )
        ],
        dataset=first_dataset,
    )
    second_fold = _Plan(
        [_Run(np.array([1]), np.array([[0.1, 0.9]]), dataset=second_dataset)],
        dataset=second_dataset,
    )
    plans = [first_fold, second_fold]
    publisher = _publisher(_Runtime(plans))
    choices = build_evaluation_cross_fold_choices(plans)

    assert len(choices) == 1
    assert choices[0].display_name == "All Folds"
    assert choices[0].run_label == "Run 1 (Summary)"
    assert choices[0].sample_count == 3

    publication = publisher.publish(
        EvaluationRenderRequest(
            publication_generation=3,
            selection=choices[0].identity,
        )
    )

    assert publication.data.summary_identity is None
    assert publication.data.labels.tolist() == [0, 1, 1]
    assert publication.data.outputs.tolist() == [
        [0.8, 0.2],
        [0.4, 0.6],
        [0.1, 0.9],
    ]
    assert publication.data.metrics["macro_avg"]["support"] == 3

    publisher = _publisher(_Runtime(plans))
    with pytest.raises(PreconditionError, match="only for saved test predictions"):
        publisher.publish(
            EvaluationRenderRequest(
                publication_generation=3,
                selection=choices[0].identity,
                split="training",
            )
        )


def test_cross_fold_choices_keep_repeats_as_distinct_summaries() -> None:
    epoch_data = _EpochData()
    config = SimpleNamespace(is_cross_validation=True)
    first_dataset = _Dataset(
        epoch_data=epoch_data,
        config=config,
        test_mask=np.array([True, False]),
    )
    second_dataset = _Dataset(
        epoch_data=epoch_data,
        config=config,
        test_mask=np.array([False, True]),
    )
    plans = [
        _Plan(
            [
                _Run(
                    np.array([0]),
                    np.array([[0.8, 0.2]]),
                    dataset=first_dataset,
                ),
                _Run(
                    np.array([0]),
                    np.array([[0.7, 0.3]]),
                    dataset=first_dataset,
                ),
            ],
            dataset=first_dataset,
        ),
        _Plan(
            [
                _Run(
                    np.array([1]),
                    np.array([[0.1, 0.9]]),
                    dataset=second_dataset,
                ),
                _Run(
                    np.array([1]),
                    np.array([[0.2, 0.8]]),
                    dataset=second_dataset,
                ),
            ],
            dataset=second_dataset,
        ),
    ]

    choices = build_evaluation_cross_fold_choices(plans)

    assert [choice.identity.run_index for choice in choices] == [0, 1]
    assert [choice.run_label for choice in choices] == [
        "Run 1 (Summary)",
        "Run 2 (Summary)",
    ]


def test_cross_fold_publication_requires_the_split_in_every_finished_run() -> None:
    epoch_data = _EpochData()
    config = SimpleNamespace(is_cross_validation=True)
    first_dataset = _Dataset(
        epoch_data=epoch_data,
        config=config,
        test_mask=np.array([True, False]),
    )
    second_dataset = _Dataset(
        epoch_data=epoch_data,
        config=config,
        test_mask=np.array([False, True]),
    )
    first = _Run(np.array([0]), np.array([[0.8, 0.2]]), dataset=first_dataset)
    second = _Run(np.array([1]), np.array([[0.1, 0.9]]), dataset=second_dataset)
    second.evaluation_records = {}
    second.eval_record = None
    plans = [
        _Plan([first], dataset=first_dataset),
        _Plan([second], dataset=second_dataset),
    ]
    publisher = _publisher(_Runtime(plans))
    identity = EvaluationCrossFoldIdentity(
        members=(
            EvaluationRunIdentity(EvaluationPlanIdentity(0), 0),
            EvaluationRunIdentity(EvaluationPlanIdentity(1), 0),
        )
    )

    assert build_evaluation_cross_fold_choices(plans) == ()
    with pytest.raises(PreconditionError, match="no longer available"):
        publisher.publish(
            EvaluationRenderRequest(
                publication_generation=3,
                selection=identity,
            )
        )


def test_cross_fold_choices_reject_overlapping_test_masks() -> None:
    epoch_data = _EpochData()
    config = SimpleNamespace(is_cross_validation=True)
    first_dataset = _Dataset(
        epoch_data=epoch_data,
        config=config,
        test_mask=np.array([True, False]),
    )
    second_dataset = _Dataset(
        epoch_data=epoch_data,
        config=config,
        test_mask=np.array([True, False]),
    )
    plans = [
        _Plan(
            [_Run(np.array([0]), np.array([[0.8, 0.2]]), dataset=first_dataset)],
            dataset=first_dataset,
        ),
        _Plan(
            [_Run(np.array([1]), np.array([[0.1, 0.9]]), dataset=second_dataset)],
            dataset=second_dataset,
        ),
    ]

    assert build_evaluation_cross_fold_choices(plans) == ()


def test_cross_fold_identity_requires_one_run_across_distinct_ordered_folds() -> None:
    plan_zero = EvaluationPlanIdentity(0)
    plan_one = EvaluationPlanIdentity(1)

    with pytest.raises(ValueError, match="unique folds"):
        EvaluationCrossFoldIdentity(
            members=(
                EvaluationRunIdentity(plan_zero, 0),
                EvaluationRunIdentity(plan_zero, 0),
            )
        )
    with pytest.raises(ValueError, match="same run index"):
        EvaluationCrossFoldIdentity(
            members=(
                EvaluationRunIdentity(plan_zero, 0),
                EvaluationRunIdentity(plan_one, 1),
            )
        )
    with pytest.raises(ValueError, match="canonical fold order"):
        EvaluationCrossFoldIdentity(
            members=(
                EvaluationRunIdentity(plan_one, 0),
                EvaluationRunIdentity(plan_zero, 0),
            )
        )


def test_run_publication_selects_the_requested_saved_split() -> None:
    run = _Run(np.array([0]), np.array([[0.9, 0.1]]))
    run.evaluation_records["training"] = _EvalRecord(
        np.array([1, 1]),
        np.array([[0.1, 0.9], [0.2, 0.8]]),
        evaluation_split="training",
    )
    publisher = _publisher(_Runtime([_Plan([run])]))
    identity = EvaluationRunIdentity(
        plan=EvaluationPlanIdentity(plan_index=0),
        run_index=0,
    )

    publication = publisher.publish(
        EvaluationRenderRequest(
            publication_generation=3,
            selection=identity,
            split="training",
        )
    )

    assert publication.data.evaluation_split == "training"
    assert publication.data.labels.tolist() == [1, 1]
    assert publication.data.outputs.tolist() == [[0.1, 0.9], [0.2, 0.8]]


def test_plan_publication_never_mixes_splits_when_aggregating() -> None:
    first = _Run(np.array([0]), np.array([[0.8, 0.2]]))
    second = _Run(np.array([1]), np.array([[0.1, 0.9]]))
    first.evaluation_records["validation"] = _EvalRecord(
        np.array([0]),
        np.array([[0.7, 0.3]]),
        evaluation_split="validation",
    )
    publisher = _publisher(_Runtime([_Plan([first, second])]))

    with pytest.raises(PreconditionError) as raised:
        publisher.publish(
            EvaluationRenderRequest(
                publication_generation=3,
                selection=EvaluationPlanIdentity(plan_index=0),
                split="validation",
            )
        )

    assert raised.value.diagnostics["evaluation_split_unavailable"] is True
    assert raised.value.diagnostics["retryable"] is False


@pytest.mark.parametrize("evaluation_split", ["training", "unknown", ""])
def test_render_rejects_metrics_without_held_out_provenance(
    evaluation_split: str,
) -> None:
    run = _Run(np.array([0]), np.array([[1.0, 0.0]]))
    run.eval_record.evaluation_split = evaluation_split
    publisher = _publisher(_Runtime([_Plan([run])]))

    with pytest.raises(PreconditionError) as raised:
        publisher.publish(
            EvaluationRenderRequest(
                publication_generation=3,
                selection=EvaluationRunIdentity(
                    plan=EvaluationPlanIdentity(plan_index=0),
                    run_index=0,
                ),
            )
        )

    assert raised.value.diagnostics == {
        "evaluation_split_unavailable": True,
        "retryable": False,
    }


@pytest.mark.parametrize(
    "render_request",
    [
        EvaluationRenderRequest(
            publication_generation=3,
            selection=EvaluationPlanIdentity(plan_index=4),
        ),
        EvaluationRenderRequest(
            publication_generation=3,
            selection=EvaluationRunIdentity(
                plan=EvaluationPlanIdentity(plan_index=0),
                run_index=9,
            ),
        ),
    ],
)
def test_invalid_render_identity_fails_closed(
    render_request: EvaluationRenderRequest,
) -> None:
    publisher = _publisher(
        _Runtime(
            [
                _Plan(
                    [_Run(np.array([0]), np.array([[1.0, 0.0]]))],
                )
            ]
        )
    )

    with pytest.raises(PreconditionError) as exc_info:
        publisher.publish(render_request)

    assert exc_info.value.diagnostics["evaluation_render_stale"] is True
    assert exc_info.value.diagnostics["retryable"] is True


def test_stale_publication_generation_fails_before_domain_read() -> None:
    runtime = _Runtime([_Plan([_Run(np.array([0]), np.array([[1.0, 0.0]]))])])
    publisher = _publisher(runtime, publication_generation=4)

    with pytest.raises(PreconditionError) as exc_info:
        publisher.publish(
            EvaluationRenderRequest(
                publication_generation=3,
                selection=EvaluationPlanIdentity(plan_index=0),
            )
        )

    assert exc_info.value.diagnostics["evaluation_render_stale"] is True
    assert exc_info.value.diagnostics["publication_generation_after"] == 4


def test_training_boundary_change_discards_copied_render_data() -> None:
    runtime = _Runtime([_Plan([_Run(np.array([0]), np.array([[1.0, 0.0]]))])])
    publisher = _publisher(
        runtime,
        boundaries=[_boundary(), _boundary(generation=8)],
    )

    with pytest.raises(PreconditionError) as exc_info:
        publisher.publish(
            EvaluationRenderRequest(
                publication_generation=3,
                selection=EvaluationPlanIdentity(plan_index=0),
            )
        )

    assert exc_info.value.diagnostics["evaluation_render_stale"] is True
    assert exc_info.value.diagnostics["training_state_changed"] is True


def test_summary_identity_rejects_a_run_from_another_plan() -> None:
    first = EvaluationPlanIdentity(plan_index=0)
    second = EvaluationPlanIdentity(plan_index=1)

    with pytest.raises(ValueError, match="same plan"):
        EvaluationSummaryIdentity(
            plan=first,
            run=EvaluationRunIdentity(plan=second, run_index=0),
        )
