"""Analysis and visualization command handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

import numpy as np

from ..training_manager import current_post_training_saliency_target
from .capabilities import SALIENCY_TRAINING_ACTIVE_REASON
from .commands import (
    Command,
    EvaluateCommand,
    SaliencyCommand,
    VisualizeCommand,
)
from .errors import PreconditionError
from .evaluation_render import (
    EvaluationPlanIdentity,
    EvaluationRunIdentity,
    EvaluationSummaryIdentity,
    build_evaluation_cross_fold_choices,
    build_evaluation_model_summary_result,
)
from .resource_guard import ResourcePreflightResult
from .saliency_policy import normalize_saliency_params
from .saliency_render import build_saliency_cross_fold_choices
from .saliency_resource import (
    SaliencyResourceAdmission,
    check_saliency_resource_preflight,
)
from .state import ApplicationStateSnapshot
from .training_runtime import TrainingProjectionReadPort

HandlerResult = str | tuple[str, dict[str, Any]]


class _EvaluationRunSummary(TypedDict):
    identity: dict[str, int]
    name: str
    finished: bool
    evaluation_split: str
    evaluation_splits: list[str]


class _EvaluationPlanSummary(TypedDict):
    identity: dict[str, int]
    name: str
    run_count: int
    finished_run_count: int
    evaluation_splits: list[str]
    runs: list[_EvaluationRunSummary]


def _strict_saliency_params_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _strict_saliency_params_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _strict_saliency_params_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return bool(left == right)


class AnalysisCommandService:
    """Handle evaluation, visualization, and saliency commands."""

    def __init__(
        self,
        *,
        training_runtime: TrainingProjectionReadPort,
        visualization: Any,
        get_state: Callable[[], ApplicationStateSnapshot],
    ) -> None:
        self.training_runtime = training_runtime
        self.visualization = visualization
        self._get_state = get_state
        self._saliency_resource_admission = SaliencyResourceAdmission()

    def handle_evaluate(self, command: Command) -> HandlerResult:
        if not isinstance(command, EvaluateCommand):
            raise TypeError("Invalid command for evaluate")
        plans = list(self.training_runtime.training_plan_holders())
        summaries: list[_EvaluationPlanSummary] = []
        evaluation_splits: set[str] = set()
        for plan_idx, plan in enumerate(plans):
            runs = self._safe_plan_runs(plan)
            finished = [run for run in runs if self._run_finished(run)]
            plan_evaluation_splits = self._evaluation_splits(finished)
            evaluation_splits.update(plan_evaluation_splits)
            plan_identity = EvaluationPlanIdentity(plan_index=plan_idx)
            summaries.append(
                {
                    "identity": plan_identity.to_dict(),
                    "name": self._safe_plan_name(plan, plan_idx),
                    "run_count": len(runs),
                    "finished_run_count": len(finished),
                    "evaluation_splits": plan_evaluation_splits,
                    "runs": [
                        {
                            "identity": EvaluationRunIdentity(
                                plan=plan_identity,
                                run_index=run_index,
                            ).to_dict(),
                            "name": self._safe_run_name(run, run_index),
                            "finished": self._run_finished(run),
                            "evaluation_split": str(
                                getattr(
                                    getattr(run, "eval_record", None),
                                    "evaluation_split",
                                    None,
                                )
                                or "unknown"
                            ),
                            "evaluation_splits": self._run_evaluation_splits(run),
                        }
                        for run_index, run in enumerate(runs)
                    ],
                }
            )
        finished_total = sum(item["finished_run_count"] for item in summaries)
        message = (
            "Evaluation summary ready."
            if finished_total
            else "No completed training runs are available for evaluation yet."
        )
        diagnostics: dict[str, Any] = {
            "payload_type": "evaluation_summary",
            "available": finished_total > 0,
            "target": command.target,
            "plan_count": len(plans),
            "finished_run_count": finished_total,
            "evaluation_splits": sorted(evaluation_splits),
            "training_active": self._get_state().training.is_running,
            "plans": summaries,
            "cross_fold_choices": [
                choice.to_dict()
                for choice in build_evaluation_cross_fold_choices(plans)
            ],
        }
        if command.summary_identity is not None:
            if not isinstance(command.summary_identity, EvaluationSummaryIdentity):
                raise TypeError(
                    "EvaluateCommand.summary_identity must be an "
                    "EvaluationSummaryIdentity"
                )
            model_summary = build_evaluation_model_summary_result(
                self.training_runtime,
                command.summary_identity,
            )
            diagnostics["model_summary"] = {
                "identity": command.summary_identity.to_dict(),
                "status": model_summary.status,
                "text": model_summary.text,
            }
        return (
            message,
            diagnostics,
        )

    def handle_visualize(self, command: Command) -> HandlerResult:
        if not isinstance(command, VisualizeCommand):
            raise TypeError("Invalid command for visualize")
        state = self._get_state()
        trainers = self._call_list(self.visualization.get_trainers)
        available_views = []
        blocked_views: dict[str, list[str]] = {}
        if state.epoch.available:
            available_views.append("montage setup")
        if state.evaluation.finished_runs:
            available_views.extend(["confusion matrix", "metrics", "saliency setup"])
        if state.visualization.saliency_available:
            available_views.extend(
                ["saliency map", "spectrogram", "topographic map"],
            )
            if state.visualization.channel_positions_available:
                available_views.append("3D plot")
            else:
                blocked_views["3D plot"] = ["Set Montage before opening the 3D plot."]
        plot_views_available = bool(
            state.evaluation.finished_runs or state.visualization.saliency_available
        )
        message = (
            "Visualization summary ready."
            if available_views
            else "No visualization views are ready yet."
        )
        diagnostics: dict[str, Any] = {
            "payload_type": "visualization_summary",
            "available": bool(available_views),
            "view": command.view,
            "available_views": available_views,
            "blocked_views": blocked_views,
            "plot_views_available": plot_views_available,
            "trainer_count": len(trainers),
            "channel_count": state.visualization.channel_count,
            "montage_available": state.visualization.montage_available,
            "saliency_configured": state.visualization.saliency_configured,
            "saliency_available": state.visualization.saliency_available,
            "saliency_cross_fold_choices": [
                choice.to_dict()
                for choice in build_saliency_cross_fold_choices(
                    self.training_runtime.training_plan_holders()
                )
            ],
        }
        return (
            message,
            diagnostics,
        )

    def handle_saliency(self, command: Command) -> HandlerResult:
        if not isinstance(command, SaliencyCommand):
            raise TypeError("Invalid command for saliency")
        configure_requested = bool(command.params) or bool(command.method)
        if configure_requested:
            params, requested_method = normalize_saliency_params(
                command.method,
                command.params,
            )
            state = self._get_state()
            configure_reasons = self._saliency_configuration_reasons(state)
            if configure_reasons:
                raise PreconditionError("; ".join(configure_reasons))
            resource_preflight = self._saliency_resource_preflight(
                command,
                params,
                evaluator_required=state.active_training.has_trainer,
            )
            automatic_target = current_post_training_saliency_target()
            self.visualization.set_saliency_params(params)
            if automatic_target is not None:
                schedule = automatic_target.schedule_outcome
                if schedule is None:
                    raise PreconditionError(
                        "Automatic saliency scheduler did not publish an outcome.",
                        diagnostics={
                            "post_training_saliency_schedule": {
                                "disposition": "rejected",
                                "reason": "outcome_unavailable",
                            }
                        },
                    )
                schedule_diagnostics = schedule.to_dict()
                if not schedule.scheduled:
                    raise PreconditionError(
                        schedule.message,
                        diagnostics={
                            "post_training_saliency_schedule": schedule_diagnostics,
                        },
                    )
                return (
                    schedule.message,
                    {
                        "payload_type": "saliency_configuration",
                        "action": "schedule",
                        "saliency_configured": True,
                        "saliency_available": (
                            self._get_state().visualization.saliency_available
                        ),
                        "requested_method": requested_method,
                        "params": self._json_safe(params),
                        "resource_preflight": resource_preflight,
                        "post_training_saliency_schedule": schedule_diagnostics,
                    },
                )
            applied_params = self.visualization.get_saliency_params()
            readback_matches = isinstance(
                applied_params,
                dict,
            ) and _strict_saliency_params_equal(applied_params, params)
            if not readback_matches:
                raise ValueError(
                    "Saliency configuration could not be verified in "
                    "authoritative state."
                )
            return (
                "Saliency parameters configured.",
                {
                    "payload_type": "saliency_configuration",
                    "action": "configure",
                    "saliency_configured": True,
                    "saliency_available": (
                        self._get_state().visualization.saliency_available
                    ),
                    "requested_method": requested_method,
                    "params": self._json_safe(applied_params),
                    "resource_preflight": resource_preflight,
                },
            )

        current_params = self.visualization.get_saliency_params()
        state = self._get_state()
        configure_reasons = self._saliency_configuration_reasons(state)
        return (
            (
                "Saliency summary ready."
                if current_params
                else "Saliency parameters are not configured yet."
            ),
            {
                "payload_type": "saliency_summary",
                "action": "query",
                "saliency_configured": bool(current_params),
                "saliency_available": state.visualization.saliency_available,
                "configure_available": not configure_reasons,
                "configure_reasons": configure_reasons,
                "params": self._json_safe(current_params or {}),
                "finished_run_count": state.evaluation.finished_runs,
            },
        )

    @staticmethod
    def _saliency_configuration_reasons(
        state: ApplicationStateSnapshot,
    ) -> list[str]:
        reasons = []
        if state.active_training.is_running:
            reasons.append(SALIENCY_TRAINING_ACTIVE_REASON)
        if state.active_training.has_trainer or (
            state.active_training.has_model
            and state.active_training.has_training_option
        ):
            return reasons
        reasons.append(
            "Select a model and training settings before configuring saliency."
        )
        return reasons

    def _saliency_resource_preflight(
        self,
        command: SaliencyCommand,
        params: dict[str, Any],
        *,
        evaluator_required: bool,
    ) -> dict[str, Any]:
        if not evaluator_required:
            preflight = ResourcePreflightResult(
                issues=(),
                diagnostics={
                    "operation": "saliency_recomputation",
                    "admission_required": False,
                    "reason": "no_trained_evaluator",
                    "message": (
                        "Saliency parameters are being saved without evaluator "
                        "allocation."
                    ),
                },
            )
            return self._saliency_resource_admission.authorize(
                command,
                params,
                preflight,
            ).to_diagnostics()
        try:
            context = self.training_runtime.resource_context()
            holders = tuple(self.training_runtime.training_plan_holders())
            holder_datasets = self._saliency_holder_datasets(holders)
        except Exception as exc:
            raise PreconditionError(
                "Saliency resource admission could not read the current dataset, "
                "model, and training settings.",
                diagnostics={
                    "resource_preflight": {
                        "operation": "saliency_recomputation",
                        "risk_level": "blocking",
                        "reason": "resource_context_read_failed",
                        "error_type": type(exc).__name__,
                    }
                },
            ) from exc
        preflight = check_saliency_resource_preflight(
            holder_datasets or context.datasets,
            context.training_option,
            context.model_holder,
            params,
            training_plan_holders=holders,
        )
        return self._saliency_resource_admission.authorize(
            command,
            params,
            preflight,
        ).to_diagnostics()

    @staticmethod
    def _saliency_holder_datasets(holders: tuple[Any, ...]) -> tuple[Any, ...]:
        datasets: list[Any] = []
        identities: set[int] = set()
        for holder in holders:
            getter = getattr(holder, "get_dataset", None)
            if not callable(getter):
                continue
            dataset = getter()
            if dataset is None or id(dataset) in identities:
                continue
            identities.add(id(dataset))
            datasets.append(dataset)
        return tuple(datasets)

    @staticmethod
    def _call_list(call: Callable[[], Any]) -> list[Any]:
        value = call()
        return list(value) if value is not None else []

    @staticmethod
    def _safe_plan_runs(plan: Any) -> list[Any]:
        return list(plan.get_plans())

    @staticmethod
    def _safe_plan_name(plan: Any, idx: int) -> str:
        try:
            return str(plan.get_name())
        except Exception:
            return f"Plan {idx + 1}"

    @staticmethod
    def _safe_run_name(run: Any, idx: int) -> str:
        try:
            return str(run.get_name())
        except Exception:
            return f"Repeat-{idx}"

    @staticmethod
    def _run_finished(run: Any) -> bool:
        return bool(run.is_finished())

    @staticmethod
    def _evaluation_splits(runs: list[Any]) -> list[str]:
        """Return every saved prediction split across completed runs."""
        splits = {
            split
            for run in runs
            for split in AnalysisCommandService._run_evaluation_splits(run)
        }
        return sorted(splits)

    @staticmethod
    def _run_evaluation_splits(run: Any) -> list[str]:
        records = getattr(run, "evaluation_records", None)
        if isinstance(records, dict):
            saved = {
                str(split).strip().casefold()
                for split, record in records.items()
                if record is not None
                and str(split).strip().casefold() in {"training", "validation", "test"}
            }
            if saved:
                return sorted(saved)
        legacy_record = getattr(run, "eval_record", None)
        if legacy_record is None:
            return []
        legacy_split = (
            str(getattr(legacy_record, "evaluation_split", None) or "unknown")
            .strip()
            .casefold()
        )
        return (
            [legacy_split] if legacy_split in {"training", "validation", "test"} else []
        )

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, dict):
            return {str(k): cls._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_safe(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)
