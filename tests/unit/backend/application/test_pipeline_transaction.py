from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from XBrainLab.backend.application.pipeline_transaction import PipelineStateTransaction
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyStatus,
    TrainingOutcomeState,
    TrainingPipelineMutationBoundary,
    TrainingReadBoundary,
    TrainingTerminalOutcome,
)


class _TrainingRuntime:
    def __init__(self) -> None:
        self.boundary = TrainingPipelineMutationBoundary(
            read_boundary=TrainingReadBoundary.no_trainer(),
            terminal_outcome=TrainingTerminalOutcome(
                state=TrainingOutcomeState.UNKNOWN,
                detail="No trainer is configured.",
            ),
            saliency_status=PostTrainingSaliencyStatus.idle(generation=3),
            saliency_work_active=False,
        )
        self.calls: list[tuple[str, Any]] = []
        self.startup_snapshot = object()

    def begin_raw_replacement(self) -> TrainingPipelineMutationBoundary:
        self.calls.append(("begin_raw", None))
        return self.boundary

    def begin_downstream_replacement(self) -> TrainingPipelineMutationBoundary:
        self.calls.append(("begin_downstream", None))
        return self.boundary

    def commit_pipeline_invalidation(
        self,
        expected: TrainingPipelineMutationBoundary,
    ) -> bool:
        self.calls.append(("commit", expected))
        return False

    def commit_pipeline_replacement(
        self,
        expected: TrainingPipelineMutationBoundary,
        *,
        publish,
    ) -> bool:
        self.calls.append(("commit_replacement", expected))
        publish()
        return False

    def capture_startup_rollback_snapshot(self) -> Any:
        self.calls.append(("capture_startup", None))
        return self.startup_snapshot

    def restore_startup_rollback_snapshot(self, snapshot: Any) -> None:
        self.calls.append(("restore_startup", snapshot))


def _study() -> SimpleNamespace:
    data_manager = SimpleNamespace(
        loaded_data_list=["raw"],
        backup_loaded_data_list=["backup"],
        preprocessed_data_list=["preprocessed"],
        epoch_data="epochs",
        datasets=["dataset"],
        dataset_generator="generator",
        dataset_locked=True,
    )
    return SimpleNamespace(
        data_manager=data_manager,
        training_manager=SimpleNamespace(trainer=object()),
    )


def test_pipeline_snapshot_and_restore_do_not_touch_training_manager() -> None:
    study = _study()
    runtime = _TrainingRuntime()
    transaction = PipelineStateTransaction(study, training_runtime=runtime)
    original_trainer = study.training_manager.trainer

    snapshot = transaction.capture()
    transaction.prepare_raw_replacement()
    study.training_manager.trainer = "changed outside data transaction"
    transaction.restore(snapshot)

    assert not hasattr(snapshot, "trainer")
    assert study.training_manager.trainer == "changed outside data transaction"
    assert study.training_manager.trainer is not original_trainer


def test_pipeline_transaction_delegates_typed_mutation_boundaries() -> None:
    runtime = _TrainingRuntime()
    transaction = PipelineStateTransaction(_study(), training_runtime=runtime)

    raw = transaction.begin_raw_replacement()
    downstream = transaction.begin_downstream_replacement()

    assert raw is runtime.boundary
    assert downstream is runtime.boundary
    assert transaction.commit_pipeline_invalidation(raw) is False
    assert runtime.calls == [
        ("begin_raw", None),
        ("begin_downstream", None),
        ("commit", runtime.boundary),
    ]


def test_pipeline_transaction_publishes_datasets_without_training_mutation() -> None:
    study = _study()
    runtime = _TrainingRuntime()
    transaction = PipelineStateTransaction(study, training_runtime=runtime)
    trainer = study.training_manager.trainer
    replacement = [object(), object()]
    generator = object()

    transaction.publish_datasets(replacement, generator)

    assert study.data_manager.datasets == replacement
    assert study.data_manager.dataset_generator is generator
    assert study.training_manager.trainer is trainer
    assert runtime.calls == []


def test_pipeline_transaction_commits_dataset_publication_through_runtime() -> None:
    study = _study()
    runtime = _TrainingRuntime()
    transaction = PipelineStateTransaction(study, training_runtime=runtime)
    replacement = [object(), object()]
    generator = object()

    candidate = replace(
        transaction.capture_dataset_publication(),
        datasets=tuple(replacement),
        dataset_generator=generator,
    )
    retired = transaction.commit_dataset_replacement(
        candidate,
        expected=runtime.boundary,
    )

    assert retired is False
    assert study.data_manager.datasets == replacement
    assert study.data_manager.dataset_generator is generator
    assert runtime.calls == [("commit_replacement", runtime.boundary)]


def test_pipeline_transaction_delegates_complete_training_startup_rollback() -> None:
    runtime = _TrainingRuntime()
    transaction = PipelineStateTransaction(_study(), training_runtime=runtime)

    snapshot = transaction.capture_training_startup_snapshot()
    transaction.restore_training_startup_snapshot(snapshot)

    assert snapshot is runtime.startup_snapshot
    assert runtime.calls == [
        ("capture_startup", None),
        ("restore_startup", runtime.startup_snapshot),
    ]


def test_dataset_publication_restore_rejects_stale_epoch_before_any_mutation() -> None:
    study = _study()
    runtime = _TrainingRuntime()
    transaction = PipelineStateTransaction(study, training_runtime=runtime)
    snapshot = transaction.capture_dataset_publication()
    newer_dataset = object()
    newer_generator = object()
    newer_epoch = object()
    study.data_manager.datasets = [newer_dataset]
    study.data_manager.dataset_generator = newer_generator
    study.data_manager.dataset_locked = False
    study.data_manager.epoch_data = newer_epoch

    with pytest.raises(RuntimeError, match="Epoch data changed"):
        transaction.restore_dataset_publication(snapshot)

    assert study.data_manager.datasets == [newer_dataset]
    assert study.data_manager.dataset_generator is newer_generator
    assert study.data_manager.dataset_locked is False
    assert study.data_manager.epoch_data is newer_epoch
