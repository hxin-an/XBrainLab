"""Application boundary: training configuration behavior."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.backend.application.application_test_support import (
    THREAD_WATCHDOG_SECONDS,
    _positive_epoch_data,
    _prepare_saved_training_split,
    _publish_mock_training_identity,
    _valid_model_holder,
    _valid_training_option,
)
from tests.unit.backend.application.preprocess_test_support import (
    _minimal_raw,
)
from XBrainLab.backend.application import (
    ApplicationService,
    CommandName,
    ConfigureTrainingCommand,
    ErrorType,
    ResetPreprocessCommand,
    TrainCommand,
)
from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.errors import ApplicationError, PreconditionError
from XBrainLab.backend.application.owned_work import (
    OwnedWorkPhase,
)
from XBrainLab.backend.application.resource_guard import (
    ResourceChecker,
    TrainingResourcePreviewRequest,
    TrainingResourcePreviewResult,
    TrainingResourceRefinement,
)
from XBrainLab.backend.application.training_submission import (
    attach_training_submission_provenance,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import (
    ModelHolder,
    TrainingEvaluation,
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


def test_training_model_signal_context_is_detached_from_epoch_state():
    service = ApplicationService(Study())
    source = {
        "n_classes": 4,
        "channels": 22,
        "samples": 256,
        "sfreq": 128.0,
        "chs_info": [],
    }
    service.training.get_epoch_data = MagicMock(
        return_value=SimpleNamespace(get_model_args=lambda: source),
    )

    context = service.get_training_model_signal_context()

    assert context == source
    assert context is not source
    assert service.get_view_publication().state.training.model_name is None


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


def test_training_resource_preview_begin_is_nonblocking_and_exactly_owned() -> None:
    estimate_started = Event()
    release_estimate = Event()
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

    def estimate(draft, _context):
        estimate_started.set()
        assert release_estimate.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return TrainingResourcePreviewResult(
            request_generation=draft.request_generation,
            publication_generation=draft.publication_generation,
            requested_batch_size=draft.batch_size,
            suggested_batch_size=draft.batch_size,
            estimated_vram_bytes=0,
            available_vram_bytes=None,
            risk_level="safe",
            vram_known=False,
        )

    service.training_resource_preview._estimate = estimate
    ticket = service.begin_training_resource_preview(request)
    assert estimate_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    snapshot = service.training_resource_preview_background_work_snapshot()

    assert ticket.done is False
    assert service.get_owned_operation(ticket.operation_id).kind.value == (
        "training_resource_preview"
    )
    assert service.get_owned_operation(ticket.operation_id).phase is (
        OwnedWorkPhase.RUNNING
    )
    assert snapshot["remaining_workers"] == 1
    assert snapshot["alive_workers"] == 1
    assert snapshot["active_jobs"] == 1

    service.begin_training_resource_preview_shutdown()
    release_estimate.set()
    with pytest.raises(ApplicationError, match="closing"):
        ticket.result(timeout=THREAD_WATCHDOG_SECONDS)
    assert service.get_owned_operation(ticket.operation_id).phase is (
        OwnedWorkPhase.CANCELLED
    )
    assert service.training_resource_preview.wait_for_idle(
        timeout=THREAD_WATCHDOG_SECONDS
    )
    assert service.cancel_training_resource_preview_shutdown() is True

    retried = service.begin_training_resource_preview(
        replace(request, request_generation=2)
    )
    assert retried.result(timeout=THREAD_WATCHDOG_SECONDS).request_generation == 2
    assert service.get_owned_operation(retried.operation_id).phase is (
        OwnedWorkPhase.COMPLETED
    )
    service.close()


def test_lazy_training_service_import_configures_after_epoch_preparation() -> None:
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = _positive_epoch_data()
    service.get_state()
    publication = service.get_view_publication()

    assert "training_commands" not in vars(service)

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
    assert "training_commands" in vars(service)
    service.close()


def test_configure_training_rejects_early_stopping_without_proven_validation() -> None:
    service = ApplicationService(Study())

    result = service.execute(
        ConfigureTrainingCommand(
            model_name="EEGNet",
            model_params={"f1": 2, "f2": 4, "d": 1},
            epoch=2,
            batch_size=2,
            learning_rate=0.001,
            optimizer="Adam",
            device="cpu",
            evaluation_option="Best validation loss",
            early_stopping_enabled=True,
        )
    )

    assert result.failed is True
    assert "Early stopping requires a validation split" in result.message
    assert service.study.training_manager.training_option is None
    service.close()


def test_start_admission_rejects_stale_early_stopping_without_validation() -> None:
    service = ApplicationService(Study())
    option = _valid_training_option()
    option.evaluation_option = TrainingEvaluation.VAL_LOSS
    option.early_stopping_enabled = True
    service.study.set_training_option(option)
    service.study.datasets = []

    with pytest.raises(PreconditionError, match="validation split"):
        service.training_commands._validate_early_stopping_admission()
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
    direct_estimator.assert_not_called()
    model_factory.assert_not_called()
    model_lookup.assert_not_called()


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
