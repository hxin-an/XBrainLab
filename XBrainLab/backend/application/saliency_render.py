"""Typed, detached saliency render publications for UI consumers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import numpy as np

from XBrainLab.backend.training_state_contract import TrainingReadBoundary

from .errors import PreconditionError
from .training_runtime import TrainingRuntimePort
from .view_publication import ApplicationViewPublication


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


@dataclass(frozen=True)
class SaliencyRenderRequest:
    """Request one method payload from an exact application generation."""

    publication_generation: int
    run: SaliencyRunIdentity
    method: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.publication_generation, bool)
            or not isinstance(self.publication_generation, int)
            or self.publication_generation < 1
        ):
            raise ValueError("publication_generation must be a positive integer")
        if not isinstance(self.run, SaliencyRunIdentity):
            raise TypeError("run must be a SaliencyRunIdentity")
        method = str(self.method).strip()
        if not method:
            raise ValueError("method must be a non-empty string")
        object.__setattr__(self, "method", method)


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

    def __post_init__(self) -> None:
        method = str(self.method).strip()
        if not method:
            raise ValueError("render method must be a non-empty string")
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


class SaliencyRenderPublisher:
    """Copy one domain render target across a verified read boundary."""

    def __init__(
        self,
        *,
        training_runtime: TrainingRuntimePort,
        get_publication: Callable[[], ApplicationViewPublication],
        capture_training_boundary: Callable[[], TrainingReadBoundary],
    ) -> None:
        self._training_runtime = training_runtime
        self._get_publication = get_publication
        self._capture_training_boundary = capture_training_boundary

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
        record_getter = getattr(run, "get_eval_record", None)
        eval_record = (
            record_getter()
            if callable(record_getter)
            else getattr(run, "eval_record", None)
        )
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
        class_map = self._validated_class_map(eval_record, epoch_data)
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
        )

    @staticmethod
    def _validated_class_map(
        eval_record: Any,
        epoch_data: Any,
    ) -> tuple[tuple[object, str], ...]:
        validator = getattr(eval_record, "validate_saliency_context", None)
        if not callable(validator):
            raise PreconditionError(
                "Saliency identity context is unavailable. Recompute saliency "
                "before rendering.",
                diagnostics={"retryable": False},
            )
        context = validator(epoch_data)
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
        attribute = {
            "Gradient": "gradient",
            "Gradient * Input": "gradient_input",
            "SmoothGrad": "smoothgrad",
            "SmoothGrad_Squared": "smoothgrad_sq",
            "VarGrad": "vargrad",
        }.get(method)
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
