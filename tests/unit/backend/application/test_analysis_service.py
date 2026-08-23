"""Focused tests for analysis and visualization command handlers."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import numpy as np
import pytest

from XBrainLab.backend.application import saliency_resource
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
from XBrainLab.backend.application.evaluation_render import (
    EvaluationModelSummary,
    EvaluationPlanIdentity,
    EvaluationRunIdentity,
    EvaluationSummaryIdentity,
)
from XBrainLab.backend.application.resource_guard import (
    ResourceConfirmationRequiredError,
    ResourcePreflightResult,
)
from XBrainLab.backend.application.resource_preflight import ResourcePreflightView
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
    SaliencyMethodCoverageSnapshot,
    SaliencyRunCoverageSnapshot,
    TrainingStateSnapshot,
    VisualizationStateSnapshot,
)
from XBrainLab.backend.application.training_runtime import TrainingRuntimeContext
from XBrainLab.backend.training_manager import (
    PostTrainingSaliencyTarget,
    TrainingManager,
    current_post_training_saliency_target,
    post_training_saliency_target,
)
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyScheduleDisposition,
    PostTrainingSaliencyScheduleOutcome,
    PostTrainingSaliencyScheduleReason,
    PostTrainingSaliencyStatus,
    TrainingRunIdentity,
)


class _EvalRecord:
    def __init__(self, evaluation_split: str) -> None:
        self.evaluation_split = evaluation_split


class _Run:
    def __init__(self, finished: bool, *, evaluation_split: str = "test") -> None:
        self._finished = finished
        self.eval_record = _EvalRecord(evaluation_split) if finished else None
        self.evaluation_records = (
            {evaluation_split: self.eval_record} if self.eval_record is not None else {}
        )

    def is_finished(self) -> bool:
        return self._finished

    @staticmethod
    def get_name() -> str:
        return "Repeat-0"


class _Plan:
    def __init__(self, name: str, runs: list[_Run]) -> None:
        self._name = name
        self._runs = runs

    def get_name(self) -> str:
        return self._name

    def get_plans(self) -> list[_Run]:
        return list(self._runs)


class _ShapeOnlyArray:
    def __init__(self, shape: tuple[int, int, int]) -> None:
        self.shape = shape
        self.nbytes = math.prod(shape) * np.dtype(np.float32).itemsize


class _EpochData:
    def __init__(self, shape: tuple[int, int, int] = (8, 2, 16)) -> None:
        self._data = _ShapeOnlyArray(shape)
        self._labels = np.zeros(shape[0], dtype=np.int64)

    def get_data(self) -> _ShapeOnlyArray:
        return self._data

    def get_label_list(self) -> np.ndarray:
        return self._labels

    def get_model_args(self) -> dict[str, int]:
        return {
            "n_classes": 1,
            "channels": self._data.shape[1],
            "samples": self._data.shape[2],
            "sfreq": 128,
        }


class _Dataset:
    def __init__(self, shape: tuple[int, int, int] = (8, 2, 16)) -> None:
        self._epoch_data = _EpochData(shape)
        self.train_mask = np.zeros(shape[0], dtype=bool)
        self.val_mask = np.zeros(shape[0], dtype=bool)
        self.test_mask = np.ones(shape[0], dtype=bool)

    def get_epoch_data(self) -> _EpochData:
        return self._epoch_data


class _TrainingOption:
    def __init__(
        self,
        *,
        batch_size: int = 2,
        use_cpu: bool = True,
        gpu_idx: int | None = None,
    ) -> None:
        self.bs = batch_size
        self.repeat_num = 1
        self.use_cpu = use_cpu
        self.gpu_idx = gpu_idx


class _ModelParameter:
    @staticmethod
    def numel() -> int:
        return 1_024

    @staticmethod
    def element_size() -> int:
        return 4


class _Model:
    @staticmethod
    def parameters() -> list[_ModelParameter]:
        return [_ModelParameter()]

    def cpu(self) -> _Model:
        return self


class _ModelHolder:
    @staticmethod
    def get_model(_args: dict[str, Any]) -> _Model:
        return _Model()


class _TrainingRuntime:
    def __init__(
        self,
        plans: list[_Plan],
        *,
        datasets: tuple[_Dataset, ...] | None = None,
        training_option: _TrainingOption | None = None,
    ) -> None:
        self._plans = plans
        self._resource_context = TrainingRuntimeContext(
            datasets=datasets or (_Dataset(),),
            training_option=training_option or _TrainingOption(),
            model_holder=_ModelHolder(),
        )

    def training_plan_holders(self) -> tuple[_Plan, ...]:
        return tuple(self._plans)

    def resource_context(self) -> Any:
        return self._resource_context

    def is_training(self) -> bool:
        return False

    def current_training_plan_index(self) -> int | None:
        return None

    def progress_text(self) -> str:
        return ""


class _BrokenTrainingRuntime(_TrainingRuntime):
    def training_plan_holders(self) -> tuple[_Plan, ...]:
        raise RuntimeError("evaluation query failed")


class _BrokenSaliencyResourceRuntime(_TrainingRuntime):
    def resource_context(self) -> Any:
        raise RuntimeError("resource snapshot failed")


class _VisualizationController:
    def __init__(self) -> None:
        self.params: dict[str, Any] | None = None
        self.averaged_record_calls = 0
        self.saliency_set_calls = 0

    def get_trainers(self) -> list[str]:
        return ["trainer-a"]

    def get_averaged_record(self, trainer: Any) -> str:
        self.averaged_record_calls += 1
        return f"{trainer}-average"

    def set_saliency_params(self, params: dict[str, Any]) -> None:
        self.saliency_set_calls += 1
        self.params = params

    def get_saliency_params(self) -> dict[str, Any] | None:
        return self.params


class _SchedulingVisualizationController(_VisualizationController):
    def set_saliency_params(self, params: dict[str, Any]) -> None:
        super().set_saliency_params(params)
        target = current_post_training_saliency_target()
        if target is None:
            raise AssertionError("explicit saliency target is unavailable")
        methods = tuple(params.get("_methods", ()))
        status = PostTrainingSaliencyStatus.pending(
            generation=1,
            run=target.run,
            training_generation=7,
            methods=methods,
        )
        target.publish_schedule_outcome(
            PostTrainingSaliencyScheduleOutcome(
                disposition=PostTrainingSaliencyScheduleDisposition.SCHEDULED,
                reason=PostTrainingSaliencyScheduleReason.SCHEDULED,
                message=status.message or "Saliency is waiting to start.",
                status=status,
            )
        )


class _BrokenVisualizationController(_VisualizationController):
    def get_trainers(self) -> list[str]:
        raise RuntimeError("visualization query failed")


class _LossySaliencyController(_VisualizationController):
    def set_saliency_params(self, params: dict[str, Any]) -> None:
        self.params = {
            **params,
            "SmoothGrad": {
                "nt_samples": 5,
                "nt_samples_batch_size": None,
                "stdevs": 1.0,
            },
        }


class _TypeCoercingSaliencyController(_VisualizationController):
    def set_saliency_params(self, params: dict[str, Any]) -> None:
        self.params = {
            **params,
            "SmoothGrad": {
                **params["SmoothGrad"],
                "nt_samples": float(params["SmoothGrad"]["nt_samples"]),
            },
        }


class _EvaluatorSentinelController(_VisualizationController):
    def set_saliency_params(self, params: dict[str, Any]) -> None:
        raise AssertionError("saliency evaluator was reached before admission")


def _saliency_preflight(risk_level: str) -> ResourcePreflightResult:
    message = f"Saliency resource risk: {risk_level}."
    return ResourcePreflightResult(
        issues=(message,) if risk_level == "blocking" else (),
        warnings=(message,) if risk_level == "warning" else (),
        unknowns=(message,) if risk_level == "unknown" else (),
        diagnostics={
            "operation": "saliency_recomputation",
            "risk_level": risk_level,
            "required_memory_bytes": 1024,
        },
    )


def _resource_challenge(error: ResourceConfirmationRequiredError):
    preflight = ResourcePreflightView.from_diagnostics(error.diagnostics)
    assert preflight is not None
    assert preflight.challenge is not None
    return preflight.challenge


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
    saliency_params: dict[str, Any] | None = None,
    saliency_coverage: list[SaliencyRunCoverageSnapshot] | None = None,
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
            saliency_params=dict(saliency_params or {}),
            saliency_coverage=list(saliency_coverage or []),
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
    plans: list[_Plan] | None = None,
    training_runtime: _TrainingRuntime | None = None,
) -> tuple[AnalysisCommandService, _VisualizationController]:
    visualization = _VisualizationController()
    service = AnalysisCommandService(
        training_runtime=training_runtime or _TrainingRuntime(plans or []),
        visualization=visualization,
        get_state=lambda: state or _state(),
    )
    return service, visualization


def _expect_payload(result: HandlerResult) -> tuple[str, dict[str, Any]]:
    assert isinstance(result, tuple)
    return cast(tuple[str, dict[str, Any]], result)


def test_analysis_service_summarizes_finished_evaluation_runs() -> None:
    plan = _Plan("Plan A", [_Run(finished=True), _Run(finished=False)])
    service, _visualization = _service(plans=[plan])

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
    assert diagnostics["cross_fold_choices"] == []
    assert diagnostics["plans"][0] == {
        "identity": {"plan_index": 0},
        "name": "Plan A",
        "run_count": 2,
        "finished_run_count": 1,
        "evaluation_splits": ["test"],
        "runs": [
            {
                "identity": {"plan_index": 0, "run_index": 0},
                "name": "Repeat-0",
                "finished": True,
                "evaluation_split": "test",
                "evaluation_splits": ["test"],
            },
            {
                "identity": {"plan_index": 0, "run_index": 1},
                "name": "Repeat-0",
                "finished": False,
                "evaluation_split": "unknown",
                "evaluation_splits": [],
            },
        ],
    }


def test_analysis_service_publishes_only_admitted_cross_fold_runs() -> None:
    epoch_data = SimpleNamespace(label_map={0: "Left", 1: "Right"})
    config = SimpleNamespace(is_cross_validation=True)

    class Dataset:
        def __init__(self, mask: list[bool]) -> None:
            self.epoch_data = epoch_data
            self.config = config
            self.cross_validation_cohort_id = "cohort-1"
            self.test_mask = np.asarray(mask, dtype=bool)

        def get_epoch_data(self):
            return self.epoch_data

    def make_plan(mask: list[bool], labels: list[int], outputs: list[list[float]]):
        dataset = Dataset(mask)
        record = SimpleNamespace(
            label=np.asarray(labels),
            output=np.asarray(outputs),
            evaluation_split="test",
        )
        run = SimpleNamespace(
            dataset=dataset,
            eval_record=record,
            evaluation_records={"test": record},
            is_finished=lambda: True,
            get_name=lambda: "Repeat-0",
        )
        return SimpleNamespace(
            dataset=dataset,
            get_plans=lambda: [run],
            get_name=lambda: "Fold",
        )

    plans = [
        make_plan([True, False], [0], [[0.8, 0.2]]),
        make_plan([False, True], [1], [[0.1, 0.9]]),
    ]
    service, _visualization = _service(plans=plans)

    _message, diagnostics = _expect_payload(
        service.handle_evaluate(EvaluateCommand()),
    )

    assert diagnostics["cross_fold_choices"] == [
        {
            "identity": {
                "members": [
                    {"plan_index": 0, "run_index": 0},
                    {"plan_index": 1, "run_index": 0},
                ]
            },
            "display_name": "All Folds",
            "run_label": "Run 1 (Summary)",
            "evaluation_splits": ["test"],
            "fold_count": 2,
            "sample_count": 2,
        }
    ]


def test_analysis_service_keeps_appended_fold_round_summaries_independent() -> None:
    epoch_data = SimpleNamespace(label_map={0: "Left", 1: "Right"})
    config = SimpleNamespace(is_cross_validation=True)

    class Dataset:
        def __init__(self, mask: list[bool]) -> None:
            self.epoch_data = epoch_data
            self.config = config
            self.cross_validation_cohort_id = "cohort-1"
            self.test_mask = np.asarray(mask, dtype=bool)

        def get_epoch_data(self):
            return self.epoch_data

    fold_datasets = (Dataset([True, False]), Dataset([False, True]))

    def make_round(round_id: str):
        plans = []
        for fold_index, dataset in enumerate(fold_datasets):
            label = fold_index
            record = SimpleNamespace(
                label=np.asarray([label]),
                output=np.asarray([[0.8, 0.2] if label == 0 else [0.1, 0.9]]),
                evaluation_split="test",
            )
            run = SimpleNamespace(
                dataset=dataset,
                eval_record=record,
                evaluation_records={"test": record},
                is_finished=lambda: True,
                get_name=lambda: "Repeat-0",
            )
            plans.append(
                SimpleNamespace(
                    dataset=dataset,
                    training_round_id=round_id,
                    get_plans=lambda run=run: [run],
                    get_name=lambda: "Fold",
                )
            )
        return plans

    service, _visualization = _service(
        plans=[*make_round("training-round-1"), *make_round("training-round-2")]
    )

    _first_message, first_diagnostics = _expect_payload(
        service.handle_evaluate(EvaluateCommand()),
    )
    _second_message, second_diagnostics = _expect_payload(
        service.handle_evaluate(EvaluateCommand()),
    )

    assert second_diagnostics == first_diagnostics
    assert [
        choice["display_name"] for choice in first_diagnostics["cross_fold_choices"]
    ] == ["Fold Set 1", "Fold Set 2"]
    assert [
        tuple(member["plan_index"] for member in choice["identity"]["members"])
        for choice in first_diagnostics["cross_fold_choices"]
    ] == [(0, 1), (2, 3)]

    _message, visualization = _expect_payload(
        service.handle_visualize(VisualizeCommand(view="summary")),
    )
    assert [
        choice["display_name"]
        for choice in visualization["evaluation_cross_fold_choices"]
    ] == ["Fold Set 1", "Fold Set 2"]
    assert all(
        choice["saliency_available"] is False
        and "Compute Saliency" in choice["saliency_reason"]
        for choice in visualization["evaluation_cross_fold_choices"]
    )


def test_analysis_service_reports_validation_fallback_provenance() -> None:
    plan = _Plan(
        "Plan A",
        [
            _Run(finished=True, evaluation_split="validation"),
            _Run(finished=True, evaluation_split="test"),
        ],
    )
    service, _visualization = _service(plans=[plan])

    _message, diagnostics = _expect_payload(
        service.handle_evaluate(EvaluateCommand(target="latest")),
    )

    assert diagnostics["evaluation_splits"] == ["test", "validation"]
    assert diagnostics["plans"][0]["evaluation_splits"] == ["test", "validation"]


def test_analysis_service_reports_every_saved_split_per_run() -> None:
    run = _Run(finished=True)
    run.evaluation_records = {
        "training": _EvalRecord("training"),
        "validation": _EvalRecord("validation"),
        "test": run.eval_record,
    }
    service, _visualization = _service(plans=[_Plan("Plan A", [run])])

    _message, diagnostics = _expect_payload(service.handle_evaluate(EvaluateCommand()))

    assert diagnostics["plans"][0]["runs"][0]["evaluation_splits"] == [
        "test",
        "training",
        "validation",
    ]


def test_analysis_service_reports_no_results_without_facade() -> None:
    service, _visualization = _service()

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
        training_runtime=_BrokenTrainingRuntime([]),
    )

    with pytest.raises(RuntimeError, match="evaluation query failed"):
        service.handle_evaluate(EvaluateCommand(target="latest"))


def test_analysis_service_does_not_turn_visualization_failure_into_empty_success() -> (
    None
):
    visualization = _BrokenVisualizationController()
    service = AnalysisCommandService(
        training_runtime=_TrainingRuntime([]),
        visualization=visualization,
        get_state=_state,
    )

    with pytest.raises(RuntimeError, match="visualization query failed"):
        service.handle_visualize(VisualizeCommand(view="summary"))


def test_analysis_service_rejects_stale_model_summary_identity() -> None:
    service, _visualization = _service()
    stale_identity = EvaluationSummaryIdentity(
        plan=EvaluationPlanIdentity(plan_index=4),
    )

    with pytest.raises(PreconditionError, match="no longer available"):
        service.handle_evaluate(
            EvaluateCommand(summary_identity=stale_identity),
        )


def test_analysis_service_reports_training_active_without_facade() -> None:
    plan_a = _Plan("Plan A", [_Run(finished=True)])
    plan_b = _Plan("Plan B", [_Run(finished=True)])
    service, _visualization = _service(
        state=_state(is_training=True, finished_runs=2),
        plans=[plan_a, plan_b],
    )

    _message, diagnostics = _expect_payload(
        service.handle_evaluate(EvaluateCommand(target="latest")),
    )

    assert diagnostics["plan_count"] == 2
    assert diagnostics["finished_run_count"] == 2
    assert diagnostics["training_active"] is True
    assert [plan["name"] for plan in diagnostics["plans"]] == ["Plan A", "Plan B"]


def test_analysis_service_never_returns_ui_evaluation_objects() -> None:
    plan = _Plan("Plan A", [_Run(finished=True), _Run(finished=False)])
    service, _visualization = _service(plans=[plan])

    _message, diagnostics = _expect_payload(
        service.handle_evaluate(EvaluateCommand()),
    )

    assert "plan_objects" not in diagnostics
    assert "pooled_eval_results" not in diagnostics
    assert "model_summaries" not in diagnostics
    assert diagnostics["plans"][0]["identity"] == {"plan_index": 0}
    assert diagnostics["plans"][0]["runs"][0]["identity"] == {
        "plan_index": 0,
        "run_index": 0,
    }


def test_analysis_service_targets_requested_model_summary_only(monkeypatch) -> None:
    plan_a = _Plan("Plan A", [_Run(finished=True), _Run(finished=True)])
    plan_b = _Plan("Plan B", [_Run(finished=True)])
    runtime = _TrainingRuntime([plan_a, plan_b])
    service, _visualization = _service(training_runtime=runtime)
    identity = EvaluationSummaryIdentity(
        plan=EvaluationPlanIdentity(plan_index=1),
        run=EvaluationRunIdentity(
            plan=EvaluationPlanIdentity(plan_index=1),
            run_index=0,
        ),
    )
    summary_builder = MagicMock(
        return_value=EvaluationModelSummary(
            status="ready",
            text="Plan B summary run",
        )
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.analysis_service.build_evaluation_model_summary_result",
        summary_builder,
    )

    _message, diagnostics = _expect_payload(
        service.handle_evaluate(
            EvaluateCommand(summary_identity=identity),
        ),
    )

    assert diagnostics["model_summary"] == {
        "identity": {"plan_index": 1, "run_index": 0},
        "status": "ready",
        "text": "Plan B summary run",
    }
    summary_builder.assert_called_once_with(runtime, identity)


def test_analysis_service_catalog_is_summary_only() -> None:
    plan = _Plan("Plan A", [_Run(finished=True), _Run(finished=False)])
    service, _visualization = _service(plans=[plan])

    _message, diagnostics = _expect_payload(
        service.handle_evaluate(EvaluateCommand()),
    )

    assert "plan_objects" not in diagnostics
    assert "metrics" not in diagnostics["plans"][0]
    assert "pooled_eval_results" not in diagnostics
    assert "model_summaries" not in diagnostics


def test_analysis_service_visualize_and_saliency_handlers() -> None:
    state = _state(saliency_available=True, saliency_configured=True, finished_runs=1)
    service, visualization = _service(state=state)

    _visualize_message, visualize = _expect_payload(
        service.handle_visualize(VisualizeCommand(view="summary")),
    )
    _saliency_message, saliency = _expect_payload(
        service.handle_saliency(
            SaliencyCommand(method="SmoothGrad", params={"nt_samples": 2}),
        ),
    )
    assert visualize["payload_type"] == "visualization_summary"
    assert "saliency map" in visualize["available_views"]
    assert visualize["saliency_cross_fold_choices"] == []
    assert saliency["payload_type"] == "saliency_configuration"
    assert saliency["requested_method"] == "SmoothGrad"
    assert saliency["params"]["_methods"] == ["SmoothGrad"]
    assert saliency["params"]["SmoothGrad"]["nt_samples"] == 2
    assert visualization.params is not None


def test_explicit_saliency_accumulates_verified_complete_methods_before_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smoothgrad_params = {
        "nt_samples": 9,
        "nt_samples_batch_size": 3,
        "stdevs": 0.4,
    }
    first_run = _Run(finished=True)
    first_run.eval_record = SimpleNamespace(
        saliency_method_parameters={
            "Gradient": {},
            "SmoothGrad": smoothgrad_params,
            "SmoothGrad_Squared": {
                "nt_samples": 5,
                "nt_samples_batch_size": None,
                "stdevs": 1.0,
            },
        }
    )
    second_run = _Run(finished=True)
    second_run.eval_record = SimpleNamespace(
        saliency_method_parameters={"Gradient * Input": {}},
    )
    coverage = [
        SaliencyRunCoverageSnapshot(
            plan_index=0,
            run_index=0,
            methods=[
                SaliencyMethodCoverageSnapshot(
                    method="Gradient",
                    available=True,
                    complete=True,
                ),
                SaliencyMethodCoverageSnapshot(
                    method="SmoothGrad",
                    available=True,
                    complete=True,
                ),
                SaliencyMethodCoverageSnapshot(
                    method="SmoothGrad_Squared",
                    available=True,
                    complete=False,
                ),
            ],
        ),
        SaliencyRunCoverageSnapshot(
            plan_index=0,
            run_index=1,
            methods=[
                SaliencyMethodCoverageSnapshot(
                    method="Gradient * Input",
                    available=True,
                    complete=True,
                ),
            ],
        ),
    ]
    state = _state(
        has_trainer=True,
        finished_runs=2,
        saliency_available=True,
        saliency_configured=True,
        saliency_coverage=coverage,
    )
    visualization = _SchedulingVisualizationController()
    service = AnalysisCommandService(
        training_runtime=_TrainingRuntime([_Plan("Plan A", [first_run, second_run])]),
        visualization=visualization,
        get_state=lambda: state,
    )
    admitted_params: list[dict[str, Any]] = []

    def safe_preflight(_datasets, _option, _model, params, **_kwargs):
        admitted_params.append(params)
        return _saliency_preflight("safe")

    monkeypatch.setattr(
        "XBrainLab.backend.application.analysis_service."
        "check_saliency_resource_preflight",
        safe_preflight,
    )
    target = PostTrainingSaliencyTarget(
        run=TrainingRunIdentity(trainer_id="trainer-a", run_id=1),
        finished_runs_before=0,
        finished_runs_after=2,
        append=False,
        explicit=True,
    )

    with post_training_saliency_target(target):
        _message, diagnostics = _expect_payload(
            service.handle_saliency(
                SaliencyCommand(
                    method="VarGrad",
                    params={
                        "nt_samples": 7,
                        "nt_samples_batch_size": 2,
                        "stdevs": 0.25,
                    },
                )
            )
        )

    expected_methods = [
        "Gradient",
        "Gradient * Input",
        "SmoothGrad",
        "VarGrad",
    ]
    assert admitted_params[0]["_methods"] == expected_methods
    assert admitted_params[0]["SmoothGrad"] == smoothgrad_params
    assert admitted_params[0]["VarGrad"] == {
        "nt_samples": 7,
        "nt_samples_batch_size": 2,
        "stdevs": 0.25,
    }
    assert "_profile" not in admitted_params[0]
    assert diagnostics["params"] == admitted_params[0]
    assert diagnostics["post_training_saliency_schedule"]["status"]["methods"] == (
        expected_methods
    )
    assert visualization.params == admitted_params[0]


def test_explicit_saliency_rejects_conflicting_retained_artifact_params_before_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs = [_Run(finished=True), _Run(finished=True)]
    for run, nt_samples in zip(runs, (3, 9), strict=True):
        run.eval_record = SimpleNamespace(
            saliency_method_parameters={
                "SmoothGrad": {
                    "nt_samples": nt_samples,
                    "nt_samples_batch_size": None,
                    "stdevs": 0.5,
                }
            }
        )
    coverage = [
        SaliencyRunCoverageSnapshot(
            plan_index=0,
            run_index=run_index,
            methods=[
                SaliencyMethodCoverageSnapshot(
                    method="SmoothGrad",
                    available=True,
                    complete=True,
                )
            ],
        )
        for run_index in range(2)
    ]
    state = _state(
        has_trainer=True,
        finished_runs=2,
        saliency_available=True,
        saliency_coverage=coverage,
    )
    visualization = _EvaluatorSentinelController()
    service = AnalysisCommandService(
        training_runtime=_TrainingRuntime([_Plan("Plan A", runs)]),
        visualization=visualization,
        get_state=lambda: state,
    )
    preflight = MagicMock(side_effect=AssertionError("preflight must not run"))
    monkeypatch.setattr(
        "XBrainLab.backend.application.analysis_service."
        "check_saliency_resource_preflight",
        preflight,
    )
    target = PostTrainingSaliencyTarget(
        run=TrainingRunIdentity(trainer_id="trainer-a", run_id=1),
        finished_runs_before=0,
        finished_runs_after=2,
        append=False,
        explicit=True,
    )

    with (
        post_training_saliency_target(target),
        pytest.raises(PreconditionError, match="conflict for SmoothGrad") as raised,
    ):
        service.handle_saliency(SaliencyCommand(method="VarGrad"))

    assert raised.value.diagnostics["state_preserved"] is True
    assert visualization.params is None
    preflight.assert_not_called()


def test_explicit_saliency_rejects_missing_retained_artifact_params_before_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _Run(finished=True)
    run.eval_record = SimpleNamespace(saliency_method_parameters={})
    state = _state(
        has_trainer=True,
        finished_runs=1,
        saliency_available=True,
        saliency_coverage=[
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                methods=[
                    SaliencyMethodCoverageSnapshot(
                        method="VarGrad",
                        available=True,
                        complete=True,
                    )
                ],
            )
        ],
    )
    visualization = _EvaluatorSentinelController()
    service = AnalysisCommandService(
        training_runtime=_TrainingRuntime([_Plan("Plan A", [run])]),
        visualization=visualization,
        get_state=lambda: state,
    )
    preflight = MagicMock(side_effect=AssertionError("preflight must not run"))
    monkeypatch.setattr(
        "XBrainLab.backend.application.analysis_service."
        "check_saliency_resource_preflight",
        preflight,
    )
    target = PostTrainingSaliencyTarget(
        run=TrainingRunIdentity(trainer_id="trainer-a", run_id=1),
        finished_runs_before=0,
        finished_runs_after=1,
        append=False,
        explicit=True,
    )

    with (
        post_training_saliency_target(target),
        pytest.raises(PreconditionError, match="unavailable for VarGrad") as raised,
    ):
        service.handle_saliency(SaliencyCommand(method="Gradient"))

    assert raised.value.diagnostics["state_preserved"] is True
    assert visualization.params is None
    preflight.assert_not_called()


def test_explicit_saliency_incoming_params_resolve_prior_artifact_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs = [_Run(finished=True), _Run(finished=True)]
    for run, nt_samples in zip(runs, (3, 9), strict=True):
        run.eval_record = SimpleNamespace(
            saliency_method_parameters={
                "SmoothGrad": {
                    "nt_samples": nt_samples,
                    "nt_samples_batch_size": None,
                    "stdevs": 0.5,
                }
            }
        )
    coverage = [
        SaliencyRunCoverageSnapshot(
            plan_index=0,
            run_index=run_index,
            methods=[
                SaliencyMethodCoverageSnapshot(
                    method="SmoothGrad",
                    available=True,
                    complete=True,
                )
            ],
        )
        for run_index in range(2)
    ]
    state = _state(
        has_trainer=True,
        finished_runs=2,
        saliency_available=True,
        saliency_coverage=coverage,
    )
    visualization = _SchedulingVisualizationController()
    service = AnalysisCommandService(
        training_runtime=_TrainingRuntime([_Plan("Plan A", runs)]),
        visualization=visualization,
        get_state=lambda: state,
    )
    admitted_params: list[dict[str, Any]] = []

    def safe_preflight(_datasets, _option, _model, params, **_kwargs):
        admitted_params.append(params)
        return _saliency_preflight("safe")

    monkeypatch.setattr(
        "XBrainLab.backend.application.analysis_service."
        "check_saliency_resource_preflight",
        safe_preflight,
    )
    target = PostTrainingSaliencyTarget(
        run=TrainingRunIdentity(trainer_id="trainer-a", run_id=1),
        finished_runs_before=0,
        finished_runs_after=2,
        append=False,
        explicit=True,
    )

    with post_training_saliency_target(target):
        service.handle_saliency(
            SaliencyCommand(
                method="SmoothGrad",
                params={
                    "nt_samples": 7,
                    "nt_samples_batch_size": 2,
                    "stdevs": 0.25,
                },
            )
        )

    assert admitted_params[0]["_methods"] == ["SmoothGrad"]
    assert admitted_params[0]["SmoothGrad"] == {
        "nt_samples": 7,
        "nt_samples_batch_size": 2,
        "stdevs": 0.25,
    }


def test_saliency_receipt_cannot_authorize_a_changed_completed_method_union(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _Run(finished=True)
    run.eval_record = SimpleNamespace(saliency_method_parameters={"Gradient": {}})
    states = [
        _state(has_trainer=True, finished_runs=1),
        _state(
            has_trainer=True,
            finished_runs=1,
            saliency_available=True,
            saliency_coverage=[
                SaliencyRunCoverageSnapshot(
                    plan_index=0,
                    run_index=0,
                    methods=[
                        SaliencyMethodCoverageSnapshot(
                            method="Gradient",
                            available=True,
                            complete=True,
                        )
                    ],
                )
            ],
        ),
    ]
    state_index = [0]
    service = AnalysisCommandService(
        training_runtime=_TrainingRuntime([_Plan("Plan A", [run])]),
        visualization=_EvaluatorSentinelController(),
        get_state=lambda: states[state_index[0]],
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.analysis_service."
        "check_saliency_resource_preflight",
        lambda *_args, **_kwargs: _saliency_preflight("warning"),
    )
    target = PostTrainingSaliencyTarget(
        run=TrainingRunIdentity(trainer_id="trainer-a", run_id=1),
        finished_runs_before=0,
        finished_runs_after=1,
        append=False,
        explicit=True,
    )

    with (
        post_training_saliency_target(target),
        pytest.raises(ResourceConfirmationRequiredError) as first_error,
    ):
        service.handle_saliency(SaliencyCommand(method="VarGrad"))
    first = _resource_challenge(first_error.value)
    state_index[0] = 1

    with (
        post_training_saliency_target(target),
        pytest.raises(ResourceConfirmationRequiredError) as changed_error,
    ):
        service.handle_saliency(
            SaliencyCommand(
                method="VarGrad",
                resource_preflight_confirmed=True,
                resource_preflight_token=first.challenge_id,
            )
        )

    changed = _resource_challenge(changed_error.value)
    assert changed.challenge_id != first.challenge_id
    assert changed.configuration_fingerprint != first.configuration_fingerprint


def test_automatic_saliency_baseline_does_not_accumulate_prior_advanced_methods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _Run(finished=True)
    run.eval_record = SimpleNamespace(saliency_method_parameters={})
    state = _state(
        has_trainer=True,
        finished_runs=1,
        saliency_available=True,
        saliency_coverage=[
            SaliencyRunCoverageSnapshot(
                plan_index=0,
                run_index=0,
                methods=[
                    SaliencyMethodCoverageSnapshot(
                        method="SmoothGrad",
                        available=True,
                        complete=True,
                    )
                ],
            )
        ],
    )
    visualization = _SchedulingVisualizationController()
    service = AnalysisCommandService(
        training_runtime=_TrainingRuntime([_Plan("Plan A", [run])]),
        visualization=visualization,
        get_state=lambda: state,
    )
    admitted_params: list[dict[str, Any]] = []

    def safe_preflight(_datasets, _option, _model, params, **_kwargs):
        admitted_params.append(params)
        return _saliency_preflight("safe")

    monkeypatch.setattr(
        "XBrainLab.backend.application.analysis_service."
        "check_saliency_resource_preflight",
        safe_preflight,
    )
    target = PostTrainingSaliencyTarget(
        run=TrainingRunIdentity(trainer_id="trainer-a", run_id=1),
        finished_runs_before=0,
        finished_runs_after=1,
        append=True,
        explicit=False,
    )

    with post_training_saliency_target(target):
        service.handle_saliency(
            SaliencyCommand(
                method="Gradient",
                params={
                    "profile": "recommended",
                    "methods": ["Gradient", "Gradient * Input"],
                },
            )
        )

    assert admitted_params[0]["_methods"] == ["Gradient", "Gradient * Input"]
    assert admitted_params[0]["_profile"] == "recommended"


def test_analysis_service_rejects_oversized_saliency_before_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _TrainingRuntime(
        [],
        datasets=(_Dataset((64, 128, 4096)),),
        training_option=_TrainingOption(
            batch_size=32,
            use_cpu=False,
            gpu_idx=0,
        ),
    )
    visualization = _EvaluatorSentinelController()
    service = AnalysisCommandService(
        training_runtime=runtime,
        visualization=visualization,
        get_state=lambda: _state(has_trainer=True, finished_runs=1),
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.resource_guard.ResourceChecker.get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 2 * 1024**3,
                "total_bytes": 4 * 1024**3,
                "used_bytes": 2 * 1024**3,
            }
        ),
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.resource_guard.ResourceChecker.get_gpu_vram_status",
        staticmethod(
            lambda _gpu_idx=None: {
                "available_bytes": 1024**3,
                "total_bytes": 2 * 1024**3,
                "used_bytes": 1024**3,
                "gpu_index": 0,
                "reason": None,
            }
        ),
    )

    with pytest.raises(
        PreconditionError,
        match=r"(?i)(?:saliency.*memory|memory.*saliency)",
    ):
        service.handle_saliency(
            SaliencyCommand(
                method="SmoothGrad",
                params={"nt_samples": 512},
            ),
        )


@pytest.mark.parametrize("risk_level", ["warning", "unknown"])
def test_analysis_service_requires_matching_receipt_for_risky_saliency(
    monkeypatch: pytest.MonkeyPatch,
    risk_level: str,
) -> None:
    service, visualization = _service(
        state=_state(has_trainer=True, finished_runs=1),
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.analysis_service."
        "check_saliency_resource_preflight",
        lambda *_args, **_kwargs: _saliency_preflight(risk_level),
    )

    with pytest.raises(ResourceConfirmationRequiredError) as raised:
        service.handle_saliency(SaliencyCommand(method="Gradient"))

    challenge = _resource_challenge(raised.value)
    assert challenge.command_name == "saliency"
    assert visualization.params is None

    _message, diagnostics = _expect_payload(
        service.handle_saliency(
            SaliencyCommand(
                method="Gradient",
                resource_preflight_confirmed=True,
                resource_preflight_token=challenge.challenge_id,
            )
        )
    )

    assert visualization.params is not None
    assert diagnostics["resource_preflight"]["risk_level"] == risk_level
    assert diagnostics["resource_preflight"]["confirmation_receipt_reused"] is True

    with pytest.raises(ResourceConfirmationRequiredError) as replayed:
        service.handle_saliency(
            SaliencyCommand(
                method="Gradient",
                resource_preflight_confirmed=True,
                resource_preflight_token=challenge.challenge_id,
            )
        )

    assert _resource_challenge(replayed.value).challenge_id != challenge.challenge_id
    assert visualization.saliency_set_calls == 1


def test_analysis_service_rejects_tokenless_saliency_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, visualization = _service(
        state=_state(has_trainer=True, finished_runs=1),
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.analysis_service."
        "check_saliency_resource_preflight",
        lambda *_args, **_kwargs: _saliency_preflight("warning"),
    )

    with pytest.raises(ResourceConfirmationRequiredError) as raised:
        service.handle_saliency(
            SaliencyCommand(
                method="Gradient",
                resource_preflight_confirmed=True,
            )
        )

    challenge = _resource_challenge(raised.value)
    assert challenge.command_name == "saliency"
    assert visualization.params is None
    assert visualization.saliency_set_calls == 0


def test_analysis_service_rejects_mismatched_saliency_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, visualization = _service(
        state=_state(has_trainer=True, finished_runs=1),
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.analysis_service."
        "check_saliency_resource_preflight",
        lambda *_args, **_kwargs: _saliency_preflight("warning"),
    )

    with pytest.raises(ResourceConfirmationRequiredError) as raised:
        service.handle_saliency(SaliencyCommand(method="Gradient"))
    first = _resource_challenge(raised.value)

    with pytest.raises(ResourceConfirmationRequiredError) as mismatched:
        service.handle_saliency(
            SaliencyCommand(
                method="SmoothGrad",
                params={"nt_samples": 2},
                resource_preflight_confirmed=True,
                resource_preflight_token=first.challenge_id,
            )
        )

    replacement = _resource_challenge(mismatched.value)
    assert replacement.challenge_id != first.challenge_id
    assert replacement.scope_fingerprint != first.scope_fingerprint
    assert visualization.params is None


def test_analysis_service_rejects_expired_saliency_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [100.0]
    monkeypatch.setattr(saliency_resource.time, "monotonic", lambda: now[0])
    service, visualization = _service(
        state=_state(has_trainer=True, finished_runs=1),
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.analysis_service."
        "check_saliency_resource_preflight",
        lambda *_args, **_kwargs: _saliency_preflight("warning"),
    )

    with pytest.raises(ResourceConfirmationRequiredError) as raised:
        service.handle_saliency(SaliencyCommand(method="Gradient"))
    first = _resource_challenge(raised.value)
    now[0] += 121.0

    with pytest.raises(ResourceConfirmationRequiredError) as expired:
        service.handle_saliency(
            SaliencyCommand(
                method="Gradient",
                resource_preflight_confirmed=True,
                resource_preflight_token=first.challenge_id,
            )
        )

    replacement = _resource_challenge(expired.value)
    assert replacement.challenge_id != first.challenge_id
    assert replacement.scope_fingerprint == first.scope_fingerprint
    assert visualization.params is None


def test_analysis_service_allows_safe_saliency_without_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, visualization = _service(
        state=_state(has_trainer=True, finished_runs=1),
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.analysis_service."
        "check_saliency_resource_preflight",
        lambda *_args, **_kwargs: _saliency_preflight("safe"),
    )

    _message, diagnostics = _expect_payload(
        service.handle_saliency(SaliencyCommand(method="Gradient"))
    )

    assert visualization.params is not None
    assert diagnostics["resource_preflight"]["risk_level"] == "safe"
    assert diagnostics["resource_preflight"]["confirmation_receipt_reused"] is False
    assert "confirmation_challenge" not in diagnostics["resource_preflight"]


def test_analysis_service_blocks_saliency_without_confirmation_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AnalysisCommandService(
        training_runtime=_TrainingRuntime([]),
        visualization=_EvaluatorSentinelController(),
        get_state=lambda: _state(has_trainer=True, finished_runs=1),
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.analysis_service."
        "check_saliency_resource_preflight",
        lambda *_args, **_kwargs: _saliency_preflight("blocking"),
    )

    with pytest.raises(PreconditionError) as raised:
        service.handle_saliency(SaliencyCommand(method="Gradient"))

    preflight = ResourcePreflightView.from_diagnostics(raised.value.diagnostics)
    assert preflight is not None
    assert preflight.risk_level == "blocking"
    assert preflight.challenge is None


def test_analysis_service_blocks_when_saliency_resource_context_is_unavailable() -> (
    None
):
    service = AnalysisCommandService(
        training_runtime=_BrokenSaliencyResourceRuntime([]),
        visualization=_EvaluatorSentinelController(),
        get_state=lambda: _state(has_trainer=True, finished_runs=1),
    )

    with pytest.raises(PreconditionError) as raised:
        service.handle_saliency(SaliencyCommand(method="Gradient"))

    assert "current dataset, model, and training settings" in str(raised.value)
    assert raised.value.diagnostics["resource_preflight"] == {
        "operation": "saliency_recomputation",
        "risk_level": "blocking",
        "reason": "resource_context_read_failed",
        "error_type": "RuntimeError",
    }


def test_analysis_service_rejects_unverified_saliency_readback() -> None:
    visualization = _LossySaliencyController()
    service = AnalysisCommandService(
        training_runtime=_TrainingRuntime([]),
        visualization=visualization,
        get_state=lambda: _state(has_trainer=True, finished_runs=1),
    )

    with pytest.raises(ValueError, match="could not be verified"):
        service.handle_saliency(
            SaliencyCommand(
                method="SmoothGrad",
                params={
                    "nt_samples": 2,
                    "nt_samples_batch_size": 1,
                    "stdevs": 1.0,
                },
            ),
        )


def test_analysis_service_rejects_type_coerced_saliency_readback() -> None:
    visualization = _TypeCoercingSaliencyController()
    service = AnalysisCommandService(
        training_runtime=_TrainingRuntime([]),
        visualization=visualization,
        get_state=lambda: _state(has_trainer=True, finished_runs=1),
    )

    with pytest.raises(ValueError, match="could not be verified"):
        service.handle_saliency(
            SaliencyCommand(
                method="SmoothGrad",
                params={
                    "nt_samples": 2,
                    "nt_samples_batch_size": 1,
                    "stdevs": 1.0,
                },
            ),
        )


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
        training_runtime=_TrainingRuntime([]),
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
        "Set a 3D montage before opening the 3D plot."
    ]
    assert "topographic map" not in visualize["available_views"]
    assert visualize["blocked_views"]["topographic map"] == [
        "Set Montage before opening the topographic map."
    ]


def test_analysis_service_returns_only_detached_visualization_summary() -> None:
    state = _state(saliency_available=True, saliency_configured=True, finished_runs=1)
    service, visualization = _service(state=state)

    _message, diagnostics = _expect_payload(
        service.handle_visualize(VisualizeCommand(view="summary")),
    )

    assert diagnostics["trainer_count"] == 1
    assert "trainer_objects" not in diagnostics
    assert "averaged_records" not in diagnostics
    assert visualization.averaged_record_calls == 0


def test_analysis_service_does_not_define_live_object_projection_helpers() -> None:
    assert not hasattr(AnalysisCommandService, "_averaged_record")
