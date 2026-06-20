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
_RECOMMENDED_SALIENCY_METHODS = ("Gradient", "Gradient * Input")
_ALL_SALIENCY_METHODS = (
    *_RECOMMENDED_SALIENCY_METHODS,
    *_SUPPORTED_SALIENCY_PARAM_KEYS,
)


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
        pooled_eval_results: list[Any] = []
        model_summaries: list[dict[str, Any]] = []
        for plan_idx, plan in enumerate(plans):
            runs = self._safe_plan_runs(plan)
            finished = [run for run in runs if self._run_finished(run)]
            metrics: dict[str, Any] = {}
            pooled_result: Any = None
            if finished and (command.include_metrics or command.include_pooled_results):
                try:
                    labels, outputs, metrics = self.evaluation.get_pooled_eval_result(
                        plan,
                    )
                    pooled_result = (labels, outputs, metrics)
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
        trainers = self._safe_call_list(self.visualization.get_trainers)
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
                self._safe_averaged_record(trainer) for trainer in trainers
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
            params, requested_method = self._normalize_saliency_params(
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
    def _normalize_saliency_params(
        method: str | None,
        params: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], str | None]:
        """Normalize agent-friendly saliency args to evaluator-required keys."""
        raw = dict(params or {})
        requested_method = str(raw.pop("method", method or "") or "").strip() or None
        profile = str(raw.pop("profile", "") or "").strip().lower()
        explicit_methods = AnalysisCommandService._normalize_saliency_methods(
            raw.pop("methods", None),
        )
        configured_method_keys = [
            key
            for key in _SUPPORTED_SALIENCY_PARAM_KEYS
            if isinstance(raw.get(key), dict)
        ]
        flat_params: dict[str, Any] = {}
        normalized: dict[str, Any] = {
            key: dict(_DEFAULT_SALIENCY_PARAMS)
            for key in _SUPPORTED_SALIENCY_PARAM_KEYS
        }
        for key, value in raw.items():
            if key in _SUPPORTED_SALIENCY_PARAM_KEYS and isinstance(value, dict):
                normalized[key].update(value)
            elif key not in _SUPPORTED_SALIENCY_PARAM_KEYS:
                flat_params[key] = value
        if flat_params:
            for key in _SUPPORTED_SALIENCY_PARAM_KEYS:
                method_params = normalized[key]
                method_params.update(flat_params)
        selected_methods = AnalysisCommandService._select_saliency_methods(
            requested_method=requested_method,
            profile=profile,
            explicit_methods=explicit_methods,
            configured_method_keys=configured_method_keys,
        )
        normalized["_methods"] = selected_methods
        if profile:
            normalized["_profile"] = profile
        return normalized, requested_method

    @staticmethod
    def _normalize_saliency_methods(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = [value]
        elif isinstance(value, (list, tuple, set)):
            items = list(value)
        else:
            return []

        methods = []
        for item in items:
            method = str(item).strip()
            if method in _ALL_SALIENCY_METHODS and method not in methods:
                methods.append(method)
        return methods

    @staticmethod
    def _select_saliency_methods(
        *,
        requested_method: str | None,
        profile: str,
        explicit_methods: list[str],
        configured_method_keys: list[str],
    ) -> list[str]:
        if explicit_methods:
            return explicit_methods
        if profile == "recommended":
            return list(_RECOMMENDED_SALIENCY_METHODS)
        if profile == "advanced":
            return configured_method_keys or list(_SUPPORTED_SALIENCY_PARAM_KEYS)
        if requested_method in _ALL_SALIENCY_METHODS:
            return [requested_method]
        if configured_method_keys:
            return configured_method_keys
        return list(_ALL_SALIENCY_METHODS)

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

    def _safe_model_summary(self, plan: Any, record: Any | None = None) -> str:
        try:
            return str(self.evaluation.get_model_summary_str(plan, record))
        except Exception:
            logger.debug("Failed to build evaluation model summary", exc_info=True)
            return ""

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
                "plan": self._safe_model_summary(plan),
                "runs": [self._safe_model_summary(plan, run) for run in runs],
            }

        if requested_plan_index is not None and plan_index != requested_plan_index:
            return {"plan": "", "runs": [""] * len(runs)}

        run_summaries = [""] * len(runs)
        if requested_run_index is None:
            return {
                "plan": self._safe_model_summary(plan),
                "runs": run_summaries,
            }

        if 0 <= requested_run_index < len(runs):
            run_summaries[requested_run_index] = self._safe_model_summary(
                plan,
                runs[requested_run_index],
            )
        return {"plan": "", "runs": run_summaries}

    def _safe_averaged_record(self, trainer: Any) -> Any:
        try:
            return self.visualization.get_averaged_record(trainer)
        except Exception:
            logger.debug("Failed to build averaged visualization record", exc_info=True)
            return None

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
