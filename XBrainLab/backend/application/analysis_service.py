"""Analysis and visualization command handlers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
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
    EvaluationModelSummary,
    EvaluationModelSummaryPreparation,
    EvaluationPlanIdentity,
    EvaluationRunIdentity,
    EvaluationSummaryIdentity,
    build_evaluation_cross_fold_choices,
    build_evaluation_model_summary_result,
    build_prepared_evaluation_model_summary,
    prepare_evaluation_model_summary,
)
from .owned_work import owned_work_checkpoint
from .resource_guard import ResourcePreflightResult
from .saliency_policy import (
    ADVANCED_SALIENCY_METHODS,
    merge_saliency_recompute_params,
    normalize_saliency_params,
    selected_saliency_methods_from_params,
)
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
        result, _plans = self._build_evaluation_catalog(command)
        if command.summary_identity is None:
            return result
        model_summary = build_evaluation_model_summary_result(
            self.training_runtime,
            command.summary_identity,
        )
        return self.complete_prepared_evaluate(result, command, model_summary)

    def prepare_evaluate(
        self,
        command: Command,
    ) -> tuple[
        tuple[str, dict[str, Any]],
        EvaluationModelSummaryPreparation | None,
    ]:
        """Capture an Evaluation catalog and lightweight summary target."""
        if not isinstance(command, EvaluateCommand):
            raise TypeError("Invalid command for evaluate")
        result, plans = self._build_evaluation_catalog(command)
        if command.summary_identity is None:
            return result, None
        preparation = prepare_evaluation_model_summary(
            plans,
            command.summary_identity,
        )
        return result, preparation

    @staticmethod
    def build_prepared_model_summary(
        preparation: EvaluationModelSummaryPreparation,
    ) -> EvaluationModelSummary:
        """Perform model construction and torchinfo inspection for one target."""
        return build_prepared_evaluation_model_summary(preparation)

    @staticmethod
    def complete_prepared_evaluate(
        result: tuple[str, dict[str, Any]],
        command: EvaluateCommand,
        model_summary: EvaluationModelSummary,
    ) -> tuple[str, dict[str, Any]]:
        """Attach one verified summary to its already captured catalog."""
        if command.summary_identity is None:
            raise TypeError("EvaluateCommand.summary_identity must be provided")
        if not isinstance(model_summary, EvaluationModelSummary):
            raise TypeError("model_summary must be an EvaluationModelSummary")
        message, diagnostics = result
        return (
            message,
            {
                **diagnostics,
                "model_summary": {
                    "identity": command.summary_identity.to_dict(),
                    "status": model_summary.status,
                    "text": model_summary.text,
                },
            },
        )

    def _build_evaluation_catalog(
        self,
        command: EvaluateCommand,
    ) -> tuple[tuple[str, dict[str, Any]], list[Any]]:
        """Build the lightweight Evaluation catalog without model inspection."""
        owned_work_checkpoint("Reading evaluation plans")
        plans = list(self.training_runtime.training_plan_holders())
        owned_work_checkpoint("Evaluation plans ready")
        summaries: list[_EvaluationPlanSummary] = []
        evaluation_splits: set[str] = set()
        for plan_idx, plan in enumerate(plans):
            owned_work_checkpoint(
                f"Reading evaluation plan {plan_idx + 1} of {len(plans)}",
                completed=plan_idx,
                total=len(plans),
            )
            runs = self._safe_plan_runs(plan)
            finished = []
            run_summaries: list[_EvaluationRunSummary] = []
            for run_index, run in enumerate(runs):
                owned_work_checkpoint(
                    (f"Reading evaluation run {run_index + 1} of {len(runs)}"),
                    completed=run_index,
                    total=len(runs),
                )
                run_finished = self._run_finished(run)
                if run_finished:
                    finished.append(run)
                run_summaries.append(
                    {
                        "identity": EvaluationRunIdentity(
                            plan=EvaluationPlanIdentity(plan_index=plan_idx),
                            run_index=run_index,
                        ).to_dict(),
                        "name": self._safe_run_name(run, run_index),
                        "finished": run_finished,
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
                )
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
                    "runs": run_summaries,
                }
            )
            owned_work_checkpoint(
                f"Evaluation plan {plan_idx + 1} ready",
                completed=plan_idx + 1,
                total=len(plans),
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
        if command.summary_identity is not None and not isinstance(
            command.summary_identity,
            EvaluationSummaryIdentity,
        ):
            raise TypeError(
                "EvaluateCommand.summary_identity must be an EvaluationSummaryIdentity"
            )
        return (message, diagnostics), plans

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
            available_views.extend(["saliency map", "spectrogram"])
            if state.visualization.channel_positions_available:
                available_views.append("topographic map")
            if state.visualization.three_dimensional_positions_available:
                available_views.append("3D plot")
            if not state.visualization.channel_positions_available:
                preparation_state = state.visualization.montage_preparation_state
                reason = (
                    "Preparing electrode positions..."
                    if preparation_state == "pending"
                    else "Set Montage before opening the topographic map."
                )
                blocked_views["topographic map"] = [reason]
            if not state.visualization.three_dimensional_positions_available:
                preparation_state = state.visualization.montage_preparation_state
                blocked_views["3D plot"] = [
                    (
                        "Preparing electrode positions..."
                        if preparation_state == "pending"
                        else "Set a 3D montage before opening the 3D plot."
                    )
                ]
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
            "montage_source": state.visualization.montage_source,
            "montage_preparation_state": (
                state.visualization.montage_preparation_state
            ),
            "montage_preparation_reason": (
                state.visualization.montage_preparation_reason
            ),
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
            automatic_target = current_post_training_saliency_target()
            if automatic_target is not None and automatic_target.explicit:
                params = self._accumulated_saliency_recompute_params(params, state)
            resource_preflight = self._saliency_resource_preflight(
                command,
                params,
                evaluator_required=state.active_training.has_trainer,
            )
            self.visualization.set_saliency_params(params)
            if automatic_target is not None:
                schedule = automatic_target.schedule_outcome
                if schedule is None:
                    raise PreconditionError(
                        "Saliency scheduler did not publish an outcome.",
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

    def _accumulated_saliency_recompute_params(
        self,
        incoming_params: dict[str, Any],
        state: ApplicationStateSnapshot,
    ) -> dict[str, Any]:
        """Add verified completed methods to one explicit full recomputation."""
        completed_methods = {
            method.method
            for run in state.visualization.saliency_coverage
            for method in run.methods
            if method.available and method.complete
        }
        incoming_methods = selected_saliency_methods_from_params(incoming_params)
        retained_advanced = (
            completed_methods.intersection(ADVANCED_SALIENCY_METHODS) - incoming_methods
        )
        retained_params = self._retained_saliency_method_params(
            state,
            retained_advanced,
        )
        try:
            return merge_saliency_recompute_params(
                incoming_params,
                completed_methods=completed_methods,
                retained_method_params=retained_params,
            )
        except ValueError as exc:
            raise self._completed_saliency_params_error(str(exc)) from exc

    def _retained_saliency_method_params(
        self,
        state: ApplicationStateSnapshot,
        retained_methods: set[str],
    ) -> dict[str, dict[str, Any]]:
        if not retained_methods:
            return {}
        try:
            holders = tuple(self.training_runtime.training_plan_holders())
        except Exception as exc:
            raise self._completed_saliency_params_error(
                "Completed saliency records could not be read."
            ) from exc

        retained: dict[str, dict[str, Any]] = {}
        for run_coverage in state.visualization.saliency_coverage:
            covered_methods = {
                method.method
                for method in run_coverage.methods
                if method.available
                and method.complete
                and method.method in retained_methods
            }
            if not covered_methods:
                continue
            try:
                holder = holders[run_coverage.plan_index]
                runs = tuple(holder.get_plans())
                run = runs[run_coverage.run_index]
                record_getter = getattr(run, "get_saliency_eval_record", None)
                record = (
                    record_getter()
                    if callable(record_getter)
                    else getattr(run, "eval_record", None)
                )
                artifact_params = getattr(record, "saliency_method_parameters", None)
            except Exception as exc:
                raise self._completed_saliency_params_error(
                    "Completed saliency records changed while settings were applied."
                ) from exc
            if not isinstance(artifact_params, Mapping):
                missing = sorted(covered_methods)[0]
                raise self._completed_saliency_params_error(
                    f"Completed saliency parameters are unavailable for {missing}."
                )
            for method in ADVANCED_SALIENCY_METHODS:
                if method not in covered_methods:
                    continue
                raw_params = artifact_params.get(method)
                if not isinstance(raw_params, Mapping):
                    raise self._completed_saliency_params_error(
                        f"Completed saliency parameters are unavailable for {method}."
                    )
                try:
                    normalized, _requested_method = normalize_saliency_params(
                        method,
                        raw_params,
                    )
                except (TypeError, ValueError) as exc:
                    raise self._completed_saliency_params_error(
                        f"Completed saliency parameters are invalid for {method}."
                    ) from exc
                effective = dict(normalized[method])
                previous = retained.get(method)
                if previous is not None and not _strict_saliency_params_equal(
                    previous,
                    effective,
                ):
                    raise self._completed_saliency_params_error(
                        f"Completed saliency parameters conflict for {method}. "
                        "Select that method in Saliency Settings to choose one "
                        "configuration."
                    )
                retained[method] = effective

        missing_methods = retained_methods.difference(retained)
        if missing_methods:
            missing = next(
                method
                for method in ADVANCED_SALIENCY_METHODS
                if method in missing_methods
            )
            raise self._completed_saliency_params_error(
                f"Completed saliency parameters are unavailable for {missing}."
            )
        return retained

    @staticmethod
    def _completed_saliency_params_error(message: str) -> PreconditionError:
        return PreconditionError(
            message,
            diagnostics={
                "reason": "completed_saliency_parameters_unavailable",
                "state_preserved": True,
            },
        )

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
