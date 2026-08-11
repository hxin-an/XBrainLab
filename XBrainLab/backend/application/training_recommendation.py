"""Deterministic starting-parameter recommendations for EEG training.

This module owns both recommendation formulas and per-field provenance. The
result is a conservative starting point; final training admission remains the
responsibility of the existing resource preflight.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum
from threading import RLock
from typing import Any

RECOMMENDATION_PROFILE_VERSION = "training-start-v1"
SAFE_UNKNOWN_VRAM_BATCH_SIZE = 8
CPU_BATCH_SIZE_CAP = 32
SMALL_DATASET_SAMPLE_LIMIT = 128
MEDIUM_DATASET_SAMPLE_LIMIT = 512
LARGE_DATASET_SAMPLE_LIMIT = 2_048
HIGH_DIMENSIONAL_EPOCH_SIZE = 32_768
VERY_HIGH_DIMENSIONAL_EPOCH_SIZE = 65_536
VALIDATION_LOSS_STRATEGY = "Best validation loss"
LAST_EPOCH_STRATEGY = "Last Epoch"

_STARTING_POINT_WARNING = (
    "These values are a conservative starting point, not a claim of best parameters."
)
_FINAL_PREFLIGHT_WARNING = (
    "Start Training final resource preflight remains authoritative."
)


class TrainingRecommendationField(str, Enum):
    """The five fields controlled by the recommendation service."""

    EPOCHS = "epochs"
    BATCH_SIZE = "batch_size"
    LEARNING_RATE = "learning_rate"
    OPTIMIZER = "optimizer"
    EVALUATION_STRATEGY = "evaluation_strategy"


class TrainingSettingProvenance(str, Enum):
    """Whether one effective field follows the recommendation or the user."""

    RECOMMENDED = "recommended"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class TrainingRecommendationValues:
    """The five typed values exposed to UI, assistant, and scripts."""

    epochs: int
    batch_size: int
    learning_rate: float
    optimizer: str
    evaluation_strategy: str

    def to_mapping(self) -> dict[TrainingRecommendationField, int | float | str]:
        """Return values keyed by the public recommendation fields."""
        return {
            TrainingRecommendationField.EPOCHS: self.epochs,
            TrainingRecommendationField.BATCH_SIZE: self.batch_size,
            TrainingRecommendationField.LEARNING_RATE: self.learning_rate,
            TrainingRecommendationField.OPTIMIZER: self.optimizer,
            TrainingRecommendationField.EVALUATION_STRATEGY: (self.evaluation_strategy),
        }

    @classmethod
    def from_mapping(
        cls,
        values: dict[TrainingRecommendationField, int | float | str],
    ) -> TrainingRecommendationValues:
        """Build typed values from one complete field mapping."""
        return cls(
            epochs=int(values[TrainingRecommendationField.EPOCHS]),
            batch_size=int(values[TrainingRecommendationField.BATCH_SIZE]),
            learning_rate=float(values[TrainingRecommendationField.LEARNING_RATE]),
            optimizer=str(values[TrainingRecommendationField.OPTIMIZER]),
            evaluation_strategy=str(
                values[TrainingRecommendationField.EVALUATION_STRATEGY]
            ),
        )


@dataclass(frozen=True, slots=True)
class TrainingRecommendationReason:
    """Explain one deterministic field decision."""

    field: TrainingRecommendationField
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class TrainingRecommendation:
    """Typed recommendation plus effective values and provenance."""

    context_fingerprint: str
    recommended_values: TrainingRecommendationValues
    values: TrainingRecommendationValues
    provenance: dict[str, TrainingSettingProvenance]
    reasons: tuple[TrainingRecommendationReason, ...]
    warnings: tuple[str, ...]
    profile_version: str = RECOMMENDATION_PROFILE_VERSION
    is_starting_point: bool = True

    @property
    def manual_fields(self) -> tuple[TrainingRecommendationField, ...]:
        """Return manual fields in stable public-contract order."""
        return tuple(
            field
            for field in TrainingRecommendationField
            if self.provenance.get(field.value) is TrainingSettingProvenance.MANUAL
        )

    def with_user_values(
        self,
        values: Mapping[Any, int | float | str],
    ) -> TrainingRecommendation:
        """Apply explicitly edited values and retain their manual provenance."""
        effective = self.values.to_mapping()
        provenance = dict(self.provenance)
        for raw_field, value in values.items():
            try:
                field = (
                    raw_field
                    if isinstance(raw_field, TrainingRecommendationField)
                    else TrainingRecommendationField(str(raw_field))
                )
            except ValueError:
                continue
            effective[field] = value
            provenance[field.value] = TrainingSettingProvenance.MANUAL

        return replace(
            self,
            values=TrainingRecommendationValues.from_mapping(effective),
            provenance=provenance,
        )

    def with_submitted_values(
        self,
        values: Mapping[Any, int | float | str],
        *,
        edited_fields: frozenset[TrainingRecommendationField],
    ) -> TrainingRecommendation:
        """Reconcile one saved option while honoring explicit edit provenance."""
        effective = self.values.to_mapping()
        recommended = self.recommended_values.to_mapping()
        provenance = dict(self.provenance)
        for raw_field, value in values.items():
            try:
                field = (
                    raw_field
                    if isinstance(raw_field, TrainingRecommendationField)
                    else TrainingRecommendationField(str(raw_field))
                )
            except ValueError:
                continue
            was_manual = provenance.get(field.value) is TrainingSettingProvenance.MANUAL
            if field in edited_fields or was_manual:
                effective[field] = value
                provenance[field.value] = TrainingSettingProvenance.MANUAL
            else:
                effective[field] = recommended[field]
                provenance[field.value] = TrainingSettingProvenance.RECOMMENDED
        return replace(
            self,
            values=TrainingRecommendationValues.from_mapping(effective),
            provenance=provenance,
        )

    def refresh_from(
        self,
        recommendation: TrainingRecommendation,
    ) -> TrainingRecommendation:
        """Carry only current manual values into a new context recommendation."""
        preserved = {
            field: self.values.to_mapping()[field] for field in self.manual_fields
        }
        return recommendation.with_user_values(preserved)


@dataclass(frozen=True, slots=True)
class TrainingRecommendationContext:
    """Serializable context inputs that may change a recommendation."""

    model_name: str | None
    model_params: dict[str, Any]
    epoch_count: int | None
    n_channels: int | None
    n_times: int | None
    dataset_count: int
    training_sample_count: int | None
    validation_sample_count: int | None
    device: str


@dataclass(frozen=True, slots=True)
class _ModelFamilyProfile:
    name: str
    epochs: int
    batch_size: int
    learning_rate: float
    optimizer: str


_COMPACT_PROFILE = _ModelFamilyProfile("compact_conv", 50, 64, 0.001, "Adam")
_DEEP_PROFILE = _ModelFamilyProfile("deep_conv", 60, 32, 0.0005, "AdamW")
_ATTENTION_PROFILE = _ModelFamilyProfile("attention", 75, 16, 0.0003, "AdamW")
_UNKNOWN_PROFILE = _ModelFamilyProfile("unknown", 40, 16, 0.0005, "Adam")

_COMPACT_MODEL_TOKENS = (
    "eegnet",
    "shallowconvnet",
    "shallowfbcspnet",
    "sccnet",
    "eeginceptionerp",
)
_DEEP_MODEL_TOKENS = ("deep4net", "eegnex", "eegitnet")
_ATTENTION_MODEL_TOKENS = ("eegconformer", "atcnet", "ctnet", "transformer")


class TrainingRecommendationService:
    """Own recommendation formulas and manual-override provenance."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._current: TrainingRecommendation | None = None
        self._context_key: str | None = None
        self._configuration_submission_pending: (
            frozenset[TrainingRecommendationField] | None
        ) = None

    def note_configuration_submitted(
        self,
        edited_fields: frozenset[TrainingRecommendationField]
        | set[TrainingRecommendationField],
    ) -> None:
        """Record exactly which recommendation fields the submitter edited."""
        with self._lock:
            self._configuration_submission_pending = frozenset(edited_fields)

    def cached_for_context(
        self,
        context: TrainingRecommendationContext,
    ) -> TrainingRecommendation | None:
        """Project a matching cached result without running recommendation logic."""
        context_key = _detached_context_key(context)
        with self._lock:
            if self._configuration_submission_pending is not None:
                return None
            if self._context_key != context_key:
                return None
            return self._current

    def for_state_snapshot(
        self,
        context: TrainingRecommendationContext,
        *,
        current_option: Any | None,
    ) -> TrainingRecommendation | None:
        """Consume a pending submission or return matching cached state only."""
        context_key = _detached_context_key(context)
        with self._lock:
            if self._configuration_submission_pending is not None:
                return self.recommend(context, current_option=current_option)
            if self._context_key != context_key:
                return None
            return self._current

    def clear(self) -> None:
        """Clear provenance when the application training configuration resets."""
        with self._lock:
            self._current = None
            self._context_key = None
            self._configuration_submission_pending = None

    def recommend(
        self,
        context: TrainingRecommendationContext,
        *,
        current_option: Any | None = None,
    ) -> TrainingRecommendation:
        """Return a cached recommendation derived only from detached metadata."""
        context_key = _detached_context_key(context)
        option_values = _values_from_training_option(current_option)
        with self._lock:
            current = self._current
            if current is not None and self._context_key == context_key:
                recommendation = current
            else:
                baseline = self._build_recommendation(context)
                recommendation = (
                    current.refresh_from(baseline) if current is not None else baseline
                )

            pending_fields = self._configuration_submission_pending
            if pending_fields is not None:
                if option_values is not None:
                    recommendation = recommendation.with_submitted_values(
                        option_values,
                        edited_fields=pending_fields,
                    )
                self._configuration_submission_pending = None
            self._current = recommendation
            self._context_key = context_key
            return recommendation

    def _build_recommendation(
        self,
        context: TrainingRecommendationContext,
    ) -> TrainingRecommendation:
        profile = _profile_for_model(context.model_name)
        sample_count = _positive_optional_int(
            context.training_sample_count
        ) or _positive_optional_int(context.epoch_count)
        epochs = _recommended_epochs(profile.epochs, sample_count)
        sample_cap = _dataset_batch_cap(sample_count)
        shape_cap = _epoch_shape_batch_cap(context.n_channels, context.n_times)
        candidate_batch = min(profile.batch_size, sample_cap, shape_cap)
        if sample_count is not None:
            candidate_batch = min(
                candidate_batch,
                _largest_power_of_two_at_most(sample_count),
            )
        candidate_batch = max(candidate_batch, 1)
        use_cpu = _uses_cpu(context.device)
        if use_cpu:
            device_cap = CPU_BATCH_SIZE_CAP
            device_warning = None
        else:
            device_cap = SAFE_UNKNOWN_VRAM_BATCH_SIZE
            device_warning = (
                "GPU memory is intentionally not queried while opening Training "
                f"Setting; batch size is capped at {SAFE_UNKNOWN_VRAM_BATCH_SIZE}."
            )
        batch_size = min(candidate_batch, device_cap)
        evaluation_strategy = (
            VALIDATION_LOSS_STRATEGY
            if (context.validation_sample_count or 0) > 0
            else LAST_EPOCH_STRATEGY
        )
        recommended = TrainingRecommendationValues(
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=profile.learning_rate,
            optimizer=profile.optimizer,
            evaluation_strategy=evaluation_strategy,
        )
        batch_reason = (
            f"Dataset cap {sample_cap}, epoch shape cap {shape_cap}, and "
            f"metadata-only device cap {device_cap} produced batch size "
            f"{batch_size}."
        )
        reasons = (
            TrainingRecommendationReason(
                TrainingRecommendationField.EPOCHS,
                "model_family_and_sample_count",
                (
                    f"{profile.name} profile with {sample_count or 'unknown'} "
                    "training samples sets a conservative epoch count."
                ),
            ),
            TrainingRecommendationReason(
                TrainingRecommendationField.BATCH_SIZE,
                "dataset_shape_and_metadata_caps",
                batch_reason,
            ),
            TrainingRecommendationReason(
                TrainingRecommendationField.LEARNING_RATE,
                "model_family_profile",
                f"{profile.name} uses learning rate {profile.learning_rate:g}.",
            ),
            TrainingRecommendationReason(
                TrainingRecommendationField.OPTIMIZER,
                "model_family_profile",
                f"{profile.name} uses {profile.optimizer} as its starting optimizer.",
            ),
            TrainingRecommendationReason(
                TrainingRecommendationField.EVALUATION_STRATEGY,
                "validation_availability",
                (
                    "Validation loss is available for checkpoint selection."
                    if evaluation_strategy == VALIDATION_LOSS_STRATEGY
                    else "No validation split is available, so the last epoch is used."
                ),
            ),
        )
        warnings = [_STARTING_POINT_WARNING, _FINAL_PREFLIGHT_WARNING]
        if sample_count is None:
            warnings.append(
                "Training sample count is unavailable; a conservative data cap "
                "was used."
            )
        elif sample_count < SMALL_DATASET_SAMPLE_LIMIT:
            warnings.append(
                "The training dataset is small; monitor overfitting and "
                "validation stability."
            )
        if evaluation_strategy == LAST_EPOCH_STRATEGY:
            warnings.append(
                "No validation split is available; validation-based checkpoint "
                "selection cannot be recommended."
            )
        if device_warning:
            warnings.append(device_warning)
        fingerprint = _context_fingerprint(
            context,
            profile=profile,
            recommended=recommended,
        )
        return TrainingRecommendation(
            context_fingerprint=fingerprint,
            recommended_values=recommended,
            values=recommended,
            provenance={
                field.value: TrainingSettingProvenance.RECOMMENDED
                for field in TrainingRecommendationField
            },
            reasons=reasons,
            warnings=tuple(warnings),
        )


def _profile_for_model(model_name: str | None) -> _ModelFamilyProfile:
    normalized = "".join(
        character for character in str(model_name or "").lower() if character.isalnum()
    )
    if any(token in normalized for token in _ATTENTION_MODEL_TOKENS):
        return _ATTENTION_PROFILE
    if any(token in normalized for token in _DEEP_MODEL_TOKENS):
        return _DEEP_PROFILE
    if any(token in normalized for token in _COMPACT_MODEL_TOKENS):
        return _COMPACT_PROFILE
    return _UNKNOWN_PROFILE


def _recommended_epochs(base_epochs: int, sample_count: int | None) -> int:
    if sample_count is None:
        return min(base_epochs, 40)
    if sample_count < SMALL_DATASET_SAMPLE_LIMIT:
        return min(base_epochs, 30)
    if sample_count < MEDIUM_DATASET_SAMPLE_LIMIT:
        return min(base_epochs, 40)
    return base_epochs


def _dataset_batch_cap(sample_count: int | None) -> int:
    if sample_count is None or sample_count < SMALL_DATASET_SAMPLE_LIMIT:
        return 8
    if sample_count < MEDIUM_DATASET_SAMPLE_LIMIT:
        return 16
    if sample_count < LARGE_DATASET_SAMPLE_LIMIT:
        return 32
    return 64


def _epoch_shape_batch_cap(n_channels: int | None, n_times: int | None) -> int:
    channels = _positive_optional_int(n_channels)
    times = _positive_optional_int(n_times)
    if channels is None or times is None:
        return 8
    epoch_size = channels * times
    if epoch_size >= VERY_HIGH_DIMENSIONAL_EPOCH_SIZE:
        return 8
    if epoch_size >= HIGH_DIMENSIONAL_EPOCH_SIZE:
        return 16
    return 64


def _largest_power_of_two_at_most(value: int) -> int:
    positive = max(int(value), 1)
    return 1 << (positive.bit_length() - 1)


def _positive_optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _uses_cpu(device: str) -> bool:
    return str(device or "auto").strip().lower().startswith("cpu")


def _values_from_training_option(
    option: Any | None,
) -> dict[TrainingRecommendationField, int | float | str] | None:
    if option is None:
        return None
    optimizer = getattr(option, "optim", None)
    optimizer_name = str(getattr(optimizer, "__name__", optimizer) or "")
    evaluation = getattr(option, "evaluation_option", None)
    evaluation_value = str(getattr(evaluation, "value", evaluation) or "")
    try:
        return {
            TrainingRecommendationField.EPOCHS: int(option.epoch),
            TrainingRecommendationField.BATCH_SIZE: int(option.bs),
            TrainingRecommendationField.LEARNING_RATE: float(option.lr),
            TrainingRecommendationField.OPTIMIZER: optimizer_name,
            TrainingRecommendationField.EVALUATION_STRATEGY: evaluation_value,
        }
    except (TypeError, ValueError):
        return None


def _context_fingerprint(
    context: TrainingRecommendationContext,
    *,
    profile: _ModelFamilyProfile,
    recommended: TrainingRecommendationValues,
) -> str:
    payload = {
        "profile_version": RECOMMENDATION_PROFILE_VERSION,
        "model_name": context.model_name,
        "model_params": context.model_params,
        "model_family": profile.name,
        "epoch_count": context.epoch_count,
        "n_channels": context.n_channels,
        "n_times": context.n_times,
        "dataset_count": context.dataset_count,
        "training_sample_count": context.training_sample_count,
        "validation_sample_count": context.validation_sample_count,
        "device": context.device,
        "recommended_values": {
            field.value: value for field, value in recommended.to_mapping().items()
        },
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _detached_context_key(context: TrainingRecommendationContext) -> str:
    payload = {
        "profile_version": RECOMMENDATION_PROFILE_VERSION,
        "model_name": context.model_name,
        "model_params": context.model_params,
        "epoch_count": context.epoch_count,
        "n_channels": context.n_channels,
        "n_times": context.n_times,
        "dataset_count": context.dataset_count,
        "training_sample_count": context.training_sample_count,
        "validation_sample_count": context.validation_sample_count,
        "device": context.device,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "CPU_BATCH_SIZE_CAP",
    "HIGH_DIMENSIONAL_EPOCH_SIZE",
    "LARGE_DATASET_SAMPLE_LIMIT",
    "MEDIUM_DATASET_SAMPLE_LIMIT",
    "RECOMMENDATION_PROFILE_VERSION",
    "SAFE_UNKNOWN_VRAM_BATCH_SIZE",
    "SMALL_DATASET_SAMPLE_LIMIT",
    "VERY_HIGH_DIMENSIONAL_EPOCH_SIZE",
    "TrainingRecommendation",
    "TrainingRecommendationContext",
    "TrainingRecommendationField",
    "TrainingRecommendationReason",
    "TrainingRecommendationService",
    "TrainingRecommendationValues",
    "TrainingSettingProvenance",
]
