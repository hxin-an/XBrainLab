"""Analysis and visualization command handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from .commands import (
    ApplyMontageCommand,
    Command,
    EvaluateCommand,
    SaliencyCommand,
    VisualizeCommand,
)
from .errors import PreconditionError
from .saliency_policy import normalize_saliency_params
from .state import ApplicationStateSnapshot

HandlerResult = str | tuple[str, dict[str, Any]]


class AnalysisCommandService:
    """Handle evaluation, visualization, saliency, and montage commands."""

    def __init__(
        self,
        *,
        evaluation: Any,
        visualization: Any,
        preprocess: Any,
        get_state: Callable[[], ApplicationStateSnapshot],
    ) -> None:
        self.evaluation = evaluation
        self.visualization = visualization
        self.preprocess = preprocess
        self._get_state = get_state

    def handle_evaluate(self, command: Command) -> HandlerResult:
        if not isinstance(command, EvaluateCommand):
            raise TypeError("Invalid command for evaluate")
        plans = self._call_list(self.evaluation.get_plans)
        summaries = []
        pooled_eval_results: list[Any] = []
        model_summaries: list[dict[str, Any]] = []
        for plan_idx, plan in enumerate(plans):
            runs = self._safe_plan_runs(plan)
            finished = [run for run in runs if self._run_finished(run)]
            metrics: dict[str, Any] = {}
            pooled_result: Any = None
            if finished and (command.include_metrics or command.include_pooled_results):
                labels, outputs, metrics = self.evaluation.get_pooled_eval_result(plan)
                pooled_result = (labels, outputs, metrics)
            summaries.append(
                {
                    "index": plan_idx,
                    "name": self._safe_plan_name(plan, plan_idx),
                    "run_count": len(runs),
                    "finished_run_count": len(finished),
                    "metrics": self._json_safe(metrics),
                }
            )
            if command.include_pooled_results:
                pooled_eval_results.append(pooled_result)
            if command.include_model_summaries:
                model_summaries.append(
                    self._model_summary_payload(
                        plan,
                        runs,
                        plan_index=plan_idx,
                        requested_plan_index=command.model_summary_plan_index,
                        requested_run_index=command.model_summary_run_index,
                    ),
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
            "training_active": self._get_state().training.is_running,
            "plans": summaries,
        }
        if command.include_objects:
            diagnostics["plan_objects"] = plans
        if command.include_pooled_results:
            diagnostics["pooled_eval_results"] = pooled_eval_results
        if command.include_model_summaries:
            diagnostics["model_summaries"] = model_summaries
            diagnostics["model_summary_request"] = {
                "plan_index": command.model_summary_plan_index,
                "run_index": command.model_summary_run_index,
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
        }
        if command.include_objects:
            diagnostics["trainer_objects"] = trainers
        if command.include_averaged_records:
            diagnostics["averaged_records"] = [
                self._averaged_record(trainer) for trainer in trainers
            ]
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
            self.visualization.set_saliency_params(params)
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
                    "params": self._json_safe(params),
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

    def handle_apply_montage(self, command: Command) -> HandlerResult:
        if not isinstance(command, ApplyMontageCommand):
            raise TypeError("Invalid command for apply_montage")
        if not command.channels:
            raise PreconditionError("channels list cannot be empty.")
        if not command.positions:
            raise PreconditionError("positions list cannot be empty.")
        if len(command.channels) != len(command.positions):
            raise PreconditionError("channels and positions must have equal length.")

        self.preprocess.apply_montage(command.channels, command.positions)
        message = (
            f"Applied montage '{command.montage_name}' "
            f"to {len(command.channels)} channel(s)."
            if command.montage_name
            else f"Applied montage to {len(command.channels)} channel(s)."
        )
        return (
            message,
            {
                "channel_count": len(command.channels),
                "montage_name": command.montage_name,
            },
        )

    @staticmethod
    def _saliency_configuration_reasons(
        state: ApplicationStateSnapshot,
    ) -> list[str]:
        if state.active_training.has_trainer or (
            state.active_training.has_model
            and state.active_training.has_training_option
        ):
            return []
        return ["Select a model and training settings before configuring saliency."]

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

    def _model_summary(self, plan: Any, record: Any | None = None) -> str:
        return str(self.evaluation.get_model_summary_str(plan, record))

    def _model_summary_payload(
        self,
        plan: Any,
        runs: list[Any],
        *,
        plan_index: int,
        requested_plan_index: int | None,
        requested_run_index: int | None,
    ) -> dict[str, Any]:
        """Build only the requested model summary to avoid UI-triggered stalls."""
        if requested_plan_index is None and requested_run_index is None:
            return {
                "plan": self._model_summary(plan),
                "runs": [self._model_summary(plan, run) for run in runs],
            }

        if requested_plan_index is not None and plan_index != requested_plan_index:
            return {"plan": "", "runs": [""] * len(runs)}

        run_summaries = [""] * len(runs)
        if requested_run_index is None:
            return {
                "plan": self._model_summary(plan),
                "runs": run_summaries,
            }

        if 0 <= requested_run_index < len(runs):
            run_summaries[requested_run_index] = self._model_summary(
                plan,
                runs[requested_run_index],
            )
        return {"plan": "", "runs": run_summaries}

    def _averaged_record(self, trainer: Any) -> Any:
        return self.visualization.get_averaged_record(trainer)

    @staticmethod
    def _run_finished(run: Any) -> bool:
        return bool(run.is_finished())

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
