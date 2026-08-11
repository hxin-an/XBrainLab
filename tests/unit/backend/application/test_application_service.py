"""Application service contract tests."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from threading import Condition, Event, Lock, Thread, current_thread
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import mne
import numpy as np
import pytest
import torch

from XBrainLab.backend.application import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationService,
    ApplyInterpretationCommand,
    ApplyMontageCommand,
    ApplySmartParseCommand,
    AttachLabelsCommand,
    ChangedState,
    ClearDatasetsCommand,
    ClearTrainingHistoryCommand,
    CommandName,
    CommandResult,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    DiscardTrainingPreparationCommand,
    ErrorType,
    EvaluateCommand,
    ImportLabelsCommand,
    LabelImportPlan,
    LoadDataCommand,
    NewSessionCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    QueryStateCommand,
    ReloadInterpretationRecipeCommand,
    RemoveFilesCommand,
    ResetPreprocessCommand,
    ResetSessionCommand,
    ReviewInterpretationCommand,
    SaliencyCommand,
    SaveDatasetSplitCommand,
    SaveInterpretationRecipeCommand,
    ScanSourceCommand,
    StopTrainingCommand,
    TrainCommand,
    UpdateMetadataCommand,
    ValidateInterpretationCommand,
    VisualizeCommand,
    data_interpretation_internal_events,
    get_application_service,
)
from XBrainLab.backend.application.bids_montage_preparation import (
    AggregateMontageCompatibility,
    BidsMontageRecordingRequest,
    BidsMontageResourceReceipt,
    MontagePreparationSnapshot,
    RecordingMontagePreparation,
)
from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.errors import ApplicationError
from XBrainLab.backend.application.montage_preparation_lifecycle import (
    ManualMontageOverride,
)
from XBrainLab.backend.application.resource_guard import (
    ResourceChecker,
    ResourcePreflightResult,
    TrainingResourcePreviewRequest,
    TrainingResourcePreviewResult,
    TrainingResourceRefinement,
)
from XBrainLab.backend.application.state import (
    ActiveDatasetSnapshot,
    ActiveTrainingSnapshot,
    ApplicationStateSnapshot,
    EvaluationStateSnapshot,
    TrainingStateSnapshot,
)
from XBrainLab.backend.application.training_submission import (
    attach_training_submission_provenance,
)
from XBrainLab.backend.application.view_publication import ApplicationViewStore
from XBrainLab.backend.dataset import (
    Dataset,
    DataSplittingConfig,
    Epochs,
    EpochWindowProvenance,
    TrainingType,
)
from XBrainLab.backend.exceptions import StaleTrainingPipelineMutationError
from XBrainLab.backend.load_data.raw import Raw
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import (
    ModelHolder,
    Trainer,
    TrainingEvaluation,
    TrainingOption,
    TrainingPlanHolder,
)
from XBrainLab.backend.training.evaluator import Evaluator
from XBrainLab.backend.training.record import RecordKey, TrainRecord, TrainRecordKey
from XBrainLab.backend.training_manager import (
    PostTrainingSaliencyTarget,
    post_training_saliency_target,
)
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyScheduleDisposition,
    PostTrainingSaliencyScheduleReason,
    TrainingLifecycleEvent,
    TrainingOutcomeState,
    TrainingReadBoundary,
    TrainingRunIdentity,
    TrainingStateToken,
    TrainingTerminalOutcome,
)
from XBrainLab.backend.utils.filesystem_identity import LegacyOutputNamespaceError
from XBrainLab.backend.utils.observer import ObserverDeliveryStatus

THREAD_WATCHDOG_SECONDS = 5.0
TRAINING_ACTIVE_SALIENCY_REASON = (
    "Wait for training to finish before configuring saliency."
)
STALE_SALIENCY_MESSAGE = (
    "Training or evaluation state changed during saliency recomputation. "
    "No saliency changes were applied; retry after training is idle."
)
SALIENCY_OOM_MESSAGE = (
    "Not enough GPU memory to recompute saliency. Existing evaluation results "
    "were kept. Reduce the selected saliency methods or sample count, then retry."
)


def _class_value_decisions(
    class_names: dict[str, str],
) -> dict[str, dict[str, object]]:
    return {
        raw_value: {
            "role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": class_name,
        }
        for raw_value, class_name in class_names.items()
    }


def _minimal_raw(
    filepath: Path,
    *,
    sfreq: float = 100.0,
    duration_seconds: float = 5.0,
) -> Raw:
    sample_count = max(1, round(sfreq * duration_seconds))
    return Raw(
        str(filepath),
        mne.io.RawArray(
            np.zeros((1, sample_count)),
            mne.create_info(["Cz"], sfreq=sfreq, ch_types="eeg"),
            verbose="ERROR",
        ),
    )


def _valid_model_holder() -> ModelHolder:
    return ModelHolder(int, {})


def _valid_training_option(*, batch_size: int = 4) -> TrainingOption:
    return TrainingOption(
        output_dir="./test-output",
        optim=torch.optim.Adam,
        optim_params={},
        use_cpu=True,
        gpu_idx=None,
        epoch=1,
        bs=batch_size,
        lr=0.001,
        checkpoint_epoch=0,
        evaluation_option=TrainingEvaluation.LAST_EPOCH,
        repeat_num=1,
    )


def _publish_mock_training_identity(service: ApplicationService) -> None:
    """Keep mocked starts honest about the typed runtime identity contract."""
    trainer = Trainer([])
    trainer.run(interact=False)
    service.study.training_manager.trainer = trainer


def _positive_epoch_data() -> Epochs:
    labels = np.array([0, 1, 0, 1, 0, 1], dtype=int)
    event_names = ("Left hand", "Right hand")
    epoch_data = Epochs([])
    epoch_data.data = np.zeros((len(labels), 2, 16), dtype=np.float32)
    epoch_data.event_id = {
        name: identifier for identifier, name in enumerate(event_names)
    }
    epoch_data.label_map = {
        identifier: name for name, identifier in epoch_data.event_id.items()
    }
    epoch_data.label = labels
    epoch_data.subject = np.zeros(len(labels), dtype=int)
    epoch_data.session = np.zeros(len(labels), dtype=int)
    epoch_data.idx = np.arange(len(labels), dtype=int)
    epoch_data.trial_group = np.arange(len(labels), dtype=int)
    epoch_data.subject_map = {0: "S01"}
    epoch_data.session_map = {0: "001"}
    epoch_data.ch_names = ["C3", "C4"]
    epoch_data.sfreq = 128.0
    epoch_data.epoch_window_provenance = tuple(
        EpochWindowProvenance(
            source_recording_id=f"content-sha256:{'a' * 64}",
            event_sample=index * 32,
            window_start_sample=index * 32,
            window_end_sample_exclusive=index * 32 + 16,
            source_sfreq=128.0,
            epoch_sfreq=128.0,
            tmin_seconds=0.0,
            tmax_seconds=15 / 128,
            source_coordinates_verified=True,
        )
        for index in range(len(labels))
    )
    return epoch_data


def _prepare_saved_training_split(service: ApplicationService) -> dict[str, Any]:
    """Prepare one real, audited split through the deferred public contract."""
    service.study.data_manager.loaded_data_list = [
        _minimal_raw(Path("/tmp/application-service-training.fif"))
    ]
    service.study.data_manager.epoch_data = _positive_epoch_data()

    saved = service.execute(SaveDatasetSplitCommand(split_strategy="trial"))
    assert saved.ok is True
    assert saved.state.dataset.split_spec_saved is True
    assert saved.state.dataset.split_materialized is False

    candidate = service.dataset_generation.prepare_saved_split_candidate()
    prepared = service.dataset_generation.commit_prepared_split(candidate)
    state = service.get_state()
    assert prepared["materialized"] is True
    assert prepared["split_audit"]["ok"] is True
    assert state.dataset.split_spec_saved is True
    assert state.dataset.split_materialized is True
    return prepared


def _bound_method_identity(handler: Any) -> tuple[Any, Any]:
    return (
        getattr(handler, "__self__", None),
        getattr(handler, "__func__", handler),
    )


def test_application_service_binds_every_command_handler_at_initialization():
    service = ApplicationService(Study())
    expected_handlers = {
        CommandName.SCAN_SOURCE: service.interpretation.handle_scan_source,
        CommandName.REVIEW_INTERPRETATION: (
            service.interpretation.handle_review_interpretation
        ),
        CommandName.PREVIEW_INTERPRETATION: (
            service.interpretation.handle_preview_interpretation
        ),
        CommandName.VALIDATE_INTERPRETATION: (
            service.interpretation.handle_validate_interpretation
        ),
        CommandName.APPLY_INTERPRETATION: (
            service.interpretation.handle_apply_interpretation
        ),
        CommandName.SAVE_INTERPRETATION_RECIPE: (
            service.interpretation.handle_save_interpretation_recipe
        ),
        CommandName.RELOAD_INTERPRETATION_RECIPE: (
            service.interpretation.handle_reload_interpretation_recipe
        ),
        CommandName.LOAD_DATA: service.data_compatibility.handle_load_data,
        CommandName.ATTACH_LABELS: service.data_compatibility.handle_attach_labels,
        CommandName.IMPORT_LABELS: service.data_compatibility.handle_import_labels,
        CommandName.UPDATE_METADATA: service.data_table.handle_update_metadata,
        CommandName.APPLY_SMART_PARSE: service.data_table.handle_apply_smart_parse,
        CommandName.REMOVE_FILES: service.data_table.handle_remove_files,
        CommandName.PREPROCESS: service.preprocess_commands.handle_preprocess,
        CommandName.CREATE_EPOCH: service.preprocess_commands.handle_create_epoch,
        CommandName.CONFIGURE_DATASET_SPLIT: (
            service.dataset_generation.handle_save_dataset_split
        ),
        CommandName.CLEAR_DATASETS: service.dataset_generation.handle_clear_datasets,
        CommandName.CONFIGURE_TRAINING: (
            service.training_commands.handle_configure_training
        ),
        CommandName.TRAIN: service._handle_train_with_automation,
        CommandName.DISCARD_TRAINING_PREPARATION: (
            service._handle_discard_training_preparation
        ),
        CommandName.STOP_TRAINING: service.training_commands.handle_stop_training,
        CommandName.CLEAR_TRAINING_HISTORY: (
            service.training_commands.handle_clear_training_history
        ),
        CommandName.EVALUATE: service.analysis.handle_evaluate,
        CommandName.VISUALIZE: service.analysis.handle_visualize,
        CommandName.SALIENCY: service.analysis.handle_saliency,
        CommandName.APPLY_MONTAGE: service.preprocess_commands.handle_apply_montage,
        CommandName.QUERY_STATE: service.query_state_commands.handle_query_state,
        CommandName.RESET_PREPROCESS: service.lifecycle.handle_reset_preprocess,
        CommandName.RESET_SESSION: service.lifecycle.handle_reset_session,
        CommandName.NEW_SESSION: service.lifecycle.handle_new_session,
    }

    assert set(expected_handlers) == set(CommandName)
    assert set(service._command_handlers) == set(expected_handlers)
    for name, expected in expected_handlers.items():
        actual = service._command_handlers[name]
        assert callable(actual)
        assert _bound_method_identity(actual) == _bound_method_identity(expected), (
            name.value
        )


def test_training_recommendation_previews_model_family_without_committing_model():
    service = ApplicationService(Study())

    with patch(
        "XBrainLab.backend.application.training_service.get_model_spec",
        side_effect=AssertionError(
            "recommendation preview must not resolve or instantiate a model"
        ),
    ) as model_lookup:
        recommendation = service.get_training_recommendation(
            prospective_model_name="braindecode.eegconformer",
            prospective_model_params={},
        )

    assert recommendation.recommended_values.epochs == 40
    assert recommendation.recommended_values.learning_rate == 0.0003
    assert recommendation.recommended_values.optimizer == "AdamW"
    assert service.get_state().training.model_name is None
    model_lookup.assert_not_called()


def test_training_recommendation_previews_device_in_backend_owned_context():
    service = ApplicationService(Study())

    cpu = service.get_training_recommendation(
        prospective_model_name="braindecode.deep4net",
        prospective_model_params={"n_filters_time": 25},
        prospective_device="cpu",
    )
    gpu = service.get_training_recommendation(
        prospective_model_name="braindecode.deep4net",
        prospective_model_params={"n_filters_time": 25},
        prospective_device="cuda:0",
    )

    assert cpu.recommended_values.batch_size == 8
    assert gpu.recommended_values.batch_size == 8
    assert cpu.context_fingerprint != gpu.context_fingerprint
    assert not any("GPU memory" in warning for warning in cpu.warnings)
    assert not any("GPU memory" in warning for warning in gpu.warnings)
    assert service.get_state().training.model_name is None


def test_training_resource_preview_is_typed_generation_bound_and_non_mutating():
    service = ApplicationService(Study())
    publication = service.get_view_publication()
    request = TrainingResourcePreviewRequest(
        request_generation=1,
        publication_generation=publication.generation,
        model_name=None,
        model_params={},
        device="cpu",
        batch_size=16,
        optimizer="Adam",
    )

    with pytest.raises(ApplicationError, match="requires prepared EEG epochs"):
        service.get_training_resource_preview(request)
    assert service.get_view_publication() == publication

    stale = replace(request, request_generation=2, publication_generation=999)
    with pytest.raises(ApplicationError, match="Training context changed"):
        service.get_training_resource_preview(stale)


def test_lazy_training_service_import_configures_after_epoch_preparation() -> None:
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = _positive_epoch_data()
    service.get_state()
    publication = service.get_view_publication()

    assert service.training_commands._service_instance is None

    configured = service.execute(
        ConfigureTrainingCommand(
            model_name="EEGNet",
            model_params={"f1": 2, "f2": 4, "d": 1},
            epoch=2,
            batch_size=2,
            learning_rate=0.001,
            optimizer="Adam",
            device="cpu",
        ),
        expected_publication_generation=publication.generation,
    )

    assert configured.ok is True
    assert configured.state.training.model_name == "EEGNet (XBrainLab)"
    assert configured.state.training.training_option is not None
    assert configured.state.training.training_option["batch_size"] == 2
    assert service.training_commands._service_instance is not None
    service.close()


def test_training_resource_preview_rejects_epoch_mutation_after_estimation() -> None:
    estimate_started = Event()
    release_estimate = Event()
    failures: list[BaseException] = []
    service = ApplicationService(Study())
    service.study.data_manager.loaded_data_list = [
        _minimal_raw(Path("/tmp/training-preview-stale.fif"))
    ]
    service.study.data_manager.epoch_data = _positive_epoch_data()
    service.get_state()
    publication = service.get_view_publication()
    request = TrainingResourcePreviewRequest(
        request_generation=1,
        publication_generation=publication.generation,
        model_name=None,
        model_params={},
        device="cpu",
        batch_size=16,
        optimizer="Adam",
    )

    def estimate(draft, _context):
        estimate_started.set()
        assert release_estimate.wait(timeout=2.0)
        return TrainingResourcePreviewResult(
            request_generation=draft.request_generation,
            publication_generation=draft.publication_generation,
            requested_batch_size=draft.batch_size,
            suggested_batch_size=draft.batch_size,
            estimated_vram_bytes=1024,
            available_vram_bytes=None,
            risk_level="unknown",
            vram_known=False,
        )

    service.training_resource_preview._estimate = estimate

    def query_preview() -> None:
        try:
            service.get_training_resource_preview(request)
        except BaseException as exc:
            failures.append(exc)

    query = Thread(target=query_preview, name="test-training-preview-client")
    query.start()
    assert estimate_started.wait(timeout=2.0)

    reset = service.execute(ResetPreprocessCommand(confirmed=True))
    assert reset.ok is True
    assert reset.state.epoch.available is False
    release_estimate.set()
    query.join(timeout=2.0)

    assert not query.is_alive()
    assert len(failures) == 1
    assert isinstance(failures[0], ApplicationError)
    assert "Training context changed" in str(failures[0])
    service.close()


def test_resource_adjusted_batch_provenance_survives_configure_snapshot_and_reopen() -> (
    None
):
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = _positive_epoch_data()
    service.get_state()
    publication = service.get_view_publication()
    request = TrainingResourcePreviewRequest(
        request_generation=1,
        publication_generation=publication.generation,
        model_name=None,
        model_params={},
        device="cpu",
        batch_size=16,
        optimizer="Adam",
    )
    refinement = TrainingResourceRefinement.batch_size(
        requested=16,
        refined=4,
    )
    service.training_resource_preview._estimate = lambda draft, _context: (
        TrainingResourcePreviewResult(
            request_generation=draft.request_generation,
            publication_generation=draft.publication_generation,
            requested_batch_size=draft.batch_size,
            suggested_batch_size=4,
            estimated_vram_bytes=1024,
            available_vram_bytes=2048,
            risk_level="warning",
            vram_known=True,
            warning="Batch size was resource-adjusted.",
            refinement=refinement,
        )
    )

    preview = service.get_training_resource_preview(request)
    assert preview.refinement == refinement
    assert preview.receipt is not None
    configured = service.execute(
        attach_training_submission_provenance(
            ConfigureTrainingCommand(
                epoch=3,
                batch_size=4,
                learning_rate=0.001,
                optimizer="Adam",
                device="cpu",
            ),
            frozenset(),
            resource_preview_receipt=preview.receipt,
        ),
        expected_publication_generation=publication.generation,
    )

    assert configured.ok is True
    recommendation = configured.state.training.recommendation
    assert recommendation is not None
    assert recommendation.values.batch_size == 4
    assert recommendation.provenance["batch_size"].value == "resource_adjusted"
    reopened = service.get_training_recommendation()
    assert reopened.values.batch_size == 4
    assert reopened.provenance["batch_size"].value == "resource_adjusted"
    service.close()


def test_matching_configuration_without_preview_receipt_is_not_resource_adjusted() -> (
    None
):
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = _positive_epoch_data()
    service.get_state()
    publication = service.get_view_publication()
    request = TrainingResourcePreviewRequest(
        request_generation=1,
        publication_generation=publication.generation,
        model_name=None,
        model_params={},
        device="cpu",
        batch_size=16,
        optimizer="Adam",
    )
    service.training_resource_preview._estimate = lambda draft, _context: (
        TrainingResourcePreviewResult(
            request_generation=draft.request_generation,
            publication_generation=draft.publication_generation,
            requested_batch_size=draft.batch_size,
            suggested_batch_size=4,
            estimated_vram_bytes=1024,
            available_vram_bytes=2048,
            risk_level="warning",
            vram_known=True,
            refinement=TrainingResourceRefinement.batch_size(
                requested=16,
                refined=4,
            ),
        )
    )
    preview = service.get_training_resource_preview(request)
    assert preview.receipt is not None

    configured = service.execute(
        ConfigureTrainingCommand(
            epoch=3,
            batch_size=4,
            learning_rate=0.001,
            optimizer="Adam",
            device="cpu",
        ),
        expected_publication_generation=publication.generation,
    )

    assert configured.ok is True
    recommendation = configured.state.training.recommendation
    assert recommendation is not None
    assert recommendation.provenance["batch_size"].value != "resource_adjusted"
    service.close()


def test_get_training_recommendation_does_not_touch_payload_or_resource_queries():
    service = ApplicationService(Study())
    epoch_get_data = MagicMock(
        side_effect=AssertionError("recommendation materialized epoch payload")
    )
    get_epoch_data = MagicMock(return_value=SimpleNamespace(get_data=epoch_get_data))
    service.study.datasets = [
        SimpleNamespace(name="payload-trap", get_epoch_data=get_epoch_data)
    ]
    unknown_vram = {
        "available_bytes": None,
        "total_bytes": None,
        "used_bytes": None,
        "reason": "test",
    }

    with (
        patch.object(
            ResourceChecker,
            "check_training_config_safe",
            wraps=ResourceChecker.check_training_config_safe,
        ) as resource_check,
        patch.object(
            ResourceChecker,
            "get_gpu_vram_status",
            return_value=unknown_vram,
        ) as gpu_query,
        patch.object(
            ResourceChecker,
            "estimate_training_vram",
            side_effect=AssertionError("recommendation estimated training VRAM"),
        ) as vram_estimator,
        patch(
            "XBrainLab.backend.application.resource_guard.estimate_training_resources",
            side_effect=AssertionError("recommendation ran direct estimator"),
        ) as direct_estimator,
        patch.object(
            ModelHolder,
            "get_model",
            side_effect=AssertionError("recommendation instantiated a model"),
        ) as model_factory,
        patch(
            "XBrainLab.backend.application.training_service.get_model_spec",
            side_effect=AssertionError("recommendation resolved a model factory"),
        ) as model_lookup,
    ):
        recommendation = service.get_training_recommendation()

    assert recommendation.is_starting_point is True
    get_epoch_data.assert_not_called()
    epoch_get_data.assert_not_called()
    resource_check.assert_not_called()
    gpu_query.assert_not_called()
    vram_estimator.assert_not_called()
    direct_estimator.assert_not_called()
    model_factory.assert_not_called()
    model_lookup.assert_not_called()


def test_shutdown_owner_exists_before_lifecycle_observers_can_publish(
    monkeypatch,
) -> None:
    study = Study()
    training_events = study.training_state_service
    original_subscribe = training_events.subscribe_training_started
    observed_callbacks: list[object] = []

    def subscribe_and_publish(callback) -> None:
        original_subscribe(callback)
        observed_callbacks.append(callback)
        callback()

    monkeypatch.setattr(
        training_events,
        "subscribe_training_started",
        subscribe_and_publish,
    )

    service = ApplicationService(study)

    assert observed_callbacks
    assert service.is_closed is False
    service.close()


def test_application_service_serializes_commands_across_calling_threads(monkeypatch):
    study = Study()
    service = ApplicationService(study)
    second_service = ApplicationService(study)
    original_execute_allowed = service._execute_allowed
    counter_lock = Lock()
    active_calls = 0
    max_active_calls = 0

    def tracked_execute_allowed(command, name):
        nonlocal active_calls, max_active_calls
        with counter_lock:
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
        try:
            time.sleep(0.03)
            return original_execute_allowed(command, name)
        finally:
            with counter_lock:
                active_calls -= 1

    monkeypatch.setattr(service, "_execute_allowed", tracked_execute_allowed)
    monkeypatch.setattr(second_service, "_execute_allowed", tracked_execute_allowed)
    commands = [NewSessionCommand(confirmed=True) for _ in range(2)]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda item: item[0].execute(item[1]),
                zip((service, second_service), commands, strict=True),
            )
        )

    assert all(result.ok for result in results)
    assert max_active_calls == 1


def test_query_state_command_reads_committed_publication_without_mutation_lock() -> (
    None
):
    study = Study()
    service = ApplicationService(study)
    initial = service.get_view_publication()
    lock_acquired = Event()
    release_lock = Event()
    holder_timed_out = Event()

    def hold_mutation_lock() -> None:
        with service._command_lock:
            lock_acquired.set()
            if not release_lock.wait(timeout=THREAD_WATCHDOG_SECONDS):
                holder_timed_out.set()

    holder = Thread(target=hold_mutation_lock)
    holder.start()
    assert lock_acquired.wait(timeout=THREAD_WATCHDOG_SECONDS)

    results = []
    query_completed = Event()

    def query_state() -> None:
        results.append(service.execute(QueryStateCommand(query="state")))
        query_completed.set()

    query_thread = Thread(target=query_state)
    started_at = time.perf_counter()
    query_thread.start()
    completed_while_locked = query_completed.wait(timeout=0.2)
    elapsed = time.perf_counter() - started_at
    holder_owned_lock = (
        holder.is_alive()
        and not holder_timed_out.is_set()
        and not release_lock.is_set()
    )

    release_lock.set()
    holder.join(timeout=THREAD_WATCHDOG_SECONDS)
    query_thread.join(timeout=THREAD_WATCHDOG_SECONDS)
    assert completed_while_locked is True
    assert elapsed < 0.2
    assert holder_owned_lock is True
    assert not holder.is_alive()
    assert not query_thread.is_alive()
    result = results[0]
    assert result.ok is True
    assert result.state == initial.state
    assert result.diagnostics["publication_generation"] == initial.generation
    assert result.diagnostics["publication_revision"] == initial.revision
    assert result.diagnostics["view_stale"] is False


def test_state_query_flags_do_not_mix_publication_generations() -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication().state
    updated = replace(before, pipeline_stage="data_loaded")
    service.state_snapshot.build = MagicMock(side_effect=[before, updated])

    result = service.execute(
        QueryStateCommand(
            query="state",
            params={"unused": True},
        )
    )

    assert result.ok is True
    assert result.state.pipeline_stage == result.diagnostics["state"]["pipeline_stage"]
    assert service.state_snapshot.build.call_count == 0


def test_published_state_query_returns_actionable_readiness_summary() -> None:
    service = ApplicationService(Study())

    result = service.execute(QueryStateCommand(query="state"))

    assert result.ok is True
    assert result.message == "No data loaded. Next: Scan data source."


def test_detached_data_query_fails_fast_instead_of_waiting_for_mutation_lock() -> None:
    service = ApplicationService(Study())
    lock_acquired = Event()
    release_lock = Event()

    def hold_mutation_lock() -> None:
        with service._command_lock:
            lock_acquired.set()
            release_lock.wait(timeout=THREAD_WATCHDOG_SECONDS)

    holder = Thread(target=hold_mutation_lock)
    holder.start()
    assert lock_acquired.wait(timeout=THREAD_WATCHDOG_SECONDS)

    results = []
    query_completed = Event()

    def query_objects() -> None:
        results.append(
            service.execute(
                QueryStateCommand(query="data_lists"),
            )
        )
        query_completed.set()

    query_thread = Thread(target=query_objects)
    query_thread.start()
    assert query_completed.wait(timeout=THREAD_WATCHDOG_SECONDS)
    assert release_lock.is_set() is False

    release_lock.set()
    holder.join(timeout=THREAD_WATCHDOG_SECONDS)
    query_thread.join(timeout=THREAD_WATCHDOG_SECONDS)
    assert not holder.is_alive()
    assert not query_thread.is_alive()
    result = results[0]
    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert result.diagnostics["application_busy"] is True


def test_data_summary_query_uses_committed_publication_while_command_lock_is_busy(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.get_state()
    live_read = MagicMock(
        side_effect=AssertionError(
            "published summary must not read mutable EEG objects"
        )
    )
    monkeypatch.setattr(service.dataset, "get_loaded_data_list", live_read)
    lock_acquired = Event()
    release_lock = Event()

    def hold_mutation_lock() -> None:
        with service._command_lock:
            lock_acquired.set()
            release_lock.wait(timeout=THREAD_WATCHDOG_SECONDS)

    holder = Thread(target=hold_mutation_lock)
    holder.start()
    assert lock_acquired.wait(timeout=THREAD_WATCHDOG_SECONDS)

    try:
        result = service.execute(QueryStateCommand(query="data_summary"))
    finally:
        release_lock.set()
        holder.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not holder.is_alive()
    assert result.ok is True
    assert result.message == "Dataset summary ready."
    assert result.diagnostics["count"] == 1
    assert result.diagnostics["files"] == [raw.get_filename()]
    live_read.assert_not_called()


def test_data_summary_query_rejects_stale_expected_publication_generation() -> None:
    service = ApplicationService(Study())
    publication = service.get_view_publication()

    result = service.execute(
        QueryStateCommand(query="data_summary"),
        expected_publication_generation=publication.generation + 1,
    )

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.diagnostics["stale_publication"] is True
    assert result.diagnostics["expected_publication_generation"] == (
        publication.generation + 1
    )
    assert result.diagnostics["current_publication_generation"] == (
        publication.generation
    )


def test_data_summary_query_fails_closed_for_unusable_publication() -> None:
    service = ApplicationService(Study())
    service._view_coordinator.mark_stale("forced summary publication failure")

    result = service.execute(QueryStateCommand(query="data_summary"))

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.diagnostics["view_stale"] is True
    assert result.diagnostics["view_verified"] is False


def test_view_publication_keeps_state_and_capabilities_on_one_generation() -> None:
    service = ApplicationService(Study())

    before = service.get_view_publication()
    result = service.execute(ScanSourceCommand(source_path="missing.fif"))
    after = service.get_view_publication()

    assert result.failed is True
    assert after.generation > before.generation
    assert after.state == result.state
    assert after.capabilities == build_capability_policy(after.state)


def test_bids_catalog_only_scan_preserves_application_publication(
    tmp_path: Path,
) -> None:
    bids_root = tmp_path / "bids"
    eeg_dir = bids_root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (bids_root / "dataset_description.json").write_text("{}", encoding="utf-8")
    (eeg_dir / "sub-01_task-P300_eeg.set").write_bytes(b"catalog only")
    service = ApplicationService(Study())
    delivered = []
    service.subscribe(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, delivered.append)
    before = service.get_view_publication()

    result = service.execute(
        ScanSourceCommand(
            source_path=str(bids_root),
            source_hint="bids",
            catalog_only=True,
        )
    )
    after = service.get_view_publication()

    assert result.ok is True
    assert result.diagnostics["bids_subject_catalog"]["subject_count"] == 1
    assert result.state == before.state
    assert after == before
    assert delivered == [before]
    assert service.acknowledge_view_publication_delivery(before.revision) is True

    repeated = service.execute(
        ScanSourceCommand(
            source_path=str(bids_root),
            source_hint="bids",
            catalog_only=True,
        )
    )

    assert repeated.ok is True
    assert service.get_view_publication() == before
    assert delivered == [before]


def test_view_publication_consumers_cannot_mutate_committed_state_or_policy() -> None:
    service = ApplicationService(Study())
    lock_acquired = Event()
    release_lock = Event()

    def hold_mutation_lock() -> None:
        with service._command_lock:
            lock_acquired.set()
            release_lock.wait(timeout=2.0)

    holder = Thread(target=hold_mutation_lock)
    holder.start()
    assert lock_acquired.wait(timeout=1.0)

    exposed = service.get_view_publication()
    exposed.state.raw.files.append("tampered.gdf")
    train = exposed.capabilities.get(CommandName.TRAIN)
    exposed.capabilities.capabilities[CommandName.TRAIN.value] = replace(
        train,
        enabled=True,
    )
    committed = service.get_view_publication()

    release_lock.set()
    holder.join(timeout=1.0)
    assert not holder.is_alive()
    assert "tampered.gdf" not in committed.state.raw.files
    assert committed.capabilities.get(CommandName.TRAIN).enabled is False


def test_view_publication_read_never_rebuilds_backend_state(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    updated_state = replace(before.state, pipeline_stage="training")
    monkeypatch.setattr(
        service.state_snapshot,
        "build",
        MagicMock(return_value=updated_state),
    )

    after = service.get_view_publication()

    assert after == before
    service.state_snapshot.build.assert_not_called()


def test_training_stopped_event_publishes_a_fresh_backend_generation(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    updated_state = replace(before.state, pipeline_stage="trained")
    build = MagicMock(return_value=updated_state)
    monkeypatch.setattr(service.state_snapshot, "build", build)

    service.training.notify("training_stopped")
    after = service.get_view_publication()

    assert build.call_count == 1
    assert after.generation > before.generation
    assert after.state.pipeline_stage == "trained"


def test_training_terminal_event_is_emitted_once_after_its_publication() -> None:
    service = ApplicationService(Study())
    trainer = Trainer([])
    service.study.training_manager.trainer = trainer
    trainer.run(interact=False)
    terminal_events = []
    service.training.subscribe("training_terminal_published", terminal_events.append)

    service.training.notify("training_stopped")
    service.training.notify("training_stopped")

    assert len(terminal_events) == 1
    event = terminal_events[0]
    publication = service.get_view_publication()
    assert event.publication_generation == publication.generation
    assert event.token == trainer.get_state_snapshot_token()
    assert event.outcome.state is TrainingOutcomeState.COMPLETED


def test_training_terminal_delivery_waits_for_canonical_view_acknowledgement(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    state = service.get_state()
    lifecycle_event = MagicMock(spec=TrainingLifecycleEvent)
    publish_view = MagicMock(return_value=False)
    deliver_terminal = MagicMock(return_value=True)
    monkeypatch.setattr(
        service.publication_lifecycle,
        "_refresh_training_publication",
        MagicMock(return_value=state),
    )
    monkeypatch.setattr(
        service.publication_lifecycle,
        "terminal_training_publication_event",
        MagicMock(return_value=lifecycle_event),
    )
    monkeypatch.setattr(
        service.publication_lifecycle,
        "_publish_view_changed",
        publish_view,
    )
    monkeypatch.setattr(
        service.publication_lifecycle,
        "deliver_training_terminal_publication",
        deliver_terminal,
    )

    assert service.publication_lifecycle.publish_training_terminal_state() is False
    publish_view.assert_called_once()
    deliver_terminal.assert_called_once_with(lifecycle_event)


def test_deferred_view_ack_releases_retained_training_terminal_event() -> None:
    service = ApplicationService(Study())
    trainer = Trainer([])
    service.study.training_manager.trainer = trainer
    trainer.run(interact=False)
    deferred_revisions: list[int] = []
    terminal_events: list[TrainingLifecycleEvent] = []

    def defer_view(publication) -> ObserverDeliveryStatus:
        deferred_revisions.append(publication.revision)
        return ObserverDeliveryStatus.DEFERRED

    service.subscribe(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, defer_view)
    service.training.subscribe(
        "training_terminal_published",
        terminal_events.append,
    )

    assert service.publication_lifecycle.publish_training_terminal_state() is False
    publication = service.get_view_publication()
    delivery = service.training_publications.training_delivery_state()

    assert deferred_revisions == [publication.revision]
    assert terminal_events == []
    assert delivery.pending_count == 1

    assert service.acknowledge_view_publication_delivery(publication.revision) is True

    delivery = service.training_publications.training_delivery_state()
    assert len(terminal_events) == 1
    assert delivery.pending_count == 0
    assert delivery.delivered_count == 1


def test_saliency_delivery_waits_for_canonical_view_acknowledgement(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    publish_view = MagicMock(return_value=False)
    notify_visualization = MagicMock(return_value=True)
    monkeypatch.setattr(
        service.publication_lifecycle,
        "_publish_view_changed",
        publish_view,
    )
    monkeypatch.setattr(
        service.publication_lifecycle._visualization,
        "notify",
        notify_visualization,
    )

    assert service.publication_lifecycle.notify_saliency_publication_changed() is False

    publish_view.assert_called_once()
    notify_visualization.assert_not_called()


def test_saliency_delivery_does_not_publish_stale_view_during_mutation(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    publish_view = MagicMock(return_value=True)
    notify_visualization = MagicMock(return_value=True)
    monkeypatch.setattr(
        service.publication_lifecycle,
        "_publish_view_changed",
        publish_view,
    )
    monkeypatch.setattr(
        service.publication_lifecycle._visualization,
        "notify",
        notify_visualization,
    )
    service._view_coordinator.mark_stale("mutation in progress")
    service._mutation_in_progress = True
    try:
        assert (
            service.publication_lifecycle.notify_saliency_publication_changed() is False
        )
    finally:
        service._mutation_in_progress = False

    publish_view.assert_not_called()
    notify_visualization.assert_not_called()


def test_training_terminal_event_rejects_mismatched_trainer_identity(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    trainer = Trainer([])
    service.study.training_manager.trainer = trainer
    trainer.run(interact=False)
    service.training.notify("training_stopped")
    publication = service.get_view_publication()
    outcome = publication.state.training.terminal_outcome
    assert outcome.run is not None
    mismatched_state = replace(
        publication.state,
        training=replace(
            publication.state.training,
            terminal_outcome=replace(
                outcome,
                run=TrainingRunIdentity(
                    trainer_id="different-trainer",
                    run_id=outcome.run.run_id,
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        service,
        "_committed_view_publication",
        lambda: replace(publication, state=mismatched_state),
    )

    assert (
        service.publication_lifecycle.terminal_training_publication_event(
            mismatched_state
        )
        is None
    )


def test_training_terminal_publication_ledger_accepts_each_new_generation_once(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    state = service.get_state()
    first_run = TrainingRunIdentity(trainer_id="terminal-ledger", run_id=1)
    second_run = TrainingRunIdentity(trainer_id="terminal-ledger", run_id=2)
    first = TrainingLifecycleEvent(
        token=TrainingStateToken(generation=11, stable=True),
        outcome=TrainingTerminalOutcome(
            state=TrainingOutcomeState.COMPLETED,
            run=first_run,
        ),
        publication_generation=21,
    )
    second = TrainingLifecycleEvent(
        token=TrainingStateToken(generation=12, stable=True),
        outcome=TrainingTerminalOutcome(
            state=TrainingOutcomeState.COMPLETED,
            run=second_run,
        ),
        publication_generation=22,
    )
    stale = TrainingLifecycleEvent(
        token=TrainingStateToken(generation=10, stable=True),
        outcome=TrainingTerminalOutcome(
            state=TrainingOutcomeState.FAILED,
            run=TrainingRunIdentity(trainer_id="terminal-ledger", run_id=3),
        ),
        publication_generation=20,
    )
    terminal_events: list[TrainingLifecycleEvent] = []

    def observe(event: TrainingLifecycleEvent) -> None:
        terminal_events.append(event)

    generated_events = iter((first, first, second, second, stale))
    monkeypatch.setattr(
        service.publication_lifecycle,
        "_refresh_training_publication",
        lambda: state,
    )
    monkeypatch.setattr(
        service.publication_lifecycle,
        "terminal_training_publication_event",
        lambda _state: next(generated_events),
    )
    service.training.subscribe("training_terminal_published", observe)

    service.publication_lifecycle.publish_training_terminal_state()
    service.publication_lifecycle.publish_training_terminal_state()
    service.publication_lifecycle.publish_training_terminal_state()
    service.publication_lifecycle.publish_training_terminal_state()
    service.publication_lifecycle.publish_training_terminal_state()

    assert terminal_events == [first, second]
    delivery_state = service.training_publications.training_delivery_state()
    assert delivery_state.active_count == 0
    assert delivery_state.delivered_count == 2
    assert delivery_state.latest_publication_generation == 22


def test_training_updated_event_publishes_live_progress_and_policy(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    updated_state = replace(
        before.state,
        pipeline_stage="training",
        training=replace(
            before.state.training,
            is_running=True,
            progress_message="Epoch 2/5",
        ),
        active_training=replace(
            before.state.active_training,
            is_running=True,
        ),
    )
    build = MagicMock(return_value=updated_state)
    monkeypatch.setattr(service.state_snapshot, "build", build)

    service.training.notify("training_updated")
    after = service.get_view_publication()
    query = service.execute(QueryStateCommand(query="state"))

    assert build.call_count == 1
    assert after.generation > before.generation
    assert after.state.training.progress_message == "Epoch 2/5"
    assert after.capabilities == build_capability_policy(after.state)
    assert query.ok is True
    assert query.state == after.state
    assert query.diagnostics["publication_generation"] == after.generation
    assert query.diagnostics["publication_revision"] == after.revision
    assert query.diagnostics["state"]["training"]["progress_message"] == "Epoch 2/5"


def test_real_training_updated_event_is_visible_through_query_state() -> None:
    study = Study()
    service = ApplicationService(study)
    trainer = Trainer([])
    study.training_manager.trainer = trainer
    trainer.progress_text = "Epoch 2/5"

    service.training.notify("training_updated")
    result = service.execute(QueryStateCommand(query="state"))

    assert result.ok is True
    assert result.state.training.has_trainer is True
    assert result.state.training.progress_message == "Epoch 2/5"
    assert result.diagnostics["state"]["training"]["progress_message"] == "Epoch 2/5"
    assert result.diagnostics["publication_generation"] > 1


def test_training_updated_skips_publication_while_training_token_is_unstable(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    unstable = TrainingReadBoundary(
        trainer_identity="unstable-training-test",
        token=TrainingStateToken(generation=3, stable=False),
    )
    monkeypatch.setattr(
        service.state_snapshot,
        "capture_training_read_boundary",
        MagicMock(return_value=unstable),
    )
    build = MagicMock()
    monkeypatch.setattr(service.state_snapshot, "build", build)

    service.training.notify("training_updated")
    after = service.get_view_publication()

    build.assert_not_called()
    assert after == before
    assert after.usable is True


def test_training_updated_does_not_wait_for_the_command_lock(monkeypatch) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    lock_acquired = Event()
    release_lock = Event()

    def hold_command_lock() -> None:
        with service._command_lock:
            lock_acquired.set()
            release_lock.wait(timeout=THREAD_WATCHDOG_SECONDS)

    holder = Thread(target=hold_command_lock)
    holder.start()
    assert lock_acquired.wait(timeout=THREAD_WATCHDOG_SECONDS)
    build = MagicMock()
    monkeypatch.setattr(service.state_snapshot, "build", build)
    update_returned = Event()

    notifier = Thread(
        target=lambda: (
            service.training.notify("training_updated"),
            update_returned.set(),
        )
    )
    notifier.start()

    assert update_returned.wait(timeout=THREAD_WATCHDOG_SECONDS)
    assert service._committed_view_publication() == before
    build.assert_not_called()

    release_lock.set()
    holder.join(timeout=THREAD_WATCHDOG_SECONDS)
    notifier.join(timeout=THREAD_WATCHDOG_SECONDS)
    assert not holder.is_alive()
    assert not notifier.is_alive()


def test_training_updated_recovers_after_a_transient_unstable_snapshot(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    updated_state = replace(
        before.state,
        pipeline_stage="training",
        training=replace(
            before.state.training,
            is_running=True,
            progress_message="Epoch 3/5",
        ),
        active_training=replace(before.state.active_training, is_running=True),
    )
    unstable_state = replace(
        updated_state,
        pipeline_stage="unavailable",
        state_reliable=False,
        training_liveness_reliable=False,
        read_errors=["training state changed during snapshot"],
    )
    build = MagicMock(side_effect=[unstable_state, updated_state])
    monkeypatch.setattr(service.state_snapshot, "build", build)

    service.training.notify("training_updated")
    transient = service._committed_view_publication()
    service.training.notify("training_updated")
    recovered = service._committed_view_publication()

    assert transient.usable is False
    assert transient.generation == before.generation
    assert recovered.usable is True
    assert recovered.generation > before.generation
    assert recovered.state.training.progress_message == "Epoch 3/5"
    assert build.call_count == 2


def test_training_history_query_reuses_live_event_publication(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    updated_state = replace(
        before.state,
        pipeline_stage="training",
        training=replace(
            before.state.training,
            is_running=True,
            progress_message="Epoch 1/5",
        ),
        active_training=replace(
            before.state.active_training,
            is_running=True,
        ),
    )
    build = MagicMock(return_value=updated_state)
    monkeypatch.setattr(service.state_snapshot, "build", build)

    service.training.notify("training_updated")
    published = service.get_view_publication()
    result = service.execute(
        QueryStateCommand(query="training_history"),
    )

    assert result.ok is True
    assert result.state == published.state
    assert build.call_count == 1


def test_training_history_query_rejects_when_training_token_outgrows_publication(
    monkeypatch,
) -> None:
    study = Study()
    trainer = Trainer([])
    study.training_manager.trainer = trainer
    service = ApplicationService(study)
    build = MagicMock(wraps=service.state_snapshot.build)
    monkeypatch.setattr(service.state_snapshot, "build", build)

    trainer.add_training_plan_holders([])
    result = service.execute(
        QueryStateCommand(query="training_history"),
    )

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.diagnostics["read_only_query"] is True
    assert result.diagnostics["query"] == "training_history"
    assert build.call_count == 0


def test_view_publication_health_and_policy_are_atomic_under_concurrent_reads() -> None:
    initial = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(initial, TrainingReadBoundary.no_trainer())
    start = Event()

    def publish_updates() -> None:
        start.wait(timeout=1.0)
        for index in range(80):
            state = replace(initial, pipeline_stage=f"stage-{index}")
            store.publish(state, TrainingReadBoundary.no_trainer())
            store.mark_stale(f"refresh-{index}")

    def read_and_validate() -> None:
        start.wait(timeout=1.0)
        for _ in range(240):
            publication = store.read()
            assert publication.capabilities == build_capability_policy(
                publication.state
            )
            assert publication.verified is publication.state.state_reliable
            if publication.stale:
                assert publication.refresh_error
            else:
                assert publication.refresh_error is None

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(publish_updates)]
        futures.extend(executor.submit(read_and_validate) for _ in range(4))
        start.set()
        for future in futures:
            future.result(timeout=5.0)


def test_view_store_restores_only_the_same_verified_generation() -> None:
    initial = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(initial, TrainingReadBoundary.no_trainer())
    expected = store.read()
    store.mark_stale("command is awaiting confirmation")

    restored = store.restore_verified(expected)

    assert restored.generation == expected.generation
    assert restored.revision == expected.revision + 2
    assert restored.state == expected.state
    assert restored.capabilities == expected.capabilities
    assert restored.training_boundary == expected.training_boundary
    assert restored.usable is True


def test_view_store_refuses_to_restore_over_a_newer_domain_generation() -> None:
    initial = ApplicationStateSnapshot.empty()
    store = ApplicationViewStore(initial, TrainingReadBoundary.no_trainer())
    old = store.read()
    updated = replace(initial, pipeline_stage="data_loaded")
    current = store.publish(updated, TrainingReadBoundary.no_trainer())

    with pytest.raises(RuntimeError, match="changed during control-flow recovery"):
        store.restore_verified(old)

    assert store.read() == current


def test_stale_committed_view_exposes_fail_closed_consumer_capabilities() -> None:
    service = ApplicationService(Study())
    service._view_coordinator.mark_stale("background state unavailable")

    publication = service._committed_view_publication()

    assert publication.usable is False
    assert publication.public_unavailable_code == "application_state_unavailable"
    assert (
        publication.unavailable_reason == "Workflow state is temporarily unavailable."
    )
    assert publication.diagnostic_error == "background state unavailable"
    effective = publication.effective_capabilities
    assert effective.get(CommandName.QUERY_STATE).enabled is True
    assert effective.get(CommandName.STOP_TRAINING).enabled is True
    assert effective.get(CommandName.RESET_SESSION).enabled is True
    assert effective.get(CommandName.NEW_SESSION).enabled is True
    assert effective.get(CommandName.RESET_SESSION).requires_confirmation is True
    assert effective.get(CommandName.NEW_SESSION).requires_confirmation is True
    assert effective.get(CommandName.SCAN_SOURCE).enabled is False
    assert any(
        "Workflow state is temporarily unavailable." in reason
        for reason in publication.effective_capabilities.get(
            CommandName.SCAN_SOURCE
        ).reasons
    )


def test_query_state_fails_closed_when_publication_recovery_still_fails(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    service._view_coordinator.mark_stale("background state unavailable")
    monkeypatch.setattr(
        service.state_snapshot,
        "build",
        MagicMock(side_effect=RuntimeError("background state unavailable")),
    )

    result = service.execute(QueryStateCommand(query="state"))

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.state.state_reliable is False
    assert result.state.active_training.is_running is True
    assert result.state.training.terminal_outcome.state is TrainingOutcomeState.UNKNOWN
    assert result.diagnostics["publication_generation"] == before.generation
    assert result.diagnostics["view_stale"] is True
    assert result.diagnostics["view_refresh_error"] == "background state unavailable"
    assert (
        result.diagnostics["capabilities"][CommandName.SCAN_SOURCE.value]["enabled"]
        is False
    )


def test_repeated_view_refresh_failure_does_not_churn_generation_or_errors(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    before = service.get_view_publication()
    service._view_coordinator.mark_stale("background state unavailable")
    build_state = MagicMock(side_effect=RuntimeError("background state unavailable"))
    monkeypatch.setattr(service.state_snapshot, "build", build_state)

    publications = [service.get_view_publication() for _ in range(5)]

    assert all(item.generation == before.generation for item in publications)
    assert all(item.usable is False for item in publications)
    assert all(item.state.state_reliable is False for item in publications)
    assert all(item.state.active_training.is_running is True for item in publications)
    assert all(
        item.state.read_errors == ["Workflow state is temporarily unavailable."]
        for item in publications
    )
    assert all(item.stale is True for item in publications)
    assert all(
        item.refresh_error == "background state unavailable" for item in publications
    )
    build_calls_before_query = build_state.call_count

    query_result = service.execute(QueryStateCommand(query="state"))

    assert query_result.failed is True
    assert query_result.error_type is ErrorType.PRECONDITION
    assert query_result.diagnostics["publication_generation"] == before.generation
    assert query_result.diagnostics["view_refresh_error"] == (
        "background state unavailable"
    )
    assert query_result.state.read_errors == [
        "Workflow state is temporarily unavailable."
    ]
    assert build_calls_before_query == 5
    assert build_state.call_count == build_calls_before_query


def test_object_query_uses_committed_generation_without_refresh_side_effects(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    build = MagicMock(wraps=service.state_snapshot.build)
    reconcile = MagicMock(
        side_effect=AssertionError("read-only query must not reconcile callbacks")
    )
    monkeypatch.setattr(service.state_snapshot, "build", build)
    monkeypatch.setattr(
        service.publication_lifecycle,
        "reconcile_pending_saliency_terminal",
        reconcile,
    )

    result = service.execute(QueryStateCommand(query="data_summary"))

    assert result.ok is True
    assert build.call_count == 0
    reconcile.assert_not_called()
    assert result.diagnostics["count"] == result.state.raw.count


@pytest.mark.parametrize(
    "token_error_type",
    [RuntimeError, KeyError],
    ids=["runtime-error", "key-error"],
)
def test_explicit_throwing_trainer_token_fails_closed_without_breaking_service(
    token_error_type,
) -> None:
    class _ThrowingTokenTrainer:
        def get_state_snapshot_token(self):
            raise token_error_type("token backend broken")

    study = Study()
    study.training_manager.trainer = cast(Any, _ThrowingTokenTrainer())

    service = ApplicationService(study)
    publication = service.get_view_publication()

    assert publication.state.state_reliable is False
    assert publication.state.pipeline_stage == "unavailable"
    assert publication.state.read_errors == [
        "Workflow state is temporarily unavailable."
    ]
    assert publication.verified is False
    assert publication.stale is True
    assert publication.refresh_error is not None
    assert "training state changed during snapshot" in publication.refresh_error
    assert publication.diagnostic_error == publication.refresh_error


def test_transient_real_training_mutation_keeps_last_verified_view_until_publish() -> (
    None
):
    service = ApplicationService(Study())
    record = object.__new__(TrainRecord)
    record._state_tracker = None
    record.epoch = 0
    record.option = cast(Any, type("Option", (), {"epoch": 1})())
    record.train = {key: [] for key in TrainRecordKey()}
    record.val = {key: [] for key in RecordKey()}
    record.eval_record = None

    holder = object.__new__(TrainingPlanHolder)
    holder.train_record_list = [record]
    holder._state_tracker = None
    holder._interrupt = Event()
    holder.error = None
    holder.status = "Pending"
    holder.model_holder = cast(
        Any,
        type(
            "ModelHolder",
            (),
            {"target_model": type("EEGNet", (), {})},
        )(),
    )
    trainer = Trainer([holder])
    service.study.training_manager.trainer = trainer
    service.get_state()
    before = service.get_view_publication()

    mutation_entered = Event()
    release_mutation = Event()

    class _BlockingMetrics(dict):
        def items(self):
            mutation_entered.set()
            assert release_mutation.wait(timeout=2.0)
            return super().items()

    worker = Thread(
        target=lambda: record.update_train(_BlockingMetrics({RecordKey.LOSS: 1.0}))
    )
    worker.start()
    assert mutation_entered.wait(timeout=2.0)

    during = service.get_view_publication()

    release_mutation.set()
    worker.join(timeout=2.0)
    assert not worker.is_alive()
    after = service.get_view_publication()

    assert during.generation == before.generation
    assert during.usable is True
    assert during.state == before.state
    assert after == during

    service.training.notify("training_stopped")
    terminal = service.get_view_publication()

    assert terminal.usable is True
    assert terminal.generation >= before.generation


def test_runtime_factory_shares_one_application_service_identity_per_study() -> None:
    study = Study()
    first = get_application_service(study)
    second = get_application_service(study)

    assert second is first
    assert first.study is study
    assert study._application_service is first


def test_shutdown_fence_blocks_mutations_until_cancelled() -> None:
    service = ApplicationService(Study())

    service.request_shutdown_fence()
    blocked = service.execute(NewSessionCommand(confirmed=True))
    blocked_train = service.execute(TrainCommand(confirmed=True))
    query = service.execute(QueryStateCommand(query="state"))
    stop = service.execute(StopTrainingCommand(wait_timeout=0.0))
    service.release_shutdown_fence()
    resumed = service.execute(NewSessionCommand(confirmed=True))

    assert blocked.failed is True
    assert blocked.error_type == ErrorType.PRECONDITION
    assert "closing" in blocked.message
    assert blocked_train.failed is True
    assert "closing" in blocked_train.message
    assert query.ok is True
    assert "closing" not in stop.message
    assert resumed.ok is True


def test_shutdown_fence_cancels_automatic_saliency_without_waiting() -> None:
    service = ApplicationService(Study())
    service.post_training_saliency.cancel = MagicMock()
    service.training_runtime.cancel_saliency_job = MagicMock()

    service.request_shutdown_fence()

    service.post_training_saliency.cancel.assert_called_once_with()
    service.training_runtime.cancel_saliency_job.assert_called_once_with()


def test_shutdown_fence_does_not_wait_for_saliency_terminal_reconciliation() -> None:
    service = ApplicationService(Study())
    command_lock_held = Event()
    release_command_lock = Event()
    shutdown_returned = Event()
    pending_terminal = MagicMock()
    service.publication_lifecycle.pending_saliency_terminal = MagicMock(
        return_value=pending_terminal
    )
    service.post_training_saliency.cancel = MagicMock()
    service.training_runtime.cancel_saliency_job = MagicMock(
        side_effect=(
            lambda: service.publication_lifecycle.reconcile_pending_saliency_terminal()
        ),
    )

    def hold_command_lock() -> None:
        with service._command_lock:
            command_lock_held.set()
            assert release_command_lock.wait(timeout=2.0)

    lock_owner = Thread(target=hold_command_lock)
    lock_owner.start()
    assert command_lock_held.wait(timeout=1.0)

    def request_shutdown() -> None:
        service.request_shutdown_fence()
        shutdown_returned.set()

    shutdown_thread = Thread(target=request_shutdown)
    shutdown_thread.start()

    try:
        assert shutdown_returned.wait(timeout=0.25)
    finally:
        release_command_lock.set()
        lock_owner.join(timeout=1.0)
        shutdown_thread.join(timeout=1.0)

    assert not lock_owner.is_alive()
    assert not shutdown_thread.is_alive()
    service.training_runtime.cancel_saliency_job.assert_called_once_with()


def test_close_releases_saliency_delivery_when_automation_cancel_fails() -> None:
    service = ApplicationService(Study())
    service.post_training_saliency.cancel = MagicMock(
        side_effect=RuntimeError("automation cancel failed")
    )
    service.training_runtime.cancel_saliency_job = MagicMock()
    service.training_runtime.discard_saliency_delivery = MagicMock()

    service.close()

    assert service.is_closed is True
    service.post_training_saliency.cancel.assert_called_once_with()
    service.training_runtime.cancel_saliency_job.assert_called_once_with()
    service.training_runtime.discard_saliency_delivery.assert_called_once_with()


def test_shutdown_fence_rechecks_command_queued_before_fence(monkeypatch) -> None:
    study = Study()
    service = ApplicationService(study)
    original_admission_lock = service._command_admission_lock
    admission_passed = Event()
    result_holder = []
    mutation_thread: Thread | None = None

    class _ObservedAdmissionLock:
        def __enter__(self):
            original_admission_lock.acquire()
            return self

        def __exit__(self, *_args):
            original_admission_lock.release()
            if current_thread() is mutation_thread:
                admission_passed.set()

    monkeypatch.setattr(
        service.shutdown_lifecycle,
        "_command_admission_lock",
        _ObservedAdmissionLock(),
    )

    def execute_queued_mutation() -> None:
        result_holder.append(service.execute(NewSessionCommand(confirmed=True)))

    with service._command_lock:
        mutation_thread = Thread(target=execute_queued_mutation)
        mutation_thread.start()
        assert admission_passed.wait(timeout=1.0)
        service.request_shutdown_fence()

    mutation_thread.join(timeout=1.0)

    assert not mutation_thread.is_alive()
    assert len(result_holder) == 1
    assert result_holder[0].failed is True
    assert result_holder[0].error_type == ErrorType.PRECONDITION
    assert "closing" in result_holder[0].message


def test_shutdown_fence_release_stays_exact_when_state_refresh_fails() -> None:
    service = ApplicationService(Study())
    service.get_state()
    service.request_shutdown_fence()
    fence_generation = service.shutdown_lifecycle.fence_generation
    original_build = service.state_snapshot.build
    service.state_snapshot.build = MagicMock(
        side_effect=RuntimeError("state backend unavailable"),
    )

    assert service.release_shutdown_fence() is False

    assert service.shutdown_lifecycle.is_shutdown_fenced is True
    assert service.shutdown_lifecycle.fence_generation == fence_generation

    service.state_snapshot.build = original_build

    assert service.release_shutdown_fence() is True
    assert service.shutdown_lifecycle.is_shutdown_fenced is False


def test_shutdown_fence_release_rejects_unusable_refresh_publication() -> None:
    service = ApplicationService(Study())
    reliable_state = service.get_state()
    unreliable_state = replace(reliable_state, state_reliable=False)
    service.request_shutdown_fence()
    fence_generation = service.shutdown_lifecycle.fence_generation
    original_build = service.state_snapshot.build
    service.state_snapshot.build = MagicMock(return_value=unreliable_state)

    assert service.release_shutdown_fence() is False
    assert service.shutdown_lifecycle.is_shutdown_fenced is True
    assert service.shutdown_lifecycle.fence_generation == fence_generation
    assert service._committed_view_publication().usable is False

    service.state_snapshot.build = original_build

    assert service.release_shutdown_fence() is True
    assert service.shutdown_lifecycle.is_shutdown_fenced is False


def test_product_interpretation_rollback_uses_complete_data_manager_state() -> None:
    study = Study()
    service = ApplicationService(study)
    interpretation = service.interpretation._service()
    manager = study.data_manager
    old_raw = object()
    old_backup = object()
    old_preprocessed = object()
    old_epoch = object()
    old_dataset = object()
    old_generator = object()
    manager.loaded_data_list = [old_raw]  # type: ignore[list-item]
    manager.backup_loaded_data_list = [old_backup]  # type: ignore[list-item]
    manager.preprocessed_data_list = [old_preprocessed]  # type: ignore[list-item]
    manager.epoch_data = old_epoch  # type: ignore[assignment]
    manager.datasets = [old_dataset]  # type: ignore[list-item]
    manager.dataset_generator = old_generator  # type: ignore[assignment]
    manager.dataset_locked = True

    snapshot = interpretation._snapshot_raw_state()
    manager.loaded_data_list = []
    manager.backup_loaded_data_list = None
    manager.preprocessed_data_list = []
    manager.epoch_data = None
    manager.datasets = []
    manager.dataset_generator = None
    manager.dataset_locked = False
    interpretation._restore_raw_state(snapshot)

    assert manager.loaded_data_list == [old_raw]
    assert manager.backup_loaded_data_list == [old_backup]
    assert manager.preprocessed_data_list == [old_preprocessed]
    assert manager.epoch_data is old_epoch
    assert manager.datasets == [old_dataset]
    assert manager.dataset_generator is old_generator
    assert manager.dataset_locked is True


def test_apply_interpretation_rolls_back_when_metadata_apply_raises(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "metadata_failure"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"scan-only fixture")
    study = Study()
    service = ApplicationService(study)
    manager = study.data_manager
    old_raw = _raw_mock()
    old_raw.get_filepath.return_value = "/previous/active.fif"
    old_backup = _raw_mock()
    old_preprocessed = _raw_mock()
    old_preprocessed.get_preprocess_history.return_value = []
    manager.loaded_data_list = [old_raw]
    manager.backup_loaded_data_list = [old_backup]
    manager.preprocessed_data_list = [old_preprocessed]
    imported_raw = _raw_mock()
    imported_raw.get_filename.return_value = eeg_path.name
    imported_raw.get_filepath.return_value = str(eeg_path)

    def import_files(_paths: list[str]) -> tuple[int, list[str]]:
        manager.loaded_data_list = [imported_raw]
        manager.preprocessed_data_list = [imported_raw]
        return 1, []

    service.dataset.import_files = MagicMock(side_effect=import_files)
    interpretation = service.interpretation._service()
    interpretation.apply_service.apply_candidate_metadata_to_loaded_data = MagicMock(
        side_effect=RuntimeError("metadata write failed"),
    )
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

    result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert result.failed is True
    assert result.error_type == ErrorType.INTERNAL
    assert "metadata write failed" in result.message
    assert manager.loaded_data_list == [old_raw]
    assert manager.backup_loaded_data_list == [old_backup]
    assert manager.preprocessed_data_list == [old_preprocessed]
    assert result.state.interpretation.has_applied_interpretation is False


def test_failed_replacement_restores_raw_interpretation_and_recipe(
    tmp_path: Path,
) -> None:
    old_source = tmp_path / "old_source"
    new_source = tmp_path / "new_source"
    old_source.mkdir()
    new_source.mkdir()
    old_eeg = old_source / "subject01_run1.fif"
    new_eeg = new_source / "subject02_run1.fif"
    old_eeg.write_bytes(b"old scan fixture")
    new_eeg.write_bytes(b"new scan fixture")
    recipe_path = tmp_path / "old-recipe.json"
    service = ApplicationService(Study())
    manager = service.study.data_manager

    def import_files(paths: list[str]) -> tuple[int, list[str]]:
        imported = []
        for path in paths:
            raw = _raw_mock()
            raw.get_filename.return_value = Path(path).name
            raw.get_filepath.return_value = path
            imported.append(raw)
        manager.loaded_data_list = imported
        manager.preprocessed_data_list = list(imported)
        return len(imported), []

    service.dataset.import_files = MagicMock(side_effect=import_files)
    service.execute(ScanSourceCommand(source_path=str(old_source)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "metadata_overrides": {
                    old_eeg.name: {
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
    first_apply = service.execute(ApplyInterpretationCommand(confirmed=True))
    saved = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )
    assert first_apply.ok is True
    assert saved.ok is True
    old_raw = manager.loaded_data_list[0]
    old_interpretation_id = first_apply.state.interpretation.latest_interpretation_id
    old_recipe_id = saved.state.interpretation.latest_recipe_id

    service.execute(ScanSourceCommand(source_path=str(new_source)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "metadata_overrides": {
                    new_eeg.name: {
                        "subject": "subject02",
                        "session": "session-01",
                        "task": "rest",
                        "run": "1",
                    },
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    interpretation = service.interpretation._service()
    interpretation.apply_service.apply_candidate_metadata_to_loaded_data = MagicMock(
        side_effect=RuntimeError("replacement metadata failed"),
    )

    failed = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert failed.failed is True
    assert manager.loaded_data_list == [old_raw]
    assert failed.state.interpretation.latest_interpretation_id == (
        old_interpretation_id
    )
    assert failed.state.interpretation.latest_recipe_id == old_recipe_id
    assert failed.state.interpretation.recipe_path == str(recipe_path)
    assert interpretation.state.resolve_recipe(None).recipe_id == old_recipe_id
    assert interpretation.state.resolve_recipe(None).label_imports == []


def test_reset_preprocess_is_blocked_while_training_is_running() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="training",
        active_dataset=ActiveDatasetSnapshot(has_raw_data=True),
        active_training=ActiveTrainingSnapshot(
            has_trainer=True,
            is_running=True,
        ),
    )

    capability = build_capability_policy(state).get(CommandName.RESET_PREPROCESS)

    assert capability.available is False
    assert any("training" in reason.lower() for reason in capability.reasons)


def test_reset_preprocess_command_does_not_mutate_live_training_state() -> None:
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_preprocess_history.return_value = ["filter"]
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    trainer = Trainer([])
    trainer.is_running = MagicMock(return_value=True)
    service.study.training_manager.trainer = trainer
    service.study.reset_preprocess = MagicMock()
    service.training.clean_datasets = MagicMock()

    result = service.execute(ResetPreprocessCommand(confirmed=True))

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    service.study.reset_preprocess.assert_not_called()
    service.training.clean_datasets.assert_not_called()
    assert service.study.data_manager.loaded_data_list == [raw]
    assert service.study.data_manager.preprocessed_data_list == [raw]
    assert service.study.training_manager.trainer is trainer


def test_reset_preprocess_command_rolls_back_stale_training_commit() -> None:
    service = ApplicationService(Study())
    manager = service.study.data_manager
    raw = _raw_mock()
    raw.get_preprocess_history.return_value = ["filter"]
    backup = _raw_mock()
    preprocessed = _raw_mock()
    preprocessed.get_preprocess_history.return_value = ["filter"]
    epoch = MagicMock()
    dataset = MagicMock()
    generator = MagicMock()
    trainer = Trainer([])
    trainer.is_running = MagicMock(return_value=False)
    manager.loaded_data_list = [raw]
    manager.backup_loaded_data_list = [backup]
    manager.preprocessed_data_list = [preprocessed]
    manager.epoch_data = epoch
    manager.datasets = [dataset]
    manager.dataset_generator = generator
    manager.dataset_locked = True
    service.study.training_manager.trainer = trainer

    def reset_preprocess(*, force_update: bool) -> None:
        assert force_update is True
        manager.loaded_data_list = [backup]
        manager.backup_loaded_data_list = None
        manager.preprocessed_data_list = []
        manager.epoch_data = None
        manager.datasets = []
        manager.dataset_generator = None
        manager.dataset_locked = False

    service.study.reset_preprocess = MagicMock(side_effect=reset_preprocess)
    service.study.training_manager.retire_trainer_if_current = MagicMock(
        side_effect=StaleTrainingPipelineMutationError(),
    )

    result = service.execute(ResetPreprocessCommand(confirmed=True))

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert manager.loaded_data_list == [raw]
    assert manager.backup_loaded_data_list == [backup]
    assert manager.preprocessed_data_list == [preprocessed]
    assert manager.epoch_data is epoch
    assert manager.datasets == [dataset]
    assert manager.dataset_generator is generator
    assert manager.dataset_locked is True
    assert service.study.training_manager.trainer is trainer


def test_empty_state_snapshot_and_policy():
    service = ApplicationService(Study())

    state = service.get_state()
    policy = service.get_capabilities()

    assert state.pipeline_stage == "empty"
    assert state.raw.loaded is False
    assert state.preprocessed.available is False
    assert state.epoch.available is False
    assert state.dataset.available is False
    assert state.training.has_trainer is False
    assert state.interpretation.has_scan_result is False
    assert state.interpretation.has_applied_interpretation is False
    assert policy.get(CommandName.LOAD_DATA).available is True
    assert policy.get(CommandName.SCAN_SOURCE).available is True
    assert policy.get(CommandName.PREVIEW_INTERPRETATION).available is False
    assert policy.get(CommandName.PREPROCESS).available is False
    assert policy.get(CommandName.TRAIN).available is False
    assert policy.get(CommandName.TRAIN).requires_confirmation is True
    assert policy.get(CommandName.TRAIN).can_auto_execute is False
    assert policy.get(CommandName.RESET_SESSION).confirmation_required is False


def test_serialized_query_uses_committed_state_when_fresh_builder_is_unavailable() -> (
    None
):
    service = ApplicationService(Study())
    service.state_snapshot.build = MagicMock(
        side_effect=RuntimeError("state backend unavailable"),
    )

    result = service.execute(QueryStateCommand(query="data_lists"))

    assert result.ok is True
    assert result.diagnostics["raw_count"] == 0
    assert result.state.state_reliable is True
    assert result.state.pipeline_stage == "empty"
    service.state_snapshot.build.assert_not_called()


def test_state_fallback_never_reuses_stale_idle_training_liveness() -> None:
    service = ApplicationService(Study())
    idle_state = service.get_state()
    assert idle_state.active_training.is_running is False
    service.state_snapshot.build = MagicMock(
        side_effect=RuntimeError("state backend unavailable"),
    )

    result = service.execute(StopTrainingCommand(wait_timeout=0.0))

    assert result.failed is True
    assert result.state.training_liveness_reliable is False
    assert result.state.active_training.is_running is True
    assert result.state.training.is_running is True


def test_handler_error_and_refresh_failure_fails_closed_without_retry() -> None:
    service = ApplicationService(Study())
    before = service.get_state()
    service.state_snapshot.build = MagicMock(
        side_effect=[before, RuntimeError("refresh unavailable")],
    )

    result = service.execute(
        ConfigureTrainingCommand(model_name="not-a-real-model"),
    )

    assert result.failed is True
    assert result.error_type == ErrorType.INTERNAL
    assert result.recoverable is False
    assert result.diagnostics["state_refresh_error"] == "refresh unavailable"
    assert result.diagnostics["handler_error_type"] == ErrorType.VALIDATION.value
    assert "Unknown model architecture" in result.diagnostics["handler_error_message"]
    assert result.diagnostics["command_effect_may_have_applied"] is True
    assert result.state is not before
    assert result.state.state_reliable is False
    assert result.state.pipeline_stage == "unavailable"


def test_handler_failure_does_not_execute_hostile_exception_metaclass() -> None:
    class HostileMeta(type):
        def __getattribute__(cls, name: str) -> object:
            if name == "__name__":
                raise AssertionError("hostile exception metaclass name access executed")
            return super().__getattribute__(name)

    class HostileHandlerError(Exception, metaclass=HostileMeta):
        def __str__(self) -> str:
            raise AssertionError("hostile exception string protocol executed")

    service = ApplicationService(Study())

    def fail(_command: ConfigureTrainingCommand) -> Any:
        raise HostileHandlerError("/srv/Clinical Records/Mary Example")

    service._command_handlers[CommandName.CONFIGURE_TRAINING] = fail

    result = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))

    assert result.failed is True
    assert result.error_type == ErrorType.INTERNAL
    assert result.message == "An unexpected application error occurred."
    assert result.diagnostics["exception_type"] == "Exception"
    assert "Mary Example" not in repr(result.to_public_dict())


def test_unexpected_handler_failure_is_logged_at_the_command_boundary() -> None:
    service = ApplicationService(Study())

    class InjectedTrainingFailure(Exception):
        pass

    def fail(_command: ConfigureTrainingCommand) -> Any:
        raise InjectedTrainingFailure("injected training configuration failure")

    service._command_handlers[CommandName.CONFIGURE_TRAINING] = fail

    with patch(
        "XBrainLab.backend.application.service.logger.exception",
    ) as log_exception:
        result = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))

    assert result.failed is True
    assert result.message == "An unexpected application error occurred."
    log_exception.assert_called_once_with(
        "%s command failed unexpectedly",
        CommandName.CONFIGURE_TRAINING.value,
    )


def test_legacy_training_output_namespace_is_an_actionable_precondition() -> None:
    service = ApplicationService(Study())

    def fail(_command: TrainCommand) -> Any:
        raise LegacyOutputNamespaceError("private legacy namespace detail")

    service._command_handlers[CommandName.TRAIN] = fail
    service._ensure_command_allowed = MagicMock()

    result = service.execute(TrainCommand(confirmed=True))

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.message == (
        "The selected training output folder contains results from an older "
        "XBrainLab version. Choose a different output folder or archive the "
        "existing results before starting training."
    )
    assert "private legacy namespace detail" not in repr(result.to_public_dict())


def test_explicit_state_unknown_handler_failure_fails_closed_when_state_is_readable() -> (
    None
):
    service = ApplicationService(Study())

    def fail_with_partial_rollback(_command: Any) -> Any:
        raise ApplicationError(
            message="Label rollback was incomplete.",
            error_type=ErrorType.INTERNAL,
            recoverable=False,
            diagnostics={
                "state_unknown": True,
                "retryable": False,
                "command_effect_may_have_applied": True,
            },
        )

    service._command_handlers[CommandName.CONFIGURE_TRAINING] = (
        fail_with_partial_rollback
    )

    result = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))

    assert result.failed is True
    assert result.recoverable is False
    assert result.diagnostics["state_unknown"] is True
    assert result.diagnostics["command_effect_may_have_applied"] is True
    assert result.changed_state.state_unknown is True
    assert result.state.state_reliable is False


class _RecoveryBlockingPlan(TrainingPlanHolder):
    """Minimal real Trainer plan that exits only after StopTraining interrupts it."""

    def __init__(self) -> None:
        self.started = Event()
        self._interrupt = Event()
        self.tracker = None

    def bind_state_tracker(self, tracker) -> None:
        self.tracker = tracker

    def get_name(self) -> str:
        return "Blocking plan"

    def get_plans(self) -> list[Any]:
        return []

    def train(self) -> None:
        self.started.set()
        self._interrupt.wait(timeout=THREAD_WATCHDOG_SECONDS)

    def set_interrupt(self) -> None:
        self._interrupt.set()

    def clear_interrupt(self) -> None:
        self._interrupt.clear()


class _SlowCancellationPlan(TrainingPlanHolder):
    """Keep the worker alive after interruption until the test releases cleanup."""

    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.interrupt_requested = Event()
        self.error: str | None = None
        self.tracker = None

    def bind_state_tracker(self, tracker) -> None:
        self.tracker = tracker

    def get_name(self) -> str:
        return "Slow cancellation plan"

    def get_plans(self) -> list[Any]:
        return []

    def get_training_status(self) -> str:
        return "Pending"

    def train(self) -> None:
        self.started.set()
        assert self.release.wait(timeout=THREAD_WATCHDOG_SECONDS)

    def set_interrupt(self) -> None:
        self.interrupt_requested.set()

    def clear_interrupt(self) -> None:
        self.interrupt_requested.clear()


def test_synchronous_train_command_allows_stop_command_to_reach_active_worker() -> None:
    service = ApplicationService(Study())
    _prepare_saved_training_split(service)
    service.study.set_model_holder(_valid_model_holder())
    service.study.set_training_option(_valid_training_option())
    plan = _RecoveryBlockingPlan()
    trainer = Trainer([cast(TrainingPlanHolder, plan)])

    def install_blocking_plan(
        *,
        force_update: bool = False,
        append: bool = False,
    ) -> None:
        del force_update, append
        service.study.training_manager.trainer = trainer

    service.study.generate_plan = install_blocking_plan  # type: ignore[method-assign]
    train_results: list[CommandResult] = []
    stop_results: list[CommandResult] = []
    train_thread = Thread(
        target=lambda: train_results.append(
            service.execute(
                TrainCommand(
                    confirmed=True,
                    interactive=False,
                    resource_preflight_confirmed=True,
                )
            )
        )
    )
    stop_thread = Thread(
        target=lambda: stop_results.append(
            service.execute(StopTrainingCommand(wait_timeout=THREAD_WATCHDOG_SECONDS))
        )
    )

    train_thread.start()
    assert plan.started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    stop_thread.start()
    stop_reached_worker = plan._interrupt.wait(timeout=0.25)
    if not stop_reached_worker:
        # Release only this test's worker so a red assertion cannot leak a thread.
        plan.set_interrupt()

    train_thread.join(timeout=THREAD_WATCHDOG_SECONDS)
    stop_thread.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not train_thread.is_alive()
    assert not stop_thread.is_alive()
    assert stop_reached_worker is True
    assert len(stop_results) == 1
    assert stop_results[0].ok is True
    assert stop_results[0].diagnostics["terminal_outcome"] == "cancelled"
    assert len(train_results) == 1
    assert train_results[0].failed is True
    assert train_results[0].error_type is ErrorType.TRAINING
    assert train_results[0].message == "Training was cancelled."


def test_stop_command_reports_requested_until_real_worker_exit() -> None:
    service = ApplicationService(Study())
    plan = _SlowCancellationPlan()
    trainer = Trainer([cast(TrainingPlanHolder, plan)])
    service.study.training_manager.trainer = trainer
    trainer.run(interact=True)
    assert plan.started.wait(timeout=THREAD_WATCHDOG_SECONDS)

    try:
        result = service.execute(StopTrainingCommand(wait_timeout=0.01))

        assert result.ok is True
        assert result.message == "Training stop requested."
        assert result.diagnostics["stopped"] is False
        assert result.diagnostics["terminal_outcome"] == "stop_requested"
        assert result.state.training.terminal_outcome.state is (
            TrainingOutcomeState.STOP_REQUESTED
        )
        assert result.state.active_training.is_running is True
        assert trainer.is_running() is True
    finally:
        plan.release.set()
        thread = trainer.job_thread
        if thread is not None:
            thread.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert trainer.is_running() is False
    assert trainer.get_terminal_outcome().state is TrainingOutcomeState.CANCELLED


@pytest.mark.parametrize(
    "recovery_command",
    ["stop_training", "reset_session", "new_session"],
)
def test_recovery_command_executes_real_handler_after_initial_snapshot_failure(
    recovery_command: str,
) -> None:
    study = Study()
    service = ApplicationService(study)
    plan: _RecoveryBlockingPlan | None = None
    trainer: Trainer | None = None
    if recovery_command == "stop_training":
        plan = _RecoveryBlockingPlan()
        trainer = Trainer([cast(TrainingPlanHolder, plan)])
        study.training_manager.trainer = trainer
        trainer.run(interact=True)
        assert plan.started.wait(timeout=THREAD_WATCHDOG_SECONDS)
        command = StopTrainingCommand(wait_timeout=THREAD_WATCHDOG_SECONDS)
    else:
        study.data_manager.loaded_data_list = [cast(Any, object())]
        study.data_manager.preprocessed_data_list = [cast(Any, object())]
        study.data_manager.epoch_data = cast(Any, object())
        study.data_manager.datasets = [cast(Any, object())]
        study.data_manager.dataset_generator = cast(Any, object())
        study.data_manager.dataset_locked = True
        # Deliberately corrupt private state to exercise recovery after a failed read.
        study.training_manager._model_holder = cast(Any, object())
        study.training_manager._training_option = cast(Any, object())
        study.training_manager.saliency_params = {"SmoothGrad": {"nt_samples": 5}}
        study.training_manager.trainer = Trainer([])
        command = (
            ResetSessionCommand(confirmed=True)
            if recovery_command == "reset_session"
            else NewSessionCommand(confirmed=True)
        )
    real_build = service.state_snapshot.build
    calls = 0

    def fail_once_then_build(*, last_error=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("snapshot unavailable")
        return real_build(last_error=last_error)

    service.state_snapshot.build = MagicMock(side_effect=fail_once_then_build)

    try:
        result = service.execute(command)

        assert result.ok is True
        assert result.command_name == command.name.value
        assert result.state.state_reliable is True
        assert service.state_snapshot.build.call_count == 2
        if recovery_command == "stop_training":
            assert result.message == "Training stopped."
            assert result.diagnostics["stopped"] is True
            assert result.state.active_training.is_running is False
            assert plan is not None and plan.interrupt is True
            assert trainer is not None and not trainer.is_running()
            assert study.training_manager.trainer is trainer
        else:
            assert result.state.pipeline_stage == "empty"
            assert study.data_manager.loaded_data_list == []
            assert study.data_manager.preprocessed_data_list == []
            assert study.data_manager.epoch_data is None
            assert study.data_manager.datasets == []
            assert study.data_manager.dataset_generator is None
            assert study.data_manager.dataset_locked is False
            assert study.training_manager.model_holder is None
            assert study.training_manager.training_option is None
            assert study.training_manager.saliency_params is None
            assert study.training_manager.trainer is None
    finally:
        if trainer is not None and trainer.is_running():
            trainer.stop(wait_timeout=THREAD_WATCHDOG_SECONDS)


@pytest.mark.parametrize(
    "command_type",
    [ResetSessionCommand, NewSessionCommand],
    ids=["reset-session", "new-session"],
)
@pytest.mark.parametrize(
    "materialize_training_service",
    [False, True],
    ids=["lazy", "materialized"],
)
def test_session_reset_uses_one_training_configuration_owner_regardless_of_laziness(
    monkeypatch: pytest.MonkeyPatch,
    command_type: type[ResetSessionCommand] | type[NewSessionCommand],
    materialize_training_service: bool,
) -> None:
    study = Study()
    service = ApplicationService(study)
    manager = study.training_manager
    manager.set_model_holder(_valid_model_holder())
    manager.set_training_option(_valid_training_option())
    manager.saliency_params = {"SmoothGrad": {"nt_samples": 5}}
    if materialize_training_service:
        service.training_commands._service()

    reset_owner = service.training_configuration_reset
    original_clear = reset_owner.clear
    clear_count = 0

    def record_clear() -> None:
        nonlocal clear_count
        clear_count += 1
        original_clear()

    monkeypatch.setattr(reset_owner, "clear", record_clear)

    result = service.execute(command_type(confirmed=True))

    assert result.ok is True
    assert clear_count == 1
    assert manager.model_holder is None
    assert manager.training_option is None
    assert manager.saliency_params is None
    assert (service.training_commands._service_instance is not None) is (
        materialize_training_service
    )


def test_state_read_failure_marks_the_entire_ui_state_unknown() -> None:
    service = ApplicationService(Study())
    service.state_snapshot.build = MagicMock(
        side_effect=RuntimeError("snapshot unavailable")
    )

    result = service.execute(ConfigureTrainingCommand(model_name="EEGNet"))

    assert result.failed is True
    assert result.changed_state.error_changed is True
    assert result.changed_state.state_unknown is True


def test_successful_mutation_fails_closed_when_updated_state_cannot_be_verified() -> (
    None
):
    service = ApplicationService(Study())
    before_publication = service.get_view_publication()
    publications = []
    service.subscribe(
        APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
        publications.append,
    )
    before = service.get_state()
    service.state_snapshot.build = MagicMock(
        side_effect=[before, RuntimeError("refresh unavailable")],
    )

    result = service.execute(NewSessionCommand(confirmed=True))

    assert result.failed is True
    assert result.error_type == ErrorType.INTERNAL
    assert result.recoverable is False
    assert result.state.state_reliable is False
    assert result.diagnostics["state_refresh_failed"] is True
    assert result.diagnostics["command_effect_may_have_applied"] is True
    assert result.changed_state.state_unknown is True
    assert len(publications) == 1
    assert publications[0].generation == before_publication.generation
    assert publications[0].revision > before_publication.revision
    assert publications[0].usable is False


def test_train_capability_blocks_short_epoch_for_selected_model():
    state = ApplicationService(Study()).get_state()
    ready_for_train = replace(
        state,
        epoch=replace(state.epoch, available=True, exists=True, n_times=100, sfreq=250),
        dataset=replace(
            state.dataset,
            available=True,
            count=1,
            active_split_summary={"audit": {"issues": []}},
        ),
        training=replace(
            state.training,
            has_model=True,
            model_name="EEGNet",
            model_params={},
            has_training_option=True,
        ),
        active_dataset=replace(
            state.active_dataset,
            has_raw_data=True,
            has_epoch_data=True,
            has_datasets=True,
            has_saved_split=True,
        ),
        active_training=replace(
            state.active_training,
            has_model=True,
            has_training_option=True,
        ),
    )

    train = build_capability_policy(ready_for_train).get(CommandName.TRAIN)

    assert train.available is False
    assert any("EEGNet needs at least" in reason for reason in train.reasons)


def test_train_capability_blocks_split_audit_errors():
    state = ApplicationService(Study()).get_state()
    ready_for_train = replace(
        state,
        epoch=replace(state.epoch, available=True, exists=True, n_times=512, sfreq=128),
        dataset=replace(
            state.dataset,
            available=True,
            count=1,
            split_spec_saved=True,
            last_split_attempt={
                "status": "failed",
                "audit": {
                    "issues": [
                        {
                            "severity": "error",
                            "message": "train split is missing class label(s) 1.",
                        }
                    ]
                },
            },
        ),
        training=replace(
            state.training,
            has_model=True,
            model_name="EEGNet",
            model_params={},
            has_training_option=True,
        ),
        active_dataset=replace(
            state.active_dataset,
            has_raw_data=True,
            has_epoch_data=True,
            has_datasets=True,
            has_saved_split=True,
        ),
        active_training=replace(
            state.active_training,
            has_model=True,
            has_training_option=True,
        ),
    )

    train = build_capability_policy(ready_for_train).get(CommandName.TRAIN)

    assert train.available is False
    assert (
        "Resolve dataset split audit before training: train split is missing "
        "class label(s) 1."
    ) in train.reasons


def test_capability_policy_covers_all_declared_commands():
    service = ApplicationService(Study())
    policy = service.get_capabilities()

    assert set(policy.capabilities) == {name.value for name in CommandName}
    assert policy.get(CommandName.EVALUATE).available is False
    assert policy.get(CommandName.VISUALIZE).available is False
    assert policy.get(CommandName.SALIENCY).available is False
    assert policy.get(CommandName.RESET_PREPROCESS).available is False
    assert policy.get(CommandName.CLEAR_DATASETS).available is False
    assert policy.get(CommandName.CLEAR_TRAINING_HISTORY).available is False
    assert policy.get(CommandName.SCAN_SOURCE).available is True
    assert policy.get(CommandName.REVIEW_INTERPRETATION).available is True
    assert policy.get(CommandName.PREVIEW_INTERPRETATION).available is False
    assert policy.get(CommandName.VALIDATE_INTERPRETATION).available is False
    assert policy.get(CommandName.APPLY_INTERPRETATION).available is False
    assert policy.get(CommandName.SAVE_INTERPRETATION_RECIPE).available is False
    assert policy.get(CommandName.RELOAD_INTERPRETATION_RECIPE).available is True
    assert policy.get(CommandName.QUERY_STATE).available is True
    assert policy.get(CommandName.NEW_SESSION).available is True


def test_read_only_training_history_query_reuses_committed_publication(monkeypatch):
    service = ApplicationService(Study())
    original_get_state = service.get_state
    calls = 0

    def counted_get_state():
        nonlocal calls
        calls += 1
        return original_get_state()

    monkeypatch.setattr(service, "get_state", counted_get_state)

    result = service.execute(QueryStateCommand(query="training_history"))

    assert result.failed is False
    assert result.changed_state == ChangedState()
    assert calls == 0


def test_training_history_query_returns_detached_json_rows(monkeypatch):
    service = ApplicationService(Study())
    plan = SimpleNamespace(
        option=SimpleNamespace(epoch=3),
        get_training_status=lambda: "Training 1",
    )
    record = SimpleNamespace(
        epoch=2,
        train={
            TrainRecordKey.LOSS: [0.5, 0.4],
            TrainRecordKey.ACC: [80.0, 82.0],
            TrainRecordKey.AUC: [0.7, 0.75],
            TrainRecordKey.LR: [0.001, 0.0005],
            TrainRecordKey.TIME: [1.2, 1.1],
        },
        val={
            RecordKey.LOSS: [0.6, 0.45],
            RecordKey.ACC: [75.0, 79.0],
            RecordKey.AUC: [0.65, 0.72],
        },
        start_timestamp=10.0,
        end_timestamp=70.0,
    )
    record.get_epoch = lambda: record.epoch
    record.is_finished = lambda: False
    source_row = {
        "plan": plan,
        "record": record,
        "group_name": "Group 1",
        "run_name": "2",
        "model_name": "EEGNet",
        "is_active": True,
        "is_current_run": True,
    }
    monkeypatch.setattr(
        service.state_snapshot.training_state,
        "get_formatted_history",
        lambda: [source_row],
    )

    result = service.execute(QueryStateCommand(query="training_history"))

    assert result.ok is True
    json.dumps(result.diagnostics, allow_nan=False)
    returned_row = result.diagnostics["rows"][0]
    expected_row = {
        "identity": {"plan_index": 0, "run_index": 0},
        "group_name": "Group 1",
        "run_name": "2",
        "model_name": "EEGNet",
        "status": "Running",
        "status_detail": None,
        "epoch": 2,
        "max_epochs": 3,
        "is_active": True,
        "is_current_run": True,
        "start_timestamp": 10.0,
        "end_timestamp": 70.0,
        "metrics": {
            "train": {
                "loss": [0.5, 0.4],
                "accuracy": [80.0, 82.0],
                "auc": [0.7, 0.75],
                "lr": [0.001, 0.0005],
                "time": [1.2, 1.1],
            },
            "validation": {
                "loss": [0.6, 0.45],
                "accuracy": [75.0, 79.0],
                "auc": [0.65, 0.72],
            },
            "test": {"accuracy": []},
        },
    }
    assert returned_row == expected_row

    record.train[TrainRecordKey.ACC].append(99.0)
    record.val[RecordKey.LOSS][0] = 9.9
    record.epoch = 3
    source_row["model_name"] = "MutatedNet"

    assert result.diagnostics["rows"][0] == expected_row


def test_data_interpretation_unresolved_sequence_target_cannot_be_confirmed(tmp_path):
    source_dir = tmp_path / "gdf_with_external_labels"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during scan")
    label_path.write_bytes(b"not loaded during scan")
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(1, []))

    scan = service.execute(ScanSourceCommand(source_path=str(source_dir)))
    preview = service.execute(PreviewInterpretationCommand())
    validation = service.execute(ValidateInterpretationCommand())
    unconfirmed_apply = service.execute(ApplyInterpretationCommand())
    confirmed_apply = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert scan.ok is True
    assert scan.command_name == CommandName.SCAN_SOURCE.value
    assert scan.changed_state.interpretation_changed is True
    assert scan.state.raw.loaded is False
    assert scan.diagnostics["scan_result"]["source_kind"] == "folder"
    assert scan.diagnostics["scan_result"]["eeg_files"] == [str(eeg_path)]
    assert scan.diagnostics["scan_result"]["label_carriers"] == [str(label_path)]

    assert preview.ok is True
    assert preview.diagnostics["preview"]["label_carrier_count"] == 1
    confirmation_text = " ".join(
        preview.diagnostics["preview"]["confirmation_items"]
    ).lower()
    assert "label placement" in confirmation_text
    assert "trial anchors" in confirmation_text
    assert validation.ok is True
    [carrier] = preview.diagnostics["candidate"]["label_carrier_plan"]
    assert carrier["placement_review"]["status"] == "blocked"
    assert validation.diagnostics["validation_decision"]["decision"] == "blocked"
    assert validation.state.interpretation.validation_decision == "blocked"

    assert unconfirmed_apply.failed is True
    assert unconfirmed_apply.error_type == ErrorType.PRECONDITION
    assert confirmed_apply.failed is True
    assert confirmed_apply.error_type == ErrorType.PRECONDITION
    assert "explicit target EEG event" in confirmed_apply.message
    assert service.dataset.import_files.call_count == 0
    assert confirmed_apply.state.interpretation.has_applied_interpretation is False


def test_data_interpretation_review_command_scans_previews_and_validates(tmp_path):
    source_dir = tmp_path / "review_command"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during review")
    label_path.write_bytes(b"not loaded during review")
    service = ApplicationService(Study())

    review = service.execute(
        ReviewInterpretationCommand(source_path=str(source_dir)),
    )

    assert review.ok is True
    assert review.command_name == CommandName.REVIEW_INTERPRETATION.value
    assert review.changed_state.interpretation_changed is True
    assert review.state.raw.loaded is False
    assert review.diagnostics["payload_type"] == "interpretation_review"
    assert review.diagnostics["scan_result"]["eeg_files"] == [str(eeg_path)]
    assert review.diagnostics["preview"]["label_carrier_count"] == 1
    assert review.diagnostics["candidate"]["candidate_id"]
    assert review.diagnostics["validation_decision"]["decision"] in {
        "safe",
        "needs_confirmation",
        "blocked",
    }


def test_data_interpretation_choices_flow_into_recipe(tmp_path):
    source_dir = tmp_path / "reviewed_source"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"not loaded during scan")
    recipe_path = tmp_path / "reviewed_recipe.json"
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(1, []))

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "metadata_overrides": {
                    "subject01_run1.fif": {
                        "session": "session-01",
                        "task": "motor-imagery",
                    }
                },
                "label_carrier": "embedded_events",
                "class_map": {"1": "left hand", "2": "right hand"},
            }
        )
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))
    save_result = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    metadata_preview = preview.diagnostics["preview"]["metadata_preview"][0]
    assert metadata_preview["session"]["value"] == "session-01"
    assert metadata_preview["session"]["source"] == "user_override"
    assert metadata_preview["task"]["value"] == "motor-imagery"
    assert preview.diagnostics["preview"]["class_map"] == {
        "1": "left hand",
        "2": "right hand",
    }
    applied = apply_result.diagnostics["applied_interpretation"]
    assert applied["class_map"] == {"1": "left hand", "2": "right hand"}
    recipe = save_result.diagnostics["recipe"]
    assert recipe["metadata"][0]["session"]["override"] == "session-01"
    assert recipe["metadata"][0]["task"]["override"] == "motor-imagery"
    assert recipe["class_map"] == {"1": "left hand", "2": "right hand"}
    assert "choices:metadata_overrides" in recipe["recipe_trace"]
    assert "choices:class_map" in recipe["recipe_trace"]


def test_safe_data_interpretation_cannot_be_applied_twice(tmp_path):
    source_dir = tmp_path / "safe_source"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"not loaded during scan")
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(1, []))

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
                    }
                }
            }
        )
    )
    validation = service.execute(ValidateInterpretationCommand())
    first_apply = service.execute(ApplyInterpretationCommand(confirmed=True))
    apply_capability = service.get_capabilities().get(CommandName.APPLY_INTERPRETATION)
    second_apply = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert validation.ok is True
    assert validation.state.interpretation.validation_decision == "safe"
    assert first_apply.ok is True
    assert first_apply.state.interpretation.has_applied_interpretation is True
    assert apply_capability.available is False
    assert "Interpretation has already been applied." in apply_capability.reasons
    assert second_apply.failed is True
    assert second_apply.error_type == ErrorType.PRECONDITION
    assert service.dataset.import_files.call_count == 1


def test_data_interpretation_preview_exposes_internal_event_evidence(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    eeg_path.write_bytes(b"not loaded during scan")
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "768": {"count": 288, "description": "768"},
                "769": {"count": 72, "description": "769"},
                "770": {"count": 72, "description": "770"},
                "1023": {"count": 15, "description": "1023"},
            }
        },
    )
    service = ApplicationService(Study())

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    result = service.execute(
        PreviewInterpretationCommand(
            choices={"label_carrier": "embedded_events"},
        )
    )

    preview_payload = result.diagnostics["preview"]["internal_event_preview"]
    candidate_payload = result.diagnostics["candidate"]["internal_event_preview"]

    assert preview_payload == candidate_payload
    assert preview_payload["source"] == "mne_internal_events"
    assert [row["event_code"] for row in preview_payload["candidate_label_events"]] == [
        "769",
        "770",
    ]
    assert preview_payload["candidate_label_events"][0]["event_count"] == 72
    assert [row["event_code"] for row in preview_payload["not_used_events"]] == [
        "768",
        "1023",
    ]


def test_data_interpretation_apply_updates_loaded_metadata(tmp_path):
    source_dir = tmp_path / "reviewed_source"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"not loaded during scan")
    service = ApplicationService(Study())

    class LoadedData:
        def __init__(self, filepath: str) -> None:
            self.filepath = filepath
            self.subject = "0"
            self.session = "0"
            self.runtime_details: dict[str, dict[str, str]] = {}

        def get_filepath(self) -> str:
            return self.filepath

        def set_subject_name(self, subject: str) -> None:
            self.subject = subject

        def set_session_name(self, session: str) -> None:
            self.session = session

        def set_runtime_detail(self, name: str, detail: dict[str, str]) -> None:
            self.runtime_details[name] = detail

    loaded = LoadedData(str(eeg_path))

    def import_files(_filepaths: object) -> tuple[int, list[str]]:
        cast(Any, service.study).loaded_data_list = [loaded]
        return 1, []

    service.dataset.import_files = MagicMock(side_effect=import_files)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "metadata_overrides": {
                    "subject01_run1.fif": {
                        "subject": "S01",
                        "session": "session-01",
                        "task": "motor-imagery",
                        "run": "1",
                    }
                }
            }
        )
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert loaded.subject == "S01"
    assert loaded.session == "session-01"
    assert loaded.runtime_details["data_interpretation_metadata"] == {
        "subject": "S01",
        "session": "session-01",
        "task": "motor-imagery",
        "run": "1",
    }
    assert apply_result.diagnostics["metadata_apply"] == [
        {
            "file": "subject01_run1.fif",
            "subject": "S01",
            "session": "session-01",
            "task": "motor-imagery",
            "run": "1",
        }
    ]


def test_data_interpretation_label_carrier_choices_flow_into_recipe(tmp_path):
    from scipy.io import savemat

    source_dir = tmp_path / "gdf_with_mat_labels"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during scan")
    savemat(
        label_path,
        {
            "classlabel": [1, 2, 1, 2],
            "cue_onset": [100, 200, 300, 400],
            "artifact_flag": [0, 0, 1, 0],
        },
    )
    recipe_path = tmp_path / "mat_label_recipe.json"
    service = ApplicationService(Study())
    raw = Raw(
        str(eeg_path),
        mne.io.RawArray(
            np.zeros((1, 500)),
            mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg"),
            verbose="ERROR",
        ),
    )
    service.dataset.import_files = MagicMock(return_value=(1, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
    service.dataset.apply_labels_batch = MagicMock(return_value=1)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    initial_preview = service.execute(PreviewInterpretationCommand())
    reviewed_preview = service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "classlabel",
                        "anchor": "cue_onset",
                        "time_model": "sample_index",
                        "sample_index_base": "zero_based",
                        "sample_index_origin": "recording_relative",
                        "granularity": "trial",
                        "role": "class cue labels",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    }
                },
                "event_roles": {"cue_onset": "trial anchor"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))
    save_result = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    initial_carriers = initial_preview.diagnostics["preview"]["label_carrier_preview"]
    assert initial_carriers[0]["format"] == "MAT"
    assert "classlabel" in initial_carriers[0]["label_candidates"]
    assert "cue_onset" in initial_carriers[0]["anchor_candidates"]

    reviewed_carrier = reviewed_preview.diagnostics["preview"]["label_carrier_preview"][
        0
    ]
    assert reviewed_carrier["selected_label_field"] == "classlabel"
    assert reviewed_carrier["selected_anchor"] == "cue_onset"
    assert reviewed_carrier["time_model"] == "sample_index"
    assert reviewed_carrier["granularity"] == "trial"
    assert reviewed_carrier["role"] == "class cue labels"

    applied = apply_result.diagnostics["applied_interpretation"]
    assert applied["label_carrier_plan"][0]["selected_label_field"] == "classlabel"
    assert applied["label_carrier_plan"][0]["selected_anchor"] == "cue_onset"
    assert applied["label_carrier_plan"][0]["role"] == "class cue labels"
    assert applied["event_roles"]["cue_onset"] == "trial anchor"
    recipe = save_result.diagnostics["recipe"]
    assert recipe["label_carrier_plan"][0]["path"] == str(label_path)
    assert recipe["label_carrier_plan"][0]["selected_label_field"] == "classlabel"
    assert recipe["label_carrier_plan"][0]["selected_anchor"] == "cue_onset"
    assert recipe["label_carrier_plan"][0]["role"] == "class cue labels"
    assert recipe["event_roles"]["cue_onset"] == "trial anchor"
    assert "choices:label_carriers" in recipe["recipe_trace"]
    assert "choices:event_roles" in recipe["recipe_trace"]


def test_data_interpretation_state_snapshot_preserves_import_review_truth(tmp_path):
    from scipy.io import savemat

    source_dir = tmp_path / "reviewed_state_truth"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during scan")
    savemat(label_path, {"classlabel": [1, 2], "cue_onset": [100, 200]})
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(1, []))

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "classlabel",
                        "anchor": "cue_onset",
                        "time_model": "sample_index",
                        "sample_index_base": "zero_based",
                        "sample_index_origin": "recording_relative",
                        "granularity": "trial",
                        "role": "class labels",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    },
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))
    query_result = service.execute(QueryStateCommand(query="state"))

    interpretation = apply_result.state.interpretation
    assert interpretation.label_carrier_plan[0]["path"] == str(label_path)
    assert interpretation.label_carrier_plan[0]["selected_label_field"] == "classlabel"
    assert interpretation.label_carrier_plan[0]["selected_anchor"] == "cue_onset"
    assert interpretation.class_map == {"1": "left hand", "2": "right hand"}
    assert (
        interpretation.event_roles["label_carrier"] == "external label or event source"
    )
    capabilities = {item["name"]: item for item in interpretation.format_capabilities}
    assert capabilities["A01T.gdf"]["status"] == "needs_review"
    assert capabilities["A01T.mat"]["format"] == "MAT labels"

    state_payload = query_result.diagnostics["state"]["interpretation"]
    assert state_payload["label_carrier_plan"] == interpretation.label_carrier_plan
    assert state_payload["format_capabilities"] == interpretation.format_capabilities
    assert state_payload["class_map"] == interpretation.class_map
    assert state_payload["event_roles"] == interpretation.event_roles


def test_data_interpretation_scan_reports_format_capability_boundaries(tmp_path):
    source_dir = tmp_path / "mixed_format_source"
    source_dir.mkdir()
    files = {
        "A01T.gdf": b"gdf placeholder",
        "physionet.edf": b"edf placeholder",
        "brainvision.vhdr": b"vhdr placeholder",
        "brainvision.vmrk": b"vmrk placeholder",
        "labels.mat": b"mat placeholder",
        "events.tsv": b"onset\ttrial_type\n0.0\tleft\n",
        "lsl_recording.xdf": b"xdf placeholder",
    }
    for name, content in files.items():
        (source_dir / name).write_bytes(content)
    from scipy.io import savemat

    savemat(
        source_dir / "eeglab.set",
        {
            "EEG": {
                "data": np.zeros((2, 16), dtype=np.float32),
                "nbchan": 2.0,
                "pnts": 16.0,
                "trials": 1.0,
                "srate": 128.0,
            }
        },
        do_compression=True,
    )
    service = ApplicationService(Study())

    scan = service.execute(ScanSourceCommand(source_path=str(source_dir)))
    preview = service.execute(PreviewInterpretationCommand())

    capabilities = {
        item["name"]: item
        for item in scan.diagnostics["scan_result"]["format_capabilities"]
    }

    assert capabilities["A01T.gdf"]["format"] == "GDF"
    assert capabilities["A01T.gdf"]["status"] == "needs_review"
    assert "trial anchor" in capabilities["A01T.gdf"]["message"]
    assert capabilities["physionet.edf"]["format"] == "EDF"
    assert "annotations" in capabilities["physionet.edf"]["message"]
    assert capabilities["eeglab.set"]["format"] == "EEGLAB"
    assert "boundary" in capabilities["eeglab.set"]["message"]
    assert capabilities["brainvision.vhdr"]["format"] == "BrainVision"
    assert "stimulus" in capabilities["brainvision.vhdr"]["message"]
    assert capabilities["brainvision.vmrk"]["format"] == "BrainVision markers"
    assert capabilities["brainvision.vmrk"]["role"] == "sidecar"
    assert capabilities["labels.mat"]["format"] == "MAT labels"
    assert capabilities["events.tsv"]["format"] == "BIDS events"
    assert capabilities["lsl_recording.xdf"]["status"] == "blocked"
    assert (
        "XDF / LSL stream selection is not available"
        in capabilities["lsl_recording.xdf"]["message"]
    )
    preview_capabilities = {
        item["name"]: item
        for item in preview.diagnostics["preview"]["format_capabilities"]
    }
    assert "brainvision.vmrk" not in preview_capabilities
    assert "lsl_recording.xdf" not in preview_capabilities
    assert set(preview_capabilities) == {
        "A01T.gdf",
        "brainvision.vhdr",
        "eeglab.set",
        "events.tsv",
        "labels.mat",
        "physionet.edf",
    }


def test_apply_interpretation_applies_reviewed_timestamp_label_carrier(tmp_path):
    source_dir = tmp_path / "reviewed_bids_events"
    source_dir.mkdir()
    eeg_path = source_dir / "sub-01_task-mi_raw.fif"
    events_path = source_dir / "events.tsv"
    eeg_path.write_bytes(b"not loaded during scan")
    events_path.write_text(
        "onset\tduration\ttrial_type\n0.5\t0.1\tleft\n1.5\t0.1\tright\n",
        encoding="utf-8",
    )
    service = ApplicationService(Study())
    raw = _minimal_raw(eeg_path)
    service.dataset.import_files = MagicMock(return_value=(1, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(events_path): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"left": "left hand", "right": "right hand"}
                        ),
                    }
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "applied"
    events, event_id = raw.get_event_list()
    np.testing.assert_array_equal(
        events,
        np.array([[50, 0, 1], [150, 0, 2]]),
    )
    assert event_id == {"left hand": 1, "right hand": 2}
    mne_raw = raw.get_mne()
    assert mne_raw is not None
    annotations = mne_raw.annotations
    assert annotations is not None
    np.testing.assert_allclose(annotations.onset, [0.5, 1.5])
    np.testing.assert_allclose(annotations.duration, [0.1, 0.1])
    assert list(annotations.description) == ["left hand", "right hand"]
    assert raw.is_labels_imported() is True
    assert apply_result.state.interpretation.label_import_count == 1
    assert apply_result.state.interpretation.label_imports[0]["mode"] == "timestamp"
    assert (
        "label_import:timestamp:1"
        in apply_result.diagnostics["applied_interpretation"]["recipe_trace"]
    )


def test_apply_interpretation_converts_sample_index_csv_labels_to_seconds(tmp_path):
    source_dir = tmp_path / "reviewed_csv_sample_index"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    labels_path = source_dir / "A01T_events.csv"
    eeg_path.write_bytes(b"not loaded during scan")
    labels_path.write_text(
        "sample,duration,label\n128,64,left\n256,64,right\n",
        encoding="utf-8",
    )
    service = ApplicationService(Study())
    raw = _minimal_raw(eeg_path, sfreq=128.0)
    service.dataset.import_files = MagicMock(return_value=(1, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(labels_path): {
                        "label_field": "label",
                        "anchor": "sample",
                        "duration_field": "duration",
                        "placement_method": "time_field",
                        "time_model": "sample_index",
                        "sample_index_base": "zero_based",
                        "sample_index_origin": "recording_relative",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"left": "left hand", "right": "right hand"}
                        ),
                    }
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    events, event_id = raw.get_event_list()
    np.testing.assert_array_equal(
        events,
        np.array([[128, 0, 1], [256, 0, 2]]),
    )
    assert event_id == {"left hand": 1, "right hand": 2}
    mne_raw = raw.get_mne()
    assert mne_raw is not None
    annotations = mne_raw.annotations
    assert annotations is not None
    np.testing.assert_allclose(annotations.onset, [1.0, 2.0])
    np.testing.assert_allclose(annotations.duration, [0.5, 0.5])
    assert list(annotations.description) == ["left hand", "right hand"]
    assert apply_result.state.interpretation.label_imports[0]["mode"] == "timestamp"


def test_apply_interpretation_applies_reviewed_csv_tsv_event_order_labels(
    tmp_path,
    monkeypatch,
):
    for suffix, delimiter in (("csv", ","), ("tsv", "\t")):
        source_dir = tmp_path / f"reviewed_{suffix}_event_order"
        source_dir.mkdir()
        eeg_path = source_dir / "A01T.gdf"
        labels_path = source_dir / f"A01T_events.{suffix}"
        eeg_path.write_bytes(b"not loaded during scan")
        labels_path.write_text(
            delimiter.join(["onset", "duration", "classlabel"])
            + "\n"
            + delimiter.join(["0.5", "0.1", "1"])
            + "\n"
            + delimiter.join(["1.5", "0.1", "2"])
            + "\n",
            encoding="utf-8",
        )
        _patch_internal_events(
            monkeypatch,
            {"A01T.gdf": {"768": {"count": 2, "description": "trial start"}}},
        )
        service = ApplicationService(Study())
        raw = _raw_mock()
        raw.get_filepath.return_value = str(eeg_path)
        raw.get_filename.return_value = eeg_path.name
        service.dataset.import_files = MagicMock(return_value=(1, []))
        service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
        service.dataset.apply_labels_batch = MagicMock(return_value=1)

        service.execute(ScanSourceCommand(source_path=str(source_dir)))
        service.execute(
            PreviewInterpretationCommand(
                choices={
                    "label_carrier_choices": {
                        str(labels_path): {
                            "label_field": "classlabel",
                            "target_event_codes": ["768"],
                            "placement_method": "eeg_event",
                            "time_model": "trial_order",
                            "granularity": "trial",
                            "value_decisions": _class_value_decisions(
                                {"1": "left hand", "2": "right hand"}
                            ),
                        },
                    },
                },
            ),
        )
        service.execute(ValidateInterpretationCommand())
        apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

        assert apply_result.ok is True
        assert apply_result.diagnostics["label_apply"]["mode"] == "sequence"
        label_map = service.dataset.apply_labels_batch.call_args.args[1]
        np.testing.assert_array_equal(label_map[str(labels_path)], np.array([1, 2]))
        assert service.dataset.apply_labels_batch.call_args.args[4] == {"768"}


def test_apply_interpretation_applies_reviewed_timestamp_label_carriers_by_stem(
    tmp_path,
):
    source_dir = tmp_path / "reviewed_bids_multi_events"
    source_dir.mkdir()
    eeg_1 = source_dir / "sub-01_task-mi_run-1_raw.fif"
    eeg_2 = source_dir / "sub-01_task-mi_run-2_raw.fif"
    events_1 = source_dir / "sub-01_task-mi_run-1_events.tsv"
    events_2 = source_dir / "sub-01_task-mi_run-2_events.tsv"
    eeg_1.write_bytes(b"not loaded during scan")
    eeg_2.write_bytes(b"not loaded during scan")
    events_1.write_text(
        "onset\tduration\ttrial_type\n0.5\t0.1\tleft\n",
        encoding="utf-8",
    )
    events_2.write_text(
        "onset\tduration\ttrial_type\n1.5\t0.1\tright\n",
        encoding="utf-8",
    )
    service = ApplicationService(Study())
    raw_1 = _minimal_raw(eeg_1)
    raw_2 = _minimal_raw(eeg_2)
    service.dataset.import_files = MagicMock(return_value=(2, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw_1, raw_2])

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(events_1): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"left": "left hand"}
                        ),
                    },
                    str(events_2): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"right": "right hand"}
                        ),
                    },
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "applied"
    assert apply_result.diagnostics["label_apply"]["success_count"] == 2
    first_events, first_event_id = raw_1.get_event_list()
    second_events, second_event_id = raw_2.get_event_list()
    np.testing.assert_array_equal(first_events, np.array([[50, 0, 1]]))
    np.testing.assert_array_equal(second_events, np.array([[150, 0, 1]]))
    assert first_event_id == {"left hand": 1}
    assert second_event_id == {"right hand": 1}
    assert raw_1.is_labels_imported() is True
    assert raw_2.is_labels_imported() is True
    assert apply_result.state.interpretation.label_import_count == 1
    assert apply_result.state.interpretation.label_imports[0]["file_mapping"] == {
        str(eeg_1): str(events_1),
        str(eeg_2): str(events_2),
    }


def test_apply_interpretation_skips_ambiguous_multi_file_timestamp_labels(tmp_path):
    source_dir = tmp_path / "ambiguous_multi_events"
    source_dir.mkdir()
    eeg_1 = source_dir / "sub-01_task-mi_run-1_raw.fif"
    eeg_2 = source_dir / "sub-01_task-mi_run-2_raw.fif"
    events = source_dir / "events.tsv"
    eeg_1.write_bytes(b"not loaded during scan")
    eeg_2.write_bytes(b"not loaded during scan")
    events.write_text("onset\ttrial_type\n0.5\tleft\n", encoding="utf-8")
    service = ApplicationService(Study())
    raw_1 = _raw_mock()
    raw_1.get_filepath.return_value = str(eeg_1)
    raw_2 = _raw_mock()
    raw_2.get_filepath.return_value = str(eeg_2)
    service.dataset.import_files = MagicMock(return_value=(2, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw_1, raw_2])
    service.dataset.apply_labels_batch = MagicMock(return_value=2)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(events): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "granularity": "trial",
                    },
                },
                "class_map": {"left": "left hand"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.failed is True
    assert apply_result.error_type == ErrorType.PRECONDITION
    assert "Label carrier pairing is incomplete" in apply_result.message
    service.dataset.import_files.assert_not_called()
    service.dataset.apply_labels_batch.assert_not_called()


def test_apply_interpretation_blocks_partial_manual_timestamp_label_mapping(
    tmp_path,
):
    source_dir = tmp_path / "manual_timestamp_mapping"
    source_dir.mkdir()
    eeg_1 = source_dir / "sub-01_task-mi_run-1_raw.fif"
    eeg_2 = source_dir / "sub-01_task-mi_run-2_raw.fif"
    events = source_dir / "events.tsv"
    eeg_1.write_bytes(b"not loaded during scan")
    eeg_2.write_bytes(b"not loaded during scan")
    events.write_text("onset\ttrial_type\n0.5\tleft\n", encoding="utf-8")
    service = ApplicationService(Study())
    raw_1 = _raw_mock()
    raw_1.get_filepath.return_value = str(eeg_1)
    raw_1.get_filename.return_value = eeg_1.name
    raw_2 = _raw_mock()
    raw_2.get_filepath.return_value = str(eeg_2)
    raw_2.get_filename.return_value = eeg_2.name
    service.dataset.import_files = MagicMock(return_value=(2, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw_1, raw_2])
    service.dataset.apply_labels_batch = MagicMock(return_value=1)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(events): {
                        "target_file": eeg_2.name,
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "time_model": "seconds",
                        "granularity": "trial",
                    },
                },
                "class_map": {"left": "left hand"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.failed is True
    assert apply_result.error_type == ErrorType.PRECONDITION
    assert "Label carrier pairing is incomplete" in apply_result.message
    assert "task-mi_run-1_raw.fif" in apply_result.message
    assert "sub-01" not in apply_result.message
    assert "[SUBJECT_REF:" in apply_result.message
    service.dataset.import_files.assert_not_called()
    service.dataset.apply_labels_batch.assert_not_called()


def test_apply_interpretation_applies_reviewed_mat_sequence_label_carrier(
    tmp_path,
    monkeypatch,
):
    from scipy.io import savemat

    source_dir = tmp_path / "reviewed_mat_sequence"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during scan")
    savemat(label_path, {"classlabel": np.array([1, 2, 1, 2])})
    _patch_internal_events(
        monkeypatch,
        {"A01T.gdf": {"768": {"count": 4, "description": "768"}}},
    )
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_filepath.return_value = str(eeg_path)
    raw.get_filename.return_value = eeg_path.name
    service.dataset.import_files = MagicMock(return_value=(1, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
    service.dataset.apply_labels_batch = MagicMock(return_value=1)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    }
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "applied"
    assert apply_result.diagnostics["label_apply"]["mode"] == "sequence"
    args = service.dataset.apply_labels_batch.call_args.args
    assert args[0] == [raw]
    np.testing.assert_array_equal(args[1][str(label_path)], np.array([1, 2, 1, 2]))
    assert args[3] == {1: "left hand", 2: "right hand"}
    assert apply_result.state.interpretation.label_imports[0]["mode"] == "sequence"
    assert (
        "label_import:sequence:1"
        in apply_result.diagnostics["applied_interpretation"]["recipe_trace"]
    )


def test_apply_interpretation_blocks_mixed_label_placement_modes(
    tmp_path,
    monkeypatch,
):
    from scipy.io import savemat

    source_dir = tmp_path / "mixed_label_placement"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    second_eeg_path = source_dir / "B01T.gdf"
    sequence_labels = source_dir / "A01T.mat"
    timed_labels = source_dir / "B01T_events.tsv"
    eeg_path.write_bytes(b"not loaded during scan")
    second_eeg_path.write_bytes(b"not loaded during scan")
    savemat(sequence_labels, {"classlabel": np.array([1, 2])})
    timed_labels.write_text(
        "onset\ttrial_type\n0.5\tleft\n1.5\tright\n",
        encoding="utf-8",
    )
    _patch_internal_events(
        monkeypatch,
        {"A01T.gdf": {"768": {"count": 2, "description": "768"}}},
    )
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_filepath.return_value = str(eeg_path)
    raw.get_filename.return_value = eeg_path.name
    second_raw = _raw_mock()
    second_raw.get_filepath.return_value = str(second_eeg_path)
    second_raw.get_filename.return_value = second_eeg_path.name
    service.dataset.import_files = MagicMock(return_value=(2, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw, second_raw])
    service.dataset.apply_labels_batch = MagicMock(return_value=2)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(sequence_labels): {
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"1": "Left hand", "2": "Right hand"}
                        ),
                    },
                    str(timed_labels): {
                        "label_field": "trial_type",
                        "anchor": "onset",
                        "placement_method": "time_field",
                        "time_model": "seconds",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"left": "Left hand", "right": "Right hand"}
                        ),
                    },
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.failed is True
    assert apply_result.error_type == ErrorType.VALIDATION
    assert apply_result.diagnostics["label_apply"]["status"] == "failed"
    assert "mixed placement modes" in apply_result.diagnostics["label_apply"]["reason"]
    assert apply_result.state.interpretation.has_applied_interpretation is False
    service.dataset.apply_labels_batch.assert_not_called()


def test_apply_interpretation_blocks_sequence_label_apply_count_mismatch(
    tmp_path,
    monkeypatch,
):
    from scipy.io import savemat

    source_dir = tmp_path / "sequence_apply_count_mismatch"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during scan")
    savemat(label_path, {"classlabel": np.array([1, 2])})
    _patch_internal_events(
        monkeypatch,
        {"A01T.gdf": {"768": {"count": 2, "description": "768"}}},
    )
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_filepath.return_value = str(eeg_path)
    raw.get_filename.return_value = eeg_path.name
    service.dataset.import_files = MagicMock(return_value=(1, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
    service.dataset.apply_labels_batch = MagicMock(return_value=0)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                    }
                },
                "class_map": {"1": "Left hand", "2": "Right hand"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.failed is True
    assert apply_result.error_type == ErrorType.VALIDATION
    assert apply_result.diagnostics["label_apply"]["status"] == "failed"
    assert "Applied labels to 0/1" in apply_result.diagnostics["label_apply"]["reason"]
    assert apply_result.state.interpretation.has_applied_interpretation is False


def test_apply_interpretation_filters_sequence_labels_to_selected_event_codes(
    tmp_path,
    monkeypatch,
):
    from scipy.io import savemat

    source_dir = tmp_path / "reviewed_mat_sequence_target_event"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during scan")
    savemat(label_path, {"classlabel": np.array([1, 2])})
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "768": {"count": 2, "description": "768"},
                "769": {"count": 1, "description": "769"},
                "770": {"count": 1, "description": "770"},
            }
        },
    )
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_filepath.return_value = str(eeg_path)
    raw.get_filename.return_value = eeg_path.name
    service.dataset.import_files = MagicMock(return_value=(1, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
    service.dataset.apply_labels_batch = MagicMock(return_value=1)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    }
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    call = service.dataset.apply_labels_batch.call_args
    assert call.args[4] == {"768"}
    assert apply_result.state.interpretation.label_imports[0][
        "selected_event_names"
    ] == ["768"]


def test_apply_interpretation_applies_reviewed_mat_sample_anchor_label_carrier(
    tmp_path,
):
    from scipy.io import savemat

    source_dir = tmp_path / "reviewed_mat_sample_anchor"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    label_path = source_dir / "A01T.mat"
    eeg_path.write_bytes(b"not loaded during scan")
    savemat(
        label_path,
        {
            "classlabel": np.array([1, 2, 1]),
            "cue_onset": np.array([100, 250, 400]),
            "cue_duration": np.array([50, 75, 25]),
        },
    )
    service = ApplicationService(Study())
    raw = _minimal_raw(eeg_path)
    service.dataset.import_files = MagicMock(return_value=(1, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "classlabel",
                        "anchor": "cue_onset",
                        "duration_field": "cue_duration",
                        "time_model": "sample_index",
                        "sample_index_base": "zero_based",
                        "sample_index_origin": "recording_relative",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    }
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "applied"
    assert apply_result.diagnostics["label_apply"]["mode"] == "anchored"
    events, event_id = raw.get_event_list()
    np.testing.assert_array_equal(
        events,
        np.array([[100, 0, 1], [250, 0, 2], [400, 0, 1]]),
    )
    assert event_id == {"left hand": 1, "right hand": 2}
    mne_raw = raw.get_mne()
    assert mne_raw is not None
    annotations = mne_raw.annotations
    assert annotations is not None
    np.testing.assert_allclose(annotations.onset, [1.0, 2.5, 4.0])
    np.testing.assert_allclose(annotations.duration, [0.5, 0.75, 0.25])
    assert list(annotations.description) == [
        "left hand",
        "right hand",
        "left hand",
    ]
    assert apply_result.state.interpretation.label_imports[0]["mode"] == "anchored"
    assert (
        "label_import:anchored:1"
        in apply_result.diagnostics["applied_interpretation"]["recipe_trace"]
    )


def test_apply_interpretation_applies_reviewed_event_code_label_carrier(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "reviewed_event_code_labels"
    source_dir.mkdir()
    eeg_path = source_dir / "session.edf"
    label_path = source_dir / "events.tsv"
    eeg_path.write_bytes(b"not loaded during scan")
    label_path.write_text(
        "event_code\tcondition\n11\tleft\n12\tright\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "11": {"count": 2, "description": "11"},
                "12": {"count": 1, "description": "12"},
            }
        },
    )
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_filepath.return_value = str(eeg_path)
    raw.get_filename.return_value = eeg_path.name
    raw.get_event_list.return_value = (
        np.array([[100, 0, 11], [200, 0, 12], [300, 0, 11]], dtype=np.int32),
        {"11": 11, "12": 12},
    )
    service.dataset.import_files = MagicMock(return_value=(1, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "condition",
                        "anchor": "event_code",
                        "placement_method": "event_code",
                        # Event-code placement must not fall into the timestamp path
                        # when a label table also carries timing-style metadata.
                        "time_model": "seconds",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"left": "Left hand", "right": "Right hand"}
                        ),
                    }
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["mode"] == "event_code"
    events, event_id = raw.set_event.call_args.args
    np.testing.assert_array_equal(
        events,
        np.array([[100, 0, 1], [200, 0, 2], [300, 0, 1]], dtype=np.int32),
    )
    assert event_id == {"Left hand": 1, "Right hand": 2}
    raw.set_labels_imported.assert_called_once_with(True)
    assert apply_result.state.interpretation.label_imports[0]["mode"] == "event_code"


def test_apply_interpretation_honors_interval_end_field(
    tmp_path,
):
    source_dir = tmp_path / "reviewed_interval_end"
    source_dir.mkdir()
    eeg_path = source_dir / "session.fif"
    label_path = source_dir / "events.tsv"
    eeg_path.write_bytes(b"not loaded during scan")
    label_path.write_text(
        "onset\tend\tlabel\n0.1\t0.6\tleft\n1.0\t1.4\tright\n",
        encoding="utf-8",
    )
    service = ApplicationService(Study())
    raw = _minimal_raw(eeg_path)
    service.dataset.import_files = MagicMock(return_value=(1, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])

    scan_result = service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_path): {
                        "label_field": "label",
                        "anchor": "onset",
                        "duration_field": "end",
                        "placement_method": "interval",
                        "time_model": "seconds",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"left": "Left hand", "right": "Right hand"}
                        ),
                    }
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert scan_result.diagnostics["scan_result"]["source_kind"] == "folder"
    assert apply_result.ok is True
    events, event_id = raw.get_event_list()
    np.testing.assert_array_equal(
        events,
        np.array([[10, 0, 1], [100, 0, 2]]),
    )
    assert event_id == {"Left hand": 1, "Right hand": 2}
    mne_raw = raw.get_mne()
    assert mne_raw is not None
    annotations = mne_raw.annotations
    assert annotations is not None
    np.testing.assert_allclose(annotations.onset, [0.1, 1.0])
    np.testing.assert_allclose(annotations.duration, [0.5, 0.4])
    assert list(annotations.description) == ["Left hand", "Right hand"]
    epoch_hint = raw.get_runtime_detail("data_interpretation_epoch_hint")
    assert isinstance(epoch_hint, dict)
    assert epoch_hint["source"] == "Loaded label file"
    assert epoch_hint["placement_method"] == "interval"
    assert epoch_hint["label_field"] == "label"
    assert epoch_hint["time_field"] == "onset"
    assert epoch_hint["duration_field"] == "end"
    assert epoch_hint["time_model"] == "seconds"
    assert epoch_hint["class_map"] == {"left": "Left hand", "right": "Right hand"}
    assert epoch_hint["recommended_events"] == ["Left hand", "Right hand"]
    assert epoch_hint["duration_stats"] == {
        "max": 0.5,
        "min": 0.4,
        "numeric_count": 2,
        "row_count": 2,
        "value_counts": {"0.4": 1, "0.5": 1},
    }


def test_apply_interpretation_records_internal_event_epoch_hint(
    tmp_path,
    monkeypatch,
):
    source_dir = tmp_path / "internal_event_epoch_hint"
    source_dir.mkdir()
    eeg_path = source_dir / "A01T.gdf"
    eeg_path.write_bytes(b"not loaded during scan")
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        lambda _path: {
            "events": {
                "769": {"count": 72, "description": "769"},
                "770": {"count": 72, "description": "770"},
                "768": {"count": 288, "description": "768"},
            }
        },
    )
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_filepath.return_value = str(eeg_path)
    raw.get_filename.return_value = eeg_path.name
    service.dataset.import_files = MagicMock(return_value=(1, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier": "embedded_events",
                "class_map": {"769": "Left hand", "770": "Right hand"},
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    epoch_hint = next(
        call.args[1]
        for call in raw.set_runtime_detail.call_args_list
        if call.args[0] == "data_interpretation_epoch_hint"
    )
    assert epoch_hint["source"] == "Labels inside EEG files"
    assert epoch_hint["placement_method"] == "internal_events"
    assert epoch_hint["class_map"] == {"769": "Left hand", "770": "Right hand"}
    assert epoch_hint["recommended_events"] == ["769", "770"]
    assert epoch_hint["event_label_aliases"] == {
        "769": "Left hand",
        "770": "Right hand",
    }


def test_apply_interpretation_applies_reviewed_sequence_label_carriers_by_stem(
    tmp_path,
    monkeypatch,
):
    from scipy.io import savemat

    source_dir = tmp_path / "reviewed_mat_sequence_multi"
    source_dir.mkdir()
    eeg_1 = source_dir / "A01T.gdf"
    eeg_2 = source_dir / "B01T.gdf"
    label_1 = source_dir / "A01T.mat"
    label_2 = source_dir / "B01T.mat"
    eeg_1.write_bytes(b"not loaded during scan")
    eeg_2.write_bytes(b"not loaded during scan")
    savemat(label_1, {"classlabel": np.array([1, 2])})
    savemat(label_2, {"classlabel": np.array([2, 1])})
    _patch_internal_events(
        monkeypatch,
        {
            "A01T.gdf": {"768": {"count": 2, "description": "768"}},
            "B01T.gdf": {"768": {"count": 2, "description": "768"}},
        },
    )
    service = ApplicationService(Study())
    raw_1 = _raw_mock()
    raw_1.get_filepath.return_value = str(eeg_1)
    raw_1.get_filename.return_value = eeg_1.name
    raw_2 = _raw_mock()
    raw_2.get_filepath.return_value = str(eeg_2)
    raw_2.get_filename.return_value = eeg_2.name
    service.dataset.import_files = MagicMock(return_value=(2, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw_1, raw_2])
    service.dataset.apply_labels_batch = MagicMock(return_value=2)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(label_1): {
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    },
                    str(label_2): {
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    },
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.ok is True
    assert apply_result.diagnostics["label_apply"]["status"] == "applied"
    assert apply_result.diagnostics["label_apply"]["success_count"] == 2
    calls = service.dataset.apply_labels_batch.call_args_list
    assert len(calls) == 1
    assert calls[0].args[0] == [raw_1, raw_2]
    np.testing.assert_array_equal(calls[0].args[1][str(label_1)], np.array([1, 2]))
    np.testing.assert_array_equal(calls[0].args[1][str(label_2)], np.array([2, 1]))
    assert calls[0].args[2] == {
        str(eeg_1): str(label_1),
        str(eeg_2): str(label_2),
    }
    assert apply_result.state.interpretation.label_imports[0]["file_mapping"] == {
        str(eeg_1): str(label_1),
        str(eeg_2): str(label_2),
    }


def test_apply_interpretation_blocks_ambiguous_multi_file_sequence_labels(
    tmp_path,
    monkeypatch,
):
    from scipy.io import savemat

    source_dir = tmp_path / "ambiguous_sequence_multi"
    source_dir.mkdir()
    eeg_1 = source_dir / "A01T.gdf"
    eeg_2 = source_dir / "B01T.gdf"
    labels = source_dir / "labels.mat"
    eeg_1.write_bytes(b"not loaded during scan")
    eeg_2.write_bytes(b"not loaded during scan")
    savemat(labels, {"classlabel": np.array([1, 2, 1, 2])})
    _patch_internal_events(
        monkeypatch,
        {
            "A01T.gdf": {"768": {"count": 2, "description": "768"}},
            "B01T.gdf": {"768": {"count": 2, "description": "768"}},
        },
    )
    service = ApplicationService(Study())
    raw_1 = _raw_mock()
    raw_1.get_filepath.return_value = str(eeg_1)
    raw_2 = _raw_mock()
    raw_2.get_filepath.return_value = str(eeg_2)
    service.dataset.import_files = MagicMock(return_value=(2, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw_1, raw_2])
    service.dataset.apply_labels_batch = MagicMock(return_value=2)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(labels): {
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    },
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.failed is True
    assert apply_result.error_type == ErrorType.PRECONDITION
    assert "Label carrier pairing is incomplete" in apply_result.message
    service.dataset.import_files.assert_not_called()
    service.dataset.apply_labels_batch.assert_not_called()


def test_apply_interpretation_blocks_partial_manual_sequence_label_mapping(
    tmp_path,
    monkeypatch,
):
    from scipy.io import savemat

    source_dir = tmp_path / "manual_sequence_mapping"
    source_dir.mkdir()
    eeg_1 = source_dir / "A01T.gdf"
    eeg_2 = source_dir / "B01T.gdf"
    labels = source_dir / "labels.mat"
    eeg_1.write_bytes(b"not loaded during scan")
    eeg_2.write_bytes(b"not loaded during scan")
    savemat(labels, {"classlabel": np.array([1, 2])})
    _patch_internal_events(
        monkeypatch,
        {
            "A01T.gdf": {"768": {"count": 2, "description": "768"}},
            "B01T.gdf": {"768": {"count": 2, "description": "768"}},
        },
    )
    service = ApplicationService(Study())
    raw_1 = _raw_mock()
    raw_1.get_filepath.return_value = str(eeg_1)
    raw_1.get_filename.return_value = eeg_1.name
    raw_2 = _raw_mock()
    raw_2.get_filepath.return_value = str(eeg_2)
    raw_2.get_filename.return_value = eeg_2.name
    service.dataset.import_files = MagicMock(return_value=(2, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw_1, raw_2])
    service.dataset.apply_labels_batch = MagicMock(return_value=1)

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(
        PreviewInterpretationCommand(
            choices={
                "label_carrier_choices": {
                    str(labels): {
                        "target_file": str(eeg_1),
                        "label_field": "classlabel",
                        "target_event_codes": ["768"],
                        "placement_method": "eeg_event",
                        "time_model": "trial_order",
                        "granularity": "trial",
                        "value_decisions": _class_value_decisions(
                            {"1": "left hand", "2": "right hand"}
                        ),
                    },
                },
            },
        ),
    )
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert apply_result.failed is True
    assert apply_result.error_type == ErrorType.PRECONDITION
    assert "Label carrier pairing is incomplete" in apply_result.message
    assert eeg_2.name in apply_result.message
    service.dataset.import_files.assert_not_called()
    service.dataset.apply_labels_batch.assert_not_called()


def test_data_interpretation_blocks_sources_without_eeg_files(tmp_path):
    source_dir = tmp_path / "labels_only"
    source_dir.mkdir()
    (source_dir / "labels.csv").write_text("label\n1\n2\n", encoding="utf-8")
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(1, []))

    scan = service.execute(ScanSourceCommand(source_path=str(source_dir)))
    preview = service.execute(PreviewInterpretationCommand())
    validation = service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert scan.ok is True
    assert preview.ok is True
    assert validation.ok is True
    assert validation.diagnostics["validation_decision"]["decision"] == "blocked"
    assert apply_result.failed is True
    assert apply_result.error_type == ErrorType.PRECONDITION
    assert "blocked" in apply_result.message.lower()
    service.dataset.import_files.assert_not_called()


def test_data_interpretation_recipe_save_and_reload_rescans_without_apply(tmp_path):
    source_dir = tmp_path / "simple_source"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"not loaded during scan")
    recipe_path = tmp_path / "recipe.json"
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(1, []))

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(PreviewInterpretationCommand())
    service.execute(ValidateInterpretationCommand())
    apply_result = service.execute(ApplyInterpretationCommand(confirmed=True))
    save_result = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    assert apply_result.ok is True
    assert save_result.ok is True
    assert recipe_path.exists()
    assert save_result.state.interpretation.has_recipe is True

    fresh_service = ApplicationService(Study())
    fresh_service.dataset.import_files = MagicMock(return_value=(1, []))
    reload_result = fresh_service.execute(
        ReloadInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    assert reload_result.ok is True
    assert reload_result.diagnostics["recipe"]["source_path"] == str(source_dir)
    assert reload_result.diagnostics["scan_result"]["eeg_files"] == [str(eeg_path)]
    assert reload_result.state.interpretation.has_recipe is True
    assert reload_result.state.interpretation.has_applied_interpretation is False
    fresh_service.dataset.import_files.assert_not_called()


def test_preprocess_capability_requires_raw_data_not_existing_preprocessed_copy():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = []
    service.get_state()

    policy = service.get_capabilities()

    assert policy.get(CommandName.PREPROCESS).available is True
    assert policy.get(CommandName.CREATE_EPOCH).available is False
    assert (
        "Preprocess data before creating EEG epochs"
        in (policy.get(CommandName.CREATE_EPOCH).reasons[0])
    )


def test_load_data_blocks_after_preprocessing_operations():
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_preprocess_history.return_value = ["bandpass"]
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.dataset.import_files = MagicMock(return_value=(1, []))
    service.get_state()

    policy = service.get_capabilities()
    result = service.execute(LoadDataCommand(paths=["/tmp/new_file.gdf"]))

    assert policy.get(CommandName.LOAD_DATA).available is False
    assert "Reset preprocessing" in policy.get(CommandName.LOAD_DATA).reasons[0]
    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    service.dataset.import_files.assert_not_called()


def test_evaluate_command_returns_typed_service_backed_summary():
    service = ApplicationService(Study())
    run = MagicMock()
    run.is_finished.return_value = True
    run.get_name.return_value = "Repeat-0"
    run.eval_record.evaluation_split = "test"
    plan = MagicMock()
    plan.get_name.return_value = "Plan A"
    plan.get_plans.return_value = [run]
    trainer = Trainer([])
    trainer.get_training_plan_holders = MagicMock(return_value=[plan])
    service.study.training_manager.trainer = trainer
    service.training_runtime.training_plan_holders = MagicMock(return_value=(plan,))

    result = service.execute(EvaluateCommand())

    assert result.ok is True
    assert not hasattr(service, "evaluation")
    assert result.command_name == "evaluate"
    assert result.diagnostics["payload_type"] == "evaluation_summary"
    assert result.diagnostics["evaluation_publication_generation"] == (
        service.get_view_publication().generation
    )
    assert result.diagnostics["available"] is True
    assert result.diagnostics["plan_count"] == 1
    assert result.diagnostics["plans"] == [
        {
            "identity": {"plan_index": 0},
            "name": "Plan A",
            "run_count": 1,
            "finished_run_count": 1,
            "evaluation_splits": ["test"],
            "runs": [
                {
                    "identity": {"plan_index": 0, "run_index": 0},
                    "name": "Repeat-0",
                    "finished": True,
                    "evaluation_split": "test",
                    "evaluation_splits": ["test"],
                }
            ],
        }
    ]
    assert "plan_objects" not in result.diagnostics
    assert result.diagnostics["training_read_verified"] is True
    assert isinstance(result.diagnostics["training_read_generation"], int)
    assert result.state.last_error is None


def test_evaluation_query_fails_when_training_generation_changes_mid_read() -> None:
    service = ApplicationService(Study())
    run = MagicMock()
    run.is_finished.return_value = True
    plan = MagicMock()
    plan.get_name.return_value = "Plan A"
    plan.get_plans.return_value = [run]
    trainer = Trainer([])
    trainer.get_training_plan_holders = MagicMock(return_value=[plan])
    service.study.training_manager.trainer = trainer

    original_handle_evaluate = service.analysis.handle_evaluate

    def mutate_training_while_reading(command: Any) -> Any:
        summary = original_handle_evaluate(command)
        trainer.set_interrupt()
        trainer.clear_interrupt()
        return summary

    service._command_handlers[CommandName.EVALUATE] = MagicMock(
        side_effect=mutate_training_while_reading
    )

    result = service.execute(EvaluateCommand())

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.diagnostics["training_state_changed"] is True


def test_evaluation_catalog_keeps_the_generation_read_under_command_lock() -> None:
    """A later mutation must not relabel an older Evaluation catalog."""
    service = ApplicationService(Study())
    run = MagicMock()
    run.is_finished.return_value = True
    run.get_name.return_value = "Repeat-0"
    run.eval_record.evaluation_split = "test"
    plan = MagicMock()
    plan.get_name.return_value = "Old plan"
    plan.get_plans.return_value = [run]
    trainer = Trainer([])
    trainer.get_training_plan_holders = MagicMock(return_value=[plan])
    service.study.training_manager.trainer = trainer
    service.training_runtime.training_plan_holders = MagicMock(return_value=(plan,))

    command_lock_released = Event()
    allow_evaluate_to_return = Event()
    original_lock = service._command_lock
    lock_depths: dict[object, int] = {}

    class _ReleaseBarrierLock:
        def acquire(self, *args: Any, **kwargs: Any) -> bool:
            acquired = original_lock.acquire(*args, **kwargs)
            if acquired:
                thread = current_thread()
                lock_depths[thread] = lock_depths.get(thread, 0) + 1
            return acquired

        def release(self) -> None:
            thread = current_thread()
            depth = lock_depths.get(thread, 0)
            assert depth > 0
            if depth == 1:
                del lock_depths[thread]
            else:
                lock_depths[thread] = depth - 1
            original_lock.release()
            if (
                depth == 1
                and thread.name.startswith("ThreadPoolExecutor")
                and not command_lock_released.is_set()
            ):
                command_lock_released.set()
                assert allow_evaluate_to_return.wait(timeout=5)

        def __enter__(self) -> _ReleaseBarrierLock:
            self.acquire()
            return self

        def __exit__(self, *_args: Any) -> None:
            self.release()

    service._command_lock = _ReleaseBarrierLock()
    before_generation = service.get_view_publication().generation

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(service.execute, EvaluateCommand())
        assert command_lock_released.wait(timeout=5)
        clear_result = service.execute(ClearTrainingHistoryCommand(confirmed=True))
        after_generation = service.get_view_publication().generation
        allow_evaluate_to_return.set()
        evaluate_result = future.result(timeout=5)

    assert clear_result.ok is True
    assert after_generation > before_generation
    assert evaluate_result.ok is True
    assert evaluate_result.diagnostics["plans"][0]["name"] == "Old plan"
    catalog_generation = evaluate_result.diagnostics[
        "evaluation_publication_generation"
    ]
    assert before_generation <= catalog_generation < after_generation


def test_training_history_query_fails_when_generation_changes_mid_read() -> None:
    service = ApplicationService(Study())
    trainer = Trainer([])
    service.study.training_manager.trainer = trainer

    def mutate_training_while_reading() -> list[dict[str, Any]]:
        trainer.set_interrupt()
        trainer.clear_interrupt()
        return []

    service.training_state.get_formatted_history = mutate_training_while_reading

    result = service.execute(QueryStateCommand(query="training_history"))

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.diagnostics["training_state_changed"] is True


def test_visualize_and_saliency_commands_return_typed_query_payloads():
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = MagicMock()
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())

    visualize = service.execute(VisualizeCommand(view="summary"))
    saliency = service.execute(SaliencyCommand())

    assert visualize.ok is True
    assert visualize.command_name == "visualize"
    assert visualize.diagnostics["payload_type"] == "visualization_summary"
    assert visualize.diagnostics["available"] is True
    assert "available_views" in visualize.diagnostics
    assert saliency.ok is True
    assert saliency.command_name == "saliency"
    assert saliency.diagnostics["payload_type"] == "saliency_summary"
    assert saliency.diagnostics["action"] == "query"
    assert saliency.diagnostics["saliency_configured"] is False


def test_saliency_command_can_configure_params():
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())

    result = service.execute(SaliencyCommand(params={"method": "Gradient"}))

    assert result.ok is True
    assert result.changed_state.visualization_changed is True
    assert result.diagnostics["action"] == "configure"
    assert result.diagnostics["saliency_configured"] is True
    assert result.diagnostics["saliency_available"] is False
    params = result.diagnostics["params"]
    assert params["_methods"] == ["Gradient"]
    assert {"SmoothGrad", "SmoothGrad_Squared", "VarGrad"}.issubset(params)


def test_manual_saliency_configuration_retries_failed_batched_view_delivery() -> None:
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())
    attempts = 0

    def fail_once() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient visualization observer failure")

    service.visualization.subscribe("saliency_changed", fail_once)

    result = service.execute(SaliencyCommand(params={"method": "Gradient"}))

    assert result.ok is True
    assert attempts == 2


def test_manual_saliency_configuration_reports_persistent_view_delivery_failure() -> (
    None
):
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())
    attempts = 0

    def always_fail() -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("persistent visualization observer failure")

    service.visualization.subscribe("saliency_changed", always_fail)

    result = service.execute(SaliencyCommand(params={"method": "Gradient"}))

    assert result.ok is True
    assert attempts == 2
    assert result.diagnostics["view_notification_retry_attempted"] is True
    assert result.diagnostics["view_notification_delivered"] is False
    assert "rejected both delivery attempts" in result.diagnostics["view_refresh_error"]


def test_concurrent_manual_saliency_commands_own_their_observer_acknowledgements(
    monkeypatch,
) -> None:
    """A waiting command must not join or erase another command's view batch."""
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())
    first_in_handler = Event()
    release_first = Event()
    second_batch_entered = Event()
    batch_entry_count = 0
    batch_entry_lock = Lock()
    original_batch = service.visualization.batch_notifications
    original_set = service.study.training_manager.set_saliency_params
    observer_attempts: dict[str, int] = {}
    results: dict[str, CommandResult] = {}
    failures: list[BaseException] = []

    @contextmanager
    def tracked_batch():
        nonlocal batch_entry_count
        with original_batch():
            with batch_entry_lock:
                batch_entry_count += 1
                entry = batch_entry_count
            if entry == 2:
                second_batch_entered.set()
            yield

    def controlled_set(params):
        if current_thread().name == "saliency-first":
            first_in_handler.set()
            assert release_first.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return original_set(params)

    def fail_first_delivery_per_thread() -> None:
        thread_name = current_thread().name
        observer_attempts[thread_name] = observer_attempts.get(thread_name, 0) + 1
        if thread_name == "saliency-first" and observer_attempts[thread_name] == 1:
            raise RuntimeError("transient first-command observer failure")

    def execute_saliency(name: str) -> None:
        try:
            results[name] = service.execute(
                SaliencyCommand(params={"method": "Gradient"})
            )
        except BaseException as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    monkeypatch.setattr(service.visualization, "batch_notifications", tracked_batch)
    monkeypatch.setattr(
        service.study.training_manager,
        "set_saliency_params",
        controlled_set,
    )
    service.visualization.subscribe("saliency_changed", fail_first_delivery_per_thread)
    first = Thread(
        target=execute_saliency,
        args=("first",),
        name="saliency-first",
    )
    second = Thread(
        target=execute_saliency,
        args=("second",),
        name="saliency-second",
    )

    first.start()
    assert first_in_handler.wait(timeout=THREAD_WATCHDOG_SECONDS)
    second.start()
    assert second_batch_entered.wait(timeout=THREAD_WATCHDOG_SECONDS)
    release_first.set()
    first.join(timeout=THREAD_WATCHDOG_SECONDS)
    second.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not first.is_alive()
    assert not second.is_alive()
    assert failures == []
    assert results["first"].ok is True
    assert results["second"].ok is True
    assert results["first"].diagnostics["view_notification_retry_attempted"] is True
    assert results["first"].diagnostics["view_notification_delivered"] is True
    assert "view_notification_retry_attempted" not in results["second"].diagnostics
    assert observer_attempts == {"saliency-first": 2, "saliency-second": 1}


def test_automatic_saliency_rejection_is_a_failed_command_result() -> None:
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())
    target = PostTrainingSaliencyTarget(
        run=TrainingRunIdentity(trainer_id="retired-trainer", run_id=1),
        finished_runs_before=0,
        finished_runs_after=1,
        append=True,
    )

    with post_training_saliency_target(target):
        result = service.execute(
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
    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.recoverable is True
    assert schedule.disposition is PostTrainingSaliencyScheduleDisposition.STALE
    assert schedule.reason is PostTrainingSaliencyScheduleReason.TRAINER_UNAVAILABLE
    assert schedule.status.phase is PostTrainingSaliencyPhase.CANCELLED
    assert result.message == schedule.message == schedule.status.message
    assert result.diagnostics["post_training_saliency_schedule"] == (schedule.to_dict())
    assert (
        service.study.training_manager.get_post_training_saliency_status()
        == schedule.status
    )


def _saliency_recompute_service() -> tuple[
    ApplicationService,
    Trainer,
    TrainingPlanHolder,
    TrainRecord,
    object,
]:
    service = ApplicationService(Study())
    old_eval_record = object()
    option = _valid_training_option(batch_size=1)
    model_holder = ModelHolder(type("EEGNet", (), {}), {})
    epoch_data = _positive_epoch_data()
    sample_count = len(epoch_data.get_label_list())
    dataset = SimpleNamespace(
        get_name=lambda: "saliency-dataset",
        get_epoch_data=lambda: epoch_data,
        train_mask=np.ones(sample_count, dtype=bool),
        val_mask=np.zeros(sample_count, dtype=bool),
        test_mask=np.ones(sample_count, dtype=bool),
    )
    record = object.__new__(TrainRecord)
    record._state_tracker = None
    record.epoch = option.epoch
    record.option = cast(Any, option)
    record.eval_record = cast(Any, old_eval_record)
    record.model = torch.nn.Linear(1, 1, bias=False)
    record.repeat = 0
    record.seed = 7
    record.plan_id = "saliency-plan"

    holder = object.__new__(TrainingPlanHolder)
    holder.model_holder = cast(Any, model_holder)
    holder.dataset = cast(Any, dataset)
    holder.option = cast(Any, option)
    holder.plan_id = "saliency-plan"
    holder.saliency_params = {"Gradient": {}}
    holder.train_record_list = [record]
    holder._state_tracker = None
    holder._interrupt = Event()
    holder.error = None
    holder.status = "Done"
    test_loader = object()
    holder.get_loader = MagicMock(return_value=(None, None, test_loader))
    holder.get_eval_pair = MagicMock(return_value=(object(), test_loader))

    trainer = Trainer([holder])
    service.study.training_manager.model_holder = model_holder
    service.study.training_manager.set_training_option(option)
    service.study.training_manager.trainer = trainer
    service.study.training_manager.saliency_params = holder.saliency_params
    return service, trainer, holder, record, old_eval_record


def test_saliency_configuration_is_blocked_while_training_but_query_remains_usable():
    study = Study()
    service = ApplicationService(study)
    plan = _RecoveryBlockingPlan()
    trainer = Trainer([cast(TrainingPlanHolder, plan)])
    study.training_manager.trainer = trainer
    trainer.run(interact=True)
    assert plan.started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    service.get_state()

    try:
        policy = service.get_capabilities().get(CommandName.SALIENCY)
        configured = service.execute(SaliencyCommand(method="Gradient"))
        queried = service.execute(SaliencyCommand())
    finally:
        trainer.stop(wait_timeout=THREAD_WATCHDOG_SECONDS)

    assert policy.available is False
    assert policy.reasons == [TRAINING_ACTIVE_SALIENCY_REASON]
    assert configured.failed is True
    assert configured.error_type == ErrorType.PRECONDITION
    assert configured.recoverable is True
    assert configured.message == TRAINING_ACTIVE_SALIENCY_REASON
    assert study.training_manager.saliency_params is None
    assert queried.ok is True
    assert queried.diagnostics["action"] == "query"
    assert queried.diagnostics["configure_available"] is False
    assert queried.diagnostics["configure_reasons"] == [TRAINING_ACTIVE_SALIENCY_REASON]


@pytest.mark.parametrize(
    "tracked_change",
    [True, False],
    ids=["tracked-generation-and-identity", "identity-only"],
)
def test_saliency_stale_prepare_returns_retryable_precondition_without_commit(
    tracked_change: bool,
):
    service, trainer, holder, record, old_eval_record = _saliency_recompute_service()
    manager = service.study.training_manager
    old_manager_params = manager.saliency_params
    old_holder_params = holder.saliency_params
    newer_eval_record = object()
    prepared_eval_record = object()
    generation_after_race: list[int] = []
    generation_before = trainer.get_state_generation()

    def mutate_after_prepare_started(*_args, **_kwargs):
        if tracked_change:
            record.set_eval_record(cast(Any, newer_eval_record))
        else:
            record.eval_record = cast(Any, newer_eval_record)
        generation_after_race.append(trainer.get_state_generation())
        return prepared_eval_record

    with patch.object(
        Evaluator,
        "evaluate_with_saliency",
        side_effect=mutate_after_prepare_started,
    ):
        result = service.execute(SaliencyCommand(method="Gradient"))

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.message == STALE_SALIENCY_MESSAGE
    assert result.diagnostics["retryable"] is True
    assert result.diagnostics["stale_saliency_update"] is True
    assert result.diagnostics["state_preserved"] is True
    assert result.changed_state.error_changed is True
    assert result.changed_state.evaluation_changed is False
    assert result.changed_state.visualization_changed is False
    assert manager.saliency_params is old_manager_params
    assert holder.saliency_params is old_holder_params
    assert record.eval_record is newer_eval_record
    assert record.eval_record is not old_eval_record
    assert record.eval_record is not prepared_eval_record
    assert trainer.get_state_generation() == generation_after_race[0]
    assert generation_after_race[0] == generation_before + (2 if tracked_change else 0)


def test_saliency_compute_error_without_state_change_remains_internal() -> None:
    service, trainer, holder, record, old_eval_record = _saliency_recompute_service()
    manager = service.study.training_manager
    old_manager_params = manager.saliency_params
    old_holder_params = holder.saliency_params
    generation_before = trainer.get_state_generation()

    with patch.object(
        Evaluator,
        "evaluate_with_saliency",
        side_effect=RuntimeError("saliency kernel failed"),
    ):
        result = service.execute(SaliencyCommand(method="Gradient"))

    assert result.failed is True
    assert result.error_type == ErrorType.INTERNAL
    assert result.recoverable is False
    assert result.message == "saliency kernel failed"
    assert result.diagnostics["exception_type"] == "RuntimeError"
    assert "stale_saliency_update" not in result.diagnostics
    assert manager.saliency_params is old_manager_params
    assert holder.saliency_params is old_holder_params
    assert record.eval_record is old_eval_record
    assert trainer.get_state_generation() == generation_before


def test_saliency_identity_change_without_compute_target_does_not_commit() -> None:
    service, trainer, holder, record, old_eval_record = _saliency_recompute_service()
    manager = service.study.training_manager
    old_manager_params = manager.saliency_params
    old_holder_params = holder.saliency_params
    newer_eval_record = object()
    generation_before = trainer.get_state_generation()

    def invalidate_record_before_target(*_args, **_kwargs):
        record.eval_record = cast(Any, newer_eval_record)
        return None, None

    holder.get_eval_pair = MagicMock(side_effect=invalidate_record_before_target)

    result = service.execute(SaliencyCommand(method="Gradient"))

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.message == STALE_SALIENCY_MESSAGE
    assert result.diagnostics["stale_saliency_update"] is True
    assert result.diagnostics["state_preserved"] is True
    assert manager.saliency_params is old_manager_params
    assert holder.saliency_params is old_holder_params
    assert record.eval_record is newer_eval_record
    assert record.eval_record is not old_eval_record
    assert trainer.get_state_generation() == generation_before


def test_saliency_identity_change_at_publish_boundary_does_not_commit() -> None:
    service, trainer, holder, record, old_eval_record = _saliency_recompute_service()
    manager = service.study.training_manager
    old_manager_params = manager.saliency_params
    old_holder_params = holder.saliency_params
    newer_eval_record = object()
    prepared_eval_record = MagicMock()
    generation_before = trainer.get_state_generation()

    class MutateIdentityOnEnter:
        def __enter__(self) -> bool:
            record.eval_record = cast(Any, newer_eval_record)
            return True

        def __exit__(self, *_args: object) -> None:
            return None

    with (
        patch.object(
            Evaluator,
            "evaluate_with_saliency",
            return_value=prepared_eval_record,
        ),
        patch.object(
            trainer._state_tracker,
            "mutation_if_current",
            return_value=MutateIdentityOnEnter(),
        ),
    ):
        result = service.execute(SaliencyCommand(method="Gradient"))

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.message == STALE_SALIENCY_MESSAGE
    assert result.diagnostics["stale_saliency_update"] is True
    assert result.diagnostics["state_preserved"] is True
    assert manager.saliency_params is old_manager_params
    assert holder.saliency_params is old_holder_params
    assert record.eval_record is newer_eval_record
    assert record.eval_record is not old_eval_record
    assert record.eval_record is not prepared_eval_record
    assert trainer.get_state_generation() == generation_before


def test_saliency_oom_returns_recoverable_visualization_error_and_releases_cache():
    service, trainer, holder, record, old_eval_record = _saliency_recompute_service()
    manager = service.study.training_manager
    old_manager_params = manager.saliency_params
    old_holder_params = holder.saliency_params
    generation_before = trainer.get_state_generation()
    oom = torch.cuda.OutOfMemoryError("CUDA out of memory in saliency")

    with (
        patch.object(Evaluator, "evaluate_with_saliency", side_effect=oom),
        patch("XBrainLab.backend.training_manager.release_cuda_cache") as release_cache,
    ):
        result = service.execute(SaliencyCommand(method="Gradient"))

    assert result.failed is True
    assert result.error_type == ErrorType.VISUALIZATION
    assert result.recoverable is True
    assert result.message == SALIENCY_OOM_MESSAGE
    assert result.diagnostics["retryable"] is True
    assert result.diagnostics["resource"] == "cuda_memory"
    assert result.diagnostics["operation"] == "saliency_recomputation"
    assert result.diagnostics["state_preserved"] is True
    assert result.changed_state.error_changed is True
    assert result.changed_state.evaluation_changed is False
    assert result.changed_state.visualization_changed is False
    release_cache.assert_called_once_with(torch)
    assert manager.saliency_params is old_manager_params
    assert holder.saliency_params is old_holder_params
    assert record.eval_record is old_eval_record
    assert trainer.get_state_generation() == generation_before


def test_oversized_saliency_is_rejected_before_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _trainer, holder, _record, _old_eval_record = _saliency_recompute_service()
    epoch_count = 64
    shape_only_data = SimpleNamespace(
        shape=(epoch_count, 128, 4096),
        nbytes=epoch_count * 128 * 4096 * 4,
    )
    shape_only_epoch = SimpleNamespace(get_data=lambda: shape_only_data)
    holder.dataset = cast(
        Any,
        SimpleNamespace(
            get_epoch_data=lambda: shape_only_epoch,
            train_mask=np.zeros(epoch_count, dtype=bool),
            val_mask=np.zeros(epoch_count, dtype=bool),
            test_mask=np.ones(epoch_count, dtype=bool),
        ),
    )
    monkeypatch.setattr(
        ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 2 * 1024**3,
                "total_bytes": 4 * 1024**3,
                "used_bytes": 2 * 1024**3,
            }
        ),
    )

    with patch.object(
        Evaluator,
        "evaluate_with_saliency",
        side_effect=AssertionError("evaluator crossed saliency admission"),
    ) as evaluator:
        result = service.execute(
            SaliencyCommand(
                method="SmoothGrad",
                params={"nt_samples": 512},
            )
        )

    assert result.failed
    assert result.error_type == ErrorType.PRECONDITION
    assert result.recoverable
    assert "saliency" in result.message.lower()
    assert "ram" in result.message.lower()
    assert result.diagnostics["resource_preflight"]["risk_level"] == "blocking"
    evaluator.assert_not_called()


def test_reconfiguring_saliency_marks_visualization_changed() -> None:
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())
    first = service.execute(
        SaliencyCommand(method="SmoothGrad", params={"nt_samples": 2}),
    )

    second = service.execute(
        SaliencyCommand(method="SmoothGrad", params={"nt_samples": 7}),
    )

    assert first.ok is True
    assert second.ok is True
    assert second.changed_state.visualization_changed is True
    assert second.state.visualization.saliency_params["SmoothGrad"]["nt_samples"] == 7


def test_reapplying_montage_with_new_positions_marks_visualization_changed() -> None:
    class EpochWithMontage:
        def __init__(self) -> None:
            self.ch_names = ["Cz"]
            self.channel_position = [(0.0, 0.0, 0.0)]

        def set_channels(
            self,
            channels: list[str],
            positions: list[tuple[float, float, float]],
        ) -> None:
            self.ch_names = list(channels)
            self.channel_position = list(positions)

        def get_channel_names(self) -> list[str]:
            return list(self.ch_names)

    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = EpochWithMontage()
    first = service.execute(
        ApplyMontageCommand(
            channels=["Cz"],
            positions=[(0.0, 0.0, 0.0)],
            montage_name="custom-a",
        ),
    )

    second = service.execute(
        ApplyMontageCommand(
            channels=["Cz"],
            positions=[(0.1, 0.2, 0.3)],
            montage_name="custom-b",
        ),
    )

    assert first.ok is True
    assert second.ok is True
    assert second.changed_state.visualization_changed is True
    assert second.state.visualization.montage_channels == ["Cz"]
    assert second.state.visualization.montage_positions == [[0.1, 0.2, 0.3]]


def test_saliency_command_applies_exact_requested_params_to_authoritative_state():
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())

    result = service.execute(
        SaliencyCommand(
            method="SmoothGrad",
            params={
                "nt_samples": 2,
                "nt_samples_batch_size": 1,
                "stdevs": 1.0,
            },
        ),
    )

    assert result.ok is True
    assert result.diagnostics["requested_method"] == "SmoothGrad"
    params = result.diagnostics["params"]
    assert params == result.state.visualization.saliency_params
    assert params["_methods"] == ["SmoothGrad"]
    assert params["SmoothGrad"] == {
        "nt_samples": 2,
        "nt_samples_batch_size": 1,
        "stdevs": 1.0,
    }
    assert params["SmoothGrad_Squared"] == {
        "nt_samples": 5,
        "nt_samples_batch_size": None,
        "stdevs": 1.0,
    }


@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("IntegratedGradients", None),
        ("Gradient", {"nt_samples": 2}),
    ],
)
def test_saliency_command_returns_typed_validation_failure_for_unsupported_request(
    method: str,
    params: dict[str, object] | None,
) -> None:
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())

    result = service.execute(SaliencyCommand(method=method, params=params))

    assert result.failed is True
    assert result.error_type == ErrorType.VALIDATION
    assert result.state.visualization.saliency_configured is False
    assert result.state.visualization.saliency_params == {}


def test_command_result_classifies_unsupported_load(tmp_path):
    service = ApplicationService(Study())
    unsupported_path = tmp_path / "sample.unsupported"
    unsupported_path.write_text("not eeg", encoding="utf-8")

    result = service.execute(LoadDataCommand(paths=[str(unsupported_path)]))

    assert result.failed is True
    assert result.ok is False
    assert result.command_name == "load_data"
    assert result.error_type == ErrorType.UNSUPPORTED_FORMAT
    assert result.recoverable is True
    assert result.state.last_error is not None
    assert result.state.last_error.error_type == "unsupported_format"
    assert result.changed_state.error_changed is True


def test_successful_command_clears_previous_last_error():
    service = ApplicationService(Study())

    failed_result = service.execute(TrainCommand())
    assert failed_result.failed is True
    assert failed_result.state.last_error is not None

    reset_result = service.execute(ResetSessionCommand())

    assert reset_result.ok is True
    assert reset_result.state.last_error is None
    assert reset_result.changed_state.error_changed is True


def test_train_command_blocked_until_backend_ready():
    service = ApplicationService(Study())

    result = service.execute(TrainCommand())

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert (
        "Save a valid data splitting specification before training." in result.message
    )
    assert result.state.training.has_trainer is False


def test_train_command_requires_confirmation_before_long_running_start():
    service = ApplicationService(Study())
    _prepare_saved_training_split(service)
    service.study.set_model_holder(_valid_model_holder())
    service.study.set_training_option(_valid_training_option())
    service.training.start_training = MagicMock(return_value=1)

    result = service.execute(TrainCommand())
    _publish_mock_training_identity(service)
    confirmed = service.execute(TrainCommand(confirmed=True))

    assert result.failed is True
    assert result.error_type == ErrorType.CONFIRMATION_REQUIRED
    assert confirmed.ok is True
    service.training.start_training.assert_called_once()


class _SynchronousFailingTrainingPlan(TrainingPlanHolder):
    """Real Trainer-compatible plan that publishes one terminal failure."""

    def __init__(self, message: str) -> None:
        self.error: str | None = None
        self._message = message
        self._tracker: Any | None = None

    def bind_state_tracker(self, tracker: Any) -> None:
        self._tracker = tracker

    def get_name(self) -> str:
        return "Failing plan"

    def get_plans(self) -> list[Any]:
        return []

    def train(self) -> None:
        self.error = self._message

    def set_interrupt(self) -> None:
        return None

    def clear_interrupt(self) -> None:
        return None


@pytest.mark.parametrize(
    ("failure_message", "is_oom"),
    [
        ("CUDA out of memory during training. Reduce batch size.", True),
        ("training data loader failed", False),
    ],
)
def test_synchronous_train_command_returns_failed_result_for_plan_failure(
    failure_message: str,
    is_oom: bool,
) -> None:
    service = ApplicationService(Study())
    _prepare_saved_training_split(service)
    service.study.set_model_holder(_valid_model_holder())
    service.study.set_training_option(_valid_training_option())

    def install_failing_plan(
        *,
        force_update: bool = False,
        append: bool = False,
    ) -> None:
        del force_update, append
        service.study.trainer = Trainer(
            [cast(TrainingPlanHolder, _SynchronousFailingTrainingPlan(failure_message))]
        )

    service.study.generate_plan = install_failing_plan  # type: ignore[method-assign]

    result = service.execute(
        TrainCommand(
            confirmed=True,
            interactive=False,
            resource_preflight_confirmed=True,
        ),
    )

    assert result.ok is False
    assert result.failed is True
    assert result.error_type is ErrorType.TRAINING
    assert result.recoverable is True
    assert result.message == failure_message
    assert result.diagnostics["training_failed"] is True
    assert result.diagnostics["cuda_oom"] is is_oom
    assert result.state.training.progress_message == f"Error: {failure_message}"


def test_synchronous_training_failure_waits_for_exact_terminal_handoff(
    monkeypatch,
) -> None:
    """Worker failure is not returned until its monitor publication is terminal."""
    service = ApplicationService(Study())
    _prepare_saved_training_split(service)
    service.study.set_model_holder(_valid_model_holder())
    service.study.set_training_option(_valid_training_option())
    failure_message = "training data loader failed"
    plan = _SynchronousFailingTrainingPlan(failure_message)
    trainer = Trainer([cast(TrainingPlanHolder, plan)])
    plan_started = Event()
    release_plan = Event()
    monitor_waiting = Event()
    release_monitor_poll = Event()
    results: list[CommandResult] = []

    def install_failing_plan(
        *,
        force_update: bool = False,
        append: bool = False,
    ) -> None:
        del force_update, append
        service.study.training_manager.trainer = trainer

    def controlled_monitor_wait(_timeout: float | None = None) -> bool:
        monitor_waiting.set()
        assert release_monitor_poll.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return False

    def blocking_failure() -> None:
        plan_started.set()
        assert release_plan.wait(timeout=THREAD_WATCHDOG_SECONDS)
        plan.error = failure_message

    plan.train = blocking_failure  # type: ignore[method-assign]
    service.study.generate_plan = install_failing_plan  # type: ignore[method-assign]
    training_state = cast(Any, service.training)
    monkeypatch.setattr(
        training_state._shutdown_event,
        "wait",
        controlled_monitor_wait,
    )
    train_thread = Thread(
        target=lambda: results.append(
            service.execute(
                TrainCommand(
                    confirmed=True,
                    interactive=False,
                    resource_preflight_confirmed=True,
                )
            )
        ),
        name="synchronous-failing-train",
    )

    train_thread.start()
    assert plan_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    assert monitor_waiting.wait(timeout=THREAD_WATCHDOG_SECONDS)
    release_plan.set()
    worker = trainer.job_thread
    assert worker is not None
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)
    assert not worker.is_alive()
    returned_before_terminal_handoff = not train_thread.is_alive()

    release_monitor_poll.set()
    train_thread.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert returned_before_terminal_handoff is False
    assert not train_thread.is_alive()
    assert len(results) == 1
    assert results[0].failed is True
    assert results[0].error_type is ErrorType.TRAINING
    assert results[0].message == failure_message


def test_train_restart_cleanup_waits_before_command_lock_and_fails_recoverably(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    command_lock = Lock()
    service._command_lock = command_lock
    lock_was_free: list[bool] = []

    def wait_until_restart_safe(*, timeout: float | None = None) -> bool:
        assert timeout == 2.0
        acquired = command_lock.acquire(blocking=False)
        lock_was_free.append(acquired)
        if acquired:
            command_lock.release()
        return False

    monkeypatch.setattr(service.training, "is_training", lambda: False)
    monkeypatch.setattr(
        service.training,
        "wait_until_restart_safe",
        wait_until_restart_safe,
    )
    execute_with_lock = MagicMock()
    monkeypatch.setattr(service, "_execute_with_command_lock", execute_with_lock)

    result = service.execute(TrainCommand(confirmed=True, interactive=True))

    assert lock_was_free == [True]
    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.diagnostics["training_restart_pending"] is True
    execute_with_lock.assert_not_called()


def test_training_automation_commits_split_after_resource_admission() -> None:
    service = ApplicationService(Study())
    split_preparation: dict[str, object] = {
        "materialized": False,
        "cache_reused": True,
        "split_epoch_revision": 3,
        "split_specification_fingerprint": "saved-split-fingerprint",
        "split_summary": {"count": 1},
    }
    candidate = SimpleNamespace(datasets=(object(),))
    service.dataset_generation.prepare_saved_split_candidate = MagicMock(
        return_value=candidate
    )
    service.dataset_generation.commit_prepared_split = MagicMock(
        return_value=split_preparation
    )
    service.post_training_saliency = MagicMock()
    preflight = ResourcePreflightResult(issues=(), diagnostics={})
    service.training_commands.resolve_train_preflight = MagicMock(
        return_value=(preflight, False)
    )
    service.training_commands.start_train_after_preflight = MagicMock(
        return_value=("Training completed.", {}),
    )
    command = TrainCommand(append=False, interactive=False)

    result = service._handle_train_with_automation(command)

    assert result == (
        "Training completed.",
        {"split_preparation": split_preparation},
    )
    service.dataset_generation.prepare_saved_split_candidate.assert_called_once_with()
    service.training_commands.resolve_train_preflight.assert_called_once_with(
        command,
        datasets=candidate.datasets,
    )
    service.dataset_generation.commit_prepared_split.assert_called_once_with(candidate)
    service.training_commands.start_train_after_preflight.assert_called_once_with(
        command,
        preflight=preflight,
        receipt_reused=False,
        defer_synchronous_completion=True,
    )
    service.post_training_saliency.arm.assert_called_once_with(append=False)
    service.post_training_saliency.cancel.assert_not_called()


def test_wait_for_background_tasks_waits_for_submission_then_saliency_job() -> None:
    service = ApplicationService(Study())
    call_order: list[str] = []
    service.training.wait_for_terminal_notification = MagicMock(
        side_effect=lambda generation=None, timeout=None: (
            call_order.append(f"monitor_terminal:{generation}") or True
        ),
    )
    service.publication_lifecycle.publish_training_terminal_state = MagicMock(
        side_effect=lambda: call_order.append("terminal_reconcile") or True,
    )
    service.training_publications.wait_for_training_delivery = MagicMock(
        side_effect=lambda timeout=None: call_order.append("training_terminal") or True,
    )
    service.post_training_saliency.wait_for_idle = MagicMock(
        side_effect=lambda timeout=None: call_order.append("submission") or True,
    )
    service.training_runtime.wait_for_saliency_job = MagicMock(
        side_effect=lambda timeout=None: call_order.append("saliency") or True,
    )
    service.training_runtime.wait_for_saliency_delivery = MagicMock(
        side_effect=lambda timeout=None: call_order.append("manager_terminal") or True,
    )
    service.training_publications.wait_for_saliency_delivery = MagicMock(
        side_effect=lambda timeout=None: call_order.append("saliency_terminal") or True,
    )

    assert (
        service.wait_for_background_tasks(
            timeout=1.0,
            training_handoff_generation=23,
        )
        is True
    )

    assert call_order == [
        "monitor_terminal:23",
        "terminal_reconcile",
        "training_terminal",
        "submission",
        "saliency",
        "manager_terminal",
        "saliency_terminal",
    ]
    monitor_terminal_timeout = (
        service.training.wait_for_terminal_notification.call_args.kwargs["timeout"]
    )
    training_terminal_timeout = (
        service.training_publications.wait_for_training_delivery.call_args.kwargs[
            "timeout"
        ]
    )
    submission_timeout = service.post_training_saliency.wait_for_idle.call_args.kwargs[
        "timeout"
    ]
    saliency_timeout = service.training_runtime.wait_for_saliency_job.call_args.kwargs[
        "timeout"
    ]
    assert (
        0.0
        <= saliency_timeout
        <= submission_timeout
        <= training_terminal_timeout
        <= monitor_terminal_timeout
        <= 1.0
    )


def test_wait_for_background_tasks_retries_terminal_reconciliation_after_empty_ledger(
    monkeypatch,
) -> None:
    """A transient monitor refresh failure cannot look like an idle success."""
    service = ApplicationService(Study())
    reconcile = MagicMock(side_effect=[False, True])
    monkeypatch.setattr(
        service.publication_lifecycle,
        "publish_training_terminal_state",
        reconcile,
    )

    assert service.wait_for_background_tasks(timeout=1.0) is True

    assert reconcile.call_count == 2


def test_wait_for_background_tasks_rejects_persistent_terminal_reconciliation_failure(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    reconcile = MagicMock(return_value=False)
    monkeypatch.setattr(
        service.publication_lifecycle,
        "publish_training_terminal_state",
        reconcile,
    )

    assert service.wait_for_background_tasks(timeout=1.0) is False

    assert reconcile.call_count == 2


def test_wait_for_background_tasks_stops_when_submission_does_not_finish() -> None:
    service = ApplicationService(Study())
    service.post_training_saliency.wait_for_idle = MagicMock(return_value=False)
    service.training_runtime.wait_for_saliency_job = MagicMock(return_value=True)

    assert service.wait_for_background_tasks(timeout=0.0) is False

    service.training_runtime.wait_for_saliency_job.assert_not_called()


def test_synchronous_train_waits_for_application_background_tasks() -> None:
    service = ApplicationService(Study())
    expected = MagicMock(ok=True)
    expected.diagnostics = {"training_handoff_generation": 7}
    service._execute_serialized = MagicMock(return_value=expected)
    service.wait_for_background_tasks = MagicMock(return_value=True)

    result = service.execute(TrainCommand(interactive=False))

    assert result is expected
    service.wait_for_background_tasks.assert_called_once_with(
        timeout=300.0, training_handoff_generation=7
    )


def test_synchronous_train_waits_for_real_monitor_terminal_handoff(monkeypatch) -> None:
    """Worker exit alone is not completion until monitor callbacks have returned."""
    service = ApplicationService(Study())
    _prepare_saved_training_split(service)
    service.study.set_model_holder(_valid_model_holder())
    service.study.set_training_option(_valid_training_option())
    plan = _SlowCancellationPlan()
    trainer = Trainer([cast(TrainingPlanHolder, plan)])
    monitor_waiting = Event()
    release_monitor_poll = Event()
    terminal_events: list[TrainingLifecycleEvent] = []
    results: list[CommandResult] = []
    failures: list[BaseException] = []

    def install_plan(
        *,
        force_update: bool = False,
        append: bool = False,
    ) -> None:
        del force_update, append
        service.study.training_manager.trainer = trainer

    def controlled_monitor_wait(_timeout: float | None = None) -> bool:
        monitor_waiting.set()
        assert release_monitor_poll.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return False

    def execute_train() -> None:
        try:
            results.append(
                service.execute(
                    TrainCommand(
                        confirmed=True,
                        interactive=False,
                        resource_preflight_confirmed=True,
                    )
                )
            )
        except BaseException as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    service.study.generate_plan = install_plan  # type: ignore[method-assign]
    training_state = cast(Any, service.training)
    monkeypatch.setattr(
        training_state._shutdown_event,
        "wait",
        controlled_monitor_wait,
    )
    service.training.subscribe("training_terminal_published", terminal_events.append)
    train_thread = Thread(target=execute_train, name="synchronous-train")

    train_thread.start()
    assert plan.started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    assert monitor_waiting.wait(timeout=THREAD_WATCHDOG_SECONDS)
    plan.release.set()
    worker = trainer.job_thread
    assert worker is not None
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)
    returned_before_terminal_handoff = not train_thread.is_alive()
    release_monitor_poll.set()
    train_thread.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert returned_before_terminal_handoff is False
    assert not train_thread.is_alive()
    assert failures == []
    assert len(results) == 1
    assert results[0].ok is True
    assert isinstance(results[0].diagnostics["training_handoff_generation"], int)
    assert len(terminal_events) == 1


def test_parallel_services_keep_synchronous_training_handoffs_isolated() -> None:
    """Deferred waits may overlap without mixing either run's evidence."""
    study = Study()
    first_service = ApplicationService(study)
    second_service = ApplicationService(study)
    state = first_service.get_view_publication().state
    first_waiting = Event()
    release_first = Event()
    second_completed = Event()
    results: dict[str, CommandResult] = {}
    waited_generations: dict[str, list[int | None]] = {
        "first": [],
        "second": [],
    }

    def started_result(generation: int, identity: str) -> CommandResult:
        return CommandResult.success_result(
            command_name=CommandName.TRAIN.value,
            message="Training started.",
            state=state,
            changed_state=ChangedState(training_changed=True),
            diagnostics={
                "synchronous_completion_deferred": True,
                "training_handoff_generation": generation,
                "training_trainer_identity": identity,
            },
        )

    def complete_first(started: CommandResult) -> CommandResult:
        assert started.diagnostics["training_handoff_generation"] == 41
        assert started.diagnostics["training_trainer_identity"] == "trainer-A"
        assert study._synchronous_training_lifecycle_lock.locked() is False
        first_waiting.set()
        assert release_first.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return replace(
            started,
            message="Training A completed.",
            diagnostics={
                "training_handoff_generation": 41,
                "training_trainer_identity": "trainer-A",
            },
        )

    def complete_second(started: CommandResult) -> CommandResult:
        assert started.diagnostics["training_handoff_generation"] == 42
        assert started.diagnostics["training_trainer_identity"] == "trainer-B"
        assert study._synchronous_training_lifecycle_lock.locked() is False
        second_completed.set()
        return replace(
            started,
            message="Training B completed.",
            diagnostics={
                "training_handoff_generation": 42,
                "training_trainer_identity": "trainer-B",
            },
        )

    def background_wait(owner: str):
        def wait(
            timeout: float | None = None,
            *,
            training_handoff_generation: int | None = None,
        ) -> bool:
            assert timeout is not None and timeout > 0
            waited_generations[owner].append(training_handoff_generation)
            return True

        return wait

    first_service._execute_serialized = MagicMock(  # type: ignore[method-assign]
        return_value=started_result(41, "trainer-A")
    )
    second_service._execute_serialized = MagicMock(  # type: ignore[method-assign]
        return_value=started_result(42, "trainer-B")
    )
    first_service.synchronous_training_lifecycle.complete_deferred = complete_first  # type: ignore[method-assign]
    second_service.synchronous_training_lifecycle.complete_deferred = complete_second  # type: ignore[method-assign]
    first_service.wait_for_background_tasks = background_wait("first")  # type: ignore[method-assign]
    second_service.wait_for_background_tasks = background_wait("second")  # type: ignore[method-assign]

    first = Thread(
        target=lambda: results.__setitem__(
            "first",
            first_service.execute(TrainCommand(interactive=False)),
        ),
        name="first-synchronous-train",
    )
    second = Thread(
        target=lambda: results.__setitem__(
            "second",
            second_service.execute(TrainCommand(interactive=False)),
        ),
        name="second-synchronous-train",
    )
    first.start()
    assert first_waiting.wait(timeout=THREAD_WATCHDOG_SECONDS)
    second.start()
    assert second_completed.wait(timeout=THREAD_WATCHDOG_SECONDS)
    release_first.set()
    first.join(timeout=THREAD_WATCHDOG_SECONDS)
    second.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not first.is_alive()
    assert not second.is_alive()
    assert results["first"].diagnostics["training_trainer_identity"] == "trainer-A"
    assert results["second"].diagnostics["training_trainer_identity"] == "trainer-B"
    assert waited_generations == {"first": [41], "second": [42]}


def test_close_wakes_synchronous_train_waiting_for_terminal_handoff() -> None:
    service = ApplicationService(Study())
    state = service.get_view_publication().state
    wait_entered = Event()
    release_wait = Event()
    close_done = Event()
    cancelled: list[str] = []
    train_results: list[CommandResult] = []
    service._execute_serialized = MagicMock(
        return_value=CommandResult.success_result(
            command_name=CommandName.TRAIN.value,
            message="Training completed.",
            state=state,
            changed_state=ChangedState(training_changed=True),
            diagnostics={"training_handoff_generation": 51},
        )
    )

    def wait_for_terminal(
        generation: int | None = None,
        *,
        timeout: float | None = None,
    ) -> bool:
        del timeout
        assert generation == 51
        wait_entered.set()
        assert release_wait.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return False

    def cancel_terminal_waits(reason: str) -> None:
        cancelled.append(reason)
        release_wait.set()

    service.training.wait_for_terminal_notification = wait_for_terminal  # type: ignore[method-assign]
    service.training.cancel_terminal_notification_waits = cancel_terminal_waits  # type: ignore[attr-defined,method-assign]
    train_thread = Thread(
        target=lambda: train_results.append(
            service.execute(TrainCommand(interactive=False))
        ),
        name="closing-synchronous-train",
    )

    def close_service() -> None:
        service.close()
        close_done.set()

    close_thread = Thread(target=close_service, name="application-service-close")
    train_thread.start()
    assert wait_entered.wait(timeout=THREAD_WATCHDOG_SECONDS)
    close_thread.start()
    closed_without_manual_release = close_done.wait(timeout=0.5)
    if not closed_without_manual_release:
        release_wait.set()
    close_thread.join(timeout=THREAD_WATCHDOG_SECONDS)
    train_thread.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert closed_without_manual_release is True
    assert cancelled == ["Application service is closing."]
    assert not close_thread.is_alive()
    assert not train_thread.is_alive()
    assert len(train_results) == 1
    assert train_results[0].failed is True


def test_close_stops_worker_blocking_synchronous_training_completion() -> None:
    service = ApplicationService(Study())
    state = service.get_view_publication().state
    worker_wait_entered = Event()
    worker_released = Event()
    close_done = Event()
    stop_timeouts: list[float | None] = []
    train_results: list[CommandResult] = []
    service._execute_serialized = MagicMock(
        return_value=CommandResult.success_result(
            command_name=CommandName.TRAIN.value,
            message="Training started.",
            state=state,
            changed_state=ChangedState(training_changed=True),
            diagnostics={
                "synchronous_completion_deferred": True,
                "training_handoff_generation": 52,
                "training_trainer_identity": "trainer-close-test",
            },
        )
    )

    def wait_for_worker(
        *,
        expected_trainer_identity: str | None = None,
        timeout: float | None = None,
    ) -> bool:
        assert expected_trainer_identity == "trainer-close-test"
        assert timeout is not None and timeout > 0
        worker_wait_entered.set()
        return worker_released.wait(timeout=THREAD_WATCHDOG_SECONDS)

    def stop_worker(*, wait_timeout: float | None = None) -> bool:
        stop_timeouts.append(wait_timeout)
        worker_released.set()
        return True

    service.training_runtime.wait_for_training_completion = wait_for_worker  # type: ignore[method-assign]
    service.training_runtime.stop_training = stop_worker  # type: ignore[method-assign]
    service.training.wait_for_terminal_notification = MagicMock(return_value=False)  # type: ignore[method-assign]
    service.training.cancel_terminal_notification_waits = MagicMock()  # type: ignore[attr-defined,method-assign]
    service._retry_synchronous_training_terminal_delivery = MagicMock(  # type: ignore[method-assign]
        return_value=False
    )

    train_thread = Thread(
        target=lambda: train_results.append(
            service.execute(TrainCommand(interactive=False))
        ),
        name="worker-blocked-synchronous-train",
    )
    close_thread = Thread(
        target=lambda: (service.close(), close_done.set()),
        name="application-service-close",
    )
    train_thread.start()
    assert worker_wait_entered.wait(timeout=THREAD_WATCHDOG_SECONDS)
    close_thread.start()
    closed_without_manual_release = close_done.wait(timeout=0.5)
    if not closed_without_manual_release:
        worker_released.set()
    close_thread.join(timeout=THREAD_WATCHDOG_SECONDS)
    train_thread.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert closed_without_manual_release is True
    assert stop_timeouts and stop_timeouts[0] is not None
    assert not close_thread.is_alive()
    assert not train_thread.is_alive()
    assert len(train_results) == 1
    assert train_results[0].failed is True


def test_close_does_not_commit_while_real_synchronous_worker_ignores_stop() -> None:
    service = ApplicationService(Study())
    _prepare_saved_training_split(service)
    service.study.set_model_holder(_valid_model_holder())
    service.study.set_training_option(_valid_training_option())
    plan = _SlowCancellationPlan()
    trainer = Trainer([cast(TrainingPlanHolder, plan)])
    results: list[CommandResult] = []

    def install_plan(
        *,
        force_update: bool = False,
        append: bool = False,
    ) -> None:
        del force_update, append
        service.study.training_manager.trainer = trainer

    service.study.generate_plan = install_plan  # type: ignore[method-assign]
    train_thread = Thread(
        target=lambda: results.append(
            service.execute(
                TrainCommand(
                    confirmed=True,
                    interactive=False,
                    resource_preflight_confirmed=True,
                )
            )
        ),
        name="stubborn-synchronous-train",
    )

    train_thread.start()
    assert plan.started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    try:
        service.close()
        closed_while_worker_was_alive = service.is_closed
    finally:
        plan.release.set()
        train_thread.join(timeout=THREAD_WATCHDOG_SECONDS)
        if not service.is_closed:
            service.close()

    assert plan.interrupt_requested.is_set()
    assert closed_while_worker_was_alive is False
    assert not train_thread.is_alive()
    assert len(results) == 1


def test_close_stop_exception_keeps_service_open_and_runtime_owned(monkeypatch) -> None:
    study = Study()
    service = get_application_service(study)
    original_stop = service.training_runtime.stop_training

    def fail_stop(*, wait_timeout: float | None = None) -> bool:
        del wait_timeout
        raise RuntimeError("stop failed")

    monkeypatch.setattr(service.training_runtime, "stop_training", fail_stop)

    service.close()

    assert service.is_closed is False
    assert get_application_service(study) is service

    monkeypatch.setattr(service.training_runtime, "stop_training", original_stop)
    service.close()


def test_close_waits_for_synchronous_completion_publication_to_quiesce(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    _prepare_saved_training_split(service)
    service.study.set_model_holder(_valid_model_holder())
    service.study.set_training_option(_valid_training_option())
    plan = _SlowCancellationPlan()
    trainer = Trainer([cast(TrainingPlanHolder, plan)])
    completion_wait_entered = Event()
    release_completion_wait = Event()
    close_done = Event()
    callback_states: list[bool] = []
    results: list[CommandResult] = []
    original_wait = service.training_runtime.wait_for_training_completion

    def install_plan(
        *,
        force_update: bool = False,
        append: bool = False,
    ) -> None:
        del force_update, append
        service.study.training_manager.trainer = trainer

    def delayed_completion_wait(
        *,
        expected_trainer_identity: str | None = None,
        timeout: float | None = None,
    ) -> bool:
        completion_wait_entered.set()
        assert release_completion_wait.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return original_wait(
            expected_trainer_identity=expected_trainer_identity,
            timeout=timeout,
        )

    def observe_publication(_publication: object) -> bool:
        callback_states.append(service.is_closed)
        return True

    service.study.generate_plan = install_plan  # type: ignore[method-assign]
    monkeypatch.setattr(
        service.training_runtime,
        "wait_for_training_completion",
        delayed_completion_wait,
    )
    service.subscribe(
        APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
        observe_publication,
    )
    train_thread = Thread(
        target=lambda: results.append(
            service.execute(
                TrainCommand(
                    confirmed=True,
                    interactive=False,
                    resource_preflight_confirmed=True,
                )
            )
        ),
        name="late-synchronous-completion",
    )
    close_thread = Thread(
        target=lambda: (service.close(), close_done.set()),
        name="close-during-synchronous-completion",
    )

    train_thread.start()
    assert plan.started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    plan.release.set()
    assert completion_wait_entered.wait(timeout=THREAD_WATCHDOG_SECONDS)
    close_thread.start()
    closed_while_completion_was_blocked = close_done.wait(timeout=0.25)
    release_completion_wait.set()
    train_thread.join(timeout=THREAD_WATCHDOG_SECONDS)
    close_thread.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert closed_while_completion_was_blocked is False
    assert close_done.is_set()
    assert service.is_closed is True
    assert not train_thread.is_alive()
    assert not close_thread.is_alive()
    assert len(results) == 1
    assert all(closed is False for closed in callback_states)


def test_close_fences_train_queued_before_lifecycle_admission() -> None:
    """A Train already approaching admission cannot pass a queued close."""

    class _FifoLifecycleLock:
        def __init__(self) -> None:
            self._condition = Condition()
            self._next_ticket = 0
            self._serving = 0
            self._held = False
            self.close_queued = Event()
            self.train_queued = Event()

        def __enter__(self) -> _FifoLifecycleLock:
            with self._condition:
                ticket = self._next_ticket
                self._next_ticket += 1
                if current_thread().name == "application-service-close":
                    self.close_queued.set()
                if current_thread().name == "queued-synchronous-train":
                    self.train_queued.set()
                admitted = self._condition.wait_for(
                    lambda: ticket == self._serving and not self._held,
                    timeout=THREAD_WATCHDOG_SECONDS,
                )
                assert admitted and ticket == self._serving and not self._held
                self._held = True
            return self

        def __exit__(self, *_args: Any) -> None:
            with self._condition:
                self._held = False
                self._serving += 1
                self._condition.notify_all()

    service = ApplicationService(Study())
    lifecycle_lock = _FifoLifecycleLock()
    service._synchronous_training_lifecycle_lock = cast(Any, lifecycle_lock)
    service.shutdown_lifecycle._synchronous_training_lifecycle_lock = cast(
        Any,
        lifecycle_lock,
    )
    close_done = Event()
    train_results: list[CommandResult] = []
    service._execute_serialized = MagicMock()  # type: ignore[method-assign]
    queued_train = Thread(
        target=lambda: train_results.append(
            service.execute(TrainCommand(interactive=False))
        ),
        name="queued-synchronous-train",
    )

    def close_service() -> None:
        service.close()
        close_done.set()

    closing = Thread(target=close_service, name="application-service-close")
    lifecycle_lock.__enter__()
    try:
        closing.start()
        assert lifecycle_lock.close_queued.wait(timeout=THREAD_WATCHDOG_SECONDS)
        assert service.shutdown_lifecycle.is_shutdown_fenced is True
        queued_train.start()
        assert lifecycle_lock.train_queued.wait(timeout=THREAD_WATCHDOG_SECONDS)
    finally:
        lifecycle_lock.__exit__(None, None, None)

    assert close_done.wait(timeout=THREAD_WATCHDOG_SECONDS)
    queued_train.join(timeout=THREAD_WATCHDOG_SECONDS)
    closing.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not queued_train.is_alive()
    assert not closing.is_alive()
    assert len(train_results) == 1
    assert train_results[0].failed is True
    assert train_results[0].diagnostics["application_service_closed"] is True
    service._execute_serialized.assert_not_called()


def test_synchronous_train_reports_incomplete_background_delivery() -> None:
    service = ApplicationService(Study())
    expected = CommandResult.success_result(
        command_name=CommandName.TRAIN.value,
        message="Training completed.",
        state=service.get_view_publication().state,
        changed_state=ChangedState(),
        diagnostics={
            "training_completed": True,
            "training_handoff_generation": 61,
        },
    )
    service._execute_serialized = MagicMock(return_value=expected)
    service.wait_for_background_tasks = MagicMock(return_value=False)

    result = service.execute(TrainCommand(interactive=False))

    assert result.failed is True
    assert result.error_type is ErrorType.INTERNAL
    assert result.recoverable is True
    assert result.diagnostics["background_delivery_incomplete"] is True
    assert result.diagnostics["training_completed"] is True
    service.wait_for_background_tasks.assert_called_once_with(
        timeout=300.0, training_handoff_generation=61
    )


def test_interactive_train_returns_without_waiting_for_background_tasks() -> None:
    service = ApplicationService(Study())
    expected = MagicMock(ok=True)
    service._execute_serialized = MagicMock(return_value=expected)
    service.wait_for_background_tasks = MagicMock(return_value=True)

    result = service.execute(TrainCommand(interactive=True))

    assert result is expected
    service.wait_for_background_tasks.assert_not_called()


def test_non_query_command_retries_retained_training_terminal_delivery() -> None:
    service = ApplicationService(Study())
    expected = MagicMock(ok=True)
    service._execute_serialized = MagicMock(return_value=expected)
    service.training_publications.retry_training_terminal_delivery = MagicMock(
        return_value=True
    )

    result = service.execute(TrainCommand(interactive=True))

    assert result is expected
    service.training_publications.retry_training_terminal_delivery.assert_called_once_with()


def test_published_state_query_does_not_retry_training_terminal_delivery() -> None:
    service = ApplicationService(Study())
    service.training_publications.retry_training_terminal_delivery = MagicMock(
        return_value=True
    )

    result = service.execute(QueryStateCommand(query="state"))

    assert result.ok is True
    service.training_publications.retry_training_terminal_delivery.assert_not_called()


def test_train_resource_warning_is_returned_before_training_starts(monkeypatch):
    service = ApplicationService(Study())
    option = _valid_training_option(batch_size=4)
    _prepare_saved_training_split(service)
    service.study.set_model_holder(_valid_model_holder())
    service.study.set_training_option(option)
    service.training.start_training = MagicMock(return_value=1)
    monkeypatch.setattr(
        "XBrainLab.backend.application.resource_guard.available_ram_bytes",
        lambda: 200_000_000,
    )

    warning = service.execute(TrainCommand(confirmed=True))

    assert warning.failed is True
    assert warning.error_type == ErrorType.CONFIRMATION_REQUIRED
    assert warning.diagnostics["resource_preflight"]["risk_level"] == "warning"
    receipt = warning.diagnostics["resource_preflight"]["confirmation_token"]
    assert receipt
    service.training.start_training.assert_not_called()

    _publish_mock_training_identity(service)
    continued = service.execute(
        TrainCommand(
            confirmed=True,
            resource_preflight_confirmed=True,
            resource_preflight_token=receipt,
        ),
    )

    assert continued.ok is True
    assert continued.diagnostics["resource_preflight"]["risk_level"] == "warning"
    service.training.start_training.assert_called_once()


def test_every_declared_command_returns_result_envelope():
    service = ApplicationService(Study())
    commands = [
        LoadDataCommand(paths=[]),
        AttachLabelsCommand(mapping={}),
        ImportLabelsCommand(plan=LabelImportPlan()),
        UpdateMetadataCommand(index=0, subject="S01"),
        ApplySmartParseCommand(results={"/tmp/sample.fif": ("S01", "001")}),
        RemoveFilesCommand(indices=[0]),
        PreprocessCommand(
            operation=PreprocessOperation.BANDPASS,
            low_freq=1,
            high_freq=40,
        ),
        CreateEpochCommand(t_min=0, t_max=1),
        SaveDatasetSplitCommand(),
        ClearDatasetsCommand(),
        ConfigureTrainingCommand(model_name="EEGNet"),
        TrainCommand(),
        DiscardTrainingPreparationCommand(),
        EvaluateCommand(),
        VisualizeCommand(),
        SaliencyCommand(),
        StopTrainingCommand(),
        ClearTrainingHistoryCommand(),
        ScanSourceCommand(source_path=""),
        ReviewInterpretationCommand(source_path=""),
        PreviewInterpretationCommand(),
        ValidateInterpretationCommand(),
        ApplyInterpretationCommand(),
        SaveInterpretationRecipeCommand(recipe_path=""),
        ReloadInterpretationRecipeCommand(recipe_path=""),
        ApplyMontageCommand(channels=["Cz"], positions=[(0.0, 0.0, 0.0)]),
        QueryStateCommand(),
        ResetPreprocessCommand(),
        ResetSessionCommand(),
        NewSessionCommand(),
    ]

    seen = set()
    for command in commands:
        result = service.execute(command)
        seen.add(result.command_name)
        assert result.command_name
        assert result.status.value in {"ok", "failed"}
        assert result.state is not None
        assert result.changed_state is not None

    assert seen == {name.value for name in CommandName}


def test_raw_mutation_commands_block_after_epoch_without_side_effects():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = MagicMock()
    service.dataset_state.remove_files = MagicMock()

    result = service.execute(RemoveFilesCommand(indices=[0]))

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert "Reset the session" in result.message
    service.dataset_state.remove_files.assert_not_called()


def test_apply_interpretation_blocks_after_epoch_without_import_side_effect(
    tmp_path,
):
    source_dir = tmp_path / "new_source"
    source_dir.mkdir()
    eeg_path = source_dir / "sub-02_task-mi_raw.fif"
    eeg_path.write_bytes(b"not loaded during scan")
    service = ApplicationService(Study())
    service.dataset.import_files = MagicMock(return_value=(1, []))

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(PreviewInterpretationCommand())
    validation = service.execute(ValidateInterpretationCommand())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = MagicMock()
    service.get_state()
    policy = service.get_capabilities()

    result = service.execute(ApplyInterpretationCommand(confirmed=True))

    assert validation.ok is True
    assert policy.get(CommandName.APPLY_INTERPRETATION).available is False
    assert "Reset the session" in " ".join(
        policy.get(CommandName.APPLY_INTERPRETATION).reasons,
    )
    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert "Reset the session" in result.message
    service.dataset.import_files.assert_not_called()


def test_configure_dataset_split_save_preserves_existing_dataset_without_confirmation():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = _positive_epoch_data()
    service.study.data_manager.datasets = [MagicMock()]

    result = service.execute(
        SaveDatasetSplitCommand(),
    )

    assert result.ok is True
    assert service.study.data_manager.datasets[0] is not None
    capability = service.get_capabilities().get(CommandName.CONFIGURE_DATASET_SPLIT)
    assert capability.enabled is True
    assert capability.requires_confirmation is False
    assert capability.destructive is False


def test_configure_dataset_split_save_is_non_destructive_with_existing_generator():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = _positive_epoch_data()
    service.study.data_manager.dataset_generator = MagicMock()
    service.get_state()

    capability = service.get_capabilities().get(CommandName.CONFIGURE_DATASET_SPLIT)

    assert capability.enabled is True
    assert capability.requires_confirmation is False
    assert capability.destructive is False


def test_configure_dataset_split_command_has_no_replacement_confirmation_field():
    service = ApplicationService(Study())
    raw = _raw_mock()
    existing_dataset = MagicMock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = _positive_epoch_data()
    service.study.data_manager.datasets = [existing_dataset]

    result = service.execute(SaveDatasetSplitCommand())

    assert result.ok is True
    assert service.study.data_manager.datasets == [existing_dataset]


def test_deferred_dataset_replacement_failure_restores_previous_training_state(
    monkeypatch,
):
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    epoch_data = _positive_epoch_data()
    service.study.data_manager.epoch_data = epoch_data

    old_dataset = MagicMock(name="old_dataset")
    old_dataset.get_name.return_value = "existing_split"
    old_dataset.train_mask = np.array([True, False, False])
    old_dataset.val_mask = np.array([False, True, False])
    old_dataset.test_mask = np.array([False, False, True])
    old_generator = MagicMock(name="old_generator")
    old_trainer = Trainer([])
    old_history = [MagicMock(name="completed_training_record")]
    old_history[0].get_plans.return_value = []
    old_trainer.training_plan_holders = cast(Any, list(old_history))
    service.study.data_manager.datasets = [old_dataset]
    service.study.data_manager.dataset_generator = old_generator
    service.study.training_manager.trainer = old_trainer

    replacement_dataset = MagicMock(name="replacement_dataset")
    replacement_dataset.get_name.return_value = "replacement_split"
    replacement_dataset.get_epoch_data.return_value = epoch_data
    replacement_dataset.train_mask = np.array([True, True, False, False, False, False])
    replacement_dataset.val_mask = np.array([False, False, True, True, False, False])
    replacement_dataset.test_mask = np.array([False, False, False, False, True, True])
    replacement_generator = MagicMock(name="replacement_generator")
    replacement_generator.prepare_result.return_value = [replacement_dataset]
    partial_dataset = MagicMock(name="partial_dataset")
    partial_generator = MagicMock(name="partial_generator")

    def fail_after_partial_publication(_datasets, _generator):
        service.study.data_manager.datasets = [partial_dataset]
        service.study.data_manager.dataset_generator = partial_generator
        raise RuntimeError("dataset publication failed")

    service.study.get_datasets_generator = MagicMock(
        return_value=replacement_generator,
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.dataset_generation_service.audit_dataset_splits",
        lambda *_args, **_kwargs: SimpleNamespace(
            ok=True,
            dataset_count=1,
            issues=[],
        ),
    )
    service.dataset_generation.pipeline_transaction.publish_datasets = MagicMock(
        side_effect=fail_after_partial_publication,
    )

    saved = service.execute(
        SaveDatasetSplitCommand(),
    )

    assert saved.ok is True
    assert service.study.data_manager.datasets == [old_dataset]
    assert service.study.data_manager.dataset_generator is old_generator
    assert service.study.training_manager.trainer is old_trainer
    candidate = service.dataset_generation.prepare_saved_split_candidate()
    with pytest.raises(ApplicationError) as exc_info:
        service.dataset_generation.commit_prepared_split(candidate)

    assert service.study.data_manager.datasets == [old_dataset]
    assert service.study.data_manager.dataset_generator is old_generator
    assert service.study.training_manager.trainer is old_trainer
    assert old_trainer.get_training_plan_holders() == old_history
    assert exc_info.value.diagnostics["state_preserved"] is True
    assert exc_info.value.diagnostics["replacement_mode"] == "replace_existing"


def test_configure_dataset_split_blocks_while_training_is_running():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = _positive_epoch_data()
    service.study.training_manager.is_training = MagicMock(return_value=True)

    result = service.execute(SaveDatasetSplitCommand())

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert "Stop training before changing data splitting." in result.message


def test_clear_datasets_blocks_while_training_is_running():
    service = ApplicationService(Study())
    service.study.data_manager.datasets = [MagicMock()]
    service.study.training_manager.is_training = MagicMock(return_value=True)
    service.training.clean_datasets = MagicMock()

    result = service.execute(ClearDatasetsCommand(confirmed=True))

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert "Stop training before clearing generated datasets." in result.message
    service.training.clean_datasets.assert_not_called()


def test_training_split_preparation_fails_for_empty_or_leaking_splits():
    service = ApplicationService(Study())
    epoch_data = _positive_epoch_data()
    service.study.data_manager.epoch_data = epoch_data
    leaking = MagicMock()
    leaking.get_name.return_value = "bad_split"
    leaking.train_mask = np.array([True, True, False, False, False, False])
    leaking.val_mask = np.array([False, True, False, False, False, False])
    leaking.test_mask = np.zeros(6, dtype=bool)
    leaking.get_epoch_data.return_value = epoch_data
    generator = MagicMock()
    generator.prepare_result.return_value = [leaking]
    service.study.get_datasets_generator = MagicMock(return_value=generator)

    saved = service.execute(
        SaveDatasetSplitCommand(split_strategy="trial"),
    )

    assert saved.ok is True
    with pytest.raises(ApplicationError) as exc_info:
        service.dataset_generation.prepare_saved_split_candidate()

    error = exc_info.value
    state = service.get_state()
    assert error.error_type == ErrorType.DATA_MISMATCH
    assert "split audit" in error.message
    assert state.dataset.available is False
    assert state.dataset.generator_exists is False
    assert state.training.has_trainer is False
    assert error.diagnostics["state_preserved"] is True
    assert error.diagnostics["split_audit"]["ok"] is False
    assert any(
        "split is empty" in issue["message"]
        for issue in error.diagnostics["split_audit"]["issues"]
    )


def test_training_split_preparation_rolls_back_stale_apply(monkeypatch):
    service = ApplicationService(Study())
    epoch_data = _positive_epoch_data()
    service.study.data_manager.epoch_data = epoch_data
    replacement_dataset = MagicMock(name="replacement_dataset")
    replacement_dataset.get_name.return_value = "replacement_split"
    replacement_dataset.get_epoch_data.return_value = epoch_data
    replacement_dataset.train_mask = np.array([True, True, False, False, False, False])
    replacement_dataset.val_mask = np.array([False, False, True, True, False, False])
    replacement_dataset.test_mask = np.array([False, False, False, False, True, True])
    replacement_trainer = Trainer([])

    def prepare_after_new_trainer_started():
        service.study.training_manager.trainer = replacement_trainer
        return [replacement_dataset]

    generator = MagicMock()
    generator.prepare_result.side_effect = prepare_after_new_trainer_started
    service.study.get_datasets_generator = MagicMock(return_value=generator)
    monkeypatch.setattr(
        "XBrainLab.backend.application.dataset_generation_service.audit_dataset_splits",
        lambda *_args, **_kwargs: SimpleNamespace(
            ok=True,
            dataset_count=1,
            issues=[],
        ),
    )

    saved = service.execute(SaveDatasetSplitCommand())

    assert saved.ok is True
    candidate = service.dataset_generation.prepare_saved_split_candidate()
    with pytest.raises(ApplicationError):
        service.dataset_generation.commit_prepared_split(candidate)
    state = service.get_state()
    assert state.dataset.available is False
    assert state.dataset.generator_exists is False
    assert state.training.has_trainer is True
    assert service.study.training_manager.trainer is replacement_trainer


def test_training_split_preparation_audits_custom_trial_protocol():
    service = ApplicationService(Study())
    epoch_data = _positive_epoch_data()
    service.study.data_manager.epoch_data = epoch_data
    dataset = Dataset(
        epoch_data,
        DataSplittingConfig(TrainingType.IND, False, [], []),
    )
    dataset.name = "trial_split"
    dataset.train_mask = np.array([True, True, False, False, False, False])
    dataset.val_mask = np.array([False, False, True, True, False, False])
    dataset.test_mask = np.array([False, False, False, False, True, True])
    generator = MagicMock()
    generator.prepare_result.return_value = [dataset]
    service.study.get_datasets_generator = MagicMock(return_value=generator)
    saved = service.execute(
        SaveDatasetSplitCommand(
            split_config={
                "train_type": "Individual",
                "is_cross_validation": False,
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
                        "split_unit": "Ratio",
                        "value": "0.2",
                    },
                ],
            },
        ),
    )

    assert saved.ok is True
    candidate = service.dataset_generation.prepare_saved_split_candidate()
    prepared = service.dataset_generation.commit_prepared_split(candidate)
    assert prepared["protocol"] == "trial-wise"
    assert service.get_state().dataset.available is True


def test_reset_preprocess_command_clears_downstream_training_plan():
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_preprocess_history.return_value = ["filter"]
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = MagicMock()
    service.study.data_manager.datasets = [MagicMock()]
    service.study.training_manager.trainer = Trainer([])
    service.study.reset_preprocess = MagicMock(
        side_effect=lambda force_update: (
            setattr(service.study.data_manager, "epoch_data", None),
            setattr(service.study.data_manager, "datasets", []),
            setattr(service.study.data_manager, "dataset_generator", None),
        )
    )

    unconfirmed = service.execute(ResetPreprocessCommand())
    assert unconfirmed.failed is True
    assert unconfirmed.error_type == ErrorType.CONFIRMATION_REQUIRED

    result = service.execute(ResetPreprocessCommand(confirmed=True))

    assert result.ok is True
    assert result.state.epoch.available is False
    assert result.state.dataset.available is False
    assert result.state.training.has_trainer is False
    assert result.diagnostics["trainer_cleared"] is True


def test_clear_datasets_and_training_history_commands_route_cleanup():
    service = ApplicationService(Study())
    service.study.data_manager.datasets = [MagicMock()]
    service.training.clean_datasets = MagicMock()

    clear_datasets = service.execute(ClearDatasetsCommand(confirmed=True))

    assert clear_datasets.ok is True
    service.training.clean_datasets.assert_called_once_with(force_update=True)

    trainer = Trainer([])
    plan = MagicMock()
    trainer.get_training_plan_holders = MagicMock(return_value=[plan])
    service.study.training_manager.trainer = trainer
    service.training.clear_history = MagicMock()

    clear_history = service.execute(ClearTrainingHistoryCommand(confirmed=True))

    assert clear_history.ok is True
    service.training.clear_history.assert_called_once_with()


def test_clear_datasets_reads_trainer_presence_from_runtime_not_study_alias():
    class _TrainerAliasRaisesStudy(Study):
        @property
        def trainer(self):
            raise AssertionError("Study.trainer alias must not be read")

    study = _TrainerAliasRaisesStudy()
    study.data_manager.datasets = [MagicMock()]
    study.training_manager.trainer = Trainer([])
    service = ApplicationService(study)

    result = service.execute(ClearDatasetsCommand(confirmed=True))

    assert result.ok is True
    assert result.diagnostics["trainer_cleared"] is True
    assert study.training_manager.trainer is None


def test_evaluate_and_clear_history_block_when_trainer_has_no_plan_history():
    service = ApplicationService(Study())
    trainer = Trainer([])
    service.study.training_manager.trainer = trainer

    policy = service.get_capabilities()
    evaluate = service.execute(EvaluateCommand())
    clear_history = service.execute(ClearTrainingHistoryCommand(confirmed=True))

    assert policy.get(CommandName.EVALUATE).available is False
    assert policy.get(CommandName.CLEAR_TRAINING_HISTORY).available is False
    assert evaluate.failed is True
    assert evaluate.error_type == ErrorType.PRECONDITION
    assert clear_history.failed is True
    assert clear_history.error_type == ErrorType.PRECONDITION


def test_evaluate_is_blocked_until_a_training_run_has_finished() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="dataset_ready",
        evaluation=EvaluationStateSnapshot(
            available=False,
            total_plans=1,
            total_runs=1,
            finished_runs=0,
        ),
        active_training=ActiveTrainingSnapshot(has_trainer=True),
    )

    capability = build_capability_policy(state).get(CommandName.EVALUATE)

    assert capability.available is False
    assert capability.reasons == [
        "Complete at least one training run before evaluating results."
    ]


def test_existing_finished_results_remain_evaluable_after_a_later_failure() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="trained",
        evaluation=EvaluationStateSnapshot(
            available=True,
            total_plans=2,
            total_runs=2,
            finished_runs=1,
            metrics_available=True,
        ),
        training=TrainingStateSnapshot(
            has_trainer=True,
            finished_run_count=1,
            terminal_outcome=TrainingTerminalOutcome(
                state=TrainingOutcomeState.FAILED,
                detail="later run failed",
            ),
        ),
        active_training=ActiveTrainingSnapshot(has_trainer=True),
    )

    capability = build_capability_policy(state).get(CommandName.EVALUATE)

    assert capability.available is True


def test_blocked_query_and_lifecycle_commands_still_return_result_envelopes():
    service = ApplicationService(Study())

    for command in (
        EvaluateCommand(),
        VisualizeCommand(),
        SaliencyCommand(),
        ClearDatasetsCommand(),
        ClearTrainingHistoryCommand(),
        ResetPreprocessCommand(),
    ):
        result = service.execute(command)

        assert result.failed is True
        assert result.command_name == command.name.value
        assert result.error_type == ErrorType.PRECONDITION
        assert result.state is not None
        assert result.changed_state is not None


def test_metadata_update_command_routes_through_service():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.dataset_state.update_metadata_batch = MagicMock(return_value=1)

    result = service.execute(UpdateMetadataCommand(index=0, subject="S01"))

    assert result.ok is True
    assert result.command_name == CommandName.UPDATE_METADATA.value
    assert result.diagnostics["success_count"] == 1
    service.dataset_state.update_metadata_batch.assert_called_once_with(
        [(0, "S01", None)],
    )


def test_import_labels_plan_routes_batch_import(tmp_path):
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.dataset.apply_labels_batch = MagicMock(return_value=1)
    label_path = tmp_path / "labels.txt"
    label_path.write_text("1 2\n", encoding="utf-8")

    result = service.execute(
        ImportLabelsCommand(
            plan=LabelImportPlan(
                target_indices=[0],
                label_paths=[str(label_path)],
                file_mapping={"/tmp/sample.fif": str(label_path)},
                mapping={1: "left", 2: "right"},
                mode="batch",
            ),
        ),
    )

    assert result.ok is True
    assert result.diagnostics["success_count"] == 1
    service.dataset.apply_labels_batch.assert_called_once()


def test_import_labels_updates_applied_interpretation_recipe_trace(tmp_path):
    source_dir = tmp_path / "interpreted_with_external_labels"
    source_dir.mkdir()
    eeg_path = source_dir / "subject01_run1.fif"
    eeg_path.write_bytes(b"not loaded during scan")
    recipe_path = tmp_path / "recipe_with_labels.json"
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.dataset.import_files = MagicMock(return_value=(1, []))
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
    service.dataset.apply_labels_batch = MagicMock(return_value=1)
    label_path = tmp_path / "labels.tsv"
    label_path.write_text("label\n1\n2\n", encoding="utf-8")

    service.execute(ScanSourceCommand(source_path=str(source_dir)))
    service.execute(PreviewInterpretationCommand())
    service.execute(ValidateInterpretationCommand())
    service.execute(ApplyInterpretationCommand(confirmed=True))
    service.study.data_manager.loaded_data_list = [raw]
    import_result = service.execute(
        ImportLabelsCommand(
            plan=LabelImportPlan(
                target_indices=[0],
                label_paths=[str(label_path)],
                file_mapping={"/tmp/sample.fif": str(label_path)},
                mapping={1: "left", 2: "right"},
                mode="batch",
                selected_event_names=["cue"],
            ),
        ),
    )
    save_result = service.execute(
        SaveInterpretationRecipeCommand(recipe_path=str(recipe_path)),
    )

    assert import_result.ok is True
    assert import_result.diagnostics["recipe_updated"] is True
    label_import = import_result.diagnostics["label_import"]
    canonical_label_path = str(label_path.resolve())
    assert label_import["mode"] == "batch"
    assert label_import["label_carriers"] == [canonical_label_path]
    assert label_import["selected_event_names"] == ["cue"]
    assert import_result.state.interpretation.label_carriers == [canonical_label_path]
    assert import_result.state.interpretation.label_import_count == 1
    assert save_result.ok is True
    recipe = save_result.diagnostics["recipe"]
    assert recipe["label_carriers"] == [canonical_label_path]
    assert recipe["label_imports"][0]["class_map"] == {"1": "left", "2": "right"}
    assert "label_import:batch:1" in recipe["recipe_trace"]


def test_apply_montage_command_routes_confirmed_positions():
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = MagicMock()
    service.preprocess.apply_montage = MagicMock()

    result = service.execute(
        ApplyMontageCommand(
            channels=["Cz"],
            positions=[(0.0, 0.0, 0.0)],
            montage_name="standard_1020",
        ),
    )

    assert result.ok is True
    assert result.command_name == CommandName.APPLY_MONTAGE.value
    service.preprocess.apply_montage.assert_called_once_with(
        ["Cz"],
        [(0.0, 0.0, 0.0)],
    )


@pytest.mark.parametrize(
    ("command", "name"),
    [
        (LoadDataCommand(paths=["/tmp/sample.fif"]), CommandName.LOAD_DATA),
        (RemoveFilesCommand(indices=[0]), CommandName.REMOVE_FILES),
    ],
)
def test_data_inventory_changes_refresh_optional_montage_preparation(
    command,
    name,
) -> None:
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_mne.return_value.get_channel_types.return_value = ["eeg", "eeg"]
    service.dataset.get_loaded_data_list = MagicMock(return_value=[raw])
    coordinator = MagicMock()
    coordinator.synchronize_loaded_recordings.return_value = (
        MontagePreparationSnapshot.pending(
            generation=1,
            recording_paths=("/tmp/sample.fif",),
        )
    )
    service.bids_montage_preparation = coordinator

    diagnostics = service._update_montage_preparation_after_command(
        command=command,
        name=name,
        diagnostics={},
    )

    coordinator.synchronize_loaded_recordings.assert_called_once_with([raw])
    assert diagnostics["montage_preparation"]["state"] == "pending"


def test_clear_datasets_preserves_epoch_scoped_manual_montage() -> None:
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = _positive_epoch_data()
    service.study.data_manager.datasets = [MagicMock()]
    service.bids_montage_preparation.select_manual(
        ManualMontageOverride(
            name="manual",
            channel_names=("C3", "C4"),
            positions_m=((0.0, 0.1, 0.0), (0.0, -0.1, 0.0)),
            coordinate_frame="head",
        )
    )
    service.get_state()

    result = service.execute(ClearDatasetsCommand(confirmed=True))

    assert result.ok is True
    assert result.state.dataset.available is False
    assert result.state.epoch.available is True
    assert result.state.visualization.montage_source == "manual"
    effective = service.bids_montage_preparation.effective_montage()
    assert effective is not None
    assert effective.source == "manual"
    service.close()


def test_bids_montage_refresh_failure_retains_candidate_until_view_recovers() -> None:
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = _positive_epoch_data()
    service.get_state()
    request = BidsMontageRecordingRequest(
        recording_path="/tmp/sub-01_task-rest_eeg.fif",
        channel_names=("C3", "C4"),
        channel_types=("eeg", "eeg"),
    )

    def admit(recordings) -> BidsMontageResourceReceipt:
        return BidsMontageResourceReceipt(
            recording_resources=tuple((item.recording_path, ()) for item in recordings)
        )

    def prepare(recordings, *, generation, **_kwargs):
        paths = tuple(item.recording_path for item in recordings)
        return MontagePreparationSnapshot(
            state="ready",
            generation=generation,
            requested_recording_paths=paths,
            recordings=tuple(
                RecordingMontagePreparation(
                    recording_path=item.recording_path,
                    state="ready",
                    recording_channel_names=item.channel_names,
                    channel_names=item.channel_names,
                    positions_m=((0.1, 0.0, 0.0), (-0.1, 0.0, 0.0)),
                    coordinate_system="CapTrak",
                    coordinate_frame="head",
                    coordinate_units="m",
                    source_coordinate_units="m",
                )
                for item in recordings
            ),
            aggregate=AggregateMontageCompatibility(
                compatible=True,
                channel_names=("C3", "C4"),
                positions_m=((0.1, 0.0, 0.0), (-0.1, 0.0, 0.0)),
                coordinate_frame="head",
                coordinate_units="m",
            ),
        )

    service.bids_montage_preparation._admit = admit
    service.bids_montage_preparation._prepare = prepare
    build_state = service.state_snapshot.build
    refresh_attempted = Event()
    attempt_count = 0

    def fail_once(*args, **kwargs):
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count == 1:
            refresh_attempted.set()
            raise RuntimeError("forced montage refresh failure")
        return build_state(*args, **kwargs)

    service.state_snapshot.build = fail_once
    pending = service.bids_montage_preparation.start((request,))
    assert pending.state == "pending"
    assert refresh_attempted.wait(timeout=2.0)
    assert service.bids_montage_preparation.wait_for_idle(timeout=2.0)

    failed_view = service._committed_view_publication()
    assert failed_view.usable is False
    assert service.bids_montage_preparation.snapshot().state == "pending"

    recovered = service.get_view_publication()

    assert recovered.usable is True
    assert recovered.state.visualization.montage_preparation_state == "ready"
    assert recovered.state.visualization.montage_source == "bids"
    assert service.bids_montage_preparation.snapshot().state == "ready"
    service.close()


def test_apply_montage_rejects_channel_subset_after_dataset_generation():
    class EpochWithChannels:
        def __init__(self) -> None:
            self.channels = ["C3", "C4"]

        def get_channel_names(self) -> list[str]:
            return list(self.channels)

        def set_channels(self, channels, _positions) -> None:
            self.channels = list(channels)

    study = Study()
    epoch = EpochWithChannels()
    study.data_manager.epoch_data = cast(Any, epoch)
    study.data_manager.datasets = [MagicMock()]
    service = ApplicationService(study)

    result = service.execute(
        ApplyMontageCommand(
            channels=["C3"],
            positions=[(0.0, 0.0, 1.0)],
        ),
    )

    assert result.failed is True
    assert "before generating datasets" in result.message
    assert epoch.channels == ["C3", "C4"]


def test_query_state_returns_typed_dataset_summary():
    raw = _raw_mock()
    study = Study()
    study.data_manager.loaded_data_list = [raw]
    study.data_manager.preprocessed_data_list = [raw]
    service = ApplicationService(study)

    result = service.execute(QueryStateCommand(query="data_summary"))

    assert result.ok is True
    assert result.diagnostics["count"] == 1
    assert result.diagnostics["metadata"][0]["subject"] == "S01"


def test_query_state_smart_filter_uses_study_port_target_file_argument():
    service = ApplicationService(Study())
    raw = object()
    service.study.data_manager.loaded_data_list = [raw]
    service.dataset_state.get_smart_filter_suggestions = MagicMock(return_value=[7, 8])

    result = service.execute(
        QueryStateCommand(
            query="smart_filter_suggestions",
            params={"target_index": 0, "target_count": 2},
        ),
    )

    assert result.ok is True
    assert result.diagnostics == {"suggestions": [7, 8]}
    service.dataset_state.get_smart_filter_suggestions.assert_called_once_with(raw, 2)


def test_new_session_requires_confirmation_and_clears_single_backend_session():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]

    unconfirmed = service.execute(NewSessionCommand())

    assert unconfirmed.failed is True
    assert unconfirmed.error_type == ErrorType.CONFIRMATION_REQUIRED

    confirmed = service.execute(NewSessionCommand(confirmed=True))

    assert confirmed.ok is True
    assert confirmed.command_name == "new_session"
    assert confirmed.state.raw.loaded is False


def test_mutation_publishes_only_committed_application_view(monkeypatch):
    service = ApplicationService(Study())
    initial = service.get_view_publication()
    publications = []
    original_execute_allowed = service._execute_allowed

    def execute_without_early_publication(command, name):
        assert publications == []
        return original_execute_allowed(command, name)

    monkeypatch.setattr(service, "_execute_allowed", execute_without_early_publication)
    service.subscribe(
        APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
        publications.append,
    )

    result = service.execute(NewSessionCommand(confirmed=True))

    assert result.ok is True
    assert len(publications) == 1
    publication = publications[0]
    assert publication.usable is True
    assert publication.generation > initial.generation
    assert publication.state == result.state
    assert publication == service.get_view_publication()


def test_destructive_capabilities_expose_confirmation_boundary_metadata():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.datasets = [object()]
    trainer = Trainer([])
    service.study.training_manager.trainer = trainer
    service.get_state()

    policy = service.get_capabilities()

    for command_name in (
        CommandName.RESET_SESSION,
        CommandName.NEW_SESSION,
        CommandName.CLEAR_DATASETS,
    ):
        capability = policy.get(command_name)
        assert capability.confirmation_required is True
        assert capability.requires_confirmation is True
        assert capability.can_auto_execute is False
        assert capability.decision_boundary


def test_set_montage_preprocess_operation_requires_ui_confirmation():
    service = ApplicationService(Study())
    raw = _raw_mock()
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]

    result = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.SET_MONTAGE,
            montage_name="standard_1020",
        ),
    )

    assert result.failed is True
    assert result.error_type == ErrorType.CONFIRMATION_REQUIRED
    assert "app confirmation path" in result.message


def _patch_internal_events(
    monkeypatch: Any,
    events_by_file: dict[str, dict[str, dict[str, Any]]],
) -> None:
    def read_events(path: str) -> dict[str, Any]:
        name = Path(str(path)).name
        return {"events": events_by_file.get(name, events_by_file.get("*", {}))}

    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_internal_events_for_file",
        read_events,
    )


def _raw_mock():
    raw = MagicMock()
    raw.get_filename.return_value = "sample.fif"
    raw.get_filepath.return_value = "/tmp/sample.fif"
    raw.get_subject_name.return_value = "S01"
    raw.get_session_name.return_value = "001"
    raw.is_raw.return_value = True
    mne_raw = MagicMock()
    mne_raw.ch_names = ["C3", "C4"]
    mne_raw.annotations = []
    raw.get_mne.return_value = mne_raw
    return raw
