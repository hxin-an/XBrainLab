"""Lightweight read models used by application state snapshots."""

from __future__ import annotations

from typing import Any

from .training_runtime import TrainingProjectionReadPort


class TrainingStateReadModel:
    """Read training state without materializing the training controller stack."""

    def __init__(self, training_runtime: TrainingProjectionReadPort) -> None:
        self._training_runtime = training_runtime

    def is_training(self) -> bool:
        return self._training_runtime.is_training()

    def get_formatted_history(self) -> list[dict[str, Any]]:
        holders = self._training_runtime.training_plan_holders()
        current_index = self._training_runtime.current_training_plan_index()
        training = self.is_training()

        history: list[dict[str, Any]] = []
        for plan_idx, plan in enumerate(holders):
            model_holder = getattr(plan, "model_holder", None)
            target_model = getattr(model_holder, "target_model", None)
            model_name = getattr(target_model, "__name__", "Unknown model")
            is_active_plan = training and current_index == plan_idx
            records = list(plan.get_plans())
            for run_idx, record in enumerate(records):
                history.append(
                    {
                        "plan": plan,
                        "record": record,
                        "group_name": f"Group {plan_idx + 1}",
                        "run_name": f"{run_idx + 1}",
                        "model_name": str(model_name),
                        "is_active": is_active_plan,
                        "is_current_run": self._is_current_run(
                            plan,
                            record,
                            is_active_plan,
                        ),
                    },
                )
        return history

    def get_missing_requirements(self) -> list[str]:
        context = self._training_runtime.resource_context()
        missing: list[str] = []
        if not context.datasets:
            missing.append("Data Splitting")
        if context.model_holder is None:
            missing.append("Model Selection")
        if context.training_option is None:
            missing.append("Training Settings")
        return missing

    @staticmethod
    def _is_current_run(plan: Any, record: Any, is_active_plan: bool) -> bool:
        if not is_active_plan:
            return False
        current_repeat = plan.get_training_repeat()
        return current_repeat == getattr(record, "repeat", None)


class EvaluationStateReadModel:
    """Read evaluation plan state without materializing the evaluation controller."""

    def __init__(self, training_runtime: TrainingProjectionReadPort) -> None:
        self._training_runtime = training_runtime

    def get_plans(self) -> list[Any]:
        return list(self._training_runtime.training_plan_holders())
