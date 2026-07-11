"""Focused tests for training command handlers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from XBrainLab.backend.application import resource_guard
from XBrainLab.backend.application.commands import (
    ClearTrainingHistoryCommand,
    ConfigureTrainingCommand,
    StopTrainingCommand,
    TrainCommand,
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
from XBrainLab.backend.application.training_service import (
    HandlerResult,
    TrainingCommandService,
)
from XBrainLab.backend.training import option as training_option_module


class _TrainingController:
    def __init__(self) -> None:
        self.model_holder: Any | None = None
        self.training_option: Any | None = None
        self.started = False
        self.stopped = False
        self.history_cleared = False
        self.notifications: list[str] = []
        self.resource_context: dict[str, Any] | None = None

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

    def start_training(self, *, append: bool = True, interactive: bool = True) -> None:
        self.started = True
        self.started_append = append
        self.started_interactive = interactive

    def stop_training(self, wait_timeout: float | None = None) -> bool:
        self.stopped = True
        self.stop_wait_timeout = wait_timeout
        return True

    def clear_history(self) -> None:
        self.history_cleared = True

    def notify(self, event_name: str) -> None:
        self.notifications.append(event_name)

    def get_resource_preflight_context(self) -> dict[str, Any]:
        return dict(self.resource_context or {})


class _TrainingManager:
    def __init__(self) -> None:
        self.model_holder: Any | None = object()
        self.training_option: Any | None = object()
        self.saliency_params: dict[str, Any] | None = {"SmoothGrad": {}}


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


def _state() -> ApplicationStateSnapshot:
    return ApplicationStateSnapshot(
        pipeline_stage="dataset_ready",
        raw=RawStateSnapshot(),
        preprocessed=PreprocessedStateSnapshot(),
        epoch=EpochStateSnapshot(),
        dataset=DatasetStateSnapshot(available=True, count=1),
        training=TrainingStateSnapshot(),
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
    return TrainingCommandService(training=training, get_state=_state), training


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
    assert service.model_name(training.model_holder) == "EEGNet"
    assert option_message == "Training configured."
    assert training.training_option is not None
    assert option_payload["training_option"] == {
        "epoch": 2,
        "batch_size": 4,
        "learning_rate": 0.001,
        "repeat": 1,
        "device": "cpu",
        "optimizer": "SGD",
        "optimizer_params": {},
        "evaluation_option": "Last Epoch",
        "checkpoint_epoch": 0,
        "output_dir": "./tmp-output",
    }


def test_training_service_maps_case_insensitive_model_without_facade() -> None:
    service, training = _service()

    message = service.handle_configure_training(
        ConfigureTrainingCommand(model_name="EEGNET"),
    )

    assert message == "Model configured: EEGNET."
    assert training.model_holder is not None
    assert service.model_name(training.model_holder) == "EEGNet"


def test_training_service_rejects_unknown_model_without_facade() -> None:
    service, _training = _service()

    with pytest.raises(ValueError, match="Unknown model architecture"):
        service.handle_configure_training(
            ConfigureTrainingCommand(model_name="nonexistent_model"),
        )


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


def test_incomplete_training_configuration_does_not_mutate_model() -> None:
    service, training = _service()
    existing_model = object()
    existing_option = object()
    training.model_holder = existing_model
    training.training_option = existing_option

    with pytest.raises(PreconditionError, match="epoch, batch_size"):
        service.handle_configure_training(
            ConfigureTrainingCommand(
                model_name="EEGNet",
                epoch=3,
                batch_size=8,
            ),
        )

    assert training.model_holder is existing_model
    assert training.training_option is existing_option


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"optimizer": "mystery"}, "Unknown optimizer"),
        ({"device": "cuda:not-an-index"}, "Unknown training device"),
        ({"evaluation_option": "mystery"}, "Unknown training evaluation"),
        ({"epoch": 0}, "epoch must be greater than zero"),
        ({"batch_size": 0}, "batch_size must be greater than zero"),
        ({"learning_rate": 0.0}, "learning_rate must be greater than zero"),
        ({"learning_rate": True}, "learning_rate must be greater than zero"),
        ({"repeat": 0}, "repeat must be greater than zero"),
        ({"save_checkpoints_every": -1}, "save_checkpoints_every cannot be negative"),
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
        service.handle_train(TrainCommand(append=False, interactive=False)),
    )
    stop = service.handle_stop_training(StopTrainingCommand(wait_timeout=1.5))
    clear_message, clear_payload = _expect_payload(
        service.handle_clear_training_history(ClearTrainingHistoryCommand()),
    )

    assert start_message == "Training started."
    assert start_payload["append"] is False
    assert start_payload["interactive"] is False
    assert start_payload["resource_preflight"]["dataset_bytes"] == 0
    assert stop == (
        "Training stopped.",
        {"stopped": True, "wait_timeout": 1.5},
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


def test_training_service_clears_configuration() -> None:
    service, training = _service()
    manager = _TrainingManager()

    service.clear_configuration(manager)

    assert manager.model_holder is None
    assert manager.training_option is None
    assert manager.saliency_params is None
    assert training.notifications == ["config_changed"]
