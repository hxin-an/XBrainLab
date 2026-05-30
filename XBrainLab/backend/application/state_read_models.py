"""Lightweight read models used by application state snapshots."""

from __future__ import annotations

from typing import Any

from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.logger import logger


class TrainingStateReadModel:
    """Read training state without materializing the training controller stack."""

    def __init__(self, study: Study) -> None:
        self._study = study

    def is_training(self) -> bool:
        training_manager = getattr(self._study, "training_manager", None)
        if training_manager is None:
            return False
        try:
            return bool(training_manager.is_training())
        except Exception:
            logger.debug("Failed to read training state", exc_info=True)
            return False

    def get_formatted_history(self) -> list[dict[str, Any]]:
        trainer = getattr(self._study, "trainer", None)
        if trainer is None:
            return []
        try:
            holders = list(trainer.get_training_plan_holders())
        except Exception:
            logger.debug("Failed to read training plan holders", exc_info=True)
            return []

        history: list[dict[str, Any]] = []
        for plan_idx, plan in enumerate(holders):
            model_holder = getattr(plan, "model_holder", None)
            target_model = getattr(model_holder, "target_model", None)
            model_name = getattr(target_model, "__name__", "Unknown model")
            is_active_plan = (
                self.is_training()
                and getattr(
                    trainer,
                    "current_idx",
                    None,
                )
                == plan_idx
            )
            try:
                records = list(plan.get_plans())
            except Exception:
                logger.debug("Failed to read training records", exc_info=True)
                continue
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
        missing: list[str] = []
        if not list(getattr(self._study, "datasets", []) or []):
            missing.append("Data Splitting")
        if getattr(self._study, "model_holder", None) is None:
            missing.append("Model Selection")
        if getattr(self._study, "training_option", None) is None:
            missing.append("Training Settings")
        return missing

    @staticmethod
    def _is_current_run(plan: Any, record: Any, is_active_plan: bool) -> bool:
        if not is_active_plan:
            return False
        try:
            current_repeat = plan.get_training_repeat()
        except Exception:
            return False
        return current_repeat == getattr(record, "repeat", None)


class EvaluationStateReadModel:
    """Read evaluation plan state without materializing the evaluation controller."""

    def __init__(self, study: Study) -> None:
        self._study = study

    def get_plans(self) -> list[Any]:
        trainer = getattr(self._study, "trainer", None)
        if trainer is None:
            return []
        try:
            return list(trainer.get_training_plan_holders())
        except Exception:
            logger.debug("Failed to read training plans", exc_info=True)
            return []
