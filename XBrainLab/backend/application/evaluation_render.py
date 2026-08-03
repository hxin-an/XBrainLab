"""Typed, detached Evaluation render publications for UI consumers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import numpy as np

from XBrainLab.backend.training_state_contract import TrainingReadBoundary
from XBrainLab.backend.utils.logger import logger

from .errors import PreconditionError
from .training_runtime import TrainingProjectionReadPort
from .view_publication import ApplicationViewPublication

AVAILABLE_EVALUATION_SPLITS = frozenset({"training", "validation", "test"})


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


EvaluationSelectionIdentity = EvaluationPlanIdentity | EvaluationRunIdentity


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
            (EvaluationPlanIdentity, EvaluationRunIdentity),
        ):
            raise TypeError("selection must be an Evaluation plan or run identity")
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
    return int(value) if isinstance(value, int) else float(value)


def _freeze_metrics(value: Mapping[Any, Any]) -> EvaluationMetrics:
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


def _freeze_class_labels(value: Mapping[Any, Any]) -> Mapping[int, str]:
    copied: dict[int, str] = {}
    for raw_key, raw_name in value.items():
        if isinstance(raw_key, bool):
            continue
        try:
            key = int(raw_key)
        except (TypeError, ValueError):
            continue
        if key < 0:
            continue
        copied[key] = str(raw_name)
    return MappingProxyType(copied)


@dataclass(frozen=True, slots=True)
class EvaluationRenderData:
    """Copied arrays and presentation metadata for one run or pooled plan."""

    labels: np.ndarray
    outputs: np.ndarray
    metrics: EvaluationMetrics
    class_labels: Mapping[int, str]
    summary_identity: EvaluationSummaryIdentity
    evaluation_split: str

    def __post_init__(self) -> None:
        labels = _copy_array_readonly(self.labels)
        outputs = _copy_array_readonly(self.outputs)
        if labels.ndim != 1:
            raise ValueError("Evaluation labels must be one-dimensional")
        if outputs.ndim != 2:
            raise ValueError("Evaluation outputs must be two-dimensional")
        if labels.shape[0] != outputs.shape[0] or labels.shape[0] == 0:
            raise ValueError("Evaluation labels and outputs must have matching samples")
        if not isinstance(self.summary_identity, EvaluationSummaryIdentity):
            raise TypeError("summary_identity must be an EvaluationSummaryIdentity")
        evaluation_split = str(self.evaluation_split or "unknown").strip() or "unknown"
        object.__setattr__(self, "labels", labels)
        object.__setattr__(self, "outputs", outputs)
        object.__setattr__(self, "metrics", _freeze_metrics(self.metrics))
        object.__setattr__(
            self,
            "class_labels",
            _freeze_class_labels(self.class_labels),
        )
        object.__setattr__(self, "evaluation_split", evaluation_split)


@dataclass(frozen=True, slots=True)
class EvaluationRenderPublication:
    """One detached render payload proven against application and training truth."""

    request: EvaluationRenderRequest
    generation: int
    training_boundary: TrainingReadBoundary
    data: EvaluationRenderData

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
        before_publication = self._get_publication()
        before_boundary = self._capture_training_boundary()
        self._validate_guard(
            request,
            publication=before_publication,
            boundary=before_boundary,
        )

        data = self._copy_render_data(request.selection, split=request.split)

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
        return EvaluationRenderPublication(
            request=request,
            generation=after_publication.generation,
            training_boundary=after_boundary,
            data=data,
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
    ) -> EvaluationRenderData:
        plans = _iterable_items(
            self._training_runtime.training_plan_holders(),
            "Training plan collection",
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
            return EvaluationRenderData(
                labels=np.asarray(labels),
                outputs=np.asarray(outputs),
                metrics=_record_metrics(eval_record),
                class_labels=_class_labels(selected_run, selected_plan),
                summary_identity=EvaluationSummaryIdentity(
                    plan=selection.plan,
                    run=selection,
                ),
                evaluation_split=split,
            )

        finished = [run for run in runs if _run_finished(run)]
        if not finished:
            raise self._target_error(
                "The selected training plan has no completed evaluation results"
            )
        eval_records = [self._record_for_split(run, split) for run in finished]
        if any(record is None for record in eval_records):
            raise self._split_unavailable_error(
                f"The selected aggregate is missing saved {split} predictions "
                "for one or more finished runs"
            )
        selected_records = [record for record in eval_records if record is not None]
        try:
            labels = np.concatenate([record.label for record in selected_records])
            outputs = np.concatenate([record.output for record in selected_records])
            from XBrainLab.backend.training.record import EvalRecord  # noqa: PLC0415

            pooled_record = EvalRecord(labels, outputs, {}, {}, {}, {}, {})
            metrics = pooled_record.get_per_class_metrics()
        except Exception as exc:
            raise self._target_error(
                "The selected evaluation results could not be combined"
            ) from exc
        return EvaluationRenderData(
            labels=labels,
            outputs=outputs,
            metrics=metrics,
            class_labels=_class_labels(finished[0], selected_plan),
            summary_identity=EvaluationSummaryIdentity(plan=selection),
            evaluation_split=split,
        )

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
    if not isinstance(identity, EvaluationSummaryIdentity):
        raise TypeError("identity must be an EvaluationSummaryIdentity")
    plans = _iterable_items(
        training_runtime.training_plan_holders(),
        "Training plan collection",
    )
    if identity.plan.plan_index >= len(plans):
        raise EvaluationRenderPublisher._target_error(
            "The selected training plan is no longer available"
        )
    selected_plan = plans[identity.plan.plan_index]
    selected_run: Any | None = None
    if identity.run is not None:
        runs = _plan_runs(selected_plan)
        if identity.run.run_index >= len(runs):
            raise EvaluationRenderPublisher._target_error(
                "The selected training run is no longer available"
            )
        selected_run = runs[identity.run.run_index]

    try:
        if selected_run is not None and hasattr(selected_run, "model"):
            model_instance = selected_run.model
        else:
            epoch_data = selected_plan.dataset.get_epoch_data()
            model_instance = selected_plan.model_holder.get_model(
                epoch_data.get_model_args()
            ).to(selected_plan.option.get_device())
        training_data, _ = selected_plan.dataset.get_training_data()
        input_shape = (
            selected_plan.option.bs,
            1,
            *training_data.shape[-2:],
        )
        try:
            from torchinfo import summary  # noqa: PLC0415
        except ModuleNotFoundError:
            summary_text = _fallback_model_summary(model_instance, input_shape)
        else:
            summary_text = str(
                summary(model_instance, input_size=input_shape, verbose=0)
            )
        if selected_run is not None:
            get_name = getattr(selected_run, "get_name", None)
            run_name = str(get_name()) if callable(get_name) else "Selected run"
            summary_text = f"=== Run: {run_name} ===\n{summary_text}"
    except Exception:
        logger.error("Error generating Evaluation model summary", exc_info=True)
        return ""
    else:
        return summary_text


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
    lines.extend(["", "Detailed layer shapes require optional dependency 'torchinfo'."])
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


def _class_labels(run: Any, plan: Any) -> Mapping[Any, Any]:
    dataset = getattr(run, "dataset", None) or getattr(plan, "dataset", None)
    epoch_getter = getattr(dataset, "get_epoch_data", None)
    if not callable(epoch_getter):
        return {}
    epoch_data = epoch_getter()
    labels = getattr(epoch_data, "label_map", {})
    return labels if isinstance(labels, Mapping) else {}


__all__ = [
    "EvaluationPlanIdentity",
    "EvaluationRenderData",
    "EvaluationRenderPublication",
    "EvaluationRenderPublisher",
    "EvaluationRenderRequest",
    "EvaluationRunIdentity",
    "EvaluationSelectionIdentity",
    "EvaluationSummaryIdentity",
    "build_evaluation_model_summary",
]
