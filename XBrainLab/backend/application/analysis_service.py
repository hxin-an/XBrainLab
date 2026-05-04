"""Analysis and visualization command handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from XBrainLab.backend.utils.logger import logger

from .commands import (
    ApplyMontageCommand,
    Command,
    EvaluateCommand,
    SaliencyCommand,
    VisualizeCommand,
)
from .errors import PreconditionError
from .state import ApplicationStateSnapshot

HandlerResult = str | tuple[str, dict[str, Any]]

_DEFAULT_SALIENCY_PARAMS: dict[str, Any] = {
    "nt_samples": 5,
    "nt_samples_batch_size": None,
    "stdevs": 1.0,
}
_SUPPORTED_SALIENCY_PARAM_KEYS = ("SmoothGrad", "SmoothGrad_Squared", "VarGrad")


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
        plans = self._safe_call_list(self.evaluation.get_plans)
        summaries = []
        for plan_idx, plan in enumerate(plans):
            runs = self._safe_plan_runs(plan)
            finished = [run for run in runs if self._run_finished(run)]
            metrics: dict[str, Any] = {}
            if finished:
                try:
                    _labels, _outputs, metrics = self.evaluation.get_pooled_eval_result(
                        plan,
                    )
                except Exception:
                    logger.debug("Failed to pool evaluation metrics", exc_info=True)
                    metrics = {}
            summaries.append(
                {
                    "index": plan_idx,
                    "name": self._safe_plan_name(plan, plan_idx),
                    "run_count": len(runs),
                    "finished_run_count": len(finished),
                    "metrics": self._json_safe(metrics),
                }
            )
        finished_total = sum(item["finished_run_count"] for item in summaries)
        message = (
            "Evaluation summary ready."
            if finished_total
            else "No completed training runs are available for evaluation yet."
        )
        return (
            message,
            {
                "payload_type": "evaluation_summary",
                "available": finished_total > 0,
                "target": command.target,
                "plan_count": len(plans),
                "finished_run_count": finished_total,
                "plans": summaries,
            },
        )

    def handle_visualize(self, command: Command) -> HandlerResult:
        if not isinstance(command, VisualizeCommand):
            raise TypeError("Invalid command for visualize")
        state = self._get_state()
        trainers = self._safe_call_list(self.visualization.get_trainers)
        available_views = []
        if state.epoch.available:
            available_views.extend(["epoch overview", "channel montage"])
        if state.evaluation.finished_runs:
            available_views.extend(["confusion matrix", "metrics", "saliency setup"])
        if state.visualization.saliency_available:
            available_views.extend(
                ["saliency map", "spectrogram", "topographic map", "3D plot"],
            )
        message = (
            "Visualization summary ready."
            if available_views
            else "No visualization views are ready yet."
        )
        return (
            message,
            {
                "payload_type": "visualization_summary",
                "available": bool(available_views),
                "view": command.view,
                "available_views": available_views,
                "trainer_count": len(trainers),
                "channel_count": state.visualization.channel_count,
                "montage_available": state.visualization.montage_available,
                "saliency_configured": state.visualization.saliency_configured,
                "saliency_available": state.visualization.saliency_available,
            },
        )

    def handle_saliency(self, command: Command) -> HandlerResult:
        if not isinstance(command, SaliencyCommand):
            raise TypeError("Invalid command for saliency")
        configure_requested = bool(command.params) or bool(command.method)
        if configure_requested:
            params, requested_method = self._normalize_saliency_params(
                command.method,
                command.params,
            )
            state = self._get_state()
            if not (
                state.active_training.has_trainer
                or (
                    state.active_training.has_model
                    and state.active_training.has_training_option
                )
            ):
                raise PreconditionError(
                    "Select a model and training settings before configuring saliency.",
                )
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
        return (
            (
                "Saliency summary ready."
                if current_params
                else "Saliency parameters are not configured yet."
            ),
            {
                "payload_type": "saliency_summary",
                "action": "query",
                "saliency_configured": current_params is not None,
                "saliency_available": state.visualization.saliency_available,
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
    def _normalize_saliency_params(
        method: str | None,
        params: dict[str, Any] | None,
    ) -> tuple[dict[str, dict[str, Any]], str | None]:
        """Normalize agent-friendly saliency args to evaluator-required keys."""
        raw = dict(params or {})
        requested_method = str(raw.pop("method", method or "") or "").strip() or None
        flat_params: dict[str, Any] = {}
        normalized = {
            key: dict(_DEFAULT_SALIENCY_PARAMS)
            for key in _SUPPORTED_SALIENCY_PARAM_KEYS
        }
        for key, value in raw.items():
            if key in _SUPPORTED_SALIENCY_PARAM_KEYS and isinstance(value, dict):
                normalized[key].update(value)
            elif key not in _SUPPORTED_SALIENCY_PARAM_KEYS:
                flat_params[key] = value
        if flat_params:
            for method_params in normalized.values():
                method_params.update(flat_params)
        return normalized, requested_method

    @staticmethod
    def _safe_call_list(call: Callable[[], Any]) -> list[Any]:
        try:
            value = call()
        except Exception:
            return []
        return list(value) if value is not None else []

    @staticmethod
    def _safe_plan_runs(plan: Any) -> list[Any]:
        try:
            return list(plan.get_plans())
        except Exception:
            return []

    @staticmethod
    def _safe_plan_name(plan: Any, idx: int) -> str:
        try:
            return str(plan.get_name())
        except Exception:
            return f"Plan {idx + 1}"

    @staticmethod
    def _run_finished(run: Any) -> bool:
        try:
            return bool(run.is_finished())
        except Exception:
            return False

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
