"""Focused tests for training command handlers."""

from __future__ import annotations

from typing import Any, cast

import pytest

from XBrainLab.backend.application.commands import (
    ClearTrainingHistoryCommand,
    ConfigureTrainingCommand,
    StopTrainingCommand,
    TrainCommand,
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

    def set_model_holder(self, holder: Any) -> None:
        self.model_holder = holder

    def set_training_option(self, option: Any) -> None:
        self.training_option = option

    def start_training(self, *, append: bool = True, interactive: bool = True) -> None:
        self.started = True
        self.started_append = append
        self.started_interactive = interactive

    def stop_training(self) -> None:
        self.stopped = True

    def clear_history(self) -> None:
        self.history_cleared = True

    def notify(self, event_name: str) -> None:
        self.notifications.append(event_name)


class _TrainingManager:
    def __init__(self) -> None:
        self.model_holder: Any | None = object()
        self.training_option: Any | None = object()
        self.saliency_params: dict[str, Any] | None = {"SmoothGrad": {}}


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
    stop = service.handle_stop_training(StopTrainingCommand())
    clear_message, clear_payload = _expect_payload(
        service.handle_clear_training_history(ClearTrainingHistoryCommand()),
    )

    assert start_message == "Training started."
    assert start_payload == {"append": False, "interactive": False}
    assert stop == "Training stop requested."
    assert training.started is True
    assert training.started_append is False
    assert training.started_interactive is False
    assert training.stopped is True
    assert training.history_cleared is True
    assert training.notifications == ["training_updated"]
    assert clear_message == "Training history cleared."
    assert clear_payload == {
        "plan_count_before": 2,
        "run_count_before": 3,
        "finished_run_count_before": 1,
    }


def test_training_service_clears_configuration() -> None:
    service, training = _service()
    manager = _TrainingManager()

    service.clear_configuration(manager)

    assert manager.model_holder is None
    assert manager.training_option is None
    assert manager.saliency_params is None
    assert training.notifications == ["config_changed"]
