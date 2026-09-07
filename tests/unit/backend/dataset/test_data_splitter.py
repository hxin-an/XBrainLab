import pytest

from XBrainLab.backend.dataset import (
    DataSplitter,
    DataSplittingConfig,
    SplitByType,
    SplitUnit,
    TrainingType,
    ValSplitByType,
)


@pytest.mark.parametrize(
    "split_unit,value_var,expected_value",
    [
        (SplitUnit.RATIO, "0.3", 0.3),
        (SplitUnit.NUMBER, "2", 2.0),
        (SplitUnit.KFOLD, "2", 2.0),
        (SplitUnit.MANUAL, "0 2", [0, 2]),
    ],
)
@pytest.mark.parametrize(
    "split_type",
    [
        *SplitByType,
        ValSplitByType.TRIAL,
        ValSplitByType.SESSION,
        ValSplitByType.SUBJECT,
    ],
)
def test_splitter_accepts_interior_values_for_every_enum_and_unit(
    split_type, split_unit, value_var, expected_value
):
    is_option = True
    splitter = DataSplitter(split_type, value_var, split_unit, is_option)

    assert splitter.is_option == is_option
    assert splitter.split_type == split_type
    assert splitter.text == split_type.value
    assert splitter.value_var == value_var
    assert splitter.split_unit == split_unit

    assert splitter.is_valid()
    assert splitter.get_value() == expected_value
    assert splitter.get_raw_value() == value_var


@pytest.mark.parametrize(
    "split_type",
    [
        SplitByType.TRIAL,
        ValSplitByType.TRIAL,
    ],
)
@pytest.mark.parametrize(
    "split_unit,value_var",
    [
        (SplitUnit.RATIO, "0"),
        (SplitUnit.RATIO, "1"),
        (SplitUnit.RATIO, "-0.1"),
        (SplitUnit.RATIO, "1.2"),
        (SplitUnit.RATIO, "not-a-number"),
        (SplitUnit.NUMBER, "0"),
        (SplitUnit.NUMBER, "-1"),
        (SplitUnit.NUMBER, "1.5"),
        (SplitUnit.KFOLD, "0"),
        (SplitUnit.KFOLD, "1"),
        (SplitUnit.KFOLD, "-1"),
        (SplitUnit.KFOLD, "2.0"),
        (SplitUnit.MANUAL, ""),
        (SplitUnit.MANUAL, "   "),
        (SplitUnit.MANUAL, "-1"),
        (SplitUnit.MANUAL, "0 1.5"),
    ],
)
def test_splitter_rejects_empty_and_out_of_range_values(
    split_type, split_unit, value_var
):
    splitter = DataSplitter(split_type, value_var, split_unit)

    assert not splitter.is_valid()
    with pytest.raises(ValueError):
        splitter.get_value()
    with pytest.raises(ValueError):
        splitter.get_raw_value()


@pytest.mark.parametrize("split_type", [SplitByType.SESSION, ValSplitByType.SESSION])
def test_splitter_without_unit_is_invalid(split_type):
    splitter = DataSplitter(split_type, "0.2")

    assert not splitter.is_valid()
    with pytest.raises(ValueError):
        splitter.get_value()


@pytest.mark.parametrize("split_type", [SplitByType.TRIAL, ValSplitByType.TRIAL])
@pytest.mark.parametrize("split_unit", list(SplitUnit))
def test_splitter_rejects_missing_value_for_every_unit(split_type, split_unit):
    splitter = DataSplitter(split_type, None, split_unit)

    assert not splitter.is_valid()
    with pytest.raises(ValueError):
        splitter.get_value()
    with pytest.raises(ValueError):
        splitter.get_raw_value()


@pytest.mark.parametrize("split_type", [SplitByType.TRIAL, ValSplitByType.TRIAL])
def test_manual_splitter_preserves_trailing_whitespace_parse_contract(split_type):
    splitter = DataSplitter(split_type, "2 ", SplitUnit.MANUAL)

    assert splitter.is_valid()
    assert splitter.get_value() == [2]
    assert splitter.get_raw_value() == "2 "


@pytest.mark.parametrize("split_unit", [*list(SplitUnit), "test"])
def test_splitter_not_implemented(split_unit):
    split_type = SplitByType.SESSION
    value_var = "2"
    is_option = True
    splitter = DataSplitter(split_type, value_var, SplitUnit.MANUAL, is_option)
    splitter.split_unit = split_unit
    if split_unit == "test":
        with pytest.raises(NotImplementedError):
            splitter.is_valid()
    else:
        splitter.is_valid()


def test_splitter_getter():
    split_type = SplitByType.SESSION
    split_unit = SplitUnit.KFOLD
    value_var = "1"
    is_option = True
    splitter = DataSplitter(split_type, value_var, split_unit, is_option)

    assert splitter.get_split_unit() == split_unit
    assert splitter.get_split_type_repr() == "SplitByType.SESSION"
    assert splitter.get_split_unit_repr() == "SplitUnit.KFOLD"


def test_config():
    train_type = TrainingType.FULL
    is_cross_validation = True
    val_splitter_list = [DataSplitter(SplitByType.SESSION, "1", SplitUnit.KFOLD, True)]
    test_splitter_list = [DataSplitter(SplitByType.SESSION, "1", SplitUnit.KFOLD, True)]
    config = DataSplittingConfig(
        train_type, is_cross_validation, val_splitter_list, test_splitter_list
    )

    assert config.train_type == train_type
    assert config.is_cross_validation == is_cross_validation
    assert config.val_splitter_list == val_splitter_list
    assert config.test_splitter_list == test_splitter_list

    assert config.get_splitter_option() == (val_splitter_list, test_splitter_list)
    assert config.get_train_type_repr() == "TrainingType.FULL"
