"""Focused tests for dataset-generation command handlers."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, Generic, Protocol, TypeVar, cast

import numpy as np
import pytest

from XBrainLab.backend.application.commands import (
    ClearDatasetsCommand,
    DatasetGenerationMode,
    GenerateDatasetCommand,
)
from XBrainLab.backend.application.dataset_generation_service import (
    DatasetGenerationCommandService,
    HandlerResult,
)
from XBrainLab.backend.application.errors import ApplicationError
from XBrainLab.backend.application.results import ErrorType
from XBrainLab.backend.dataset import (
    Dataset,
    DataSplittingConfig,
    EpochWindowProvenance,
    SplitByType,
    SplitUnit,
    TrainingType,
    ValSplitByType,
)
from XBrainLab.backend.exceptions import StaleTrainingPipelineMutationError
from XBrainLab.backend.training_manager import TrainingManager
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyStatus,
    TrainingOutcomeState,
    TrainingPipelineMutationBoundary,
    TrainingReadBoundary,
    TrainingRunIdentity,
    TrainingStateToken,
    TrainingTerminalOutcome,
)


class _Epoch:
    def __init__(self) -> None:
        self.subjects = np.asarray([1, 1, 2, 3])
        self.sessions = np.asarray([1, 1, 2, 3])
        self.labels = np.asarray([1, 2, 1, 2])

    def get_subject_list_by_mask(self, mask: np.ndarray) -> np.ndarray:
        return self.subjects[mask]

    def get_session_list_by_mask(self, mask: np.ndarray) -> np.ndarray:
        return self.sessions[mask]

    def get_label_list_by_mask(self, mask: np.ndarray) -> np.ndarray:
        return self.labels[mask]

    def get_epoch_window_provenance(
        self,
    ) -> tuple[EpochWindowProvenance, ...]:
        return tuple(
            EpochWindowProvenance(
                source_recording_id=f"content-sha256:{'a' * 64}",
                event_sample=index * 100,
                window_start_sample=index * 100,
                window_end_sample_exclusive=(index + 1) * 100,
                source_sfreq=100.0,
                epoch_sfreq=100.0,
                tmin_seconds=0.0,
                tmax_seconds=0.99,
                source_coordinates_verified=True,
            )
            for index in range(len(self.labels))
        )


class _Dataset:
    def __init__(
        self,
        *,
        train: list[bool],
        val: list[bool],
        test: list[bool],
    ) -> None:
        self.train_mask = np.asarray(train)
        self.val_mask = np.asarray(val)
        self.test_mask = np.asarray(test)
        self._epoch = _Epoch()

    def get_name(self) -> str:
        return "focused-dataset"

    def get_epoch_data(self) -> _Epoch:
        return self._epoch


class _DataManager:
    def __init__(self) -> None:
        self.datasets: list[Any] = []
        self.dataset_generator: Any | None = None
        self.loaded_data_list: list[Any] = []
        self.backup_loaded_data_list: list[Any] | None = None
        self.preprocessed_data_list: list[Any] = []
        self.epoch_data: Any | None = None
        self.dataset_locked = False

    def set_datasets(self, datasets: list[Any], force_update: bool = False) -> None:
        del force_update
        self.datasets = list(datasets)


class _TrainingManager:
    def __init__(self) -> None:
        self.trainer: Any | None = None
        self.saliency_generation = 0

    def capture_pipeline_mutation_boundary(
        self,
    ) -> TrainingPipelineMutationBoundary:
        trainer_identity = (
            None if self.trainer is None else f"trainer:{id(self.trainer)}"
        )
        return TrainingPipelineMutationBoundary(
            read_boundary=(
                TrainingReadBoundary.no_trainer()
                if trainer_identity is None
                else TrainingReadBoundary(
                    trainer_identity=trainer_identity,
                    token=TrainingStateToken(generation=1, stable=True),
                )
            ),
            terminal_outcome=TrainingTerminalOutcome(
                state=(
                    TrainingOutcomeState.UNKNOWN
                    if trainer_identity is None
                    else TrainingOutcomeState.NOT_STARTED
                ),
                detail="No active training worker.",
            ),
            saliency_status=PostTrainingSaliencyStatus.idle(
                generation=self.saliency_generation,
            ),
            saliency_work_active=False,
        )

    def retire_trainer_if_current(
        self,
        expected: TrainingPipelineMutationBoundary,
    ) -> bool:
        if self.capture_pipeline_mutation_boundary() != expected:
            raise StaleTrainingPipelineMutationError
        retired = self.trainer is not None
        self.trainer = None
        self.saliency_generation += 1
        return retired

    def commit_pipeline_replacement(
        self,
        expected: TrainingPipelineMutationBoundary,
        *,
        publish: Callable[[], None],
    ) -> bool:
        if self.capture_pipeline_mutation_boundary() != expected:
            raise StaleTrainingPipelineMutationError
        publish()
        return self.retire_trainer_if_current(expected)


class _StableTrainer:
    def __init__(self) -> None:
        self.run = TrainingRunIdentity(trainer_id="dataset-audit-trainer", run_id=1)
        self.clean_calls: list[bool] = []

    def get_state_snapshot_identity(self) -> str:
        return self.run.trainer_id

    def get_state_snapshot_token(self) -> TrainingStateToken:
        return TrainingStateToken(generation=7, stable=True)

    def get_terminal_outcome(self) -> TrainingTerminalOutcome:
        return TrainingTerminalOutcome(
            state=TrainingOutcomeState.COMPLETED,
            run=self.run,
        )

    def is_running(self) -> bool:
        return False

    def clean(self, *, force_update: bool) -> None:
        self.clean_calls.append(force_update)


class _Generator:
    def __init__(
        self,
        datasets: list[Any],
        *,
        before_prepare: Callable[[], None] | None = None,
    ) -> None:
        self.datasets = list(datasets)
        self.before_prepare = before_prepare
        self.prepare_count = 0

    def prepare_result(self) -> list[Any]:
        self.prepare_count += 1
        if self.before_prepare is not None:
            self.before_prepare()
        return list(self.datasets)


class _TrainerOwner(Protocol):
    trainer: Any | None


_ManagerT = TypeVar("_ManagerT", bound=_TrainerOwner)


class _Study(Generic[_ManagerT]):
    def __init__(self, training_manager: _ManagerT) -> None:
        self.data_manager = _DataManager()
        self.training_manager = training_manager
        self.generated_config: DataSplittingConfig | None = None
        self.next_datasets: list[Any] = []

    @property
    def datasets(self) -> list[Any]:
        return self.data_manager.datasets

    @property
    def dataset_generator(self) -> Any | None:
        return self.data_manager.dataset_generator

    @property
    def trainer(self) -> Any | None:
        return self.training_manager.trainer

    def get_datasets_generator(self, config: DataSplittingConfig) -> object:
        self.generated_config = config
        return _Generator(self.next_datasets)


class _TrainingController:
    def __init__(self, study: _Study[Any]) -> None:
        self.study = study
        self.cleaned = False
        self.force_update: bool | None = None

    @property
    def next_datasets(self) -> list[Any]:
        return self.study.next_datasets

    @next_datasets.setter
    def next_datasets(self, value: list[Any]) -> None:
        self.study.next_datasets = list(value)

    def apply_data_splitting(self, generator: Any) -> None:
        del generator
        raise AssertionError("dataset generation must be staged before publication")

    def clean_datasets(self, *, force_update: bool) -> None:
        self.cleaned = True
        self.force_update = force_update


def _expect_payload(result: HandlerResult) -> tuple[str, dict[str, Any]]:
    assert isinstance(result, tuple)
    return cast(tuple[str, dict[str, Any]], result)


def _service() -> tuple[
    DatasetGenerationCommandService,
    _Study[_TrainingManager],
    _TrainingController,
]:
    study = _Study(_TrainingManager())
    training = _TrainingController(study)
    return (
        DatasetGenerationCommandService(
            study=study,
            training=training,
            has_trainer=lambda: study.training_manager.trainer is not None,
        ),
        study,
        training,
    )


def test_dataset_generation_service_builds_config_audits_and_summarizes() -> None:
    service, study, training = _service()
    training.next_datasets = [
        _Dataset(
            train=[True, True, False, False],
            val=[False, False, True, False],
            test=[False, False, False, True],
        ),
    ]

    message, payload = _expect_payload(
        service.handle_generate_dataset(
            GenerateDatasetCommand(
                split_strategy="trial",
                training_mode="group",
                test_ratio=0.25,
                val_ratio=0.25,
            ),
        ),
    )

    assert message == "Generated 1 dataset(s)."
    assert study.generated_config is not None
    assert study.generated_config.train_type == TrainingType.FULL
    assert payload["dataset_count"] == 1
    assert payload["protocol"] == "trial-wise"
    assert payload["split_audit"]["ok"] is True
    assert payload["split_summary"]["train_count"] == 2
    assert payload["split_summary"]["val_count"] == 1
    assert payload["split_summary"]["test_count"] == 1


@pytest.mark.parametrize(
    ("split_strategy", "expected_test_split", "expected_val_split", "protocol"),
    [
        ("trial", SplitByType.TRIAL, ValSplitByType.TRIAL, "trial-wise"),
        ("session", SplitByType.SESSION, ValSplitByType.SESSION, "session-wise"),
        ("subject", SplitByType.SUBJECT, ValSplitByType.SUBJECT, "subject-wise"),
    ],
)
def test_dataset_generation_service_maps_command_split_strategies_without_facade(
    split_strategy: str,
    expected_test_split: SplitByType,
    expected_val_split: ValSplitByType,
    protocol: str,
) -> None:
    service, study, training = _service()
    training.next_datasets = [
        _Dataset(
            train=[True, True, False, False],
            val=[False, False, True, False],
            test=[False, False, False, True],
        ),
    ]

    _message, payload = _expect_payload(
        service.handle_generate_dataset(
            GenerateDatasetCommand(
                split_strategy=split_strategy,
                test_ratio=0.25,
                val_ratio=0.25,
            ),
        ),
    )

    assert study.generated_config is not None
    assert (
        study.generated_config.test_splitter_list[0].split_type == expected_test_split
    )
    assert study.generated_config.val_splitter_list[0].split_type == expected_val_split
    assert payload["protocol"] == protocol
    assert payload["split_audit"]["ok"] is True


@pytest.mark.parametrize(
    ("training_mode", "expected_train_type"),
    [
        ("individual", TrainingType.IND),
        ("group", TrainingType.FULL),
    ],
)
def test_dataset_generation_service_maps_command_training_modes_without_facade(
    training_mode: str,
    expected_train_type: TrainingType,
) -> None:
    service, study, training = _service()
    training.next_datasets = [
        _Dataset(
            train=[True, True, False, False],
            val=[False, False, True, False],
            test=[False, False, False, True],
        ),
    ]

    _message, payload = _expect_payload(
        service.handle_generate_dataset(
            GenerateDatasetCommand(training_mode=training_mode),
        ),
    )

    assert study.generated_config is not None
    assert study.generated_config.train_type == expected_train_type
    assert payload["split_audit"]["ok"] is True


def test_dataset_generation_service_empty_split_payload_fails_through_audit() -> None:
    service, study, training = _service()
    training.next_datasets = [
        _Dataset(
            train=[True, True, True, True],
            val=[False, False, False, False],
            test=[False, False, False, False],
        ),
    ]

    with pytest.raises(ApplicationError) as exc_info:
        service.handle_generate_dataset(
            GenerateDatasetCommand(
                split_config={
                    "train_type": "Full Data",
                    "is_cross_validation": False,
                    "val_splitters": [],
                    "test_splitters": [],
                },
            ),
        )

    assert study.generated_config is not None
    assert study.generated_config.val_splitter_list == []
    assert study.generated_config.test_splitter_list == []
    error = exc_info.value
    assert error.error_type == ErrorType.DATA_MISMATCH
    assert any(
        "split is empty" in issue["message"]
        for issue in error.diagnostics["split_audit"]["issues"]
    )


def test_dataset_generation_service_rolls_back_unknown_trial_provenance() -> None:
    service, study, training = _service()
    dataset = _Dataset(
        train=[True, True, False, False],
        val=[False, False, True, False],
        test=[False, False, False, True],
    )
    dataset._epoch.get_epoch_window_provenance = lambda: tuple(  # type: ignore[method-assign]
        EpochWindowProvenance(
            source_recording_id=f"unverified-wrapper-sha256:{'b' * 64}",
            event_sample=index * 100,
            window_start_sample=index * 100,
            window_end_sample_exclusive=(index + 1) * 100,
            source_sfreq=100.0,
            epoch_sfreq=100.0,
            tmin_seconds=0.0,
            tmax_seconds=0.99,
            source_coordinates_verified=False,
        )
        for index in range(4)
    )
    training.next_datasets = [dataset]

    with pytest.raises(ApplicationError) as exc_info:
        service.handle_generate_dataset(
            GenerateDatasetCommand(split_strategy="trial"),
        )

    error = exc_info.value
    provenance_issue = next(
        issue
        for issue in error.diagnostics["split_audit"]["issues"]
        if issue["details"].get("kind") == "missing_epoch_window_provenance"
    )
    assert error.error_type == ErrorType.DATA_MISMATCH
    assert error.diagnostics["rolled_back"] is True
    assert provenance_issue["severity"] == "error"
    assert provenance_issue["details"]["unverified_count"] == 4
    assert study.datasets == []
    assert study.dataset_generator is None
    assert study.trainer is None


def test_dataset_generation_service_accepts_trial_kfold_split_payload() -> None:
    service, study, training = _service()
    training.next_datasets = [
        _Dataset(
            train=[True, True, False, False],
            val=[False, False, True, False],
            test=[False, False, False, True],
        ),
    ]

    _message, payload = _expect_payload(
        service.handle_generate_dataset(
            GenerateDatasetCommand(
                split_config={
                    "train_type": "Full Data",
                    "is_cross_validation": True,
                    "val_splitters": [
                        {
                            "split_type": "By Trial",
                            "split_unit": "Ratio",
                            "value": "0.2",
                        },
                    ],
                    "test_splitters": [
                        {
                            "split_type": "By Trial",
                            "split_unit": "K Fold",
                            "value": "5",
                        },
                    ],
                },
            ),
        ),
    )

    assert study.generated_config is not None
    assert study.generated_config.is_cross_validation is True
    assert study.generated_config.test_splitter_list[0].split_type == SplitByType.TRIAL
    assert study.generated_config.test_splitter_list[0].split_unit == SplitUnit.KFOLD
    assert study.generated_config.test_splitter_list[0].value_var == "5"
    assert payload["protocol"] == "trial-wise"
    assert payload["split_audit"]["ok"] is True


def test_dataset_generation_service_rolls_back_failed_split_audit() -> None:
    service, study, training = _service()
    previous_dataset = object()
    previous_generator = object()
    previous_trainer = object()
    study.data_manager.datasets = [previous_dataset]
    study.data_manager.dataset_generator = previous_generator
    study.training_manager.trainer = previous_trainer
    previous_saliency_generation = study.training_manager.saliency_generation
    training.next_datasets = [
        _Dataset(
            train=[True, False, False],
            val=[False, False, False],
            test=[False, True, False],
        ),
    ]

    with pytest.raises(ApplicationError) as exc_info:
        service.handle_generate_dataset(
            GenerateDatasetCommand(
                split_strategy="trial",
                replacement_mode=DatasetGenerationMode.REPLACE_EXISTING,
                confirmed=True,
            ),
        )

    error = exc_info.value
    assert error.error_type == ErrorType.DATA_MISMATCH
    assert error.diagnostics["rolled_back"] is True
    assert any(
        "split is empty" in issue["message"]
        for issue in error.diagnostics["split_audit"]["issues"]
    )
    assert study.data_manager.datasets == [previous_dataset]
    assert study.data_manager.dataset_generator is previous_generator
    assert study.training_manager.trainer is previous_trainer
    assert study.training_manager.saliency_generation == previous_saliency_generation
    assert training.cleaned is False


def test_failed_split_audit_restores_shared_epoch_evidence_and_dataset_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, study, _training = _service()
    shared_epoch = SimpleNamespace(
        trial_selection_evidence=[{"source": "accepted", "count": 4}],
        trial_selection_evidence_dropped=2,
    )
    study.data_manager.epoch_data = shared_epoch
    monkeypatch.setattr(Dataset, "SEQ", 41)
    candidate = _Dataset(
        train=[True, False, False],
        val=[False, False, False],
        test=[False, True, False],
    )

    def mutate_shared_generation_state() -> None:
        Dataset.SEQ = 1
        shared_epoch.trial_selection_evidence[0]["source"] = "candidate"
        shared_epoch.trial_selection_evidence.append({"source": "rejected"})
        shared_epoch.trial_selection_evidence_dropped = 9

    generator = _Generator(
        [candidate],
        before_prepare=mutate_shared_generation_state,
    )
    monkeypatch.setattr(study, "get_datasets_generator", lambda _config: generator)

    with pytest.raises(ApplicationError):
        service.handle_generate_dataset(
            GenerateDatasetCommand(split_strategy="trial"),
        )

    assert Dataset.SEQ == 41
    assert shared_epoch.trial_selection_evidence == [{"source": "accepted", "count": 4}]
    assert shared_epoch.trial_selection_evidence_dropped == 2


def test_failed_split_audit_preserves_concrete_saliency_terminal_state() -> None:
    manager = TrainingManager()
    study = _Study(manager)
    training = _TrainingController(study)
    service = DatasetGenerationCommandService(
        study=study,
        training=training,
        has_trainer=manager.has_trainer,
    )
    previous_dataset = object()
    previous_generator = object()
    trainer = _StableTrainer()
    manager.trainer = cast(Any, trainer)
    manager.saliency_params = {"Gradient": {"absolute": True}}
    pending = PostTrainingSaliencyStatus.pending(
        generation=4,
        run=trainer.run,
        training_generation=7,
        methods=("Gradient",),
    )
    running = pending.transition(
        generation=4,
        phase=PostTrainingSaliencyPhase.RUNNING,
    )
    succeeded = running.transition(
        generation=4,
        phase=PostTrainingSaliencyPhase.SUCCEEDED,
        message="Automatic saliency is available.",
    )
    manager._post_training_saliency_status = succeeded
    study.data_manager.datasets = [previous_dataset]
    study.data_manager.dataset_generator = previous_generator
    training.next_datasets = [
        _Dataset(
            train=[True, False, False],
            val=[False, False, False],
            test=[False, True, False],
        ),
    ]

    with pytest.raises(ApplicationError):
        service.handle_generate_dataset(
            GenerateDatasetCommand(
                split_strategy="trial",
                replacement_mode=DatasetGenerationMode.REPLACE_EXISTING,
                confirmed=True,
            ),
        )

    assert study.data_manager.datasets == [previous_dataset]
    assert study.data_manager.dataset_generator is previous_generator
    assert manager.trainer is trainer
    assert manager.get_post_training_saliency_status() is succeeded
    assert manager.saliency_params == {"Gradient": {"absolute": True}}
    assert trainer.clean_calls == []


def test_dataset_generation_service_stale_commit_preserves_newer_trainer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, study, training = _service()
    previous_dataset = object()
    previous_generator = object()
    previous_trainer = object()
    replacement_trainer = object()
    replacement_dataset = _Dataset(
        train=[True, True, False, False],
        val=[False, False, True, False],
        test=[False, False, False, True],
    )
    study.data_manager.datasets = [previous_dataset]
    study.data_manager.dataset_generator = previous_generator
    study.training_manager.trainer = previous_trainer

    def replace_training_before_prepare() -> None:
        study.training_manager.trainer = replacement_trainer

    generator = _Generator(
        [replacement_dataset],
        before_prepare=replace_training_before_prepare,
    )
    monkeypatch.setattr(study, "get_datasets_generator", lambda _config: generator)

    with pytest.raises(ApplicationError) as exc_info:
        service.handle_generate_dataset(
            GenerateDatasetCommand(
                replacement_mode=DatasetGenerationMode.REPLACE_EXISTING,
                confirmed=True,
            ),
        )

    assert exc_info.value.diagnostics["rolled_back"] is True
    assert study.data_manager.datasets == [previous_dataset]
    assert study.data_manager.dataset_generator is previous_generator
    assert study.training_manager.trainer is replacement_trainer
    assert training.cleaned is False


def test_dataset_generation_service_requires_explicit_replacement_mode() -> None:
    service, study, training = _service()
    previous_dataset = object()
    previous_generator = object()
    previous_trainer = object()
    study.data_manager.datasets = [previous_dataset]
    study.data_manager.dataset_generator = previous_generator
    study.training_manager.trainer = previous_trainer

    with pytest.raises(ApplicationError) as exc_info:
        service.handle_generate_dataset(GenerateDatasetCommand())

    assert exc_info.value.error_type == ErrorType.PRECONDITION
    assert exc_info.value.diagnostics["replacement_required"] is True
    assert study.data_manager.datasets == [previous_dataset]
    assert study.data_manager.dataset_generator is previous_generator
    assert study.training_manager.trainer is previous_trainer
    assert training.next_datasets == []


def test_dataset_generation_service_commits_confirmed_replacement_once() -> None:
    service, study, training = _service()
    previous_dataset = object()
    previous_generator = object()
    previous_trainer = object()
    replacement_dataset = _Dataset(
        train=[True, True, False, False],
        val=[False, False, True, False],
        test=[False, False, False, True],
    )
    study.data_manager.datasets = [previous_dataset]
    study.data_manager.dataset_generator = previous_generator
    study.training_manager.trainer = previous_trainer
    training.next_datasets = [replacement_dataset]

    _message, payload = _expect_payload(
        service.handle_generate_dataset(
            GenerateDatasetCommand(
                replacement_mode=DatasetGenerationMode.REPLACE_EXISTING,
                confirmed=True,
            ),
        ),
    )

    assert study.data_manager.datasets == [replacement_dataset]
    assert study.data_manager.dataset_generator is not previous_generator
    assert study.training_manager.trainer is None
    assert payload["replaced_existing"] is True
    assert payload["previous_dataset_count"] == 1
    assert payload["previous_trainer_present"] is True
    assert payload["trainer_retired"] is True
    assert payload["split_audit"]["ok"] is True


def test_dataset_generation_service_clears_dataset_state() -> None:
    service, study, training = _service()
    study.data_manager.datasets = [object(), object()]
    study.training_manager.trainer = object()

    message, payload = _expect_payload(
        service.handle_clear_datasets(ClearDatasetsCommand(confirmed=True)),
    )

    assert message == "Datasets and dependent training plans cleared."
    assert payload == {
        "dataset_count_before": 2,
        "trainer_cleared": True,
    }
    assert training.cleaned is True
    assert training.force_update is True
