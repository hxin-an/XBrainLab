"""Canonical numeric contract for training configuration inputs."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from XBrainLab.backend.training_contract import (
    DEFAULT_TRAINING_OUTPUT_DIR as _DEFAULT_TRAINING_OUTPUT_DIR,
)
from XBrainLab.backend.training_contract import (
    TRAINING_MODEL_NAMES as _TRAINING_MODEL_NAMES,
)

REQUIRED_TRAINING_FIELDS = ("epoch", "batch_size", "learning_rate")
TRAINING_MODEL_NAMES = _TRAINING_MODEL_NAMES
DEFAULT_TRAINING_OUTPUT_DIR = _DEFAULT_TRAINING_OUTPUT_DIR
TRAINING_OPTIMIZER_NAMES = ("adam", "sgd", "adamw")
TRAINING_DEVICE_NAMES = ("cpu", "cuda")
TRAINING_EVALUATION_NAMES = ("val_loss", "val_auc", "val_acc", "last_epoch")


class TrainingInputContractError(ValueError):
    """Raised when training inputs cannot build a valid configuration."""

    def __init__(
        self,
        message: str,
        *,
        missing_fields: tuple[str, ...] = (),
    ) -> None:
        public_message = (
            message
            if type(message) is str
            else "The training configuration is invalid."
        )
        self.public_message = public_message
        super().__init__(public_message)
        self.missing_fields = missing_fields


@dataclass(frozen=True, slots=True)
class NormalizedTrainingInput:
    """Canonical core values ready for a training configuration command."""

    epoch: int
    batch_size: int
    learning_rate: float


def normalize_training_input(params: Mapping[str, Any]) -> NormalizedTrainingInput:
    """Validate and normalize the required epoch/batch/learning-rate triplet."""
    missing = tuple(
        field
        for field in REQUIRED_TRAINING_FIELDS
        if field not in params or params[field] is None
    )
    if missing:
        raise TrainingInputContractError(
            "Missing required training parameter(s): " + ", ".join(missing) + ".",
            missing_fields=missing,
        )

    return NormalizedTrainingInput(
        epoch=normalize_positive_integer("epoch", params["epoch"]),
        batch_size=normalize_positive_integer("batch_size", params["batch_size"]),
        learning_rate=normalize_positive_finite_float(
            "learning_rate",
            params["learning_rate"],
        ),
    )


def has_training_option_arguments(params: Mapping[str, Any]) -> bool:
    """Return whether a proposal contains any explicit core training option."""
    return any(
        field in params and params[field] is not None
        for field in REQUIRED_TRAINING_FIELDS
    )


def training_option_value_is_valid(field: str, value: Any) -> bool:
    """Validate one extracted value using the canonical numeric contract."""
    try:
        if field in {"epoch", "batch_size"}:
            normalize_positive_integer(field, value)
            return True
        if field == "learning_rate":
            normalize_positive_finite_float(field, value)
            return True
    except TrainingInputContractError:
        return False
    return False


def training_parameter_schema() -> dict[str, dict[str, Any]]:
    """Return strict JSON-schema fragments for prompt-facing tool calls.

    Internal command boundaries may normalize compatible numeric strings, but
    the published JSON contract must describe native JSON number types so a
    standards-compliant schema consumer enforces the same numeric constraints.
    """
    return {
        "epoch": {
            "type": "integer",
            "minimum": 1,
        },
        "batch_size": {
            "type": "integer",
            "minimum": 1,
        },
        "learning_rate": {
            "type": "number",
            "exclusiveMinimum": 0,
        },
    }


def positive_integer_parameter_schema(*, default: int) -> dict[str, Any]:
    """Return a strict schema fragment for a positive JSON integer."""
    return {
        "type": "integer",
        "minimum": 1,
        "default": default,
    }


def non_negative_integer_parameter_schema(*, default: int) -> dict[str, Any]:
    """Return a strict schema fragment for a non-negative JSON integer."""
    return {
        "type": "integer",
        "minimum": 0,
        "default": default,
    }


def normalize_positive_integer(field: str, value: Any) -> int:
    """Return an exact positive integer without silently truncating fractions."""
    return _normalize_integer(field, value, minimum=1)


def normalize_non_negative_integer(field: str, value: Any) -> int:
    """Return an exact non-negative integer without silent truncation."""
    return _normalize_integer(field, value, minimum=0)


def normalize_positive_finite_float(field: str, value: Any) -> float:
    """Return a finite floating-point value greater than zero."""
    return _normalize_finite_float(field, value, allow_zero=False)


def normalize_non_negative_finite_float(field: str, value: Any) -> float:
    """Return a finite floating-point value greater than or equal to zero."""
    return _normalize_finite_float(field, value, allow_zero=True)


def normalize_strict_boolean(field: str, value: Any) -> bool:
    """Return an exact boolean without Python truthiness coercion."""
    if type(value) is not bool:
        raise TrainingInputContractError(f"{field} must be a boolean.")
    return value


def _normalize_finite_float(
    field: str,
    value: Any,
    *,
    allow_zero: bool,
) -> float:
    qualifier = "non-negative" if allow_zero else "greater than zero"
    if isinstance(value, bool):
        raise TrainingInputContractError(f"{field} must be finite and {qualifier}.")
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TrainingInputContractError(
            f"{field} must be finite and {qualifier}."
        ) from exc
    if not math.isfinite(parsed) or parsed < 0 or (not allow_zero and parsed == 0):
        raise TrainingInputContractError(f"{field} must be finite and {qualifier}.")
    return parsed


def _normalize_integer(field: str, value: Any, *, minimum: int) -> int:
    if isinstance(value, bool):
        raise TrainingInputContractError(_integer_error(field, minimum))
    try:
        parsed = int(value)
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TrainingInputContractError(_integer_error(field, minimum)) from exc
    if not math.isfinite(numeric) or parsed < minimum or numeric != parsed:
        raise TrainingInputContractError(_integer_error(field, minimum))
    return parsed


def _integer_error(field: str, minimum: int) -> str:
    qualifier = "positive" if minimum == 1 else "non-negative"
    return f"{field} must be a {qualifier} integer."
