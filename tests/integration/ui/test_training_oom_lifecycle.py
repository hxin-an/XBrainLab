"""Real UI-to-worker coverage for recoverable CUDA OOM training failures."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import numpy as np
import torch
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMainWindow

from XBrainLab.backend.application import (
    ApplicationService,
    AttachLabelsCommand,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    GenerateDatasetCommand,
    LoadDataCommand,
    PreprocessCommand,
    PreprocessOperation,
)
from XBrainLab.backend.application.runtime import get_application_service
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import training_plan as training_plan_module
from XBrainLab.backend.training.record.eval import EvalRecord
from XBrainLab.backend.training.training_plan import TrainingPlanHolder
from XBrainLab.backend.training_state_contract import TrainingOutcomeState
from XBrainLab.ui.async_command_runner import application_command_registry
from XBrainLab.ui.panels.training.panel import TrainingPanel

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "data"


def _prepare_real_training_service(tmp_path: Path) -> ApplicationService:
    service = get_application_service(Study())
    gdf_path = str(FIXTURE_ROOT / "A01T.gdf")
    label_path = str(FIXTURE_ROOT / "label" / "A01T.mat")

    assert service.execute(LoadDataCommand(paths=[gdf_path])).ok
    assert service.execute(
        AttachLabelsCommand(
            mapping={"A01T.gdf": label_path},
            label_paths=[label_path],
        )
    ).ok
    assert service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.BANDPASS,
            low_freq=4,
            high_freq=38,
        )
    ).ok
    assert service.execute(CreateEpochCommand(0, 4, event_ids=["1", "2", "3", "4"])).ok
    assert service.execute(
        GenerateDatasetCommand(
            test_ratio=0.2,
            val_ratio=0.2,
            split_strategy="trial",
            training_mode="individual",
        )
    ).ok
    assert service.execute(ConfigureTrainingCommand(model_name="EEGNet")).ok
    assert service.execute(
        ConfigureTrainingCommand(
            output_dir=str(tmp_path / "oom-ui-output"),
            device="cpu",
            epoch=1,
            batch_size=16,
            learning_rate=0.001,
            save_checkpoints_every=0,
            evaluation_option="val_acc",
        )
    ).ok
    return service


def test_training_panel_recovers_after_async_cuda_oom(
    qtbot,
    tmp_path: Path,
    monkeypatch,
    request,
) -> None:
    """An OOM inside the real trainer thread must become a stable UI failure."""
    service = _prepare_real_training_service(tmp_path)

    def close_service() -> None:
        service.wait_for_background_tasks(timeout=10.0)
        service.close()

    request.addfinalizer(close_service)
    study = service.study
    lifecycle_events: list[str] = []
    training_controller = study.get_controller("training")
    training_controller.subscribe(
        "training_started",
        lambda: lifecycle_events.append("started"),
    )
    training_controller.subscribe(
        "training_stopped",
        lambda: lifecycle_events.append("stopped"),
    )
    host = QMainWindow()
    cast(Any, host).study = study
    panel = TrainingPanel(
        parent=host,
        controller=training_controller,
        dataset_controller=study.get_controller("dataset"),
        preprocess_controller=study.get_controller("preprocess"),
    )
    host.setCentralWidget(panel)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    panel.sidebar.check_ready_to_train()
    assert panel.sidebar.btn_start.isEnabled()

    cache_release_calls: list[object] = []
    release_cuda_cache = training_plan_module.release_cuda_cache

    def record_cache_release(torch_module) -> None:
        cache_release_calls.append(torch_module)
        release_cuda_cache(torch_module)

    training_attempts = 0

    def fail_once_then_complete(
        holder: TrainingPlanHolder,
        record,
    ) -> None:
        nonlocal training_attempts
        training_attempts += 1
        if training_attempts == 1:
            raise torch.cuda.OutOfMemoryError(
                "CUDA out of memory. Tried to allocate 1.00 GiB"
            )
        while record.get_epoch() < holder.option.epoch:
            record.step()
        record.set_eval_record(
            EvalRecord(
                label=np.array([0], dtype=np.int64),
                output=np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32),
                gradient={},
                gradient_input={},
                smoothgrad={},
                smoothgrad_sq={},
                vargrad={},
                evaluation_split="test",
            )
        )

    monkeypatch.setattr(
        training_plan_module,
        "release_cuda_cache",
        record_cache_release,
    )
    monkeypatch.setattr(
        TrainingPlanHolder,
        "train_one_repeat",
        fail_once_then_complete,
    )

    qtbot.mouseClick(panel.sidebar.btn_start, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(
        lambda: (
            study.trainer is not None
            and study.trainer.get_terminal_outcome().state
            is TrainingOutcomeState.FAILED
            and not study.is_training()
        ),
        timeout=10_000,
    )
    qtbot.waitUntil(
        lambda: application_command_registry().active_count(panel.sidebar) == 0,
        timeout=5_000,
    )
    qtbot.waitUntil(
        lambda: lifecycle_events == ["started", "stopped"],
        timeout=5_000,
    )
    qtbot.wait(250)
    visible_log = panel.log_text.toPlainText()

    outcome = study.trainer.get_terminal_outcome()
    assert outcome.state is TrainingOutcomeState.FAILED
    assert outcome.detail is not None
    assert "CUDA out of memory during training" in outcome.detail
    assert cache_release_calls == [torch]
    assert panel.sidebar.btn_stop.isEnabled() is False
    assert panel.sidebar.btn_start.isEnabled() is True
    assert "Training failed:" in visible_log, visible_log
    assert "batch size" in visible_log.lower()
    assert "input length" in visible_log.lower()

    qtbot.mouseClick(panel.sidebar.btn_start, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(
        lambda: (
            study.trainer is not None
            and study.trainer.get_terminal_outcome().state
            is TrainingOutcomeState.COMPLETED
            and not study.is_training()
        ),
        timeout=10_000,
    )
    qtbot.waitUntil(
        lambda: application_command_registry().active_count(panel.sidebar) == 0,
        timeout=5_000,
    )
    qtbot.waitUntil(
        lambda: lifecycle_events == ["started", "stopped", "started", "stopped"],
        timeout=5_000,
    )
    qtbot.wait(250)

    trainer = study.trainer
    assert trainer is not None
    holders = trainer.get_training_plan_holders()
    assert [holder.is_finished() for holder in holders] == [False, True]
    assert training_attempts == 2
    assert trainer.get_terminal_outcome().state is TrainingOutcomeState.COMPLETED
    assert panel.sidebar.btn_stop.isEnabled() is False
    assert panel.sidebar.btn_start.isEnabled() is True
    assert panel.log_text.toPlainText().count("CUDA out of memory during training") == 1
    assert service.wait_for_background_tasks(timeout=10.0)
