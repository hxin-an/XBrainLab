from XBrainLab.backend.dataset.option import (
    SplitByType,
    SplitUnit,
    TrainingType,
    ValSplitByType,
)


def test_split_unit():
    assert SplitUnit.RATIO.value == "Ratio"
    assert SplitUnit.NUMBER.value == "Number"
    assert SplitUnit.MANUAL.value == "Manual"
    assert SplitUnit.KFOLD.value == "K Fold"


def test_training_type():
    assert TrainingType.FULL.value == "Full Data"
    assert TrainingType.IND.value == "Individual"


def test_split_by_type():
    assert SplitByType.SESSION.value == "By Session"
    assert SplitByType.TRIAL.value == "By Trial"
    assert SplitByType.SUBJECT.value == "By Subject"


def test_val_split_by_type():
    assert ValSplitByType.DISABLE.value == "Disable"
    assert ValSplitByType.SESSION.value == "By Session"
    assert ValSplitByType.TRIAL.value == "By Trial"
    assert ValSplitByType.SUBJECT.value == "By Subject"
