"""Focused tests for analysis and visualization command handlers."""

from __future__ import annotations

from typing import Any, cast

import numpy as np

from XBrainLab.backend.application.analysis_service import (
    AnalysisCommandService,
    HandlerResult,
)
from XBrainLab.backend.application.commands import (
    ApplyMontageCommand,
    EvaluateCommand,
    SaliencyCommand,
    VisualizeCommand,
)
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


class _Run:
    def __init__(self, finished: bool) -> None:
        self._finished = finished
        self.eval_record = object() if finished else None

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

    def get_plans(self) -> list[_Plan]:
        return list(self._plans)

    def get_pooled_eval_result(
        self,
        _plan: _Plan,
    ) -> tuple[list[int], list[int], dict[str, Any]]:
        return [], [], {"accuracy": np.float32(0.75)}


class _VisualizationController:
    def __init__(self) -> None:
        self.params: dict[str, Any] | None = None

    def get_trainers(self) -> list[str]:
        return ["trainer-a"]

    def set_saliency_params(self, params: dict[str, Any]) -> None:
        self.params = params

    def get_saliency_params(self) -> dict[str, Any] | None:
        return self.params


class _PreprocessController:
    def __init__(self) -> None:
        self.applied_montage: tuple[list[str], list[tuple[float, float, float]]] | None
        self.applied_montage = None

    def apply_montage(
        self,
        channels: list[str],
        positions: list[tuple[float, float, float]],
    ) -> None:
        self.applied_montage = (channels, positions)


def _state(
    *,
    has_epoch: bool = True,
    saliency_available: bool = False,
    saliency_configured: bool = False,
    finished_runs: int = 0,
    has_model: bool = True,
    has_training_option: bool = True,
    has_trainer: bool = False,
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
            montage_available=True,
            channel_positions_available=True,
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
) -> tuple[AnalysisCommandService, _VisualizationController, _PreprocessController]:
    visualization = _VisualizationController()
    preprocess = _PreprocessController()
    service = AnalysisCommandService(
        evaluation=evaluation or _EvaluationController([]),
        visualization=visualization,
        preprocess=preprocess,
        get_state=lambda: state or _state(),
    )
    return service, visualization, preprocess


def _expect_payload(result: HandlerResult) -> tuple[str, dict[str, Any]]:
    assert isinstance(result, tuple)
    return cast(tuple[str, dict[str, Any]], result)


def test_analysis_service_summarizes_finished_evaluation_runs() -> None:
    plan = _Plan("Plan A", [_Run(finished=True), _Run(finished=False)])
    service, _visualization, _preprocess = _service(
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
    assert diagnostics["plans"][0]["name"] == "Plan A"
    assert diagnostics["plans"][0]["metrics"] == {"accuracy": 0.75}


def test_analysis_service_visualize_saliency_and_montage_handlers() -> None:
    state = _state(saliency_available=True, saliency_configured=True, finished_runs=1)
    service, visualization, preprocess = _service(state=state)

    _visualize_message, visualize = _expect_payload(
        service.handle_visualize(VisualizeCommand(view="summary")),
    )
    _saliency_message, saliency = _expect_payload(
        service.handle_saliency(
            SaliencyCommand(method="Gradient", params={"nt_samples": 2}),
        ),
    )
    montage_message, montage = _expect_payload(
        service.handle_apply_montage(
            ApplyMontageCommand(
                channels=["Cz"],
                positions=[(0.0, 0.0, 0.0)],
                montage_name="standard_1020",
            ),
        ),
    )

    assert visualize["payload_type"] == "visualization_summary"
    assert "saliency map" in visualize["available_views"]
    assert saliency["payload_type"] == "saliency_configuration"
    assert saliency["requested_method"] == "Gradient"
    assert saliency["params"]["SmoothGrad"]["nt_samples"] == 2
    assert visualization.params is not None
    assert preprocess.applied_montage == (["Cz"], [(0.0, 0.0, 0.0)])
    assert montage_message == "Applied montage 'standard_1020' to 1 channel(s)."
    assert montage == {"channel_count": 1, "montage_name": "standard_1020"}
