"""Public admission regressions for the supported dataset split contract."""

from __future__ import annotations

import pytest

from XBrainLab.backend.application.commands import SaveDatasetSplitCommand
from XBrainLab.backend.application.dataset_generation_service import (
    DatasetGenerationCommandService,
)
from XBrainLab.backend.application.dataset_split_preview import (
    DatasetSplitContext,
    DatasetSplitSpecification,
)


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "train_type": "Full Data",
        "is_cross_validation": False,
        "val_splitters": [],
        "test_splitters": [
            {
                "split_type": "By Trial",
                "split_unit": "Ratio",
                "value": "0.2",
                "is_option": True,
            }
        ],
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "field,value",
    [
        ("is_cross_validation", "false"),
        ("is_cross_validation", 0),
    ],
)
def test_split_specification_rejects_non_boolean_cross_validation(
    field: str,
    value: object,
) -> None:
    with pytest.raises(TypeError, match="is_cross_validation must be a bool"):
        DatasetSplitSpecification.from_payload(_payload(**{field: value}))


def test_split_specification_rejects_non_boolean_rule_enabled_flag() -> None:
    with pytest.raises(TypeError, match="is_option must be a bool"):
        DatasetSplitSpecification.from_payload(
            _payload(
                test_splitters=[
                    {
                        "split_type": "By Trial",
                        "split_unit": "Ratio",
                        "value": "0.2",
                        "is_option": "false",
                    }
                ]
            )
        )


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("train_type", None, "train_type"),
        ("train_type", "", "train_type"),
        ("is_cross_validation", None, "is_cross_validation"),
    ],
)
def test_structured_split_payload_requires_explicit_train_type_and_cross_validation(
    field: str, value: object | None, expected: str
) -> None:
    payload = _payload()
    if value is None:
        payload.pop(field)
    else:
        payload[field] = value
    with pytest.raises((TypeError, ValueError), match=expected):
        DatasetSplitSpecification.from_payload(payload)


def test_structured_split_payload_rejects_inactive_rules() -> None:
    payload = _payload(
        test_splitters=[
            {
                "split_type": "By Trial",
                "split_unit": "Ratio",
                "value": "0.2",
                "is_option": True,
            },
            {
                "split_type": "By Session",
                "split_unit": "Ratio",
                "value": "0.2",
                "is_option": False,
            },
        ]
    )

    with pytest.raises(ValueError, match=r"(?i)inactive"):
        DatasetGenerationCommandService.config_from_payload(payload)


@pytest.mark.parametrize(
    "split_type",
    ["Disable", "By Trial (Independent)", "By Session (Independent)"],
)
def test_split_config_rejects_retired_test_strategies(split_type: str) -> None:
    with pytest.raises(ValueError, match="supported"):
        DatasetGenerationCommandService.config_from_payload(
            _payload(
                test_splitters=[
                    {
                        "split_type": split_type,
                        "split_unit": "Ratio",
                        "value": "0.2",
                        "is_option": True,
                    }
                ]
            )
        )


@pytest.mark.parametrize(
    "split_field",
    ["test_splitters", "val_splitters"],
)
def test_individual_subject_split_is_rejected_for_test_or_validation(
    split_field: str,
) -> None:
    splitters = [
        {
            "split_type": "By Subject",
            "split_unit": "Ratio",
            "value": "0.2",
            "is_option": True,
        }
    ]
    with pytest.raises(ValueError, match=r"Individual.*Subject"):
        DatasetGenerationCommandService.config_from_payload(
            _payload(train_type="Individual", **{split_field: splitters})
        )


@pytest.mark.parametrize(
    "unit,value",
    [("Ratio", "0"), ("Number", "0"), ("K Fold", "1"), ("Manual", "")],
)
def test_enabled_split_rule_requires_a_non_empty_supported_value(
    unit: str,
    value: str,
) -> None:
    with pytest.raises(ValueError):
        DatasetGenerationCommandService.config_from_payload(
            _payload(
                test_splitters=[
                    {
                        "split_type": "By Trial",
                        "split_unit": unit,
                        "value": value,
                        "is_option": True,
                    }
                ]
            )
        )


def test_cross_validation_requires_kfold_test_and_non_manual_validation() -> None:
    with pytest.raises(ValueError, match="K Fold"):
        DatasetGenerationCommandService.config_from_payload(
            _payload(is_cross_validation=True)
        )


def test_legacy_none_uses_a_usable_full_trial_default_but_empty_payload_is_not_legacy() -> (
    None
):
    legacy = DatasetGenerationCommandService._build_data_splitting_config(
        SaveDatasetSplitCommand(split_config=None),
    )

    assert legacy.train_type.value == "Full Data"
    assert legacy.test_splitter_list[0].split_type.value == "By Trial"
    DatasetGenerationCommandService._validate_split_config(legacy)

    with pytest.raises(ValueError, match="train_type is required"):
        DatasetGenerationCommandService._build_data_splitting_config(
            SaveDatasetSplitCommand(split_config={}),
        )


def test_validation_disable_is_canonical_empty_rules_not_a_test_disable() -> None:
    config = DatasetGenerationCommandService.config_from_payload(
        _payload(val_splitters=[]),
    )

    assert config.val_splitter_list == []


def test_split_context_exposes_backend_owned_strategy_availability() -> None:
    context = DatasetSplitContext(epoch_available=True)

    assert context.full_test_strategies == ("By Trial", "By Session", "By Subject")
    assert context.individual_test_strategies == ("By Trial", "By Session")
    assert context.full_validation_strategies == (
        "Disable",
        "By Trial",
        "By Session",
        "By Subject",
    )
    assert context.individual_validation_strategies == (
        "Disable",
        "By Trial",
        "By Session",
    )
    assert context.non_cv_split_units == ("Ratio", "Number", "Manual")
    assert context.cv_test_split_units == ("K Fold",)
    assert context.cv_validation_split_units == ("Ratio", "Number")
    assert context.individual_subject_unavailable_reason
    with pytest.raises(ValueError, match="Manual"):
        DatasetGenerationCommandService.config_from_payload(
            _payload(
                is_cross_validation=True,
                test_splitters=[
                    {
                        "split_type": "By Trial",
                        "split_unit": "K Fold",
                        "value": "2",
                        "is_option": True,
                    }
                ],
                val_splitters=[
                    {
                        "split_type": "By Trial",
                        "split_unit": "Manual",
                        "value": "0",
                        "is_option": True,
                    }
                ],
            )
        )
