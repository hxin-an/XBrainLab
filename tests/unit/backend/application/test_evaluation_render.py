from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.evaluation_render import (
    EvaluationCrossFoldIdentity,
    EvaluationModelSummary,
    EvaluationPlanIdentity,
    EvaluationRenderData,
    EvaluationRenderPublisher,
    EvaluationRenderRequest,
    EvaluationRunIdentity,
    EvaluationSummaryIdentity,
    build_evaluation_cross_fold_choices,
    build_evaluation_model_summary,
    build_evaluation_model_summary_result,
    build_prepared_evaluation_model_summary,
    prepare_evaluation_model_summary,
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
    def __init__(self, shape: tuple[int, int, int] = (2, 2, 4)) -> None:
        self.label_map = {0: "Left", 1: "Right"}
        self.data = np.zeros(shape, dtype=np.float32)

    @staticmethod
    def get_model_args() -> dict[str, int]:
        return {}

    def get_data(self) -> np.ndarray:
        return self.data


class _Dataset:
    def __init__(
        self,
        *,
        epoch_data: _EpochData | None = None,
        config: Any | None = None,
        test_mask: np.ndarray | None = None,
        cross_validation_cohort_id: str = "cohort-1",
    ) -> None:
        self.epoch_data = epoch_data or _EpochData()
        self.config = config or SimpleNamespace(is_cross_validation=False)
        self.test_mask = (
            np.asarray(test_mask, dtype=bool)
            if test_mask is not None
            else np.array([True, True])
        )
        self.cross_validation_cohort_id = cross_validation_cohort_id

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
        model: Any | None = None,
        repeat: int = 0,
        finished: bool = True,
    ) -> None:
        self.dataset = dataset or _Dataset()
        self.eval_record = _EvalRecord(labels, outputs)
        self.evaluation_records = {"test": self.eval_record}
        self.model = model
        self.repeat = repeat
        self.finished = finished

    def is_finished(self) -> bool:
        return self.finished

    def get_name(self) -> str:
        return f"Repeat-{self.repeat}"


class _Plan:
    def __init__(
        self,
        runs: list[_Run],
        *,
        dataset: _Dataset | None = None,
        training_round_id: str | None = None,
    ) -> None:
        self.dataset = dataset or (runs[0].dataset if runs else _Dataset())
        self._runs = runs
        self.option = SimpleNamespace(bs=32, get_device=lambda: "cpu")
        if training_round_id is not None:
            self.training_round_id = training_round_id

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
    split_specification_fingerprint: str | None = "split-specification-sha256",
    split_epoch_revision: int | None = 11,
) -> EvaluationRenderPublisher:
    boundary_values = iter(boundaries or [_boundary(), _boundary()])
    publication = SimpleNamespace(
        generation=publication_generation,
        usable=True,
        training_boundary=_boundary(),
        state=SimpleNamespace(
            dataset=SimpleNamespace(
                split_specification_fingerprint=split_specification_fingerprint,
                split_epoch_revision=split_epoch_revision,
            )
        ),
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
    plan = _Plan([run])
    publisher = _publisher(_Runtime([plan]))
    run_identity = EvaluationRunIdentity(
        plan=EvaluationPlanIdentity(plan_index=0),
        run_index=0,
    )
    request = EvaluationRenderRequest(
        publication_generation=3,
        selection=run_identity,
        trainer_identity="trainer-evaluation",
        split_specification_fingerprint="split-specification-sha256",
        split_epoch_revision=11,
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
    assert publication.data.output_numeric_summary.to_dict() == {
        "shape": [2, 2],
        "dtype": "float64",
        "count": 4,
        "finite_count": 4,
        "nonfinite_count": 0,
        "minimum": 0.1,
        "maximum": 0.9,
    }
    assert publication.split_specification_fingerprint == ("split-specification-sha256")
    assert publication.split_epoch_revision == 11

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


def test_selected_run_read_survives_unselected_training_update() -> None:
    """A different fold progressing cannot invalidate the chosen result."""
    run = _Run(
        np.array([0, 1]),
        np.array([[0.9, 0.1], [0.2, 0.8]]),
    )
    selected_plan = _Plan([run])
    unselected_plan = _Plan(
        [_Run(np.array([1]), np.array([[0.1, 0.9]]), finished=False)]
    )
    runtime = _Runtime([selected_plan, unselected_plan])
    publication = SimpleNamespace(
        generation=3,
        usable=True,
        training_boundary=_boundary(7),
        state=SimpleNamespace(
            dataset=SimpleNamespace(
                split_specification_fingerprint="split-specification-sha256",
                split_epoch_revision=11,
            )
        ),
    )
    boundaries = iter(
        (
            _boundary(7),
            TrainingReadBoundary(
                trainer_identity="trainer-evaluation",
                token=TrainingStateToken(generation=8, stable=False),
            ),
        )
    )
    publisher = EvaluationRenderPublisher(
        training_runtime=runtime,  # type: ignore[arg-type]
        get_publication=lambda: publication,
        capture_training_boundary=lambda: next(boundaries),
    )
    original = publisher._copy_render_data

    def copy_while_other_fold_progresses(*args, **kwargs):
        value = original(*args, **kwargs)
        publication.generation = 4
        unselected_plan._runs[0].finished = True
        return value

    publisher._copy_render_data = copy_while_other_fold_progresses  # type: ignore[method-assign]

    result = publisher.publish(
        EvaluationRenderRequest(
            publication_generation=3,
            selection=EvaluationRunIdentity(EvaluationPlanIdentity(0), 0),
            trainer_identity="trainer-evaluation",
            split_specification_fingerprint="split-specification-sha256",
            split_epoch_revision=11,
        )
    )

    assert result.data.labels.tolist() == [0, 1]


@pytest.mark.parametrize(
    ("trainer_identity", "fingerprint", "revision"),
    [
        ("replacement-trainer", "split-specification-sha256", 11),
        ("trainer-evaluation", "replacement-split-sha256", 12),
    ],
)
def test_queued_request_with_replaced_origin_fails_before_copy(
    trainer_identity: str,
    fingerprint: str,
    revision: int,
) -> None:
    runtime = _Runtime([_Plan([_Run(np.array([0]), np.array([[1.0, 0.0]]))])])
    publication = SimpleNamespace(
        generation=3,
        usable=True,
        training_boundary=TrainingReadBoundary(
            trainer_identity=trainer_identity,
            token=TrainingStateToken(generation=8, stable=True),
        ),
        state=SimpleNamespace(
            dataset=SimpleNamespace(
                split_specification_fingerprint=fingerprint,
                split_epoch_revision=revision,
            )
        ),
    )
    publisher = EvaluationRenderPublisher(
        training_runtime=runtime,  # type: ignore[arg-type]
        get_publication=lambda: publication,
        capture_training_boundary=lambda: publication.training_boundary,
    )
    copied = False

    def copy_must_not_run(*args: Any, **kwargs: Any) -> Any:
        nonlocal copied
        copied = True
        raise AssertionError("stale origin reached evaluation copy")

    publisher._copy_render_data = copy_must_not_run  # type: ignore[method-assign]

    with pytest.raises(PreconditionError) as exc_info:
        publisher.publish(
            EvaluationRenderRequest(
                publication_generation=3,
                selection=EvaluationPlanIdentity(0),
                trainer_identity="trainer-evaluation",
                split_specification_fingerprint="split-specification-sha256",
                split_epoch_revision=11,
            )
        )

    assert copied is False
    assert exc_info.value.diagnostics["evaluation_render_stale"] is True


def test_selected_target_replacement_during_copy_discards_result() -> None:
    original_run = _Run(np.array([0]), np.array([[1.0, 0.0]]))
    runtime = _Runtime([_Plan([original_run])])
    publisher = _publisher(runtime)
    original_copy = publisher._copy_render_data

    def copy_then_replace_selected_target(*args: Any, **kwargs: Any) -> Any:
        value = original_copy(*args, **kwargs)
        runtime.plans[0] = _Plan([_Run(np.array([1]), np.array([[0.0, 1.0]]))])
        return value

    publisher._copy_render_data = copy_then_replace_selected_target  # type: ignore[method-assign]

    with pytest.raises(PreconditionError) as exc_info:
        publisher.publish(
            EvaluationRenderRequest(
                publication_generation=3,
                selection=EvaluationPlanIdentity(0),
                trainer_identity="trainer-evaluation",
                split_specification_fingerprint="split-specification-sha256",
                split_epoch_revision=11,
            )
        )

    assert exc_info.value.diagnostics["evaluation_render_stale"] is True


def test_selected_target_aba_during_copy_uses_captured_result() -> None:
    original_plan = _Plan([_Run(np.array([0]), np.array([[1.0, 0.0]]))])
    runtime = _Runtime([original_plan])
    publisher = _publisher(runtime)
    original_copy = publisher._copy_render_data

    def copy_while_target_is_temporarily_replaced(*args: Any, **kwargs: Any) -> Any:
        replacement = _Plan([_Run(np.array([1]), np.array([[0.0, 1.0]]))])
        runtime.plans[0] = replacement
        try:
            return original_copy(*args, **kwargs)
        finally:
            runtime.plans[0] = original_plan

    publisher._copy_render_data = copy_while_target_is_temporarily_replaced  # type: ignore[method-assign]

    result = publisher.publish(
        EvaluationRenderRequest(
            publication_generation=3,
            selection=EvaluationPlanIdentity(0),
            trainer_identity="trainer-evaluation",
            split_specification_fingerprint="split-specification-sha256",
            split_epoch_revision=11,
        )
    )

    assert result.data.labels.tolist() == [0]


@pytest.mark.parametrize(
    ("field", "invalid", "error", "message"),
    [
        (
            "labels",
            np.array(["0", "1"]),
            TypeError,
            "labels must contain real numeric",
        ),
        (
            "labels",
            np.array([False, True]),
            TypeError,
            "labels must contain real numeric",
        ),
        (
            "labels",
            np.array([0.0, np.nan]),
            ValueError,
            "labels must contain only finite",
        ),
        (
            "outputs",
            np.array([["0.9", "0.1"], ["0.2", "0.8"]]),
            TypeError,
            "outputs must contain real numeric",
        ),
        (
            "outputs",
            np.array([[True, False], [False, True]]),
            TypeError,
            "outputs must contain real numeric",
        ),
        (
            "outputs",
            np.array([[0.9, np.inf], [0.2, 0.8]]),
            ValueError,
            "outputs must contain only finite",
        ),
        (
            "outputs",
            np.array([[0.9 + 0j, 0.1 + 0j], [0.2 + 0j, 0.8 + 0j]]),
            TypeError,
            "outputs must contain real numeric",
        ),
    ],
)
def test_render_data_rejects_non_numeric_or_nonfinite_arrays(
    field: str,
    invalid: np.ndarray,
    error: type[Exception],
    message: str,
) -> None:
    kwargs = {
        "labels": np.array([0, 1]),
        "outputs": np.array([[0.9, 0.1], [0.2, 0.8]]),
        "metrics": {},
        "class_labels": {0: "Left", 1: "Right"},
        "summary_identity": None,
        "evaluation_split": "test",
    }
    kwargs[field] = invalid

    with pytest.raises(error, match=message):
        EvaluationRenderData(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("labels", "outputs", "class_labels", "message"),
    [
        (
            np.array([0, 1]),
            np.empty((2, 0)),
            {},
            "at least one class",
        ),
        (
            np.array([0, 2]),
            np.array([[0.9, 0.1], [0.2, 0.8]]),
            {0: "Left", 1: "Right"},
            "labels must be within",
        ),
        (
            np.array([-1, 1]),
            np.array([[0.9, 0.1], [0.2, 0.8]]),
            {0: "Left", 1: "Right"},
            "labels must be within",
        ),
        (
            np.array([0.5, 1.0]),
            np.array([[0.9, 0.1], [0.2, 0.8]]),
            {0: "Left", 1: "Right"},
            "labels must be integer class indices",
        ),
        (
            np.array([0, 1]),
            np.array([[0.9, 0.1], [0.2, 0.8]]),
            {0: "Left"},
            "class label mapping must exactly cover",
        ),
        (
            np.array([0, 1]),
            np.array([[0.9, 0.1], [0.2, 0.8]]),
            {0: "Left", 1: "Right", 2: "Unused"},
            "class label mapping must exactly cover",
        ),
        (
            np.array([0, 1]),
            np.array([[0.9, 0.1], [0.2, 0.8]]),
            {0: "Same", 1: "Same"},
            "class label names must be unique",
        ),
    ],
)
def test_render_data_rejects_label_output_and_class_mapping_mismatch(
    labels: np.ndarray,
    outputs: np.ndarray,
    class_labels: dict[int, str],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        EvaluationRenderData(
            labels=labels,
            outputs=outputs,
            metrics={},
            class_labels=class_labels,
            summary_identity=None,
            evaluation_split="test",
        )


@pytest.mark.parametrize("invalid_metric", [np.nan, np.inf, "0.75", True])
def test_publication_rejects_nonfinite_or_nonnumeric_metrics(
    invalid_metric: object,
) -> None:
    run = _Run(
        np.array([0, 1]),
        np.array([[0.9, 0.1], [0.2, 0.8]]),
    )
    run.eval_record.metrics["macro_avg"]["precision"] = invalid_metric
    publisher = _publisher(_Runtime([_Plan([run])]))

    with pytest.raises((TypeError, ValueError), match="metric values"):
        publisher.publish(
            EvaluationRenderRequest(
                publication_generation=3,
                trainer_identity="trainer-evaluation",
                split_specification_fingerprint="split-specification-sha256",
                split_epoch_revision=11,
                selection=EvaluationRunIdentity(
                    plan=EvaluationPlanIdentity(plan_index=0),
                    run_index=0,
                ),
            )
        )


def test_plan_publication_rejects_class_mapping_drift_between_runs() -> None:
    first_dataset = _Dataset()
    second_dataset = _Dataset()
    second_dataset.epoch_data.label_map = {0: "Right", 1: "Left"}
    publisher = _publisher(
        _Runtime(
            [
                _Plan(
                    [
                        _Run(
                            np.array([0]),
                            np.array([[0.9, 0.1]]),
                            dataset=first_dataset,
                        ),
                        _Run(
                            np.array([1]),
                            np.array([[0.2, 0.8]]),
                            dataset=second_dataset,
                        ),
                    ],
                    dataset=first_dataset,
                )
            ]
        )
    )

    with pytest.raises(PreconditionError, match="Class label mappings differ"):
        publisher.publish(
            EvaluationRenderRequest(
                publication_generation=3,
                trainer_identity="trainer-evaluation",
                split_specification_fingerprint="split-specification-sha256",
                split_epoch_revision=11,
                selection=EvaluationPlanIdentity(plan_index=0),
            )
        )


def test_plan_publication_pools_only_finished_evaluation_arrays() -> None:
    first = _Run(np.array([0]), np.array([[0.8, 0.2]]))
    second = _Run(np.array([1]), np.array([[0.1, 0.9]]))
    publisher = _publisher(_Runtime([_Plan([first, second])]))
    plan_identity = EvaluationPlanIdentity(plan_index=0)

    publication = publisher.publish(
        EvaluationRenderRequest(
            publication_generation=3,
            trainer_identity="trainer-evaluation",
            split_specification_fingerprint="split-specification-sha256",
            split_epoch_revision=11,
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
            trainer_identity="trainer-evaluation",
            split_specification_fingerprint="split-specification-sha256",
            split_epoch_revision=11,
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
                trainer_identity="trainer-evaluation",
                split_specification_fingerprint="split-specification-sha256",
                split_epoch_revision=11,
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


def test_cross_fold_choices_keep_appended_training_rounds_separate() -> None:
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

    def round_plans(round_id: str, *, finished: bool) -> list[_Plan]:
        return [
            _Plan(
                [
                    _Run(
                        np.array([label]),
                        np.array([[0.8, 0.2] if label == 0 else [0.1, 0.9]]),
                        dataset=dataset,
                        finished=finished,
                    )
                ],
                dataset=dataset,
                training_round_id=round_id,
            )
            for label, dataset in enumerate((first_dataset, second_dataset))
        ]

    first_round = round_plans("training-round-1", finished=True)
    pending_second_round = round_plans("training-round-2", finished=False)

    while_second_round_is_pending = build_evaluation_cross_fold_choices(
        [*first_round, *pending_second_round]
    )

    assert len(while_second_round_is_pending) == 1
    assert while_second_round_is_pending[0].display_name == "Fold Set 1"
    assert tuple(
        member.plan.plan_index
        for member in while_second_round_is_pending[0].identity.members
    ) == (0, 1)

    completed_second_round = round_plans("training-round-2", finished=True)
    after_second_round_finishes = build_evaluation_cross_fold_choices(
        [*first_round, *completed_second_round]
    )

    assert [choice.display_name for choice in after_second_round_finishes] == [
        "Fold Set 1",
        "Fold Set 2",
    ]
    assert [
        tuple(member.plan.plan_index for member in choice.identity.members)
        for choice in after_second_round_finishes
    ] == [(0, 1), (2, 3)]


def test_cross_fold_choices_do_not_merge_distinct_subject_cohorts() -> None:
    epoch_data = _EpochData()
    config = SimpleNamespace(is_cross_validation=True)
    first_dataset = _Dataset(
        epoch_data=epoch_data,
        config=config,
        test_mask=np.array([True, False]),
        cross_validation_cohort_id="subject-1",
    )
    second_dataset = _Dataset(
        epoch_data=epoch_data,
        config=config,
        test_mask=np.array([False, True]),
        cross_validation_cohort_id="subject-2",
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
                trainer_identity="trainer-evaluation",
                split_specification_fingerprint="split-specification-sha256",
                split_epoch_revision=11,
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
            trainer_identity="trainer-evaluation",
            split_specification_fingerprint="split-specification-sha256",
            split_epoch_revision=11,
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
                trainer_identity="trainer-evaluation",
                split_specification_fingerprint="split-specification-sha256",
                split_epoch_revision=11,
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
                trainer_identity="trainer-evaluation",
                split_specification_fingerprint="split-specification-sha256",
                split_epoch_revision=11,
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
            trainer_identity="trainer-evaluation",
            split_specification_fingerprint="split-specification-sha256",
            split_epoch_revision=11,
            selection=EvaluationPlanIdentity(plan_index=4),
        ),
        EvaluationRenderRequest(
            publication_generation=3,
            trainer_identity="trainer-evaluation",
            split_specification_fingerprint="split-specification-sha256",
            split_epoch_revision=11,
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


def test_global_publication_generation_change_does_not_stale_selected_result() -> None:
    runtime = _Runtime([_Plan([_Run(np.array([0]), np.array([[1.0, 0.0]]))])])
    publisher = _publisher(runtime, publication_generation=4)

    result = publisher.publish(
        EvaluationRenderRequest(
            publication_generation=3,
            trainer_identity="trainer-evaluation",
            split_specification_fingerprint="split-specification-sha256",
            split_epoch_revision=11,
            selection=EvaluationPlanIdentity(plan_index=0),
        )
    )

    assert result.data.labels.tolist() == [0]


def test_global_training_token_change_does_not_stale_selected_result() -> None:
    runtime = _Runtime([_Plan([_Run(np.array([0]), np.array([[1.0, 0.0]]))])])
    publisher = _publisher(
        runtime,
        boundaries=[_boundary(), _boundary(generation=8)],
    )

    result = publisher.publish(
        EvaluationRenderRequest(
            publication_generation=3,
            trainer_identity="trainer-evaluation",
            split_specification_fingerprint="split-specification-sha256",
            split_epoch_revision=11,
            selection=EvaluationPlanIdentity(plan_index=0),
        )
    )

    assert result.data.labels.tolist() == [0]


def test_render_fails_closed_without_backend_split_provenance() -> None:
    runtime = _Runtime([_Plan([_Run(np.array([0]), np.array([[1.0, 0.0]]))])])
    publisher = _publisher(
        runtime,
        split_specification_fingerprint=None,
        split_epoch_revision=None,
    )

    with pytest.raises(PreconditionError, match="split provenance") as exc_info:
        publisher.publish(
            EvaluationRenderRequest(
                publication_generation=3,
                trainer_identity="trainer-evaluation",
                split_specification_fingerprint="split-specification-sha256",
                split_epoch_revision=11,
                selection=EvaluationPlanIdentity(plan_index=0),
            )
        )

    assert exc_info.value.diagnostics["evaluation_render_stale"] is True


def test_summary_identity_rejects_a_run_from_another_plan() -> None:
    first = EvaluationPlanIdentity(plan_index=0)
    second = EvaluationPlanIdentity(plan_index=1)

    with pytest.raises(ValueError, match="same plan"):
        EvaluationSummaryIdentity(
            plan=first,
            run=EvaluationRunIdentity(plan=second, run_index=0),
        )


def test_model_summary_maps_selected_fold_and_run_to_its_trained_model() -> None:
    from XBrainLab.backend.model_base.model_catalog import get_model_spec

    dataset = _Dataset(epoch_data=_EpochData(shape=(4, 4, 168)))
    selected_model = get_model_spec("braindecode.eegnet").factory(
        n_classes=2,
        channels=4,
        samples=168,
        sfreq=128,
    )
    plans = [
        _Plan(
            [
                _Run(
                    np.array([0]),
                    np.array([[1.0, 0.0]]),
                    model=object(),
                )
            ]
        ),
        _Plan(
            [
                _Run(
                    np.array([0]),
                    np.array([[1.0, 0.0]]),
                    dataset=dataset,
                    model=object(),
                ),
                _Run(
                    np.array([1]),
                    np.array([[0.0, 1.0]]),
                    dataset=dataset,
                    model=selected_model,
                    repeat=1,
                ),
            ],
            dataset=dataset,
        ),
    ]
    plan_identity = EvaluationPlanIdentity(plan_index=1)

    summary = build_evaluation_model_summary(
        _Runtime(plans),
        EvaluationSummaryIdentity(
            plan=plan_identity,
            run=EvaluationRunIdentity(plan=plan_identity, run_index=1),
        ),
    )

    assert "=== Run: Repeat-1 ===" in summary
    assert "EEGNet" in summary
    assert "Total params" in summary


def test_model_summary_preparation_defers_model_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed_with: list[dict[str, int]] = []
    model = SimpleNamespace(parameters=list)
    plan = SimpleNamespace(
        dataset=_Dataset(),
        model_holder=SimpleNamespace(
            get_model=lambda args: (constructed_with.append(args), model)[1]
        ),
    )
    identity = EvaluationSummaryIdentity(
        plan=EvaluationPlanIdentity(plan_index=0),
    )

    preparation = prepare_evaluation_model_summary([plan], identity)

    assert constructed_with == []
    monkeypatch.setattr("torchinfo.summary", lambda *_args, **_kwargs: "Summary")
    result = build_prepared_evaluation_model_summary(preparation)

    assert constructed_with == [{}]
    assert result == EvaluationModelSummary(status="ready", text="Summary")


def test_model_summary_is_unavailable_when_selected_run_model_is_missing() -> None:
    run = _Run(
        np.array([0]),
        np.array([[1.0, 0.0]]),
        model=None,
    )
    plan = _Plan([run])
    plan_identity = EvaluationPlanIdentity(plan_index=0)

    summary = build_evaluation_model_summary(
        _Runtime([plan]),
        EvaluationSummaryIdentity(
            plan=plan_identity,
            run=EvaluationRunIdentity(plan=plan_identity, run_index=0),
        ),
    )

    assert summary == ""
    assert build_evaluation_model_summary_result(
        _Runtime([plan]),
        EvaluationSummaryIdentity(
            plan=plan_identity,
            run=EvaluationRunIdentity(plan=plan_identity, run_index=0),
        ),
    ) == EvaluationModelSummary(status="unavailable")
