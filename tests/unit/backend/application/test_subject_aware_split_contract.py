"""Public configuration contract for subject-aware dataset splitting."""

import pytest

from XBrainLab.backend.application.dataset_split_preview import (
    DatasetSplitContext,
    DatasetSplitSpecification,
)


def payload(test="By Trial", validation="By Trial", *, seed=42):
    def rule(kind):
        return {"split_type": kind, "split_unit": "Ratio", "value": "0.2"}

    return {
        "train_type": "Full Data",
        "is_cross_validation": False,
        "test_splitters": [rule(test)],
        "val_splitters": [] if validation is None else [rule(validation)],
        "seed": seed,
    }


@pytest.mark.parametrize("test", ["By Trial", "By Session", "By Subject"])
def test_context_offers_exactly_the_admitted_validation_strategies(test):
    context = DatasetSplitContext(epoch_available=False)
    choices = context.validation_strategies_for("Full Data", test)
    expected = {
        "By Trial": ("Disable", "By Trial"),
        "By Session": ("Disable", "By Trial", "By Session"),
        "By Subject": ("Disable", "By Trial", "By Session", "By Subject"),
    }
    assert choices == expected[test]
    for validation in ("By Trial", "By Session", "By Subject"):
        spec = DatasetSplitSpecification.from_payload(payload(test, validation))
        if validation in choices:
            spec.to_config()
        else:
            with pytest.raises(ValueError, match="Validation"):
                spec.to_config()


@pytest.mark.parametrize("field", ["test_splitters", "val_splitters"])
def test_removed_manual_rules_fail_closed(field):
    value = payload()
    value[field][0].update(split_unit="Manual", value="0")
    with pytest.raises(ValueError):
        DatasetSplitSpecification.from_payload(value).to_config()


def test_split_seed_round_trips_and_binds_the_preview_identity():
    spec = DatasetSplitSpecification.from_payload(payload(seed=173))
    assert spec.to_payload()["seed"] == 173
    config = spec.to_config()
    assert config.seed == 173
    assert DatasetSplitSpecification.from_config(config) == spec
    assert (
        spec.fingerprint
        != DatasetSplitSpecification.from_payload(payload(seed=174)).fingerprint
    )


@pytest.mark.parametrize("seed", [True, -1, "42", 1.5, 2**32])
def test_invalid_split_seed_is_rejected(seed):
    with pytest.raises((TypeError, ValueError)):
        DatasetSplitSpecification.from_payload(payload(seed=seed))
