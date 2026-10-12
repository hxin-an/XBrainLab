"""Application boundary: interpretation preparation behavior."""

from __future__ import annotations

import os
import time
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.backend.application.application_test_support import (
    THREAD_WATCHDOG_SECONDS,
    _raw_mock,
    _use_test_raw_factory,
)
from tests.unit.backend.application.preprocess_test_support import (
    _minimal_raw,
)
from XBrainLab.backend.application import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationService,
    ApplyInterpretationCommand,
    ChangedState,
    CommandResult,
    ErrorType,
    NewSessionCommand,
    PreviewInterpretationCommand,
    ReviewInterpretationCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    UpdateMetadataCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.application.owned_work import (
    OwnedWorkPhase,
)
from XBrainLab.backend.exceptions import StaleTrainingPipelineMutationError
from XBrainLab.backend.load_data.raw import Raw
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import (
    Trainer,
)


def test_apply_interpretation_rolls_back_when_metadata_apply_raises(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "metadata_failure"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"scan-only fixture")
    study = Study()
    manager = study.data_manager
    old_raw = _raw_mock()
    old_raw.get_filepath.return_value = "/previous/active.fif"
    old_backup = _raw_mock()
    old_preprocessed = _raw_mock()
    old_preprocessed.get_preprocess_history.return_value = []
    manager.loaded_data_list = [old_raw]
    manager.backup_loaded_data_list = [old_backup]
    manager.preprocessed_data_list = [old_preprocessed]
    service = ApplicationService(study)
    imported_raw = _raw_mock()
    imported_raw.get_filename.return_value = eeg_path.name
    imported_raw.get_filepath.return_value = str(eeg_path)

    interpretation = service.interpretation
    _use_test_raw_factory(service, cast(Raw, imported_raw))
    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "metadata_overrides": {
                    eeg_path.name: {
                        "subject": "subject01",
                        "session": "session-01",
                        "task": "rest",
                        "run": "1",
                    },
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    service.dataset.notify = MagicMock(side_effect=RuntimeError("notify failed"))

    with patch.object(
        type(interpretation.apply_service),
        "apply_candidate_metadata_to_loaded_data",
        side_effect=RuntimeError("metadata write failed"),
    ):
        result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert result.failed is True
    assert result.error_type == ErrorType.INTERNAL
    assert "metadata write failed" in result.message
    assert manager.loaded_data_list == [old_raw]
    assert manager.backup_loaded_data_list == [old_backup]
    assert manager.preprocessed_data_list == [old_preprocessed]
    assert result.state.interpretation.has_applied_interpretation is False


def test_apply_retirement_failure_restores_pipeline_and_training_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_dir = tmp_path / "apply-retirement-failure"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"reviewed EEG identity")
    study = Study()
    previous_path = tmp_path / "previous.fif"
    previous_path.write_bytes(b"previous reviewed EEG identity")
    service = ApplicationService(study)
    _use_test_raw_factory(
        service,
        {
            str(previous_path): _minimal_raw(previous_path),
            str(eeg_path): _minimal_raw(eeg_path),
        },
    )
    assert service.execute(ScanSourceCommand(source_path=str(previous_path))).ok
    assert service.execute(
        PreviewInterpretationCommand(choices={"skip_labels": True})
    ).ok
    assert service.execute(ValidateInterpretationCommand()).ok
    applied = service.execute(ApplyInterpretationCommand(confirmed=True))
    assert applied.ok
    recipe_path = tmp_path / "previous-recipe.json"
    saved = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path))
    )
    assert saved.ok
    interpretation = service.interpretation
    previous_recipe = interpretation.state.resolve_recipe(None).to_dict()
    previous_interpretation_id = applied.state.interpretation.latest_interpretation_id
    trainer = Trainer([])
    history_holder = MagicMock(name="completed_apply_training_history")
    trainer.training_plan_holders = cast(Any, [history_holder])
    study.training_manager.trainer = trainer
    # This fixture injects completed history directly; publish it before review.
    service.get_state()
    assert service.execute(ScanSourceCommand(source_path=str(source_dir))).ok
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg_path)],
                "skip_labels": True,
            }
        )
    )
    candidate_id = preview.diagnostics["candidate"]["candidate_id"]
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok
    pipeline_before = service.pipeline_transaction.capture()
    publication_before = service.get_view_publication()
    # Exercise the transaction invariant independently of today's capability
    # and raw-admission policies, which both block replacement after trainer
    # creation before the prepared commit contract is reached.
    monkeypatch.setattr(service, "_ensure_command_allowed", lambda *_args: None)
    monkeypatch.setattr(
        service.pipeline_transaction,
        "begin_raw_replacement",
        service.pipeline_transaction.begin_downstream_replacement,
    )

    def _mutate_training_then_fail(expected, *, publish) -> bool:
        del expected
        publish()
        assert (
            interpretation.state.resolve_applied_interpretation().interpretation_id
            != previous_interpretation_id
        )
        trainer.clear_history()
        study.training_manager.trainer = None
        raise RuntimeError("apply trainer retirement failed after cleanup")

    monkeypatch.setattr(
        study.training_manager,
        "commit_pipeline_replacement",
        _mutate_training_then_fail,
    )

    result = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )

    assert result.failed
    assert result.error_type is ErrorType.INTERNAL
    assert "apply trainer retirement failed after cleanup" in result.message
    assert service.pipeline_transaction.capture() == pipeline_before
    assert study.training_manager.trainer is trainer
    assert trainer.get_training_plan_holders() == [history_holder]
    assert result.state.interpretation.has_applied_interpretation is True
    assert result.state.interpretation.latest_interpretation_id == (
        previous_interpretation_id
    )
    assert result.state.interpretation.latest_recipe_id == (
        saved.state.interpretation.latest_recipe_id
    )
    assert result.state.interpretation.recipe_path == str(recipe_path)
    assert interpretation.state.resolve_recipe(None).to_dict() == previous_recipe
    publication_after = service.get_view_publication()
    assert (
        replace(
            publication_after.state.training,
            read_generation=publication_before.state.training.read_generation,
        )
        == publication_before.state.training
    )
    assert publication_after.training_history == publication_before.training_history


def test_apply_stale_training_boundary_preserves_newer_training_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_dir = tmp_path / "apply-stale-training"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"reviewed EEG identity")
    study = Study()
    previous_raw = _minimal_raw(tmp_path / "previous.fif")
    study.set_loaded_data_list([previous_raw], force_update=True)
    previous_trainer = Trainer([])
    replacement_trainer = Trainer([])
    study.training_manager.trainer = previous_trainer
    service = ApplicationService(study)
    _use_test_raw_factory(service, _minimal_raw(eeg_path))
    assert service.execute(ScanSourceCommand(source_path=str(source_dir))).ok
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg_path)],
                "skip_labels": True,
            }
        )
    )
    candidate_id = preview.diagnostics["candidate"]["candidate_id"]
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok
    pipeline_before = service.pipeline_transaction.capture()
    # Exercise the transaction invariant independently of today's capability
    # and raw-admission policies, which both block replacement after trainer
    # creation before the prepared commit contract is reached.
    monkeypatch.setattr(service, "_ensure_command_allowed", lambda *_args: None)
    monkeypatch.setattr(
        service.pipeline_transaction,
        "begin_raw_replacement",
        service.pipeline_transaction.begin_downstream_replacement,
    )
    restore_training = MagicMock(
        side_effect=AssertionError("stale boundary must not restore old training"),
    )
    monkeypatch.setattr(
        study.training_manager,
        "restore_startup_rollback_snapshot",
        restore_training,
    )

    def _replace_training_then_reject(expected, *, publish) -> bool:
        del expected, publish
        study.training_manager.trainer = replacement_trainer
        raise StaleTrainingPipelineMutationError

    monkeypatch.setattr(
        study.training_manager,
        "commit_pipeline_replacement",
        _replace_training_then_reject,
    )

    result = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )

    assert result.failed
    assert result.error_type is ErrorType.PRECONDITION
    assert result.diagnostics["code"] == "training_pipeline_boundary_changed"
    assert service.pipeline_transaction.capture() == pipeline_before
    assert study.training_manager.trainer is replacement_trainer
    assert result.state.training.has_trainer is True
    assert result.state.interpretation.has_applied_interpretation is False
    restore_training.assert_not_called()


def test_apply_base_exception_survives_best_effort_rollback_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ApplyCommitSentinel(BaseException):
        pass

    source_dir = tmp_path / "apply-base-exception"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"reviewed EEG identity")
    study = Study()
    previous_raw = _minimal_raw(tmp_path / "previous.fif")
    study.set_loaded_data_list([previous_raw], force_update=True)
    service = ApplicationService(study)
    _use_test_raw_factory(service, _minimal_raw(eeg_path))
    assert service.execute(ScanSourceCommand(source_path=str(source_dir))).ok
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg_path)],
                "skip_labels": True,
            }
        )
    )
    candidate_id = preview.diagnostics["candidate"]["candidate_id"]
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok
    pipeline_before = service.pipeline_transaction.capture()
    restore_training = MagicMock(
        side_effect=RuntimeError("training rollback failed"),
    )
    monkeypatch.setattr(
        study.training_manager,
        "restore_startup_rollback_snapshot",
        restore_training,
    )
    sentinel = _ApplyCommitSentinel()

    def _publish_then_interrupt(expected, *, publish) -> bool:
        del expected
        publish()
        raise sentinel

    monkeypatch.setattr(
        study.training_manager,
        "commit_pipeline_replacement",
        _publish_then_interrupt,
    )

    with pytest.raises(_ApplyCommitSentinel) as raised:
        service.execute(
            ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
        )

    assert raised.value is sentinel
    restore_training.assert_called_once()
    assert service.pipeline_transaction.capture() == pipeline_before
    assert service.get_state().interpretation.has_applied_interpretation is False


def test_apply_interpretation_cancel_preserves_real_study_and_can_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_dir = tmp_path / "reviewed"
    source_dir.mkdir()
    recording_paths = [
        source_dir / "subject01_run1.fif",
        source_dir / "subject01_run2.fif",
    ]
    for path in recording_paths:
        path.write_bytes(b"reviewed EEG identity")

    old_path = tmp_path / "previous.fif"
    old_path.write_bytes(b"previous EEG identity")
    old_raw = _minimal_raw(old_path)
    study = Study()
    study.set_loaded_data_list([old_raw], force_update=True)
    service = ApplicationService(study)
    publications = []
    service.subscribe(
        APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
        publications.append,
    )

    assert service.execute(ScanSourceCommand(source_path=str(source_dir))).ok
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(path) for path in recording_paths],
                "skip_labels": True,
            },
        )
    )
    assert preview.ok
    candidate_id = preview.diagnostics["candidate"]["candidate_id"]
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok
    before_apply = service.get_view_publication()
    assert service._last_error is None

    second_load_started = Event()
    release_second_load = Event()
    load_count = 0

    class _BlockingFactory:
        @staticmethod
        def load(path: str) -> Raw:
            nonlocal load_count
            load_count += 1
            if load_count == 2:
                second_load_started.set()
                assert release_second_load.wait(timeout=THREAD_WATCHDOG_SECONDS)
            return _minimal_raw(Path(path))

    service.dataset._raw_factory_provider = lambda: _BlockingFactory
    command = ApplyInterpretationCommand(
        candidate_id=candidate_id,
        confirmed=True,
    )
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="apply-interpretation-cancel",
    )
    publications_before_apply = len(publications)

    worker.start()
    assert second_load_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    progress_during_second_load = service.get_owned_operation(operation.operation_id)
    command_lock_available = service._command_lock.acquire(blocking=False)
    if command_lock_available:
        service._command_lock.release()
    started_at = time.monotonic()
    cancelled = service.cancel_owned_operation(operation.operation_id)
    cancel_elapsed = time.monotonic() - started_at
    release_second_load.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert command_lock_available is True
    assert cancelled is True
    assert cancel_elapsed < 0.1
    assert progress_during_second_load.stage == "Loading EEG recording 2 of 2"
    assert progress_during_second_load.completed == 1
    assert progress_during_second_load.total is None
    assert progress_during_second_load.indeterminate is True
    assert len(results) == 1
    cancelled_result = results[0]
    assert cancelled_result.failed
    assert cancelled_result.error_type is ErrorType.CANCELLED
    assert cancelled_result.recoverable is True
    assert cancelled_result.diagnostics["operation_cancelled"] is True
    assert cancelled_result.diagnostics["state_preserved"] is True
    assert cancelled_result.diagnostics["control_flow_outcome"] is True
    assert cancelled_result.changed_state == ChangedState()
    assert cancelled_result.state == before_apply.state
    assert service._last_error is None
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.CANCELLED
    )
    assert study.data_manager.loaded_data_list == [old_raw]
    assert study.data_manager.preprocessed_data_list == [old_raw]
    assert cancelled_result.state.interpretation.has_applied_interpretation is False
    assert cancelled_result.state.interpretation.latest_candidate_id == candidate_id
    assert cancelled_result.state.interpretation.validation_decision is not None
    cancelled_publication = service.get_view_publication()
    assert cancelled_publication == before_apply
    assert all(
        not publication.state.interpretation.has_applied_interpretation
        for publication in publications[publications_before_apply:]
    )

    interpretation = service.interpretation
    original_label_verification = interpretation._ensure_label_apply_succeeded
    ready_to_commit = Event()
    release_commit_admission = Event()

    def _block_before_commit(candidate, label_apply):
        original_label_verification(candidate, label_apply)
        ready_to_commit.set()
        assert release_commit_admission.wait(timeout=THREAD_WATCHDOG_SECONDS)

    monkeypatch.setattr(
        interpretation,
        "_ensure_label_apply_succeeded",
        _block_before_commit,
    )
    commit_operation = service.begin_owned_operation(command)
    commit_results: list[CommandResult] = []
    commit_worker = Thread(
        target=lambda: commit_results.append(
            service.execute(command, operation_id=commit_operation.operation_id)
        ),
        name="apply-interpretation-commit-admission-cancel",
    )

    commit_worker.start()
    assert ready_to_commit.wait(timeout=THREAD_WATCHDOG_SECONDS)
    assert study.data_manager.loaded_data_list == [old_raw]
    assert service.cancel_owned_operation(commit_operation.operation_id) is True
    release_commit_admission.set()
    commit_worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not commit_worker.is_alive()
    assert len(commit_results) == 1
    assert commit_results[0].error_type is ErrorType.CANCELLED
    assert commit_results[0].changed_state == ChangedState()
    assert commit_results[0].state == before_apply.state
    assert service._last_error is None
    assert service.get_owned_operation(commit_operation.operation_id).phase is (
        OwnedWorkPhase.CANCELLED
    )
    assert study.data_manager.loaded_data_list == [old_raw]
    assert study.data_manager.preprocessed_data_list == [old_raw]
    assert commit_results[0].state.interpretation.has_applied_interpretation is False
    commit_cancelled_publication = service.get_view_publication()
    assert commit_cancelled_publication.generation == before_apply.generation
    assert commit_cancelled_publication.state == before_apply.state
    assert all(
        not publication.state.interpretation.has_applied_interpretation
        for publication in publications[publications_before_apply:]
    )

    monkeypatch.setattr(
        interpretation,
        "_ensure_label_apply_succeeded",
        original_label_verification,
    )
    retry_operation = service.begin_owned_operation(command)
    retried = service.execute(
        command,
        operation_id=retry_operation.operation_id,
    )

    assert retried.ok
    assert retried.state.interpretation.has_applied_interpretation is True
    assert service.get_owned_operation(retry_operation.operation_id).phase is (
        OwnedWorkPhase.COMPLETED
    )
    assert [raw.get_filepath() for raw in study.data_manager.loaded_data_list] == [
        str(path) for path in recording_paths
    ]


def test_apply_interpretation_rejects_preparation_staled_by_concurrent_mutation(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "reviewed"
    source_dir.mkdir()
    recording_paths = [
        source_dir / "subject01_run1.fif",
        source_dir / "subject01_run2.fif",
    ]
    for path in recording_paths:
        path.write_bytes(b"reviewed EEG identity")
    old_path = tmp_path / "previous.fif"
    old_path.write_bytes(b"previous EEG identity")
    old_raw = _minimal_raw(old_path)
    study = Study()
    study.set_loaded_data_list([old_raw], force_update=True)
    service = ApplicationService(study)

    assert service.execute(ScanSourceCommand(source_path=str(source_dir))).ok
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(path) for path in recording_paths],
                "skip_labels": True,
            },
        )
    )
    assert preview.ok
    candidate_id = preview.diagnostics["candidate"]["candidate_id"]
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok

    second_load_started = Event()
    release_second_load = Event()
    load_count = 0

    class _BlockingFactory:
        @staticmethod
        def load(path: str) -> Raw:
            nonlocal load_count
            load_count += 1
            if load_count == 2:
                second_load_started.set()
                assert release_second_load.wait(timeout=THREAD_WATCHDOG_SECONDS)
            return _minimal_raw(Path(path))

    service.dataset._raw_factory_provider = lambda: _BlockingFactory
    command = ApplyInterpretationCommand(
        candidate_id=candidate_id,
        confirmed=True,
    )
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="apply-interpretation-stale-prepare",
    )

    worker.start()
    assert second_load_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    assert service._command_lock.acquire(blocking=False) is True
    service._command_lock.release()
    concurrent = service.execute(UpdateMetadataCommand(index=0, subject="S99"))
    assert concurrent.ok
    concurrent_raw = study.data_manager.loaded_data_list[0]
    assert concurrent_raw.get_subject_name() == "S99"
    release_second_load.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert len(results) == 1
    stale = results[0]
    assert stale.failed
    assert stale.error_type is ErrorType.PRECONDITION
    assert stale.recoverable is True
    assert stale.diagnostics["stale_prepared_interpretation_apply"] is True
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.FAILED
    )
    assert study.data_manager.loaded_data_list == [concurrent_raw]
    assert concurrent_raw.get_subject_name() == "S99"
    assert stale.state.interpretation.has_applied_interpretation is False


@pytest.mark.parametrize("blocked_phase", ["resource_preflight", "label_admission"])
def test_apply_resource_admission_runs_without_holding_command_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    blocked_phase: str,
) -> None:
    source_dir = tmp_path / "reviewed"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"reviewed EEG identity")
    service = ApplicationService(Study())
    _use_test_raw_factory(service)
    assert service.execute(ScanSourceCommand(source_path=str(source_dir))).ok
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={"selected_eeg_files": [str(eeg_path)], "skip_labels": True}
        )
    )
    candidate_id = preview.diagnostics["candidate"]["candidate_id"]
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok
    from XBrainLab.backend.application import data_interpretation_service

    admission_started = Event()
    release_admission = Event()

    if blocked_phase == "resource_preflight":
        original_preflight = data_interpretation_service.check_import_resource_preflight
        monkeypatch.setattr(
            data_interpretation_service,
            "available_ram_bytes",
            lambda: 0,
        )

        def _blocking_preflight(paths):
            admission_started.set()
            assert release_admission.wait(timeout=THREAD_WATCHDOG_SECONDS)
            return original_preflight(paths)

        monkeypatch.setattr(
            data_interpretation_service,
            "check_import_resource_preflight",
            _blocking_preflight,
        )
    else:
        interpretation = service.interpretation
        original_label_admission = interpretation._admitted_reviewed_label_resources

        def _blocking_label_admission(candidate, preflight):
            admission_started.set()
            assert release_admission.wait(timeout=THREAD_WATCHDOG_SECONDS)
            return original_label_admission(candidate, preflight)

        monkeypatch.setattr(
            interpretation,
            "_admitted_reviewed_label_resources",
            _blocking_label_admission,
        )
    command = ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="apply-interpretation-resource-preflight",
    )

    worker.start()
    assert admission_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    assert service._command_lock.acquire(blocking=False) is True
    service._command_lock.release()
    release_admission.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert len(results) == 1
    assert results[0].ok


def test_apply_commit_rejects_same_value_interpretation_revision_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_dir = tmp_path / "reviewed"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"reviewed EEG identity")
    old_path = tmp_path / "previous.fif"
    old_path.write_bytes(b"previous EEG identity")
    old_raw = _minimal_raw(old_path)
    study = Study()
    study.set_loaded_data_list([old_raw], force_update=True)
    service = ApplicationService(study)
    _use_test_raw_factory(service)
    assert service.execute(ScanSourceCommand(source_path=str(source_dir))).ok
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={"selected_eeg_files": [str(eeg_path)], "skip_labels": True}
        )
    )
    candidate_id = preview.diagnostics["candidate"]["candidate_id"]
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok
    interpretation = service.interpretation
    original_prepare = interpretation.prepare_apply_interpretation

    def _mutate_same_value_after_prepare(plan):
        prepared = original_prepare(plan)
        decision = interpretation.state.resolve_validation_decision(candidate_id)
        assert decision is not None
        interpretation.state.record_validation(candidate_id, decision)
        return prepared

    monkeypatch.setattr(
        interpretation,
        "prepare_apply_interpretation",
        _mutate_same_value_after_prepare,
    )

    result = service.execute(
        ApplyInterpretationCommand(candidate_id=candidate_id, confirmed=True)
    )

    assert result.failed
    assert result.error_type is ErrorType.PRECONDITION
    assert result.diagnostics["stale_prepared_interpretation_apply"] is True
    assert study.data_manager.loaded_data_list == [old_raw]
    assert result.state.interpretation.has_applied_interpretation is False


@pytest.mark.parametrize("failure_mode", ["cancel", "load_error"])
def test_detached_apply_failure_preserves_concurrent_publication_truth(
    tmp_path: Path,
    failure_mode: str,
) -> None:
    source_dir = tmp_path / "reviewed"
    source_dir.mkdir()
    recording_paths = [
        source_dir / "subject01_run1.fif",
        source_dir / "subject01_run2.fif",
    ]
    for path in recording_paths:
        path.write_bytes(b"reviewed EEG identity")
    old_path = tmp_path / "previous.fif"
    old_path.write_bytes(b"previous EEG identity")
    old_raw = _minimal_raw(old_path)
    study = Study()
    study.set_loaded_data_list([old_raw], force_update=True)
    service = ApplicationService(study)

    assert service.execute(ScanSourceCommand(source_path=str(source_dir))).ok
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(path) for path in recording_paths],
                "skip_labels": True,
            },
        )
    )
    candidate_id = preview.diagnostics["candidate"]["candidate_id"]
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok

    second_load_started = Event()
    release_second_load = Event()
    load_count = 0

    class _BlockingFactory:
        @staticmethod
        def load(path: str) -> Raw:
            nonlocal load_count
            load_count += 1
            if load_count == 2:
                second_load_started.set()
                assert release_second_load.wait(timeout=THREAD_WATCHDOG_SECONDS)
                if failure_mode == "load_error":
                    raise RuntimeError("detached loader failed")
            return _minimal_raw(Path(path))

    service.dataset._raw_factory_provider = lambda: _BlockingFactory
    command = ApplyInterpretationCommand(
        candidate_id=candidate_id,
        confirmed=True,
    )
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name=f"apply-interpretation-{failure_mode}-after-concurrent-command",
    )

    worker.start()
    assert second_load_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    concurrent = service.execute(UpdateMetadataCommand(index=0, subject="S99"))
    assert concurrent.ok
    concurrent_publication = service.get_view_publication()
    if failure_mode == "cancel":
        assert service.cancel_owned_operation(operation.operation_id) is True
    release_second_load.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert len(results) == 1
    failed = results[0]
    assert failed.failed
    assert failed.error_type is (
        ErrorType.CANCELLED if failure_mode == "cancel" else ErrorType.RUNTIME
    )
    assert failed.state == concurrent_publication.state
    assert failed.changed_state == ChangedState()
    assert failed.diagnostics["detached_prepare_failed_after_concurrent_change"]
    assert failed.diagnostics["state_preserved"] is True
    assert service.get_view_publication() == concurrent_publication
    assert service._last_error is None
    assert study.data_manager.loaded_data_list[0].get_subject_name() == "S99"
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.CANCELLED if failure_mode == "cancel" else OwnedWorkPhase.FAILED
    )


@pytest.mark.parametrize(
    "command_factory",
    [
        lambda path: ScanSourceCommand(source_path=str(path)),
        lambda path: ReviewInterpretationCommand(
            source_path=str(path),
            choices={"skip_labels": True},
        ),
    ],
    ids=("scan", "review"),
)
def test_import_discovery_heavy_prepare_cancel_preserves_and_can_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command_factory,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "subject01_run1.fif").write_bytes(b"scan fixture one")
    (source / "subject01_run2.fif").write_bytes(b"scan fixture two")
    service = ApplicationService(Study())
    before = service.get_view_publication()
    scan_started = Event()
    release_scan = Event()
    should_block = Event()
    should_block.set()
    from XBrainLab.backend.application import data_interpretation_service

    original_scan = data_interpretation_service.scan_source_path

    def _blocking_scan(*args, **kwargs):
        if should_block.is_set():
            scan_started.set()
            assert release_scan.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return original_scan(*args, **kwargs)

    monkeypatch.setattr(
        data_interpretation_service,
        "scan_source_path",
        _blocking_scan,
    )
    command = command_factory(source)
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="import-discovery-cancel",
    )

    worker.start()
    assert scan_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    command_lock_available = service._command_lock.acquire(blocking=False)
    if command_lock_available:
        service._command_lock.release()
    started_at = time.monotonic()
    cancelled = service.cancel_owned_operation(operation.operation_id)
    cancel_elapsed = time.monotonic() - started_at
    release_scan.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert command_lock_available is True
    assert cancelled is True
    assert cancel_elapsed < 0.1
    assert len(results) == 1
    cancelled_result = results[0]
    assert cancelled_result.failed
    assert cancelled_result.error_type is ErrorType.CANCELLED
    assert cancelled_result.changed_state == ChangedState()
    assert cancelled_result.state == before.state
    assert cancelled_result.diagnostics["state_preserved"] is True
    assert service._last_error is None
    assert service.get_view_publication() == before
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.CANCELLED
    )
    assert service.get_state().interpretation == before.state.interpretation

    should_block.clear()
    retry = service.begin_owned_operation(command)
    retried = service.execute(command, operation_id=retry.operation_id)

    assert retried.ok
    assert service.get_owned_operation(retry.operation_id).phase is (
        OwnedWorkPhase.COMPLETED
    )
    assert retried.state.interpretation.has_scan_result is True
    if isinstance(command, ReviewInterpretationCommand):
        assert retried.state.interpretation.has_candidate is True
        assert retried.state.interpretation.has_validation_decision is True


@pytest.mark.parametrize(
    "command_factory",
    [
        lambda path: ScanSourceCommand(source_path=str(path)),
        lambda path: ReviewInterpretationCommand(
            source_path=str(path),
            choices={"skip_labels": True},
        ),
    ],
    ids=("scan", "review"),
)
def test_import_discovery_rejects_prepare_staled_by_concurrent_session_reset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command_factory,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "subject01_run1.fif").write_bytes(b"scan fixture")
    service = ApplicationService(Study())
    scan_started = Event()
    release_scan = Event()
    from XBrainLab.backend.application import data_interpretation_service

    original_scan = data_interpretation_service.scan_source_path

    def _blocking_scan(*args, **kwargs):
        scan_started.set()
        assert release_scan.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return original_scan(*args, **kwargs)

    monkeypatch.setattr(
        data_interpretation_service,
        "scan_source_path",
        _blocking_scan,
    )
    command = command_factory(source)
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="interpretation-review-stale",
    )

    worker.start()
    assert scan_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    assert service._command_lock.acquire(blocking=False) is True
    service._command_lock.release()
    concurrent = service.execute(NewSessionCommand(confirmed=True))
    assert concurrent.ok
    release_scan.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert len(results) == 1
    stale = results[0]
    assert stale.failed
    assert stale.error_type is ErrorType.PRECONDITION
    assert stale.diagnostics["stale_prepared_interpretation_discovery"] is True
    assert stale.changed_state == ChangedState()
    assert stale.state == concurrent.state
    assert stale.state.interpretation.has_scan_result is False
    assert stale.state.interpretation.has_candidate is False
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.FAILED
    )


def test_import_discovery_merges_unrelated_concurrent_metadata_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_path = tmp_path / "active.fif"
    active_path.write_bytes(b"active fixture")
    study = Study()
    study.set_loaded_data_list([_minimal_raw(active_path)], force_update=True)
    service = ApplicationService(study)
    source = tmp_path / "source"
    source.mkdir()
    (source / "subject01_run1.fif").write_bytes(b"scan fixture")
    scan_started = Event()
    release_scan = Event()
    from XBrainLab.backend.application import data_interpretation_service

    original_scan = data_interpretation_service.scan_source_path

    def _blocking_scan(*args, **kwargs):
        scan_started.set()
        assert release_scan.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return original_scan(*args, **kwargs)

    monkeypatch.setattr(
        data_interpretation_service,
        "scan_source_path",
        _blocking_scan,
    )
    command = ScanSourceCommand(source_path=str(source))
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="interpretation-scan-concurrent-metadata",
    )

    worker.start()
    assert scan_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    concurrent = service.execute(UpdateMetadataCommand(index=0, subject="S99"))
    assert concurrent.ok
    release_scan.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert len(results) == 1
    merged = results[0]
    assert merged.ok
    assert merged.state.raw.metadata[0]["subject"] == "S99"
    assert merged.state.interpretation.has_scan_result is True
    assert study.data_manager.loaded_data_list[0].get_subject_name() == "S99"
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.COMPLETED
    )


@pytest.mark.parametrize("command_kind", ["preview", "validate"])
def test_interpretation_review_heavy_prepare_cancel_preserves_and_can_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command_kind: str,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "subject01_run1.fif").write_bytes(b"review fixture")
    service = ApplicationService(Study())
    assert service.execute(ScanSourceCommand(source_path=str(source))).ok
    if command_kind == "preview":
        command = PreviewInterpretationCommand(choices={"skip_labels": True})
        target_name = "build_interpretation_candidate"
    else:
        preview = service.execute(
            PreviewInterpretationCommand(choices={"skip_labels": True})
        )
        assert preview.ok
        command = ValidateInterpretationCommand(
            candidate_id=preview.diagnostics["candidate"]["candidate_id"]
        )
        target_name = "validate_interpretation_candidate"
    before = service.get_view_publication()
    processing_started = Event()
    release_processing = Event()
    should_block = Event()
    should_block.set()
    from XBrainLab.backend.application import data_interpretation_service

    original = getattr(data_interpretation_service, target_name)

    def _blocking_review_work(*args, **kwargs):
        if should_block.is_set():
            processing_started.set()
            assert release_processing.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return original(*args, **kwargs)

    monkeypatch.setattr(
        data_interpretation_service,
        target_name,
        _blocking_review_work,
    )
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name=f"interpretation-{command_kind}-cancel",
    )

    worker.start()
    assert processing_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    command_lock_available = service._command_lock.acquire(blocking=False)
    if command_lock_available:
        service._command_lock.release()
    started_at = time.monotonic()
    cancelled = service.cancel_owned_operation(operation.operation_id)
    cancel_elapsed = time.monotonic() - started_at
    release_processing.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert command_lock_available is True
    assert operation.cancellable is True
    assert cancelled is True
    assert cancel_elapsed < 0.1
    assert len(results) == 1
    cancelled_result = results[0]
    assert cancelled_result.failed
    assert cancelled_result.error_type is ErrorType.CANCELLED
    assert cancelled_result.changed_state == ChangedState()
    assert cancelled_result.state == before.state
    assert cancelled_result.diagnostics["state_preserved"] is True
    assert service._last_error is None
    assert service.get_view_publication() == before
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.CANCELLED
    )

    should_block.clear()
    retry = service.begin_owned_operation(command)
    retried = service.execute(command, operation_id=retry.operation_id)

    assert retried.ok
    assert service.get_owned_operation(retry.operation_id).phase is (
        OwnedWorkPhase.COMPLETED
    )
    assert retried.state.interpretation.has_candidate is True
    assert retried.state.interpretation.has_validation_decision is (
        command_kind == "validate"
    )


@pytest.mark.parametrize("command_kind", ["preview", "validate"])
def test_interpretation_review_rejects_prepare_staled_by_concurrent_reset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command_kind: str,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "subject01_run1.fif").write_bytes(b"review fixture")
    service = ApplicationService(Study())
    assert service.execute(ScanSourceCommand(source_path=str(source))).ok
    if command_kind == "preview":
        command = PreviewInterpretationCommand(choices={"skip_labels": True})
        target_name = "build_interpretation_candidate"
    else:
        preview = service.execute(
            PreviewInterpretationCommand(choices={"skip_labels": True})
        )
        assert preview.ok
        command = ValidateInterpretationCommand(
            candidate_id=preview.diagnostics["candidate"]["candidate_id"]
        )
        target_name = "validate_interpretation_candidate"
    processing_started = Event()
    release_processing = Event()
    from XBrainLab.backend.application import data_interpretation_service

    original = getattr(data_interpretation_service, target_name)

    def _blocking_review_work(*args, **kwargs):
        processing_started.set()
        assert release_processing.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return original(*args, **kwargs)

    monkeypatch.setattr(
        data_interpretation_service,
        target_name,
        _blocking_review_work,
    )
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name=f"interpretation-{command_kind}-stale",
    )

    worker.start()
    assert processing_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    command_lock_available = service._command_lock.acquire(blocking=False)
    if command_lock_available:
        service._command_lock.release()
    if not command_lock_available:
        release_processing.set()
        worker.join(timeout=THREAD_WATCHDOG_SECONDS)
        pytest.fail("review preparation retained the shared command lock")
    concurrent = service.execute(NewSessionCommand(confirmed=True))
    assert concurrent.ok
    release_processing.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert len(results) == 1
    stale = results[0]
    assert stale.failed
    assert stale.error_type is ErrorType.PRECONDITION
    assert stale.diagnostics["stale_prepared_interpretation_discovery"] is True
    assert stale.changed_state == ChangedState()
    assert stale.state == concurrent.state
    assert stale.state.interpretation.has_scan_result is False
    assert stale.state.interpretation.has_candidate is False
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.FAILED
    )


def test_interpretation_review_failure_after_concurrent_reset_keeps_current_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "subject01_run1.fif").write_bytes(b"review fixture")
    service = ApplicationService(Study())
    processing_started = Event()
    release_processing = Event()
    from XBrainLab.backend.application import data_interpretation_service

    original_scan = data_interpretation_service.scan_source_path

    def _failing_scan(*args, **kwargs):
        processing_started.set()
        assert release_processing.wait(timeout=THREAD_WATCHDOG_SECONDS)
        original_scan(*args, **kwargs)
        raise RuntimeError("detached review failed")

    monkeypatch.setattr(
        data_interpretation_service,
        "scan_source_path",
        _failing_scan,
    )
    command = ReviewInterpretationCommand(
        source_path=str(source),
        choices={"skip_labels": True},
    )
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="interpretation-review-failure-after-reset",
    )

    worker.start()
    assert processing_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    concurrent = service.execute(NewSessionCommand(confirmed=True))
    assert concurrent.ok
    concurrent_publication = service.get_view_publication()
    release_processing.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert len(results) == 1
    failed = results[0]
    assert failed.failed
    assert failed.error_type is ErrorType.INTERNAL
    assert failed.state == concurrent.state
    assert failed.changed_state == ChangedState()
    assert failed.diagnostics["detached_prepare_failed_after_concurrent_change"]
    assert failed.diagnostics["state_preserved"] is True
    assert service.get_view_publication() == concurrent_publication
    assert service._last_error is None
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.FAILED
    )


def test_validate_cancel_after_commit_admission_is_rejected_and_success_publishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "subject01_run1.fif").write_bytes(b"review fixture")
    service = ApplicationService(Study())
    assert service.execute(ScanSourceCommand(source_path=str(source))).ok
    preview = service.execute(
        PreviewInterpretationCommand(choices={"skip_labels": True})
    )
    assert preview.ok
    command = ValidateInterpretationCommand(
        candidate_id=preview.diagnostics["candidate"]["candidate_id"]
    )
    interpretation = service.interpretation
    original_publish = interpretation.state.publish_staged_session_state
    commit_started = Event()
    release_commit = Event()

    def _blocking_publish(checkpoint) -> None:
        commit_started.set()
        assert release_commit.wait(timeout=THREAD_WATCHDOG_SECONDS)
        original_publish(checkpoint)

    monkeypatch.setattr(
        interpretation.state,
        "publish_staged_session_state",
        _blocking_publish,
    )
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="interpretation-validate-commit-admitted",
    )

    worker.start()
    assert commit_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    assert service.cancel_owned_operation(operation.operation_id) is False
    release_commit.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert len(results) == 1
    committed = results[0]
    assert committed.ok
    assert committed.state.interpretation.has_validation_decision is True
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.COMPLETED
    )


def test_apply_interpretation_rehashes_content_before_short_commit_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from XBrainLab.backend.application.data_interpretation_apply_preparation import (
        SourceFileBoundary,
    )

    source_dir = tmp_path / "reviewed"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    reviewed_bytes = b"reviewed EEG identity a"
    rewritten_bytes = b"reviewed EEG identity b"
    assert len(reviewed_bytes) == len(rewritten_bytes)
    eeg_path.write_bytes(reviewed_bytes)
    old_path = tmp_path / "previous.fif"
    old_path.write_bytes(b"previous EEG identity")
    old_raw = _minimal_raw(old_path)
    study = Study()
    study.set_loaded_data_list([old_raw], force_update=True)
    service = ApplicationService(study)
    _use_test_raw_factory(service)

    assert service.execute(ScanSourceCommand(source_path=str(source_dir))).ok
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "selected_eeg_files": [str(eeg_path)],
                "skip_labels": True,
            },
        )
    )
    candidate_id = preview.diagnostics["candidate"]["candidate_id"]
    assert service.execute(ValidateInterpretationCommand(candidate_id=candidate_id)).ok
    candidate = service.interpretation.state.resolve_candidate(candidate_id)
    identity_row = next(
        item
        for item in candidate.content_identity["files"]
        if item["role"] == "selected_eeg"
    )
    initial_stat = eeg_path.stat()
    untrusted_stat_boundary = SourceFileBoundary(
        path=str(eeg_path.resolve()),
        role=str(identity_row["role"]),
        sha256=str(identity_row["sha256"]),
        device=int(initial_stat.st_dev),
        inode=int(initial_stat.st_ino),
        file_bytes=int(initial_stat.st_size),
        modified_ns=int(initial_stat.st_mtime_ns),
        changed_ns=int(initial_stat.st_ctime_ns),
    )
    monkeypatch.setattr(
        SourceFileBoundary,
        "capture",
        classmethod(lambda _cls, _path, **_kwargs: untrusted_stat_boundary),
    )

    interpretation = service.interpretation
    original_prepare = interpretation.prepare_apply_interpretation
    preparation_ready = Event()
    release_preparation = Event()

    def _block_after_prepare(plan):
        prepared = original_prepare(plan)
        preparation_ready.set()
        assert release_preparation.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return prepared

    monkeypatch.setattr(
        interpretation,
        "prepare_apply_interpretation",
        _block_after_prepare,
    )
    command = ApplyInterpretationCommand(
        candidate_id=candidate_id,
        confirmed=True,
    )
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="apply-interpretation-content-rehash",
    )

    worker.start()
    assert preparation_ready.wait(timeout=THREAD_WATCHDOG_SECONDS)
    eeg_path.write_bytes(rewritten_bytes)
    os.utime(
        eeg_path,
        ns=(initial_stat.st_atime_ns, initial_stat.st_mtime_ns),
    )
    assert eeg_path.stat().st_size == initial_stat.st_size
    assert eeg_path.stat().st_mtime_ns == initial_stat.st_mtime_ns
    release_preparation.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert len(results) == 1
    rejected = results[0]
    assert rejected.failed
    assert rejected.error_type is ErrorType.PRECONDITION
    assert rejected.diagnostics["reason"] == "reviewed_content_or_contract_changed"
    assert study.data_manager.loaded_data_list == [old_raw]
    assert rejected.state.interpretation.has_applied_interpretation is False

    monkeypatch.setattr(
        interpretation,
        "prepare_apply_interpretation",
        original_prepare,
    )
    eeg_path.write_bytes(reviewed_bytes)
    retry = service.execute(
        command,
        operation_id=service.begin_owned_operation(command).operation_id,
    )

    assert retry.ok
    assert retry.state.interpretation.has_applied_interpretation is True
    assert study.data_manager.loaded_data_list[0].get_filepath() == str(eeg_path)
