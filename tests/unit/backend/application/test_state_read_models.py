from __future__ import annotations

from typing import Any

import pytest

from XBrainLab.backend.application.state_read_models import (
    EvaluationStateReadModel,
    TrainingStateReadModel,
)
from XBrainLab.backend.application.training_runtime import TrainingRuntimeContext


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


class _Runtime:
    def __init__(self) -> None:
        self.trainer = _Trainer()
        self.training = True
        self.datasets: tuple[Any, ...] = (object(),)
        self.model_holder: Any | None = _ModelHolder()
        self.training_option: Any | None = object()

    def is_training(self) -> bool:
        return self.training

    def training_plan_holders(self) -> tuple[Any, ...]:
        return tuple(self.trainer.get_training_plan_holders())

    def current_training_plan_index(self) -> int | None:
        return self.trainer.current_idx

    def resource_context(self) -> TrainingRuntimeContext:
        return TrainingRuntimeContext(
            self.datasets,
            self.training_option,
            self.model_holder,
        )


def test_training_state_read_model_formats_history_without_controller_lookup() -> None:
    history = TrainingStateReadModel(_Runtime()).get_formatted_history()  # type: ignore[arg-type]

    assert history == [
        {
            "plan": history[0]["plan"],
            "record": history[0]["record"],
            "plan_index": 0,
            "run_index": 0,
            "group_name": "Group 1",
            "run_name": "1",
            "model_name": "_TargetModel",
            "is_active": True,
            "is_current_run": True,
        },
    ]


def test_evaluation_state_read_model_lists_plans_without_controller_lookup() -> None:
    plans = EvaluationStateReadModel(_Runtime()).get_plans()  # type: ignore[arg-type]

    assert len(plans) == 1
    assert isinstance(plans[0], _Plan)


def test_training_state_read_failure_is_not_reported_as_idle() -> None:
    runtime = _Runtime()
    runtime.is_training = lambda: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="boom"):
        TrainingStateReadModel(runtime).is_training()  # type: ignore[arg-type]


def test_evaluation_state_read_failure_is_not_reported_as_no_plans() -> None:
    runtime = _Runtime()
    runtime.trainer = type(
        "BrokenTrainer",
        (),
        {
            "get_training_plan_holders": lambda self: (_ for _ in ()).throw(
                RuntimeError("plans unavailable")
            )
        },
    )()

    with pytest.raises(RuntimeError, match="plans unavailable"):
        EvaluationStateReadModel(runtime).get_plans()  # type: ignore[arg-type]
