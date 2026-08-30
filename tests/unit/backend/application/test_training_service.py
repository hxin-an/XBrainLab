"""Focused tests for training command handlers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields, replace
from threading import Barrier, Event, Thread
from time import sleep
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import numpy as np
import pytest
import torch

from XBrainLab.backend.application import resource_guard
from XBrainLab.backend.application import (
    training_resource_receipt as training_receipt_module,
)
from XBrainLab.backend.application import training_service as training_service_module
from XBrainLab.backend.application.commands import (
    ClearTrainingHistoryCommand,
    ConfigureTrainingCommand,
    StopTrainingCommand,
    TrainCommand,
)
from XBrainLab.backend.application.errors import ApplicationError, PreconditionError
from XBrainLab.backend.application.owned_work import (
    OwnedOperationCancelledError,
    OwnedWorkKind,
    OwnedWorkPhase,
    OwnedWorkRegistry,
)
from XBrainLab.backend.application.resource_guard import (
    TrainingResourcePreviewRequest,
    TrainingResourcePreviewResult,
)
from XBrainLab.backend.application.results import ErrorType
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
from XBrainLab.backend.application.training_recommendation import (
    TrainingRecommendationField,
)
from XBrainLab.backend.application.training_runtime import TrainingRuntimeContext
from XBrainLab.backend.application.training_service import (
    HandlerResult,
    TrainingCommandService,
)
from XBrainLab.backend.application.training_submission import (
    attach_training_submission_provenance,
)
from XBrainLab.backend.model_base import model_catalog as model_catalog_module
from XBrainLab.backend.training import option as training_option_module
from XBrainLab.backend.training.option import ClassWeightMode, class_map_fingerprint
from XBrainLab.backend.training_state_contract import (
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingTerminalOutcome,
)


class _TrainingController:
    def __init__(self) -> None:
        self.model_holder: Any | None = None
        self.training_option: Any | None = None
        self.started = False
        self.start_count = 0
        self.stopped = False
        self.stop_result = True
        self.stop_wait_timeout: float | None = None
        self.history_cleared = False
        self.notifications: list[str] = []
        self.resource_context: dict[str, Any] | None = {
            "datasets": [],
            "training_option": SimpleNamespace(
                use_cpu=True,
                bs=1,
                get_device=lambda: "cpu",
            ),
            "model_holder": None,
        }
        self.progress_text = "Pending"
        self.terminal_outcome = TrainingTerminalOutcome(
            state=TrainingOutcomeState.COMPLETED,
            run=TrainingRunIdentity(trainer_id="test-trainer", run_id=1),
        )

    def set_model_holder(self, holder: Any) -> None:
        self.model_holder = holder

    def set_training_option(self, option: Any) -> None:
        self.training_option = option

    def apply_configuration(
        self,
        *,
        model_holder: Any | None,
        training_option: Any | None,
        update_model: bool,
        update_option: bool,
    ) -> None:
        if update_model:
            self.model_holder = model_holder
        if update_option:
            self.training_option = training_option

    def start_training(self, *, append: bool = True, interactive: bool = True) -> int:
        self.started = True
        self.start_count += 1
        self.started_append = append
        self.started_interactive = interactive
        return self.start_count

    def clear_history(self) -> None:
        self.history_cleared = True

    def notify(self, event_name: str) -> None:
        self.notifications.append(event_name)

    def get_progress_text(self) -> str:
        return self.progress_text


class _TrainingRuntime:
    def __init__(self, training: _TrainingController) -> None:
        self.training = training

    def resource_context(self) -> TrainingRuntimeContext:
        context = self.training.resource_context or {}
        return TrainingRuntimeContext(
            datasets=tuple(context.get("datasets", ()) or ()),
            training_option=context.get("training_option"),
            model_holder=context.get("model_holder"),
        )

    def stop_training(self, *, wait_timeout: float | None = None) -> bool:
        self.training.stopped = True
        self.training.stop_wait_timeout = wait_timeout
        return self.training.stop_result

    def wait_for_training_completion(
        self,
        *,
        expected_trainer_identity: str | None = None,
        timeout: float | None = None,
    ) -> bool:
        del expected_trainer_identity, timeout
        return True

    def terminal_outcome(self) -> TrainingTerminalOutcome:
        return self.training.terminal_outcome


class _ArrayLike:
    def __init__(self, *, nbytes: int, shape: tuple[int, ...] = (1,)) -> None:
        self.nbytes = nbytes
        self.shape = shape


class _EpochData:
    def __init__(self, *, data_nbytes: int, label_nbytes: int = 0) -> None:
        self.data = _ArrayLike(nbytes=data_nbytes, shape=(10, data_nbytes // 10))
        self.labels = _ArrayLike(nbytes=label_nbytes, shape=(10,))

    def get_data(self) -> _ArrayLike:
        return self.data

    def get_label_list(self) -> _ArrayLike:
        return self.labels


class _Dataset:
    def __init__(self, epoch_data: _EpochData) -> None:
        self.epoch_data = epoch_data

    def get_epoch_data(self) -> _EpochData:
        return self.epoch_data


class _EEGNetModel:
    pass


class _TinyParameter:
    def numel(self) -> int:
        return 1_000

    def element_size(self) -> int:
        return 4


class _TinyModel:
    def parameters(self) -> list[_TinyParameter]:
        return [_TinyParameter()]

    def cpu(self) -> None:
        return None


class _TinyModelHolder:
    target_model = _EEGNetModel

    def get_model(self, _args: dict[str, Any]) -> _TinyModel:
        return _TinyModel()


def _receipt_training_context() -> dict[str, Any]:
    return {
        "datasets": [
            _Dataset(_EpochData(data_nbytes=10_000, label_nbytes=1_000)),
        ],
        "training_option": SimpleNamespace(
            use_cpu=True,
            gpu_idx=None,
            bs=8,
            epoch=2,
            lr=0.001,
            repeat_num=1,
            optim_params={},
            checkpoint_epoch=0,
            output_dir="./output",
            evaluation_option="last_epoch",
            get_device=lambda: "cpu",
            get_optim_name=lambda: "Adam",
        ),
        "model_holder": SimpleNamespace(
            target_model=_EEGNetModel,
            model_params_map={"input_size": 256, "num_classes": 2},
            pretrained_weight_path=None,
        ),
    }


def _warning_training_preflight(
    _datasets: Any,
    _training_option: Any,
    _model_holder: Any,
) -> resource_guard.ResourcePreflightResult:
    return resource_guard.ResourcePreflightResult(
        issues=(),
        warnings=("Training may use most available memory.",),
        diagnostics={
            "dataset_bytes": 11_000,
            "peak_input_batch_bytes": 4_096,
            "estimated_gpu_batch_working_set_bytes": 8_192,
            "uses_cpu": True,
        },
    )


def _state(*, progress_message: str | None = None) -> ApplicationStateSnapshot:
    return ApplicationStateSnapshot(
        pipeline_stage="dataset_ready",
        raw=RawStateSnapshot(),
        preprocessed=PreprocessedStateSnapshot(),
        epoch=EpochStateSnapshot(),
        dataset=DatasetStateSnapshot(available=True, count=1),
        training=TrainingStateSnapshot(progress_message=progress_message),
        evaluation=EvaluationStateSnapshot(
            available=True,
            total_plans=2,
            total_runs=3,
            finished_runs=1,
            metrics_available=True,
        ),
        visualization=VisualizationStateSnapshot(),
        interpretation=InterpretationStateSnapshot(),
        active_dataset=ActiveDatasetSnapshot(has_datasets=True),
        active_training=ActiveTrainingSnapshot(),
    )


def _expect_payload(result: HandlerResult) -> tuple[str, dict[str, Any]]:
    assert isinstance(result, tuple)
    return cast(tuple[str, dict[str, Any]], result)


def _service() -> tuple[TrainingCommandService, _TrainingController]:
    training = _TrainingController()
    return (
        TrainingCommandService(
            training=training,
            training_runtime=_TrainingRuntime(training),
            get_state=_state,
        ),
        training,
    )


def _class_weighting_option(
    *,
    mode: ClassWeightMode,
    custom_class_weights: dict[str, float],
    fingerprint: str | None,
):
    return training_option_module.TrainingOption(
        output_dir="./tmp-output",
        optim=torch.optim.Adam,
        optim_params={},
        use_cpu=True,
        gpu_idx=None,
        epoch=1,
        bs=1,
        lr=0.001,
        checkpoint_epoch=0,
        evaluation_option=training_option_module.TrainingEvaluation.VAL_LOSS,
        repeat_num=1,
        class_weight_mode=mode,
        custom_class_weights=custom_class_weights,
        class_map_fingerprint_value=fingerprint,
    )


def test_training_service_configures_model_and_options() -> None:
    service, training = _service()

    model_message = service.handle_configure_training(
        ConfigureTrainingCommand(model_name="EEGNet"),
    )
    option_message, option_payload = _expect_payload(
        service.handle_configure_training(
            ConfigureTrainingCommand(
                epoch=2,
                batch_size=4,
                learning_rate=0.001,
                optimizer="sgd",
                device="cpu",
                output_dir="./tmp-output",
            ),
        ),
    )

    assert model_message == "Model configured: EEGNet."
    assert training.model_holder is not None
    assert service.model_name(training.model_holder) == "EEGNet (XBrainLab)"
    assert option_message == "Training configured."
    assert training.training_option is not None
    generated_seed = training.training_option.seed
    assert type(generated_seed) is int
    assert option_payload["training_option"] == {
        "epoch": 2,
        "batch_size": 4,
        "learning_rate": 0.001,
        "repeat": 1,
        "seed": generated_seed,
        "repeat_seeds": [generated_seed],
        "device": "cpu",
        "optimizer": "SGD",
        "optimizer_params": {},
        "evaluation_option": "Last Epoch",
        "checkpoint_epoch": 0,
        "output_dir": "./tmp-output",
        "class_weight_mode": "off",
        "custom_class_weights": {},
        "class_map_fingerprint": None,
    }


def test_configure_training_command_has_no_unvalidated_option_object_path() -> None:
    assert "training_option" not in {
        field.name for field in fields(ConfigureTrainingCommand)
    }


def test_configure_custom_weights_require_the_current_reviewed_class_names() -> None:
    training = _TrainingController()
    state = replace(
        _state(),
        epoch=EpochStateSnapshot(
            available=True,
            event_ids={"left": 0, "right": 1},
        ),
    )
    service = TrainingCommandService(
        training=training,
        training_runtime=_TrainingRuntime(training),
        get_state=lambda: state,
    )
    command = ConfigureTrainingCommand(
        epoch=2,
        batch_size=4,
        learning_rate=0.001,
        device="cpu",
        class_weight_mode="custom",
        custom_class_weights={"left": 1.0, "right": 2.0},
    )

    service.handle_configure_training(command)

    assert training.training_option.class_weight_mode is ClassWeightMode.CUSTOM
    assert training.training_option.custom_class_weights == {
        "left": 1.0,
        "right": 2.0,
    }
    assert training.training_option.class_map_fingerprint == class_map_fingerprint(
        {0: "left", 1: "right"}
    )

    with pytest.raises(PreconditionError, match="do not match"):
        service.handle_configure_training(
            ConfigureTrainingCommand(
                epoch=2,
                batch_size=4,
                learning_rate=0.001,
                device="cpu",
                class_weight_mode="custom",
                custom_class_weights={"left": 1.0, "unknown": 2.0},
            )
        )


@pytest.mark.parametrize("mode", [ClassWeightMode.OFF, ClassWeightMode.BALANCED])
def test_start_training_blocks_zero_class_before_runtime_handoff(
    mode: ClassWeightMode,
) -> None:
    class _WeightingEpoch:
        def get_label_map(self) -> dict[int, str]:
            return {0: "left", 1: "right"}

        def get_label_list(self) -> np.ndarray:
            return np.asarray([0, 0, 1])

    class _WeightingDataset:
        train_mask = np.asarray([True, True, False])

        def get_epoch_data(self) -> _WeightingEpoch:
            return _WeightingEpoch()

    service, training = _service()
    training.resource_context = {
        "datasets": [_WeightingDataset()],
        "training_option": _class_weighting_option(
            mode=mode,
            custom_class_weights={},
            fingerprint=class_map_fingerprint({0: "left", 1: "right"}),
        ),
        "model_holder": object(),
    }
    preflight = resource_guard.ResourcePreflightResult(issues=(), diagnostics={})

    with pytest.raises(PreconditionError, match="missing class"):
        service.start_train_after_preflight(
            TrainCommand(),
            preflight=preflight,
            receipt_reused=False,
        )

    assert training.start_count == 0


def test_start_training_rechecks_custom_weights_against_the_current_map() -> None:
    class _WeightingEpoch:
        def get_label_map(self) -> dict[int, str]:
            return {0: "left", 1: "right"}

        def get_label_list(self) -> np.ndarray:
            return np.asarray([0, 1])

    class _WeightingDataset:
        train_mask = np.asarray([True, True])

        def get_epoch_data(self) -> _WeightingEpoch:
            return _WeightingEpoch()

    service, training = _service()
    training.resource_context = {
        "datasets": [_WeightingDataset()],
        "training_option": _class_weighting_option(
            mode=ClassWeightMode.CUSTOM,
            custom_class_weights={"left": 1.0, "old-right": 2.0},
            fingerprint=class_map_fingerprint({0: "left", 1: "old-right"}),
        ),
        "model_holder": object(),
    }

    with pytest.raises(PreconditionError, match="mapping changed"):
        service.start_train_after_preflight(
            TrainCommand(),
            preflight=resource_guard.ResourcePreflightResult(issues=(), diagnostics={}),
            receipt_reused=False,
        )

    assert training.start_count == 0


def test_training_service_forwards_only_typed_edited_recommendation_fields() -> None:
    training = _TrainingController()
    recommendation = MagicMock()
    service = TrainingCommandService(
        training=training,
        training_runtime=_TrainingRuntime(training),
        get_state=_state,
        recommendation=recommendation,
    )

    service.handle_configure_training(
        attach_training_submission_provenance(
            ConfigureTrainingCommand(
                epoch=3,
                batch_size=8,
                learning_rate=0.001,
            ),
            frozenset(
                {
                    TrainingRecommendationField.BATCH_SIZE,
                    TrainingRecommendationField.OPTIMIZER,
                }
            ),
        )
    )

    recommendation.note_configuration_submitted.assert_called_once_with(
        frozenset(
            {
                TrainingRecommendationField.BATCH_SIZE,
                TrainingRecommendationField.OPTIMIZER,
            }
        )
    )


def test_training_service_maps_case_insensitive_model_without_facade() -> None:
    service, training = _service()

    message = service.handle_configure_training(
        ConfigureTrainingCommand(model_name="EEGNET"),
    )

    assert message == "Model configured: EEGNET."
    assert training.model_holder is not None
    assert service.model_name(training.model_holder) == "EEGNet (XBrainLab)"


def test_training_service_rejects_unknown_model_without_facade() -> None:
    service, _training = _service()

    with pytest.raises(ValueError, match="Unknown model architecture"):
        service.handle_configure_training(
            ConfigureTrainingCommand(model_name="nonexistent_model"),
        )


def test_training_service_resolves_braindecode_catalog_model() -> None:
    service, training = _service()

    message = service.handle_configure_training(
        ConfigureTrainingCommand(
            model_name="braindecode.eegnet",
            model_params={"F1": 12},
        ),
    )

    assert message == "Model configured: braindecode.eegnet."
    assert training.model_holder.model_id == "braindecode.eegnet"
    assert training.model_holder.display_name == "EEGNet (Braindecode)"
    assert training.model_holder.provider == "braindecode"
    assert training.model_holder.source_revision == "braindecode==1.6.1"
    assert training.model_holder.model_params_map == {"F1": 12}


def test_training_service_rejects_catalog_model_marked_unavailable(monkeypatch) -> None:
    service, _training = _service()
    monkeypatch.setattr(
        training_service_module,
        "get_model_spec",
        lambda _name, **_kwargs: SimpleNamespace(
            available=False,
            display_name="REVE (Braindecode)",
            unavailable_reason="Reviewed electrode positions are required.",
        ),
    )

    with pytest.raises(ValueError, match="Reviewed electrode positions are required"):
        service.handle_configure_training(
            ConfigureTrainingCommand(model_name="braindecode.reve"),
        )


def test_training_service_rechecks_dataset_model_compatibility_before_mutation(
    monkeypatch,
) -> None:
    service, training = _service()
    existing_holder = object()
    training.model_holder = existing_holder
    training.get_epoch_data = lambda: SimpleNamespace(  # type: ignore[attr-defined]
        get_model_args=lambda: {
            "n_classes": 4,
            "channels": 22,
            "samples": 256,
            "sfreq": 128.0,
            "chs_info": [],
        }
    )
    monkeypatch.setattr(
        model_catalog_module,
        "braindecode_provider_status",
        lambda: model_catalog_module.BraindecodeProviderStatus(
            available=True,
            installed_version="1.6.1",
            reason="",
            checked=True,
        ),
    )

    with pytest.raises(ValueError, match="divisible by 200"):
        service.handle_configure_training(
            ConfigureTrainingCommand(model_name="braindecode.cbramod"),
        )

    assert training.model_holder is existing_holder


@pytest.mark.parametrize(
    ("legacy_value", "expected"),
    [
        ("test_acc", training_option_module.TrainingEvaluation.VAL_ACC),
        ("Best testing performance", training_option_module.TrainingEvaluation.VAL_ACC),
        ("test_auc", training_option_module.TrainingEvaluation.VAL_AUC),
        ("Best testing AUC", training_option_module.TrainingEvaluation.VAL_AUC),
    ],
)
def test_legacy_test_selection_is_migrated_to_validation(
    legacy_value: str,
    expected: training_option_module.TrainingEvaluation,
) -> None:
    assert TrainingCommandService._resolve_training_evaluation(legacy_value) is expected


def test_training_snapshot_preserves_evaluation_and_optimizer_settings() -> None:
    service, _training = _service()

    result = service.handle_configure_training(
        ConfigureTrainingCommand(
            output_dir="./output",
            optimizer="Adam",
            optimizer_params={"weight_decay": 0.01},
            device="cpu",
            epoch=3,
            batch_size=8,
            learning_rate=0.001,
            save_checkpoints_every=0,
            evaluation_option="val_acc",
            repeat=1,
        )
    )

    assert isinstance(result, tuple)
    snapshot = result[1]["training_option"]
    assert snapshot["evaluation_option"] == "Best validation performance"
    assert snapshot["optimizer_params"] == {"weight_decay": 0.01}


def test_training_service_propagates_explicit_seed_and_repeat_snapshot() -> None:
    service, training = _service()

    result = service.handle_configure_training(
        ConfigureTrainingCommand(
            output_dir="./output",
            device="cpu",
            epoch=3,
            batch_size=8,
            learning_rate=0.001,
            repeat=3,
            seed=4294967293,
        )
    )

    assert isinstance(result, tuple)
    assert training.training_option is not None
    assert training.training_option.seed == 4294967293
    assert result[1]["training_option"]["seed"] == 4294967293
    assert result[1]["training_option"]["repeat_seeds"] == [
        4294967293,
        4294967294,
        4294967295,
    ]


def test_incomplete_training_configuration_does_not_mutate_model() -> None:
    service, training = _service()
    existing_model = object()
    existing_option = object()
    training.model_holder = existing_model
    training.training_option = existing_option

    with pytest.raises(PreconditionError, match="Training epochs, batch size"):
        service.handle_configure_training(
            ConfigureTrainingCommand(
                model_name="EEGNet",
                epoch=3,
                batch_size=8,
            ),
        )

    assert training.model_holder is existing_model
    assert training.training_option is existing_option


def test_seed_without_complete_training_option_is_not_silently_ignored() -> None:
    service, training = _service()
    existing_model = object()
    existing_option = object()
    training.model_holder = existing_model
    training.training_option = existing_option

    with pytest.raises(PreconditionError, match="Training epochs, batch size"):
        service.handle_configure_training(
            ConfigureTrainingCommand(model_name="EEGNet", seed=1729),
        )

    assert training.model_holder is existing_model
    assert training.training_option is existing_option


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"repeat": 0}, "repeat must be a positive integer"),
        (
            {"save_checkpoints_every": -1},
            "save_checkpoints_every must be a non-negative integer",
        ),
        ({"optimizer": "mystery"}, "Unknown optimizer"),
        ({"device": "cuda:not-an-index"}, "Unknown training device"),
        ({"evaluation_option": "mystery"}, "Unknown training evaluation"),
    ],
)
def test_model_only_configuration_rejects_invalid_option_without_mutation(
    overrides: dict[str, Any],
    message: str,
) -> None:
    service, training = _service()
    existing_model = object()
    existing_option = object()
    training.model_holder = existing_model
    training.training_option = existing_option

    with pytest.raises(ValueError, match=message):
        service.handle_configure_training(
            ConfigureTrainingCommand(model_name="EEGNet", **overrides),
        )

    assert training.model_holder is existing_model
    assert training.training_option is existing_option


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"optimizer": "mystery"}, "Unknown optimizer"),
        ({"device": "cuda:not-an-index"}, "Unknown training device"),
        ({"evaluation_option": "mystery"}, "Unknown training evaluation"),
        ({"epoch": 0}, "epoch must be a positive integer"),
        ({"batch_size": 0}, "batch_size must be a positive integer"),
        (
            {"learning_rate": 0.0},
            "learning_rate must be finite and greater than zero",
        ),
        (
            {"learning_rate": True},
            "learning_rate must be finite and greater than zero",
        ),
        ({"repeat": 0}, "repeat must be a positive integer"),
        (
            {"save_checkpoints_every": -1},
            "save_checkpoints_every must be a non-negative integer",
        ),
        ({"seed": True}, "Invalid seed"),
        ({"seed": 0xFFFF_FFFF, "repeat": 2}, "Invalid seed"),
    ],
)
def test_invalid_training_configuration_is_rejected_without_mutation(
    overrides: dict[str, Any],
    message: str,
) -> None:
    service, training = _service()
    existing_model = object()
    existing_option = object()
    training.model_holder = existing_model
    training.training_option = existing_option
    params: dict[str, Any] = {
        "model_name": "EEGNet",
        "epoch": 3,
        "batch_size": 8,
        "learning_rate": 0.001,
        "device": "cpu",
    }
    params.update(overrides)

    with pytest.raises((PreconditionError, ValueError), match=message):
        service.handle_configure_training(ConfigureTrainingCommand(**params))

    assert training.model_holder is existing_model
    assert training.training_option is existing_option


def test_training_service_maps_adamw_optimizer_without_facade() -> None:
    service, training = _service()

    _message, payload = _expect_payload(
        service.handle_configure_training(
            ConfigureTrainingCommand(
                epoch=3,
                batch_size=8,
                learning_rate=0.002,
                optimizer="adamw",
                device="cpu",
            ),
        ),
    )

    option = training.training_option
    assert option is not None
    assert option.get_optim_name() == "AdamW"
    assert payload["training_option"]["optimizer"] == "AdamW"


def test_training_service_draft_resource_preview_does_not_commit_configuration(
    monkeypatch,
) -> None:
    service, training = _service()
    existing_model = object()
    existing_option = object()
    training.model_holder = existing_model
    training.training_option = existing_option
    request = TrainingResourcePreviewRequest(
        request_generation=2,
        publication_generation=9,
        model_name="EEGNet",
        model_params={},
        device="cpu",
        batch_size=16,
        optimizer="Adam",
    )
    context = resource_guard.TrainingResourcePreviewContext(
        input_shape=(22, 256),
        sample_count=128,
        class_count=4,
        sampling_frequency=250.0,
    )
    expected = TrainingResourcePreviewResult(
        request_generation=2,
        publication_generation=9,
        requested_batch_size=16,
        suggested_batch_size=16,
        estimated_vram_bytes=0,
        available_vram_bytes=None,
        risk_level=resource_guard.RISK_SAFE,
        vram_known=False,
        warning=None,
    )
    captured: dict[str, Any] = {}

    def preview(draft, preview_context, *, model_holder=None):
        captured["request"] = draft
        captured["context"] = preview_context
        captured["model_holder"] = model_holder
        return expected

    monkeypatch.setattr(training_service_module, "preview_training_resources", preview)

    result = service.get_resource_preview(request, context)

    assert result is expected
    assert captured["request"] is request
    assert captured["context"] is context
    assert captured["model_holder"] is not existing_model
    assert training.model_holder is existing_model
    assert training.training_option is existing_option


def test_training_service_preview_cancel_after_blocked_model_build_skips_estimate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _training = _service()
    request = TrainingResourcePreviewRequest(
        request_generation=3,
        publication_generation=9,
        model_name="EEGNet",
        model_params={},
        device="cuda:0",
        batch_size=16,
        optimizer="Adam",
    )
    context = resource_guard.TrainingResourcePreviewContext(
        input_shape=(2, 64),
        sample_count=8,
        class_count=2,
        sampling_frequency=128.0,
    )
    model_build_started = Event()
    release_model_build = Event()
    preview = MagicMock(return_value=MagicMock())

    def blocked_model_build(_request):
        model_build_started.set()
        assert release_model_build.wait(timeout=2.0)
        return object()

    monkeypatch.setattr(
        service,
        "_build_resource_preview_model_holder",
        blocked_model_build,
    )
    monkeypatch.setattr(training_service_module, "preview_training_resources", preview)
    registry = OwnedWorkRegistry()
    operation = registry.begin(
        OwnedWorkKind.TRAINING_RESOURCE_PREVIEW,
        cancellable=True,
        command_identity="training_resource_preview",
    )
    errors: list[BaseException] = []

    def run_preview() -> None:
        registry.claim_start(
            operation.operation_id,
            kind=OwnedWorkKind.TRAINING_RESOURCE_PREVIEW,
            command_identity="training_resource_preview",
        )
        try:
            with registry.bind(operation.operation_id):
                service.get_resource_preview(request, context)
        except BaseException as exc:
            errors.append(exc)

    worker = Thread(target=run_preview, name="blocked-training-preview-model")
    worker.start()
    assert model_build_started.wait(timeout=2.0)

    assert registry.cancel(operation.operation_id) is True
    release_model_build.set()
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], OwnedOperationCancelledError)
    assert registry.snapshot(operation.operation_id).phase is OwnedWorkPhase.CANCELLED
    preview.assert_not_called()


def test_training_service_preview_instantiates_tiny_real_eegnet_estimate(
    monkeypatch,
) -> None:
    service, training = _service()
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_gpu_vram_status",
        staticmethod(
            lambda _gpu_idx=None: {
                "available_bytes": None,
                "total_bytes": None,
                "used_bytes": None,
                "reason": "gpu_memory_query_failed",
            }
        ),
    )
    request = TrainingResourcePreviewRequest(
        request_generation=1,
        publication_generation=3,
        model_name="EEGNet",
        model_params={"f1": 2, "f2": 4, "d": 1},
        device="cuda:0",
        batch_size=2,
        optimizer="Adam",
    )
    context = resource_guard.TrainingResourcePreviewContext(
        input_shape=(2, 256),
        sample_count=4,
        class_count=2,
        sampling_frequency=128.0,
    )

    result = service.get_resource_preview(request, context)

    assert result.estimated_vram_bytes > 0
    assert result.model_parameter_estimate_reliable is True
    assert result.model_parameter_estimate_source == "instantiated"
    assert training.model_holder is None
    assert training.training_option is None


def test_training_service_maps_auto_device_without_facade(monkeypatch) -> None:
    service, training = _service()

    def cuda_device_is_usable(_gpu_idx: int | None) -> tuple[bool, str | None]:
        return True, None

    monkeypatch.setattr(
        training_option_module,
        "is_cuda_device_usable",
        cuda_device_is_usable,
    )
    _message, payload = _expect_payload(
        service.handle_configure_training(
            ConfigureTrainingCommand(
                epoch=3,
                batch_size=8,
                learning_rate=0.002,
                device="auto",
            ),
        ),
    )

    option = training.training_option
    assert option is not None
    assert option.use_cpu is False
    assert option.gpu_idx == 0
    assert payload["training_option"]["device"] == "cuda:0"


def test_training_service_start_stop_and_clear_history() -> None:
    service, training = _service()

    start_message, start_payload = _expect_payload(
        service.handle_train(
            TrainCommand(
                append=False,
                interactive=False,
                resource_preflight_confirmed=True,
            ),
        ),
    )
    stop = service.handle_stop_training(StopTrainingCommand(wait_timeout=1.5))
    clear_message, clear_payload = _expect_payload(
        service.handle_clear_training_history(ClearTrainingHistoryCommand()),
    )

    assert start_message == "Training completed."
    assert start_payload["append"] is False
    assert start_payload["interactive"] is False
    assert start_payload["training_handoff_generation"] == 1
    assert start_payload["resource_preflight"]["dataset_bytes"] == 0
    assert start_payload["resource_preflight"]["risk_level"] == "safe"
    assert stop == (
        "Training stopped.",
        {
            "stopped": True,
            "wait_timeout": 1.5,
            "terminal_outcome": "completed",
            "training_run": {
                "trainer_id": "test-trainer",
                "run_id": 1,
            },
        },
    )
    assert training.started is True
    assert training.started_append is False
    assert training.started_interactive is False
    assert training.stopped is True
    assert training.stop_wait_timeout == 1.5
    assert training.history_cleared is True
    assert training.notifications == ["training_updated"]
    assert clear_message == "Training history cleared."
    assert clear_payload == {
        "plan_count_before": 2,
        "run_count_before": 3,
        "finished_run_count_before": 1,
    }


def test_training_service_rejects_missing_terminal_handoff_generation() -> None:
    service, training = _service()
    training.start_training = MagicMock(return_value=None)  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="handoff generation"):
        service.handle_train(TrainCommand())


@pytest.mark.parametrize(
    "failure_message",
    [
        "Error: CUDA out of memory during training. Reduce batch size.",
        "Error: training data loader failed",
    ],
)
def test_synchronous_training_failure_is_not_reported_as_success(
    failure_message: str,
) -> None:
    training = _TrainingController()
    training.progress_text = failure_message
    training.terminal_outcome = TrainingTerminalOutcome(
        state=TrainingOutcomeState.FAILED,
        run=TrainingRunIdentity(trainer_id="failed-trainer", run_id=1),
        detail=failure_message.removeprefix("Error: "),
    )
    service = TrainingCommandService(
        training=training,
        training_runtime=_TrainingRuntime(training),
        get_state=lambda: (_ for _ in ()).throw(
            AssertionError("terminal failure must not rebuild application state")
        ),
    )

    with pytest.raises(
        ApplicationError,
        match=failure_message.removeprefix("Error: "),
    ) as raised:
        service.handle_train(
            TrainCommand(
                interactive=False,
                resource_preflight_confirmed=True,
            ),
        )

    assert training.started is True
    assert raised.value.error_type is ErrorType.TRAINING
    assert raised.value.recoverable is True
    assert raised.value.diagnostics["training_failed"] is True
    assert raised.value.diagnostics["cuda_oom"] is (
        "out of memory" in failure_message.lower()
    )


@pytest.mark.parametrize(
    ("state", "message"),
    [
        (TrainingOutcomeState.CANCELLED, "Training was cancelled."),
        (TrainingOutcomeState.UNKNOWN, "Training outcome could not be verified."),
    ],
)
def test_synchronous_training_requires_verified_completion(
    state: TrainingOutcomeState,
    message: str,
) -> None:
    training = _TrainingController()
    training.terminal_outcome = TrainingTerminalOutcome(
        state=state,
        run=TrainingRunIdentity(trainer_id="test-trainer", run_id=2),
    )
    service = TrainingCommandService(
        training=training,
        training_runtime=_TrainingRuntime(training),
        get_state=lambda: _state(),
    )

    with pytest.raises(ApplicationError, match=message):
        service.handle_train(
            TrainCommand(
                interactive=False,
                resource_preflight_confirmed=True,
            )
        )


def test_stop_command_reports_requested_while_worker_is_still_alive() -> None:
    training = _TrainingController()
    training.stop_result = False
    training.terminal_outcome = TrainingTerminalOutcome(
        state=TrainingOutcomeState.STOP_REQUESTED,
        run=TrainingRunIdentity(trainer_id="test-trainer", run_id=3),
    )
    service = TrainingCommandService(
        training=training,
        training_runtime=_TrainingRuntime(training),
        get_state=lambda: _state(),
    )

    message, diagnostics = _expect_payload(
        service.handle_stop_training(StopTrainingCommand(wait_timeout=0.01))
    )

    assert message == "Training stop requested."
    assert diagnostics == {
        "stopped": False,
        "wait_timeout": 0.01,
        "terminal_outcome": "stop_requested",
        "training_run": {"trainer_id": "test-trainer", "run_id": 3},
    }


def test_training_service_blocks_training_when_dataset_exceeds_available_ram(
    monkeypatch,
) -> None:
    service, training = _service()
    training.resource_context = {
        "datasets": [_Dataset(_EpochData(data_nbytes=10_000, label_nbytes=1_000))],
        "training_option": SimpleNamespace(
            use_cpu=True, bs=4, get_device=lambda: "cpu"
        ),
    }
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 5_000)
    monkeypatch.setattr(resource_guard, "available_vram_bytes", lambda _idx=None: None)

    with pytest.raises(PreconditionError, match="available RAM"):
        service.handle_train(TrainCommand())

    assert training.started is False


def test_training_service_blocks_cuda_training_when_batch_exceeds_available_vram(
    monkeypatch,
) -> None:
    service, training = _service()
    training.resource_context = {
        "datasets": [
            _Dataset(_EpochData(data_nbytes=40_000, label_nbytes=1_000)),
        ],
        "training_option": SimpleNamespace(
            use_cpu=False,
            gpu_idx=0,
            bs=10,
            get_device=lambda: "cuda:0",
        ),
    }
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 10_000_000)
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_gpu_vram_status",
        staticmethod(
            lambda _idx=None: {
                "gpu_name": "synthetic CUDA device",
                "available_bytes": 5_000,
                "total_bytes": 10_000,
                "used_bytes": 5_000,
                "allocated_bytes": 0,
                "reserved_bytes": 0,
            },
        ),
    )

    with pytest.raises(PreconditionError, match="GPU memory"):
        service.handle_train(TrainCommand())

    assert training.started is False


def test_training_service_returns_warning_before_start_and_requires_confirmation(
    monkeypatch,
) -> None:
    service, training = _service()
    training.resource_context = {
        "datasets": [_Dataset(_EpochData(data_nbytes=10_000, label_nbytes=1_000))],
        "training_option": SimpleNamespace(
            use_cpu=True,
            bs=4,
            get_device=lambda: "cpu",
        ),
        "model_holder": _TinyModelHolder(),
    }
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 90_000)

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as raised:
        service.handle_train(TrainCommand(confirmed=True))

    assert training.started is False
    assert raised.value.diagnostics["resource_preflight"]["risk_level"] == "warning"
    token = raised.value.diagnostics["resource_preflight"]["confirmation_token"]

    message, payload = _expect_payload(
        service.handle_train(
            TrainCommand(
                confirmed=True,
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            ),
        ),
    )

    assert message == "Training started."
    assert training.started is True
    assert payload["resource_preflight"]["risk_level"] == "warning"


def test_training_warning_issues_one_shot_backend_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, training = _service()
    training.resource_context = _receipt_training_context()
    monkeypatch.setattr(
        training_service_module,
        "check_training_resource_preflight",
        _warning_training_preflight,
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as raised:
        service.handle_train(TrainCommand(confirmed=True))

    receipt = raised.value.diagnostics["resource_preflight"]
    token = receipt["confirmation_token"]
    assert receipt["confirmation_command"] == "start_training"
    assert len(receipt["configuration_fingerprint"]) == 64
    assert len(receipt["preflight_fingerprint"]) == 64
    assert len(receipt["scope_fingerprint"]) == 64
    assert receipt["confirmation_ttl_seconds"] > 0
    assert training.start_count == 0

    _message, payload = _expect_payload(
        service.handle_train(
            TrainCommand(
                confirmed=True,
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )
    )

    assert training.start_count == 1
    assert payload["resource_preflight"]["confirmation_receipt_reused"] is True

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as replayed:
        service.handle_train(
            TrainCommand(
                confirmed=True,
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )

    assert training.start_count == 1
    assert (
        replayed.value.diagnostics["resource_preflight"]["confirmation_token"] != token
    )


def test_training_receipt_is_consumed_once_under_concurrent_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, training = _service()
    training.resource_context = _receipt_training_context()
    monkeypatch.setattr(
        training_service_module,
        "check_training_resource_preflight",
        _warning_training_preflight,
    )
    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as raised:
        service.handle_train(TrainCommand(confirmed=True))
    token = raised.value.diagnostics["resource_preflight"]["confirmation_token"]

    authority = service._resource_receipts
    original_matching = authority._matching

    def delayed_matching(token_value, preflight):
        receipt = original_matching(token_value, preflight)
        if receipt is not None:
            sleep(0.01)
        return receipt

    monkeypatch.setattr(authority, "_matching", delayed_matching)
    worker_count = 8
    ready = Barrier(worker_count)

    def replay() -> bool:
        ready.wait()
        try:
            service.handle_train(
                TrainCommand(
                    confirmed=True,
                    resource_preflight_confirmed=True,
                    resource_preflight_token=token,
                )
            )
        except resource_guard.ResourceConfirmationRequiredError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        starts = list(executor.map(lambda _index: replay(), range(worker_count)))

    assert starts.count(True) == 1
    assert training.start_count == 1


@pytest.mark.parametrize(
    "mutate_scope",
    [
        pytest.param(
            lambda context: setattr(context["training_option"], "bs", 16),
            id="batch-size",
        ),
        pytest.param(
            lambda context: context["model_holder"].model_params_map.update(
                {"input_size": 512}
            ),
            id="model",
        ),
        pytest.param(
            lambda context: setattr(
                context["datasets"][0].epoch_data,
                "data",
                _ArrayLike(nbytes=10_000, shape=(20, 500)),
            ),
            id="input-shape",
        ),
        pytest.param(
            lambda context: context.__setitem__(
                "datasets",
                [_Dataset(_EpochData(data_nbytes=10_000, label_nbytes=1_000))],
            ),
            id="dataset-instance",
        ),
    ],
)
def test_training_receipt_scope_change_requires_fresh_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    mutate_scope,
) -> None:
    service, training = _service()
    context = _receipt_training_context()
    training.resource_context = context
    monkeypatch.setattr(
        training_service_module,
        "check_training_resource_preflight",
        _warning_training_preflight,
    )
    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as raised:
        service.handle_train(TrainCommand(confirmed=True))
    old_receipt = raised.value.diagnostics["resource_preflight"]

    mutate_scope(context)

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as refreshed:
        service.handle_train(
            TrainCommand(
                confirmed=True,
                resource_preflight_confirmed=True,
                resource_preflight_token=old_receipt["confirmation_token"],
            )
        )

    new_receipt = refreshed.value.diagnostics["resource_preflight"]
    assert new_receipt["confirmation_token"] != old_receipt["confirmation_token"]
    assert new_receipt["scope_fingerprint"] != old_receipt["scope_fingerprint"]
    assert training.start_count == 0


def test_training_receipt_expiry_requires_fresh_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, training = _service()
    training.resource_context = _receipt_training_context()
    monkeypatch.setattr(
        training_service_module,
        "check_training_resource_preflight",
        _warning_training_preflight,
    )
    monotonic_now = 100.0
    monkeypatch.setattr(
        training_receipt_module.time,
        "monotonic",
        lambda: monotonic_now,
    )
    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as raised:
        service.handle_train(TrainCommand(confirmed=True))
    old_token = raised.value.diagnostics["resource_preflight"]["confirmation_token"]
    monotonic_now += training_receipt_module.TRAINING_PREFLIGHT_RECEIPT_TTL_SECONDS

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as refreshed:
        service.handle_train(
            TrainCommand(
                confirmed=True,
                resource_preflight_confirmed=True,
                resource_preflight_token=old_token,
            )
        )

    assert (
        refreshed.value.diagnostics["resource_preflight"]["confirmation_token"]
        != old_token
    )
    assert training.start_count == 0


def test_training_blocking_preflight_cannot_use_warning_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, training = _service()
    training.resource_context = _receipt_training_context()
    monkeypatch.setattr(
        training_service_module,
        "check_training_resource_preflight",
        _warning_training_preflight,
    )
    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as raised:
        service.handle_train(TrainCommand(confirmed=True))
    token = raised.value.diagnostics["resource_preflight"]["confirmation_token"]

    monkeypatch.setattr(
        training_service_module,
        "check_training_resource_preflight",
        lambda *_args: resource_guard.ResourcePreflightResult(
            issues=("Training exceeds available GPU memory.",),
            warnings=(),
            diagnostics={"risk_level": "blocking"},
        ),
    )

    with pytest.raises(PreconditionError, match="exceeds available GPU memory"):
        service.handle_train(
            TrainCommand(
                confirmed=True,
                resource_preflight_confirmed=True,
                resource_preflight_token=token,
            )
        )

    assert training.start_count == 0


def test_training_service_keeps_unavailable_cuda_memory_explicit(
    monkeypatch,
) -> None:
    service, training = _service()
    training.resource_context = {
        "datasets": [],
        "training_option": SimpleNamespace(
            use_cpu=False,
            gpu_idx=0,
            bs=32,
            get_device=lambda: "cuda:0",
        ),
    }
    monkeypatch.setattr(resource_guard, "available_ram_bytes", lambda: 10_000_000)
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_gpu_vram_status",
        staticmethod(lambda _idx=None: {"available_bytes": None, "gpu_name": None}),
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError) as raised:
        service.handle_train(TrainCommand(confirmed=True))

    diagnostics = raised.value.diagnostics["resource_preflight"]
    assert diagnostics["risk_level"] == "unknown"
    assert diagnostics["requires_confirmation"] is True
    assert "Unable to estimate GPU memory" in diagnostics["message"]
    assert training.started is False


def test_training_service_rechecks_unknown_preflight_before_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, training = _service()
    calls = 0

    def _recovering_preflight(
        _datasets: Any,
        _training_option: Any,
        _model_holder: Any,
    ) -> resource_guard.ResourcePreflightResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            return resource_guard.ResourcePreflightResult(
                issues=(),
                warnings=(),
                unknowns=("Unable to query GPU memory.",),
                diagnostics={"vram_risk_level": resource_guard.RISK_UNKNOWN},
            )
        return resource_guard.ResourcePreflightResult(
            issues=(),
            warnings=(),
            unknowns=(),
            diagnostics={"vram_risk_level": resource_guard.RISK_SAFE},
        )

    monkeypatch.setattr(
        training_service_module,
        "check_training_resource_preflight",
        _recovering_preflight,
    )

    with pytest.raises(resource_guard.ResourceConfirmationRequiredError):
        service.handle_train(TrainCommand())

    message, payload = _expect_payload(service.handle_train(TrainCommand()))

    assert calls == 2
    assert training.start_count == 1
    assert message == "Training started."
    assert payload["resource_preflight"]["risk_level"] == resource_guard.RISK_SAFE
