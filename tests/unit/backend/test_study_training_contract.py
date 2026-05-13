"""Unit-level Study training configuration compatibility contracts."""

from typing import Any, cast

import torch

from XBrainLab import Study
from XBrainLab.backend.training import TrainingEvaluation, TrainingOption


def _ui_text(value: str) -> Any:
    """Represent text-field values passed through runtime validation."""
    return cast(Any, value)


def _training_option() -> TrainingOption:
    return TrainingOption(
        output_dir="./test_output",
        optim=torch.optim.Adam,
        optim_params={},
        use_cpu=True,
        gpu_idx=None,
        epoch=_ui_text("5"),
        bs=_ui_text("4"),
        lr=_ui_text("0.001"),
        checkpoint_epoch=_ui_text("1"),
        evaluation_option=TrainingEvaluation.TEST_ACC,
        repeat_num=_ui_text("1"),
    )


def test_study_exposes_training_option_property_not_training_setting():
    """Study's lower-level compatibility property is training_option."""
    study = Study()

    assert study.training_option is None
    assert not hasattr(study, "training_setting")


def test_study_set_training_option_updates_training_manager():
    """Study.set_training_option remains a domain compatibility contract."""
    study = Study()
    option = _training_option()

    study.set_training_option(option)

    assert study.training_option is option
    assert study.training_manager.training_option is option
    assert option.epoch == 5
    assert option.lr == 0.001
    assert option.optim == torch.optim.Adam
