"""Focused tests for analysis and visualization command handlers."""

from __future__ import annotations

from typing import Any, cast

import numpy as np
import pytest

from XBrainLab.backend.application.analysis_service import (
    AnalysisCommandService,
    HandlerResult,
)
from XBrainLab.backend.application.commands import (
    EvaluateCommand,
    SaliencyCommand,
    VisualizeCommand,
)
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.state import (
    ActiveDatasetSnapshot,
    ActiveTrainingSnapshot,
    ApplicationStateSnapshot,
    DatasetStateSnapshot,
    EpochStateSnapshot,
    EvaluationStateSnapshot,
    InterpretationStateSnapshot,
    PreprocessedStateSnapshot,
    RawStateSnapshot,
    TrainingStateSnapshot,
    VisualizationStateSnapshot,
)
from XBrainLab.backend.training_manager import (
    PostTrainingSaliencyTarget,
    TrainingManager,
    post_training_saliency_target,
)
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyScheduleDisposition,
    PostTrainingSaliencyScheduleReason,
    TrainingRunIdentity,
)


class _EvalRecord:
    def __init__(self, evaluation_split: str) -> None:
        self.evaluation_split = evaluation_split


class _Run:
    def __init__(self, finished: bool, *, evaluation_split: str = "test") -> None:
        self._finished = finished
        self.eval_record = _EvalRecord(evaluation_split) if finished else None

    def is_finished(self) -> bool:
        return self._finished


class _Plan:
    def __init__(self, name: str, runs: list[_Run]) -> None:
        self._name = name
        self._runs = runs

    def get_name(self) -> str:
        return self._name

    def get_plans(self) -> list[_Run]:
        return list(self._runs)


class _EvaluationController:
    def __init__(self, plans: list[_Plan]) -> None:
        self._plans = plans
        self.pooled_result_calls = 0
        self.model_summary_calls = 0

    def get_plans(self) -> list[_Plan]:
        return list(self._plans)

    def get_pooled_eval_result(
        self,
        _plan: _Plan,
    ) -> tuple[list[int], list[int], dict[str, Any]]:
        self.pooled_result_calls += 1
        return [], [], {"accuracy": np.float32(0.75)}

    def get_model_summary_str(self, plan: _Plan, record: _Run | None = None) -> str:
        self.model_summary_calls += 1
        suffix = " run" if record is not None else ""
        return f"{plan.get_name()} summary{suffix}"


class _BrokenEvaluationController(_EvaluationController):
    def get_plans(self) -> list[_Plan]:
        raise RuntimeError("evaluation query failed")


class _BrokenModelSummaryController(_EvaluationController):
    def get_model_summary_str(self, plan: _Plan, record: _Run | None = None) -> str:
        raise RuntimeError("model summary failed")


class _VisualizationController:
    def __init__(self) -> None:
        self.params: dict[str, Any] | None = None
        self.averaged_record_calls = 0

    def get_trainers(self) -> list[str]:
        return ["trainer-a"]

    def get_averaged_record(self, trainer: Any) -> str:
        self.averaged_record_calls += 1
        return f"{trainer}-average"

    def set_saliency_params(self, params: dict[str, Any]) -> None:
        self.params = params

    def get_saliency_params(self) -> dict[str, Any] | None:
        return self.params


class _BrokenVisualizationController(_VisualizationController):
    def get_trainers(self) -> list[str]:
        raise RuntimeError("visualization query failed")


class _BrokenAveragedRecordController(_VisualizationController):
    def get_averaged_record(self, trainer: Any) -> str:
        raise RuntimeError("averaged record failed")


def _state(
    *,
    has_epoch: bool = True,
    saliency_available: bool = False,
    saliency_configured: bool = False,
    finished_runs: int = 0,
    montage_available: bool = True,
    channel_positions_available: bool = True,
    has_model: bool = True,
    has_training_option: bool = True,
    has_trainer: bool = False,
    is_training: bool = False,
) -> ApplicationStateSnapshot:
    return ApplicationStateSnapshot(
        pipeline_stage="dataset_ready",
        raw=RawStateSnapshot(),
        preprocessed=PreprocessedStateSnapshot(),
        epoch=EpochStateSnapshot(available=has_epoch, exists=has_epoch),
        dataset=DatasetStateSnapshot(available=True, count=1),
        training=TrainingStateSnapshot(
            has_model=has_model,
            has_training_option=has_training_option,
            has_trainer=has_trainer,
            is_running=is_training,
        ),
        evaluation=EvaluationStateSnapshot(
            available=finished_runs > 0,
            total_plans=1 if finished_runs else 0,
            total_runs=finished_runs,
            finished_runs=finished_runs,
            metrics_available=finished_runs > 0,
        ),
        visualization=VisualizationStateSnapshot(
            saliency_configured=saliency_configured,
            saliency_available=saliency_available,
            montage_available=montage_available,
            channel_positions_available=channel_positions_available,
            channel_count=1,
        ),
        interpretation=InterpretationStateSnapshot(),
        active_dataset=ActiveDatasetSnapshot(
            has_epoch_data=has_epoch, has_datasets=True
        ),
        active_training=ActiveTrainingSnapshot(
            has_model=has_model,
            has_training_option=has_training_option,
            has_trainer=has_trainer,
        ),
    )


def _service(
    *,
    state: ApplicationStateSnapshot | None = None,
    evaluation: _EvaluationController | None = None,
) -> tuple[AnalysisCommandService, _VisualizationController]:
    visualization = _VisualizationController()
    service = AnalysisCommandService(
        evaluation=evaluation or _EvaluationController([]),
        visualization=visualization,
        get_state=lambda: state or _state(),
    )
    return service, visualization


def _expect_payload(result: HandlerResult) -> tuple[str, dict[str, Any]]:
    assert isinstance(result, tuple)
    return cast(tuple[str, dict[str, Any]], result)


def test_analysis_service_summarizes_finished_evaluation_runs() -> None:
    plan = _Plan("Plan A", [_Run(finished=True), _Run(finished=False)])
    service, _visualization = _service(
        evaluation=_EvaluationController([plan]),
    )

    message, diagnostics = _expect_payload(
        service.handle_evaluate(EvaluateCommand(target="latest")),
    )

    assert message == "Evaluation summary ready."
    assert diagnostics["payload_type"] == "evaluation_summary"
    assert diagnostics["available"] is True
    assert diagnostics["target"] == "latest"
    assert diagnostics["plan_count"] == 1
    assert diagnostics["finished_run_count"] == 1
    assert diagnostics["evaluation_splits"] == ["test"]
    assert diagnostics["training_active"] is False
    assert diagnostics["plans"][0]["name"] == "Plan A"
    assert diagnostics["plans"][0]["evaluation_splits"] == ["test"]
    assert diagnostics["plans"][0]["metrics"] == {"accuracy": 0.75}


def test_analysis_service_reports_validation_fallback_provenance() -> None:
    plan = _Plan(
        "Plan A",
        [
            _Run(finished=True, evaluation_split="validation"),
            _Run(finished=True, evaluation_split="test"),
        ],
    )
    service, _visualization = _service(
        evaluation=_EvaluationController([plan]),
    )

    _message, diagnostics = _expect_payload(
        service.handle_evaluate(EvaluateCommand(target="latest")),
    )

    assert diagnostics["evaluation_splits"] == ["test", "validation"]
    assert diagnostics["plans"][0]["evaluation_splits"] == ["test", "validation"]


def test_analysis_service_reports_no_results_without_facade() -> None:
    service, _visualization = _service(
        evaluation=_EvaluationController([]),
    )

    message, diagnostics = _expect_payload(
        service.handle_evaluate(EvaluateCommand(target="latest")),
    )

    assert message == "No completed training runs are available for evaluation yet."
    assert diagnostics["payload_type"] == "evaluation_summary"
    assert diagnostics["available"] is False
    assert diagnostics["plan_count"] == 0
    assert diagnostics["finished_run_count"] == 0
    assert diagnostics["training_active"] is False
    assert diagnostics["plans"] == []


def test_analysis_service_does_not_turn_evaluation_failure_into_empty_success() -> None:
    service, _visualization = _service(
        evaluation=_BrokenEvaluationController([]),
    )

    with pytest.raises(RuntimeError, match="evaluation query failed"):
        service.handle_evaluate(EvaluateCommand(target="latest"))


def test_analysis_service_does_not_turn_visualization_failure_into_empty_success() -> (
    None
):
    visualization = _BrokenVisualizationController()
    service = AnalysisCommandService(
        evaluation=_EvaluationController([]),
        visualization=visualization,
        get_state=_state,
    )

    with pytest.raises(RuntimeError, match="visualization query failed"):
        service.handle_visualize(VisualizeCommand(view="summary"))


def test_analysis_service_does_not_hide_requested_model_summary_failure() -> None:
    plan = _Plan("Plan A", [_Run(finished=True)])
    service, _visualization = _service(
        evaluation=_BrokenModelSummaryController([plan]),
    )

    with pytest.raises(RuntimeError, match="model summary failed"):
        service.handle_evaluate(EvaluateCommand(include_model_summaries=True))


def test_analysis_service_does_not_hide_requested_averaged_record_failure() -> None:
    visualization = _BrokenAveragedRecordController()
    service = AnalysisCommandService(
        evaluation=_EvaluationController([]),
        visualization=visualization,
        get_state=lambda: _state(finished_runs=1),
    )

    with pytest.raises(RuntimeError, match="averaged record failed"):
        service.handle_visualize(
            VisualizeCommand(view="summary", include_averaged_records=True),
        )


def test_analysis_service_reports_training_active_without_facade() -> None:
    plan_a = _Plan("Plan A", [_Run(finished=True)])
    plan_b = _Plan("Plan B", [_Run(finished=True)])
    service, _visualization = _service(
        state=_state(is_training=True, finished_runs=2),
        evaluation=_EvaluationController([plan_a, plan_b]),
    )

    _message, diagnostics = _expect_payload(
        service.handle_evaluate(EvaluateCommand(target="latest")),
    )

    assert diagnostics["plan_count"] == 2
    assert diagnostics["finished_run_count"] == 2
    assert diagnostics["training_active"] is True
    assert [plan["name"] for plan in diagnostics["plans"]] == ["Plan A", "Plan B"]


def test_analysis_service_can_return_ui_evaluation_objects() -> None:
    plan = _Plan("Plan A", [_Run(finished=True), _Run(finished=False)])
    service, _visualization = _service(
        evaluation=_EvaluationController([plan]),
    )

    _message, diagnostics = _expect_payload(
        service.handle_evaluate(
            EvaluateCommand(
                include_objects=True,
                include_pooled_results=True,
                include_model_summaries=True,
            ),
        ),
    )

    assert diagnostics["plan_objects"] == [plan]
    assert diagnostics["pooled_eval_results"][0][2] == {"accuracy": 0.75}
    assert diagnostics["model_summaries"][0]["plan"] == "Plan A summary"
    assert diagnostics["model_summaries"][0]["runs"] == [
        "Plan A summary run",
        "Plan A summary run",
    ]


def test_analysis_service_targets_requested_model_summary_only() -> None:
    plan_a = _Plan("Plan A", [_Run(finished=True), _Run(finished=True)])
    plan_b = _Plan("Plan B", [_Run(finished=True)])
    evaluation = _EvaluationController([plan_a, plan_b])
    service, _visualization = _service(evaluation=evaluation)

    _message, diagnostics = _expect_payload(
        service.handle_evaluate(
            EvaluateCommand(
                include_model_summaries=True,
                model_summary_plan_index=1,
                model_summary_run_index=0,
            ),
        ),
    )

    assert diagnostics["model_summaries"] == [
        {"plan": "", "runs": ["", ""]},
        {"plan": "", "runs": ["Plan B summary run"]},
    ]
    assert evaluation.model_summary_calls == 1


def test_analysis_service_can_skip_heavy_evaluation_payloads() -> None:
    plan = _Plan("Plan A", [_Run(finished=True), _Run(finished=False)])
    evaluation = _EvaluationController([plan])
    service, _visualization = _service(evaluation=evaluation)

    _message, diagnostics = _expect_payload(
        service.handle_evaluate(
            EvaluateCommand(include_objects=True, include_metrics=False),
        ),
    )

    assert diagnostics["plan_objects"] == [plan]
    assert diagnostics["plans"][0]["metrics"] == {}
    assert "pooled_eval_results" not in diagnostics
    assert "model_summaries" not in diagnostics
    assert evaluation.pooled_result_calls == 0
    assert evaluation.model_summary_calls == 0


def test_analysis_service_visualize_and_saliency_handlers() -> None:
    state = _state(saliency_available=True, saliency_configured=True, finished_runs=1)
    service, visualization = _service(state=state)

    _visualize_message, visualize = _expect_payload(
        service.handle_visualize(VisualizeCommand(view="summary")),
    )
    _saliency_message, saliency = _expect_payload(
        service.handle_saliency(
            SaliencyCommand(method="Gradient", params={"nt_samples": 2}),
        ),
    )
    assert visualize["payload_type"] == "visualization_summary"
    assert "saliency map" in visualize["available_views"]
    assert saliency["payload_type"] == "saliency_configuration"
    assert saliency["requested_method"] == "Gradient"
    assert saliency["params"]["_methods"] == ["Gradient"]
    assert saliency["params"]["SmoothGrad"]["nt_samples"] == 2
    assert visualization.params is not None


def test_analysis_service_rejects_automatic_scheduler_noop_with_terminal_status() -> (
    None
):
    manager = TrainingManager()

    class _ManagerVisualizationController(_VisualizationController):
        def set_saliency_params(self, params: dict[str, Any]):
            self.params = params
            return manager.set_saliency_params(params)

        def get_saliency_params(self) -> dict[str, Any] | None:
            return manager.get_saliency_params()

    visualization = _ManagerVisualizationController()
    service = AnalysisCommandService(
        evaluation=_EvaluationController([]),
        visualization=visualization,
        get_state=lambda: _state(has_trainer=True, finished_runs=1),
    )
    run = TrainingRunIdentity(trainer_id="missing-trainer", run_id=1)
    target = PostTrainingSaliencyTarget(
        run=run,
        finished_runs_before=0,
        finished_runs_after=1,
        append=True,
    )

    with (
        post_training_saliency_target(target),
        pytest.raises(PreconditionError) as raised,
    ):
        service.handle_saliency(
            SaliencyCommand(
                method="Gradient",
                params={
                    "profile": "recommended",
                    "methods": ["Gradient", "Gradient * Input"],
                },
            )
        )

    schedule = target.schedule_outcome
    assert schedule is not None
    assert schedule.disposition is PostTrainingSaliencyScheduleDisposition.STALE
    assert schedule.reason is PostTrainingSaliencyScheduleReason.TRAINER_UNAVAILABLE
    assert schedule.status.phase is PostTrainingSaliencyPhase.CANCELLED
    assert str(raised.value) == schedule.status.message == schedule.message
    assert raised.value.diagnostics["post_training_saliency_schedule"] == (
        schedule.to_dict()
    )


def test_analysis_service_settings_params_select_only_advanced_methods() -> None:
    state = _state(saliency_available=False, saliency_configured=False, finished_runs=1)
    service, visualization = _service(state=state)

    _message, saliency = _expect_payload(
        service.handle_saliency(
            SaliencyCommand(
                params={
                    "SmoothGrad": {"nt_samples": 3},
                    "SmoothGrad_Squared": {"nt_samples": 3},
                    "VarGrad": {"nt_samples": 3},
                },
            ),
        ),
    )

    assert saliency["payload_type"] == "saliency_configuration"
    assert saliency["params"]["_methods"] == [
        "SmoothGrad",
        "SmoothGrad_Squared",
        "VarGrad",
    ]
    assert visualization.params is not None
    assert visualization.params["_methods"] == [
        "SmoothGrad",
        "SmoothGrad_Squared",
        "VarGrad",
    ]


def test_analysis_service_reports_saliency_configuration_readiness() -> None:
    state = _state(
        has_epoch=True,
        has_model=False,
        has_training_option=False,
        has_trainer=False,
    )
    service, _visualization = _service(state=state)

    _message, saliency = _expect_payload(service.handle_saliency(SaliencyCommand()))

    assert saliency["payload_type"] == "saliency_summary"
    assert saliency["configure_available"] is False
    assert saliency["configure_reasons"] == [
        "Select a model and training settings before configuring saliency."
    ]


def test_analysis_service_reports_montage_setup_without_plot_views() -> None:
    state = _state(
        has_epoch=True,
        saliency_available=False,
        saliency_configured=False,
        finished_runs=0,
    )
    service, _visualization = _service(state=state)

    _message, visualize = _expect_payload(
        service.handle_visualize(VisualizeCommand(view="summary")),
    )

    assert visualize["payload_type"] == "visualization_summary"
    assert visualize["available"] is True
    assert visualize["available_views"] == ["montage setup"]
    assert visualize["plot_views_available"] is False


def test_analysis_service_requires_channel_positions_for_3d_plot() -> None:
    state = _state(
        saliency_available=True,
        saliency_configured=True,
        finished_runs=1,
        montage_available=False,
        channel_positions_available=False,
    )
    service, _visualization = _service(state=state)

    _message, visualize = _expect_payload(
        service.handle_visualize(VisualizeCommand(view="summary")),
    )

    assert "saliency map" in visualize["available_views"]
    assert "3D plot" not in visualize["available_views"]
    assert visualize["blocked_views"]["3D plot"] == [
        "Set Montage before opening the 3D plot."
    ]


def test_analysis_service_can_return_ui_visualization_objects_without_averaging() -> (
    None
):
    state = _state(saliency_available=True, saliency_configured=True, finished_runs=1)
    service, visualization = _service(state=state)

    _message, diagnostics = _expect_payload(
        service.handle_visualize(
            VisualizeCommand(view="summary", include_objects=True)
        ),
    )

    assert diagnostics["trainer_objects"] == ["trainer-a"]
    assert "averaged_records" not in diagnostics
    assert visualization.averaged_record_calls == 0


def test_analysis_service_returns_averaged_records_only_when_requested() -> None:
    state = _state(saliency_available=True, saliency_configured=True, finished_runs=1)
    service, visualization = _service(state=state)

    _message, diagnostics = _expect_payload(
        service.handle_visualize(
            VisualizeCommand(
                view="summary",
                include_objects=True,
                include_averaged_records=True,
            )
        ),
    )

    assert diagnostics["averaged_records"] == ["trainer-a-average"]
    assert visualization.averaged_record_calls == 1
