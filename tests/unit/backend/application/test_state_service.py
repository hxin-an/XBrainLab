"""Focused tests for application state snapshot and query services."""

from __future__ import annotations

import threading
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, ClassVar, cast
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.commands import (
    CommandName,
    ConfigureTrainingCommand,
    QueryStateCommand,
)
from XBrainLab.backend.application.dataset_generation_service import (
    DatasetGenerationCommandService,
)
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.query_state_service import (
    HandlerResult,
    QueryStateCommandService,
)
from XBrainLab.backend.application.saliency_coverage import (
    SaliencyCoverageProjector,
)
from XBrainLab.backend.application.service import ApplicationService
from XBrainLab.backend.application.state import (
    ApplicationStateSnapshot,
    DatasetSplitLifecycle,
    DatasetStateSnapshot,
    EpochStateSnapshot,
    InterpretationStateSnapshot,
    SaliencyMethodCoverageSnapshot,
    SaliencyRunCoverageSnapshot,
)
from XBrainLab.backend.application.state_service import StateSnapshotService
from XBrainLab.backend.application.training_recommendation import (
    TrainingRecommendationField,
    TrainingRecommendationService,
    TrainingSettingProvenance,
)
from XBrainLab.backend.application.training_runtime import (
    TrainingConfigurationSnapshot,
    TrainingRuntimeContext,
)
from XBrainLab.backend.application.training_service import TrainingCommandService
from XBrainLab.backend.application.training_submission import (
    attach_training_submission_provenance,
)
from XBrainLab.backend.application.view_publication import (
    ApplicationViewCoordinator,
    ApplicationViewStore,
)
from XBrainLab.backend.training import Trainer, TrainingPlanHolder
from XBrainLab.backend.training.record import TrainRecord
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyStatus,
    TrainingOutcomeState,
    TrainingReadBoundary,
    TrainingRunIdentity,
    TrainingStateToken,
    TrainingTerminalOutcome,
)


class _Raw:
    def __init__(self, filename: str = "subject01.fif") -> None:
        self.filename = filename

    def get_filename(self) -> str:
        return self.filename

    def get_subject_name(self) -> str:
        return "S01"

    def get_session_name(self) -> str:
        return "session-01"

    def get_mne(self) -> Any:
        return type("MNE", (), {"ch_names": ["C3", "C4"]})()

    def get_preprocess_history(self) -> list[str]:
        return ["filter", "normalize"]


class _BrokenPreprocessHistoryRaw(_Raw):
    def get_preprocess_history(self) -> list[str]:
        raise RuntimeError("preprocess history unavailable")


class _Epoch:
    event_id: ClassVar[dict[str, int]] = {"left": 1}
    data: ClassVar[list[list[list[float]]]] = [[[0.0, 0.1], [0.2, 0.3]]]
    channel_position: ClassVar[dict[str, tuple[float, float, float]]] = {
        "C3": (0.0, 0.0, 0.0),
    }

    def __len__(self) -> int:
        return 1

    def get_channel_names(self) -> list[str]:
        return ["C3", "C4"]


class _MalformedCapabilityEpoch:
    event_id: ClassVar[dict[str, int]] = {"left": 1}
    data: ClassVar[Any] = type(
        "MalformedShape",
        (),
        {"shape": ("invalid", 2, 3)},
    )()
    sfreq: ClassVar[Any] = "not-a-frequency"
    channel_position: ClassVar[dict[str, tuple[float, float, float]]] = {
        "C3": (0.0, 0.0, 0.0),
    }

    def __len__(self) -> int:
        return 1

    def get_channel_names(self) -> list[str]:
        return ["C3", "C4"]


class _EpochWithManualGeometry(_Epoch):
    data: ClassVar[np.ndarray] = np.zeros((1, 4, 2), dtype=np.float32)

    def __init__(
        self,
        positions: tuple[tuple[float, float, float], ...],
    ) -> None:
        self.channel_position = dict(
            zip(self.get_channel_names(), positions, strict=True)
        )

    def get_channel_names(self) -> list[str]:
        return ["C3", "C4", "Cz", "Pz"]


class _Study:
    def __init__(self) -> None:
        raw = _Raw()
        self.loaded_data_list = [raw]
        self.preprocessed_data_list = [raw]
        self.epoch_data = _Epoch()
        self.datasets: list[Any] = [type("Dataset", (), {"name": "D1"})()]
        self.trainer = None
        self.model_holder = None
        self.training_option = None
        self.dataset_generator = object()
        self.saliency_params = object()
        self.pipeline_stage = "loaded"

    def is_locked(self) -> bool:
        return True


class _DatasetController:
    def __init__(self, study: _Study) -> None:
        self.study = study

    def get_runtime_diagnostics(self) -> dict[str, Any]:
        return {
            "source": "runtime",
            "runtime_signals": ["signal one"],
            "gdf_duplicate_channel_files": ["sub01.gdf"],
            "gdf_duplicate_channel_details": [
                {
                    "file": "sub01.gdf",
                    "generated_bases": ["EEG"],
                    "generated_channels": ["EEG-0", "EEG-1"],
                    "message": "detail message",
                },
            ],
        }

    def get_event_info(self) -> dict[str, Any]:
        return {"total": 2, "unique_labels": ["left"]}

    def is_locked(self) -> bool:
        return True

    def get_loaded_data_list(self) -> list[Any]:
        return self.study.loaded_data_list

    def get_loaded_data_rows(self) -> list[dict[str, object]]:
        return [
            {"filepath": item.get_filename()} for item in self.study.loaded_data_list
        ]

    def get_preprocessed_data_rows(self) -> list[dict[str, object]]:
        return [
            {"filepath": item.get_filename()}
            for item in self.study.preprocessed_data_list
        ]

    def get_smart_filter_suggestions(
        self, _target: Any, target_count: int
    ) -> list[int]:
        return list(range(target_count))


class _BrokenLoadedDataController(_DatasetController):
    def get_loaded_data_list(self) -> list[Any]:
        raise RuntimeError("loaded data list unavailable")


class _BrokenOptionalDatasetDiagnosticsController(_DatasetController):
    def get_runtime_diagnostics(self) -> dict[str, Any]:
        raise RuntimeError("dataset diagnostics unavailable")

    def get_event_info(self) -> dict[str, Any]:
        raise RuntimeError("event summary unavailable")


class _PreprocessController:
    def get_runtime_diagnostics(self) -> dict[str, Any]:
        return {
            "preprocess": "ok",
            "runtime_signals": ["preprocess signal"],
            "gdf_duplicate_channel_files": ["preprocessed-sub01.gdf"],
        }

    def is_epoched(self) -> bool:
        return True

    def get_channel_names(self) -> list[str]:
        return ["C3", "C4"]


class _BrokenPreprocessEpochedController(_PreprocessController):
    def is_epoched(self) -> bool:
        raise RuntimeError("epoch state unavailable")


class _BrokenPreprocessChannelController(_PreprocessController):
    def get_channel_names(self) -> list[str]:
        raise RuntimeError("preprocess channels unavailable")


class _BrokenOptionalPreprocessDiagnosticsController(_PreprocessController):
    def get_runtime_diagnostics(self) -> dict[str, Any]:
        raise RuntimeError("preprocess diagnostics unavailable")


class _UnexpectedPreprocessReadController(_PreprocessController):
    def is_epoched(self) -> bool:
        raise AssertionError("is_epoched must not be read without preprocess context")

    def get_channel_names(self) -> list[str]:
        raise AssertionError("channels must not be read without preprocess context")


class _TrainingController:
    def is_training(self) -> bool:
        return False

    def get_progress_text(self) -> str:
        return "Epoch 2/10"

    def get_terminal_outcome(self) -> TrainingTerminalOutcome:
        return TrainingTerminalOutcome(
            state=TrainingOutcomeState.COMPLETED,
            run=TrainingRunIdentity(trainer_id="trainer-state-test", run_id=4),
        )

    def get_missing_requirements(self) -> list[str]:
        return ["model"]

    def get_formatted_history(self) -> list[dict[str, Any]]:
        plan = object()
        record = type("Record", (), {"epoch": 2})()
        return [
            {
                "plan": plan,
                "record": record,
                "group_name": "Group 1",
                "run_name": "1",
                "model_name": "EEGNet",
                "is_active": True,
                "is_current_run": True,
            }
        ]


class _TrainingRuntime:
    def __init__(
        self,
        study: _Study,
        training: _TrainingController,
        *,
        saliency_status: PostTrainingSaliencyStatus | None = None,
    ) -> None:
        self.study = study
        self.training = training
        self._saliency_status = saliency_status or PostTrainingSaliencyStatus.idle()
        self._configuration = TrainingConfigurationSnapshot(
            model_holder=study.model_holder,
            training_option=study.training_option,
            saliency_params={"Gradient": {}},
        )

    def configuration_snapshot(self) -> TrainingConfigurationSnapshot:
        return self._configuration

    def set_saliency_params(self, params: dict[str, Any] | None) -> None:
        self._configuration = replace(
            self._configuration,
            saliency_params=params,
        )

    def resource_context(self) -> TrainingRuntimeContext:
        return TrainingRuntimeContext((), None, None)

    def terminal_outcome(self) -> TrainingTerminalOutcome:
        trainer = self.study.trainer
        if trainer is None:
            return TrainingTerminalOutcome(
                state=TrainingOutcomeState.UNKNOWN,
                detail="No trainer is available.",
            )
        getter = getattr(trainer, "get_terminal_outcome", None)
        if callable(getter):
            return getter()
        return self.training.get_terminal_outcome()

    def has_trainer(self) -> bool:
        return self.study.trainer is not None

    def capture_read_boundary(self) -> TrainingReadBoundary:
        trainer = self.study.trainer
        if trainer is None:
            return TrainingReadBoundary.no_trainer()
        identity_getter = getattr(trainer, "get_state_snapshot_identity", None)
        token_getter = getattr(trainer, "get_state_snapshot_token", None)
        if not callable(identity_getter) or not callable(token_getter):
            return TrainingReadBoundary(
                trainer_identity=(
                    f"untracked:{type(trainer).__module__}.{type(trainer).__qualname__}"
                ),
                token=TrainingStateToken(0, False),
            )
        try:
            identity = identity_getter()
            token = token_getter()
        except Exception:
            identity = None
            token = None
        if (
            not isinstance(identity, str)
            or not identity.strip()
            or not isinstance(token, TrainingStateToken)
        ):
            return TrainingReadBoundary(
                trainer_identity=(
                    f"untracked:{type(trainer).__module__}.{type(trainer).__qualname__}"
                ),
                token=TrainingStateToken(0, False),
            )
        return TrainingReadBoundary(
            trainer_identity=identity,
            token=token,
        )

    def saliency_status(self) -> PostTrainingSaliencyStatus:
        return self._saliency_status

    def set_saliency_status(self, status: PostTrainingSaliencyStatus) -> None:
        self._saliency_status = status


class _BrokenTrainingRequirementsController(_TrainingController):
    def get_missing_requirements(self) -> list[str]:
        raise RuntimeError("training requirements unavailable")


class _BrokenTrainingProgressController(_TrainingController):
    def get_progress_text(self) -> str:
        raise RuntimeError("training progress unavailable")


class _RunningTrainingController(_TrainingController):
    def is_training(self) -> bool:
        return True

    def get_terminal_outcome(self) -> TrainingTerminalOutcome:
        return TrainingTerminalOutcome(
            state=TrainingOutcomeState.RUNNING,
            run=TrainingRunIdentity(trainer_id="trainer-state-test", run_id=5),
        )


class _TerminalTrainingController(_TrainingController):
    def __init__(self, outcome: TrainingOutcomeState) -> None:
        self._outcome = outcome

    def get_terminal_outcome(self) -> TrainingTerminalOutcome:
        return TrainingTerminalOutcome(
            state=self._outcome,
            run=TrainingRunIdentity(trainer_id="trainer-state-test", run_id=6),
        )


class _StableTrainer:
    def get_state_snapshot_identity(self) -> str:
        return "trainer-state-test"

    def get_state_snapshot_token(self) -> TrainingStateToken:
        return TrainingStateToken(generation=1, stable=True)


class _EvaluationController:
    def get_plans(self) -> list[Any]:
        return []


class _BrokenEvaluationController:
    def get_plans(self) -> list[Any]:
        raise RuntimeError("evaluation state unavailable")


class _BrokenTrainingController(_TrainingController):
    def is_training(self) -> bool:
        raise RuntimeError("training state unavailable")


class _FinishedRun:
    def __init__(self, eval_record: Any) -> None:
        self.eval_record = eval_record

    def is_finished(self) -> bool:
        return True


class _Plan:
    def __init__(self, runs: list[Any]) -> None:
        self._runs = runs

    def get_plans(self) -> list[Any]:
        return self._runs


class _BrokenPlan:
    def get_plans(self) -> list[Any]:
        raise RuntimeError("plan run list unavailable")


class _BrokenRun:
    eval_record = None

    def is_finished(self) -> bool:
        raise RuntimeError("run completion unavailable")


class _BrokenEvalRecordRun:
    def is_finished(self) -> bool:
        return True

    @property
    def eval_record(self) -> Any:
        raise RuntimeError("evaluation record unavailable")


class _EvaluationControllerWithPlans:
    def __init__(self, plans: list[Any]) -> None:
        self._plans = plans

    def get_plans(self) -> list[Any]:
        return self._plans


def _snapshot_service(
    *,
    saliency_coverage_projector: SaliencyCoverageProjector | None = None,
    montage_snapshot_provider: Any | None = None,
    effective_montage_provider: Any | None = None,
) -> StateSnapshotService:
    study = _Study()
    study.trainer = _StableTrainer()
    dataset = _DatasetController(study)
    training = _TrainingController()
    training_runtime = _TrainingRuntime(study, training)
    return StateSnapshotService(
        study=study,
        dataset=dataset,
        preprocess=_PreprocessController(),
        training=training,
        training_runtime=cast(Any, training_runtime),
        evaluation=_EvaluationController(),
        visualization=object(),
        dataset_generation=DatasetGenerationCommandService(
            study=study,
            training=object(),
            has_trainer=training_runtime.has_trainer,
        ),
        training_commands=TrainingCommandService(
            training=object(),
            training_runtime=cast(Any, training_runtime),
            get_state=lambda: cast(ApplicationStateSnapshot, None),
        ),
        saliency_coverage_projector=(
            saliency_coverage_projector or SaliencyCoverageProjector()
        ),
        interpretation=type(
            "Interpretation",
            (),
            {
                "snapshot": lambda self: InterpretationStateSnapshot(
                    has_scan_result=True
                )
            },
        )(),
        montage_snapshot_provider=montage_snapshot_provider,
        effective_montage_provider=effective_montage_provider,
    )


def _expect_payload(result: HandlerResult) -> tuple[str, dict[str, Any]]:
    assert isinstance(result, tuple)
    return cast(tuple[str, dict[str, Any]], result)


def test_state_snapshot_service_builds_workflow_snapshot() -> None:
    state = _snapshot_service().build()

    assert state.pipeline_stage == "epoch_ready"
    assert state.raw.loaded is True
    assert state.raw.files == ["subject01.fif"]
    assert state.raw.metadata[0]["subject"] == "S01"
    assert state.preprocessed.operations == ["filter", "normalize"]
    assert state.raw.diagnostics["runtime_signals"] == ["signal one"]
    assert state.preprocessed.diagnostics["runtime_signals"] == ["preprocess signal"]
    assert state.epoch.available is True
    assert state.epoch.event_ids == {"left": 1}
    assert state.dataset.count == 1
    assert state.training.progress_message == "Epoch 2/10"
    assert state.training.terminal_outcome.state is TrainingOutcomeState.COMPLETED
    assert state.training.terminal_outcome.run == TrainingRunIdentity(
        trainer_id="trainer-state-test",
        run_id=4,
    )
    assert state.training.terminal_outcome.detail is None
    terminal_outcome = state.to_dict()["training"]["terminal_outcome"]
    assert terminal_outcome == {
        "state": "completed",
        "run": {"trainer_id": "trainer-state-test", "run_id": 4},
        "detail": None,
    }
    assert type(terminal_outcome["state"]) is str
    assert state.training_liveness_reliable is True
    assert state.visualization.saliency_configured is True
    assert state.interpretation.has_scan_result is True
    assert state.active_dataset.has_epoch_data is True


def test_state_snapshot_projects_partial_bids_geometry_without_hiding_channels() -> (
    None
):
    service = _snapshot_service(
        montage_snapshot_provider=lambda: SimpleNamespace(
            state="ready",
            reason=None,
        ),
        effective_montage_provider=lambda: SimpleNamespace(
            source="bids",
            channel_names=("C3",),
            positions_m=((0.0, 0.0, 0.08),),
        ),
    )

    state = service.build()

    assert state.epoch.channel_names == ["C3", "C4"]
    assert state.visualization.channel_count == 2
    assert state.visualization.channel_positions_available is False
    assert state.visualization.three_dimensional_positions_available is False
    assert state.visualization.montage_source == "bids"
    assert state.visualization.montage_channels == ["C3"]
    assert state.visualization.montage_positions == [[0.0, 0.0, 0.08]]


@pytest.mark.parametrize(
    ("positions", "supports_topographic", "supports_three_dimensional"),
    [
        (
            (
                (-0.04, -0.04, 0.0),
                (0.04, -0.04, 0.0),
                (-0.04, 0.04, 0.0),
                (0.04, 0.04, 0.0),
            ),
            True,
            False,
        ),
        (
            (
                (-0.04, 0.0, 0.0),
                (-0.01, 0.0, 0.0),
                (0.01, 0.0, 0.0),
                (0.04, 0.0, 0.0),
            ),
            False,
            False,
        ),
        (
            (
                (0.0, 0.0, 0.0),
                (0.04, 0.0, 0.0),
                (0.0, 0.04, 0.0),
                (0.0, 0.0, 0.04),
            ),
            True,
            True,
        ),
    ],
    ids=("planar", "degenerate", "three-dimensional"),
)
def test_state_snapshot_applies_manual_geometry_capability_policy(
    positions: tuple[tuple[float, float, float], ...],
    supports_topographic: bool,
    supports_three_dimensional: bool,
) -> None:
    service = _snapshot_service()
    service.study.epoch_data = _EpochWithManualGeometry(positions)

    state = service.build()

    assert state.visualization.montage_source == "manual"
    assert state.visualization.channel_positions_available is supports_topographic
    assert (
        state.visualization.three_dimensional_positions_available
        is supports_three_dimensional
    )


def test_state_and_explicit_recommendation_do_not_read_dataset_payload() -> None:
    get_epoch_data = MagicMock(
        side_effect=AssertionError("recommendation read dataset epoch payload")
    )
    state_builder = _snapshot_service()
    state_builder.study.datasets = [
        SimpleNamespace(name="detached-summary-only", get_epoch_data=get_epoch_data)
    ]
    state_builder.dataset_generation = SimpleNamespace(
        dataset_split_state=lambda _datasets: {
            "split_spec_saved": True,
            "split_specification": {},
            "split_specification_fingerprint": "test-split",
            "split_epoch_revision": 1,
            "split_preview_summary": {},
            "split_lifecycle": DatasetSplitLifecycle.VERIFIED,
            "split_materialized": True,
            "active_split_summary": {
                "count": 1,
                "train_count": 32,
                "val_count": 8,
                "test_count": 8,
            },
            "last_split_attempt": {},
        },
    )
    state_builder.training_recommendation = TrainingRecommendationService()

    recommendation_service = state_builder.training_recommendation
    assert recommendation_service is not None
    with patch.object(
        recommendation_service,
        "_build_recommendation",
        wraps=recommendation_service._build_recommendation,
    ) as build_recommendation:
        first = state_builder.build()
        second = state_builder.build()

        assert first.training.recommendation == second.training.recommendation
        assert second.training.recommendation is None
        build_recommendation.assert_not_called()

        explicit = state_builder.refresh_training_recommendation(second)
        build_recommendation.assert_called_once()
        third = state_builder.build()
        fourth = state_builder.build()
        assert explicit == third.training.recommendation
        assert explicit == fourth.training.recommendation
        build_recommendation.assert_called_once()

    get_epoch_data.assert_not_called()


def test_pending_training_submission_publishes_coherent_recommendation_once() -> None:
    state_builder = _snapshot_service()
    recommendation_service = TrainingRecommendationService()
    state_builder.training_recommendation = recommendation_service
    saved_option = SimpleNamespace(
        epoch=30,
        bs=1,
        lr=0.0005,
        optim=type("Adam", (), {}),
        optim_params={},
        evaluation_option=SimpleNamespace(value="Last Epoch"),
        repeat_num=1,
        seed=1729,
        checkpoint_epoch=0,
        output_dir="./output",
        get_device=lambda: "cpu",
        get_optim_name=lambda: "Adam",
        get_configured_repeat_seeds=lambda: [1729],
    )
    state_builder.training_runtime._configuration = replace(
        state_builder.training_runtime.configuration_snapshot(),
        training_option=saved_option,
    )
    recommendation_service.note_configuration_submitted(
        {TrainingRecommendationField.EPOCHS}
    )

    with patch.object(
        recommendation_service,
        "_build_recommendation",
        wraps=recommendation_service._build_recommendation,
    ) as build_recommendation:
        published = state_builder.build()
        reread = state_builder.build()

    recommendation = published.training.recommendation
    assert recommendation is not None
    assert published.training.training_option == {
        "epoch": 30,
        "batch_size": 1,
        "learning_rate": 0.0005,
        "repeat": 1,
        "seed": 1729,
        "repeat_seeds": [1729],
        "device": "cpu",
        "optimizer": "Adam",
        "optimizer_params": {},
        "checkpoint_epoch": 0,
        "output_dir": "./output",
        "evaluation_option": "Last Epoch",
    }
    assert recommendation.values.to_mapping() == {
        TrainingRecommendationField.EPOCHS: 30,
        TrainingRecommendationField.BATCH_SIZE: 1,
        TrainingRecommendationField.LEARNING_RATE: 0.0005,
        TrainingRecommendationField.OPTIMIZER: "Adam",
        TrainingRecommendationField.EVALUATION_STRATEGY: "Last Epoch",
    }
    assert recommendation.provenance["epochs"] is TrainingSettingProvenance.MANUAL
    assert reread.training.recommendation == recommendation
    build_recommendation.assert_called_once()


def test_configure_training_publishes_saved_recommendation_provenance() -> None:
    service = ApplicationService()
    try:
        starting_point = service.get_training_recommendation()
        values = starting_point.values
        command = attach_training_submission_provenance(
            ConfigureTrainingCommand(
                epoch=values.epochs,
                batch_size=values.batch_size,
                learning_rate=values.learning_rate,
                device="cpu",
                optimizer=values.optimizer,
                evaluation_option=values.evaluation_strategy,
            ),
            frozenset({TrainingRecommendationField.EPOCHS}),
        )

        result = service.execute(command)

        assert result.ok is True
        recommendation = result.state.training.recommendation
        assert recommendation is not None
        option = result.state.training.training_option
        assert recommendation.values.to_mapping() == {
            TrainingRecommendationField.EPOCHS: option["epoch"],
            TrainingRecommendationField.BATCH_SIZE: option["batch_size"],
            TrainingRecommendationField.LEARNING_RATE: option["learning_rate"],
            TrainingRecommendationField.OPTIMIZER: option["optimizer"],
            TrainingRecommendationField.EVALUATION_STRATEGY: option[
                "evaluation_option"
            ],
        }
        assert recommendation.manual_fields == (TrainingRecommendationField.EPOCHS,)
        assert "device" not in recommendation.provenance
        assert set(recommendation.provenance) == {
            field.value for field in TrainingRecommendationField
        }
    finally:
        service.close()


def test_training_recommendation_context_uses_saved_split_preview_counts() -> None:
    context = StateSnapshotService._training_recommendation_context(
        epoch=EpochStateSnapshot(
            available=True,
            exists=True,
            epoch_count=12,
            n_channels=22,
            n_times=1_000,
        ),
        dataset=DatasetStateSnapshot(
            split_spec_saved=True,
            split_preview_summary={
                "dataset_count": 1,
                "train_count": 8,
                "validation_count": 2,
                "test_count": 2,
            },
            split_materialized=False,
            active_split_summary={},
        ),
        model_name="braindecode.eegnet",
        model_params={},
        training_option_values={},
    )

    assert context.training_sample_count == 8
    assert context.validation_sample_count == 2
    assert context.dataset_count == 1
    assert context.device == "auto"


def test_state_snapshot_does_not_read_study_training_aliases() -> None:
    class _BlockingStudyAliases:
        def __init__(self, source: _Study) -> None:
            self._source = source

        def __getattr__(self, name: str) -> Any:
            if name in {"model_holder", "training_option", "saliency_params"}:
                raise AssertionError(f"State snapshot read Study.{name}")
            return getattr(self._source, name)

    service = _snapshot_service()
    service.study = _BlockingStudyAliases(service.study)

    state = service.build()

    assert state.state_reliable is True
    assert state.visualization.saliency_configured is True


@pytest.mark.parametrize(
    (
        "case_name",
        "has_raw",
        "has_preprocessed",
        "has_epoch",
        "has_dataset",
        "has_trainer",
        "is_training",
        "finished_run_count",
        "expected_stage",
    ),
    [
        ("empty", False, False, False, False, False, False, 0, "empty"),
        ("raw", True, False, False, False, False, False, 0, "data_loaded"),
        (
            "preprocessed",
            True,
            True,
            False,
            False,
            False,
            False,
            0,
            "preprocessed",
        ),
        (
            "epoch",
            True,
            True,
            True,
            False,
            False,
            False,
            0,
            "epoch_ready",
        ),
        (
            "dataset",
            True,
            True,
            True,
            True,
            False,
            False,
            0,
            "epoch_ready",
        ),
        (
            "training",
            True,
            True,
            True,
            True,
            True,
            True,
            0,
            "training",
        ),
        (
            "trained",
            True,
            True,
            True,
            True,
            True,
            False,
            1,
            "trained",
        ),
    ],
)
def test_state_snapshot_publishes_backend_stage_contract(
    case_name: str,
    has_raw: bool,
    has_preprocessed: bool,
    has_epoch: bool,
    has_dataset: bool,
    has_trainer: bool,
    is_training: bool,
    finished_run_count: int,
    expected_stage: str,
) -> None:
    del case_name
    service = _snapshot_service()
    raw = _Raw()
    service.study.loaded_data_list = [raw] if has_raw else []
    service.study.preprocessed_data_list = [raw] if has_preprocessed else []
    service.study.epoch_data = _Epoch() if has_epoch else None
    service.study.datasets = [object()] if has_dataset else []
    service.study.trainer = _StableTrainer() if has_trainer else None
    service.evaluation_state = _EvaluationControllerWithPlans(
        [_Plan([_FinishedRun(eval_record=object()) for _ in range(finished_run_count)])]
        if finished_run_count
        else []
    )
    service.training_state = (
        _RunningTrainingController() if is_training else _TrainingController()
    )

    assert service.build().pipeline_stage == expected_stage


@pytest.mark.parametrize(
    "terminal_outcome",
    [TrainingOutcomeState.FAILED, TrainingOutcomeState.CANCELLED],
)
def test_trainer_without_finished_results_preserves_terminal_outcome_without_trained_stage(
    terminal_outcome: TrainingOutcomeState,
) -> None:
    service = _snapshot_service()
    service.study.trainer = _StableTrainer()
    controller = _TerminalTrainingController(terminal_outcome)
    service.training = controller
    service.training_state = controller
    cast(_TrainingRuntime, service.training_runtime).training = controller

    state = service.build()

    assert state.evaluation.finished_runs == 0
    assert state.pipeline_stage == "epoch_ready"
    assert state.training.terminal_outcome.state is terminal_outcome


def test_prior_finished_result_remains_available_after_later_training_failure() -> None:
    service = _snapshot_service()
    service.study.trainer = _StableTrainer()
    controller = _TerminalTrainingController(TrainingOutcomeState.FAILED)
    service.training = controller
    service.training_state = controller
    cast(_TrainingRuntime, service.training_runtime).training = controller
    service.evaluation_state = _EvaluationControllerWithPlans(
        [_Plan([_FinishedRun(eval_record=object())])]
    )

    state = service.build()

    assert state.evaluation.finished_runs == 1
    assert state.pipeline_stage == "trained"
    assert state.training.terminal_outcome.state is TrainingOutcomeState.FAILED


def test_state_snapshot_retries_when_training_changes_during_build(
    monkeypatch,
) -> None:
    service = _snapshot_service()
    baseline = service.build()
    mixed = replace(baseline, pipeline_stage="training")
    stable = replace(baseline, pipeline_stage="trained")
    build_once = MagicMock(side_effect=[mixed, stable])
    tokens = iter(
        [
            TrainingStateToken(1, True),
            TrainingStateToken(2, True),
            TrainingStateToken(2, True),
            TrainingStateToken(2, True),
        ]
    )

    class _TokenTrainer:
        def get_state_snapshot_identity(self) -> str:
            return "trainer-state-test"

        def get_state_snapshot_token(self) -> TrainingStateToken:
            return next(tokens)

    service.study.trainer = _TokenTrainer()
    monkeypatch.setattr(service, "_build_once", build_once, raising=False)

    state = service.build()

    assert state == stable
    assert build_once.call_count == 2


def test_state_snapshot_fails_closed_when_training_never_stabilizes(
    monkeypatch,
) -> None:
    service = _snapshot_service()
    baseline = service.build()
    monkeypatch.setattr(
        service,
        "_build_once",
        MagicMock(return_value=baseline),
        raising=False,
    )
    tokens = iter(TrainingStateToken(index, True) for index in range(6))

    class _ChangingTokenTrainer:
        def get_state_snapshot_identity(self) -> str:
            return "state-service-changing-trainer"

        def get_state_snapshot_token(self) -> TrainingStateToken:
            return next(tokens)

    service.study.trainer = _ChangingTokenTrainer()

    state = service.build()

    assert state.state_reliable is False
    assert state.training_liveness_reliable is False
    assert state.active_training.is_running is True
    assert "training state changed during snapshot" in state.read_errors


def test_state_snapshot_fails_closed_for_mismatched_terminal_run_identity() -> None:
    class _DifferentTrainer(_StableTrainer):
        def get_state_snapshot_identity(self) -> str:
            return "different-trainer"

    service = _snapshot_service()
    service.study.trainer = _DifferentTrainer()

    state = service.build()

    assert state.state_reliable is False
    assert state.training_liveness_reliable is False
    assert state.pipeline_stage == "unavailable"
    assert state.training.is_running is True
    assert state.active_training.is_running is True
    assert any(
        "terminal outcome identity does not match" in error
        for error in state.read_errors
    )


def test_state_snapshot_without_trainer_publishes_unknown_terminal_outcome() -> None:
    service = _snapshot_service()
    service.study.trainer = None

    state = service.build()

    assert state.state_reliable is True
    assert state.training.has_trainer is False
    assert state.training.terminal_outcome.state is TrainingOutcomeState.UNKNOWN
    assert state.training.terminal_outcome.run is None


@pytest.mark.parametrize(
    "malformed_token",
    ["not-a-token", (None, True), ("0", True)],
)
def test_state_snapshot_fails_closed_for_malformed_explicit_trainer_token(
    malformed_token,
) -> None:
    class _MalformedTokenTrainer:
        def get_state_snapshot_token(self):
            return malformed_token

    service = _snapshot_service()
    service.study.trainer = _MalformedTokenTrainer()

    state = service.build()

    assert state.state_reliable is False
    assert state.pipeline_stage == "unavailable"
    assert "training state changed during snapshot" in state.read_errors


def test_state_snapshot_fails_closed_for_untracked_active_trainer() -> None:
    service = _snapshot_service()
    service.study.trainer = object()

    state = service.build()

    assert state.state_reliable is False
    assert state.pipeline_stage == "unavailable"
    assert "training state changed during snapshot" in state.read_errors


@pytest.mark.parametrize("add_many", [False, True])
def test_state_snapshot_retries_record_transition_for_added_plan(
    add_many: bool,
) -> None:
    """A record finishing mid-read must not publish a mixed evaluation state."""
    record = object.__new__(TrainRecord)
    record.epoch = 1
    record.option = cast(Any, SimpleNamespace(epoch=1))
    record.eval_record = None
    record._state_tracker = None

    holder = object.__new__(TrainingPlanHolder)
    holder.train_record_list = [record]
    holder._state_tracker = None
    holder._interrupt = threading.Event()
    holder.error = None
    holder.status = "Pending"
    holder.model_holder = cast(
        Any,
        SimpleNamespace(
            target_model=type("EEGNet", (), {}),
        ),
    )

    trainer = Trainer([])
    if add_many:
        trainer.add_training_plan_holders([holder])
    else:
        trainer.add_plan(holder)
    service = _snapshot_service()
    service.study.trainer = trainer
    service.evaluation_state = _EvaluationControllerWithPlans([holder])

    first_finished_read = threading.Event()
    allow_first_read_to_continue = threading.Event()
    original_run_finished = service._run_finished
    call_count = 0

    def pause_after_first_finished_read(run: Any) -> bool:
        nonlocal call_count
        result = original_run_finished(run)
        call_count += 1
        if call_count == 1:
            first_finished_read.set()
            assert allow_first_read_to_continue.wait(timeout=2.0)
        return result

    service._run_finished = pause_after_first_finished_read
    built: list[ApplicationStateSnapshot] = []
    build_thread = threading.Thread(target=lambda: built.append(service.build()))
    build_thread.start()

    assert first_finished_read.wait(timeout=2.0)
    record.set_eval_record(cast(Any, object()))
    allow_first_read_to_continue.set()
    build_thread.join(timeout=2.0)

    assert not build_thread.is_alive()
    assert len(built) == 1
    assert call_count >= 2
    assert built[0].evaluation.finished_runs == 1
    assert built[0].evaluation.metrics_available is True
    assert built[0].state_reliable is True


def test_state_snapshot_records_critical_read_failures_and_fails_closed() -> None:
    state_builder = _snapshot_service()
    state_builder.training_state = _BrokenTrainingController()
    state_builder.evaluation_state = _BrokenEvaluationController()

    state = state_builder.build()

    assert state.training.is_running is True
    assert state.evaluation.total_plans == 0
    assert state.state_reliable is False
    assert state.training_liveness_reliable is False
    assert state.read_errors == [
        "evaluation.plans: evaluation state unavailable",
        "training.is_running: training state unavailable",
    ]

    policy = build_capability_policy(state)
    assert policy.get(CommandName.UPDATE_METADATA).enabled is False
    assert policy.get(CommandName.TRAIN).enabled is False

    assert policy.get(CommandName.QUERY_STATE).enabled is True


@pytest.mark.parametrize(
    ("read_label", "expected_error", "configure", "assert_fallback"),
    [
        (
            "preprocess.is_epoched",
            "epoch state unavailable",
            lambda service: setattr(
                service,
                "preprocess",
                _BrokenPreprocessEpochedController(),
            ),
            lambda state: state.preprocessed.is_epoched is False,
        ),
        (
            "preprocess.channel_names",
            "preprocess channels unavailable",
            lambda service: setattr(
                service,
                "preprocess",
                _BrokenPreprocessChannelController(),
            ),
            lambda state: state.preprocessed.channel_names == [],
        ),
        (
            "training.missing_requirements",
            "training requirements unavailable",
            lambda service: setattr(
                service,
                "training_state",
                _BrokenTrainingRequirementsController(),
            ),
            lambda state: state.training.missing_requirements == [],
        ),
    ],
)
def test_authoritative_controller_read_failure_fails_state_and_publication_closed(
    read_label: str,
    expected_error: str,
    configure,
    assert_fallback,
) -> None:
    state_builder = _snapshot_service()
    configure(state_builder)

    state = state_builder.build()

    assert assert_fallback(state)
    assert state.state_reliable is False
    assert state.read_errors == [f"{read_label}: {expected_error}"]

    publication = ApplicationViewStore(
        state,
        TrainingReadBoundary.no_trainer(),
    ).read()
    assert publication.verified is False
    assert publication.stale is True
    assert read_label in str(publication.refresh_error)
    assert publication.effective_capabilities.get(CommandName.TRAIN).enabled is False


def test_training_progress_failure_is_explicitly_optional_diagnostic() -> None:
    state_builder = _snapshot_service()
    state_builder.training = _BrokenTrainingProgressController()

    state = state_builder.build()

    assert state.training.progress_message is None
    assert state.state_reliable is True
    assert state.read_errors == []
    publication = ApplicationViewStore(
        state,
        TrainingReadBoundary.no_trainer(),
    ).read()
    assert publication.verified is True
    assert publication.stale is False


def test_optional_diagnostic_failures_do_not_invalidate_workflow_state() -> None:
    state_builder = _snapshot_service()
    state_builder.dataset = _BrokenOptionalDatasetDiagnosticsController(
        state_builder.study,
    )
    state_builder.preprocess = _BrokenOptionalPreprocessDiagnosticsController()

    state = state_builder.build()

    assert state.raw.diagnostics == {}
    assert state.raw.event_total == 0
    assert state.raw.unique_events == []
    assert state.preprocessed.diagnostics == {}
    assert state.state_reliable is True
    assert state.read_errors == []


def test_absent_preprocess_context_does_not_read_authoritative_preprocess_fields() -> (
    None
):
    state_builder = _snapshot_service()
    state_builder.study.preprocessed_data_list = []
    state_builder.study.epoch_data = None
    state_builder.preprocess = _UnexpectedPreprocessReadController()

    state = state_builder.build()

    assert state.preprocessed.is_epoched is False
    assert state.preprocessed.channel_names == []
    assert state.state_reliable is True
    assert state.read_errors == []


def test_preprocess_history_failure_fails_capability_driving_state_closed() -> None:
    state_builder = _snapshot_service()
    state_builder.study.preprocessed_data_list = [_BrokenPreprocessHistoryRaw()]

    state = state_builder.build()

    assert state.preprocessed.operations == []
    assert state.state_reliable is False
    assert state.read_errors == [
        "preprocess.history[0]: preprocess history unavailable",
    ]
    policy = build_capability_policy(state)
    assert policy.get(CommandName.LOAD_DATA).enabled is False


def test_malformed_epoch_model_inputs_fail_capability_state_closed() -> None:
    state_builder = _snapshot_service()
    state_builder.study.epoch_data = _MalformedCapabilityEpoch()

    state = state_builder.build()

    assert state.epoch.n_times is None
    assert state.epoch.sfreq is None
    assert state.state_reliable is False
    assert state.read_errors == [
        "epoch.n_times: invalid shape ('invalid', 2, 3)",
        "epoch.sfreq: invalid value 'not-a-frequency'",
    ]
    policy = build_capability_policy(state)
    assert policy.get(CommandName.TRAIN).enabled is False


def test_authoritative_read_failure_marks_committed_publication_stale() -> None:
    state_builder = _snapshot_service()
    boundary = state_builder.capture_training_read_boundary()
    coordinator = ApplicationViewCoordinator(
        state_builder.build(),
        initial_training_boundary=boundary,
        build_state=state_builder.build,
        capture_training_boundary=state_builder.capture_training_read_boundary,
    )
    initial = coordinator.committed()
    state_builder.preprocess = _BrokenPreprocessChannelController()

    refreshed = coordinator.refresh_strict()
    committed = coordinator.committed()

    assert refreshed.state_reliable is False
    assert refreshed.read_errors == [
        "preprocess.channel_names: preprocess channels unavailable",
    ]
    assert committed.generation == initial.generation
    assert committed.verified is False
    assert committed.stale is True
    assert "preprocess.channel_names" in str(committed.refresh_error)
    assert committed.effective_capabilities.get(CommandName.TRAIN).enabled is False


def test_state_snapshot_records_plan_run_list_failure_and_fails_closed() -> None:
    state_builder = _snapshot_service()
    state_builder.evaluation_state = _EvaluationControllerWithPlans([_BrokenPlan()])

    state = state_builder.build()

    assert state.evaluation.total_plans == 1
    assert state.evaluation.total_runs == 0
    assert state.state_reliable is False
    assert state.read_errors == [
        "evaluation.plan[0].runs: plan run list unavailable",
    ]

    policy = build_capability_policy(state)
    assert policy.get(CommandName.UPDATE_METADATA).enabled is False
    assert policy.get(CommandName.TRAIN).enabled is False

    publication = ApplicationViewStore(
        state,
        TrainingReadBoundary.no_trainer(),
    ).read()
    assert publication.verified is False
    assert publication.stale is True
    assert "evaluation.plan[0].runs" in str(publication.refresh_error)
    assert publication.effective_capabilities.get(CommandName.TRAIN).enabled is False


def test_state_snapshot_records_run_completion_failure_and_fails_closed() -> None:
    state_builder = _snapshot_service()
    state_builder.evaluation_state = _EvaluationControllerWithPlans(
        [_Plan([_BrokenRun()])],
    )

    state = state_builder.build()

    assert state.evaluation.total_plans == 1
    assert state.evaluation.total_runs == 1
    assert state.evaluation.finished_runs == 0
    assert state.state_reliable is False
    assert state.read_errors == [
        "evaluation.plan[0].run[0].is_finished: run completion unavailable",
    ]

    policy = build_capability_policy(state)
    assert policy.get(CommandName.EVALUATE).enabled is False
    assert policy.get(CommandName.TRAIN).enabled is False


def test_state_snapshot_records_run_evaluation_record_failure() -> None:
    state_builder = _snapshot_service()
    state_builder.evaluation_state = _EvaluationControllerWithPlans(
        [_Plan([_BrokenEvalRecordRun()])],
    )

    state = state_builder.build()

    assert state.evaluation.total_plans == 1
    assert state.evaluation.total_runs == 1
    assert state.evaluation.finished_runs == 1
    assert state.evaluation.metrics_available is False
    assert state.state_reliable is False
    assert state.read_errors == [
        "evaluation.plan[0].run[0].eval_record: evaluation record unavailable",
    ]


def test_state_snapshot_lock_failure_blocks_raw_edits() -> None:
    state_builder = _snapshot_service()
    state_builder.study.is_locked = lambda: (_ for _ in ()).throw(
        RuntimeError("lock unavailable")
    )

    state = state_builder.build()
    policy = build_capability_policy(state)

    assert state.active_dataset.is_locked is True
    assert state.state_reliable is False
    assert state.training_liveness_reliable is True
    assert state.read_errors == ["dataset.is_locked: lock unavailable"]
    assert policy.get(CommandName.UPDATE_METADATA).enabled is False
    assert (
        "Backend state could not be verified"
        in policy.get(CommandName.UPDATE_METADATA).reasons[0]
    )


def test_state_snapshot_requires_real_saliency_arrays_for_availability() -> None:
    state_builder = _snapshot_service()
    cast(_TrainingRuntime, state_builder.training_runtime).set_saliency_params({})
    empty_eval = type("Eval", (), {"gradient": {0: []}})()
    state_builder.evaluation_state = _EvaluationControllerWithPlans(
        [_Plan([_FinishedRun(empty_eval)])],
    )

    state = state_builder.build()

    assert state.evaluation.finished_runs == 1
    assert state.visualization.saliency_configured is False
    assert state.visualization.saliency_available is False


def test_state_snapshot_reports_saliency_available_only_with_output_data() -> None:
    state_builder = _snapshot_service()
    cast(_TrainingRuntime, state_builder.training_runtime).set_saliency_params(
        {"SmoothGrad": {"nt_samples": 1}}
    )
    eval_record = SimpleNamespace(
        saliency_context=SimpleNamespace(
            class_map=((1, "left"),),
            channel_names=("C3", "C4"),
            epoch_sample_count=2,
        ),
        saliency_context_status="verified",
        gradient={0: np.ones((1, 2, 2), dtype=np.float32)},
    )
    state_builder.evaluation_state = _EvaluationControllerWithPlans(
        [_Plan([_FinishedRun(eval_record)])],
    )

    state = state_builder.build()

    assert state.evaluation.finished_runs == 1
    assert state.visualization.saliency_configured is True
    assert state.visualization.saliency_available is True


def test_state_snapshot_reports_saliency_coverage_per_method_and_class() -> None:
    state_builder = _snapshot_service()
    eval_record = SimpleNamespace(
        saliency_context=SimpleNamespace(
            class_map=((769, "Left hand"), (770, "Right hand")),
            channel_names=("C3", "C4"),
            epoch_sample_count=2,
        ),
        saliency_context_status="verified",
        gradient={
            0: np.ones((1, 2, 2), dtype=np.float32),
            1: np.empty((0, 2, 2), dtype=np.float32),
        },
        gradient_input={
            0: np.full((1, 2, 2), 0.5, dtype=np.float32),
            1: np.full((1, 2, 2), 0.25, dtype=np.float32),
        },
        smoothgrad={},
        smoothgrad_sq={},
        vargrad={},
    )
    state_builder.evaluation_state = _EvaluationControllerWithPlans(
        [_Plan([_FinishedRun(eval_record)])],
    )

    state = state_builder.build()

    assert state.visualization.saliency_available is True
    assert len(state.visualization.saliency_coverage) == 1
    run_coverage = state.visualization.saliency_coverage[0]
    assert (run_coverage.plan_index, run_coverage.run_index) == (0, 0)

    methods = {item.method: item for item in run_coverage.methods}
    gradient = methods["Gradient"]
    assert gradient.available is True
    assert gradient.complete is False
    assert [item.display_name for item in gradient.classes] == [
        "Left hand",
        "Right hand",
    ]
    assert [item.available for item in gradient.classes] == [True, False]
    assert "Recompute" in str(gradient.classes[1].reason)

    gradient_input = methods["Gradient * Input"]
    assert gradient_input.available is True
    assert gradient_input.complete is True
    assert all(item.available for item in gradient_input.classes)

    serialized = state.to_dict()["visualization"]["saliency_coverage"]
    assert serialized[0]["methods"][0]["classes"][0]["event_code"] == 769
    assert serialized[0]["methods"][0]["classes"][1]["available"] is False


def test_state_snapshot_consumes_injected_saliency_coverage_projector() -> None:
    projector = MagicMock(spec=SaliencyCoverageProjector)
    projector.label_items_from_epoch.return_value = [(769, "Left hand")]
    projected_run = SaliencyRunCoverageSnapshot(
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
    projector.project_run.return_value = projected_run
    state_builder = _snapshot_service(saliency_coverage_projector=projector)
    eval_record = SimpleNamespace(gradient={0: [[1.0]]})
    state_builder.evaluation_state = _EvaluationControllerWithPlans(
        [_Plan([_FinishedRun(eval_record)])],
    )

    state = state_builder.build()

    projector.label_items_from_epoch.assert_called_once_with(
        state_builder.study.epoch_data,
    )
    projector.project_run.assert_called_once_with(
        eval_record,
        plan_index=0,
        run_index=0,
        label_items=[(769, "Left hand")],
    )
    assert state.visualization.saliency_coverage == [
        replace(
            projected_run,
            plan_name="Plan 1",
            model_name="Unknown model",
            run_name="Run 1",
        )
    ]
    assert state.visualization.saliency_available is True


def test_state_snapshot_does_not_publish_incompatible_saliency_arrays() -> None:
    state_builder = _snapshot_service()
    eval_record = SimpleNamespace(
        saliency_context=SimpleNamespace(
            class_map=((1, "left"),),
            channel_names=("C3", "C4"),
            epoch_sample_count=2,
        ),
        saliency_context_status="incompatible",
        saliency_recompute_reason="Saliency context integrity check failed.",
        gradient={0: np.ones((1, 2, 2), dtype=np.float32)},
    )
    state_builder.evaluation_state = _EvaluationControllerWithPlans(
        [_Plan([_FinishedRun(eval_record)])],
    )

    state = state_builder.build()

    gradient = state.visualization.saliency_coverage[0].methods[0]
    assert gradient.method == "Gradient"
    assert gradient.available is False
    assert gradient.complete is False
    assert state.visualization.saliency_available is False


@pytest.mark.parametrize(
    ("available", "complete"),
    [(True, False), (False, True)],
)
def test_state_snapshot_requires_consistent_complete_saliency_coverage_for_publication(
    available: bool,
    complete: bool,
) -> None:
    projector = MagicMock(spec=SaliencyCoverageProjector)
    projector.label_items_from_epoch.return_value = [(1, "left")]
    projector.project_run.return_value = SaliencyRunCoverageSnapshot(
        plan_index=0,
        run_index=0,
        methods=[
            SaliencyMethodCoverageSnapshot(
                method="Gradient",
                available=available,
                complete=complete,
            ),
        ],
    )
    state_builder = _snapshot_service(saliency_coverage_projector=projector)
    state_builder.evaluation_state = _EvaluationControllerWithPlans(
        [_Plan([_FinishedRun(SimpleNamespace())])],
    )

    state = state_builder.build()

    assert state.visualization.saliency_available is False


def test_state_snapshot_saliency_coverage_is_backward_compatible_when_empty() -> None:
    state_builder = _snapshot_service()
    state_builder.evaluation_state = _EvaluationControllerWithPlans(
        [_Plan([_FinishedRun(SimpleNamespace(gradient={}))])],
    )

    state = state_builder.build()

    assert state.visualization.saliency_available is False
    assert len(state.visualization.saliency_coverage) == 1
    assert all(
        method.available is False
        for method in state.visualization.saliency_coverage[0].methods
    )
    assert ApplicationStateSnapshot.empty().visualization.saliency_coverage == []
    assert (
        ApplicationStateSnapshot.empty().visualization.post_training_saliency.phase
        is PostTrainingSaliencyPhase.IDLE
    )


@pytest.mark.parametrize(
    ("phase", "error_code", "message"),
    [
        (PostTrainingSaliencyPhase.PENDING, None, None),
        (PostTrainingSaliencyPhase.RUNNING, None, None),
        (
            PostTrainingSaliencyPhase.FAILED,
            "cuda_oom",
            "Automatic saliency could not finish.",
        ),
        (
            PostTrainingSaliencyPhase.CANCELLED,
            None,
            "Automatic saliency computation was cancelled.",
        ),
    ],
)
def test_state_snapshot_serializes_post_training_saliency_lifecycle(
    phase: PostTrainingSaliencyPhase,
    error_code: str | None,
    message: str | None,
) -> None:
    pending = PostTrainingSaliencyStatus.pending(
        generation=4,
        run=TrainingRunIdentity(trainer_id="trainer-saliency", run_id=2),
        training_generation=9,
        methods=("Gradient", "Gradient * Input"),
    )
    status = (
        pending
        if phase is PostTrainingSaliencyPhase.PENDING
        else pending.transition(
            generation=4,
            phase=phase,
            error_code=error_code,
            message=message,
            diagnostic_type="OutOfMemoryError"
            if phase is PostTrainingSaliencyPhase.FAILED
            else None,
        )
    )
    state_builder = _snapshot_service()
    cast(_TrainingRuntime, state_builder.training_runtime).set_saliency_status(status)

    state = state_builder.build()

    assert state.visualization.post_training_saliency == status
    serialized = state.to_dict()["visualization"]["post_training_saliency"]
    assert serialized["phase"] == phase.value
    assert serialized["generation"] == 4
    assert serialized["run"] == {
        "trainer_id": "trainer-saliency",
        "run_id": 2,
    }
    assert serialized["methods"] == ["Gradient", "Gradient * Input"]
    assert serialized["error_code"] == error_code


def test_state_snapshot_preserves_retired_saliency_generation() -> None:
    status = PostTrainingSaliencyStatus.idle(generation=12)
    state_builder = _snapshot_service()
    cast(_TrainingRuntime, state_builder.training_runtime).set_saliency_status(status)

    state = state_builder.build()

    assert state.visualization.post_training_saliency.phase is (
        PostTrainingSaliencyPhase.IDLE
    )
    assert state.visualization.post_training_saliency.generation == 12
    serialized = state.to_dict()["visualization"]["post_training_saliency"]
    assert serialized["phase"] == "idle"
    assert serialized["generation"] == 12


def test_data_summary_query_falls_back_to_state_when_loaded_list_query_fails() -> None:
    state_builder = _snapshot_service()
    state = state_builder.build()
    state_builder.dataset = _BrokenLoadedDataController(state_builder.study)

    summary = state_builder.data_summary_from_state(state)

    assert summary["count"] == state.raw.count
    assert summary["files"] == state.raw.files
    assert summary["formats"] == state.raw.formats
    assert summary["metadata"] == state.raw.metadata
    assert summary["unique_labels"] == ["left"]


def test_published_data_summary_preserves_live_summary_schema() -> None:
    state_builder = _snapshot_service()
    state = state_builder.build()

    published = state_builder.data_summary_from_published_state(state)
    live = state_builder.data_summary_from_state(state)

    assert published == live
    assert published == {
        "count": 1,
        "files": ["subject01.fif"],
        "formats": [".fif"],
        "channels": ["C3", "C4"],
        "metadata": [
            {
                "index": "0",
                "file": "subject01.fif",
                "subject": "S01",
                "session": "session-01",
            }
        ],
        "total": 2,
        "unique_count": 1,
        "unique_labels": ["left"],
        "runtime_signals": ["signal one"],
        "gdf_duplicate_channel_files": ["sub01.gdf"],
        "gdf_duplicate_channel_details": [
            {
                "file": "sub01.gdf",
                "generated_bases": ["EEG"],
                "generated_channels": ["EEG-0", "EEG-1"],
                "message": "detail message",
            }
        ],
        "source": "runtime",
    }


def test_query_state_service_returns_readonly_summaries() -> None:
    state_builder = _snapshot_service()
    query = QueryStateCommandService(
        study=state_builder.study,
        dataset=state_builder.dataset,
        state_builder=state_builder,
        get_state=state_builder.build,
    )

    summary_message, summary = _expect_payload(
        query.handle_query_state(QueryStateCommand(query="data_summary")),
    )
    assert summary_message == "Dataset summary ready."
    assert summary["count"] == 1
    assert summary["unique_labels"] == ["left"]
    assert summary["runtime_signals"] == ["signal one"]
    assert summary["gdf_duplicate_channel_files"] == ["sub01.gdf"]
    assert summary["gdf_duplicate_channel_details"][0]["message"] == "detail message"

    suggestions_message, suggestions = _expect_payload(
        query.handle_query_state(
            QueryStateCommand(
                query="smart_filter_suggestions",
                params={"target_index": 0, "target_count": 2},
            ),
        ),
    )
    assert suggestions_message == "Smart filter suggestions ready."
    assert suggestions == {"suggestions": [0, 1]}

    data_lists_message, data_lists = _expect_payload(
        query.handle_query_state(QueryStateCommand(query="data_lists")),
    )
    assert data_lists_message == "Data list query ready."
    assert set(data_lists) == {
        "raw_count",
        "preprocessed_count",
        "raw_files",
        "preprocessed_files",
        "raw_rows",
        "preprocessed_rows",
    }
    assert data_lists["raw_count"] == 1
    assert data_lists["preprocessed_count"] == 1
    assert data_lists["raw_files"] == ["subject01.fif"]
    assert data_lists["preprocessed_files"] == ["subject01.fif"]
    assert data_lists["raw_rows"] == [{"filepath": "subject01.fif"}]
    assert data_lists["preprocessed_rows"] == [{"filepath": "subject01.fif"}]
    assert "loaded_data_list" not in data_lists
    assert "preprocessed_data_list" not in data_lists

    history_message, history = _expect_payload(
        query.handle_query_state(QueryStateCommand(query="training_history")),
    )
    assert history_message == "Training history query ready."
    assert history["row_count"] == 1
    assert history["rows"][0] == {
        "identity": {"plan_index": 0, "run_index": 0},
        "group_name": "Group 1",
        "run_name": "1",
        "model_name": "EEGNet",
        "runtime_device": "",
        "status": "Running",
        "status_detail": None,
        "epoch": 2,
        "max_epochs": 0,
        "is_active": True,
        "is_current_run": True,
        "start_timestamp": None,
        "end_timestamp": None,
        "metrics": {
            "train": {
                "loss": [],
                "accuracy": [],
                "auc": [],
                "lr": [],
                "time": [],
            },
            "validation": {
                "loss": [],
                "accuracy": [],
                "auc": [],
            },
            "test": {"accuracy": []},
        },
    }

    with pytest.raises(
        ValueError,
        match="Unknown query_state request: dataset_generation_context",
    ):
        query.handle_query_state(
            QueryStateCommand(query="dataset_generation_context"),
        )


def test_query_state_service_rejects_duplicate_state_publication_route() -> None:
    state_builder = _snapshot_service()
    query = QueryStateCommandService(
        study=state_builder.study,
        dataset=state_builder.dataset,
        state_builder=state_builder,
        get_state=state_builder.build,
    )

    with pytest.raises(PreconditionError, match="ApplicationService publication"):
        query.handle_query_state(QueryStateCommand(query="state"))


def test_training_history_query_does_not_build_full_state_snapshot() -> None:
    state_builder = _snapshot_service()

    def fail_get_state() -> ApplicationStateSnapshot:
        raise AssertionError("training_history should not build the full state")

    query = QueryStateCommandService(
        study=state_builder.study,
        dataset=state_builder.dataset,
        state_builder=state_builder,
        get_state=fail_get_state,
    )

    message, payload = _expect_payload(
        query.handle_query_state(
            QueryStateCommand(query="training_history"),
        ),
    )

    assert message == "Training history query ready."
    assert payload["row_count"] == 1
    assert "plan" not in payload["rows"][0]
    assert "record" not in payload["rows"][0]
    assert payload["rows"][0]["identity"] == {
        "plan_index": 0,
        "run_index": 0,
    }
