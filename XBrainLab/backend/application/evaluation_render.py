"""Typed, detached Evaluation render publications for UI consumers."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import numpy as np

from XBrainLab.backend.training_state_contract import TrainingReadBoundary
from XBrainLab.backend.utils.logger import logger

from .errors import PreconditionError
from .owned_work import (
    OwnedOperationCancelledError,
    owned_work_checkpoint,
)
from .training_runtime import TrainingProjectionReadPort
from .view_publication import ApplicationViewPublication

AVAILABLE_EVALUATION_SPLITS = frozenset({"training", "validation", "test"})

if TYPE_CHECKING:
    from XBrainLab.backend.training.saliency_provenance import (
        SaliencyProducerIdentity,
    )


@dataclass(frozen=True, slots=True)
class EvaluationPlanIdentity:
    """Stable plan index within one application publication generation."""

    plan_index: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.plan_index, bool)
            or not isinstance(self.plan_index, int)
            or self.plan_index < 0
        ):
            raise ValueError("plan_index must be a non-negative integer")

    def to_dict(self) -> dict[str, int]:
        return {"plan_index": self.plan_index}


@dataclass(frozen=True, slots=True)
class EvaluationRunIdentity:
    """Stable run index nested beneath one Evaluation plan identity."""

    plan: EvaluationPlanIdentity
    run_index: int

    def __post_init__(self) -> None:
        if not isinstance(self.plan, EvaluationPlanIdentity):
            raise TypeError("plan must be an EvaluationPlanIdentity")
        if (
            isinstance(self.run_index, bool)
            or not isinstance(self.run_index, int)
            or self.run_index < 0
        ):
            raise ValueError("run_index must be a non-negative integer")

    def to_dict(self) -> dict[str, int]:
        return {
            "plan_index": self.plan.plan_index,
            "run_index": self.run_index,
        }


@dataclass(frozen=True, slots=True)
class EvaluationCrossFoldIdentity:
    """One exact repeat represented across a validated fold cohort."""

    members: tuple[EvaluationRunIdentity, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.members, tuple) or len(self.members) < 2:
            raise ValueError("cross-fold identity requires at least two run members")
        if any(
            not isinstance(member, EvaluationRunIdentity) for member in self.members
        ):
            raise TypeError("cross-fold members must be EvaluationRunIdentity values")
        plan_indexes = tuple(member.plan.plan_index for member in self.members)
        if len(set(plan_indexes)) != len(plan_indexes):
            raise ValueError("cross-fold members must reference unique folds")
        if plan_indexes != tuple(sorted(plan_indexes)):
            raise ValueError("cross-fold members must use canonical fold order")
        run_indexes = {member.run_index for member in self.members}
        if len(run_indexes) != 1:
            raise ValueError("cross-fold members must reference the same run index")

    @property
    def run_index(self) -> int:
        return self.members[0].run_index

    def to_dict(self) -> dict[str, list[dict[str, int]]]:
        return {"members": [member.to_dict() for member in self.members]}


@dataclass(frozen=True, slots=True)
class EvaluationCrossFoldChoice:
    """Backend-admitted cross-fold result available to product consumers."""

    identity: EvaluationCrossFoldIdentity
    display_name: str
    run_label: str
    evaluation_splits: tuple[str, ...]
    fold_count: int
    sample_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "display_name": self.display_name,
            "run_label": self.run_label,
            "evaluation_splits": list(self.evaluation_splits),
            "fold_count": self.fold_count,
            "sample_count": self.sample_count,
        }


@dataclass(frozen=True, slots=True)
class EvaluationSummaryIdentity:
    """Plan or exact run whose model summary may be requested."""

    plan: EvaluationPlanIdentity
    run: EvaluationRunIdentity | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.plan, EvaluationPlanIdentity):
            raise TypeError("plan must be an EvaluationPlanIdentity")
        if self.run is not None:
            if not isinstance(self.run, EvaluationRunIdentity):
                raise TypeError("run must be an EvaluationRunIdentity or None")
            if self.run.plan != self.plan:
                raise ValueError(
                    "summary run and summary plan must reference the same plan"
                )

    def to_dict(self) -> dict[str, int | None]:
        return {
            "plan_index": self.plan.plan_index,
            "run_index": self.run.run_index if self.run is not None else None,
        }


EvaluationSelectionIdentity = (
    EvaluationPlanIdentity | EvaluationRunIdentity | EvaluationCrossFoldIdentity
)


@dataclass(frozen=True, slots=True)
class EvaluationModelSummary:
    """Structured readiness for one requested model summary."""

    status: str
    text: str = ""

    def __post_init__(self) -> None:
        if self.status not in {"ready", "pending", "unavailable"}:
            raise ValueError("model summary status is invalid")
        if not isinstance(self.text, str):
            raise TypeError("model summary text must be a string")
        if self.status == "ready" and not self.text.strip():
            raise ValueError("ready model summary text cannot be empty")
        if self.status != "ready" and self.text:
            raise ValueError("non-ready model summary text must be empty")


@dataclass(frozen=True, slots=True)
class EvaluationModelSummaryPreparation:
    """Lightweight selected inputs captured before expensive model inspection."""

    identity: EvaluationSummaryIdentity
    dataset: Any | None = None
    model_instance: Any | None = None
    model_holder: Any | None = None
    run_name: str | None = None
    terminal: EvaluationModelSummary | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, EvaluationSummaryIdentity):
            raise TypeError("identity must be an EvaluationSummaryIdentity")
        if self.terminal is not None:
            if not isinstance(self.terminal, EvaluationModelSummary):
                raise TypeError("terminal must be an EvaluationModelSummary or None")
            if self.terminal.status == "ready":
                raise ValueError("a prepared terminal model summary cannot be ready")
            if any(
                value is not None
                for value in (
                    self.dataset,
                    self.model_instance,
                    self.model_holder,
                    self.run_name,
                )
            ):
                raise ValueError(
                    "terminal model summary preparation cannot retain build inputs"
                )


@dataclass(frozen=True, slots=True)
class EvaluationRenderRequest:
    """Request detached render data from one exact application generation."""

    publication_generation: int
    selection: EvaluationSelectionIdentity
    split: str = "test"

    def __post_init__(self) -> None:
        if (
            isinstance(self.publication_generation, bool)
            or not isinstance(self.publication_generation, int)
            or self.publication_generation < 1
        ):
            raise ValueError("publication_generation must be a positive integer")
        if not isinstance(
            self.selection,
            (
                EvaluationPlanIdentity,
                EvaluationRunIdentity,
                EvaluationCrossFoldIdentity,
            ),
        ):
            raise TypeError(
                "selection must be an Evaluation plan, run, or cross-fold identity"
            )
        normalized_split = str(self.split or "").strip().casefold()
        if normalized_split not in AVAILABLE_EVALUATION_SPLITS:
            raise ValueError("split must be training, validation, or test")
        object.__setattr__(self, "split", normalized_split)


MetricScalar = int | float
EvaluationMetrics = Mapping[int | str, Mapping[str, MetricScalar]]


def _copy_array_readonly(value: Any) -> np.ndarray:
    source = np.asarray(value)
    if source.dtype.hasobject:
        raise TypeError("Evaluation render arrays must not contain Python objects")
    immutable_buffer = source.tobytes(order="C")
    return np.frombuffer(immutable_buffer, dtype=source.dtype).reshape(source.shape)


def _metric_scalar(value: Any) -> MetricScalar:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Evaluation metric values must be numeric")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Evaluation metric values must be finite")
    return int(value) if isinstance(value, int) else float(value)


def _freeze_metrics(value: Mapping[Any, Any]) -> EvaluationMetrics:
    if not isinstance(value, Mapping):
        raise TypeError("Evaluation metrics must be a mapping")
    frozen: dict[int | str, Mapping[str, MetricScalar]] = {}
    for raw_key, raw_metrics in value.items():
        key: int | str
        if isinstance(raw_key, bool) or not isinstance(raw_key, (int, str)):
            raise TypeError("Evaluation metric keys must be integers or strings")
        key = raw_key
        if not isinstance(raw_metrics, Mapping):
            raise TypeError("Evaluation per-class metrics must be mappings")
        frozen[key] = MappingProxyType(
            {
                str(metric_name): _metric_scalar(metric_value)
                for metric_name, metric_value in raw_metrics.items()
            }
        )
    return MappingProxyType(frozen)


def _freeze_class_labels(
    value: Mapping[Any, Any],
    *,
    class_count: int,
) -> Mapping[int, str]:
    if not isinstance(value, Mapping):
        raise TypeError("Evaluation class labels must be a mapping")
    copied: dict[int, str] = {}
    for raw_key, raw_name in value.items():
        if isinstance(raw_key, bool) or not isinstance(raw_key, (int, np.integer)):
            raise TypeError("Evaluation class label keys must be integer indices")
        key = int(raw_key)
        if key in copied:
            raise ValueError("Evaluation class label indices must be unique")
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise TypeError("Evaluation class label names must be non-empty strings")
        copied[key] = raw_name.strip()
    expected = set(range(class_count))
    if set(copied) != expected:
        raise ValueError(
            "Evaluation class label mapping must exactly cover the output classes"
        )
    if len(set(copied.values())) != class_count:
        raise ValueError("Evaluation class label names must be unique")
    return MappingProxyType(copied)


def _require_finite_real_array(value: np.ndarray, *, field_name: str) -> None:
    if not (
        np.issubdtype(value.dtype, np.integer)
        or np.issubdtype(value.dtype, np.floating)
    ):
        raise TypeError(f"Evaluation {field_name} must contain real numeric values")
    if not bool(np.isfinite(value).all()):
        raise ValueError(f"Evaluation {field_name} must contain only finite values")


@dataclass(frozen=True, slots=True)
class EvaluationNumericSummary:
    """Bounded public evidence describing one validated numeric array."""

    shape: tuple[int, ...]
    dtype: str
    count: int
    finite_count: int
    nonfinite_count: int
    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if (
            not isinstance(self.shape, tuple)
            or not self.shape
            or any(
                isinstance(dimension, bool)
                or not isinstance(dimension, int)
                or dimension < 1
                for dimension in self.shape
            )
        ):
            raise ValueError("Evaluation numeric summary shape must be positive")
        if not isinstance(self.dtype, str) or not self.dtype.strip():
            raise TypeError("Evaluation numeric summary dtype must be non-empty")
        expected_count = math.prod(self.shape)
        if (
            isinstance(self.count, bool)
            or not isinstance(self.count, int)
            or self.count != expected_count
            or isinstance(self.finite_count, bool)
            or not isinstance(self.finite_count, int)
            or self.finite_count != self.count
            or isinstance(self.nonfinite_count, bool)
            or not isinstance(self.nonfinite_count, int)
            or self.nonfinite_count != 0
        ):
            raise ValueError("Evaluation numeric summary counts are inconsistent")
        if (
            isinstance(self.minimum, bool)
            or not isinstance(self.minimum, (int, float))
            or not math.isfinite(float(self.minimum))
            or isinstance(self.maximum, bool)
            or not isinstance(self.maximum, (int, float))
            or not math.isfinite(float(self.maximum))
            or float(self.minimum) > float(self.maximum)
        ):
            raise ValueError("Evaluation numeric summary bounds must be finite")

    @classmethod
    def from_finite_array(cls, value: np.ndarray) -> EvaluationNumericSummary:
        """Summarize an already validated, non-empty finite numeric array."""
        count = int(value.size)
        finite_count = int(np.count_nonzero(np.isfinite(value)))
        if count < 1 or finite_count != count:
            raise ValueError("Evaluation numeric summary requires finite values")
        minimum = float(np.min(value))
        maximum = float(np.max(value))
        if not math.isfinite(minimum) or not math.isfinite(maximum):
            raise ValueError("Evaluation numeric summary bounds must be finite floats")
        return cls(
            shape=tuple(int(dimension) for dimension in value.shape),
            dtype=value.dtype.name,
            count=count,
            finite_count=finite_count,
            nonfinite_count=count - finite_count,
            minimum=minimum,
            maximum=maximum,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "shape": list(self.shape),
            "dtype": self.dtype,
            "count": self.count,
            "finite_count": self.finite_count,
            "nonfinite_count": self.nonfinite_count,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


@dataclass(frozen=True, slots=True)
class EvaluationRenderData:
    """Copied arrays and presentation metadata for one run or pooled plan."""

    labels: np.ndarray
    outputs: np.ndarray
    metrics: EvaluationMetrics
    class_labels: Mapping[int, str]
    summary_identity: EvaluationSummaryIdentity | None
    evaluation_split: str
    output_numeric_summary: EvaluationNumericSummary = field(init=False)

    def __post_init__(self) -> None:
        owned_work_checkpoint("Copying evaluation labels")
        labels = _copy_array_readonly(self.labels)
        owned_work_checkpoint("Copying evaluation predictions")
        outputs = _copy_array_readonly(self.outputs)
        if labels.ndim != 1:
            raise ValueError("Evaluation labels must be one-dimensional")
        if outputs.ndim != 2:
            raise ValueError("Evaluation outputs must be two-dimensional")
        if labels.shape[0] != outputs.shape[0] or labels.shape[0] == 0:
            raise ValueError("Evaluation labels and outputs must have matching samples")
        if outputs.shape[1] < 1:
            raise ValueError("Evaluation outputs must contain at least one class")
        _require_finite_real_array(labels, field_name="labels")
        _require_finite_real_array(outputs, field_name="outputs")
        if np.issubdtype(labels.dtype, np.floating) and not bool(
            np.equal(labels, np.trunc(labels)).all()
        ):
            raise ValueError("Evaluation labels must be integer class indices")
        if bool(np.any(labels < 0)) or bool(np.any(labels >= outputs.shape[1])):
            raise ValueError(
                "Evaluation labels must be within the model output class range"
            )
        if self.summary_identity is not None and not isinstance(
            self.summary_identity,
            EvaluationSummaryIdentity,
        ):
            raise TypeError(
                "summary_identity must be an EvaluationSummaryIdentity or None"
            )
        evaluation_split = str(self.evaluation_split or "unknown").strip() or "unknown"
        object.__setattr__(self, "labels", labels)
        object.__setattr__(self, "outputs", outputs)
        object.__setattr__(self, "metrics", _freeze_metrics(self.metrics))
        object.__setattr__(
            self,
            "class_labels",
            _freeze_class_labels(
                self.class_labels,
                class_count=outputs.shape[1],
            ),
        )
        object.__setattr__(self, "evaluation_split", evaluation_split)
        object.__setattr__(
            self,
            "output_numeric_summary",
            EvaluationNumericSummary.from_finite_array(outputs),
        )
        owned_work_checkpoint("Freezing evaluation render")


@dataclass(frozen=True, slots=True)
class _EvaluationRenderMaterialization:
    data: EvaluationRenderData
    producer_identities: tuple[SaliencyProducerIdentity, ...]


@dataclass(frozen=True, slots=True)
class EvaluationRenderPublication:
    """One detached render payload proven against application and training truth."""

    request: EvaluationRenderRequest
    generation: int
    training_boundary: TrainingReadBoundary
    data: EvaluationRenderData
    operation_id: str | None = None
    producer_identities: tuple[SaliencyProducerIdentity, ...] = ()
    split_specification_fingerprint: str | None = None
    split_epoch_revision: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request, EvaluationRenderRequest):
            raise TypeError("request must be an EvaluationRenderRequest")
        if self.generation != self.request.publication_generation:
            raise ValueError("render generation must match its request")
        if not isinstance(self.training_boundary, TrainingReadBoundary):
            raise TypeError("training_boundary must be a TrainingReadBoundary")
        if not self.training_boundary.stable:
            raise ValueError("training_boundary must be stable")
        if not isinstance(self.data, EvaluationRenderData):
            raise TypeError("data must be EvaluationRenderData")
        if self.operation_id is not None and (
            not isinstance(self.operation_id, str) or not self.operation_id.strip()
        ):
            raise TypeError("operation_id must be a non-empty string or None")
        if not isinstance(self.producer_identities, tuple):
            raise TypeError("producer_identities must be a tuple")
        if self.producer_identities:
            from XBrainLab.backend.training.saliency_provenance import (  # noqa: PLC0415
                SaliencyProducerIdentity,
            )

            if any(
                not isinstance(identity, SaliencyProducerIdentity)
                for identity in self.producer_identities
            ):
                raise TypeError(
                    "producer_identities must contain SaliencyProducerIdentity values"
                )
        if self.split_specification_fingerprint is not None and (
            not isinstance(self.split_specification_fingerprint, str)
            or not self.split_specification_fingerprint.strip()
        ):
            raise TypeError(
                "split_specification_fingerprint must be a non-empty string or None"
            )
        if self.split_epoch_revision is not None and (
            isinstance(self.split_epoch_revision, bool)
            or not isinstance(self.split_epoch_revision, int)
            or self.split_epoch_revision < 1
        ):
            raise TypeError("split_epoch_revision must be a positive integer or None")


class EvaluationRenderPublisher:
    """Copy one Evaluation target across a verified training read boundary."""

    def __init__(
        self,
        *,
        training_runtime: TrainingProjectionReadPort,
        get_publication: Callable[[], ApplicationViewPublication],
        capture_training_boundary: Callable[[], TrainingReadBoundary],
    ) -> None:
        self._training_runtime = training_runtime
        self._get_publication = get_publication
        self._capture_training_boundary = capture_training_boundary

    def publish(
        self,
        request: EvaluationRenderRequest,
    ) -> EvaluationRenderPublication:
        """Return detached render data or reject stale/invalid identity."""
        if not isinstance(request, EvaluationRenderRequest):
            raise TypeError("request must be an EvaluationRenderRequest")
        owned_work_checkpoint("Capturing evaluation identity")
        before_publication = self._get_publication()
        before_boundary = self._capture_training_boundary()
        self._validate_guard(
            request,
            publication=before_publication,
            boundary=before_boundary,
        )

        owned_work_checkpoint("Reading evaluation results")
        materialization = self._copy_render_data(
            request.selection,
            split=request.split,
        )

        owned_work_checkpoint("Verifying evaluation identity")
        after_boundary = self._capture_training_boundary()
        after_publication = self._get_publication()
        if (
            after_publication.generation != before_publication.generation
            or not after_publication.usable
            or after_boundary != before_boundary
            or not after_boundary.stable
        ):
            raise self._stale_error(
                request,
                before_publication=before_publication,
                after_publication=after_publication,
                before_boundary=before_boundary,
                after_boundary=after_boundary,
            )
        self._validate_guard(
            request,
            publication=after_publication,
            boundary=after_boundary,
        )
        split_fingerprint, split_epoch_revision = _split_provenance(after_publication)
        return EvaluationRenderPublication(
            request=request,
            generation=after_publication.generation,
            training_boundary=after_boundary,
            data=materialization.data,
            producer_identities=materialization.producer_identities,
            split_specification_fingerprint=split_fingerprint,
            split_epoch_revision=split_epoch_revision,
        )

    def _validate_guard(
        self,
        request: EvaluationRenderRequest,
        *,
        publication: ApplicationViewPublication,
        boundary: TrainingReadBoundary,
    ) -> None:
        if (
            not publication.usable
            or publication.generation != request.publication_generation
            or not boundary.stable
            or publication.training_boundary != boundary
        ):
            raise self._stale_error(
                request,
                before_publication=publication,
                after_publication=publication,
                before_boundary=boundary,
                after_boundary=boundary,
            )

    def _copy_render_data(
        self,
        selection: EvaluationSelectionIdentity,
        *,
        split: str,
    ) -> _EvaluationRenderMaterialization:
        owned_work_checkpoint("Reading evaluation plans")
        plans = _iterable_items(
            self._training_runtime.training_plan_holders(),
            "Training plan collection",
        )
        if isinstance(selection, EvaluationCrossFoldIdentity):
            return self._copy_cross_fold_render_data(
                plans,
                selection=selection,
                split=split,
            )
        plan_identity = (
            selection.plan
            if isinstance(selection, EvaluationRunIdentity)
            else selection
        )
        if plan_identity.plan_index >= len(plans):
            raise self._target_error(
                "The selected training plan is no longer available"
            )
        selected_plan = plans[plan_identity.plan_index]
        runs = _plan_runs(selected_plan)

        if isinstance(selection, EvaluationRunIdentity):
            if selection.run_index >= len(runs):
                raise self._target_error(
                    "The selected training run is no longer available"
                )
            selected_run = runs[selection.run_index]
            if not _run_finished(selected_run):
                raise self._target_error("The selected training run is not complete")
            eval_record = self._record_for_split(selected_run, split)
            if eval_record is None:
                raise self._split_unavailable_error(
                    f"The selected training run has no saved {split} predictions"
                )
            labels = getattr(eval_record, "label", None)
            outputs = getattr(eval_record, "output", None)
            if labels is None or outputs is None:
                raise self._target_error(
                    "The selected training run has incomplete evaluation results"
                )
            producer_identity = _evaluation_producer_identity(
                selected_plan,
                selected_run,
                split=split,
            )
            return _EvaluationRenderMaterialization(
                data=EvaluationRenderData(
                    labels=np.asarray(labels),
                    outputs=np.asarray(outputs),
                    metrics=_record_metrics(eval_record),
                    class_labels=_class_labels(selected_run, selected_plan),
                    summary_identity=EvaluationSummaryIdentity(
                        plan=selection.plan,
                        run=selection,
                    ),
                    evaluation_split=split,
                ),
                producer_identities=(producer_identity,),
            )

        finished: list[Any] = []
        total_runs = len(runs)
        for index, run in enumerate(runs):
            owned_work_checkpoint(
                "Checking completed evaluation runs",
                completed=index,
                total=total_runs or None,
            )
            if _run_finished(run):
                finished.append(run)
        if total_runs:
            owned_work_checkpoint(
                "Checking completed evaluation runs",
                completed=total_runs,
                total=total_runs,
            )
        if not finished:
            raise self._target_error(
                "The selected training plan has no completed evaluation results"
            )
        eval_records: list[Any | None] = []
        for index, run in enumerate(finished):
            owned_work_checkpoint(
                "Selecting evaluation predictions",
                completed=index,
                total=len(finished),
            )
            eval_records.append(self._record_for_split(run, split))
        owned_work_checkpoint(
            "Selecting evaluation predictions",
            completed=len(finished),
            total=len(finished),
        )
        if any(record is None for record in eval_records):
            raise self._split_unavailable_error(
                f"The selected aggregate is missing saved {split} predictions "
                "for one or more finished runs"
            )
        selected_records = [record for record in eval_records if record is not None]
        labels, outputs, metrics = self._pool_evaluation_records(selected_records)
        producer_identities = tuple(
            _evaluation_producer_identity(selected_plan, run, split=split)
            for run in finished
        )
        return _EvaluationRenderMaterialization(
            data=EvaluationRenderData(
                labels=labels,
                outputs=outputs,
                metrics=metrics,
                class_labels=self._consistent_class_labels(
                    [(run, selected_plan) for run in finished]
                ),
                summary_identity=EvaluationSummaryIdentity(plan=selection),
                evaluation_split=split,
            ),
            producer_identities=producer_identities,
        )

    def _copy_cross_fold_render_data(
        self,
        plans: list[Any],
        *,
        selection: EvaluationCrossFoldIdentity,
        split: str,
    ) -> _EvaluationRenderMaterialization:
        if split != "test":
            raise self._split_unavailable_error(
                "Cross-fold summaries are available only for saved test predictions"
            )
        choices = {
            choice.identity: choice
            for choice in build_evaluation_cross_fold_choices(plans)
        }
        if selection not in choices:
            raise self._target_error(
                "The selected cross-fold result is no longer available"
            )
        selected_records: list[Any] = []
        label_sources: list[tuple[Any, Any]] = []
        producer_identities: list[SaliencyProducerIdentity] = []
        total_members = len(selection.members)
        for index, member in enumerate(selection.members):
            owned_work_checkpoint(
                "Collecting evaluation folds",
                completed=index,
                total=total_members,
            )
            plan = plans[member.plan.plan_index]
            run = _plan_runs(plan)[member.run_index]
            record = self._record_for_split(run, split)
            if record is None:
                raise self._split_unavailable_error(
                    "The cross-fold summary is missing saved test predictions"
                )
            selected_records.append(record)
            label_sources.append((run, plan))
            producer_identities.append(
                _evaluation_producer_identity(
                    plan,
                    run,
                    split=split,
                )
            )
        owned_work_checkpoint(
            "Collecting evaluation folds",
            completed=total_members,
            total=total_members,
        )

        labels, outputs, metrics = self._pool_evaluation_records(selected_records)
        return _EvaluationRenderMaterialization(
            data=EvaluationRenderData(
                labels=labels,
                outputs=outputs,
                metrics=metrics,
                class_labels=self._consistent_class_labels(label_sources),
                summary_identity=None,
                evaluation_split=split,
            ),
            producer_identities=tuple(producer_identities),
        )

    def _pool_evaluation_records(
        self,
        records: list[Any],
    ) -> tuple[np.ndarray, np.ndarray, Mapping[Any, Any]]:
        label_parts: list[Any] = []
        output_parts: list[Any] = []
        total_records = len(records)
        for index, record in enumerate(records):
            owned_work_checkpoint(
                "Pooling evaluation predictions",
                completed=index,
                total=total_records,
            )
            label_parts.append(record.label)
            output_parts.append(record.output)
        owned_work_checkpoint(
            "Pooling evaluation predictions",
            completed=total_records,
            total=total_records,
        )
        try:
            labels = np.concatenate(label_parts)
            outputs = np.concatenate(output_parts)
            from XBrainLab.backend.training.record import EvalRecord  # noqa: PLC0415

            pooled_record = EvalRecord(labels, outputs, {}, {}, {}, {}, {})
            metrics = pooled_record.get_per_class_metrics()
        except OwnedOperationCancelledError:
            raise
        except Exception as exc:
            raise self._target_error(
                "The selected evaluation results could not be combined"
            ) from exc
        owned_work_checkpoint("Computing evaluation metrics")
        return labels, outputs, metrics

    def _consistent_class_labels(
        self,
        sources: list[tuple[Any, Any]],
    ) -> Mapping[Any, Any]:
        mappings = [dict(_class_labels(run, plan)) for run, plan in sources]
        expected = mappings[0] if mappings else {}
        if any(mapping != expected for mapping in mappings[1:]):
            raise self._target_error(
                "Class label mappings differ across training folds"
            )
        return expected

    @staticmethod
    def _record_for_split(run: Any, split: str) -> Any | None:
        records = getattr(run, "evaluation_records", None)
        if isinstance(records, Mapping):
            record = records.get(split)
            record_split = (
                str(getattr(record, "evaluation_split", None) or "unknown")
                .strip()
                .casefold()
            )
            if record is not None and record_split == split:
                return record
        legacy_record = getattr(run, "eval_record", None)
        legacy_split = (
            str(getattr(legacy_record, "evaluation_split", None) or "unknown")
            .strip()
            .casefold()
        )
        return legacy_record if legacy_split == split else None

    @staticmethod
    def _split_unavailable_error(message: str) -> PreconditionError:
        return PreconditionError(
            f"{message}. Select another available split.",
            diagnostics={
                "evaluation_split_unavailable": True,
                "retryable": False,
            },
        )

    @staticmethod
    def _final_unavailable_error(message: str) -> PreconditionError:
        return PreconditionError(
            f"{message}. Configure a validation or test split and train again.",
            diagnostics={
                "evaluation_final_unavailable": True,
                "retryable": False,
            },
        )

    @staticmethod
    def _target_error(message: str) -> PreconditionError:
        return PreconditionError(
            f"{message}. Refresh Evaluation and try again.",
            diagnostics={
                "evaluation_render_stale": True,
                "retryable": True,
            },
        )

    @staticmethod
    def _stale_error(
        request: EvaluationRenderRequest,
        *,
        before_publication: ApplicationViewPublication,
        after_publication: ApplicationViewPublication,
        before_boundary: TrainingReadBoundary,
        after_boundary: TrainingReadBoundary,
    ) -> PreconditionError:
        return PreconditionError(
            "Evaluation results changed while render data was being read. "
            "Refresh Evaluation and try again.",
            diagnostics={
                "evaluation_render_stale": True,
                "training_state_changed": (
                    before_boundary != after_boundary or not after_boundary.stable
                ),
                "retryable": True,
                "publication_generation_before": request.publication_generation,
                "publication_generation_after": after_publication.generation,
                "observed_publication_generation_before": (
                    before_publication.generation
                ),
                "training_generation_before": before_boundary.token.generation,
                "training_generation_after": after_boundary.token.generation,
                "trainer_identity_changed": (
                    before_boundary.trainer_identity != after_boundary.trainer_identity
                ),
            },
        )


def build_evaluation_model_summary(
    training_runtime: TrainingProjectionReadPort,
    identity: EvaluationSummaryIdentity,
) -> str:
    """Build one model summary from a validated backend-only identity."""
    return build_evaluation_model_summary_result(training_runtime, identity).text


def build_evaluation_model_summary_result(
    training_runtime: TrainingProjectionReadPort,
    identity: EvaluationSummaryIdentity,
) -> EvaluationModelSummary:
    """Build one model summary together with explicit readiness semantics."""
    if not isinstance(identity, EvaluationSummaryIdentity):
        raise TypeError("identity must be an EvaluationSummaryIdentity")
    owned_work_checkpoint("Reading model summary plans")
    plans = _iterable_items(
        training_runtime.training_plan_holders(),
        "Training plan collection",
    )
    owned_work_checkpoint("Model summary plans ready")
    preparation = prepare_evaluation_model_summary(plans, identity)
    return build_prepared_evaluation_model_summary(preparation)


def prepare_evaluation_model_summary(
    plans: Iterable[Any],
    identity: EvaluationSummaryIdentity,
) -> EvaluationModelSummaryPreparation:
    """Capture one selected model target without constructing or inspecting it."""
    if not isinstance(identity, EvaluationSummaryIdentity):
        raise TypeError("identity must be an EvaluationSummaryIdentity")
    selected_plans = _iterable_items(plans, "Training plan collection")
    if identity.plan.plan_index >= len(selected_plans):
        raise EvaluationRenderPublisher._target_error(
            "The selected training plan is no longer available"
        )
    selected_plan = selected_plans[identity.plan.plan_index]
    owned_work_checkpoint("Selecting model summary plan")
    selected_run: Any | None = None
    if identity.run is not None:
        owned_work_checkpoint("Reading model summary runs")
        runs = _plan_runs(selected_plan)
        if identity.run.run_index >= len(runs):
            raise EvaluationRenderPublisher._target_error(
                "The selected training run is no longer available"
            )
        selected_run = runs[identity.run.run_index]
        owned_work_checkpoint("Selected model summary run")
        if not _run_finished(selected_run):
            return EvaluationModelSummaryPreparation(
                identity=identity,
                terminal=EvaluationModelSummary(status="pending"),
            )

    dataset = getattr(selected_run, "dataset", None) or getattr(
        selected_plan,
        "dataset",
        None,
    )
    if selected_run is not None:
        owned_work_checkpoint("Reading trained model instance")
        model_instance = getattr(selected_run, "model", None)
        if model_instance is None:
            return EvaluationModelSummaryPreparation(
                identity=identity,
                terminal=EvaluationModelSummary(status="unavailable"),
            )
        get_name = getattr(selected_run, "get_name", None)
        run_name = str(get_name()) if callable(get_name) else "Selected run"
        return EvaluationModelSummaryPreparation(
            identity=identity,
            dataset=dataset,
            model_instance=model_instance,
            run_name=run_name,
        )
    return EvaluationModelSummaryPreparation(
        identity=identity,
        dataset=dataset,
        model_holder=getattr(selected_plan, "model_holder", None),
    )


def build_prepared_evaluation_model_summary(
    preparation: EvaluationModelSummaryPreparation,
) -> EvaluationModelSummary:
    """Construct and inspect one prepared model outside application command locks."""
    if not isinstance(preparation, EvaluationModelSummaryPreparation):
        raise TypeError("preparation must be an EvaluationModelSummaryPreparation")
    if preparation.terminal is not None:
        owned_work_checkpoint("Model summary terminal state ready")
        return preparation.terminal

    dataset = preparation.dataset
    model_instance = preparation.model_instance
    if model_instance is None:
        owned_work_checkpoint("Reading model summary input metadata")
        epoch_getter = getattr(dataset, "get_epoch_data", None)
        if not callable(epoch_getter):
            raise ValueError("The selected model input metadata is unavailable")
        epoch_data = epoch_getter()
        model_args_getter = getattr(epoch_data, "get_model_args", None)
        if not callable(model_args_getter):
            raise ValueError("The selected model input metadata is unavailable")
        model_args = model_args_getter()
        if not isinstance(model_args, dict):
            raise ValueError("The selected model input metadata is unavailable")
        model_builder = getattr(preparation.model_holder, "get_model", None)
        if not callable(model_builder):
            raise ValueError("The selected model configuration is unavailable")
        owned_work_checkpoint("Constructing model summary instance")
        model_instance = model_builder(model_args)
        owned_work_checkpoint("Model summary instance ready")
    owned_work_checkpoint("Reading model summary input shape")
    input_shape = _model_summary_input_shape(dataset)
    owned_work_checkpoint("Model summary input shape ready")
    try:
        owned_work_checkpoint("Loading detailed model summary")
        from torchinfo import summary  # noqa: PLC0415

        try:
            owned_work_checkpoint("Building detailed model summary")
            summary_text = str(
                summary(
                    model_instance,
                    input_size=input_shape,
                    mode="eval",
                    verbose=0,
                )
            )
            owned_work_checkpoint("Detailed model summary ready")
        except OwnedOperationCancelledError:
            raise
        except Exception:
            logger.warning(
                "Detailed Evaluation model summary failed; using basic model details",
                exc_info=True,
            )
            owned_work_checkpoint("Building fallback model summary")
            summary_text = _fallback_model_summary(model_instance, input_shape)
            owned_work_checkpoint("Fallback model summary ready")
    except ModuleNotFoundError:
        logger.warning(
            "Required torchinfo dependency is unavailable; using basic model details"
        )
        owned_work_checkpoint("Building fallback model summary")
        summary_text = _fallback_model_summary(model_instance, input_shape)
        owned_work_checkpoint("Fallback model summary ready")
    if preparation.run_name is not None:
        summary_text = f"=== Run: {preparation.run_name} ===\n{summary_text}"
    owned_work_checkpoint("Model summary publication ready")
    return EvaluationModelSummary(status="ready", text=summary_text)


def _model_summary_input_shape(dataset: Any) -> tuple[int, int, int]:
    epoch_getter = getattr(dataset, "get_epoch_data", None)
    if not callable(epoch_getter):
        raise ValueError("The selected model input metadata is unavailable")
    data_getter = getattr(epoch_getter(), "get_data", None)
    if not callable(data_getter):
        raise ValueError("The selected model input metadata is unavailable")
    shape = getattr(data_getter(), "shape", None)
    if (
        not isinstance(shape, tuple)
        or len(shape) != 3
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in shape
        )
    ):
        raise ValueError("The selected model input shape is unavailable")
    return (1, shape[1], shape[2])


def _fallback_model_summary(model_instance: Any, input_shape: tuple[int, ...]) -> str:
    model_name = model_instance.__class__.__name__
    lines = [f"Model: {model_name}", f"Input shape: {input_shape}"]
    try:
        parameters = list(model_instance.parameters())
    except Exception:
        parameters = []
    if parameters:
        total = sum(int(parameter.numel()) for parameter in parameters)
        trainable = sum(
            int(parameter.numel())
            for parameter in parameters
            if getattr(parameter, "requires_grad", False)
        )
        lines.extend(
            [
                f"Total parameters: {total:,}",
                f"Trainable parameters: {trainable:,}",
            ]
        )
    else:
        lines.append("Parameters: unavailable")
    try:
        children = list(model_instance.named_children())
    except Exception:
        children = []
    if children:
        lines.extend(["", "Top-level modules:"])
        for name, module in children[:20]:
            lines.append(f"  {name}: {module.__class__.__name__}")
        if len(children) > 20:
            lines.append(f"  ... {len(children) - 20} more module(s)")
    else:
        lines.extend(["", str(model_instance)])
    lines.extend(["", "Detailed layer shapes are unavailable."])
    return "\n".join(lines)


def _iterable_items(value: object, description: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        raise PreconditionError(
            f"{description} is unavailable",
            diagnostics={"evaluation_render_stale": True, "retryable": True},
        )
    return list(value)


def _plan_runs(plan: Any) -> list[Any]:
    getter = getattr(plan, "get_plans", None)
    if not callable(getter):
        raise EvaluationRenderPublisher._target_error(
            "The selected training plan has no readable runs"
        )
    return _iterable_items(getter(), "Training run collection")


def _run_finished(run: Any) -> bool:
    checker = getattr(run, "is_finished", None)
    return bool(checker()) if callable(checker) else False


def _record_metrics(eval_record: Any) -> Mapping[Any, Any]:
    getter = getattr(eval_record, "get_per_class_metrics", None)
    if not callable(getter):
        raise EvaluationRenderPublisher._target_error(
            "The selected evaluation metrics are unavailable"
        )
    metrics = getter()
    if not isinstance(metrics, Mapping):
        raise EvaluationRenderPublisher._target_error(
            "The selected evaluation metrics are invalid"
        )
    return metrics


def _evaluation_producer_identity(
    plan: Any,
    run: Any,
    *,
    split: str,
) -> SaliencyProducerIdentity:
    """Return the backend-generated dataset/split/run/model identity."""
    builder = getattr(plan, "build_saliency_producer_identity", None)
    if not callable(builder):
        raise EvaluationRenderPublisher._target_error(
            "Evaluation producer identity is unavailable"
        )
    identity = builder(run, evaluation_split=split)
    from XBrainLab.backend.training.saliency_provenance import (  # noqa: PLC0415
        SaliencyProducerIdentity,
    )

    if not isinstance(identity, SaliencyProducerIdentity):
        raise EvaluationRenderPublisher._target_error(
            "Evaluation producer identity is invalid"
        )
    return identity


def _split_provenance(
    publication: ApplicationViewPublication,
) -> tuple[str, int]:
    """Require the saved split identity from the exact verified publication."""
    state = getattr(publication, "state", None)
    dataset = getattr(state, "dataset", None)
    fingerprint = getattr(dataset, "split_specification_fingerprint", None)
    revision = getattr(dataset, "split_epoch_revision", None)
    if (
        not isinstance(fingerprint, str)
        or not fingerprint.strip()
        or isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision < 1
    ):
        raise EvaluationRenderPublisher._target_error(
            "Evaluation split provenance is unavailable"
        )
    return fingerprint, revision


def _class_labels(run: Any, plan: Any) -> Mapping[Any, Any]:
    dataset = getattr(run, "dataset", None) or getattr(plan, "dataset", None)
    epoch_getter = getattr(dataset, "get_epoch_data", None)
    if not callable(epoch_getter):
        return {}
    epoch_data = epoch_getter()
    labels = getattr(epoch_data, "label_map", {})
    return labels if isinstance(labels, Mapping) else {}


def build_evaluation_cross_fold_choices(
    plans: Iterable[Any],
) -> tuple[EvaluationCrossFoldChoice, ...]:
    """Return exact test-only cross-fold runs admitted by backend evidence."""
    indexed_plans = list(enumerate(plans))
    cohorts: dict[tuple[int, int, str], list[tuple[int, Any]]] = {}
    for plan_index, plan in indexed_plans:
        dataset = getattr(plan, "dataset", None)
        epoch_data = getattr(dataset, "epoch_data", None)
        config = getattr(dataset, "config", None)
        cohort_id = getattr(dataset, "cross_validation_cohort_id", None)
        if (
            dataset is None
            or epoch_data is None
            or config is None
            or not isinstance(cohort_id, str)
            or not cohort_id
            or getattr(config, "is_cross_validation", False) is not True
        ):
            continue
        cohorts.setdefault((id(epoch_data), id(config), cohort_id), []).append(
            (plan_index, plan)
        )

    admitted_cohorts = [
        cohort
        for cohort in sorted(cohorts.values(), key=lambda value: value[0][0])
        if len(cohort) >= 2
    ]
    choices: list[EvaluationCrossFoldChoice] = []
    for cohort_position, cohort in enumerate(admitted_cohorts, start=1):
        run_lists = [_plan_runs(plan) for _plan_index, plan in cohort]
        common_run_count = min((len(runs) for runs in run_lists), default=0)
        display_name = (
            "All Folds" if len(admitted_cohorts) == 1 else f"Fold Set {cohort_position}"
        )
        for run_index in range(common_run_count):
            members = tuple(
                EvaluationRunIdentity(
                    plan=EvaluationPlanIdentity(plan_index=plan_index),
                    run_index=run_index,
                )
                for plan_index, _plan in cohort
            )
            sample_count = _cross_fold_sample_count(
                cohort,
                run_lists,
                run_index=run_index,
            )
            if sample_count is None:
                continue
            choices.append(
                EvaluationCrossFoldChoice(
                    identity=EvaluationCrossFoldIdentity(members=members),
                    display_name=display_name,
                    run_label=f"Run {run_index + 1} (Summary)",
                    evaluation_splits=("test",),
                    fold_count=len(members),
                    sample_count=sample_count,
                )
            )
    return tuple(choices)


def _cross_fold_sample_count(
    cohort: list[tuple[int, Any]],
    run_lists: list[list[Any]],
    *,
    run_index: int,
) -> int | None:
    masks: list[np.ndarray] = []
    output_width: int | None = None
    class_labels: dict[Any, Any] | None = None
    mask_shape: tuple[int, ...] | None = None
    sample_count = 0
    for (_plan_index, plan), runs in zip(cohort, run_lists, strict=True):
        run = runs[run_index]
        if not _run_finished(run):
            return None
        plan_dataset = getattr(plan, "dataset", None)
        dataset = getattr(run, "dataset", None) or plan_dataset
        if dataset is not plan_dataset:
            return None
        mask = np.asarray(getattr(dataset, "test_mask", None))
        if mask.ndim != 1 or mask.dtype.kind != "b" or not mask.any():
            return None
        if mask_shape is None:
            mask_shape = mask.shape
        elif mask.shape != mask_shape:
            return None
        record = EvaluationRenderPublisher._record_for_split(run, "test")
        if record is None:
            return None
        labels = np.asarray(getattr(record, "label", None))
        outputs = np.asarray(getattr(record, "output", None))
        expected_count = int(np.count_nonzero(mask))
        if (
            labels.ndim != 1
            or outputs.ndim != 2
            or labels.shape[0] != expected_count
            or outputs.shape[0] != expected_count
        ):
            return None
        if output_width is None:
            output_width = int(outputs.shape[1])
        elif outputs.shape[1] != output_width:
            return None
        current_labels = dict(_class_labels(run, plan))
        if not current_labels or len(current_labels) != output_width:
            return None
        if class_labels is None:
            class_labels = current_labels
        elif current_labels != class_labels:
            return None
        if any(np.any(mask & previous) for previous in masks):
            return None
        masks.append(mask)
        sample_count += expected_count
    return sample_count if sample_count > 0 else None


__all__ = [
    "EvaluationCrossFoldChoice",
    "EvaluationCrossFoldIdentity",
    "EvaluationModelSummary",
    "EvaluationModelSummaryPreparation",
    "EvaluationPlanIdentity",
    "EvaluationRenderData",
    "EvaluationRenderPublication",
    "EvaluationRenderPublisher",
    "EvaluationRenderRequest",
    "EvaluationRunIdentity",
    "EvaluationSelectionIdentity",
    "EvaluationSummaryIdentity",
    "build_evaluation_cross_fold_choices",
    "build_evaluation_model_summary",
    "build_evaluation_model_summary_result",
    "build_prepared_evaluation_model_summary",
    "prepare_evaluation_model_summary",
]
