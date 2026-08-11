"""Typed, detached saliency render publications for UI consumers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import InitVar, dataclass, replace
from types import MappingProxyType
from typing import Any, Literal

import numpy as np

from XBrainLab.backend.training_state_contract import TrainingReadBoundary

from .errors import PreconditionError
from .evaluation_render import build_evaluation_cross_fold_choices
from .montage_capability import (
    MontageCoordinateDimension,
    project_montage_geometry,
)
from .training_runtime import TrainingRuntimePort
from .view_publication import ApplicationViewPublication

SALIENCY_METHOD_ATTRIBUTES = {
    "Gradient": "gradient",
    "Gradient * Input": "gradient_input",
    "SmoothGrad": "smoothgrad",
    "SmoothGrad_Squared": "smoothgrad_sq",
    "VarGrad": "vargrad",
}

_DETACHED_SALIENCY_ARRAYS = object()


@dataclass(frozen=True)
class SaliencyPlanIdentity:
    """Stable index identity for one plan in an application publication."""

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


@dataclass(frozen=True)
class SaliencyRunIdentity:
    """Stable plan/run identity carried by visualization controls."""

    plan: SaliencyPlanIdentity
    run_index: int

    def __post_init__(self) -> None:
        if not isinstance(self.plan, SaliencyPlanIdentity):
            raise TypeError("plan must be a SaliencyPlanIdentity")
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


@dataclass(frozen=True)
class SaliencyCrossFoldIdentity:
    """One exact run index represented across a validated fold cohort."""

    members: tuple[SaliencyRunIdentity, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.members, tuple) or len(self.members) < 2:
            raise ValueError("cross-fold saliency requires at least two folds")
        if any(not isinstance(member, SaliencyRunIdentity) for member in self.members):
            raise TypeError("cross-fold members must be SaliencyRunIdentity values")
        plan_indexes = tuple(member.plan.plan_index for member in self.members)
        if len(set(plan_indexes)) != len(plan_indexes):
            raise ValueError("cross-fold saliency members must use distinct folds")
        if plan_indexes != tuple(sorted(plan_indexes)):
            raise ValueError("cross-fold saliency members must use canonical order")
        if len({member.run_index for member in self.members}) != 1:
            raise ValueError("cross-fold saliency members must use one run index")

    @property
    def run_index(self) -> int:
        return self.members[0].run_index

    def to_dict(self) -> dict[str, list[dict[str, int]]]:
        return {"members": [member.to_dict() for member in self.members]}


@dataclass(frozen=True)
class SaliencyCrossFoldClass:
    """One class identity shared by every admitted fold member."""

    class_index: int
    display_name: str
    event_code: object
    store_key: object


@dataclass(frozen=True)
class SaliencyCrossFoldChoice:
    """Backend-admitted pooled out-of-fold saliency summary."""

    identity: SaliencyCrossFoldIdentity
    display_name: str
    run_label: str
    methods: tuple[str, ...]
    source_split: str
    classes: tuple[SaliencyCrossFoldClass, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "display_name": self.display_name,
            "run_label": self.run_label,
            "methods": list(self.methods),
            "source_split": self.source_split,
            "fold_count": len(self.identity.members),
            "classes": [
                {
                    "class_index": item.class_index,
                    "display_name": item.display_name,
                    "event_code": item.event_code,
                    "store_key": item.store_key,
                }
                for item in self.classes
            ],
        }


@dataclass(frozen=True)
class _ValidatedSaliencyCrossFoldChoice:
    """One admitted choice and the exact records validated for its render."""

    choice: SaliencyCrossFoldChoice
    records: tuple[Any, ...]
    contexts: tuple[Any, ...]
    epoch_data: tuple[Any, ...]


SaliencySelectionIdentity = SaliencyRunIdentity | SaliencyCrossFoldIdentity
SaliencyRenderView = Literal[
    "channel_time",
    "topographic_map",
    "three_dimensional",
]
_POSITION_DEPENDENT_VIEWS = {"topographic_map", "three_dimensional"}


@dataclass(frozen=True)
class SaliencyRenderRequest:
    """Request one method payload from an exact application generation."""

    publication_generation: int
    run: SaliencySelectionIdentity
    method: str
    normalize: bool = False
    view: SaliencyRenderView = "channel_time"

    def __post_init__(self) -> None:
        if (
            isinstance(self.publication_generation, bool)
            or not isinstance(self.publication_generation, int)
            or self.publication_generation < 1
        ):
            raise ValueError("publication_generation must be a positive integer")
        if not isinstance(
            self.run,
            (SaliencyRunIdentity, SaliencyCrossFoldIdentity),
        ):
            raise TypeError("run must be a saliency run or cross-fold identity")
        method = str(self.method).strip()
        if not method:
            raise ValueError("method must be a non-empty string")
        if type(self.normalize) is not bool:
            raise TypeError("normalize must be a bool")
        view = str(self.view).strip()
        if view not in {
            "channel_time",
            "topographic_map",
            "three_dimensional",
        }:
            raise ValueError("view must identify a supported saliency render view")
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "view", view)


def _copy_array_readonly(value: Any) -> np.ndarray:
    """Copy one array-like payload and permanently disable writes."""
    copied = np.array(value, copy=True)
    copied.setflags(write=False)
    return copied


@dataclass(frozen=True)
class SaliencyRenderData:
    """Renderer-only EEG metadata and one detached saliency method store."""

    method: str
    saliency_by_class: Mapping[object, np.ndarray]
    class_map: tuple[tuple[object, str], ...]
    event_ids: Mapping[str, int]
    channel_names: tuple[str, ...]
    channel_positions: tuple[tuple[float, ...], ...]
    sfreq: float
    tmin: float
    source_split: str = "unknown"
    aggregation: str = "per-epoch"
    fold_count: int = 1
    normalized: bool = False
    _detached_arrays: InitVar[object | None] = None

    def __post_init__(self, _detached_arrays: object | None) -> None:
        method = str(self.method).strip()
        if not method:
            raise ValueError("render method must be a non-empty string")
        if _detached_arrays is _DETACHED_SALIENCY_ARRAYS:
            copied_store = {
                key: self._adopt_detached_array(value)
                for key, value in self.saliency_by_class.items()
            }
        else:
            copied_store = {
                key: _copy_array_readonly(value)
                for key, value in self.saliency_by_class.items()
            }
        if not copied_store:
            raise ValueError(f"No {method} saliency is available for this run")
        sfreq = float(self.sfreq)
        tmin = float(self.tmin)
        if not np.isfinite(sfreq) or sfreq <= 0:
            raise ValueError("Sampling frequency must be finite and positive")
        if not np.isfinite(tmin):
            raise ValueError("Epoch start time must be finite")
        source_split = str(self.source_split or "unknown").strip() or "unknown"
        aggregation = str(self.aggregation or "per-epoch").strip() or "per-epoch"
        if (
            isinstance(self.fold_count, bool)
            or not isinstance(self.fold_count, int)
            or self.fold_count < 1
        ):
            raise ValueError("fold_count must be a positive integer")
        if type(self.normalized) is not bool:
            raise TypeError("normalized must be a bool")
        object.__setattr__(self, "method", method)
        object.__setattr__(
            self,
            "saliency_by_class",
            MappingProxyType(copied_store),
        )
        object.__setattr__(
            self,
            "class_map",
            tuple((key, str(name)) for key, name in self.class_map),
        )
        object.__setattr__(
            self,
            "event_ids",
            MappingProxyType(
                {str(name): int(code) for name, code in self.event_ids.items()}
            ),
        )
        object.__setattr__(
            self,
            "channel_names",
            tuple(str(name) for name in self.channel_names),
        )
        object.__setattr__(
            self,
            "channel_positions",
            tuple(
                tuple(float(coordinate) for coordinate in position)
                for position in self.channel_positions
            ),
        )
        object.__setattr__(self, "sfreq", sfreq)
        object.__setattr__(self, "tmin", tmin)
        object.__setattr__(self, "source_split", source_split)
        object.__setattr__(self, "aggregation", aggregation)

    @staticmethod
    def _adopt_detached_array(value: Any) -> np.ndarray:
        """Freeze one private array that was freshly allocated for this DTO."""
        if (
            not isinstance(value, np.ndarray)
            or not value.flags.owndata
            or value.base is not None
        ):
            raise ValueError("Detached saliency arrays must own their storage")
        value.setflags(write=False)
        return value

    @property
    def expected_class_count(self) -> int | None:
        """Return the authoritative model-class count when published."""
        return len(self.class_map) or None

    def get_channel_names(self) -> list[str]:
        """Return a detached channel-name list for existing render algorithms."""
        return list(self.channel_names)

    def get_montage_position(self) -> list[tuple[float, ...]]:
        """Return detached montage positions for existing render algorithms."""
        return list(self.channel_positions)

    def get_model_args(self) -> dict[str, float]:
        """Return the sampling metadata used by existing render algorithms."""
        return {"sfreq": self.sfreq}

    @property
    def event_id(self) -> Mapping[str, int]:
        """Expose immutable event IDs to existing render algorithms."""
        return self.event_ids

    @property
    def label_map(self) -> Mapping[object, str]:
        """Expose the validated class map without mutable dataset access."""
        return MappingProxyType(dict(self.class_map))


@dataclass(frozen=True)
class SaliencyRenderPublication:
    """One render payload proven to match an application/training generation."""

    request: SaliencyRenderRequest
    generation: int
    training_generation: int
    data: SaliencyRenderData

    def __post_init__(self) -> None:
        if not isinstance(self.request, SaliencyRenderRequest):
            raise TypeError("request must be a SaliencyRenderRequest")
        if self.generation != self.request.publication_generation:
            raise ValueError("render generation must match its request")
        if (
            isinstance(self.training_generation, bool)
            or not isinstance(self.training_generation, int)
            or self.training_generation < 0
        ):
            raise ValueError("training_generation must be a non-negative integer")
        if not isinstance(self.data, SaliencyRenderData):
            raise TypeError("data must be SaliencyRenderData")


def _plan_runs(holder: Any) -> list[Any]:
    getter = getattr(holder, "get_plans", None)
    value = getter() if callable(getter) else getattr(holder, "train_record_list", ())
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        return []
    return list(value)


def _holder_and_run(
    holders: list[Any],
    identity: SaliencyRunIdentity,
) -> tuple[Any, Any]:
    plan_index = identity.plan.plan_index
    if plan_index >= len(holders):
        raise SaliencyRenderPublisher._target_error(
            "The selected training plan is no longer available"
        )
    holder = holders[plan_index]
    runs = _plan_runs(holder)
    if identity.run_index >= len(runs):
        raise SaliencyRenderPublisher._target_error(
            "The selected training run is no longer available"
        )
    return holder, runs[identity.run_index]


def _saliency_eval_record(run: Any) -> Any | None:
    getter = getattr(run, "get_saliency_eval_record", None)
    if callable(getter):
        return getter()
    record_getter = getattr(run, "get_eval_record", None)
    if callable(record_getter):
        return record_getter()
    return getattr(run, "eval_record", None)


def _record_source_split(eval_record: Any) -> str:
    return str(getattr(eval_record, "evaluation_split", None) or "unknown").strip()


def _epoch_data_for_holder(holder: Any) -> Any:
    dataset_getter = getattr(holder, "get_dataset", None)
    dataset = (
        dataset_getter()
        if callable(dataset_getter)
        else getattr(holder, "dataset", None)
    )
    epoch_getter = getattr(dataset, "get_epoch_data", None)
    epoch_data = epoch_getter() if callable(epoch_getter) else None
    if epoch_data is None:
        raise SaliencyRenderPublisher._target_error(
            "EEG epoch data is no longer available"
        )
    return epoch_data


def _saliency_producer_identity(
    holder: Any,
    run: Any,
    eval_record: Any,
) -> Any | None:
    builder = getattr(holder, "build_saliency_producer_identity", None)
    source_split = _record_source_split(eval_record)
    if not callable(builder) or source_split not in {"test", "validation"}:
        return None
    return builder(run, evaluation_split=source_split)


def _context_axis_identity(context: Any) -> tuple[Any, ...]:
    return (
        tuple(getattr(context, "class_map", ())),
        tuple(getattr(context, "channel_names", ())),
        float(context.sampling_frequency_hz),
        float(context.epoch_start_seconds),
        float(context.epoch_end_seconds),
        int(context.epoch_sample_count),
        getattr(context, "montage_fingerprint", None),
        str(context.epoch_data_fingerprint),
    )


def _ordered_store_keys(
    store: Mapping[object, Any],
    class_map: tuple[tuple[object, str], ...],
) -> tuple[object, ...] | None:
    indexed = tuple(range(len(class_map)))
    if all(key in store for key in indexed):
        return indexed
    event_codes = tuple(key for key, _name in class_map)
    if all(key in store for key in event_codes):
        return event_codes
    names = tuple(name for _key, name in class_map)
    if all(name in store for name in names):
        return names
    return None


def _validated_method_shape(
    records: list[Any],
    method: str,
    class_map: tuple[tuple[object, str], ...],
) -> tuple[tuple[object, ...], tuple[int, int]] | None:
    attribute = SALIENCY_METHOD_ATTRIBUTES[method]
    expected_keys: tuple[object, ...] | None = None
    trailing_shape: tuple[int, int] | None = None
    for record in records:
        store = getattr(record, attribute, None)
        if not isinstance(store, Mapping) or not store:
            return None
        keys = _ordered_store_keys(store, class_map)
        if keys is None or (expected_keys is not None and keys != expected_keys):
            return None
        expected_keys = keys
        labels = np.asarray(getattr(record, "label", None))
        if labels.ndim != 1:
            return None
        for class_index, key in enumerate(keys):
            values = np.asarray(store[key])
            if (
                values.ndim != 3
                or values.shape[0] < 1
                or values.shape[0] != int(np.count_nonzero(labels == class_index))
                or not np.issubdtype(values.dtype, np.number)
                or not np.isfinite(values).all()
            ):
                return None
            shape = (int(values.shape[1]), int(values.shape[2]))
            if trailing_shape is None:
                trailing_shape = shape
            elif shape != trailing_shape:
                return None
    if expected_keys is None or trailing_shape is None:
        return None
    return expected_keys, trailing_shape


def build_saliency_cross_fold_choices(
    plans: Iterable[Any],
) -> tuple[SaliencyCrossFoldChoice, ...]:
    """Publish pooled out-of-fold summaries admitted by Evaluation evidence."""
    indexed_plans = list(plans)
    choices: list[SaliencyCrossFoldChoice] = []
    for evaluation_choice in build_evaluation_cross_fold_choices(indexed_plans):
        try:
            validated = _validate_saliency_cross_fold_choice(
                indexed_plans,
                evaluation_choice,
            )
        except (AssertionError, TypeError, ValueError):
            continue
        choices.append(validated.choice)
    return tuple(choices)


def _saliency_members(evaluation_choice: Any) -> tuple[SaliencyRunIdentity, ...]:
    return tuple(
        SaliencyRunIdentity(
            plan=SaliencyPlanIdentity(member.plan.plan_index),
            run_index=member.run_index,
        )
        for member in evaluation_choice.identity.members
    )


def _validate_saliency_cross_fold_choice(
    indexed_plans: list[Any],
    evaluation_choice: Any,
) -> _ValidatedSaliencyCrossFoldChoice:
    members = _saliency_members(evaluation_choice)
    records: list[Any] = []
    contexts: list[Any] = []
    epoch_data_items: list[Any] = []
    source_splits: set[str] = set()
    repeats: set[int] = set()
    saliency_params: list[dict[str, Any]] = []
    for member in members:
        holder, run = _holder_and_run(indexed_plans, member)
        repeat = getattr(run, "repeat", None)
        if isinstance(repeat, bool) or not isinstance(repeat, int):
            raise ValueError("cross-fold run repeat is unavailable")
        repeats.add(repeat)
        record = _saliency_eval_record(run)
        if record is None:
            raise ValueError("cross-fold saliency record is unavailable")
        source_split = _record_source_split(record)
        if source_split != "test":
            raise ValueError("cross-fold saliency must use test data")
        source_splits.add(source_split)
        producer_identity = _saliency_producer_identity(holder, run, record)
        validator = getattr(record, "validate_saliency_context", None)
        if producer_identity is None or not callable(validator):
            raise ValueError("saliency provenance is unavailable")
        epoch_data = _epoch_data_for_holder(holder)
        context = validator(
            epoch_data,
            producer_identity=producer_identity,
        )
        records.append(record)
        contexts.append(context)
        epoch_data_items.append(epoch_data)
        params_getter = getattr(holder, "get_saliency_params", None)
        params = (
            params_getter()
            if callable(params_getter)
            else getattr(holder, "saliency_params", {})
        )
        saliency_params.append(dict(params) if isinstance(params, Mapping) else {})
    if len(repeats) != 1 or len(source_splits) != 1:
        raise ValueError("cross-fold run identity differs")
    if any(params != saliency_params[0] for params in saliency_params[1:]):
        raise ValueError("cross-fold saliency settings differ")
    axis_identities = {_context_axis_identity(context) for context in contexts}
    if len(axis_identities) != 1:
        raise ValueError("cross-fold EEG axes differ")
    class_map = tuple(getattr(contexts[0], "class_map", ()))
    if not class_map:
        raise ValueError("cross-fold class map is unavailable")
    methods: list[str] = []
    class_store_keys: tuple[object, ...] | None = None
    for method in SALIENCY_METHOD_ATTRIBUTES:
        method_shape = _validated_method_shape(records, method, class_map)
        if method_shape is None:
            continue
        store_keys, _shape = method_shape
        if class_store_keys is None:
            class_store_keys = store_keys
        elif class_store_keys != store_keys:
            continue
        methods.append(method)
    if not methods or class_store_keys is None:
        raise ValueError("cross-fold methods are incomplete")
    return _ValidatedSaliencyCrossFoldChoice(
        choice=SaliencyCrossFoldChoice(
            identity=SaliencyCrossFoldIdentity(members=members),
            display_name=evaluation_choice.display_name,
            run_label=evaluation_choice.run_label,
            methods=tuple(methods),
            source_split="test",
            classes=tuple(
                SaliencyCrossFoldClass(
                    class_index=index,
                    display_name=str(class_map[index][1]),
                    event_code=class_map[index][0],
                    store_key=store_key,
                )
                for index, store_key in enumerate(class_store_keys)
            ),
        ),
        records=tuple(records),
        contexts=tuple(contexts),
        epoch_data=tuple(epoch_data_items),
    )


def _normalize_saliency_store(
    store: Mapping[object, Any],
) -> dict[object, np.ndarray]:
    arrays = {key: np.asarray(value) for key, value in store.items()}
    if not arrays:
        raise PreconditionError(
            "Saliency data is unavailable for normalization",
            diagnostics={"retryable": False},
        )
    if any(not np.isfinite(values).all() for values in arrays.values()):
        raise PreconditionError(
            "Saliency data contains non-finite values",
            diagnostics={"retryable": False},
        )
    scale = max(
        float(np.max(np.abs(values), initial=0.0)) for values in arrays.values()
    )
    if scale <= np.finfo(np.float64).eps:
        return {key: np.array(values, copy=True) for key, values in arrays.items()}
    normalized: dict[object, np.ndarray] = {}
    for key, values in arrays.items():
        output_dtype = (
            values.dtype
            if np.issubdtype(values.dtype, np.floating)
            else np.dtype(np.float64)
        )
        destination = np.empty(values.shape, dtype=output_dtype)
        np.divide(
            values,
            np.asarray(scale, dtype=output_dtype),
            out=destination,
        )
        normalized[key] = destination
    return normalized


def _pool_cross_fold_saliency(
    fold_stores: tuple[Mapping[object, Any], ...],
    classes: tuple[SaliencyCrossFoldClass, ...],
    *,
    normalize: bool,
) -> dict[object, np.ndarray]:
    """Pool every admitted fold once into final owned render arrays."""
    arrays_by_key = {
        item.store_key: tuple(
            np.asarray(store[item.store_key]) for store in fold_stores
        )
        for item in classes
    }
    if not normalize:
        return {
            key: np.concatenate(arrays, axis=0) for key, arrays in arrays_by_key.items()
        }

    scale = max(
        float(np.max(np.abs(values), initial=0.0))
        for arrays in arrays_by_key.values()
        for values in arrays
    )
    if scale <= np.finfo(np.float64).eps:
        return {
            key: np.concatenate(arrays, axis=0) for key, arrays in arrays_by_key.items()
        }

    pooled: dict[object, np.ndarray] = {}
    for key, arrays in arrays_by_key.items():
        total_epochs = sum(int(values.shape[0]) for values in arrays)
        source_dtype = np.result_type(*(values.dtype for values in arrays))
        output_dtype = (
            source_dtype
            if np.issubdtype(source_dtype, np.floating)
            else np.dtype(np.float64)
        )
        destination = np.empty(
            (total_epochs, *arrays[0].shape[1:]),
            dtype=output_dtype,
        )
        offset = 0
        for values in arrays:
            next_offset = offset + int(values.shape[0])
            np.divide(
                values,
                np.asarray(scale, dtype=output_dtype),
                out=destination[offset:next_offset],
            )
            offset = next_offset
        pooled[key] = destination
    return pooled


def normalized_saliency_render_publication(
    publication: SaliencyRenderPublication,
) -> SaliencyRenderPublication:
    """Derive the existing display normalization from a verified raw DTO."""
    if not isinstance(publication, SaliencyRenderPublication):
        raise TypeError("publication must be a SaliencyRenderPublication")
    if publication.request.normalize:
        if not publication.data.normalized:
            raise ValueError("normalized render request contains raw saliency data")
        return publication
    if publication.data.normalized:
        raise ValueError("raw render request contains normalized saliency data")

    source = publication.data
    normalized_data = SaliencyRenderData(
        method=source.method,
        saliency_by_class=_normalize_saliency_store(source.saliency_by_class),
        class_map=source.class_map,
        event_ids=source.event_ids,
        channel_names=source.channel_names,
        channel_positions=source.channel_positions,
        sfreq=source.sfreq,
        tmin=source.tmin,
        source_split=source.source_split,
        aggregation=source.aggregation,
        fold_count=source.fold_count,
        normalized=True,
        _detached_arrays=_DETACHED_SALIENCY_ARRAYS,
    )
    return SaliencyRenderPublication(
        request=replace(publication.request, normalize=True),
        generation=publication.generation,
        training_generation=publication.training_generation,
        data=normalized_data,
    )


class SaliencyRenderPublisher:
    """Copy one domain render target across a verified read boundary."""

    def __init__(
        self,
        *,
        training_runtime: TrainingRuntimePort,
        get_publication: Callable[[], ApplicationViewPublication],
        capture_training_boundary: Callable[[], TrainingReadBoundary],
        effective_montage_provider: Callable[[], Any] | None = None,
    ) -> None:
        self._training_runtime = training_runtime
        self._get_publication = get_publication
        self._capture_training_boundary = capture_training_boundary
        self._effective_montage_provider = effective_montage_provider

    def publish(self, request: SaliencyRenderRequest) -> SaliencyRenderPublication:
        """Return a detached payload or reject a generation-crossing read."""
        if not isinstance(request, SaliencyRenderRequest):
            raise TypeError("request must be a SaliencyRenderRequest")
        before_publication = self._get_publication()
        before_boundary = self._capture_training_boundary()
        self._validate_guard(
            request,
            publication=before_publication,
            boundary=before_boundary,
        )

        data = self._copy_render_data(request)

        after_boundary = self._capture_training_boundary()
        after_publication = self._get_publication()
        if (
            after_publication.generation != before_publication.generation
            or after_publication.usable is False
            or after_boundary != before_boundary
            or not after_boundary.stable
        ):
            raise self._stale_error(
                request,
                before_publication,
                after_publication,
                before_boundary,
                after_boundary,
            )
        self._validate_guard(
            request,
            publication=after_publication,
            boundary=after_boundary,
        )
        return SaliencyRenderPublication(
            request=request,
            generation=after_publication.generation,
            training_generation=after_boundary.token.generation,
            data=data,
        )

    def _validate_guard(
        self,
        request: SaliencyRenderRequest,
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
                publication,
                publication,
                boundary,
                boundary,
            )

    def _copy_render_data(self, request: SaliencyRenderRequest) -> SaliencyRenderData:
        if not self._training_runtime.has_trainer():
            raise self._target_error("Training results are no longer available")
        holders = self._iterable_items(
            self._training_runtime.training_plan_holders(),
            "Training plan collection",
        )
        if isinstance(request.run, SaliencyCrossFoldIdentity):
            return self._copy_cross_fold_render_data(request, holders)
        return self._copy_single_run_render_data(request, holders)

    def _copy_single_run_render_data(
        self,
        request: SaliencyRenderRequest,
        holders: list[Any],
    ) -> SaliencyRenderData:
        if not isinstance(request.run, SaliencyRunIdentity):
            raise TypeError("single-run render requires a SaliencyRunIdentity")
        plan_index = request.run.plan.plan_index
        if plan_index >= len(holders):
            raise self._target_error(
                "The selected training plan is no longer available"
            )
        holder = holders[plan_index]
        runs_getter = getattr(holder, "get_plans", None)
        runs = (
            self._iterable_items(runs_getter(), "Training run collection")
            if callable(runs_getter)
            else []
        )
        if request.run.run_index >= len(runs):
            raise self._target_error("The selected training run is no longer available")
        run = runs[request.run.run_index]
        eval_record = _saliency_eval_record(run)
        if eval_record is None:
            raise self._target_error("The selected run has no evaluation record")

        dataset_getter = getattr(holder, "get_dataset", None)
        dataset = (
            dataset_getter()
            if callable(dataset_getter)
            else getattr(holder, "dataset", None)
        )
        epoch_getter = getattr(dataset, "get_epoch_data", None)
        epoch_data = epoch_getter() if callable(epoch_getter) else None
        if epoch_data is None:
            raise self._target_error("EEG epoch data is no longer available")

        saliency_store = self._saliency_store(eval_record, request.method)
        class_map = self._validated_class_map(
            eval_record,
            epoch_data,
            producer_identity=_saliency_producer_identity(holder, run, eval_record),
        )
        if request.normalize:
            saliency_store = _normalize_saliency_store(saliency_store)
        return self._render_data_from_epoch(
            request=request,
            epoch_data=epoch_data,
            saliency_store=saliency_store,
            class_map=class_map,
            source_split=_record_source_split(eval_record),
            aggregation="per-epoch",
            fold_count=1,
        )

    def _copy_cross_fold_render_data(
        self,
        request: SaliencyRenderRequest,
        holders: list[Any],
    ) -> SaliencyRenderData:
        if not isinstance(request.run, SaliencyCrossFoldIdentity):
            raise TypeError("cross-fold render requires a SaliencyCrossFoldIdentity")
        evaluation_choice = next(
            (
                candidate
                for candidate in build_evaluation_cross_fold_choices(holders)
                if SaliencyCrossFoldIdentity(
                    members=_saliency_members(candidate),
                )
                == request.run
            ),
            None,
        )
        if evaluation_choice is None:
            raise self._target_error(
                "The selected cross-fold saliency summary is no longer available"
            )
        try:
            validated = _validate_saliency_cross_fold_choice(
                holders,
                evaluation_choice,
            )
        except (AssertionError, TypeError, ValueError):
            raise self._target_error(
                "The selected cross-fold saliency summary is no longer available"
            ) from None
        choice = validated.choice
        if choice.identity != request.run or request.method not in choice.methods:
            raise self._target_error(
                "The selected cross-fold saliency summary is no longer available"
            )

        if not validated.epoch_data or not validated.contexts:
            raise self._target_error("Cross-fold epoch metadata is unavailable")
        fold_stores = tuple(
            self._saliency_store(record, request.method) for record in validated.records
        )
        aggregated = _pool_cross_fold_saliency(
            fold_stores,
            choice.classes,
            normalize=request.normalize,
        )
        first_class_map = tuple(
            (key, str(name))
            for key, name in getattr(validated.contexts[0], "class_map", ())
        )
        if not first_class_map:
            raise self._target_error("Cross-fold class metadata is unavailable")
        return self._render_data_from_epoch(
            request=request,
            epoch_data=validated.epoch_data[0],
            saliency_store=aggregated,
            class_map=first_class_map,
            source_split=choice.source_split,
            aggregation="pooled out-of-fold epochs",
            fold_count=len(choice.identity.members),
            adopt_saliency_store=True,
        )

    def _render_data_from_epoch(
        self,
        *,
        request: SaliencyRenderRequest,
        epoch_data: Any,
        saliency_store: Mapping[object, Any],
        class_map: tuple[tuple[object, str], ...],
        source_split: str,
        aggregation: str,
        fold_count: int,
        adopt_saliency_store: bool = False,
    ) -> SaliencyRenderData:
        event_ids = getattr(epoch_data, "event_id", {}) or {}
        if not isinstance(event_ids, Mapping):
            raise PreconditionError(
                "Saliency render event metadata is unavailable",
                diagnostics={"retryable": True},
            )
        channel_names = self._iterable_items(
            self._required_call(epoch_data, "get_channel_names"),
            "Channel-name collection",
        )
        positions_getter = getattr(epoch_data, "get_montage_position", None)
        positions = (
            self._iterable_items(
                positions_getter(),
                "Channel-position collection",
            )
            if callable(positions_getter)
            else []
        )
        if len(positions) != len(channel_names):
            positions = []
        if positions and request.view in _POSITION_DEPENDENT_VIEWS:
            geometry = project_montage_geometry(
                positions,
                coordinate_dimension=3,
            )
            if not geometry.supports_view(request.view):
                raise self._position_precondition_error(request.view)
            positions = list(geometry.positions)
        if not positions and request.view in _POSITION_DEPENDENT_VIEWS:
            projection = self._automatic_montage_projection(
                channel_names,
                view=request.view,
            )
            if projection is not None:
                projected_names, positions, channel_indexes = projection
                if channel_indexes != tuple(range(len(channel_names))):
                    saliency_store = self._select_saliency_channels(
                        saliency_store,
                        channel_indexes,
                        expected_channel_count=len(channel_names),
                    )
                    channel_names = list(projected_names)
            if not positions:
                raise self._position_precondition_error(request.view)
        model_args = self._required_call(epoch_data, "get_model_args")
        sfreq = model_args.get("sfreq") if isinstance(model_args, dict) else None
        if sfreq is None:
            sfreq = getattr(epoch_data, "sfreq", None)
        if sfreq is None:
            raise PreconditionError(
                "Saliency render sampling frequency is unavailable",
                diagnostics={"retryable": True},
            )
        return SaliencyRenderData(
            method=request.method,
            saliency_by_class=saliency_store,
            class_map=class_map,
            event_ids=event_ids,
            channel_names=tuple(channel_names or ()),
            channel_positions=tuple(tuple(position) for position in positions),
            sfreq=float(sfreq),
            tmin=float(getattr(epoch_data, "tmin", 0.0)),
            source_split=source_split,
            aggregation=aggregation,
            fold_count=fold_count,
            normalized=request.normalize,
            _detached_arrays=(
                _DETACHED_SALIENCY_ARRAYS if adopt_saliency_store else None
            ),
        )

    def _automatic_montage_projection(
        self,
        channel_names: list[Any],
        *,
        view: str,
    ) -> (
        tuple[
            tuple[str, ...],
            list[tuple[float, float, float]],
            tuple[int, ...],
        ]
        | None
    ):
        provider = self._effective_montage_provider
        if provider is None:
            return None
        try:
            montage = provider()
        except Exception:
            return None
        if montage is None or getattr(montage, "source", None) != "bids":
            return None
        names = tuple(str(name) for name in getattr(montage, "channel_names", ()))
        positions: tuple[object, ...] = tuple(getattr(montage, "positions_m", ()))
        if len(names) != len(positions) or len(set(names)) != len(names):
            return None
        by_name = dict(zip(names, positions, strict=True))
        selected_names: list[str] = []
        ordered: list[object] = []
        channel_indexes: list[int] = []
        for index, channel_name in enumerate(channel_names):
            normalized_name = str(channel_name)
            source_position = by_name.get(normalized_name)
            if source_position is None:
                continue
            selected_names.append(normalized_name)
            ordered.append(source_position)
            channel_indexes.append(index)
        if not selected_names:
            return None
        raw_coordinate_dimension = getattr(montage, "coordinate_dimension", 3)
        coordinate_dimension: MontageCoordinateDimension | None
        if raw_coordinate_dimension == 2:
            coordinate_dimension = 2
        elif raw_coordinate_dimension == 3:
            coordinate_dimension = 3
        else:
            coordinate_dimension = None
        geometry = project_montage_geometry(
            ordered,
            coordinate_dimension=coordinate_dimension,
        )
        supports_topographic = geometry.supports_topographic and bool(
            getattr(
                montage,
                "supports_topographic",
                geometry.supports_topographic,
            )
        )
        supports_three_dimensional = geometry.supports_three_dimensional and bool(
            getattr(
                montage,
                "supports_three_dimensional",
                geometry.supports_three_dimensional,
            )
        )
        if view == "topographic_map" and not supports_topographic:
            return None
        if view == "three_dimensional" and not supports_three_dimensional:
            return None
        return (
            tuple(selected_names),
            list(geometry.positions),
            tuple(channel_indexes),
        )

    @staticmethod
    def _position_precondition_error(view: str) -> PreconditionError:
        return PreconditionError(
            "The selected visualization requires compatible electrode positions.",
            diagnostics={"retryable": True, "view": view},
        )

    @staticmethod
    def _select_saliency_channels(
        saliency_store: Mapping[object, Any],
        channel_indexes: tuple[int, ...],
        *,
        expected_channel_count: int,
    ) -> dict[object, np.ndarray]:
        selected: dict[object, np.ndarray] = {}
        for key, raw_values in saliency_store.items():
            values = np.asarray(raw_values)
            if values.ndim < 2 or values.shape[1] != expected_channel_count:
                raise PreconditionError(
                    "Saliency channel metadata does not match the prepared montage",
                    diagnostics={"retryable": False},
                )
            selected[key] = np.take(values, channel_indexes, axis=1)
        return selected

    @staticmethod
    def _validated_class_map(
        eval_record: Any,
        epoch_data: Any,
        *,
        producer_identity: Any | None = None,
    ) -> tuple[tuple[object, str], ...]:
        validator = getattr(eval_record, "validate_saliency_context", None)
        if not callable(validator):
            raise PreconditionError(
                "Saliency identity context is unavailable. Recompute saliency "
                "before rendering.",
                diagnostics={"retryable": False},
            )
        context = validator(epoch_data, producer_identity=producer_identity)
        class_map = getattr(context, "class_map", None)
        if not class_map:
            raise PreconditionError(
                "Saliency identity context has no class mapping. Recompute "
                "saliency before rendering.",
                diagnostics={"retryable": False},
            )
        return tuple((key, str(name)) for key, name in class_map)

    @staticmethod
    def _saliency_store(eval_record: Any, method: str) -> Mapping[object, Any]:
        attribute = SALIENCY_METHOD_ATTRIBUTES.get(method)
        if attribute is None:
            raise PreconditionError(
                f"Unknown saliency method: {method}",
                diagnostics={"retryable": False},
            )
        store = getattr(eval_record, attribute, None)
        if not isinstance(store, Mapping) or not store:
            raise PreconditionError(
                f"No {method} saliency is available for this run",
                diagnostics={"retryable": False},
            )
        return store

    @staticmethod
    def _required_call(target: Any, method_name: str) -> Any:
        method = getattr(target, method_name, None)
        if not callable(method):
            raise PreconditionError(
                f"Saliency render metadata {method_name} is unavailable",
                diagnostics={"retryable": True},
            )
        return method()

    @staticmethod
    def _iterable_items(value: object, description: str) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, (str, bytes, Mapping)) or not isinstance(
            value,
            Iterable,
        ):
            raise PreconditionError(
                f"{description} is unavailable",
                diagnostics={"retryable": True},
            )
        return list(value)

    @staticmethod
    def _target_error(message: str) -> PreconditionError:
        return PreconditionError(
            f"{message}. Refresh Visualization and try again.",
            diagnostics={
                "saliency_render_stale": True,
                "retryable": True,
            },
        )

    @staticmethod
    def _stale_error(
        request: SaliencyRenderRequest,
        before_publication: ApplicationViewPublication,
        after_publication: ApplicationViewPublication,
        before_boundary: TrainingReadBoundary,
        after_boundary: TrainingReadBoundary,
    ) -> PreconditionError:
        return PreconditionError(
            "Visualization results changed while render data was being read. "
            "Refresh Visualization and try again.",
            diagnostics={
                "saliency_render_stale": True,
                "training_state_changed": before_boundary != after_boundary
                or not after_boundary.stable,
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


__all__ = [
    "SaliencyCrossFoldChoice",
    "SaliencyCrossFoldClass",
    "SaliencyCrossFoldIdentity",
    "SaliencyPlanIdentity",
    "SaliencyRenderData",
    "SaliencyRenderPublication",
    "SaliencyRenderPublisher",
    "SaliencyRenderRequest",
    "SaliencyRunIdentity",
    "SaliencySelectionIdentity",
    "build_saliency_cross_fold_choices",
    "normalized_saliency_render_publication",
]
