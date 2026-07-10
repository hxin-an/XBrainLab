from __future__ import annotations

from typing import Any, ClassVar

import pytest

from XBrainLab.backend.application.state_read_models import (
    EvaluationStateReadModel,
    TrainingStateReadModel,
)


class _TargetModel:
    pass


class _ModelHolder:
    target_model = _TargetModel


class _Record:
    repeat = 2


class _Plan:
    model_holder = _ModelHolder()

    def get_plans(self) -> list[_Record]:
        return [_Record()]

    def get_training_repeat(self) -> int:
        return 2


class _Trainer:
    current_idx = 0

    def get_training_plan_holders(self) -> list[_Plan]:
        return [_Plan()]


class _TrainingManager:
    def is_training(self) -> bool:
        return True


class _Study:
    trainer = _Trainer()
    training_manager = _TrainingManager()
    datasets: ClassVar[list[Any]] = [object()]
    model_holder = _ModelHolder()
    training_option = object()

    def get_controller(self, _name: str) -> Any:
        raise AssertionError("Training state read model must not load controllers")


def test_training_state_read_model_formats_history_without_controller_lookup() -> None:
    history = TrainingStateReadModel(_Study()).get_formatted_history()

    assert history == [
        {
            "plan": history[0]["plan"],
            "record": history[0]["record"],
            "group_name": "Group 1",
            "run_name": "1",
            "model_name": "_TargetModel",
            "is_active": True,
            "is_current_run": True,
        },
    ]


def test_evaluation_state_read_model_lists_plans_without_controller_lookup() -> None:
    plans = EvaluationStateReadModel(_Study()).get_plans()

    assert len(plans) == 1
    assert isinstance(plans[0], _Plan)


def test_training_state_read_failure_is_not_reported_as_idle() -> None:
    study = _Study()
    study.training_manager = type(
        "BrokenTrainingManager",
        (),
        {"is_training": lambda self: (_ for _ in ()).throw(RuntimeError("boom"))},
    )()

    with pytest.raises(RuntimeError, match="boom"):
        TrainingStateReadModel(study).is_training()


def test_evaluation_state_read_failure_is_not_reported_as_no_plans() -> None:
    study = _Study()
    study.trainer = type(
        "BrokenTrainer",
        (),
        {
            "get_training_plan_holders": lambda self: (_ for _ in ()).throw(
                RuntimeError("plans unavailable")
            )
        },
    )()

    with pytest.raises(RuntimeError, match="plans unavailable"):
        EvaluationStateReadModel(study).get_plans()
