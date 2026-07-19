import math

import pytest

from XBrainLab.backend.training.input_contract import (
    REQUIRED_TRAINING_FIELDS,
    TrainingInputContractError,
    has_training_option_arguments,
    normalize_non_negative_finite_float,
    normalize_strict_boolean,
    normalize_training_input,
    training_option_value_is_valid,
)


def test_normalizes_complete_training_input_and_accepts_learning_rate_one():
    normalized = normalize_training_input(
        {"epoch": "10", "batch_size": 32.0, "learning_rate": 1},
    )

    assert normalized.epoch == 10
    assert normalized.batch_size == 32
    assert normalized.learning_rate == 1.0


def test_missing_training_fields_are_reported_together():
    with pytest.raises(TrainingInputContractError) as error:
        normalize_training_input({"epoch": 10})

    assert REQUIRED_TRAINING_FIELDS == (
        "epoch",
        "batch_size",
        "learning_rate",
    )
    assert error.value.missing_fields == ("batch_size", "learning_rate")


@pytest.mark.parametrize("value", (0, -0.1, math.inf, -math.inf, math.nan, True))
def test_learning_rate_must_be_positive_and_finite(value: object):
    assert not training_option_value_is_valid("learning_rate", value)


def test_training_option_presence_does_not_require_completeness():
    assert has_training_option_arguments({"epoch": 10})
    assert not has_training_option_arguments({"model_name": "EEGNet"})


def test_non_negative_finite_float_accepts_exact_zero():
    assert normalize_non_negative_finite_float("learning_rate", "0") == 0.0


@pytest.mark.parametrize("value", (-0.1, math.inf, -math.inf, math.nan, True))
def test_non_negative_finite_float_rejects_invalid_values(value: object):
    with pytest.raises(TrainingInputContractError):
        normalize_non_negative_finite_float("learning_rate", value)


@pytest.mark.parametrize("value", ("false", "true", 0, 1, None))
def test_strict_boolean_rejects_truthy_and_falsy_coercions(value: object):
    with pytest.raises(TrainingInputContractError, match="must be a boolean"):
        normalize_strict_boolean("confirmed", value)


def test_strict_boolean_preserves_exact_values():
    assert normalize_strict_boolean("confirmed", True) is True
    assert normalize_strict_boolean("confirmed", False) is False
